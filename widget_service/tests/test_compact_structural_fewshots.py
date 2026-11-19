"""DSL 加载同尺寸完整案例，总开关关闭时不追加案例。"""

import re

import pytest

from config.config import get_settings
from models.generation import TaskSpec
from services.prompt_builder import PromptBuilder
from services.protocol_registry import DESIGN_COMPACT_PROFILE_ID, A2UIProtocolRegistry


@pytest.mark.parametrize("size", ["2x2", "2x4"])
def test_dsl_uses_all_same_size_examples(monkeypatch, size):
    monkeypatch.setattr(get_settings(), "enable_design_compact_few_shots", True)
    task = TaskSpec(size=size, userQuery="显示天气", dataModelSchema={"data": {}})
    source = A2UIProtocolRegistry.read_design_few_shot(DESIGN_COMPACT_PROFILE_ID, size)
    context = PromptBuilder._compact_few_shot_context(task)
    identifiers = set(re.findall(r"\b2x[24]-V\d+\b", source))
    assert identifiers
    assert source in context
    assert set(re.findall(r"\b2x[24]-V\d+\b", context)) == identifiers
    other = "2x4" if size == "2x2" else "2x2"
    assert other + "-V" not in context


@pytest.mark.parametrize("size", ["2x2", "2x4"])
def test_examples_master_switch_still_disables_examples(monkeypatch, size):
    monkeypatch.setattr(get_settings(), "enable_design_compact_few_shots", False)
    task = TaskSpec(size=size, userQuery="显示天气", dataModelSchema={"data": {}})
    assert PromptBuilder._compact_few_shot_context(task) == ""
