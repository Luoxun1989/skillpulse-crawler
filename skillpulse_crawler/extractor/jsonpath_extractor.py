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