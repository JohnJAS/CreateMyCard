"""选择部署实现并按业务调用方需要加载工具。"""

from importlib import import_module

from config.config import get_settings

_MODULES = {
    "UploadFileOSMS": "upload_file_obs",
    "report_ops_metrics": "ops_metrics",
    "sts_config": "base_utils",
}
__all__ = list(_MODULES)


def _implementation_package() -> str:
    # 绿区配置独立加载，不与默认 YAML 合并；缺少此项时使用真实服务。
    # ConfigHelper 会将 YAML 布尔值规范化为字符串，兼容直接传入的布尔值。
    use_mock = get_settings().CONFIG.get("use_mock_services", False)
    if use_mock is True or use_mock == "true":
        return "utils.mock"
    if use_mock is False or use_mock == "false":
        return "utils"
    raise ValueError(f"不支持的 use_mock_services: {use_mock!r}")


_PACKAGE = _implementation_package()


def __getattr__(name: str):
    module = _MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"{_PACKAGE}.{module}"), name)
