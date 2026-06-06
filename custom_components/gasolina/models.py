"""Data models for the Gasolina integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import (
    MANUFACTURER_ID,
    MIN_MANUFACTURER_DATA_LENGTH,
    OFFSET_BATTERY,
    OFFSET_FILL_HIGH,
    OFFSET_FILL_LOW,
    OFFSET_LIQUID_DEPTH,
)


@dataclass
class GasolinaData:
    """Parsed data from a Gasolina BLE advertisement."""

    fill_level: float   # 0.0–100.0 % (derived from 16-bit per-mille value)
    battery: int        # 0–100 %
    liquid_depth: float # liquid height in cm (e.g. 12.0 cm)


def parse_advertisement(service_info: BluetoothServiceInfoBleak) -> GasolinaData | None:
    """Return parsed GasolinaData from a BLE advertisement, or None if not a Gasolina device."""
    data = service_info.manufacturer_data.get(MANUFACTURER_ID)
    if data is None or len(data) < MIN_MANUFACTURER_DATA_LENGTH:
        return None

    fill_permille = (data[OFFSET_FILL_HIGH] << 8) | data[OFFSET_FILL_LOW]
    fill_level = round(fill_permille / 10.0, 1)

    return GasolinaData(
        fill_level=fill_level,
        battery=data[OFFSET_BATTERY],
        liquid_depth=round(data[OFFSET_LIQUID_DEPTH] / 10.0, 1),
    )


def is_gasolina_device(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if this advertisement looks like a Gasolina sensor."""
    return (
        MANUFACTURER_ID in service_info.manufacturer_data
        and (service_info.name or "").startswith("@UTS")
    )
