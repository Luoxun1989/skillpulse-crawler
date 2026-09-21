"""persist_batch 按 section 分组的测试

覆盖场景：
- 多个 section items 在一次调用中按 section 拆分成多个 POST 请求
- 每条 item 含爬虫字段 fetchStatus/fetchedAt/batchId
- 聚合返回 inserted/skipped/errors 跨 section 求和
- 空输入返回零值
"""
import respx
from httpx import Response

from skillpulse_crawler.models import WeeklyDigestItem
from skillpulse_crawler.pipeline.persist import persist_batch, API_BASE


def _item(section: str, source_id: str) -> WeeklyDigestItem:
    return WeeklyDigestItem(
        section=section,
        title=f"Test {section} {source_id}",
        url=f"https://example.com/{section}/{source_id}",
        source=f"{section}-source",
        source_id=source_id,
    )


@respx.mock
def test_persist_batch_groups_by_section(monkeypatch):
    monkeypatch.setenv("SKILLPULSE_API_BASE", API_BASE)
    monkeypatch.setenv("SKILLPULSE_ADMIN_JWT", "fake-jwt")

    paper_route = respx.post(f"{API_BASE}/api/admin/weekly-digest/paper/items/batch").mock(
        return_value=Response(200, json={"success": True, "data": {"inserted": 2, "skippedDuplicate": 0, "errors": []}})
    )
    news_route = respx.post(f"{API_BASE}/api/admin/weekly-digest/news/items/batch").mock(
        return_value=Response(200, json={"success": True, "data": {"inserted": 1, "skippedDuplicate": 1, "errors": []}})
    )
    community_route = respx.post(f"{API_BASE}/api/admin/weekly-digest/community/items/batch").mock(
        return_value=Response(200, json={"success": True, "data": {"inserted": 0, "skippedDuplicate": 1, "errors": ["warn-1"]}})
    )

    items = [
        _item("paper", "p1"),
        _item("paper", "p2"),
        _item("news", "n1"),
        _item("news", "n2"),  # skipped duplicate
        _item("community", "c1"),  # skipped duplicate
    ]
    result = persist_batch(items, issue_number=108)

    assert result["inserted"] == 3
    assert result["skipped_duplicate"] == 2
    assert result["errors"] == ["warn-1"]
    assert "batch_id" in result and len(result["batch_id"]) == 16

    # 每个 section 只被请求一次
    assert paper_route.call_count == 1
    assert news_route.call_count == 1
    assert community_route.call_count == 1

    # 验证请求体含爬虫字段
    paper_call = paper_route.calls.last.request
    import json
    body = json.loads(paper_call.content)
    assert body["issueNumber"] == 108
    assert len(body["items"]) == 2
    item0 = body["items"][0]
    assert item0["fetchStatus"] == "success"
    assert item0["fetchedAt"] is not None
    assert item0["batchId"] == result["batch_id"]
    assert item0["rawUrl"] == "https://example.com/paper/p1"


def test_persist_batch_empty_returns_zeros(monkeypatch):
    monkeypatch.setenv("SKILLPULSE_ADMIN_JWT", "fake-jwt")
    result = persist_batch([], issue_number=108)
    assert result == {"inserted": 0, "skipped_duplicate": 0, "errors": []}


def test_persist_batch_uses_url_as_raw_url_fallback(monkeypatch):
    """item 未指定 raw_url 时，回退用 url 填充（spec §5.1 raw_url 是抓取时的原始 URL）"""
    monkeypatch.setenv("SKILLPULSE_ADMIN_JWT", "fake-jwt")

    with respx.mock:
        route = respx.post(f"{API_BASE}/api/admin/weekly-digest/news/items/batch").mock(
            return_value=Response(200, json={"success": True, "data": {"inserted": 1, "skippedDuplicate": 0, "errors": []}})
        )
        result = persist_batch([_item("news", "n1")], issue_number=108)
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["items"][0]["rawUrl"] == "https://example.com/news/n1"
        assert result["inserted"] == 1
