"""Constants for the Smart Announcements integration."""

DOMAIN = "smart_announcements"

# Configuration keys - Global settings
CONF_HOME_AWAY_TRACKING = "home_away_tracking"
CONF_ROOM_TRACKING = "room_tracking"
CONF_PRESENCE_VERIFICATION = "presence_verification"
CONF_DEBUG_MODE = "debug_mode"
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
CONF_TRANSLATE_ANNOUNCEMENT = "translate_announcement"

# Configuration keys - Rooms
CONF_ROOMS = "rooms"
CONF_ROOM_NAME = "room_name"
CONF_MEDIA_PLAYER = "media_player"
CONF_PRESENCE_SENSORS = "presence_sensors"

# Configuration keys - Advanced AI Prompts
CONF_PROMPT_TRANSLATE = "prompt_translate"
CONF_PROMPT_ENHANCE = "prompt_enhance"
CONF_PROMPT_BOTH = "prompt_both"

# Configuration keys - Group Settings
CONF_GROUP_ADDRESSEE = "group_addressee"

# Service parameters
ATTR_MESSAGE = "message"
ATTR_TARGET_PERSON = "target_person"
ATTR_TARGET_AREA = "target_area"
ATTR_ENHANCE_WITH_AI = "enhance_with_ai"
ATTR_TRANSLATE_ANNOUNCEMENT = "translate_announcement"
ATTR_PRE_ANNOUNCE_SOUND = "pre_announce_sound"
ATTR_ROOM_TRACKING = "room_tracking"
ATTR_PRESENCE_VERIFICATION = "presence_verification"

# Default values
DEFAULT_HOME_AWAY_TRACKING = True
DEFAULT_ROOM_TRACKING = True
DEFAULT_PRESENCE_VERIFICATION = False
DEFAULT_DEBUG_MODE = False
DEFAULT_TTS_PLATFORM = "tts.google_translate_say"
DEFAULT_PRE_ANNOUNCE_ENABLED = True
DEFAULT_PRE_ANNOUNCE_URL = "/local/sounds/chime.mp3"
DEFAULT_PRE_ANNOUNCE_DELAY = 2
DEFAULT_LANGUAGE = "english"
DEFAULT_GROUP_ADDRESSEE = "Everyone"

# Default AI prompt templates
DEFAULT_PROMPT_TRANSLATE = 'Translate this announcement to {language}. Return only the translated announcement, no explanations or confirmations. Keep who it\'s addressed to. Message: "{message}"'
DEFAULT_PROMPT_ENHANCE = 'Rephrase this announcement to be more engaging. Return only the new announcement, no explanations or confirmations. Keep who it\'s addressed to. Message: "{message}"'
DEFAULT_PROMPT_BOTH = 'Translate this announcement to {language} and make it more engaging. Return only the result, no explanations or confirmations. Keep who it\'s addressed to. Message: "{message}"'

# Language options
LANGUAGE_OPTIONS = [
    "arabic",
    "chinese",
    "czech",
    "danish",
    "dutch",
    "english",
    "filipino",
    "finnish",
    "french",
    "german",
    "greek",
    "hindi",
    "italian",
    "japanese",
    "korean",
    "norwegian",
    "polish",
    "portuguese",
    "russian",
    "spanish",
    "swedish",
    "thai",
    "turkish",
    "ukrainian",
    "vietnamese",
]

# Language to language code mapping for TTS
LANGUAGE_CODE_MAP = {
    "arabic": "ar",
    "chinese": "zh",
    "czech": "cs",
    "danish": "da",
    "dutch": "nl",
    "english": "en",
    "filipino": "tl",
    "finnish": "fi",
    "french": "fr",
    "german": "de",
    "greek": "el",
    "hindi": "hi",
    "italian": "it",
    "japanese": "ja",
    "korean": "ko",
    "norwegian": "no",
    "polish": "pl",
    "portuguese": "pt",
    "russian": "ru",
    "spanish": "es",
    "swedish": "sv",
    "thai": "th",
    "turkish": "tr",
    "ukrainian": "uk",
    "vietnamese": "vi",
}

# Events
EVENT_ANNOUNCEMENT_SENT = f"{DOMAIN}_announcement_sent"
EVENT_ANNOUNCEMENT_BLOCKED = f"{DOMAIN}_announcement_blocked"

# Entity prefixes
SWITCH_PREFIX = f"switch.{DOMAIN}"
