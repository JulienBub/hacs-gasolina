"""Gasolina BLE gas bottle sensor integration."""
from __future__ import annotations

import logging

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_BOTTLE_SIZE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCAN_INTERVAL_OPTIONS,
)
from .coordinator import GasolinaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Gasolina from a config entry."""
    address: str = entry.data["address"]
    # bottle_size can come from setup data (new) or be absent (legacy entries)
    _ = entry.data.get("bottle_size", DEFAULT_BOTTLE_SIZE)  # stored for reference

    # Scan interval: stored as label string in options, convert to seconds
    interval_label = entry.options.get(CONF_SCAN_INTERVAL, None)
    scan_interval: int = (
        SCAN_INTERVAL_OPTIONS.get(interval_label, DEFAULT_SCAN_INTERVAL)
        if isinstance(interval_label, str)
        else DEFAULT_SCAN_INTERVAL
    )

    coordinator = GasolinaCoordinator(hass, address, scan_interval)

    if service_info := async_last_service_info(hass, address):
        from .models import parse_advertisement
        coordinator.data = parse_advertisement(service_info)

    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when options change (e.g. new scan interval)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: GasolinaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unload_ok
