"""Storage-shape and execution of local weekly schedules for Danfoss Icon2 (Local).

The executor deliberately mimics how Danfoss's cloud drives the thermostat:
it only writes a preset at a *boundary crossing* of the program, never
continuously. Between two boundaries a manual change (button on the
thermostat, a tap in the app, or a temporary override from HA) is left
untouched and stands until the next scheduled transition - the "respect
until boundary" behaviour Danfoss has and the user asked for.

`ScheduleEngine` is pure and unit-testable: feed it successive timestamps and
it tells you, per device, which mode (if any) must be written now.
`ScheduleExecutor` wires that to a time tick and the coordinator.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from .schedule import Holiday, WeeklyProgram, desired_mode_at

_LOGGER = logging.getLogger(__name__)


class DeviceSchedule:
    """A device's weekly program plus optional holiday, and enabled flag."""

    def __init__(
        self,
        program: WeeklyProgram | None = None,
        holiday: Holiday | None = None,
        enabled: bool = True,
    ) -> None:
        self.program = program or WeeklyProgram()
        self.holiday = holiday
        self.enabled = enabled

    def desired_mode(self, moment: datetime) -> str | None:
        if not self.enabled:
            return None
        return desired_mode_at(self.program, moment, self.holiday)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "program": self.program.to_dict(),
            "holiday": self.holiday.to_dict() if self.holiday else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceSchedule":
        hol = data.get("holiday")
        return cls(
            program=WeeklyProgram.from_dict(data.get("program") or {}),
            holiday=Holiday.from_dict(hol) if hol else None,
            enabled=data.get("enabled", True),
        )


class ScheduleEngine:
    """Pure boundary detector.

    `tick(now)` returns {device_id: mode} for devices whose scheduled mode
    changed since the previous tick. The first tick for a device only seeds
    its baseline and returns nothing, so a standing manual override survives
    a restart (or a schedule edit) instead of being stomped mid-slot.
    """

    def __init__(self) -> None:
        self._schedules: dict[str, DeviceSchedule] = {}
        self._last_desired: dict[str, str | None] = {}

    def set_schedule(self, device_id: str, schedule: DeviceSchedule) -> None:
        self._schedules[device_id] = schedule
        self._last_desired.pop(device_id, None)

    def remove_schedule(self, device_id: str) -> None:
        self._schedules.pop(device_id, None)
        self._last_desired.pop(device_id, None)

    def get_schedule(self, device_id: str) -> DeviceSchedule | None:
        return self._schedules.get(device_id)

    def all_schedules(self) -> dict[str, DeviceSchedule]:
        return dict(self._schedules)

    def next_change(self, device_id: str, now: datetime) -> tuple[datetime, str] | None:
        """When and to what the schedule next transitions (display only)."""
        sched = self._schedules.get(device_id)
        if sched is None or not sched.enabled:
            return None
        cur = sched.desired_mode(now)
        probe = now.replace(second=0, microsecond=0)
        for _ in range(8 * 24 * 60):
            probe = probe + timedelta(minutes=1)
            m = sched.desired_mode(probe)
            if m != cur:
                return probe, m
        return None

    def tick(self, now: datetime) -> dict[str, str]:
        writes: dict[str, str] = {}
        for device_id, sched in self._schedules.items():
            desired = sched.desired_mode(now)
            if device_id not in self._last_desired:
                self._last_desired[device_id] = desired
                continue
            if desired is not None and desired != self._last_desired[device_id]:
                writes[device_id] = desired
            self._last_desired[device_id] = desired
        return writes


class ScheduleExecutor:
    """Wires ScheduleEngine to HA time ticks and the coordinator."""

    def __init__(self, engine: ScheduleEngine, apply_mode: Callable[[str, str], Awaitable[None]]) -> None:
        self._engine = engine
        self._apply_mode = apply_mode

    async def async_tick(self, now: datetime) -> None:
        for device_id, mode in self._engine.tick(now).items():
            try:
                _LOGGER.debug("Schedule boundary: %s -> %s", device_id, mode)
                await self._apply_mode(device_id, mode)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Schedule write failed for %s (%s): %s", device_id, mode, err)
