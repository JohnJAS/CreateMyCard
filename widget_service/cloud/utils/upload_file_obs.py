# -*- coding: utf-8 -*-
# Copyright (c) Huawei Technologies Co., Ltd. 2026-2026. All rights reserved.
import base64
import hashlib
import hmac
import os
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
import requests
from tqdm import tqdm

from app.logger import logger
from config.config import get_settings
from utils.base_utils import sts_config
from utils.file import get_extension_split

# 项目配置参数
hag_osms_ak = get_settings().hag_osms_ak
hag_osms_sk = sts_config.get_sts_config("hag.osms.sk")
hag_slb_url = get_settings().hag_slb_url
osms_prepare_url = get_settings().osms_prepare_url
osms_complete_url = get_settings().osms_complete_url
osms_query_url = get_settings().osms_query_url
osms_delete_url = get_settings().osms_delete_url
supported_file_type = get_settings().obs_preview_supported_file_format

SUCCESS_STATUS_CODE = 200
MAX_TIMES = 3
# 超时时间：连接超时15秒，上传/读取超时300秒（5分钟）
connect_timeout = 15
read_timeout = 300

AI_TAIL_MD = "内容由AI生成"

EMPTY_CDN_URL = "The hag osms query interface cdn url for fileDetailInfos returns is empty!"

DEFAULT_AIGC = Path(__file__).with_name("default_aigc.txt").read_text(encoding="utf-8")

AIGC_KEY_ORDER = (
    "Label",
    "ContentProducer",
    "ProduceID",
    "ReservedCode1",
    "ContentPropagator",
    "PropagateID",
)


def build_aigc_watermark_text(aigc: Mapping[str, Any]) -> str:
    lines = ["AIGC:"]
    seen = set()

    for k in AIGC_KEY_ORDER:
        if k in aigc and aigc[k] is not None:
            lines.append(f"  {k}: {aigc[k]}")
            seen.add(k)

    for k, v in aigc.items():
        if k not in seen and v is not None:
            lines.append(f"  {k}: {v}")

    return "\n".join(lines)


def format_md_hidden_watermark(wm: str) -> str:
    """
    Convert watermark text into hidden comment format for md.
    """
    text = wm or ""
    if not text:
        return ""
    return f"---\n{text}\n---"


class UploadFileOSMS:
    def __init__(self):
        self.trace_id = str(uuid.uuid4())[:16]
        self.isPermanentStorage = False

    async def upload_file(
        self,
        file_path: str,
        record_file_path=r"obs_files_to_be_deleted.json",
        isPermanentStorage=False,
    ):
        try:
            self.isPermanentStorage = isPermanentStorage
            updload_file_info = await self.upload_file_and_get_info(file_path)
            if isinstance(updload_file_info, str):
                return None
            return updload_file_info["url"]
        except Exception:
            logger.error("上传文件到osms失败")

    async def upload_file_and_get_info(
        self, file_path: str, record_file_path=r"obs_files_to_be_deleted.json"
    ):
        if not file_path:
            logger.error("文件路径为空")
            return ""

        # 验证文件存在性
        if not os.path.exists(file_path):
            logger.error(f"文件{file_path}不存在")
            return "文件不存在"

        # 验证是否为文件
        if not os.path.isfile(file_path):
            logger.error(f"{file_path}不是文件")
            return "路径不是文件"

        # 调取osms的prepare接口获取文件信息
        file_info = await self.invoking_osms_prepare(file_path)
        logger.debug(f"待上传file_path: {file_path}")
        if not file_info:
            logger.error(f"{file_path}上传OSMS失败")
            return f"{os.path.basename(file_path)}:文件上传失败OSMS"

        # 基于osms微服务完成文件上传到obs桶
        result = await self.read_file_as_bytes(file_path)
        if not result["success"]:
            return "{}:{}".format(result["file_name"], result["error"])

        updload_file_info = await self.upload_file_to_obs(
            file_info["uploadInfos"][0], result["bytes"]
        )
        if not updload_file_info:
            logger.error(f"{file_path}上传OBS失败")
            return f"{os.path.basename(file_path)}:上传文件到 obs 报错"

        # 更新osms微服务中文件上传的信息
        await self.invoking_osms_complete(file_info)

        # 调取osms的query接口获取文件cdn下载链接
        fileDetailInfos = await self.invoking_osms_query(file_info)
        if not fileDetailInfos:
            logger.error(f"{file_path}获取osms的cdn链接失败")

        return fileDetailInfos

    async def format_date(self):
        time_stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        time_stamp = time_stamp[: len(time_stamp) - 3]
        return time_stamp

    async def generate_cipher_text(self, time_stamp):
        message = (time_stamp + hag_osms_ak).encode("utf-8")
        secret = hag_osms_sk.encode("utf-8")
        signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
        return base64.b64encode(bytes.fromhex(signature)).decode("utf-8")

    async def read_file_as_bytes(self, file_path):
        # 读取任意文件的原始二进制内容
        result = {
            "success": False,
            "file_name": os.path.basename(file_path),
            "bytes": None,
            "error": None,
        }

        try:
            with open(file_path, "rb") as f:
                byte_content = f.read()
                result.update({"success": True, "bytes": byte_content})

        except PermissionError:
            result["error"] = "没有读取权限"
        except Exception as e:
            result["error"] = f"读取失败: {str(e)}"

        return result

    async def upload_file_to_obs(self, file_info, file_bytes):
        retry_delay = 1  # 初始重试延迟(秒)
        retry_time = 1  # 当前块重试次数
        while True:
            try:
                response = requests.put(
                    file_info["url"],
                    data=file_bytes,
                    headers=file_info["headers"],
                    timeout=(connect_timeout, read_timeout),
                )
                response.raise_for_status()
                return True
            except Exception as e:
                retry_time += 1
                time.sleep(retry_delay * (2**retry_time))
                if retry_time > MAX_TIMES:
                    logger.error(
                        f"上传文件到 OBS 失败 trace_id={self.trace_id} "
                        f"error_type={type(e).__name__}"
                    )
                    return False

    async def calculate_file_sha256(self, file_path):
        sha256 = hashlib.sha256()
        file_size = os.path.getsize(file_path)

        with (
            open(file_path, "rb") as f,
            tqdm(total=file_size, unit="B", unit_scale=True, desc="Calculating SHA256") as pbar,
        ):
            while chunk := f.read(4096):  # 分块4kb
                sha256.update(chunk)
                pbar.update(len(chunk))

        return sha256.hexdigest()

    async def build_osms_headers(self) -> tuple[str, dict]:
        time_stamp = await self.format_date()
        headers = {
            "Content-Type": "application/json",
            "x-access-key": hag_osms_ak,
            "x-sign": await self.generate_cipher_text(time_stamp),
            "x-ts": time_stamp,
            "x-hag-trace-id": self.trace_id,
        }
        return time_stamp, headers

    async def invoking_osms_prepare(self, file_path):
        """上传 osms prepare"""
        logger.info(f"Invoke the osms prepare interface, trace_id: {self.trace_id}")
        for times in range(0, MAX_TIMES):
            time_stamp, headers = await self.build_osms_headers()
            body = {
                "useEdge": get_settings().obs_use_edge,
                "objectType": "MIGRATE_PRIVATE_RISKCTRTEMP_CN",
                "fileName": os.path.basename(file_path),
                "fileSha256": await self.calculate_file_sha256(file_path),
                "fileSize": os.path.getsize(file_path),
                "fileOwnerInfo": {"uid": "superAgent", "teamId": "superAgent"},
            }
            if self.isPermanentStorage:
                body["isPermanentStorage"] = "COMMON_PRIVATE"

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url=osms_prepare_url, headers=headers, json=body, ssl=True
                    ) as response:
                        if response.status != SUCCESS_STATUS_CODE:
                            continue
                        resp = await response.json()
                        if (
                            "objectId" not in resp.keys()
                            or "draftId" not in resp.keys()
                            or "uploadInfos" not in resp.keys()
                        ):
                            error = "The hag osms prepare interface returns an exception"
                            raise error
                        if not resp["uploadInfos"]:
                            error = "The hag osms prepare interface uploadInfos returns is empty"
                            raise error
                        if (
                            "url" not in resp["uploadInfos"][0].keys()
                            or "headers" not in resp["uploadInfos"][0].keys()
                        ):
                            error = (
                                "The hag osms prepare interface url and headers for uploadInfos "
                                "map returns is empty"
                            )
                            raise error

                        return resp
            except Exception as e:
                logger.error(
                    f"{times + 1}st invoking Hag_OSMS_Prepare interface "
                    f"throws the exception: {str(e)}."
                )
                if times == MAX_TIMES - 1:
                    raise e
        return {}

    async def invoking_osms_complete(self, file_info):
        for times in range(0, MAX_TIMES):
            time_stamp = await self.format_date()
            cipher_text = await self.generate_cipher_text(time_stamp)
            headers = {
                "Content-Type": "application/json",
                "x-access-key": hag_osms_ak,
                "x-sign": cipher_text,
                "x-ts": time_stamp,
            }

            body = {
                "objectId": file_info["objectId"],
                "draftId": file_info["draftId"],
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url=osms_complete_url, headers=headers, json=body, ssl=True
                    ) as response:
                        if response.status != SUCCESS_STATUS_CODE:
                            continue
                        return True
            except Exception as e:
                logger.error(
                    f"{times + 1}st invoking Hag_OSMS_Prepare interface "
                    f"throws the exception: {str(e)}."
                )
                if times == MAX_TIMES - 1:
                    raise e
        return False

    async def invoking_osms_query(self, file_info):
        result = ""
        for times in range(0, MAX_TIMES):
            time_stamp, headers = await self.build_osms_headers()
            body = {
                "detectUrl4Station": False,
                "useEdge": get_settings().obs_use_edge,
                "objectInfos": [
                    {
                        "objectId": file_info["objectId"],
                        "expireTime": get_settings().obs_expire_time,  # 设置有效期
                    }
                ],
                "permissionMode": "ALL",
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url=osms_query_url, headers=headers, json=body, ssl=True
                    ) as response:
                        if response.status != SUCCESS_STATUS_CODE:
                            continue
                        resp = await response.json()
                        if "fileDetailInfos" not in resp.keys():
                            error = "The hag osms query interface fileDetailInfos returns is empty"
                            raise error

                        if "url" not in resp["fileDetailInfos"][0].keys():
                            error = EMPTY_CDN_URL
                            raise error

                        return resp["fileDetailInfos"][0]
            except Exception as e:
                logger.error(
                    f"Invoking the hag osms query interface throws the exception: {times}."
                )
                if times == MAX_TIMES - 1:
                    logger.info("三次重试过后仍旧失败！！！")
                    raise e
        return result

    def validate_osms_query_resp(self, resp: dict) -> None:
        if "fileDetailInfos" not in resp.keys():
            error = "The hag osms query interface fileDetailInfos returns is empty"
            raise Exception(error)

        if resp["fileDetailInfos"] is None or len(resp["fileDetailInfos"]) == 0:
            error = "The hag osms query interface fileDetailInfos returns is empty"
            raise Exception(error)

        if "url" not in resp["fileDetailInfos"][0].keys():
            error = EMPTY_CDN_URL
            raise Exception(error)

    async def invoking_osms_query_by_url(self, file_url, file_path=None):
        """新的url替换旧的url，且判断是否增加可预览字段"""
        result = ""
        for times in range(0, MAX_TIMES):
            time_stamp = await self.format_date()
            headers = {
                "Content-Type": "application/json",
                "x-access-key": hag_osms_ak,
                "x-sign": await self.generate_cipher_text(time_stamp),
                "x-ts": time_stamp,
                "x-hag-trace-id": "rytest002",
            }

            body = {
                "detectUrl4Station": False,
                "useEdge": get_settings().obs_use_edge,
                "objectInfos": [
                    {
                        "url": file_url,
                        "expireTime": get_settings().obs_expire_time,  # 设置有效期
                    }
                ],
                "permissionMode": "ALL",
            }

            if file_path:
                file_extension = get_extension_split(str(file_path))
                need_preview = (
                    get_settings().obs_need_preview and file_extension in supported_file_type
                )
                body["objectInfos"][0]["needPreview"] = need_preview  # 是否开启可预览字段

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url=osms_query_url, headers=headers, json=body, ssl=True
                    ) as response:
                        if response.status != SUCCESS_STATUS_CODE:
                            continue
                        resp = await response.json()
                        self.validate_osms_query_resp(resp)

                        result = (
                            resp["fileDetailInfos"][0]["url"]
                            if file_path
                            else resp["fileDetailInfos"][0]
                        )
                        if not result:
                            logger.error(EMPTY_CDN_URL)
                            error = EMPTY_CDN_URL
                            raise error

                        return result
            except Exception as e:
                logger.error(
                    f"Invoking the hag osms query interface throws the exception: {times}."
                )
                if times == MAX_TIMES - 1:
                    logger.info("三次重试过后仍旧失败！！！")
                    raise e
        return result

    async def invoking_osms_delete(self, file_url):
        try:
            time_stamp = await self.format_date()
            headers = {
                "x-access-key": hag_osms_ak,
                "x-sign": await self.generate_cipher_text(time_stamp),
                "x-ts": time_stamp,
            }

            body = {
                "url": file_url,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url=osms_delete_url, headers=headers, json=body, ssl=True
                ) as response:
                    if response.status != 200:  # 假设 200 是成功的状态码
                        response.raise_for_status()
                    return True
        except Exception as e:
            logger.error(
                f"Failed to invoke the hag osms delete interface throws the exception: {str(e)}."
            )
            return False
