# -*- coding: utf-8 -*-
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
"""计算 GetDateCounter 绑定在指定自然日的日期关系。"""

import re
from calendar import monthrange
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, timedelta, timezone
from typing import Literal

from lunardate import LunarDate

CHINA_STANDARD_TIME = timezone(timedelta(hours=8))

_DATE_FORMAT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_MISSING = object()
_FIRST_LUNAR_YEAR = 1900
_LAST_LUNAR_YEAR = 2099


@dataclass(frozen=True)
class DateCounterResult:
    relation: Literal["countdown", "countup", "today"]
    days: int
    target_date: date


class DateCounterError(ValueError):
    """云侧无法计算该绑定，异常信息只包含可记录的失败类别。"""


@dataclass(frozen=True)
class DateCounterIssue:
    field_name: str
    message: str
    expected: str
    repair_instruction: str


_DATE_COUNTER_ISSUES = {
    "invalid_target_date": DateCounterIssue(
        "targetDate",
        "目标日期格式错误，或在指定历法和平闰月中不存在。",
        "符合 YYYY-MM-DD 格式且在指定历法中有效的目标日期",
        "根据用户原始日期核对年月日、历法及闰月标记。日期有歧义时先向用户确认。",
    ),
    "invalid_calendar": DateCounterIssue(
        "calendar",
        "日期计数的历法取值无效。",
        "gregorian 或 lunar",
        "按用户实际指定的历法填写。用户未指定历法且能确认是公历时可省略此字段。",
    ),
    "invalid_leap_month": DateCounterIssue(
        "isLeapMonth",
        "闰月标记无效，公历单次计时不能使用闰月。",
        "仅单次农历计时使用闰月标记，传入时使用布尔值",
        "公历计时删除闰月标记。若用户指定了农历闰月，核对历法和日期后填写 true。",
    ),
    "invalid_repeat": DateCounterIssue(
        "repeat",
        "日期计数的重复周期配置无效。",
        "周期单位为 day、week、month 或 year，间隔为大于等于 1 的整数",
        "按用户指定的单位和间隔修正周期。用户只要求单次计时时可省略周期。",
    ),
    "lunar_out_of_range": DateCounterIssue(
        "targetDate",
        "目标日期超出云侧支持的农历年份范围。",
        "农历年份为 1900 至 2099",
        "核对原日期和历法。若确实超出范围，请说明限制，由用户确认是否接受等价公历日期或调整需求。",
    ),
    "no_next_occurrence": DateCounterIssue(
        "repeat",
        "按首个目标日期和重复周期，无法在支持的日期范围内找到今天或之后的目标日。",
        "同一周期在支持范围内存在今天或之后的有效节点",
        "核对首个目标日期、周期单位和间隔。若原需求无可用节点，请先向用户确认可接受的改法。",
    ),
}
_DEFAULT_DATE_COUNTER_ISSUE = DateCounterIssue(
    "",
    "日期计数入参无法计算出目标日期。",
    "有效的目标日期及可执行的周期",
    "按日期计数规则核对历法、日期和周期。无法确认时先向用户澄清。",
)


def describe_date_counter_error(reason: str) -> DateCounterIssue:
    """给出日期试算错误对应的字段和修复指令。"""
    return _DATE_COUNTER_ISSUES.get(reason, _DEFAULT_DATE_COUNTER_ISSUE)


@dataclass(frozen=True)
class _Repeat:
    unit: str
    interval: int


def _parse_repeat(value: object) -> _Repeat | None:
    repeat: _Repeat | None = None
    if value is not _MISSING:
        if not isinstance(value, Mapping):
            raise DateCounterError("invalid_repeat")
        unit = value.get("unit")
        interval = value.get("interval", 1)
        if not isinstance(unit, str) or unit not in ("day", "week", "month", "year"):
            raise DateCounterError("invalid_repeat")
        # JSON Schema 将 2.0 这样的整数值也视为 integer。
        if isinstance(interval, float) and interval.is_integer():
            interval = int(interval)
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
            raise DateCounterError("invalid_repeat")
        repeat = _Repeat(unit, interval)
    return repeat


def _next_linear_date(start: date, today: date, repeat: _Repeat) -> date:
    step = repeat.interval * (7 if repeat.unit == "week" else 1)
    elapsed = (today - start).days
    offset = ((elapsed + step - 1) // step) * step
    ordinal = start.toordinal() + offset
    if ordinal > date.max.toordinal():
        raise DateCounterError("no_next_occurrence")
    return date.fromordinal(ordinal)


def _gregorian_target(target: str, today: date, repeat: _Repeat | None) -> date:
    year, month, target_day = map(int, target.split("-"))
    monthly = repeat is not None and repeat.unit == "month"
    if not 1 <= target_day <= 31:
        raise DateCounterError("invalid_target_date")
    try:
        if monthly:
            last_day = monthrange(year, month)[1]
            start = date(year, month, min(target_day, last_day))
        else:
            start = date.fromisoformat(target)
    except ValueError as error:
        raise DateCounterError("invalid_target_date") from error

    if repeat is None or start >= today:
        return start
    if repeat.unit in ("day", "week"):
        return _next_linear_date(start, today, repeat)

    step = repeat.interval * (12 if repeat.unit == "year" else 1)
    start_month = start.year * 12 + start.month - 1
    current_month = today.year * 12 + today.month - 1
    elapsed_months = current_month - start_month
    offset = ((elapsed_months + step - 1) // step) * step
    for month_index in range(start_month + offset, (date.max.year + 1) * 12, step):
        year, month_from_zero = divmod(month_index, 12)
        month = month_from_zero + 1
        last_day = monthrange(year, month)[1]
        candidate = date(year, month, min(target_day, last_day))
        if candidate >= today:
            return candidate
    raise DateCounterError("no_next_occurrence")


def _lunar_months_from(anchor: LunarDate) -> Iterator[LunarDate]:
    for year in range(anchor.year, _LAST_LUNAR_YEAR + 1):
        leap_month = LunarDate.leap_month_for_year(year)
        first_month = anchor.month if year == anchor.year else 1
        for month in range(first_month, 13):
            yield LunarDate(year, month, anchor.day)
            if month == leap_month:
                yield LunarDate(year, month, anchor.day, True)


def _lunar_candidates(anchor: LunarDate, repeat: _Repeat) -> Iterator[LunarDate]:
    if repeat.unit == "year":
        for year in range(anchor.year, _LAST_LUNAR_YEAR + 1, repeat.interval):
            yield LunarDate(year, anchor.month, anchor.day)
            if LunarDate.leap_month_for_year(year) == anchor.month:
                yield LunarDate(year, anchor.month, anchor.day, True)
        return

    for offset, candidate in enumerate(_lunar_months_from(anchor)):
        if offset % repeat.interval == 0:
            yield candidate


def _lunar_to_solar(target: LunarDate, *, use_month_end: bool) -> date:
    try:
        return target.to_solar_date()
    except ValueError:
        if not use_month_end or target.day != 30 or not 1 <= target.month <= 12:
            raise
        # 农历小月的最后一天是廿九。
        return LunarDate(target.year, target.month, 29, target.is_leap_month).to_solar_date()


def _next_lunar_date(anchor: LunarDate, today: date, repeat: _Repeat) -> date:
    for lunar_date in _lunar_candidates(anchor, repeat):
        candidate = _lunar_to_solar(lunar_date, use_month_end=True)
        if candidate >= today:
            return candidate
    raise DateCounterError("no_next_occurrence")


def _lunar_target(target: str, is_leap: bool, today: date, repeat: _Repeat | None) -> date:
    year, month, day = map(int, target.split("-"))
    if not _FIRST_LUNAR_YEAR <= year <= _LAST_LUNAR_YEAR:
        raise DateCounterError("lunar_out_of_range")
    anchor = LunarDate(year, month, day, is_leap and repeat is None)
    monthly = repeat is not None and repeat.unit == "month"
    try:
        start = _lunar_to_solar(anchor, use_month_end=monthly)
    except ValueError as error:
        raise DateCounterError("invalid_target_date") from error
    if repeat is None or start >= today:
        return start
    if repeat.unit in ("day", "week"):
        return _next_linear_date(start, today, repeat)
    return _next_lunar_date(anchor, today, repeat)


def resolve_date_counter(arguments: Mapping[str, object], *, today: date) -> DateCounterResult:
    """返回指定参考日的计时关系、非负日差和实际目标的公历日期。"""
    target = arguments.get("targetDate")
    calendar = arguments.get("calendar", "gregorian")
    is_leap = arguments.get("isLeapMonth", False)
    if not isinstance(target, str) or _DATE_FORMAT.fullmatch(target) is None:
        raise DateCounterError("invalid_target_date")
    if calendar not in ("gregorian", "lunar"):
        raise DateCounterError("invalid_calendar")
    if not isinstance(is_leap, bool):
        raise DateCounterError("invalid_leap_month")
    repeat = _parse_repeat(arguments.get("repeat", _MISSING))
    if is_leap and calendar == "gregorian" and repeat is None:
        raise DateCounterError("invalid_leap_month")
    if calendar == "lunar":
        target_date = _lunar_target(target, is_leap, today, repeat)
    else:
        target_date = _gregorian_target(target, today, repeat)

    days = (target_date - today).days
    relation: Literal["countdown", "countup", "today"] = "today"
    if days > 0:
        relation = "countdown"
    elif days < 0:
        relation = "countup"
    return DateCounterResult(relation, abs(days), target_date)
