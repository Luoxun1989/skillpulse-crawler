# skillpulse-crawler

每周自动抓取 AI 相关内容，写入 skillpulse-api 的 weekly_digest_items 表。

## 快速开始

```bash
# 1. 装依赖（Python 3.11+）
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 SKILLPULSE_ADMIN_JWT（POST /api/admin/login 拿 token）

# 3. 校验配置
python -m skillpulse_crawler validate-config

# 4. 单源试跑（不写入后端）
python -m skillpulse_crawler dry-run --source paper_arxiv

# 5. 实际写入
python -m skillpulse_crawler run
```

## CLI 子命令

| 命令 | 说明 |
|---|---|
| `validate-config` | 加载 sources/ 下所有 YAML，做 schema 校验 |
| `dry-run --source <id>` | 跑单条源，但不调 REST 写入 |
| `run` | 全量跑所有 enabled 源，写入后端 |
| `run --only <id>` | 只跑指定源 |
| `run --issue <n>` | 指定期号（默认取 max+1） |

## 数据源配置

每个 YAML 一个数据源，存放在 `skillpulse_crawler/sources/`：

```yaml
id: paper_arxiv          # 全局唯一 ID
section: paper           # news | project | paper | community
fetcher:
  type: rss              # rss | http | api
  url: ...
  headers: {}
extractor:
  type: rss              # rss | xpath | jsonpath | regex
  fields:
    summary: rss
    published_date: rss
mapping:
  source: "arXiv"
  source_id:
    expr: "fn:arxiv_id_from_url"
limit:
  raw: 30                # 拉多少
  top: 10                # 入库多少
```

加新源 = 加一个 YAML，不需要改代码。

## 调度（Windows 计划任务）

```powershell
# 安装：每周日 23:00 自动跑
.\scripts\install_schtask.ps1

# 卸载
.\scripts\uninstall_schtask.ps1
```

## 目录结构

```
skillpulse-crawler/
├── skillpulse_crawler/
│   ├── __main__.py          # python -m skillpulse_crawler 入口
│   ├── cli.py               # Click 命令
│   ├── models.py            # Pydantic 模型
│   ├── config.py            # YAML 加载
│   ├── http_client.py       # httpx + 重试
│   ├── history.py           # SQLite run history
│   ├── sources/             # 数据源配置（YAML）
│   ├── extractor/           # 4 类解析器
│   └── pipeline/            # normalize / rank / dedupe / persist
├── tests/
├── scripts/                 # 调度安装
└── docs/superpowers/        # spec + plan
```

## 故障排查

- **Token 过期**：.env 里的 `SKILLPULSE_ADMIN_JWT` 失效，重新登录拿
- **网络抓取失败**：查看 `data/runs.sqlite` 的 `errors` 表
- **去重过激**：清空 `seen_keys` 表可重跑所有源
- **RSS 解析失败**：换 jsonpath / regex extractor 重写 YAML

## 详细文档

- 设计 spec：`docs/superpowers/specs/2026-09-09-skillpulse-crawler-design.md`
- 实现 plan：`docs/superpowers/plans/2026-09-09-skillpulse-crawler-v0.md`