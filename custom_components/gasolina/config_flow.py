"""Config flow for Gasolina integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.data_entry_flow import FlowResult

from .const import BOTTLE_ECHO_MAX, CONF_BOTTLE_SIZE, DEFAULT_BOTTLE_SIZE, DOMAIN
from .models import is_gasolina_device

_LOGGER = logging.getLogger(__name__)

BOTTLE_SIZE_OPTIONS = {size: size for size in BOTTLE_ECHO_MAX}


class GasolinaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Gasolina."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle automatic Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        if not is_gasolina_device(discovery_info):
            return self.async_abort(reason="not_supported")

        self._discovery_info = discovery_info
        self._address = discovery_info.address
        self._name = discovery_info.name or discovery_info.address
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Confirm a discovered Gasolina sensor."""
        assert self._discovery_info is not None

        if user_input is not None:
            return await self.async_step_bottle_size()

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._name},
        )

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Handle manual setup; shows a list of discovered Gasolina sensors."""
        if user_input is not None:
            self._address = user_input["address"]
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._name = self._discovered_devices.get(self._address, self._address)
            return await self.async_step_bottle_size()

        configured = self._async_current_ids()
        for info in async_discovered_service_info(self.hass):
            if info.address not in configured and is_gasolina_device(info):
                self._discovered_devices[info.address] = info.name or info.address

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("address"): vol.In(
                        {
                            addr: f"{name} ({addr})"
                            for addr, name in self._discovered_devices.items()
                        }
                    )
                }
            ),
        )

    async def async_step_bottle_size(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Ask for the gas bottle size."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name or self._address,
                data={
                    "address": self._address,
                    CONF_BOTTLE_SIZE: user_input[CONF_BOTTLE_SIZE],
                },
            )

        return self.async_show_form(
            step_id="bottle_size",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BOTTLE_SIZE, default=DEFAULT_BOTTLE_SIZE
                    ): vol.In(BOTTLE_SIZE_OPTIONS)
                }
            ),
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow to allow changing bottle size later."""
        return GasolinaOptionsFlow(config_entry)


class GasolinaOptionsFlow(config_entries.OptionsFlow):
    """Allow the user to change the bottle size after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._config_entry.data.get(CONF_BOTTLE_SIZE, DEFAULT_BOTTLE_SIZE)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_BOTTLE_SIZE, default=current): vol.In(
                        BOTTLE_SIZE_OPTIONS
                    )
                }
            ),
        )
