import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

UTM_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "fbclid", "gclid",
}


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    qs = {
        k: v for k, v in parse_qs(parsed.query).items()
        if k not in UTM_PARAMS
    }
    new_qs = urlencode(qs, doseq=True)
    new_path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path
    return urlunparse((parsed.scheme, parsed.netloc, new_path,
                       parsed.params, new_qs, ""))


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    s = _TAG_RE.sub("", title)
    s = _WS_RE.sub(" ", s).strip()
    if len(s) > 500:
        return s[:500] + "…"
    return s


def normalize_date(value: str, parser: str = "iso8601") -> str | None:
    if not value:
        return None
    try:
        if parser == "rfc2822":
            dt = parsedate_to_datetime(value)
            return dt.strftime("%Y-%m-%d")
        if parser == "iso8601":
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        if parser == "mysql":
            return value[:10]
        if parser == "rss":
            dt = parsedate_to_datetime(value)
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return None
    return None