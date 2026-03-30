from fastapi.testclient import TestClient
from datetime import datetime, timedelta


def _build_test_client(monkeypatch, tmp_path):
    db_path = tmp_path / "scheduler-test.db"
    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite:///{db_path}")

    import src.config.settings as settings_module
    import src.database.session as session_module
    import src.core.sub2api_scheduler as scheduler_module

    settings_module._settings = None
    session_module._db_manager = None
    scheduler_module.system_logs.clear()
    scheduler_module.global_log_counter = 0

    monkeypatch.setattr(scheduler_module, "start_sub2api_scheduler", lambda: None)
    monkeypatch.setattr(scheduler_module, "stop_sub2api_scheduler", lambda: None)
    monkeypatch.setattr(scheduler_module, "check_sub2api_services_job", lambda loop, logs=None: None)

    from src.web.app import create_app

    return TestClient(create_app())


def test_sub2api_scheduler_config_round_trip(monkeypatch, tmp_path):
    client = _build_test_client(monkeypatch, tmp_path)

    with client:
        response = client.post(
            "/api/sub2api-scheduler/config",
            json={
                "check_enabled": True,
                "check_interval": 15,
                "check_sleep": 2,
                "delete_invalid_accounts": True,
                "register_enabled": True,
                "register_threshold": 7,
                "register_batch_count": 3,
                "register_max_attempts": 10,
                "email_service": "temp_mail:12",
            },
        )
        assert response.status_code == 200
        assert response.json()["success"] is True

        saved = client.get("/api/sub2api-scheduler/config")
        assert saved.status_code == 200
        assert saved.json() == {
            "check_enabled": True,
            "check_interval": 15,
            "check_sleep": 2,
            "delete_invalid_accounts": True,
            "register_enabled": True,
            "register_threshold": 7,
            "register_batch_count": 3,
            "register_max_attempts": 10,
            "email_service": "temp_mail:12",
            "upload_enabled": True,
            "upload_service_ids": [],
            "register_mode": "parallel",
            "register_concurrency": 3,
            "register_interval_min": 5,
            "register_interval_max": 30,
        }


def test_sub2api_scheduler_stop_request_persists_disabled_flags(monkeypatch, tmp_path):
    client = _build_test_client(monkeypatch, tmp_path)

    with client:
        client.post(
            "/api/sub2api-scheduler/config",
            json={
                "check_enabled": True,
                "check_interval": 30,
                "check_sleep": 1,
                "register_enabled": True,
                "register_threshold": 10,
                "register_batch_count": 5,
                "register_max_attempts": 10,
                "email_service": "tempmail:default",
            },
        )

        response = client.post(
            "/api/sub2api-scheduler/config",
            json={
                "check_enabled": False,
                "check_interval": 30,
                "check_sleep": 1,
                "register_enabled": False,
                "register_threshold": 10,
                "register_batch_count": 5,
                "register_max_attempts": 10,
                "email_service": "tempmail:default",
            },
        )
        assert response.status_code == 200

        saved = client.get("/api/sub2api-scheduler/config").json()
        assert saved["check_enabled"] is False
        assert saved["register_enabled"] is False
        assert saved["delete_invalid_accounts"] is False


def test_sub2api_scheduler_config_defaults_delete_invalid_accounts_to_false(monkeypatch, tmp_path):
    client = _build_test_client(monkeypatch, tmp_path)

    with client:
        response = client.post(
            "/api/sub2api-scheduler/config",
            json={
                "check_enabled": True,
                "check_interval": 15,
                "check_sleep": 2,
                "register_enabled": True,
                "register_threshold": 7,
                "register_batch_count": 3,
                "register_max_attempts": 10,
                "email_service": "temp_mail:12",
            },
        )
        assert response.status_code == 200

        saved = client.get("/api/sub2api-scheduler/config")
        assert saved.status_code == 200
        assert saved.json()["delete_invalid_accounts"] is False


def test_sub2api_scheduler_status_includes_check_enabled(monkeypatch, tmp_path):
    client = _build_test_client(monkeypatch, tmp_path)

    with client:
        client.post(
            "/api/sub2api-scheduler/config",
            json={
                "check_enabled": True,
                "check_interval": 20,
                "check_sleep": 1,
                "register_enabled": False,
                "register_threshold": 10,
                "register_batch_count": 5,
                "register_max_attempts": 10,
                "email_service": "tempmail:default",
            },
        )

        status = client.get("/api/sub2api-scheduler/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["success"] is True
        assert payload["status"]["check_enabled"] is True


def test_sub2api_scheduler_history_range_filter(monkeypatch, tmp_path):
    client = _build_test_client(monkeypatch, tmp_path)

    from src.database.session import get_db
    from src.database import crud

    with get_db() as db:
        crud.create_sub2api_scheduler_history_point(
            db,
            event_type="scan_completed",
            timestamp=datetime.utcnow() - timedelta(hours=3),
            service_id=1,
            accounts_healthy_after_scan=10,
            accounts_rate_limited_after_scan=2,
            total_accounts_after_scan=12,
        )
        crud.create_sub2api_scheduler_history_point(
            db,
            event_type="replenish_completed",
            timestamp=datetime.utcnow() - timedelta(hours=30),
            service_id=1,
            replenish_success_count=3,
            total_healthy_after_replenish=13,
        )

    with client:
        res_24h = client.get("/api/sub2api-scheduler/history?range=24h")
        assert res_24h.status_code == 200
        payload_24h = res_24h.json()
        assert payload_24h["success"] is True
        assert len(payload_24h["points"]) == 1
        assert payload_24h["points"][0]["event_type"] == "auto_task_completed"
        assert payload_24h["points"][0]["total_accounts_after_scan"] == 12

        res_7d = client.get("/api/sub2api-scheduler/history?range=7d")
        assert res_7d.status_code == 200
        payload_7d = res_7d.json()
        assert payload_7d["success"] is True
        assert len(payload_7d["points"]) == 2

        invalid = client.get("/api/sub2api-scheduler/history?range=2h")
        assert invalid.status_code == 200
        assert invalid.json()["success"] is False


def test_sub2api_scheduler_history_coalesces_legacy_events(monkeypatch, tmp_path):
    client = _build_test_client(monkeypatch, tmp_path)

    from src.database.session import get_db
    from src.database import crud

    anchor = datetime.utcnow() - timedelta(hours=1)
    with get_db() as db:
        crud.create_sub2api_scheduler_history_point(
            db,
            event_type="scan_completed",
            timestamp=anchor,
            service_id=2,
            accounts_healthy_after_scan=50,
            accounts_rate_limited_after_scan=5,
            total_accounts_after_scan=55,
        )
        crud.create_sub2api_scheduler_history_point(
            db,
            event_type="replenish_completed",
            timestamp=anchor + timedelta(seconds=20),
            service_id=2,
            replenish_success_count=4,
            total_healthy_after_replenish=59,
        )

    with client:
        res = client.get("/api/sub2api-scheduler/history?range=24h")
        assert res.status_code == 200
        payload = res.json()
        assert payload["success"] is True
        assert len(payload["points"]) == 1
        point = payload["points"][0]
        assert point["event_type"] == "auto_task_completed"
        assert point["accounts_healthy_after_scan"] == 50
        assert point["replenish_success_count"] == 4
        assert point["total_healthy_after_replenish"] == 59
