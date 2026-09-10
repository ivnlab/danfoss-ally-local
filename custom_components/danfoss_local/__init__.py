"""The Danfoss Icon2 integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import DanfossLocalCoordinator
from .panel import async_register_heating_panel, async_unregister_heating_panel
from .schedule_manager import ScheduleManager, async_register_services

PLATFORMS = ["climate", "sensor", "binary_sensor", "number", "switch", "lock"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Danfoss Icon2 from a config entry."""
    coordinator = DanfossLocalCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Local weekly schedules live next to the coordinator so platforms can
    # reach them without a second hass.data key.
    coordinator.schedule_manager = ScheduleManager(hass, coordinator)
    await coordinator.schedule_manager.async_load()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    async_register_services(
        hass,
        lambda: getattr(hass.data.get(DOMAIN, {}).get(entry.entry_id), "schedule_manager", None),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_heating_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        manager = getattr(coordinator, "schedule_manager", None)
        if manager is not None:
            await manager.async_unload()
        async_unregister_heating_panel(hass)
    return unload_ok
