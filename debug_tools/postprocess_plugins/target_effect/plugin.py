"""倒计时目标效果评测后处理插件。

纯规则判定：L0 产物与渲染、L2 可见性、倒计时规范符合性。评分只由规范符合
（60）与可见性（40）构成；版式与素材规则只做诊断，不影响分数与结论。
不做期望图与模型渲染的视觉比对。模型不参与判定。

浏览器采集只在 process_dataset 执行一次；finalize 负责把结论与证据
并入样本产物，供看板评分卡和独立样本详情页直接使用。
"""

from __future__ import annotations

import asyncio
import html
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent
DEBUG_TOOLS_ROOT = PLUGIN_DIR.parents[1]
RESOURCE_ROOT = DEBUG_TOOLS_ROOT / "a2ui_render" / "entry" / "src" / "main" / "resources"
CAPTURE_SCRIPT = DEBUG_TOOLS_ROOT / "scripts" / "capture_target_effect.mjs"
_THEME_REGISTRY_OVERRIDE = os.environ.get("DEBUG_TOOLS_THEME_REGISTRY", "").strip()
THEME_REGISTRY_PATH = (
    Path(_THEME_REGISTRY_OVERRIDE)
    if _THEME_REGISTRY_OVERRIDE
    else DEBUG_TOOLS_ROOT.parent / "widget_service" / "cloud" / "data" / "post_layout_themes.json"
)
_THEME_REGISTRY: dict[str, dict[str, Any]] | None = None


def _load_sibling(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载插件模块：{name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


te_genui = _load_sibling("te_genui")
te_rules = _load_sibling("te_rules")
te_spec = _load_sibling("te_spec")
te_layout = _load_sibling("te_layout")
te_dom = _load_sibling("te_dom")
te_score = _load_sibling("te_score")

PASS = te_rules.STATUS_PASS
FAIL = te_rules.STATUS_FAIL
PENDING = te_rules.STATUS_PENDING
NA = te_rules.STATUS_NA
CAPTURE_FAILED_RULE = "L0.CAPTURE_FAILED"

RULE_ORDER = [
    "L0.RESULT_STATUS",
    "L0.ARTIFACT_MISSING",
    "L0.PARSE_FAILED",
    "VIS.TEXT_CLIPPED",
    "VIS.TEXT_OVERFLOW",
    "VIS.TEXT_OVERLAP",
    "VIS.IMAGE_OVERFLOW",
    "VIS.IMAGE_LOAD_FAILED",
    "VIS.FONT_TOO_SMALL",
    "VIS.CONTRAST_LOW",
    "VIS.EVIDENCE_MISSING",
    "LAYOUT.CARD_OVERFLOW",
    "LAYOUT.PARENT_CLIP",
    "LAYOUT.SIBLING_OVERLAP",
    "ASSET.FILE_MISSING",
    "ASSET.RENDERED",
    "SPEC.THEME_ELIGIBLE",
    "SPEC.RADIUS",
    "SPEC.CLIP",
    "SPEC.PADDING",
    "SPEC.BG_FULL_BLEED",
    "SPEC.BG_SINGLE",
    "SPEC.BG_FIT",
    "SPEC.MASK",
    "SPEC.TITLE_REQUIRED",
    "SPEC.TITLE_FONT",
    "SPEC.TITLE_ELLIPSIS",
    "SPEC.TITLE_COLOR",
    "SPEC.PRIMARY_FONT",
    "SPEC.PRIMARY_COLOR",
    "SPEC.UNIT_FONT",
    "SPEC.UNIT_COLOR",
    "SPEC.SUPPORT_FONT",
    "SPEC.SUPPORT_COLOR",
    "SPEC.CONTENT_TYPE",
    "SPEC.PATTERN_GEOMETRY",
    "SPEC.DIGIT_LIMIT",
    "SPEC.ICON",
    "SPEC.ACTION_PATTERN",
    "SPEC.PATTERN_PITCH",
    "SPEC.UNIT_BASELINE",
    "SPEC.SAFE_AREA",
    "SPEC.USER_PREFERENCE",
]
RULE_TITLES = {
    "L0.RESULT_STATUS": "样本执行状态",
    "L0.ARTIFACT_MISSING": "可渲染产物存在",
    "L0.PARSE_FAILED": "A2UI 解析",
    "VIS.TEXT_CLIPPED": "文字未被裁切",
    "VIS.TEXT_OVERFLOW": "文字未越出画布",
    "VIS.TEXT_OVERLAP": "文字未互相遮挡",
    "VIS.IMAGE_OVERFLOW": "图片未越出画布",
    "VIS.IMAGE_LOAD_FAILED": "素材真实加载",
    "VIS.FONT_TOO_SMALL": "正文字号下限",
    "VIS.CONTRAST_LOW": "文字对比度",
    "VIS.EVIDENCE_MISSING": "可见性证据完整",
    "LAYOUT.CARD_OVERFLOW": "内容未越出卡片画布",
    "LAYOUT.PARENT_CLIP": "内容未被父容器裁切",
    "LAYOUT.SIBLING_OVERLAP": "兄弟节点未互相遮挡",
    "ASSET.FILE_MISSING": "本地素材文件存在",
    "ASSET.RENDERED": "素材真实渲染",
    "SPEC.THEME_ELIGIBLE": "主题属于图+蒙层路线",
    "SPEC.RADIUS": "圆角 20",
    "SPEC.CLIP": "内容不越出圆角",
    "SPEC.PADDING": "内边距 12",
    "SPEC.BG_FULL_BLEED": "背景铺满",
    "SPEC.BG_SINGLE": "背景图唯一",
    "SPEC.BG_FIT": "背景填充方式",
    "SPEC.MASK": "黑色蒙层 60%",
    "SPEC.TITLE_REQUIRED": "标题必选",
    "SPEC.TITLE_FONT": "标题 16/20fp",
    "SPEC.TITLE_ELLIPSIS": "标题单行省略",
    "SPEC.TITLE_COLOR": "标题白色",
    "SPEC.PRIMARY_FONT": "主值 56/38fp",
    "SPEC.PRIMARY_COLOR": "主数字白色",
    "SPEC.UNIT_FONT": "单位 16fp 独立",
    "SPEC.UNIT_COLOR": "单位 60% 白",
    "SPEC.SUPPORT_FONT": "副文本 16fp",
    "SPEC.SUPPORT_COLOR": "副文本 60% 白",
    "SPEC.CONTENT_TYPE": "内容属于 C1–C5",
    "SPEC.PATTERN_GEOMETRY": "图案数量",
    "SPEC.DIGIT_LIMIT": "数字最多 6 位",
    "SPEC.ICON": "图标规格",
    "SPEC.ACTION_PATTERN": "整卡点击",
    "SPEC.PATTERN_PITCH": "图案间距",
    "SPEC.UNIT_BASELINE": "数字单位基线",
    "SPEC.SAFE_AREA": "安全区内",
    "SPEC.USER_PREFERENCE": "用户样式偏好",
}
RULE_HINTS = {
    "L0.RESULT_STATUS": "样本本身执行成功，才继续评分",
    "L0.ARTIFACT_MISSING": "存在可渲染的最终卡片产物",
    "L0.PARSE_FAILED": "A2UI 能被解析成组件树",
    "VIS.TEXT_CLIPPED": "文字没有被容器裁切或省略",
    "VIS.TEXT_OVERFLOW": "文字没有越出卡片边界",
    "VIS.TEXT_OVERLAP": "文字之间没有互相遮挡",
    "VIS.IMAGE_OVERFLOW": "图标或图片没有越出卡片边界",
    "VIS.IMAGE_LOAD_FAILED": "图片资源在渲染时真实加载成功",
    "VIS.FONT_TOO_SMALL": "正文字号不低于可读下限",
    "VIS.CONTRAST_LOW": "正文对比度不低于 4.5:1，大字不低于 3:1",
    "VIS.EVIDENCE_MISSING": "DOM 与截图证据完整，能支撑可见性判定",
    "LAYOUT.CARD_OVERFLOW": "可见节点的内容矩形不越出卡片画布；只做诊断，不计分",
    "LAYOUT.PARENT_CLIP": "非文本节点不被中间容器裁切；只做诊断，不计分",
    "LAYOUT.SIBLING_OVERLAP": "同一父容器内的图文兄弟节点不互相遮挡；只做诊断，不计分",
    "ASSET.FILE_MISSING": "卡片引用的本地素材文件存在",
    "ASSET.RENDERED": "素材在 3x 渲染截图中真实绘制",
    "SPEC.THEME_ELIGIBLE": "主题属于 Pixso 图 + 黑蒙层路线；融球、渐变、纯色和黑字主题不计入规范分",
    "SPEC.RADIUS": "卡片圆角为 20",
    "SPEC.CLIP": "内容区开启裁切，不越出 20 圆角",
    "SPEC.PADDING": "内容区距卡片边缘 12",
    "SPEC.BG_FULL_BLEED": "背景图铺满整卡，四周不留边",
    "SPEC.BG_SINGLE": "整卡只有一张全屏背景图，避免叠图发灰",
    "SPEC.BG_FIT": "背景填充方式（fill/cover），其余仅诊断",
    "SPEC.MASK": "背景图上覆盖 60%（55%–70%）黑色蒙层，位于背景与内容之间",
    "SPEC.TITLE_REQUIRED": "卡片必须带标题",
    "SPEC.TITLE_FONT": "标题为 T1–T4：主标题 16 或 20fp，副标题 16fp",
    "SPEC.TITLE_ELLIPSIS": "主副标题都最多一行，超出用省略号",
    "SPEC.TITLE_COLOR": "主标题 100% 纯白，副标题 60% 白",
    "SPEC.PRIMARY_FONT": "倒计时主数字字号：C1 为 56fp，C3 为 38fp，长数字最小 29fp",
    "SPEC.PRIMARY_COLOR": "主数字为白色（100% 或 90%）",
    "SPEC.UNIT_FONT": "“天 / 小时”等单位单独成文本，字号 16fp",
    "SPEC.UNIT_COLOR": "单位为 60% 白色",
    "SPEC.SUPPORT_FONT": "日期、说明等副文本字号 16fp",
    "SPEC.SUPPORT_COLOR": "副文本为 60% 白色",
    "SPEC.CONTENT_TYPE": "内容属于规范允许的 C1–C5，且数字与图案不并存",
    "SPEC.PATTERN_GEOMETRY": "图案数量暂不判定：只记录数量；圆点=当月天数、柱体=一周天数，待确认",
    "SPEC.DIGIT_LIMIT": "主数字最多 6 位",
    "SPEC.ICON": "图标不超过 20×20 且为白色；只做诊断，不计分",
    "SPEC.ACTION_PATTERN": "整卡点击，不放独立按钮",
    "SPEC.PATTERN_PITCH": "图案间距只做诊断：柱距 19.34/33.25，圆球列距 10.7/11.16",
    "SPEC.UNIT_BASELINE": "数字与单位同行基线对齐；只做诊断，不计分",
    "SPEC.SAFE_AREA": "内容全部落在安全区内",
    "SPEC.USER_PREFERENCE": "用户显式要求背景、配色或字号时，冲突规范项豁免而不是判失败",
}


# ---------------------------------------------------------------- 公共工具


def _config(context: dict[str, Any]) -> dict[str, Any]:
    value = context.get("config")
    return value if isinstance(value, dict) else {}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- 主题与偏好


def _theme_registry() -> dict[str, dict[str, Any]]:
    global _THEME_REGISTRY
    if _THEME_REGISTRY is None:
        _THEME_REGISTRY = _load_theme_registry(THEME_REGISTRY_PATH)
    return _THEME_REGISTRY


def _load_theme_registry(path: Path) -> dict[str, dict[str, Any]]:
    value = _read_json(path)
    themes = value.get("themes") if isinstance(value, dict) else None
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(themes, list):
        return index
    for theme in themes:
        if not isinstance(theme, dict):
            continue
        theme_id = theme.get("id")
        if isinstance(theme_id, str) and theme_id:
            index[theme_id] = theme
    return index


def _theme_profile(theme_id: str) -> dict[str, Any] | None:
    """把主题登记表条目折算成规范路线判定；未登记主题不阻断规则。"""
    if not theme_id:
        return None
    theme = _theme_registry().get(theme_id)
    if theme is None:
        return {
            "id": theme_id,
            "kind": "unknown",
            "eligible": None,
            "reason": "主题未登记，按图+蒙层路线评估",
        }
    kind = str(theme.get("kind") or "")
    background = theme.get("background")
    background = background if isinstance(background, dict) else {}
    content = theme.get("content")
    roles = content.get("roles") if isinstance(content, dict) else None
    roles = roles if isinstance(roles, dict) else {}
    has_image = bool(background.get("src") or background.get("remoteUrl"))
    profile = {
        "id": theme_id,
        "name": str(theme.get("name") or ""),
        "kind": kind,
        "eligible": None,
        "reason": "",
    }
    if kind == "photo" and has_image and _is_white_primary(roles.get("primary")):
        profile["eligible"] = True
        profile["reason"] = ""
        return profile
    profile["eligible"] = False
    profile["reason"] = f"{_theme_ineligible_reason(kind, has_image)}，规范维度不计分"
    return profile


def _spec_progress(results: list[Any], theme: dict[str, Any] | None) -> str:
    """规范布局进度：只统计参与计分的 SPEC 规则，主题不适用时直接标记。"""
    if theme is not None and theme.get("eligible") is False:
        return "不适用"
    checked = [
        item
        for item in results
        if item.rule.startswith("SPEC.")
        and item.rule not in te_score.DIAGNOSTIC_RULES
        and item.status in {PASS, FAIL, PENDING}
    ]
    if not checked:
        return "不适用"
    passed = sum(1 for item in checked if item.status == PASS)
    return f"{passed}/{len(checked)} 项通过"


def _theme_text(theme: dict[str, Any] | None) -> str:
    if not theme:
        return "未识别"
    label = str(theme.get("name") or theme.get("id") or "未识别")
    kind = str(theme.get("kind") or "unknown")
    if theme.get("eligible") is True:
        route = "图+蒙层"
    elif theme.get("eligible") is False:
        route = "非 Pixso 路线"
    else:
        route = "未登记"
    return f"{label}（{kind} · {route}）"


def _theme_ineligible_reason(kind: str, has_image: bool) -> str:
    if kind == "photo" and not has_image:
        return "照片主题缺少背景图"
    if kind == "photo":
        return "照片主题使用黑色文字，不是图+白字+蒙层路线"
    if kind == "fusion":
        return "融球主题不是 Pixso 图+蒙层路线"
    if kind == "gradient":
        return "渐变主题不是 Pixso 图+蒙层路线"
    if kind == "solid":
        return "纯色主题不是 Pixso 图+蒙层路线"
    return f"主题类型 {kind or 'unknown'} 不是 Pixso 图+蒙层路线"


def _is_white_primary(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lstrip("#").upper()
    try:
        if len(text) == 8:
            alpha = int(text[:2], 16) / 255.0
            return alpha >= 0.9 and text[2:] == "FFFFFF"
        if len(text) == 6:
            return text == "FFFFFF"
    except ValueError:
        return False
    return False


def _extract_theme_id(final_dir: Path, components: dict[str, Any]) -> str:
    """主题 ID 优先取 taskspec 候选素材，其次按背景图地址回查登记表。"""
    index = _theme_registry()
    if not index:
        return ""
    blocks = _read_json(final_dir / "blocks.json") or {}
    taskspec = blocks.get("taskspec")
    taskspec = taskspec if isinstance(taskspec, dict) else {}
    candidates = taskspec.get("assetCandidates")
    if isinstance(candidates, list):
        for item in candidates:
            if not isinstance(item, dict):
                continue
            theme_id = item.get("id")
            if isinstance(theme_id, str) and theme_id in index:
                return theme_id
        for item in candidates:
            if not isinstance(item, dict):
                continue
            matched = _match_theme_src(index, item.get("src"))
            if matched:
                return matched
    for component in components.values():
        if not isinstance(component, dict) or component.get("component") != "Image":
            continue
        matched = _match_theme_src(index, component.get("src"))
        if matched:
            return matched
    return ""


def _match_theme_src(index: dict[str, dict[str, Any]], src: Any) -> str:
    if not isinstance(src, str) or not src:
        return ""
    for theme_id, theme in index.items():
        background = theme.get("background")
        if not isinstance(background, dict):
            continue
        if src in (background.get("remoteUrl"), background.get("src")):
            return theme_id
    return ""


def _extract_user_query(sample: dict[str, Any], final_dir: Path) -> str:
    """用户原话用于判断显式样式偏好；取不到时不影响规范判定。"""
    value = sample.get("query")
    if isinstance(value, str) and value.strip():
        return value.strip()
    request = _read_json(final_dir / "request.json") or {}
    query = _request_query(request)
    if query:
        return query
    blocks = _read_json(final_dir / "blocks.json") or {}
    taskspec = blocks.get("taskspec")
    if isinstance(taskspec, dict):
        query = taskspec.get("userQuery")
        if isinstance(query, str) and query.strip():
            return query.strip()
    return ""


def _request_query(request: dict[str, Any]) -> str:
    for key in ("userQuery", "description", "content", "query"):
        value = request.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    utterance = request.get("utterance")
    if isinstance(utterance, dict):
        for key in ("original", "query", "text"):
            value = utterance.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _result_from_dict(value: dict[str, Any]) -> Any:
    return te_spec.RuleResult(
        rule=str(value.get("rule") or ""),
        status=str(value.get("status") or NA),
        expected=str(value.get("expected") or ""),
        actual=str(value.get("actual") or ""),
        severity=str(value.get("severity") or "major"),
        evidence=dict(value.get("evidence") or {}),
    )


def _issue_row(result: Any, deductions: dict[str, float] | None = None) -> dict[str, Any]:
    return {
        "规则": result.rule,
        "说明": RULE_TITLES.get(result.rule, result.rule),
        "状态": "失败" if result.status == FAIL else "待复核",
        "扣分": (deductions or {}).get(result.rule, "—"),
        "预期": result.expected,
        "实际": result.actual,
        "证据": _compact(result.evidence),
    }


def _rule_deductions(score: dict[str, Any]) -> dict[str, float]:
    """按规则汇总扣分，供失败明细表直接展示，避免再重复一张分数卡。"""
    mapping: dict[str, float] = {}
    for dimension in score.get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        for item in dimension.get("items") or []:
            if not isinstance(item, dict):
                continue
            rule = str(item.get("rule") or "")
            value = item.get("deduction")
            if not rule or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            mapping[rule] = round(float(value), 1)
    return mapping


def _compact(value: Any, limit: int = 600) -> Any:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)[:limit]
    if len(text) <= limit:
        return value
    return text[:limit] + "…"


def _is_diagnostic_rule_name(rule: str) -> bool:
    return rule.startswith("LAYOUT.")


def _is_diagnostic_rule(item: Any) -> bool:
    """版式诊断只做观察，不影响评分、样本状态与结论。"""
    return _is_diagnostic_rule_name(str(item.rule))


def _is_scored_rule(rule: str) -> bool:
    """只有 VIS/SPEC 中非诊断规则进入评分与整批规则通过率。"""
    if rule in te_score.DIAGNOSTIC_RULES:
        return False
    return rule.startswith("VIS.") or rule.startswith("SPEC.")


def _blocking_results(results: list[Any]) -> list[Any]:
    blocked: list[Any] = []
    for item in results:
        if item.status not in {FAIL, PENDING}:
            continue
        if _is_diagnostic_rule(item):
            continue
        blocked.append(item)
    return blocked


def _sample_status(results: list[Any]) -> str:
    major = [
        item
        for item in results
        if item.status == FAIL and item.severity == "major" and not _is_diagnostic_rule(item)
    ]
    if major:
        return "failed"
    if _blocking_results(results):
        return "partial"
    return "success"


def _verdict_text(results: list[Any]) -> str:
    major = [
        item
        for item in results
        if item.status == FAIL and item.severity == "major" and not _is_diagnostic_rule(item)
    ]
    minor = [
        item
        for item in results
        if item.status == FAIL and item.severity != "major" and not _is_diagnostic_rule(item)
    ]
    pending = [item for item in _blocking_results(results) if item.status == PENDING]
    if any(item.rule.startswith("L0.") for item in major):
        return "L0 失败"
    if any(item.rule.startswith("VIS.") for item in major):
        return "可见性失败"
    if any(item.rule.startswith("SPEC.") for item in major):
        return "规范失败"
    if minor or pending:
        return "待复核"
    return "通过"


def _counts(results: list[Any]) -> dict[str, int]:
    scored = [item for item in results if not _is_diagnostic_rule(item)]
    return {
        "passed": sum(1 for item in scored if item.status == PASS),
        "failed": sum(1 for item in scored if item.status == FAIL),
        "pending": sum(1 for item in scored if item.status == PENDING),
        "na": sum(1 for item in scored if item.status == NA),
    }


def _issue_results(results: list[Any]) -> list[Any]:
    """失败与待复核项只展示参与评分的规则，诊断项留在完整结果里。"""
    return [
        item
        for item in results
        if item.status in {FAIL, PENDING} and not _is_diagnostic_rule(item)
    ]


# ---------------------------------------------------------------- process_sample


def process_sample(context: dict[str, Any]) -> dict[str, Any]:
    sample = context.get("sample")
    sample = sample if isinstance(sample, dict) else {}
    sample_id = str(sample.get("id") or "")
    size = str(sample.get("size") or te_rules.DEFAULT_SIZE)
    output_dir = Path(str(context.get("outputDir") or "."))
    output_dir.mkdir(parents=True, exist_ok=True)
    final_dir_value = context.get("finalAttemptDir")
    if not final_dir_value:
        return _l0_failure(output_dir, sample_id, "没有最终尝试目录")
    final_dir = Path(str(final_dir_value))
    genui_path = final_dir / "genui.jsonl"
    if not genui_path.is_file():
        return _l0_failure(output_dir, sample_id, "最终尝试缺少 genui.jsonl")
    source = genui_path.read_text(encoding="utf-8")
    parsed = te_genui.parse_genui(source)
    if not parsed.get("components"):
        return _l0_failure(output_dir, sample_id, "未解析到 A2UI 组件")
    theme_id = _extract_theme_id(final_dir, parsed["components"])
    theme = _theme_profile(theme_id)
    user_query = _extract_user_query(sample, final_dir)
    spec_results = te_spec.evaluate_spec(
        parsed["components"],
        parsed["data"],
        size=size,
        theme=theme,
        user_query=user_query,
    )
    static = {
        "sampleId": sample_id,
        "size": size,
        "rubricVersion": te_spec.RUBRIC_VERSION,
        "genuiPath": str(genui_path),
        "theme": theme,
        "userQuery": user_query,
        "spec": [item.as_dict() for item in spec_results],
    }
    _write_json(output_dir / "sample_static.json", static)
    results = list(spec_results)
    status = _sample_status(results)
    counts = _counts(results)
    verdict = _verdict_text(results)
    issues = _issue_results(results)
    theme_text = _theme_text(theme)
    return {
        "status": status,
        "summary": verdict,
        "facts": {
            "verdict": verdict,
            "theme": theme_text,
            "size": size,
            "specApplicable": not (theme is not None and theme.get("eligible") is False),
            "passed": counts["passed"],
            "failed": counts["failed"],
            "pending": counts["pending"],
        },
        "artifacts": [
            {
                "key": "verdict",
                "data": [
                    {"label": "尺寸", "value": size},
                    {"label": "主题", "value": theme_text},
                    {"label": "规范布局", "value": _spec_progress(results, theme)},
                ],
            },
            {"key": "issues", "data": [_issue_row(item) for item in issues]},
        ],
    }


def _l0_failure(output_dir: Path, sample_id: str, reason: str) -> dict[str, Any]:
    result = te_spec.RuleResult(
        rule="L0.ARTIFACT_MISSING",
        status=FAIL,
        expected="存在可渲染的最终产物",
        actual=reason,
        severity="major",
    )
    _write_json(
        output_dir / "sample_static.json",
        {"sampleId": sample_id, "spec": [result.as_dict()], "l0Error": reason},
    )
    return {
        "status": "failed",
        "summary": f"L0 失败：{reason}",
        "facts": {
            "verdict": "L0 失败",
            "passed": 0,
            "failed": 1,
            "pending": 0,
        },
        "artifacts": [
            {
                "key": "verdict",
                "data": [
                    {"label": "结论", "value": "L0 失败"},
                    {"label": "原因", "value": reason},
                ],
            },
            {"key": "issues", "data": [_issue_row(result)]},
        ],
    }


# ---------------------------------------------------------------- 浏览器采集


def _node_executable(config: dict[str, Any]) -> str:
    configured = config.get("nodeExecutable")
    if isinstance(configured, str) and Path(configured).is_file():
        return configured
    found = shutil.which("node")
    if found:
        return found
    raise RuntimeError("未找到 Node.js，无法执行目标效果采集")


def _build_jobs(
    sample_results: list[dict[str, Any]],
    plugin_dir: Path,
    scale: int,
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for item in sample_results:
        sample_id = str(item.get("sampleId") or "")
        sample_dir = plugin_dir / "samples" / sample_id
        static = _read_json(sample_dir / "sample_static.json")
        if not static or not static.get("genuiPath"):
            continue
        genui_path = Path(str(static["genuiPath"]))
        if not genui_path.is_file():
            continue
        jobs.append(
            {
                "id": sample_id,
                "size": static.get("size") or te_rules.DEFAULT_SIZE,
                "scale": scale,
                "variants": [
                    {
                        "name": "original",
                        "source": str(genui_path),
                        "png": str(sample_dir / "original.png"),
                        "evidence": str(sample_dir / "dom_original.json"),
                    },
                ],
            }
        )
    return jobs


async def _run_capture(
    jobs_path: Path,
    output_dir: Path,
    base_url: str,
    scale: int,
    config: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    node = _node_executable(config)
    if not CAPTURE_SCRIPT.is_file():
        raise RuntimeError("目标效果采集脚本不存在")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    browser = config.get("browserExecutable")
    if isinstance(browser, str) and browser.strip():
        env["WIDGET_DEBUG_GALLERY_BROWSER_EXECUTABLE"] = browser.strip()
    arguments = [
        node,
        str(CAPTURE_SCRIPT),
        "--jobs",
        str(jobs_path),
        "--output",
        str(output_dir),
        "--base",
        base_url,
        "--scale",
        str(scale),
    ]
    viewport = config.get("captureViewport")
    if isinstance(viewport, str) and viewport.strip():
        arguments.extend(["--viewport", viewport.strip()])
    process = await asyncio.create_subprocess_exec(
        *arguments,
        cwd=str(DEBUG_TOOLS_ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise RuntimeError("目标效果浏览器采集超时") from exc
    log = output.decode("utf-8", errors="replace") if output else ""
    (output_dir / "capture.log").write_text(log, encoding="utf-8")
    if process.returncode != 0:
        raise RuntimeError(log[-1500:] or f"采集进程退出码 {process.returncode}")
    value = _read_json(output_dir / "target_capture.json")
    if value is None:
        raise RuntimeError("采集结果缺少 target_capture.json")
    return value


def _capture_index(capture: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    if not capture:
        return index
    items = capture.get("items")
    if not isinstance(items, list):
        return index
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("id") or ""), str(item.get("variant") or ""))
        index[key] = item
    return index


# ---------------------------------------------------------------- 同因去重

COLOR_ROOT_CAUSE_RULES = {
    "SPEC.TITLE_COLOR": ("component", "subtitle"),
    "SPEC.PRIMARY_COLOR": ("component",),
    "SPEC.UNIT_COLOR": ("components",),
    "SPEC.SUPPORT_COLOR": ("failed",),
}
FONT_ROOT_CAUSE_RULES = {
    "SPEC.TITLE_FONT": ("component", "subtitle"),
    "SPEC.PRIMARY_FONT": ("component",),
    "SPEC.UNIT_FONT": ("component", "components", "merged"),
    "SPEC.SUPPORT_FONT": ("failed",),
}


def _dedupe_results(results: list[Any]) -> list[Any]:
    """同一根因只扣一次分：派生症状降为不适用，并记录去重原因。

    - 蒙层或文字颜色已在规范维度失败时，对比度低是同一根因的症状；
    - 声明缺失 padding 与实测越界同因，保留可见后果的安全区判定；
    - 字号不达标已在 ``SPEC.*_FONT`` 扣分时不再重复计入可见性；
    - 标题未设省略号导致的横向截断由 ``SPEC.TITLE_ELLIPSIS`` 计分；
      未溢出的短标题已由 ``_waive_title_ellipsis`` 先降为不适用。
    """
    by_rule: dict[str, Any] = {}
    for item in results:
        by_rule[item.rule] = item
    updated: list[Any] = []
    for item in results:
        updated.append(_dedupe_one(item, by_rule))
    return updated


def _dedupe_one(item: Any, by_rule: dict[str, Any]) -> Any:
    if item.rule == "VIS.CONTRAST_LOW" and item.status in {FAIL, PENDING}:
        source = _contrast_root_cause(by_rule, item)
        if source:
            return _replace_result(item, NA, f"{source} 已单独扣分，对比度不重复计分")
    if item.rule == "SPEC.PADDING" and item.status == FAIL:
        safe = by_rule.get("SPEC.SAFE_AREA")
        if safe is not None and safe.status == FAIL:
            return _replace_result(item, NA, "与 SPEC.SAFE_AREA 同因，文本越界只计一次")
    if item.rule == "VIS.FONT_TOO_SMALL" and item.status == PENDING:
        source = _covered_by(item, by_rule, FONT_ROOT_CAUSE_RULES)
        if source:
            return _replace_result(item, NA, f"{source} 已单独扣分，字号不重复计分")
    if item.rule == "VIS.TEXT_CLIPPED" and item.status == FAIL:
        ellipsis = by_rule.get("SPEC.TITLE_ELLIPSIS")
        if ellipsis is not None and ellipsis.status == FAIL:
            clipped = _ids_from_result(item)
            covered = _ids_from_rule(ellipsis, ("components",))
            if clipped and covered and clipped <= covered:
                return _replace_result(
                    item, NA, "标题省略号已由 SPEC.TITLE_ELLIPSIS 扣分"
                )
    return item


def _contrast_root_cause(by_rule: dict[str, Any], contrast: Any) -> str:
    mask = by_rule.get("SPEC.MASK")
    if mask is not None and mask.status == FAIL:
        return "SPEC.MASK"
    return _covered_by(contrast, by_rule, COLOR_ROOT_CAUSE_RULES)


def _covered_by(item: Any, by_rule: dict[str, Any], table: dict[str, tuple[str, ...]]) -> str:
    """节点集合被已失败的根因规则完全覆盖时返回根因规则名。"""
    targets = _ids_from_result(item)
    if not targets:
        return ""
    covered: set[str] = set()
    sources: list[str] = []
    for rule, fields in table.items():
        root = by_rule.get(rule)
        if root is None or root.status != FAIL:
            continue
        ids = _ids_from_rule(root, fields)
        if not ids:
            continue
        covered |= ids
        sources.append(rule)
    if not covered or not targets <= covered:
        return ""
    return "、".join(sources)


def _ids_from_rule(item: Any, fields: tuple[str, ...]) -> set[str]:
    ids: set[str] = set()
    for name in fields:
        value = item.evidence.get(name)
        if isinstance(value, str) and value:
            ids.add(value)
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and entry:
                    ids.add(entry)
    return ids


def _ids_from_result(item: Any) -> set[str]:
    ids: set[str] = set()
    _collect_ids(item.evidence, ids)
    findings = item.evidence.get("findings")
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            _collect_ids(finding, ids)
    nodes = item.evidence.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id")
            if isinstance(node_id, str) and node_id:
                ids.add(node_id)
    return ids


def _collect_ids(source: Any, ids: set[str]) -> None:
    if not isinstance(source, dict):
        return
    for key in ("component", "components"):
        value = source.get(key)
        if isinstance(value, str) and value:
            ids.add(value.split(":", 1)[0])
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, str) and entry:
                    ids.add(entry.split(":", 1)[0])


def _waive_title_ellipsis(
    results: list[Any],
    evidence: dict[str, Any],
    components: dict[str, Any],
) -> list[Any]:
    """标题没有溢出时，省略号声明缺失不扣分。

    规范只要求「超出最大宽度时单行截断并加省略号」。当 DOM 证据证明失败的
    标题/副标题只有一行、文本完整可见且没有横向溢出时，把声明缺失改为不适用；
    真正被裁掉的长标题仍然保持失败。
    """
    nodes = _evidence_nodes(evidence)
    if not nodes:
        return results
    updated: list[Any] = []
    for item in results:
        if item.rule != "SPEC.TITLE_ELLIPSIS" or item.status != FAIL:
            updated.append(item)
            continue
        missing = _ellipsis_missing_ids(item, components)
        if not missing or not all(_fits_single_line(nodes.get(name)) for name in missing):
            updated.append(item)
            continue
        updated.append(_replace_result(item, NA, "标题未溢出，省略号不影响显示"))
    return updated


def _evidence_nodes(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = evidence.get("nodes")
    if not isinstance(nodes, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id:
            index[node_id] = node
    return index


def _ellipsis_missing_ids(item: Any, components: dict[str, Any]) -> list[str]:
    checked = item.evidence.get("components")
    if not isinstance(checked, list):
        return []
    missing: list[str] = []
    for name in checked:
        if not isinstance(name, str) or not name:
            continue
        component = components.get(name)
        if not isinstance(component, dict):
            return []
        styles = component.get("styles") or {}
        if styles.get("maxLines") != 1 or styles.get("textOverflow") != "ellipsis":
            missing.append(name)
    return missing


def _fits_single_line(node: Any) -> bool:
    """DOM 节点是否单行、完整可见且没有横向溢出。"""
    if not isinstance(node, dict):
        return False
    if node.get("visible") is False or node.get("zeroSized"):
        return False
    line_count = node.get("lineCount")
    if not isinstance(line_count, int) or isinstance(line_count, bool):
        return False
    if line_count > 1:
        return False
    client = node.get("clientWidth")
    scroll = node.get("scrollWidth")
    if not _is_number(client) or not _is_number(scroll):
        return False
    if scroll > client + 2:
        return False
    text = te_dom.normalize_text(node.get("text"))
    rendered = te_dom.normalize_text(node.get("renderedText"))
    return bool(text) and rendered == text


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _replace_result(item: Any, status: str, actual: str) -> Any:
    evidence = dict(item.evidence)
    evidence["dedupe"] = {"from": item.status, "to": status, "reason": actual}
    return te_spec.RuleResult(
        rule=item.rule,
        status=status,
        expected=item.expected,
        actual=actual,
        severity=item.severity,
        evidence=evidence,
    )


# ---------------------------------------------------------------- 样本汇总


def _evaluate_sample(
    sample_id: str,
    sample_dir: Path,
    capture: dict[tuple[str, str], dict[str, Any]],
    scale: float,
) -> dict[str, Any]:
    static = _read_json(sample_dir / "sample_static.json")
    if static is None:
        return _failed_verdict(sample_id, ["缺少 sample_static.json"])
    if static.get("l0Error"):
        return _failed_verdict(sample_id, [str(static.get("l0Error"))])
    theme = static.get("theme") if isinstance(static.get("theme"), dict) else None
    score_context: dict[str, Any] = {}
    if theme is not None and theme.get("eligible") is False:
        score_context["specExcludedReason"] = str(
            theme.get("reason") or "主题不属于图+蒙层路线，规范维度不计分"
        )
    results = [_result_from_dict(item) for item in static.get("spec") or []]
    original_item = capture.get((sample_id, "original"))
    evidence = _read_json(sample_dir / "dom_original.json")
    metrics: dict[str, Any] = {}
    capture_errors: list[str] = []
    if original_item is None or not original_item.get("ok"):
        reason = "未执行浏览器采集" if original_item is None else str(
            original_item.get("error") or "采集失败"
        )
        capture_errors.append(f"original: {reason}")
    components: dict[str, Any] = {}
    genui_path = Path(str(static.get("genuiPath") or ""))
    if genui_path.is_file():
        parsed = te_genui.parse_genui(genui_path.read_text(encoding="utf-8"))
        components = parsed.get("components") or {}
    if evidence is not None:
        png_path = sample_dir / "original.png"
        dom_results, metrics = te_dom.evaluate_dom(
            evidence,
            components,
            png_path=png_path if png_path.is_file() else None,
            scale=scale,
            resource_root=RESOURCE_ROOT,
            size=str(static.get("size") or te_rules.DEFAULT_SIZE),
        )
        results.extend(dom_results)
        results = _waive_title_ellipsis(results, evidence, components)
    else:
        results.append(
            te_spec.RuleResult(
                rule="VIS.EVIDENCE_MISSING",
                status=PENDING,
                expected="DOM 与截图为可见性判定提供证据",
                actual="未采集到原始渲染证据",
                severity="major",
            )
        )
    if capture_errors:
        results.append(
            te_spec.RuleResult(
                rule=CAPTURE_FAILED_RULE,
                status=FAIL,
                expected="浏览器采集成功",
                actual="；".join(capture_errors)[:300],
                severity="major",
            )
        )
    results = _dedupe_results(results)
    score = te_score.score_sample(
        [item.as_dict() for item in results],
        score_context,
    )
    status = _sample_status(results)
    counts = _counts(results)
    verdict = _verdict_text(results)
    issues = _issue_results(results)
    payload = {
        "sampleId": sample_id,
        "status": status,
        "verdict": verdict,
        "size": str(static.get("size") or te_rules.DEFAULT_SIZE),
        "rubricVersion": te_spec.RUBRIC_VERSION,
        "theme": theme,
        "results": [item.as_dict() for item in results],
        "metrics": metrics,
        "counts": counts,
        "score": score,
        "images": {"original": "original.png"} if (sample_dir / "original.png").is_file() else {},
    }
    _write_json(sample_dir / "verdict.json", payload)
    _write_json(
        sample_dir / "issues.json",
        {"sampleId": sample_id, "issues": [_issue_row(item) for item in issues]},
    )
    return payload


def _failed_verdict(
    sample_id: str,
    reasons: list[str],
) -> dict[str, Any]:
    result = te_spec.RuleResult(
        rule="L0.ARTIFACT_MISSING",
        status=FAIL,
        expected="存在可评估的最终产物",
        actual="；".join(reasons)[:300],
        severity="major",
    )
    return {
        "sampleId": sample_id,
        "status": "failed",
        "verdict": "L0 失败",
        "results": [result.as_dict()],
        "metrics": {},
        "counts": {"passed": 0, "failed": 1, "pending": 0, "na": 0},
        "score": te_score.score_sample([result.as_dict()], {}),
        "images": {},
    }


# ---------------------------------------------------------------- 数据集


async def process_dataset(context: dict[str, Any]) -> dict[str, Any]:
    dataset_dir = Path(str(context.get("outputDir") or "."))
    dataset_dir.mkdir(parents=True, exist_ok=True)
    plugin_dir = dataset_dir.parent
    config = _config(context)
    sample_results = context.get("sampleResults")
    samples = sample_results if isinstance(sample_results, list) else []
    scale = _scale(config)
    base_url = _base_url(config)
    verdicts: dict[str, dict[str, Any]] = {}
    capture_error = ""
    capture: dict[str, Any] | None = None
    jobs = _build_jobs(samples, plugin_dir, scale)
    if jobs:
        jobs_path = dataset_dir / "capture_jobs.json"
        _write_json(jobs_path, jobs)
        try:
            capture = await _run_capture(
                jobs_path,
                dataset_dir,
                base_url,
                scale,
                config,
                float(config.get("captureTimeoutSeconds") or 1800),
            )
        except Exception as exc:  # noqa: BLE001 - 采集失败要转成业务结论
            capture_error = f"{type(exc).__name__}: {exc}"
            capture = None
    capture_map = _capture_index(capture)
    for item in samples:
        sample_id = str(item.get("sampleId") or "")
        sample_dir = plugin_dir / "samples" / sample_id
        verdict = _evaluate_sample(sample_id, sample_dir, capture_map, scale)
        if capture_error and not verdict.get("images"):
            verdict["status"] = "failed"
            verdict["verdict"] = "采集失败"
        verdicts[sample_id] = verdict
    summary = _summarize(samples, verdicts, capture_error)
    _write_json(dataset_dir / "summary.json", summary)
    (dataset_dir / "report.md").write_text(_build_markdown(summary), encoding="utf-8")
    (dataset_dir / "report.html").write_text(_build_html(summary), encoding="utf-8")
    return {
        "status": "partial" if capture_error else "success",
        "summary": _dataset_summary_text(summary),
        "facts": summary["facts"],
        "artifacts": _dataset_artifacts(summary),
    }


def _scale(config: dict[str, Any]) -> int:
    value = config.get("captureScale")
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 4:
        return value
    return 3


def _base_url(config: dict[str, Any]) -> str:
    value = config.get("rendererBaseUrl")
    if isinstance(value, str) and value.strip():
        return value.strip().rstrip("/")
    env_value = os.environ.get("DEBUG_TOOLS_RENDERER_BASE_URL", "").strip()
    if env_value:
        return env_value.rstrip("/")
    return "http://127.0.0.1:8888/debug"


def _summarize(
    samples: list[dict[str, Any]],
    verdicts: dict[str, dict[str, Any]],
    capture_error: str,
) -> dict[str, Any]:
    rule_stats: dict[str, dict[str, int]] = {}
    rule_expected: dict[str, str] = {}
    rule_metrics: dict[str, dict[str, float]] = {}
    rows: list[dict[str, Any]] = []
    statuses = {"success": 0, "partial": 0, "failed": 0}
    for item in samples:
        sample_id = str(item.get("sampleId") or "")
        verdict = verdicts.get(sample_id) or _failed_verdict(sample_id, ["未评估"])
        statuses[verdict.get("status", "failed")] = (
            statuses.get(verdict.get("status", "failed"), 0) + 1
        )
        results = verdict.get("results") or []
        for result in results:
            rule = str(result.get("rule") or "")
            bucket = rule_stats.setdefault(
                rule, {"pass": 0, "fail": 0, "pending": 0, "na": 0}
            )
            bucket[str(result.get("status") or "na")] += 1
            expected = str(result.get("expected") or "")
            if expected and not rule_expected.get(rule):
                rule_expected[rule] = expected
        counts = verdict.get("counts") or {}
        failed_rules = [
            str(result.get("rule"))
            for result in results
            if result.get("status") == FAIL
            and not _is_diagnostic_rule_name(str(result.get("rule") or ""))
        ]
        pending_rules = [
            str(result.get("rule"))
            for result in results
            if result.get("status") == PENDING
            and not _is_diagnostic_rule_name(str(result.get("rule") or ""))
        ]
        score = verdict.get("score") if isinstance(verdict.get("score"), dict) else {}
        _collect_rule_metrics(score, rule_metrics)
        images = verdict.get("images") if isinstance(verdict.get("images"), dict) else {}
        image = images.get("original")
        theme = verdict.get("theme") if isinstance(verdict.get("theme"), dict) else None
        rows.append(
            {
                "样本": sample_id,
                "状态": verdict.get("status"),
                "结论": verdict.get("verdict"),
                "主题": _theme_text(theme),
                "总分": score.get("total", 0.0),
                "等级": score.get("band") or "—",
                "规范符合": te_score.dimension_score(score, "spec"),
                "可见性": te_score.dimension_score(score, "visibility"),
                "通过": counts.get("passed", 0),
                "失败": counts.get("failed", 0),
                "待复核": counts.get("pending", 0),
                "失败项": ", ".join(failed_rules[:8]),
                "待复核项": ", ".join(pending_rules[:8]),
                "图片": f"samples/{sample_id}/{image}" if isinstance(image, str) else "",
                "尺寸": str(item.get("size") or te_rules.DEFAULT_SIZE),
                "维度": score.get("dimensions") or [],
            }
        )
    total = len(rows)
    applicable = 0
    passed = 0
    score_total = 0.0
    scored = 0
    for row in rows:
        value = row.get("总分")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            score_total += float(value)
            scored += 1
    dimension_averages = _dimension_averages(rows)
    spec_scored = sum(1 for row in rows if row.get("规范符合") is not None)
    spec_excluded = total - spec_scored
    rules = []
    for rule in RULE_ORDER:
        counts = rule_stats.get(rule) or {"pass": 0, "fail": 0, "pending": 0, "na": 0}
        metrics = rule_metrics.get(rule)
        checked = counts["pass"] + counts["fail"] + counts["pending"]
        pass_rate = counts["pass"] / checked if checked else None
        if _is_scored_rule(rule):
            applicable += checked
            passed += counts["pass"]
        rules.append(
            {
                "规则": rule,
                "维度": _rule_dimension(rule),
                "细分项": RULE_TITLES.get(rule, rule),
                "含义": RULE_HINTS.get(rule, ""),
                "期望示例": rule_expected.get(rule, ""),
                "单条满分": _rule_weight_text(metrics),
                "平均得分": _rule_average_text(metrics),
                "通过率": round(pass_rate * 100, 1) if pass_rate is not None else None,
                "参与样本": int(metrics["samples"]) if metrics else 0,
                "通过": counts["pass"],
                "失败": counts["fail"],
                "待复核": counts["pending"],
                "不适用": counts["na"],
            }
        )
    return {
        "profile": te_spec.PROFILE_ID,
        "rubricVersion": te_spec.RUBRIC_VERSION,
        "total": total,
        "samples": rows,
        "rules": rules,
        "captureError": capture_error,
        "facts": {
            "total": total,
            "passed": statuses.get("success", 0),
            "partial": statuses.get("partial", 0),
            "failed": statuses.get("failed", 0),
            "passRate": round((passed / applicable) * 100, 1) if applicable else 0.0,
            "averageScore": round(score_total / scored, 1) if scored else 0.0,
            "averageVisibility": _average_of(dimension_averages, "visibility"),
            "averageSpec": _average_of(dimension_averages, "spec"),
            "specApplicable": spec_scored,
            "specExcluded": spec_excluded,
        },
    }


def _dimension_averages(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按维度汇总整批平均分；不适用维度按 0 分计入，同时记录实际计分样本数。"""
    buckets: dict[str, list[float]] = {}
    scored: dict[str, int] = {}
    for row in rows:
        for item in row.get("维度") or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            value = item.get("score")
            if not key or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            buckets.setdefault(key, []).append(float(value))
            if item.get("applicable") is not False:
                scored[key] = scored.get(key, 0) + 1
    averages: list[dict[str, Any]] = []
    for key, label, weight in te_score.DIMENSION_ORDER:
        values = buckets.get(key) or []
        average = round(sum(values) / len(values), 1) if values else None
        averages.append(
            {
                "key": key,
                "label": label,
                "max": weight,
                "score": average,
                "ratio": round(average / weight * 100, 1)
                if average is not None and weight
                else None,
                "samples": len(values),
                "applicable": scored.get(key, 0),
            }
        )
    return averages


def _average_of(averages: list[dict[str, Any]], key: str) -> float | None:
    for item in averages:
        if item.get("key") == key:
            value = item.get("score")
            return float(value) if isinstance(value, (int, float)) else None
    return None


def _collect_rule_metrics(
    score: dict[str, Any],
    rule_metrics: dict[str, dict[str, float]],
) -> None:
    """累计每条规则在整批中的得分，分母是它在各样本里实际占的满分。

    每条规则的单条满分 = 所在维度分值 ÷ 该维度的适用规则数，会随样本变化；
    平均得分取各样本 ``单条满分 × 通过值`` 的算术平均，因此同一维度下
    所有规则的平均得分累加约等于该维度的整批平均分（展示保留一位小数）。
    """
    dimensions = score.get("dimensions")
    if not isinstance(dimensions, list):
        return
    for dimension in dimensions:
        if not isinstance(dimension, dict) or not dimension.get("applicable"):
            continue
        items = dimension.get("items")
        maximum = dimension.get("max")
        if not isinstance(items, list) or not items:
            continue
        if not isinstance(maximum, (int, float)) or isinstance(maximum, bool):
            continue
        unit = float(maximum) / len(items)
        for item in items:
            if not isinstance(item, dict):
                continue
            rule = str(item.get("rule") or "")
            value = item.get("value")
            if not rule or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            bucket = rule_metrics.setdefault(
                rule,
                {
                    "earned": 0.0,
                    "weight": 0.0,
                    "samples": 0.0,
                    "unitMin": unit,
                    "unitMax": unit,
                },
            )
            bucket["earned"] += unit * float(value)
            bucket["weight"] += unit
            bucket["samples"] += 1
            bucket["unitMin"] = min(bucket["unitMin"], unit)
            bucket["unitMax"] = max(bucket["unitMax"], unit)


def _rule_dimension(rule: str) -> str:
    """规则前缀到维度名的映射；诊断项不进维度分。"""
    prefix = rule.split(".", 1)[0]
    if rule in te_score.DIAGNOSTIC_RULES:
        return "规范（仅诊断）" if prefix == "SPEC" else "素材（仅诊断）"
    return {
        "L0": "前置条件",
        "VIS": "可见性",
        "SPEC": "规范符合",
        "ASSET": "素材（仅诊断）",
    }.get(prefix, "其他")


def _rule_weight_text(metrics: dict[str, float] | None) -> str:
    """单条满分；不同样本适用规则数不同导致分值浮动时给出区间。"""
    if not metrics:
        return "—"
    minimum = float(metrics.get("unitMin") or 0.0)
    maximum = float(metrics.get("unitMax") or 0.0)
    if abs(maximum - minimum) < 0.05:
        return f"{maximum:.1f}"
    return f"{minimum:.1f}–{maximum:.1f}"


def _rule_average_text(metrics: dict[str, float] | None) -> str:
    if not metrics:
        return "—"
    samples = float(metrics.get("samples") or 0.0)
    if samples <= 0:
        return "—"
    return f"{float(metrics.get('earned') or 0.0) / samples:.1f}"


def _dataset_summary_text(summary: dict[str, Any]) -> str:
    facts = summary.get("facts") or {}
    text = (
        f"目标效果评测完成：{facts.get('total', 0)} 个样本，"
        f"通过 {facts.get('passed', 0)}，待复核 {facts.get('partial', 0)}，"
        f"失败 {facts.get('failed', 0)}"
    )
    if summary.get("captureError"):
        text += f"；采集异常：{summary['captureError']}"
    return text


def _dataset_artifacts(summary: dict[str, Any]) -> list[dict[str, Any]]:
    facts = summary.get("facts") or {}
    overview = [
        {"label": "样本数", "value": facts.get("total", 0)},
        {"label": "平均总分", "value": facts.get("averageScore", 0)},
    ]
    for item in _dimension_averages(summary.get("samples") or []):
        if not isinstance(item, dict) or item.get("score") is None:
            continue
        overview.append(
            {
                "label": _average_label(item),
                "value": _average_short(item.get("score")),
            }
        )
    overview.extend(
        [
            {"label": "通过", "value": facts.get("passed", 0)},
            {"label": "待复核", "value": facts.get("partial", 0)},
            {"label": "失败", "value": facts.get("failed", 0)},
            {"label": "规则通过率", "value": f"{facts.get('passRate', 0)}%"},
        ]
    )
    # 顺序：概览 → 细分维度 → 全部样本 → 卡片评分，HTML 报告入口移到顶部工具栏。
    return [
        {"key": "overview", "data": overview},
        {"key": "rules", "data": _dimension_table_rows(summary)},
        {"key": "samples", "data": _table_rows(summary.get("samples") or [])},
        {"key": "scores", "data": _score_rows(summary)},
        {"key": "report", "path": "report.html", "alt": "目标效果评测报告"},
    ]


def _dimension_table_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """外层按维度汇总，细则挂在 items，由看板逐维度展开。"""
    rules = [rule for rule in summary.get("rules") or [] if isinstance(rule, dict)]
    averages = {
        str(item.get("key")): item
        for item in _dimension_averages(summary.get("samples") or [])
        if isinstance(item, dict)
    }
    groups: list[str] = [label for _, label, _ in te_score.DIMENSION_ORDER]
    for rule in rules:
        dimension = str(rule.get("维度") or "其他")
        if dimension not in groups:
            groups.append(dimension)
    rows: list[dict[str, Any]] = []
    for dimension in groups:
        items: list[dict[str, Any]] = []
        passed = 0
        checked = 0
        for rule in rules:
            if rule.get("维度") != dimension:
                continue
            passed += int(rule.get("通过") or 0)
            checked += sum(int(rule.get(key) or 0) for key in ("通过", "失败", "待复核"))
            rate = rule.get("通过率")
            items.append(
                {
                    "规则": f"{rule.get('规则')} {rule.get('细分项')}".strip(),
                    "含义": rule.get("含义") or "—",
                    "均分 / 满分": f"{rule.get('平均得分')} / {rule.get('单条满分')}",
                    "通过率": "—" if rate is None else f"{rate}%",
                    "参与样本": rule.get("参与样本", 0),
                }
            )
        key = _dimension_key(dimension)
        average = averages.get(key) or {}
        if not items and average.get("score") is None:
            continue
        applicable = int(average.get("applicable", 0))
        label = dimension
        if key and not applicable:
            label = f"{dimension}（不适用）"
        rows.append(
            {
                "维度": label,
                "均分 / 满分": _average_text(average.get("score"), average.get("max")),
                "通过率": f"{round(passed / checked * 100, 1)}%" if checked else "—",
                "计分样本": applicable if key else "—",
                "items": items,
            }
        )
    return rows


def _dimension_key(label: str) -> str:
    for key, name, _ in te_score.DIMENSION_ORDER:
        if name == label:
            return key
    return ""


def _rule_table_rows(rules: list[Any]) -> list[dict[str, Any]]:
    """平台表格只保留解释细分维度所需的列，避免整行原始统计挤成一团。"""
    rows: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rate = rule.get("通过率")
        average = rule.get("平均得分")
        maximum = rule.get("单条满分")
        rows.append(
            {
                "细分维度": " · ".join(
                    part
                    for part in (
                        str(rule.get("维度") or ""),
                        f"{rule.get('规则')} {rule.get('细分项')}",
                    )
                    if part
                ),
                "含义": rule.get("含义") or "—",
                "均分 / 满分": f"{average} / {maximum}",
                "通过率": "—" if rate is None else f"{rate}%",
                "计分样本": rule.get("参与样本", 0),
            }
        )
    return rows


_SAMPLE_TABLE_HIDDEN = {"维度", "图片", "等级", "通过", "失败", "待复核"}


def _table_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """表格只保留定位失败样本所需的列；评分与截图在卡片和样本详情中查看。"""
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        output.append(
            {key: value for key, value in row.items() if key not in _SAMPLE_TABLE_HIDDEN}
        )
    return output


def _average_text(score: Any, maximum: Any) -> str:
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return "—"
    return f"{score} / {maximum}"


def _average_label(item: dict[str, Any]) -> str:
    maximum = item.get("max")
    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
        return f"平均{item.get('label')} /{maximum:g}"
    return f"平均{item.get('label')}"


def _average_short(score: Any) -> str:
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return "—"
    return str(score)


def _dimension_kpis(summary: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for item in _dimension_averages(summary.get("samples") or []):
        if not isinstance(item, dict) or item.get("score") is None:
            continue
        rows.append(
            "<div class=\"kpi\">{}<strong>{}</strong></div>".format(
                html.escape(_average_label(item)),
                html.escape(_average_short(item.get("score"))),
            )
        )
    return rows


def _score_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """评分卡总览：每行一张卡，字段名固定给前端 score-grid 使用。"""
    rows: list[dict[str, Any]] = []
    for row in summary.get("samples") or []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "sampleId": row.get("样本"),
                "title": row.get("样本"),
                "status": row.get("状态"),
                "verdict": row.get("结论"),
                "total": row.get("总分"),
                "band": row.get("等级"),
                "image": row.get("图片") or "",
                "size": row.get("尺寸") or te_rules.DEFAULT_SIZE,
                "dimensions": _score_dimensions(row.get("维度")),
            }
        )
    return rows


def _score_dimensions(value: Any) -> list[dict[str, Any]]:
    """给评分卡补上每条规则的说明；不适用维度保留 0 分与原因，保证两项相加为 100。"""
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for item in value:
        if not isinstance(item, dict):
            continue
        copy = dict(item)
        copy["items"] = _score_items(item.get("items"))
        rows.append(copy)
    return rows


def _score_items(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for item in value:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("rule") or "")
        rows.append(
            {
                "rule": rule,
                "title": RULE_TITLES.get(rule, rule),
                "status": str(item.get("status") or ""),
                "deduction": item.get("deduction"),
                "weight": item.get("weight"),
                "expected": str(item.get("expected") or ""),
                "actual": str(item.get("actual") or ""),
            }
        )
    return rows


# ---------------------------------------------------------------- finalize


def finalize(context: dict[str, Any]) -> dict[str, Any]:
    dataset_dir = Path(str(context.get("datasetOutputDir") or "."))
    summary = _read_json(dataset_dir / "summary.json") or {"samples": [], "rules": []}
    dataset_status = "partial" if summary.get("captureError") else "success"
    updates: list[dict[str, Any]] = []
    sample_dirs = context.get("sampleOutputDirs")
    if not isinstance(sample_dirs, dict):
        sample_dirs = {}
    for sample_id, raw_path in sample_dirs.items():
        sample_dir = Path(str(raw_path))
        verdict = _read_json(sample_dir / "verdict.json")
        if verdict is None:
            updates.append(
                {
                    "sampleId": sample_id,
                    "status": "failed",
                    "summary": "缺少评测结论",
                    "facts": {"verdict": "L0 失败", "failed": 1, "pending": 0},
                    "artifacts": [],
                }
            )
            continue
        updates.append(_sample_artifacts(sample_id, verdict))
    return {
        "status": "success",
        "summary": _dataset_summary_text(summary),
        "sampleResults": updates,
        "datasetResult": {
            "status": dataset_status,
            "summary": _dataset_summary_text(summary),
            "facts": summary.get("facts") or {},
            "artifacts": _dataset_artifacts(summary),
        },
    }


def _sample_artifacts(
    sample_id: str,
    verdict: dict[str, Any],
) -> dict[str, Any]:
    results = [_result_from_dict(item) for item in verdict.get("results") or []]
    issues = _issue_results(results)
    counts = verdict.get("counts") or {}
    score = verdict.get("score") if isinstance(verdict.get("score"), dict) else {}
    deductions = _rule_deductions(score)
    theme = verdict.get("theme") if isinstance(verdict.get("theme"), dict) else None
    # 总分、结论、失败数和渲染缩略图已在上方评分卡展示，
    # 独立样本详情页只保留规范布局进度与扣分明细。
    artifacts: list[dict[str, Any]] = [
        {
            "key": "verdict",
            "data": [
                {"label": "尺寸", "value": str(verdict.get("size") or "—")},
                {"label": "主题", "value": _theme_text(theme)},
                {"label": "规范布局", "value": _spec_progress(results, theme)},
            ],
        },
        {"key": "issues", "data": [_issue_row(item, deductions) for item in issues]},
    ]
    status = str(verdict.get("status") or "failed")
    return {
        "sampleId": sample_id,
        "status": status,
        "summary": _score_summary(verdict.get("verdict"), score),
        "facts": {
            "verdict": str(verdict.get("verdict") or "—"),
            "theme": _theme_text(theme),
            "size": str(verdict.get("size") or "—"),
            "specApplicable": te_score.dimension_score(score, "spec") is not None,
            "score": score.get("total", 0.0),
            "scoreVisibility": te_score.dimension_score(score, "visibility"),
            "scoreSpec": te_score.dimension_score(score, "spec"),
            "passed": int(counts.get("passed") or 0),
            "failed": int(counts.get("failed") or 0),
            "pending": int(counts.get("pending") or 0),
        },
        "artifacts": artifacts,
    }


def _deduction_text(items: Any, limit: int = 4) -> str:
    """把规则扣分压成一行，例如“标题 16/20fp −2.8；副文本 60% 白 −2.8”。"""
    drops: list[tuple[str, float]] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get("deduction")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if value <= 0:
                continue
            rule = str(item.get("rule") or "")
            drops.append((RULE_TITLES.get(rule, rule), float(value)))
    if not drops:
        return ""
    parts = [f"{title} −{value:g}" for title, value in drops[:limit]]
    if len(drops) > limit:
        parts.append("…")
    return "；".join(parts)


def _score_summary(verdict: Any, score: dict[str, Any]) -> str:
    text = str(verdict or "—")
    total = score.get("total")
    if total is not None:
        text += f" · {total} 分"
    note = str(score.get("note") or "")
    return f"{text}（{note}）" if note else text


# ---------------------------------------------------------------- 报告


def _build_markdown(summary: dict[str, Any]) -> str:
    facts = summary.get("facts") or {}
    lines = [
        "# 倒计时目标效果评测",
        "",
        f"- profile：`{summary.get('profile')}`（rubric v{summary.get('rubricVersion', 2)}）",
        f"- 样本数：{facts.get('total', 0)}，通过 {facts.get('passed', 0)}，"
        f"待复核 {facts.get('partial', 0)}，失败 {facts.get('failed', 0)}",
        f"- 规则通过率：{facts.get('passRate', 0)}%",
        f"- 平均总分：{facts.get('averageScore', 0)} / 100",
        "- 维度平均："
        + "、".join(
            f"{item.get('label')} {_average_text(item.get('score'), item.get('max'))}"
            for item in _dimension_averages(summary.get("samples") or [])
            if item.get("score") is not None
        ),
        f"- 规范维度：{facts.get('specApplicable', 0)} 个样本计分，"
        f"{facts.get('specExcluded', 0)} 个样本因主题不属于 Pixso 图+蒙层路线而不计分。",
        "- 评分口径：规范符合 60、可见性 40，两项固定构成 100 分；"
        "不适用维度记 0 分并展示原因，维度分相加即总分。版式与素材规则"
        "只做诊断，不计分也不影响结论。待复核按半通过。",
        "- 细分项均分 = 各样本“单条满分 × 通过值”的平均，单条满分 = 维度分值 ÷ "
        "该维度适用规则数；均分按一位小数展示，同一维度下累加与维度平均可能存在 ≤0.5 的取整差。",
    ]
    if summary.get("captureError"):
        lines.append(f"- 采集异常：{summary['captureError']}")
    lines.extend(["", "## 细分维度明细（整批平均）", ""])
    lines.append(
        "| 维度 | 细分项 | 含义 | 期望示例 | 单条满分 | 平均得分 | 通过率 | 参与样本 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for rule in summary.get("rules") or []:
        rate = rule.get("通过率")
        lines.append(
            f"| {rule.get('维度')} | `{rule.get('规则')}` {rule.get('细分项')} | "
            f"{rule.get('含义') or '—'} | {rule.get('期望示例') or '—'} | "
            f"{rule.get('单条满分')} | {rule.get('平均得分')} | "
            f"{'—' if rate is None else str(rate) + '%'} | {rule.get('参与样本')} |"
        )
    lines.extend([
        "",
        "## 样本结论",
        "",
        "| 样本 | 主题 | 总分 | 规范符合 | 可见性 | "
        "状态 | 结论 | 失败项 | 待复核项 |",
    ])
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in summary.get("samples") or []:
        lines.append(
            f"| `{row.get('样本')}` | {row.get('主题') or '—'} | "
            f"{_score_text(row.get('总分'))} | "
            f"{_score_text(row.get('规范符合'))} | "
            f"{_score_text(row.get('可见性'))} | "
            f"{row.get('状态')} | {row.get('结论')} | "
            f"{row.get('失败项') or '—'} | {row.get('待复核项') or '—'} |"
        )
    lines.extend(["", "## 扣分明细", ""])
    for row in summary.get("samples") or []:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{row.get('样本')}`：{_markdown_deductions(row)}"
        )
    lines.append("")
    return "\n".join(lines)


def _markdown_deductions(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in row.get("维度") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "")
        score = item.get("score")
        if item.get("applicable") is False:
            reason = str(item.get("reason") or "不适用")
            parts.append(f"{label} 0.0/{item.get('max')}（{reason}）")
            continue
        if score is None:
            parts.append(f"{label} —/{item.get('max')}（不适用）")
            continue
        text = f"{label} {_score_text(score)}/{item.get('max')}"
        drops = _deduction_text(item.get("items"), 6)
        parts.append(f"{text}：{drops or '全部通过'}")
    return "；".join(parts)


def _score_text(value: Any) -> str:
    return "—" if value is None else str(value)


def _size_ratio(size: Any) -> str:
    parts = str(size or "").lower().split("x")
    if len(parts) != 2:
        return "1 / 1"
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return "1 / 1"
    if width <= 0 or height <= 0:
        return "1 / 1"
    return f"{width} / {height}"


def _score_cards_html(summary: dict[str, Any]) -> str:
    cards: list[str] = []
    for row in summary.get("samples") or []:
        if not isinstance(row, dict):
            continue
        sample_id = str(row.get("样本") or "")
        image = str(row.get("图片") or "")
        image_url = f"../{image}" if image else ""
        image_href = html.escape(image_url)
        image_alt = html.escape(f"{sample_id} 渲染截图")
        shot_style = f' style="aspect-ratio:{_size_ratio(row.get("尺寸"))}"'
        shot = (
            f'<a class="shot"{shot_style} href="{image_href}" target="_blank" rel="noreferrer">'
            f'<img src="{image_href}" alt="{image_alt}" loading="lazy"></a>'
            if image
            else f'<div class="shot empty"{shot_style}>无截图</div>'
        )
        dimensions = []
        for item in row.get("维度") or []:
            if not isinstance(item, dict):
                continue
            score = item.get("score")
            maximum = item.get("max") or 0
            ratio = 0.0
            if isinstance(score, (int, float)) and isinstance(maximum, (int, float)) and maximum:
                ratio = max(0.0, min(100.0, float(score) / float(maximum) * 100.0))
            value = "—" if score is None else f"{score} / {maximum}"
            dimensions.append(
                '<li class="dim"><div class="dim-head"><span>{}</span>'
                '<i><em style="width:{:.1f}%"></em></i><b>{}</b></div>{}</li>'.format(
                    html.escape(str(item.get("label") or "")),
                    ratio,
                    html.escape(value),
                    _card_deductions_html(item),
                )
            )
        status = str(row.get("状态") or "")
        cards.append(
            '<article class="score-card {}">{}<div class="score-head"><b>{}</b>'
            '<span class="verdict {}">{}</span></div>'
            '<div class="score-total"><strong>{}</strong><span>总分 / 100 · {}</span></div>'
            "<ul>{}</ul></article>".format(
                html.escape(status),
                shot,
                html.escape(sample_id),
                html.escape(status),
                html.escape(str(row.get("结论") or "—")),
                html.escape(_score_text(row.get("总分"))),
                html.escape(str(row.get("等级") or "—")),
                "".join(dimensions),
            )
        )
    return f'<div class="score-grid">{"".join(cards)}</div>'


def _card_deductions_html(item: dict[str, Any]) -> str:
    """评分卡单个维度的扣分明细；只列扣分规则，全部通过时给一行提示。"""
    if not item.get("applicable"):
        reason = str(item.get("reason") or "不适用")
        return f'<p class="clear">{html.escape(reason)}</p>'
    drops: list[str] = []
    for rule_item in item.get("items") or []:
        if not isinstance(rule_item, dict):
            continue
        value = rule_item.get("deduction")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            continue
        rule = str(rule_item.get("rule") or "")
        title = RULE_TITLES.get(rule, rule)
        hint = _deduction_hint(rule_item)
        status = "待复核 " if rule_item.get("status") == PENDING else ""
        title_attr = f' title="{html.escape(hint)}"' if hint else ""
        actual = str(rule_item.get("actual") or "")
        actual_html = f"<em>{html.escape(actual)}</em>" if actual else ""
        drops.append(
            f"<li{title_attr}><span>{status}{html.escape(title)}{actual_html}</span>"
            f"<b>−{value:g}</b></li>"
        )
    if not drops:
        return '<p class="clear">全部通过</p>'
    return f'<ul class="drops">{"".join(drops)}</ul>'


def _deduction_hint(item: dict[str, Any]) -> str:
    parts: list[str] = []
    expected = str(item.get("expected") or "")
    actual = str(item.get("actual") or "")
    if expected:
        parts.append(f"期望：{expected}")
    if actual:
        parts.append(f"实际：{actual}")
    return "；".join(parts)


def _build_html(summary: dict[str, Any]) -> str:
    facts = summary.get("facts") or {}
    rule_rows = []
    for rule in summary.get("rules") or []:
        rate = rule.get("通过率")
        rule_rows.append(
            "<tr><td>{}</td><td><code>{}</code> {}</td><td>{}</td>"
            "<td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(str(rule.get("维度"))),
                html.escape(str(rule.get("规则"))),
                html.escape(str(rule.get("细分项"))),
                html.escape(str(rule.get("含义") or "—")),
                html.escape(str(rule.get("期望示例") or "—")),
                html.escape(str(rule.get("单条满分"))),
                html.escape(str(rule.get("平均得分"))),
                "—" if rate is None else f"{rate}%",
            )
        )
    sample_rows = []
    for row in summary.get("samples") or []:
        sample_rows.append(
            "<tr><td><code>{}</code></td><td>{}</td><td>{}</td>"
            "<td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>"
            "<td>{}</td></tr>".format(
                html.escape(str(row.get("样本"))),
                html.escape(str(row.get("主题") or "—")),
                html.escape(_score_text(row.get("总分"))),
                html.escape(_score_text(row.get("规范符合"))),
                html.escape(_score_text(row.get("可见性"))),
                html.escape(str(row.get("状态"))),
                html.escape(str(row.get("结论"))),
                html.escape(str(row.get("失败项") or "—")),
                html.escape(str(row.get("待复核项") or "—")),
            )
        )
    score_cards = _score_cards_html(summary)
    dimension_kpis = _dimension_kpis(summary)
    capture = (
        f"<p class=\"warn\">采集异常：{html.escape(summary['captureError'])}</p>"
        if summary.get("captureError")
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>倒计时目标效果评测</title>
<style>
body {{ margin:0; padding:28px; font-family:"Microsoft YaHei",system-ui,sans-serif;
  background:#0f172a; color:#e5edf8; }}
h1 {{ font-size:22px; margin:0 0 6px; }}
h2 {{ font-size:16px; margin:28px 0 10px; }}
p {{ color:#9fb0c8; }}
.kpis {{ display:flex; gap:12px; flex-wrap:wrap; margin:16px 0; }}
.kpi {{ background:#17233b; border:1px solid #263a5c; border-radius:10px; padding:12px 16px; }}
.kpi strong {{ display:block; font-size:22px; color:#7dd3fc; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; background:#131d31; }}
th,td {{ text-align:left; padding:7px 9px; border-bottom:1px solid #22314d; vertical-align:top; }}
th {{ color:#9fb0c8; font-weight:600; }}
code {{ color:#f5c76b; }}
.table-scroll {{ overflow-x:auto; border-radius:8px; }}
table.rule-table {{ min-width:1120px; }}
table.rule-table td:nth-child(1) {{ white-space:nowrap; }}
table.rule-table td:nth-child(3) {{ min-width:260px; }}
table.rule-table td:nth-child(4) {{ min-width:150px; }}
table.sample-table {{ min-width:900px; }}
.warn {{ color:#fca5a5; }}
.score-grid {{ display:grid; grid-template-columns:repeat(auto-fill,
  minmax(min(210px,100%),1fr)); gap:14px; }}
.score-card {{ display:flex; flex-direction:column; gap:9px; padding:12px; border:1px solid #263a5c;
  border-radius:12px; background:#131d31; }}
.score-card.failed {{ border-color:#7f3b47; }}
.score-card.partial {{ border-color:#7d6230; }}
.score-card .shot {{ position:relative; display:block; width:100%;
  aspect-ratio:1 / 1; overflow:hidden; border-radius:9px; background:#0b1425; }}
.score-card .shot img {{ position:absolute; inset:0; width:100%; height:100%;
  object-fit:contain; }}
.score-card .shot.empty {{ display:flex; align-items:center; justify-content:center;
  color:#6f8099; font-size:12px; }}
.score-head {{ display:flex; align-items:center; justify-content:space-between; gap:8px; }}
.score-head b {{ color:#e5edf8; font-size:14px; }}
.verdict {{ max-width:62%; overflow:hidden; padding:2px 7px; border-radius:999px;
  background:#22314d; color:#c7d5e8; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }}
.verdict.failed {{ background:#4a2028; color:#fca5a5; }}
.verdict.partial {{ background:#493a1d; color:#f5c76b; }}
.verdict.success {{ background:#14392a; color:#7ee2a8; }}
.score-total {{ display:flex; align-items:baseline; gap:8px; }}
.score-total strong {{ color:#7dd3fc; font-size:30px; line-height:1; }}
.score-total span {{ color:#9fb0c8; font-size:11px; }}
.score-card ul {{ display:flex; flex-direction:column; gap:5px; margin:0; padding:0;
  list-style:none; }}
.score-card li {{ display:block; color:#9fb0c8; font-size:11px; }}
.score-card .dim-head {{ display:grid; grid-template-columns:62px 1fr 66px;
  align-items:center; gap:6px; }}
.score-card .dim-head i {{ height:5px; overflow:hidden; border-radius:99px; background:#22314d; }}
.score-card .dim-head em {{ display:block; height:100%; border-radius:99px; background:#38bdf8; }}
.score-card li b {{ color:#e5edf8; text-align:right; font-weight:600; }}
.score-card ul.drops {{ gap:2px; margin:4px 0 0; padding-left:2px; }}
.score-card ul.drops li {{ display:flex; justify-content:space-between; gap:6px;
  color:#8ea3c0; font-size:10px; line-height:1.45; }}
.score-card ul.drops li span {{ min-width:0; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; }}
.score-card ul.drops li span em {{ display:inline; height:auto; margin-left:6px;
  border-radius:0; background:none; color:#6f849f; font-style:normal; }}
.score-card ul.drops li b {{ color:#f0a3a3; font-weight:600; white-space:nowrap; }}
.score-card .clear {{ margin:4px 0 0 2px; color:#5f7590; font-size:10px; }}
</style></head><body>
<h1>倒计时目标效果评测</h1>
<p>profile <code>{html.escape(str(summary.get("profile")))}</code>（rubric
v{html.escape(str(summary.get("rubricVersion", 2)))}）；只做确定性规则打分，
评分由规范符合 60 与可见性 40 构成；版式与素材规则只做诊断、不参与计分；
非 Pixso 图+蒙层主题不计规范分。</p>
{capture}
<div class="kpis">
<div class="kpi">样本数<strong>{facts.get("total", 0)}</strong></div>
<div class="kpi">平均总分<strong>{facts.get("averageScore", 0)}</strong></div>
<div class="kpi">通过<strong>{facts.get("passed", 0)}</strong></div>
<div class="kpi">待复核<strong>{facts.get("partial", 0)}</strong></div>
<div class="kpi">失败<strong>{facts.get("failed", 0)}</strong></div>
<div class="kpi">规则通过率<strong>{facts.get("passRate", 0)}%</strong></div>
</div>
<div class="kpis">
{''.join(dimension_kpis)}
</div>
<p>评分口径：规范符合 60、可见性 40，两项固定构成 100 分；不适用维度记 0 分并
展示原因，维度分相加即总分。版式与素材规则只做诊断，不计分也不影响结论。
待复核按半通过计分。
细分项“单条满分”= 所在维度分值 ÷ 该维度适用规则数，会随样本变化；“平均得分”是各样本
单条得分的算术平均，按一位小数展示，同一维度下累加与维度平均可能存在 ≤0.5 的取整差。</p>
<h2>细分维度明细（整批平均）</h2>
<div class="table-scroll"><table class="rule-table"><thead><tr><th>维度</th><th>细分项</th>
<th>含义</th>
<th>期望示例</th><th>单条满分</th><th>平均得分</th><th>通过率</th></tr></thead>
<tbody>{''.join(rule_rows)}</tbody></table></div>
<h2>卡片评分总览</h2>
{score_cards}
<h2>样本结论</h2>
<div class="table-scroll"><table class="sample-table"><thead><tr><th>样本</th>
<th>主题</th><th>总分</th>
<th>规范符合</th><th>可见性</th>
<th>状态</th><th>结论</th><th>失败项</th><th>待复核项</th></tr></thead>
<tbody>{''.join(sample_rows)}</tbody></table></div>
</body></html>
"""
