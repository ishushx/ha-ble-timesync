"""Button platform: one 'sync now' button per device."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODEL_LABELS
from .coordinator import JiumuCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: JiumuCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([JiumuSyncButton(coordinator, entry)])


class JiumuSyncButton(CoordinatorEntity[JiumuCoordinator], ButtonEntity):
    """Trigger one BLE time sync."""

    _attr_has_entity_name = True
    _attr_name = "立即校时"
    _attr_icon = "mdi:clock-check"

    def __init__(self, coordinator: JiumuCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        address = entry.data["address"]
        self._attr_unique_id = f"{address}_sync_now"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="Jiumu / BlueToothTool",
            model=MODEL_LABELS.get(entry.data.get("model", "auto")),
        )

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
        if not self.coordinator.last_update_success:
            raise HomeAssistantError(
                f"校时失败: {self.coordinator.last_exception}"
            )
