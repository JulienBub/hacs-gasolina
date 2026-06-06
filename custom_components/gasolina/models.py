"""Data models for the Gasolina integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from .const import (
    BOTTLE_ECHO_MAX,
    DEFAULT_BOTTLE_SIZE,
    MANUFACTURER_ID,
    MIN_MANUFACTURER_DATA_LENGTH,
    OFFSET_BATTERY,
    OFFSET_FILL_ECHO,
)


@dataclass
class GasolinaData:
    """Parsed data from a Gasolina BLE advertisement."""

    fill_level: float  # 0.0–100.0 %
    battery: int       # 0–100 %


def parse_advertisement(
    service_info: BluetoothServiceInfoBleak,
    bottle_size: str = DEFAULT_BOTTLE_SIZE,
) -> GasolinaData | None:
    """Return parsed GasolinaData from a BLE advertisement, or None if not valid."""
    data = service_info.manufacturer_data.get(MANUFACTURER_ID)
    if data is None or len(data) < MIN_MANUFACTURER_DATA_LENGTH:
        return None

    echo_max = BOTTLE_ECHO_MAX.get(bottle_size, BOTTLE_ECHO_MAX[DEFAULT_BOTTLE_SIZE])
    fill_echo = data[OFFSET_FILL_ECHO]
    fill_level = round(min(fill_echo * 100.0 / echo_max, 100.0), 1)

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
