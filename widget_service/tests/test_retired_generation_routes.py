"""退役路线不能恢复，保留既有修复预算及独立语义编辑。"""

import json
from types import SimpleNamespace

import pytest

from api.schemas import GenerateWidgetCardRequest
from config.config import Settings, get_settings
from core.errors import ErrorCode, GenerationStatus
from custom.a2ui_model_client import A2UIModelClient
from services.artifact_store import ArtifactStore
from services.compact_repair_strategy import CompactRepairStrategyTracker
from services.generation_pipeline import (
    DslProcessingResult,
    DslProcessorKind,
    QualityIssue,
    get_dsl_processor,
)
from services.widget_edit_utils import _components, _load_json, _messages, _same, source_digest
from services.widget_generation_service import WidgetGenerationService


@pytest.fixture
def failing_generation(monkeypatch):
    settings = get_settings()
    for name, value in {
        "enable_a2ui_model_mock": False,
        "enable_artifact_validation": False,
        "enable_validation_failure_retry": True,
        "enable_static_content_generation_policy": False,
        "enable_generation_trace_recording": False,
    }.items():
        monkeypatch.setattr(settings, name, value)
    state = SimpleNamespace(calls=[], saved=[], retryable=True)
    source = '["root","Text",{"content":"测试"}]'

    async def generate(_client, _messages, profile=None, **_kwargs):
        model_format = (profile or {}).get("format")
        state.calls.append(("initial", model_format))
        if model_format == "raw-json":
            return json.dumps({"name": "submit_card_plan", "arguments": {
                "info_required": [{"text": "测试", "requirement": "显示测试",
                                   "priority": "must", "componentHints": ["EmphasisText"]}],
                "layoutHints": ["W-top-bottom"],
            }}, ensure_ascii=False)
        assert model_format == "compact-dsl"
        return source

    async def repair(_client, _messages, profile=None, **_kwargs):
        model_format = (profile or {}).get("format")
        assert model_format == "compact-dsl"
        state.calls.append(("repair", model_format))
        return source

    def process(source_dsl, _context):
        return DslProcessingResult(source_dsl=source_dsl, issues=(QualityIssue(
            stage="validation", code="COMPACT_DSL_VALIDATION_FAILED",
            message="component root: vertical layout requires at least 164vp within 126vp",
        ),))

    def directive(*_args, **_kwargs):
        return SimpleNamespace(retryable=state.retryable, to_prompt_payload=lambda: {
            "category": "layout_capacity", "scope": "sublayout",
            "repairStrategy": "rebudget", "retryable": state.retryable,
        })

    def save(*_args, **_kwargs):
        pytest.fail("修复失败不得保存或额外兜底")

    monkeypatch.setattr(A2UIModelClient, "generate", generate)
    monkeypatch.setattr(A2UIModelClient, "generate_repair", repair)
    monkeypatch.setattr(get_dsl_processor(DslProcessorKind.DESIGN_COMPACT), "process", process)
    monkeypatch.setattr(CompactRepairStrategyTracker, "next_directive", directive)
    monkeypatch.setattr(ArtifactStore, "save", save)
    monkeypatch.setattr(WidgetGenerationService, "_enable_card_template", lambda _self: False)
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [1, 3, 5, 7])
@pytest.mark.parametrize("retryable", [False, True])
async def test_failed_generation_ends_at_existing_budget(
    failing_generation, monkeypatch, budget, retryable,
):
    monkeypatch.setattr(get_settings(), "validation_failure_max_repair_attempts", budget)
    failing_generation.retryable = retryable
    request = GenerateWidgetCardRequest(
        uid="retired-route-test", prdVer="11.7.7.331", device={"romVersion": "7.0"},
        userQuery="创建测试卡片", size="2x4", title="测试", description="离线边界回归",
        candidateDataBindings=[], candidateEventCandidates=[], candidateAssetIds=[],
    )
    response = await WidgetGenerationService().generate_widget_card_compact_dsl(request)
    assert response.status == GenerationStatus.FAILED
    assert response.errorCode == ErrorCode.VALIDATION_FAILED.value
    assert not response.artifactUrl
    repairs = budget if retryable else 0
    assert failing_generation.calls == [
        ("initial", "raw-json"), ("initial", "compact-dsl"),
        *[("repair", "compact-dsl")] * repairs,
    ]


def test_retired_settings_cannot_be_reenabled_by_environment(monkeypatch):
    retired = ("enable_single_step_widget_edit", "enable_single_step_generation_fallback")
    for name in retired:
        monkeypatch.setenv(name.upper(), "true")
        monkeypatch.setenv("WIDGET_SERVICE_" + name.upper(), "true")
    settings = Settings(_env_file=None)
    for name in retired:
        assert name not in Settings.model_fields
        assert not hasattr(settings, name)
    assert settings.enable_semantic_widget_edit is True
    assert settings.enable_widget_edit is True


@pytest.mark.parametrize("source", [
    '{"a":1,"a":2}', '{"a":{"b":1,"b":2}}',
])
def test_shared_edit_parser_rejects_duplicate_keys(source):
    with pytest.raises(ValueError, match="duplicate JSON key"):
        _load_json(source)


@pytest.mark.parametrize("source", ["", "[]", "1", '["root","Text",{}]'])
def test_shared_edit_parser_requires_expanded_messages(source):
    with pytest.raises(ValueError, match="expanded A2UI"):
        _messages(source)


def test_shared_edit_components_preserve_identity_and_strict_types():
    source = '{"updateComponents":{"components":[{"id":"title","component":"Text"}]}}'
    nodes = _components(_messages(source))
    assert nodes.get("title") == {"id": "title", "component": "Text"}
    assert _same({"b": 2, "a": 1}, {"a": 1, "b": 2})
    assert not _same(True, 1)
    assert not _same([1, 2], [2, 1])
    assert not _same({}, {"value": None})
    assert source_digest(source) == source_digest(source)
    assert source_digest(source) != source_digest(source + "\n")
    duplicate = _messages(source + "\n" + source)
    with pytest.raises(ValueError, match="unique nonempty component IDs"):
        _components(duplicate)
