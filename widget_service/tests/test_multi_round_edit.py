# -*- coding: utf-8 -*-
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
# ruff: noqa: E402
import asyncio
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLOUD_ROOT = PROJECT_ROOT / "cloud"
APP_VERSION = ".".join(("11", "7", "5", "205"))
ROM_VERSION = "CLS-AL30 " + ".".join(("6", "0", "0", "328"))
if str(CLOUD_ROOT) not in sys.path:
    sys.path.insert(0, str(CLOUD_ROOT))

from api.schemas import GenerateWidgetCardRequest
from config.config import get_settings
from core.errors import ErrorCode, GenerationStatus
from models.generation import TaskSpec
from services.prompt_builder import PromptBuilder
from services.source_artifact_repository import (
    SourceArtifactError,
    SourceArtifactRepository,
)
from services.widget_generation_service import WidgetGenerationService
from utils.upload_file_obs import UploadFileOSMS


def _base_request(**updates):
    values = {
        "uid": "user-a",
        "device": {"romVersion": "6.0"},
        "prdVer": APP_VERSION,
        "userQuery": "生成天气卡片",
        "title": "天气",
        "description": "当前天气",
        "candidateDataBindings": [
            {
                "capabilityId": "ViewWeather",
                "arguments": {"prefectureName": "上海市", "forecastDays": 1},
                "writeResultTo": "/data/weather",
                "candidateOutputFields": ["/current/condition"],
            }
        ],
        "candidateEventCandidates": [
            {
                "capabilityId": "event.open.weather",
                "action": {
                    "call": "clickToDeeplink",
                    "args": {
                        "intentName": "Weather_CityCode",
                        "bundleName": "",
                        "abilityName": "",
                        "uri": (
                            "{{ 'hww://www.huawei.com/totemweather?enterType=share&cityCode=' "
                            "+ ${/data/weather/location/cityCode} }}"
                        ),
                    },
                },
            }
        ],
        "candidateAssetIds": ["asset.drop_1"],
    }
    values.update(updates)
    return GenerateWidgetCardRequest(**values)


@pytest.fixture
def editable_artifact_storage(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "enable_a2ui_model_mock", True)
    monkeypatch.setattr(settings, "enable_semantic_widget_edit", False)
    # 本组覆盖共用来源存储与请求解析；新编辑编排在语义编辑专项中验证。
    monkeypatch.setattr(settings, "enable_static_content_generation_policy", False)
    monkeypatch.setattr(settings, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(settings, "artifact_base_url", "https://obs.test/widget")
    monkeypatch.setattr(settings, "enable_widget_edit", True)
    monkeypatch.setattr(settings, "enable_artifact_download_mock", True)
    monkeypatch.setattr(
        "services.artifact_store.file_obs",
        UploadFileOSMS(
            base_url=settings.artifact_base_url,
            mock_storage_dir=tmp_path / "mock_obs",
        ),
    )
    return tmp_path / "mock_obs"


def test_request_distinguishes_create_and_edit_omission():
    with pytest.raises(ValidationError, match="title is required in create mode"):
        GenerateWidgetCardRequest(
            uid="user-a",
            device={"romVersion": "6.0"},
            userQuery="生成卡片",
            description="说明",
        )

    edit_request = GenerateWidgetCardRequest(
        uid="user-a",
        device={"romVersion": "6.0"},
        userQuery="改成蓝色",
        sourceArtifactUrl="https://obs.test/widget/artifact_x.md",
    )
    assert edit_request.candidateDataBindings is None
    assert "candidateDataBindings" not in edit_request.model_fields_set

    clear_request = GenerateWidgetCardRequest(
        uid="user-a",
        device={"romVersion": "6.0"},
        userQuery="清空数据",
        sourceArtifactUrl="https://obs.test/widget/artifact_x.md",
        candidateDataBindings=[],
    )
    assert clear_request.candidateDataBindings == []
    assert "candidateDataBindings" in clear_request.model_fields_set


@pytest.mark.parametrize("value", [None, ""])
def test_edit_rejects_null_or_empty_source_url(value):
    with pytest.raises(ValidationError, match="sourceArtifactUrl"):
        GenerateWidgetCardRequest(
            uid="user-a",
            device={"romVersion": "6.0"},
            userQuery="修改卡片",
            sourceArtifactUrl=value,
        )


@pytest.mark.asyncio
async def test_source_artifact_remote_mode_uses_shared_download_utility(
    editable_artifact_storage,
    monkeypatch,
):
    """验证关闭 mock 后由公共 URL 下载方法读取来源 artifact。"""
    settings = get_settings()
    created = await WidgetGenerationService().generate_widget_card_a2ui_form(_base_request())
    source_file = editable_artifact_storage / created.artifactUrl.rsplit("/", 1)[-1]
    source_content = source_file.read_bytes()
    requested: dict = {}

    async def fake_download(url, save_path, **kwargs):
        requested["url"] = url
        requested["save_path"] = save_path
        requested.update(kwargs)
        Path(save_path).write_bytes(source_content)
        return save_path

    monkeypatch.setattr(settings, "enable_artifact_download_mock", False)
    monkeypatch.setattr(
        "services.source_artifact_repository.download_file",
        fake_download,
    )

    loaded = await asyncio.to_thread(
        SourceArtifactRepository().load,
        created.artifactUrl,
    )

    assert loaded.download_mode == "remote"
    assert loaded.artifact.meta.artifactId in created.artifactUrl
    assert requested["url"] == created.artifactUrl
    assert requested["max_size_bytes"] == settings.source_artifact_max_bytes
    assert requested["timeout_seconds"] == settings.source_artifact_read_timeout_seconds
    assert requested["allow_redirects"] is False
    assert not Path(requested["save_path"]).exists()


@pytest.mark.asyncio
async def test_source_artifact_load_does_not_validate_url_storage(
    editable_artifact_storage,
):
    created = await WidgetGenerationService().generate_widget_card_a2ui_form(_base_request())
    source_name = created.artifactUrl.rsplit("/", 1)[-1]
    loaded = await asyncio.to_thread(
        SourceArtifactRepository().load,
        f"http://other.test/other-prefix/{source_name}?token=test#fragment",
    )

    assert loaded.artifact.meta.artifactId in source_name


def test_missing_source_artifact_is_structured(editable_artifact_storage):
    url = "https://obs.test/widget/artifact_11111111-1111-4111-8111-111111111111.md"
    with pytest.raises(SourceArtifactError) as exc_info:
        SourceArtifactRepository().load(url)

    assert exc_info.value.error_code == ErrorCode.SOURCE_ARTIFACT_NOT_FOUND


def test_v1_artifact_is_reported_as_unsupported():
    content = '```schema\n{"schemaVersion":"widget-artifact-v1"}\n```\n'

    with pytest.raises(SourceArtifactError) as exc_info:
        SourceArtifactRepository()._parse(content)

    assert exc_info.value.error_code == ErrorCode.SOURCE_ARTIFACT_SCHEMA_UNSUPPORTED


@pytest.mark.parametrize(
    "generation_method",
    [
        "generate_widget_card_a2ui_form",
        "generate_widget_card_compact_dsl",
    ],
)
@pytest.mark.asyncio
async def test_edit_feature_switch_does_not_fall_back_to_create(
    monkeypatch,
    generation_method,
):
    monkeypatch.setattr(get_settings(), "enable_widget_edit", False)
    request = GenerateWidgetCardRequest(
        uid="user-a",
        device={"romVersion": "6.0"},
        userQuery="修改卡片",
        sourceArtifactUrl="https://obs.test/widget/artifact_x.md",
    )

    service = WidgetGenerationService()
    response = await getattr(service, generation_method)(request)

    assert response.status == GenerationStatus.UNSUPPORTED
    assert response.errorCode == ErrorCode.WIDGET_EDIT_DISABLED.value
    assert response.artifactUrl == ""


@pytest.mark.parametrize("size", ["2x2", "2x4"])
def test_edit_prompt_contains_previous_genui_but_not_source_url(size):
    previous_genui = '{"version":"v0.9"}\n{}\n{}'
    task_spec = TaskSpec(
        userQuery="改成蓝色",
        size=size,
        dataModelSchema={"data": {}},
    )
    builder = PromptBuilder()
    create_prompt = builder.build(task_spec)
    prompt = builder.build(task_spec, previous_genui=previous_genui)

    edit_context = json.loads(prompt[1].get("content"))
    system_prompt = prompt[0].get("content")
    assert isinstance(system_prompt, str)
    create_system_prompt = create_prompt[0].get("content")
    assert isinstance(create_system_prompt, str)
    # 沿用当前同规格协议提示词，不再绑定已退出的固定骨架章节标题。
    assert create_system_prompt in system_prompt
    assert "编辑模式附加规则" in system_prompt
    assert edit_context.get("mode") == "edit"
    assert edit_context.get("targetSize") == size
    assert edit_context.get("previousGenui") == previous_genui
    assert edit_context.get("editInstruction") == "改成蓝色"
    new_task_spec = edit_context.get("newTaskSpec")
    assert isinstance(new_task_spec, dict)
    assert new_task_spec.get("size") == size
    assert "appVersion" not in new_task_spec
    assert "sourceArtifactUrl" not in str(prompt)
