"""Switch entities for Smart Announcements mute controls."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_PEOPLE,
    CONF_ROOMS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Smart Announcements switches from a config entry."""
    _LOGGER.debug("Setting up Smart Announcements switches")

    entities: list[SwitchEntity] = []

    # Get config data
    config = entry.data

    # Create person mute switches
    people = config.get(CONF_PEOPLE, [])
    for person_config in people:
        person_entity = person_config.get("person_entity", "")
        if person_entity:
            # Extract name from entity_id (person.mike -> mike)
            person_name = person_entity.replace("person.", "")
            entities.append(
                PersonMuteSwitch(hass, entry, person_entity, person_name)
            )
            _LOGGER.debug("Created mute switch for person: %s", person_name)

    # Create room mute switches
    rooms = config.get(CONF_ROOMS, [])
    for room_config in rooms:
        area_id = room_config.get("area_id", "")
        room_name = room_config.get("room_name", "")
        if area_id and room_name:
            entities.append(
                RoomMuteSwitch(hass, entry, area_id, room_name)
            )
            _LOGGER.debug("Created mute switch for room: %s", room_name)

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d mute switches", len(entities))
    else:
        _LOGGER.warning("No mute switches created - check configuration")


class PersonMuteSwitch(SwitchEntity):
    """Switch to mute announcements for a specific person."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        person_entity: str,
        person_name: str,
    ) -> None:
        """Initialize the person mute switch."""
        self.hass = hass
        self._entry = entry
        self._person_entity = person_entity
        self._person_name = person_name
        self._attr_is_on = False

        # Entity attributes
        safe_name = person_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe_name}_mute"
        self._attr_name = f"Smart Announcements {person_name.title()} Mute"
        self._attr_icon = "mdi:account-voice-off"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for grouping entities."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Smart Announcements",
            "manufacturer": "Custom",
            "model": "Smart Announcements",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "person_entity": self._person_entity,
            "mute_type": "person",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the mute (enable muting)."""
        self._attr_is_on = True
        self._update_mute_state(True)
        self.async_write_ha_state()
        _LOGGER.debug("Muted announcements for person: %s", self._person_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the mute (disable muting)."""
        self._attr_is_on = False
        self._update_mute_state(False)
        self.async_write_ha_state()
        _LOGGER.debug("Unmuted announcements for person: %s", self._person_name)

    def _update_mute_state(self, muted: bool) -> None:
        """Update the mute state in hass.data."""
        if DOMAIN in self.hass.data and self._entry.entry_id in self.hass.data[DOMAIN]:
            mutes = self.hass.data[DOMAIN][self._entry.entry_id].get("mutes", {})
            mutes.setdefault("people", {})[self._person_entity] = muted


class RoomMuteSwitch(SwitchEntity):
    """Switch to mute announcements for a specific room."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        area_id: str,
        room_name: str,
    ) -> None:
        """Initialize the room mute switch."""
        self.hass = hass
        self._entry = entry
        self._area_id = area_id
        self._room_name = room_name
        self._attr_is_on = False

        # Entity attributes
        safe_name = room_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe_name}_mute"
        self._attr_name = f"Smart Announcements {room_name} Mute"
        self._attr_icon = "mdi:volume-off"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for grouping entities."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Smart Announcements",
            "manufacturer": "Custom",
            "model": "Smart Announcements",
        }

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "area_id": self._area_id,
            "room_name": self._room_name,
            "mute_type": "room",
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the mute (enable muting)."""
        self._attr_is_on = True
        self._update_mute_state(True)
        self.async_write_ha_state()
        _LOGGER.debug("Muted announcements for room: %s", self._room_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the mute (disable muting)."""
        self._attr_is_on = False
        self._update_mute_state(False)
        self.async_write_ha_state()
        _LOGGER.debug("Unmuted announcements for room: %s", self._room_name)

    def _update_mute_state(self, muted: bool) -> None:
        """Update the mute state in hass.data."""
        if DOMAIN in self.hass.data and self._entry.entry_id in self.hass.data[DOMAIN]:
            mutes = self.hass.data[DOMAIN][self._entry.entry_id].get("mutes", {})
            mutes.setdefault("rooms", {})[self._area_id] = muted
