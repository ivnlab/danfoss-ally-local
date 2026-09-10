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
from homeassistant.util import dt as dt_util

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

    def _build_entities(coordinator: DanfossLocalCoordinator) -> list[SensorEntity]:
        # Fixed entity set per thermostat - see number.py for why creation is
        # not gated on the key already being present in the device data.
        entities: list[SensorEntity] = [
            DanfossLocalSensor(coordinator, device_id, description)
            for device_id in (coordinator.data or {})
            for description in SENSORS
        ]
        # One schedule sensor per thermostat, fed by the schedule manager
        # rather than by polled device data.
        entities.extend(
            DanfossLocalScheduleSensor(coordinator, device_id)
            for device_id in (coordinator.data or {})
        )
        return entities

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


SCHEDULE_STATE_OFF = "off"
SCHEDULE_STATES = ["at_home", "leaving_home", "pause", "holiday", SCHEDULE_STATE_OFF]


class DanfossLocalScheduleSensor(DanfossLocalEntity, SensorEntity):
    """What the local weekly schedule wants right now, plus the program itself.

    State is the scheduled mode at this minute ("off" when no schedule or
    disabled). The full program, holiday overlay and next transition are
    exposed as attributes for the dashboard card to render and edit through
    the danfoss_local.* schedule services.
    """

    _attr_translation_key = "schedule"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = SCHEDULE_STATES
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: DanfossLocalCoordinator, device_id: str) -> None:
        """Initialize the schedule sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"schedule_{device_id}_danfoss_local"

    @property
    def _manager(self):
        return getattr(self.coordinator, "schedule_manager", None)

    async def async_added_to_hass(self) -> None:
        """Also refresh whenever the schedule manager changes or ticks."""
        await super().async_added_to_hass()
        manager = self._manager
        if manager is not None:
            self.async_on_remove(manager.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> str:
        """Return the scheduled mode for this minute, or off."""
        manager = self._manager
        if manager is None:
            return SCHEDULE_STATE_OFF
        sched = manager.engine.get_schedule(self._device_id)
        if sched is None or not sched.enabled:
            return SCHEDULE_STATE_OFF
        return sched.desired_mode(dt_util.now()) or SCHEDULE_STATE_OFF

    @property
    def extra_state_attributes(self) -> dict:
        """Expose program, holiday, enabled flag and next transition."""
        manager = self._manager
        if manager is None:
            return {}
        sched = manager.engine.get_schedule(self._device_id)
        if sched is None:
            return {"enabled": False, "program": None, "holiday": None, "next_change_at": None, "next_mode": None}
        nxt = manager.engine.next_change(self._device_id, dt_util.now())
        data = sched.to_dict()
        return {
            "enabled": data["enabled"],
            "program": data["program"],
            "holiday": data["holiday"],
            "next_change_at": nxt[0].isoformat() if nxt else None,
            "next_mode": nxt[1] if nxt else None,
        }
