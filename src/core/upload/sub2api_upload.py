"""
Sub2API 账号上传功能
将账号以 sub2api-data 格式批量导入到 Sub2API 平台
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any

from curl_cffi import requests as cffi_requests

from ...database.session import get_db
from ...database.models import Account

logger = logging.getLogger(__name__)


def upload_to_sub2api(
    accounts: List[Account],
    api_url: str,
    api_key: str,
    concurrency: int = 3,
    priority: int = 50,
    group_ids: Optional[List[int]] = None,
) -> Tuple[bool, str]:
    """
    上传账号列表到 Sub2API 平台（不走代理）

    Args:
        accounts: 账号模型实例列表
        api_url: Sub2API 地址，如 http://host
        api_key: Admin API Key（x-api-key header）
        concurrency: 账号并发数，默认 3
        priority: 账号优先级，默认 50

    Returns:
        (成功标志, 消息)
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
                acc, api_url, api_key,
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

    url = api_url.rstrip("/") + "/api/v1/admin/accounts/data"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "Idempotency-Key": f"import-{exported_at}",
    }

    try:
        response = cffi_requests.post(
            url,
            json=payload,
            headers=headers,
            proxies=None,
            timeout=30,
            impersonate="chrome110",
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

    except Exception as e:
        logger.error(f"Sub2API 上传异常: {e}")
        return False, f"上传异常: {str(e)}"


def batch_upload_to_sub2api(
    account_ids: List[int],
    api_url: str,
    api_key: str,
    concurrency: int = 3,
    priority: int = 50,
    group_ids: Optional[List[int]] = None,
) -> dict:
    """
    批量上传指定 ID 的账号到 Sub2API 平台

    Returns:
        包含成功/失败/跳过统计和详情的字典
    """
    results = {
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "details": []
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
                    acc, api_url, api_key,
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
    测试 Sub2API 连接（GET /api/v1/admin/accounts/data 探活）

    Returns:
        (成功标志, 消息)
    """
    if not api_url:
        return False, "API URL 不能为空"
    if not api_key:
        return False, "API Key 不能为空"

    url = api_url.rstrip("/") + "/api/v1/admin/accounts/data"
    headers = {"x-api-key": api_key}

    try:
        response = cffi_requests.get(
            url,
            headers=headers,
            proxies=None,
            timeout=10,
            impersonate="chrome110",
        )

        if response.status_code in (200, 201, 204, 405):
            return True, "Sub2API 连接测试成功"
        if response.status_code == 401:
            return False, "连接成功，但 API Key 无效"
        if response.status_code == 403:
            return False, "连接成功，但权限不足"

        return False, f"服务器返回异常状态码: {response.status_code}"

    except cffi_requests.exceptions.ConnectionError as e:
        return False, f"无法连接到服务器: {str(e)}"
    except cffi_requests.exceptions.Timeout:
        return False, "连接超时，请检查网络配置"
    except Exception as e:
        return False, f"连接测试失败: {str(e)}"


def list_sub2api_groups(api_url: str, api_key: str, platform: str = "openai") -> List[Dict[str, Any]]:
    """
    获取 Sub2API 可用分组（优先 openai 平台）

    Returns:
        [{"id": 1, "name": "openai-default", "platform": "openai", "status": "active"}, ...]
    """
    if not api_url or not api_key:
        return []

    url = api_url.rstrip("/") + "/api/v1/admin/groups/all"
    headers = {"x-api-key": api_key}
    params = {"platform": platform} if platform else None

    try:
        response = cffi_requests.get(
            url,
            headers=headers,
            params=params,
            proxies=None,
            timeout=15,
            impersonate="chrome110",
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


def _build_sub2api_account_items(accounts: List[Account], concurrency: int, priority: int) -> List[Dict[str, Any]]:
    """构建 /accounts/data 导入格式"""
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
                    "gpt-5.4": "gpt-5.4"
                },
                "organization_id": acc.workspace_id or "",
                "refresh_token": acc.refresh_token or "",
            },
            "extra": {},
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
    """按单账号创建接口上传并绑定分组（smewai 支持 group_ids）"""
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
                "gpt-5.4": "gpt-5.4"
            },
            "organization_id": acc.workspace_id or "",
            "refresh_token": acc.refresh_token or "",
        },
        "extra": {},
        "concurrency": concurrency,
        "priority": priority,
        "rate_multiplier": 1,
        "auto_pause_on_expired": True,
        "group_ids": group_ids,
        "confirm_mixed_channel_risk": True,
    }

    url = api_url.rstrip("/") + "/api/v1/admin/accounts"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }
    try:
        response = cffi_requests.post(
            url,
            json=payload,
            headers=headers,
            proxies=None,
            timeout=30,
            impersonate="chrome110",
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
    except Exception as e:
        logger.error(f"Sub2API 单账号分组上传异常: {e}")
        return False, str(e)


def _normalize_group_ids(group_ids: Optional[List[int]]) -> List[int]:
    out: List[int] = []
    for gid in group_ids or []:
        try:
            v = int(gid)
        except Exception:
            continue
        if v > 0 and v not in out:
            out.append(v)
    return out
