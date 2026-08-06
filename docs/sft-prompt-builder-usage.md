# SFT Prompt Builder 使用说明

`widget_service/scripts/build_sft_prompt.py` 用于把外部已经构造好的 `TaskSpec` 转成与线上一致的
模型 `messages`。它只负责组装 Prompt，不调用大模型、不重新执行能力裁决、不生成或上传 artifact。

## 1. 环境准备

在项目根目录执行：

```powershell
cd D:\workspace\CreateMyCard\widget_service
.\.venv\Scripts\python.exe -m scripts.build_sft_prompt --help
```

如果尚未创建虚拟环境：

```powershell
cd D:\workspace\CreateMyCard\widget_service
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. TaskSpec 输入

`--input` 文件必须是 UTF-8（建议无 BOM）JSON，并符合服务现有的 `TaskSpec` 模型。最小示例：

```json
{
  "userQuery": "生成一张天气卡片",
  "size": "2x2",
  "eventCandidates": [],
  "dataModelSchema": {
    "data": {}
  },
  "assetCandidates": []
}
```

其中：

- `userQuery`：本轮用户需求或编辑指令。
- `size`：目前只能是 `2x2` 或 `2x4`。
- `eventCandidates`：事件候选列表，没有候选时传空数组。
- `dataModelSchema`：已经由外部流程构造好的数据模型 Schema。
- `assetCandidates`：素材候选列表，没有候选时传空数组。

脚本会使用 Pydantic 校验输入，缺少必填字段、尺寸非法或包含未知顶层字段时返回错误。

## 3. 路由差异

通过 `--route` 选择模型 Prompt 路线，默认是 `standard`。

下表中的文件路径均相对 `widget_service` 目录。

| 路由 | system 消息来源 | user 消息内容 | assistant 目标格式 |
| --- | --- | --- | --- |
| `standard` | 默认 `docs/system_prompt.txt` | 原始 `userQuery` | 标准 A2UI 三行 JSONL |
| `design` | `cloud/data/protocol_profiles/design-compact-dsl/PROMPT.md` | TaskSpec JSON | Design Compact DSL |
| `terse` | `cloud/data/protocol_profiles/terse-dsl-nested-2/PROMPT.md` | TaskSpec JSON | TerseDSL-Nested-2 |

三条路线都会返回两条消息：一条 `system`，一条 `user`。脚本不会复制或改写 system prompt 正文，
而是从当前项目配置和协议 profile 读取。

`standard` 的 edit 模式还会使用默认的 `docs/edit_system_prompt.txt`，repair 模式会在初始 system 消息后追加
`docs/repair_system_prompt.txt`。实际文件位置也可以由服务配置覆盖。

## 4. CLI 参数与模式选择

如果只想构造首次生成的模型输入，最简单的命令就是：

```powershell
cd D:\workspace\CreateMyCard\widget_service
.\.venv\Scripts\python.exe -m scripts.build_sft_prompt --input .\task.json
```

这里的 `--route standard`、`--mode create` 和 `--output-format messages` 都是默认值，因此可以省略。
此命令只输出 `system` 和 `user` 两条消息，不需要上一轮内容，也不需要 assistant 答案。

`edit` 和 `repair` 不是首次生成的必选步骤，而是为了复用线上已有的多轮流程：

- `edit`：把上一轮完整源 DSL 和本轮编辑指令一起交给模型，构造多轮编辑训练样本。
- `repair`：把无效源 DSL 和校验错误一起交给模型，构造质量修复训练样本，复现线上定向修复流程。

如果你的数据只有外部传入的 TaskSpec，没有上一轮源 DSL 或校验错误，使用 `create` 即可。

### 参数说明

| 参数 | 默认值 | 作用和约束 |
| --- | --- | --- |
| `--input PATH` | 不指定 | 从 UTF-8（建议无 BOM）JSON 文件读取 TaskSpec；不指定时从 stdin 读取。 |
| `--route ROUTE` | `standard` | 选择 `standard`、`design` 或 `terse` Prompt 路线。 |
| `--mode MODE` | `create` | 选择 `create`、`edit` 或 `repair`。 |
| `--previous-file PATH` | 不指定 | 上一轮完整源 DSL；edit 必填，repair 可选，create 禁止。 |
| `--degradation-context TEXT` | 空字符串 | standard edit 的能力降级说明；create、design 和 terse 当前不使用。 |
| `--invalid-source-file PATH` | 不指定 | repair 必填，读取待修复的完整源 DSL。 |
| `--quality-errors-file PATH` | 不指定 | repair 必填，读取非空 JSON 错误数组；每项要有 `stage`、`code`、`message`。 |
| `--assistant-file PATH` | 不指定 | 仅用于 `--output-format sft`，读取调用方准备好的 assistant 目标文本。 |
| `--output-format FORMAT` | `messages` | `messages` 只输出 system/user；`sft` 追加 assistant，且必须同时传 `--assistant-file`。 |
| `--help` | 不适用 | 显示 argparse 参数帮助并退出。 |

`--assistant-file` 不会调用模型，也不会自动生成答案。它只是把外部准备好的目标输出追加为第三条
`assistant` 消息。类似地，脚本没有 `--system-prompt` 参数，因为 system prompt 按路由从项目配置和
协议 profile 读取，确保与线上 PromptBuilder 一致。

## 5. create：首次生成

create 模式只需要 TaskSpec。使用 `--input` 文件：

```powershell
cd D:\workspace\CreateMyCard\widget_service
.\.venv\Scripts\python.exe -m scripts.build_sft_prompt `
  --input .\task.json `
  --route standard `
  --mode create
```

输出是一个 JSON 对象：

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "生成一张天气卡片"}
  ]
}
```

`design` 和 `terse` 的命令只需替换路由：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_sft_prompt `
  --input .\task.json --route design --mode create

.\.venv\Scripts\python.exe -m scripts.build_sft_prompt `
  --input .\task.json --route terse --mode create
```

不指定 `--input` 时，脚本会从 stdin 读取 UTF-8 JSON。PowerShell 中可通过 `cmd.exe` 使用文件重定向：

```cmd
cmd /c ".\.venv\Scripts\python.exe -m scripts.build_sft_prompt --route standard --mode create < .\task.json"
```

## 6. edit：多轮编辑

edit 模式需要 `--previous-file`：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_sft_prompt `
  --input .\edit-task.json `
  --route standard `
  --mode edit `
  --previous-file .\previous.genui `
  --degradation-context "weather capability unavailable"
```

不同路由的上一轮内容如下：

- `standard`：上一轮完整标准 `genui`。
- `design`：上一轮完整 Design Compact DSL。
- `terse`：上一轮完整 TerseDSL-Nested-2 源 DSL。

create 模式禁止传 `--previous-file`，否则会返回错误。脚本只把上一轮源内容放入模型消息，不接受
artifact URL 作为模型输入。

## 7. repair：修复无效源 DSL

repair 模式需要两个文件：无效源 DSL，以及结构化质量错误数组。

`quality-errors.json` 示例：

```json
[
  {
    "stage": "validation",
    "code": "E001",
    "message": "root component is missing"
  }
]
```

调用示例：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_sft_prompt `
  --input .\task.json `
  --route standard `
  --mode repair `
  --invalid-source-file .\invalid.genui `
  --quality-errors-file .\quality-errors.json
```

`quality-errors.json` 必须是非空数组，每项都要有非空的 `stage`、`code`、`message`。repair 可以不传
`--previous-file`，这表示修复首次生成；如果传入，则必须是非空内容，表示修复编辑上下文。

repair 请求会在 system 消息中追加修复约束，并在 user JSON 中携带：

- `originalUserContent`
- `invalidSourceDsl`
- `qualityErrors`
- `dslFormat`

其中 `dslFormat` 会按路由自动设置为 `a2ui-form`、`design-compact-dsl` 或 `terse-dsl-nested-2`。

## 8. 生成完整 SFT 样本

脚本不生成 assistant 答案。调用方把目标答案写入文件后，使用 `--output-format sft` 追加到消息数组：

```powershell
.\.venv\Scripts\python.exe -m scripts.build_sft_prompt `
  --input .\task.json `
  --route standard `
  --mode create `
  --output-format sft `
  --assistant-file .\assistant.genui
```

输出结构为：

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

`assistant.genui` 应保存目标模型输出的完整文本：

- `standard`：标准 A2UI 三行 JSONL。
- `design`：完整 Design Compact DSL。
- `terse`：完整 TerseDSL-Nested-2 源 DSL。

脚本输出使用 UTF-8 且不转义中文，便于直接写入中文 SFT 数据集。

## 9. Python 调用方式

如果外部数据处理程序已经在 Python 中运行，也可以直接复用 `build_messages`：

```python
from scripts.build_sft_prompt import build_messages

messages = build_messages(
    task_spec_payload,
    route="standard",
    mode="create",
)
```

返回值是：

```python
[
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
]
```

## 10. 常见错误

| 场景 | 处理方式 |
| --- | --- |
| edit 未传 `--previous-file` | 返回非零退出码，并提示缺少 previous content |
| create 传入 `--previous-file` | 返回非零退出码，避免模式被静默改成 edit |
| repair 未传源 DSL | 返回非零退出码，并提示缺少 invalid source DSL |
| repair 未传质量错误或格式错误 | 返回非零退出码，并提示 quality errors |
| JSON 为空或格式错误 | 返回非零退出码，并提示 JSON 错误 |
| `--output-format messages` 同时传 `--assistant-file` | 返回非零退出码 |

用户输入错误的 CLI 退出码为 `2`，错误原因写入 stderr。

## 11. 相关实现

- CLI：[widget_service/scripts/build_sft_prompt.py](../widget_service/scripts/build_sft_prompt.py)
- 测试：[widget_service/tests/test_build_sft_prompt.py](../widget_service/tests/test_build_sft_prompt.py)
- Prompt 构造：[widget_service/cloud/services/prompt_builder.py](../widget_service/cloud/services/prompt_builder.py)
- 设计说明：
  [superpowers/specs/2026-08-05-sft-prompt-builder-design.md](superpowers/specs/2026-08-05-sft-prompt-builder-design.md)
