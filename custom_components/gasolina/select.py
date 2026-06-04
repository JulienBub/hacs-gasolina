"""Select entity for Gasolina bottle size configuration."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BOTTLE_SIZE_OPTIONS,
    BOTTLE_SIZE_TO_WRITE_BYTE,
    DOMAIN,
    GATT_CHAR_WRITE_NR,
)
from .coordinator import GasolinaCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gasolina select entity."""
    coordinator: GasolinaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GasolinaBottleSizeSelect(coordinator)])


class GasolinaBottleSizeSelect(SelectEntity):
    """Select entity to read and set the configured bottle size.

    Reading works fully via passive BLE advertisement (data[10]).
    Writing is implemented based on partial reverse-engineering:
      - Characteristic 0002 (Write Without Response) accepts a single byte.
      - BOTTLE_SIZE_TO_WRITE_BYTE maps each label to its confirmed write byte.
      - Protocol was confirmed with Android HCI snoop log.
    """

    _attr_has_entity_name = True
    _attr_name = "Flaschengröße"
    _attr_options = BOTTLE_SIZE_OPTIONS
    _attr_should_poll = False

    def __init__(self, coordinator: GasolinaCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_bottle_size"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=f"Gasolina {coordinator.address[-5:]}",
            manufacturer="Gasolina",
            model="Gas Bottle Sensor",
        )

    @property
    def current_option(self) -> str | None:
        if self._coordinator.data is None:
            return None
        size = self._coordinator.data.bottle_size
        return size if size in BOTTLE_SIZE_OPTIONS else None

    @property
    def available(self) -> bool:
        return self._coordinator.data is not None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Write new bottle size to sensor via GATT (characteristic 0002)."""
        write_byte = BOTTLE_SIZE_TO_WRITE_BYTE.get(option)
        if write_byte is None:
            _LOGGER.error(
                "Cannot set bottle size '%s': write byte not yet confirmed. "
                "Please open a GitHub issue with your Android HCI snoop log.",
                option,
            )
            return

        try:
            from bleak import BleakClient
            async with BleakClient(self._coordinator.address) as client:
                await client.write_gatt_char(
                    GATT_CHAR_WRITE_NR,
                    bytes([write_byte]),
                    response=False,
                )
                _LOGGER.debug(
                    "Wrote bottle size %s (byte %#04x) to %s via char 0002",
                    option,
                    write_byte,
                    self._coordinator.address,
                )
        except Exception as exc:
            _LOGGER.error(
                "Failed to write bottle size to %s: %s",
                self._coordinator.address,
                exc,
            )
