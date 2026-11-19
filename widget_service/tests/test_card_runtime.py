"""验证同一业务入口在两种部署下的选择和失败行为。"""
import runpy
import sys
from pathlib import Path

import pytest

import utils
from utils.card_mock import base_utils, ops_metrics, upload_file_obs

RUNTIME = Path(utils.__file__).with_name("card_runtime.py")


def test_local_exports():
    exports = runpy.run_path(str(RUNTIME))
    assert exports.get("sts_config") is base_utils.sts_config
    assert exports.get("report_ops_metrics") is ops_metrics.report_ops_metrics
    assert exports.get("UploadFileOSMS") is upload_file_obs.UploadFileOSMS


@pytest.mark.parametrize("broken", [False, True])
def test_internal_adapter(tmp_path, monkeypatch, broken):
    adapter = tmp_path / "genui_runtime.py"
    source = "UploadFileOSMS = report_ops_metrics = sts_config = 'internal'"
    if broken:
        source = "import missing_genui_sdk_for_test"
    adapter.write_text(source, encoding="utf-8")
    monkeypatch.setattr(utils, "__path__", [str(tmp_path), *utils.__path__])
    monkeypatch.delitem(sys.modules, "utils.genui_runtime", raising=False)
    monkeypatch.delattr(utils, "genui_runtime", raising=False)
    try:
        if broken:
            with pytest.raises(ModuleNotFoundError, match="missing_genui_sdk_for_test"):
                runpy.run_path(str(RUNTIME))
        else:
            exports = runpy.run_path(str(RUNTIME))
            for name in ("UploadFileOSMS", "report_ops_metrics", "sts_config"):
                assert exports.get(name) == "internal"
    finally:
        sys.modules.pop("utils.genui_runtime", None)
        if hasattr(utils, "genui_runtime"):
            del utils.genui_runtime
