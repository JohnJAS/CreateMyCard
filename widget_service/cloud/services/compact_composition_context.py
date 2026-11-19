"""复用现有合同核算组件容量、完整显示文本与原始字号。"""

import ast
import copy
import json
import math
import re
from typing import Any

from services.compact_component_runtime import (
    component_visual_recipe,
    secondary_body_text_width,
    secondary_body_variant,
    text_block_full_width_budget,
    text_block_width_contract,
)
from services.compact_composition_planner import (
    _schema_value,
    _text_width,
    is_compound_duration_text,
)
from services.compact_layout_runtime import load_layout_contract
from services.compact_reference_canvas import reference_dimension
from services.display_text import concatenated_display_text

_RULE_KEYS = (
    "path", "types", "childCount", "childCountMin", "childCountMax", "eventPolicy",
)


def compact_text_block_capacity_context(size: str) -> str:
    """提供必需的组件容量边界，不依赖可选的全量运行时工作表。"""
    if size != "2x4":
        return ""
    contract = text_block_width_contract(size)
    layouts = _layout_geometry(size, None)
    patterns = layouts.get("W-top-bottom", [])
    widths: list[float] = []
    for area in _content_budgets(size, {"W-top-bottom": patterns}, 0):
        width = area.get("innerWidth")
        if isinstance(width, (int, float)):
            widths.append(float(width))
    if not widths:
        raise ValueError("W-top-bottom has no known TextBlock width budget.")
    available = max(widths)
    budget = text_block_full_width_budget(available, available)
    requirements: list[str] = []
    for count in range(contract.minimum_items, contract.maximum_items + 1):
        requirements.append(f"{count}项至少{contract.required_width(count):g}vp")
    return (
        "# TextBlock 槽位容量合同\n\n"
        f"按当前 Recipe 核算：{'；'.join(requirements)}。"
        f"W-top-bottom.details 的实际槽宽为{available:g}vp，横向校验预算上界为{budget:g}vp，"
        f"最多容纳{contract.capacity_for_width(budget)}项，较窄槽位须按实际宽度重新核算。"
        "280vp预算只允许满宽四项TextBlock最多4vp的差额，不改变实际槽位或组件样式。"
        "组件项目数上限不代表当前槽位放得下；只在已登记的 details 槽使用。"
        "放不下时按全部事实重新选择合法组件与布局，不能删项、隐藏绑定、缩字或缩间距。"
        "若合并紧密相关信息，必须保留每项标签、完整值、单位和独立绑定，并复核文字宽度。"
    )


def repair_display_roles(source: str, *, size: str | None = None) -> dict[str, dict[str, Any]]:
    """保留失败源的主文字规格，不能因容量恢复把18fp主文变成14fp正文。"""
    from services.compact_dsl_a2ui_converter import parse_compact_dsl_rows
    from services.compact_high_level_components import CompactDslConversionError, ComponentRow

    try:
        rows = parse_compact_dsl_rows(source)
    except CompactDslConversionError:
        return {}
    roles: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, ComponentRow):
            continue
        if row.component_type not in {"EmphasisText", "EmphasizedData", "SecondaryBody"}:
            continue
        if row.component_type == "SecondaryBody":
            items = row.props.get("items", [])
            if not isinstance(items, list):
                continue
            values = [item.get("value") for item in items if isinstance(item, dict)]
        else:
            key = "mainText" if row.component_type == "EmphasisText" else "value"
            values = [row.props.get(key)]
        for value in values:
            encoded = json.dumps(value, ensure_ascii=False)
            paths = re.findall(r"\$\{(/[^{}]+)\}", encoded)
            if isinstance(value, dict) and isinstance(value.get("path"), str):
                paths = [value.get("path")]
            if len(paths) == 1:
                priority = {"EmphasizedData": 3, "EmphasisText": 2, "SecondaryBody": 1}
                previous = roles.get(paths[0], {})
                if priority.get(previous.get("component"), 0) > priority.get(row.component_type, 0):
                    continue
                roles[paths[0]] = {
                    "component": row.component_type,
                    "displayExpression": value,
                }
                if size == "2x2":
                    variant = None
                    part = "main" if row.component_type == "EmphasisText" else "value"
                    if row.component_type == "SecondaryBody":
                        variant = secondary_body_variant(items, row.props.get("columns", 2))
                        part = "text"
                    recipe = component_visual_recipe(row.component_type, size=size, variant=variant)
                    roles[paths[0]]["fontSize"] = recipe.get("parts", {}).get(part, {}).get(
                        "styles", {},
                    ).get("fontSize")
                if row.component_type == "SecondaryBody":
                    for item in items:
                        if isinstance(item, dict) and item.get("value") == value:
                            roles[paths[0]]["displayLabel"] = item.get("label")
    return roles


def retain_original_small_display_roles(
    reference: dict[str, dict[str, Any]], source: str, task: dict[str, Any] | None = None,
) -> None:
    """逐路径保留首次可读规格；不以中途失败输出覆盖原字号。"""
    for path, role in repair_display_roles(source, size="2x2").items():
        if role.get("component") == "EmphasizedData" and task is not None:
            displayed = _literal_display_sample(role.get("displayExpression"), task)
            if displayed is not None and is_compound_duration_text(displayed[1]):
                continue  # 此选型本来不合法，不把错误30fp冻结成必须保留的规格。
        if path not in reference:
            reference[path] = copy.deepcopy(role)


def literal_display_parts(value: Any, task: dict[str, Any]) -> list[dict[str, str]]:
    """仅分离原纯文字前缀，动态路径和后缀原样保留；未知表达式不尝试。"""
    displayed = _literal_display_sample(value, task)
    if displayed is None or not isinstance(value, str):
        return []
    path, sample = displayed
    marker = "${" + path + "}"
    body = value.strip().removeprefix("{{").removesuffix("}}").strip()
    before, _, after = body.partition(marker)
    literal = r'''(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')'''
    prefix = "".join(ast.literal_eval(match.group(0)) for match in re.finditer(literal, before))
    if not prefix.strip():
        return []
    return [
        {"text": prefix.strip(), "sample": prefix.strip()},
        {"text": "{{ " + marker + after + " }}", "sample": sample[len(prefix):].strip()},
    ]


def _literal_display_sample(value: Any, task: dict[str, Any]) -> tuple[str, str] | None:
    """只接受一个原路径和字符串字面量的加法串；函数、算术和多路径都不猜测。"""
    if isinstance(value, dict) and set(value) == {"path"}:
        path = value.get("path")
        if not isinstance(path, str):
            return None
        sample = _schema_value(task, path).get("sampleValue")
        if isinstance(sample, (str, int, float)) and not isinstance(sample, bool):
            return path, str(sample)
        return None
    if not isinstance(value, str) or not value.strip().startswith("{{"):
        return None
    expression = re.fullmatch(r"\s*\{\{(.*?)\}\}\s*", value, flags=re.DOTALL)
    if expression is None:
        return None
    literal = r'''(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')'''
    token = re.compile(rf"(?P<path>\$\{{(/[^{{}}]+)\}})|(?P<literal>{literal})")
    body = expression.group(1).strip()
    paths: list[str] = []
    parts: list[str] = []
    offset = 0
    for match in token.finditer(body):
        separator = body[offset:match.start()].strip()
        if separator != ("+" if parts else ""):
            return None
        raw_path = match.group("path")
        if raw_path is not None:
            path = raw_path.removeprefix("${").removesuffix("}")
            sample = _schema_value(task, path).get("sampleValue")
            if isinstance(sample, bool) or not isinstance(sample, (str, int, float)):
                return None
            paths.append(path)
            parts.append(str(sample))
        else:
            try:
                text = ast.literal_eval(match.group("literal"))
            except (SyntaxError, ValueError):
                return None
            if not isinstance(text, str):
                return None
            parts.append(text)
        offset = match.end()
    if len(paths) != 1 or body[offset:].strip():
        return None
    return paths[0], "".join(parts)


def small_card_display_text(
    value: Any, task: dict[str, Any], *, bounded_only: bool = False,
) -> str | None:
    """小卡完整文字压力：只读字符串连接或简单布尔映射，不执行表达式。"""
    if isinstance(value, dict):
        if bounded_only:
            return None
        displayed = _literal_display_sample(value, task)
        return displayed[1] if displayed is not None else None
    if not isinstance(value, str):
        if bounded_only and type(value) in {int, float}:
            return str(value)
        return None
    if "{{" not in value:
        return value
    expression = re.fullmatch(r"\s*\{\{(.*?)\}\}\s*", value, flags=re.DOTALL)
    if expression is None:
        return None
    literal = r'''(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')'''
    conditional = re.fullmatch(
        r"\s*\$\{(/[^{}]+)\}\s*(?:(==|!=)\s*-?\d+(?:\.\d+)?\s*)?\?\s*("
        + literal + r")\s*:\s*(" + literal + r")\s*", expression.group(1),
    )
    if conditional is not None:
        allowed_types = {"integer", "number"} if conditional.group(2) else {"boolean"}
        field_type = _schema_value(task, conditional.group(1)).get("type")
        if not bounded_only and field_type not in allowed_types:
            return None
        try:
            branches = [ast.literal_eval(conditional.group(index)) for index in (3, 4)]
        except (SyntaxError, ValueError):
            return None
        if bounded_only:
            if any(re.search(r"[\r\n\t]", branch) for branch in branches):
                return None
            return max(branches, key=lambda text: secondary_body_text_width(text, 1))
        return max(branches, key=lambda text: _text_width(text, 1))
    if bounded_only:
        return None
    return concatenated_display_text(
        value, lambda path: _schema_value(task, path).get("sampleValue"),
    )


def _layout_geometry(size: str, action_count: int | None) -> dict[str, Any]:
    layouts = load_layout_contract().get("layouts", {})
    output: dict[str, Any] = {}
    for name, layout in layouts.items():
        if layout.get("size") != size:
            continue
        count = layout.get("actionCount", {})
        if action_count is not None and not (
            count.get("min", 0) <= action_count <= count.get("max", action_count)
        ):
            continue
        patterns: list[list[dict[str, Any]]] = []
        for pattern in layout.get("patterns", []):
            rules: list[dict[str, Any]] = []
            for rule in pattern.get("rules", []):
                item = {key: copy.deepcopy(rule[key]) for key in _RULE_KEYS if key in rule}
                props = copy.deepcopy(rule.get("props", {}))
                box: dict[str, Any] = {}
                for axis in ("width", "height"):
                    if axis in props:
                        box[axis] = props.pop(axis)
                box.update(copy.deepcopy(rule.get("slotSize", {})))
                if box:
                    item["referenceBox"] = box
                if props:
                    item["fixedProps"] = props
                rules.append(item)
            patterns.append(rules)
        output[name] = patterns
    return output


def composition_group_minimum_height(size: str, group: dict[str, Any]) -> float | None:
    """核算能够无歧义确定条数的文本组合；其它组件继续由完整合同核算。"""
    name = group.get("component")
    if name in {"SingleLineTitle", "PillButton", "CardButton", "CircleButton"}:
        recipe = component_visual_recipe(name, size=size)
        return float(recipe.get("parts", {}).get("root", {}).get("styles", {}).get("height"))
    if size == "2x2" and name in {"EmphasizedData", "EmphasisText"}:
        recipe = component_visual_recipe(name, size=size)
        parts = recipe.get("parts", {})
        main = "value" if name == "EmphasizedData" else "main"
        height = parts.get(main, {}).get("styles", {}).get("height")
        if not isinstance(height, (int, float)):
            return None
        if name == "EmphasisText" and "secondaryText" in group.get("placements", []):
            secondary = parts.get("secondary", {}).get("styles", {}).get("height")
            gap = parts.get("root", {}).get("styles", {}).get("itemMargin", 0)
            if not isinstance(secondary, (int, float)):
                return None
            height += secondary + gap
        return float(height)
    if name not in {"SecondaryBody", "TableText"}:
        return None
    indexes: set[int] = set()
    for placement in group.get("placements", []):
        match = re.match(r"items\[(\d+)\]\.", placement)
        if match is not None:
            indexes.add(int(match.group(1)))
    if not indexes or indexes != set(range(len(indexes))):
        return None
    count = len(indexes)
    if name == "TableText":
        if count not in (2, 3):
            return None
        recipe = component_visual_recipe(name, size=size, variant="compact" if count == 3 else None)
        height = recipe.get("parts", {}).get("row", {}).get("styles", {}).get("height", 0)
        gap_key = "threeRowGap" if count == 3 else "twoRowGap"
        return float(count * height + (count - 1) * recipe.get("metrics", {}).get(gap_key, 0))
    columns = group.get("columns", 2)
    lines = group.get("lines", [1] * count)
    variant = secondary_body_variant([{"maxLines": line} for line in lines], columns)
    recipe = component_visual_recipe(name, size=size, variant=variant)
    styles = recipe.get("parts", {}).get("text", {}).get("styles", {})
    line_height = styles.get("height", 0) / styles.get("maxLines", 1)
    if len(lines) != count:
        return None
    height = 0.0
    for start in range(0, count, columns):
        height += line_height * max(lines[start:start + columns])
    rows = math.ceil(count / columns)
    gap = recipe.get("parts", {}).get("root", {}).get("styles", {}).get("itemMargin", 0)
    return height + (rows - 1) * gap


def _padding_pair(value: Any, axis: str) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) * 2
    if isinstance(value, dict):
        sides = ("left", "right") if axis == "width" else ("top", "bottom")
        return sum(float(value.get(side, 0)) for side in sides)
    return 0.0


def _content_budgets(
    size: str, layouts: dict[str, Any], action_count: int
) -> list[dict[str, Any]]:
    """列出合同参考区域的容量算式，不创建几何或锁定业务骨架。"""
    title = component_visual_recipe("SingleLineTitle", size=size)
    button = component_visual_recipe("PillButton", size=size)
    body = component_visual_recipe("SecondaryBody", size=size)
    title_height = title.get("parts", {}).get("root", {}).get("styles", {}).get("height", 0)
    button_height = button.get("parts", {}).get("root", {}).get("styles", {}).get("height", 0)
    group_gap = body.get("parts", {}).get("root", {}).get("styles", {}).get("itemMargin", 0)
    output: list[dict[str, Any]] = []
    for name, patterns in layouts.items():
        for index, rules in enumerate(patterns, start=1):
            for rule in rules:
                if rule.get("eventPolicy") == "require":
                    continue
                box = rule.get("referenceBox", {})
                if not rule.get("path") and len(rules) == 1:
                    box = {"width": reference_dimension(size, "width"),
                           "height": reference_dimension(size, "height")}
                width, height = box.get("width"), box.get("height")
                if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
                    continue
                props = rule.get("fixedProps", {})
                padding = props.get("padding", 0)
                inner_width = width - _padding_pair(padding, "width")
                inner_height = height - _padding_pair(padding, "height")
                gap = props.get("itemMargin", group_gap)
                reservations: list[dict[str, Any]] = []
                for titles in (0, 1):
                    for actions in range(min(action_count, 2) + 1):
                        reserved = titles * title_height + actions * button_height
                        remaining = inner_height - reserved - gap * (titles + actions)
                        reservations.append({"localTitles": titles, "localPillActions": actions,
                                             "bodyHeightAfterReservations": remaining})
                output.append({"layout": name, "variant": index, "path": rule.get("path"),
                               "innerWidth": inner_width, "innerHeight": inner_height,
                               "groupGapForArithmeticOnly": gap,
                               "localReservations": reservations,
                               "condition": (
                                   "Respect the complete variant child roles/counts. "
                                   "Do not reserve a title/action again inside a dedicated "
                                   "body or beside an already separate action slot."
                               )})
    return output
