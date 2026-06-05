"""Data models for the Gasolina integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import (
    MANUFACTURER_ID,
    MIN_MANUFACTURER_DATA_LENGTH,
    OFFSET_BATTERY,
    OFFSET_FILL_LEVEL,
)


@dataclass
class GasolinaData:
    """Parsed data from a Gasolina BLE advertisement."""

    fill_level: int  # 0–100 %
    battery: int     # 0–100 %


def parse_advertisement(service_info: BluetoothServiceInfoBleak) -> GasolinaData | None:
    """Return parsed GasolinaData from a BLE advertisement, or None if not a Gasolina device."""
    data = service_info.manufacturer_data.get(MANUFACTURER_ID)
    if data is None or len(data) < MIN_MANUFACTURER_DATA_LENGTH:
        return None

    return GasolinaData(
        fill_level=data[OFFSET_FILL_LEVEL],
        battery=data[OFFSET_BATTERY],
    )


def is_gasolina_device(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if this advertisement looks like a Gasolina sensor."""
    return (
        MANUFACTURER_ID in service_info.manufacturer_data
        and (service_info.name or "").startswith("@UTS")
    )
