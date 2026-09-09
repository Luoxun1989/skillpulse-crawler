from skillpulse_crawler.pipeline.normalize import normalize_url, normalize_title, normalize_date


def test_normalize_url_strip_utm():
    assert normalize_url("https://x.com/a?utm_source=t&b=1") == "https://x.com/a?b=1"


def test_normalize_url_strip_trailing_slash():
    assert normalize_url("https://x.com/a/") == "https://x.com/a"


def test_normalize_url_keep_root_slash():
    assert normalize_url("https://x.com/") == "https://x.com/"


def test_normalize_title_strip_html():
    assert normalize_title("<b>Hello</b>  world  ") == "Hello world"


def test_normalize_title_truncate():
    assert len(normalize_title("x" * 1000)) == 501


def test_normalize_date_rfc2822():
    assert normalize_date("Mon, 09 Sep 2026 10:00:00 GMT", parser="rfc2822") == "2026-09-09"


def test_normalize_date_iso8601():
    assert normalize_date("2026-09-09T10:00:00Z", parser="iso8601") == "2026-09-09"


def test_normalize_date_invalid_returns_none():
    assert normalize_date("not a date", parser="iso8601") is None