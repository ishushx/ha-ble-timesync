"""Config flow: Bluetooth auto-discovery + explicit confirmation."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_ADDRESS,
    CONF_MODEL,
    CONF_NAME,
    DOMAIN,
    MODEL_AUTO,
    MODEL_LABELS,
    MODELS,
)
from .protocol import detect_service_family, guess_model

MAC_RE = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class JiumuBleSyncConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle discovery and manual fallback."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: BluetoothServiceInfoBleak | None = None
        self._suggested_model = MODEL_AUTO

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Called by HA when an advertisement matches manifest bluetooth matchers."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovered = discovery_info
        name = discovery_info.name or discovery_info.address
        family = None
        for service_uuid in discovery_info.service_uuids:
            family = detect_service_family(service_uuid)
            if family is not None:
                break

        self._suggested_model = guess_model(family, name) or MODEL_AUTO
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the scan result and wait for explicit user confirmation."""
        assert self._discovered is not None

        if user_input is not None:
            return self.async_create_entry(
                title=self._discovered.name or self._discovered.address,
                data={
                    CONF_ADDRESS: self._discovered.address,
                    CONF_MODEL: user_input[CONF_MODEL],
                    CONF_NAME: self._discovered.name or self._discovered.address,
                },
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODEL, default=self._suggested_model): vol.In(
                        MODELS
                    )
                }
            ),
            description_placeholders={
                "name": self._discovered.name or "未知",
                "address": self._discovered.address,
                "model": MODEL_LABELS[self._suggested_model],
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual fallback for devices that do not advertise a matchable UUID/name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if not MAC_RE.match(address):
                errors["base"] = "invalid_address"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=address,
                    data={
                        CONF_ADDRESS: address,
                        CONF_MODEL: user_input[CONF_MODEL],
                        CONF_NAME: address,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_MODEL, default=MODEL_AUTO): vol.In(MODELS),
                }
            ),
            errors=errors,
        )
