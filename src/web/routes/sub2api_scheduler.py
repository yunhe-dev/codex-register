"""
Sub2API 自动维护调度配置 API。
"""

import asyncio

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from ...config.settings import get_settings, update_settings

router = APIRouter()


class Sub2ApiSchedulerConfig(BaseModel):
    check_enabled: bool
    check_interval: int
    check_sleep: int
    register_enabled: bool
    register_threshold: int
    register_batch_count: int
    register_max_attempts: int
    email_service: str


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

    return {"success": True, "status": get_scheduler_status_snapshot()}


@router.post("/config")
async def update_sub2api_scheduler_config(request: Sub2ApiSchedulerConfig, background_tasks: BackgroundTasks):
    update_settings(
        sub2api_auto_check_enabled=request.check_enabled,
        sub2api_auto_check_interval=request.check_interval,
        sub2api_auto_check_sleep_seconds=request.check_sleep,
        sub2api_auto_register_enabled=request.register_enabled,
        sub2api_auto_register_threshold=request.register_threshold,
        sub2api_auto_register_batch_count=request.register_batch_count,
        sub2api_auto_register_max_attempts=request.register_max_attempts,
        sub2api_auto_register_email_service=request.email_service,
    )

    if request.check_enabled:
        from ...core.sub2api_scheduler import check_sub2api_services_job

        loop = asyncio.get_event_loop()
        background_tasks.add_task(loop.run_in_executor, None, check_sub2api_services_job, loop, None)

    return {"success": True, "message": "Sub2API 自动维护配置已保存"}


@router.post("/trigger")
async def trigger_sub2api_scheduler_check():
    from ...core.sub2api_scheduler import check_sub2api_services_job

    manual_logs = []
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, check_sub2api_services_job, loop, manual_logs)
        return {"success": True, "logs": manual_logs, "message": "Sub2API 巡检执行完毕"}
    except Exception as exc:
        return {"success": False, "logs": manual_logs, "message": str(exc)}
