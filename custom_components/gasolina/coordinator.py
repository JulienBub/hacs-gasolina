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

        # Bottle size is encoded in every advertisement (mfr_payload[10]).
        # Update our local value whenever the device tells us its current setting,
        # unless the user has explicitly picked a size via the UI (optimistic update).
        if new_data.bottle_size is not None and not self._bottle_size_user_set:
            if new_data.bottle_size != self.bottle_size:
                _LOGGER.info(
                    "%s: bottle size from advertisement = %s",
                    self.address, new_data.bottle_size,
                )
                self.bottle_size = new_data.bottle_size
                self._notify_listeners()
                return  # listeners already notified

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
        """Read bottle size on the next advertisement via GATT (fallback/fast-path).

        Since bottle size is now parsed from every passive advertisement
        (mfr_payload[10]), this GATT read is only a fast-path for the first
        boot before the first advertisement arrives.  If the advertisement
        already supplied a value, this is a no-op.
        """
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

        Write strategy (derived from HCI log analysis 2026-06-06 21:21):
        The official Gasolina Android app uses a Qualcomm vendor-specific HCI
        command (opcode 0xFD57) to write the bottle size.  Its 18-byte parameter
        has the form [0x01, 0x00, size_code, 0x40, 0x00, 0x11, 0x11, 0x01, 0x80,
        0x00, …].  The first two bytes (0x01 0x00) appear to be the target
        attribute handle (0x0001 little-endian), followed by the write value.
        At the standard ATT level this translates to a Write Request to attribute
        handle 0x0001 with a 16-byte payload starting with the size code.

        We try in order:
          A) 16-byte write to char 0001 (attr handle 1, the first/data char)
             – matches the vendor command payload exactly.
          B) 1-byte write to char 0001 (minimal variant).
          C) 1-byte write-without-response to char 0002.
          D) 1-byte write to char 0003 (previous fallback).

        Each attempt is followed by a char-0001 read to verify byte[7].
        After a successful write the sensor's next advertisement will also
        show the new code in mfr_payload[10].
        """
        from .const import (
            BOTTLE_SIZE_TO_BYTE,
            GATT_CHAR_CMD_UUID,
            GATT_CHAR_DATA_UUID,
            GATT_CHAR_RW_UUID,
            GATT_DATA_BOTTLE_SIZE_OFFSET,
        )
        import asyncio

        write_byte = BOTTLE_SIZE_TO_BYTE.get(bottle_size)
        if write_byte is None:
            return False

        # Payload A: 16-byte pattern matching the vendor HCI command parameter
        # [size_code, 0x40, 0x00, 0x11, 0x11, 0x01, 0x80, 0x00 × 9]
        payload_16 = bytes([write_byte, 0x40, 0x00, 0x11, 0x11, 0x01, 0x80,
                            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        payload_1  = bytes([write_byte])
        payload_4  = bytes([0x01, 0x00, 0x03, write_byte])

        # current_byte = byte code of currently shown bottle size (for 3-byte sequence)
        current_byte = BOTTLE_SIZE_TO_BYTE.get(self.bottle_size, write_byte)

        # Payloads from HCI log analysis (vendor cmd 0xFD57 parameter structure):
        #   22-byte: [conn 01 00] [size_code] [40 00 11 11 01 80 00×9]
        #   3-byte:  [01 01 old_code] then [01 01 new_code]
        #   2-byte:  [00 01]  (commit)
        # Under the hood the vendor cmd likely maps to ATT Write on char 0002 or 0003.
        # We try both chars and both payload sizes.

        async def _write(client):
            await asyncio.sleep(2.0)

            # Read current byte[7] for reference before any write
            try:
                pre = await asyncio.wait_for(
                    client.read_gatt_char(GATT_CHAR_DATA_UUID), timeout=4.0
                )
                _LOGGER.info(
                    "%s: pre-write char0001=%s  byte[7]=0x%02X",
                    self.address, pre.hex(), pre[GATT_DATA_BOTTLE_SIZE_OFFSET] if len(pre) > GATT_DATA_BOTTLE_SIZE_OFFSET else -1,
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.info("%s: pre-write read failed – %s", self.address, exc)

            # ── Sequence 1: 16-byte to char 0002 (write-without-response) ──
            try:
                await asyncio.wait_for(
                    client.write_gatt_char(GATT_CHAR_RW_UUID, payload_16, response=False),
                    timeout=6.0,
                )
                _LOGGER.info("%s: 1) 16-byte WO-RSP → char 0002 OK", self.address)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.info("%s: 1) 16-byte WO-RSP → char 0002 FAILED: %s", self.address, exc)

            await asyncio.sleep(0.3)

            # ── Sequence 2: [01 01 old] to char 0003 ──────────────────────
            try:
                await asyncio.wait_for(
                    client.write_gatt_char(
                        GATT_CHAR_CMD_UUID, bytes([0x01, 0x01, current_byte]), response=True
                    ),
                    timeout=6.0,
                )
                _LOGGER.info("%s: 2) [01 01 0x%02X] → char 0003 OK (old size)", self.address, current_byte)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.info("%s: 2) [01 01 0x%02X] → char 0003 FAILED: %s", self.address, current_byte, exc)

            await asyncio.sleep(0.3)

            # ── Sequence 3: [01 01 new] to char 0003 ──────────────────────
            try:
                await asyncio.wait_for(
                    client.write_gatt_char(
                        GATT_CHAR_CMD_UUID, bytes([0x01, 0x01, write_byte]), response=True
                    ),
                    timeout=6.0,
                )
                _LOGGER.info("%s: 3) [01 01 0x%02X] → char 0003 OK (new size)", self.address, write_byte)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.info("%s: 3) [01 01 0x%02X] → char 0003 FAILED: %s", self.address, write_byte, exc)

            await asyncio.sleep(0.3)

            # ── Sequence 4: [00 01] commit to char 0002 ───────────────────
            try:
                await asyncio.wait_for(
                    client.write_gatt_char(
                        GATT_CHAR_RW_UUID, bytes([0x00, 0x01]), response=False
                    ),
                    timeout=6.0,
                )
                _LOGGER.info("%s: 4) [00 01] commit WO-RSP → char 0002 OK", self.address)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.info("%s: 4) [00 01] commit WO-RSP → char 0002 FAILED: %s", self.address, exc)

            await asyncio.sleep(1.5)

            # Verify via char 0001 byte[7]
            for _ in range(3):
                try:
                    raw = await asyncio.wait_for(
                        client.read_gatt_char(GATT_CHAR_DATA_UUID), timeout=4.0
                    )
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(1.5)
                    continue
                if raw and len(raw) > GATT_DATA_BOTTLE_SIZE_OFFSET:
                    got = raw[GATT_DATA_BOTTLE_SIZE_OFFSET]
                    verified = (got == write_byte)
                    _LOGGER.info(
                        "%s: post-write char0001 byte[7]=0x%02X (target=0x%02X) → %s",
                        self.address, got, write_byte, "OK" if verified else "NOT CHANGED",
                    )
                    return verified
            return False

        for attempt in range(1, 4):
            try:
                if await self._gatt_trigger.run_on_next_advertisement(_write) is True:
                    _LOGGER.info("%s: bottle size set to %s (verified)", self.address, bottle_size)
                    # Reset flag so future BLE advertisements keep the value in sync.
                    self._bottle_size_user_set = False
                    return True
            except Exception as exc:  # noqa: BLE001
                _LOGGER.info("%s: write attempt %d – GATT connection error: %s", self.address, attempt, exc)
            await asyncio.sleep(3.0)

        _LOGGER.warning(
            "%s: could not set bottle size to %s. The official app uses a "
            "Qualcomm vendor HCI command (0xFD57) that bypasses standard ATT. "
            "Tried A(char0001/16B) B(char0001/1B) C(char0002/4B) D(char0003/1B).",
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
