"""Config flow for Smart Announcements integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    CONF_ROOM_TRACKING,
    CONF_PRESENCE_VERIFICATION,
    CONF_DEFAULT_TTS_PLATFORM,
    CONF_DEFAULT_CONVERSATION_ENTITY,
    CONF_PRE_ANNOUNCE_ENABLED,
    CONF_PRE_ANNOUNCE_URL,
    CONF_PRE_ANNOUNCE_DELAY,
    CONF_PEOPLE,
    CONF_ROOMS,
    DEFAULT_ROOM_TRACKING,
    DEFAULT_PRESENCE_VERIFICATION,
    DEFAULT_TTS_PLATFORM,
    DEFAULT_PRE_ANNOUNCE_ENABLED,
    DEFAULT_PRE_ANNOUNCE_URL,
    DEFAULT_PRE_ANNOUNCE_DELAY,
)

_LOGGER = logging.getLogger(__name__)


def get_tts_entities(hass: HomeAssistant) -> list[str]:
    """Get list of available TTS entities."""
    entity_reg = er.async_get(hass)
    return [
        entity.entity_id
        for entity in entity_reg.entities.values()
        if entity.entity_id.startswith("tts.")
    ]


def get_conversation_entities(hass: HomeAssistant) -> list[str]:
    """Get list of available conversation entities."""
    entity_reg = er.async_get(hass)
    return [
        entity.entity_id
        for entity in entity_reg.entities.values()
        if entity.entity_id.startswith("conversation.")
    ]


def get_person_entities(hass: HomeAssistant) -> list[str]:
    """Get list of person entities."""
    return [
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.startswith("person.")
    ]


def get_areas(hass: HomeAssistant) -> list[dict]:
    """Get list of areas."""
    area_reg = ar.async_get(hass)
    return [
        {"id": area.id, "name": area.name}
        for area in area_reg.async_list_areas()
    ]


def get_media_players(hass: HomeAssistant) -> list[str]:
    """Get list of media player entities."""
    return [
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.startswith("media_player.")
    ]


def get_presence_sensors(hass: HomeAssistant) -> list[str]:
    """Get list of presence/occupancy sensors."""
    entity_reg = er.async_get(hass)
    presence_sensors = []

    for entity in entity_reg.entities.values():
        if not entity.entity_id.startswith("binary_sensor."):
            continue
        # Include sensors with occupancy, presence, or motion device class
        if entity.original_device_class in ["occupancy", "presence", "motion"]:
            presence_sensors.append(entity.entity_id)

    return presence_sensors


class SmartAnnouncementsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Announcements."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize."""
        self.global_data: dict[str, Any] = {}
        self.people_data: list[dict[str, Any]] = []
        self.rooms_data: list[dict[str, Any]] = []
        self._current_person_index: int = 0
        self._current_room_index: int = 0
        self._persons_list: list[str] = []
        self._areas_list: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle step 1 - global settings."""
        errors: dict[str, str] = {}

        # Check for existing config entry
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            self.global_data = user_input
            # Initialize people and rooms lists
            self._persons_list = get_person_entities(self.hass)
            self._areas_list = get_areas(self.hass)

            if not self._persons_list:
                errors["base"] = "no_persons"
            elif not self._areas_list:
                errors["base"] = "no_areas"
            else:
                self._current_person_index = 0
                return await self.async_step_person_config()

        # Build schema
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ROOM_TRACKING, default=DEFAULT_ROOM_TRACKING
                ): BooleanSelector(),
                vol.Required(
                    CONF_PRESENCE_VERIFICATION, default=DEFAULT_PRESENCE_VERIFICATION
                ): BooleanSelector(),
                vol.Optional(CONF_DEFAULT_TTS_PLATFORM): EntitySelector(
                    EntitySelectorConfig(domain="tts")
                ),
                vol.Optional(CONF_DEFAULT_CONVERSATION_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="conversation")
                ),
                vol.Required(
                    CONF_PRE_ANNOUNCE_ENABLED, default=DEFAULT_PRE_ANNOUNCE_ENABLED
                ): BooleanSelector(),
                vol.Optional(
                    CONF_PRE_ANNOUNCE_URL, default=DEFAULT_PRE_ANNOUNCE_URL
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                vol.Optional(
                    CONF_PRE_ANNOUNCE_DELAY, default=DEFAULT_PRE_ANNOUNCE_DELAY
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=10, step=0.5, mode=NumberSelectorMode.BOX)
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_person_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle person configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store this person's config
            person_entity = self._persons_list[self._current_person_index]
            user_input["person_entity"] = person_entity
            self.people_data.append(user_input)

            # Move to next person or to rooms
            self._current_person_index += 1
            if self._current_person_index < len(self._persons_list):
                return await self.async_step_person_config()
            else:
                self._current_room_index = 0
                return await self.async_step_room_config()

        # Get current person
        person_entity = self._persons_list[self._current_person_index]
        person_name = person_entity.replace("person.", "").replace("_", " ").title()

        # Build schema for this person
        data_schema = vol.Schema(
            {
                vol.Optional("tts_platform"): EntitySelector(
                    EntitySelectorConfig(domain="tts")
                ),
                vol.Optional("tts_voice"): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT)
                ),
                vol.Optional("conversation_entity"): EntitySelector(
                    EntitySelectorConfig(domain="conversation")
                ),
                vol.Optional("language", default="english"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {"value": "english", "label": "English"},
                            {"value": "japanese", "label": "Japanese"},
                            {"value": "tagalog", "label": "Tagalog"},
                            {"value": "scottish", "label": "Scottish"},
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="person_config",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"name": person_name},
        )

    async def async_step_room_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle room configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store this room's config
            area = self._areas_list[self._current_room_index]
            user_input["area_id"] = area["id"]
            user_input["room_name"] = area["name"]
            self.rooms_data.append(user_input)

            # Move to next room or finish
            self._current_room_index += 1
            if self._current_room_index < len(self._areas_list):
                return await self.async_step_room_config()
            else:
                # All done - create entry
                return self._create_entry()

        # Get current area
        area = self._areas_list[self._current_room_index]
        area_name = area["name"]

        # Get available sensors
        presence_sensors = get_presence_sensors(self.hass)
        media_players = get_media_players(self.hass)

        # Build schema for this room
        data_schema = vol.Schema(
            {
                vol.Optional("media_player"): EntitySelector(
                    EntitySelectorConfig(domain="media_player")
                ),
                vol.Optional("presence_sensors"): EntitySelector(
                    EntitySelectorConfig(
                        domain="binary_sensor",
                        device_class=["occupancy", "presence", "motion"],
                        multiple=True,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="room_config",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"name": area_name},
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        # Combine all data
        combined_data = {
            **self.global_data,
            CONF_PEOPLE: self.people_data,
            CONF_ROOMS: self.rooms_data,
        }

        return self.async_create_entry(
            title="Smart Announcements",
            data=combined_data,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get options flow for this handler."""
        return SmartAnnouncementsOptionsFlow(config_entry)


class SmartAnnouncementsOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Smart Announcements."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Get current values
        options = self.config_entry.options
        data = self.config_entry.data

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ROOM_TRACKING,
                    default=options.get(
                        CONF_ROOM_TRACKING,
                        data.get(CONF_ROOM_TRACKING, DEFAULT_ROOM_TRACKING)
                    ),
                ): BooleanSelector(),
                vol.Required(
                    CONF_PRESENCE_VERIFICATION,
                    default=options.get(
                        CONF_PRESENCE_VERIFICATION,
                        data.get(CONF_PRESENCE_VERIFICATION, DEFAULT_PRESENCE_VERIFICATION)
                    ),
                ): BooleanSelector(),
                vol.Required(
                    CONF_PRE_ANNOUNCE_ENABLED,
                    default=options.get(
                        CONF_PRE_ANNOUNCE_ENABLED,
                        data.get(CONF_PRE_ANNOUNCE_ENABLED, DEFAULT_PRE_ANNOUNCE_ENABLED)
                    ),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_PRE_ANNOUNCE_URL,
                    default=options.get(
                        CONF_PRE_ANNOUNCE_URL,
                        data.get(CONF_PRE_ANNOUNCE_URL, DEFAULT_PRE_ANNOUNCE_URL)
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                vol.Optional(
                    CONF_PRE_ANNOUNCE_DELAY,
                    default=options.get(
                        CONF_PRE_ANNOUNCE_DELAY,
                        data.get(CONF_PRE_ANNOUNCE_DELAY, DEFAULT_PRE_ANNOUNCE_DELAY)
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=10, step=0.5, mode=NumberSelectorMode.BOX)
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors=errors,
        )
