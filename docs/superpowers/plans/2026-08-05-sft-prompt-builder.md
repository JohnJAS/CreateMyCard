# SFT Prompt Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 提供一个纯本地 CLI，接收外部 `TaskSpec`，复用现有 `PromptBuilder` 输出标准、Design 或 Terse
路线的 SFT messages。

**Architecture:** 新脚本只负责输入读取、Pydantic 校验、路由参数归一化和 JSON 输出；系统提示词、编辑
封装和 repair 封装全部委托现有 `PromptBuilder`。脚本不实例化模型客户端，也不执行能力裁决、DSL 转换或
artifact 保存。

**Tech Stack:** Python 3.12、Pydantic v2、现有 `PromptBuilder`、pytest、Ruff。

---

### Task 1: 建立标准创建路径的失败测试

**Files:**
- Create: `widget_service/tests/test_build_sft_prompt.py`
- Create: `widget_service/scripts/build_sft_prompt.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_messages_standard_create_injects_task_spec_and_keeps_raw_query():
    task_spec = {
        "userQuery": "生成一张天气卡片",
        "size": "2x2",
        "eventCandidates": [],
        "dataModelSchema": {"data": {}},
        "assetCandidates": [],
    }

    result = build_messages(task_spec, route="standard", mode="create")

    assert result[1] == {"role": "user", "content": "生成一张天气卡片"}
    assert '"userQuery":"生成一张天气卡片"' in result[0]["content"]
    assert result[0]["role"] == "system"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `py -3.12 -m pytest tests/test_build_sft_prompt.py::test_build_messages_standard_create_injects_task_spec_and_keeps_raw_query -q`

Expected: FAIL because `scripts.build_sft_prompt` and `build_messages` do not exist.

- [ ] **Step 3: Write minimal implementation**

Create `build_messages(task_spec_payload, route, mode, previous_content=None, degradation_context="", invalid_source_dsl=None, quality_errors=None)`.
Validate with `TaskSpec.model_validate`, call `PromptBuilder().build()` for standard create, and return the two
messages without changing their contents.

- [ ] **Step 4: Run it to verify it passes**

Run: `py -3.12 -m pytest tests/test_build_sft_prompt.py::test_build_messages_standard_create_injects_task_spec_and_keeps_raw_query -q`

Expected: PASS.

### Task 2: Add route and mode handling

**Files:**
- Modify: `widget_service/scripts/build_sft_prompt.py`
- Modify: `widget_service/tests/test_build_sft_prompt.py`

- [ ] **Step 1: Write failing tests for edit, repair, Design and Terse**

Tests must assert:

```python
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


def test_repair_appends_repair_prompt_and_preserves_quality_errors():
    messages = build_messages(
        _task_spec("天气卡片"),
        route="standard",
        mode="repair",
        invalid_source_dsl="invalid-dsl",
        quality_errors=[
            {"stage": "validation", "code": "E001", "message": "bad root"}
        ],
    )
    assert "不可信数据" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["invalidSourceDsl"] == "invalid-dsl"
    assert payload["qualityErrors"][0]["code"] == "E001"


def test_design_and_terse_create_use_task_spec_as_user_content():
    for route in ("design", "terse"):
        messages = build_messages(_task_spec("天气卡片"), route=route, mode="create")
        assert messages[1]["role"] == "user"
        assert json.loads(messages[1]["content"])["userQuery"] == "天气卡片"
```

- [ ] **Step 2: Run tests to verify the new cases fail**

Run: `py -3.12 -m pytest tests/test_build_sft_prompt.py -q`

Expected: the new edit/repair/design/terse assertions fail before route handling is implemented.

- [ ] **Step 3: Implement route and mode normalization**

Use `PromptBuilder.build_design_compact()` with `design-compact-dsl` and
`PromptBuilder.build_terse_dsl_nested2()` with `terse-dsl-nested-2`. For edit, require `previous_content`.
For repair, build the initial create/edit prompt first, require a non-empty source DSL and a list of objects with
`stage`, `code`, and `message`, then call `PromptBuilder.build_repair()` with the route source format.

- [ ] **Step 4: Run the focused tests**

Run: `py -3.12 -m pytest tests/test_build_sft_prompt.py -q`

Expected: PASS.

### Task 3: Add CLI input/output and validation tests

**Files:**
- Modify: `widget_service/scripts/build_sft_prompt.py`
- Modify: `widget_service/tests/test_build_sft_prompt.py`

- [ ] **Step 1: Write failing CLI tests**

Cover stdin input, `--input` file input, `--output-format sft` with an assistant file, missing edit source,
malformed JSON, and missing repair error data. Assert non-zero exit code and a useful stderr message for invalid
requests.

- [ ] **Step 2: Run the CLI tests to verify they fail**

Run: `py -3.12 -m pytest tests/test_build_sft_prompt.py -q`

Expected: CLI tests fail because `main()` and argument parsing are not implemented.

- [ ] **Step 3: Implement the CLI**

Support `--input`, `--route {standard,design,terse}`, `--mode {create,edit,repair}`, `--previous-file`,
`--degradation-context`, `--invalid-source-file`, `--quality-errors-file`, `--assistant-file`, and
`--output-format {messages,sft}`. Read all files as UTF-8, emit one JSON object to stdout with
`ensure_ascii=False`, and return exit code 2 for user input errors. Add a direct-execution path that inserts
`widget_service/cloud` into `sys.path` so the command works from the repository root.

- [ ] **Step 4: Run the CLI tests**

Run: `py -3.12 -m pytest tests/test_build_sft_prompt.py -q`

Expected: PASS.

### Task 4: Verify repository quality

**Files:**
- Verify: `widget_service/scripts/build_sft_prompt.py`
- Verify: `widget_service/tests/test_build_sft_prompt.py`

- [ ] **Step 1: Run Ruff**

Run: `py -3.12 -m ruff check cloud scripts tests/test_build_sft_prompt.py`

Expected: no diagnostics.

- [ ] **Step 2: Run the full service unit test file**

Run: `py -3.12 -m pytest tests/test_build_sft_prompt.py tests/test_service_units.py -q`

Expected: all tests pass.

- [ ] **Step 3: Run whitespace checks**

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 4: Inspect the generated CLI sample**

Run:

```powershell
@'{"userQuery":"天气卡片","size":"2x2","eventCandidates":[],"dataModelSchema":{"data":{}},"assetCandidates":[]}'@ |
  py -3.12 scripts\build_sft_prompt.py --route standard --mode create
```

Expected: stdout is a JSON object containing exactly two messages, with a system message and a user message whose
content is `天气卡片`.
