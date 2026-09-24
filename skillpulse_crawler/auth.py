"""admin JWT 解析。

优先顺序：
1. 环境变量 SKILLPULSE_ADMIN_JWT（手动预取，调试用）
2. 环境变量 ADMIN_USER + ADMIN_PASS → 调 /api/admin/login 自动获取（生产推荐）

所有调后端的脚本都用本模块，避免在每个调用点重复实现。
lru_cache 复用同一 token：login 一次复用 24h，避免每请求都 login 增加延迟。
"""
import os
import httpx
from functools import lru_cache

API_BASE = os.environ.get("SKILLPULSE_API_BASE", "http://localhost:8081")
_ADMIN_USER = os.environ.get("ADMIN_USER") or os.environ.get("SKILLPULSE_ADMIN_USER", "")
_ADMIN_PASS = os.environ.get("ADMIN_PASS") or os.environ.get("SKILLPULSE_ADMIN_PASS", "")
_MANUAL_JWT = os.environ.get("SKILLPULSE_ADMIN_JWT", "")


@lru_cache(maxsize=1)
def get_admin_jwt() -> str:
    """获取 admin JWT。手工注入的优先；否则自动 login。"""
    if _MANUAL_JWT:
        return _MANUAL_JWT
    if not _ADMIN_USER or not _ADMIN_PASS:
        raise RuntimeError(
            "需要 ADMIN_USER + ADMIN_PASS（推荐）或 SKILLPULSE_ADMIN_JWT"
        )
    r = httpx.post(
        f"{API_BASE}/api/admin/login",
        json={"username": _ADMIN_USER, "password": _ADMIN_PASS},
        timeout=10,
    )
    r.raise_for_status()
    token = r.json().get("data", {}).get("token")
    if not token:
        raise RuntimeError(f"login failed: {r.text[:200]}")
    return token


def auth_headers() -> dict:
    """请求头里带 Bearer token。"""
    return {
        "Authorization": f"Bearer {get_admin_jwt()}",
        "Content-Type": "application/json",
    }
