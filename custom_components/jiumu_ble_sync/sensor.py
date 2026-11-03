"""Sensor platform: last successful sync timestamp."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JiumuCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: JiumuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([JiumuLastSyncSensor(coordinator, entry)])


class JiumuLastSyncSensor(CoordinatorEntity[JiumuCoordinator], SensorEntity):
    """Expose the last successful sync time."""

    _attr_has_entity_name = True
    _attr_name = "最后校时时间"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: JiumuCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        address = entry.data["address"]
        self._attr_unique_id = f"{address}_last_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="Jiumu / BlueToothTool",
        )

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_sync
