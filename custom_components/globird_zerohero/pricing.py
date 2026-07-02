"""Pure pricing engine for GloBird ZEROHERO.

Framework-free (no Home Assistant imports) so the core algorithm is
unit-testable without an `hass` fixture. All monetary values here are in
cents/kWh; conversion to AUD/kWh happens once, at the sensor boundary
(see sensor.py), to avoid float-rounding drift from multiple conversions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .const import (
    TIER_CRITICAL_PEAK,
    TIER_FREE,
    TIER_OFF_PEAK,
    TIER_PEAK,
    TIER_ZWS_BOOST,
    ZH_STATUS_EARNED,
    ZH_STATUS_MISSED,
    ZH_STATUS_PENDING,
)
from .schedule import TouSchedule


@dataclass(frozen=True)
class ZeroWastedSolarConfig:
    rate_c: float
    cap_kwh: float
    window_start: time
    window_end: time


@dataclass(frozen=True)
class ZeroLimitsConfig:
    export_rate_c: float
    import_surcharge_c: float


def _window_contains(start: time, end: time, t: time) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= t < end
    return t >= start or t < end


def _next_datetime_for_boundary(now: datetime, boundary: time) -> datetime:
    """Combine a time-of-day boundary with `now` into the next datetime it occurs at."""
    candidate = datetime.combine(now.date(), boundary, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


class PricingEngine:
    def __init__(
        self,
        import_schedule: TouSchedule,
        export_schedule: TouSchedule,
        zws: ZeroWastedSolarConfig | None = None,
        zerolimits: ZeroLimitsConfig | None = None,
    ) -> None:
        self.import_schedule = import_schedule
        self.export_schedule = export_schedule
        self.zws = zws
        self.zerolimits = zerolimits

    # --- Price ---

    def current_import_price_c(self, now: datetime, critical_peak_active: bool) -> float:
        base = self.import_schedule.rate_at(now.time())
        if critical_peak_active and self.zerolimits is not None:
            base += self.zerolimits.import_surcharge_c
        return base

    def zws_active(self, now: datetime, exported_in_window_kwh: float | None) -> bool:
        if self.zws is None or exported_in_window_kwh is None:
            return False
        if not _window_contains(self.zws.window_start, self.zws.window_end, now.time()):
            return False
        return exported_in_window_kwh < self.zws.cap_kwh

    def current_export_price_c(
        self,
        now: datetime,
        critical_peak_active: bool,
        exported_in_window_kwh: float | None = None,
    ) -> float:
        # Critical peak (ZeroLimits) is assumed to override the ZeroWastedSolar
        # boost rather than stack with it -- GloBird doesn't publish how the
        # two interact when both are active. See README for this assumption.
        if critical_peak_active and self.zerolimits is not None:
            return self.zerolimits.export_rate_c
        if self.zws_active(now, exported_in_window_kwh):
            return self.zws.rate_c
        return self.export_schedule.rate_at(now.time())

    def price_tier(
        self,
        now: datetime,
        critical_peak_active: bool,
        exported_in_window_kwh: float | None = None,
    ) -> str:
        if critical_peak_active:
            return TIER_CRITICAL_PEAK
        if self.zws_active(now, exported_in_window_kwh):
            return TIER_ZWS_BOOST
        rate = self.import_schedule.rate_at(now.time())
        if rate <= 0:
            return TIER_FREE
        max_rate = max((w.rate for w in self.import_schedule.windows), default=rate)
        return TIER_PEAK if rate >= max_rate else TIER_OFF_PEAK

    # --- Scheduling ---

    def next_transition(self, now: datetime) -> datetime:
        """Earliest datetime after `now` at which any price/state input changes.

        Includes import/export schedule boundaries, the ZeroWastedSolar
        window edges, and midnight (for daily counter resets). Critical-peak
        toggles are event-driven, not schedule-driven, so they're not
        included here -- the coordinator recomputes immediately on toggle.
        """
        candidates: list[time] = [
            self.import_schedule.next_boundary_after(now.time()),
            self.export_schedule.next_boundary_after(now.time()),
        ]
        if self.zws is not None:
            candidates.append(self.zws.window_start)
            candidates.append(self.zws.window_end)

        # Always include midnight explicitly (daily counters reset then).
        midnight_next = datetime.combine(
            now.date() + timedelta(days=1), time(0, 0), tzinfo=now.tzinfo
        )
        best = midnight_next
        for boundary in candidates:
            candidate_dt = _next_datetime_for_boundary(now, boundary)
            if candidate_dt < best:
                best = candidate_dt
        return best


def zerohero_status(
    now: datetime,
    window_start: time,
    window_end: time,
    still_eligible: bool,
) -> str:
    """Pure helper for the ZeroHero credit status (pending/earned/missed).

    `still_eligible` is a running flag maintained by the coordinator: it
    starts True at window-open and latches to False the first time the
    linked import sensor exceeds the per-hour threshold during the window.
    """
    t = now.time()
    if _window_contains(window_start, window_end, t):
        return ZH_STATUS_PENDING if still_eligible else ZH_STATUS_MISSED
    # Outside the window: before it opens today is also "pending" for today.
    before_open = window_start <= window_end and t < window_start
    after_close = window_start <= window_end and t >= window_end
    if window_start > window_end:
        # Window wraps midnight; anything not "in window" here is after close.
        after_close = True
        before_open = False
    if before_open:
        return ZH_STATUS_PENDING
    if after_close:
        return ZH_STATUS_EARNED if still_eligible else ZH_STATUS_MISSED
    return ZH_STATUS_PENDING


def zws_remaining_kwh(cap_kwh: float, exported_in_window_kwh: float) -> float:
    return max(0.0, cap_kwh - max(0.0, exported_in_window_kwh))


def is_new_day(last_date: date | None, today: date) -> bool:
    return last_date is None or last_date != today
