# SFT Prompt 构造脚本设计

## 目标

新增一个轻量 CLI，接收外部系统已经构造好的 `TaskSpec` JSON，复用微服务现有
`PromptBuilder` 生成与线上模型一致的消息，不调用模型、不查询能力、不上传 artifact。

默认服务标准 `generateWidgetCard` 的 create 路径，同时支持当前已有的 standard、design、terse
三种模型输入格式，以及 create、edit、repair 三种模式，便于构造不同来源的 SFT 样本。

## 输入

CLI 支持从 `--input` 文件读取 JSON，或在未指定文件时从 stdin 读取。

标准 TaskSpec 必须符合现有 `models.generation.TaskSpec`：

```json
{
  "userQuery": "生成一张天气卡片",
  "size": "2x2",
  "eventCandidates": [],
  "dataModelSchema": {"data": {}},
  "assetCandidates": []
}
```

创建模式只需要 TaskSpec。编辑模式额外接收上一轮标准 `genui` 或对应源格式 Design Token；repair
模式额外接收 `invalidSourceDsl` 和结构化 `qualityErrors`。

## 输出

默认输出完整的 OpenAI 风格 `messages` 数组：

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ]
}
```

可选 SFT 输出将 assistant 标签追加到同一个 `messages` 数组；assistant 内容由调用方通过文件或
标准输入传入，脚本不生成模型答案。输出使用 UTF-8、`ensure_ascii=false`，便于直接进入中文训练集。

## 路由和模式

- `--route standard` 调用 `PromptBuilder.build()`，默认值为 `standard`。
- `--route design` 调用 `build_design_compact()`。
- `--route terse` 调用 `build_terse_dsl_nested2()`。
- `--mode create` 构造首次生成消息。
- `--mode edit` 构造完整编辑消息，禁止把来源 URL放入模型输入。
- `--mode repair` 基于首次消息调用 `build_repair()`，输出完整修复请求。

standard create/edit 使用配置解析的 `docs/system_prompt.txt` 和 `docs/edit_system_prompt.txt`；
design/terse 使用协议 profile 目录中的 `PROMPT.md`。脚本不复制提示词正文。

## 校验和错误处理

脚本使用 Pydantic 的 `TaskSpec` 校验输入，拒绝未知顶层字段、非法尺寸和缺失必填字段。edit 模式
缺少来源内容、repair 模式缺少错误载荷时返回非零退出码，并把原因写到 stderr。文件读取、JSON
解析和输出错误均不吞掉异常。

## 文件边界

- 新增 `widget_service/scripts/build_sft_prompt.py`：CLI 和少量参数归一化逻辑。
- 新增 `widget_service/tests/test_build_sft_prompt.py`：覆盖 create、edit、repair、design/terse
  路由和非法输入。
- 不修改 `PromptBuilder`、系统提示词和模型调用代码。

## 非目标

- 不直接调用 MEP、DeepSeek、llmclient 或任何网络模型服务。
- 不重新执行能力裁决、TaskSpec 构造、CardSpec 构造、DSL 校验或 artifact 保存。
- 不从用户 query 自动推断或补齐 TaskSpec；TaskSpec 由外部系统负责。
