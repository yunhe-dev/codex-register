import asyncio
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
