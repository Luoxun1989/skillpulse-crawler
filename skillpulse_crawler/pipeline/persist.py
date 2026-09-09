import os
import httpx
from ..models import WeeklyDigestItem

API_BASE = os.environ.get("SKILLPULSE_API_BASE", "http://localhost:8081")
ADMIN_JWT = os.environ.get("SKILLPULSE_ADMIN_JWT", "")


def persist_batch(items: list, issue_number: int) -> dict:
    if not items:
        return {"inserted": 0, "skipped_duplicate": 0, "errors": []}
    body = {
        "issueNumber": issue_number,
        "items": [item.model_dump(mode="json", by_alias=True) for item in items],
    }
    headers = {
        "Authorization": f"Bearer {ADMIN_JWT}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30) as client:
        r = client.post(f"{API_BASE}/api/admin/weekly-digest/items",
                        json=body, headers=headers)
        r.raise_for_status()
        return r.json()["data"]