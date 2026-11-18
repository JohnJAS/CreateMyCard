"""几何版式诊断：采集证据上的越界、父容器裁切与兄弟重叠。

只产出 ``LAYOUT.`` 诊断，不进入评分前缀；旧版证据直接跳过，
避免历史产物因缺少字段被误判。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from te_rules import LAYOUT_OVERLAP_RATIO, LAYOUT_TOLERANCE, STATUS_PENDING
from te_spec import RuleResult

SCHEMA_VERSION = "target-dom-v2"
TOLERANCE = LAYOUT_TOLERANCE
OVERLAP_RATIO = LAYOUT_OVERLAP_RATIO
STACKING_CONTAINERS = {"Stack", "RelativeContainer", "AbsoluteLayout"}
DECORATIVE_PREFIX = "__"


def evaluate_layout(
    evidence: dict[str, Any],
    components: dict[str, Any],
) -> list[RuleResult]:
    if evidence.get("schemaVersion") != SCHEMA_VERSION:
        return []
    nodes = _measured_nodes(evidence)
    if not nodes:
        return []
    results: list[RuleResult] = []
    results.extend(_card_overflow(evidence, nodes))
    results.extend(_parent_clip(evidence, nodes, components))
    results.extend(_sibling_overlap(nodes, components))
    return results


def _measured_nodes(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = evidence.get("nodes")
    if not isinstance(nodes, list):
        return []
    measured: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("visible") is False or node.get("zeroSized"):
            continue
        if _box(node.get("box")) is None:
            continue
        measured.append(node)
    return measured


def _card_overflow(
    evidence: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> list[RuleResult]:
    surface = _box(evidence.get("surface"))
    if surface is None:
        return []
    offenders: list[tuple[dict[str, Any], float]] = []
    for node in nodes:
        rect = _box(node.get("contentRect")) or _box(node.get("box"))
        if rect is None:
            continue
        horizontal, vertical = _axis_overflow(rect, surface)
        clip_x, clip_y = _clipped_axes(node)
        spilled = 0.0
        if horizontal > TOLERANCE and not clip_x:
            spilled = horizontal
        if vertical > TOLERANCE and not clip_y:
            spilled = max(spilled, vertical)
        if spilled <= TOLERANCE:
            continue
        offenders.append((node, spilled))
    if not offenders:
        return []
    offender_ids: set[str] = set()
    for node, _ in offenders:
        node_id = _node_id(node)
        if node_id:
            offender_ids.add(node_id)
    covered: set[str] = set()
    for node, _ in offenders:
        for ancestor_id in _ancestor_ids(node):
            if ancestor_id in offender_ids:
                covered.add(ancestor_id)
    causes = [
        (node, overflow)
        for node, overflow in offenders
        if _node_id(node) not in covered
    ]
    items = [_overflow_item(node, overflow, surface) for node, overflow in causes]
    return [
        RuleResult(
            rule="LAYOUT.CARD_OVERFLOW",
            status=STATUS_PENDING,
            expected="可见节点内容不超出卡片画布",
            actual=f"{len(items)} 个节点越出卡片画布，需确认是否为有意设计",
            severity="minor",
            evidence={"findings": items, "count": len(items)},
        )
    ]


def _overflow_item(
    node: dict[str, Any],
    overflow: float,
    surface: dict[str, float],
) -> dict[str, Any]:
    return {
        "component": _node_id(node),
        "tag": node.get("tag"),
        "text": _preview(node),
        "contentRect": node.get("contentRect") or node.get("box"),
        "surface": surface,
        "overflow": round(overflow, 2),
    }


def _parent_clip(
    evidence: dict[str, Any],
    nodes: list[dict[str, Any]],
    components: dict[str, Any],
) -> list[RuleResult]:
    surface = _box(evidence.get("surface"))
    items: list[dict[str, Any]] = []
    for node in nodes:
        if _preview(node):
            continue
        if _node_id(node).startswith(DECORATIVE_PREFIX):
            continue
        clip = _nearest_clip(node, surface)
        if clip is None:
            continue
        clip_id = str(clip.get("id") or "")
        if _component_type(components, clip_id) in STACKING_CONTAINERS:
            continue
        rect = _box(node.get("contentRect")) or _box(node.get("box"))
        clip_box = _box(clip.get("box"))
        if rect is None or clip_box is None:
            continue
        overflow = _max_overflow(rect, clip_box)
        if overflow <= TOLERANCE:
            continue
        items.append(
            {
                "component": _node_id(node),
                "tag": node.get("tag"),
                "contentRect": rect,
                "clip": {"component": clip_id or None, "tag": clip.get("tag"), "box": clip_box},
                "overflow": round(overflow, 2),
            }
        )
    if not items:
        return []
    return [
        RuleResult(
            rule="LAYOUT.PARENT_CLIP",
            status=STATUS_PENDING,
            expected="非文本节点不被父容器裁切",
            actual=f"{len(items)} 个节点被父容器裁切，需确认是否为有意裁剪",
            severity="minor",
            evidence={"findings": items, "count": len(items)},
        )
    ]


def _nearest_clip(
    node: dict[str, Any],
    surface: dict[str, float] | None,
) -> dict[str, Any] | None:
    ancestors = node.get("ancestors")
    if not isinstance(ancestors, list):
        return None
    for entry in ancestors:
        if not isinstance(entry, dict):
            continue
        overflow = f"{entry.get('overflowX')} {entry.get('overflowY')}"
        if not re.search(r"hidden|clip", overflow):
            continue
        box = _box(entry.get("box"))
        if box is None:
            continue
        if surface is not None and _same_box(box, surface):
            return None
        return entry
    return None


def _sibling_overlap(
    nodes: list[dict[str, Any]],
    components: dict[str, Any],
) -> list[RuleResult]:
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if not node.get("leaf"):
            continue
        parent_id = node.get("parentId")
        if not isinstance(parent_id, str) or not parent_id:
            continue
        by_parent.setdefault(parent_id, []).append(node)
    items: list[dict[str, Any]] = []
    for parent_id, children in by_parent.items():
        if _component_type(components, parent_id) in STACKING_CONTAINERS:
            continue
        items.extend(_overlap_pairs(children))
    if not items:
        return []
    return [
        RuleResult(
            rule="LAYOUT.SIBLING_OVERLAP",
            status=STATUS_PENDING,
            expected="同一父容器内的兄弟节点互不遮挡",
            actual=f"{len(items)} 对兄弟节点相交，需确认遮挡程度",
            severity="minor",
            evidence={"findings": items, "count": len(items)},
        )
    ]


def _overlap_pairs(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, first in enumerate(children):
        first_box = _box(first.get("box"))
        if first_box is None:
            continue
        for second in children[index + 1:]:
            second_box = _box(second.get("box"))
            if second_box is None:
                continue
            if _preview(first) and _preview(second):
                continue
            ratio = _overlap_ratio(first_box, second_box)
            if ratio is None or ratio <= OVERLAP_RATIO:
                continue
            items.append(
                {
                    "components": [_node_id(first), _node_id(second)],
                    "texts": [_preview(first), _preview(second)],
                    "boxes": [first_box, second_box],
                    "ratio": round(ratio, 3),
                }
            )
    return items


def _overlap_ratio(
    first: dict[str, float],
    second: dict[str, float],
) -> float | None:
    width = min(first["x"] + first["width"], second["x"] + second["width"])
    width -= max(first["x"], second["x"])
    height = min(first["y"] + first["height"], second["y"] + second["height"])
    height -= max(first["y"], second["y"])
    if width <= TOLERANCE or height <= TOLERANCE:
        return None
    smaller = min(
        first["width"] * first["height"],
        second["width"] * second["height"],
    )
    if smaller <= 0:
        return None
    return (width * height) / smaller


def _axis_overflow(
    rect: dict[str, float],
    region: dict[str, float],
) -> tuple[float, float]:
    horizontal = max(
        region["x"] - rect["x"],
        rect["x"] + rect["width"] - region["x"] - region["width"],
    )
    vertical = max(
        region["y"] - rect["y"],
        rect["y"] + rect["height"] - region["y"] - region["height"],
    )
    return horizontal, vertical


def _clipped_axes(node: dict[str, Any]) -> tuple[bool, bool]:
    """节点内容是否已被祖先裁切；被裁掉的溢出不可见，不重复报越界。"""
    clip_x = False
    clip_y = False
    chain = node.get("clipChain")
    if not isinstance(chain, list):
        return clip_x, clip_y
    for entry in chain:
        if not isinstance(entry, dict):
            continue
        overflow_x = str(entry.get("overflowX") or "")
        overflow_y = str(entry.get("overflowY") or "")
        if re.search(r"hidden|clip", overflow_x):
            clip_x = True
        if re.search(r"hidden|clip", overflow_y):
            clip_y = True
    return clip_x, clip_y


def _max_overflow(
    rect: dict[str, float],
    region: dict[str, float],
) -> float:
    horizontal, vertical = _axis_overflow(rect, region)
    return max(horizontal, vertical)


def _ancestor_ids(node: dict[str, Any]) -> list[str]:
    ancestors = node.get("ancestors")
    if not isinstance(ancestors, list):
        return []
    ids: list[str] = []
    for entry in ancestors:
        if not isinstance(entry, dict):
            continue
        value = entry.get("id")
        if isinstance(value, str) and value:
            ids.append(value)
    return ids


def _component_type(components: dict[str, Any], component_id: str) -> str:
    if not component_id:
        return ""
    component = components.get(component_id)
    if not isinstance(component, dict):
        return ""
    value = component.get("component")
    return value if isinstance(value, str) else ""


def _box(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    box: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        number = value.get(key)
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            return None
        box[key] = float(number)
    if box["width"] <= 0 or box["height"] <= 0:
        return None
    return box


def _same_box(first: dict[str, float], second: dict[str, float]) -> bool:
    return all(abs(first[key] - second[key]) <= TOLERANCE for key in ("x", "y", "width", "height"))


def _node_id(node: dict[str, Any]) -> str:
    value = node.get("id")
    return value if isinstance(value, str) else ""


def _preview(node: dict[str, Any]) -> str:
    value = node.get("renderedText") or node.get("text")
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", text).strip()[:20]
