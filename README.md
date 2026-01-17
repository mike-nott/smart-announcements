# Smart Announcements for Home Assistant

A Home Assistant custom integration for intelligent, context-aware voice announcements that automatically route messages to the right room based on who's home and where they are. Supports AI enhancement, multiple languages, and per-person customization.

## Key Features

- ✅ **Intelligent Room Routing**: Automatically finds people and announces to their current room
- ✅ **AI Enhancement & Translation**: Optional AI-powered message rephrasing and translation via conversation agents
- ✅ **Multi-Language Support**: Per-person language configuration for TTS
- ✅ **Room Tracking**: Supports Bermuda, ESPresense, or any device tracker/sensor
- ✅ **Presence Verification**: Optional occupancy sensor verification for accuracy
- ✅ **Per-Person Configuration**: Individual TTS platform, voice, language, and AI settings
- ✅ **Group Announcements**: Special settings when multiple people are in the same room
- ✅ **Multi-Person Targeting**: Target multiple people with comma-separated names
- ✅ **Enable/Disable Switches**: Per-person and per-room announcement control
- ✅ **Home/Away Tracking Toggle**: Optionally ignore person entity home/away state when using room tracking
- ✅ **Pre-Announce Sound**: Optional chime before announcements
- ✅ **Audio Ducking**: Automatically lowers background music during announcements and restores playback
- ✅ **Debug Mode**: Comprehensive emoji-enhanced logging for troubleshooting

## The Problem Smart Announcements Solves

Traditional Home Assistant announcements require you to manually specify which media player to use. This means:
- Writing complex automations for every announcement
- Hard-coding room names and media players
- No automatic person tracking
- Can't handle people moving between rooms
- Announcements to empty rooms or wrong rooms
- No personalization per person

## How Smart Announcements Works

Instead of manual routing, Smart Announcements:

1. **Tracks people** using device trackers or room presence sensors
2. **Finds their current room** based on configured tracking entities
3. **Detects group vs individual rooms** - automatically switches between individual and group settings
4. **Routes announcements** to the media player in that room
5. **Personalizes the message** using per-person TTS voices and languages (or group addressee for groups)
6. **Enhances with AI** (optional) for natural, conversational announcements
7. **Verifies presence** (optional) using occupancy sensors
8. **Delivers with audio ducking** - automatically lowers background music, announces, then restores playback
9. **Respects enable/disable switches** for both people and rooms

### Group vs Individual Announcements

Smart Announcements intelligently detects whether a room has one person or multiple people, and automatically selects the appropriate settings:

**Individual Room (1 person):**
- Uses that person's TTS platform, voice, and language
- Uses that person's AI enhancement and translation settings
- Prepends the person's name: "John, dinner is ready"

**Group Room (2+ people):**
- Uses group TTS platform, voice, and language
- Uses group AI enhancement and translation settings
- Prepends the group addressee: "Everyone, dinner is ready"

**Targeted Announcements:**
- When you specify a `target_person`, always uses that person's settings
- Even if multiple people are in the room, targets the specific person
- Overrides group detection: "John, your package arrived"
- **Multi-person targeting**: Use comma-separated names (e.g., `"John, Alice"`)
  - Announces to each person's current room
  - If both in same room → uses group settings automatically
  - If in different rooms → each gets announcement with their individual settings

This means you can configure different voices for individuals (e.g., John gets English Google voice, Alice gets Japanese ElevenLabs voice), and when they're together in a room, the system automatically uses your configured group settings.

## Requirements

- Home Assistant 2024.1+
- At least one TTS platform configured (Google Translate, ElevenLabs, Piper, etc.)
- Media players in your rooms (Google Home, Sonos, Echo, etc.)
- Optional: Room tracking (Bermuda, ESPresense, or device trackers)
- Optional: Conversation agent for AI enhancement (MCP Assist, Extended OpenAI Conversation, etc.)
- Optional: Presence sensors for verification

## Installation

### Add to HACS

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mike-nott&repository=smart-announcements&category=integration)

### Option A: HACS (Recommended)
1. Click the badge above to add this repository to HACS, or manually add it as a custom repository
2. Install "Smart Announcements" from HACS
3. Restart Home Assistant

### Option B: Manual Installation
1. Copy the `custom_components/smart_announcements` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

### 1. Add the Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Smart Announcements" and select it

### 2. Setup Flow

The setup wizard guides you through configuration:

**Step 1 - Select People:**
- Choose which people in your home should receive announcements
- You can select multiple people using checkboxes

**Step 2 - Configure Each Person (2-step per person):**

*Part 1 - Language & TTS:*
- **Room Tracking Entity**: Device tracker or sensor that reports this person's current room
- **Language**: Choose from available language options
- **TTS Platform**: Which TTS service to use for this person
- **Enhance with AI**: Toggle AI enhancement for natural rephrasing
- **Translate Announcement**: Toggle message translation to selected language

*Part 2 - Voice & AI:*
- **Conversation Entity**: AI agent for enhancement/translation (only if either AI or translation enabled)
- **TTS Voice**: Voice selection (dynamically loaded based on TTS platform and language)

**Step 3 - Group Settings (only if multiple people):**

When multiple people are in the same room, use these settings instead of individual preferences.

*Part 1 - Language & TTS:*
- **Group Name/Addressee**: How to address groups (default: "Everyone", can be "Family", "Guys", etc.)
- **Language**: Language for group announcements
- **TTS Platform**: TTS service for groups
- **Enhance with AI**: Toggle AI enhancement
- **Translate Announcement**: Toggle message translation

*Part 2 - Voice & AI:*
- **Conversation Entity**: AI agent for groups (only if either AI or translation enabled)
- **TTS Voice**: Voice for group announcements

**Step 4 - Room Tracking Settings:**
- **Enable Home/Away Tracking**: Only announce if person entity shows "home" (disable to trust room tracking regardless of home/away state)
- **Enable Room Tracking**: Use device trackers to find people
- **Verify with Presence Sensors**: Confirm occupancy with sensors

**Step 5 - Select Rooms:**
- Choose which rooms should receive announcements
- Select multiple rooms using checkboxes

**Step 6 - Configure Each Room:**
- **Media Player**: Which speaker/display to use
- **Presence Sensors**: Occupancy sensors for verification (only if enabled in Step 4)

**Step 7 - Pre-Announce Sound:**
- **Enable Pre-Announce Sound**: Play a chime before announcements
- **Pre-Announce Sound URL**: Path to audio file (e.g., `/local/chime.mp3`)
- **Delay After Pre-Announce**: Seconds to wait after chime (0-10)

### 3. Managing Configuration

After setup, you can edit settings via **Configure** button:

**Global Settings:**
- Home/away tracking toggle
- Room tracking toggle
- Presence verification toggle
- Pre-announce sound settings
- Debug mode toggle

**Edit People:**
- Select a person to edit their settings
- Or choose "+ Add Person" to add new people

**Edit Rooms:**
- Select a room to edit its settings
- Or choose "+ Add Rooms" to add multiple rooms at once

**Group Settings:**
- Edit group announcement preferences (only if multiple people configured)
- Configure how groups are addressed

**Advanced Settings:**
- Customize AI prompts for your specific LLM
- Three customizable templates: translate-only, enhance-only, and both
- Useful for adapting to different LLMs (Claude, ChatGPT, Gemini, etc.)

## Usage

### Service: `smart_announcements.announce`

Send announcements to people based on their location.

#### Basic Announcement (to all occupied rooms)
```yaml
service: smart_announcements.announce
data:
  message: "Dinner is ready"
```

#### Target a Specific Person
```yaml
service: smart_announcements.announce
data:
  message: "Your package has arrived"
  target_person: "John"
```

#### Target Multiple People
```yaml
service: smart_announcements.announce
data:
  message: "Time for your meeting"
  target_person: "John, Alice"
```
If both are in the same room, uses group settings. If in different rooms, each gets announcement with their individual settings.

#### Target a Specific Area
```yaml
service: smart_announcements.announce
data:
  message: "Motion detected in the garage"
  target_area: living_room
```

#### With AI Enhancement
```yaml
service: smart_announcements.announce
data:
  message: "The washing machine has finished"
  enhance_with_ai: true
```

#### Without Pre-Announce Sound
```yaml
service: smart_announcements.announce
data:
  message: "Quiet announcement"
  pre_announce_sound: false
```

#### Emergency Announcement (Whole House)
```yaml
service: smart_announcements.announce
data:
  message: "Emergency! Everyone evacuate now!"
  room_tracking: false
  presence_verification: false
```
Disabling both room tracking and presence verification announces to **all configured rooms** regardless of occupancy - perfect for emergencies.

### Service Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `message` | string | Yes | The announcement message |
| `target_person` | string | No | Person name or comma-separated names (e.g., `"John"` or `"John, Alice"`) |
| `target_area` | string | No | Area ID (e.g., `living_room`) |
| `enhance_with_ai` | boolean | No | Override AI enhancement setting |
| `translate_announcement` | boolean | No | Override translation setting |
| `pre_announce_sound` | boolean | No | Override pre-announce sound setting |
| `room_tracking` | boolean | No | Override room tracking setting |
| `presence_verification` | boolean | No | Override presence verification setting |

### Enable/Disable Switches

The integration creates switches to control announcements:

**Per-Person Switches:**
- `switch.smart_announcements_john` - Enable/disable announcements for John
- `switch.smart_announcements_alice` - Enable/disable announcements for Alice

**Per-Room Switches:**
- `switch.smart_announcements_living_room` - Enable/disable Living Room announcements
- `switch.smart_announcements_bedroom` - Enable/disable Bedroom announcements

All switches are **ON by default** (enabled). Turn a switch OFF to disable announcements.

Each switch exposes its configuration as read-only attributes (TTS platform, voice, language, etc.).

## Room Tracking

Smart Announcements supports various room tracking methods:

### Bermuda / ESPresense Pattern
If your tracking entity reports the area name in its state:
```
sensor.person_room_presence
  state: "living_room"
```

### Area Attribute Pattern
If your tracking entity has an `area` attribute:
```
device_tracker.person_phone
  state: "home"
  attributes:
    area: "bedroom"
```

### Room Attribute Pattern
If your tracking entity has a `room` attribute:
```
sensor.person_location
  state: "home"
  attributes:
    room: "kitchen"
```

### Presence Verification

If enabled, the integration can verify room occupancy using presence sensors before announcing:

1. Person's tracking entity says they're in the living room
2. Integration checks living room's configured presence sensors
3. If ANY sensor is "on", announcement proceeds
4. If ALL sensors are "off", announcement is skipped

This prevents announcements to rooms where tracking may be stale.

## AI Enhancement & Translation

Smart Announcements supports two independent features via conversation agents:

**AI Enhancement** - Rephrases messages to be more engaging using your conversation agent's personality
**Translation** - Translates messages to the person's configured language

You can enable one, both, or neither. When both are enabled, the message is enhanced first, then translated.

### Examples

**Enhancement Only:**
- Original: "The washing machine has finished"
- Enhanced: "Hey! The washing machine just finished its cycle. Your laundry is ready to be moved to the dryer."

**Translation Only:**
- Original: "Dinner is ready"
- Translated: "夕食の準備ができました" (Japanese)

**Both Enhancement + Translation:**
- Original: "Motion detected in the garage"
- Result: AI makes it more engaging, then translates to the person's language

### Customizing AI Prompts

Different LLMs (Claude, ChatGPT, Gemini, etc.) interpret prompts differently. You can customize the AI prompts in **Advanced Settings** to get better results with your specific model.

The integration uses three prompt templates:
- **Translate-only**: Used when translation is enabled but enhancement is disabled
- **Enhance-only**: Used when enhancement is enabled but translation is disabled
- **Both**: Used when both enhancement and translation are enabled

Each template supports variables:
- `{language}` - The target language
- `{message}` - The announcement text

The default prompts work well for most cases, but you can adjust them if your LLM adds unwanted meta-commentary or doesn't follow instructions correctly.

## Debug Mode

Enable debug mode for comprehensive logging with emoji markers:

- 🔔 Announcement start/end
- 📝 Message content
- 👤 Target person
- 📍 Target area
- ⚙️ Configuration settings
- 🔍 Decision logic
- ✅/❌ Success/failure
- 🏠 Room processing
- 🤖 AI enhancement
- 🔔 Pre-announce sound
- 🎙️ TTS service calls

Debug logs show every decision point, making it easy to troubleshoot routing issues.

## Automation Examples

### Morning Announcements
```yaml
automation:
  - alias: "Morning Weather Announcement"
    trigger:
      - platform: time
        at: "07:00:00"
    condition:
      - condition: state
        entity_id: person.john
        state: "home"
    action:
      - service: smart_announcements.announce
        data:
          message: "Good morning! It's {{ states('sensor.outdoor_temperature') }}°F outside with {{ states('weather.home') }}. Have a great day!"
          target_person: person.john
          enhance_with_ai: true
```

### Package Delivery Notification
```yaml
automation:
  - alias: "Package Delivery Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door_camera_person
        to: "on"
    action:
      - service: smart_announcements.announce
        data:
          message: "Someone is at the front door. It might be a package delivery."
          enhance_with_ai: true
```

### Reminder When Arriving Home
```yaml
automation:
  - alias: "Arrival Reminder"
    trigger:
      - platform: state
        entity_id: person.alice
        to: "home"
    action:
      - service: smart_announcements.announce
        data:
          message: "Welcome home! Don't forget to take out the trash tonight."
          target_person: person.alice
```

### Multi-Language Household
```yaml
automation:
  - alias: "Dinner Ready (Multi-Language)"
    trigger:
      - platform: time
        at: "18:00:00"
    action:
      # Will automatically use each person's configured language
      - service: smart_announcements.announce
        data:
          message: "Dinner is ready"
          enhance_with_ai: true
```

## Troubleshooting

### Announcements Not Playing

**Check enable switches:**
- Verify person switch is ON: `switch.smart_announcements_john`
- Verify room switch is ON: `switch.smart_announcements_living_room`

**Check room tracking:**
- Enable debug mode in Global Settings
- Trigger an announcement and check logs
- Look for "📍 Area ID" to see which room was detected
- Verify the room tracking entity is reporting correctly

**Check media player:**
- Ensure the media player is powered on and connected
- Test TTS directly: `service: tts.speak` with the same media player
- Verify the media player supports TTS announcements

### Wrong Room Receiving Announcements

**Check room tracking entity:**
- Verify the person's room tracking entity is configured correctly
- Check that entity's current state matches the person's actual location
- Try a different device tracker or sensor

**Enable presence verification:**
- Add presence sensors to rooms in Room Settings
- Enable "Verify with Presence Sensors" in Global Settings
- This ensures tracking entity matches actual occupancy

### AI Enhancement or Translation Not Working

**Verify conversation entity:**
- Check that the conversation entity is configured for the person
- Test the conversation entity directly in Developer Tools
- Ensure the conversation agent is running and responding

**Check settings:**
- Person config: Is "Enhance with AI" or "Translate Announcement" enabled?
- Group config: Is "Enhance with AI" or "Translate Announcement" enabled (if multiple people in room)?
- Service call: Are you overriding with `enhance_with_ai: false` or `translate_announcement: false`?
- Note: Translation requires a conversation entity even if AI enhancement is disabled

**Customize prompts (if AI adds unwanted content):**
- Go to Smart Announcements → Configure → Advanced Settings
- Edit the AI prompt templates to work better with your specific LLM
- Different models (Claude, ChatGPT, Gemini) may need different prompt styles

### Pre-Announce Sound Not Playing

**Check file path:**
- File must be in `/config/www/` directory
- Use `/local/` prefix in config (e.g., `/local/chime.mp3`)
- Verify file exists and is a valid audio format

**Check pre-announce setting:**
- Global Settings: Is "Enable Pre-Announce Sound" ON?
- Service call: Are you overriding with `pre_announce_sound: false`?

### Debug Mode Issues

**Enable debug mode:**
1. Go to Smart Announcements → Configure
2. Select "Global Settings"
3. Enable "Debug Mode (verbose logging)"
4. Save

**View debug logs:**
1. Go to Settings → System → Logs
2. Look for entries with `[DEBUG]` prefix
3. Logs show every decision point with emoji markers

## Entity Exposure

When using AI enhancement, ensure your conversation agent has access to necessary entities. Some conversation agents (like MCP Assist) handle entity discovery automatically, while others may require manual entity exposure.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/mike-nott/smart-announcements/issues)
- **Discussions**: [GitHub Discussions](https://github.com/mike-nott/smart-announcements/discussions)
- **Home Assistant Community**: [Community Forum](https://community.home-assistant.io/)
