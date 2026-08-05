# -*- coding: utf-8 -*-
import io
import json
import sys
from importlib import import_module
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_prompt_builder_module = import_module("scripts.build_sft_prompt")
PromptBuildError = _prompt_builder_module.PromptBuildError
build_messages = _prompt_builder_module.build_messages
main = _prompt_builder_module.main


def _task_spec(user_query: str = "天气卡片") -> dict:
    return {
        "userQuery": user_query,
        "size": "2x2",
        "eventCandidates": [],
        "dataModelSchema": {"data": {}},
        "assetCandidates": [],
    }


def test_build_messages_standard_create_injects_task_spec_and_keeps_raw_query():
    result = build_messages(
        _task_spec("生成一张天气卡片"),
        route="standard",
        mode="create",
    )

    assert result[1] == {"role": "user", "content": "生成一张天气卡片"}
    assert '"userQuery":"生成一张天气卡片"' in result[0]["content"]
    assert result[0]["role"] == "system"


def test_standard_edit_uses_previous_genui_and_degradation_context():
    messages = build_messages(
        _task_spec("改成蓝色"),
        route="standard",
        mode="edit",
        previous_content="old-genui",
        degradation_context="weather removed",
    )

    payload = json.loads(messages[1]["content"])
    assert payload["previousGenui"] == "old-genui"
    assert payload["degradationContext"] == "weather removed"
    assert "sourceArtifactUrl" not in messages[1]["content"]


def test_repair_appends_repair_prompt_and_preserves_quality_errors():
    messages = build_messages(
        _task_spec("天气卡片"),
        route="standard",
        mode="repair",
        invalid_source_dsl="invalid-dsl",
        quality_errors=[{"stage": "validation", "code": "E001", "message": "bad root"}],
    )

    assert "不可信数据" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["invalidSourceDsl"] == "invalid-dsl"
    assert payload["qualityErrors"][0]["code"] == "E001"
    assert payload["dslFormat"] == "a2ui-form"


def test_design_and_terse_create_use_task_spec_as_user_content():
    expected_markers = {
        "design": "独立 Form GenUI 裸直出提示词",
        "terse": "TerseDSL-Nested-2 生成器",
    }
    for route, marker in expected_markers.items():
        messages = build_messages(_task_spec("天气卡片"), route=route, mode="create")

        assert marker in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert json.loads(messages[1]["content"])["userQuery"] == "天气卡片"


def test_edit_requires_previous_content():
    with pytest.raises(PromptBuildError, match="previous content"):
        build_messages(_task_spec("改成蓝色"), route="standard", mode="edit")


def test_repair_requires_source_and_quality_errors():
    with pytest.raises(PromptBuildError, match="invalid source DSL"):
        build_messages(_task_spec(), route="standard", mode="repair")

    with pytest.raises(PromptBuildError, match="quality errors"):
        build_messages(
            _task_spec(),
            route="standard",
            mode="repair",
            invalid_source_dsl="invalid",
        )


def test_cli_reads_stdin_and_outputs_messages(capsys, monkeypatch):
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps(_task_spec("stdin query"), ensure_ascii=False)),
    )

    exit_code = main(["--route", "standard", "--mode", "create"])

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert len(output["messages"]) == 2
    assert output["messages"][1]["content"] == "stdin query"


def test_cli_sft_output_appends_assistant_file(tmp_path, capsys, monkeypatch):
    task_file = tmp_path / "task.json"
    assistant_file = tmp_path / "assistant.genui"
    task_file.write_text(
        json.dumps(_task_spec("sft query"), ensure_ascii=False),
        encoding="utf-8",
    )
    assistant_file.write_text("```genui\noutput\n```", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    exit_code = main(
        [
            "--input",
            str(task_file),
            "--output-format",
            "sft",
            "--assistant-file",
            str(assistant_file),
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["messages"][-1] == {
        "role": "assistant",
        "content": "```genui\noutput\n```",
    }


@pytest.mark.parametrize(
    ("arguments", "expected_message"),
    [
        (["--mode", "edit"], "previous content"),
        (["--mode", "repair", "--invalid-source-file", "missing.dsl"], "quality errors"),
    ],
)
def test_cli_reports_invalid_mode_inputs(arguments, expected_message, capsys, monkeypatch):
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps(_task_spec(), ensure_ascii=False)),
    )

    exit_code = main(arguments)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert expected_message in captured.err


def test_cli_reports_malformed_json(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not-json"))

    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "JSON" in captured.err
