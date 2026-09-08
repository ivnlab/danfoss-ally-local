"""Binary sensor support for Danfoss Icon2 (Local)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .coordinator import DanfossLocalCoordinator
from .entity import DanfossLocalEntity, async_setup_dynamic_platform_entities


@dataclass(frozen=True, kw_only=True)
class DanfossLocalBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Danfoss Icon2 (Local) binary sensor."""

    value_fn: Callable[[dict[str, object]], bool]
    unique_prefix: str


BINARY_SENSORS: tuple[DanfossLocalBinarySensorDescription, ...] = (
    DanfossLocalBinarySensorDescription(
        key="thermal_actuator",
        translation_key="thermal_actuator",
        device_class=BinarySensorDeviceClass.OPENING,
        icon="mdi:pipe-valve",
        value_fn=lambda device: bool(device["output_status"]),
        unique_prefix="thermal actuator",
    ),
    DanfossLocalBinarySensorDescription(
        key="fault",
        translation_key="fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: bool(device["fault"]),
        unique_prefix="fault",
    ),
    DanfossLocalBinarySensorDescription(
        key="setpoint_change_source",
        translation_key="setpoint_change_source",
        value_fn=lambda device: (
            device.get("setpointchangesource", device.get("SetpointChangeSource"))
            == "Manual"
        ),
        unique_prefix="setpoint change source",
    ),
    DanfossLocalBinarySensorDescription(
        key="child_lock_status",
        translation_key="child_lock_status",
        device_class=BinarySensorDeviceClass.LOCK,
        value_fn=lambda device: not bool(device["child_lock"]),
        unique_prefix="child lock status",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Danfoss Icon2 (Local) binary sensors."""
    coordinator: DanfossLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _build_entities(
        coordinator: DanfossLocalCoordinator,
    ) -> list[DanfossLocalBinarySensor]:
        # Fixed entity set per thermostat - see number.py for why creation is
        # not gated on the key already being present in the device data.
        return [
            DanfossLocalBinarySensor(coordinator, device_id, description)
            for device_id in (coordinator.data or {})
            for description in BINARY_SENSORS
        ]

    async_setup_dynamic_platform_entities(coordinator, async_add_entities, _build_entities)


class DanfossLocalBinarySensor(DanfossLocalEntity, BinarySensorEntity):
    """Representation of a Danfoss Icon2 (Local) binary sensor."""

    entity_description: DanfossLocalBinarySensorDescription

    def __init__(
        self,
        coordinator: DanfossLocalCoordinator,
        device_id: str,
        description: DanfossLocalBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{description.unique_prefix}_{device_id}_danfoss_local"

    @property
    def is_on(self) -> bool | None:
        """Return the current binary sensor state (None until first report)."""
        try:
            return self.entity_description.value_fn(self.device)
        except (KeyError, TypeError):
            return None
