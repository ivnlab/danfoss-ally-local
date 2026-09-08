"""Lock support for Danfoss Icon2 (Local) - child lock."""

from __future__ import annotations

from homeassistant.components.lock import LockEntity
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
    """Set up Danfoss Icon2 (Local) locks."""
    coordinator: DanfossLocalCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _build_entities(coordinator: DanfossLocalCoordinator) -> list[DanfossLocalChildLock]:
        # One per thermostat, unconditionally - see number.py for why creation
        # is not gated on the dp already being present in the device data.
        return [
            DanfossLocalChildLock(coordinator, device_id)
            for device_id in (coordinator.data or {})
        ]

    async_setup_dynamic_platform_entities(coordinator, async_add_entities, _build_entities)


class DanfossLocalChildLock(DanfossLocalEntity, LockEntity):
    """Child lock (raw dp 30). true = locked."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "child_lock"

    def __init__(self, coordinator: DanfossLocalCoordinator, device_id: str) -> None:
        """Initialize the lock."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"child_lock_{device_id}_danfoss_local"

    @property
    def is_locked(self) -> bool | None:
        """Return whether the child lock is engaged (None until first report)."""
        value = self.device.get("child_lock")
        return None if value is None else bool(value)

    async def async_lock(self, **kwargs) -> None:
        """Engage the child lock."""
        await self.coordinator.async_set_child_lock(
            self._device_id, True, optimistic_updates={"child_lock": True}
        )

    async def async_unlock(self, **kwargs) -> None:
        """Disengage the child lock."""
        await self.coordinator.async_set_child_lock(
            self._device_id, False, optimistic_updates={"child_lock": False}
        )
