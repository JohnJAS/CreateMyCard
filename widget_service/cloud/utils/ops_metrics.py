#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通过 GenUI Agent MQ 上报运维指标数据。
"""

import asyncio
import base64
import hashlib
import hmac
import platform
import threading
import time
import uuid
from collections.abc import Coroutine
from concurrent.futures import Future
from typing import Any

import httpx

from app.logger import logger, task_logger
from config.config import get_settings
from utils.base_utils import sts_config

_MODULE = "[Ops Metrics]"
OPS_METRICS_PATH = "/genui-agent/v1/mq/trigger"
REQUEST_TIMEOUT_SECONDS = 10.0
OSMS_SECRET_CONFIG_KEY = "hag.osms.sk"
HAG_SLB_DOMAIN = get_settings().hag_slb_url

_background_tasks: set[asyncio.Task[None]] = set()
_background_futures: set[Future[None]] = set()
_background_lock = threading.Lock()
_fallback_loop: asyncio.AbstractEventLoop | None = None


def _format_timestamp() -> str:
    """生成 Unix 毫秒时间戳。"""

    return str(time.time_ns() // 1_000_000)


def _build_auth_headers(access_key: str) -> dict[str, str]:
    """按照 HMAC-SHA256 规则构造请求头。"""

    if not access_key:
        raise ValueError("运维数据打点鉴权 access key 为空")

    secret_key = sts_config.get_sts_config(OSMS_SECRET_CONFIG_KEY)
    secret_bytes = secret_key.encode("utf-8") if isinstance(secret_key, str) else secret_key
    if not secret_bytes:
        raise ValueError("运维数据打点鉴权 secret key 为空")

    timestamp = _format_timestamp()
    digest = hmac.new(secret_bytes, timestamp.encode(), hashlib.sha256).digest()
    return {
        "Content-Type": "application/json",
        "x-access-key": access_key,
        "x-ts": timestamp,
        "x-sign": base64.b64encode(digest).decode("utf-8"),
    }


async def _report_ops_metrics_async(
    url: str,
    payload: dict[str, Any],
    session_id: str,
    host: str,
) -> None:
    """异步上报运维指标并记录结果。"""

    try:
        headers = _build_auth_headers(get_settings().hag_osms_ak)
        logger.info(f"{_MODULE} ops_metrics_report sessionId={session_id}")
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, trust_env=False) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        logger.info(f"{_MODULE} ops_metrics_report_success status={response.status_code}")
    except Exception as exc:
        logger.error(
            f"{_MODULE} ops_metrics_report_failed sessionId={session_id} host={host} error={exc}"
        )


def _run_fallback_loop(loop: asyncio.AbstractEventLoop) -> None:
    """在守护线程中运行供同步调用方使用的事件循环。"""

    asyncio.set_event_loop(loop)
    loop.run_forever()


def _get_fallback_loop() -> asyncio.AbstractEventLoop:
    """惰性创建同步调用方共享的后台事件循环。"""

    global _fallback_loop
    with _background_lock:
        if _fallback_loop is None:
            _fallback_loop = asyncio.new_event_loop()
            thread = threading.Thread(
                target=_run_fallback_loop,
                args=(_fallback_loop,),
                name="ops-metrics-loop",
                daemon=True,
            )
            thread.start()
        return _fallback_loop


def _remove_background_task(task: asyncio.Task[None]) -> None:
    with _background_lock:
        _background_tasks.discard(task)


def _remove_background_future(future: Future[None]) -> None:
    with _background_lock:
        _background_futures.discard(future)


def _schedule(coroutine: Coroutine[Any, Any, None]) -> None:
    """将协程投递到当前或后台事件循环，不等待网络请求完成。"""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        future = asyncio.run_coroutine_threadsafe(coroutine, _get_fallback_loop())
        with _background_lock:
            _background_futures.add(future)
        future.add_done_callback(_remove_background_future)
        return

    task = loop.create_task(coroutine, name="report-ops-metrics")
    with _background_lock:
        _background_tasks.add(task)
    task.add_done_callback(_remove_background_task)


def report_ops_metrics(
    body: dict[str, Any],
    host_port: str | None = None,
    session_id: str | None = None,
) -> None:
    """非阻塞上报运维指标，响应结果由后台任务记录。

    Args:
        body: 运维指标字段子集
        host_port: 服务地址，Windows 默认 127.0.0.1:8080，容器默认取 hag 域名
        session_id: 会话标识，作为DMQ消息key；为None时自动生成UUID
    """

    session_id = task_logger.get_session_id()
    if not get_settings().ai_widget_data_huashan_enable:
        logger.info(f"{_MODULE} ops_metrics_disabled ai_widget_data_huashan_enable=False")
        return

    if session_id is None:
        session_id = str(uuid.uuid4())

    if platform.system() == "Windows":
        host_port = "http://127.0.0.1:8080"

    if host_port is None:
        host_port = HAG_SLB_DOMAIN

    url = f"{host_port}{OPS_METRICS_PATH}"
    payload = {"sessionId": session_id, "body": body}
    _schedule(_report_ops_metrics_async(url, payload, session_id, host_port))
