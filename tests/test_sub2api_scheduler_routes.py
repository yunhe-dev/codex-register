from fastapi.testclient import TestClient


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
            "register_enabled": True,
            "register_threshold": 7,
            "register_batch_count": 3,
            "register_max_attempts": 10,
            "email_service": "temp_mail:12",
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
