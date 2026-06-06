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

        # Read current bottle size from char 0001 byte[7] on the next advertisement
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

        # Single-op read of char 0001 byte[7] = the bottle-size register.
        async def _read(client):
            from .const import (
                GATT_CHAR_DATA_UUID,
                GATT_DATA_BOTTLE_SIZE_OFFSET,
                BYTE_TO_BOTTLE_SIZE,
            )
            import asyncio
            await asyncio.sleep(1.5)
            raw = await asyncio.wait_for(
                client.read_gatt_char(GATT_CHAR_DATA_UUID), timeout=6.0
            )
            if raw and len(raw) > GATT_DATA_BOTTLE_SIZE_OFFSET:
                code = raw[GATT_DATA_BOTTLE_SIZE_OFFSET]
                _LOGGER.info(
                    "%s: bottle-size register byte[7]=0x%02X (%s)  [char0001=%s]",
                    self.address, code,
                    BYTE_TO_BOTTLE_SIZE.get(code, "unknown"), raw.hex(),
                )
                return BYTE_TO_BOTTLE_SIZE.get(code)
            return None

        try:
            size = await self._gatt_trigger.run_on_next_advertisement(_read)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("%s: GATT init read failed – %s", self.address, exc)
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

    def revert_bottle_size(self, previous: str) -> None:
        """Revert an optimistic selection after a failed GATT write."""
        self._bottle_size_user_set = False
        self.bottle_size = previous
        self._notify_listeners()

    async def async_write_bottle_size(self, bottle_size: str) -> bool:
        """Attempt to set the bottle size via GATT and verify via char 0001 byte[7].

        NOTE: the exact command the official app uses to change the bottle size
        is not yet known (it is NOT a plain byte write to char 0002 or 0003 –
        both were verified to leave byte[7] unchanged). This method therefore
        writes the size code to the command characteristic and then *verifies*
        the result by reading byte[7]; it only returns True if the register
        actually changed. Once the real command sequence is captured from an
        HCI log, only the write payload below needs updating.
        """
        from .const import (
            BOTTLE_SIZE_TO_BYTE,
            GATT_CHAR_CMD_UUID,
            GATT_CHAR_DATA_UUID,
            GATT_DATA_BOTTLE_SIZE_OFFSET,
        )
        import asyncio

        write_byte = BOTTLE_SIZE_TO_BYTE.get(bottle_size)
        if write_byte is None:
            return False

        async def _write(client):
            await asyncio.sleep(2.0)
            # Write the size code to the command characteristic (acknowledged).
            await asyncio.wait_for(
                client.write_gatt_char(
                    GATT_CHAR_CMD_UUID, bytes([write_byte]), response=True
                ),
                timeout=8.0,
            )
            await asyncio.sleep(1.5)
            # Verify via the real register (char 0001 byte[7]).
            for _ in range(3):
                try:
                    raw = await asyncio.wait_for(
                        client.read_gatt_char(GATT_CHAR_DATA_UUID), timeout=4.0
                    )
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(1.5)
                    continue
                if raw and len(raw) > GATT_DATA_BOTTLE_SIZE_OFFSET:
                    return raw[GATT_DATA_BOTTLE_SIZE_OFFSET] == write_byte
            return False

        for attempt in range(1, 4):
            try:
                if await self._gatt_trigger.run_on_next_advertisement(_write) is True:
                    _LOGGER.info("%s: bottle size set to %s (verified)", self.address, bottle_size)
                    return True
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("%s: write attempt %d failed – %s", self.address, attempt, exc)
            await asyncio.sleep(3.0)

        _LOGGER.warning(
            "%s: could not set bottle size to %s – the device did not accept the "
            "command (the app's exact set-size sequence is not yet implemented).",
            self.address, bottle_size,
        )
        return False

    async def async_stop(self) -> None:
        if self._cancel_callback:
            self._cancel_callback()
            self._cancel_callback = None
        if self._cancel_interval:
            self._cancel_interval()
            self._cancel_interval = None
        _LOGGER.debug("Stopped coordinator for %s", self.address)
