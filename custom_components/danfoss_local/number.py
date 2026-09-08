"""Number support for Danfoss Icon2 (Local)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .coordinator import DanfossLocalCoordinator
from .entity import DanfossLocalEntity, async_setup_dynamic_platform_entities

MIN_TEMPERATURE = 4.0
MAX_TEMPERATURE = 35.0
TEMPERATURE_STEP = 0.5


@dataclass(frozen=True, kw_only=True)
class DanfossLocalNumberDescription(NumberEntityDescription):
    """Describe a Danfoss Icon2 (Local) number entity."""

    unique_prefix: str
    setter_name: str


NUMBERS: tuple[DanfossLocalNumberDescription, ...] = (
    DanfossLocalNumberDescription(
        key="upper_temp",
        translation_key="upper_temp",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=MIN_TEMPERATURE,
        native_max_value=MAX_TEMPERATURE,
        native_step=TEMPERATURE_STEP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        unique_prefix="upper temperature",
        setter_name="async_set_upper_temp",
    ),
    DanfossLocalNumberDescription(
        key="lower_temp",
        translation_key="lower_temp",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=MIN_TEMPERATURE,
        native_max_value=MAX_TEMPERATURE,
        native_step=TEMPERATURE_STEP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        unique_prefix="lower temperature",
        setter_name="async_set_lower_temp",
    ),
    DanfossLocalNumberDescription(
        key="at_home_setting",
        translation_key="at_home_setting",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=MIN_TEMPERATURE,
        native_max_value=MAX_TEMPERATURE,
        native_step=TEMPERATURE_STEP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        unique_prefix="at home setting",
        setter_name="async_set_at_home_setting",
    ),
    DanfossLocalNumberDescription(
        key="leaving_home_setting",
        translation_key="leaving_home_setting",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=MIN_TEMPERATURE,
        native_max_value=MAX_TEMPERATURE,
        native_step=TEMPERATURE_STEP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        unique_prefix="leaving home setting",
        setter_name="async_set_leaving_home_setting",
    ),
    DanfossLocalNumberDescription(
        key="pause_setting",
        translation_key="pause_setting",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=MIN_TEMPERATURE,
        native_max_value=MAX_TEMPERATURE,
        native_step=TEMPERATURE_STEP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        unique_prefix="pause setting",
        setter_name="async_set_pause_setting",
    ),
    DanfossLocalNumberDescription(
        key="holiday_setting",
        translation_key="holiday_setting",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_min_value=MIN_TEMPERATURE,
        native_max_value=MAX_TEMPERATURE,
        native_step=TEMPERATURE_STEP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
        unique_prefix="holiday setting",
        setter_name="async_set_holiday_setting",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Danfoss Icon2 (Local) numbers."""
    coordinator: DanfossLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _build_entities(coordinator: DanfossLocalCoordinator) -> list[DanfossLocalNumber]:
        # Every RT exposes the same fixed set of setpoints, so create all of
        # them for every thermostat unconditionally. The gateway only reports
        # a dp locally once the device has changed it at least once, so
        # gating on "key in device" made e.g. the Home setpoint appear only
        # on thermostats whose Home temperature had ever been touched.
        return [
            DanfossLocalNumber(coordinator, device_id, description)
            for device_id in (coordinator.data or {})
            for description in NUMBERS
        ]

    async_setup_dynamic_platform_entities(coordinator, async_add_entities, _build_entities)


class DanfossLocalNumber(DanfossLocalEntity, NumberEntity):
    """Representation of a Danfoss Icon2 (Local) number."""

    entity_description: DanfossLocalNumberDescription

    def __init__(
        self,
        coordinator: DanfossLocalCoordinator,
        device_id: str,
        description: DanfossLocalNumberDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, device_id)
        self.entity_description = description
        self._attr_unique_id = f"{description.unique_prefix}_{device_id}_danfoss_local"

    @property
    def native_value(self) -> float | None:
        """Return the current number value."""
        value = self.device.get(self.entity_description.key)
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value."""
        temperature = float(value)
        setter = getattr(self.coordinator, self.entity_description.setter_name)
        await setter(
            self._device_id,
            temperature,
            optimistic_updates={self.entity_description.key: temperature},
        )
