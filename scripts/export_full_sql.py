"""从 dev 后端拉全 4 表数据 → 生成 SQL 初始化脚本。

走 admin API（认证登录 → 拉每个 section 全表）→ 转 SQL INSERT 列表。
不在脚本里硬编码任何凭证，凭证从环境变量读。

用法：
    API_BASE=http://localhost:8081 ADMIN_USER=admin ADMIN_PASS=xxx \
      .venv/Scripts/python -X utf8 -m scripts.export_full_sql
产出：sql/init_full_data.sql
"""
import os
import sys
import json
import re
import subprocess
from pathlib import Path

API_BASE = os.environ.get("API_BASE", "http://localhost:8081")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")

SECTIONS = ["news", "paper", "project", "community"]
OUT = Path(__file__).resolve().parent.parent / "sql" / "init_full_data.sql"

# 表名 → 用于 INSERT
TABLE = {
    "news": "news_item",
    "paper": "paper_item",
    "project": "project_item",
    "community": "community_item",
}


def login() -> str:
    r = subprocess.check_output([
        "curl", "-s", "-X", "POST", f"{API_BASE}/api/admin/login",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}),
    ])
    token = json.loads(r).get("data", {}).get("token")
    if not token:
        raise SystemExit(f"登录失败: {r.decode()[:200]}")
    return token


def fetch_all(token: str, section: str) -> list:
    items = []
    page = 1
    while True:
        r = subprocess.check_output([
            "curl", "-s",
            f"{API_BASE}/api/admin/weekly-digest/{section}/items?page={page}&limit=500",
            "-H", f"Authorization: Bearer {token}",
        ])
        data = json.loads(r).get("data", [])
        items.extend(data)
        if len(data) < 500:
            break
        page += 1
    return items


def _to_mysql_datetime(v) -> str | None:
    """ISO8601 datetime str → MySQL DATETIME 字符串。

    API 返回形如 '2026-09-24T01:15:00.000+00:00'，MySQL DATETIME 列只接
    'YYYY-MM-DD HH:MM:SS'。截断到秒、丢弃时区后缀。
    if 无法解析，返回原 str（视为普通文本，由外层 esc 加引号）。
    """
    if not isinstance(v, str):
        return None
    # 至少得有 'T' 才能识别为 datetime
    if "T" not in v:
        return None
    # 切到秒：2026-09-24T01:15:00.000+00:00 → 2026-09-24 01:15:00
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})", v)
    if not m:
        return None
    return f"{m.group(1)} {m.group(2)}"


def esc(v) -> str:
    """SQL 字符串转义：None→NULL；str→加单引号+转义单引号/反斜杠/NUL。

    - ISO8601 datetime 自动转 MySQL DATETIME 格式
    - mysql 客户端默认禁用 binary-mode，遇到 NUL 字节整段 SQL 拒绝执行
    """
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, bool):
        return "1" if v else "0"
    dt = _to_mysql_datetime(v)
    s = dt if dt is not None else str(v)
    s = s.replace("\\", "\\\\").replace("'", "\\'").replace("\x00", " ")
    return f"'{s}'"


def to_row(item: dict) -> str:
    # API 返回 camelCase（sourceId/commentsCount/likesCount/publishedDate/...），
    # 但 SQL 列名是 snake_case（source_id/comments_count/likes_count/published_date/...）。
    # 字段映射字典显式列两边，避免 dict.get() 不匹配返回 None。
    field_map = {
        "id": "id",
        "title": "title",
        "summary": "summary",
        "url": "url",
        "source": "source",
        "source_id": "sourceId",
        "stars": "stars",
        "comments_count": "commentsCount",
        "likes_count": "likesCount",
        "published_date": "publishedDate",
        "issue_number": "issueNumber",
        "is_active": "isActive",
        "sort_order": "sortOrder",
        "fetch_status": "fetchStatus",
        "fetched_at": "fetchedAt",
        "batch_id": "batchId",
        "raw_url": "rawUrl",
        "error_msg": "errorMsg",
        "retry_count": "retryCount",
        "metadata": "metadata",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
    }
    vals = [esc(item.get(api_key)) for _, api_key in field_map.items()]
    return f"({', '.join(vals)})"


def main():
    if not ADMIN_PASS:
        raise SystemExit("ADMIN_PASS env required")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    token = login()
    grand = 0
    with OUT.open("w", encoding="utf-8") as f:
        f.write(_sql_header())
        for sec in SECTIONS:
            items = fetch_all(token, sec)
            f.write(f"-- ====== {TABLE[sec]} ({len(items)} rows) ======\n")
            if not items:
                f.write("-- (no rows)\n\n")
                continue
            cols = [
                "id", "title", "summary", "url", "source", "source_id",
                "stars", "comments_count", "likes_count", "published_date",
                "issue_number", "is_active", "sort_order",
                "fetch_status", "fetched_at", "batch_id", "raw_url",
                "error_msg", "retry_count", "metadata",
                "created_at", "updated_at",
            ]
            f.write(f"INSERT INTO {TABLE[sec]} ({', '.join(cols)}) VALUES\n")
            rows = [to_row(it) for it in items]
            f.write(",\n".join(rows))
            f.write(";\n\n")
            grand += len(items)
        f.write("SET FOREIGN_KEY_CHECKS = 1;\n")
    print(f"OK: {grand} rows → {OUT}")


def _sql_header() -> str:
    """SQL 文件头部：DDL + SET。DDL 来源 mysql/migrations/V20260921__create_section_tables.sql。

    顺序：先 DROP 已有表（清掉任何脏数据），再 CREATE IF NOT EXISTS，再 INSERT。
    服务器导入时会清空 4 表，再写入 2108 条干净数据。
    注意：DROP 会丢表上所有已有数据，包括爬虫新采集的（如果有）。
    """
    from datetime import datetime
    return (
        "-- SkillPulse 4 表全量初始数据\n"
        f"-- 生成时间：{datetime.now().isoformat()}\n"
        "-- 用法：mysql -u root -p skillpulse < init_full_data.sql\n"
        "-- ⚠️ 此脚本会 DROP 4 张表后重建，所有表上已有数据会丢失\n"
        "-- 服务器首次/重新导入用；不要在已有爬虫新数据的库上跑\n"
        "SET NAMES utf8mb4;\n"
        "SET FOREIGN_KEY_CHECKS = 0;\n\n"
        "-- ============================================================\n"
        "-- 先清掉旧表（DROP IF EXISTS 幂等；解决脏数据/test 数据混入）\n"
        "-- ============================================================\n"
        "DROP TABLE IF EXISTS news_item;\n"
        "DROP TABLE IF EXISTS paper_item;\n"
        "DROP TABLE IF EXISTS project_item;\n"
        "DROP TABLE IF EXISTS community_item;\n\n"
        "-- ============================================================\n"
        "-- 4 表 DDL（来源 V20260921__create_section_tables.sql）\n"
        "-- ============================================================\n"
        "CREATE TABLE news_item (\n"
        "    id              VARCHAR(32)     NOT NULL,\n"
        "    title           VARCHAR(512)    NOT NULL,\n"
        "    summary         TEXT            NULL,\n"
        "    url             VARCHAR(1024)   NOT NULL,\n"
        "    source          VARCHAR(64)     NOT NULL,\n"
        "    source_id       VARCHAR(128)    NOT NULL,\n"
        "    stars           INT             NULL,\n"
        "    comments_count  INT             NULL,\n"
        "    likes_count     INT             NULL,\n"
        "    published_date  DATE            NULL,\n"
        "    issue_number    INT             NULL,\n"
        "    is_active       TINYINT(1)      NOT NULL DEFAULT 1,\n"
        "    sort_order      INT             NOT NULL DEFAULT 0,\n"
        "    fetch_status    VARCHAR(16)     NOT NULL DEFAULT 'success',\n"
        "    fetched_at      DATETIME        NULL,\n"
        "    batch_id        VARCHAR(64)     NULL,\n"
        "    raw_url         VARCHAR(1024)   NULL,\n"
        "    error_msg       VARCHAR(1024)   NULL,\n"
        "    retry_count     INT             NOT NULL DEFAULT 0,\n"
        "    metadata        JSON            NULL,\n"
        "    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,\n"
        "    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n"
        "    PRIMARY KEY (id),\n"
        "    UNIQUE KEY uk_natural_key (source, source_id),\n"
        "    KEY idx_active_issue_sort (is_active, issue_number, sort_order),\n"
        "    KEY idx_published_date (published_date),\n"
        "    KEY idx_fetch_status (fetch_status, fetched_at)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI 行业动态';\n"
        "CREATE TABLE paper_item LIKE news_item;\n"
        "ALTER TABLE paper_item COMMENT='本周精选论文';\n"
        "CREATE TABLE project_item LIKE news_item;\n"
        "ALTER TABLE project_item COMMENT='本周热门项目';\n"
        "CREATE TABLE community_item LIKE news_item;\n"
        "ALTER TABLE community_item COMMENT='社区声音·一周热议';\n\n"
        "-- ============================================================\n"
        "-- 数据导入\n"
        "-- ============================================================\n\n"
    )


if __name__ == "__main__":
    main()
