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

## 数据源清单（2026-09-22 实测）

**当前 7 个已适配源**：

| ID | Section | 类型 | URL | 备注 |
|---|---|---|---|---|
| `news_qnmlgb_daily` | news | http | https://qnmlgb.tech/daily | 微信公众号聚合早报，14 条/期 |
| `news_aihot_industry` | news | **playwright** | aihot.news/?category=industry | AI 行业聚合，~10 条/期 |
| `paper_aihot` | paper | **playwright** | aihot.news/?category=paper | 论文聚合（Claude/OpenAI/Dwarkesh 等） |
| `project_open_itc` | project | http | open.itc.cn/github/trend/repos | GitHub 每日趋势榜，~30 条/期 |
| `project_aihot_products` | project | **playwright** | aihot.news/?category=ai-products | AI 产品榜 |
| `community_smithery` | community | api | registry.smithery.ai/skills | Skills 注册中心 API（无反爬） |
| `community_skillhub` | community | **playwright** | skillhub.cn/skills | 中文 AI Skills 聚合（绕过 CF captcha） |

**反爬绕过方案**：Cloudflare captcha / JS 渲染源（aihot/skillhub）用 `fetcher.type=playwright`，首次 fetch 需 ~3s 等 JS 渲染。

**已知不可达源**（反爬严重，已放弃）：
- 36kr.com（阿里云 JS 风控）
- 知乎 project-square（强反爬）
- discoverhub.cn（需 JS 交互加载）
- latepost.com（SSL 证书 + 付费墙）
- jiqizhixin.com（首页为推广页，RSS 实际重定向）
- github trending / huggingface（Cloudflare captcha）

**环境变量**：
```bash
SKILLPULSE_API_BASE=http://localhost:8081  # 后端地址
SKILLPULSE_ADMIN_JWT=<token>               # POST /api/admin/login 拿
SKILLPULSE_CRAWLER_DB=./data/runs.sqlite   # 历史 SQLite 路径
PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright  # 国内镜像加速
```

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