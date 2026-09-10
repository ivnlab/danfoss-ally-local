"""Weekly schedule model and evaluator for Danfoss Icon2 (Local).

Pure logic, deliberately free of Home Assistant imports so it can be unit
tested on its own. A program is 7 days (Mon=0 .. Sun=6); each day is a list
of periods. A period pins a preset mode to a half-open minute range
[start, end) of that day. Minutes outside every period fall back to the day's
default mode.

This generalizes Danfoss's own app model (where a "period" just means
at_home and everything else is leaving_home): here a period carries an
explicit mode, so the same structure covers home / away / pause, and holiday
is layered on top as a date range that overrides the weekly program while it
is active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

# Preset modes as the coordinator/climate layer already knows them.
MODE_AT_HOME = "at_home"
MODE_LEAVING_HOME = "leaving_home"
MODE_PAUSE = "pause"
MODE_HOLIDAY = "holiday"
VALID_MODES = {MODE_AT_HOME, MODE_LEAVING_HOME, MODE_PAUSE, MODE_HOLIDAY}

DAYS = 7  # Mon..Sun


@dataclass(frozen=True)
class Period:
    """A [start, end) minute range within a day, pinned to a preset mode."""

    start: int  # minutes since midnight, 0..1440
    end: int    # minutes since midnight, > start, <= 1440
    mode: str

    def __post_init__(self) -> None:
        if not (0 <= self.start < self.end <= 24 * 60):
            raise ValueError(f"bad period range {self.start}..{self.end}")
        if self.mode not in VALID_MODES:
            raise ValueError(f"unknown mode {self.mode!r}")


@dataclass
class WeeklyProgram:
    """A full weekly program plus the fallback mode for uncovered minutes."""

    days: list[list[Period]] = field(default_factory=lambda: [[] for _ in range(DAYS)])
    default_mode: str = MODE_LEAVING_HOME

    def __post_init__(self) -> None:
        if len(self.days) != DAYS:
            raise ValueError("program must have exactly 7 days")
        for idx, periods in enumerate(self.days):
            self._check_day(idx, periods)

    @staticmethod
    def _check_day(idx: int, periods: list[Period]) -> None:
        ordered = sorted(periods, key=lambda p: p.start)
        for a, b in zip(ordered, ordered[1:]):
            if a.end > b.start:
                raise ValueError(f"overlapping periods on day {idx}: {a} / {b}")

    def mode_at(self, moment: datetime) -> str:
        """Return the preset mode the program dictates at this local datetime."""
        minute = moment.hour * 60 + moment.minute
        for period in self.days[moment.weekday()]:
            if period.start <= minute < period.end:
                return period.mode
        return self.default_mode

    # -- (de)serialization for HA storage + the wkf cloud mirror -----------

    def to_dict(self) -> dict:
        return {
            "default_mode": self.default_mode,
            "days": [
                [{"start": p.start, "end": p.end, "mode": p.mode} for p in day]
                for day in self.days
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WeeklyProgram":
        days = [
            [Period(p["start"], p["end"], p["mode"]) for p in day]
            for day in data.get("days", [[] for _ in range(DAYS)])
        ]
        return cls(days=days, default_mode=data.get("default_mode", MODE_LEAVING_HOME))

    # -- Danfoss wkf cloud shape (per day: loops mask + at_home windows) ---

    def to_wkf_days(self) -> list[dict]:
        """Express each day the way tuya.m.custom.wkf.week.timer.create wants:
        a 7-bit Mon..Sun loops mask and the list of at_home windows as
        HH:MM strings. Non-at_home periods are implied by their absence
        (the device treats gaps as leaving_home)."""
        out: list[dict] = []
        for idx, periods in enumerate(self.days):
            windows = [
                {"startTime": _hhmm(p.start), "endTime": _hhmm(p.end)}
                for p in sorted(periods, key=lambda p: p.start)
                if p.mode == MODE_AT_HOME
            ]
            loops = ["0"] * DAYS
            loops[idx] = "1"
            out.append({"loops": "".join(loops), "periods": windows})
        return out


@dataclass
class Holiday:
    """A holiday/vacation overlay active for a whole-day date range."""

    start: date
    end: date  # inclusive
    mode: str = MODE_HOLIDAY

    def active_on(self, day: date) -> bool:
        return self.start <= day <= self.end


def desired_mode_at(
    program: WeeklyProgram,
    moment: datetime,
    holiday: Holiday | None = None,
) -> str:
    """Top-level resolver: holiday overlay wins, else the weekly program."""
    if holiday is not None and holiday.active_on(moment.date()):
        return holiday.mode
    return program.mode_at(moment)


def _hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def hhmm_to_min(text: str) -> int:
    hh, mm = text.split(":")
    return int(hh) * 60 + int(mm)
