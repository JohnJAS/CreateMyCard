"""解析 A2UI/GenUI JSONL，供规范规则与 DOM 证据共用。"""

from __future__ import annotations

import json
from typing import Any


def parse_genui(source: str) -> dict[str, Any]:
    """解析 JSONL 行，返回组件、数据模型和 surface 信息。"""
    components: dict[str, dict[str, Any]] = {}
    data: dict[str, Any] = {}
    surface_id = "surface_card"
    surface: dict[str, Any] = {}
    rows = 0
    for line in source.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        rows += 1
        create = row.get("createSurface")
        if isinstance(create, dict):
            if isinstance(create.get("surfaceId"), str):
                surface_id = create["surfaceId"]
            surface = dict(create)
        update_data = row.get("updateDataModel")
        if isinstance(update_data, dict):
            path = update_data.get("path")
            value = update_data.get("value")
            if path in (None, "/") and isinstance(value, dict):
                data.update(value)
            elif isinstance(path, str) and isinstance(value, dict):
                _set_path(data, path, value)
        update = row.get("updateComponents")
        if not isinstance(update, dict):
            continue
        items = update.get("components")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                components[item["id"]] = item
    return {
        "components": components,
        "data": data,
        "surfaceId": surface_id,
        "surface": surface,
        "rows": rows,
    }


def _set_path(data: dict[str, Any], path: str, value: dict[str, Any]) -> None:
    parts = [part for part in path.split("/") if part]
    node: dict[str, Any] = data
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    if parts:
        node[parts[-1]] = value
