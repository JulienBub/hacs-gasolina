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

        # (GATT map already captured; dump disabled. No on-start GATT op so the
        # connection slot stays free for user-triggered bottle-size writes.)

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

    async def _async_dump_gatt(self) -> None:
        """One-shot diagnostic: connect and log the full GATT table.

        Logs every service + characteristic with its properties and current
        readable value, so we can identify which characteristic actually
        stores the bottle size (the one that reads 0x06 for an 11kg bottle).
        """
        async def _dump(client):
            import asyncio as _asyncio
            _LOGGER.warning("=== GATT-DUMP for %s START ===", self.address)
            services = client.services
            try:
                service_list = list(services)
            except TypeError:
                service_list = list(getattr(services, "services", {}).values())
            for service in service_list:
                _LOGGER.warning("GATT-DUMP service %s", service.uuid)
                for char in service.characteristics:
                    props = ",".join(char.properties)
                    value_hex = "-"
                    if "read" in char.properties:
                        try:
                            raw = await _asyncio.wait_for(
                                client.read_gatt_char(char.uuid), timeout=3.0
                            )
                            value_hex = raw.hex() if raw else "empty"
                        except Exception as exc:  # noqa: BLE001
                            value_hex = f"read-error:{exc}"
                    _LOGGER.warning(
                        "GATT-DUMP   char %s [%s] = %s",
                        char.uuid, props, value_hex,
                    )
            _LOGGER.warning("=== GATT-DUMP for %s END ===", self.address)
            return True

        try:
            await self._gatt_trigger.run_on_next_advertisement(_dump)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("%s: GATT dump failed – %s", self.address, exc)

    @callback
    def _async_periodic_gatt_read(self, _now=None) -> None:
        if not self._bottle_size_user_set:
            self.hass.async_create_task(self._async_init_bottle_size())

    def set_bottle_size_from_user(self, bottle_size: str) -> None:
        """Called by the select entity when the user explicitly picks a size."""
        self._bottle_size_user_set = True
        self.bottle_size = bottle_size
        self._notify_listeners()

    def revert_bottle_size(self, previous: str) -> None:
        """Revert an optimistic selection after a failed GATT write."""
        self._bottle_size_user_set = False
        self.bottle_size = previous
        self._notify_listeners()

    async def async_write_bottle_size(self, bottle_size: str) -> bool:
        """Write bottle size via GATT, waiting for the next advertisement first."""
        from .gatt import BOTTLE_SIZE_TO_BYTE, _connect_and_run
        import asyncio

        write_byte = BOTTLE_SIZE_TO_BYTE.get(bottle_size)
        if write_byte is None:
            return False

        async def _write(client):
            from .const import GATT_CHAR_CMD_UUID, GATT_CHAR_DATA_UUID

            async def _size_byte():
                """Read char 0001 and return byte[7] (the bottle-size register)."""
                try:
                    raw = await asyncio.wait_for(
                        client.read_gatt_char(GATT_CHAR_DATA_UUID), timeout=4.0
                    )
                    if raw and len(raw) > 7:
                        return raw[7], raw.hex()
                    return None, (raw.hex() if raw else "empty")
                except Exception as exc:  # noqa: BLE001
                    return None, f"err:{type(exc).__name__}"

            await asyncio.sleep(2.0)

            # WRITE FIRST (most critical op – do it while the link is freshest)
            await asyncio.wait_for(
                client.write_gatt_char(
                    GATT_CHAR_CMD_UUID, bytes([write_byte]), response=True
                ),
                timeout=8.0,
            )
            _LOGGER.warning(
                "%s: SIZE-TEST wrote 0x%02X (%s) to cmd 0003 (acknowledged)",
                self.address, write_byte, bottle_size,
            )
            await asyncio.sleep(1.5)

            # Verify via char 0001 byte[7] – give the read several chances
            after_b = None
            for vtry in range(3):
                after_b, after_hex = await _size_byte()
                _LOGGER.warning(
                    "%s: SIZE-TEST verify%d → byte7=%s  0001=%s",
                    self.address, vtry,
                    ("0x%02X" % after_b) if after_b is not None else "?",
                    after_hex,
                )
                if after_b is not None:
                    break
                await asyncio.sleep(1.5)

            ok = after_b == write_byte
            _LOGGER.warning(
                "%s: SIZE-TEST result → %s (wanted 0x%02X, got %s)",
                self.address, "SUCCESS" if ok else "NO-CHANGE/UNVERIFIED",
                write_byte,
                ("0x%02X" % after_b) if after_b is not None else "?",
            )
            await asyncio.sleep(1.0)
            return ok

        # Retry the whole connect+write up to 5 times to beat error-133 flakiness
        last_exc = None
        for attempt in range(1, 6):
            try:
                _LOGGER.warning(
                    "%s: bottle-size write attempt %d/5", self.address, attempt
                )
                result = await self._gatt_trigger.run_on_next_advertisement(_write)
                if result is True:
                    return True
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                _LOGGER.warning(
                    "%s: write attempt %d failed – %s", self.address, attempt, exc
                )
            await asyncio.sleep(3.0)

        if last_exc:
            _LOGGER.error("%s: GATT write failed after retries – %s", self.address, last_exc)
        return False

    async def async_stop(self) -> None:
        if self._cancel_callback:
            self._cancel_callback()
            self._cancel_callback = None
        if self._cancel_interval:
            self._cancel_interval()
            self._cancel_interval = None
        _LOGGER.debug("Stopped coordinator for %s", self.address)
