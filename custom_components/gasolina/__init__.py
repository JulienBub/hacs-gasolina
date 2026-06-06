"""Gasolina BLE gas bottle sensor integration."""
from __future__ import annotations

import logging

from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_BOTTLE_SIZE, DEFAULT_BOTTLE_SIZE, DOMAIN
from .coordinator import GasolinaCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


def _get_bottle_size(entry: ConfigEntry) -> str:
    """Read bottle size from options (preferred) or data (legacy), with fallback."""
    return (
        entry.options.get(CONF_BOTTLE_SIZE)
        or entry.data.get(CONF_BOTTLE_SIZE)
        or DEFAULT_BOTTLE_SIZE
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Gasolina from a config entry."""
    address: str = entry.data["address"]
    bottle_size = _get_bottle_size(entry)

    coordinator = GasolinaCoordinator(hass, address, bottle_size)

    if service_info := async_last_service_info(hass, address):
        from .models import parse_advertisement
        coordinator.data = parse_advertisement(service_info, bottle_size)

    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload the entry whenever options change (e.g. bottle size updated)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: GasolinaCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_stop()
    return unload_ok
