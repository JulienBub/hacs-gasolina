"""Sensor entities for the Gasolina integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GasolinaCoordinator
from .models import GasolinaData


@dataclass(frozen=True)
class GasolinaSensorEntityDescription(SensorEntityDescription):
    """Describes a Gasolina sensor entity."""
    value_fn: Callable[[GasolinaData], int | float | str | None] = lambda _: None


SENSOR_DESCRIPTIONS: tuple[GasolinaSensorEntityDescription, ...] = (
    GasolinaSensorEntityDescription(
        key="fill_level",
        name="Füllstand",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.fill_level,
    ),
    GasolinaSensorEntityDescription(
        key="battery",
        name="Batterie",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.battery,
    ),
    GasolinaSensorEntityDescription(
        key="temperature",
        name="Temperatur",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.temperature,
    ),
    GasolinaSensorEntityDescription(
        key="bottle_size",
        name="Flaschengröße",
        icon="mdi:gas-cylinder",
        value_fn=lambda d: d.bottle_size,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gasolina sensor entities."""
    coordinator: GasolinaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        GasolinaSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    )


class GasolinaSensor(SensorEntity):
    """A single Gasolina sensor entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: GasolinaCoordinator,
        description: GasolinaSensorEntityDescription,
    ) -> None:
        self.entity_description: GasolinaSensorEntityDescription = description
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=f"Gasolina {coordinator.address[-5:]}",
            manufacturer="Gasolina",
            model="Gas Bottle Sensor",
        )

    @property
    def native_value(self) -> int | float | str | None:
        if self._coordinator.data is None:
            return None
        return self.entity_description.value_fn(self._coordinator.data)

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
