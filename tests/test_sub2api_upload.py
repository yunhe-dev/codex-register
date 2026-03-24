from src.core.upload import sub2api_upload


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
