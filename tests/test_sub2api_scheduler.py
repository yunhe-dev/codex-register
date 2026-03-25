import asyncio
import threading
from contextlib import contextmanager
from types import SimpleNamespace

from src.core import sub2api_scheduler as scheduler


def test_trigger_auto_registration_uses_parallel_mode_with_fixed_concurrency(monkeypatch):
    captured = {}

    @contextmanager
    def fake_get_db():
        yield object()

    async def fake_run_batch_registration(**kwargs):
        captured.update(kwargs)

    def fake_create_registration_task(db, task_uuid, email_service_id, proxy):
        return SimpleNamespace(task_uuid=task_uuid, email_service_id=email_service_id, proxy=proxy)

    def fake_get_registration_task_by_uuid(db, task_uuid):
        return SimpleNamespace(status="completed", result={"sub2api_upload_success": True})

    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            sub2api_auto_register_max_attempts=1,
            registration_sleep_min=5,
            registration_sleep_max=30,
        ),
    )
    monkeypatch.setattr(scheduler, "get_db", fake_get_db)
    monkeypatch.setattr(scheduler, "_resolve_auto_register_email_service", lambda: ("tempmail", None))
    monkeypatch.setattr(scheduler, "_should_continue_auto_register", lambda: True)
    monkeypatch.setattr(scheduler, "run_batch_registration", fake_run_batch_registration)
    monkeypatch.setattr(scheduler, "append_system_log", lambda level, msg: None)
    monkeypatch.setattr(scheduler, "_update_scheduler_state", lambda **kwargs: None)
    monkeypatch.setattr(scheduler.crud, "create_registration_task", fake_create_registration_task)
    monkeypatch.setattr(scheduler.crud, "get_registration_task_by_uuid", fake_get_registration_task_by_uuid)

    scheduler._auto_registering_services.clear()

    asyncio.run(
        scheduler.trigger_auto_registration(count=3, sub2api_service_id=99, current_available_count=2)
    )

    assert captured["mode"] == scheduler.AUTO_REGISTER_BATCH_MODE == "parallel"
    assert captured["concurrency"] == scheduler.AUTO_REGISTER_BATCH_CONCURRENCY == 5
    assert captured["auto_upload_sub2api"] is True
    assert captured["sub2api_service_ids"] == [99]


def test_manual_check_keeps_next_scheduled_time(monkeypatch):
    @contextmanager
    def fake_get_db():
        yield object()

    scheduler._scheduler_state["next_scan_scheduled_at"] = "2099-01-01T00:00:00"
    scheduler._scheduler_state["last_scan_status"] = "idle"

    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            sub2api_auto_check_enabled=True,
            sub2api_auto_register_enabled=False,
        ),
    )
    monkeypatch.setattr(scheduler, "get_db", fake_get_db)
    monkeypatch.setattr(scheduler.crud, "get_sub2api_services", lambda db, enabled=True: [])
    monkeypatch.setattr(scheduler, "append_system_log", lambda level, msg: None)

    scheduler.check_sub2api_services_job(main_loop=None, manual_logs=[])

    snapshot = scheduler.get_scheduler_status_snapshot()
    assert snapshot["next_scan_scheduled_at"] == "2099-01-01T00:00:00"
    assert snapshot["last_scan_status"] == "completed"


def test_scan_counters_update_during_service_check(monkeypatch):
    @contextmanager
    def fake_get_db():
        yield object()

    service = SimpleNamespace(id=1, name="svc", api_url="https://example.com", api_key="k")
    second_account_started = threading.Event()
    release_second_account = threading.Event()
    call_count = {"value": 0}

    def fake_test_sub2api_account(api_url, api_key, account_id):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return True, "ok"
        second_account_started.set()
        release_second_account.wait(timeout=2)
        return True, "ok"

    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: SimpleNamespace(
            sub2api_auto_check_enabled=True,
            sub2api_auto_register_enabled=False,
            sub2api_auto_check_sleep_seconds=0,
            sub2api_auto_register_threshold=10,
            sub2api_auto_register_batch_count=5,
        ),
    )
    monkeypatch.setattr(scheduler, "get_db", fake_get_db)
    monkeypatch.setattr(scheduler.crud, "get_sub2api_services", lambda db, enabled=True: [service])
    monkeypatch.setattr(
        scheduler,
        "list_sub2api_openai_accounts",
        lambda api_url, api_key: [{"id": 1, "name": "a1"}, {"id": 2, "name": "a2"}],
    )
    monkeypatch.setattr(scheduler, "test_sub2api_account", fake_test_sub2api_account)
    monkeypatch.setattr(scheduler, "append_system_log", lambda level, msg: None)

    scheduler._is_checking = False
    scheduler._update_scheduler_state(
        accounts_scanned=0,
        accounts_healthy=0,
        accounts_rate_limited=0,
        accounts_unknown=0,
        accounts_invalid=0,
        accounts_deleted=0,
        accounts_delete_failed=0,
        available_accounts=0,
        services_succeeded=0,
        services_failed=0,
    )

    worker = threading.Thread(target=scheduler.check_sub2api_services_job, args=(None, None))
    worker.start()

    assert second_account_started.wait(timeout=2) is True
    mid_snapshot = scheduler.get_scheduler_status_snapshot()
    assert mid_snapshot["accounts_scanned"] == 1
    assert mid_snapshot["accounts_healthy"] == 1
    assert mid_snapshot["available_accounts"] == 1

    release_second_account.set()
    worker.join(timeout=2)
    assert worker.is_alive() is False

    final_snapshot = scheduler.get_scheduler_status_snapshot()
    assert final_snapshot["accounts_scanned"] == 2
    assert final_snapshot["accounts_healthy"] == 2
    assert final_snapshot["available_accounts"] == 2
    assert final_snapshot["services_succeeded"] == 1
