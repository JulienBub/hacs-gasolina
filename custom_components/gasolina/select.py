"""Select entity for Gasolina bottle size (writes via GATT)."""
from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BOTTLE_SIZE_TO_BYTE, DOMAIN
from .coordinator import GasolinaCoordinator
from .gatt import async_write_bottle_size

_LOGGER = logging.getLogger(__name__)

BOTTLE_SIZE_OPTIONS = list(BOTTLE_SIZE_TO_BYTE.keys())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: GasolinaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GasolinaBottleSizeSelect(coordinator)])


class GasolinaBottleSizeSelect(SelectEntity):
    """Select entity that reads & writes the gas bottle size via GATT."""

    _attr_has_entity_name = True
    _attr_name = "Flaschengröße"
    _attr_icon = "mdi:gas-cylinder"
    _attr_should_poll = False

    def __init__(self, coordinator: GasolinaCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_bottle_size"
        self._attr_options = BOTTLE_SIZE_OPTIONS
        self._attr_current_option = coordinator.bottle_size
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=f"Gasolina {coordinator.address[-5:]}",
            manufacturer="Thincke Inc",
            model="Gas Bottle Sensor (UTS_MIN)",
        )

    async def async_select_option(self, option: str) -> None:
        """Write the new bottle size to the device via GATT."""
        _LOGGER.info("Setting bottle size to %s for %s", option, self._coordinator.address)

        # Mark as user-set BEFORE the write so the async init task cannot override it
        self._coordinator.set_bottle_size_from_user(option)
        self._attr_current_option = option
        self.async_write_ha_state()

        # Write to device (fire-and-forget result; UI is already updated optimistically)
        success = await async_write_bottle_size(
            self.hass, self._coordinator.address, option
        )
        if not success:
            _LOGGER.warning(
                "%s: GATT write failed – check ESP32 proxy. "
                "Selection shown but device may not have updated.",
                self._coordinator.address,
            )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        self._attr_current_option = self._coordinator.bottle_size
        self.async_write_ha_state()
