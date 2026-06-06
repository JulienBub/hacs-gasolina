"""Data models for the Gasolina integration."""
from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import (
    BYTE_TO_BOTTLE_SIZE,
    MANUFACTURER_ID,
    MIN_MANUFACTURER_DATA_LENGTH,
    OFFSET_BATTERY,
    OFFSET_BOTTLE_SIZE,
    OFFSET_FILL_HIGH,
    OFFSET_FILL_LOW,
)


@dataclass
class GasolinaData:
    """Parsed data from a Gasolina BLE advertisement."""

    fill_level: float        # 0.0–100.0 %
    battery: int             # 0–100 %
    bottle_size: str | None = field(default=None)   # e.g. "11kg", or None if unknown code


def parse_advertisement(service_info: BluetoothServiceInfoBleak) -> GasolinaData | None:
    """Return parsed GasolinaData from a BLE advertisement, or None if not valid."""
    data = service_info.manufacturer_data.get(MANUFACTURER_ID)
    if data is None or len(data) < MIN_MANUFACTURER_DATA_LENGTH:
        return None

    fill_permille = (data[OFFSET_FILL_HIGH] << 8) | data[OFFSET_FILL_LOW]
    fill_level = round(min(fill_permille / 10.0, 100.0), 1)

    # Bottle size is encoded in the advertisement at offset 10 (after company ID).
    # Confirmed via HCI log analysis: mfr_payload[10] == GATT char-0001 byte[7].
    bottle_size: str | None = None
    if len(data) > OFFSET_BOTTLE_SIZE:
        bottle_size = BYTE_TO_BOTTLE_SIZE.get(data[OFFSET_BOTTLE_SIZE])

    return GasolinaData(
        fill_level=fill_level,
        battery=data[OFFSET_BATTERY],
        bottle_size=bottle_size,
    )


def is_gasolina_device(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if this advertisement looks like a Gasolina sensor.

    Primary signal: Company ID 0x0211 (Telink) in manufacturer data.
    The local name (@UTS…) is a secondary hint but not always present in the
    HA Bluetooth cache, so we do NOT require it here.
    """
    return MANUFACTURER_ID in service_info.manufacturer_data
