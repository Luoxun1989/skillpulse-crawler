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
    assert cfg.limit.top == 10