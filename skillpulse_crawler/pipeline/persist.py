import os
import uuid
from datetime import datetime
from collections import defaultdict
from typing import Iterable

import httpx

from ..models import WeeklyDigestItem

API_BASE = os.environ.get("SKILLPULSE_API_BASE", "http://localhost:8081")
ADMIN_JWT = os.environ.get("SKILLPULSE_ADMIN_JWT", "")


def _generate_batch_id() -> str:
    """一次 crawl run 一个 batch_id（spec 2026-09-21 §5.1）
    短随机串 16 字符，便于 SQL 索引与日志检索
    """
    return uuid.uuid4().hex[:16]


def persist_batch(items: Iterable[WeeklyDigestItem], issue_number: int) -> dict:
    """按 section 分组调新 4 端点（spec 2026-09-21 §7）

    POST /api/admin/weekly-digest/{section}/items/batch

    每条 item 自动填充：
      - fetchStatus='success'
      - fetchedAt=NOW()
      - batchId=本次 run 共享
    返回聚合结果：{inserted, skippedDuplicate, errors}
    """
    materialised = list(items)
    if not materialised:
        return {"inserted": 0, "skipped_duplicate": 0, "errors": []}

    batch_id = _generate_batch_id()
    fetched_at = datetime.utcnow()

    # 按 section 分组
    grouped: dict[str, list[WeeklyDigestItem]] = defaultdict(list)
    for item in materialised:
        grouped[item.section].append(item)

    headers = {
        "Authorization": f"Bearer {ADMIN_JWT}",
        "Content-Type": "application/json",
    }

    total_inserted = 0
    total_skipped = 0
    all_errors: list = []

    with httpx.Client(timeout=30) as client:
        for section, section_items in grouped.items():
            payload_items = []
            for item in section_items:
                dumped = item.model_dump(mode="json", by_alias=True, exclude_none=True)
                # 注入爬虫字段（spec 2026-09-21 §3.1）
                dumped["fetchStatus"] = "success"
                dumped["fetchedAt"] = fetched_at.isoformat()
                dumped["batchId"] = batch_id
                if item.raw_url is None:
                    dumped["rawUrl"] = item.url  # 退化：未抓取时 raw_url 等于 url
                payload_items.append(dumped)

            body = {"issueNumber": issue_number, "items": payload_items}
            url = f"{API_BASE}/api/admin/weekly-digest/{section}/items/batch"
            r = client.post(url, json=body, headers=headers)
            r.raise_for_status()
            resp = r.json()
            data = resp.get("data") or {}
            total_inserted += data.get("inserted", 0)
            total_skipped += data.get("skippedDuplicate", 0)
            all_errors.extend(data.get("errors", []))

    return {
        "inserted": total_inserted,
        "skipped_duplicate": total_skipped,
        "errors": all_errors,
        "batch_id": batch_id,
    }
