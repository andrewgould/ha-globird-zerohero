"""Pure unit tests for pricing.py -- no hass fixture needed."""

from datetime import UTC, datetime, time

from custom_components.globird_zerohero.const import (
    TIER_CRITICAL_PEAK,
    TIER_FREE,
    TIER_OFF_PEAK,
    TIER_PEAK,
    TIER_ZWS_BOOST,
    ZH_STATUS_EARNED,
    ZH_STATUS_MISSED,
    ZH_STATUS_PENDING,
)
from custom_components.globird_zerohero.pricing import (
    PricingEngine,
    ZeroLimitsConfig,
    ZeroWastedSolarConfig,
    zerohero_status,
    zws_remaining_kwh,
)
from custom_components.globird_zerohero.schedule import TimeWindow, TouSchedule

IMPORT_WINDOWS = [
    TimeWindow(time(0, 0), time(11, 0), 25.5),
    TimeWindow(time(11, 0), time(14, 0), 0.0),
    TimeWindow(time(14, 0), time(15, 0), 25.5),
    TimeWindow(time(15, 0), time(21, 0), 35.2),
    TimeWindow(time(21, 0), time(0, 0), 25.5),
]
EXPORT_WINDOWS = [
    TimeWindow(time(0, 0), time(10, 0), 5.0),
    TimeWindow(time(10, 0), time(15, 0), 1.0),
    TimeWindow(time(15, 0), time(21, 0), 5.0),
    TimeWindow(time(21, 0), time(0, 0), 5.0),
]


def _dt(h, m=0, d=1):
    return datetime(2026, 7, d, h, m, tzinfo=UTC)


def _engine(zws=None, zerolimits=None):
    return PricingEngine(
        import_schedule=TouSchedule(IMPORT_WINDOWS),
        export_schedule=TouSchedule(EXPORT_WINDOWS),
        zws=zws,
        zerolimits=zerolimits,
    )


def test_current_import_price_follows_schedule():
    engine = _engine()
    assert engine.current_import_price_c(_dt(12), critical_peak_active=False) == 0.0
    assert engine.current_import_price_c(_dt(17), critical_peak_active=False) == 35.2


def test_import_price_adds_zerolimits_surcharge_when_active():
    zl = ZeroLimitsConfig(export_rate_c=100.0, import_surcharge_c=5.0)
    engine = _engine(zerolimits=zl)
    assert engine.current_import_price_c(_dt(17), critical_peak_active=True) == 40.2
    assert engine.current_import_price_c(_dt(17), critical_peak_active=False) == 35.2


def test_export_price_falls_back_to_base_schedule_without_zws():
    engine = _engine()
    assert engine.current_export_price_c(_dt(17), critical_peak_active=False) == 5.0


def test_zws_boost_applies_under_cap_within_window():
    zws = ZeroWastedSolarConfig(
        rate_c=15.0, cap_kwh=10.0, window_start=time(15, 0), window_end=time(21, 0)
    )
    engine = _engine(zws=zws)
    assert engine.current_export_price_c(_dt(17), False, exported_in_window_kwh=4.0) == 15.0
    assert engine.price_tier(_dt(17), False, exported_in_window_kwh=4.0) == TIER_ZWS_BOOST


def test_zws_boost_stops_exactly_at_cap():
    zws = ZeroWastedSolarConfig(
        rate_c=15.0, cap_kwh=10.0, window_start=time(15, 0), window_end=time(21, 0)
    )
    engine = _engine(zws=zws)
    # exactly at cap -> no longer boosted
    assert engine.current_export_price_c(_dt(17), False, exported_in_window_kwh=10.0) == 5.0
    # just under cap -> still boosted
    assert engine.current_export_price_c(_dt(17), False, exported_in_window_kwh=9.999) == 15.0


def test_zws_boost_does_not_apply_outside_window():
    zws = ZeroWastedSolarConfig(
        rate_c=15.0, cap_kwh=10.0, window_start=time(15, 0), window_end=time(21, 0)
    )
    engine = _engine(zws=zws)
    assert engine.current_export_price_c(_dt(12), False, exported_in_window_kwh=1.0) == 1.0


def test_critical_peak_overrides_zws_boost():
    zws = ZeroWastedSolarConfig(
        rate_c=15.0, cap_kwh=10.0, window_start=time(15, 0), window_end=time(21, 0)
    )
    zl = ZeroLimitsConfig(export_rate_c=100.0, import_surcharge_c=5.0)
    engine = _engine(zws=zws, zerolimits=zl)
    assert engine.current_export_price_c(_dt(17), True, exported_in_window_kwh=2.0) == 100.0
    assert engine.price_tier(_dt(17), True, exported_in_window_kwh=2.0) == TIER_CRITICAL_PEAK


def test_price_tier_free_offpeak_peak():
    engine = _engine()
    assert engine.price_tier(_dt(12), False) == TIER_FREE
    assert engine.price_tier(_dt(1), False) == TIER_OFF_PEAK
    assert engine.price_tier(_dt(17), False) == TIER_PEAK


def test_next_transition_within_day():
    engine = _engine()
    # At 12:00, next boundary across import/export schedules is 14:00 (import).
    assert engine.next_transition(_dt(12)) == _dt(14)


def test_next_transition_includes_zws_window_edges():
    zws = ZeroWastedSolarConfig(
        rate_c=15.0, cap_kwh=10.0, window_start=time(15, 30), window_end=time(20, 30)
    )
    engine = _engine(zws=zws)
    # At 15:00, import schedule's next boundary is also 15:00->21:00... wait we're at 15:00 exactly,
    # so next boundary after 15:00 is 21:00 for import; zws window_start 15:30 is earlier.
    assert engine.next_transition(_dt(15, 0)) == _dt(15, 30)


def test_next_transition_falls_back_to_midnight_for_daily_reset():
    engine = _engine()
    # Just after the last schedule boundary of the day (21:00), the schedules wrap
    # back to 00:00, which coincides with the midnight daily-reset boundary anyway.
    assert engine.next_transition(_dt(22)) == datetime(2026, 7, 2, 0, 0, tzinfo=UTC)


def test_next_import_price_change_ignores_export_boundaries():
    engine = _engine()
    # 10:00 is an export-window boundary only; the import price holds 25.5
    # until 11:00. Regression: the sensor used to report the 10:00 export edge.
    assert engine.next_transition(_dt(9)) == _dt(10)
    assert engine.next_import_price_change(_dt(9)) == _dt(11)


def test_next_import_price_change_skips_midnight_when_rate_is_unchanged():
    engine = _engine()
    # 21:00-24:00 and 00:00-11:00 are both 25.5: midnight re-arms the timer
    # for the daily counter reset but isn't a price change.
    assert engine.next_transition(_dt(22)) == datetime(2026, 7, 2, 0, 0, tzinfo=UTC)
    assert engine.next_import_price_change(_dt(22)) == _dt(11, d=2)


def test_next_import_price_change_is_none_for_a_flat_import_rate():
    flat = PricingEngine(
        TouSchedule([TimeWindow(time(0, 0), time(0, 0), 30.0)]),
        TouSchedule(EXPORT_WINDOWS),
    )
    assert flat.next_import_price_change(_dt(9)) is None


def test_zerohero_status_pending_before_window():
    assert (
        zerohero_status(_dt(10), time(15, 0), time(21, 0), still_eligible=True) == ZH_STATUS_PENDING
    )


def test_zerohero_status_pending_during_window_while_eligible():
    assert (
        zerohero_status(_dt(17), time(15, 0), time(21, 0), still_eligible=True) == ZH_STATUS_PENDING
    )


def test_zerohero_status_missed_during_window_once_ineligible():
    assert (
        zerohero_status(_dt(17), time(15, 0), time(21, 0), still_eligible=False) == ZH_STATUS_MISSED
    )


def test_zerohero_status_earned_after_window_closes():
    assert (
        zerohero_status(_dt(22), time(15, 0), time(21, 0), still_eligible=True) == ZH_STATUS_EARNED
    )


def test_zerohero_status_missed_after_window_closes():
    assert (
        zerohero_status(_dt(22), time(15, 0), time(21, 0), still_eligible=False) == ZH_STATUS_MISSED
    )


def test_zws_remaining_kwh_clamps_at_zero():
    assert zws_remaining_kwh(cap_kwh=10.0, exported_in_window_kwh=12.0) == 0.0
    assert zws_remaining_kwh(cap_kwh=10.0, exported_in_window_kwh=3.0) == 7.0
    assert zws_remaining_kwh(cap_kwh=10.0, exported_in_window_kwh=-1.0) == 10.0
