"""倒计时卡片评分的规范阈值与权重。

本模块是 rubric 数值的唯一来源：规范符合、可见性、版式诊断和几何采集的
阈值都在这里集中声明，规则实现只引用常量。数值来自《倒计时卡片规范》
（Pixso 源文件逐节点解析）与 rubric v6 口径；改动数值必须同步
``评分规则与扣分明细.md`` 和 ``tests/python/test_target_effect.py``。
"""

from __future__ import annotations

SIZES = ("2x2", "2x4")
DEFAULT_SIZE = "2x2"

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_PENDING = "pending"
STATUS_NA = "na"
STATUS_VALUE = {
    "pass": 1.0,
    "fail": 0.0,
    "pending": 0.5,
}

DIMENSION_ORDER = (
    ("spec", "规范符合", 60.0),
    ("visibility", "可见性", 40.0),
)
FULL_WEIGHT = 100.0
BANDS = (
    (90.0, "优秀"),
    (75.0, "良好"),
    (60.0, "及格"),
    (0.0, "不合格"),
)

# 规范符合（SPEC）。
CARD_RADIUS = 20.0
CARD_PADDING = 12.0
MASK_ALPHA_MIN = 0.55
MASK_ALPHA_MAX = 0.70
TITLE_FONT_SIZE = 16.0
TITLE_FONT_SIZE_ALT = 20.0
TITLE_WHITE_MIN = 0.95
TITLE_SUPPORT_WHITE_MIN = 0.52
TITLE_SUPPORT_WHITE_MAX = 0.68
PRIMARY_FONT_SIZE = 56.0
PRIMARY_FONT_SIZE_ALT = 38.0
PRIMARY_FONT_SIZE_MIN = 29.0
PRIMARY_WHITE_MIN = 0.88
UNIT_FONT_SIZE = 16.0
SUPPORT_FONT_SIZE = 16.0
WHITE_ALPHA_MIN = 0.52
WHITE_ALPHA_MAX = 0.68
DIGIT_LIMIT = 6
ICON_MAX_SIZE = 20.0
ICON_WHITE_MIN = 0.9

# 图案数量与几何间距：圆点=当月天数，柱体=一周天数；间距按卡片尺寸取样。
EXPECTED_BARS = {"2x2": 7, "2x4": 9}
EXPECTED_DOTS = {"2x2": 72, "2x4": 100}
BAR_PITCH = {"2x2": 19.34, "2x4": 33.25}
DOT_COL_PITCH = {"2x2": 10.7, "2x4": 11.16}
PATTERN_TOLERANCE = 0.8
BASELINE_TOLERANCE = 3.0

# 可见性（VIS）与安全区。
MIN_FONT_SIZE = 12.0
CONTRAST_MIN = 4.5
CONTRAST_MIN_LARGE = 3.0
LARGE_TEXT_SIZE = 24.0
LARGE_TEXT_BOLD_SIZE = 18.66
LARGE_TEXT_BOLD_WEIGHT = 700
SAFE_AREA_INSET = 12.0
SAFE_AREA_TOLERANCE = 2.0

# 版式诊断（LAYOUT）。
LAYOUT_TOLERANCE = 2.0
LAYOUT_OVERLAP_RATIO = 0.12
