"""Config flow for Gasolina integration.

Setup steps
-----------
1. scan         – BLE scan list with Refresh button
2. bond         – press SYNC, HA bonds via GATT
3. bottle_size  – choose bottle size
→ Entry created

Auto-discovery
--------------
When HA discovers the device via the bluetooth matcher it jumps straight to
step 2 (bond), skipping the scan step.
"""
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
    BOTTLE_SIZE_TO_BYTE,
    CONF_SCAN_INTERVAL,
    DEFAULT_BOTTLE_SIZE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCAN_INTERVAL_OPTIONS,
)
from .models import is_gasolina_device

_LOGGER = logging.getLogger(__name__)

_BOND_TIMEOUT = 30.0
_RESCAN_KEY   = "__rescan__"   # sentinel value in address dropdown


def _device_label(info: BluetoothServiceInfoBleak) -> str:
    """Human-readable label: name + address, or just address."""
    name = info.name or ""
    if name:
        return f"{name}  ({info.address})"
    return info.address


class GasolinaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """4-step config flow: scan → bond → bottle size → done."""

    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._name: str | None = None

    # ------------------------------------------------------------------ #
    # Auto-discovery via Bluetooth matcher                                 #
    # ------------------------------------------------------------------ #
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not is_gasolina_device(discovery_info):
            return self.async_abort(reason="not_supported")
        self._address = discovery_info.address
        self._name = discovery_info.name or discovery_info.address
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """HA-required step for auto-discovered devices – forwards directly to bond."""
        return await self.async_step_bond(user_input)

    # ------------------------------------------------------------------ #
    # Step 1: Manual entry point – shows scan list                        #
    # ------------------------------------------------------------------ #
    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """Show discovered Gasolina sensors; re-scan if 'Rescan' is chosen."""
        return await self.async_step_scan(user_input)

    async def async_step_scan(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """BLE scan list with a built-in Rescan option."""
        errors: dict[str, str] = {}

        if user_input is not None:
            chosen = user_input.get("address", "")
            if chosen and chosen != _RESCAN_KEY:
                # User selected a real device → go to bonding
                self._address = chosen
                await self.async_set_unique_id(chosen, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                # Retrieve cached name for display
                for info in async_discovered_service_info(self.hass):
                    if info.address == chosen:
                        self._name = info.name or chosen
                        break
                else:
                    self._name = chosen
                return await self.async_step_bond()
            # Otherwise: rescan (fall through to rebuild the form)

        # Build device list (exclude already-configured addresses)
        configured = self._async_current_ids()
        devices: dict[str, str] = {}
        for info in async_discovered_service_info(self.hass):
            if info.address in configured:
                continue
            if is_gasolina_device(info):
                devices[info.address] = _device_label(info)

        if not devices:
            # No devices yet – show a waiting screen with only the Rescan option
            return self.async_show_form(
                step_id="scan",
                data_schema=vol.Schema(
                    {
                        vol.Required("address", default=_RESCAN_KEY): vol.In(
                            {_RESCAN_KEY: "🔄  Erneut suchen…"}
                        )
                    }
                ),
                description_placeholders={},
                errors={"base": "no_devices_found_yet"},
            )

        # Add "Rescan" as last option so user can refresh without restarting
        options = {**devices, _RESCAN_KEY: "🔄  Erneut suchen…"}

        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Required("address"): vol.In(options)
                }
            ),
            description_placeholders={},
            errors=errors,
        )

    # ------------------------------------------------------------------ #
    # Step 2: Bond – press SYNC then click Pair                           #
    # ------------------------------------------------------------------ #
    async def async_step_bond(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            result = await self._async_attempt_bond()
            if result == "ok":
                return await self.async_step_bottle_size()
            errors["base"] = result  # "bond_failed" | "bond_timeout"

        return self.async_show_form(
            step_id="bond",
            description_placeholders={"name": self._name or self._address},
            errors=errors,
        )

    async def _async_attempt_bond(self) -> str:
        try:
            from bleak import BleakClient
            from homeassistant.components.bluetooth import async_ble_device_from_address

            device = async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
            if device is None:
                return "bond_failed"

            async with BleakClient(device, timeout=_BOND_TIMEOUT) as client:
                try:
                    await asyncio.wait_for(client.pair(), timeout=15.0)
                    _LOGGER.info("%s: initial BLE bond established ✓", self._address)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.debug("%s: pair() optional – %s", self._address, exc)
            return "ok"

        except asyncio.TimeoutError:
            return "bond_timeout"
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("%s: bond failed – %s", self._address, exc)
            return "bond_failed"

    # ------------------------------------------------------------------ #
    # Step 3: Bottle size                                                  #
    # ------------------------------------------------------------------ #
    async def async_step_bottle_size(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._name or self._address,
                data={
                    "address": self._address,
                    "bottle_size": user_input["bottle_size"],
                    "bonded": True,
                },
            )

        return self.async_show_form(
            step_id="bottle_size",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "bottle_size", default=DEFAULT_BOTTLE_SIZE
                    ): vol.In(list(BOTTLE_SIZE_TO_BYTE.keys()))
                }
            ),
        )

    # ------------------------------------------------------------------ #
    # Options flow                                                         #
    # ------------------------------------------------------------------ #
    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return GasolinaOptionsFlow(config_entry)


class GasolinaOptionsFlow(config_entries.OptionsFlow):
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
