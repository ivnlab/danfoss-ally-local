"""Switch support for Danfoss Icon2 (Local)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .coordinator import DanfossLocalCoordinator
from .entity import DanfossLocalEntity, async_setup_dynamic_platform_entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Danfoss Icon2 (Local) switches."""
    coordinator: DanfossLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _build_entities(coordinator: DanfossLocalCoordinator) -> list[DanfossLocalPreheatSwitch]:
        # One per thermostat, unconditionally - see number.py for why creation
        # is not gated on the dp already being present in the device data.
        return [
            DanfossLocalPreheatSwitch(coordinator, device_id)
            for device_id in (coordinator.data or {})
        ]

    async_setup_dynamic_platform_entities(coordinator, async_add_entities, _build_entities)


class DanfossLocalPreheatSwitch(DanfossLocalEntity, SwitchEntity):
    """Pre-heat enable switch (raw dp 1)."""

    _attr_icon = "mdi:heat-wave"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "pre_heat"

    def __init__(self, coordinator: DanfossLocalCoordinator, device_id: str) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"pre_heat_{device_id}_danfoss_local"

    @property
    def is_on(self) -> bool | None:
        """Return whether pre-heat is enabled (None until first report)."""
        value = self.device.get("switch")
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs) -> None:
        """Enable pre-heat."""
        await self.coordinator.async_set_switch(
            self._device_id, True, optimistic_updates={"switch": True}
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Disable pre-heat."""
        await self.coordinator.async_set_switch(
            self._device_id, False, optimistic_updates={"switch": False}
        )
