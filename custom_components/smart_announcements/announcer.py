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

            # Match by entity ID directly (e.g., "person.mike")
            if entity_id and entity_id == person_name:
                return person

            # Match by friendly name from HA entity (preferred)
            if entity_id:
                from .config_flow import get_person_friendly_name
                friendly_name = get_person_friendly_name(self.hass, entity_id)
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
        room_tracking: bool | None = None,
        presence_verification: bool | None = None,
        context=None,
    ) -> None:
        """Send an announcement to the appropriate room(s)."""
        # Store context for service calls
        self.context = context

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
        self._debug("📍 Room tracking (param): %s", room_tracking if room_tracking is not None else "Not specified (use config)")
        self._debug("✅ Presence verification (param): %s", presence_verification if presence_verification is not None else "Not specified (use config)")

        # Resolve target rooms
        self._debug("🔍 Starting room resolution...")
        target_rooms = await self._resolve_targets(
            target_person, target_area, room_tracking, presence_verification
        )

        if not target_rooms:
            self._debug("❌ No target rooms found!")
            if target_person:
                raise HomeAssistantError(
                    f"Cannot announce to '{target_person}': person(s) not home or have no configured room"
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
            # Extract target_person from room_info if present, otherwise use original
            room_target_person = room_info.get("target_person", target_person)
            await self._announce_to_room(
                room_info=room_info,
                message=message,
                target_person=room_target_person,
                enhance_with_ai=enhance_with_ai,
                translate_announcement=translate_announcement,
                pre_announce_sound=pre_announce_sound,
            )

        self._debug("✅ ========== ANNOUNCEMENT COMPLETE ==========")

    async def _resolve_targets(
        self,
        target_person: str | None,
        target_area: str | None,
        room_tracking: bool | None = None,
        presence_verification: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve target rooms based on parameters."""
        # Use service parameter overrides if provided, otherwise use config
        if room_tracking is None:
            room_tracking = self.config.get(CONF_ROOM_TRACKING, True)
        if presence_verification is None:
            presence_verification = self.config.get(CONF_PRESENCE_VERIFICATION, False)
        rooms = self.config.get(CONF_ROOMS, [])

        from .const import CONF_HOME_AWAY_TRACKING, DEFAULT_HOME_AWAY_TRACKING
        home_away_tracking = self.config.get(CONF_HOME_AWAY_TRACKING, DEFAULT_HOME_AWAY_TRACKING)

        self._debug("⚙️ Home/away tracking enabled: %s", home_away_tracking)
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

        # If target_person specified, parse comma-separated names and find their rooms
        if target_person:
            # Parse comma-separated names
            target_people = [name.strip() for name in target_person.split(",")]
            self._debug("👤 Target person(s) specified: %s", target_people)

            # Track rooms and which people are in each room
            room_to_people = {}  # {area_id: [person_names]}

            for person_name in target_people:
                person_config = self._get_person_config(person_name)
                if not person_config:
                    self._debug("❌ Person '%s' not found in configuration", person_name)
                    raise HomeAssistantError(
                        f"Person '{person_name}' is not configured in Smart Announcements"
                    )

                person_entity = person_config.get("person_entity")
                self._debug("✅ Person '%s' entity: %s", person_name, person_entity)

                # Check if person is home first
                person_state = self.hass.states.get(person_entity)
                if person_state:
                    self._debug("📊 Person '%s' state: %s", person_name, person_state.state)
                else:
                    self._debug("❌ Person entity not found in Home Assistant")

                if room_tracking:
                    self._debug("🔍 Room tracking is enabled, finding %s's location...", person_name)
                    # Get person's current room
                    room_id = await self.room_tracker.async_get_person_room(person_entity)
                    if room_id:
                        self._debug("✅ Person '%s' is in room (area_id): %s", person_name, room_id)
                        room_config = self._get_room_config(room_id)
                        if room_config:
                            self._debug("✅ Room configuration found: %s", room_config.get("room_name"))
                            # Add person to this room's target list
                            if room_id not in room_to_people:
                                room_to_people[room_id] = []
                            room_to_people[room_id].append(person_name)
                        else:
                            self._debug("⚠️ Room '%s' is not configured in Smart Announcements", room_id)
                    else:
                        self._debug("⚠️ Could not determine %s's room from tracking", person_name)
                        # Will handle this in final fallback

            # Build target room list with target_person metadata
            target_rooms = []
            for room_id, people_list in room_to_people.items():
                room_config = self._get_room_config(room_id)
                if room_config:
                    # Add metadata about which specific people are targeted in this room
                    room_with_targets = room_config.copy()
                    # If multiple people targeted in same room, use None (will trigger group detection)
                    # If single person targeted, use their name
                    room_with_targets["target_person"] = people_list[0] if len(people_list) == 1 else None
                    room_with_targets["targeted_people"] = people_list
                    target_rooms.append(room_with_targets)
                    self._debug("📍 Room %s will announce to: %s (target_person=%s)",
                               room_config.get("room_name"),
                               people_list,
                               room_with_targets["target_person"])

            if target_rooms:
                return target_rooms

            # Fallback: if no specific rooms found but people are home, use occupied rooms
            for person_name in target_people:
                person_config = self._get_person_config(person_name)
                if person_config:
                    person_entity = person_config.get("person_entity")
                    person_state = self.hass.states.get(person_entity)
                    if person_state and person_state.state == "home":
                        self._debug("🏠 At least one person is home but room unknown, using occupied rooms")
                        # Use same logic as no-target-person: get occupied rooms
                        occupied_rooms = await self.room_tracker.async_get_occupied_rooms(
                            use_tracking=room_tracking,
                            use_presence=presence_verification,
                        )
                        self._debug("📊 Occupied room area_ids: %s", occupied_rooms)
                        fallback_rooms = [r for r in rooms if r.get("area_id") in occupied_rooms]
                        self._debug("📢 Will announce to %d occupied room(s): %s", len(fallback_rooms), [r.get("room_name") for r in fallback_rooms])
                        return fallback_rooms

            self._debug("❌ No target people are home")
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

        # STEP 1: Detect people in room and determine if group
        self._debug("============ GROUP DETECTION ============")
        people_in_room = await self.room_tracker.async_get_people_in_room(area_id)
        is_group_room = len(people_in_room) > 1

        self._debug("👥 People in room %s: %s", area_id, people_in_room)
        self._debug("🔢 People count: %d", len(people_in_room))
        self._debug("👫 Is group room: %s", is_group_room)
        self._debug("🎯 Target person override: %s", target_person or "None")
        self._debug("=======================================")

        # STEP 2: Get appropriate settings based on group status
        settings = self._get_announcement_settings(target_person, people_in_room, is_group_room)

        # Log which settings are being used
        self._debug("⚙️  Using settings from: %s", settings.get("source"))
        if is_group_room and not target_person:
            self._debug("👥 GROUP ANNOUNCEMENT")
            from .const import CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE
            group_config = self.config.get("group", {})
            self._debug("  📢 Addressee: %s", group_config.get(CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE))
        else:
            self._debug("👤 INDIVIDUAL ANNOUNCEMENT")
            if target_person:
                self._debug("  👤 Target person: %s", target_person)
            elif len(people_in_room) == 1:
                self._debug("  👤 Person in room: %s", people_in_room[0])

        self._debug("  🌐 Language: %s", settings.get("language"))
        self._debug("  🎤 TTS Platform: %s", settings.get("tts_platform"))
        self._debug("  🎙️  TTS Voice: %s", settings.get("tts_voice"))
        self._debug("  🤖 Conversation Entity: %s", settings.get("conversation_entity") or "Not configured")

        # Override settings with service parameters if provided
        should_enhance = enhance_with_ai if enhance_with_ai is not None else settings.get("enhance_with_ai", True)
        should_translate = translate_announcement if translate_announcement is not None else settings.get("translate_announcement", False)

        if enhance_with_ai is not None:
            self._debug("  🤖 AI Enhancement (service override): %s", should_enhance)
        else:
            self._debug("  🤖 AI Enhancement (config): %s", should_enhance)

        if translate_announcement is not None:
            self._debug("  🌐 Translation (service override): %s", should_translate)
        else:
            self._debug("  🌐 Translation (config): %s", should_translate)

        # STEP 3: Personalize message with appropriate name
        self._debug("🔍 Personalizing message...")
        personalized_message = self._personalize_message(
            message, target_person, people_in_room, is_group_room
        )
        if personalized_message != message:
            self._debug("✏️ Message personalized: '%s' -> '%s'", message, personalized_message)

        # STEP 4: Enhance/translate using selected settings
        final_message = personalized_message
        if should_enhance or should_translate:
            if should_enhance and should_translate:
                self._debug("🤖 Enhancing and translating message...")
            elif should_enhance:
                self._debug("🤖 Enhancing message with AI...")
            else:
                self._debug("🌐 Translating message...")
            final_message = await self._enhance_message(
                personalized_message,
                settings.get("conversation_entity"),
                settings.get("language"),
                should_enhance,
                should_translate,
            )
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

        # STEP 5: Call TTS with selected platform and voice
        self._debug("🎙️ Calling TTS service...")
        self._debug("📝 Final message: '%s'", final_message)
        await self._call_tts(
            media_player=media_player,
            message=final_message,
            tts_platform=settings.get("tts_platform"),
            tts_voice=settings.get("tts_voice"),
        )
        self._debug("✅ TTS announcement sent successfully")

        # Log to Activity dashboard (if enabled)
        if self.config.get("log_to_activity", False):
            await self.hass.services.async_call(
                "logbook",
                "log",
                {
                    "name": f"Smart Announcements: {room_name}",
                    "message": final_message,
                    "entity_id": f"switch.{DOMAIN}_{area_id}",
                    "domain": DOMAIN,
                },
                blocking=False,
                context=self.context,
            )
            self._debug("✅ Activity dashboard entry created")

        # Fire success event
        self._fire_sent_event(room_name, final_message, target_person)

        _LOGGER.info("Announced to %s: %s", room_name, final_message)

    def _get_announcement_settings(
        self,
        target_person: str | None,
        people_in_room: list[str],
        is_group_room: bool,
    ) -> dict[str, Any]:
        """Get appropriate settings for this announcement.

        Priority order:
        1. If target_person specified → use that person's settings
        2. If is_group_room (2+ people) → use group settings
        3. If 1 person in room → use that person's settings
        4. Fallback → use group settings

        Returns dict with:
            - conversation_entity
            - language
            - tts_platform
            - tts_voice
            - enhance_with_ai
            - translate_announcement
            - source (for debugging)
        """
        # Priority 1: If target_person specified, use their settings
        if target_person:
            person_config = self._get_person_config(target_person)
            if person_config:
                return {
                    "conversation_entity": person_config.get("conversation_entity"),
                    "language": person_config.get("language", "english"),
                    "tts_platform": person_config.get("tts_platform"),
                    "tts_voice": person_config.get("tts_voice"),
                    "enhance_with_ai": person_config.get("enhance_with_ai", True),
                    "translate_announcement": person_config.get("translate_announcement", False),
                    "source": f"person:{target_person}",
                }

        # Priority 2: Group room (2+ people) → use group settings
        if is_group_room:
            group_config = self.config.get("group", {})
            return {
                "conversation_entity": group_config.get("group_conversation_entity"),
                "language": group_config.get("group_language", "english"),
                "tts_platform": group_config.get("group_tts_platform"),
                "tts_voice": group_config.get("group_tts_voice"),
                "enhance_with_ai": group_config.get("group_enhance_with_ai", True),
                "translate_announcement": group_config.get("group_translate_announcement", False),
                "source": "group",
            }

        # Priority 3: Individual room (1 person) → use that person's settings
        if len(people_in_room) == 1:
            person_entity = people_in_room[0]
            person_config = self._get_person_config(person_entity)
            if person_config:
                return {
                    "conversation_entity": person_config.get("conversation_entity"),
                    "language": person_config.get("language", "english"),
                    "tts_platform": person_config.get("tts_platform"),
                    "tts_voice": person_config.get("tts_voice"),
                    "enhance_with_ai": person_config.get("enhance_with_ai", True),
                    "translate_announcement": person_config.get("translate_announcement", False),
                    "source": f"person:{person_entity}",
                }

        # Fallback: Use group settings
        group_config = self.config.get("group", {})
        return {
            "conversation_entity": group_config.get("group_conversation_entity"),
            "language": group_config.get("group_language", "english"),
            "tts_platform": group_config.get("group_tts_platform"),
            "tts_voice": group_config.get("group_tts_voice"),
            "enhance_with_ai": group_config.get("group_enhance_with_ai", True),
            "translate_announcement": group_config.get("group_translate_announcement", False),
            "source": "group(fallback)",
        }

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

    def _personalize_message(
        self,
        message: str,
        target_person: str | None,
        people_in_room: list[str],
        is_group_room: bool,
    ) -> str:
        """Personalize message with name."""
        # Determine the name to use
        name = None

        # Priority 1: If target_person specified, always use their name
        if target_person:
            person_config = self._get_person_config(target_person)
            if person_config:
                from .config_flow import get_person_friendly_name
                entity_id = person_config.get("person_entity")
                name = get_person_friendly_name(self.hass, entity_id) if entity_id else target_person
            else:
                name = target_person
        # Priority 2: If group room and no target_person, use group addressee
        elif is_group_room:
            from .const import CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE
            group_config = self.config.get("group", {})
            name = group_config.get(CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE)
        # Priority 3: If 1 person in room, use that person's name
        elif len(people_in_room) == 1:
            person_entity = people_in_room[0]
            person_config = self._get_person_config(person_entity)
            if person_config:
                from .config_flow import get_person_friendly_name
                entity_id = person_config.get("person_entity")
                name = get_person_friendly_name(self.hass, entity_id) if entity_id else person_entity
            else:
                name = person_entity

        # Handle {{ name }} placeholder or prepend
        if "{{ name }}" in message or "{{name}}" in message:
            if name:
                message = message.replace("{{ name }}", name).replace("{{name}}", name)
            else:
                # Fallback to group addressee if no name determined
                from .const import CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE
                group_config = self.config.get("group", {})
                group_addressee = group_config.get(CONF_GROUP_ADDRESSEE, DEFAULT_GROUP_ADDRESSEE)
                message = message.replace("{{ name }}", group_addressee).replace("{{name}}", group_addressee)
        elif name:
            message = f"{name}, {message}"

        return message

    async def _enhance_message(
        self,
        message: str,
        conversation_entity: str | None,
        language: str,
        enhance_with_ai: bool,
        translate_announcement: bool,
    ) -> str:
        """Enhance and/or translate message using conversation entity."""
        self._debug("🔍 _enhance_message called:")
        self._debug("  📝 Message: '%s'", message)
        self._debug("  🤖 Conversation entity: %s", conversation_entity or "None")
        self._debug("  🌐 Language: %s", language)
        self._debug("  ✨ Enhance with AI: %s", enhance_with_ai)
        self._debug("  🌍 Translate: %s", translate_announcement)

        # If neither enhance nor translate is enabled, return original message
        if not enhance_with_ai and not translate_announcement:
            self._debug("⏭️ Skipping: Neither AI enhancement nor translation enabled")
            return message

        # If no conversation entity configured, return original message
        if not conversation_entity:
            self._debug("⏭️ Skipping: No conversation entity configured")
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
            self._debug("  📋 Using translate-only prompt for language: %s", language)
        elif enhance_with_ai and not translate_announcement:
            # Enhance only
            prompt = prompt_enhance.format(message=message)
            self._debug("  📋 Using enhance-only prompt")
        else:
            # Both enhance and translate
            prompt = prompt_both.format(language=language, message=message)
            self._debug("  📋 Using enhance+translate prompt for language: %s", language)

        self._debug("  💬 Actual prompt being sent to LLM: '%s'", prompt)

        try:
            # Call conversation.process service
            self._debug("  📞 Calling conversation.process service")
            response = await self.hass.services.async_call(
                "conversation",
                "process",
                {
                    "agent_id": conversation_entity,
                    "text": prompt,
                },
                blocking=True,
                return_response=True,
                context=self.context,
            )
            self._debug("  ✅ Received response from conversation.process")

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
                context=self.context,
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
                    context=self.context,
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
                    context=self.context,
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
