"""Jiumu BLE time sync integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ADDRESS,
    CONF_MODEL,
    CONF_WAIT_NOTIFY,
    DOMAIN,
    MODEL_AUTO,
    MODELS,
)
from .coordinator import JiumuCoordinator
from .sync import async_sync_time

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["button", "sensor"]

SERVICE_SYNC_TIME = "sync_time"
SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADDRESS): cv.string,
        vol.Optional(CONF_MODEL, default=MODEL_AUTO): vol.In(MODELS),
        vol.Optional(CONF_WAIT_NOTIFY, default=True): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})

    if not hass.services.has_service(DOMAIN, SERVICE_SYNC_TIME):

        async def _async_handle_sync(call: ServiceCall) -> dict:
            address = call.data[CONF_ADDRESS].strip().upper()
            return await async_sync_time(
                hass,
                address,
                call.data.get(CONF_MODEL, MODEL_AUTO),
                wait_notify=call.data.get(CONF_WAIT_NOTIFY, True),
            )

        hass.services.async_register(
            DOMAIN,
            SERVICE_SYNC_TIME,
            _async_handle_sync,
            schema=SERVICE_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = JiumuCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
