"""回填脚本：对每个 enabled source 全量跑一次入库。

特点：
- 不依赖 history.py 本地去重（跳过 filter_new）
- 依赖后端 service 层 dedupe（SELECT 查 source/source_id）和 DB 唯一索引兜底
- 用于把"之前因 limit.top=10 被截断丢弃"的数据补入库
- 入库到今天的 issue（YYYYMMDD 数字）

用法：
    ADMIN_PASS=xxx .venv/Scripts/python -m scripts.replay_all
    # 或直接预取 JWT
    SKILLPULSE_ADMIN_JWT=xxx .venv/Scripts/python -m scripts.replay_all
"""
import os
import sys
import uuid
import httpx
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from skillpulse_crawler.config import load_all_sources
from skillpulse_crawler.cli import _build_extractor, _row_to_item, _today_date
from skillpulse_crawler.http_client import SkillPulseHTTP, PlaywrightHTTP
from skillpulse_crawler.models import WeeklyDigestItem
from skillpulse_crawler.auth import get_admin_jwt, API_BASE

ISSUE_TODAY = int(datetime.now().strftime("%Y%m%d"))


def fetch_raw(source):
    """取 source 原始 HTML/JSON（支持多页）"""
    pages = getattr(source.fetcher, "pages", None) or 1
    all_rows = []
    for p in range(1, pages + 1):
        url = source.fetcher.url
        if pages > 1 or "{page}" in url:
            kwargs = {"page": p}
            ps = getattr(source.fetcher, "page_size", None)
            if ps:
                kwargs["page_size"] = ps
            url = url.format(**kwargs)
        if source.fetcher.type == "playwright":
            wrapper = PlaywrightHTTP()
            raw = wrapper.fetch(url, headers=source.fetcher.headers).text
        else:
            verify_ssl = getattr(source.fetcher, "verify_ssl", True)
            with httpx.Client(timeout=30, follow_redirects=True, verify=not verify_ssl) as client:
                wrapper = SkillPulseHTTP(client)
                raw = wrapper.fetch(url, headers=source.fetcher.headers,
                                    verify_ssl=verify_ssl).text
        extractor = _build_extractor(source.extractor)
        all_rows.extend(extractor.extract(raw))
    return all_rows


def item_to_dto(item: WeeklyDigestItem, batch_id: str, fetched_at: str):
    """WeeklyDigestItem → 后端 batchUpsert 接受的 DTO dict"""
    d = item.model_dump(mode="json", by_alias=True, exclude_none=True)
    d["fetchStatus"] = "success"
    d["fetchedAt"] = fetched_at
    d["batchId"] = batch_id
    if "rawUrl" not in d:
        d["rawUrl"] = item.url
    return d


def post_batch(section: str, items: list, issue_number: int):
    """调 admin batch 入库（按 section 一次提交）"""
    if not items:
        return {"inserted": 0, "skippedDuplicate": 0, "errors": []}
    url = f"{API_BASE}/api/admin/weekly-digest/{section}/items/batch"
    headers = {
        "Authorization": f"Bearer {get_admin_jwt()}",
        "Content-Type": "application/json",
    }
    body = {"issueNumber": issue_number, "items": items}
    with httpx.Client(timeout=60) as c:
        r = c.post(url, json=body, headers=headers)
        r.raise_for_status()
        return r.json().get("data") or {}


def main():
    # admin JWT 在第一次 post_batch 时按需自动申请（auth.get_admin_jwt）
    sources_dir = ROOT / "skillpulse_crawler" / "sources"
    sources = [s for s in load_all_sources(sources_dir) if s.enabled]
    print(f"[replay] {len(sources)} enabled sources, issue={ISSUE_TODAY} ({_today_date()})")
    print(f"[replay] API_BASE={API_BASE}")

    grand_inserted = 0
    grand_skipped = 0
    for source in sources:
        print(f"\n=== {source.id} (section={source.section}) ===")
        try:
            rows = fetch_raw(source)
        except Exception as e:
            print(f"  ERROR fetch: {e}")
            continue
        print(f"  raw rows: {len(rows)}")

        # 跳过空 title 脏数据
        items = []
        for r in rows[: source.limit.raw]:
            try:
                item = _row_to_item(r, source)
            except Exception as e:
                continue
            if not item.title or not item.title.strip():
                continue
            items.append(item)
        print(f"  valid items (non-empty title): {len(items)}")

        if not items:
            continue

        batch_id = uuid.uuid4().hex[:16]
        fetched_at = datetime.utcnow().isoformat()
        dto_list = [item_to_dto(i, batch_id, fetched_at) for i in items]

        try:
            res = post_batch(source.section, dto_list, ISSUE_TODAY)
            inserted = res.get("inserted", 0)
            skipped = res.get("skippedDuplicate", 0)
            errors = res.get("errors", [])
            print(f"  inserted={inserted}  skipped={skipped}  errors={len(errors)}")
            if errors:
                print(f"  first errors: {errors[:3]}")
            grand_inserted += inserted
            grand_skipped += skipped
        except httpx.HTTPStatusError as e:
            print(f"  ERROR post: HTTP {e.response.status_code}: {e.response.text[:200]}")

    print(f"\n[replay] DONE: total_inserted={grand_inserted}  total_skipped={grand_skipped}")
    print(f"[replay] (skipped = 已入库，dedupe 工作正常)")


if __name__ == "__main__":
    main()
