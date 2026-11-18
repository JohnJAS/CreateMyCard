"""卡片预览使用的 Python Compact DSL 转换接口。"""

from __future__ import annotations

import json
import re
from contextlib import nullcontext
from typing import Literal

from debug_tools.paths import ensure_cloud_import_path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class ConvertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=1_000_000)
    size: Literal["auto", "2x2", "2x4"] = "auto"
    appVersion: str | None = None


class ConvertResponse(BaseModel):
    genui: str
    size: Literal["2x2", "2x4"]


_DATA_ROOT_PATTERN = re.compile(r"/data/([^/}\s\"'+]+)")
_EXPLICIT_THEME_PROPS = frozenset(
    {"backgroundColor", "backgroundImage", "design", "linearGradient"}
)
_STATIC_COMPONENT_TYPES = frozenset({"TextList", "SingleLineList", "ComparisonGroup"})
_STATIC_SUPPORT_COMPONENT_TYPES = frozenset({"EmphasisText"})
_STATIC_LAYOUT_TYPES = frozenset({"S-static-content", "W-static-content"})


def _uses_static_content_components(source: str) -> bool:
    """只按 Compact 行的组件类型决定预览转换上下文。"""
    try:
        parsed = json.loads(source)
        rows = parsed if isinstance(parsed, list) else [parsed]
        if rows and isinstance(rows[0], str):
            rows = [rows]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in source.splitlines() if line.strip()]
    has_static_component = False
    has_static_layout = False
    has_static_support_component = False
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        component_type = row[1]
        if not isinstance(component_type, str):
            continue
        if component_type in _STATIC_COMPONENT_TYPES:
            has_static_component = True
        if component_type in _STATIC_SUPPORT_COMPONENT_TYPES:
            has_static_support_component = True
        props = row[2] if len(row) >= 3 else None
        if component_type == "Layout" and isinstance(props, dict):
            layout = props.get("layout")
            has_static_layout = isinstance(layout, str) and layout in _STATIC_LAYOUT_TYPES
    return has_static_component or (has_static_layout and has_static_support_component)


def _preview_theme_task(source: str, size: str, app_version: str | None) -> dict:
    roots = sorted(set(_DATA_ROOT_PATTERN.findall(source)))
    return {
        "size": size,
        "appVersion": app_version,
        "userQuery": "",
        "dataModelSchema": {"data": {root: {} for root in roots}},
    }


def _source_declares_theme(rows: tuple[object, ...]) -> bool:
    for row in rows:
        if getattr(row, "component_id", None) != "root":
            continue
        props = getattr(row, "props", None)
        return isinstance(props, dict) and bool(_EXPLICIT_THEME_PROPS.intersection(props))
    return False


def register_renderer_conversion_routes(app: FastAPI) -> None:
    """复用云侧转换器，转换端点在 SPA fallback 之前注册。"""

    ensure_cloud_import_path()

    from services.compact_dsl_a2ui_converter import (
        CompactDslConversionError,
        ComponentRow,
        convert_compact_dsl_to_a2ui,
        parse_compact_dsl_rows,
    )
    from services.generation_content_policy import STATIC_CONTENT_POLICY, content_policy_scope
    from services.post_layout_theme import apply_theme
    from services.post_layout_theme_registry import fallback_theme
    from services.theme_selection_policy import default_palette_family
    from services.theme_style_roles import layout_phase

    @app.post("/debug/renderer/convert", response_model=ConvertResponse)
    def convert_for_preview(request: ConvertRequest) -> ConvertResponse:
        size: Literal["2x2", "2x4"] = "2x2"
        try:
            static_scope = (
                content_policy_scope(STATIC_CONTENT_POLICY)
                if _uses_static_content_components(request.source)
                else nullcontext()
            )
            with static_scope:
                rows = parse_compact_dsl_rows(request.source, expand_layouts=False)
                if request.size == "auto":
                    for row in rows:
                        if not isinstance(row, ComponentRow):
                            continue
                        layout = row.props.get("layout")
                        if row.component_type == "Layout" and isinstance(layout, str):
                            size = "2x4" if layout.startswith("W-") else "2x2"
                            break
                        width = row.props.get("width")
                        if isinstance(width, (int, float)) and width >= 240:
                            size = "2x4"
                            break
                else:
                    size = request.size

                protocol_profile = {"version": "v0.9", "appVersion": request.appVersion}
                if _source_declares_theme(rows):
                    genui = convert_compact_dsl_to_a2ui(
                        request.source,
                        size=size,
                        protocol_profile=protocol_profile,
                    )
                else:
                    task = _preview_theme_task(request.source, size, request.appVersion)
                    with layout_phase(task=task):
                        genui = convert_compact_dsl_to_a2ui(
                            request.source,
                            size=size,
                            protocol_profile=protocol_profile,
                        )
                    family = default_palette_family(task)
                    genui = apply_theme(genui, fallback_theme(family), task, {})
        except (CompactDslConversionError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return ConvertResponse(genui=genui, size=size)
