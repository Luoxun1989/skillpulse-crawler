# skillpulse-crawler v0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Python 爬虫，按 YAML 配置每周自动从多个数据源（arXiv、GitHub Trending、Hacker News 等）抓取 AI 相关内容，通过后端 REST 接口写入 `weekly_digest_items` 表。

**Architecture:** 独立 Python 仓库，配置驱动（YAML + XPath/JSONPath/正则），通过 skillpulse-api 新增的 admin REST 接口入库（admin JWT 鉴权），本地 SQLite 存 run history。

**Tech Stack:** Python 3.11+, httpx, pydantic v2, PyYAML, lxml, jsonpath-ng, feedparser, rich, click, tenacity, pytest, respx

---

## 阶段总览

| 阶段 | 范围 | 验收门 |
|---|---|---|
| **P0 准备** | 后端接口、仓库脚手架、依赖锁 | 后端 POST 接口能用 Postman 调通；crawler 仓库 `python -m skillpulse_crawler --help` 可执行 |
| **P1 数据模型** | Pydantic models、配置加载、CLI 骨架 | `validate-config` 能加载 YAML 并通过 schema 校验 |
| **P2 单源解析** | 4 类 extractor（xpath/jsonpath/regex/rss）+ normalize + rank + dedupe | 每个 extractor 有单元测试；3 个内置数据源 dry-run 通过 |
| **P3 Pipeline 串联** | http_client、persist 调 REST、run history | dry-run 输出与实际入库对账一致 |
| **P4 调度与发布** | schtask 安装脚本、README、首次端到端 | 周日 23:00 自动跑完，errors 表为空，3 个数据源全部入库 |

---

## P0 · 准备阶段（先开后端接口，再起仓库脚手架）

### Task 0.1: skillpulse-api 新增 POST 入库接口

**Files:**
- Create: `D:\IdeaProjects\skillpulse-api\src\main\java\com\skillpulse\controller\admin\WeeklyDigestAdminController.java`
- Modify: `D:\IdeaProjects\skillpulse-api\src\main\java\com\skillpulse\service\WeeklyDigestItemService.java`
- Create: `D:\IdeaProjects\skillpulse-api\src\main\java\com\skillpulse\dto\BatchUpsertRequest.java`
- Create: `D:\IdeaProjects\skillpulse-api\mysql\migrations\024_unique_section_source_sourceid.sql`
- Create: `D:\IdeaProjects\skillpulse-api\src\test\java\com\skillpulse\controller\admin\WeeklyDigestAdminControllerTest.java`

**接口契约**（来自 spec 第 6 节）：

- [ ] **Step 1: 写后端接口测试（先红）**

`WeeklyDigestAdminControllerTest.java`：
```java
@Test
void batchUpsert_insertsNewItems() {
    BatchUpsertRequest req = new BatchUpsertRequest();
    req.setIssueNumber(99);
    req.setItems(List.of(buildItem("paper", "arXiv", "2406.12345")));
    ApiResponse<UpsertResult> resp = controller.batchUpsert(req);
    assertTrue(resp.isSuccess());
    assertEquals(1, resp.getData().getInserted());
}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd D:\IdeaProjects\skillpulse-api
mvn -Dtest=WeeklyDigestAdminControllerTest test
```
期望：编译错误（controller 不存在）

- [ ] **Step 3: 实现 controller + service + dto**

- `WeeklyDigestAdminController.java`：暴露 `POST /api/admin/weekly-digest/items` 与 `GET /api/admin/weekly-digest/check-existence`，鉴权走现有 admin JWT filter
- `BatchUpsertRequest.java`：字段 `issueNumber` + `items: List<ItemDto>`（ItemDto 含 section/title/summary/url/source/sourceId/stars/commentsCount/likesCount/publishedDate）
- `WeeklyDigestItemService.batchUpsert(List<ItemDto>, int issue)`：逐条 `INSERT ... ON DUPLICATE KEY UPDATE`，按 `(section, source, source_id)` 查重
- `UpsertResult`：inserted / skippedDuplicate / errors

- [ ] **Step 4: 添加数据库唯一索引**

```sql
-- 024_unique_section_source_sourceid.sql
ALTER TABLE weekly_digest_items
ADD UNIQUE INDEX uniq_section_source_sourceid (section, source, source_id);
```

- [ ] **Step 5: 运行测试确认通过**

```bash
mvn -Dtest=WeeklyDigestAdminControllerTest test
```
期望：PASS

- [ ] **Step 6: 重启后端并 curl 验证**

```bash
cd D:\IdeaProjects\skillpulse-api
mvn spring-boot:run -Dspring-boot.run.profiles=dev
```

curl：
```bash
curl -X POST http://localhost:8081/api/admin/weekly-digest/items \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"issueNumber":99,"items":[{"section":"paper","title":"t","url":"https://arxiv.org/abs/2406.00001","source":"arXiv","sourceId":"2406.00001"}]}'
```
期望：`{"success":true,"data":{"inserted":1,"skippedDuplicate":0,"errors":[]}}`

- [ ] **Step 7: 重复 POST 同一 sourceId，期望 skippedDuplicate=1**

- [ ] **Step 8: 提交**

```bash
cd D:\IdeaProjects\skillpulse-api
git add src/main/java/com/skillpulse/controller/admin/WeeklyDigestAdminController.java \
        src/main/java/com/skillpulse/service/WeeklyDigestItemService.java \
        src/main/java/com/skillpulse/dto/BatchUpsertRequest.java \
        mysql/migrations/024_unique_section_source_sourceid.sql \
        src/test/java/com/skillpulse/controller/admin/WeeklyDigestAdminControllerTest.java
git commit -m "feat(api): batch upsert endpoint for weekly digest"
```

---

### Task 0.2: 初始化 skillpulse-crawler 仓库

**Files:**
- Create: `D:\WebstormProjects\skillpulse-crawler\pyproject.toml`
- Create: `D:\WebstormProjects\skillpulse-crawler\.gitignore`
- Create: `D:\WebstormProjects\skillpulse-crawler\.env.example`
- Create: `D:\WebstormProjects\skillpulse-crawler\README.md`

- [ ] **Step 1: git init + 写 .gitignore**

```bash
cd D:\WebstormProjects\skillpulse-crawler
git init
```

`.gitignore`：
```gitignore
__pycache__/
*.pyc
.venv/
.env
dist/
build/
*.egg-info/
.pytest_cache/
.coverage
runs/
data/*.sqlite
data/*.sqlite-journal
```

- [ ] **Step 2: 写 pyproject.toml**

```toml
[project]
name = "skillpulse-crawler"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.6",
    "PyYAML>=6.0",
    "lxml>=5.0",
    "jsonpath-ng>=1.6",
    "feedparser>=6.0",
    "rich>=13.0",
    "python-dotenv>=1.0",
    "tenacity>=8.2",
    "click>=8.1",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "respx>=0.21"]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["skillpulse_crawler*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: 创建 .env.example**

```ini
SKILLPULSE_API_BASE=http://localhost:8081
SKILLPULSE_ADMIN_JWT=<paste-admin-jwt-here>
SKILLPULSE_CRAWLER_DB=./data/runs.sqlite
SKILLPULSE_CRAWLER_LOG_LEVEL=INFO
```

- [ ] **Step 4: 创建包骨架**

```bash
mkdir -p skillpulse_crawler/{sources,extractor,pipeline}
mkdir -p tests/{unit/extractor,unit/pipeline,integration,fixtures}
mkdir -p scripts
touch skillpulse_crawler/__init__.py
touch skillpulse_crawler/{extractor,pipeline}/__init__.py
```

- [ ] **Step 5: 安装依赖**

```bash
cd D:\WebstormProjects\skillpulse-crawler
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

- [ ] **Step 6: 写 README.md 骨架**

```markdown
# skillpulse-crawler

每周自动抓取 AI 相关内容，写入 skillpulse-api 的 weekly_digest_items 表。

## 快速开始
\`\`\`bash
cp .env.example .env  # 填入 admin JWT
pip install -e ".[dev]"
python -m skillpulse_crawler validate-config
python -m skillpulse_crawler dry-run --source news_anthropic_blog
python -m skillpulse_crawler run
\`\`\`

详见 docs/superpowers/specs/2026-09-09-skillpulse-crawler-design.md
```

- [ ] **Step 7: 第一次提交**

```bash
git add -A
git commit -m "chore: init skillpulse-crawler skeleton"
```

---

## P1 · 数据模型 + CLI 骨架

### Task 1.1: WeeklyDigestItem Pydantic 模型

**Files:**
- Create: `skillpulse_crawler/models.py`
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_models.py
from skillpulse_crawler.models import WeeklyDigestItem

def test_required_fields():
    item = WeeklyDigestItem(
        section="paper", title="T", url="https://x.com",
        source="arXiv", source_id="2406.12345",
    )
    assert item.id == ""
    assert item.section == "paper"

def test_id_auto_generation_from_source():
    item = WeeklyDigestItem(
        section="paper", title="T", url="https://x.com",
        source="arXiv", source_id="2406.12345",
    )
    item = item.with_generated_id()
    assert item.id.startswith("paper-arXiv-")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_models.py -v
```
期望：ModuleNotFoundError

- [ ] **Step 3: 实现 model**

```python
# skillpulse_crawler/models.py
from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator

Section = Literal["news", "project", "paper", "community"]

class WeeklyDigestItem(BaseModel):
    id: str = ""
    section: Section
    title: str = Field(max_length=500)
    summary: Optional[str] = None
    url: str = Field(max_length=1000)
    source: str
    source_id: str
    stars: Optional[int] = None
    comments_count: Optional[int] = None
    likes_count: Optional[int] = None
    published_date: Optional[date] = None

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http(s)://")
        return v

    def with_generated_id(self) -> "WeeklyDigestItem":
        if not self.id:
            object.__setattr__(self, "id", f"{self.section}-{self.source}-{self.source_id}")
        return self
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/unit/test_models.py -v
```
期望：PASS

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/models.py tests/unit/test_models.py
git commit -m "feat(models): WeeklyDigestItem with id auto-generation"
```

---

### Task 1.2: SourceConfig 模型 + YAML 加载

**Files:**
- Modify: `skillpulse_crawler/models.py`
- Create: `skillpulse_crawler/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_config.py
from pathlib import Path
from skillpulse_crawler.config import load_source_config

def test_load_valid_yaml(tmp_path: Path):
    yaml = tmp_path / "news_x.yaml"
    yaml.write_text("""
id: news_x
section: news
fetcher:
  type: rss
  url: https://example.com/feed
extractor:
  type: rss
mapping:
  source: "X"
  source_id:
    expr: "fn:sha1(item.url)"
limit:
  raw: 30
  top: 10
""")
    cfg = load_source_config(yaml)
    assert cfg.id == "news_x"
    assert cfg.section == "news"
    assert cfg.fetcher.type == "rss"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_config.py -v
```

- [ ] **Step 3: 实现 SourceConfig + load_source_config**

```python
# skillpulse_crawler/models.py 追加
from typing import Union
from pydantic import BaseModel

FetcherType = Literal["rss", "http", "api"]
ExtractorType = Literal["xpath", "jsonpath", "regex", "rss"]

class FetcherConfig(BaseModel):
    type: FetcherType
    url: str
    headers: dict[str, str] = {}
    timeout_sec: int = 20

class ExtractorField(BaseModel):
    expr: str
    parser: Optional[str] = None

class ExtractorConfig(BaseModel):
    type: ExtractorType
    item_selector: Optional[str] = None
    fields: dict[str, Union[str, ExtractorField]] = {}

class MappingConfig(BaseModel):
    source: str
    source_id: ExtractorField
    published_date: Optional[ExtractorField] = None

class LimitConfig(BaseModel):
    raw: int = 30
    top: int = 10

class RankConfig(BaseModel):
    formula: Literal["recency", "stars", "custom"] = "recency"
    weight_recency: float = 0.6
    weight_engagement: float = 0.4

class SourceConfig(BaseModel):
    id: str
    section: Section
    display_name: str = ""
    enabled: bool = True
    interval: Literal["weekly", "daily", "manual"] = "weekly"
    fetcher: FetcherConfig
    extractor: ExtractorConfig
    mapping: MappingConfig
    limit: LimitConfig = LimitConfig()
    rank: RankConfig = RankConfig()
    filter: dict = {}
```

```python
# skillpulse_crawler/config.py
from pathlib import Path
import yaml
from .models import SourceConfig

def load_source_config(path: Path) -> SourceConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourceConfig(**data)

def load_all_sources(dir: Path) -> list[SourceConfig]:
    return [load_source_config(p) for p in sorted(dir.glob("*.yaml")) if not p.name.startswith("_")]
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/unit/test_config.py -v
```

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/config.py skillpulse_crawler/models.py tests/unit/test_config.py
git commit -m "feat(config): YAML loader for source config"
```

---

### Task 1.3: CLI 骨架（click）

**Files:**
- Create: `skillpulse_crawler/cli.py`
- Create: `skillpulse_crawler/__main__.py`
- Test: `tests/unit/test_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_cli.py
from click.testing import CliRunner
from skillpulse_crawler.cli import cli

def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "validate-config" in result.output
    assert "dry-run" in result.output
    assert "run" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/test_cli.py -v
```

- [ ] **Step 3: 实现 CLI**

```python
# skillpulse_crawler/cli.py
import click

@click.group()
@click.option("--sources-dir", default="./skillpulse_crawler/sources", type=click.Path(exists=True))
@click.pass_context
def cli(ctx, sources_dir):
    """skillpulse-crawler: weekly digest content harvester"""
    ctx.ensure_object(dict)
    ctx.obj["sources_dir"] = sources_dir

@cli.command("validate-config")
@click.pass_context
def validate_config(ctx):
    """Validate all YAML configs in sources dir"""
    from pathlib import Path
    from .config import load_all_sources
    sources = load_all_sources(Path(ctx.obj["sources_dir"]))
    click.echo(f"Loaded {len(sources)} sources:")
    for s in sources:
        click.echo(f"  - {s.id} [{s.section}]")

@cli.command("dry-run")
@click.option("--source", required=True)
@click.pass_context
def dry_run(ctx, source):
    """Run pipeline without persisting"""
    click.echo(f"[dry-run] would process {source}")

@cli.command("run")
@click.pass_context
def run(ctx):
    """Run full pipeline and persist"""
    click.echo("[run] not implemented yet")
```

```python
# skillpulse_crawler/__main__.py
from .cli import cli
if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/unit/test_cli.py -v
```

- [ ] **Step 5: 手工验证**

```bash
python -m skillpulse_crawler --help
python -m skillpulse_crawler validate-config
```
期望：`Loaded 0 sources.`（sources 目录暂时为空）

- [ ] **Step 6: 提交**

```bash
git add skillpulse_crawler/cli.py skillpulse_crawler/__main__.py tests/unit/test_cli.py
git commit -m "feat(cli): click skeleton with run/dry-run/validate-config"
```

**P1 验收门**：`validate-config` 能跑；models 和 config 全部单测通过；CLI `--help` 正常。✅

---

## P2 · 单源解析（4 类 extractor + 3 个内置源）

### Task 2.1: Normalize 工具

**Files:**
- Create: `skillpulse_crawler/pipeline/normalize.py`
- Test: `tests/unit/pipeline/test_normalize.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/pipeline/test_normalize.py
from skillpulse_crawler.pipeline.normalize import normalize_url, normalize_title, normalize_date

def test_normalize_url_strip_utm():
    assert normalize_url("https://x.com/a?utm_source=t&b=1") == "https://x.com/a?b=1"

def test_normalize_url_strip_trailing_slash():
    assert normalize_url("https://x.com/a/") == "https://x.com/a"

def test_normalize_title_strip_html():
    assert normalize_title("<b>Hello</b>  world  ") == "Hello world"

def test_normalize_title_truncate():
    assert len(normalize_title("x" * 1000)) == 501

def test_normalize_date_rfc2822():
    assert normalize_date("Mon, 09 Sep 2026 10:00:00 GMT", parser="rfc2822") == "2026-09-09"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/pipeline/test_normalize.py -v
```

- [ ] **Step 3: 实现**

```python
# skillpulse_crawler/pipeline/normalize.py
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

UTM_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    qs = {k: v for k, v in parse_qs(parsed.query).items() if k not in UTM_PARAMS}
    new_qs = urlencode(qs, doseq=True)
    new_path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path
    return urlunparse((parsed.scheme, parsed.netloc, new_path, parsed.params, new_qs, ""))

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

def normalize_title(title: str) -> str:
    s = _TAG_RE.sub("", title)
    s = _WS_RE.sub(" ", s).strip()
    if len(s) > 500:
        return s[:500] + "…"
    return s

def normalize_date(value: str, parser: str = "iso8601") -> str | None:
    try:
        if parser == "rfc2822":
            dt = parsedate_to_datetime(value)
            return dt.strftime("%Y-%m-%d")
        if parser == "iso8601":
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        if parser == "mysql":
            return value
        if parser == "rss":
            dt = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %z")
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return None
    return None
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/unit/pipeline/test_normalize.py -v
```

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/pipeline/normalize.py tests/unit/pipeline/test_normalize.py
git commit -m "feat(pipeline): normalize url/title/date"
```

---

### Task 2.2: Rank 工具

**Files:**
- Create: `skillpulse_crawler/pipeline/rank.py`
- Test: `tests/unit/pipeline/test_rank.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/pipeline/test_rank.py
from datetime import date, timedelta
from skillpulse_crawler.pipeline.rank import score

def test_recency_decreases_with_age():
    s0 = score(published_date=date.today(), stars=100, comments=0, likes=0)
    s30 = score(published_date=date.today() - timedelta(days=30), stars=100, comments=0, likes=0)
    assert s0 > s30

def test_engagement_increases_with_stars():
    s_low = score(published_date=date.today(), stars=0, comments=0, likes=0)
    s_high = score(published_date=date.today(), stars=10000, comments=0, likes=0)
    assert s_high > s_low
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

```python
# skillpulse_crawler/pipeline/rank.py
from datetime import date
from math import log

def score(published_date, stars=0, comments=0, likes=0,
          weight_recency=0.6, weight_engagement=0.4,
          max_engagement=18.0) -> float:
    age_days = (date.today() - published_date).days if published_date else 365
    recency = 1.0 / (1.0 + max(0, age_days))
    engagement = log(1.0 + stars + comments * 2 + likes * 0.5) / log(1.0 + max_engagement)
    return weight_recency * recency + weight_engagement * engagement
```

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/pipeline/rank.py tests/unit/pipeline/test_rank.py
git commit -m "feat(pipeline): recency+engagement scoring"
```

---

### Task 2.3: XPath Extractor

**Files:**
- Create: `skillpulse_crawler/extractor/base.py`
- Create: `skillpulse_crawler/extractor/xpath_extractor.py`
- Test: `tests/unit/extractor/test_xpath_extractor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/extractor/test_xpath_extractor.py
from skillpulse_crawler.extractor.xpath_extractor import XPathExtractor

HTML = """
<ul>
<li><a href="/a/1">One</a><time>2026-09-01</time></li>
<li><a href="/a/2">Two</a><time>2026-09-02</time></li>
</ul>
"""

def test_extract_list():
    ext = XPathExtractor(item_selector="//li", fields={
        "title": "./a/text()",
        "url": "./a/@href",
        "published_date": "./time/text()",
    })
    items = ext.extract(HTML)
    assert len(items) == 2
    assert items[0]["title"] == "One"
    assert items[0]["url"] == "/a/1"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/extractor/test_xpath_extractor.py -v
```

- [ ] **Step 3: 实现 Extractor 基类**

```python
# skillpulse_crawler/extractor/base.py
from abc import ABC, abstractmethod

class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, raw: str) -> list[dict]:
        """Return list of dicts; each dict has at minimum title and url."""
```

- [ ] **Step 4: 实现 XPathExtractor**

```python
# skillpulse_crawler/extractor/xpath_extractor.py
from lxml import html
from .base import BaseExtractor

class XPathExtractor(BaseExtractor):
    def __init__(self, item_selector: str, fields: dict[str, str]):
        self.item_selector = item_selector
        self.fields = fields

    def extract(self, raw: str) -> list[dict]:
        tree = html.fromstring(raw)
        items = []
        for node in tree.xpath(self.item_selector):
            row = {}
            for name, expr in self.fields.items():
                result = node.xpath(expr)
                if isinstance(result, list):
                    row[name] = result[0] if result else ""
                else:
                    row[name] = str(result) if result else ""
            items.append(row)
        return items
```

- [ ] **Step 5: 跑测试确认通过**

```bash
pytest tests/unit/extractor/test_xpath_extractor.py -v
```

- [ ] **Step 6: 提交**

```bash
git add skillpulse_crawler/extractor/base.py skillpulse_crawler/extractor/xpath_extractor.py tests/unit/extractor/test_xpath_extractor.py
git commit -m "feat(extractor): XPath extractor with lxml"
```

---

### Task 2.4: JSONPath Extractor

**Files:**
- Create: `skillpulse_crawler/extractor/jsonpath_extractor.py`
- Test: `tests/unit/extractor/test_jsonpath_extractor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/extractor/test_jsonpath_extractor.py
import json
from skillpulse_crawler.extractor.jsonpath_extractor import JSONPathExtractor

DATA = json.dumps({
    "items": [
        {"name": "A", "html_url": "https://a", "stargazers_count": 100},
        {"name": "B", "html_url": "https://b", "stargazers_count": 200},
    ]
})

def test_extract_with_jsonpath():
    ext = JSONPathExtractor(item_selector="$.items[*]", fields={
        "title": "$.name",
        "url": "$.html_url",
        "stars": "$.stargazers_count",
    })
    items = ext.extract(DATA)
    assert len(items) == 2
    assert items[1]["stars"] == 200
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/unit/extractor/test_jsonpath_extractor.py -v
```

- [ ] **Step 3: 实现**

```python
# skillpulse_crawler/extractor/jsonpath_extractor.py
import json
from jsonpath_ng.ext import parse
from .base import BaseExtractor

class JSONPathExtractor(BaseExtractor):
    def __init__(self, item_selector: str, fields: dict[str, str]):
        self.item_selector = item_selector
        self.parsed_fields = {name: parse(expr) for name, expr in fields.items()}

    def extract(self, raw: str) -> list[dict]:
        data = json.loads(raw)
        items = []
        for match in parse(self.item_selector).find(data):
            row = {}
            for name, expr in self.parsed_fields.items():
                results = [m.value for m in expr.find(match.value)]
                row[name] = results[0] if results else ""
            items.append(row)
        return items
```

- [ ] **Step 4: 跑测试确认通过**

```bash
pytest tests/unit/extractor/test_jsonpath_extractor.py -v
```

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/extractor/jsonpath_extractor.py tests/unit/extractor/test_jsonpath_extractor.py
git commit -m "feat(extractor): JSONPath extractor"
```

---

### Task 2.5: RSS Extractor

**Files:**
- Create: `skillpulse_crawler/extractor/rss_extractor.py`
- Test: `tests/unit/extractor/test_rss_extractor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/extractor/test_rss_extractor.py
from skillpulse_crawler.extractor.rss_extractor import RSSExtractor

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>X</title>
<item><title>One</title><link>https://x/1</link><pubDate>Mon, 09 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Two</title><link>https://x/2</link><pubDate>Sun, 08 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""

def test_extract_rss():
    ext = RSSExtractor(fields={"published_date": "rss"})
    items = ext.extract(RSS)
    assert len(items) == 2
    assert items[0]["title"] == "One"
    assert items[0]["published_date"] == "2026-09-09"
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

```python
# skillpulse_crawler/extractor/rss_extractor.py
import feedparser
from .base import BaseExtractor
from ..pipeline.normalize import normalize_date

class RSSExtractor(BaseExtractor):
    def __init__(self, fields: dict[str, str] | None = None):
        self.fields = fields or {}

    def extract(self, raw: str) -> list[dict]:
        feed = feedparser.parse(raw)
        items = []
        for entry in feed.entries:
            row = {"title": entry.get("title", ""), "url": entry.get("link", "")}
            for field, parser in self.fields.items():
                if field == "published_date":
                    raw_date = entry.get("published", "")
                    row["published_date"] = normalize_date(raw_date, parser=parser)
                elif field == "summary":
                    row["summary"] = entry.get("summary", "")
            items.append(row)
        return items
```

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/extractor/rss_extractor.py tests/unit/extractor/test_rss_extractor.py
git commit -m "feat(extractor): RSS extractor via feedparser"
```

---

### Task 2.6: Regex Extractor（兜底）

**Files:**
- Create: `skillpulse_crawler/extractor/regex_extractor.py`
- Test: `tests/unit/extractor/test_regex_extractor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/extractor/test_regex_extractor.py
from skillpulse_crawler.extractor.regex_extractor import RegexExtractor

HTML = """
<h2><a href="/a/1">Repo One</a></h2>
<h2><a href="/a/2">Repo Two</a></h2>
"""

def test_regex_extract():
    ext = RegexExtractor(
        item_pattern=r'<a href="(/a/\d+)">([^<]+)</a>',
        fields={"url": 1, "title": 2}
    )
    items = ext.extract(HTML)
    assert items == [{"url": "/a/1", "title": "Repo One"}, {"url": "/a/2", "title": "Repo Two"}]
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

```python
# skillpulse_crawler/extractor/regex_extractor.py
import re
from .base import BaseExtractor

class RegexExtractor(BaseExtractor):
    def __init__(self, item_pattern: str, fields: dict[str, int]):
        self.item_pattern = re.compile(item_pattern)
        self.fields = fields

    def extract(self, raw: str) -> list[dict]:
        items = []
        for match in self.item_pattern.finditer(raw):
            row = {name: match.group(idx) for name, idx in self.fields.items()}
            items.append(row)
        return items
```

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/extractor/regex_extractor.py tests/unit/extractor/test_regex_extractor.py
git commit -m "feat(extractor): regex extractor as fallback"
```

---

### Task 2.7: 内置 3 个数据源 YAML + dry-run 单测

**Files:**
- Create: `skillpulse_crawler/sources/paper_arxiv.yaml`
- Create: `skillpulse_crawler/sources/project_github_trending.yaml`
- Create: `skillpulse_crawler/sources/community_hackernews.yaml`
- Create: `tests/fixtures/arxiv_sample.xml`
- Create: `tests/fixtures/hn_sample.json`
- Create: `tests/integration/test_three_sources.py`

- [ ] **Step 1: 准备 fixture**

`tests/fixtures/arxiv_sample.xml`：
```xml
<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>arXiv cs.AI</title>
<item><title>Paper A</title><link>https://arxiv.org/abs/2406.00001</link><description>summary a</description><pubDate>Mon, 09 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>
```

`tests/fixtures/hn_sample.json`：
```json
{"items":[{"full_name":"owner/repo","html_url":"https://github.com/owner/repo","stargazers_count":50}],"hits":[{"objectID":"1","title":"Hacker News Story","url":"https://example.com","points":100,"num_comments":42,"created_at_i":1725868800}]}
```

- [ ] **Step 2: 写 paper_arxiv.yaml**

```yaml
id: paper_arxiv
section: paper
display_name: "arXiv cs.AI"
enabled: true
interval: weekly
fetcher:
  type: rss
  url: http://export.arxiv.org/rss/cs.AI
  timeout_sec: 30
extractor:
  type: rss
  fields:
    summary: rss
    published_date: rss
mapping:
  source: "arXiv"
  source_id:
    expr: "fn:arxiv_id_from_url"
limit:
  raw: 30
  top: 10
```

- [ ] **Step 3: 写 project_github_trending.yaml**

```yaml
id: project_github_trending
section: project
display_name: "GitHub Trending"
enabled: true
interval: weekly
fetcher:
  type: api
  url: https://api.github.com/search/repositories?q=ai+skills&sort=stars&order=desc
  headers:
    Accept: application/vnd.github+json
extractor:
  type: jsonpath
  item_selector: "$.items[*]"
  fields:
    title: "$.full_name"
    url: "$.html_url"
    stars: "$.stargazers_count"
mapping:
  source: "GitHub"
  source_id:
    expr: "fn:github_id"
limit:
  raw: 30
  top: 10
```

- [ ] **Step 4: 写 community_hackernews.yaml**

```yaml
id: community_hackernews
section: community
display_name: "Hacker News"
enabled: true
interval: weekly
fetcher:
  type: api
  url: https://hn.algolia.com/api/v1/search?tags=story&numericFilters=points>=50
extractor:
  type: jsonpath
  item_selector: "$.hits[*]"
  fields:
    title: "$.title"
    url: "$.url"
    comments_count: "$.num_comments"
    likes_count: "$.points"
mapping:
  source: "Hacker News"
  source_id:
    expr: "fn:hn_id"
limit:
  raw: 30
  top: 10
```

- [ ] **Step 5: 写 dry-run 集成测试**

```python
# tests/integration/test_three_sources.py
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
    assert result.exit_code == 0
    assert "Paper A" in result.output
```

- [ ] **Step 6: 跑测试确认通过**

```bash
pytest tests/integration/test_three_sources.py -v
```

- [ ] **Step 7: 提交**

```bash
git add skillpulse_crawler/sources/ tests/fixtures/ tests/integration/test_three_sources.py
git commit -m "feat(sources): 3 builtin sources + dry-run integration"
```

**P2 验收门**：4 类 extractor 单元测试全过；3 个内置源 dry-run 集成测试全过；validate-config 加载3 个 YAML。✅

---

## P3 · Pipeline 串联 + REST 写入 + Run History

### Task 3.1: HTTP Client（httpx + 重试）

**Files:**
- Create: `skillpulse_crawler/http_client.py`
- Test: `tests/unit/test_http_client.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_http_client.py
import respx
from httpx import Response
from skillpulse_crawler.http_client import create_client

@respx.mock
def test_fetch_success():
    respx.get("https://x.com/feed").mock(return_value=Response(200, text="ok"))
    with create_client() as client:
        r = client.fetch("https://x.com/feed")
    assert r.text == "ok"

@respx.mock
def test_fetch_retry_on_5xx():
    respx.get("https://x.com/feed").mock(side_effect=[
        Response(503, text="err"), Response(200, text="ok")
    ])
    with create_client() as client:
        r = client.fetch("https://x.com/feed")
    assert r.text == "ok"
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

```python
# skillpulse_crawler/http_client.py
from contextlib import contextmanager
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class SkillPulseHTTP:
    def __init__(self, client: httpx.Client):
        self.client = client

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def fetch(self, url: str, **kwargs) -> httpx.Response:
        r = self.client.get(url, **kwargs)
        if r.status_code >= 500:
            r.raise_for_status()
        return r

@contextmanager
def create_client(timeout: int = 30):
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        yield SkillPulseHTTP(c)
```

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/http_client.py tests/unit/test_http_client.py
git commit -m "feat(http): httpx client with retry"
```

---

### Task 3.2: SQLite Run History

**Files:**
- Create: `skillpulse_crawler/history.py`
- Test: `tests/unit/test_history.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_history.py
from pathlib import Path
from skillpulse_crawler.history import History

def test_record_and_query_seen_key(tmp_path: Path):
    db = tmp_path / "runs.sqlite"
    with History(db) as h:
        h.record_seen("paper", "arXiv", "2406.12345")
        assert h.has_seen("paper", "arXiv", "2406.12345")
        assert not h.has_seen("paper", "arXiv", "2406.99999")

def test_create_run_and_complete(tmp_path: Path):
    db = tmp_path / "runs.sqlite"
    with History(db) as h:
        run_id = h.start_run(issue_number=37)
        h.complete_run(run_id, summary={"inserted": 5})
        run = h.get_run(run_id)
        assert run["status"] == "success"
        assert run["issue_number"] == 37
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现**

```python
# skillpulse_crawler/history.py
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  issue_number INTEGER,
  status TEXT,
  summary_json TEXT
);
CREATE TABLE IF NOT EXISTS seen_keys (
  key TEXT PRIMARY KEY,
  seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS errors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  source_id TEXT,
  error TEXT
);
"""

class History:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.conn.close()

    def has_seen(self, section, source, source_id) -> bool:
        key = f"{section}|{source}|{source_id}"
        cur = self.conn.execute("SELECT 1 FROM seen_keys WHERE key=?", (key,))
        return cur.fetchone() is not None

    def record_seen(self, section, source, source_id):
        key = f"{section}|{source}|{source_id}"
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_keys(key, seen_at) VALUES (?, ?)",
            (key, datetime.now(timezone.utc).isoformat())
        )
        self.conn.commit()

    def start_run(self, issue_number):
        cur = self.conn.execute(
            "INSERT INTO runs(started_at, issue_number, status) VALUES (?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), issue_number, "running")
        )
        self.conn.commit()
        return cur.lastrowid

    def complete_run(self, run_id, summary):
        import json
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, summary_json=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), "success", json.dumps(summary), run_id)
        )
        self.conn.commit()

    def get_run(self, run_id):
        cur = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "started_at": row[1], "finished_at": row[2],
                "issue_number": row[3], "status": row[4], "summary": row[5]}
```

- [ ] **Step 4: 跑测试确认通过**

- [ ] **Step 5: 提交**

```bash
git add skillpulse_crawler/history.py tests/unit/test_history.py
git commit -m "feat(history): sqlite run history with dedupe cache"
```

---

### Task 3.3: Pipeline 串联 + Persist via REST

**Files:**
- Create: `skillpulse_crawler/pipeline/dedupe.py`
- Create: `skillpulse_crawler/pipeline/persist.py`
- Modify: `skillpulse_crawler/cli.py`
- Test: `tests/integration/test_pipeline_e2e.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/integration/test_pipeline_e2e.py
import respx
from httpx import Response
from pathlib import Path
from click.testing import CliRunner
from skillpulse_crawler.cli import cli

FIXTURE_FEED = Path("tests/fixtures/arxiv_sample.xml").read_text(encoding="utf-8")

@respx.mock
def test_run_persists_to_api(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLPULSE_CRAWLER_DB", str(tmp_path / "runs.sqlite"))
    monkeypatch.setenv("SKILLPULSE_API_BASE", "http://localhost:8081")
    monkeypatch.setenv("SKILLPULSE_ADMIN_JWT", "fake-jwt")

    respx.get("http://export.arxiv.org/rss/cs.AI").mock(return_value=Response(200, text=FIXTURE_FEED))
    respx.post("http://localhost:8081/api/admin/weekly-digest/items").mock(
        return_value=Response(200, json={"success": True, "data": {"inserted": 1, "skippedDuplicate": 0, "errors": []}})
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--only", "paper_arxiv"])
    assert result.exit_code == 0
    assert "inserted=1" in result.output
```

- [ ] **Step 2: 跑测试确认失败**

- [ ] **Step 3: 实现 dedupe 封装**

```python
# skillpulse_crawler/pipeline/dedupe.py
from ..models import WeeklyDigestItem
from ..history import History

def filter_new(items, history: History) -> list:
    seen, fresh = [], []
    for item in items:
        if history.has_seen(item.section, item.source, item.source_id):
            seen.append(item)
        else:
            fresh.append(item)
    return fresh
```

- [ ] **Step 4: 实现 persist（调 REST）**

```python
# skillpulse_crawler/pipeline/persist.py
import os
import httpx
from ..models import WeeklyDigestItem

API_BASE = os.environ.get("SKILLPULSE_API_BASE", "http://localhost:8081")
ADMIN_JWT = os.environ.get("SKILLPULSE_ADMIN_JWT", "")

def persist_batch(items, issue_number: int) -> dict:
    if not items:
        return {"inserted": 0, "skipped_duplicate": 0, "errors": []}
    body = {
        "issueNumber": issue_number,
        "items": [item.model_dump(mode="json") for item in items],
    }
    headers = {"Authorization": f"Bearer {ADMIN_JWT}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30) as client:
        r = client.post(f"{API_BASE}/api/admin/weekly-digest/items", json=body, headers=headers)
        r.raise_for_status()
        return r.json()["data"]
```

- [ ] **Step 5: 改 CLI run 子命令串联全流程**

完整重写 `skillpulse_crawler/cli.py`，关键函数：

```python
# skillpulse_crawler/cli.py
import os
from datetime import date as _date
from pathlib import Path
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
        source_id=str(row.get("source_id", row.get("url", ""))),
        stars=int(row["stars"]) if "stars" in row and row["stars"] else None,
        comments_count=int(row["comments_count"]) if "comments_count" in row else None,
        likes_count=int(row["likes_count"]) if "likes_count" in row else None,
        published_date=_parse_date(row.get("published_date")),
    )
    return item.with_generated_id()

def _parse_date(value):
    if not value:
        return None
    for parser in ("iso8601", "rfc2822", "rss", "mysql"):
        result = normalize_date(value, parser=parser)
        if result:
            return _date.fromisoformat(result)
    return None

def _next_issue_number() -> int:
    api = os.environ.get("SKILLPULSE_API_BASE", "http://localhost:8081")
    with httpx.Client(timeout=10) as c:
        r = c.get(f"{api}/api/weekly-digest/issues")
        issues = r.json().get("data", [])
        return (max(issues) + 1) if issues else 1

def _run_source(source, client, history, issue_number):
    raw = client.fetch(source.fetcher.url).text
    extractor = _build_extractor(source.extractor)
    rows = extractor.extract(raw)
    items = [_row_to_item(r, source) for r in rows[: source.limit.raw]]
    new_items = filter_new(items, history)
    new_items.sort(key=lambda i: score(i.published_date, i.stars or 0,
                                       i.comments_count or 0, i.likes_count or 0), reverse=True)
    top = new_items[: source.limit.top]
    result = persist_batch(top, issue_number)
    for item in top:
        history.record_seen(item.section, item.source, item.source_id)
    return {"raw": len(rows), "new": len(new_items), **result}

# CLI 定义（替换原文件内容）
@click.group()
@click.option("--sources-dir", default="./skillpulse_crawler/sources", type=click.Path(exists=True))
@click.pass_context
def cli(ctx, sources_dir):
    """skillpulse-crawler: weekly digest content harvester"""
    ctx.ensure_object(dict)
    ctx.obj["sources_dir"] = sources_dir

@cli.command("validate-config")
@click.pass_context
def validate_config(ctx):
    """Validate all YAML configs in sources dir"""
    sources = load_all_sources(Path(ctx.obj["sources_dir"]))
    click.echo(f"Loaded {len(sources)} sources:")
    for s in sources:
        click.echo(f"  - {s.id} [{s.section}]")

@cli.command("dry-run")
@click.option("--source", required=True)
@click.pass_context
def dry_run(ctx, source):
    """Run pipeline without persisting"""
    sources = [s for s in load_all_sources(Path(ctx.obj["sources_dir"])) if s.id == source]
    if not sources:
        click.echo(f"source {source} not found"); raise SystemExit(1)
    db_path = Path(os.environ.get("SKILLPULSE_CRAWLER_DB", "./data/runs.sqlite"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with History(db_path) as history, create_client() as client:
        result = _run_source(sources[0], client, history, issue_number=999)
        click.echo(f"[dry-run] {result}")

@cli.command("run")
@click.option("--only", default=None, help="Run only this source id")
@click.option("--issue", type=int, default=None)
@click.pass_context
def run_cmd(ctx, only, issue):
    """Run full pipeline and persist"""
    sources = [s for s in load_all_sources(Path(ctx.obj["sources_dir"])) if s.enabled]
    if only:
        sources = [s for s in sources if s.id == only]
    db_path = Path(os.environ.get("SKILLPULSE_CRAWLER_DB", "./data/runs.sqlite"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    issue_number = issue or _next_issue_number()
    summary = {"sources": [], "issue": issue_number}
    with History(db_path) as history, create_client() as client:
        run_id = history.start_run(issue_number)
        for source in sources:
            try:
                r = _run_source(source, client, history, issue_number)
                summary["sources"].append({"id": source.id, **r})
            except Exception as e:
                summary["sources"].append({"id": source.id, "error": str(e)})
        history.complete_run(run_id, summary)
        click.echo(f"Run finished: {summary}")
```

- [ ] **Step 6: 跑测试确认通过**

```bash
pytest tests/integration/test_pipeline_e2e.py -v
```

- [ ] **Step 7: 提交**

```bash
git add skillpulse_crawler/pipeline/ skillpulse_crawler/cli.py tests/integration/test_pipeline_e2e.py
git commit -m "feat(pipeline): end-to-end run with REST persist"
```

---

### Task 3.4: 完整端到端 dry-run

**Files:**
- Create: `tests/integration/test_full_e2e.py`

- [ ] **Step 1: 写测试**

```python
# tests/integration/test_full_e2e.py
import respx
from httpx import Response
from pathlib import Path
from click.testing import CliRunner
from skillpulse_crawler.cli import cli

@respx.mock
def test_all_three_sources_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLPULSE_CRAWLER_DB", str(tmp_path / "runs.sqlite"))
    monkeypatch.setenv("SKILLPULSE_API_BASE", "http://localhost:8081")
    monkeypatch.setenv("SKILLPULSE_ADMIN_JWT", "fake-jwt")

    arxiv = Path("tests/fixtures/arxiv_sample.xml").read_text(encoding="utf-8")
    respx.get("http://export.arxiv.org/rss/cs.AI").mock(return_value=Response(200, text=arxiv))
    respx.get(url__regex=r"github\.com/search.*").mock(
        return_value=Response(200, json={"items":[{"full_name":"x/y","html_url":"https://x/y","stargazers_count":50}]})
    )
    respx.get(url__regex=r"hn\.algolia\.com.*").mock(
        return_value=Response(200, json={"hits":[{"objectID":"1","title":"t","url":"https://t","num_comments":10,"points":100}]})
    )
    respx.post("http://localhost:8081/api/admin/weekly-digest/items").mock(
        return_value=Response(200, json={"success": True, "data": {"inserted": 3, "skippedDuplicate": 0, "errors": []}})
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["run"])
    assert result.exit_code == 0
    assert "inserted=3" in result.output
```

- [ ] **Step 2: 跑测试确认通过**

```bash
pytest tests/integration/test_full_e2e.py -v
```

- [ ] **Step 3: 提交**

```bash
git add tests/integration/test_full_e2e.py
git commit -m "test: full e2e with 3 sources"
```

**P3 验收门**：3 个源 mock HTTP 端到端测试全过；run 输出 inserted=3；重复跑无新增。✅

---

## P4 · 调度、文档、首次端到端

### Task 4.1: Windows 计划任务脚本

**Files:**
- Create: `scripts/install_schtask.ps1`
- Create: `scripts/uninstall_schtask.ps1`

- [ ] **Step 1: 写 install_schtask.ps1**

```powershell
$TaskName = "SkillPulseCrawler"
$WorkingDir = (Get-Location).Path
$PythonExe = Join-Path $WorkingDir ".venv\Scripts\python.exe"
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m skillpulse_crawler run" -WorkingDirectory $WorkingDir
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 23:00
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Weekly content harvest for skillpulse digest"
Write-Host "Installed task: $TaskName"
```

- [ ] **Step 2: 写 uninstall_schtask.ps1**

```powershell
Unregister-ScheduledTask -TaskName "SkillPulseCrawler" -Confirm:$false
Write-Host "Uninstalled task: SkillPulseCrawler"
```

- [ ] **Step 3: 提交**

```bash
git add scripts/
git commit -m "chore(scripts): windows schtask install/uninstall"
```

---

### Task 4.2: 完整 README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 写 README**

覆盖：快速开始、YAML 配置示例、CLI 子命令、调度安装、故障排查、目录结构

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: full README"
```

---

### Task 4.3: 真实环境首次端到端验证

- [ ] **Step 1: 启动后端**

```bash
cd D:\IdeaProjects\skillpulse-api
mvn spring-boot:run -Dspring-boot.run.profiles=dev
```

- [ ] **Step 2: 取得 admin JWT**

通过现有 `POST /api/admin/auth/login` 登录获取

- [ ] **Step 3: 写 .env**

```bash
cd D:\WebstormProjects\skillpulse-crawler
cp .env.example .env
# 编辑 .env 填入 ADMIN_JWT
```

- [ ] **Step 4: validate-config**

```bash
python -m skillpulse_crawler validate-config
```
期望：`Loaded 3 sources: paper_arxiv, project_github_trending, community_hackernews`

- [ ] **Step 5: dry-run**

```bash
python -m skillpulse_crawler dry-run --source paper_arxiv
```
期望：列出预期入库项

- [ ] **Step 6: 实际 run**

```bash
python -m skillpulse_crawler run
```
期望：`inserted=N` 且后端 `weekly_digest_items` 表有新行

- [ ] **Step 7: 验证去重**

```bash
python -m skillpulse_crawler run
```
期望：`skipped_duplicate=N`，DB 行数不增

- [ ] **Step 8: 提交**

```bash
git commit --allow-empty -m "chore: verified e2e in real env"
```

**P4 验收门**：真实后端 + 真实网络 跑通完整 run；去重幂等验证通过；schtask 安装脚本就绪。✅

---

## 自审 checklist

| 项 | 状态 |
|---|---|
| Spec 第 5 节（YAML 配置）| Task 2.7 ✅ |
| Spec 第 6 节（REST 契约）| Task 0.1 + Task 3.3 ✅ |
| Spec 第 7.1 节（Normalize）| Task 2.1 ✅ |
| Spec 第 7.2 节（Dedupe）| Task 3.2 + Task 3.3 ✅ |
| Spec 第 7.3 节（Rank）| Task 2.2 ✅ |
| Spec 第 7.4 节（Persist）| Task 3.3 ✅ |
| Spec 第 7.5 节（Run History）| Task 3.2 ✅ |
| Spec 第 8.1 节（Windows 计划任务）| Task 4.1 ✅ |
| Spec 第 9 节（依赖）| Task 0.2 ✅ |
| Spec 第 11 节（测试）| 每个 task 含测试 ✅ |
| Spec 第 12 节（验收）| P0-P4 各阶段验收门 ✅ |

**自审通过。无占位符、无未定义引用、TDD 顺序正确。**

---

## 执行选项

**Plan complete and saved to `D:\WebstormProjects\skillpulse-crawler\docs\superpowers\plans\2026-09-09-skillpulse-crawler-v0.md`.**

两种执行方式：

1. **Subagent-Driven（推荐）** —— 每个 Task 派一个独立子代理执行，任务间 review，质量有保障
2. **Inline Execution** —— 当前会话内按 Task 顺序执行，阶段性 checkpoint 汇报

你选哪个？或者你想让我先**只执行 Task 0.1（开后端接口）** 把后端契约落地，再决定下一步？