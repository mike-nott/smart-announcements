"""Room tracking logic for Smart Announcements."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import area_registry as ar

from .const import (
    DOMAIN,
    CONF_PEOPLE,
    CONF_ROOMS,
    CONF_PRESENCE_VERIFICATION,
)

_LOGGER = logging.getLogger(__name__)


class RoomTracker:
    """Track person locations using device trackers and presence sensors."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the room tracker."""
        self.hass = hass
        self.entry = entry
        self.config = entry.data

    async def async_get_person_room(self, person_entity: str) -> str | None:
        """Get the current room for a person.

        Returns the area_id of the person's current room, or None if unknown.
        """
        person_state = self.hass.states.get(person_entity)
        if not person_state:
            _LOGGER.debug("Person entity %s not found", person_entity)
            return None

        # Check if person is home
        if person_state.state != "home":
            _LOGGER.debug("Person %s is not home (state: %s)", person_entity, person_state.state)
            return None

        # Get device trackers from person entity
        source_trackers = person_state.attributes.get("source", [])
        if isinstance(source_trackers, str):
            source_trackers = [source_trackers]

        _LOGGER.debug("Person %s has trackers: %s", person_entity, source_trackers)

        # Find a tracker that reports a room/area
        area_id = await self._get_area_from_trackers(source_trackers)

        if area_id:
            # Optionally verify with presence sensors
            if self.config.get(CONF_PRESENCE_VERIFICATION, True):
                if await self._verify_presence(area_id):
                    return area_id
                else:
                    _LOGGER.debug(
                        "Presence verification failed for %s in area %s",
                        person_entity,
                        area_id,
                    )
                    return None
            return area_id

        _LOGGER.debug("Could not determine room for %s", person_entity)
        return None

    async def _get_area_from_trackers(self, trackers: list[str]) -> str | None:
        """Get area from device tracker entities.

        Supports trackers that report area in their state (like Bermuda/ESPresense)
        or in attributes.
        """
        area_reg = ar.async_get(self.hass)
        areas = {area.name.lower(): area.id for area in area_reg.async_list_areas()}

        for tracker_id in trackers:
            tracker_state = self.hass.states.get(tracker_id)
            if not tracker_state:
                continue

            # Method 1: State is an area name (Bermuda pattern)
            # Bermuda reports the area name directly as the state
            state_value = tracker_state.state.lower()
            if state_value not in ["home", "not_home", "unknown", "unavailable"]:
                # State might be an area name
                if state_value in areas:
                    _LOGGER.debug(
                        "Tracker %s reports area %s via state",
                        tracker_id,
                        state_value,
                    )
                    return areas[state_value]

            # Method 2: Check for area attribute
            area_attr = tracker_state.attributes.get("area")
            if area_attr:
                area_lower = area_attr.lower()
                if area_lower in areas:
                    return areas[area_lower]

            # Method 3: Check for room attribute
            room_attr = tracker_state.attributes.get("room")
            if room_attr:
                room_lower = room_attr.lower()
                if room_lower in areas:
                    return areas[room_lower]

        return None

    async def _verify_presence(self, area_id: str) -> bool:
        """Verify presence in a room using configured presence sensors.

        Returns True if ANY presence sensor in the room is on.
        """
        rooms = self.config.get(CONF_ROOMS, [])

        # Find room config for this area
        room_config = None
        for room in rooms:
            if room.get("area_id") == area_id:
                room_config = room
                break

        if not room_config:
            _LOGGER.debug("No room config found for area %s", area_id)
            return True  # No config = can't verify, assume present

        presence_sensors = room_config.get("presence_sensors", [])
        if not presence_sensors:
            _LOGGER.debug("No presence sensors configured for area %s", area_id)
            return True  # No sensors = can't verify, assume present

        # Check if any sensor is on
        for sensor_id in presence_sensors:
            sensor_state = self.hass.states.get(sensor_id)
            if sensor_state and sensor_state.state == "on":
                _LOGGER.debug(
                    "Presence verified in %s by sensor %s",
                    area_id,
                    sensor_id,
                )
                return True

        _LOGGER.debug(
            "No presence sensors active in %s (checked: %s)",
            area_id,
            presence_sensors,
        )
        return False

    async def async_get_occupied_rooms(self) -> list[str]:
        """Get list of currently occupied room area_ids.

        Returns area_ids where either:
        - A person's device tracker reports they are there, OR
        - A presence sensor is active (if presence_verification is enabled)
        """
        occupied = set()
        rooms = self.config.get(CONF_ROOMS, [])

        # Check presence sensors for each room
        for room in rooms:
            area_id = room.get("area_id")
            if not area_id:
                continue

            presence_sensors = room.get("presence_sensors", [])

            # If no sensors, check if any person is tracked there
            if not presence_sensors:
                # Room has no sensors - we'll include it if we detect someone there
                # via device trackers (handled below)
                continue

            # Check if any presence sensor is on
            for sensor_id in presence_sensors:
                sensor_state = self.hass.states.get(sensor_id)
                if sensor_state and sensor_state.state == "on":
                    occupied.add(area_id)
                    _LOGGER.debug("Room %s occupied (sensor: %s)", area_id, sensor_id)
                    break

        # Also check for people tracked to rooms without sensors
        people = self.config.get(CONF_PEOPLE, [])
        for person in people:
            person_entity = person.get("person_entity")
            if person_entity:
                room_id = await self.async_get_person_room(person_entity)
                if room_id:
                    occupied.add(room_id)

        return list(occupied)

    async def async_get_people_in_room(self, area_id: str) -> list[str]:
        """Get list of people currently in a room.

        Returns list of person entity IDs.
        """
        people_in_room = []
        people = self.config.get(CONF_PEOPLE, [])

        for person in people:
            person_entity = person.get("person_entity")
            if person_entity:
                room_id = await self.async_get_person_room(person_entity)
                if room_id == area_id:
                    people_in_room.append(person_entity)

        return people_in_room
