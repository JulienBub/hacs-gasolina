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

    def __init__(self, hass: HomeAssistant, address: str, scan_interval: int = 0) -> None:
        self.hass = hass
        self.address = address
        self.bottle_size: str = DEFAULT_BOTTLE_SIZE
        self.scan_interval: int = scan_interval  # seconds; 0 = disabled
        self.data: GasolinaData | None = None
        self._listeners: list[Callable[[], None]] = []
        self._cancel_callback: Callable[[], None] | None = None
        self._cancel_interval: Callable[[], None] | None = None
        # Flag: True once user has explicitly set bottle size via select entity.
        # Prevents the async GATT init task from overwriting the user's choice.
        self._bottle_size_user_set: bool = False

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
        """Start passive BLE listener, read bottle size via GATT, set up periodic scan."""
        self._cancel_callback = async_register_callback(
            self.hass,
            self._async_handle_update,
            BluetoothCallbackMatcher(address=self.address),
            BluetoothScanningMode.PASSIVE,
        )
        _LOGGER.debug("Started BLE listener for %s", self.address)

        # Initial GATT read (non-blocking background task)
        self.hass.async_create_task(self._async_gatt_read_bottle_size())

        # Periodic GATT read (if configured)
        if self.scan_interval > 0:
            self._cancel_interval = async_track_time_interval(
                self.hass,
                self._async_periodic_gatt_read,
                timedelta(seconds=self.scan_interval),
            )
            _LOGGER.debug(
                "%s: periodic GATT scan every %ds", self.address, self.scan_interval
            )

    async def _async_gatt_read_bottle_size(self) -> None:
        """Read bottle size from device via GATT.

        Only updates coordinator.bottle_size if the user has NOT already
        set it manually – prevents race-condition overwrite.
        """
        if self._bottle_size_user_set:
            _LOGGER.debug("%s: skipping GATT init read (user already set)", self.address)
            return

        from .gatt import async_read_bottle_size
        size = await async_read_bottle_size(self.hass, self.address)

        # Guard again after the await – user might have set it while we were connecting
        if self._bottle_size_user_set:
            _LOGGER.debug(
                "%s: discarding GATT read result (%s), user set it in the meantime",
                self.address, size,
            )
            return

        if size != self.bottle_size:
            _LOGGER.info("%s: bottle size from GATT = %s", self.address, size)
            self.bottle_size = size
            self._notify_listeners()

    @callback
    def _async_periodic_gatt_read(self, _now=None) -> None:
        """Trigger a periodic GATT bottle-size refresh."""
        if not self._bottle_size_user_set:
            self.hass.async_create_task(self._async_gatt_read_bottle_size())

    def set_bottle_size_from_user(self, bottle_size: str) -> None:
        """Called by the select entity when the user explicitly picks a size."""
        self._bottle_size_user_set = True
        self.bottle_size = bottle_size
        self._notify_listeners()

    async def async_stop(self) -> None:
        """Stop BLE listener and periodic scan."""
        if self._cancel_callback:
            self._cancel_callback()
            self._cancel_callback = None
        if self._cancel_interval:
            self._cancel_interval()
            self._cancel_interval = None
        _LOGGER.debug("Stopped coordinator for %s", self.address)
