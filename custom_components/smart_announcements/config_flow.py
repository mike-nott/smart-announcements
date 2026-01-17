"""Config flow for Smart Announcements integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.tts import get_engine_instance
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
    CONF_DEBUG_MODE,
    CONF_DEFAULT_TTS_PLATFORM,
    CONF_DEFAULT_CONVERSATION_ENTITY,
    CONF_PRE_ANNOUNCE_ENABLED,
    CONF_PRE_ANNOUNCE_URL,
    CONF_PRE_ANNOUNCE_DELAY,
    CONF_PEOPLE,
    CONF_ROOMS,
    CONF_PERSON_FRIENDLY_NAME,
    CONF_TRANSLATE_ANNOUNCEMENT,
    CONF_PROMPT_TRANSLATE,
    CONF_PROMPT_ENHANCE,
    CONF_PROMPT_BOTH,
    CONF_GROUP_ADDRESSEE,
    DEFAULT_ROOM_TRACKING,
    DEFAULT_PRESENCE_VERIFICATION,
    DEFAULT_DEBUG_MODE,
    DEFAULT_TTS_PLATFORM,
    DEFAULT_PRE_ANNOUNCE_ENABLED,
    DEFAULT_PRE_ANNOUNCE_URL,
    DEFAULT_PRE_ANNOUNCE_DELAY,
    DEFAULT_PROMPT_TRANSLATE,
    DEFAULT_PROMPT_ENHANCE,
    DEFAULT_PROMPT_BOTH,
    DEFAULT_GROUP_ADDRESSEE,
    LANGUAGE_OPTIONS,
    LANGUAGE_CODE_MAP,
)

_LOGGER = logging.getLogger(__name__)


def get_language_options() -> list[dict]:
    """Get language options formatted for selector."""
    return [
        {"value": lang, "label": lang.capitalize()}
        for lang in LANGUAGE_OPTIONS
    ]


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


def get_person_friendly_name(hass: HomeAssistant, person_entity: str) -> str:
    """Get the friendly name for a person entity."""
    state = hass.states.get(person_entity)
    if state and state.attributes.get("friendly_name"):
        return state.attributes["friendly_name"]
    # Fallback to parsing entity ID if no friendly name
    return person_entity.replace("person.", "").replace("_", " ").title()


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
        self.group_data: dict[str, Any] = {}
        self.rooms_data: list[dict[str, Any]] = []
        self._current_person_index: int = 0
        self._current_room_index: int = 0
        self._persons_list: list[str] = []
        self._areas_list: list[dict] = []
        self._current_person_data: dict[str, Any] = {}  # Temp storage for multi-step person config
        self._current_group_data: dict[str, Any] = {}  # Temp storage for multi-step group config

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial step - just initialize and go to people select."""
        errors: dict[str, str] = {}

        # Check for existing config entry
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        # Initialize people and rooms lists
        self._persons_list = get_person_entities(self.hass)
        self._areas_list = get_areas(self.hass)

        if not self._persons_list:
            errors["base"] = "no_persons"
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}), errors=errors)
        elif not self._areas_list:
            errors["base"] = "no_areas"
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}), errors=errors)

        # Go directly to people select
        return await self.async_step_people_select()

    async def async_step_people_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle step 2 - select which people to configure."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_people = user_input.get("selected_people", [])
            if not selected_people:
                errors["base"] = "no_people_selected"
            else:
                # Filter persons list to only selected ones
                self._persons_list = selected_people
                self._current_person_index = 0
                return await self.async_step_person_config()

        # Build options for multi-select
        people_options = []
        for person_entity in self._persons_list:
            person_name = get_person_friendly_name(self.hass, person_entity)
            people_options.append({
                "value": person_entity,
                "label": person_name,
            })

        data_schema = vol.Schema(
            {
                vol.Required("selected_people"): SelectSelector(
                    SelectSelectorConfig(
                        options=people_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="people_select",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_person_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle person configuration step 1 - Language and TTS Platform."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store step 1 data and proceed to step 2
            self._current_person_data = user_input
            return await self.async_step_person_voice()

        # Get current person
        person_entity = self._persons_list[self._current_person_index]
        person_name = get_person_friendly_name(self.hass, person_entity)

        # Build schema for step 1: Language, TTS Platform, Room Tracking, and AI Enhancement toggle
        data_schema = vol.Schema(
            {
                vol.Optional("room_tracking_entity"): EntitySelector(
                    EntitySelectorConfig(domain=["device_tracker", "sensor"])
                ),
                vol.Optional("language", default="english"): SelectSelector(
                    SelectSelectorConfig(
                        options=get_language_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("tts_platform"): EntitySelector(
                    EntitySelectorConfig(domain="tts")
                ),
                vol.Required("enhance_with_ai", default=True): BooleanSelector(),
                vol.Required("translate_announcement", default=False): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="person_config",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"name": person_name},
        )

    async def async_step_person_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle person configuration step 2 - Conversation Entity and TTS Voice."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Combine data from both steps
            person_entity = self._persons_list[self._current_person_index]
            combined_data = {
                **self._current_person_data,
                **user_input,
                "person_entity": person_entity,
                CONF_PERSON_FRIENDLY_NAME: get_person_friendly_name(self.hass, person_entity),
            }
            self.people_data.append(combined_data)
            self._current_person_data = {}  # Clear temp data

            # Move to next person or to group config (if multiple people) or room tracking
            self._current_person_index += 1
            if self._current_person_index < len(self._persons_list):
                return await self.async_step_person_config()
            elif len(self._persons_list) > 1:
                # Only show group settings if more than one person selected
                return await self.async_step_group_config()
            else:
                # Single person - skip group settings
                return await self.async_step_room_tracking()

        # Get current person
        person_entity = self._persons_list[self._current_person_index]
        person_name = get_person_friendly_name(self.hass, person_entity)

        # Get TTS voices based on language and platform from step 1
        tts_platform = self._current_person_data.get("tts_platform")
        language = self._current_person_data.get("language", "english")

        # Map our language names to language codes
        lang_code = LANGUAGE_CODE_MAP.get(language, "en")

        # Build voice options
        voice_options = []
        if tts_platform:
            try:
                engine = get_engine_instance(self.hass, tts_platform)
                if engine:
                    voices = engine.async_get_supported_voices(lang_code)
                    if voices:
                        for voice in voices:
                            voice_options.append({
                                "value": voice.voice_id,
                                "label": voice.name if hasattr(voice, 'name') else voice.voice_id,
                            })
            except Exception as err:
                _LOGGER.debug("Could not fetch TTS voices: %s", err)

        # Build voice selector
        if voice_options:
            voice_selector = SelectSelector(
                SelectSelectorConfig(
                    options=voice_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            # Fallback to text input if no voices found
            voice_selector = TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            )

        # Build schema for step 2: Conversation Entity (if AI enabled OR translation enabled) and TTS Voice
        enhance_with_ai = self._current_person_data.get("enhance_with_ai", True)
        translate_announcement = self._current_person_data.get("translate_announcement", False)

        schema_dict: dict[Any, Any] = {}
        # Show conversation entity if either AI enhancement or translation is enabled
        if enhance_with_ai or translate_announcement:
            schema_dict[vol.Optional("conversation_entity")] = EntitySelector(
                EntitySelectorConfig(domain="conversation")
            )
        schema_dict[vol.Optional("tts_voice")] = voice_selector

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="person_voice",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"name": person_name},
        )

    async def async_step_group_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle group settings step 1 - Language and TTS Platform."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store step 1 data and proceed to step 2
            self._current_group_data = user_input
            return await self.async_step_group_voice()

        # Build schema for step 1: Language, TTS Platform, AI Enhancement, and Translation toggles
        data_schema = vol.Schema(
            {
                vol.Optional("group_language", default="english"): SelectSelector(
                    SelectSelectorConfig(
                        options=get_language_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("group_tts_platform"): EntitySelector(
                    EntitySelectorConfig(domain="tts")
                ),
                vol.Required("group_enhance_with_ai", default=True): BooleanSelector(),
                vol.Required("group_translate_announcement", default=False): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="group_config",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_group_voice(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle group settings step 2 - Conversation Entity and TTS Voice."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Combine data from both steps
            self.group_data = {
                **self._current_group_data,
                **user_input,
            }
            self._current_group_data = {}  # Clear temp data
            return await self.async_step_room_tracking()

        # Get TTS voices based on language and platform from step 1
        tts_platform = self._current_group_data.get("group_tts_platform")
        language = self._current_group_data.get("group_language", "english")

        # Map our language names to language codes
        lang_code = LANGUAGE_CODE_MAP.get(language, "en")

        # Build voice options
        voice_options = []
        if tts_platform:
            try:
                engine = get_engine_instance(self.hass, tts_platform)
                if engine:
                    voices = engine.async_get_supported_voices(lang_code)
                    if voices:
                        for voice in voices:
                            voice_options.append({
                                "value": voice.voice_id,
                                "label": voice.name if hasattr(voice, 'name') else voice.voice_id,
                            })
            except Exception as err:
                _LOGGER.debug("Could not fetch TTS voices: %s", err)

        # Build voice selector
        if voice_options:
            voice_selector = SelectSelector(
                SelectSelectorConfig(
                    options=voice_options,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            voice_selector = TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            )

        # Build schema for step 2: Conversation Entity (if AI enabled OR translation enabled) and TTS Voice
        enhance_with_ai = self._current_group_data.get("group_enhance_with_ai", True)
        translate_announcement = self._current_group_data.get("group_translate_announcement", False)

        schema_dict: dict[Any, Any] = {}
        # Show conversation entity if either AI enhancement or translation is enabled
        if enhance_with_ai or translate_announcement:
            schema_dict[vol.Optional("group_conversation_entity")] = EntitySelector(
                EntitySelectorConfig(domain="conversation")
            )
        schema_dict[vol.Optional("group_tts_voice")] = voice_selector

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="group_voice",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_room_tracking(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle room tracking settings step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Room tracking input: %s", user_input)
            self.global_data.update(user_input)
            _LOGGER.debug("Global data after room tracking: %s", self.global_data)
            return await self.async_step_rooms_select()

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ROOM_TRACKING, default=DEFAULT_ROOM_TRACKING
                ): BooleanSelector(),
                vol.Required(
                    CONF_PRESENCE_VERIFICATION, default=DEFAULT_PRESENCE_VERIFICATION
                ): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="room_tracking",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_rooms_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle room selection step - select which rooms to configure."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_rooms = user_input.get("selected_rooms", [])
            if not selected_rooms:
                errors["base"] = "no_rooms_selected"
            else:
                # Filter areas list to only selected ones
                self._areas_list = [
                    area for area in self._areas_list
                    if area["id"] in selected_rooms
                ]
                self._current_room_index = 0
                return await self.async_step_room_config()

        # Build options for multi-select
        room_options = []
        for area in self._areas_list:
            room_options.append({
                "value": area["id"],
                "label": area["name"],
            })

        data_schema = vol.Schema(
            {
                vol.Required("selected_rooms"): SelectSelector(
                    SelectSelectorConfig(
                        options=room_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="rooms_select",
            data_schema=data_schema,
            errors=errors,
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

            # Move to next room or to pre-announce settings
            self._current_room_index += 1
            if self._current_room_index < len(self._areas_list):
                return await self.async_step_room_config()
            else:
                return await self.async_step_pre_announce()

        # Get current area
        area = self._areas_list[self._current_room_index]
        area_id = area["id"]
        area_name = area["name"]

        # Find entities assigned to this area for pre-population
        entity_reg = er.async_get(self.hass)

        # Find media players in this area
        default_media_player = None
        for entity in entity_reg.entities.values():
            if (
                entity.entity_id.startswith("media_player.")
                and entity.area_id == area_id
            ):
                default_media_player = entity.entity_id
                break  # Use first match

        # Find presence sensors in this area
        default_presence_sensors = []
        for entity in entity_reg.entities.values():
            if (
                entity.entity_id.startswith("binary_sensor.")
                and entity.area_id == area_id
                and entity.original_device_class in ["occupancy", "presence", "motion"]
            ):
                default_presence_sensors.append(entity.entity_id)

        # Check if presence verification is enabled
        presence_verification = self.global_data.get(CONF_PRESENCE_VERIFICATION, False)

        _LOGGER.debug(
            "Room config for %s: presence_verification=%s, default_media_player=%s, default_presence_sensors=%s",
            area_name,
            presence_verification,
            default_media_player,
            default_presence_sensors,
        )

        # Build schema for this room
        schema_dict: dict[Any, Any] = {
            vol.Optional("media_player"): EntitySelector(
                EntitySelectorConfig(domain="media_player")
            ),
        }

        if presence_verification:
            schema_dict[vol.Optional("presence_sensors")] = EntitySelector(
                EntitySelectorConfig(
                    domain="binary_sensor",
                    device_class=["occupancy", "presence", "motion"],
                    multiple=True,
                )
            )

        data_schema = vol.Schema(schema_dict)

        # Build suggested values for pre-population
        suggested_values: dict[str, Any] = {}
        if default_media_player:
            suggested_values["media_player"] = default_media_player
        if presence_verification and default_presence_sensors:
            suggested_values["presence_sensors"] = default_presence_sensors

        return self.async_show_form(
            step_id="room_config",
            data_schema=self.add_suggested_values_to_schema(data_schema, suggested_values),
            errors=errors,
            description_placeholders={"name": area_name},
        )

    async def async_step_pre_announce(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle pre-announce settings step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self.global_data.update(user_input)
            return self._create_entry()

        data_schema = vol.Schema(
            {
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
            step_id="pre_announce",
            data_schema=data_schema,
            errors=errors,
        )

    def _create_entry(self) -> FlowResult:
        """Create the config entry."""
        # Combine all data
        combined_data = {
            **self.global_data,
            "group": self.group_data,
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
        self.entry = config_entry
        self._selected_person_index: int | None = None
        self._selected_room_index: int | None = None
        self._new_person_entity: str | None = None
        self._new_person_data: dict[str, Any] = {}
        self._new_rooms_to_add: list[dict] = []
        self._current_new_room_index: int = 0

    async def async_step_init(self, user_input=None):
        """Show menu of what to configure."""
        data = self.entry.data
        people = data.get(CONF_PEOPLE, [])

        # Only show group_settings if more than one person configured
        menu_options = ["global_settings", "edit_people", "edit_rooms"]
        if len(people) > 1:
            menu_options.append("group_settings")
        menu_options.append("advanced_settings")

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
        )

    async def async_step_global_settings(self, user_input=None):
        """Edit global settings."""
        errors: dict[str, str] = {}
        data = self.entry.data

        if user_input is not None:
            # Update config entry data
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data={})

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_ROOM_TRACKING,
                    default=data.get(CONF_ROOM_TRACKING, DEFAULT_ROOM_TRACKING),
                ): BooleanSelector(),
                vol.Required(
                    CONF_PRESENCE_VERIFICATION,
                    default=data.get(CONF_PRESENCE_VERIFICATION, DEFAULT_PRESENCE_VERIFICATION),
                ): BooleanSelector(),
                vol.Required(
                    CONF_PRE_ANNOUNCE_ENABLED,
                    default=data.get(CONF_PRE_ANNOUNCE_ENABLED, DEFAULT_PRE_ANNOUNCE_ENABLED),
                ): BooleanSelector(),
                vol.Optional(
                    CONF_PRE_ANNOUNCE_URL,
                    default=data.get(CONF_PRE_ANNOUNCE_URL, DEFAULT_PRE_ANNOUNCE_URL),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                vol.Optional(
                    CONF_PRE_ANNOUNCE_DELAY,
                    default=data.get(CONF_PRE_ANNOUNCE_DELAY, DEFAULT_PRE_ANNOUNCE_DELAY),
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=10, step=0.5, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_DEBUG_MODE,
                    default=data.get(CONF_DEBUG_MODE, DEFAULT_DEBUG_MODE),
                ): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="global_settings",
            data_schema=options_schema,
            errors=errors,
        )

    async def async_step_edit_people(self, user_input=None):
        """Select a person to edit or add a new person."""
        errors: dict[str, str] = {}
        data = self.entry.data
        people = data.get(CONF_PEOPLE, [])

        if user_input is not None:
            selected = user_input.get("selected_person")
            if selected == "add_new":
                return await self.async_step_add_person_select()
            elif selected == "delete_person":
                return await self.async_step_delete_person_select()
            elif selected is not None:
                self._selected_person_index = int(selected)
                return await self.async_step_edit_person()

        # Build list of people with "Add Person" option
        person_options = [{"value": "add_new", "label": "+ Add Person"}]
        for idx, person in enumerate(people):
            person_entity = person.get("person_entity", "")
            # Use stored friendly name if available, otherwise get from entity
            person_name = person.get(CONF_PERSON_FRIENDLY_NAME) or get_person_friendly_name(self.hass, person_entity)
            person_options.append({"value": str(idx), "label": person_name})

        # Add "Delete Person" option at bottom
        person_options.append({"value": "delete_person", "label": "- Delete Person"})

        data_schema = vol.Schema(
            {
                vol.Required("selected_person"): SelectSelector(
                    SelectSelectorConfig(
                        options=person_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="edit_people",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_edit_person(self, user_input=None):
        """Edit a specific person's settings."""
        errors: dict[str, str] = {}
        data = self.entry.data
        people = list(data.get(CONF_PEOPLE, []))
        person = people[self._selected_person_index]
        person_entity = person.get("person_entity", "")
        # Use stored friendly name if available, otherwise get from entity
        person_name = person.get(CONF_PERSON_FRIENDLY_NAME) or get_person_friendly_name(self.hass, person_entity)

        if user_input is not None:
            # Update the person's config
            people[self._selected_person_index] = {
                **person,
                **user_input,
                CONF_PERSON_FRIENDLY_NAME: get_person_friendly_name(self.hass, person_entity),
            }
            new_data = {**data, CONF_PEOPLE: people}
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data={})

        # Get TTS voices if platform is set
        tts_platform = person.get("tts_platform")
        language = person.get("language", "english")
        lang_code = LANGUAGE_CODE_MAP.get(language, "en")

        voice_options = []
        if tts_platform:
            try:
                engine = get_engine_instance(self.hass, tts_platform)
                if engine:
                    voices = engine.async_get_supported_voices(lang_code)
                    if voices:
                        for voice in voices:
                            voice_options.append({
                                "value": voice.voice_id,
                                "label": voice.name if hasattr(voice, 'name') else voice.voice_id,
                            })
            except Exception:
                pass

        if voice_options:
            voice_selector = SelectSelector(
                SelectSelectorConfig(options=voice_options, mode=SelectSelectorMode.DROPDOWN)
            )
        else:
            voice_selector = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))

        # Build schema
        schema_dict: dict[Any, Any] = {}

        # Add room_tracking_entity with default if set
        if person.get("room_tracking_entity"):
            schema_dict[vol.Optional("room_tracking_entity", default=person.get("room_tracking_entity"))] = EntitySelector(
                EntitySelectorConfig(domain=["device_tracker", "sensor"])
            )
        else:
            schema_dict[vol.Optional("room_tracking_entity")] = EntitySelector(
                EntitySelectorConfig(domain=["device_tracker", "sensor"])
            )

        schema_dict[vol.Optional("language", default=person.get("language", "english"))] = SelectSelector(
            SelectSelectorConfig(
                options=get_language_options(),
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        schema_dict[vol.Optional("tts_platform", default=person.get("tts_platform"))] = EntitySelector(
            EntitySelectorConfig(domain="tts")
        )
        schema_dict[vol.Optional("tts_voice", default=person.get("tts_voice"))] = voice_selector
        schema_dict[vol.Required("enhance_with_ai", default=person.get("enhance_with_ai", True))] = BooleanSelector()
        schema_dict[vol.Required("translate_announcement", default=person.get("translate_announcement", False))] = BooleanSelector()

        # Show conversation entity if either AI enhancement or translation is enabled
        if person.get("enhance_with_ai", True) or person.get("translate_announcement", False):
            schema_dict[vol.Optional("conversation_entity", default=person.get("conversation_entity"))] = EntitySelector(
                EntitySelectorConfig(domain="conversation")
            )

        return self.async_show_form(
            step_id="edit_person",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={"name": person_name},
        )

    async def async_step_delete_person_select(self, user_input=None):
        """Select which person to delete."""
        errors: dict[str, str] = {}
        data = self.entry.data
        people = data.get(CONF_PEOPLE, [])

        if not people:
            return self.async_abort(reason="no_people")

        if user_input is not None:
            selected_idx = user_input.get("selected_person")
            if selected_idx is not None:
                self._selected_person_index = int(selected_idx)
                return await self.async_step_confirm_delete_person()

        # Build list of people to delete
        person_options = []
        for idx, person in enumerate(people):
            person_entity = person.get("person_entity", "")
            # Use stored friendly name if available, otherwise get from entity
            person_name = person.get(CONF_PERSON_FRIENDLY_NAME) or get_person_friendly_name(self.hass, person_entity)
            person_options.append({"value": str(idx), "label": person_name})

        data_schema = vol.Schema(
            {
                vol.Required("selected_person"): SelectSelector(
                    SelectSelectorConfig(
                        options=person_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="delete_person_select",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_confirm_delete_person(self, user_input=None):
        """Confirm deletion of person."""
        data = self.entry.data
        people = list(data.get(CONF_PEOPLE, []))
        person = people[self._selected_person_index]
        person_entity = person.get("person_entity", "")
        # Use stored friendly name if available, otherwise get from entity
        person_name = person.get(CONF_PERSON_FRIENDLY_NAME) or get_person_friendly_name(self.hass, person_entity)

        if user_input is not None:
            if user_input.get("confirm"):
                # Delete the person
                people.pop(self._selected_person_index)
                new_data = {**data, CONF_PEOPLE: people}
                self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="confirm_delete_person",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): BooleanSelector(),
            }),
            description_placeholders={"name": person_name},
        )

    async def async_step_add_person_select(self, user_input=None):
        """Select which person entity to add."""
        errors: dict[str, str] = {}
        data = self.entry.data
        people = data.get(CONF_PEOPLE, [])

        # Get all person entities and filter out already configured ones
        configured_entities = {p.get("person_entity") for p in people}
        available_persons = [
            entity_id for entity_id in get_person_entities(self.hass)
            if entity_id not in configured_entities
        ]

        if not available_persons:
            return self.async_abort(reason="no_available_people")

        if user_input is not None:
            self._new_person_entity = user_input.get("person_entity")
            return await self.async_step_add_person_config()

        # Build options
        person_options = []
        for person_entity in available_persons:
            person_name = get_person_friendly_name(self.hass, person_entity)
            person_options.append({"value": person_entity, "label": person_name})

        data_schema = vol.Schema(
            {
                vol.Required("person_entity"): SelectSelector(
                    SelectSelectorConfig(
                        options=person_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="add_person_select",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_add_person_config(self, user_input=None):
        """Configure new person - Language and TTS Platform."""
        errors: dict[str, str] = {}
        person_name = get_person_friendly_name(self.hass, self._new_person_entity)

        if user_input is not None:
            self._new_person_data = user_input
            return await self.async_step_add_person_voice()

        data_schema = vol.Schema(
            {
                vol.Optional("room_tracking_entity"): EntitySelector(
                    EntitySelectorConfig(domain=["device_tracker", "sensor"])
                ),
                vol.Optional("language", default="english"): SelectSelector(
                    SelectSelectorConfig(
                        options=get_language_options(),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional("tts_platform"): EntitySelector(
                    EntitySelectorConfig(domain="tts")
                ),
                vol.Required("enhance_with_ai", default=True): BooleanSelector(),
                vol.Required("translate_announcement", default=False): BooleanSelector(),
            }
        )

        return self.async_show_form(
            step_id="add_person_config",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"name": person_name},
        )

    async def async_step_add_person_voice(self, user_input=None):
        """Configure new person - Voice and AI settings."""
        errors: dict[str, str] = {}
        person_name = get_person_friendly_name(self.hass, self._new_person_entity)

        if user_input is not None:
            # Combine all data and save the new person
            data = self.entry.data
            people = list(data.get(CONF_PEOPLE, []))

            new_person = {
                "person_entity": self._new_person_entity,
                CONF_PERSON_FRIENDLY_NAME: get_person_friendly_name(self.hass, self._new_person_entity),
                **self._new_person_data,
                **user_input,
            }
            people.append(new_person)

            new_data = {**data, CONF_PEOPLE: people}
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)

            # Clear temp data
            self._new_person_entity = None
            self._new_person_data = {}

            return self.async_create_entry(title="", data={})

        # Get TTS voices based on language and platform from previous step
        tts_platform = self._new_person_data.get("tts_platform")
        language = self._new_person_data.get("language", "english")
        lang_code = LANGUAGE_CODE_MAP.get(language, "en")

        voice_options = []
        if tts_platform:
            try:
                engine = get_engine_instance(self.hass, tts_platform)
                if engine:
                    voices = engine.async_get_supported_voices(lang_code)
                    if voices:
                        for voice in voices:
                            voice_options.append({
                                "value": voice.voice_id,
                                "label": voice.name if hasattr(voice, 'name') else voice.voice_id,
                            })
            except Exception:
                pass

        if voice_options:
            voice_selector = SelectSelector(
                SelectSelectorConfig(options=voice_options, mode=SelectSelectorMode.DROPDOWN)
            )
        else:
            voice_selector = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))

        # Build schema - show conversation_entity if AI enhancement OR translation is enabled
        enhance_with_ai = self._new_person_data.get("enhance_with_ai", True)
        translate_announcement = self._new_person_data.get("translate_announcement", False)
        schema_dict: dict[Any, Any] = {}
        # Show conversation entity if either AI enhancement or translation is enabled
        if enhance_with_ai or translate_announcement:
            schema_dict[vol.Optional("conversation_entity")] = EntitySelector(
                EntitySelectorConfig(domain="conversation")
            )
        schema_dict[vol.Optional("tts_voice")] = voice_selector

        return self.async_show_form(
            step_id="add_person_voice",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={"name": person_name},
        )

    async def async_step_edit_rooms(self, user_input=None):
        """Select a room to edit or add a new room."""
        errors: dict[str, str] = {}
        data = self.entry.data
        rooms = data.get(CONF_ROOMS, [])

        if user_input is not None:
            selected = user_input.get("selected_room")
            if selected == "add_new":
                return await self.async_step_add_room_select()
            elif selected == "delete_room":
                return await self.async_step_delete_room_select()
            elif selected is not None:
                self._selected_room_index = int(selected)
                return await self.async_step_edit_room()

        # Build list of rooms with "Add Rooms" option
        room_options = [{"value": "add_new", "label": "+ Add Rooms"}]
        for idx, room in enumerate(rooms):
            room_name = room.get("room_name", "Unknown")
            room_options.append({"value": str(idx), "label": room_name})

        # Add "Delete Room" option at bottom
        room_options.append({"value": "delete_room", "label": "- Delete Room"})

        data_schema = vol.Schema(
            {
                vol.Required("selected_room"): SelectSelector(
                    SelectSelectorConfig(
                        options=room_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="edit_rooms",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_edit_room(self, user_input=None):
        """Edit a specific room's settings."""
        errors: dict[str, str] = {}
        data = self.entry.data
        rooms = list(data.get(CONF_ROOMS, []))
        room = rooms[self._selected_room_index]
        room_name = room.get("room_name", "Unknown")

        if user_input is not None:
            # Update the room's config
            rooms[self._selected_room_index] = {
                **room,
                **user_input,
            }
            new_data = {**data, CONF_ROOMS: rooms}
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data={})

        # Check if presence verification is enabled
        presence_verification = data.get(CONF_PRESENCE_VERIFICATION, False)

        schema_dict: dict[Any, Any] = {
            vol.Optional("media_player", default=room.get("media_player")): EntitySelector(
                EntitySelectorConfig(domain="media_player")
            ),
        }

        if presence_verification:
            schema_dict[vol.Optional("presence_sensors", default=room.get("presence_sensors", []))] = EntitySelector(
                EntitySelectorConfig(
                    domain="binary_sensor",
                    device_class=["occupancy", "presence", "motion"],
                    multiple=True,
                )
            )

        return self.async_show_form(
            step_id="edit_room",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders={"name": room_name},
        )

    async def async_step_delete_room_select(self, user_input=None):
        """Select which room to delete."""
        errors: dict[str, str] = {}
        data = self.entry.data
        rooms = data.get(CONF_ROOMS, [])

        if not rooms:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            selected_idx = user_input.get("selected_room")
            if selected_idx is not None:
                self._selected_room_index = int(selected_idx)
                return await self.async_step_confirm_delete_room()

        # Build list of rooms to delete
        room_options = []
        for idx, room in enumerate(rooms):
            room_name = room.get("room_name", "Unknown")
            room_options.append({"value": str(idx), "label": room_name})

        data_schema = vol.Schema(
            {
                vol.Required("selected_room"): SelectSelector(
                    SelectSelectorConfig(
                        options=room_options,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="delete_room_select",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_confirm_delete_room(self, user_input=None):
        """Confirm deletion of room."""
        data = self.entry.data
        rooms = list(data.get(CONF_ROOMS, []))
        room = rooms[self._selected_room_index]
        room_name = room.get("room_name", "Unknown")

        if user_input is not None:
            if user_input.get("confirm"):
                # Delete the room
                rooms.pop(self._selected_room_index)
                new_data = {**data, CONF_ROOMS: rooms}
                self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="confirm_delete_room",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): BooleanSelector(),
            }),
            description_placeholders={"name": room_name},
        )

    async def async_step_add_room_select(self, user_input=None):
        """Select which areas to add as rooms."""
        errors: dict[str, str] = {}
        data = self.entry.data
        rooms = data.get(CONF_ROOMS, [])

        # Get all areas and filter out already configured ones
        configured_areas = {r.get("area_id") for r in rooms}
        all_areas = get_areas(self.hass)
        available_areas = [
            area for area in all_areas
            if area["id"] not in configured_areas
        ]

        if not available_areas:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            selected_area_ids = user_input.get("selected_areas", [])
            if not selected_area_ids:
                errors["base"] = "no_rooms_selected"
            else:
                # Store the selected areas to configure
                self._new_rooms_to_add = [
                    area for area in available_areas
                    if area["id"] in selected_area_ids
                ]
                self._current_new_room_index = 0
                return await self.async_step_add_room_config()

        # Build options
        area_options = []
        for area in available_areas:
            area_options.append({"value": area["id"], "label": area["name"]})

        data_schema = vol.Schema(
            {
                vol.Required("selected_areas"): SelectSelector(
                    SelectSelectorConfig(
                        options=area_options,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="add_room_select",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_add_room_config(self, user_input=None):
        """Configure new room - media player and presence sensors."""
        errors: dict[str, str] = {}
        data = self.entry.data

        # Get the current area being configured
        current_area = self._new_rooms_to_add[self._current_new_room_index]
        area_name = current_area["name"]
        area_id = current_area["id"]

        if user_input is not None:
            # Add the new room
            rooms = list(data.get(CONF_ROOMS, []))
            new_room = {
                "area_id": area_id,
                "room_name": area_name,
                **user_input,
            }
            rooms.append(new_room)

            # Update the entry with the new room
            new_data = {**data, CONF_ROOMS: rooms}
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)

            # Move to next room or finish
            self._current_new_room_index += 1
            if self._current_new_room_index < len(self._new_rooms_to_add):
                # Configure next room
                return await self.async_step_add_room_config()
            else:
                # All rooms configured, clear temp data and finish
                self._new_rooms_to_add = []
                self._current_new_room_index = 0
                return self.async_create_entry(title="", data={})

        # Find entities assigned to this area for pre-population
        entity_reg = er.async_get(self.hass)

        # Find media players in this area
        default_media_player = None
        for entity in entity_reg.entities.values():
            if (
                entity.entity_id.startswith("media_player.")
                and entity.area_id == area_id
            ):
                default_media_player = entity.entity_id
                break  # Use first match

        # Find presence sensors in this area
        default_presence_sensors = []
        for entity in entity_reg.entities.values():
            if (
                entity.entity_id.startswith("binary_sensor.")
                and entity.area_id == area_id
                and entity.original_device_class in ["occupancy", "presence", "motion"]
            ):
                default_presence_sensors.append(entity.entity_id)

        # Check if presence verification is enabled
        presence_verification = data.get(CONF_PRESENCE_VERIFICATION, False)

        # Build schema
        schema_dict: dict[Any, Any] = {
            vol.Optional("media_player"): EntitySelector(
                EntitySelectorConfig(domain="media_player")
            ),
        }

        if presence_verification:
            schema_dict[vol.Optional("presence_sensors")] = EntitySelector(
                EntitySelectorConfig(
                    domain="binary_sensor",
                    device_class=["occupancy", "presence", "motion"],
                    multiple=True,
                )
            )

        data_schema = vol.Schema(schema_dict)

        # Build suggested values for pre-population
        suggested_values: dict[str, Any] = {}
        if default_media_player:
            suggested_values["media_player"] = default_media_player
        if presence_verification and default_presence_sensors:
            suggested_values["presence_sensors"] = default_presence_sensors

        return self.async_show_form(
            step_id="add_room_config",
            data_schema=self.add_suggested_values_to_schema(data_schema, suggested_values),
            errors=errors,
            description_placeholders={"name": area_name},
        )

    async def async_step_group_settings(self, user_input=None):
        """Edit group settings."""
        errors: dict[str, str] = {}
        data = self.entry.data
        group = data.get("group", {})
        people = data.get(CONF_PEOPLE, [])

        # Fall back to first person's settings if group settings are empty
        first_person = people[0] if people else {}

        if user_input is not None:
            new_data = {**data, "group": user_input}
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data={})

        # Get values with fallback to first person's settings
        tts_platform = group.get("group_tts_platform") or first_person.get("tts_platform")
        language = group.get("group_language") or first_person.get("language", "english")
        lang_code = LANGUAGE_CODE_MAP.get(language, "en")

        voice_options = []
        if tts_platform:
            try:
                engine = get_engine_instance(self.hass, tts_platform)
                if engine:
                    voices = engine.async_get_supported_voices(lang_code)
                    if voices:
                        for voice in voices:
                            voice_options.append({
                                "value": voice.voice_id,
                                "label": voice.name if hasattr(voice, 'name') else voice.voice_id,
                            })
            except Exception:
                pass

        if voice_options:
            voice_selector = SelectSelector(
                SelectSelectorConfig(options=voice_options, mode=SelectSelectorMode.DROPDOWN)
            )
        else:
            voice_selector = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_GROUP_ADDRESSEE, default=group.get(CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE)): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Optional("group_language", default=group.get("group_language", "english")): SelectSelector(
                SelectSelectorConfig(
                    options=get_language_options(),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional("group_tts_platform", default=group.get("group_tts_platform")): EntitySelector(
                EntitySelectorConfig(domain="tts")
            ),
            vol.Optional("group_tts_voice", default=group.get("group_tts_voice")): voice_selector,
            vol.Required("group_enhance_with_ai", default=group.get("group_enhance_with_ai", True)): BooleanSelector(),
            vol.Required("group_translate_announcement", default=group.get("group_translate_announcement", False)): BooleanSelector(),
        }

        # Show conversation entity if either AI enhancement or translation is enabled
        if group.get("group_enhance_with_ai", True) or group.get("group_translate_announcement", False):
            schema_dict[vol.Optional("group_conversation_entity", default=group.get("group_conversation_entity"))] = EntitySelector(
                EntitySelectorConfig(domain="conversation")
            )

        return self.async_show_form(
            step_id="group_settings",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    async def async_step_advanced_settings(self, user_input=None):
        """Edit advanced AI prompt settings."""
        errors: dict[str, str] = {}
        data = self.entry.data

        if user_input is not None:
            # Update config entry data
            new_data = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self.entry, data=new_data)
            return self.async_create_entry(title="", data={})

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PROMPT_TRANSLATE,
                    default=data.get(CONF_PROMPT_TRANSLATE, DEFAULT_PROMPT_TRANSLATE),
                ): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Optional(
                    CONF_PROMPT_ENHANCE,
                    default=data.get(CONF_PROMPT_ENHANCE, DEFAULT_PROMPT_ENHANCE),
                ): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Optional(
                    CONF_PROMPT_BOTH,
                    default=data.get(CONF_PROMPT_BOTH, DEFAULT_PROMPT_BOTH),
                ): TextSelector(TextSelectorConfig(multiline=True)),
            }
        )

        return self.async_show_form(
            step_id="advanced_settings",
            data_schema=data_schema,
            errors=errors,
        )
