from skillpulse_crawler.extractor.rss_extractor import RSSExtractor

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>X</title>
<item><title>One</title><link>https://x/1</link><pubDate>Mon, 09 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Two</title><link>https://x/2</link><pubDate>Sun, 08 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_extract_rss():
    ext = RSSExtractor(fields={"published_date": "rss"})
    items = ext.extract(RSS)
    assert len(items) == 2
    assert items[0]["title"] == "One"
    assert items[0]["published_date"] == "2026-09-09"