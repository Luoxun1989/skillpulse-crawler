import json
from skillpulse_crawler.extractor.jsonpath_extractor import JSONPathExtractor

DATA = json.dumps({
    "items": [
        {"name": "A", "html_url": "https://a", "stargazers_count": 100},
        {"name": "B", "html_url": "https://b", "stargazers_count": 200},
    ]
})


def test_extract_with_jsonpath():
    ext = JSONPathExtractor(item_selector="$.items[*]", fields={
        "title": "$.name",
        "url": "$.html_url",
        "stars": "$.stargazers_count",
    })
    items = ext.extract(DATA)
    assert len(items) == 2
    assert items[1]["stars"] == 200