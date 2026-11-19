# -*- coding: utf-8 -*-
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
import asyncio
import shutil
from pathlib import Path
from urllib.parse import quote

from config.config import get_settings


class UploadFileOSMS:
    """OBS 文件上传适配器。

    当前上传使用本地 mock，并返回与真实 OBS 一致形式的访问地址。
    """

    def __init__(self):
        self.base_url = get_settings().artifact_base_url.rstrip("/")

    @property
    def mock_storage_dir(self) -> Path:
        """跟随当前服务配置选择本地落盘目录。"""
        return get_settings().WORKSPACE_ROOT / "mock_obs"

    async def upload_file(
        self,
        file_path: str,
        record_file_path=r"obs_files_to_be_deleted.json",
        isPermanentStorage=False,
    ):
        """保存本地副本并返回 mock 地址。

        record_file_path 和 isPermanentStorage 与真实上传的调用参数一致。
        本地副本不写远端清理记录，也没有远端存储期限。
        """
        source_path = Path(file_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"待上传文件不存在: {source_path}")

        self.mock_storage_dir.mkdir(parents=True, exist_ok=True)
        target_path = self.mock_storage_dir / source_path.name
        await asyncio.to_thread(shutil.copy2, source_path, target_path)
        return f"{self.base_url}/{quote(source_path.name)}"
