"""Storage-shape and execution of local weekly schedules for Danfoss Icon2 (Local).

The executor deliberately mimics how Danfoss's cloud drives the thermostat:
it only writes when the *desired state* of the program changes (a boundary
crossing, a holiday starting or ending, a Saturday-window edge during an
at-home holiday), never continuously. Between two such changes a manual
change on the thermostat or in the app stands until the next one - the
"respect until boundary" behaviour Danfoss has and the user asked for.

`ScheduleEngine` is pure and unit-testable: feed it successive timestamps and
it tells you, per device, the new desired state to apply now.
`ScheduleExecutor` wires that to a time tick and the coordinator.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from .schedule import Desired, Holiday, WeeklyProgram, desired_state_at

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

    def desired(self, moment: datetime) -> Desired | None:
        if not self.enabled:
            return None
        return desired_state_at(self.program, moment, self.holiday)

    def desired_mode(self, moment: datetime) -> str | None:
        d = self.desired(moment)
        return d.mode if d else None

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
    """Pure change detector over desired states.

    `tick(now)` returns {device_id: (desired, previous)} for devices whose
    desired state changed since the previous tick. The first tick for a
    device only seeds its baseline and returns nothing, so a standing manual
    override survives a restart (or a schedule edit) instead of being
    stomped mid-slot. `seed(device_id, desired)` sets the baseline explicitly
    after an immediate apply (holiday set/cancel).
    """

    def __init__(self) -> None:
        self._schedules: dict[str, DeviceSchedule] = {}
        self._last: dict[str, Desired | None] = {}

    def set_schedule(self, device_id: str, schedule: DeviceSchedule) -> None:
        self._schedules[device_id] = schedule
        self._last.pop(device_id, None)

    def remove_schedule(self, device_id: str) -> None:
        self._schedules.pop(device_id, None)
        self._last.pop(device_id, None)

    def get_schedule(self, device_id: str) -> DeviceSchedule | None:
        return self._schedules.get(device_id)

    def all_schedules(self) -> dict[str, DeviceSchedule]:
        return dict(self._schedules)

    def seed(self, device_id: str, desired: Desired | None) -> None:
        self._last[device_id] = desired

    def next_change(self, device_id: str, now: datetime) -> tuple[datetime, str] | None:
        """When the scheduled *mode* next changes (display only)."""
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

    def tick(self, now: datetime) -> dict[str, tuple[Desired, Desired | None]]:
        changes: dict[str, tuple[Desired, Desired | None]] = {}
        for device_id, sched in self._schedules.items():
            desired = sched.desired(now)
            if device_id not in self._last:
                self._last[device_id] = desired
                continue
            previous = self._last[device_id]
            if desired is not None and desired != previous:
                changes[device_id] = (desired, previous)
            self._last[device_id] = desired
        return changes


class ScheduleExecutor:
    """Wires ScheduleEngine to HA time ticks and the coordinator."""

    def __init__(
        self,
        engine: ScheduleEngine,
        apply: Callable[[str, Desired, Desired | None], Awaitable[None]],
    ) -> None:
        self._engine = engine
        self._apply = apply

    async def async_tick(self, now: datetime) -> None:
        for device_id, (desired, previous) in self._engine.tick(now).items():
            try:
                _LOGGER.debug("Schedule change: %s -> %s (was %s)", device_id, desired, previous)
                await self._apply(device_id, desired, previous)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Schedule write failed for %s (%s): %s", device_id, desired, err)
