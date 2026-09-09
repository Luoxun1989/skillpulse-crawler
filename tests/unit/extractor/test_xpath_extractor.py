from skillpulse_crawler.extractor.xpath_extractor import XPathExtractor

HTML = """
<ul>
<li><a href="/a/1">One</a><time>2026-09-01</time></li>
<li><a href="/a/2">Two</a><time>2026-09-02</time></li>
</ul>
"""


def test_extract_list():
    ext = XPathExtractor(item_selector="//li", fields={
        "title": "./a/text()",
        "url": "./a/@href",
        "published_date": "./time/text()",
    })
    items = ext.extract(HTML)
    assert len(items) == 2
    assert items[0]["title"] == "One"
    assert items[0]["url"] == "/a/1"