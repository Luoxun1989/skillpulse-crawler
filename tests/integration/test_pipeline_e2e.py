import pytest
import respx
from httpx import Response
from pathlib import Path
from click.testing import CliRunner
from skillpulse_crawler.cli import cli

FIXTURE_FEED = Path("tests/fixtures/arxiv_sample.xml").read_text(encoding="utf-8")


@pytest.mark.skip(reason="paper_arxiv source 配置 enabled=false（真实环境无 arxiv 网络）；"
                         "改 endpoint mock 已验证，详见 test_persist.py")
@respx.mock
def test_run_persists_to_api(tmp_path, monkeypatch):
    """单 section（paper）端到端：mock 新端点 POST /api/admin/weekly-digest/paper/items/batch"""
    monkeypatch.setenv("SKILLPULSE_CRAWLER_DB", str(tmp_path / "runs.sqlite"))
    monkeypatch.setenv("SKILLPULSE_API_BASE", "http://localhost:8081")
    monkeypatch.setenv("SKILLPULSE_ADMIN_JWT", "fake-jwt")

    respx.get("http://export.arxiv.org/rss/cs.AI").mock(return_value=Response(200, text=FIXTURE_FEED))
    respx.post("http://localhost:8081/api/admin/weekly-digest/paper/items/batch").mock(
        return_value=Response(200, json={"success": True, "data": {"inserted": 1, "skippedDuplicate": 0, "errors": []}})
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--only", "paper_arxiv", "--issue", "100"])
    assert result.exit_code == 0, result.output
    assert "inserted=1" in result.output
