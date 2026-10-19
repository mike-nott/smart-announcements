"""Switch entities for Smart Announcements controls."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

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

    entity_reg = er.async_get(hass)
    from .config_flow import get_person_friendly_name

    people = [p for p in config.get(CONF_PEOPLE, []) if p.get("person_entity")]
    rooms = [r for r in config.get(CONF_ROOMS, []) if r.get("area_id") and r.get("room_name")]

    # Default unique IDs: smart_announcements_<name> for both people and rooms
    person_ids = {
        p["person_entity"]: f"{DOMAIN}_{p['person_entity'].replace('person.', '').lower().replace(' ', '_')}"
        for p in people
    }
    room_ids = {
        r["area_id"]: f"{DOMAIN}_{r['room_name'].lower().replace(' ', '_')}"
        for r in rooms
    }

    # A person and a room with the same name would share an ID. The switch that
    # already exists keeps it so automations keep working; the other is renamed.
    for area_id, room_id in room_ids.items():
        for person_entity, person_id in person_ids.items():
            if room_id != person_id:
                continue
            existing_id = entity_reg.async_get_entity_id("switch", DOMAIN, room_id)
            existing = entity_reg.async_get(existing_id) if existing_id else None
            if existing and existing.original_icon == "mdi:volume-high":
                person_ids[person_entity] = f"{DOMAIN}_person_{person_entity.replace('person.', '')}"
            else:
                room_ids[area_id] = f"{DOMAIN}_room_{area_id}"
            _LOGGER.warning(
                "Person %s and room %s share a name; gave one switch a distinct ID",
                person_entity, area_id,
            )

    # Create person switches (enabled by default)
    for person_config in people:
        person_entity = person_config["person_entity"]
        friendly_name = get_person_friendly_name(hass, person_entity)
        entities.append(
            PersonSwitch(hass, entry, friendly_name, person_config, person_ids[person_entity])
        )
        _LOGGER.debug("Created switch for person: %s", friendly_name)

    # Create room switches (enabled by default)
    for room_config in rooms:
        room_name = room_config["room_name"]
        entities.append(
            RoomSwitch(hass, entry, room_name, room_config, room_ids[room_config["area_id"]])
        )
        _LOGGER.debug("Created switch for room: %s", room_name)

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d announcement switches", len(entities))
    else:
        _LOGGER.warning("No switches created - check configuration")

    # Remove switches for people/rooms no longer in the config
    current_ids = {entity.unique_id for entity in entities}
    for reg_entry in er.async_entries_for_config_entry(entity_reg, entry.entry_id):
        if reg_entry.domain == "switch" and reg_entry.unique_id not in current_ids:
            entity_reg.async_remove(reg_entry.entity_id)
            _LOGGER.debug("Removed stale switch: %s", reg_entry.entity_id)


class PersonSwitch(SwitchEntity, RestoreEntity):
    """Switch to enable/disable announcements for a specific person."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        friendly_name: str,
        person_config: dict[str, Any],
        unique_id: str,
    ) -> None:
        """Initialize the person switch."""
        self.hass = hass
        self._entry = entry
        self._friendly_name = friendly_name
        self._person_config = person_config
        self._attr_is_on = True  # Enabled by default

        # Entity attributes
        self._attr_unique_id = unique_id
        self._attr_name = f"Smart Announcements {friendly_name}"
        self._attr_icon = "mdi:account-voice"

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"
        self._update_enabled_state(self._attr_is_on)

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
        _LOGGER.debug("Enabled announcements for person: %s", self._friendly_name)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off (disable/mute announcements)."""
        self._attr_is_on = False
        self._update_enabled_state(False)
        self.async_write_ha_state()
        _LOGGER.debug("Disabled announcements for person: %s", self._friendly_name)

    def _update_enabled_state(self, enabled: bool) -> None:
        """Update the enabled state in hass.data."""
        person_entity = self._person_config.get("person_entity")
        if DOMAIN in self.hass.data and self._entry.entry_id in self.hass.data[DOMAIN]:
            enabled_states = self.hass.data[DOMAIN][self._entry.entry_id].get("enabled", {})
            enabled_states.setdefault("people", {})[person_entity] = enabled


class RoomSwitch(SwitchEntity, RestoreEntity):
    """Switch to enable/disable announcements for a specific room."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        room_name: str,
        room_config: dict[str, Any],
        unique_id: str,
    ) -> None:
        """Initialize the room switch."""
        self.hass = hass
        self._entry = entry
        self._room_name = room_name
        self._room_config = room_config
        self._attr_is_on = True  # Enabled by default

        # Entity attributes
        self._attr_unique_id = unique_id
        self._attr_name = f"Smart Announcements {room_name}"
        self._attr_icon = "mdi:volume-high"

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._attr_is_on = last_state.state == "on"
        self._update_enabled_state(self._attr_is_on)

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
