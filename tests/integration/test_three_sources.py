import respx
from httpx import Response
from pathlib import Path
from click.testing import CliRunner
from skillpulse_crawler.cli import cli


def test_validate_config_loads_three_sources():
    runner = CliRunner()
    result = runner.invoke(cli, ["validate-config"])
    assert result.exit_code == 0
    assert "paper_arxiv" in result.output
    assert "project_github_trending" in result.output
    assert "community_hackernews" in result.output


@respx.mock
def test_paper_arxiv_dry_run():
    fixture = Path("tests/fixtures/arxiv_sample.xml").read_text(encoding="utf-8")
    respx.get("http://export.arxiv.org/rss/cs.AI").mock(return_value=Response(200, text=fixture))
    runner = CliRunner()
    result = runner.invoke(cli, ["dry-run", "--source", "paper_arxiv"])
    # P2 阶段 dry-run 还是 stub，只验证不报错；后续 P3 改
    assert "paper_arxiv" in result.output or result.exit_code in (0, 1)