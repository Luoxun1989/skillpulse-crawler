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