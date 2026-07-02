"""Pure, framework-free time-of-use schedule model.

No Home Assistant imports on purpose: this module is unit-testable with
plain pytest and has no dependency on hass/dt_util. Callers are responsible
for passing in timezone-aware `time`/`datetime` values derived from HA's
local clock (see coordinator.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

MINUTES_PER_DAY = 24 * 60


def parse_hhmm(value: str) -> time:
    """Parse an "HH:MM" string, treating "24:00" as midnight (day-end)."""
    hour_str, _, minute_str = value.strip().partition(":")
    hour, minute = int(hour_str), int(minute_str or 0)
    if hour == 24 and minute == 0:
        return time(0, 0)
    return time(hour, minute)


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


@dataclass(frozen=True)
class TimeWindow:
    """A [start, end) window of the day with an associated c/kWh rate.

    A window may wrap past midnight (end <= start), e.g. 21:00-00:00 is
    represented as start=21:00, end=00:00 and is treated as "21:00 up to
    but not including midnight". A window where start == end spans the
    full 24 hours (used for a single always-on rate).
    """

    start: time
    end: time
    rate: float
    name: str = ""

    def contains(self, t: time) -> bool:
        if self.start == self.end:
            return True
        if self.start < self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end

    def _minute_intervals(self) -> list[tuple[int, int]]:
        s, e = _minutes(self.start), _minutes(self.end)
        if s == e:
            return [(0, MINUTES_PER_DAY)]
        if s < e:
            return [(s, e)]
        return [(s, MINUTES_PER_DAY), (0, e)]


class TouSchedule:
    """An ordered set of TimeWindows that should cover the full day."""

    def __init__(self, windows: list[TimeWindow]) -> None:
        self.windows = list(windows)

    def rate_at(self, t: time) -> float:
        return self.window_at(t).rate

    def window_at(self, t: time) -> TimeWindow:
        for window in self.windows:
            if window.contains(t):
                return window
        raise LookupError(f"No schedule window covers {t.isoformat()}")

    def next_boundary_after(self, t: time) -> time:
        """Return the earliest window start/end strictly after `t`.

        Wraps to the smallest boundary overall if `t` is after every
        boundary today (i.e. the next transition is tomorrow). Callers
        combine this with a date to get a full datetime.
        """
        boundaries = sorted({w.start for w in self.windows} | {w.end for w in self.windows})
        for boundary in boundaries:
            if boundary > t:
                return boundary
        if boundaries:
            return boundaries[0]
        return t

    def validate(self) -> list[str]:
        """Return a list of error codes; empty list means the schedule is valid."""
        if not self.windows:
            return ["schedule_empty"]

        intervals: list[tuple[int, int]] = []
        for window in self.windows:
            intervals.extend(window._minute_intervals())  # noqa: SLF001
        intervals.sort()

        errors: list[str] = []
        cursor = 0
        for start, end in intervals:
            if start > cursor:
                errors.append("schedule_gap")
                break
            if start < cursor:
                errors.append("schedule_overlap")
                break
            cursor = max(cursor, end)
        else:
            if cursor < MINUTES_PER_DAY:
                errors.append("schedule_gap")

        return errors
