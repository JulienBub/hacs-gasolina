"""Data models for the Gasolina integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import (
    MANUFACTURER_ID,
    MIN_MANUFACTURER_DATA_LENGTH,
    OFFSET_BATTERY,
    OFFSET_EMPTY_ECHO,
    OFFSET_FILL_ECHO,
)


@dataclass
class GasolinaData:
    """Parsed data from a Gasolina BLE advertisement."""

    fill_level: float  # 0.0–100.0 %
    battery: int       # 0–100 %


def parse_advertisement(service_info: BluetoothServiceInfoBleak) -> GasolinaData | None:
    """Return parsed GasolinaData from a BLE advertisement, or None if not a Gasolina device."""
    data = service_info.manufacturer_data.get(MANUFACTURER_ID)
    if data is None or len(data) < MIN_MANUFACTURER_DATA_LENGTH:
        return None

    fill_echo  = data[OFFSET_FILL_ECHO]   # echo units of liquid
    empty_echo = data[OFFSET_EMPTY_ECHO]  # echo units of empty space
    total = fill_echo + empty_echo

    fill_level = round(fill_echo * 100.0 / total, 1) if total > 0 else 0.0

    return GasolinaData(
        fill_level=fill_level,
        battery=data[OFFSET_BATTERY],
    )


def is_gasolina_device(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if this advertisement looks like a Gasolina sensor."""
    return (
        MANUFACTURER_ID in service_info.manufacturer_data
        and (service_info.name or "").startswith("@UTS")
    )
