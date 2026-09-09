import feedparser
from datetime import datetime
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
                    raw_date = entry.get("published", "") or entry.get("updated", "")
                    if not raw_date and entry.get("published_parsed"):
                        raw_date = datetime(*entry.published_parsed[:6]).strftime("%a, %d %b %Y %H:%M:%S +0000")
                    row["published_date"] = normalize_date(raw_date, parser=parser) or ""
                elif field == "summary":
                    row["summary"] = entry.get("summary", "")
            items.append(row)
        return items