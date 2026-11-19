"""正式槽位核算与显示文本检查共用的参考几何和测量工具。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from services.compact_component_runtime import component_visual_recipe
from services.compact_reference_canvas import reference_dimension

_CONTAINERS = {"Column", "Row", "Stack"}
_DURATION_PART = r"\d+(?:\.\d+)?\s*(?:小时|分钟|毫秒|天|时|分|秒)"
_COMPOUND_DURATION = re.compile(rf"\s*(?:{_DURATION_PART}\s*){{2,}}")


@dataclass
class Region:
    path: tuple[int, ...]
    kind: str
    props: dict[str, Any]
    rule: dict[str, Any]
    children: list[Region] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0


def _part(size: str, name: str, part: str, variant: str | None = None) -> dict[str, Any]:
    recipe = component_visual_recipe(name, size=size, variant=variant)
    return recipe.get("parts", {}).get(part, {}).get("styles", {})


def _extent(value: Any, axis: str) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) * 2
    if isinstance(value, dict):
        sides = ("left", "right") if axis == "width" else ("top", "bottom")
        return sum(float(value.get(side, 0)) for side in sides)
    return 0.0


def _schema_value(task: dict[str, Any], path: str) -> dict[str, Any]:
    node = task.get("dataModelSchema", {})
    for token in path.removeprefix("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list) and token.isdigit():
            index = int(token)
            node = node[index] if index < len(node) else None
        elif isinstance(node, dict):
            node = node.get("items") if token.isdigit() and "items" in node else node.get(token)
        else:
            return {}
    return node if isinstance(node, dict) else {}


def is_compound_duration_text(value: Any) -> bool:
    """只识别完整多段时长样值，不推测字段名、不拆单位或执行表达式。"""
    return isinstance(value, str) and _COMPOUND_DURATION.fullmatch(value) is not None


def compound_duration_bindings(plan: dict[str, Any], task: dict[str, Any]) -> list[str]:
    """列出事实中具有明确完整多段时长样值的字符串绑定。"""
    paths: list[str] = []
    for fact in plan.get("info_required", []):
        path = fact.get("dataId")
        if not isinstance(path, str):
            continue
        schema_field = _schema_value(task, path)
        if schema_field.get("type") != "string":
            continue
        if is_compound_duration_text(schema_field.get("sampleValue")) and path not in paths:
            paths.append(path)
    return paths


def _text_width(value: str, font_size: float) -> float:
    # 保守压力估算，换行按实际字符累计，不把总宽直接除以行数冒充可换行。
    widths = []
    for line in value.splitlines():
        widths.append(sum(font_size * (0.6 if ch.isascii() else 1) for ch in line))
    return math.ceil(max(widths, default=0))


def _wrapped_lines(text: str, font_size: float, width: float) -> int:
    lines = 1
    used = 0.0
    for character in text:
        if character == "\n":
            lines += 1
            used = 0.0
            continue
        advance = font_size * (0.6 if character.isascii() else 1)
        if advance > width:
            return 3
        if used + advance > width:
            lines += 1
            used = 0.0
        used += advance
    return lines


def _region_tree(size: str, rules: list[dict[str, Any]]) -> Region | None:
    nodes: dict[tuple[int, ...], Region] = {}
    for rule in rules:
        path = tuple(rule.get("path", []))
        for depth in range(len(path) + 1):
            prefix = path[:depth]
            if prefix not in nodes:
                nodes[prefix] = Region(prefix, "Column", {}, {})
        region = nodes.get(path)
        if region is None:
            return None
        types = rule.get("types", ["Column"])
        containers = [name for name in types if name in _CONTAINERS]
        region.kind = containers[0] if containers else types[0]
        region.props = {**rule.get("props", {}), **rule.get("slotSize", {})}
        region.rule = rule
    _add_implicit_allocation_slots(nodes)
    for path in sorted(nodes):
        if path:
            parent = nodes.get(path[:-1])
            if parent is None:
                return None
            parent.children.append(nodes.get(path))
    root = nodes.get(())
    if root is None:
        return None
    if not _assign_boxes(
        root, reference_dimension(size, "width"), reference_dimension(size, "height"), size
    ):
        return None
    return root


def _add_implicit_allocation_slots(nodes: dict[tuple[int, ...], Region]) -> None:
    """补齐合同已声明数量但未指定组件类型的子槽，用于参考尺寸核算。"""
    for path, region in list(nodes.items()):
        count = region.rule.get("childCount")
        if not isinstance(count, int):
            count = region.rule.get("childCountMin")
        if not isinstance(count, int) or count <= 0:
            continue
        for index in range(count):
            child_path = (*path, index)
            if child_path not in nodes:
                nodes[child_path] = Region(child_path, "Column", {}, {})


def _assign_boxes(region: Region, width: float, height: float, size: str) -> bool:
    region.width = width - _extent(region.props.get("padding"), "width")
    region.height = height - _extent(region.props.get("padding"), "height")
    if region.width <= 0 or region.height <= 0:
        return False
    axis = "width" if region.kind == "Row" else "height"
    available = region.width if axis == "width" else region.height
    gap = region.props.get("itemMargin", 0)
    fixed = 0.0
    flexible = 0
    extents: list[float | None] = []
    for child in region.children:
        extent = child.props.get(axis)
        if axis == "height" and child.kind not in _CONTAINERS and extent is None:
            extent = _part(size, child.kind, "root").get("height")
        if not isinstance(extent, (int, float)):
            extent = None
            flexible += 1
        else:
            fixed += extent
        extents.append(extent)
    remaining = available - fixed - gap * max(0, len(extents) - 1)
    if region.kind != "Stack" and remaining < 0:
        return False
    for child, extent in zip(region.children, extents, strict=True):
        child_width = child.props.get("width")
        child_height = child.props.get("height")
        if not isinstance(child_width, (int, float)):
            child_width = region.width
        if not isinstance(child_height, (int, float)):
            child_height = region.height
        if region.kind != "Stack":
            allocated = extent if extent is not None else remaining / flexible
            if axis == "width":
                child_width = allocated
            else:
                child_height = allocated
        if child_width > region.width or child_height > region.height:
            return False
        if not _assign_boxes(child, child_width, child_height, size):
            return False
    return True


def _leaves(region: Region) -> list[Region]:
    if not region.children:
        return [region]
    output: list[Region] = []
    for child in region.children:
        output.extend(_leaves(child))
    return output
