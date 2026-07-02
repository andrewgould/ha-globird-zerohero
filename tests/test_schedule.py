"""Pure unit tests for schedule.py -- no hass fixture needed."""

from datetime import time

import pytest

from custom_components.globird_zerohero.schedule import TimeWindow, TouSchedule, parse_hhmm


def test_parse_hhmm_handles_midnight_rollover():
    assert parse_hhmm("24:00") == time(0, 0)
    assert parse_hhmm("00:00") == time(0, 0)
    assert parse_hhmm("15:30") == time(15, 30)


def test_window_wraparound_containment():
    window = TimeWindow(start=time(22, 0), end=time(6, 0), rate=10.0)
    assert window.contains(time(23, 30))
    assert window.contains(time(3, 0))
    assert not window.contains(time(12, 0))
    assert window.contains(time(22, 0))  # inclusive start
    assert not window.contains(time(6, 0))  # exclusive end


def test_window_full_day_when_start_equals_end():
    window = TimeWindow(start=time(0, 0), end=time(0, 0), rate=20.0)
    assert window.contains(time(0, 0))
    assert window.contains(time(13, 37))
    assert window.contains(time(23, 59))


FULL_COVERAGE_WINDOWS = [
    TimeWindow(time(0, 0), time(11, 0), 25.5),
    TimeWindow(time(11, 0), time(14, 0), 0.0),
    TimeWindow(time(14, 0), time(15, 0), 25.5),
    TimeWindow(time(15, 0), time(21, 0), 35.2),
    TimeWindow(time(21, 0), time(0, 0), 25.5),
]


def test_valid_schedule_has_no_errors():
    schedule = TouSchedule(FULL_COVERAGE_WINDOWS)
    assert schedule.validate() == []


def test_schedule_with_gap_is_invalid():
    windows = [
        TimeWindow(time(0, 0), time(10, 0), 25.5),
        # gap 10:00-11:00
        TimeWindow(time(11, 0), time(0, 0), 25.5),
    ]
    assert TouSchedule(windows).validate() == ["schedule_gap"]


def test_schedule_with_overlap_is_invalid():
    windows = [
        TimeWindow(time(0, 0), time(12, 0), 25.5),
        TimeWindow(time(11, 0), time(0, 0), 25.5),
    ]
    assert TouSchedule(windows).validate() == ["schedule_overlap"]


def test_empty_schedule_is_invalid():
    assert TouSchedule([]).validate() == ["schedule_empty"]


def test_rate_at_picks_window_that_starts_at_boundary():
    schedule = TouSchedule(FULL_COVERAGE_WINDOWS)
    # 15:00:00 belongs to the window that *starts* at 15:00, not the one ending there.
    assert schedule.rate_at(time(15, 0)) == 35.2
    assert schedule.rate_at(time(14, 59, 59)) == 25.5


def test_rate_at_raises_for_uncovered_gap():
    windows = [TimeWindow(time(0, 0), time(10, 0), 25.5)]
    schedule = TouSchedule(windows)
    with pytest.raises(LookupError):
        schedule.rate_at(time(23, 0))


def test_next_boundary_after_within_day():
    schedule = TouSchedule(FULL_COVERAGE_WINDOWS)
    assert schedule.next_boundary_after(time(12, 0)) == time(14, 0)
    assert schedule.next_boundary_after(time(9, 0)) == time(11, 0)


def test_next_boundary_after_wraps_to_next_day():
    schedule = TouSchedule(FULL_COVERAGE_WINDOWS)
    # After the last boundary of the day, wrap to the earliest boundary overall.
    assert schedule.next_boundary_after(time(23, 0)) == time(0, 0)
