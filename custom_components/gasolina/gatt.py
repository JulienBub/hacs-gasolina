"""Active GATT operations for the Gasolina integration (via ESPHome BT proxy)."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.bluetooth import async_ble_device_from_address
from homeassistant.core import HomeAssistant

from .const import (
    BOTTLE_SIZE_TO_BYTE,
    BYTE_TO_BOTTLE_SIZE,
    DEFAULT_BOTTLE_SIZE,
    GATT_CHAR_RW_UUID,
)

_LOGGER = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10.0   # seconds to establish BLE connection
_OP_TIMEOUT      = 5.0    # seconds for individual GATT read/write


async def async_read_bottle_size(hass: HomeAssistant, address: str) -> str:
    """Connect via GATT and read the current bottle size from the device.

    Returns the bottle size string (e.g. '11kg') or DEFAULT_BOTTLE_SIZE on failure.
    The connection is closed immediately after reading.
    """
    try:
        from bleak import BleakClient  # imported lazily – not available on all platforms

        device = async_ble_device_from_address(hass, address, connectable=True)
        if device is None:
            _LOGGER.warning(
                "%s: no connectable BLE device found – is the ESP32 proxy active?",
                address,
            )
            return DEFAULT_BOTTLE_SIZE

        _LOGGER.debug("%s: connecting via GATT to read bottle size", address)
        async with BleakClient(device, timeout=_CONNECT_TIMEOUT) as client:
            raw = await asyncio.wait_for(
                client.read_gatt_char(GATT_CHAR_RW_UUID), timeout=_OP_TIMEOUT
            )
            _LOGGER.debug("%s: GATT char read → %s", address, raw.hex())

            if raw:
                size = BYTE_TO_BOTTLE_SIZE.get(raw[0])
                if size:
                    _LOGGER.info("%s: bottle size from device = %s", address, size)
                    return size
                _LOGGER.warning(
                    "%s: unknown bottle-size byte 0x%02X – defaulting to %s",
                    address, raw[0], DEFAULT_BOTTLE_SIZE,
                )

    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("%s: GATT read failed – %s", address, exc)

    return DEFAULT_BOTTLE_SIZE


async def async_write_bottle_size(
    hass: HomeAssistant, address: str, bottle_size: str
) -> bool:
    """Connect via GATT and write the bottle size to the device.

    Returns True on success, False on failure.
    The connection is closed immediately after writing.
    """
    write_byte = BOTTLE_SIZE_TO_BYTE.get(bottle_size)
    if write_byte is None:
        _LOGGER.error("%s: unknown bottle size '%s'", address, bottle_size)
        return False

    try:
        from bleak import BleakClient

        device = async_ble_device_from_address(hass, address, connectable=True)
        if device is None:
            _LOGGER.warning(
                "%s: no connectable BLE device found for GATT write", address
            )
            return False

        _LOGGER.debug(
            "%s: connecting via GATT to write bottle size %s (0x%02X)",
            address, bottle_size, write_byte,
        )
        async with BleakClient(device, timeout=_CONNECT_TIMEOUT) as client:
            await asyncio.wait_for(
                client.write_gatt_char(
                    GATT_CHAR_RW_UUID,
                    bytes([write_byte]),
                    response=False,
                ),
                timeout=_OP_TIMEOUT,
            )
            _LOGGER.info(
                "%s: bottle size successfully set to %s via GATT", address, bottle_size
            )
            return True

    except Exception as exc:  # noqa: BLE001
        _LOGGER.error("%s: GATT write failed – %s", address, exc)
        return False
