from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from debug_tools.batch_testing.postprocess import PostprocessManager

PLUGIN_DIR = (
    Path(__file__).resolve().parents[3]
    / "debug_tools/postprocess_plugins/target_effect"
)
SPEC = importlib.util.spec_from_file_location("target_effect_plugin_test", PLUGIN_DIR / "plugin.py")
assert SPEC is not None and SPEC.loader is not None
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)

spec_module = plugin.te_spec
dom_module = plugin.te_dom


@pytest.fixture
def work_dir() -> Any:
    with tempfile.TemporaryDirectory() as name:
        yield Path(name)


def _component(component_id: str, component: str, **rest: Any) -> dict[str, Any]:
    value: dict[str, Any] = {"id": component_id, "component": component}
    value.update(rest)
    return value


def _q001_components() -> dict[str, Any]:
    """对齐真实 Q001 的节点结构：标题/主值/单位/副文本均为 12 号字。"""
    items = [
        _component(
            "root",
            "Stack",
            children=["__post_theme_background", "content"],
            styles={
                "width": "matchParent",
                "height": "matchParent",
                "padding": 0,
                "borderRadius": 20,
                "backgroundColor": "#FF1F1F99",
            },
        ),
        _component(
            "__post_theme_background",
            "Image",
            src="https://example.com/theme.jpg",
            styles={"width": "matchParent", "height": "matchParent", "objectFit": "fill"},
        ),
        _component(
            "__genui_render_component__root",
            "Column",
            children=["title_title", "primary_value", "primary_unit", "support_item0_value"],
            styles={"width": "matchParent", "height": "matchParent", "padding": 12},
        ),
        _component(
            "title_title",
            "Text",
            content="{{ '考试 ' + ${/data/dateCounter/relationText} }}",
            styles={"fontSize": 12, "maxLines": 1, "fontColor": "#CCFFFFFF"},
        ),
        _component(
            "primary_value",
            "Text",
            content="{{ ${/data/dateCounter/days} }}",
            styles={"fontSize": 30, "fontColor": "#FFFFFFFF"},
        ),
        _component(
            "primary_unit",
            "Text",
            content="天",
            styles={"fontSize": 12, "fontColor": "#99FFFFFF"},
        ),
        _component(
            "support_item0_value",
            "Text",
            content="{{ ${/data/dateCounter/targetDateText} }}",
            styles={"fontSize": 12, "fontColor": "#FFFFFFFF"},
        ),
    ]
    return {item["id"]: item for item in items}


def _compliant_components() -> dict[str, Any]:
    items = [
        _component(
            "root",
            "Stack",
            children=["theme_base", "mask", "__genui_render_component__root"],
            styles={
                "width": "matchParent",
                "height": "matchParent",
                "padding": 0,
                "borderRadius": 20,
                "clip": True,
                "backgroundColor": "#FF1F1F99",
            },
        ),
        _component(
            "theme_base",
            "Image",
            src="https://example.com/theme.jpg",
            styles={"width": "matchParent", "height": "matchParent", "objectFit": "fill"},
        ),
        _component(
            "mask",
            "Divider",
            styles={
                "width": "matchParent",
                "height": "matchParent",
                "backgroundColor": "#99000000",
            },
        ),
        _component(
            "__genui_render_component__root",
            "Column",
            children=["title_title", "primary_value", "primary_unit", "support_item0_value"],
            styles={"width": "matchParent", "height": "matchParent", "padding": 12},
        ),
        _component(
            "title_title",
            "Text",
            content="{{ '考试 ' + ${/data/dateCounter/relationText} }}",
            styles={
                "fontSize": 16,
                "maxLines": 1,
                "textOverflow": "ellipsis",
                "fontColor": "#FFFFFFFF",
            },
        ),
        _component(
            "primary_value",
            "Text",
            content="{{ ${/data/dateCounter/days} }}",
            styles={"fontSize": 56, "fontColor": "#FFFFFFFF"},
        ),
        _component(
            "primary_unit",
            "Text",
            content="天",
            styles={"fontSize": 16, "fontColor": "#99FFFFFF"},
        ),
        _component(
            "support_item0_value",
            "Text",
            content="{{ ${/data/dateCounter/targetDateText} }}",
            styles={"fontSize": 16, "fontColor": "#99FFFFFF"},
        ),
    ]
    return {item["id"]: item for item in items}


def _genui(components: dict[str, Any], data: dict[str, Any] | None = None) -> str:
    rows = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "surface_card",
                "catalogId": "ohos.a2ui.extended.catalog.form",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "surface_card",
                "root": "root",
                "components": list(components.values()),
            },
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "surface_card",
                "path": "/",
                "value": data
                or {
                    "data": {
                        "dateCounter": {
                            "days": 3,
                            "relationText": "还剩",
                            "targetDateText": "2026/12/19",
                        }
                    }
                },
            },
        },
    ]
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"


def _node(
    node_id: str,
    text: str,
    *,
    font_size: float = 16.0,
    x: float = 12.0,
    y: float = 12.0,
    width: float = 100.0,
    height: float = 20.0,
    color: str = "rgb(255, 255, 255)",
) -> dict[str, Any]:
    return {
        "id": node_id,
        "tag": "SPAN",
        "leaf": True,
        "visible": True,
        "text": text,
        "box": {"x": x, "y": y, "width": width, "height": height},
        "style": {"fontSize": font_size, "color": color},
        "clientWidth": width,
        "clientHeight": height,
        "scrollWidth": width,
        "scrollHeight": height,
        "image": None,
    }


def _evidence(
    text: str,
    nodes: list[dict[str, Any]],
    *,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "target-dom-v1",
        "surface": {"x": 0, "y": 0, "width": 150, "height": 150},
        "visibleText": text,
        "nodes": nodes,
        "devicePixelRatio": 3,
        "webQuality": {"findings": findings or [], "coverage": []},
    }


def _rendered_evidence(days: int = 46, relation: str = "还剩") -> dict[str, Any]:
    text = f"考试 {relation} {days} 天 考试日期 2026/12/19"
    return _evidence(
        text,
        [
            _node("title_title", f"考试 {relation}", width=126, height=20),
            _node("primary_value", str(days), font_size=56, y=40, width=70, height=56),
            _node("primary_unit", "天", y=80, width=16, height=16),
            _node("support_item0_value", "2026/12/19", y=110, width=100, height=16),
        ],
    )


def _days_data(days: int | None = 46) -> dict[str, Any]:
    if days is None:
        return {}
    return {"data": {"dateCounter": {"days": days}}}


def test_spec_compliant_card_passes() -> None:
    components = _compliant_components()
    results = spec_module.evaluate_spec(components, _days_data(46), size="2x2")
    failed = [item.rule for item in results if item.status == "fail"]
    assert failed == []
    for rule in ("SPEC.RADIUS", "SPEC.PADDING", "SPEC.BG_FULL_BLEED", "SPEC.MASK"):
        assert next(item for item in results if item.rule == rule).status == "pass"


def test_spec_reports_real_q001_gaps() -> None:
    results = spec_module.evaluate_spec(_q001_components(), _days_data(46), size="2x2")
    by_rule = {item.rule: item.status for item in results}
    assert by_rule["SPEC.THEME_ELIGIBLE"] == "pass"
    assert by_rule["SPEC.RADIUS"] == "pass"
    assert by_rule["SPEC.CLIP"] == "fail"
    assert by_rule["SPEC.PADDING"] == "pass"
    assert by_rule["SPEC.BG_FULL_BLEED"] == "pass"
    assert by_rule["SPEC.BG_SINGLE"] == "pass"
    assert by_rule["SPEC.MASK"] == "fail"
    assert by_rule["SPEC.TITLE_FONT"] == "fail"
    assert by_rule["SPEC.TITLE_ELLIPSIS"] == "fail"
    assert by_rule["SPEC.TITLE_COLOR"] == "fail"
    assert by_rule["SPEC.PRIMARY_FONT"] == "fail"
    assert by_rule["SPEC.PRIMARY_COLOR"] == "pass"
    assert by_rule["SPEC.UNIT_FONT"] == "fail"
    assert by_rule["SPEC.UNIT_COLOR"] == "pass"
    assert by_rule["SPEC.SUPPORT_FONT"] == "fail"
    assert by_rule["SPEC.SUPPORT_COLOR"] == "fail"
    assert by_rule["SPEC.ACTION_PATTERN"] == "pass"
    assert by_rule["SPEC.DIGIT_LIMIT"] == "pass"
    assert by_rule["SPEC.PATTERN_GEOMETRY"] == "na"


def test_long_days_use_relaxed_primary_font() -> None:
    components = _compliant_components()
    components["primary_value"]["styles"]["fontSize"] = 44
    results = spec_module.evaluate_spec(components, _days_data(365), size="2x2")
    primary = next(item for item in results if item.rule == "SPEC.PRIMARY_FONT")
    assert primary.status == "pass"
    assert primary.expected == "长数字 29–56"


def test_short_days_require_standard_primary_font() -> None:
    components = _compliant_components()
    components["primary_value"]["styles"]["fontSize"] = 44
    results = spec_module.evaluate_spec(components, _days_data(3), size="2x2")
    primary = next(item for item in results if item.rule == "SPEC.PRIMARY_FONT")
    assert primary.status == "fail"
    assert primary.expected == "56 或 38"
    assert primary.evidence["days"] == 3
    assert primary.evidence["digits"] == 1


# ---------------------------------------------------------------- rubric v2


def _spec_status(
    components: dict[str, Any],
    *,
    size: str = "2x2",
    data: dict[str, Any] | None = None,
    theme: dict[str, Any] | None = None,
    user_query: str = "",
) -> dict[str, str]:
    results = spec_module.evaluate_spec(
        components,
        data if data is not None else _days_data(46),
        size=size,
        theme=theme,
        user_query=user_query,
    )
    return {item.rule: item.status for item in results}


def _subtitle(font_size: float = 16, color: str = "#99FFFFFF") -> dict[str, Any]:
    return _component(
        "title_subtitle",
        "Text",
        content="考试日期",
        styles={
            "fontSize": font_size,
            "maxLines": 1,
            "textOverflow": "ellipsis",
            "fontColor": color,
        },
    )


def test_spec_requires_clip_on_root_or_content() -> None:
    components = _compliant_components()
    components["root"]["styles"].pop("clip")
    assert _spec_status(components)["SPEC.CLIP"] == "fail"
    components["__genui_render_component__root"]["styles"]["clip"] = True
    assert _spec_status(components)["SPEC.CLIP"] == "pass"


def test_spec_mask_band_and_layer_order() -> None:
    components = _compliant_components()
    components["mask"]["styles"]["backgroundColor"] = "#66000000"
    assert _spec_status(components)["SPEC.MASK"] == "fail"

    components = _compliant_components()
    components["root"]["children"] = ["mask", "theme_base", "__genui_render_component__root"]
    result = next(
        item
        for item in spec_module.evaluate_spec(components, _days_data(46), size="2x2")
        if item.rule == "SPEC.MASK"
    )
    assert result.status == "fail"
    assert "背景图之下" in result.actual

    components = _compliant_components()
    components["root"]["children"] = ["theme_base", "__genui_render_component__root", "mask"]
    result = next(
        item
        for item in spec_module.evaluate_spec(components, _days_data(46), size="2x2")
        if item.rule == "SPEC.MASK"
    )
    assert result.status == "fail"
    assert "内容区之上" in result.actual


def test_title_variants_accept_20fp_and_subtitle() -> None:
    components = _compliant_components()
    components["title_title"]["styles"]["fontSize"] = 20
    components["title_subtitle"] = _subtitle()
    by_rule = _spec_status(components)
    assert by_rule["SPEC.TITLE_FONT"] == "pass"
    assert by_rule["SPEC.TITLE_COLOR"] == "pass"
    assert by_rule["SPEC.TITLE_ELLIPSIS"] == "pass"

    components["title_subtitle"]["styles"]["fontSize"] = 20
    assert _spec_status(components)["SPEC.TITLE_FONT"] == "fail"

    components = _compliant_components()
    components["title_subtitle"] = _subtitle(color="#FFFFFFFF")
    assert _spec_status(components)["SPEC.TITLE_COLOR"] == "fail"


def test_unit_rules_require_separate_text() -> None:
    merged_only = _compliant_components()
    merged_only["primary_value"]["content"] = "{{ ${/data/dateCounter/days} }} 天"
    merged_only.pop("primary_unit")
    assert _spec_status(merged_only)["SPEC.UNIT_FONT"] == "fail"

    duplicated = _compliant_components()
    duplicated["primary_value"]["content"] = "{{ ${/data/dateCounter/days} }} 天"
    assert _spec_status(duplicated)["SPEC.UNIT_FONT"] == "fail"

    missing = _compliant_components()
    missing.pop("primary_unit")
    assert _spec_status(missing)["SPEC.UNIT_FONT"] == "fail"
    assert _spec_status(missing)["SPEC.UNIT_COLOR"] == "na"


def test_support_font_and_color_cover_label_and_value() -> None:
    components = _compliant_components()
    components["support_item0_label"] = _component(
        "support_item0_label",
        "Text",
        content="考试日期",
        styles={"fontSize": 16, "fontColor": "#99FFFFFF"},
    )
    by_rule = _spec_status(components)
    assert by_rule["SPEC.SUPPORT_FONT"] == "pass"
    assert by_rule["SPEC.SUPPORT_COLOR"] == "pass"

    components["support_item0_label"]["styles"]["fontSize"] = 12
    assert _spec_status(components)["SPEC.SUPPORT_FONT"] == "fail"


def test_content_type_is_internally_consistent() -> None:
    text_only = _compliant_components()
    for key in ("primary_value", "primary_unit", "support_item0_value"):
        text_only.pop(key)
    assert _spec_status(text_only)["SPEC.CONTENT_TYPE"] == "pass"

    pattern_only = _compliant_components()
    for key in ("primary_value", "primary_unit"):
        pattern_only.pop(key)
    pattern_only["pattern_dot_0"] = _component(
        "pattern_dot_0",
        "Divider",
        styles={"width": 8, "height": 8, "backgroundColor": "#FFFFFFFF"},
    )
    results = spec_module.evaluate_spec(pattern_only, _days_data(46), size="2x2")
    content = next(item for item in results if item.rule == "SPEC.CONTENT_TYPE")
    assert content.status == "pass"
    assert content.actual == "C5 圆球"

    conflicting = _compliant_components()
    conflicting["pattern_dot_0"] = _component(
        "pattern_dot_0",
        "Divider",
        styles={"width": 8, "height": 8, "backgroundColor": "#FFFFFFFF"},
    )
    assert _spec_status(conflicting)["SPEC.CONTENT_TYPE"] == "fail"


def _pattern_result(components: dict[str, Any], *, size: str = "2x2") -> Any:
    results = spec_module.evaluate_spec(components, _days_data(46), size=size)
    return next(item for item in results if item.rule == "SPEC.PATTERN_GEOMETRY")


def test_pattern_counts_are_deferred_not_scored() -> None:
    seven_bars = _compliant_components()
    for index in range(7):
        seven_bars[f"bar_{index}"] = _component(
            f"bar_{index}",
            "Divider",
            styles={"width": 10, "height": 60, "backgroundColor": "#FFFFFFFF"},
        )
    result = _pattern_result(seven_bars)
    assert result.status == "na"
    assert result.evidence["bars"] == 7
    assert result.evidence["templateBars"] == 7
    assert result.evidence["deferred"] is True

    six_bars = dict(seven_bars)
    six_bars.pop("bar_6")
    assert _pattern_result(six_bars).status == "na"

    dots = _compliant_components()
    for index in range(72):
        dots[f"dot_{index}"] = _component(
            f"dot_{index}",
            "Divider",
            styles={"width": 8, "height": 8, "backgroundColor": "#FFFFFFFF"},
        )
    dot_result = _pattern_result(dots)
    assert dot_result.status == "na"
    assert dot_result.evidence["dots"] == 72
    assert dot_result.evidence["templateDots"] == 72

    wide_bars = _compliant_components()
    for index in range(9):
        wide_bars[f"bar_{index}"] = _component(
            f"bar_{index}",
            "Divider",
            styles={"width": 10, "height": 60, "backgroundColor": "#FFFFFFFF"},
        )
    wide_result = _pattern_result(wide_bars, size="2x4")
    assert wide_result.status == "na"
    assert wide_result.evidence["templateBars"] == 9


def test_icon_rules_are_diagnostic() -> None:
    components = _compliant_components()
    components["title_icon"] = _component(
        "title_icon",
        "Image",
        src="resources/base/media/stopwatch_fill.svg",
        styles={"width": 20, "height": 20, "fillColor": "#FFFFFFFF"},
    )
    assert _spec_status(components)["SPEC.ICON"] == "pass"

    components["title_icon"]["styles"]["width"] = 32
    assert _spec_status(components)["SPEC.ICON"] == "na"


def test_action_pattern_flags_standalone_button() -> None:
    components = _compliant_components()
    components["action_button"] = _component(
        "action_button",
        "Button",
        content="添加日程",
        styles={},
    )
    results = spec_module.evaluate_spec(components, _days_data(46), size="2x2")
    action = next(item for item in results if item.rule == "SPEC.ACTION_PATTERN")
    assert action.status == "fail"
    assert action.severity == "minor"


def test_theme_profile_marks_non_pixso_themes() -> None:
    eligible = plugin._theme_profile("photo-ux-texture-blue-diagonal-square")
    assert eligible is not None
    assert eligible["eligible"] is True

    for theme_id in (
        "fusion-ball-battery-teal",
        "gradient-blue",
        "solid-blue",
        "photo-ux-meeting-room-square",
    ):
        profile = plugin._theme_profile(theme_id)
        assert profile is not None
        assert profile["eligible"] is False
    unknown = plugin._theme_profile("no-such-theme")
    assert unknown is not None
    assert unknown["eligible"] is None


def test_ineligible_theme_skips_spec_rules() -> None:
    profile = plugin._theme_profile("fusion-ball-battery-teal")
    results = spec_module.evaluate_spec(
        _compliant_components(),
        _days_data(46),
        size="2x2",
        theme=profile,
    )
    assert [item.rule for item in results] == ["SPEC.THEME_ELIGIBLE"]
    assert results[0].status == "na"
    assert "融球" in results[0].actual


def test_user_preferences_exempt_conflicting_rules() -> None:
    background = spec_module.evaluate_spec(
        _q001_components(),
        _days_data(46),
        size="2x2",
        user_query="背景用纯色，不要蒙层",
    )
    by_rule = {item.rule: item.status for item in background}
    for rule in ("SPEC.BG_FULL_BLEED", "SPEC.BG_SINGLE", "SPEC.MASK"):
        assert by_rule[rule] == "na"
    assert by_rule["SPEC.TITLE_FONT"] == "fail"
    preference = next(item for item in background if item.rule == "SPEC.USER_PREFERENCE")
    assert preference.evidence["categories"] == ["背景"]

    colors = spec_module.evaluate_spec(
        _q001_components(),
        _days_data(46),
        size="2x2",
        user_query="数字用红色",
    )
    color_rules = {item.rule: item.status for item in colors}
    assert color_rules["SPEC.PRIMARY_COLOR"] == "na"
    assert color_rules["SPEC.SUPPORT_COLOR"] == "na"
    assert color_rules["SPEC.TITLE_COLOR"] == "na"


def _graphic_node(
    node_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "tag": "DIV",
        "leaf": True,
        "visible": True,
        "text": "",
        "box": {"x": x, "y": y, "width": width, "height": height},
        "style": {},
        "image": None,
    }


def test_pattern_pitch_is_diagnostic() -> None:
    bars = [
        _graphic_node(f"bar_{index}", 12 + index * 19.34, 78, 10, 60)
        for index in range(7)
    ]
    passed = dom_module._pattern_pitch_results(_evidence("", bars), "2x2")
    assert passed[0].rule == "SPEC.PATTERN_PITCH"
    assert passed[0].status == "pass"

    off = [
        _graphic_node(f"bar_{index}", 12 + index * 25, 78, 10, 60)
        for index in range(7)
    ]
    assert dom_module._pattern_pitch_results(_evidence("", off), "2x2")[0].status == "na"

    dots = [
        _graphic_node(f"dot_{index}", 12 + index * 10.7, 110, 8, 8)
        for index in range(12)
    ]
    assert dom_module._pattern_pitch_results(_evidence("", dots), "2x2")[0].status == "pass"


def test_unit_baseline_is_diagnostic() -> None:
    aligned = [
        _node("primary_value", "46", font_size=56, y=40, width=70, height=56),
        _node("primary_unit", "天", font_size=16, y=84, width=16, height=16),
    ]
    assert dom_module._unit_baseline_results(aligned)[0].status == "pass"

    off = [
        _node("primary_value", "46", font_size=56, y=40, width=70, height=56),
        _node("primary_unit", "天", font_size=16, y=60, width=16, height=16),
    ]
    assert dom_module._unit_baseline_results(off)[0].status == "na"


def test_theme_extraction_matches_registry_sources() -> None:
    theme_id = "photo-ux-texture-blue-diagonal-square"
    registry = plugin._theme_registry()
    remote = registry[theme_id]["background"]["remoteUrl"]
    components = _compliant_components()
    components["theme_base"]["src"] = remote
    with tempfile.TemporaryDirectory() as name:
        final_dir = Path(name)
        assert plugin._extract_theme_id(final_dir, components) == theme_id
        (final_dir / "blocks.json").write_text(
            json.dumps(
                {
                    "taskspec": {
                        "assetCandidates": [
                            {"id": theme_id, "src": "https://example.com/other.jpg"}
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        assert plugin._extract_theme_id(final_dir, {}) == theme_id


# ---------------------------------------------------------------- 同因去重


def _rule_result(
    rule: str,
    status: str,
    evidence: dict[str, Any] | None = None,
) -> Any:
    return spec_module.RuleResult(
        rule=rule,
        status=status,
        expected=rule,
        actual=rule,
        severity="major",
        evidence=evidence or {},
    )


def _clip_finding(**evidence: Any) -> dict[str, Any]:
    return {
        "rule_id": "GEOMETRY.CLIP_TEXT",
        "message": "Web 渲染中文字被裁剪或省略",
        "components": ["title_title:3"],
        "evidence": {"component": "title_title", **evidence},
    }


def test_vertical_line_box_overflow_is_not_scored_as_clipped() -> None:
    finding = _clip_finding(
        text="考试 还剩",
        box={"x": 12, "y": 16, "width": 106, "height": 12},
        textRects=[{"x": 12, "y": 16, "width": 70, "height": 17}],
        clientWidth=106,
        scrollWidth=106,
        clientHeight=12,
        scrollHeight=17,
    )
    results = dom_module._web_quality_results({"webQuality": {"findings": [finding]}})
    clipped = next(item for item in results if item.rule == "VIS.TEXT_CLIPPED")
    assert clipped.status == "pass"
    assert "纵向行框溢出" in clipped.actual
    assert clipped.evidence["ignoredCount"] == 1


def test_horizontal_truncation_still_fails_clip_rule() -> None:
    finding = _clip_finding(
        text="很久以后的考试",
        box={"x": 12, "y": 16, "width": 106, "height": 12},
        textRects=[{"x": 12, "y": 16, "width": 126, "height": 17}],
        clientWidth=106,
        scrollWidth=126,
        clientHeight=12,
        scrollHeight=17,
    )
    results = dom_module._web_quality_results({"webQuality": {"findings": [finding]}})
    clipped = next(item for item in results if item.rule == "VIS.TEXT_CLIPPED")
    assert clipped.status == "fail"


def test_safe_area_skips_text_already_scored_by_overflow() -> None:
    overflow = {
        "rule_id": "GEOMETRY.OVERFLOW_TEXT",
        "components": ["support_item0_value:4"],
        "evidence": {"component": "support_item0_value"},
    }
    evidence = _evidence(
        "天 2026/12/19",
        [
            _node("support_item0_value", "2026/12/19", x=140, width=60),
            _node("primary_unit", "天", x=140, width=60),
        ],
        findings=[overflow],
    )
    nodes = dom_module._visible_leaf_nodes(evidence)
    safe = dom_module._safe_area_results(evidence, nodes)[0]
    assert safe.status == "fail"
    assert safe.evidence["skippedOverflow"] == ["support_item0_value"]
    assert [item["id"] for item in safe.evidence["outside"]] == ["primary_unit"]


def test_contrast_is_not_double_counted_when_mask_failed() -> None:
    results = [
        _rule_result("SPEC.MASK", "fail"),
        _rule_result(
            "VIS.CONTRAST_LOW",
            "fail",
            {"nodes": [{"id": "title_title", "status": "fail"}]},
        ),
    ]
    contrast = plugin._dedupe_results(results)[1]
    assert contrast.status == "na"
    assert "不重复" in contrast.actual
    assert contrast.evidence["dedupe"]["from"] == "fail"


def test_contrast_is_not_double_counted_for_covered_nodes() -> None:
    results = [
        _rule_result("SPEC.TITLE_COLOR", "fail", {"component": "title_title"}),
        _rule_result(
            "VIS.CONTRAST_LOW",
            "fail",
            {"nodes": [{"id": "title_title", "status": "fail"}]},
        ),
    ]
    assert plugin._dedupe_results(results)[1].status == "na"


def test_contrast_keeps_deduction_when_color_rule_does_not_cover_node() -> None:
    results = [
        _rule_result("SPEC.TITLE_COLOR", "fail", {"component": "title_title"}),
        _rule_result(
            "VIS.CONTRAST_LOW",
            "fail",
            {
                "nodes": [
                    {"id": "title_title", "status": "fail"},
                    {"id": "support_item0_value", "status": "fail"},
                ]
            },
        ),
    ]
    assert plugin._dedupe_results(results)[1].status == "fail"


def test_padding_and_safe_area_share_one_deduction() -> None:
    results = [
        _rule_result("SPEC.PADDING", "fail"),
        _rule_result("SPEC.SAFE_AREA", "fail"),
    ]
    updated = plugin._dedupe_results(results)
    assert updated[0].status == "na"
    assert "同因" in updated[0].actual
    assert updated[1].status == "fail"


def test_font_too_small_is_not_double_counted() -> None:
    results = [
        _rule_result("SPEC.PRIMARY_FONT", "fail", {"component": "primary_value"}),
        _rule_result(
            "VIS.FONT_TOO_SMALL",
            "pending",
            {"nodes": [{"id": "primary_value", "fontSize": 10}]},
        ),
    ]
    assert plugin._dedupe_results(results)[1].status == "na"


def test_title_clip_is_not_double_counted_after_ellipsis_failure() -> None:
    results = [
        _rule_result(
            "SPEC.TITLE_ELLIPSIS",
            "fail",
            {"components": ["title_title", "title_subtitle"]},
        ),
        _rule_result(
            "VIS.TEXT_CLIPPED",
            "fail",
            {"findings": [{"components": ["title_title:3"], "component": "title_title"}]},
        ),
    ]
    assert plugin._dedupe_results(results)[1].status == "na"


def _ellipsis_failure(*component_ids: str) -> Any:
    return _rule_result(
        "SPEC.TITLE_ELLIPSIS", "fail", {"components": list(component_ids)}
    )


def _title_component(component_id: str, **styles: Any) -> dict[str, Any]:
    return {"id": component_id, "styles": styles}


def _title_node(component_id: str, text: str, **overrides: Any) -> dict[str, Any]:
    node = {
        "id": component_id,
        "text": text,
        "renderedText": text,
        "visible": True,
        "zeroSized": False,
        "lineCount": 1,
        "clientWidth": 106.0,
        "scrollWidth": 106.0,
    }
    node.update(overrides)
    return node


def test_title_ellipsis_is_waived_when_title_fits_single_line() -> None:
    evidence = {"nodes": [_title_node("title_title", "考试 还剩", scrollWidth=108.0)]}
    components = {"title_title": _title_component("title_title", maxLines=1)}
    updated = plugin._waive_title_ellipsis(
        [_ellipsis_failure("title_title")], evidence, components
    )
    assert updated[0].status == "na"
    assert "未溢出" in updated[0].actual
    assert updated[0].evidence["dedupe"]["from"] == "fail"


def test_title_ellipsis_keeps_failure_when_title_overflows_horizontally() -> None:
    evidence = {"nodes": [_title_node("title_title", "很久以后的考试", scrollWidth=140.0)]}
    components = {"title_title": _title_component("title_title", maxLines=1)}
    updated = plugin._waive_title_ellipsis(
        [_ellipsis_failure("title_title")], evidence, components
    )
    assert updated[0].status == "fail"


def test_title_ellipsis_keeps_failure_when_rendered_text_is_truncated() -> None:
    evidence = {
        "nodes": [_title_node("title_title", "很久以后的考试", renderedText="很久以后")]
    }
    components = {"title_title": _title_component("title_title", maxLines=1)}
    updated = plugin._waive_title_ellipsis(
        [_ellipsis_failure("title_title")], evidence, components
    )
    assert updated[0].status == "fail"


def test_title_ellipsis_keeps_failure_when_title_wraps() -> None:
    evidence = {"nodes": [_title_node("title_title", "考试 还剩", lineCount=2)]}
    components = {"title_title": _title_component("title_title", maxLines=1)}
    updated = plugin._waive_title_ellipsis(
        [_ellipsis_failure("title_title")], evidence, components
    )
    assert updated[0].status == "fail"


def test_title_ellipsis_keeps_failure_without_v2_evidence() -> None:
    v1_node = {
        "id": "title_title",
        "text": "考试 还剩",
        "visible": True,
        "zeroSized": False,
    }
    components = {"title_title": _title_component("title_title", maxLines=1)}
    updated = plugin._waive_title_ellipsis(
        [_ellipsis_failure("title_title")], {"nodes": [v1_node]}, components
    )
    assert updated[0].status == "fail"


def test_title_ellipsis_keeps_failure_when_any_title_does_not_fit() -> None:
    evidence = {
        "nodes": [
            _title_node("title_title", "考试 还剩"),
            _title_node("title_subtitle", "还剩 46 天", lineCount=2),
        ]
    }
    components = {
        "title_title": _title_component("title_title", maxLines=1),
        "title_subtitle": _title_component("title_subtitle", maxLines=1),
    }
    updated = plugin._waive_title_ellipsis(
        [_ellipsis_failure("title_title", "title_subtitle")], evidence, components
    )
    assert updated[0].status == "fail"


def test_title_ellipsis_keeps_failure_when_declaration_is_complete() -> None:
    evidence = {"nodes": [_title_node("title_title", "考试 还剩")]}
    components = {
        "title_title": _title_component(
            "title_title", maxLines=1, textOverflow="ellipsis"
        )
    }
    updated = plugin._waive_title_ellipsis(
        [_ellipsis_failure("title_title")], evidence, components
    )
    assert updated[0].status == "fail"


def _make_sample(
    work_dir: Path,
    *,
    components: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    blocks: dict[str, Any] | None = None,
    query: str | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    run_dir = work_dir / "run"
    attempt = run_dir / "Q001" / "attempt_000"
    attempt.mkdir(parents=True)
    (attempt / "genui.jsonl").write_text(
        _genui(components or _q001_components(), data), encoding="utf-8"
    )
    if blocks is not None:
        (attempt / "blocks.json").write_text(
            json.dumps(blocks, ensure_ascii=False), encoding="utf-8"
        )
    output_dir = work_dir / "plugin" / "samples" / "Q001"
    output_dir.mkdir(parents=True)
    sample = {"id": "Q001", "size": "2x2"}
    if query is not None:
        sample["query"] = query
    context = {
        "apiVersion": "batch-postprocess-v2",
        "runDir": str(run_dir),
        "sample": sample,
        "finalAttemptDir": str(attempt),
        "outputDir": str(output_dir),
        "config": {},
    }
    return context, output_dir, attempt


def test_process_sample_writes_static_spec(work_dir: Path) -> None:
    context, output_dir, _ = _make_sample(work_dir, components=_compliant_components())
    result = plugin.process_sample(context)
    assert "scenario" not in result["facts"]
    assert "expectedDays" not in result["facts"]
    assert not (output_dir / "oracle.json").exists()
    assert not (output_dir / "injected_genui.jsonl").exists()
    static = json.loads((output_dir / "sample_static.json").read_text(encoding="utf-8"))
    assert "oracle" not in static and "injected" not in static
    assert static["rubricVersion"] == 6

    manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    PostprocessManager._validate_manifest(manifest, PLUGIN_DIR)
    normalized = PostprocessManager._normalize_result(
        result,
        manifest=manifest,
        scope="sample",
        asset_root=output_dir,
        asset_base_url="/assets",
        allow_deferred=True,
    )
    assert normalized["status"] in {"success", "partial"}


def test_evaluate_sample_with_capture_evidence(work_dir: Path) -> None:
    context, output_dir, _ = _make_sample(work_dir, components=_compliant_components())
    plugin.process_sample(context)
    evidence = _rendered_evidence()
    (output_dir / "dom_original.json").write_text(
        json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
    )
    capture = {("Q001", "original"): {"ok": True}}
    verdict = plugin._evaluate_sample("Q001", output_dir, capture, 3)
    assert verdict["status"] == "success"
    assert verdict["verdict"] == "通过"
    assert verdict["counts"]["failed"] == 0
    assert not [item for item in verdict["results"] if item["rule"].startswith("TARGET.")]
    assert (output_dir / "verdict.json").is_file()


def test_evaluate_sample_waives_title_ellipsis_when_dom_proves_fit(
    work_dir: Path,
) -> None:
    context, output_dir, _ = _make_sample(work_dir)
    plugin.process_sample(context)
    static = json.loads((output_dir / "sample_static.json").read_text(encoding="utf-8"))
    declared = next(
        item for item in static["spec"] if item["rule"] == "SPEC.TITLE_ELLIPSIS"
    )
    assert declared["status"] == "fail"
    evidence = _rendered_evidence()
    evidence["schemaVersion"] = "target-dom-v2"
    title = next(node for node in evidence["nodes"] if node["id"] == "title_title")
    title.update(
        renderedText=title["text"],
        lineCount=1,
        clientWidth=106.0,
        scrollWidth=108.0,
    )
    (output_dir / "dom_original.json").write_text(
        json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
    )
    verdict = plugin._evaluate_sample(
        "Q001",
        output_dir,
        {("Q001", "original"): {"ok": True}},
        3,
    )
    title_rule = next(
        item for item in verdict["results"] if item["rule"] == "SPEC.TITLE_ELLIPSIS"
    )
    assert title_rule["status"] == "na"


def test_capture_failure_marks_sample_failed(work_dir: Path) -> None:
    context, output_dir, _ = _make_sample(work_dir, components=_compliant_components())
    plugin.process_sample(context)
    verdict = plugin._evaluate_sample("Q001", output_dir, {}, 3)
    assert verdict["status"] == "failed"
    assert any(item["rule"] == "L0.CAPTURE_FAILED" for item in verdict["results"])


def test_finalize_merges_images_and_summary(work_dir: Path) -> None:
    context, output_dir, _ = _make_sample(work_dir, components=_compliant_components())
    plugin.process_sample(context)
    evidence = _rendered_evidence()
    (output_dir / "dom_original.json").write_text(
        json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
    )
    from PIL import Image

    Image.new("RGB", (150, 150), (31, 31, 153)).save(output_dir / "original.png")
    verdict = plugin._evaluate_sample(
        "Q001",
        output_dir,
        {("Q001", "original"): {"ok": True}},
        3,
    )
    verdict["images"] = {"original": "original.png"}
    (output_dir / "verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False), encoding="utf-8"
    )
    dataset_dir = work_dir / "plugin" / "dataset"
    dataset_dir.mkdir(parents=True)
    summary = plugin._summarize(
        [{"sampleId": "Q001"}], {"Q001": verdict}, ""
    )
    (dataset_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False), encoding="utf-8"
    )
    value = plugin.finalize(
        {
            "datasetOutputDir": str(dataset_dir),
            "sampleOutputDirs": {"Q001": str(output_dir)},
        }
    )
    update = value["sampleResults"][0]
    keys = {item["key"] for item in update["artifacts"]}
    assert keys == {"verdict", "issues"}
    assert "oracle" not in keys and "evidence" not in keys
    verdict_artifact = next(item for item in update["artifacts"] if item["key"] == "verdict")
    labels = [row["label"] for row in verdict_artifact["data"]]
    assert labels == ["尺寸", "主题", "规范布局"]
    assert update["status"] == "success"

    manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    PostprocessManager._validate_manifest(manifest, PLUGIN_DIR)
    normalized = PostprocessManager._normalize_result(
        update,
        manifest=manifest,
        scope="sample",
        asset_root=output_dir,
        asset_base_url="/assets",
    )
    assert normalized["status"] == "success"


# ---------------------------------------------------------------- 评分口径


def _result(rule: str, status: str) -> dict[str, Any]:
    return {"rule": rule, "status": status, "title": rule}


def _score_context() -> dict[str, Any]:
    return {}


def _all_pass_results() -> list[dict[str, Any]]:
    return [
        _result(rule, "pass")
        for rule in (
            "VIS.OVERFLOW",
            "VIS.CONTRAST",
            "SPEC.RADIUS",
            "SPEC.PRIMARY_FONT",
            "ASSET.RENDERED",
        )
    ]


def test_score_full_pass_is_hundred() -> None:
    score = plugin.te_score.score_sample(_all_pass_results(), _score_context())
    assert score["total"] == 100.0
    assert score["band"] == "优秀"
    assert score["availableWeight"] == 100.0
    dimensions = {item["key"]: item for item in score["dimensions"]}
    assert dimensions["spec"]["score"] == 60.0
    assert dimensions["visibility"]["score"] == 40.0
    assert "target" not in dimensions
    assert "asset" not in dimensions


def test_score_visibility_failure_deducts() -> None:
    results = _all_pass_results()
    results[0] = _result("VIS.OVERFLOW", "fail")
    score = plugin.te_score.score_sample(results, _score_context())
    assert score["total"] == 80.0
    assert plugin.te_score.dimension_score(score, "visibility") == 20.0
    assert plugin.te_score.dimension_score(score, "spec") == 60.0
    assert score["note"] == ""


def test_layout_failures_are_diagnostic_only() -> None:
    results = [
        plugin._result_from_dict(_result("LAYOUT.CARD_OVERFLOW", "fail")),
        plugin._result_from_dict(_result("SPEC.MASK", "pass")),
    ]
    assert plugin._sample_status(results) == "success"
    assert plugin._verdict_text(results) == "通过"
    assert plugin._counts(results)["failed"] == 0
    assert plugin._issue_results(results) == []


def test_score_pending_counts_half() -> None:
    results = [_result("VIS.CONTRAST", "pending"), _result("SPEC.MASK", "pending")]
    score = plugin.te_score.score_sample(results, _score_context())
    assert score["total"] == 50.0
    assert score["band"] == "不合格"
    dimension = next(item for item in score["dimensions"] if item["key"] == "visibility")
    assert dimension["score"] == 20.0
    assert dimension["pending"] == 1


def test_asset_rules_are_diagnostic_only() -> None:
    results = _all_pass_results()
    results = [item for item in results if not item["rule"].startswith("ASSET.")]
    score = plugin.te_score.score_sample(results, _score_context())
    assert score["total"] == 100.0
    assert score["availableWeight"] == 100.0
    assert all(item["key"] != "asset" for item in score["dimensions"])
    assert plugin.te_score.dimension_score(score, "asset") is None

    failed_asset = _all_pass_results()
    failed_asset.append(_result("ASSET.RENDERED", "fail"))
    assert plugin.te_score.score_sample(failed_asset, _score_context())["total"] == 100.0


def test_score_l0_failure_is_zero() -> None:
    results = _all_pass_results() + [_result("L0.CAPTURE_FAILED", "fail")]
    score = plugin.te_score.score_sample(results, _score_context())
    assert score["total"] == 0.0
    assert score["fatal"] is True
    assert all(item["applicable"] is False for item in score["dimensions"])


def test_score_na_rules_keep_dimension_denominator() -> None:
    results = [_result("SPEC.RADIUS", "na")]
    score = plugin.te_score.score_sample(results, _score_context())
    assert score["total"] == 0.0
    assert score["availableWeight"] == 100.0
    dimensions = {item["key"]: item for item in score["dimensions"]}
    assert dimensions["spec"]["applicable"] is False
    assert dimensions["visibility"]["applicable"] is False


# ---------------------------------------------------------------- 素材渲染


def _image_node(src: str, *, width: float = 24, height: float = 24) -> dict[str, Any]:
    return {
        "id": "icon",
        "tag": "IMG",
        "leaf": True,
        "visible": True,
        "text": "",
        "box": {"x": 100, "y": 12, "width": 20, "height": 20},
        "style": {"fontSize": 16, "color": "rgb(255, 255, 255)"},
        "image": {
            "src": src,
            "naturalWidth": width,
            "naturalHeight": height,
            "complete": width > 0,
        },
    }


def test_asset_rules_pass_for_local_resources() -> None:
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        (root / "base" / "media").mkdir(parents=True)
        (root / "base" / "media" / "icon.svg").write_text("<svg/>", encoding="utf-8")
        results = dom_module._asset_results(
            _evidence("", [_image_node("/resources/base/media/icon.svg")]),
            root,
        )
    by_rule = {item.rule: item.status for item in results}
    assert by_rule == {"ASSET.FILE_MISSING": "pass", "ASSET.RENDERED": "pass"}


def test_asset_rules_flag_missing_and_unrendered() -> None:
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        (root / "base" / "media").mkdir(parents=True)
        (root / "base" / "media" / "icon.svg").write_text("<svg/>", encoding="utf-8")
        results = dom_module._asset_results(
            _evidence(
                "",
                [
                    _image_node("/resources/base/media/missing.svg"),
                    _image_node("/resources/base/media/icon.svg", width=0, height=0),
                ],
            ),
            root,
        )
    by_rule = {item.rule: item.status for item in results}
    assert by_rule["ASSET.FILE_MISSING"] == "fail"
    assert by_rule["ASSET.RENDERED"] == "fail"


def test_asset_rules_skip_remote_theme_images() -> None:
    results = dom_module._asset_results(
        _evidence("", [_image_node("https://example.com/theme.jpg")]),
        Path("."),
    )
    assert results == []


# ---------------------------------------------------------------- 整批维度平均


def test_size_ratio_matches_card_shape() -> None:
    assert plugin._size_ratio("2x2") == "2 / 2"
    assert plugin._size_ratio("2x4") == "2 / 4"
    assert plugin._size_ratio("4x2") == "4 / 2"
    assert plugin._size_ratio("") == "1 / 1"
    assert plugin._size_ratio("wide") == "1 / 1"


def test_score_items_expose_rule_level_deductions() -> None:
    results = [
        _result("SPEC.RADIUS", "pass"),
        _result("SPEC.MASK", "fail"),
    ]
    score = plugin.te_score.score_sample(results, _score_context())
    spec = next(item for item in score["dimensions"] if item["key"] == "spec")
    items = {item["rule"]: item for item in spec["items"]}
    assert items["SPEC.RADIUS"]["deduction"] == 0.0
    assert items["SPEC.MASK"]["deduction"] == 30.0
    assert items["SPEC.MASK"]["weight"] == 30.0
    assert items["SPEC.MASK"]["status"] == "fail"


def test_score_items_sum_matches_dimension_loss() -> None:
    results = [
        _result("VIS.TEXT_CLIPPED", "fail"),
        _result("VIS.TEXT_OVERLAP", "pending"),
        _result("VIS.CONTRAST", "pass"),
        _result("VIS.TEXT_OVERFLOW", "pass"),
    ]
    score = plugin.te_score.score_sample(results, _score_context())
    visibility = next(item for item in score["dimensions"] if item["key"] == "visibility")
    loss = sum(item["deduction"] for item in visibility["items"])
    assert visibility["score"] == 25.0
    assert round(loss, 1) == round(40.0 - visibility["score"], 1)
    assert visibility["items"][1]["status"] == "pending"


def test_score_rows_add_rule_titles() -> None:
    summary = {
        "samples": [
            {
                "样本": "Q001",
                "状态": "failed",
                "结论": "可见性失败",
                "总分": 79.6,
                "等级": "良好",
                "图片": "samples/Q001/original.png",
                "尺寸": "2x2",
                "维度": [
                    {
                        "key": "spec",
                        "label": "规范符合",
                        "max": 60.0,
                        "score": 13.3,
                        "applicable": True,
                        "items": [
                            {
                                "rule": "SPEC.TITLE_FONT",
                                "status": "fail",
                                "deduction": 5.8,
                                "weight": 5.8,
                                "expected": "16 或 20",
                                "actual": "14",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    row = plugin._score_rows(summary)[0]
    item = row["dimensions"][0]["items"][0]
    assert item["title"] == "标题 16/20fp"
    assert item["deduction"] == 5.8


def test_issue_rows_show_rule_deductions() -> None:
    score = {"dimensions": [
        {"key": "visibility", "items": [
            {"rule": "VIS.TEXT_CLIPPED", "status": "fail", "deduction": 3.6},
            {"rule": "VIS.TEXT_OVERFLOW", "status": "pass", "deduction": 0.0},
        ]},
        {"key": "spec", "items": [
            {"rule": "SPEC.RADIUS", "status": "fail", "deduction": 1.2},
        ]},
    ]}
    deductions = plugin._rule_deductions(score)
    assert deductions == {
        "VIS.TEXT_CLIPPED": 3.6, "VIS.TEXT_OVERFLOW": 0.0, "SPEC.RADIUS": 1.2,
    }
    result = plugin._result_from_dict(_result("VIS.TEXT_CLIPPED", "fail"))
    assert plugin._issue_row(result, deductions)["扣分"] == 3.6
    assert plugin._issue_row(result)["扣分"] == "—"


def test_report_renders_rule_deductions_text() -> None:
    summary = {
        "profile": "countdown-card-spec-v1",
        "facts": {},
        "samples": [
            {
                "样本": "Q001",
                "状态": "failed",
                "结论": "可见性失败",
                "总分": 79.6,
                "等级": "良好",
                "图片": "",
                "尺寸": "2x2",
                "可见性": 17.9,
                "规范符合": 13.3,
                "素材渲染": 10.0,
                "维度": [
                    {
                        "key": "spec",
                        "label": "规范符合",
                        "max": 60.0,
                        "score": 13.3,
                        "applicable": True,
                        "items": [
                            {
                                "rule": "SPEC.TITLE_FONT",
                                "status": "fail",
                                "deduction": 5.8,
                                "expected": "16 或 20",
                                "actual": "14",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    cards = plugin._score_cards_html(summary)
    assert "标题 16/20fp" in cards
    assert "−5.8" in cards
    assert "期望：16 或 20" in cards
    markdown = plugin._build_markdown(summary)
    assert "## 扣分明细" in markdown
    assert "规范符合 13.3/60.0：标题 16/20fp −5.8" in markdown
    html_report = plugin._build_html(summary)
    assert "score-card" in html_report


def test_dataset_artifacts_put_rules_then_samples_under_overview() -> None:
    summary = {"profile": "countdown-card-spec-v1", "facts": {}, "samples": [], "rules": []}
    keys = [item["key"] for item in plugin._dataset_artifacts(summary)]
    assert keys == ["overview", "rules", "samples", "scores", "report"]


def test_sample_table_hides_redundant_columns() -> None:
    rows = plugin._table_rows(
        [
            {
                "样本": "Q001",
                "状态": "failed",
                "等级": "良好",
                "图片": "samples/Q001/original.png",
                "通过": 1,
                "失败": 2,
                "待复核": 0,
                "维度": [],
                "失败项": "SPEC.MASK",
                "总分": 60.0,
            }
        ]
    )
    assert list(rows[0]) == ["样本", "状态", "失败项", "总分"]


def test_dimension_table_groups_rules_for_expandable_details() -> None:
    summary = {
        "samples": [
            {
                "维度": [
                    {"key": "spec", "label": "规范符合", "max": 60.0, "score": 30.0},
                    {"key": "visibility", "label": "可见性", "max": 40.0, "score": 40.0},
                ]
            }
        ],
        "rules": [
            {
                "规则": "SPEC.TITLE_COLOR",
                "维度": "规范符合",
                "细分项": "标题颜色",
                "含义": "标题使用主色",
                "平均得分": 30.0,
                "单条满分": 30.0,
                "通过率": 50.0,
                "参与样本": 1,
                "通过": 1,
                "失败": 1,
                "待复核": 0,
            },
        ],
    }
    rows = plugin._dimension_table_rows(summary)
    assert [row["维度"] for row in rows] == ["规范符合", "可见性"]
    assert rows[0]["均分 / 满分"] == "30.0 / 60.0"
    assert [item["规则"] for item in rows[0]["items"]] == ["SPEC.TITLE_COLOR 标题颜色"]
    assert rows[1]["items"] == []
    assert rows[1]["通过率"] == "—"
    assert rows[0]["通过率"] == "50.0%"
    assert rows[0]["items"][0]["含义"] == "标题使用主色"


def test_report_puts_rule_averages_before_score_cards() -> None:
    summary = {
        "profile": "countdown-card-spec-v1",
        "facts": {},
        "samples": [
            {
                "样本": "Q001",
                "状态": "success",
                "结论": "通过",
                "总分": 100,
                "等级": "优秀",
                "图片": "",
                "尺寸": "2x2",
                "维度": [],
            }
        ],
        "rules": [],
    }
    html_report = plugin._build_html(summary)
    assert html_report.index("细分维度明细（整批平均）") < html_report.index("卡片评分总览")


def test_dimension_averages_only_count_applicable_samples() -> None:
    rows = [
        {
            "维度": [
                {"key": "spec", "label": "规范符合", "max": 60.0, "score": None},
                {"key": "visibility", "label": "可见性", "max": 40.0, "score": 30.0},
            ]
        },
        {
            "维度": [
                {"key": "spec", "label": "规范符合", "max": 60.0, "score": 60.0},
                {"key": "visibility", "label": "可见性", "max": 40.0, "score": None},
            ]
        },
    ]
    averages = plugin._dimension_averages(rows)
    by_key = {item["key"]: item for item in averages}
    assert by_key["spec"]["score"] == 60.0
    assert by_key["spec"]["samples"] == 1
    assert by_key["visibility"]["score"] == 30.0
    assert by_key["visibility"]["samples"] == 1
    assert "target" not in by_key
    assert "asset" not in by_key


def test_rule_metrics_average_equals_dimension_average() -> None:
    rows = []
    for mask_status in ("pass", "fail"):
        results = _all_pass_results() + [_result("SPEC.MASK", mask_status)]
        rows.append(plugin.te_score.score_sample(results, _score_context()))
    metrics: dict[str, dict[str, float]] = {}
    for score in rows:
        plugin._collect_rule_metrics(score, metrics)

    mask = metrics["SPEC.MASK"]
    assert mask["samples"] == 2
    assert plugin._rule_weight_text(mask) == "20.0"
    assert plugin._rule_average_text(mask) == "10.0"
    visibility = sum(
        float(plugin._rule_average_text(metrics[rule]))
        for rule in ("VIS.OVERFLOW", "VIS.CONTRAST")
    )
    assert round(visibility, 1) == 40.0


def test_rules_table_explains_each_sub_dimension() -> None:
    sample = {
        "sampleId": "Q001",
        "status": "success",
        "verdict": "通过",
        "size": "2x2",
        "results": [
            {
                "rule": "SPEC.PRIMARY_FONT",
                "status": "pass",
                "expected": "56",
                "actual": "56",
            }
        ],
        "counts": {"passed": 1, "failed": 0, "pending": 0},
        "score": plugin.te_score.score_sample(
            [_result("SPEC.PRIMARY_FONT", "pass")], _score_context()
        ),
    }
    summary = plugin._summarize([sample], {"Q001": sample}, "")
    rules = {item["规则"]: item for item in summary["rules"]}
    primary = rules["SPEC.PRIMARY_FONT"]
    assert primary["维度"] == "规范符合"
    assert primary["细分项"] == "主值 56/38fp"
    assert "56fp" in primary["含义"]
    assert primary["期望示例"] == "56"
    assert primary["单条满分"] == "60.0"
    assert primary["平均得分"] == "60.0"
    assert primary["通过率"] == 100.0
    assert rules["ASSET.RENDERED"]["维度"] == "素材（仅诊断）"
    assert rules["ASSET.RENDERED"]["平均得分"] == "—"

    table = plugin._rule_table_rows(summary["rules"])
    primary_row = next(row for row in table if "SPEC.PRIMARY_FONT" in row["细分维度"])
    assert primary_row["细分维度"] == "规范符合 · SPEC.PRIMARY_FONT 主值 56/38fp"
    assert primary_row["均分 / 满分"] == "60.0 / 60.0"
    assert primary_row["通过率"] == "100.0%"
    assert primary_row["计分样本"] == 1


def test_summarize_reports_spec_and_visibility_only() -> None:
    spec = _result("SPEC.MASK", "pass")
    sample = {
        "sampleId": "Q001",
        "status": "success",
        "verdict": "通过",
        "size": "2x2",
        "results": [spec],
        "counts": {"passed": 1, "failed": 0, "pending": 0, "na": 1},
        "score": plugin.te_score.score_sample([spec], _score_context()),
        "images": {"original": "original.png"},
        "theme": None,
    }
    summary = plugin._summarize([{"sampleId": "Q001", "size": "2x2"}], {"Q001": sample}, "")
    groups = [row["维度"] for row in plugin._dimension_table_rows(summary)]
    assert "规范符合" in groups
    assert "可见性（不适用）" in groups
    assert "数据语义（仅诊断）" not in groups
    row = summary["samples"][0]
    assert "场景" not in row
    assert "期望天数" not in row
    assert row["规范符合"] == 60.0
    assert row["可见性"] == 0.0
    assert row["总分"] == 60.0
    assert row["失败项"] == ""
    assert "期望天数" not in plugin._table_rows(summary["samples"])[0]
    cards = plugin._score_rows(summary)
    assert [item["key"] for item in cards[0]["dimensions"]] == ["spec", "visibility"]
    markdown = plugin._build_markdown(summary)
    assert "| 规范符合 |" in markdown
    assert "| 目标语义 |" not in markdown
    assert "TARGET." not in markdown
    assert all(not item["规则"].startswith("TARGET.") for item in summary["rules"])


def _rect(x: float, y: float, width: float, height: float) -> dict[str, float]:
    return {"x": x, "y": y, "width": width, "height": height}


def _v2_node(
    node_id: str,
    box: dict[str, float],
    *,
    text: str = "",
    leaf: bool = True,
    tag: str = "DIV",
    parent_id: str | None = None,
    ancestors: list[dict[str, Any]] | None = None,
    zero_sized: bool = False,
) -> dict[str, Any]:
    chain = ancestors or []
    clip_chain = [
        entry
        for entry in chain
        if str(entry.get("overflowX")) in {"hidden", "clip"}
        or str(entry.get("overflowY")) in {"hidden", "clip"}
    ]
    return {
        "id": node_id,
        "tag": tag,
        "leaf": leaf,
        "visible": True,
        "text": text,
        "renderedText": text,
        "box": box,
        "contentRect": box,
        "ancestors": chain,
        "clipChain": clip_chain,
        "parentId": parent_id,
        "zeroSized": zero_sized,
        "style": {},
        "image": None,
    }


def _v2_evidence(
    nodes: list[dict[str, Any]],
    *,
    surface: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "target-dom-v2",
        "surface": surface or _rect(0, 0, 150, 150),
        "visibleText": " ".join(node["text"] for node in nodes if node["text"]),
        "nodes": nodes,
        "devicePixelRatio": 3,
        "webQuality": {"findings": [], "coverage": []},
    }


def _layout_rules(results: list[Any], rule: str) -> list[Any]:
    return [item for item in results if item.rule == rule]


def test_layout_card_overflow_reports_only_deepest_node() -> None:
    ancestors = [{"id": "wrap", "tag": "DIV", "box": _rect(90, 0, 80, 80)}]
    evidence = _v2_evidence(
        [
            _v2_node("wrap", _rect(90, 0, 80, 80), leaf=False),
            _v2_node("child", _rect(120, 10, 40, 20), ancestors=ancestors),
        ]
    )
    results = plugin.te_layout.evaluate_layout(evidence, {})
    items = _layout_rules(results, "LAYOUT.CARD_OVERFLOW")
    assert len(items) == 1
    assert items[0].status == "pending"
    assert items[0].evidence["count"] == 1
    assert items[0].evidence["findings"][0]["component"] == "child"


def test_layout_card_overflow_ignores_tolerance() -> None:
    evidence = _v2_evidence([_v2_node("edge", _rect(100, 0, 51, 20))])
    results = plugin.te_layout.evaluate_layout(evidence, {})
    assert _layout_rules(results, "LAYOUT.CARD_OVERFLOW") == []


def test_layout_card_overflow_skips_clipped_overflow() -> None:
    clip = {
        "id": None,
        "tag": "DIV",
        "box": _rect(0, 0, 150, 150),
        "overflowX": "hidden",
        "overflowY": "hidden",
    }
    ball = _v2_node("ball", _rect(-14, -77, 196, 196), ancestors=[clip])
    results = plugin.te_layout.evaluate_layout(_v2_evidence([ball]), {})
    assert _layout_rules(results, "LAYOUT.CARD_OVERFLOW") == []


def test_layout_parent_clip_reports_image_inside_clipping_container() -> None:
    clip = {
        "id": "content",
        "tag": "DIV",
        "box": _rect(0, 0, 40, 40),
        "overflowX": "hidden",
        "overflowY": "hidden",
    }
    evidence = _v2_evidence(
        [_v2_node("icon", _rect(10, 10, 50, 50), tag="IMG", ancestors=[clip])]
    )
    results = plugin.te_layout.evaluate_layout(evidence, {})
    items = _layout_rules(results, "LAYOUT.PARENT_CLIP")
    assert len(items) == 1
    finding = items[0].evidence["findings"][0]
    assert finding["component"] == "icon"
    assert finding["clip"]["component"] == "content"


def test_layout_parent_clip_skips_stacking_container_and_text() -> None:
    clip = {
        "id": "content",
        "tag": "DIV",
        "box": _rect(0, 0, 40, 40),
        "overflowX": "hidden",
        "overflowY": "hidden",
    }
    evidence = _v2_evidence(
        [
            _v2_node("icon", _rect(10, 10, 50, 50), tag="IMG", ancestors=[clip]),
            _v2_node("label", _rect(10, 10, 50, 50), text="12", ancestors=[clip]),
        ]
    )
    components = {"content": {"id": "content", "component": "Stack"}}
    results = plugin.te_layout.evaluate_layout(evidence, components)
    assert _layout_rules(results, "LAYOUT.PARENT_CLIP") == []


def test_layout_sibling_overlap_reports_image_text_pair() -> None:
    evidence = _v2_evidence(
        [
            _v2_node("icon", _rect(10, 10, 40, 40), tag="IMG", parent_id="row"),
            _v2_node("value", _rect(30, 20, 40, 40), text="46", parent_id="row"),
        ]
    )
    results = plugin.te_layout.evaluate_layout(evidence, {})
    items = _layout_rules(results, "LAYOUT.SIBLING_OVERLAP")
    assert len(items) == 1
    assert items[0].evidence["count"] == 1


def test_layout_sibling_overlap_skips_text_pairs_and_stacking_parent() -> None:
    overlapping = [
        _v2_node("left", _rect(10, 10, 40, 40), text="考试", parent_id="row"),
        _v2_node("right", _rect(30, 20, 40, 40), text="46", parent_id="row"),
    ]
    results = plugin.te_layout.evaluate_layout(_v2_evidence(overlapping), {})
    assert _layout_rules(results, "LAYOUT.SIBLING_OVERLAP") == []
    stacked = {"row": {"id": "row", "component": "RelativeContainer"}}
    paired = [
        _v2_node("icon", _rect(10, 10, 40, 40), tag="IMG", parent_id="row"),
        _v2_node("value", _rect(30, 20, 40, 40), text="46", parent_id="row"),
    ]
    results = plugin.te_layout.evaluate_layout(_v2_evidence(paired), stacked)
    assert _layout_rules(results, "LAYOUT.SIBLING_OVERLAP") == []


def test_layout_skips_v1_evidence_and_zero_sized_nodes() -> None:
    v1 = _evidence("考试 还剩 46 天", [_node("primary_value", "46", x=120, width=60)])
    assert plugin.te_layout.evaluate_layout(v1, {}) == []
    evidence = _v2_evidence([_v2_node("hidden", _rect(120, 0, 60, 20), zero_sized=True)])
    assert plugin.te_layout.evaluate_layout(evidence, {}) == []


def test_evaluate_dom_includes_layout_diagnostics() -> None:
    components = plugin.te_genui.parse_genui(_genui(_q001_components()))["components"]
    evidence = _v2_evidence(
        [
            _v2_node("title_title", _rect(12, 12, 126, 20), text="考试 还剩"),
            _v2_node("primary_value", _rect(12, 40, 70, 56), text="46"),
            _v2_node("primary_unit", _rect(12, 96, 16, 16), text="天"),
            _v2_node("support_item0_value", _rect(12, 120, 100, 16), text="2026/12/19"),
            _v2_node("oversized_icon", _rect(100, 120, 80, 20), tag="IMG"),
        ]
    )
    results, _ = dom_module.evaluate_dom(evidence, components)
    rules = {item.rule for item in results if item.status == "pending"}
    assert "LAYOUT.CARD_OVERFLOW" in rules


def test_layout_result_is_diagnostic_only() -> None:
    layout = plugin.te_spec.RuleResult(
        rule="LAYOUT.CARD_OVERFLOW",
        status=plugin.PENDING,
        expected="内容不越出卡片",
        actual="1 个节点越界",
        severity="minor",
    )
    assert plugin._sample_status([layout]) == "success"
    assert plugin._verdict_text([layout]) == "通过"
