"""BLE coordinator for the Gasolina integration."""
from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_register_callback,
)
from homeassistant.core import HomeAssistant, callback

from .const import DEFAULT_BOTTLE_SIZE
from .models import GasolinaData, parse_advertisement

_LOGGER = logging.getLogger(__name__)


class GasolinaCoordinator:
    """Manages passive BLE updates and GATT operations for a single Gasolina sensor."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self.bottle_size: str = DEFAULT_BOTTLE_SIZE
        self.data: GasolinaData | None = None
        self._listeners: list[Callable[[], None]] = []
        self._cancel_callback: Callable[[], None] | None = None

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register a listener; returns a function that removes it."""
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
        _LOGGER.debug(
            "%s: fill=%.1f%% battery=%d%% bottle=%s",
            self.address,
            new_data.fill_level,
            new_data.battery,
            self.bottle_size,
        )
        self._notify_listeners()

    async def async_start(self) -> None:
        """Start passive BLE listener and read bottle size via GATT."""
        self._cancel_callback = async_register_callback(
            self.hass,
            self._async_handle_update,
            BluetoothCallbackMatcher(address=self.address),
            BluetoothScanningMode.PASSIVE,
        )
        _LOGGER.debug("Started BLE listener for %s", self.address)

        # Read current bottle size from device via GATT (non-blocking)
        self.hass.async_create_task(self._async_init_bottle_size())

    async def _async_init_bottle_size(self) -> None:
        """Read bottle size from device via GATT and notify listeners."""
        from .gatt import async_read_bottle_size
        size = await async_read_bottle_size(self.hass, self.address)
        if size != self.bottle_size:
            _LOGGER.info(
                "%s: bottle size initialised from device: %s", self.address, size
            )
            self.bottle_size = size
            self._notify_listeners()

    async def async_stop(self) -> None:
        """Stop listening for BLE advertisements."""
        if self._cancel_callback:
            self._cancel_callback()
            self._cancel_callback = None
            _LOGGER.debug("Stopped BLE listener for %s", self.address)
