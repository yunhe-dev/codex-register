"""
Sub2API 自动维护调度配置 API。
"""

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ...config.settings import get_settings, update_settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _coalesce_legacy_history_points(points: list[dict]) -> list[dict]:
    """将旧口径的 scan/replenish 多事件合并为单个自动任务点。"""
    legacy_events = {"scan_completed", "replenish_round_completed", "replenish_completed"}
    if not points:
        return points

    merged: list[dict] = []
    index = 0
    while index < len(points):
        current = points[index]
        event_type = str(current.get("event_type") or "")
        if event_type not in legacy_events:
            merged.append(current)
            index += 1
            continue

        current_ts = current.get("timestamp")
        current_sid = current.get("service_id")
        try:
            anchor_dt = datetime.fromisoformat(current_ts) if isinstance(current_ts, str) else None
        except Exception:
            anchor_dt = None

        cluster = [current]
        j = index + 1
        while j < len(points):
            nxt = points[j]
            nxt_type = str(nxt.get("event_type") or "")
            if nxt_type not in legacy_events:
                break
            if nxt.get("service_id") != current_sid:
                break

            if anchor_dt is None:
                break
            try:
                nxt_dt = datetime.fromisoformat(nxt.get("timestamp")) if isinstance(nxt.get("timestamp"), str) else None
            except Exception:
                nxt_dt = None
            if nxt_dt is None:
                break
            if abs((nxt_dt - anchor_dt).total_seconds()) > 180:
                break
            cluster.append(nxt)
            j += 1

        merged_point = dict(cluster[0])
        merged_point["event_type"] = "auto_task_completed"
        for row in cluster[1:]:
            for key in (
                "accounts_healthy_after_scan",
                "replenish_success_count",
                "accounts_rate_limited_after_scan",
                "accounts_invalid_after_scan",
                "total_accounts_after_scan",
                "total_healthy_after_replenish",
            ):
                value = row.get(key)
                if value is not None:
                    merged_point[key] = value
        merged.append(merged_point)
        index = j

    return merged


class Sub2ApiSchedulerConfig(BaseModel):
    check_enabled: bool
    check_interval: int
    check_sleep: int
    delete_invalid_accounts: bool = False
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
        "delete_invalid_accounts": settings.sub2api_auto_delete_invalid_accounts,
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


@router.get("/history")
async def get_sub2api_scheduler_history(
    range: str = Query("24h"),
    service_id: int | None = Query(None),
    limit: int = Query(500),
):
    range_map = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    window = range_map.get((range or "").strip().lower())
    if window is None:
        return {"success": False, "message": "不支持的 range 参数，仅支持 24h/7d/30d", "points": []}

    safe_limit = max(1, min(int(limit or 500), 2000))
    since = datetime.utcnow() - window

    from ...database import crud
    from ...database.session import get_db

    with get_db() as db:
        points = crud.get_sub2api_scheduler_history_points(
            db,
            since=since,
            service_id=service_id,
            limit=safe_limit,
        )
    serialized_points = [point.to_dict() for point in points]
    serialized_points = _coalesce_legacy_history_points(serialized_points)

    return {
        "success": True,
        "range": (range or "24h").strip().lower(),
        "points": serialized_points,
    }


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
        sub2api_auto_delete_invalid_accounts=request.delete_invalid_accounts,
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
