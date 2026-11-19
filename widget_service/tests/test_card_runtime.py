"""验证项目配置选择和 GenUI 两种 STS 初始化路径。"""

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

import utils
from config import config


def load_runtime():
    spec = spec_from_file_location(
        "runtime_under_test", Path(utils.__file__).with_name("card_runtime.py")
    )
    assert spec is not None
    assert spec.loader is not None
    runtime = module_from_spec(spec)
    spec.loader.exec_module(runtime)
    return runtime


def test_external_configuration():
    from utils.mock import base_utils, ops_metrics, upload_file_obs

    runtime = load_runtime()
    assert runtime.sts_config is base_utils.sts_config
    assert runtime.report_ops_metrics is ops_metrics.report_ops_metrics
    assert runtime.UploadFileOSMS is upload_file_obs.UploadFileOSMS


@pytest.mark.parametrize("local", [True, False])
@pytest.mark.parametrize("explicit_switch", [True, False])
def test_genui_initializes_sts(monkeypatch, tmp_path, local, explicit_switch):
    settings_config = {"ENVIRONMENT": "test"}
    if explicit_switch:
        settings_config["use_mock_services"] = False
    settings = SimpleNamespace(
        CONFIG=settings_config,
        LOCAL_FLAG=local,
        PROJECT_ROOT=tmp_path,
        sts_server="test-sts",
        hag_slb_url="test-host",
        hag_osms_ak="test-ak",
        osms_prepare_url="/prepare",
        osms_complete_url="/complete",
        osms_query_url="/query",
        osms_delete_url="/delete",
        obs_preview_supported_file_format=[],
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    sdk = Mock()
    sdk.fetch_sensitive_configs.return_value = (
        {},
        ["MicroService/HAG/GenUIAgentService/hag.osms.sk/test"],
    )
    monkeypatch.setitem(sys.modules, "pystssdk", SimpleNamespace(sts_api=sdk))
    package = ModuleType("utils")
    package.__path__ = utils.__path__
    monkeypatch.setitem(sys.modules, "utils", package)
    names = ("utils.base_utils", "utils.ops_metrics", "utils.upload_file_obs")
    for name in names:
        monkeypatch.delitem(sys.modules, name, raising=False)
    try:
        runtime = load_runtime()
        sts = runtime.sts_config
        if local:
            sdk.init.assert_called_once_with(config_path=str(tmp_path / r"config\sts\STS_dev.ini"))
        else:
            sdk.init.assert_called_once_with(
                service="HAG", micro_service="GenUIAgentService", sts_server_domain="test-sts"
            )
        sdk.fetch_sensitive_configs.assert_called_once_with(sts.config_name_list)
        assert "utils.upload_file_obs" not in sys.modules
        assert runtime.report_ops_metrics.__module__ == "utils.ops_metrics"
        with monkeypatch.context() as missing_upload_config:
            missing_upload_config.delattr(settings, "hag_osms_ak")
            with pytest.raises(AttributeError, match="hag_osms_ak"):
                _ = runtime.UploadFileOSMS
            assert runtime.sts_config is sts
        assert runtime.UploadFileOSMS.__module__ == "utils.upload_file_obs"
    finally:
        for name in names:
            sys.modules.pop(name, None)


def test_missing_internal_dependency_propagates(monkeypatch):
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(CONFIG={}))
    monkeypatch.setitem(sys.modules, "pystssdk", None)
    runtime = load_runtime()
    with pytest.raises(ModuleNotFoundError, match="pystssdk"):
        _ = runtime.sts_config


def test_invalid_mock_switch(monkeypatch):
    settings = SimpleNamespace(CONFIG={"use_mock_services": "typo"})
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="use_mock_services"):
        load_runtime()


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "utils.mock"), ("true", "utils.mock"), (False, "utils"), ("false", "utils")],
)
def test_mock_switch_selection(monkeypatch, value, expected):
    settings = SimpleNamespace(CONFIG={"use_mock_services": value})
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    assert load_runtime()._PACKAGE == expected


def test_green_config_without_switch_uses_real_services(monkeypatch, tmp_path):
    from config.config_helper import ConfigHelper

    spec = tmp_path / "spec_records.yaml"
    spec.write_text("ENVIRONMENT: test", encoding="utf-8")
    monkeypatch.setattr(ConfigHelper, "_get_spec_config_file", lambda self: spec)
    settings = SimpleNamespace(CONFIG=ConfigHelper("local"))
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    assert load_runtime()._PACKAGE == "utils"
