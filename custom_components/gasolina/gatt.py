"""Active GATT operations for the Gasolina integration (via ESPHome BT proxy).

Uses bleak-retry-connector (HA-recommended) for reliable connection establishment
through ESPHome Bluetooth proxies.

Connection strategy
-------------------
The Gasolina sensor advertises only every ~60 s.  It also requires BLE bonding
before accepting GATT connections from new peers.  The coordinator notifies this
module whenever a fresh advertisement is received so we can connect while the
device is already "awake".

Bonding
-------
On the first connection attempt we call ``client.pair()`` so the ESP32 proxy
establishes a bond with the sensor.  Subsequent connections work without pairing.
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

_OP_TIMEOUT      = 10.0   # seconds for individual GATT read/write
_ADV_FRESHNESS_S = 10.0   # consider advertisement "fresh" if within this many seconds


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

async def _connect_and_run(hass: HomeAssistant, address: str, coro_factory):
    """Connect using bleak-retry-connector, run coro_factory(client), disconnect."""
    from bleak import BleakClient
    from bleak_retry_connector import establish_connection

    device = async_ble_device_from_address(hass, address, connectable=True)
    if device is None:
        _LOGGER.warning("%s: no connectable BLE device found", address)
        return None

    _LOGGER.warning("%s: GATT connecting (establish_connection)…", address)
    client = await establish_connection(
        BleakClient,
        device,
        address,
        max_attempts=3,
    )
    _LOGGER.warning("%s: GATT connected ✓", address)
    try:
        # Try to pair/bond (required on first connection; harmless afterwards)
        try:
            await asyncio.wait_for(client.pair(), timeout=_OP_TIMEOUT)
            _LOGGER.debug("%s: BLE pairing/bonding complete", address)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("%s: pair() skipped or not required – %s", address, exc)

        return await coro_factory(client)
    finally:
        await client.disconnect()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def async_read_bottle_size(hass: HomeAssistant, address: str) -> str:
    """Read the current bottle size from the device via GATT."""
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
                    "%s: unknown byte 0x%02X – defaulting to %s",
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
    """Write the bottle size to the device via GATT."""
    write_byte = BOTTLE_SIZE_TO_BYTE.get(bottle_size)
    if write_byte is None:
        _LOGGER.error("%s: unknown bottle size '%s'", address, bottle_size)
        return False

    try:
        async def _write(client):
            await asyncio.wait_for(
                client.write_gatt_char(
                    GATT_CHAR_RW_UUID, bytes([write_byte]), response=True
                ),
                timeout=_OP_TIMEOUT,
            )
            _LOGGER.info(
                "%s: bottle size set to %s (0x%02X)", address, bottle_size, write_byte
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

    Connecting right after an advertisement (while the device is "awake") is
    far more reliable than connecting at an arbitrary time.
    """

    def __init__(self, hass: HomeAssistant, address: str, timeout: float = 120.0) -> None:
        self._hass = hass
        self._address = address
        self._timeout = timeout
        self._event: asyncio.Event = asyncio.Event()
        self._last_adv_time: float = 0.0

    def on_advertisement(self) -> None:
        """Call this every time a new BLE advertisement is received."""
        self._last_adv_time = time.monotonic()
        self._event.set()

    async def run_on_next_advertisement(self, coro_factory) -> any:
        """Wait for the next advertisement then run the GATT operation."""
        self._event.clear()
        # If a fresh advertisement was received recently, fire immediately
        if time.monotonic() - self._last_adv_time < _ADV_FRESHNESS_S:
            self._event.set()

        try:
            await asyncio.wait_for(self._event.wait(), timeout=self._timeout)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                "%s: no advertisement in %ds – attempting GATT anyway",
                self._address, self._timeout,
            )

        self._event.clear()
        return await _connect_and_run(self._hass, self._address, coro_factory)
