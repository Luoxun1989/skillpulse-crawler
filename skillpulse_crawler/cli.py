import os
from pathlib import Path

# 加载仓库根的 .env（如果存在）
try:
    from dotenv import load_dotenv
    _ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

from datetime import date as _date, datetime
import hashlib
import click
import httpx

from .models import WeeklyDigestItem
from .config import load_all_sources
from .pipeline.normalize import normalize_url, normalize_title, normalize_date
from .pipeline.dedupe import filter_new
from .pipeline.rank import score
from .pipeline.persist import persist_batch
from .history import History
from .http_client import SkillPulseHTTP, PlaywrightHTTP
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


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def _row_to_item(row, source):
    url = row.get("url") or ""
    if source.mapping.url_template and url:
        url = source.mapping.url_template.format(**row)
    # url_template 拼接后清理前导 @（skillhub namespace 带 @）
    if url.startswith("https://www.skillhub.cn/skills/@"):
        url = "https://www.skillhub.cn/skills/" + url[len("https://www.skillhub.cn/skills/@"):]
    raw_source_id = str(row.get("source_id") or row.get("url", ""))
    # 微信长 URL 等超过 DB 列宽度的 source_id，截断为 md5 前 16 字符
    # 保证自然键唯一性 + 长度稳定；url 列保留完整可点击
    source_id = _shorten_source_id(raw_source_id)
    item = WeeklyDigestItem(
        section=source.section,
        title=normalize_title(str(row.get("title", ""))),
        summary=row.get("summary"),
        url=normalize_url(str(url)),
        source=source.mapping.source,
        source_id=source_id,
        stars=_safe_int(row.get("stars")),
        comments_count=_safe_int(row.get("comments_count")),
        likes_count=_safe_int(row.get("likes_count")),
        published_date=_parse_date(row.get("published_date")),
    )
    return item.with_generated_id()


# source_id 安全阈值：DB 列 VARCHAR(255)，utf8mb4 最坏 4 字节/字符；
# 微信文章 URL 实测 100~300 字符，留余量取 200
SOURCE_ID_MAX_LEN = 200


def _shorten_source_id(raw: str) -> str:
    """source_id 超过阈值时用 md5 前 16 字符替代，URL 完整信息不丢。"""
    if not raw:
        return ""
    if len(raw) <= SOURCE_ID_MAX_LEN:
        return raw
    return "h_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _parse_date(value):
    if not value:
        return None
    for parser in ("iso8601", "rfc2822", "rss", "mysql"):
        result = normalize_date(str(value), parser=parser)
        if result:
            return _date.fromisoformat(result)
    return None


def _next_issue_date() -> int:
    """返回今天 YYYYMMDD 数字（如 20260923）。后端 issueNumber 字段类型 INT。"""
    return int(datetime.now().strftime("%Y%m%d"))


def _today_date() -> str:
    """返回今天 YYYY-MM-DD 字符串，用于 --issue 默认值显示。"""
    return datetime.now().strftime("%Y-%m-%d")


def _run_source(source, client, history, issue_number, persist: bool = True):
    extractor = _build_extractor(source.extractor)
    all_rows = []
    pages = getattr(source.fetcher, "pages", None) or 1
    for p in range(1, pages + 1):
        url = source.fetcher.url
        if pages > 1 or "{page}" in url:
            kwargs = {"page": p}
            ps = getattr(source.fetcher, "page_size", None)
            if ps:
                kwargs["page_size"] = ps
            url = url.format(**kwargs)
        if source.fetcher.type == "playwright":
            raw = client.fetch(url, headers=source.fetcher.headers).text
        else:
            verify_ssl = getattr(source.fetcher, "verify_ssl", True)
            raw = client.fetch(url, headers=source.fetcher.headers,
                               verify_ssl=verify_ssl).text
        all_rows.extend(extractor.extract(raw))
    rows = all_rows[: source.limit.raw]
    all_items = [_row_to_item(r, source) for r in rows]
    # 丢弃 title 为空的脏数据，避免入库后前端显示空白
    titled = [i for i in all_items if i.title and i.title.strip()]
    dropped = len(all_items) - len(titled)
    new_items = filter_new(titled, history)
    new_items.sort(
        key=lambda i: score(i.published_date, i.stars or 0,
                            i.comments_count or 0, i.likes_count or 0),
        reverse=True,
    )
    # top=0 表示不限量，全部入库；top>0 保留旧截断兼容
    if source.limit.top and source.limit.top > 0:
        top = new_items[: source.limit.top]
    else:
        top = new_items
    if not persist:
        for item in top:
            history.record_seen(item.section, item.source, item.source_id)
        return {"raw": len(rows), "new": len(new_items),
                "pages": pages,
                "dropped_empty_title": dropped,
                "inserted": 0, "skipped": 0, "errors": []}
    result = persist_batch(top, issue_number)
    for item in top:
        history.record_seen(item.section, item.source, item.source_id)
    return {"raw": len(rows), "new": len(new_items),
            "pages": pages,
            "dropped_empty_title": dropped,
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
    with History(db_path) as history:
        inner_client = None
        try:
            if src.fetcher.type == "playwright":
                wrapper = PlaywrightHTTP()
            else:
                inner_client = httpx.Client(timeout=30, follow_redirects=True)
                wrapper = SkillPulseHTTP(inner_client)
            result = _run_source(src, wrapper, history, issue_number=999, persist=False)
            click.echo(f"[dry-run] {src.id}: raw={result['raw']} new={result['new']}")
        finally:
            if inner_client is not None:
                inner_client.close()


@cli.command("run")
@click.option("--only", default=None, help="Run only this source id")
@click.option("--issue", type=int, default=None, help="采集期号（YYYYMMDD 数字），默认今天")
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
    issue_number = issue or _next_issue_date()
    y, m, d = issue_number // 10000, (issue_number // 100) % 100, issue_number % 100
    click.echo(f"[crawler] issue = {issue_number} ({y:04d}-{m:02d}-{d:02d})")

    summary = {"issue": issue_number, "sources": []}
    with History(db_path) as history:
        run_id = history.start_run(issue_number)
        for source in sources:
            wrapper = None
            inner_client = None
            try:
                if source.fetcher.type == "playwright":
                    wrapper = PlaywrightHTTP()
                else:
                    inner_client = httpx.Client(timeout=30, follow_redirects=True)
                    wrapper = SkillPulseHTTP(inner_client)
                r = _run_source(source, wrapper, history, issue_number)
                summary["sources"].append({"id": source.id, **r})
                click.echo(f"  {source.id}: raw={r['raw']} new={r['new']} "
                       f"inserted={r['inserted']} skipped={r['skipped']}")
            except Exception as e:
                summary["sources"].append({"id": source.id, "error": str(e)})
                click.echo(f"  {source.id}: ERROR {e}", err=True)
            finally:
                if inner_client is not None:
                    inner_client.close()
        history.complete_run(run_id, summary)
        click.echo(f"Run finished: issue={issue_number}, sources={len(sources)}")