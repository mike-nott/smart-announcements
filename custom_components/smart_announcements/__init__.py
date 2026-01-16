"""The Smart Announcements integration."""

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    ATTR_MESSAGE,
    ATTR_TARGET_PERSON,
    ATTR_TARGET_AREA,
    ATTR_ENHANCE_WITH_AI,
    ATTR_TRANSLATE_ANNOUNCEMENT,
    ATTR_PRE_ANNOUNCE_SOUND,
)
from .announcer import Announcer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch"]

SERVICE_ANNOUNCE = "announce"
SERVICE_ANNOUNCE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TARGET_PERSON): cv.string,
        vol.Optional(ATTR_TARGET_AREA): cv.string,
        vol.Optional(ATTR_ENHANCE_WITH_AI): cv.boolean,
        vol.Optional(ATTR_TRANSLATE_ANNOUNCEMENT): cv.boolean,
        vol.Optional(ATTR_PRE_ANNOUNCE_SOUND): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Smart Announcements component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Smart Announcements from a config entry."""
    _LOGGER.info("Setting up Smart Announcements integration")

    hass.data.setdefault(DOMAIN, {})

    try:
        # Create announcer instance
        announcer = Announcer(hass, entry)

        # Store entry data
        hass.data[DOMAIN][entry.entry_id] = {
            "config": dict(entry.data),
            "announcer": announcer,
            "enabled": {
                "people": {},
                "rooms": {},
            },
        }

        # Register the announce service (only once)
        if not hass.services.has_service(DOMAIN, SERVICE_ANNOUNCE):
            async def handle_announce(call: ServiceCall) -> None:
                """Handle the announce service call."""
                await _async_handle_announce(hass, entry, call)

            hass.services.async_register(
                DOMAIN,
                SERVICE_ANNOUNCE,
                handle_announce,
                schema=SERVICE_ANNOUNCE_SCHEMA,
            )
            _LOGGER.info("Registered %s.%s service", DOMAIN, SERVICE_ANNOUNCE)

        # Forward entry setup to platforms (switch for mute entities)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        _LOGGER.info("Smart Announcements setup complete")
        return True

    except Exception as err:
        _LOGGER.error("Failed to setup Smart Announcements: %s", err)
        raise ConfigEntryNotReady(f"Setup failed: {err}") from err


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Smart Announcements")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Unregister service if no entries left
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_ANNOUNCE)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def _async_handle_announce(
    hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall
) -> None:
    """Handle the announce service call."""
    message = call.data.get(ATTR_MESSAGE)
    target_person = call.data.get(ATTR_TARGET_PERSON)
    target_area = call.data.get(ATTR_TARGET_AREA)
    enhance_with_ai = call.data.get(ATTR_ENHANCE_WITH_AI)
    translate_announcement = call.data.get(ATTR_TRANSLATE_ANNOUNCEMENT)
    pre_announce_sound = call.data.get(ATTR_PRE_ANNOUNCE_SOUND)

    _LOGGER.debug(
        "Announce service called: message=%s, target_person=%s, target_area=%s",
        message,
        target_person,
        target_area,
    )

    # Get the announcer instance
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    announcer = entry_data.get("announcer")

    if not announcer:
        _LOGGER.error("Announcer not initialized")
        return

    # Call the announcer
    await announcer.async_announce(
        message=message,
        target_person=target_person,
        target_area=target_area,
        enhance_with_ai=enhance_with_ai,
        translate_announcement=translate_announcement,
        pre_announce_sound=pre_announce_sound,
    )
