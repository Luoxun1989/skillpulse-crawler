# SkillPulse Crawler 部署文档

采集 4 栏目（news/paper/project/community）→ 调用后端 admin batch 接口入库。
每 3 小时由 cron / Task Scheduler 触发一次，与后端、前端部署解耦。

---

## 一、服务器环境要求

| 项目 | 要求 |
|------|------|
| OS | Linux (Ubuntu 20.04+ / CentOS 7+) 或 Windows Server |
| Python | 3.11+（与本机对齐，参考 [memory skillpulse-chestnut-stack](memory/skillpulse-chestnut-stack.md)） |
| 网络 | 可访问后端 API、可访问各 source YAML 中的目标站 |
| 后端 | 已部署并运行（参见 `DEPLOY.md`） |

---

## 二、目录布局

```
/data/skillpulse-crawler/
├── skillpulse_crawler/        # 代码
│   ├── cli.py
│   ├── sources/               # 17 个 YAML
│   └── ...
├── scripts/                   # 运维脚本
│   ├── replay_all.py
│   └── export_full_sql.py
├── sql/                       # 初始化 SQL
│   └── init_full_data.sql
├── logs/                      # 运行日志（cron 输出重定向到这里）
├── data/                      # SQLite state.db（全局去重）
├── .venv/                     # Python 虚拟环境
├── .env                       # 环境变量（见第三节）
└── run.sh                     # 单次跑（cron 调用）
```

---

## 三、环境配置

### 1. 安装 Python 与依赖

```bash
# Ubuntu
apt-get install -y python3.11 python3.11-venv

# 创建虚拟环境
cd /data/skillpulse-crawler
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` 至少包含：
```
httpx
lxml
jsonpath-ng
feedparser
tenacity
click
pydantic>=2
python-dotenv
pyyaml
```

Playwright（仅 `latepost` 等反爬源需要，可选）：
```bash
.venv/bin/playwright install chromium
```

### 2. .env 文件

**禁止把真实凭证 commit 到 git。** 复制模板后填入服务器独立凭证：

```bash
cp .env.example .env
chmod 600 .env
```

`.env` 内容：
```
# 后端 API 基址（与后端 jar 启动时同一台机器）
API_BASE=http://127.0.0.1:8081

# 后端 admin 登录用户名/密码（与后端 application-prod.yml 一致）
ADMIN_USER=admin
ADMIN_PASS={{ADMIN_PASSWORD}}

# 历史去重 SQLite 路径（默认 ./data/runs.sqlite）
SKILLPULSE_CRAWLER_DB=/data/skillpulse-crawler/data/runs.sqlite
```

`ADMIN_PASS` 必须替换为后端 `application-prod.yml` 中定义的 admin 密码（**不要使用 dev 默认 admin/admin123**）。

---

## 四、首次运行验证

### 1. 单源 dry-run

```bash
cd /data/skillpulse-crawler
.venv/bin/python -m skillpulse_crawler dry-run --source news_huxiu
```

期望：打印 `[dry-run] news_huxiu: raw=N new=M`（数字非零），无 traceback。

### 2. 申请 admin JWT（cron 启动时自动续）

手动跑一次验证后端连通：
```bash
ADMIN_PASS={{ADMIN_PASSWORD}} \
  .venv/bin/python -m skillpulse_crawler run --source news_huxiu
```

期望：
- `[crawler] issue = 20260924 (2026-09-24)`（YYYYMMDD 数字）
- `news_huxiu: raw=N new=M inserted=K`
- `Run finished: issue=20260924, sources=1`

### 3. 全源跑（可选）

```bash
ADMIN_PASS={{ADMIN_PASSWORD}} \
  .venv/bin/python -m skillpulse_crawler run
```

期望：所有 enabled source 跑一遍，history 已见 source_id 自动 skip。

---

## 五、定时任务

每 3 小时采集一轮。提供两种方案。

### 方案 A：Linux cron（推荐）

#### 1. 创建 run.sh

```bash
#!/bin/bash
set -e

cd /data/skillpulse-crawler

# 加载 .env
set -a
source .env
set +a

LOG=/data/skillpulse-crawler/logs/cron-$(date +%Y%m%d_%H%M).log
.venv/bin/python -X utf8 -m skillpulse_crawler run >> "$LOG" 2>&1

# 健康检查：连续失败告警（可选）
RC=$?
if [ $RC -ne 0 ]; then
    echo "[$(date)] crawler exit $RC" >> /data/skillpulse-crawler/logs/error.log
fi
```

```bash
chmod +x /data/skillpulse-crawler/run.sh
```

#### 2. 安装 cron

```bash
# 编辑当前用户的 crontab
crontab -e
```

加一行（每 3 小时一次，分钟偏移避开整点）：
```cron
17 */3 * * * /data/skillpulse-crawler/run.sh
```

#### 3. 验证

```bash
# 看 cron 列表
crontab -l

# 看下次执行时间（systemd 时代可用 run-parts；纯 vixie-cron 直接看日志）
grep CRON /var/log/syslog | tail -20
```

### 方案 B：Windows Task Scheduler

如果服务器是 Windows（用 nohup 替代 cron）：

```powershell
# 创建任务：每 3 小时触发 run.bat
schtasks /Create ^
  /TN "SkillPulseCrawler" ^
  /TR "D:\skillpulse-crawler\run.bat" ^
  /SC HOURLY /MO 3 ^
  /ST 00:17 ^
  /RL HIGHEST
```

`run.bat` 内容：
```bat
@echo off
cd /d D:\skillpulse-crawler
call .venv\Scripts\activate.bat
set ADMIN_PASS={{ADMIN_PASSWORD}}
.venv\Scripts\python.exe -X utf8 -m skillpulse_crawler run >> logs\cron-%date:~0,4%%date:~5,2%%date:~8,2%.log 2>&1
```

---

## 六、初始化数据（可选）

首次部署服务器端 DB 为空时，把当前 dev 已采集的 2024 条数据导入：

```bash
# 在爬虫目录
mysql -u root -p skillpulse < sql/init_full_data.sql
```

**注意**：服务器 DB 必须先建好 4 张表（`news_item`/`paper_item`/`project_item`/`community_item`）。
表结构由后端 `schema.sql` 或启动时 Hibernate DDL 维护；详见 `DEPLOY.md` 第二节。

---

## 七、回填脚本（数据迁移/补漏）

如果后端库里历史数据有缺失（例如之前 limit.top=10 截断时丢的），用回填脚本补齐：

```bash
ADMIN_PASS={{ADMIN_PASSWORD}} \
  .venv/bin/python scripts/replay_all.py
```

脚本对每个 enabled source 全量拉一次，绕过 history 客户端 dedupe，依赖后端 service 层 `(source, source_id)` 唯一索引兜底。

---

## 八、运维命令速查

| 命令 | 用途 |
|------|------|
| `dry-run --source X` | 单源 dry-run（不入库） |
| `run --only X` | 只跑某个 source id |
| `run --issue 20260924` | 指定采集日期（默认今天） |
| `replay_all.py` | 全源回填（绕过 history） |
| `export_full_sql.py` | 从 dev 后端拉全表导出 SQL |
| 清空 history | `rm data/runs.sqlite`（强制全量重抓，但后端 dedupe 仍兜底） |

---

## 九、故障排查

### 9.1 401 Unauthorized

`ADMIN_PASS` 与后端 `application-prod.yml` 中 admin 密码不一致。重新生成 JWT 不需要改密码——直接改 `.env` 即可。

### 9.2 source_id 超长入库 500

见 `cli.py:_shorten_source_id`：超过 200 字符自动 md5 截断为 `h_` + 16 hex。
如仍报 500，说明截断没生效，检查 `cli.py` 是否被覆盖。

### 9.3 cron 没执行

```bash
# Linux
systemctl status cron
grep CRON /var/log/syslog

# 看 run.sh 是不是有 +x
ls -l /data/skillpulse-crawler/run.sh
```

### 9.4 日志膨胀

`logs/` 下 cron 日志按 `cron-YYYYMMDD_HHMM.log` 命名。建议加 logrotate：

```bash
cat > /etc/logrotate.d/skillpulse-crawler <<'EOF'
/data/skillpulse-crawler/logs/cron-*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF
```

---

## 十、与后端/前端部署的关系

本服务**完全解耦**：
- 后端部署：参见 `DEPLOY.md`（顶层）
- 前端部署：参见 `DEPLOY.md` 第三节
- 爬虫部署：本文件

爬虫只依赖：
1. 后端 admin JWT（认证）
2. 后端 `/api/admin/weekly-digest/{section}/items/batch` 端点
3. 各 source YAML 中目标站点的网络可达性

后端重启或前端重启不影响爬虫下次执行。
