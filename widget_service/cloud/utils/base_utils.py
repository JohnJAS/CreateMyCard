# -*- coding: utf-8 -*-
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
import os

from pystssdk import sts_api

from app.logger import logger
from config.config import get_settings
from errors.codes import StatusCode
from errors.errors import raise_error

PROJECT_ROOT = get_settings().PROJECT_ROOT
ENV = get_settings().CONFIG["ENVIRONMENT"]
LOCAL_FLAG = get_settings().LOCAL_FLAG


class StsConfig:
    def __init__(self, config_path, config_name_list):
        if not config_path:
            raise_error(
                StatusCode.TOOL_VALIDATE_FILEPATH_INVALID, error_msg="config_path must be set"
            )
        if not config_name_list:
            raise_error(
                StatusCode.TOOL_VALIDATE_DATA_INVALID, error_msg="config_name_list must be set"
            )
        self.config_path = config_path
        self.config_name_list = config_name_list
        if LOCAL_FLAG:
            sts_api.init(config_path=self.config_path)
        else:
            sts_api.init(
                service="HAG",
                micro_service="GenUIAgentService",
                sts_server_domain=get_settings().sts_server,
            )
        self.encrypted_configs, self.missing_configs = sts_api.fetch_sensitive_configs(
            self.config_name_list
        )

    def get_sts_config(self, config_name):
        """
        config_name:敏感项ID
        """
        if "/" not in config_name:
            config_name = "MicroService/HAG/GenUIAgentService/" + config_name + f"/{ENV}"

        if config_name in self.missing_configs:
            logger.warning(f"{config_name} is missing in STS,return Non-str")
            return ""

        if config_name not in self.config_name_list:
            logger.warning(f"{config_name} not in config_name_list,return Non-str")
            return ""

        decrypt_value = sts_api.decrypt_sensitive_config(self.encrypted_configs[config_name])
        return decrypt_value


# 新增配置项时，都需要在此处刷新。
env_config_list = [
    f"MicroService/HAG/GenUIAgentService/hag.osms.sk/{ENV}",
    f"MicroService/HAG/GenUIAgentService/hag.work.key.sts/{ENV}",
    f"MicroService/HAG/GenUIAgentService/genui.model.secret.key/{ENV}",
    f"MicroService/HAG/GenUIAgentService/deepseek.huawei.sk/{ENV}",
    f"MicroService/HAG/GenUIAgentService/ids.secret.key/{ENV}",
]

if LOCAL_FLAG:
    env_config_path = os.path.join(PROJECT_ROOT, r"config\sts\STS_dev.ini")
else:
    env_config_path = os.path.join(PROJECT_ROOT, "config/sts/STS_dev_remote.ini")

sts_config = StsConfig(env_config_path, env_config_list)
