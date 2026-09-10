"""Home Assistant glue for local weekly schedules: storage, minute tick,
service handlers and change notifications for the schedule sensors.

Service payloads use the Danfoss Ally shapes so nothing here can express a
setting the app or the cloud would not accept:
  program  = {"days": [[{"start": "06:00", "end": "08:00"}, ...] x7]}  (at-home windows)
  holiday  = kind "away"  + start/end datetimes, or
             kind "at_home" + start/end dates (requires Saturday windows)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import _MODE_TO_SETPOINT, DanfossLocalCoordinator
from .schedule import (
    HOLIDAY_AT_HOME,
    HOLIDAY_AWAY,
    SATURDAY,
    Holiday,
    WeeklyProgram,
    Window,
    hhmm_to_min,
)
from .schedule_runtime import DeviceSchedule, ScheduleEngine, ScheduleExecutor

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY = f"{DOMAIN}.schedules"
STORAGE_VERSION = 1  # shape changes are tracked by the version_shape key, not the Store version (which would need a migrator)

SERVICE_SET_SCHEDULE = "set_schedule"
SERVICE_CLEAR_SCHEDULE = "clear_schedule"
SERVICE_COPY_SCHEDULE = "copy_schedule"
SERVICE_SET_HOLIDAY = "set_holiday"
SERVICE_CLEAR_HOLIDAY = "clear_holiday"
SERVICE_ENABLE_SCHEDULE = "enable_schedule"

_WINDOW_SCHEMA = vol.Schema({vol.Required("start"): cv.string, vol.Required("end"): cv.string})
_PROGRAM_SCHEMA = vol.Schema({vol.Required("days"): vol.All([[_WINDOW_SCHEMA]], vol.Length(min=7, max=7))})


def _program_from_service(data: dict) -> WeeklyProgram:
    try:
        return WeeklyProgram(
            days=[[Window(hhmm_to_min(w["start"]), hhmm_to_min(w["end"])) for w in day] for day in data["days"]]
        )
    except ValueError as err:
        # Model rules (30-minute grid, start < end, no overlaps) surface as a
        # normal service validation error, not a server error.
        raise vol.Invalid(str(err)) from err


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
        if data.get("version_shape") != 2 and data:
            # v1 prototype shape (per-window modes) is not Ally-compatible;
            # drop it rather than guess a translation.
            _LOGGER.warning("Discarding pre-Ally-shape schedule storage")
            data = {}
        for device_id, raw in data.get("devices", {}).items():
            try:
                self.engine.set_schedule(device_id, DeviceSchedule.from_dict(raw))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Dropping unreadable schedule for %s: %s", device_id, err)
        self.engine.tick(dt_util.now())
        self._unsub_tick = async_track_time_change(self.hass, self._on_minute, second=0)

    async def async_unload(self) -> None:
        if self._unsub_tick:
            self._unsub_tick()
            self._unsub_tick = None

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"version_shape": 2, "devices": {d: s.to_dict() for d, s in self.engine.all_schedules().items()}}
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
                device_id, float(target), code="manual_mode_fast",
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

    # -- mutations (used by services) ------------------------------------

    def _current(self, device_id: str) -> DeviceSchedule:
        return self.engine.get_schedule(device_id) or DeviceSchedule()

    async def async_set_program(self, device_id: str, program: WeeklyProgram, enabled: bool | None) -> None:
        cur = self._current(device_id)
        if cur.holiday and cur.holiday.kind == HOLIDAY_AT_HOME and not program.days[SATURDAY]:
            # Same rule as the app: Saturday cannot be cleared while an
            # at-home holiday is planned.
            raise vol.Invalid("Saturday windows cannot be cleared while an at-home holiday is planned")
        self.engine.set_schedule(device_id, DeviceSchedule(program, cur.holiday, cur.enabled if enabled is None else enabled))
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
            cur = self._current(tid)
            self.engine.set_schedule(tid, DeviceSchedule(src.program, cur.holiday, cur.enabled))
        await self._async_save()

    async def async_set_holiday(self, device_id: str, holiday: Holiday) -> None:
        cur = self._current(device_id)
        if holiday.kind == HOLIDAY_AT_HOME and not cur.program.days[SATURDAY]:
            # Same rule as the app: at-home holiday needs a Saturday program.
            raise vol.Invalid("At-home holiday requires Saturday windows to be set first")
        self.engine.set_schedule(device_id, DeviceSchedule(cur.program, holiday, cur.enabled))
        await self._async_save()

    async def async_clear_holiday(self, device_id: str) -> None:
        cur = self.engine.get_schedule(device_id)
        if cur is None:
            return
        self.engine.set_schedule(device_id, DeviceSchedule(cur.program, None, cur.enabled))
        await self._async_save()

    async def async_enable(self, device_id: str, enabled: bool) -> None:
        cur = self._current(device_id)
        self.engine.set_schedule(device_id, DeviceSchedule(cur.program, cur.holiday, enabled))
        await self._async_save()

    # -- helpers ---------------------------------------------------------

    def resolve_device(self, ref: str) -> str:
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

    def targets_of(m: ScheduleManager, call: ServiceCall) -> list[str]:
        """`device_id` or `all: true` -> list of raw device ids."""
        if call.data.get("all"):
            return m.all_device_ids()
        return [m.resolve_device(call.data["device_id"])]

    async def set_schedule(call: ServiceCall) -> None:
        m = mgr()
        program = _program_from_service(_PROGRAM_SCHEMA(call.data["program"]))
        for dev in targets_of(m, call):
            await m.async_set_program(dev, program, call.data.get("enabled"))

    async def clear_schedule(call: ServiceCall) -> None:
        m = mgr()
        for dev in targets_of(m, call):
            await m.async_clear(dev)

    async def copy_schedule(call: ServiceCall) -> None:
        m = mgr()
        src = m.resolve_device(call.data["device_id"])
        targets = [m.resolve_device(t) for t in call.data.get("targets", [])] or m.all_device_ids()
        await m.async_copy(src, targets)

    async def set_holiday(call: ServiceCall) -> None:
        m = mgr()
        kind = call.data["kind"]
        try:
            if kind == HOLIDAY_AWAY:
                holiday = Holiday(kind, dt_util.as_local(call.data["start"]), dt_util.as_local(call.data["end"]))
            else:
                s, e = call.data["start"], call.data["end"]
                holiday = Holiday(kind, datetime(s.year, s.month, s.day), datetime(e.year, e.month, e.day))
        except (ValueError, AttributeError) as err:
            raise vol.Invalid(f"invalid holiday range: {err}") from err
        for dev in targets_of(m, call):
            await m.async_set_holiday(dev, holiday)

    async def clear_holiday(call: ServiceCall) -> None:
        m = mgr()
        for dev in targets_of(m, call):
            await m.async_clear_holiday(dev)

    async def enable_schedule(call: ServiceCall) -> None:
        m = mgr()
        for dev in targets_of(m, call):
            await m.async_enable(dev, call.data["enabled"])

    target = {vol.Optional("device_id"): cv.string, vol.Optional("all", default=False): cv.boolean}
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, set_schedule,
        schema=vol.Schema({**target, vol.Required("program"): dict, vol.Optional("enabled"): cv.boolean}),
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_SCHEDULE, clear_schedule, schema=vol.Schema(target))
    hass.services.async_register(
        DOMAIN, SERVICE_COPY_SCHEDULE, copy_schedule,
        schema=vol.Schema({vol.Required("device_id"): cv.string, vol.Optional("targets"): [cv.string]}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_HOLIDAY, set_holiday,
        schema=vol.Schema(
            {
                **target,
                vol.Required("kind"): vol.In([HOLIDAY_AWAY, HOLIDAY_AT_HOME]),
                # away: datetimes; at_home: dates. Both accepted as strings and
                # parsed by cv; the handler picks the right interpretation.
                vol.Required("start"): vol.Any(cv.datetime, cv.date),
                vol.Required("end"): vol.Any(cv.datetime, cv.date),
            }
        ),
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_HOLIDAY, clear_holiday, schema=vol.Schema(target))
    hass.services.async_register(
        DOMAIN, SERVICE_ENABLE_SCHEDULE, enable_schedule,
        schema=vol.Schema({**target, vol.Required("enabled"): cv.boolean}),
    )
