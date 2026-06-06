"""Active GATT operations for the Gasolina integration (via ESPHome BT proxy).

Connection strategy
-------------------
The Gasolina sensor advertises only every ~60 s to save battery.  It also
requires BLE bonding before accepting GATT connections from new peers
(same as the official app: SYNC button → pair once → works forever after).

To avoid "Timeout waiting for connect response":
  - We wait for a *fresh* advertisement (device just woke up) before
    initiating the GATT connection.  The coordinator calls
    ``notify_advertisement_received()`` every time a new BLE packet arrives;
    that event is used as the trigger.

Bonding
-------
On the first connection attempt we call ``client.pair()`` so the ESP32 proxy
establishes a bond with the sensor.  Subsequent connections work without
pairing (the bond is stored on the proxy side by ESPHome).
"""
from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant

from .const import (
    BOTTLE_SIZE_TO_BYTE,
    BYTE_TO_BOTTLE_SIZE,
    DEFAULT_BOTTLE_SIZE,
    GATT_CHAR_RW_UUID,
)

_LOGGER = logging.getLogger(__name__)

_CONNECT_TIMEOUT  = 30.0   # seconds – generous, device may need time to respond
_OP_TIMEOUT       = 10.0   # seconds for individual GATT read/write
_ADV_FRESHNESS_S  = 10.0   # consider advertisement "fresh" if received within this many seconds


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

async def _connect_and_run(hass: HomeAssistant, address: str, coro_factory):
    """Connect to the device (with optional pairing), run coro_factory(client), disconnect."""
    from bleak import BleakClient

    device = async_ble_device_from_address(hass, address, connectable=True)
    if device is None:
        _LOGGER.warning("%s: no connectable BLE device found", address)
        return None

    async with BleakClient(device, timeout=_CONNECT_TIMEOUT) as client:
        # Try to pair on first connection (device may require bonding).
        # Subsequent connections silently succeed because the bond is cached.
        try:
            await asyncio.wait_for(client.pair(), timeout=_OP_TIMEOUT)
            _LOGGER.debug("%s: BLE pairing/bonding complete", address)
        except Exception as exc:  # noqa: BLE001
            # Many devices don't require explicit pairing; non-fatal.
            _LOGGER.debug("%s: pair() skipped or not required – %s", address, exc)

        return await coro_factory(client)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def async_read_bottle_size(hass: HomeAssistant, address: str) -> str:
    """Read the current bottle size from the device via GATT.

    Returns the bottle-size string (e.g. '11kg') or DEFAULT_BOTTLE_SIZE on failure.
    """
    try:
        async def _read(client):
            raw = await asyncio.wait_for(
                client.read_gatt_char(GATT_CHAR_RW_UUID), timeout=_OP_TIMEOUT
            )
            _LOGGER.debug("%s: GATT char read → %s", address, raw.hex() if raw else "empty")
            if raw:
                size = BYTE_TO_BOTTLE_SIZE.get(raw[0])
                if size:
                    _LOGGER.info("%s: bottle size from device = %s", address, size)
                    return size
                _LOGGER.warning(
                    "%s: unknown bottle-size byte 0x%02X – defaulting to %s",
                    address, raw[0], DEFAULT_BOTTLE_SIZE,
                )
            return DEFAULT_BOTTLE_SIZE

        result = await _connect_and_run(hass, address, _read)
        return result if result is not None else DEFAULT_BOTTLE_SIZE

    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("%s: GATT read failed – %s", address, exc)
        return DEFAULT_BOTTLE_SIZE


async def async_write_bottle_size(
    hass: HomeAssistant, address: str, bottle_size: str
) -> bool:
    """Write the bottle size to the device via GATT.

    Returns True on success, False on failure.
    """
    write_byte = BOTTLE_SIZE_TO_BYTE.get(bottle_size)
    if write_byte is None:
        _LOGGER.error("%s: unknown bottle size '%s'", address, bottle_size)
        return False

    try:
        async def _write(client):
            await asyncio.wait_for(
                client.write_gatt_char(GATT_CHAR_RW_UUID, bytes([write_byte]), response=False),
                timeout=_OP_TIMEOUT,
            )
            _LOGGER.info(
                "%s: bottle size set to %s (0x%02X) via GATT",
                address, bottle_size, write_byte,
            )
            return True

        result = await _connect_and_run(hass, address, _write)
        return result is True

    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("%s: GATT write failed – %s", address, exc)
        return False


# ---------------------------------------------------------------------------
# Advertisement-triggered connection helper
# ---------------------------------------------------------------------------

class GattOnAdvertisementTrigger:
    """Runs a GATT coroutine the next time a fresh advertisement is received.

    The Gasolina sensor only advertises every ~60 s.  Connecting immediately
    after an advertisement (while the device is "awake") is far more reliable
    than connecting at an arbitrary time.

    Usage::

        trigger = GattOnAdvertisementTrigger(hass, address, timeout=90)
        trigger.arm(coro_factory)          # schedule the GATT op
        # … coordinator calls trigger.on_advertisement() on every BLE update …
        result = await trigger.wait()      # wait for op to complete
    """

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        timeout: float = 90.0,
    ) -> None:
        self._hass = hass
        self._address = address
        self._timeout = timeout
        self._coro_factory = None
        self._event: asyncio.Event = asyncio.Event()
        self._result = None
        self._last_adv_time: float = 0.0

    def on_advertisement(self) -> None:
        """Call this every time a new BLE advertisement is received."""
        self._last_adv_time = time.monotonic()
        if self._coro_factory is not None:
            self._event.set()

    def arm(self, coro_factory) -> None:
        """Schedule a GATT operation to run on the next advertisement."""
        self._coro_factory = coro_factory
        self._event.clear()
        # If a fresh advertisement was received recently, fire immediately
        if time.monotonic() - self._last_adv_time < _ADV_FRESHNESS_S:
            self._event.set()

    async def run_on_next_advertisement(self, coro_factory) -> any:
        """Wait for the next advertisement then run the GATT operation."""
        self.arm(coro_factory)
        try:
            await asyncio.wait_for(self._event.wait(), timeout=self._timeout)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "%s: no advertisement received within %ds – attempting GATT anyway",
                self._address, self._timeout,
            )
        self._coro_factory = None
        self._event.clear()
        return await _connect_and_run(self._hass, self._address, coro_factory)
