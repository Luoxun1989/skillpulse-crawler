from lxml import html
from .base import BaseExtractor


class XPathExtractor(BaseExtractor):
    def __init__(self, item_selector: str, fields: dict[str, str]):
        self.item_selector = item_selector
        self.fields = fields

    def extract(self, raw: str) -> list[dict]:
        tree = html.fromstring(raw)
        items = []
        for node in tree.xpath(self.item_selector):
            row = {}
            for name, expr in self.fields.items():
                result = node.xpath(expr)
                if isinstance(result, list):
                    row[name] = result[0] if result else ""
                else:
                    row[name] = str(result) if result else ""
            items.append(row)
        return items