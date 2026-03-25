"""
Sub2API 自动维护调度配置 API。
"""

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from ...config.settings import get_settings, update_settings

router = APIRouter()
logger = logging.getLogger(__name__)


class Sub2ApiSchedulerConfig(BaseModel):
    check_enabled: bool
    check_interval: int
    check_sleep: int
    register_enabled: bool
    register_threshold: int
    register_batch_count: int
    register_max_attempts: int
    email_service: str
    upload_enabled: bool = True
    upload_service_ids: list[int] = []
    register_mode: str = "parallel"
    register_concurrency: int = 3
    register_interval_min: int = 5
    register_interval_max: int = 30


@router.get("/config")
async def get_sub2api_scheduler_config():
    settings = get_settings()
    return {
        "check_enabled": settings.sub2api_auto_check_enabled,
        "check_interval": settings.sub2api_auto_check_interval,
        "check_sleep": settings.sub2api_auto_check_sleep_seconds,
        "register_enabled": settings.sub2api_auto_register_enabled,
        "register_threshold": settings.sub2api_auto_register_threshold,
        "register_batch_count": settings.sub2api_auto_register_batch_count,
        "register_max_attempts": settings.sub2api_auto_register_max_attempts,
        "email_service": settings.sub2api_auto_register_email_service,
        "upload_enabled": settings.sub2api_auto_register_upload_enabled,
        "upload_service_ids": settings.sub2api_auto_register_upload_service_ids,
        "register_mode": settings.sub2api_auto_register_mode,
        "register_concurrency": settings.sub2api_auto_register_concurrency,
        "register_interval_min": settings.sub2api_auto_register_interval_min,
        "register_interval_max": settings.sub2api_auto_register_interval_max,
    }


@router.get("/logs")
async def get_sub2api_system_logs(since_id: int = 0):
    from ...core.sub2api_scheduler import global_log_counter, system_logs

    if since_id > global_log_counter:
        since_id = 0

    logs = [item for item in system_logs if item["id"] > since_id]
    last_id = logs[-1]["id"] if logs else since_id
    return {"success": True, "logs": logs, "last_id": last_id}


@router.get("/status")
async def get_sub2api_scheduler_status():
    from ...core.sub2api_scheduler import get_scheduler_status_snapshot

    settings = get_settings()
    status = get_scheduler_status_snapshot()
    status["check_enabled"] = settings.sub2api_auto_check_enabled
    return {"success": True, "status": status}


@router.post("/config")
async def update_sub2api_scheduler_config(request: Sub2ApiSchedulerConfig):
    settings = get_settings()
    was_check_enabled = bool(settings.sub2api_auto_check_enabled)
    register_mode = (request.register_mode or "parallel").strip().lower()
    if register_mode not in ("parallel", "pipeline"):
        logger.warning("非法自动补注册并发模式 %s，已回退为 parallel", request.register_mode)
        register_mode = "parallel"
    register_concurrency = max(1, min(50, int(request.register_concurrency or 3)))
    interval_min = max(0, int(request.register_interval_min or 5))
    interval_max = max(interval_min, int(request.register_interval_max or 30))

    update_settings(
        sub2api_auto_check_enabled=request.check_enabled,
        sub2api_auto_check_interval=request.check_interval,
        sub2api_auto_check_sleep_seconds=request.check_sleep,
        sub2api_auto_register_enabled=request.register_enabled,
        sub2api_auto_register_threshold=request.register_threshold,
        sub2api_auto_register_batch_count=request.register_batch_count,
        sub2api_auto_register_max_attempts=request.register_max_attempts,
        sub2api_auto_register_email_service=request.email_service,
        sub2api_auto_register_upload_enabled=request.upload_enabled,
        sub2api_auto_register_upload_service_ids=request.upload_service_ids,
        sub2api_auto_register_mode=register_mode,
        sub2api_auto_register_concurrency=register_concurrency,
        sub2api_auto_register_interval_min=interval_min,
        sub2api_auto_register_interval_max=interval_max,
    )

    from ...core.sub2api_scheduler import (
        check_sub2api_services_job,
        clear_stop_current_scan_request,
        notify_sub2api_scheduler_config_changed,
        request_stop_current_scan,
        start_sub2api_scheduler,
    )

    loop = asyncio.get_event_loop()
    if not request.check_enabled:
        request_stop_current_scan()
    else:
        clear_stop_current_scan_request()
        if not was_check_enabled:
            loop.run_in_executor(None, check_sub2api_services_job, loop, None)

    start_sub2api_scheduler()
    notify_sub2api_scheduler_config_changed()

    return {"success": True, "message": "Sub2API 自动维护配置已保存"}


@router.post("/trigger")
async def trigger_sub2api_scheduler_check():
    from ...core.sub2api_scheduler import (
        check_sub2api_services_job,
        get_scheduler_status_snapshot,
    )

    if get_scheduler_status_snapshot().get("is_running"):
        return {"success": False, "message": "当前已有扫描任务在运行"}

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, check_sub2api_services_job, loop, [])
    return {"success": True, "message": "已开始扫描"}


@router.post("/stop-scan")
async def stop_sub2api_scan():
    from ...core.sub2api_scheduler import (
        get_scheduler_status_snapshot,
        request_stop_current_scan,
    )

    if not get_scheduler_status_snapshot().get("is_running"):
        return {"success": False, "message": "当前没有进行中的扫描任务"}

    request_stop_current_scan()
    return {"success": True, "message": "已请求停止扫描"}
