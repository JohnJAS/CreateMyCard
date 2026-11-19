# -*- coding: utf-8 -*-
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.


class STSConfig:
    """安全配置读取适配器。

    从内存配置读取数据，凭据读取接口沿用真实实现的参数名。
    """

    def __init__(self, mock_configs: dict[str, bytes] | None = None) -> None:
        """初始化安全配置读取适配器。

        入参：
        - mock_configs：可选 mock 配置，key 为配置项名称，value 为二进制配置值。
        出参：无。
        """
        self._mock_configs = mock_configs or {
            "ids.secret.key": b"22222",
        }

    def get_sts_config(self, config_name):
        """按配置项名称读取安全配置。

        入参：
        - config_name：安全配置项名称，例如 ids.secret.key。
        出参：配置项对应的二进制值，可直接用于 HMAC 等加密方法。
        异常：配置项不存在时抛出 KeyError，避免使用错误密钥继续请求。
        """
        if config_name not in self._mock_configs:
            raise KeyError(f"未找到 STS 配置: {config_name}")
        return self._mock_configs[config_name]


# IDSClient 当前按模块级单例调用，保留该入口以便未来无感替换真实实现。
sts_config = STSConfig()
