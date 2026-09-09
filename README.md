# skillpulse-crawler

每周自动抓取 AI 相关内容，写入 skillpulse-api 的 weekly_digest_items 表。

## 快速开始

```bash
cp .env.example .env  # 填入 admin JWT
pip install -e ".[dev]"
python -m skillpulse_crawler validate-config
python -m skillpulse_crawler dry-run --source paper_arxiv
python -m skillpulse_crawler run
```

详见 docs/superpowers/specs/2026-09-09-skillpulse-crawler-design.md