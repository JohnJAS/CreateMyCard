"""编辑输出包装恢复保持正文、歧义拒绝和日志脱敏。"""

import json

import pytest

from custom.a2ui_model_client import A2UIModelClient
from services import widget_edit_output
from services.widget_edit_output import normalize_edit_output


@pytest.mark.parametrize("prefix,suffix", [
    ("```json\n", ""),
    ("```\n", "\n```"),
    ("说明\n```genui\n", "\n```\n完成说明"),
    ("", "\n```"),
    ("\ufeff", ""),
    ("说明 `parentId`\n```json\n", "\n```\n保留 `content`。"),
    ("说明 ``parentId``\n```json\n", ""),
])
def test_wrapper_preserves_body_and_logs_only_metadata(monkeypatch, prefix, suffix):
    records = []
    monkeypatch.setattr(widget_edit_output.logger, "info", records.append)
    body = json.dumps({"text": "敏感正文 ```json {示例}", "value": 12}, ensure_ascii=False)
    assert normalize_edit_output(prefix + body + suffix, "edit_execute") == body
    assert len(records) == 1
    assert "敏感正文" not in records[0]
    assert "edit_execute" in records[0]


@pytest.mark.parametrize("raw", [
    '```json\n{"text":"未完成',
    '```json\n{"value":1,"value":2}\n```',
    '```json\n{}\n{}\n```',
    '```json\n{}\n```\n```json\n{}\n```',
    '{}\n说明\n```json\n{}\n```',
    '说明\n```json\n{}\n```\n[]',
    '```python\n{}\n```',
    '```json\n[]\n```',
    '说明\n```json\n{}\n未闭合围栏后的说明',
    '说明 {}',
    '```json\n{"value":1,}\n```',
    '说明 `parentId`\n```json\n{"value":1,"value":2}\n```',
    '说明 `parentId`\n```json\n{"value":1',
    '说明 `parentId`\n```json\n{}\n```\n```json\n{}\n```',
    '说明 `{"value":1}`\n```json\n{}\n```',
    '说明 ``[]``\n```json\n{}\n```',
])
def test_ambiguous_or_invalid_response_is_not_rewritten(raw):
    assert normalize_edit_output(raw, "edit_intent") == raw


def test_plain_json_string_with_fence_is_not_interpreted():
    raw = json.dumps({"text": "说明\n```json\n{}\n```", "values": [1, 2]})
    assert normalize_edit_output(raw, "edit_execute") == raw


def test_reorder_intent_with_inline_code_explanation():
    """复现真实日志：修正父节点后，说明中的行内代码不得阻断完整意图。"""
    prefix = (
        "根据错误提示，“root_1”节点在 original card 中不存在，真正的父容器是 "
        "`__genui_render_component__root_1`。已修正 `childrenOrders` 中的父节点 ID，"
        "并同步更新了 targets 以反映实际发生位置变化的两个区域。\n\n"
    )
    body = json.dumps({
        "explanation": "将步数区域移到右侧。",
        "targetSize": "2x4", "mode": "reorder", "dimensions": ["layout"],
        "targets": ["root_1_0", "root_1_1"],
        "childrenOrders": [{"parentId": "__genui_render_component__root_1",
                            "children": ["root_1_1", "root_1_0"]}],
        "allowPartial": True,
    }, ensure_ascii=False, indent=2)
    raw = prefix + "```json\n" + body + "\n```"
    assert normalize_edit_output(raw, "edit_intent") == body


def test_model_adapter_keeps_incomplete_genui_for_edit_validation():
    raw = '```genui\n{"value":1,"value":2}'
    client = A2UIModelClient()
    profile = {"id": "semantic-widget-edit", "format": "raw-json"}
    assert client._process_model_output(raw, profile) == raw
    assert normalize_edit_output(raw, "edit_execute") == raw
