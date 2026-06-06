"""BLE coordinator for the Gasolina integration."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_register_callback,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import DEFAULT_BOTTLE_SIZE
from .models import GasolinaData, parse_advertisement

_LOGGER = logging.getLogger(__name__)


class GasolinaCoordinator:
    """Manages passive BLE updates and GATT operations for a single Gasolina sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        scan_interval: int = 0,
    ) -> None:
        self.hass = hass
        self.address = address
        self.bottle_size: str = DEFAULT_BOTTLE_SIZE
        self.scan_interval: int = scan_interval
        self.data: GasolinaData | None = None
        self._listeners: list[Callable[[], None]] = []
        self._cancel_callback: Callable[[], None] | None = None
        self._cancel_interval: Callable[[], None] | None = None
        self._bottle_size_user_set: bool = False
        self._gatt_trigger = None  # GattOnAdvertisementTrigger, set in async_start

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update_callback)

        def remove() -> None:
            self._listeners.remove(update_callback)

        return remove

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            listener()

    @callback
    def _async_handle_update(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        new_data = parse_advertisement(service_info)
        if new_data is None:
            return
        self.data = new_data

        # Notify the GATT trigger that the device is awake
        if self._gatt_trigger is not None:
            self._gatt_trigger.on_advertisement()

        _LOGGER.debug(
            "%s: fill=%.1f%% battery=%d%% bottle=%s",
            self.address,
            new_data.fill_level,
            new_data.battery,
            self.bottle_size,
        )
        self._notify_listeners()

    async def async_start(self) -> None:
        """Start passive BLE listener, GATT trigger, and periodic scan."""
        from .gatt import GattOnAdvertisementTrigger

        self._gatt_trigger = GattOnAdvertisementTrigger(
            self.hass, self.address, timeout=120
        )

        self._cancel_callback = async_register_callback(
            self.hass,
            self._async_handle_update,
            BluetoothCallbackMatcher(address=self.address),
            BluetoothScanningMode.PASSIVE,
        )
        _LOGGER.debug("Started BLE listener for %s", self.address)

        # Read bottle size after next advertisement (non-blocking)
        self.hass.async_create_task(self._async_init_bottle_size())

        if self.scan_interval > 0:
            self._cancel_interval = async_track_time_interval(
                self.hass,
                self._async_periodic_gatt_read,
                timedelta(seconds=self.scan_interval),
            )

    async def _async_init_bottle_size(self) -> None:
        """Read bottle size on the next advertisement (device is awake then)."""
        if self._bottle_size_user_set:
            return

        _LOGGER.debug(
            "%s: waiting for advertisement before reading bottle size via GATT",
            self.address,
        )

        from .gatt import async_read_bottle_size

        # Wait for the next fresh advertisement via trigger
        async def _read(client):
            from .const import GATT_CHAR_RW_UUID, BYTE_TO_BOTTLE_SIZE
            import asyncio
            raw = await asyncio.wait_for(
                client.read_gatt_char(GATT_CHAR_RW_UUID), timeout=10.0
            )
            if raw:
                return BYTE_TO_BOTTLE_SIZE.get(raw[0], DEFAULT_BOTTLE_SIZE)
            return DEFAULT_BOTTLE_SIZE

        try:
            size = await self._gatt_trigger.run_on_next_advertisement(_read)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("%s: GATT init read failed – %s", self.address, exc)
            return

        if self._bottle_size_user_set:
            return

        if size and size != self.bottle_size:
            _LOGGER.info("%s: bottle size from GATT = %s", self.address, size)
            self.bottle_size = size
            self._notify_listeners()

    @callback
    def _async_periodic_gatt_read(self, _now=None) -> None:
        if not self._bottle_size_user_set:
            self.hass.async_create_task(self._async_init_bottle_size())

    def set_bottle_size_from_user(self, bottle_size: str) -> None:
        """Called by the select entity when the user explicitly picks a size."""
        self._bottle_size_user_set = True
        self.bottle_size = bottle_size
        self._notify_listeners()

    async def async_write_bottle_size(self, bottle_size: str) -> bool:
        """Write bottle size via GATT, waiting for the next advertisement first."""
        from .gatt import BOTTLE_SIZE_TO_BYTE, _connect_and_run
        import asyncio

        write_byte = BOTTLE_SIZE_TO_BYTE.get(bottle_size)
        if write_byte is None:
            return False

        async def _write(client):
            from .const import GATT_CHAR_RW_UUID
            await asyncio.wait_for(
                client.write_gatt_char(GATT_CHAR_RW_UUID, bytes([write_byte]), response=False),
                timeout=10.0,
            )
            _LOGGER.info(
                "%s: bottle size set to %s (0x%02X) via GATT",
                self.address, bottle_size, write_byte,
            )
            return True

        try:
            result = await self._gatt_trigger.run_on_next_advertisement(_write)
            return result is True
        except Exception as exc:  # noqa: BLE001
            _LOGGER.error("%s: GATT write failed – %s", self.address, exc)
            return False

    async def async_stop(self) -> None:
        if self._cancel_callback:
            self._cancel_callback()
            self._cancel_callback = None
        if self._cancel_interval:
            self._cancel_interval()
            self._cancel_interval = None
        _LOGGER.debug("Stopped coordinator for %s", self.address)
