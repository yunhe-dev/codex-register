"""
Sub2API 自动维护与补注册调度器。
"""

import asyncio
import logging
import threading
import uuid
from collections import deque
from typing import Optional, Tuple

from ..config.settings import get_settings
from ..database import crud
from ..database.session import get_db
from ..web.routes.registration import run_batch_registration
from .upload.sub2api_upload import (
    delete_sub2api_account,
    list_sub2api_openai_accounts,
    test_sub2api_account,
)

logger = logging.getLogger(__name__)

global_log_counter = 0
system_logs = deque(maxlen=500)

_is_checking = False
_scheduler_task: Optional[asyncio.Task] = None
_auto_registering_services = set()
_auto_registering_lock = threading.Lock()
AUTO_REGISTER_MAX_ROUNDS = 5


def append_system_log(level: str, msg: str):
    global global_log_counter
    global_log_counter += 1
    system_logs.append({
        "id": global_log_counter,
        "level": level,
        "msg": f"[Sub2API 自动任务] {msg}",
    })


def _log(level: str, msg: str, manual_logs: Optional[list] = None):
    getattr(logger, level, logger.info)(msg)
    append_system_log(level, msg)
    if manual_logs is not None:
        manual_logs.append(f"[{level.upper()}] {msg}")


def _resolve_auto_register_email_service() -> Tuple[str, Optional[int]]:
    settings = get_settings()
    saved = (settings.sub2api_auto_register_email_service or "").strip()
    if saved:
        service_type, _, raw_service_id = saved.partition(":")
        service_type = service_type or "tempmail"
        service_id: Optional[int] = None
        if raw_service_id and raw_service_id != "default":
            try:
                service_id = int(raw_service_id)
            except ValueError:
                service_id = None
        return service_type, service_id

    with get_db() as db:
        enabled_services = crud.get_email_services(db, enabled=True)
        if enabled_services:
            best_service = enabled_services[0]
            return best_service.service_type, best_service.id

    return "tempmail", None


async def trigger_auto_registration(count: int, sub2api_service_id: int):
    logger.info("触发 Sub2API 自动补注册: count=%s service_id=%s", count, sub2api_service_id)
    if count <= 0:
        return

    with _auto_registering_lock:
        if sub2api_service_id in _auto_registering_services:
            append_system_log("warning", f"服务 {sub2api_service_id} 已有自动补注册任务在运行，跳过重复触发")
            return
        _auto_registering_services.add(sub2api_service_id)

    try:
        settings = get_settings()
        email_service_type, email_service_id = _resolve_auto_register_email_service()
        target_success_count = count
        remaining_to_create = count
        total_success_count = 0
        round_index = 0

        append_system_log(
            "info",
            f"开始为服务 {sub2api_service_id} 自动补注册，目标成功补充 {target_success_count} 个账号",
        )

        while remaining_to_create > 0 and round_index < AUTO_REGISTER_MAX_ROUNDS:
            round_index += 1
            task_uuids = [str(uuid.uuid4()) for _ in range(remaining_to_create)]
            batch_id = str(uuid.uuid4())

            with get_db() as db:
                for task_uuid in task_uuids:
                    crud.create_registration_task(
                        db,
                        task_uuid=task_uuid,
                        email_service_id=email_service_id,
                        proxy=None,
                    )

            append_system_log(
                "info",
                f"自动补注册第 {round_index} 轮开始，本轮提交 {remaining_to_create} 个任务",
            )

            await run_batch_registration(
                batch_id=batch_id,
                task_uuids=task_uuids,
                email_service_type=email_service_type,
                proxy=None,
                email_service_config=None,
                email_service_id=email_service_id,
                interval_min=settings.registration_sleep_min,
                interval_max=settings.registration_sleep_max,
                concurrency=2,
                mode="pipeline",
                auto_upload_sub2api=True,
                sub2api_service_ids=[sub2api_service_id],
            )

            round_success_count = 0
            with get_db() as db:
                for task_uuid in task_uuids:
                    task = crud.get_registration_task_by_uuid(db, task_uuid)
                    if not task or task.status != "completed":
                        continue
                    task_result = task.result or {}
                    upload_success = task_result.get("sub2api_upload_success")
                    if upload_success is False:
                        continue
                    round_success_count += 1

            total_success_count += round_success_count
            remaining_to_create = max(0, target_success_count - total_success_count)

            append_system_log(
                "info",
                f"自动补注册第 {round_index} 轮完成，成功补充 {round_success_count} 个，累计成功 {total_success_count}/{target_success_count}",
            )

            if round_success_count == 0 and remaining_to_create > 0:
                append_system_log(
                    "warning",
                    f"自动补注册第 {round_index} 轮没有新增成功账号，停止继续重试，剩余缺口 {remaining_to_create}",
                )
                break

        if remaining_to_create == 0:
            append_system_log(
                "info",
                f"服务 {sub2api_service_id} 自动补注册完成，已按成功数补齐 {target_success_count} 个账号",
            )
        else:
            append_system_log(
                "warning",
                f"服务 {sub2api_service_id} 自动补注册结束，目标 {target_success_count}，实际成功 {total_success_count}，剩余缺口 {remaining_to_create}",
            )
    finally:
        with _auto_registering_lock:
            _auto_registering_services.discard(sub2api_service_id)


def check_sub2api_services_job(main_loop, manual_logs: list = None):
    """检查所有启用的 Sub2API 服务，并在需要时自动补注册。"""
    global _is_checking
    settings = get_settings()

    if not settings.sub2api_auto_check_enabled and manual_logs is None:
        return

    if _is_checking:
        _log("warning", "当前已有一个 Sub2API 巡检任务在运行，本次请求已跳过。", manual_logs)
        return

    _is_checking = True
    _log("info", "开始检查 Sub2API 服务...", manual_logs)

    try:
        with get_db() as db:
            services = crud.get_sub2api_services(db, enabled=True)

        if not services:
            _log("warning", "当前没有任何启用的 Sub2API 服务。", manual_logs)
            return

        for svc in services:
            valid_count = 0
            try:
                _log("info", f"检查 Sub2API 服务: {svc.name}", manual_logs)
                accounts = list_sub2api_openai_accounts(svc.api_url, svc.api_key)
                _log("info", f"服务 {svc.name} 获取到 {len(accounts)} 个 openai 账号", manual_logs)

                for index, account in enumerate(accounts, start=1):
                    if manual_logs is None and not get_settings().sub2api_auto_check_enabled:
                        _log("warning", "检测到自动维护已关闭，当前巡检提前结束。", manual_logs)
                        return

                    account_id = account.get("id")
                    account_name = account.get("name") or account.get("email") or f"#{account_id}"
                    if not account_id:
                        _log("warning", f"跳过缺少 id 的远端账号: {account_name}", manual_logs)
                        continue

                    result, message = test_sub2api_account(svc.api_url, svc.api_key, int(account_id))
                    if result is True:
                        valid_count += 1
                        _log("info", f"测活进度 [{index}/{len(accounts)}] {account_name} 正常", manual_logs)
                    elif result is False:
                        _log("warning", f"测活进度 [{index}/{len(accounts)}] {account_name} 失效: {message}", manual_logs)
                        deleted, delete_message = delete_sub2api_account(svc.api_url, svc.api_key, int(account_id))
                        if deleted:
                            _log("warning", f"已删除失效账号 {account_name}: {delete_message}", manual_logs)
                        else:
                            _log("error", f"删除失效账号 {account_name} 失败: {delete_message}", manual_logs)
                    else:
                        valid_count += 1
                        _log("warning", f"账号 {account_name} 无法判定健康状态，已跳过删除: {message}", manual_logs)

                    sleep_seconds = max(0, int(get_settings().sub2api_auto_check_sleep_seconds or 0))
                    if sleep_seconds > 0 and index < len(accounts):
                        import time
                        time.sleep(sleep_seconds)

                _log("info", f"服务 {svc.name} 检查完成，有效账号数: {valid_count}", manual_logs)
            except Exception as exc:
                valid_count = 0
                _log("error", f"检查服务 {svc.name} 时异常: {exc}", manual_logs)
                _log("warning", f"为保证供应，暂按服务 {svc.name} 有效账号数为 0 处理", manual_logs)

            if settings.sub2api_auto_register_enabled and valid_count < settings.sub2api_auto_register_threshold:
                threshold = int(settings.sub2api_auto_register_threshold or 0)
                to_register = max(0, int(settings.sub2api_auto_register_batch_count or 0))
                _log(
                    "warning",
                    f"服务 {svc.name} 当前有效账号数 {valid_count} 低于阈值 {threshold}，准备自动补注册 {to_register} 个",
                    manual_logs,
                )
                if to_register > 0 and main_loop:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            trigger_auto_registration(to_register, svc.id),
                            main_loop,
                        )
                        _log("info", f"已为服务 {svc.name} 提交自动补注册任务", manual_logs)
                    except Exception as exc:
                        _log("error", f"提交自动补注册失败: {exc}", manual_logs)
                elif to_register > 0:
                    _log("error", "缺少可用事件循环，无法提交自动补注册任务", manual_logs)
    finally:
        _is_checking = False


async def _scheduler_loop():
    await asyncio.sleep(5)
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(None, check_sub2api_services_job, loop, None)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Sub2API scheduler loop 异常: %s", exc)

        interval_min = max(1, int(get_settings().sub2api_auto_check_interval or 60))
        await asyncio.sleep(interval_min * 60)


def start_sub2api_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return

    loop = asyncio.get_event_loop()
    _scheduler_task = loop.create_task(_scheduler_loop())
    logger.info("已启动 Sub2API 后台调度器")


def stop_sub2api_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    _scheduler_task = None
