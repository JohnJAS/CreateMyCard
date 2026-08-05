# -*- coding: utf-8 -*-
import io
import json
import os
import subprocess
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


def test_create_rejects_previous_content_even_when_empty():
    with pytest.raises(PromptBuildError, match="create mode"):
        build_messages(
            _task_spec("新建"),
            route="standard",
            mode="create",
            previous_content="",
        )


def test_repair_allows_non_empty_previous_content_as_edit_context():
    messages = build_messages(
        _task_spec("改成蓝色"),
        route="standard",
        mode="repair",
        previous_content="old-genui",
        invalid_source_dsl="invalid-dsl",
        quality_errors=[{"stage": "validation", "code": "E001", "message": "bad root"}],
    )

    repair_payload = json.loads(messages[1]["content"])
    original_payload = json.loads(repair_payload["originalUserContent"])
    assert original_payload["mode"] == "edit"
    assert original_payload["previousGenui"] == "old-genui"


@pytest.mark.parametrize(
    ("route", "expected_format"),
    [
        ("design", "design-compact-dsl"),
        ("terse", "terse-dsl-nested-2"),
    ],
)
def test_design_routes_edit_include_source_format(route, expected_format):
    messages = build_messages(
        _task_spec("改成蓝色"),
        route=route,
        mode="edit",
        previous_content="old-design-token",
    )

    payload = json.loads(messages[1]["content"])
    assert payload["previousDesignToken"]["format"] == expected_format
    assert payload["previousDesignToken"]["content"] == "old-design-token"


@pytest.mark.parametrize(
    ("route", "expected_format"),
    [
        ("design", "design-compact-dsl"),
        ("terse", "terse-dsl-nested-2"),
    ],
)
def test_design_routes_repair_include_source_format(route, expected_format):
    messages = build_messages(
        _task_spec("天气卡片"),
        route=route,
        mode="repair",
        invalid_source_dsl="invalid-design-token",
        quality_errors=[{"stage": "validation", "code": "E001", "message": "bad root"}],
    )

    payload = json.loads(messages[1]["content"])
    assert payload["dslFormat"] == expected_format


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


def test_module_import_works_without_cloud_pythonpath():
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from scripts.build_sft_prompt import build_messages; print(build_messages.__name__)",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "build_messages"


def test_cli_subprocess_preserves_utf8_for_stdin_and_stdout():
    task_spec = _task_spec("生成一张天气卡片")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.build_sft_prompt", "--route", "standard"],
        cwd=PROJECT_ROOT,
        input=(json.dumps(task_spec, ensure_ascii=False) + "\n").encode("utf-8"),
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    output = json.loads(result.stdout.decode("utf-8"))
    assert output["messages"][1]["content"] == "生成一张天气卡片"
