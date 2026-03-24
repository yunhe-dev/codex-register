from fastapi.testclient import TestClient


def _build_test_client(monkeypatch, tmp_path):
    db_path = tmp_path / "sub2api-proxy-test.db"
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


def test_sub2api_service_proxy_id_round_trip_and_clear(monkeypatch, tmp_path):
    client = _build_test_client(monkeypatch, tmp_path)

    with client:
        created = client.post(
            "/api/sub2api-services",
            json={
                "name": "SmewAI",
                "api_url": "https://smew.ai",
                "api_key": "key-123",
                "group_ids": [7, 8],
                "proxy_id": 42,
                "enabled": True,
                "priority": 0,
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["proxy_id"] == 42

        service_id = body["id"]
        fetched = client.get(f"/api/sub2api-services/{service_id}")
        assert fetched.status_code == 200
        assert fetched.json()["proxy_id"] == 42

        full = client.get(f"/api/sub2api-services/{service_id}/full")
        assert full.status_code == 200
        assert full.json()["proxy_id"] == 42

        cleared = client.patch(
            f"/api/sub2api-services/{service_id}",
            json={"proxy_id": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["proxy_id"] is None


def test_sub2api_service_proxies_fetch_routes(monkeypatch, tmp_path):
    import src.web.routes.upload.sub2api_services as service_routes

    client = _build_test_client(monkeypatch, tmp_path)

    monkeypatch.setattr(
        service_routes,
        "list_sub2api_proxies",
        lambda api_url, api_key: [{"id": 9, "name": "Proxy 9", "protocol": "socks5", "host": "1.1.1.1", "port": 1080, "status": "active"}],
    )

    with client:
        created = client.post(
            "/api/sub2api-services",
            json={
                "name": "SmewAI",
                "api_url": "https://smew.ai",
                "api_key": "key-123",
                "enabled": True,
                "priority": 0,
            },
        )
        service_id = created.json()["id"]

        by_id = client.get(f"/api/sub2api-services/{service_id}/proxies")
        assert by_id.status_code == 200
        assert by_id.json()["proxies"][0]["id"] == 9

        direct = client.post(
            "/api/sub2api-services/proxies/fetch",
            json={"api_url": "https://smew.ai", "api_key": "key-123"},
        )
        assert direct.status_code == 200
        assert direct.json()["proxies"][0]["name"] == "Proxy 9"


def test_batch_upload_sub2api_uses_service_group_and_proxy_defaults(monkeypatch, tmp_path):
    import src.web.routes.accounts as accounts_routes
    from src.database.models import Account, Sub2ApiService
    from src.database.session import get_db

    client = _build_test_client(monkeypatch, tmp_path)
    captured = {}

    def fake_batch_upload(account_ids, api_url, api_key, concurrency=3, priority=50, group_ids=None, proxy_id=None):
        captured["account_ids"] = account_ids
        captured["api_url"] = api_url
        captured["api_key"] = api_key
        captured["concurrency"] = concurrency
        captured["priority"] = priority
        captured["group_ids"] = group_ids
        captured["proxy_id"] = proxy_id
        return {"success_count": len(account_ids), "failed_count": 0, "skipped_count": 0, "details": []}

    monkeypatch.setattr(accounts_routes, "batch_upload_to_sub2api", fake_batch_upload)

    with get_db() as db:
        svc = Sub2ApiService(
            name="SmewAI",
            api_url="https://smew.ai",
            api_key="key-123",
            group_ids=[3, 5],
            proxy_id=88,
            enabled=True,
            priority=0,
        )
        db.add(svc)
        db.add(Account(email="tester@example.com", email_service="tempmail", access_token="token-1"))
        db.commit()
        service_id = svc.id

    with client:
        response = client.post(
            "/api/accounts/batch-upload-sub2api",
            json={
                "ids": [1],
                "service_id": service_id,
                "concurrency": 4,
                "priority": 60,
            },
        )

    assert response.status_code == 200
    assert captured == {
        "account_ids": [1],
        "api_url": "https://smew.ai",
        "api_key": "key-123",
        "concurrency": 4,
        "priority": 60,
        "group_ids": [3, 5],
        "proxy_id": 88,
    }


def test_service_upload_route_uses_service_proxy_default(monkeypatch, tmp_path):
    import src.web.routes.upload.sub2api_services as service_routes
    from src.database.models import Sub2ApiService
    from src.database.session import get_db

    client = _build_test_client(monkeypatch, tmp_path)
    captured = {}

    def fake_batch_upload(account_ids, api_url, api_key, concurrency=3, priority=50, group_ids=None, proxy_id=None):
        captured["account_ids"] = account_ids
        captured["group_ids"] = group_ids
        captured["proxy_id"] = proxy_id
        return {"success_count": len(account_ids), "failed_count": 0, "skipped_count": 0, "details": []}

    monkeypatch.setattr(service_routes, "batch_upload_to_sub2api", fake_batch_upload)

    with get_db() as db:
        svc = Sub2ApiService(
            name="SmewAI",
            api_url="https://smew.ai",
            api_key="key-123",
            group_ids=[11],
            proxy_id=99,
            enabled=True,
            priority=0,
        )
        db.add(svc)
        db.commit()
        service_id = svc.id

    with client:
        response = client.post(
            "/api/sub2api-services/upload",
            json={
                "account_ids": [7, 8],
                "service_id": service_id,
            },
        )

    assert response.status_code == 200
    assert captured["account_ids"] == [7, 8]
    assert captured["group_ids"] == [11]
    assert captured["proxy_id"] == 99
