"""Storage and execution of local weekly schedules for Danfoss Icon2 (Local).

The executor deliberately mimics how Danfoss's cloud drives the thermostat:
it only writes a preset at a *boundary crossing* of the program, never
continuously. Between two boundaries a manual change (button on the
thermostat, a tap in the app, or a temporary override from HA) is left
untouched and stands until the next scheduled transition - which is the
"respect until boundary" behaviour the user asked for.

The boundary detection is pure and unit-testable via `ScheduleEngine`: feed
it successive timestamps and it tells you, per device, which mode (if any)
must be written *now*. The HA-facing `ScheduleExecutor` just wires that to a
time tick and the coordinator's `async_set_mode`.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

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
            "holiday": (
                {
                    "start": self.holiday.start.isoformat(),
                    "end": self.holiday.end.isoformat(),
                    "mode": self.holiday.mode,
                }
                if self.holiday
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceSchedule":
        from datetime import date

        hol = data.get("holiday")
        holiday = (
            Holiday(date.fromisoformat(hol["start"]), date.fromisoformat(hol["end"]), hol["mode"])
            if hol
            else None
        )
        return cls(
            program=WeeklyProgram.from_dict(data.get("program", {})),
            holiday=holiday,
            enabled=data.get("enabled", True),
        )


class ScheduleEngine:
    """Pure boundary detector. No HA, no I/O - unit-testable.

    `tick(now)` returns {device_id: mode} for devices whose scheduled mode
    changed since the last tick (i.e. a boundary was crossed). The very first
    tick after (re)start only seeds state and returns nothing, so a standing
    manual override survives a restart instead of being stomped.
    """

    def __init__(self) -> None:
        self._schedules: dict[str, DeviceSchedule] = {}
        self._last_desired: dict[str, str | None] = {}
        self._seeded = False

    def set_schedule(self, device_id: str, schedule: DeviceSchedule) -> None:
        self._schedules[device_id] = schedule
        # Editing a schedule re-seeds that device's baseline at the next tick,
        # so a save does not itself force an immediate write mid-slot.
        self._last_desired.pop(device_id, None)

    def remove_schedule(self, device_id: str) -> None:
        self._schedules.pop(device_id, None)
        self._last_desired.pop(device_id, None)

    def get_schedule(self, device_id: str) -> DeviceSchedule | None:
        return self._schedules.get(device_id)

    def all_schedules(self) -> dict[str, DeviceSchedule]:
        return dict(self._schedules)

    def next_change(self, device_id: str, now: datetime) -> tuple[datetime, str] | None:
        """When and to what the schedule next transitions, scanning ahead a
        week in one-minute steps. Used only for display, not for control."""
        from datetime import timedelta

        sched = self._schedules.get(device_id)
        if sched is None or not sched.enabled:
            return None
        cur = sched.desired_mode(now)
        probe = now.replace(second=0, microsecond=0)
        for _ in range(7 * 24 * 60):
            probe = probe + timedelta(minutes=1)
            m = sched.desired_mode(probe)
            if m != cur:
                return probe, m
        return None

    def tick(self, now: datetime) -> dict[str, str]:
        """Return the writes to apply at this instant (boundary crossings)."""
        writes: dict[str, str] = {}
        for device_id, sched in self._schedules.items():
            desired = sched.desired_mode(now)
            previous = self._last_desired.get(device_id, "__unset__")
            if previous == "__unset__":
                # first observation for this device: seed, do not act
                self._last_desired[device_id] = desired
                continue
            if desired is not None and desired != previous:
                writes[device_id] = desired
            self._last_desired[device_id] = desired
        self._seeded = True
        return writes


class ScheduleExecutor:
    """Wires ScheduleEngine to HA time ticks and the coordinator."""

    def __init__(
        self,
        engine: ScheduleEngine,
        apply_mode: Callable[[str, str], Awaitable[None]],
    ) -> None:
        self._engine = engine
        self._apply_mode = apply_mode

    async def async_tick(self, now: datetime) -> None:
        for device_id, mode in self._engine.tick(now).items():
            try:
                _LOGGER.debug("Schedule boundary: %s -> %s", device_id, mode)
                await self._apply_mode(device_id, mode)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Schedule write failed for %s (%s): %s", device_id, mode, err)
