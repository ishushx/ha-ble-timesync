"""BLE connection and time-sync implementation."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient, BleakError
from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    CHAR_LIMIT,
    MODEL_AUTO,
    MODEL_LABELS,
    READ_AFTER_WRITE,
)
from .protocol import build_payload, detect_service_family, guess_model

_LOGGER = logging.getLogger(__name__)

# 源码没有等待 notify 订阅完成；这里给 CCCD 写入留一个很小的安全余量。
NOTIFY_SETTLE_SECONDS = 0.2


def _pick_characteristics(service: Any, model: str) -> tuple[Any, Any, Any, bool]:
    """Select read/write/notify characteristics using the app's rules."""
    characteristics = list(service.characteristics)
    limit = CHAR_LIMIT[model]
    if limit is not None:
        characteristics = characteristics[:limit]

    read_char = write_char = notify_char = None
    write_with_response = False

    for char in characteristics:
        props = {str(prop).lower() for prop in char.properties}
        if read_char is None and "read" in props:
            read_char = char
        if write_char is None and ("write" in props or "write-without-response" in props):
            write_char = char
            write_with_response = "write" in props
        # 源码里的写法是每遇到 notify/indicate 就覆盖一次，因此最终取的是
        # 扫描范围内最后一个可通知 characteristic（这里保持一致）。
        if "notify" in props or "indicate" in props:
            notify_char = char

    return read_char, write_char, notify_char, write_with_response


def _find_service(client: BleakClient) -> tuple[Any, str]:
    for service in client.services:
        family = detect_service_family(str(service.uuid))
        if family is not None:
            return service, family
    raise HomeAssistantError("未发现 FF00/FFE0/9900/FFF0 服务")


async def async_sync_time(
    hass: HomeAssistant,
    address: str,
    model: str = MODEL_AUTO,
    *,
    wait_notify: bool = True,
    timeout: float = 12.0,
    notify_timeout: float = 3.0,
) -> dict[str, Any]:
    """Connect through the best available proxy/adapter and write one time frame."""
    ble_device = async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise HomeAssistantError(
            f"{address} 当前不可连接：没有在线且支持连接的蓝牙代理/适配器"
        )

    notifications: list[str] = []
    notify_event = asyncio.Event()

    def _on_notify(characteristic: Any, data: bytearray) -> None:
        raw_hex = bytes(data).hex()
        notifications.append(raw_hex)
        _LOGGER.debug(
            "[%s] notify %s: %s", address, characteristic.uuid, raw_hex
        )
        notify_event.set()

    client = BleakClient(ble_device, timeout=timeout)
    try:
        await client.connect()
    except (BleakError, asyncio.TimeoutError, OSError) as err:
        raise HomeAssistantError(f"连接 {address} 失败: {err}") from err

    try:
        service, family = _find_service(client)
        selected_model = model
        if selected_model == MODEL_AUTO:
            selected_model = guess_model(family, ble_device.name)
            if selected_model is None:
                raise HomeAssistantError(
                    f"无法从 Service {service.uuid} / 名称 {ble_device.name} 判断分支"
                )

        read_char, write_char, notify_char, write_with_response = (
            _pick_characteristics(service, selected_model)
        )
        if write_char is None:
            raise HomeAssistantError("目标服务下没有可写 characteristic")

        _LOGGER.debug(
            "[%s] service=%s family=%s model=%s write=%s notify=%s read=%s response=%s",
            address,
            service.uuid,
            family,
            selected_model,
            getattr(write_char, "uuid", None),
            getattr(notify_char, "uuid", None),
            getattr(read_char, "uuid", None),
            write_with_response,
        )

        if notify_char is not None:
            await client.start_notify(notify_char, _on_notify)
            if NOTIFY_SETTLE_SECONDS:
                await asyncio.sleep(NOTIFY_SETTLE_SECONDS)

        payload = build_payload(selected_model, dt_util.now())
        _LOGGER.debug("[%s] write payload: %s", address, payload.hex())

        await client.write_gatt_char(
            write_char, payload, response=write_with_response
        )

        ack_received = False
        if wait_notify and notify_char is not None:
            try:
                await asyncio.wait_for(notify_event.wait(), timeout=notify_timeout)
                ack_received = True
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "[%s] %.1f 秒内未收到 notify；写入已完成，但设备未确认",
                    address,
                    notify_timeout,
                )

        read_value = None
        if READ_AFTER_WRITE[selected_model]:
            try:
                # 源码读取的是“写入特性”，不是 read 特性。
                read_value = bytes(await client.read_gatt_char(write_char)).hex()
            except (BleakError, ValueError) as err:
                _LOGGER.debug("[%s] 写后读取失败: %s", address, err)

        return {
            "address": address,
            "model": selected_model,
            "model_label": MODEL_LABELS[selected_model],
            "service_uuid": str(service.uuid),
            "write_uuid": str(write_char.uuid),
            "notify_uuid": str(notify_char.uuid) if notify_char else None,
            "read_uuid": str(read_char.uuid) if read_char else None,
            "write_with_response": write_with_response,
            "payload_hex": payload.hex(),
            "notify_ack": ack_received,
            "notifications": notifications,
            "read_value": read_value,
            "synced_at": dt_util.now().isoformat(),
        }
    except BleakError as err:
        raise HomeAssistantError(f"BLE 操作失败: {err}") from err
    finally:
        if client.is_connected:
            await client.disconnect()
