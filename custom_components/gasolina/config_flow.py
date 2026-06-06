"""Config flow for Gasolina integration."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCAN_INTERVAL_OPTIONS,
)
from .models import is_gasolina_device

_LOGGER = logging.getLogger(__name__)

_BOND_ATTEMPT_TIMEOUT = 30.0   # seconds to wait for GATT connection during bonding


class GasolinaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Gasolina.

    Steps
    -----
    1. ``bluetooth`` / ``user``  – discover / select device
    2. ``bluetooth_confirm``     – confirm the detected device
    3. ``bond``                  – user presses SYNC, HA bonds via GATT
    4. Entry is created
    """

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None

    # ------------------------------------------------------------------
    # Step 1a: automatic Bluetooth discovery
    # ------------------------------------------------------------------
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not is_gasolina_device(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovery_info = discovery_info
        self._address = discovery_info.address
        self._name = discovery_info.name or discovery_info.address
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_bluetooth_confirm()

    # ------------------------------------------------------------------
    # Step 1b: manual device selection
    # ------------------------------------------------------------------
    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._address = user_input["address"]
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._name = self._discovered_devices.get(self._address, self._address)
            return await self.async_step_bond()

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

    # ------------------------------------------------------------------
    # Step 2: confirm discovered device, then go to bonding
    # ------------------------------------------------------------------
    async def async_step_bluetooth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        assert self._discovery_info is not None
        if user_input is not None:
            return await self.async_step_bond()

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._name},
        )

    # ------------------------------------------------------------------
    # Step 3: SYNC + initial BLE bonding
    # ------------------------------------------------------------------
    async def async_step_bond(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Ask the user to press SYNC, then attempt GATT bonding."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # User clicked "Bond" – attempt the GATT connection + pairing now
            bond_result = await self._async_attempt_bond()
            if bond_result == "ok":
                return self.async_create_entry(
                    title=self._name or self._address,
                    data={"address": self._address, "bonded": True},
                )
            errors["base"] = bond_result  # "bond_failed" or "bond_timeout"

        return self.async_show_form(
            step_id="bond",
            description_placeholders={"name": self._name or self._address},
            errors=errors,
        )

    async def _async_attempt_bond(self) -> str:
        """Try to connect and pair via GATT.  Returns 'ok' or an error key."""
        try:
            from bleak import BleakClient
            from homeassistant.components.bluetooth import async_ble_device_from_address

            device = async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
            if device is None:
                _LOGGER.warning(
                    "%s: no connectable device found for bonding", self._address
                )
                return "bond_failed"

            _LOGGER.debug("%s: attempting initial GATT bond", self._address)
            async with BleakClient(device, timeout=_BOND_ATTEMPT_TIMEOUT) as client:
                try:
                    await asyncio.wait_for(client.pair(), timeout=15.0)
                    _LOGGER.info("%s: initial BLE bond established ✓", self._address)
                except Exception as exc:  # noqa: BLE001
                    # Some devices don't need explicit pairing – treat as success
                    # only if the connection itself succeeded (we got here).
                    _LOGGER.debug(
                        "%s: pair() not required or not supported – %s", self._address, exc
                    )
            return "ok"

        except asyncio.TimeoutError:
            _LOGGER.warning("%s: GATT bond timed out", self._address)
            return "bond_timeout"
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("%s: GATT bond failed – %s", self._address, exc)
            return "bond_failed"

    # ------------------------------------------------------------------
    # Options flow (scan interval)
    # ------------------------------------------------------------------
    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return GasolinaOptionsFlow(config_entry)


class GasolinaOptionsFlow(config_entries.OptionsFlow):
    """Options flow: configure periodic GATT scan interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_seconds = self._config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_label = next(
            (k for k, v in SCAN_INTERVAL_OPTIONS.items() if v == current_seconds),
            "Deaktiviert",
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current_label
                    ): vol.In(list(SCAN_INTERVAL_OPTIONS.keys()))
                }
            ),
        )
