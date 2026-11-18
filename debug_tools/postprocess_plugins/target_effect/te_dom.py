"""基于 3x 截图与 DOM 证据的可见性和版式检查。

所有判定只消费浏览器采集到的证据；截图不参与语义真值推断。
目标语义已退出评分与采集，本模块不再做天数、关系文案或绑定注入比对。
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from te_layout import evaluate_layout
from te_rules import (
    BAR_PITCH,
    BASELINE_TOLERANCE,
    CONTRAST_MIN,
    CONTRAST_MIN_LARGE,
    DOT_COL_PITCH,
    LARGE_TEXT_BOLD_SIZE,
    LARGE_TEXT_BOLD_WEIGHT,
    LARGE_TEXT_SIZE,
    MIN_FONT_SIZE,
    PATTERN_TOLERANCE,
    SAFE_AREA_INSET,
    SAFE_AREA_TOLERANCE,
    STATUS_FAIL,
    STATUS_NA,
    STATUS_PASS,
    STATUS_PENDING,
)
from te_spec import UNIT_WORDS, RuleResult


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", text).strip()


def evaluate_dom(
    evidence: dict[str, Any],
    components: dict[str, Any],
    *,
    png_path: Path | None = None,
    scale: float = 3.0,
    resource_root: Path | None = None,
    size: str = "2x2",
) -> tuple[list[RuleResult], dict[str, Any]]:
    """返回 DOM 规则结果与可展示的版式指标。"""
    results: list[RuleResult] = []
    nodes = _visible_leaf_nodes(evidence)
    metrics = _layout_metrics(evidence, nodes)
    results.extend(_web_quality_results(evidence))
    results.extend(evaluate_layout(evidence, components))
    results.extend(_font_results(nodes))
    results.extend(_contrast_results(nodes, png_path, scale, evidence.get("surface")))
    results.extend(_safe_area_results(evidence, nodes))
    results.extend(_asset_results(evidence, resource_root))
    results.extend(_pattern_pitch_results(evidence, size))
    results.extend(_unit_baseline_results(nodes))
    return results, metrics


def _visible_leaf_nodes(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = evidence.get("nodes")
    if not isinstance(nodes, list):
        return []
    leaves: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("visible") is False:
            continue
        if not node.get("leaf"):
            continue
        text = normalize_text(node.get("text"))
        if text:
            leaves.append(node)
    return leaves


def _web_quality_results(evidence: dict[str, Any]) -> list[RuleResult]:
    quality = evidence.get("webQuality")
    if not isinstance(quality, dict):
        return [
            RuleResult(
                rule="VIS.EVIDENCE_MISSING",
                status=STATUS_PENDING,
                expected="Web 可见性证据",
                actual="缺少 webQuality 证据",
                severity="major",
            )
        ]
    mapping = {
        "GEOMETRY.CLIP_TEXT": ("VIS.TEXT_CLIPPED", STATUS_FAIL),
        "GEOMETRY.OVERFLOW_TEXT": ("VIS.TEXT_OVERFLOW", STATUS_FAIL),
        "GEOMETRY.OVERFLOW_IMAGE": ("VIS.IMAGE_OVERFLOW", STATUS_FAIL),
        "GEOMETRY.OVERLAP_TEXT": ("VIS.TEXT_OVERLAP", STATUS_PENDING),
        "ASSET.WEB_LOAD_FAILED": ("VIS.IMAGE_LOAD_FAILED", STATUS_FAIL),
    }
    results: list[RuleResult] = []
    findings = quality.get("findings")
    if not isinstance(findings, list):
        return results
    grouped: dict[str, list[dict[str, Any]]] = {}
    ignored_clip: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        code = str(finding.get("rule_id") or "")
        if code == "GEOMETRY.CLIP_TEXT" and not _is_horizontal_clip(finding):
            ignored_clip.append(finding)
            continue
        if code in mapping:
            grouped.setdefault(code, []).append(finding)
    for code, (rule, status) in mapping.items():
        items = grouped.get(code) or []
        if not items:
            actual = "未发现问题"
            rule_evidence: dict[str, Any] = {}
            if code == "GEOMETRY.CLIP_TEXT" and ignored_clip:
                actual = f"未发现横向裁剪（{len(ignored_clip)} 处纵向行框溢出不计入）"
                rule_evidence = {
                    "ignoredVertical": [_compact_evidence(item) for item in ignored_clip[:6]],
                    "ignoredCount": len(ignored_clip),
                }
            results.append(
                RuleResult(
                    rule=rule,
                    status=STATUS_PASS,
                    expected="对应可见性规则通过",
                    actual=actual,
                    severity="major",
                    evidence=rule_evidence,
                )
            )
            continue
        messages = [str(item.get("message") or code) for item in items]
        fail_evidence: dict[str, Any] = {
            "findings": [_compact_evidence(item) for item in items[:6]],
            "count": len(items),
        }
        if code == "GEOMETRY.CLIP_TEXT" and ignored_clip:
            fail_evidence["ignoredVertical"] = [
                _compact_evidence(item) for item in ignored_clip[:6]
            ]
            fail_evidence["ignoredCount"] = len(ignored_clip)
        results.append(
            RuleResult(
                rule=rule,
                status=status,
                expected="对应可见性规则通过",
                actual=f"{len(items)} 处：{messages[0]}" if len(items) > 1 else messages[0],
                severity="major",
                evidence=fail_evidence,
            )
        )
    return results


def _compact_evidence(finding: dict[str, Any]) -> dict[str, Any]:
    value = finding.get("evidence")
    summary = {
        "components": finding.get("components"),
        "source": finding.get("rule_id"),
    }
    if isinstance(value, dict):
        for key in (
            "text",
            "box",
            "contentRect",
            "textRects",
            "component",
            "src",
            "clientWidth",
            "scrollWidth",
            "clientHeight",
            "scrollHeight",
            "clipChain",
            "parentId",
        ):
            if key in value:
                summary[key] = value[key]
    return summary


def _is_horizontal_clip(finding: dict[str, Any]) -> bool:
    """只把横向截断计为文字裁剪。

    ``ellipsis``/``line-clamp`` 也会因字体行框 leading 出现 3–5px 的
    ``scrollHeight`` 溢出，纵向溢出不代表内容真的被截掉；缺少尺寸证据时
    保守保留原 finding，避免漏报。
    """
    value = finding.get("evidence")
    if not isinstance(value, dict):
        return True
    client_width = value.get("clientWidth")
    scroll_width = value.get("scrollWidth")
    width_known = _is_number(client_width) and _is_number(scroll_width)
    if width_known and float(scroll_width) > float(client_width) + 2:
        return True
    if _text_rect_overflows_horizontally(value.get("box"), value.get("textRects")):
        return True
    if width_known:
        return False
    return True


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _text_rect_overflows_horizontally(box: Any, rects: Any) -> bool:
    if not isinstance(box, dict) or not isinstance(rects, list):
        return False
    left = box.get("x")
    width = box.get("width")
    if not _is_number(left) or not _is_number(width):
        return False
    right = float(left) + float(width)
    for rect in rects:
        if not isinstance(rect, dict):
            continue
        rect_left = rect.get("x")
        rect_width = rect.get("width")
        if not _is_number(rect_left) or not _is_number(rect_width):
            continue
        if float(rect_left) < float(left) - 2:
            return True
        if float(rect_left) + float(rect_width) > right + 2:
            return True
    return False


def _font_results(nodes: list[dict[str, Any]]) -> list[RuleResult]:
    if not nodes:
        return []
    small: list[dict[str, Any]] = []
    for node in nodes:
        size = _font_size(node)
        if size is not None and 0 < size < MIN_FONT_SIZE:
            small.append({"id": node.get("id"), "fontSize": size})
    if not small:
        return [
            RuleResult(
                rule="VIS.FONT_TOO_SMALL",
                status=STATUS_PASS,
                expected=f"正文字号 ≥ {MIN_FONT_SIZE:g}",
                actual="全部文本达到下限",
                severity="minor",
            )
        ]
    return [
        RuleResult(
            rule="VIS.FONT_TOO_SMALL",
            status=STATUS_PENDING,
            expected=f"正文字号 ≥ {MIN_FONT_SIZE:g}",
            actual=f"{len(small)} 个文本节点低于下限",
            severity="minor",
            evidence={"nodes": small[:10]},
        )
    ]


def _font_size(node: dict[str, Any]) -> float | None:
    style = node.get("style")
    if not isinstance(style, dict):
        return None
    value = style.get("fontSize")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _contrast_results(
    nodes: list[dict[str, Any]],
    png_path: Path | None,
    scale: float,
    surface: dict[str, Any] | None,
) -> list[RuleResult]:
    if png_path is None or not png_path.is_file():
        return [
            RuleResult(
                rule="VIS.CONTRAST_LOW",
                status=STATUS_NA,
                expected="文字对比度 ≥ 阈值",
                actual="未提供截图",
                severity="major",
            )
        ]
    try:
        from PIL import Image
    except ImportError:
        return [
            RuleResult(
                rule="VIS.CONTRAST_LOW",
                status=STATUS_NA,
                expected="对比度 ≥ 4.5:1",
                actual="缺少 Pillow，未做像素采样",
                severity="minor",
            )
        ]
    try:
        with Image.open(png_path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            scale_x, scale_y = _pixel_scales(surface, width, height, scale)
            weak: list[dict[str, Any]] = []
            sampled = 0
            for node in nodes:
                sample = _contrast_sample(node, rgb, width, height, scale_x, scale_y)
                if sample is None:
                    continue
                sampled += 1
                weak.append(sample)
    except OSError:
        return []
    if sampled == 0:
        return []
    if not weak:
        return [
            RuleResult(
                rule="VIS.CONTRAST_LOW",
                status=STATUS_PASS,
                expected="普通文字 ≥ 4.5:1，大字号 ≥ 3:1",
                actual=f"{sampled} 个文本节点对比度达标",
                severity="major",
            )
        ]
    confirmed = [item for item in weak if item["status"] == STATUS_FAIL]
    status = STATUS_FAIL if confirmed else STATUS_PENDING
    return [
        RuleResult(
            rule="VIS.CONTRAST_LOW",
            status=status,
            expected="普通文字 ≥ 4.5:1，大字号 ≥ 3:1",
            actual=f"{len(weak)} 个文本节点对比度偏低",
            severity="major",
            evidence={"nodes": weak[:10]},
        )
    ]


def _pixel_scales(
    surface: dict[str, Any] | None,
    width: int,
    height: int,
    fallback: float,
) -> tuple[float, float]:
    """按截图像素与画布 CSS 尺寸推算真实的横纵采样倍率。"""
    if isinstance(surface, dict):
        css_width = float(surface.get("width") or 0)
        css_height = float(surface.get("height") or 0)
        if css_width > 0 and css_height > 0:
            return width / css_width, height / css_height
    return fallback, fallback


def _contrast_sample(
    node: dict[str, Any],
    image: Any,
    width: int,
    height: int,
    scale_x: float,
    scale_y: float,
) -> dict[str, Any] | None:
    color = _parse_css_color((node.get("style") or {}).get("color"))
    box = node.get("box")
    if color is None or not isinstance(box, dict):
        return None
    size = _font_size(node)
    if size is None:
        return None
    left = int(max(0, box.get("x", 0) * scale_x))
    top = int(max(0, box.get("y", 0) * scale_y))
    right = int(min(width, (box.get("x", 0) + box.get("width", 0)) * scale_x))
    bottom = int(min(height, (box.get("y", 0) + box.get("height", 0)) * scale_y))
    if right - left < 6 or bottom - top < 6:
        return None
    raw = image.crop((left, top, right, bottom)).tobytes()
    pixels = []
    for index in range(0, len(raw), 3):
        pixels.append((raw[index], raw[index + 1], raw[index + 2]))
    background, variance = _background_estimate(pixels)
    if background is None:
        return None
    composite = _composite(color, background)
    ratio = _contrast_ratio(_luminance(composite), _luminance(background))
    threshold = CONTRAST_MIN_LARGE if _is_large_text(node, size) else CONTRAST_MIN
    if variance > 42:
        return {
            "id": node.get("id"),
            "ratio": round(ratio, 2),
            "status": STATUS_PENDING,
            "reason": "背景纹理复杂，需人工复核",
            "variance": round(variance, 1),
        }
    status = STATUS_FAIL if ratio < threshold * 0.9 else STATUS_PASS
    if status == STATUS_PASS:
        return None
    return {
        "id": node.get("id"),
        "ratio": round(ratio, 2),
        "threshold": threshold,
        "status": status,
        "variance": round(variance, 1),
    }


def _background_estimate(pixels: list[Any]) -> tuple[tuple[float, float, float] | None, float]:
    if not pixels:
        return None, 0.0
    luminances = [_luminance((pixel[0], pixel[1], pixel[2])) for pixel in pixels]
    ordered = sorted(luminances)
    median = ordered[len(ordered) // 2]
    mean = sum(luminances) / len(luminances)
    variance = sum((item - mean) ** 2 for item in luminances) / len(luminances)
    bright = [pixel for pixel in pixels if _luminance(pixel[:3]) >= median]
    dark = [pixel for pixel in pixels if _luminance(pixel[:3]) < median]
    pool = bright if len(bright) >= len(dark) else dark
    if not pool:
        return None, variance
    red = sum(pixel[0] for pixel in pool) / len(pool)
    green = sum(pixel[1] for pixel in pool) / len(pool)
    blue = sum(pixel[2] for pixel in pool) / len(pool)
    return (red, green, blue), variance ** 0.5


def _is_large_text(node: dict[str, Any], size: float) -> bool:
    style = node.get("style")
    weight = 400
    if isinstance(style, dict):
        try:
            weight = int(float(str(style.get("fontWeight") or 400)))
        except ValueError:
            weight = 400
    if size >= LARGE_TEXT_SIZE:
        return True
    return size >= LARGE_TEXT_BOLD_SIZE and weight >= LARGE_TEXT_BOLD_WEIGHT


def _parse_css_color(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?\s*\)",
        value.strip(),
    )
    if match is None:
        return None
    alpha = float(match.group(4)) if match.group(4) is not None else 1.0
    return (
        float(match.group(1)),
        float(match.group(2)),
        float(match.group(3)),
        alpha,
    )


def _composite(
    foreground: tuple[float, float, float, float],
    background: tuple[float, float, float],
) -> tuple[float, float, float]:
    alpha = max(0.0, min(1.0, foreground[3]))
    return (
        foreground[0] * alpha + background[0] * (1 - alpha),
        foreground[1] * alpha + background[1] * (1 - alpha),
        foreground[2] * alpha + background[2] * (1 - alpha),
    )


def _luminance(color: tuple[float, float, float]) -> float:
    channels = []
    for value in color:
        channel = value / 255.0
        if channel <= 0.03928:
            channels.append(channel / 12.92)
        else:
            channels.append(((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(first: float, second: float) -> float:
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _safe_area_results(
    evidence: dict[str, Any],
    nodes: list[dict[str, Any]],
) -> list[RuleResult]:
    surface = evidence.get("surface")
    if not isinstance(surface, dict):
        return []
    width = float(surface.get("width") or 0)
    height = float(surface.get("height") or 0)
    if width <= 0 or height <= 0:
        return []
    overflow_ids = _overflow_text_node_ids(evidence)
    outside: list[dict[str, Any]] = []
    skipped: list[str] = []
    for node in nodes:
        box = node.get("box")
        if not isinstance(box, dict):
            continue
        node_id = str(node.get("id") or "")
        x = float(box.get("x") or 0)
        y = float(box.get("y") or 0)
        right = x + float(box.get("width") or 0)
        bottom = y + float(box.get("height") or 0)
        if (
            x < SAFE_AREA_INSET - SAFE_AREA_TOLERANCE
            or y < SAFE_AREA_INSET - SAFE_AREA_TOLERANCE
            or right > width - SAFE_AREA_INSET + SAFE_AREA_TOLERANCE
            or bottom > height - SAFE_AREA_INSET + SAFE_AREA_TOLERANCE
        ):
            if node_id in overflow_ids:
                skipped.append(node_id)
                continue
            outside.append({"id": node.get("id"), "box": box})
    status = STATUS_PASS if not outside else STATUS_FAIL
    return [
        RuleResult(
            rule="SPEC.SAFE_AREA",
            status=status,
            expected="全部文本在 inset(12) 内",
            actual="全部在安全区" if not outside else f"{len(outside)} 个文本节点越界",
            severity="major",
            evidence={
                "outside": outside[:10],
                "surface": surface,
                "skippedOverflow": skipped[:10],
            },
        )
    ]


def _overflow_text_node_ids(evidence: dict[str, Any]) -> set[str]:
    """已被 ``VIS.TEXT_OVERFLOW`` 计分的节点不再计入安全区，避免同因双扣。"""
    quality = evidence.get("webQuality")
    if not isinstance(quality, dict):
        return set()
    findings = quality.get("findings")
    if not isinstance(findings, list):
        return set()
    ids: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if str(finding.get("rule_id") or "") != "GEOMETRY.OVERFLOW_TEXT":
            continue
        value = finding.get("evidence")
        if isinstance(value, dict):
            component = value.get("component")
            if isinstance(component, str) and component:
                ids.add(component)
        components = finding.get("components")
        if isinstance(components, list):
            for item in components:
                if isinstance(item, str) and item:
                    ids.add(item.split(":", 1)[0])
    return ids


def _asset_results(
    evidence: dict[str, Any],
    resource_root: Path | None,
) -> list[RuleResult]:
    if resource_root is None:
        return []
    nodes = evidence.get("nodes")
    if not isinstance(nodes, list):
        return []
    assets: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        image = node.get("image")
        if not isinstance(image, dict):
            continue
        relative = _local_asset_relative(image.get("src"))
        if relative is None:
            continue
        assets.setdefault(relative, []).append(image)
    if not assets:
        return []
    missing = sorted(
        src for src in assets if not (resource_root / src).is_file()
    )
    broken = sorted(src for src in assets if _asset_broken(assets[src]))
    results: list[RuleResult] = [
        RuleResult(
            rule="ASSET.FILE_MISSING",
            status=STATUS_PASS if not missing else STATUS_FAIL,
            expected="本地素材文件存在",
            actual=(
                f"{len(assets)} 个本地素材均已找到"
                if not missing
                else f"{len(missing)} 个素材文件缺失"
            ),
            severity="major",
            evidence={"missing": missing[:10]} if missing else {},
        ),
        RuleResult(
            rule="ASSET.RENDERED",
            status=STATUS_PASS if not broken else STATUS_FAIL,
            expected="本地素材已加载并输出可见像素",
            actual=(
                f"{len(assets)} 个本地素材均已渲染"
                if not broken
                else f"{len(broken)} 个素材未渲染"
            ),
            severity="major",
            evidence={"broken": broken[:10]} if broken else {},
        ),
    ]
    return results


def _local_asset_relative(src: Any) -> str | None:
    """只统计挂载到本地 resources 的素材；远程主题图不进入本地素材门禁。"""
    if not isinstance(src, str):
        return None
    value = src.removeprefix("/")
    if not value.startswith("resources/"):
        return None
    return value.removeprefix("resources/")


def _asset_broken(images: list[dict[str, Any]]) -> bool:
    for image in images:
        width = image.get("naturalWidth")
        height = image.get("naturalHeight")
        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            if width > 0 and height > 0 and image.get("complete") is not False:
                return False
    return True


def _pattern_pitch_results(evidence: dict[str, Any], size: str) -> list[RuleResult]:
    """图案间距只做诊断：数量在 te_spec 计分，间距偏离只记为不适用。"""
    nodes = evidence.get("nodes")
    if not isinstance(nodes, list):
        return []
    bars: list[dict[str, Any]] = []
    dots: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("visible") is False:
            continue
        box = node.get("box")
        if not isinstance(box, dict):
            continue
        width = _as_number(box.get("width"))
        height = _as_number(box.get("height"))
        if width is None or height is None:
            continue
        if abs(width - 10.0) <= 0.5 and abs(height - 60.0) <= 0.5:
            bars.append(node)
        elif abs(width - 8.0) <= 0.5 and abs(height - 8.0) <= 0.5:
            dots.append(node)
    if not bars and not dots:
        return []
    if bars:
        expected = BAR_PITCH.get(size, BAR_PITCH["2x2"])
        actual = _bar_pitch(bars)
        label = "柱体间距"
    else:
        expected = DOT_COL_PITCH.get(size, DOT_COL_PITCH["2x2"])
        actual = _dot_col_pitch(dots)
        label = "圆球列距"
    if actual is None:
        return [
            RuleResult(
                rule="SPEC.PATTERN_PITCH",
                status=STATUS_NA,
                expected=f"{label} {expected:g}",
                actual="图案不足两个，无法测量间距",
                severity="minor",
            )
        ]
    passed = abs(actual - expected) <= PATTERN_TOLERANCE
    return [
        RuleResult(
            rule="SPEC.PATTERN_PITCH",
            status=STATUS_PASS if passed else STATUS_NA,
            expected=f"{label} {expected:g}±{PATTERN_TOLERANCE:g}",
            actual=f"{label} {actual:.2f}",
            severity="minor",
            evidence={"size": size, "bars": len(bars), "dots": len(dots)},
        )
    ]


def _bar_pitch(bars: list[dict[str, Any]]) -> float | None:
    rows: dict[float, list[float]] = {}
    for node in bars:
        box = node.get("box") or {}
        y = _as_number(box.get("y"))
        x = _as_number(box.get("x"))
        if y is None or x is None:
            continue
        rows.setdefault(round(y, 1), []).append(x)
    pitches: list[float] = []
    for xs in rows.values():
        xs.sort()
        pitches.extend(xs[index + 1] - xs[index] for index in range(len(xs) - 1))
    return _median(pitches)


def _dot_col_pitch(dots: list[dict[str, Any]]) -> float | None:
    xs: set[float] = set()
    for node in dots:
        box = node.get("box") or {}
        x = _as_number(box.get("x"))
        if x is not None:
            xs.add(round(x, 1))
    ordered = sorted(xs)
    pitches = [
        ordered[index + 1] - ordered[index] for index in range(len(ordered) - 1)
    ]
    return _median(pitches)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _unit_baseline_results(nodes: list[dict[str, Any]]) -> list[RuleResult]:
    """数字与单位应同行基线对齐；只做诊断，不参与计分。"""
    days = _primary_number_node(nodes)
    units = [
        node
        for node in nodes
        if _unit_text(normalize_text(node.get("text"))) is not None
    ]
    if days is None or not units:
        return [
            RuleResult(
                rule="SPEC.UNIT_BASELINE",
                status=STATUS_NA,
                expected="数字与单位同行基线对齐",
                actual="无数字 + 单位组合",
                severity="minor",
            )
        ]
    baseline = _text_baseline(days)
    if baseline is None:
        return [
            RuleResult(
                rule="SPEC.UNIT_BASELINE",
                status=STATUS_NA,
                expected="数字与单位同行基线对齐",
                actual="缺少行高证据，无法测量基线",
                severity="minor",
            )
        ]
    offsets: list[dict[str, Any]] = []
    for node in units:
        unit_baseline = _text_baseline(node)
        if unit_baseline is None:
            continue
        offsets.append(
            {
                "id": node.get("id"),
                "diff": round(unit_baseline - baseline, 2),
            }
        )
    if not offsets:
        return [
            RuleResult(
                rule="SPEC.UNIT_BASELINE",
                status=STATUS_NA,
                expected="数字与单位同行基线对齐",
                actual="单位缺少行高证据",
                severity="minor",
            )
        ]
    worst = max(offsets, key=lambda item: abs(float(item["diff"])))
    passed = abs(float(worst["diff"])) <= BASELINE_TOLERANCE
    return [
        RuleResult(
            rule="SPEC.UNIT_BASELINE",
            status=STATUS_PASS if passed else STATUS_NA,
            expected=f"基线差 ≤ {BASELINE_TOLERANCE:g}",
            actual=f"最大基线差 {worst['diff']}",
            severity="minor",
            evidence={"units": offsets[:6]},
        )
    ]


def _primary_number_node(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    primary = None
    primary_size = -1.0
    for node in nodes:
        text = normalize_text(node.get("text"))
        if not re.fullmatch(r"\d+", text):
            continue
        size = _font_size(node)
        if size is not None and size > primary_size:
            primary = node
            primary_size = size
    return primary


def _unit_text(text: str) -> str | None:
    if not text:
        return None
    if text in UNIT_WORDS:
        return text
    tail = re.sub(r"^[\d\s]+", "", text)
    return tail if tail in UNIT_WORDS else None


def _text_baseline(node: dict[str, Any]) -> float | None:
    box = node.get("box")
    style = node.get("style")
    if not isinstance(box, dict) or not isinstance(style, dict):
        return None
    y = _as_number(box.get("y"))
    font = _as_number(style.get("fontSize"))
    if y is None or font is None:
        return None
    line_height = _as_number(style.get("lineHeight"))
    if line_height is None or line_height <= 0:
        line_height = font * 1.4
    return y + line_height / 2 + font * 0.4


def _as_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _layout_metrics(evidence: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    surface = evidence.get("surface") if isinstance(evidence.get("surface"), dict) else {}
    area = float(surface.get("width") or 0) * float(surface.get("height") or 0)
    primary = None
    for node in nodes:
        size = _font_size(node)
        if size is None:
            continue
        if primary is None or size > primary["fontSize"]:
            box = node.get("box") if isinstance(node.get("box"), dict) else {}
            primary = {
                "id": node.get("id"),
                "fontSize": size,
                "text": normalize_text(node.get("text"))[:20],
                "areaRatio": round(
                    (float(box.get("width") or 0) * float(box.get("height") or 0)) / area, 4
                )
                if area > 0
                else None,
            }
    icons = []
    nodes_all = evidence.get("nodes")
    if isinstance(nodes_all, list):
        for node in nodes_all:
            if not isinstance(node, dict):
                continue
            image = node.get("image")
            if isinstance(image, dict):
                icons.append(
                    {
                        "id": node.get("id"),
                        "src": image.get("src"),
                        "naturalWidth": image.get("naturalWidth"),
                    }
                )
    return {
        "primary": primary,
        "fontSizes": sorted({_font_size(node) for node in nodes if _font_size(node)}),
        "icons": icons,
        "leafTextCount": len(nodes),
    }
