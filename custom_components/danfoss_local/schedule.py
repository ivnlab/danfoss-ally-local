"""Weekly schedule model and evaluator for Danfoss Icon2 (Local).

Pure logic, free of Home Assistant imports so it is unit-testable on its own.

The model deliberately mirrors the Danfoss Ally app one-to-one, so that a
program built here can be pushed to Danfoss's cloud without translation and
never expresses anything the app or the thermostat would not understand:

- A day is a list of "at home" windows on a 30-minute grid (48 slots), each
  window at least one slot long, no overlaps. Every minute outside a window
  is "leaving home". There are no other per-slot modes.
- Holiday comes in the app's two forms only. "Away" is a datetime range in
  which the thermostat sits in `holiday` at the holiday setpoint (the app asks
  for that temperature). "At home" is a date range during which the
  thermostat sits in `holiday_sat` and its active setpoint follows Saturday's
  windows (at-home setpoint inside, away setpoint outside) - exactly what the
  Danfoss cloud was observed doing on 2026-09-10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

MODE_AT_HOME = "at_home"
MODE_LEAVING_HOME = "leaving_home"
MODE_HOLIDAY = "holiday"
MODE_HOLIDAY_SAT = "holiday_sat"

SETPOINT_AT_HOME = "at_home_setting"
SETPOINT_LEAVING_HOME = "leaving_home_setting"
SETPOINT_HOLIDAY = "holiday_setting"

DAYS = 7           # Mon=0 .. Sun=6, as in datetime.weekday()
SATURDAY = 5
SLOT_MINUTES = 30
DAY_MINUTES = 24 * 60

HOLIDAY_AWAY = "away"
HOLIDAY_AT_HOME = "at_home"


@dataclass(frozen=True)
class Window:
    """An "at home" window [start, end) in minutes since midnight, on the
    30-minute grid."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if not (0 <= self.start < self.end <= DAY_MINUTES):
            raise ValueError(f"bad window {self.start}..{self.end}")
        if self.start % SLOT_MINUTES or self.end % SLOT_MINUTES:
            raise ValueError(f"window {self.start}..{self.end} is not on the 30-minute grid")


@dataclass
class WeeklyProgram:
    """Seven days of at-home windows."""

    days: list[list[Window]] = field(default_factory=lambda: [[] for _ in range(DAYS)])

    def __post_init__(self) -> None:
        if len(self.days) != DAYS:
            raise ValueError("program must have exactly 7 days")
        for idx, windows in enumerate(self.days):
            ordered = sorted(windows, key=lambda w: w.start)
            for a, b in zip(ordered, ordered[1:]):
                if a.end > b.start:
                    raise ValueError(f"overlapping windows on day {idx}: {a} / {b}")
            self.days[idx] = ordered

    def is_empty(self) -> bool:
        return all(not d for d in self.days)

    def at_home(self, weekday: int, minute: int) -> bool:
        return any(w.start <= minute < w.end for w in self.days[weekday])

    def mode_for_day(self, weekday: int, minute: int) -> str:
        return MODE_AT_HOME if self.at_home(weekday, minute) else MODE_LEAVING_HOME

    def mode_at(self, moment: datetime) -> str:
        return self.mode_for_day(moment.weekday(), moment.hour * 60 + moment.minute)

    # -- (de)serialization -------------------------------------------------

    def to_dict(self) -> dict:
        return {"days": [[{"start": w.start, "end": w.end} for w in d] for d in self.days]}

    @classmethod
    def from_dict(cls, data: dict) -> "WeeklyProgram":
        raw = data.get("days") or [[] for _ in range(DAYS)]
        return cls(days=[[Window(int(w["start"]), int(w["end"])) for w in d] for d in raw])

    # -- Danfoss wkf cloud shape ---------------------------------------------

    def to_wkf_days(self) -> list[dict]:
        """One entry per day exactly as `wkf.week.timer.create` takes it:
        a 7-bit Mon..Sun `loops` mask and the day's windows as HH:MM."""
        out: list[dict] = []
        for idx, windows in enumerate(self.days):
            loops = ["0"] * DAYS
            loops[idx] = "1"
            out.append(
                {
                    "loops": "".join(loops),
                    "periods": [{"startTime": _hhmm(w.start), "endTime": _hhmm(w.end)} for w in windows],
                }
            )
        return out


@dataclass
class Holiday:
    """The app's holiday: either `away` (datetime range, thermostat held in
    `holiday` at `temperature`) or `at_home` (whole-day date range in
    `holiday_sat`, following Saturday's windows)."""

    kind: str
    start: datetime          # for at_home the time part is ignored (00:00)
    end: datetime            # away: exclusive instant; at_home: inclusive date
    temperature: float | None = None   # away only: the holiday setpoint to apply

    def __post_init__(self) -> None:
        if self.kind not in (HOLIDAY_AWAY, HOLIDAY_AT_HOME):
            raise ValueError(f"unknown holiday kind {self.kind!r}")
        if self.kind == HOLIDAY_AWAY and not self.start < self.end:
            raise ValueError("holiday start must be before end")
        if self.kind == HOLIDAY_AT_HOME and self.start.date() > self.end.date():
            raise ValueError("holiday start date must not be after end date")
        if self.temperature is not None:
            if self.kind != HOLIDAY_AWAY:
                raise ValueError("temperature only applies to an away holiday")
            if not (4.0 <= self.temperature <= 35.0) or (self.temperature * 2) % 1:
                raise ValueError("holiday temperature must be 4.0..35.0 in 0.5 steps")

    def active_at(self, moment: datetime) -> bool:
        if self.kind == HOLIDAY_AWAY:
            return self.start <= moment < self.end
        return self.start.date() <= moment.date() <= self.end.date()

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "temperature": self.temperature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Holiday":
        return cls(
            data["kind"],
            datetime.fromisoformat(data["start"]),
            datetime.fromisoformat(data["end"]),
            data.get("temperature"),
        )


@dataclass(frozen=True)
class Desired:
    """What the thermostat should be doing right now: the mode dp and which
    setpoint the active-setpoint mirror (dp114) must follow."""

    mode: str
    setpoint_code: str


def desired_state_at(program: WeeklyProgram, moment: datetime, holiday: Holiday | None = None) -> Desired:
    """Resolve the (mode, setpoint) the schedule dictates at `moment`."""
    minute = moment.hour * 60 + moment.minute
    if holiday is not None and holiday.active_at(moment):
        if holiday.kind == HOLIDAY_AWAY:
            return Desired(MODE_HOLIDAY, SETPOINT_HOLIDAY)
        # At-home holiday: mode holiday_sat, setpoint tracks Saturday's windows.
        code = SETPOINT_AT_HOME if program.at_home(SATURDAY, minute) else SETPOINT_LEAVING_HOME
        return Desired(MODE_HOLIDAY_SAT, code)
    if program.at_home(moment.weekday(), minute):
        return Desired(MODE_AT_HOME, SETPOINT_AT_HOME)
    return Desired(MODE_LEAVING_HOME, SETPOINT_LEAVING_HOME)


def desired_mode_at(program: WeeklyProgram, moment: datetime, holiday: Holiday | None = None) -> str:
    """Mode-only view of desired_state_at (used by the schedule sensor)."""
    return desired_state_at(program, moment, holiday).mode


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def hhmm_to_min(text: str) -> int:
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)
