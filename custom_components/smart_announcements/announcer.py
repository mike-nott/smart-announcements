"""Core announcement logic for Smart Announcements."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    CONF_PEOPLE,
    CONF_ROOMS,
    CONF_ROOM_TRACKING,
    CONF_PRESENCE_VERIFICATION,
    CONF_DEFAULT_TTS_PLATFORM,
    CONF_DEFAULT_CONVERSATION_ENTITY,
    CONF_PRE_ANNOUNCE_ENABLED,
    CONF_PRE_ANNOUNCE_URL,
    CONF_PRE_ANNOUNCE_DELAY,
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

    def _get_person_config(self, person_name: str) -> dict[str, Any] | None:
        """Get configuration for a person by name."""
        people = self.config.get(CONF_PEOPLE, [])
        for person in people:
            entity_id = person.get("person_entity", "")
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

    def _is_person_muted(self, person_entity: str) -> bool:
        """Check if a person is muted."""
        if DOMAIN not in self.hass.data:
            return False
        entry_data = self.hass.data[DOMAIN].get(self.entry.entry_id, {})
        mutes = entry_data.get("mutes", {})
        return mutes.get("people", {}).get(person_entity, False)

    def _is_room_muted(self, area_id: str) -> bool:
        """Check if a room is muted."""
        if DOMAIN not in self.hass.data:
            return False
        entry_data = self.hass.data[DOMAIN].get(self.entry.entry_id, {})
        mutes = entry_data.get("mutes", {})
        return mutes.get("rooms", {}).get(area_id, False)

    async def async_announce(
        self,
        message: str,
        target_person: str | None = None,
        target_area: str | None = None,
        enhance_with_ai: bool = False,
        pre_announce_sound: bool | None = None,
        sleep_override: bool = False,
    ) -> None:
        """Send an announcement to the appropriate room(s)."""
        _LOGGER.debug(
            "Announce called: message=%s, target_person=%s, target_area=%s",
            message,
            target_person,
            target_area,
        )

        # Resolve target rooms
        target_rooms = await self._resolve_targets(target_person, target_area)

        if not target_rooms:
            _LOGGER.warning("No target rooms resolved for announcement")
            return

        _LOGGER.debug("Resolved target rooms: %s", target_rooms)

        # Announce to each room
        for room_info in target_rooms:
            await self._announce_to_room(
                room_info=room_info,
                message=message,
                target_person=target_person,
                enhance_with_ai=enhance_with_ai,
                pre_announce_sound=pre_announce_sound,
                sleep_override=sleep_override,
            )

    async def _resolve_targets(
        self,
        target_person: str | None,
        target_area: str | None,
    ) -> list[dict[str, Any]]:
        """Resolve target rooms based on parameters."""
        room_tracking = self.config.get(CONF_ROOM_TRACKING, True)
        rooms = self.config.get(CONF_ROOMS, [])

        # If target_area specified, find rooms in that area
        if target_area:
            return [
                room for room in rooms
                if room.get("room_name", "").lower() == target_area.lower()
                or room.get("area_id", "").lower() == target_area.lower()
            ]

        # If target_person specified, find their room
        if target_person:
            person_config = self._get_person_config(target_person)
            if not person_config:
                _LOGGER.warning("Person '%s' not found in configuration", target_person)
                return []

            person_entity = person_config.get("person_entity")

            if room_tracking:
                # Get person's current room
                room_id = await self.room_tracker.async_get_person_room(person_entity)
                if room_id:
                    room_config = self._get_room_config(room_id)
                    if room_config:
                        return [room_config]

            # Fallback: announce to all rooms if person is home
            person_state = self.hass.states.get(person_entity)
            if person_state and person_state.state == "home":
                return [r for r in rooms if r.get("media_player")]

            _LOGGER.debug("Person %s is not home, skipping announcement", target_person)
            return []

        # No specific target: announce to all occupied rooms
        if room_tracking:
            occupied_rooms = await self.room_tracker.async_get_occupied_rooms()
            return [
                room for room in rooms
                if room.get("area_id") in occupied_rooms
            ]

        # No room tracking: announce to all rooms with media players
        return [r for r in rooms if r.get("media_player")]

    async def _announce_to_room(
        self,
        room_info: dict[str, Any],
        message: str,
        target_person: str | None,
        enhance_with_ai: bool,
        pre_announce_sound: bool | None,
        sleep_override: bool,
    ) -> None:
        """Announce to a specific room."""
        area_id = room_info.get("area_id", "")
        room_name = room_info.get("room_name", "Unknown")
        media_player = room_info.get("media_player")

        if not media_player:
            _LOGGER.warning("No media player configured for room: %s", room_name)
            return

        # Check room mute (unless sleep_override)
        if not sleep_override and self._is_room_muted(area_id):
            _LOGGER.info("Room %s is muted, skipping announcement", room_name)
            self._fire_blocked_event(room_name, "room_muted")
            return

        # Check person mute if targeting a specific person
        if target_person:
            person_config = self._get_person_config(target_person)
            if person_config:
                person_entity = person_config.get("person_entity")
                if self._is_person_muted(person_entity):
                    _LOGGER.info("Person %s is muted, skipping announcement", target_person)
                    self._fire_blocked_event(room_name, "person_muted", target_person)
                    return

        # Get TTS settings
        tts_platform, tts_voice = self._get_tts_settings(target_person)

        # Enhance message with AI if requested
        final_message = message
        if enhance_with_ai:
            final_message = await self._enhance_message(message, target_person)

        # Personalize message
        final_message = self._personalize_message(final_message, target_person)

        # Determine pre-announce setting
        should_pre_announce = pre_announce_sound
        if should_pre_announce is None:
            should_pre_announce = self.config.get(CONF_PRE_ANNOUNCE_ENABLED, True)

        # Play pre-announce sound if enabled
        if should_pre_announce:
            await self._play_pre_announce(media_player)

        # Call TTS service
        await self._call_tts(
            media_player=media_player,
            message=final_message,
            tts_platform=tts_platform,
            tts_voice=tts_voice,
        )

        # Fire success event
        self._fire_sent_event(room_name, final_message, target_person)

        _LOGGER.info("Announced to %s: %s", room_name, final_message)

    def _get_tts_settings(self, target_person: str | None) -> tuple[str | None, str | None]:
        """Get TTS platform and voice for announcement."""
        tts_platform = self.config.get(CONF_DEFAULT_TTS_PLATFORM)
        tts_voice = None

        if target_person:
            person_config = self._get_person_config(target_person)
            if person_config:
                tts_platform = person_config.get("tts_platform") or tts_platform
                tts_voice = person_config.get("tts_voice")

        return tts_platform, tts_voice

    def _personalize_message(self, message: str, target_person: str | None) -> str:
        """Personalize message with name."""
        if "{{ name }}" in message or "{{name}}" in message:
            name = target_person or "Everyone"
            message = message.replace("{{ name }}", name).replace("{{name}}", name)
        return message

    async def _enhance_message(self, message: str, target_person: str | None) -> str:
        """Enhance message using conversation entity."""
        conversation_entity = self.config.get(CONF_DEFAULT_CONVERSATION_ENTITY)

        if target_person:
            person_config = self._get_person_config(target_person)
            if person_config:
                conversation_entity = person_config.get("conversation_entity") or conversation_entity

        if not conversation_entity:
            _LOGGER.debug("No conversation entity configured, skipping AI enhancement")
            return message

        try:
            # Call conversation.process service
            response = await self.hass.services.async_call(
                "conversation",
                "process",
                {
                    "agent_id": conversation_entity,
                    "text": f"Rephrase this announcement in your style: {message}",
                },
                blocking=True,
                return_response=True,
            )

            if response and "response" in response:
                speech = response["response"].get("speech", {})
                plain = speech.get("plain", {})
                enhanced = plain.get("speech", message)
                _LOGGER.debug("Enhanced message: %s -> %s", message, enhanced)
                return enhanced

        except Exception as err:
            _LOGGER.warning("AI enhancement failed, using original message: %s", err)

        return message

    async def _play_pre_announce(self, media_player: str) -> None:
        """Play pre-announce sound."""
        media_url = self.config.get(CONF_PRE_ANNOUNCE_URL)
        delay = self.config.get(CONF_PRE_ANNOUNCE_DELAY, 2)

        if not media_url:
            return

        try:
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": media_player,
                    "media_content_id": media_url,
                    "media_content_type": "music",
                    "announce": True,
                },
                blocking=True,
            )

            # Wait for the pre-announce to finish
            if delay > 0:
                await asyncio.sleep(delay)

        except Exception as err:
            _LOGGER.warning("Failed to play pre-announce sound: %s", err)

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
            else:
                # Use default TTS via media_player.play_media
                # This is a fallback if no TTS platform is configured
                _LOGGER.warning("No TTS platform configured, announcement may fail")
                await self.hass.services.async_call(
                    "tts",
                    "speak",
                    service_data,
                    blocking=True,
                )

        except Exception as err:
            _LOGGER.error("TTS call failed: %s", err)
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
