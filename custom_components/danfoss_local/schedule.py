"""Weekly schedule model and evaluator for Danfoss Icon2 (Local).

Pure logic, free of Home Assistant imports so it is unit-testable on its own.

The model deliberately mirrors the Danfoss Ally app one-to-one, so that a
program built here can be pushed to Danfoss's cloud (`wkf.week.timer.create`)
without translation and never expresses anything the app or the thermostat
would not understand:

- A day is a list of "at home" windows on a 30-minute grid (48 slots), each
  window at least one slot long, no overlaps. Every minute outside a window
  is "leaving home". There are no other per-slot modes.
- Holiday comes in the app's two forms only. "Away" is a datetime range in
  which the thermostat sits in `holiday`. "At home" is a date range during
  which every day runs Saturday's windows (the app requires Saturday to be
  set for this and blocks clearing it while such a holiday is planned).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

MODE_AT_HOME = "at_home"
MODE_LEAVING_HOME = "leaving_home"
MODE_HOLIDAY = "holiday"

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

    def mode_for_day(self, weekday: int, minute: int) -> str:
        for w in self.days[weekday]:
            if w.start <= minute < w.end:
                return MODE_AT_HOME
        return MODE_LEAVING_HOME

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
    `holiday`) or `at_home` (whole-day date range following Saturday's
    windows)."""

    kind: str
    start: datetime          # for at_home the time part is ignored (00:00)
    end: datetime            # away: exclusive instant; at_home: inclusive date

    def __post_init__(self) -> None:
        if self.kind not in (HOLIDAY_AWAY, HOLIDAY_AT_HOME):
            raise ValueError(f"unknown holiday kind {self.kind!r}")
        if self.kind == HOLIDAY_AWAY and not self.start < self.end:
            raise ValueError("holiday start must be before end")
        if self.kind == HOLIDAY_AT_HOME and self.start.date() > self.end.date():
            raise ValueError("holiday start date must not be after end date")

    def active_at(self, moment: datetime) -> bool:
        if self.kind == HOLIDAY_AWAY:
            return self.start <= moment < self.end
        return self.start.date() <= moment.date() <= self.end.date()

    def to_dict(self) -> dict:
        return {"kind": self.kind, "start": self.start.isoformat(), "end": self.end.isoformat()}

    @classmethod
    def from_dict(cls, data: dict) -> "Holiday":
        return cls(data["kind"], datetime.fromisoformat(data["start"]), datetime.fromisoformat(data["end"]))


def desired_mode_at(program: WeeklyProgram, moment: datetime, holiday: Holiday | None = None) -> str:
    """Resolve the mode the schedule dictates at `moment`.

    Holiday overrides the week. `away` pins `holiday`; `at_home` replays
    Saturday's windows on every day of the range (Danfoss semantics)."""
    if holiday is not None and holiday.active_at(moment):
        if holiday.kind == HOLIDAY_AWAY:
            return MODE_HOLIDAY
        return program.mode_for_day(SATURDAY, moment.hour * 60 + moment.minute)
    return program.mode_at(moment)


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def hhmm_to_min(text: str) -> int:
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)
