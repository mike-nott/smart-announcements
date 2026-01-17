"""Core announcement logic for Smart Announcements."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_PEOPLE,
    CONF_ROOMS,
    CONF_ROOM_TRACKING,
    CONF_PRESENCE_VERIFICATION,
    CONF_DEBUG_MODE,
    CONF_PRE_ANNOUNCE_ENABLED,
    CONF_PRE_ANNOUNCE_URL,
    CONF_PRE_ANNOUNCE_DELAY,
    CONF_LANGUAGE,
    CONF_PERSON_FRIENDLY_NAME,
    CONF_TRANSLATE_ANNOUNCEMENT,
    EVENT_ANNOUNCEMENT_SENT,
    EVENT_ANNOUNCEMENT_BLOCKED,
)
from .room_tracker import RoomTracker

_LOGGER = logging.getLogger(__name__)


class Announcer:
    """Handle announcement routing and delivery."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the announcer."""
        self.hass = hass
        self.entry = entry
        self.config = entry.data
        self.room_tracker = RoomTracker(hass, entry)

    def _debug(self, msg: str, *args: Any) -> None:
        """Log debug message if debug mode is enabled."""
        # Always use live entry data for debug mode to pick up config changes
        if self.entry.data.get(CONF_DEBUG_MODE, False):
            _LOGGER.info("[DEBUG] " + msg, *args)

    def _get_person_config(self, person_name: str) -> dict[str, Any] | None:
        """Get configuration for a person by name."""
        people = self.config.get(CONF_PEOPLE, [])
        for person in people:
            entity_id = person.get("person_entity", "")
            friendly_name = person.get(CONF_PERSON_FRIENDLY_NAME, "")

            # Match by friendly name first (preferred)
            if friendly_name and friendly_name.lower() == person_name.lower():
                return person

            # Match by entity name (person.mike -> mike) or display name
            name_from_entity = entity_id.replace("person.", "").lower()
            if name_from_entity == person_name.lower():
                return person

            # Also check if person_name matches with underscores replaced
            if name_from_entity.replace("_", " ") == person_name.lower():
                return person
        return None

    def _get_room_config(self, area_id: str) -> dict[str, Any] | None:
        """Get configuration for a room by area ID."""
        rooms = self.config.get(CONF_ROOMS, [])
        for room in rooms:
            if room.get("area_id") == area_id:
                return room
        return None

    def _is_person_enabled(self, person_entity: str) -> bool:
        """Check if announcements are enabled for a person."""
        if DOMAIN not in self.hass.data:
            return True  # Default to enabled
        entry_data = self.hass.data[DOMAIN].get(self.entry.entry_id, {})
        enabled = entry_data.get("enabled", {})
        return enabled.get("people", {}).get(person_entity, True)

    def _is_room_enabled(self, area_id: str) -> bool:
        """Check if announcements are enabled for a room."""
        if DOMAIN not in self.hass.data:
            return True  # Default to enabled
        entry_data = self.hass.data[DOMAIN].get(self.entry.entry_id, {})
        enabled = entry_data.get("enabled", {})
        return enabled.get("rooms", {}).get(area_id, True)

    async def async_announce(
        self,
        message: str,
        target_person: str | None = None,
        target_area: str | None = None,
        enhance_with_ai: bool | None = None,
        translate_announcement: bool | None = None,
        pre_announce_sound: bool | None = None,
    ) -> None:
        """Send an announcement to the appropriate room(s)."""
        # Reload config from entry to pick up any config changes
        self.config = self.entry.data
        self.room_tracker.config = self.entry.data

        self._debug("🔔 ========== ANNOUNCEMENT START ==========")
        self._debug("📝 Message: '%s'", message)
        self._debug("👤 Target person: %s", target_person or "None (broadcast)")
        self._debug("📍 Target area: %s", target_area or "None (auto-detect)")
        self._debug("🤖 Enhance with AI (param): %s", enhance_with_ai if enhance_with_ai is not None else "Not specified (use config)")
        self._debug("🌐 Translate announcement (param): %s", translate_announcement if translate_announcement is not None else "Not specified (use config)")
        self._debug("🔊 Pre-announce sound (param): %s", pre_announce_sound if pre_announce_sound is not None else "Not specified (use config)")

        # Resolve target rooms
        self._debug("🔍 Starting room resolution...")
        target_rooms = await self._resolve_targets(target_person, target_area)

        if not target_rooms:
            self._debug("❌ No target rooms found!")
            if target_person:
                raise HomeAssistantError(
                    f"Cannot announce to '{target_person}': person is not home or has no configured room"
                )
            elif target_area:
                raise HomeAssistantError(
                    f"Cannot announce to area '{target_area}': no matching rooms configured"
                )
            else:
                raise HomeAssistantError(
                    "No occupied rooms found for announcement"
                )

        self._debug("✅ Resolved %d target room(s): %s", len(target_rooms), [r.get("room_name") for r in target_rooms])

        # Announce to each room
        for idx, room_info in enumerate(target_rooms, 1):
            self._debug("📢 Processing room %d/%d: %s", idx, len(target_rooms), room_info.get("room_name"))
            await self._announce_to_room(
                room_info=room_info,
                message=message,
                target_person=target_person,
                enhance_with_ai=enhance_with_ai,
                translate_announcement=translate_announcement,
                pre_announce_sound=pre_announce_sound,
            )

        self._debug("✅ ========== ANNOUNCEMENT COMPLETE ==========")

    async def _resolve_targets(
        self,
        target_person: str | None,
        target_area: str | None,
    ) -> list[dict[str, Any]]:
        """Resolve target rooms based on parameters."""
        room_tracking = self.config.get(CONF_ROOM_TRACKING, True)
        presence_verification = self.config.get(CONF_PRESENCE_VERIFICATION, False)
        rooms = self.config.get(CONF_ROOMS, [])

        self._debug("⚙️ Room tracking enabled: %s", room_tracking)
        self._debug("⚙️ Presence verification enabled: %s", presence_verification)
        self._debug("⚙️ Total configured rooms: %d", len(rooms))

        # If target_area specified, find rooms in that area
        if target_area:
            self._debug("📍 Target area specified: '%s'", target_area)
            self._debug("🔍 Searching for matching room configuration...")
            matching_rooms = [
                room for room in rooms
                if room.get("room_name", "").lower() == target_area.lower()
                or room.get("area_id", "").lower() == target_area.lower()
            ]
            if not matching_rooms:
                self._debug("❌ No room configuration found for area '%s'", target_area)
                raise HomeAssistantError(
                    f"Room/area '{target_area}' is not configured in Smart Announcements"
                )
            self._debug("✅ Found matching room: %s", matching_rooms[0].get("room_name"))
            return matching_rooms

        # If target_person specified, find their room
        if target_person:
            self._debug("👤 Target person specified: '%s'", target_person)
            person_config = self._get_person_config(target_person)
            if not person_config:
                self._debug("❌ Person '%s' not found in configuration", target_person)
                raise HomeAssistantError(
                    f"Person '{target_person}' is not configured in Smart Announcements"
                )

            person_entity = person_config.get("person_entity")
            self._debug("✅ Person entity: %s", person_entity)

            # Check if person is home first
            person_state = self.hass.states.get(person_entity)
            if person_state:
                self._debug("📊 Person state: %s", person_state.state)
            else:
                self._debug("❌ Person entity not found in Home Assistant")

            if room_tracking:
                self._debug("🔍 Room tracking is enabled, finding person's location...")
                # Get person's current room
                room_id = await self.room_tracker.async_get_person_room(person_entity)
                if room_id:
                    self._debug("✅ Person is in room (area_id): %s", room_id)
                    room_config = self._get_room_config(room_id)
                    if room_config:
                        self._debug("✅ Room configuration found: %s", room_config.get("room_name"))
                        return [room_config]
                    else:
                        self._debug("⚠️ Room '%s' is not configured in Smart Announcements", room_id)
                else:
                    self._debug("⚠️ Could not determine person's room from tracking")

            # Fallback: announce to all rooms if person is home
            if person_state and person_state.state == "home":
                self._debug("🏠 Person is home but room unknown, announcing to all rooms with media players")
                fallback_rooms = [r for r in rooms if r.get("media_player")]
                self._debug("📢 Will announce to %d room(s): %s", len(fallback_rooms), [r.get("room_name") for r in fallback_rooms])
                return fallback_rooms

            self._debug("❌ Person %s is not home", target_person)
            return []

        # No specific target: determine which rooms to announce to
        self._debug("🌍 No specific target, determining occupied rooms...")

        if room_tracking or presence_verification:
            self._debug("🔍 Getting occupied rooms (tracking=%s, presence=%s)", room_tracking, presence_verification)
            # Get occupied rooms based on enabled settings
            occupied_rooms = await self.room_tracker.async_get_occupied_rooms(
                use_tracking=room_tracking,
                use_presence=presence_verification,
            )
            self._debug("📊 Occupied room area_ids: %s", occupied_rooms)

            target_rooms = [
                room for room in rooms
                if room.get("area_id") in occupied_rooms
            ]
            self._debug("📢 Will announce to %d occupied room(s): %s", len(target_rooms), [r.get("room_name") for r in target_rooms])
            return target_rooms

        # Neither enabled: announce to all rooms with media players
        self._debug("⚠️ Neither room tracking nor presence verification enabled")
        self._debug("📢 Announcing to ALL rooms with media players")
        all_rooms = [r for r in rooms if r.get("media_player")]
        self._debug("📢 Will announce to %d room(s): %s", len(all_rooms), [r.get("room_name") for r in all_rooms])
        return all_rooms

    async def _announce_to_room(
        self,
        room_info: dict[str, Any],
        message: str,
        target_person: str | None,
        enhance_with_ai: bool | None,
        translate_announcement: bool | None,
        pre_announce_sound: bool | None,
    ) -> None:
        """Announce to a specific room."""
        area_id = room_info.get("area_id", "")
        room_name = room_info.get("room_name", "Unknown")
        media_player = room_info.get("media_player")

        self._debug("🏠 ========== ROOM: %s ==========", room_name)
        self._debug("📍 Area ID: %s", area_id)
        self._debug("🔊 Media player: %s", media_player)

        if not media_player:
            _LOGGER.warning("No media player configured for room: %s", room_name)
            self._debug("❌ SKIPPED: No media player configured")
            return

        # Check room enabled
        room_enabled = self._is_room_enabled(area_id)
        self._debug("🔍 Checking if room is enabled...")
        self._debug("✅ Room enabled: %s", room_enabled)
        if not room_enabled:
            _LOGGER.info("Room %s is disabled, skipping announcement", room_name)
            self._debug("❌ Room is disabled - SKIPPING")
            self._fire_blocked_event(room_name, "room_disabled")
            return

        # Check person enabled if targeting a specific person
        if target_person:
            self._debug("🔍 Checking if person '%s' is enabled...", target_person)
            person_config = self._get_person_config(target_person)
            if person_config:
                person_entity = person_config.get("person_entity")
                person_enabled = self._is_person_enabled(person_entity)
                self._debug("✅ Person '%s' enabled: %s", target_person, person_enabled)
                if not person_enabled:
                    _LOGGER.info("Person %s is disabled, skipping announcement", target_person)
                    self._debug("❌ Person is disabled - SKIPPING")
                    self._fire_blocked_event(room_name, "person_disabled", target_person)
                    return

        # Get TTS settings
        self._debug("🔍 Determining TTS settings...")
        tts_platform, tts_voice = self._get_tts_settings(target_person)
        self._debug("🎤 TTS platform: %s", tts_platform or "Not configured")
        self._debug("🗣️ TTS voice: %s", tts_voice or "Default")

        # Determine enhance_with_ai setting from config if not specified
        self._debug("🔍 Determining AI enhancement setting...")
        should_enhance = enhance_with_ai
        if should_enhance is None:
            # Check person config first, then group config
            if target_person:
                person_config = self._get_person_config(target_person)
                if person_config:
                    should_enhance = person_config.get("enhance_with_ai", True)
                    self._debug("📊 Using person's AI setting: %s", should_enhance)
            if should_enhance is None:
                # Fall back to group config
                group_config = self.config.get("group", {})
                should_enhance = group_config.get("group_enhance_with_ai", True)
                self._debug("📊 Using group AI setting: %s", should_enhance)
        else:
            self._debug("📊 Using service parameter AI setting: %s", should_enhance)

        # Determine translate_announcement setting from config if not specified
        self._debug("🔍 Determining translation setting...")
        should_translate = translate_announcement
        if should_translate is None:
            # Check person config first, then group config
            if target_person:
                person_config = self._get_person_config(target_person)
                if person_config:
                    should_translate = person_config.get("translate_announcement", False)
                    self._debug("📊 Using person's translation setting: %s", should_translate)
            if should_translate is None:
                # Fall back to group config
                group_config = self.config.get("group", {})
                should_translate = group_config.get("group_translate_announcement", False)
                self._debug("📊 Using group translation setting: %s", should_translate)
        else:
            self._debug("📊 Using service parameter translation setting: %s", should_translate)

        # Personalize message first (add name before AI processing)
        self._debug("🔍 Personalizing message...")
        personalized_message = self._personalize_message(message, target_person)
        if personalized_message != message:
            self._debug("✏️ Message personalized: '%s' -> '%s'", message, personalized_message)

        # Enhance and/or translate message if enabled
        final_message = personalized_message
        if should_enhance or should_translate:
            if should_enhance and should_translate:
                self._debug("🤖 Enhancing and translating message...")
            elif should_enhance:
                self._debug("🤖 Enhancing message with AI...")
            else:
                self._debug("🌐 Translating message...")
            final_message = await self._enhance_message(personalized_message, target_person)
            if final_message != personalized_message:
                self._debug("✨ Message processed: '%s' -> '%s'", personalized_message, final_message)
            else:
                self._debug("⚠️ Message unchanged (AI processing returned same text)")
        else:
            self._debug("⏭️ Skipping AI enhancement and translation (both disabled)")

        # Determine pre-announce setting from config if not specified
        self._debug("🔍 Determining pre-announce setting...")
        should_pre_announce = pre_announce_sound
        if should_pre_announce is None:
            should_pre_announce = self.config.get(CONF_PRE_ANNOUNCE_ENABLED, True)
            self._debug("📊 Using config pre-announce setting: %s", should_pre_announce)
        else:
            self._debug("📊 Using service parameter pre-announce setting: %s", should_pre_announce)

        # Play pre-announce sound if enabled
        if should_pre_announce:
            self._debug("🔔 Playing pre-announce sound...")
            await self._play_pre_announce(media_player)
            self._debug("✅ Pre-announce complete")
        else:
            self._debug("⏭️ Skipping pre-announce sound (disabled)")

        # Call TTS service
        self._debug("🎙️ Calling TTS service...")
        self._debug("📝 Final message: '%s'", final_message)
        await self._call_tts(
            media_player=media_player,
            message=final_message,
            tts_platform=tts_platform,
            tts_voice=tts_voice,
        )
        self._debug("✅ TTS announcement sent successfully")

        # Fire success event
        self._fire_sent_event(room_name, final_message, target_person)

        _LOGGER.info("Announced to %s: %s", room_name, final_message)

    def _get_tts_settings(self, target_person: str | None) -> tuple[str | None, str | None]:
        """Get TTS platform and voice for announcement."""
        # Start with group settings as default
        group_config = self.config.get("group", {})
        tts_platform = group_config.get("group_tts_platform")
        tts_voice = group_config.get("group_tts_voice")

        # If no group settings (single person setup), use first person's settings
        if not tts_platform:
            people = self.config.get(CONF_PEOPLE, [])
            if people:
                first_person = people[0]
                tts_platform = first_person.get("tts_platform")
                tts_voice = first_person.get("tts_voice")

        # Override with target person's settings if specified
        if target_person:
            person_config = self._get_person_config(target_person)
            if person_config:
                tts_platform = person_config.get("tts_platform") or tts_platform
                tts_voice = person_config.get("tts_voice") or tts_voice

        return tts_platform, tts_voice

    def _personalize_message(self, message: str, target_person: str | None) -> str:
        """Personalize message with name."""
        # Determine the name to use
        name = None
        if target_person:
            person_config = self._get_person_config(target_person)
            if person_config:
                name = person_config.get(CONF_PERSON_FRIENDLY_NAME) or target_person
            else:
                name = target_person

        # If message contains {{ name }} placeholder, replace it
        if "{{ name }}" in message or "{{name}}" in message:
            if name:
                message = message.replace("{{ name }}", name).replace("{{name}}", name)
            else:
                # No target person, use configured group addressee
                from .const import CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE
                group_config = self.config.get("group", {})
                group_addressee = group_config.get(CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE)
                message = message.replace("{{ name }}", group_addressee).replace("{{name}}", group_addressee)
        # If no placeholder and we have a name, prepend it
        elif name:
            message = f"{name}, {message}"

        return message

    async def _enhance_message(self, message: str, target_person: str | None) -> str:
        """Enhance and/or translate message using conversation entity."""
        # Get settings - start with group settings as default
        group_config = self.config.get("group", {})
        conversation_entity = group_config.get("group_conversation_entity")
        enhance_with_ai = group_config.get("group_enhance_with_ai", True)
        translate_announcement = group_config.get("group_translate_announcement", False)
        language = group_config.get("group_language", "english")

        # If no group settings, use first person's settings
        people = self.config.get(CONF_PEOPLE, [])
        if not conversation_entity and people:
            first_person = people[0]
            conversation_entity = first_person.get("conversation_entity")
            enhance_with_ai = first_person.get("enhance_with_ai", True)
            translate_announcement = first_person.get("translate_announcement", False)
            language = first_person.get("language", "english")

        # Override with target person's settings if specified
        if target_person:
            person_config = self._get_person_config(target_person)
            if person_config:
                conversation_entity = person_config.get("conversation_entity") or conversation_entity
                enhance_with_ai = person_config.get("enhance_with_ai", enhance_with_ai)
                translate_announcement = person_config.get("translate_announcement", translate_announcement)
                language = person_config.get("language", language)

        # If neither enhance nor translate is enabled, return original message
        if not enhance_with_ai and not translate_announcement:
            _LOGGER.debug("Neither AI enhancement nor translation enabled, using original message")
            return message

        # If no conversation entity configured, return original message
        if not conversation_entity:
            _LOGGER.debug("No conversation entity configured, skipping AI processing")
            return message

        # Get custom prompts from config or use defaults
        from .const import (
            CONF_PROMPT_TRANSLATE,
            CONF_PROMPT_ENHANCE,
            CONF_PROMPT_BOTH,
            DEFAULT_PROMPT_TRANSLATE,
            DEFAULT_PROMPT_ENHANCE,
            DEFAULT_PROMPT_BOTH,
        )

        prompt_translate = self.config.get(CONF_PROMPT_TRANSLATE, DEFAULT_PROMPT_TRANSLATE)
        prompt_enhance = self.config.get(CONF_PROMPT_ENHANCE, DEFAULT_PROMPT_ENHANCE)
        prompt_both = self.config.get(CONF_PROMPT_BOTH, DEFAULT_PROMPT_BOTH)

        # Build the appropriate prompt based on settings
        if not enhance_with_ai and translate_announcement:
            # Translate only
            prompt = prompt_translate.format(language=language, message=message)
            _LOGGER.debug("Using translate-only prompt for language: %s", language)
        elif enhance_with_ai and not translate_announcement:
            # Enhance only
            prompt = prompt_enhance.format(message=message)
            _LOGGER.debug("Using enhance-only prompt")
        else:
            # Both enhance and translate
            prompt = prompt_both.format(language=language, message=message)
            _LOGGER.debug("Using enhance+translate prompt for language: %s", language)

        try:
            # Call conversation.process service
            response = await self.hass.services.async_call(
                "conversation",
                "process",
                {
                    "agent_id": conversation_entity,
                    "text": prompt,
                },
                blocking=True,
                return_response=True,
            )

            if response and "response" in response:
                speech = response["response"].get("speech", {})
                plain = speech.get("plain", {})
                enhanced = plain.get("speech", message)
                _LOGGER.debug("AI processed message: %s -> %s", message, enhanced)
                return enhanced

        except Exception as err:
            _LOGGER.warning("AI processing failed, using original message: %s", err)

        return message

    async def _play_pre_announce(self, media_player: str) -> None:
        """Play pre-announce sound."""
        media_url = self.config.get(CONF_PRE_ANNOUNCE_URL)
        delay = self.config.get(CONF_PRE_ANNOUNCE_DELAY, 2)

        self._debug("  🔍 Pre-announce URL from config: %s", media_url or "Not configured")
        self._debug("  ⏱️ Pre-announce delay: %s seconds", delay)

        if not media_url:
            self._debug("  ⚠️ No pre-announce URL configured, skipping")
            return

        service_data = {
            "entity_id": media_player,
            "media_content_id": media_url,
            "media_content_type": "music",
            "announce": True,
        }
        self._debug("  📞 Calling media_player.play_media")
        self._debug("     └─ entity_id: %s", media_player)
        self._debug("     └─ media_content_id: %s", media_url)
        self._debug("     └─ media_content_type: music")
        self._debug("     └─ announce: True")

        try:
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                service_data,
                blocking=True,
            )
            self._debug("  ✅ media_player.play_media call succeeded")

            # Wait for the pre-announce to finish
            if delay > 0:
                self._debug("  ⏳ Waiting %s seconds for pre-announce to finish", delay)
                await asyncio.sleep(delay)
                self._debug("  ✅ Wait complete")

        except Exception as err:
            _LOGGER.warning("Failed to play pre-announce sound: %s", err)
            self._debug("  ❌ Pre-announce FAILED: %s", err)

    async def _call_tts(
        self,
        media_player: str,
        message: str,
        tts_platform: str | None,
        tts_voice: str | None,
    ) -> None:
        """Call TTS service to announce message."""
        service_data = {
            "entity_id": media_player,
            "message": message,
            "cache": True,
        }

        # Add media player target for announce mode (ducking)
        service_data["media_player_entity_id"] = media_player

        # Add voice option if specified
        if tts_voice:
            service_data["options"] = {"voice": tts_voice}

        self._debug("  📞 Calling tts.speak service")
        self._debug("     └─ entity_id (TTS): %s", tts_platform or "Not configured")
        self._debug("     └─ media_player_entity_id: %s", media_player)
        self._debug("     └─ message: '%s'", message)
        self._debug("     └─ cache: True")
        if tts_voice:
            self._debug("     └─ voice: %s", tts_voice)

        try:
            if tts_platform:
                # Use tts.speak with specific engine
                service_data["entity_id"] = tts_platform
                await self.hass.services.async_call(
                    "tts",
                    "speak",
                    service_data,
                    blocking=True,
                )
                self._debug("  ✅ tts.speak call succeeded")
            else:
                # Use default TTS via media_player.play_media
                # This is a fallback if no TTS platform is configured
                _LOGGER.warning("No TTS platform configured, announcement may fail")
                self._debug("  ⚠️ No TTS platform configured - using fallback")
                await self.hass.services.async_call(
                    "tts",
                    "speak",
                    service_data,
                    blocking=True,
                )
                self._debug("  ✅ tts.speak call succeeded (fallback)")

        except Exception as err:
            _LOGGER.error("TTS call failed: %s", err)
            self._debug("  ❌ TTS call FAILED: %s", err)
            raise

    def _fire_sent_event(
        self,
        room_name: str,
        message: str,
        target_person: str | None,
    ) -> None:
        """Fire announcement sent event."""
        self.hass.bus.async_fire(
            EVENT_ANNOUNCEMENT_SENT,
            {
                "room": room_name,
                "message": message,
                "target_person": target_person,
            },
        )

    def _fire_blocked_event(
        self,
        room_name: str,
        reason: str,
        target_person: str | None = None,
    ) -> None:
        """Fire announcement blocked event."""
        self.hass.bus.async_fire(
            EVENT_ANNOUNCEMENT_BLOCKED,
            {
                "room": room_name,
                "reason": reason,
                "target_person": target_person,
            },
        )
