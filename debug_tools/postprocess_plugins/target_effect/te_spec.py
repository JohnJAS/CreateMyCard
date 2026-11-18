"""倒计时卡片规范符合性规则（countdown-card-spec-v1 / rubric v6）。

规范来源：《倒计时卡片规范》（Pixso 源文件逐节点解析，仓库外），节点树只用于
补充实测值；两者冲突时以规范正文为准。规则只读 A2UI 组件与卡面数据模型，不改产物。

rubric v2 的决策：
- 标题接受 T1–T4（16/20fp，副标题 16fp），主标题 100% 白、副标题 60% 白；
- 主值 56/38fp，单位独立 16fp、60% 白，副文本 16fp、60% 白；
- 内容类型只做内部一致性校验（C1–C5 不按场景强制）；
- 蒙层必须是 55%–70% 黑，且位于背景图之上、内容之下；
- 非 Pixso 主题（融球/渐变/纯色/黑字）不计入规范符合；
- 用户显式指定背景、配色或字号时，相关规范项豁免而不是判失败。

rubric v3 的同因去重：
- ``VIS.TEXT_CLIPPED`` 只统计横向截断，行高 leading 造成的纵向溢出不再扣分；
- 蒙层/文字颜色失败时 ``VIS.CONTRAST_LOW`` 不重复扣分；
- ``SPEC.PADDING`` 与 ``SPEC.SAFE_AREA`` 同因时只计安全区；
- 字号已由 ``SPEC.*_FONT`` 扣分时不再计入 ``VIS.FONT_TOO_SMALL``；
- 超出画布的文本只由 ``VIS.TEXT_OVERFLOW`` 计分，不再计入安全区；
- 标题省略号缺失造成的横向截断只由 ``SPEC.TITLE_ELLIPSIS`` 计分。

rubric v4 的总分口径：
- 目标 25 + 可见性 37.5 + 规范 37.5 固定构成 100 分，不适用维度记 0 分；
- 维度分相加即总分，不再按可用权重重新归一化。

rubric v5 的评分范围：
- 去掉目标语义计分与封顶，只保留规范 60 + 可见性 40 两项构成 100 分；
- 目标语义、版式与素材规则只做诊断，不影响分数、样本状态与结论。

rubric v6 的取样口径：
- 目标语义整体退出评测，不再推导期望天数、期望日期文案或注入期望值；
- 主值字号档位与位数上限改读卡面数据模型里的 ``days``，
  没有该绑定或取不到数值时按“无数字绑定”判定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from te_rules import (
    CARD_PADDING,
    CARD_RADIUS,
    DEFAULT_SIZE,
    DIGIT_LIMIT,
    EXPECTED_BARS,
    EXPECTED_DOTS,
    ICON_MAX_SIZE,
    ICON_WHITE_MIN,
    MASK_ALPHA_MAX,
    MASK_ALPHA_MIN,
    PRIMARY_FONT_SIZE,
    PRIMARY_FONT_SIZE_ALT,
    PRIMARY_FONT_SIZE_MIN,
    PRIMARY_WHITE_MIN,
    STATUS_FAIL,
    STATUS_NA,
    STATUS_PASS,
    SUPPORT_FONT_SIZE,
    TITLE_FONT_SIZE,
    TITLE_FONT_SIZE_ALT,
    TITLE_SUPPORT_WHITE_MAX,
    TITLE_SUPPORT_WHITE_MIN,
    TITLE_WHITE_MIN,
    UNIT_FONT_SIZE,
    WHITE_ALPHA_MAX,
    WHITE_ALPHA_MIN,
)

PROFILE_ID = "countdown-card-spec-v1"
RUBRIC_VERSION = 6
UNIT_WORDS = ("天", "小时", "分钟", "秒", "个月")

BACKGROUND_TERMS = ("背景", "底色", "蒙层", "纯色", "渐变", "透明")
COLOR_TERMS = (
    "红色",
    "蓝色",
    "绿色",
    "黑色",
    "白色",
    "紫色",
    "橙色",
    "黄色",
    "粉色",
    "金色",
    "灰色",
    "深色",
    "浅色",
    "配色",
    "颜色",
)
FONT_TERMS = ("字号", "字体大小", "大字", "小字", "加粗", "字重")
PREFERENCE_RULES: dict[str, set[str]] = {
    "背景": {
        "SPEC.BG_FULL_BLEED",
        "SPEC.BG_SINGLE",
        "SPEC.BG_FIT",
        "SPEC.MASK",
    },
    "配色": {
        "SPEC.TITLE_COLOR",
        "SPEC.PRIMARY_COLOR",
        "SPEC.UNIT_COLOR",
        "SPEC.SUPPORT_COLOR",
    },
    "字号": {
        "SPEC.TITLE_FONT",
        "SPEC.PRIMARY_FONT",
        "SPEC.UNIT_FONT",
        "SPEC.SUPPORT_FONT",
    },
}


@dataclass(frozen=True)
class RuleResult:
    """单条规则的判定。evidence 只保留可复核的字段。"""

    rule: str
    status: str
    expected: str
    actual: str
    severity: str = "major"
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "status": self.status,
            "expected": self.expected,
            "actual": self.actual,
            "severity": self.severity,
            "evidence": self.evidence,
        }


def evaluate_spec(
    components: dict[str, Any],
    data: dict[str, Any],
    *,
    size: str = DEFAULT_SIZE,
    theme: dict[str, Any] | None = None,
    user_query: str = "",
) -> list[RuleResult]:
    """按规范审计单个样本。返回值顺序固定，便于报告对齐。

    数字位数与主值字号档位只读卡面数据模型里的 ``days``（批跑占位值即
    渲染到卡面的数字），不推导期望天数。
    ``theme`` 由调用方从主题登记表推导；明确不属于图+蒙层路线时，
    规范维度整体记为不适用，不把主题差异算成卡片失败。
    """
    theme_result = _theme_result(theme)
    if theme is not None and theme.get("eligible") is False:
        return [theme_result]
    results = [
        _rule_radius(components),
        _rule_clip(components),
        _rule_padding(components),
        _rule_background(components),
        _rule_bg_single(components),
        _rule_bg_fit(components),
        _rule_mask(components),
        _rule_title_required(components),
        _rule_title_font(components),
        _rule_title_ellipsis(components),
        _rule_title_color(components),
        _rule_primary_font(components, data),
        _rule_primary_color(components),
        _rule_unit_font(components),
        _rule_unit_color(components),
        _rule_support_font(components),
        _rule_support_color(components),
        _rule_content_type(components),
        _rule_pattern_geometry(components, size),
        _rule_digit_limit(components, data),
        _rule_icon(components),
        _rule_action_pattern(components),
    ]
    results, categories, exempted = _apply_preferences(results, user_query)
    results.insert(0, theme_result)
    results.append(_preference_result(categories, exempted))
    return results


def _theme_result(theme: dict[str, Any] | None) -> RuleResult:
    if theme is None:
        return RuleResult(
            rule="SPEC.THEME_ELIGIBLE",
            status=STATUS_PASS,
            expected="Pixso 图 + 60% 黑蒙层路线",
            actual="未提供主题信息，按图+蒙层路线评估",
            severity="minor",
        )
    theme_id = str(theme.get("id") or "")
    if theme.get("eligible") is not False:
        kind = str(theme.get("kind") or "photo")
        return RuleResult(
            rule="SPEC.THEME_ELIGIBLE",
            status=STATUS_PASS,
            expected="Pixso 图 + 60% 黑蒙层路线",
            actual=f"{theme_id or '主题'}（{kind}）属于图+蒙层路线",
            severity="minor",
            evidence={"theme": theme_id, "kind": kind},
        )
    return RuleResult(
        rule="SPEC.THEME_ELIGIBLE",
        status=STATUS_NA,
        expected="Pixso 图 + 60% 黑蒙层路线",
        actual=str(theme.get("reason") or "主题不属于图+蒙层路线，规范维度不计分"),
        severity="minor",
        evidence={"theme": theme_id, "kind": theme.get("kind")},
    )


def _preference_result(
    categories: list[str],
    exempted: list[str],
) -> RuleResult:
    if categories:
        actual = f"用户指定{'/'.join(categories)}，豁免 {len(exempted)} 条规范项"
    else:
        actual = "未发现与 Pixso 冲突的显式样式偏好"
    return RuleResult(
        rule="SPEC.USER_PREFERENCE",
        status=STATUS_PASS,
        expected="用户未显式要求与 Pixso 冲突的样式",
        actual=actual,
        severity="minor",
        evidence={"categories": categories, "rules": exempted},
    )


def _apply_preferences(
    results: list[RuleResult],
    user_query: str,
) -> tuple[list[RuleResult], list[str], list[str]]:
    categories = _preference_categories(user_query)
    if not categories:
        return results, [], []
    affected: set[str] = set()
    for category in categories:
        affected.update(PREFERENCE_RULES.get(category) or set())
    if not affected:
        return results, categories, []
    updated: list[RuleResult] = []
    exempted: list[str] = []
    for item in results:
        if item.rule not in affected or item.status == STATUS_NA:
            updated.append(item)
            continue
        exempted.append(item.rule)
        evidence = dict(item.evidence)
        evidence["preference"] = categories
        updated.append(
            RuleResult(
                rule=item.rule,
                status=STATUS_NA,
                expected=item.expected,
                actual=f"{item.actual}；用户明确要求{'/'.join(categories)}，按偏好豁免",
                severity=item.severity,
                evidence=evidence,
            )
        )
    return updated, categories, exempted


def _preference_categories(user_query: str) -> list[str]:
    text = str(user_query or "")
    if not text:
        return []
    categories: list[str] = []
    if any(term in text for term in BACKGROUND_TERMS):
        categories.append("背景")
    if any(term in text for term in COLOR_TERMS):
        categories.append("配色")
    if any(term in text for term in FONT_TERMS):
        categories.append("字号")
    return categories


def _rule_radius(components: dict[str, Any]) -> RuleResult:
    root = components.get("root") or {}
    actual = (root.get("styles") or {}).get("borderRadius")
    return RuleResult(
        rule="SPEC.RADIUS",
        status=STATUS_PASS if _as_float(actual) == CARD_RADIUS else STATUS_FAIL,
        expected=f"{CARD_RADIUS:.0f}",
        actual=str(actual),
        severity="minor",
    )


def _rule_clip(components: dict[str, Any]) -> RuleResult:
    root = components.get("root") or {}
    content = components.get("__genui_render_component__root") or {}
    root_clip = (root.get("styles") or {}).get("clip")
    content_clip = (content.get("styles") or {}).get("clip")
    passed = root_clip is True or content_clip is True
    return RuleResult(
        rule="SPEC.CLIP",
        status=STATUS_PASS if passed else STATUS_FAIL,
        expected="true",
        actual=f"root={root_clip}, content={content_clip}",
        severity="minor",
    )


def _rule_padding(components: dict[str, Any]) -> RuleResult:
    root = components.get("root") or {}
    root_padding = _as_float((root.get("styles") or {}).get("padding"))
    content = components.get("__genui_render_component__root") or {}
    content_padding = _as_float((content.get("styles") or {}).get("padding"))
    actual = CARD_PADDING if CARD_PADDING in (root_padding, content_padding) else content_padding
    return RuleResult(
        rule="SPEC.PADDING",
        status=STATUS_PASS if actual == CARD_PADDING else STATUS_FAIL,
        expected=f"{CARD_PADDING:.0f}",
        actual=str(actual),
        severity="major",
    )


def _rule_background(components: dict[str, Any]) -> RuleResult:
    images = _full_bleed_images(components)
    return RuleResult(
        rule="SPEC.BG_FULL_BLEED",
        status=STATUS_PASS if images else STATUS_FAIL,
        expected="铺满的背景图",
        actual=", ".join(component_id for component_id, _ in images) if images else "无铺满背景图",
        severity="major",
        evidence={"images": [component_id for component_id, _ in images]},
    )


def _rule_bg_single(components: dict[str, Any]) -> RuleResult:
    images = _full_bleed_images(components)
    if not images:
        return RuleResult(
            rule="SPEC.BG_SINGLE",
            status=STATUS_NA,
            expected="单张满铺背景图",
            actual="无满铺背景图",
            severity="minor",
        )
    passed = len(images) == 1
    return RuleResult(
        rule="SPEC.BG_SINGLE",
        status=STATUS_PASS if passed else STATUS_FAIL,
        expected="单张满铺背景图",
        actual=(
            images[0][0]
            if passed
            else f"{len(images)} 张满铺图：" + ", ".join(component_id for component_id, _ in images)
        ),
        severity="minor",
        evidence={"images": [component_id for component_id, _ in images]},
    )


def _rule_bg_fit(components: dict[str, Any]) -> RuleResult:
    images = _full_bleed_images(components)
    if not images:
        return RuleResult(
            rule="SPEC.BG_FIT",
            status=STATUS_NA,
            expected="fill 或 cover",
            actual="无满铺背景图",
            severity="minor",
        )
    fits: list[str] = []
    for _, component in images:
        styles = component.get("styles") or {}
        fits.append(str(styles.get("objectFit") or "fill"))
    passed = all(value in {"fill", "cover"} for value in fits)
    return RuleResult(
        rule="SPEC.BG_FIT",
        status=STATUS_PASS if passed else STATUS_NA,
        expected="fill 或 cover",
        actual=", ".join(fits),
        severity="minor",
        evidence={"objectFit": fits},
    )


def _rule_mask(components: dict[str, Any]) -> RuleResult:
    layers: list[tuple[float, str]] = []
    for component_id, component in components.items():
        styles = component.get("styles") or {}
        color = _parse_color(styles.get("backgroundColor"))
        if color is None:
            continue
        alpha, red, green, blue = color
        if (red, green, blue) != (0, 0, 0):
            continue
        opacity = _as_float(styles.get("opacity"))
        effective = alpha * (1.0 if opacity is None else opacity)
        layers.append((effective, component_id))
    if not layers:
        return RuleResult(
            rule="SPEC.MASK",
            status=STATUS_FAIL,
            expected="黑色蒙层 60%（55%–70%）",
            actual="未找到黑色蒙层",
            severity="major",
        )
    best_alpha, best_id = max(layers)
    if best_alpha < MASK_ALPHA_MIN or best_alpha > MASK_ALPHA_MAX:
        return RuleResult(
            rule="SPEC.MASK",
            status=STATUS_FAIL,
            expected="黑色蒙层 60%（55%–70%）",
            actual=f"{best_id} alpha={best_alpha:.2f}",
            severity="major",
            evidence={"component": best_id, "alpha": round(best_alpha, 4)},
        )
    order = _tree_order(components)
    mask_pos = order.get(best_id)
    images = _full_bleed_images(components)
    image_positions = [order[item] for item, _ in images if item in order]
    image_pos = min(image_positions) if image_positions else None
    content_pos = order.get("__genui_render_component__root")
    if image_pos is not None and mask_pos is not None and mask_pos <= image_pos:
        return RuleResult(
            rule="SPEC.MASK",
            status=STATUS_FAIL,
            expected="蒙层在背景图之上",
            actual=f"{best_id} 位于背景图之下",
            severity="major",
            evidence={"component": best_id, "alpha": round(best_alpha, 4)},
        )
    if content_pos is not None and mask_pos is not None and mask_pos >= content_pos:
        return RuleResult(
            rule="SPEC.MASK",
            status=STATUS_FAIL,
            expected="蒙层在内容之下",
            actual=f"{best_id} 位于内容区之上",
            severity="major",
            evidence={"component": best_id, "alpha": round(best_alpha, 4)},
        )
    return RuleResult(
        rule="SPEC.MASK",
        status=STATUS_PASS,
        expected="黑色蒙层 60%（55%–70%）",
        actual=f"{best_id} alpha={best_alpha:.2f}，位于背景图与内容之间",
        severity="major",
        evidence={"component": best_id, "alpha": round(best_alpha, 4)},
    )


def _find_title(components: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for component_id in ("title_title", "content_label"):
        component = components.get(component_id)
        if component is not None:
            return component_id, component
    for component_id, component in components.items():
        if component.get("component") != "Text":
            continue
        key = component_id.lower()
        if "title" in key and "sub" not in key:
            return component_id, component
    for component_id, component in components.items():
        if "relationText" in str(component.get("content")):
            return component_id, component
    return None


def _find_subtitle(components: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for component_id, component in components.items():
        if component.get("component") != "Text":
            continue
        key = component_id.lower()
        if "subtitle" in key or key.endswith("_sub") or "_sub_" in key:
            return component_id, component
    return None


def _rule_title_required(components: dict[str, Any]) -> RuleResult:
    found = _find_title(components)
    return RuleResult(
        rule="SPEC.TITLE_REQUIRED",
        status=STATUS_PASS if found else STATUS_FAIL,
        expected="存在标题区",
        actual=found[0] if found else "未找到标题文本",
        severity="major",
    )


def _rule_title_font(components: dict[str, Any]) -> RuleResult:
    found = _find_title(components)
    if found is None:
        return RuleResult("SPEC.TITLE_FONT", STATUS_NA, "16 或 20", "无标题", "major")
    component_id, component = found
    actual = _as_float((component.get("styles") or {}).get("fontSize"))
    sub = _find_subtitle(components)
    sub_actual = None
    if sub is not None:
        sub_actual = _as_float((sub[1].get("styles") or {}).get("fontSize"))
    main_ok = actual in {TITLE_FONT_SIZE, TITLE_FONT_SIZE_ALT}
    sub_ok = sub is None or sub_actual == TITLE_FONT_SIZE
    passed = main_ok and sub_ok
    detail = f"主 {actual}"
    if sub is not None:
        detail += f" / 副 {sub_actual}"
    return RuleResult(
        rule="SPEC.TITLE_FONT",
        status=STATUS_PASS if passed else STATUS_FAIL,
        expected="主 16 或 20，副 16",
        actual=detail,
        severity="major",
        evidence={"component": component_id, "subtitle": sub[0] if sub else None},
    )


def _rule_title_ellipsis(components: dict[str, Any]) -> RuleResult:
    found = _find_title(components)
    if found is None:
        return RuleResult("SPEC.TITLE_ELLIPSIS", STATUS_NA, "单行省略号", "无标题", "major")
    checks = [found]
    sub = _find_subtitle(components)
    if sub is not None:
        checks.append(sub)
    failed: list[str] = []
    for component_id, component in checks:
        styles = component.get("styles") or {}
        if styles.get("maxLines") != 1 or styles.get("textOverflow") != "ellipsis":
            failed.append(component_id)
    return RuleResult(
        rule="SPEC.TITLE_ELLIPSIS",
        status=STATUS_PASS if not failed else STATUS_FAIL,
        expected="maxLines=1 且 textOverflow=ellipsis",
        actual="全部单行省略" if not failed else "未设置：" + ", ".join(failed),
        severity="major",
        evidence={"components": [component_id for component_id, _ in checks]},
    )


def _rule_title_color(components: dict[str, Any]) -> RuleResult:
    found = _find_title(components)
    if found is None:
        return RuleResult("SPEC.TITLE_COLOR", STATUS_NA, "白色 100%", "无标题", "minor")
    component_id, component = found
    main_color = _parse_color((component.get("styles") or {}).get("fontColor"))
    main_ok = _is_white(main_color, minimum=TITLE_WHITE_MIN)
    sub = _find_subtitle(components)
    sub_ok = True
    sub_alpha = None
    if sub is not None:
        sub_color = _parse_color((sub[1].get("styles") or {}).get("fontColor"))
        sub_alpha = None if sub_color is None else sub_color[0]
        sub_ok = _is_white(
            sub_color,
            minimum=TITLE_SUPPORT_WHITE_MIN,
            maximum=TITLE_SUPPORT_WHITE_MAX,
        )
    passed = main_ok and sub_ok
    actual = f"主 alpha={None if main_color is None else main_color[0]}"
    if sub is not None:
        actual += f" / 副 alpha={sub_alpha}"
    return RuleResult(
        rule="SPEC.TITLE_COLOR",
        status=STATUS_PASS if passed else STATUS_FAIL,
        expected="主 100% 白，副 60% 白",
        actual=actual,
        severity="minor",
        evidence={"component": component_id, "subtitle": sub[0] if sub else None},
    )


def _find_days(components: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for component_id, component in components.items():
        if component.get("component") != "Text":
            continue
        if "/data/dateCounter/days" in str(component.get("content")):
            return component_id, component
    return None


def _days_value(data: dict[str, Any]) -> int | None:
    """取卡面数据模型里的 ``/data/dateCounter/days``；取不到或不是整数时返回 None。"""
    node: Any = data
    for part in ("data", "dateCounter", "days"):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    if isinstance(node, int) and not isinstance(node, bool):
        return node
    return None


def _rule_primary_font(components: dict[str, Any], data: dict[str, Any]) -> RuleResult:
    found = _find_days(components)
    if found is None:
        if _has_pattern(components):
            return RuleResult("SPEC.PRIMARY_FONT", STATUS_NA, "56/38", "图案类", "major")
        return RuleResult("SPEC.PRIMARY_FONT", STATUS_FAIL, "56/38", "无数字绑定", "major")
    component_id, component = found
    actual = _as_float((component.get("styles") or {}).get("fontSize"))
    days = _days_value(data)
    digits = None if days is None else len(str(abs(days)))
    if digits is not None and digits >= 3:
        passed = actual is not None and PRIMARY_FONT_SIZE_MIN <= actual <= PRIMARY_FONT_SIZE
        expected = f"长数字 {PRIMARY_FONT_SIZE_MIN:.0f}–{PRIMARY_FONT_SIZE:.0f}"
    else:
        passed = actual in {PRIMARY_FONT_SIZE, PRIMARY_FONT_SIZE_ALT}
        expected = f"{PRIMARY_FONT_SIZE:.0f} 或 {PRIMARY_FONT_SIZE_ALT:.0f}"
    return RuleResult(
        rule="SPEC.PRIMARY_FONT",
        status=STATUS_PASS if passed else STATUS_FAIL,
        expected=expected,
        actual=str(actual),
        severity="major",
        evidence={"component": component_id, "days": days, "digits": digits},
    )


def _rule_primary_color(components: dict[str, Any]) -> RuleResult:
    found = _find_days(components)
    if found is None:
        return RuleResult("SPEC.PRIMARY_COLOR", STATUS_NA, "白色 100%/90%", "无数字绑定", "minor")
    component_id, component = found
    color = _parse_color((component.get("styles") or {}).get("fontColor"))
    alpha = None if color is None else color[0]
    passed = _is_white(color, minimum=PRIMARY_WHITE_MIN)
    return RuleResult(
        rule="SPEC.PRIMARY_COLOR",
        status=STATUS_PASS if passed else STATUS_FAIL,
        expected="白色 100%/90%",
        actual=f"alpha={alpha}",
        severity="minor",
        evidence={"component": component_id},
    )


def _unit_nodes(components: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    units: list[tuple[str, dict[str, Any]]] = []
    for component_id, component in components.items():
        if component.get("component") != "Text":
            continue
        text = str(component.get("content") or "").strip()
        if text in UNIT_WORDS:
            units.append((component_id, component))
    return units


def _merged_unit(components: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    days = _find_days(components)
    if days is None:
        return None
    text = str(days[1].get("content") or "")
    if any(word in text for word in UNIT_WORDS):
        return days
    return None


def _rule_unit_font(components: dict[str, Any]) -> RuleResult:
    units = _unit_nodes(components)
    merged = _merged_unit(components)
    if merged is not None and units:
        return RuleResult(
            rule="SPEC.UNIT_FONT",
            status=STATUS_FAIL,
            expected="单位独立 16fp",
            actual="单位重复：既有合并单位，又有独立单位",
            severity="major",
            evidence={
                "merged": merged[0],
                "units": [component_id for component_id, _ in units],
            },
        )
    if merged is not None:
        return RuleResult(
            rule="SPEC.UNIT_FONT",
            status=STATUS_FAIL,
            expected="单位独立 16fp",
            actual="单位与数字同一文本节点",
            severity="major",
            evidence={"component": merged[0]},
        )
    if not units:
        if _has_pattern(components):
            return RuleResult("SPEC.UNIT_FONT", STATUS_NA, "16", "图案类", "major")
        return RuleResult("SPEC.UNIT_FONT", STATUS_FAIL, "16", "未找到单位", "major")
    sizes: list[str] = []
    passed = True
    for component_id, component in units:
        actual = _as_float((component.get("styles") or {}).get("fontSize"))
        sizes.append(f"{component_id}={actual}")
        if actual != UNIT_FONT_SIZE:
            passed = False
    return RuleResult(
        rule="SPEC.UNIT_FONT",
        status=STATUS_PASS if passed else STATUS_FAIL,
        expected="16",
        actual=", ".join(sizes),
        severity="major",
        evidence={"components": [component_id for component_id, _ in units]},
    )


def _rule_unit_color(components: dict[str, Any]) -> RuleResult:
    units = _unit_nodes(components)
    if not units:
        return RuleResult("SPEC.UNIT_COLOR", STATUS_NA, "白色 60%", "无独立单位", "minor")
    failures: list[str] = []
    for component_id, component in units:
        color = _parse_color((component.get("styles") or {}).get("fontColor"))
        if not _is_white(color, minimum=WHITE_ALPHA_MIN, maximum=WHITE_ALPHA_MAX):
            alpha = None if color is None else color[0]
            failures.append(f"{component_id} alpha={alpha}")
    return RuleResult(
        rule="SPEC.UNIT_COLOR",
        status=STATUS_PASS if not failures else STATUS_FAIL,
        expected="白色 60%",
        actual="全部 60% 白" if not failures else "；".join(failures),
        severity="minor",
        evidence={"components": [component_id for component_id, _ in units]},
    )


def _find_support(components: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for component_id, component in components.items():
        if component.get("component") != "Text":
            continue
        if "targetDateText" in str(component.get("content")):
            return component_id, component
    return None


def _support_nodes(components: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    nodes: list[tuple[str, dict[str, Any]]] = []
    value = _find_support(components)
    if value is not None:
        nodes.append(value)
    for component_id, component in components.items():
        if component.get("component") != "Text":
            continue
        key = component_id.lower()
        if "support" in key and "label" in key:
            nodes.append((component_id, component))
    return nodes


def _rule_support_font(components: dict[str, Any]) -> RuleResult:
    if _find_support(components) is None:
        return RuleResult("SPEC.SUPPORT_FONT", STATUS_NA, "16", "未发现副文本", "major")
    nodes = _support_nodes(components)
    failures: list[str] = []
    sizes: list[str] = []
    for component_id, component in nodes:
        actual = _as_float((component.get("styles") or {}).get("fontSize"))
        sizes.append(f"{component_id}={actual}")
        if actual != SUPPORT_FONT_SIZE:
            failures.append(component_id)
    return RuleResult(
        rule="SPEC.SUPPORT_FONT",
        status=STATUS_PASS if not failures else STATUS_FAIL,
        expected="16",
        actual=", ".join(sizes),
        severity="major",
        evidence={"failed": failures},
    )


def _rule_support_color(components: dict[str, Any]) -> RuleResult:
    if _find_support(components) is None:
        return RuleResult("SPEC.SUPPORT_COLOR", STATUS_NA, "白色 60%", "未发现副文本", "minor")
    nodes = _support_nodes(components)
    failures: list[str] = []
    for component_id, component in nodes:
        color = _parse_color((component.get("styles") or {}).get("fontColor"))
        if not _is_white(color, minimum=WHITE_ALPHA_MIN, maximum=WHITE_ALPHA_MAX):
            alpha = None if color is None else color[0]
            failures.append(f"{component_id} alpha={alpha}")
    return RuleResult(
        rule="SPEC.SUPPORT_COLOR",
        status=STATUS_PASS if not failures else STATUS_FAIL,
        expected="白色 60%",
        actual="全部 60% 白" if not failures else "；".join(failures),
        severity="minor",
        evidence={"failed": failures},
    )


def _rule_content_type(components: dict[str, Any]) -> RuleResult:
    has_pattern = _has_pattern(components)
    days = _find_days(components)
    if has_pattern and days is not None:
        return RuleResult(
            rule="SPEC.CONTENT_TYPE",
            status=STATUS_FAIL,
            expected="C1–C5 之一，数字与图案不并存",
            actual="数字与图案同时出现",
            severity="minor",
            evidence={"text": days[0]},
        )
    if has_pattern:
        kind = "C4 柱体" if _has_bars(components) else "C5 圆球"
        return RuleResult(
            rule="SPEC.CONTENT_TYPE",
            status=STATUS_PASS,
            expected="C1–C5 之一",
            actual=kind,
            severity="minor",
        )
    if days is not None:
        font = _as_float((days[1].get("styles") or {}).get("fontSize"))
        kind = "C1 大数字" if font is not None and font >= 48.0 else "C3 小数字"
        return RuleResult(
            rule="SPEC.CONTENT_TYPE",
            status=STATUS_PASS,
            expected="C1–C5 之一",
            actual=kind,
            severity="minor",
        )
    texts = [
        component_id
        for component_id, component in components.items()
        if component.get("component") == "Text"
    ]
    if texts:
        return RuleResult(
            rule="SPEC.CONTENT_TYPE",
            status=STATUS_PASS,
            expected="C1–C5 之一",
            actual="C2 辅助文本",
            severity="minor",
        )
    return RuleResult(
        rule="SPEC.CONTENT_TYPE",
        status=STATUS_NA,
        expected="C1–C5 之一",
        actual="无正文内容",
        severity="minor",
    )


def _has_bars(components: dict[str, Any]) -> bool:
    for component in components.values():
        styles = component.get("styles") or {}
        if _as_float(styles.get("width")) == 10.0 and _as_float(styles.get("height")) == 60.0:
            return True
    return False


def _has_pattern(components: dict[str, Any]) -> bool:
    for component in components.values():
        styles = component.get("styles") or {}
        width = _as_float(styles.get("width"))
        height = _as_float(styles.get("height"))
        if width == 8.0 and height == 8.0:
            return True
        if width == 10.0 and height == 60.0:
            return True
    return False


def _rule_pattern_geometry(components: dict[str, Any], size: str) -> RuleResult:
    """图案数量暂不判定，只记录实际数量与模板容量。

    规范里的 7/9 根柱体、72/100 个圆球是模板容量；圆点实际代表当月天数、
    柱体代表一周天数，数量应由目标日期推导。在拿到能表达点亮状态的图案 DSL
    之前，不按模板数量扣分。
    """
    if not _has_pattern(components):
        return RuleResult("SPEC.PATTERN_GEOMETRY", STATUS_NA, "图案几何", "非图案类", "major")
    bars = 0
    dots = 0
    for component in components.values():
        styles = component.get("styles") or {}
        if _as_float(styles.get("width")) == 10.0 and _as_float(styles.get("height")) == 60.0:
            bars += 1
        if _as_float(styles.get("width")) == 8.0 and _as_float(styles.get("height")) == 8.0:
            dots += 1
    template_bars = EXPECTED_BARS.get(size, EXPECTED_BARS[DEFAULT_SIZE])
    template_dots = EXPECTED_DOTS.get(size, EXPECTED_DOTS[DEFAULT_SIZE])
    return RuleResult(
        rule="SPEC.PATTERN_GEOMETRY",
        status=STATUS_NA,
        expected=f"数量暂不判定（模板容量 {template_bars} 根 / {template_dots} 个）",
        actual=f"{bars} 根柱体 / {dots} 个圆球",
        severity="major",
        evidence={
            "bars": bars,
            "dots": dots,
            "size": size,
            "templateBars": template_bars,
            "templateDots": template_dots,
            "deferred": True,
        },
    )


def _rule_digit_limit(components: dict[str, Any], data: dict[str, Any]) -> RuleResult:
    days = _days_value(data)
    if days is None:
        return RuleResult(
            "SPEC.DIGIT_LIMIT", STATUS_NA, "最多 6 位", "卡面数据模型无 days", "major"
        )
    digits = len(str(abs(days)))
    passed = digits <= DIGIT_LIMIT
    return RuleResult(
        rule="SPEC.DIGIT_LIMIT",
        status=STATUS_PASS if passed else STATUS_FAIL,
        expected="最多 6 位",
        actual=f"{digits} 位",
        severity="major",
        evidence={"days": days, "hasPrimary": _find_days(components) is not None},
    )


def _rule_icon(components: dict[str, Any]) -> RuleResult:
    icons: list[tuple[str, dict[str, Any]]] = []
    for component_id, component in components.items():
        if component.get("component") != "Image":
            continue
        styles = component.get("styles") or {}
        width = _as_float(styles.get("width"))
        height = _as_float(styles.get("height"))
        if component_id == "title_icon":
            icons.append((component_id, component))
            continue
        if styles.get("width") == "matchParent" and styles.get("height") == "matchParent":
            continue
        if width is not None and height is not None and (width >= 100 or height >= 100):
            continue
        icons.append((component_id, component))
    if not icons:
        return RuleResult(
            rule="SPEC.ICON",
            status=STATUS_PASS,
            expected="图标不超过 20×20，且为白色",
            actual="无图标",
            severity="minor",
        )
    bad: list[str] = []
    for component_id, component in icons:
        styles = component.get("styles") or {}
        width = _as_float(styles.get("width"))
        height = _as_float(styles.get("height"))
        if width is None or height is None or width > ICON_MAX_SIZE or height > ICON_MAX_SIZE:
            bad.append(f"{component_id}={width}×{height}")
            continue
        color = _parse_color(styles.get("fillColor"))
        if color is not None and not _is_white(color, minimum=ICON_WHITE_MIN):
            bad.append(f"{component_id} 非白色")
    return RuleResult(
        rule="SPEC.ICON",
        status=STATUS_PASS if not bad else STATUS_NA,
        expected="图标不超过 20×20，且为白色",
        actual=(
            f"{len(icons)} 个图标符合"
            if not bad
            else "仅诊断：" + "；".join(bad)
        ),
        severity="minor",
        evidence={"icons": [component_id for component_id, _ in icons], "bad": bad},
    )


def _rule_action_pattern(components: dict[str, Any]) -> RuleResult:
    buttons: list[str] = []
    for component_id, component in components.items():
        kind = str(component.get("component") or "")
        key = component_id.lower()
        text = str(component.get("content") or "").lower()
        if kind == "Button" or "button" in key or "button" in text:
            buttons.append(component_id)
    if buttons:
        return RuleResult(
            rule="SPEC.ACTION_PATTERN",
            status=STATUS_FAIL,
            expected="整卡点击，不放独立按钮",
            actual="存在独立按钮：" + ", ".join(buttons),
            severity="minor",
            evidence={"buttons": buttons},
        )
    return RuleResult(
        rule="SPEC.ACTION_PATTERN",
        status=STATUS_PASS,
        expected="整卡点击，不放独立按钮",
        actual="未发现独立按钮",
        severity="minor",
    )


def _full_bleed_images(components: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    images: list[tuple[str, dict[str, Any]]] = []
    for component_id, component in components.items():
        if component.get("component") != "Image":
            continue
        if component_id == "title_icon":
            continue
        styles = component.get("styles") or {}
        if styles.get("width") == "matchParent" and styles.get("height") == "matchParent":
            images.append((component_id, component))
    return images


def _tree_order(components: dict[str, Any]) -> dict[str, int]:
    order: dict[str, int] = {}
    root = components.get("root")
    if not isinstance(root, dict):
        return order
    counter = 0
    stack = [str(root.get("id") or "root")]
    while stack:
        component_id = stack.pop()
        if component_id in order:
            continue
        order[component_id] = counter
        counter += 1
        component = components.get(component_id) or {}
        children = component.get("children") or []
        for child in reversed(children):
            stack.append(str(child))
    for component_id in components:
        if component_id not in order:
            order[component_id] = counter
            counter += 1
    return order


def _parse_color(value: Any) -> tuple[float, int, int, int] | None:
    if not isinstance(value, str) or not value.startswith("#"):
        return None
    text = value[1:]
    try:
        if len(text) == 8:
            alpha = int(text[0:2], 16) / 255.0
            return alpha, int(text[2:4], 16), int(text[4:6], 16), int(text[6:8], 16)
        if len(text) == 6:
            return 1.0, int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return None
    return None


def _is_white(
    color: tuple[float, int, int, int] | None,
    *,
    minimum: float,
    maximum: float | None = None,
) -> bool:
    if color is None:
        return False
    alpha, red, green, blue = color
    if (red, green, blue) != (255, 255, 255):
        return False
    if alpha < minimum:
        return False
    if maximum is not None and alpha > maximum:
        return False
    return True


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
