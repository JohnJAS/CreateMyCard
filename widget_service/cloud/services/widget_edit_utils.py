"""编辑共用的严格JSON、组件读取、值比较及来源摘要工具。"""

import hashlib
import json
from typing import Any


def source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _json_object(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_json_object)


def _messages(source: str) -> list[dict]:
    messages = [_load_json(line) for line in source.splitlines() if line.strip()]
    if not messages or not all(isinstance(item, dict) for item in messages):
        raise ValueError("edit source must be expanded A2UI JSONL")
    return messages


def _components(messages: list[dict]) -> dict[str, dict]:
    components: dict[str, dict] = {}
    for message in messages:
        update = message.get("updateComponents")
        if not isinstance(update, dict):
            continue
        nodes = update.get("components")
        if not isinstance(nodes, list):
            raise ValueError("edit source components must be a list")
        for node in nodes:
            if not isinstance(node, dict):
                raise ValueError("edit source component must be an object")
            identity = node.get("id")
            if not isinstance(identity, str) or not identity or identity in components:
                raise ValueError("edit source requires unique nonempty component IDs")
            components[identity] = node
    if not components:
        raise ValueError("edit source has no components")
    return components


def _same(left: Any, right: Any) -> bool:
    # bool与整数、列表顺序、键缺失和null均不能混为相同。
    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=False,
    )
