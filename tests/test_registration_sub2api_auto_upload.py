from types import SimpleNamespace

from src.web.routes import registration as registration_routes
from src.core.upload import sub2api_upload


def test_auto_upload_registered_account_to_sub2api_passes_proxy_id(monkeypatch):
    service = SimpleNamespace(
        id=1,
        name="SmewAI",
        api_url="https://smew.ai",
        api_key="key-123",
        group_ids=[6, 5, 7],
        proxy_id=88,
    )
    account = SimpleNamespace(email="tester@example.com", access_token="token-123")
    logs = []
    captured = {}

    monkeypatch.setattr(
        registration_routes.crud,
        "get_sub2api_services",
        lambda db, enabled=True: [service],
    )
    monkeypatch.setattr(
        registration_routes.crud,
        "get_sub2api_service_by_id",
        lambda db, service_id: service if service_id == 1 else None,
    )

    def fake_upload_to_sub2api(accounts, api_url, api_key, concurrency=3, priority=50, group_ids=None, proxy_id=None):
        captured["accounts"] = accounts
        captured["api_url"] = api_url
        captured["api_key"] = api_key
        captured["group_ids"] = group_ids
        captured["proxy_id"] = proxy_id
        return True, "ok"

    monkeypatch.setattr(sub2api_upload, "upload_to_sub2api", fake_upload_to_sub2api)

    ok = registration_routes._auto_upload_registered_account_to_sub2api(
        db=object(),
        saved_account=account,
        sub2api_service_ids=[1],
        log_callback=logs.append,
    )

    assert ok is True
    assert captured["accounts"] == [account]
    assert captured["api_url"] == "https://smew.ai"
    assert captured["api_key"] == "key-123"
    assert captured["group_ids"] == [6, 5, 7]
    assert captured["proxy_id"] == 88
    assert any("proxy_id=88" in message for message in logs)
