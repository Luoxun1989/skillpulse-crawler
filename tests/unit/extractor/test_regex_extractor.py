from skillpulse_crawler.extractor.regex_extractor import RegexExtractor

HTML = """
<h2><a href="/a/1">Repo One</a></h2>
<h2><a href="/a/2">Repo Two</a></h2>
"""


def test_regex_extract():
    ext = RegexExtractor(
        item_pattern=r'<a href="(/a/\d+)">([^<]+)</a>',
        fields={"url": 1, "title": 2}
    )
    items = ext.extract(HTML)
    assert items == [{"url": "/a/1", "title": "Repo One"}, {"url": "/a/2", "title": "Repo Two"}]