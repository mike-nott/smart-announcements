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

    def _get_person_config(self, person_entity: str) -> dict[str, Any] | None:
        """Get configuration for a person by entity ID."""
        people = self.config.get(CONF_PEOPLE, [])
        for person in people:
            if person.get("person_entity") == person_entity:
                return person
        return None

    async def async_get_person_room(self, person_entity: str) -> str | None:
        """Get the current room for a person.

        Returns the area_id of the person's current room, or None if unknown.
        Uses the configured room_tracking_entity for the person.
        """
        # Get person config to find their room tracking entity
        person_config = self._get_person_config(person_entity)
        if not person_config:
            _LOGGER.debug("No config found for person %s", person_entity)
            return None

        room_tracking_entity = person_config.get("room_tracking_entity")
        if not room_tracking_entity:
            _LOGGER.debug("No room tracking entity configured for %s", person_entity)
            return None

        # Check if person is home first
        person_state = self.hass.states.get(person_entity)
        if not person_state:
            _LOGGER.debug("Person entity %s not found", person_entity)
            return None

        if person_state.state != "home":
            _LOGGER.debug("Person %s is not home (state: %s)", person_entity, person_state.state)
            return None

        # Get the room from the tracking entity
        area_id = await self._get_area_from_entity(room_tracking_entity)

        if area_id:
            # Optionally verify with presence sensors
            if self.config.get(CONF_PRESENCE_VERIFICATION, False):
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

        _LOGGER.debug("Could not determine room for %s from entity %s", person_entity, room_tracking_entity)
        return None

    async def _get_area_from_entity(self, entity_id: str) -> str | None:
        """Get area from a room tracking entity.

        Supports entities that report area in their state (like Bermuda/ESPresense)
        or in attributes (area, room).
        """
        entity_state = self.hass.states.get(entity_id)
        if not entity_state:
            _LOGGER.debug("Room tracking entity %s not found", entity_id)
            return None

        area_reg = ar.async_get(self.hass)
        areas = {area.name.lower(): area.id for area in area_reg.async_list_areas()}

        # Method 1: State is an area name (Bermuda pattern)
        # Bermuda reports the area name directly as the state
        state_value = entity_state.state.lower()
        if state_value not in ["home", "not_home", "unknown", "unavailable", "none"]:
            # State might be an area name
            if state_value in areas:
                _LOGGER.debug(
                    "Entity %s reports area %s via state",
                    entity_id,
                    state_value,
                )
                return areas[state_value]

        # Method 2: Check for area attribute
        area_attr = entity_state.attributes.get("area")
        if area_attr:
            area_lower = area_attr.lower()
            if area_lower in areas:
                _LOGGER.debug(
                    "Entity %s reports area %s via attribute",
                    entity_id,
                    area_lower,
                )
                return areas[area_lower]

        # Method 3: Check for room attribute
        room_attr = entity_state.attributes.get("room")
        if room_attr:
            room_lower = room_attr.lower()
            if room_lower in areas:
                _LOGGER.debug(
                    "Entity %s reports area %s via room attribute",
                    entity_id,
                    room_lower,
                )
                return areas[room_lower]

        _LOGGER.debug(
            "Entity %s state '%s' does not match any area",
            entity_id,
            entity_state.state,
        )
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

    async def async_get_rooms_with_presence(self) -> list[str]:
        """Get list of room area_ids where presence sensors detect someone.

        Only checks presence sensors, ignores device trackers.
        """
        occupied = set()
        rooms = self.config.get(CONF_ROOMS, [])

        for room in rooms:
            area_id = room.get("area_id")
            if not area_id:
                continue

            presence_sensors = room.get("presence_sensors", [])
            if not presence_sensors:
                continue

            # Check if any presence sensor is on
            for sensor_id in presence_sensors:
                sensor_state = self.hass.states.get(sensor_id)
                if sensor_state and sensor_state.state == "on":
                    occupied.add(area_id)
                    _LOGGER.debug("Room %s has presence (sensor: %s)", area_id, sensor_id)
                    break

        return list(occupied)

    async def async_get_rooms_with_tracked_people(self) -> list[str]:
        """Get list of room area_ids where device trackers report people.

        Only checks device trackers, ignores presence sensors.
        """
        occupied = set()
        people = self.config.get(CONF_PEOPLE, [])

        for person in people:
            person_entity = person.get("person_entity")
            if person_entity:
                room_id = await self.async_get_person_room(person_entity)
                if room_id:
                    occupied.add(room_id)
                    _LOGGER.debug("Room %s has tracked person: %s", room_id, person_entity)

        return list(occupied)

    async def async_get_occupied_rooms(
        self, use_tracking: bool = True, use_presence: bool = True
    ) -> list[str]:
        """Get list of currently occupied room area_ids.

        Args:
            use_tracking: Include rooms where device trackers report people
            use_presence: Include rooms where presence sensors are active
        """
        occupied = set()

        if use_presence:
            presence_rooms = await self.async_get_rooms_with_presence()
            occupied.update(presence_rooms)

        if use_tracking:
            tracked_rooms = await self.async_get_rooms_with_tracked_people()
            occupied.update(tracked_rooms)

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
