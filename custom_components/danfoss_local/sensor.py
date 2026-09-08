"""Sensor support for Danfoss Icon2 (Local)."""

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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .coordinator import DanfossLocalCoordinator
from .entity import DanfossLocalEntity, async_setup_dynamic_platform_entities


@dataclass(frozen=True, kw_only=True)
class DanfossLocalSensorDescription(SensorEntityDescription):
    """Describe a Danfoss Icon2 (Local) sensor entity."""

    value_fn: Callable[[dict[str, object]], object]
    unique_prefix: str


SETPOINT_CHANGE_SOURCE_OPTIONS = ["Manual", "Externally", "schedule"]


SENSORS: tuple[DanfossLocalSensorDescription, ...] = (
    DanfossLocalSensorDescription(
        key="temperature",
        translation_key="air_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device["temperature"],
        unique_prefix="air temperature",
    ),
    DanfossLocalSensorDescription(
        key="floor_temperature",
        translation_key="floor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device["floor_temperature"],
        unique_prefix="floor temperature",
    ),
    DanfossLocalSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device["humidity"],
        unique_prefix="humidity",
    ),
    DanfossLocalSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device["battery"],
        unique_prefix="battery",
    ),
    DanfossLocalSensorDescription(
        key="setpoint_change_source",
        translation_key="setpoint_change_source",
        device_class=SensorDeviceClass.ENUM,
        options=SETPOINT_CHANGE_SOURCE_OPTIONS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device["setpointchangesource"],
        unique_prefix="setpoint change source",
    ),
    DanfossLocalSensorDescription(
        key="adaptation_run_status",
        translation_key="adaptation_run_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device["adaptation_runstatus"],
        unique_prefix="adaptation run status",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Danfoss Icon2 (Local) sensor entities."""
    coordinator: DanfossLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _build_entities(coordinator: DanfossLocalCoordinator) -> list[DanfossLocalSensor]:
        # Fixed entity set per thermostat - see number.py for why creation is
        # not gated on the key already being present in the device data.
        return [
            DanfossLocalSensor(coordinator, device_id, description)
            for device_id in (coordinator.data or {})
            for description in SENSORS
        ]

    async_setup_dynamic_platform_entities(coordinator, async_add_entities, _build_entities)


class DanfossLocalSensor(DanfossLocalEntity, SensorEntity):
    """Representation of a Danfoss Icon2 (Local) sensor."""

    entity_description: DanfossLocalSensorDescription

    def __init__(
        self,
        coordinator: DanfossLocalCoordinator,
        device_id: str,
        description: DanfossLocalSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{description.unique_prefix}_{device_id}_danfoss_local"

    @property
    def native_value(self) -> object:
        """Return the current sensor value."""
        try:
            return self.entity_description.value_fn(self.device)
        except (KeyError, TypeError):
            return None
