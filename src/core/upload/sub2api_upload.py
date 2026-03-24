"""
Sub2API 账号上传与管理功能。
将账号以 sub2api-data 格式批量导入到 Sub2API 平台，并提供管理侧辅助接口。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from curl_cffi import requests as cffi_requests

from ...database.models import Account
from ...database.session import get_db

logger = logging.getLogger(__name__)

DEFAULT_SUB2API_TIMEOUT = 30
DEFAULT_SUB2API_IMPERSONATE = "chrome110"


def _build_sub2api_admin_url(api_url: str, path: str) -> str:
    """拼接 Sub2API 管理端 URL，兼容用户输入已带 /api/v1 前缀的情况。"""
    base_url = (api_url or "").strip().rstrip("/")
    normalized_path = path if path.startswith("/") else f"/{path}"

    if base_url.endswith("/api/v1"):
        return f"{base_url}{normalized_path}"
    if normalized_path.startswith("/api/v1/"):
        return f"{base_url}{normalized_path}"
    return f"{base_url}/api/v1{normalized_path}"


def _build_sub2api_headers(api_key: str, content_type: Optional[str] = None) -> Dict[str, str]:
    headers = {"x-api-key": api_key}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _extract_sub2api_message(payload: Any, default: str) -> str:
    if isinstance(payload, dict):
        for key in ("message", "detail", "error", "msg"):
            value = payload.get(key)
            if value:
                return str(value)
        nested = payload.get("data")
        if isinstance(nested, dict):
            return _extract_sub2api_message(nested, default)
    return default


def _sub2api_payload_indicates_failure(payload: Any) -> Optional[str]:
    """仅在响应明确标记失败时返回失败原因，其余情况返回 None 以避免误删。"""
    if not isinstance(payload, dict):
        return None

    if payload.get("success") is False:
        return _extract_sub2api_message(payload, "接口明确返回失败")

    code = payload.get("code")
    if isinstance(code, int) and code not in (0, 200):
        return _extract_sub2api_message(payload, f"接口返回异常 code={code}")

    status = payload.get("status")
    if isinstance(status, str) and status.lower() in {"failed", "error", "invalid", "inactive"}:
        return _extract_sub2api_message(payload, f"账号状态异常: {status}")

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("success", "valid", "available", "passed"):
            value = data.get(key)
            if value is False:
                return _extract_sub2api_message(data, f"{key}=false")

        nested_status = data.get("status")
        if isinstance(nested_status, str) and nested_status.lower() in {"failed", "error", "invalid", "inactive"}:
            return _extract_sub2api_message(data, f"账号状态异常: {nested_status}")

    return None


def _extract_json_from_text(text: str) -> Optional[Any]:
    if not text:
        return None
    text = text.strip()
    if not text:
        return None

    if text.startswith("{") or text.startswith("["):
        import json
        try:
            return json.loads(text)
        except Exception:
            return None
    return None


def _extract_sub2api_failure_from_text(text: str) -> Optional[str]:
    if not text:
        return None

    parsed = _extract_json_from_text(text)
    if parsed is not None:
        return _sub2api_payload_indicates_failure(parsed) or _extract_sub2api_message(parsed, "")

    normalized = text.lower()
    keywords = (
        "account_deactivated",
        "deactivated",
        "invalid_api_key",
        "insufficient_quota",
        "usage_limit_reached",
        "token expired",
        "invalid token",
        "unauthorized",
        "forbidden",
    )
    if any(keyword in normalized for keyword in keywords):
        return text.strip()
    return None


def _parse_sse_test_events(text: str) -> Tuple[Optional[bool], Optional[str]]:
    """
    解析 Sub2API /test 接口的 SSE 响应。

    返回:
        (False, reason): 明确失败
        (True, message): 明确成功
        (None, None): 无法从 SSE 中判定
    """
    if not text:
        return None, None

    data_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("data:"):
            data_lines.append(stripped[5:].strip())

    if not data_lines:
        return None, None

    saw_success_signal = False
    for payload_text in data_lines:
        payload = _extract_json_from_text(payload_text)
        if not isinstance(payload, dict):
            failure = _extract_sub2api_failure_from_text(payload_text)
            if failure:
                return False, failure
            continue

        event_type = str(payload.get("type") or "").strip().lower()
        if event_type in {"error", "test_error", "failed"}:
            error_text = payload.get("error") or payload.get("message") or payload_text
            failure = _extract_sub2api_failure_from_text(str(error_text)) or str(error_text)
            return False, failure

        if event_type in {"result", "test_result", "complete", "completed", "success"}:
            failure = _sub2api_payload_indicates_failure(payload)
            if failure:
                return False, failure
            saw_success_signal = True
            continue

        failure = _sub2api_payload_indicates_failure(payload)
        if failure:
            return False, failure

    if saw_success_signal:
        return True, "账号测试成功"

    return None, None


def _parse_sub2api_accounts_payload(payload: Any, page_size: int) -> Tuple[List[Dict[str, Any]], bool]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    items: List[Dict[str, Any]] = []
    has_more = False

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)], False

    if not isinstance(data, dict):
        return [], False

    for key in ("items", "list", "accounts", "records", "rows"):
        candidate = data.get(key)
        if isinstance(candidate, list):
            items = [item for item in candidate if isinstance(item, dict)]
            break

    pagination = None
    for key in ("pagination", "page_info", "pageInfo", "meta"):
        candidate = data.get(key)
        if isinstance(candidate, dict):
            pagination = candidate
            break

    total = pagination.get("total") if pagination else data.get("total")
    page = pagination.get("page") if pagination else data.get("page")
    pages = pagination.get("pages") if pagination else data.get("pages")
    page_size_value = (
        pagination.get("page_size")
        if pagination and pagination.get("page_size") is not None
        else pagination.get("pageSize") if pagination else data.get("page_size")
    )
    has_more_flag = pagination.get("has_more") if pagination else data.get("has_more")

    if isinstance(has_more_flag, bool):
        has_more = has_more_flag
    elif isinstance(page, int) and isinstance(pages, int):
        has_more = page < pages
    elif isinstance(page, int) and isinstance(page_size_value, int) and isinstance(total, int):
        has_more = page * page_size_value < total
    elif items:
        has_more = len(items) >= page_size

    return items, has_more


def upload_to_sub2api(
    accounts: List[Account],
    api_url: str,
    api_key: str,
    concurrency: int = 3,
    priority: int = 50,
    group_ids: Optional[List[int]] = None,
) -> Tuple[bool, str]:
    """
    上传账号列表到 Sub2API 平台（不走代理）。
    """
    if not accounts:
        return False, "无可上传的账号"

    if not api_url:
        return False, "Sub2API URL 未配置"

    if not api_key:
        return False, "Sub2API API Key 未配置"

    normalized_group_ids = _normalize_group_ids(group_ids)
    if normalized_group_ids:
        success_count = 0
        failed_count = 0
        for acc in accounts:
            if not acc.access_token:
                continue
            ok, _ = _create_account_with_group_binding(
                acc,
                api_url,
                api_key,
                concurrency=concurrency,
                priority=priority,
                group_ids=normalized_group_ids,
            )
            if ok:
                success_count += 1
            else:
                failed_count += 1

        if failed_count == 0 and success_count > 0:
            return True, f"成功上传 {success_count} 个账号（并绑定分组）"
        if success_count == 0:
            return False, "分组上传失败"
        return False, f"部分上传成功：成功 {success_count}，失败 {failed_count}"

    exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    account_items = _build_sub2api_account_items(accounts, concurrency, priority)

    if not account_items:
        return False, "所有账号均缺少 access_token，无法上传"

    payload = {
        "data": {
            "type": "sub2api-data",
            "version": 1,
            "exported_at": exported_at,
            "proxies": [],
            "accounts": account_items,
        },
        "skip_default_group_bind": True,
    }

    url = _build_sub2api_admin_url(api_url, "/admin/accounts/data")
    headers = _build_sub2api_headers(api_key, content_type="application/json")
    headers["Idempotency-Key"] = f"import-{exported_at}"

    try:
        response = cffi_requests.post(
            url,
            json=payload,
            headers=headers,
            proxies=None,
            timeout=DEFAULT_SUB2API_TIMEOUT,
            impersonate=DEFAULT_SUB2API_IMPERSONATE,
        )

        if response.status_code in (200, 201):
            return True, f"成功上传 {len(account_items)} 个账号"

        error_msg = f"上传失败: HTTP {response.status_code}"
        try:
            detail = response.json()
            if isinstance(detail, dict):
                error_msg = detail.get("message", error_msg)
        except Exception:
            error_msg = f"{error_msg} - {response.text[:200]}"
        return False, error_msg
    except Exception as exc:
        logger.error("Sub2API 上传异常: %s", exc)
        return False, f"上传异常: {exc}"


def batch_upload_to_sub2api(
    account_ids: List[int],
    api_url: str,
    api_key: str,
    concurrency: int = 3,
    priority: int = 50,
    group_ids: Optional[List[int]] = None,
) -> dict:
    """
    批量上传指定 ID 的账号到 Sub2API 平台。
    """
    results = {
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "details": [],
    }

    with get_db() as db:
        accounts = []
        for account_id in account_ids:
            acc = db.query(Account).filter(Account.id == account_id).first()
            if not acc:
                results["failed_count"] += 1
                results["details"].append({"id": account_id, "email": None, "success": False, "error": "账号不存在"})
                continue
            if not acc.access_token:
                results["skipped_count"] += 1
                results["details"].append({"id": account_id, "email": acc.email, "success": False, "error": "缺少 access_token"})
                continue
            accounts.append(acc)

        if not accounts:
            return results

        normalized_group_ids = _normalize_group_ids(group_ids)
        if normalized_group_ids:
            for acc in accounts:
                ok, msg = _create_account_with_group_binding(
                    acc,
                    api_url,
                    api_key,
                    concurrency=concurrency,
                    priority=priority,
                    group_ids=normalized_group_ids,
                )
                if ok:
                    results["success_count"] += 1
                    results["details"].append({"id": acc.id, "email": acc.email, "success": True, "message": msg})
                else:
                    results["failed_count"] += 1
                    results["details"].append({"id": acc.id, "email": acc.email, "success": False, "error": msg})
        else:
            success, message = upload_to_sub2api(accounts, api_url, api_key, concurrency, priority, group_ids=None)
            if success:
                for acc in accounts:
                    results["success_count"] += 1
                    results["details"].append({"id": acc.id, "email": acc.email, "success": True, "message": message})
            else:
                for acc in accounts:
                    results["failed_count"] += 1
                    results["details"].append({"id": acc.id, "email": acc.email, "success": False, "error": message})

    return results


def test_sub2api_connection(api_url: str, api_key: str) -> Tuple[bool, str]:
    """
    测试 Sub2API 连接（GET /api/v1/admin/accounts/data 探活）。
    """
    if not api_url:
        return False, "API URL 不能为空"
    if not api_key:
        return False, "API Key 不能为空"

    url = _build_sub2api_admin_url(api_url, "/admin/accounts/data")
    headers = _build_sub2api_headers(api_key)

    try:
        response = cffi_requests.get(
            url,
            headers=headers,
            proxies=None,
            timeout=10,
            impersonate=DEFAULT_SUB2API_IMPERSONATE,
        )

        if response.status_code in (200, 201, 204, 405):
            return True, "Sub2API 连接测试成功"
        if response.status_code == 401:
            return False, "连接成功，但 API Key 无效"
        if response.status_code == 403:
            return False, "连接成功，但权限不足"

        return False, f"服务器返回异常状态码: {response.status_code}"
    except cffi_requests.exceptions.ConnectionError as exc:
        return False, f"无法连接到服务器: {exc}"
    except cffi_requests.exceptions.Timeout:
        return False, "连接超时，请检查网络配置"
    except Exception as exc:
        return False, f"连接测试失败: {exc}"


def list_sub2api_groups(api_url: str, api_key: str, platform: str = "openai") -> List[Dict[str, Any]]:
    """
    获取 Sub2API 可用分组（优先 openai 平台）。
    """
    if not api_url or not api_key:
        return []

    url = _build_sub2api_admin_url(api_url, "/admin/groups/all")
    headers = _build_sub2api_headers(api_key)
    params = {"platform": platform} if platform else None

    try:
        response = cffi_requests.get(
            url,
            headers=headers,
            params=params,
            proxies=None,
            timeout=15,
            impersonate=DEFAULT_SUB2API_IMPERSONATE,
        )
        if response.status_code not in (200, 201):
            return []

        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(data, list):
            return []

        groups: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            gid = item.get("id")
            name = item.get("name")
            if gid is None or name is None:
                continue
            try:
                gid = int(gid)
            except Exception:
                continue
            groups.append({
                "id": gid,
                "name": str(name),
                "platform": item.get("platform", ""),
                "status": item.get("status", ""),
            })
        return groups
    except Exception:
        return []


def list_sub2api_openai_accounts(api_url: str, api_key: str, page_size: int = 100) -> List[Dict[str, Any]]:
    """列出远端 openai 账号，自动处理常见分页返回结构。"""
    if not api_url or not api_key:
        return []

    url = _build_sub2api_admin_url(api_url, "/admin/accounts")
    headers = _build_sub2api_headers(api_key)
    page = 1
    collected: List[Dict[str, Any]] = []

    while True:
        response = cffi_requests.get(
            url,
            headers=headers,
            params={"page": page, "page_size": page_size, "platform": "openai"},
            proxies=None,
            timeout=DEFAULT_SUB2API_TIMEOUT,
            impersonate=DEFAULT_SUB2API_IMPERSONATE,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"拉取 Sub2API 账号列表失败: HTTP {response.status_code}")

        payload = response.json()
        items, has_more = _parse_sub2api_accounts_payload(payload, page_size)
        if not items:
            break

        for item in items:
            platform = str(item.get("platform") or "").strip().lower()
            if not platform or platform == "openai":
                collected.append(item)

        if not has_more:
            break
        page += 1

    return collected


def test_sub2api_account(api_url: str, api_key: str, account_id: int) -> Tuple[Optional[bool], str]:
    """
    测试单个远端账号。

    返回:
        (True, msg): 明确健康
        (False, msg): 明确失效
        (None, msg): 无法判定，调度器应仅记录日志，不执行删除
    """
    if not api_url or not api_key:
        return None, "Sub2API 连接配置不完整"

    url = _build_sub2api_admin_url(api_url, f"/admin/accounts/{account_id}/test")
    headers = _build_sub2api_headers(api_key, content_type="application/json")

    try:
        response = cffi_requests.post(
            url,
            headers=headers,
            json={},
            proxies=None,
            timeout=DEFAULT_SUB2API_TIMEOUT,
            impersonate=DEFAULT_SUB2API_IMPERSONATE,
        )
    except cffi_requests.exceptions.Timeout:
        return None, "测试账号超时"
    except cffi_requests.exceptions.ConnectionError as exc:
        return None, f"测试账号连接失败: {exc}"
    except Exception as exc:
        logger.error("Sub2API 单账号测试异常: %s", exc)
        return None, f"测试账号异常: {exc}"

    if response.status_code in (401, 403):
        return None, f"测试接口鉴权失败: HTTP {response.status_code}"
    if response.status_code == 404:
        return False, "远端账号不存在"
    if response.status_code >= 500:
        return None, f"测试接口异常: HTTP {response.status_code}"
    if response.status_code >= 400:
        try:
            payload = response.json()
        except Exception:
            return False, f"账号测试失败: HTTP {response.status_code}"
        return False, _extract_sub2api_message(payload, f"账号测试失败: HTTP {response.status_code}")

    try:
        payload = response.json()
    except Exception:
        sse_result, sse_message = _parse_sse_test_events(getattr(response, "text", ""))
        if sse_result is not None:
            return sse_result, sse_message or "账号测试完成"
        failure = _extract_sub2api_failure_from_text(getattr(response, "text", ""))
        if failure:
            return False, failure
        return True, "账号测试成功"

    failure_reason = _sub2api_payload_indicates_failure(payload)
    if failure_reason:
        return False, failure_reason
    return True, _extract_sub2api_message(payload, "账号测试成功")


def delete_sub2api_account(api_url: str, api_key: str, account_id: int) -> Tuple[bool, str]:
    """删除单个远端账号。"""
    if not api_url or not api_key:
        return False, "Sub2API 连接配置不完整"

    url = _build_sub2api_admin_url(api_url, f"/admin/accounts/{account_id}")
    headers = _build_sub2api_headers(api_key)

    try:
        response = cffi_requests.delete(
            url,
            headers=headers,
            proxies=None,
            timeout=DEFAULT_SUB2API_TIMEOUT,
            impersonate=DEFAULT_SUB2API_IMPERSONATE,
        )
    except Exception as exc:
        logger.error("Sub2API 删除账号异常: %s", exc)
        return False, f"删除账号异常: {exc}"

    if response.status_code in (200, 201, 204):
        try:
            payload = response.json()
        except Exception:
            return True, "删除成功"
        return True, _extract_sub2api_message(payload, "删除成功")

    try:
        payload = response.json()
    except Exception:
        return False, f"删除失败: HTTP {response.status_code}"
    return False, _extract_sub2api_message(payload, f"删除失败: HTTP {response.status_code}")


def _build_sub2api_account_items(accounts: List[Account], concurrency: int, priority: int) -> List[Dict[str, Any]]:
    """构建 /accounts/data 导入格式。"""
    account_items: List[Dict[str, Any]] = []
    for acc in accounts:
        if not acc.access_token:
            continue
        expires_at = int(acc.expires_at.timestamp()) if acc.expires_at else 0
        account_items.append({
            "name": acc.email,
            "platform": "openai",
            "type": "oauth",
            "credentials": {
                "access_token": acc.access_token,
                "chatgpt_account_id": acc.account_id or "",
                "chatgpt_user_id": "",
                "client_id": acc.client_id or "",
                "expires_at": expires_at,
                "expires_in": 863999,
                "model_mapping": {
                    "gpt-5.1": "gpt-5.1",
                    "gpt-5.1-codex": "gpt-5.1-codex",
                    "gpt-5.1-codex-max": "gpt-5.1-codex-max",
                    "gpt-5.1-codex-mini": "gpt-5.1-codex-mini",
                    "gpt-5.2": "gpt-5.2",
                    "gpt-5.2-codex": "gpt-5.2-codex",
                    "gpt-5.3": "gpt-5.3",
                    "gpt-5.3-codex": "gpt-5.3-codex",
                    "gpt-5.4": "gpt-5.4",
                },
                "organization_id": acc.workspace_id or "",
                "refresh_token": acc.refresh_token or "",
            },
            "extra": {
                "managed_by": "codex-register",
            },
            "concurrency": concurrency,
            "priority": priority,
            "rate_multiplier": 1,
            "auto_pause_on_expired": True,
        })
    return account_items


def _create_account_with_group_binding(
    acc: Account,
    api_url: str,
    api_key: str,
    concurrency: int,
    priority: int,
    group_ids: List[int],
) -> Tuple[bool, str]:
    """按单账号创建接口上传并绑定分组（smewai 支持 group_ids）。"""
    expires_at = int(acc.expires_at.timestamp()) if acc.expires_at else 0
    payload = {
        "name": acc.email,
        "platform": "openai",
        "type": "oauth",
        "credentials": {
            "access_token": acc.access_token,
            "chatgpt_account_id": acc.account_id or "",
            "chatgpt_user_id": "",
            "client_id": acc.client_id or "",
            "expires_at": expires_at,
            "expires_in": 863999,
            "model_mapping": {
                "gpt-5.1": "gpt-5.1",
                "gpt-5.1-codex": "gpt-5.1-codex",
                "gpt-5.1-codex-max": "gpt-5.1-codex-max",
                "gpt-5.1-codex-mini": "gpt-5.1-codex-mini",
                "gpt-5.2": "gpt-5.2",
                "gpt-5.2-codex": "gpt-5.2-codex",
                "gpt-5.3": "gpt-5.3",
                "gpt-5.3-codex": "gpt-5.3-codex",
                "gpt-5.4": "gpt-5.4",
            },
            "organization_id": acc.workspace_id or "",
            "refresh_token": acc.refresh_token or "",
        },
        "extra": {
            "managed_by": "codex-register",
        },
        "concurrency": concurrency,
        "priority": priority,
        "rate_multiplier": 1,
        "auto_pause_on_expired": True,
        "group_ids": group_ids,
        "confirm_mixed_channel_risk": True,
    }

    url = _build_sub2api_admin_url(api_url, "/admin/accounts")
    headers = _build_sub2api_headers(api_key, content_type="application/json")
    try:
        response = cffi_requests.post(
            url,
            json=payload,
            headers=headers,
            proxies=None,
            timeout=DEFAULT_SUB2API_TIMEOUT,
            impersonate=DEFAULT_SUB2API_IMPERSONATE,
        )
        if response.status_code in (200, 201):
            return True, "上传并绑定分组成功"

        err = f"HTTP {response.status_code}"
        try:
            detail = response.json()
            if isinstance(detail, dict):
                err = detail.get("detail") or detail.get("message") or err
        except Exception:
            err = f"{err} - {response.text[:200]}"
        return False, err
    except Exception as exc:
        logger.error("Sub2API 单账号分组上传异常: %s", exc)
        return False, str(exc)


def _normalize_group_ids(group_ids: Optional[List[int]]) -> List[int]:
    out: List[int] = []
    for gid in group_ids or []:
        try:
            value = int(gid)
        except Exception:
            continue
        if value > 0 and value not in out:
            out.append(value)
    return out
