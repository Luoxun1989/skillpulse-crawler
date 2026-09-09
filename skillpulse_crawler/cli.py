import os
from pathlib import Path

# 加载仓库根的 .env（如果存在）
try:
    from dotenv import load_dotenv
    _ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from datetime import date as _date
import click
import httpx

from .models import WeeklyDigestItem
from .config import load_all_sources
from .pipeline.normalize import normalize_url, normalize_title, normalize_date
from .pipeline.dedupe import filter_new
from .pipeline.rank import score
from .pipeline.persist import persist_batch
from .history import History
from .http_client import create_client
from .extractor.xpath_extractor import XPathExtractor
from .extractor.jsonpath_extractor import JSONPathExtractor
from .extractor.regex_extractor import RegexExtractor
from .extractor.rss_extractor import RSSExtractor

EXTRACTORS = {
    "xpath": XPathExtractor,
    "jsonpath": JSONPathExtractor,
    "regex": RegexExtractor,
    "rss": RSSExtractor,
}


def _build_extractor(cfg):
    cls = EXTRACTORS[cfg.type]
    if cfg.type in ("xpath", "jsonpath"):
        return cls(item_selector=cfg.item_selector, fields=cfg.fields)
    if cfg.type == "regex":
        return cls(item_pattern=cfg.fields["_pattern"], fields=cfg.fields)
    if cfg.type == "rss":
        return cls(fields=cfg.fields)


def _row_to_item(row, source):
    item = WeeklyDigestItem(
        section=source.section,
        title=normalize_title(str(row.get("title", ""))),
        summary=row.get("summary"),
        url=normalize_url(str(row.get("url", ""))),
        source=source.mapping.source,
        source_id=str(row.get("source_id") or row.get("url", "")),
        stars=int(row["stars"]) if "stars" in row and row["stars"] not in ("", None) else None,
        comments_count=int(row["comments_count"]) if "comments_count" in row and row["comments_count"] not in ("", None) else None,
        likes_count=int(row["likes_count"]) if "likes_count" in row and row["likes_count"] not in ("", None) else None,
        published_date=_parse_date(row.get("published_date")),
    )
    return item.with_generated_id()


def _parse_date(value):
    if not value:
        return None
    for parser in ("iso8601", "rfc2822", "rss", "mysql"):
        result = normalize_date(str(value), parser=parser)
        if result:
            return _date.fromisoformat(result)
    return None


def _next_issue_number() -> int:
    api = os.environ.get("SKILLPULSE_API_BASE", "http://localhost:8081")
    with httpx.Client(timeout=10) as c:
        r = c.get(f"{api}/api/weekly-digest/issues")
        issues = r.json().get("data", []) or []
        return (max(issues) + 1) if issues else 1


def _run_source(source, client, history, issue_number, persist: bool = True):
    raw = client.fetch(source.fetcher.url, headers=source.fetcher.headers).text
    extractor = _build_extractor(source.extractor)
    rows = extractor.extract(raw)
    items = [_row_to_item(r, source) for r in rows[: source.limit.raw]]
    new_items = filter_new(items, history)
    new_items.sort(
        key=lambda i: score(i.published_date, i.stars or 0,
                            i.comments_count or 0, i.likes_count or 0),
        reverse=True,
    )
    top = new_items[: source.limit.top]
    if not persist:
        for item in top:
            history.record_seen(item.section, item.source, item.source_id)
        return {"raw": len(rows), "new": len(new_items),
                "inserted": 0, "skipped": 0, "errors": []}
    result = persist_batch(top, issue_number)
    for item in top:
        history.record_seen(item.section, item.source, item.source_id)
    return {"raw": len(rows), "new": len(new_items),
            "inserted": result.get("inserted", 0),
            "skipped": result.get("skippedDuplicate", 0),
            "errors": result.get("errors", [])}


@click.group()
@click.option("--sources-dir", default="./skillpulse_crawler/sources", type=click.Path(exists=False))
@click.pass_context
def cli(ctx, sources_dir):
    """skillpulse-crawler: weekly digest content harvester"""
    ctx.ensure_object(dict)
    ctx.obj["sources_dir"] = sources_dir


@cli.command("validate-config")
@click.pass_context
def validate_config(ctx):
    """Validate all YAML configs in sources dir"""
    sources_dir = Path(ctx.obj["sources_dir"])
    if not sources_dir.exists():
        click.echo(f"sources dir not found: {sources_dir}")
        raise SystemExit(1)
    sources = load_all_sources(sources_dir)
    click.echo(f"Loaded {len(sources)} sources:")
    for s in sources:
        click.echo(f"  - {s.id} [{s.section}]")


@cli.command("dry-run")
@click.option("--source", required=True)
@click.pass_context
def dry_run(ctx, source):
    """Run pipeline without persisting to REST"""
    from .config import load_source_config
    sources_dir = Path(ctx.obj["sources_dir"])
    yaml_path = sources_dir / f"{source}.yaml"
    if not yaml_path.exists():
        click.echo(f"source {source} not found at {yaml_path}")
        raise SystemExit(1)
    src = load_source_config(yaml_path)
    db_path = Path(os.environ.get("SKILLPULSE_CRAWLER_DB", "./data/runs.sqlite"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with History(db_path) as history, create_client() as client:
        result = _run_source(src, client, history, issue_number=999, persist=False)
        # dry-run 不调 REST，仅打印本地 pipeline 结果
        click.echo(f"[dry-run] {src.id}: raw={result['raw']} new={result['new']}")


@cli.command("run")
@click.option("--only", default=None, help="Run only this source id")
@click.option("--issue", type=int, default=None)
@click.pass_context
def run_cmd(ctx, only, issue):
    """Run full pipeline and persist"""
    sources_dir = Path(ctx.obj["sources_dir"])
    if not sources_dir.exists():
        click.echo(f"sources dir not found: {sources_dir}")
        raise SystemExit(1)
    sources = [s for s in load_all_sources(sources_dir) if s.enabled]
    if only:
        sources = [s for s in sources if s.id == only]
        if not sources:
            click.echo(f"--only {only} not found in enabled sources")
            raise SystemExit(1)

    db_path = Path(os.environ.get("SKILLPULSE_CRAWLER_DB", "./data/runs.sqlite"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    issue_number = issue or _next_issue_number()

    summary = {"issue": issue_number, "sources": []}
    with History(db_path) as history, create_client() as client:
        run_id = history.start_run(issue_number)
        for source in sources:
            try:
                r = _run_source(source, client, history, issue_number)
                summary["sources"].append({"id": source.id, **r})
                click.echo(f"  {source.id}: raw={r['raw']} new={r['new']} "
                           f"inserted={r['inserted']} skipped={r['skipped']}")
            except Exception as e:
                summary["sources"].append({"id": source.id, "error": str(e)})
                click.echo(f"  {source.id}: ERROR {e}", err=True)
        history.complete_run(run_id, summary)
        click.echo(f"Run finished: issue={issue_number}, sources={len(sources)}")