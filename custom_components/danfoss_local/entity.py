"""Entity helpers for Danfoss Icon2 (Local).

Adapted from mtrab/danfoss_ally's entity.py (GPLv3) - same shared-entity
pattern, wired to DanfossLocalCoordinator instead of the cloud coordinator.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DanfossLocalCoordinator

type DanfossEntityFactory = Callable[
    [DanfossLocalCoordinator],
    Iterable[Entity],
]


def async_setup_dynamic_platform_entities(
    coordinator: DanfossLocalCoordinator,
    async_add_entities: Callable[[list[Entity]], None],
    entity_factory: DanfossEntityFactory,
) -> None:
    """Add entities now and whenever the coordinator discovers new devices."""
    known_unique_ids: set[str] = set()

    @callback
    def async_add_new_entities() -> None:
        new_entities: list[Entity] = []

        for entity in entity_factory(coordinator):
            if entity.unique_id is None or entity.unique_id in known_unique_ids:
                continue
            known_unique_ids.add(entity.unique_id)
            new_entities.append(entity)

        if new_entities:
            async_add_entities(new_entities)

    async_add_new_entities()
    coordinator.async_add_listener(async_add_new_entities)


class DanfossLocalEntity(CoordinatorEntity[DanfossLocalCoordinator], Entity):
    """Shared base entity for Danfoss Icon2 (Local) entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DanfossLocalCoordinator, device_id: str) -> None:
        """Initialize the shared device entity state."""
        super().__init__(coordinator, context=device_id)
        self._device_id = device_id

    @property
    def device(self) -> dict[str, Any]:
        """Return the latest cached device data."""
        if self.coordinator.data is None:
            return {}
        return self.coordinator.data.get(self._device_id, {})

    def device_value(self, *keys: str, default: Any = None) -> Any:
        """Return the first available device value for the provided keys."""
        for key in keys:
            if key in self.device:
                return self.device[key]
        return default

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the backing Danfoss device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Danfoss",
            model=self.device.get("model"),
            name=self.device.get("name", self._device_id),
        )

    @property
    def available(self) -> bool:
        """Return whether the backing device is online."""
        return self._device_id in (self.coordinator.data or {}) and bool(
            self.device.get("online", True)
        )

    def uses_window_sensor_source(self) -> bool:
        """Always false: window sensor override is not wired up locally."""
        return False

    def native_window_detection_enabled(self) -> bool:
        """Always false: no window_toggle dp on Icon2 RT."""
        return bool(self.device.get("window_toggle"))
