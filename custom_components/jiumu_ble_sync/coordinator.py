"""Coordinator for one Jiumu BLE time-sync device."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_ADDRESS, CONF_MODEL, DOMAIN
from .sync import async_sync_time

_LOGGER = logging.getLogger(__name__)


class JiumuCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Run syncs on demand; no polling."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.data[CONF_ADDRESS]}",
            update_interval=None,
        )
        self.address: str = entry.data[CONF_ADDRESS]
        self.model: str = entry.data.get(CONF_MODEL, "auto")
        self.last_sync: datetime | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            result = await async_sync_time(self.hass, self.address, self.model)
        except (HomeAssistantError, asyncio.TimeoutError, OSError) as err:
            raise UpdateFailed(str(err)) from err

        self.last_sync = dt_util.utcnow()
        result["last_sync"] = self.last_sync
        return result
