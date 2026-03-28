from src.core.upload import sub2api_upload
from src.config.constants import OPENAI_SUB2API_MODEL_MAPPING


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json payload")
        return self._payload


def test_list_sub2api_openai_accounts_handles_paginated_response(monkeypatch):
    calls = []
    responses = [
        FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "items": [
                        {"id": 1, "platform": "openai", "name": "openai-1"},
                        {"id": 2, "platform": "anthropic", "name": "claude-1"},
                    ],
                    "page": 1,
                    "pages": 2,
                }
            },
        ),
        FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "items": [
                        {"id": 3, "platform": "openai", "name": "openai-2"},
                    ],
                    "page": 2,
                    "pages": 2,
                }
            },
        ),
    ]

    def fake_get(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return responses.pop(0)

    monkeypatch.setattr(sub2api_upload.cffi_requests, "get", fake_get)

    accounts = sub2api_upload.list_sub2api_openai_accounts(
        "https://sub2api.example.com",
        "key-123",
        page_size=100,
    )

    assert [account["id"] for account in accounts] == [1, 3]
    assert calls[0]["url"] == "https://sub2api.example.com/api/v1/admin/accounts"
    assert calls[0]["kwargs"]["params"]["page"] == 1
    assert calls[1]["kwargs"]["params"]["page"] == 2


def test_list_sub2api_proxies_handles_success_wrapper(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(
            status_code=200,
            payload={
                "success": True,
                "data": [
                    {
                        "id": 7,
                        "name": "Proxy A",
                        "protocol": "socks5",
                        "host": "1.2.3.4",
                        "port": 1080,
                        "status": "active",
                    },
                    {
                        "id": "8",
                        "name": "Proxy B",
                        "protocol": "http",
                        "host": "5.6.7.8",
                        "port": 8080,
                        "status": "inactive",
                    },
                ],
            },
        )

    monkeypatch.setattr(sub2api_upload.cffi_requests, "get", fake_get)

    proxies = sub2api_upload.list_sub2api_proxies(
        "https://sub2api.example.com",
        "key-123",
    )

    assert proxies == [
        {
            "id": 7,
            "name": "Proxy A",
            "protocol": "socks5",
            "host": "1.2.3.4",
            "port": 1080,
            "status": "active",
        },
        {
            "id": 8,
            "name": "Proxy B",
            "protocol": "http",
            "host": "5.6.7.8",
            "port": 8080,
            "status": "inactive",
        },
    ]
    assert calls[0]["url"] == "https://sub2api.example.com/api/v1/admin/proxies/all"


def test_test_sub2api_account_returns_false_for_explicit_failure(monkeypatch):
    def fake_post(url, **kwargs):
        return FakeResponse(status_code=200, payload={"success": False, "message": "token expired"})

    monkeypatch.setattr(sub2api_upload.cffi_requests, "post", fake_post)

    result, message = sub2api_upload.test_sub2api_account(
        "https://sub2api.example.com",
        "key-123",
        9,
    )

    assert result is False
    assert message == "token expired"


def test_upload_to_sub2api_uses_account_create_when_proxy_id_is_configured(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(status_code=201, payload={"success": True})

    account = type(
        "AccountStub",
        (),
        {
            "email": "tester@example.com",
            "access_token": "token-123",
            "expires_at": None,
            "account_id": "acct-1",
            "client_id": "client-1",
            "workspace_id": "ws-1",
            "refresh_token": "refresh-1",
        },
    )()

    monkeypatch.setattr(sub2api_upload.cffi_requests, "post", fake_post)

    success, message = sub2api_upload.upload_to_sub2api(
        [account],
        "https://sub2api.example.com",
        "key-123",
        proxy_id=42,
    )

    assert success is True
    assert "绑定代理" in message
    assert calls[0]["url"] == "https://sub2api.example.com/api/v1/admin/accounts"
    assert calls[0]["kwargs"]["json"]["proxy_id"] == 42
    assert calls[0]["kwargs"]["json"]["group_ids"] == []
    assert calls[0]["kwargs"]["json"]["credentials"]["model_mapping"] == OPENAI_SUB2API_MODEL_MAPPING


def test_upload_to_sub2api_bulk_payload_includes_gpt_5_4_mini(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(status_code=201, payload={"success": True})

    account = type(
        "AccountStub",
        (),
        {
            "email": "tester@example.com",
            "access_token": "token-123",
            "expires_at": None,
            "account_id": "acct-1",
            "client_id": "client-1",
            "workspace_id": "ws-1",
            "refresh_token": "refresh-1",
        },
    )()

    monkeypatch.setattr(sub2api_upload.cffi_requests, "post", fake_post)

    success, message = sub2api_upload.upload_to_sub2api(
        [account],
        "https://sub2api.example.com",
        "key-123",
    )

    assert success is True
    assert message == "成功上传 1 个账号"
    assert calls[0]["url"] == "https://sub2api.example.com/api/v1/admin/accounts/data"
    payload = calls[0]["kwargs"]["json"]["data"]["accounts"][0]
    assert payload["credentials"]["model_mapping"] == OPENAI_SUB2API_MODEL_MAPPING
    assert payload["credentials"]["model_mapping"]["gpt-5.4-mini"] == "gpt-5.4-mini"


def test_test_sub2api_account_returns_unknown_on_timeout(monkeypatch):
    def fake_post(url, **kwargs):
        raise sub2api_upload.cffi_requests.exceptions.Timeout("boom")

    monkeypatch.setattr(sub2api_upload.cffi_requests, "post", fake_post)

    result, message = sub2api_upload.test_sub2api_account(
        "https://sub2api.example.com",
        "key-123",
        9,
    )

    assert result is None
    assert "超时" in message


def test_test_sub2api_account_returns_false_on_rate_limit(monkeypatch):
    def fake_post(url, **kwargs):
        return FakeResponse(status_code=429)

    monkeypatch.setattr(sub2api_upload.cffi_requests, "post", fake_post)

    result, message = sub2api_upload.test_sub2api_account(
        "https://sub2api.example.com",
        "key-123",
        9,
    )

    assert result is False
    assert "按失效处理" in message


def test_delete_sub2api_account_accepts_204(monkeypatch):
    calls = []

    def fake_delete(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(status_code=204)

    monkeypatch.setattr(sub2api_upload.cffi_requests, "delete", fake_delete)

    success, message = sub2api_upload.delete_sub2api_account(
        "https://sub2api.example.com",
        "key-123",
        42,
    )

    assert success is True
    assert message == "删除成功"
    assert calls[0]["url"] == "https://sub2api.example.com/api/v1/admin/accounts/42"
