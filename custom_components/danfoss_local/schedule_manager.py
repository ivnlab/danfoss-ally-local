"""Home Assistant glue for local weekly schedules: storage, minute tick,
service handlers and change notifications for the schedule sensors."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import _MODE_TO_SETPOINT, DanfossLocalCoordinator
from .schedule import VALID_MODES, Holiday, Period, WeeklyProgram
from .schedule_runtime import DeviceSchedule, ScheduleEngine, ScheduleExecutor

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.schedules"
STORAGE_VERSION = 1

SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_CLEAR_SCHEDULE = "clear_schedule"
SERVICE_COPY_SCHEDULE = "copy_schedule"
SERVICE_SET_HOLIDAY = "set_holiday"
SERVICE_CLEAR_HOLIDAY = "clear_holiday"
SERVICE_ENABLE_SCHEDULE = "enable_schedule"

_PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required("start"): cv.string,  # "HH:MM"
        vol.Required("end"): cv.string,
        vol.Required("mode"): vol.In(sorted(VALID_MODES)),
    }
)
_PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Optional("default_mode", default="leaving_home"): vol.In(sorted(VALID_MODES)),
        vol.Required("days"): vol.All([[_PERIOD_SCHEMA]], vol.Length(min=7, max=7)),
    }
)


def _hhmm(text: str) -> int:
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)


def _program_from_service(data: dict) -> WeeklyProgram:
    days = [
        [Period(_hhmm(p["start"]), _hhmm(p["end"]), p["mode"]) for p in day]
        for day in data["days"]
    ]
    return WeeklyProgram(days=days, default_mode=data.get("default_mode", "leaving_home"))


class ScheduleManager:
    """Owns the engine, persists schedules and runs the minute tick."""

    def __init__(self, hass: HomeAssistant, coordinator: DanfossLocalCoordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.engine = ScheduleEngine()
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._executor = ScheduleExecutor(self.engine, self._apply_mode)
        self._listeners: list[Callable[[], None]] = []
        self._unsub_tick: Callable[[], None] | None = None

    # -- lifecycle -------------------------------------------------------

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        for device_id, raw in data.get("devices", {}).items():
            try:
                self.engine.set_schedule(device_id, DeviceSchedule.from_dict(raw))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Dropping unreadable schedule for %s: %s", device_id, err)
        # Seed baselines now so the first real minute tick can act on a
        # boundary if one falls right after startup.
        self.engine.tick(dt_util.now())
        self._unsub_tick = async_track_time_change(self.hass, self._on_minute, second=0)

    async def async_unload(self) -> None:
        if self._unsub_tick:
            self._unsub_tick()
            self._unsub_tick = None

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"devices": {d: s.to_dict() for d, s in self.engine.all_schedules().items()}}
        )
        self._notify()

    # -- tick + write ----------------------------------------------------

    @callback
    def _on_minute(self, _now: datetime) -> None:
        self.hass.async_create_task(self._async_minute())

    async def _async_minute(self) -> None:
        await self._executor.async_tick(dt_util.now())
        self._notify()

    async def _apply_mode(self, device_id: str, mode: str) -> None:
        """Same write path climate.py uses for a preset change: mode dp, then
        nudge the dp114 active-setpoint mirror to that mode's setpoint."""
        await self.coordinator.async_set_mode(device_id, mode, optimistic_updates={"mode": mode})
        device = (self.coordinator.data or {}).get(device_id, {})
        code = _MODE_TO_SETPOINT.get(mode)
        target = device.get(code) if code else None
        if target is not None and "manual_mode_fast" in device:
            await self.coordinator.async_set_temperature(
                device_id,
                float(target),
                code="manual_mode_fast",
                optimistic_updates={"manual_mode_fast": float(target)},
            )

    # -- listeners for sensors ------------------------------------------

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update)

        def _remove() -> None:
            self._listeners.remove(update)

        return _remove

    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    # -- public mutations (used by services) -----------------------------

    async def async_set_program(self, device_id: str, program: WeeklyProgram, enabled: bool | None) -> None:
        current = self.engine.get_schedule(device_id) or DeviceSchedule()
        self.engine.set_schedule(
            device_id,
            DeviceSchedule(program, current.holiday, current.enabled if enabled is None else enabled),
        )
        await self._async_save()

    async def async_clear(self, device_id: str) -> None:
        self.engine.remove_schedule(device_id)
        await self._async_save()

    async def async_copy(self, source_id: str, targets: list[str]) -> None:
        src = self.engine.get_schedule(source_id)
        if src is None:
            raise vol.Invalid(f"{source_id} has no schedule to copy")
        for tid in targets:
            if tid == source_id:
                continue
            cur = self.engine.get_schedule(tid) or DeviceSchedule()
            self.engine.set_schedule(tid, DeviceSchedule(src.program, cur.holiday, cur.enabled))
        await self._async_save()

    async def async_set_holiday(self, device_id: str, start: date, end: date, mode: str) -> None:
        cur = self.engine.get_schedule(device_id) or DeviceSchedule()
        self.engine.set_schedule(device_id, DeviceSchedule(cur.program, Holiday(start, end, mode), cur.enabled))
        await self._async_save()

    async def async_clear_holiday(self, device_id: str) -> None:
        cur = self.engine.get_schedule(device_id)
        if cur is None:
            return
        self.engine.set_schedule(device_id, DeviceSchedule(cur.program, None, cur.enabled))
        await self._async_save()

    async def async_enable(self, device_id: str, enabled: bool) -> None:
        cur = self.engine.get_schedule(device_id) or DeviceSchedule()
        self.engine.set_schedule(device_id, DeviceSchedule(cur.program, cur.holiday, enabled))
        await self._async_save()

    # -- service registration -------------------------------------------

    def _resolve_device(self, ref: str) -> str:
        """Accept either an HA device-registry id or the raw Tuya device_id."""
        entry = dr.async_get(self.hass).async_get(ref)
        if entry is not None:
            for domain, ident in entry.identifiers:
                if domain == DOMAIN:
                    return ident
        if ref in (self.coordinator.data or {}):
            return ref
        raise vol.Invalid(f"unknown device {ref}")

    def all_device_ids(self) -> list[str]:
        return list((self.coordinator.data or {}).keys())


def async_register_services(hass: HomeAssistant, get_manager: Callable[[], ScheduleManager | None]) -> None:
    """Register the schedule services once per HA instance."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        return

    def mgr() -> ScheduleManager:
        m = get_manager()
        if m is None:
            raise vol.Invalid("danfoss_local is not loaded")
        return m

    async def set_schedule(call: ServiceCall) -> None:
        m = mgr()
        dev = m._resolve_device(call.data["device_id"])
        program = _program_from_service(_PROGRAM_SCHEMA(call.data["program"]))
        await m.async_set_program(dev, program, call.data.get("enabled"))

    async def clear_schedule(call: ServiceCall) -> None:
        m = mgr()
        await m.async_clear(m._resolve_device(call.data["device_id"]))

    async def copy_schedule(call: ServiceCall) -> None:
        m = mgr()
        src = m._resolve_device(call.data["device_id"])
        targets = [m._resolve_device(t) for t in call.data.get("targets", [])] or m.all_device_ids()
        await m.async_copy(src, targets)

    async def set_holiday(call: ServiceCall) -> None:
        m = mgr()
        await m.async_set_holiday(
            m._resolve_device(call.data["device_id"]),
            call.data["start"],
            call.data["end"],
            call.data.get("mode", "holiday"),
        )

    async def clear_holiday(call: ServiceCall) -> None:
        m = mgr()
        await m.async_clear_holiday(m._resolve_device(call.data["device_id"]))

    async def enable_schedule(call: ServiceCall) -> None:
        m = mgr()
        await m.async_enable(m._resolve_device(call.data["device_id"]), call.data["enabled"])

    dev = vol.Required("device_id")
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, set_schedule,
        schema=vol.Schema({dev: cv.string, vol.Required("program"): dict, vol.Optional("enabled"): cv.boolean}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_SCHEDULE, clear_schedule, schema=vol.Schema({dev: cv.string})
    )
    hass.services.async_register(
        DOMAIN, SERVICE_COPY_SCHEDULE, copy_schedule,
        schema=vol.Schema({dev: cv.string, vol.Optional("targets"): [cv.string]}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_HOLIDAY, set_holiday,
        schema=vol.Schema(
            {dev: cv.string, vol.Required("start"): cv.date, vol.Required("end"): cv.date,
             vol.Optional("mode", default="holiday"): vol.In(sorted(VALID_MODES))}
        ),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_HOLIDAY, clear_holiday, schema=vol.Schema({dev: cv.string})
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ENABLE_SCHEDULE, enable_schedule,
        schema=vol.Schema({dev: cv.string, vol.Required("enabled"): cv.boolean}),
    )
