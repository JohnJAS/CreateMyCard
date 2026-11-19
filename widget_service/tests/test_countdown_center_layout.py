"""宽卡居中倒计时：真实转换、绑定保留与旧标题隔离。"""

import json

import pytest

from services.card_validation import CompactDslValidationError, validate_compact_dsl
from services.card_validation.theme_phase_validator import theme_phase_errors
from services.compact_component_runtime import visual_recipe_part
from services.compact_dsl_a2ui_converter import (
    CompactDslConversionError,
    ComponentRow,
    convert_compact_dsl_to_a2ui,
    parse_compact_dsl_rows,
)
from services.compact_layout_runtime import (
    allowed_layout_ids,
    load_layout_contract,
    match_compact_layout,
)
from services.compact_plan import build_compact_plan_tool, parse_compact_plan_call
from services.content_business import BusinessContext, FinalBusinessContext
from services.post_layout_theme import apply_theme, components, decode, presets
from services.post_layout_theme_registry import registered_themes
from services.theme_content_regions import photo_layout_evidence
from services.theme_photo_eligibility import fusion_photo_facts, photo_content_reason
from services.theme_style_roles import layout_phase, role


def _rows(days: int = 100) -> list[list]:
    title = "{{ '春节 ' + ${/data/countdown/relationText} }}"
    return [
        ["root", "Layout", {"layout": "W-countdown-center"},
         ["header", "countdown", "target"]],
        ["header", "SingleLineTitle", {"title": title}],
        ["countdown", "EmphasizedData", {"value": {"path": "/data/countdown/days"}, "unit": "天"}],
        ["target", "SecondaryBody", {"items": [
            {"label": "目标日：", "value": {"path": "/data/countdown/targetDateText"}},
        ]}],
        ["/data/countdown", {"days": days, "targetDateText": "2027/02/06", "relationText": "还剩"}],
    ]


def _source(rows: list[list]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


@pytest.mark.parametrize("days", [0, 9, 100, 1000])
def test_countdown_conversion_preserves_geometry_and_bindings(days: int) -> None:
    source = _source(_rows(days))
    parsed = parse_compact_dsl_rows(source, size="2x4")
    components = [row for row in parsed if isinstance(row, ComponentRow)]
    match = match_compact_layout(
        components, size="2x4", layout_scope="W-countdown-center",
        declared_layout="W-countdown-center",
    )
    assert match.layout_id == "W-countdown-center"
    converted = convert_compact_dsl_to_a2ui(source, size="2x4")
    messages = [json.loads(line) for line in converted.splitlines()]
    update = messages[1].get("updateComponents")
    assert update is not None
    nodes = update.get("components")
    assert nodes is not None
    by_id = {}
    for node in nodes:
        by_id[node.get("id")] = node
    root = by_id.get("root")
    title = by_id.get("header_title")
    value = by_id.get("countdown_value")
    unit = by_id.get("countdown_unit")
    target = by_id.get("target")
    assert all(node is not None for node in (root, title, value, unit, target))
    assert root.get("styles", {}).get("padding") == 12
    assert root.get("itemMargin") == 5
    assert root.get("styles", {}).get("alignItems") == "center"
    assert title.get("styles", {}).get("fontWeight") == 500
    assert "lineHeight" not in title.get("styles", {})
    assert target is not None
    assert target.get("component") == "Text"
    assert not target.get("children")
    assert "itemMargin" not in target
    assert target.get("styles") == {
        "width": "matchParent",
        "height": 21,
        "fontSize": 16,
        "fontWeight": 500,
        "maxLines": 1,
        "textAlign": "center",
        "flexShrink": 0,
        "fontColor": "#991F4799",
        "textOverflow": "clip",
    }
    assert unit.get("styles", {}).get("fontWeight") == 700
    for node, font, height in ((title, 16, 21), (value, 56, 56), (unit, 16, 21), (target, 16, 21)):
        assert node.get("styles", {}).get("fontSize") == font
        assert node.get("styles", {}).get("height") == height
    numeric_slot = by_id.get("countdown")
    assert numeric_slot is not None
    assert numeric_slot.get("component") == "Column"
    assert numeric_slot.get("styles", {}).get("height") == 74
    assert numeric_slot.get("styles", {}).get("justifyContent") == "center"
    assert numeric_slot.get("children") == ["countdown_row"]
    number_row = by_id.get("countdown_row")
    assert number_row is not None
    assert number_row.get("children") == ["countdown_value", "countdown_unit"]
    assert number_row.get("styles", {}).get("height") == 56
    assert number_row.get("styles", {}).get("alignItems") == "bottom"
    assert number_row.get("itemMargin") == 2
    assert number_row.get("styles", {}).get("justifyContent") == "center"
    assert "margin" not in unit.get("styles", {})
    assert "lineHeight" not in value.get("styles", {})
    assert "lineHeight" not in unit.get("styles", {})
    assert "/data/countdown/days" in json.dumps(value)
    assert "/data/countdown/targetDateText" in json.dumps(target)
    assert "目标日：" in json.dumps(target, ensure_ascii=False)


@pytest.mark.parametrize("case", ["icon", "font", "unit", "extra-date", "wrong-role", "action"])
def test_countdown_rejects_invalid_roles_and_style_overrides(case: str) -> None:
    rows = _rows()
    if case == "icon":
        rows[1][2]["icon"] = "resources/base/media/calendar_fill.svg"
    elif case == "font":
        rows[1][2]["fontSize"] = 12
    elif case == "unit":
        rows[2][2].pop("unit")
    elif case == "extra-date":
        rows[3][2].get("items").append({"value": "额外事实"})
    elif case == "wrong-role":
        rows[3][1] = "TextBlock"
    else:
        rows[2][2]["onClick"] = [{"call": "open", "args": {}}]
    with pytest.raises(CompactDslConversionError):
        convert_compact_dsl_to_a2ui(_source(rows), size="2x4")


def test_countdown_is_not_available_on_small_cards() -> None:
    with pytest.raises(CompactDslConversionError):
        convert_compact_dsl_to_a2ui(_source(_rows()), size="2x2")


def test_countdown_rejects_old_root_variant() -> None:
    rows = _rows()
    rows[0][2] = {"layout": "W-top-bottom", "variant": "countdown-center"}
    with pytest.raises(CompactDslConversionError, match="W-top-bottom.variant 未登记"):
        convert_compact_dsl_to_a2ui(_source(rows), size="2x4")


def test_countdown_final_business_identifies_number_as_primary_region() -> None:
    task = {"size": "2x4", "dataModelSchema": {}}
    source = _source(_rows())
    context = FinalBusinessContext.from_layout(source, BusinessContext.from_task(task))
    assert context.payload().get("primaryRegionId") == "countdown"
    with layout_phase():
        a2ui = convert_compact_dsl_to_a2ui(source, size="2x4")
    data_model = {"data": {"countdown": _rows()[-1][1]}}
    evidence = photo_layout_evidence(components(decode(a2ui)), data_model, final_layout=source)
    facts = fusion_photo_facts(task, evidence, source, business_context=context)
    assert facts.error is None
    top_focus = facts.scopes.get("top-focus")
    assert top_focus is not None
    assert top_focus.body_flow.get("lineCount") == 1
    photos = registered_themes("photos")
    gradient = next(photo for photo in photos if photo.get("id") == "photo-ux-gradient-wide")
    assert photo_content_reason(gradient, task, evidence, source) is None
    over_budget = {**evidence, "photoBodyTextFlow": {"countdown": {"lineCount": 5}}}
    assert photo_content_reason(gradient, task, over_budget, source) is not None


def test_default_title_recipes_keep_existing_dimensions() -> None:
    for size in ("2x2", "2x4"):
        _, plain = visual_recipe_part("SingleLineTitle", "root", size=size)
        _, icon = visual_recipe_part("SingleLineTitle", "root", size=size, variant="withIcon")
        _, text = visual_recipe_part("SingleLineTitle", "title", size=size)
        assert plain.get("height") == 12
        assert icon.get("height") == 20
        assert text.get("fontSize") == 12
        assert text.get("fontWeight") == 400
        assert text.get("textAlign") == "start"


@pytest.mark.parametrize("theme_id", ["gradient-blue", "gradient-purple", "solid-warm", "photo"])
@pytest.mark.parametrize("text_override", [None, "#FF123456"])
def test_countdown_date_follows_theme_with_sixty_percent_opacity(theme_id, text_override) -> None:
    task = {"size": "2x4"}
    if theme_id == "photo":
        theme = next(item for item in registered_themes("photos") if item.get("size") == "2x4")
    else:
        theme = next(item for item in presets(task) if item.get("id") == theme_id)
    with layout_phase():
        layout = convert_compact_dsl_to_a2ui(_source(_rows()), size="2x4")
    assert theme_phase_errors(layout, layout=True) == []
    layout_nodes = {}
    for node in components(decode(layout)):
        layout_nodes[node.get("id")] = node
    assert layout_nodes.get("target", {}).get("styles", {}).get("fontColor") == role("primary", 0.6)
    assert layout_nodes.get("header_title", {}).get("styles", {}).get("fontColor") == (
        role("secondary")
    )
    overrides = {"text": {"color": text_override}} if text_override else {}
    final = apply_theme(layout, theme, task, overrides)
    assert theme_phase_errors(final, layout=False) == []
    final_nodes = {}
    for node in components(decode(final)):
        final_nodes[node.get("id")] = node
    primary = text_override or theme.get("content", {}).get("roles", {}).get("primary")
    assert primary is not None
    date_styles = final_nodes.get("target", {}).get("styles", {})
    assert date_styles.get("fontColor") == "#99" + primary.removeprefix("#FF")
    assert date_styles.get("fontWeight") == 500
    assert final_nodes.get("header_title", {}).get("styles", {}).get("fontWeight") == 500
    assert final_nodes.get("countdown_unit", {}).get("styles", {}).get("fontWeight") == 700
    assert "/data/countdown/targetDateText" in final


@pytest.mark.parametrize("scope", [None, "W-plan-guided", "W-adaptive-single-business"])
def test_countdown_full_validation_accepts_fixed_height_budget(scope: str | None) -> None:
    task = {
        "size": "2x4",
        "dataModelSchema": {"data": {"countdown": {
            "days": {"type": "integer", "sampleValue": 100},
            "relationText": {"type": "string", "sampleValue": "还剩"},
            "targetDateText": {"type": "string", "sampleValue": "2027/02/06"},
        }}},
    }
    validate_compact_dsl(
        _source(_rows()), task_spec=task,
        card_spec={"suggestSize": "2x4"}, enforce_model_component_types=True,
        layout_scope=scope,
    )
    with pytest.raises(CompactDslValidationError, match="is not allowed in W-top-bottom"):
        validate_compact_dsl(
            _source(_rows()), task_spec=task,
            card_spec={"suggestSize": "2x4"}, enforce_model_component_types=True,
            layout_scope="W-top-bottom",
        )


def test_countdown_enters_online_layout_candidates() -> None:
    layout = "W-countdown-center"
    assert allowed_layout_ids("2x4", layout) == (layout,)
    assert layout in allowed_layout_ids("2x4", "W-plan-guided")
    assert layout in allowed_layout_ids("2x4", "W-adaptive-single-business")
    assert layout in load_layout_contract().get("layouts", {})
    tool = build_compact_plan_tool(
        {"size": "2x4"}, layout_scope="W-plan-guided",
    )
    properties = tool.get("function", {}).get("parameters", {}).get("properties", {})
    assert layout in properties.get("layoutHints", {}).get("items", {}).get("enum", [])


def test_countdown_plan_keeps_facts_and_actions_in_other_layouts() -> None:
    layout = "W-countdown-center"
    task = {
        "userQuery": "运动会倒计时，显示标题、天数和目标日期",
        "size": "2x4",
        "dataModelSchema": {"data": {"countdown": {
            "title": {"type": "string", "sampleValue": "运动会"},
            "days": {"type": "integer", "sampleValue": 7},
            "date": {"type": "string", "sampleValue": "2027/02/06"},
        }}},
        "eventCandidates": [{
            "id": "event.open.calendar", "description": "打开日历",
            "call": "clickToDeeplink", "args": {"uri": "hww://calendar"},
        }],
    }
    facts = []
    slots = (
        ("title", "SingleLineTitle"),
        ("days", "EmphasizedData"),
        ("date", "SecondaryBody"),
    )
    for field, component in slots:
        facts.append({
            "requirement": field, "dataId": f"/data/countdown/{field}",
            "componentHints": [component], "priority": "must",
        })
    arguments = {"info_required": facts, "layoutHints": [layout]}
    payload = {"name": "submit_card_plan", "arguments": arguments}
    result = parse_compact_plan_call(json.dumps(payload), task)
    assert result.plan.get("layoutHints") == [layout]
    assert len(result.plan.get("info_required", [])) == 3
    facts.append({
        "requirement": "打开日历", "actionId": "event.open.calendar",
        "componentHints": ["PillButton"], "priority": "must",
    })
    result = parse_compact_plan_call(json.dumps(payload), task)
    assert layout not in result.plan.get("layoutHints", [])
    accepted_actions = []
    for fact in result.plan.get("info_required", []):
        action = fact.get("actionId")
        if action is not None:
            accepted_actions.append(action)
    assert accepted_actions == ["event.open.calendar"]


def test_countdown_component_variant_cannot_enable_itself_in_an_old_layout() -> None:
    source = _source([
        ["root", "Column", {"padding": 12}, ["title"]],
        ["title", "SingleLineTitle", {"title": "旧标题", "variant": "countdown-center"}],
    ])
    with pytest.raises(CompactDslConversionError, match="仅由宽卡倒计时布局启用"):
        convert_compact_dsl_to_a2ui(source, size="2x4")


@pytest.mark.parametrize("area", ["title", "date", "number", "title-lines", "date-lines"])
def test_countdown_does_not_hide_known_overflow(area: str) -> None:
    rows = _rows()[:4]
    rows[1][2]["title"] = "运动会还有"
    rows[2][2]["value"] = 100
    rows[3][2]["items"] = [{"value": "目标日：2027年2月6日"}]
    if area == "title":
        rows[1][2]["title"] = "完整标题" * 20
    elif area == "date":
        rows[3][2]["items"] = [{"value": "完整目标日期" * 20}]
    elif area == "title-lines":
        rows[1][2]["title"] = "倒计时\n标题"
    elif area == "date-lines":
        rows[3][2]["items"] = [{"value": "目标日：\n2027年2月6日"}]
    else:
        rows[2][2]["value"] = 12345678901234567890
    expected = "countdown-center requires one line" if area == "date-lines" else None
    with pytest.raises(CompactDslValidationError, match=expected):
        validate_compact_dsl(
            _source(rows), task_spec={"size": "2x4", "dataModelSchema": {"data": {}}},
            card_spec={"suggestSize": "2x4"}, enforce_model_component_types=True,
        )


def test_countdown_checks_number_and_unit_together() -> None:
    rows = _rows()[:4]
    rows[1][2]["title"] = "运动会还有"
    rows[2][2]["value"] = 12345678
    rows[3][2]["items"] = [{"value": "2027/02/06"}]
    with pytest.raises(CompactDslValidationError, match="value and unit require"):
        validate_compact_dsl(
            _source(rows), task_spec={"size": "2x4", "dataModelSchema": {"data": {}}},
            card_spec={"suggestSize": "2x4"},
        )
