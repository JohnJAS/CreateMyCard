# -*- coding: utf-8 -*-
"""构造与在线卡片服务一致的 SFT 模型输入。"""

from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

_CLOUD_ROOT = Path(__file__).resolve().parents[1] / "cloud"
if str(_CLOUD_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLOUD_ROOT))

ValidationError = import_module("pydantic").ValidationError
TaskSpec = import_module("models.generation").TaskSpec
PromptBuilder = import_module("services.prompt_builder").PromptBuilder
_protocol_registry = import_module("services.protocol_registry")
DESIGN_COMPACT_PROFILE_ID = _protocol_registry.DESIGN_COMPACT_PROFILE_ID
TERSE_DSL_NESTED2_PROFILE_ID = _protocol_registry.TERSE_DSL_NESTED2_PROFILE_ID
A2UIProtocolRegistry = _protocol_registry.A2UIProtocolRegistry

Route = Literal["standard", "design", "terse"]
Mode = Literal["create", "edit", "repair"]

_ROUTES: tuple[Route, ...] = ("standard", "design", "terse")
_MODES: tuple[Mode, ...] = ("create", "edit", "repair")
_SOURCE_FORMATS: dict[Route, str] = {
    "standard": "a2ui-form",
    "design": DESIGN_COMPACT_PROFILE_ID,
    "terse": TERSE_DSL_NESTED2_PROFILE_ID,
}


class PromptBuildError(ValueError):
    """表示输入无法构造成合法模型消息。"""


def build_messages(
    task_spec_payload: dict[str, Any],
    *,
    route: str = "standard",
    mode: str = "create",
    previous_content: str | None = None,
    degradation_context: str = "",
    invalid_source_dsl: str | None = None,
    quality_errors: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """按线上路由构造两条模型消息，不调用模型。"""
    normalized_route = _normalize_choice(route, _ROUTES, "route")
    normalized_mode = _normalize_choice(mode, _MODES, "mode")
    task_spec = _validate_task_spec(task_spec_payload)
    if normalized_mode == "create" and previous_content is not None:
        raise PromptBuildError("create mode does not accept previous content")
    if normalized_mode == "edit" and not _has_content(previous_content):
        raise PromptBuildError("edit mode requires previous content")
    if normalized_mode == "repair" and previous_content is not None:
        if not _has_content(previous_content):
            raise PromptBuildError("repair mode previous content must not be empty")

    initial_messages = _build_initial_messages(
        task_spec,
        normalized_route,
        previous_content=previous_content,
        degradation_context=degradation_context,
    )
    if normalized_mode != "repair":
        return initial_messages

    if not _has_content(invalid_source_dsl):
        raise PromptBuildError("repair mode requires invalid source DSL")
    normalized_errors = _normalize_quality_errors(quality_errors)
    return PromptBuilder().build_repair(
        initial_messages,
        invalid_source_dsl,
        normalized_errors,
        dsl_format=_SOURCE_FORMATS[normalized_route],
    )


def _build_initial_messages(
    task_spec: TaskSpec,
    route: Route,
    *,
    previous_content: str | None,
    degradation_context: str,
) -> list[dict[str, str]]:
    builder = PromptBuilder()
    if route == "standard":
        return builder.build(
            task_spec,
            removed_capability_summary=degradation_context,
            previous_genui=previous_content,
        )

    profile_id = _design_profile_id(route)
    system_prompt = A2UIProtocolRegistry.read_design_prompt(profile_id)
    if route == "design":
        return builder.build_design_compact(
            task_spec,
            system_prompt,
            previous_design_token=previous_content,
        )
    return builder.build_terse_dsl_nested2(
        task_spec,
        system_prompt,
        previous_design_token=previous_content,
    )


def _design_profile_id(route: Route) -> str:
    if route == "design":
        return DESIGN_COMPACT_PROFILE_ID
    if route == "terse":
        return TERSE_DSL_NESTED2_PROFILE_ID
    raise PromptBuildError(f"route does not have a design profile: {route}")


def _validate_task_spec(payload: object) -> TaskSpec:
    if not isinstance(payload, dict):
        raise PromptBuildError("TaskSpec JSON must be an object")
    try:
        return TaskSpec.model_validate(payload)
    except ValidationError as exc:
        raise PromptBuildError(f"invalid TaskSpec: {exc}") from exc


def _normalize_choice(value: str, choices: tuple[str, ...], name: str) -> str:
    if value not in choices:
        choices_text = ", ".join(choices)
        raise PromptBuildError(f"invalid {name} {value!r}; expected one of: {choices_text}")
    return value


def _normalize_quality_errors(
    quality_errors: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    if not isinstance(quality_errors, list) or not quality_errors:
        raise PromptBuildError("repair mode requires quality errors")
    normalized: list[dict[str, str]] = []
    required_fields = ("stage", "code", "message")
    for index, item in enumerate(quality_errors):
        if not isinstance(item, dict):
            raise PromptBuildError(f"quality errors item {index} must be an object")
        if any(
            not isinstance(item.get(field), str) or not item[field].strip()
            for field in required_fields
        ):
            raise PromptBuildError(
                f"quality errors item {index} requires non-empty stage, code, and message"
            )
        normalized.append({field: item[field] for field in required_fields})
    return normalized


def _has_content(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptBuildError(f"cannot read {label}: {path}") from exc


def _read_json_text(text: str, label: str) -> object:
    if not text.strip():
        raise PromptBuildError(f"{label} is empty")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PromptBuildError(f"{label} is not valid JSON: {exc.msg}") from exc


def _read_input(path: Path | None) -> object:
    if path is not None:
        return _read_json_text(_read_text(path, "input file"), "input file")
    return _read_json_text(_read_stdin_text(), "stdin")


def _read_stdin_text() -> str:
    stdin_buffer = getattr(sys.stdin, "buffer", None)
    if stdin_buffer is None:
        return sys.stdin.read()
    raw_input = stdin_buffer.read()
    if not isinstance(raw_input, bytes):
        raise PromptBuildError("stdin buffer must return bytes")
    try:
        return raw_input.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PromptBuildError("stdin must be valid UTF-8") from exc


def _write_stdout(serialized: str) -> None:
    output = serialized + "\n"
    stdout_buffer = getattr(sys.stdout, "buffer", None)
    if stdout_buffer is None:
        sys.stdout.write(output)
        return
    stdout_buffer.write(output.encode("utf-8"))
    stdout_buffer.flush()


def _read_optional_file(path: Path | None, label: str) -> str | None:
    if path is None:
        return None
    return _read_text(path, label)


def _read_quality_errors(path: Path | None) -> list[dict[str, str]] | None:
    if path is None:
        return None
    payload = _read_json_text(_read_text(path, "quality errors file"), "quality errors file")
    if not isinstance(payload, list):
        raise PromptBuildError("quality errors file must contain a JSON array")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="构造与在线卡片服务一致的 SFT Prompt，不调用模型。"
    )
    parser.add_argument("--input", type=Path, help="TaskSpec JSON 文件；省略时从 stdin 读取")
    parser.add_argument("--route", choices=_ROUTES, default="standard")
    parser.add_argument("--mode", choices=_MODES, default="create")
    parser.add_argument("--previous-file", type=Path, help="上一轮 genui 或源 DSL 文件")
    parser.add_argument("--degradation-context", default="")
    parser.add_argument("--invalid-source-file", type=Path, help="repair 的源 DSL 文件")
    parser.add_argument("--quality-errors-file", type=Path, help="repair 错误 JSON 数组文件")
    parser.add_argument("--assistant-file", type=Path, help="SFT assistant 标签文件")
    parser.add_argument(
        "--output-format",
        choices=("messages", "sft"),
        default="messages",
        help="messages 只输出模型输入；sft 追加 assistant 标签",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.mode == "edit" and args.previous_file is None:
            raise PromptBuildError("edit mode requires previous content file")
        if args.mode == "repair" and args.invalid_source_file is None:
            raise PromptBuildError("repair mode requires invalid source DSL file")
        if args.mode == "repair" and args.quality_errors_file is None:
            raise PromptBuildError("repair mode requires quality errors file")
        if args.output_format == "messages" and args.assistant_file is not None:
            raise PromptBuildError("assistant file requires --output-format sft")
        if args.output_format == "sft" and args.assistant_file is None:
            raise PromptBuildError("sft output requires assistant file")

        task_spec_payload = _read_input(args.input)
        previous_content = _read_optional_file(args.previous_file, "previous content file")
        invalid_source_dsl = _read_optional_file(
            args.invalid_source_file,
            "invalid source DSL file",
        )
        quality_errors = _read_quality_errors(args.quality_errors_file)
        messages = build_messages(
            task_spec_payload,
            route=args.route,
            mode=args.mode,
            previous_content=previous_content,
            degradation_context=args.degradation_context,
            invalid_source_dsl=invalid_source_dsl,
            quality_errors=quality_errors,
        )
        if args.output_format == "sft":
            assistant_content = _read_text(args.assistant_file, "assistant file")
            if not assistant_content.strip():
                raise PromptBuildError("assistant file is empty")
            messages.append({"role": "assistant", "content": assistant_content})
        serialized = json.dumps({"messages": messages}, ensure_ascii=False, separators=(",", ":"))
        _write_stdout(serialized)
        return 0
    except PromptBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
