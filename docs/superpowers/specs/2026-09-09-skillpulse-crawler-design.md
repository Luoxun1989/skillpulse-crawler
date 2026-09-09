# skillpulse-crawler 设计文档

> 状态：**Draft · 待评审**
> 日期：2026-09-09
> 关联项目：skillpulse-api（D:\IdeaProjects\skillpulse-api）、skillpulse-chestnut（前端展示）

## 1. 背景与目标

skillpulse 主页"一周精选"目前 4 个栏目（`news` / `project` / `paper` / `community`）的内容需要人工挑选。我们需要构建一个自动采集程序，每周灌入下一期内容，目标如下：

1. **零代码扩展**：增加新数据源只需新增一份 YAML
2. **数据契约清晰**：写入经由后端 REST 接口，crawler 不直接连 MySQL
3. **可重入、可观测**：失败后重跑不污染，可随时查看历史

非目标（Out of Scope）：

- 不做内容审核（crawler 默认 `is_active=1`，若需审稿流程由后端 admin 手动操作）
- 不做用户订阅推送
- 不做全文抓取入库，仅保留 metadata（标题/摘要/外链/热度）

## 2. 关键决策（来自 brainstorm 阶段）

| # | 决策点 | 选择 |
|---|---|---|
| 1 | 写入路径 | 后端加 REST POST（admin JWT），crawler HTTP |
| 2 | 解析方式 | YAML + XPath/JSONPath/正则 |
| 3 | 浏览器 | v0 不装 Playwright |
| 4 | 运行环境 | 独立 Python 进程 + Windows 计划任务 |
| 5 | 去重粒度 | 全表唯一（同 source_id） |
| 6 | 采集上限 | 每源 30 粗筛→ top 10 入库 |
| 7 | 失败处理 | 本地 SQLite 存 run history |

## 3. 整体架构

```
┌──────────────────────────┐         POST /api/admin/weekly-digest/items
│  skillpulse-crawler      │  ──────────────────────────────────────────►  ┌──────────────────────────┐
│  (Python, 独立仓库)      │         admin JWT                             │  skillpulse-api           │
│                          │                                                │  (Spring Boot 8081)       │
│  ┌──────────────────┐    │                                                │                          │
│  │ Scheduler        │    │                                                │  weekly_digest_items     │
│  │ (Windows 计划任务)│    │                                                │  (MySQL)                 │
│  └──────────────────┘    │                                                └──────────────────────────┘
│           │              │
│           ▼              │
│  ┌──────────────────┐    │         ┌─────────────────┐
│  │ Source Loader    │ ───│───YAML──►│ Extractor       │
│  │ sources/*.yaml   │    │         │ - XPath/JSONPath│
│  └──────────────────┘    │         │ - 正则/RSS      │
│           │              │         └─────────────────┘
│           ▼              │
│  ┌──────────────────┐    │
│  │ Pipeline         │    │         ┌─────────────────┐
│  │ - normalize      │ ───┼──HTTP──►│ HTTP Client     │
│  │ - dedupe         │    │         │ (httpx)         │
│  │ - rank           │    │         └─────────────────┘
│  │ - persist        │    │
│  └──────────────────┘    │
│           │              │
│           ▼              │
│  ┌──────────────────┐    │
│  │ Run History      │    │
│  │ (SQLite 本地)    │    │
│  └──────────────────┘    │
└──────────────────────────┘
```

## 4. 目录结构

```
skillpulse-crawler/
├── pyproject.toml
├── README.md
├── .env.example
├── skillpulse_crawler/
│   ├── __init__.py
│   ├── __main__.py            # python -m skillpulse_crawler
│   ├── cli.py                 # run / dry-run / validate-config
│   ├── config.py              # 环境变量 + YAML 加载
│   ├── models.py              # Pydantic 模型
│   ├── sources/
│   │   ├── paper_arxiv.yaml
│   │   ├── paper_openalex.yaml
│   │   ├── project_github_trending.yaml
│   │   ├── news_anthropic_blog.yaml
│   │   ├── community_hackernews.yaml
│   │   └── ...
│   ├── extractor/
│   │   ├── base.py
│   │   ├── xpath_extractor.py    # lxml
│   │   ├── jsonpath_extractor.py # jsonpath-ng
│   │   ├── regex_extractor.py
│   │   └── rss_extractor.py      # feedparser
│   ├── pipeline/
│   │   ├── normalize.py
│   │   ├── dedupe.py
│   │   ├── rank.py
│   │   └── persist.py            # 调 REST API
│   ├── http_client.py            # httpx + 限速
│   ├── scheduler.py              # 内部 cron（可选，仅 dry-run 用）
│   ├── history.py                # SQLite
│   └── logging.py                # 结构化日志
├── tests/
│   ├── unit/
│   └── integration/
└── docs/
    ├── source-format.md         # YAML 配置规范
    └── api-contract.md          # 后端 REST 契约
```

## 5. 数据契约：YAML 配置

完整规范见 `docs/source-format.md`，本节给核心示例。

```yaml
# sources/news_anthropic_blog.yaml
id: news_anthropic_blog
section: news
display_name: "Anthropic Blog"
enabled: true
interval: weekly

fetcher:
  type: rss
  url: https://www.anthropic.com/feed.xml
  timeout_sec: 20

extractor:
  type: rss
  # 也可写 type: xpath + item_selector + fields
  fields:
    title: "./title/text()"
    url: "./link/text()"
    summary: "./description/text()"
    published_date: "./pubDate/text()"

mapping:
  source: "Anthropic"
  source_id:
    expr: "fn:sha1(item.url)"

fallback:
  title: "{link}"

filter:
  min_title_length: 8
  exclude_keywords: ["[Sponsored]"]

limit:
  raw: 30
  top: 10

rank:
  formula: recency
  weight_recency: 0.6
  weight_engagement: 0.4
```

支持的 fetcher type：`http`、`api`、`rss`。
支持的 extractor type：`xpath`、`jsonpath`、`regex`、`rss`。

## 6. 写入 REST 契约

crawler 唯一写入通道，定义在 `docs/api-contract.md`。

### 6.1 批量入库

**POST `/api/admin/weekly-digest/items`**

请求：
```json
{
  "issue_number": 37,
  "items": [
    {
      "section": "paper",
      "title": "...",
      "url": "...",
      "summary": "...",
      "source": "arXiv",
      "source_id": "2406.12345",
      "stars": 128,
      "published_date": "2026-09-09"
    }
  ]
}
```

Header：`Authorization: Bearer <admin_jwt>`

响应 200：
```json
{
  "success": true,
  "data": {
    "inserted": 8,
    "skipped_duplicate": 2,
    "errors": []
  }
}
```

**去重契约**：后端按 `(section, source, source_id)` 复合唯一，已存在则跳过（计入 `skipped_duplicate`，不报错）。
**幂等契约**：同一个 `issue_number` 多次 POST 安全。
**错误码**：
- 400：必填字段缺失 / issue_number 非法
- 401：admin JWT 缺失或过期
- 403：当前 admin 角色无 weekly_digest 写权限
- 500：DB 异常

### 6.2 存在性查询（供 crawler 预筛）

**GET `/api/admin/weekly-digest/check-existence?section=&source=&source_id=`**

响应：`{"exists": true | false}`

### 6.3 期号管理

crawler 通过 `GET /api/weekly-digest/issues` 读取最新期号，下一期 = max + 1。管理员可通过 admin 接口手动指定。

## 7. Pipeline 详细行为

### 7.1 Normalize

- URL：去 utm_* / fbclid / gclid 参数；去 trailing slash；统一 https
- title：strip HTML 实体、空白、长度限制 500 字符（超长截断 + "…"）
- 日期：parser 支持 `iso8601` / `rfc2822` / `rss` / `mysql`，统一转 `YYYY-MM-DD`
- source：字符串校验，禁止包含 SQL 注入关键词

### 7.2 Dedupe（双保险）

1. 本地 SQLite 缓存查 `seen_keys` 表（key = `f"{section}|{source}|{source_id}"`）
2. 后端 `check-existence` 接口二次确认
3. 命中即跳过（计入 `skipped_duplicate`）

### 7.3 Rank（默认公式）

```
recency_score    = 1 / (1 + age_days)            # age_days 为 (今天 - published_date)
engagement_score = log(1 + stars + comments*2 + likes*0.5) / log(1 + max_engagement)
score            = weight_recency * recency_score + weight_engagement * engagement_score
```

按 `score DESC` 取 `limit.top` 条。

### 7.4 Persist

按栏目分批 POST（每批 50 条），重试 3 次指数退避。响应失败立即 fail fast。

### 7.5 Run History

每次 run 写入 SQLite：

```sql
CREATE TABLE runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  issue_number INTEGER,
  status TEXT,                       -- success / partial / failed
  summary_json TEXT                  -- 每源拉取/入库/跳过/错误统计
);

CREATE TABLE seen_keys (
  key TEXT PRIMARY KEY,              -- section|source|source_id
  seen_at TEXT NOT NULL
);

CREATE TABLE errors (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL,
  source_id TEXT,
  error TEXT,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);
```

## 8. 调度与可观测性

### 8.1 调度

Windows 计划任务脚本（`scripts/install_schtask.ps1`）：
```powershell
schtasks /create /tn "SkillPulseCrawler" /tr "python -m skillpulse_crawler run" /sc weekly /d SUN /st 23:00 /ru SYSTEM
```

### 8.2 日志

- 控制台：`rich` 输出进度条与表格
- 文件：`runs/{YYYY-MM-DD_HH-mm-ss}.json` 完整 run 报告
- 日志级别：默认 INFO，`--verbose` 改 DEBUG

### 8.3 错误处理

| 错误类型 | 处理 |
|---|---|
| 单源 fetch 失败 | 隔离：该源记 `errors`，其他源继续 |
| 单源解析失败 | 同上 |
| 单条字段校验失败 | 跳过该条，记 `errors` |
| 后端 4xx | 立即停止整个 run |
| 后端 5xx | 重试 3 次（1s/5s/25s 退避）后停止 |
| 网络超时 | 单源重试 3 次后标记失败 |

## 9. 依赖选型

```toml
[project]
dependencies = [
    "httpx>=0.27",              # 异步 HTTP
    "pydantic>=2.6",            # 数据校验
    "PyYAML>=6.0",              # YAML 解析
    "lxml>=5.0",                # XPath
    "jsonpath-ng>=1.6",         # JSONPath
    "feedparser>=6.0",          # RSS
    "rich>=13.0",               # 终端输出
    "python-dotenv>=1.0",       # .env
    "tenacity>=8.2",            # 重试
    "click>=8.1",               # CLI
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "respx>=0.21"]
```

**为什么不上 Scrapy？**
- Scrapy 是为大型整站抓取设计的，引入 200MB+ 依赖
- 本项目只需要 N 个数据源，httpx + lxml 更轻量
- Scrapy 的 Spider/Twisted 异步模型对本场景过度复杂

## 10. 安全

- 所有后端凭证（admin JWT、数据库密码）走 env，不进 git
- `.env` 已加 `.gitignore`
- admin JWT 用最小权限角色
- crawler 不接收用户输入，全部 pipeline 来自 YAML + HTTP 响应，不存在 XSS / SQLi 风险

## 11. 测试策略

- **单元测试**：normalize / dedupe / rank / 各类 extractor
- **集成测试**：用 `respx` mock HTTP，验证整个 pipeline 行为
- **契约测试**：用 OpenAPI schema 校验请求/响应
- **手动 dry-run**：`python -m skillpulse_crawler dry-run --source news_anthropic_blog` 输出预期入库项，不实际 POST

## 12. 验收标准

- [ ] 至少 3 个 YAML 数据源（paper_arxiv / project_github_trending / community_hackernews）端到端跑通
- [ ] dry-run 输出与实际入库一致
- [ ] 重复 POST 同 issue 不产生新行（验证后端幂等）
- [ ] 单源失败不影响其他源
- [ ] 关闭网络后 crawler 优雅失败，记录在 errors 表

## 13. 风险与缓解

| 风险 | 缓解 |
|---|---|
| YAML 配置写错导致字段全空 | CLI `validate-config` 子命令 dry-run 校验 |
| 数据源网站改版 | extractor 解析失败被隔离，记录到 errors |
| 后端接口变更 | 契约文档化、OpenAPI schema 自动校验 |
| crawler 占用过多内存 | 流式解析 lxml.iterparse，避免大文档一次性 load |

## 14. 后续可演进（不在 v0 范围）

- Playwright 适配器（应对 JS 渲染）
- 增量采集（diff URL 列表，只拉新增）
- 多语种 summary（GPT 翻译）
- Web 管理面板（查看 run history、强制重跑）