# -*- coding: utf-8 -*-
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
from datetime import date

import pytest

from core.date_counter import DateCounterError, DateCounterResult, resolve_date_counter


@pytest.mark.parametrize(
    ("calendar", "target"),
    [("gregorian", "2026-02-17"), ("lunar", "2026-01-01")],
)
@pytest.mark.parametrize(
    ("today", "relation", "days"),
    [
        (date(2026, 2, 16), "countdown", 1),
        (date(2026, 2, 17), "today", 0),
        (date(2026, 2, 18), "countup", 1),
    ],
)
def test_single_date_uses_natural_day_difference(calendar, target, today, relation, days):
    arguments = {"targetDate": target, "calendar": calendar}
    assert resolve_date_counter(arguments, today=today) == DateCounterResult(
        relation, days, date(2026, 2, 17)
    )


@pytest.mark.parametrize(
    ("target", "leap", "expected"),
    [
        ("1900-01-01", False, date(1900, 1, 31)),
        ("1901-01-01", False, date(1901, 2, 19)),
        ("2025-06-01", False, date(2025, 6, 25)),
        ("2025-06-01", True, date(2025, 7, 25)),
        ("2099-01-01", False, date(2099, 1, 21)),
    ],
)
def test_lunar_conversion_resolves_leap_month_and_supported_years(target, leap, expected):
    arguments = {"targetDate": target, "calendar": "lunar", "isLeapMonth": leap}
    assert resolve_date_counter(arguments, today=expected) == DateCounterResult(
        "today", 0, expected
    )


@pytest.mark.parametrize(
    ("target", "today", "repeat", "expected"),
    [
        ("2027-01-01", "2026-12-31", {"unit": "day"}, "2027-01-01"),
        ("2026-12-30", "2027-01-03", {"unit": "day", "interval": 2.0}, "2027-01-03"),
        ("2026-12-30", "2027-01-04", {"unit": "week", "interval": 2}, "2027-01-13"),
        ("2026-01-31", "2026-02-01", {"unit": "month"}, "2026-02-28"),
        ("2028-01-31", "2028-02-29", {"unit": "month"}, "2028-02-29"),
        ("2026-01-31", "2026-04-01", {"unit": "month", "interval": 3}, "2026-04-30"),
        ("2026-02-31", "2026-02-01", {"unit": "month"}, "2026-02-28"),
        ("2026-02-31", "2026-03-01", {"unit": "month"}, "2026-03-31"),
        ("2026-01-31", "2026-09-01", {"unit": "month", "interval": 3}, "2026-10-31"),
        ("2024-02-29", "2025-02-28", {"unit": "year"}, "2025-02-28"),
        ("2024-02-29", "2027-03-01", {"unit": "year"}, "2028-02-29"),
        ("2024-02-29", "2028-03-01", {"unit": "year", "interval": 3}, "2030-02-28"),
    ],
)
def test_gregorian_recurrence_keeps_the_original_anchor(target, today, repeat, expected):
    reference_date = date.fromisoformat(today)
    expected_date = date.fromisoformat(expected)
    result = resolve_date_counter(
        {"targetDate": target, "repeat": repeat},
        today=reference_date,
    )
    difference = (expected_date - reference_date).days
    relation = "countdown" if difference else "today"
    assert result == DateCounterResult(relation, difference, expected_date)


@pytest.mark.parametrize(
    ("target", "leap", "today", "unit", "interval", "expected"),
    [
        ("2025-06-01", False, "2025-06-26", "month", 1, "2025-07-25"),
        ("2025-06-01", False, "2025-06-26", "month", 2, "2025-08-23"),
        ("2025-06-01", False, "2025-08-24", "month", 2, "2025-10-21"),
        ("2025-07-30", False, "2025-09-22", "month", 1, "2025-10-20"),
        ("2025-08-30", False, "2025-09-22", "month", 1, "2025-10-20"),
        ("2025-08-30", False, "2025-10-21", "month", 1, "2025-11-19"),
        ("2025-06-30", False, "2025-07-25", "month", 1, "2025-08-22"),
        ("2025-06-01", True, "2025-07-26", "month", 1, "2025-08-23"),
        ("2025-06-01", True, "2025-07-26", "month", 2, "2025-08-23"),
        ("2025-06-01", True, "2025-07-26", "year", 1, "2026-07-14"),
        ("2025-06-01", False, "2025-06-26", "year", 1, "2025-07-25"),
        ("2025-06-01", False, "2025-07-26", "year", 2, "2027-07-04"),
        ("2025-06-30", False, "2025-07-25", "year", 1, "2025-08-22"),
        ("2025-07-30", False, "2026-08-13", "year", 1, "2026-09-10"),
        ("2025-06-01", False, "2025-06-26", "day", 30, "2025-07-25"),
        ("2025-06-01", True, "2025-07-26", "week", 2, "2025-08-06"),
    ],
)
def test_lunar_recurrence_uses_lunar_calendar(target, leap, today, unit, interval, expected):
    reference_date = date.fromisoformat(today)
    expected_date = date.fromisoformat(expected)
    arguments = {
        "targetDate": target,
        "calendar": "lunar",
        "isLeapMonth": leap,
        "repeat": {"unit": unit, "interval": interval},
    }
    assert resolve_date_counter(arguments, today=reference_date) == DateCounterResult(
        "countdown", (expected_date - reference_date).days, expected_date
    )


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        ({}, "invalid_target_date"),
        ({"targetDate": "20260217"}, "invalid_target_date"),
        ({"targetDate": "2026-02-29"}, "invalid_target_date"),
        ({"targetDate": "2026-01-01", "calendar": "unknown"}, "invalid_calendar"),
        ({"targetDate": "2026-01-01", "isLeapMonth": True}, "invalid_leap_month"),
        (
            {"targetDate": "2026-06-01", "calendar": "lunar", "isLeapMonth": True},
            "invalid_target_date",
        ),
        (
            {"targetDate": "2025-06-30", "calendar": "lunar", "isLeapMonth": True},
            "invalid_target_date",
        ),
        ({"targetDate": "2026-13-01", "calendar": "lunar"}, "invalid_target_date"),
        ({"targetDate": "1899-12-01", "calendar": "lunar"}, "lunar_out_of_range"),
        ({"targetDate": "2100-01-01", "calendar": "lunar"}, "lunar_out_of_range"),
        (
            {"targetDate": "2026-01-01", "repeat": {"unit": "day", "interval": True}},
            "invalid_repeat",
        ),
        ({"targetDate": "2026-01-01", "repeat": None}, "invalid_repeat"),
        (
            {"targetDate": "2026-01-01", "repeat": {"unit": "day", "interval": 10**30}},
            "no_next_occurrence",
        ),
    ],
)
def test_unresolvable_date_reports_a_reason(arguments, reason):
    with pytest.raises(DateCounterError, match=f"^{reason}$"):
        resolve_date_counter(arguments, today=date(2026, 2, 17))


@pytest.mark.parametrize(
    ("calendar", "target"),
    [
        ("gregorian", "2026-13-01"),
        ("gregorian", "2026-02-32"),
        ("gregorian", "2026-02-00"),
        ("gregorian", "0000-02-31"),
        ("lunar", "2026-13-01"),
        ("lunar", "2026-02-31"),
        ("lunar", "2026-02-00"),
    ],
)
def test_monthly_recurrence_rejects_dates_outside_calendar_bounds(calendar, target):
    arguments = {"targetDate": target, "calendar": calendar, "repeat": {"unit": "month"}}
    with pytest.raises(DateCounterError, match="^invalid_target_date$"):
        resolve_date_counter(arguments, today=date(2026, 2, 17))


@pytest.mark.parametrize(
    ("calendar", "target"),
    [("gregorian", "2026-02-31"), ("gregorian", "2026-02-29"), ("lunar", "2025-08-30")],
)
def test_yearly_recurrence_requires_a_valid_first_date(calendar, target):
    arguments = {"targetDate": target, "calendar": calendar, "repeat": {"unit": "year"}}
    with pytest.raises(DateCounterError, match="^invalid_target_date$"):
        resolve_date_counter(arguments, today=date(2026, 2, 17))


def test_lunar_month_recurrence_stops_at_the_supported_year_boundary():
    arguments = {
        "targetDate": "2099-12-01",
        "calendar": "lunar",
        "repeat": {"unit": "month"},
    }
    with pytest.raises(DateCounterError, match="^no_next_occurrence$"):
        resolve_date_counter(arguments, today=date(2100, 3, 1))
