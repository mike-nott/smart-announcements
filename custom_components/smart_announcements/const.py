"""Constants for the Smart Announcements integration."""

DOMAIN = "smart_announcements"

# Configuration keys - Global settings
CONF_ROOM_TRACKING = "room_tracking"
CONF_PRESENCE_VERIFICATION = "presence_verification"
CONF_DEFAULT_TTS_PLATFORM = "default_tts_platform"
CONF_DEFAULT_CONVERSATION_ENTITY = "default_conversation_entity"
CONF_PRE_ANNOUNCE_ENABLED = "pre_announce_enabled"
CONF_PRE_ANNOUNCE_URL = "pre_announce_url"
CONF_PRE_ANNOUNCE_DELAY = "pre_announce_delay"

# Configuration keys - People
CONF_PEOPLE = "people"
CONF_PERSON_ENTITY = "person_entity"
CONF_TTS_PLATFORM = "tts_platform"
CONF_TTS_VOICE = "tts_voice"
CONF_CONVERSATION_ENTITY = "conversation_entity"
CONF_LANGUAGE = "language"

# Configuration keys - Rooms
CONF_ROOMS = "rooms"
CONF_ROOM_NAME = "room_name"
CONF_MEDIA_PLAYER = "media_player"
CONF_PRESENCE_SENSORS = "presence_sensors"

# Service parameters
ATTR_MESSAGE = "message"
ATTR_TARGET_PERSON = "target_person"
ATTR_TARGET_AREA = "target_area"
ATTR_ENHANCE_WITH_AI = "enhance_with_ai"
ATTR_PRE_ANNOUNCE_SOUND = "pre_announce_sound"
ATTR_SLEEP_OVERRIDE = "sleep_override"

# Default values
DEFAULT_ROOM_TRACKING = True
DEFAULT_PRESENCE_VERIFICATION = True
DEFAULT_TTS_PLATFORM = "tts.google_translate_say"
DEFAULT_PRE_ANNOUNCE_ENABLED = True
DEFAULT_PRE_ANNOUNCE_URL = "/local/sounds/chime.mp3"
DEFAULT_PRE_ANNOUNCE_DELAY = 2
DEFAULT_LANGUAGE = "english"

# Language options
LANGUAGE_OPTIONS = [
    "english",
    "japanese",
    "tagalog",
    "scottish",
]

# Events
EVENT_ANNOUNCEMENT_SENT = f"{DOMAIN}_announcement_sent"
EVENT_ANNOUNCEMENT_BLOCKED = f"{DOMAIN}_announcement_blocked"

# Entity prefixes
SWITCH_PREFIX = f"switch.{DOMAIN}"
