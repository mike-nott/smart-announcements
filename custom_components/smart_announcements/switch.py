"""Switch entities for Smart Announcements controls."""

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

    # Create person switches (enabled by default)
    people = config.get(CONF_PEOPLE, [])
    for person_config in people:
        person_entity = person_config.get("person_entity", "")
        if person_entity:
            # Extract name from entity_id for entity naming (person.mike -> mike)
            entity_name = person_entity.replace("person.", "")
            # Get friendly name for display from HA entity
            from .config_flow import get_person_friendly_name
            entity_id = person_config.get("person_entity")
            friendly_name = get_person_friendly_name(hass, entity_id) if entity_id else entity_name.replace("_", " ").title()
            entities.append(
                PersonSwitch(hass, entry, entity_name, friendly_name, person_config)
            )
            _LOGGER.debug("Created switch for person: %s", friendly_name)

    # Create room switches (enabled by default)
    rooms = config.get(CONF_ROOMS, [])
    for room_config in rooms:
        area_id = room_config.get("area_id", "")
        room_name = room_config.get("room_name", "")
        if area_id and room_name:
            entities.append(
                RoomSwitch(hass, entry, room_name, room_config)
            )
            _LOGGER.debug("Created switch for room: %s", room_name)

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d announcement switches", len(entities))
    else:
        _LOGGER.warning("No switches created - check configuration")


class PersonSwitch(SwitchEntity):
    """Switch to enable/disable announcements for a specific person."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        entity_name: str,
        friendly_name: str,
        person_config: dict[str, Any],
    ) -> None:
        """Initialize the person switch."""
        self.hass = hass
        self._entry = entry
        self._entity_name = entity_name
        self._friendly_name = friendly_name
        self._person_config = person_config
        self._attr_is_on = True  # Enabled by default

        # Entity attributes - use entity_name for ID, friendly_name for display
        safe_name = entity_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe_name}"
        self._attr_name = f"Smart Announcements {friendly_name}"
        self._attr_icon = "mdi:account-voice"

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        # Initialize enabled state in hass.data
        self._update_enabled_state(True)

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
        attrs = {
            "type": "person",
            "person_entity": self._person_config.get("person_entity"),
            "room_tracking_entity": self._person_config.get("room_tracking_entity"),
            "language": self._person_config.get("language"),
            "tts_platform": self._person_config.get("tts_platform"),
            "tts_voice": self._person_config.get("tts_voice"),
            "enhance_with_ai": self._person_config.get("enhance_with_ai"),
            "translate_announcement": self._person_config.get("translate_announcement"),
        }
        # Only include conversation_entity if AI enhancement or translation is enabled
        if self._person_config.get("enhance_with_ai", True) or self._person_config.get("translate_announcement", False):
            attrs["conversation_entity"] = self._person_config.get("conversation_entity")
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (enable announcements)."""
        self._attr_is_on = True
        self._update_enabled_state(True)
        self.async_write_ha_state()
        _LOGGER.debug("Enabled announcements for person: %s", self._person_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (disable/mute announcements)."""
        self._attr_is_on = False
        self._update_enabled_state(False)
        self.async_write_ha_state()
        _LOGGER.debug("Disabled announcements for person: %s", self._person_name)

    def _update_enabled_state(self, enabled: bool) -> None:
        """Update the enabled state in hass.data."""
        person_entity = self._person_config.get("person_entity")
        if DOMAIN in self.hass.data and self._entry.entry_id in self.hass.data[DOMAIN]:
            enabled_states = self.hass.data[DOMAIN][self._entry.entry_id].get("enabled", {})
            enabled_states.setdefault("people", {})[person_entity] = enabled


class RoomSwitch(SwitchEntity):
    """Switch to enable/disable announcements for a specific room."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        room_name: str,
        room_config: dict[str, Any],
    ) -> None:
        """Initialize the room switch."""
        self.hass = hass
        self._entry = entry
        self._room_name = room_name
        self._room_config = room_config
        self._attr_is_on = True  # Enabled by default

        # Entity attributes
        safe_name = room_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{safe_name}"
        self._attr_name = f"Smart Announcements {room_name}"
        self._attr_icon = "mdi:volume-high"

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        # Initialize enabled state in hass.data
        self._update_enabled_state(True)

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
            "type": "room",
            "area_id": self._room_config.get("area_id"),
            "room_name": self._room_config.get("room_name"),
            "media_player": self._room_config.get("media_player"),
            "presence_sensors": self._room_config.get("presence_sensors", []),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (enable announcements)."""
        self._attr_is_on = True
        self._update_enabled_state(True)
        self.async_write_ha_state()
        _LOGGER.debug("Enabled announcements for room: %s", self._room_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (disable/mute announcements)."""
        self._attr_is_on = False
        self._update_enabled_state(False)
        self.async_write_ha_state()
        _LOGGER.debug("Disabled announcements for room: %s", self._room_name)

    def _update_enabled_state(self, enabled: bool) -> None:
        """Update the enabled state in hass.data."""
        area_id = self._room_config.get("area_id")
        if DOMAIN in self.hass.data and self._entry.entry_id in self.hass.data[DOMAIN]:
            enabled_states = self.hass.data[DOMAIN][self._entry.entry_id].get("enabled", {})
            enabled_states.setdefault("rooms", {})[area_id] = enabled
