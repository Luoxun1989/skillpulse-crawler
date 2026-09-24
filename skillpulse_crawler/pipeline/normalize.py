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
            # try a few common forms before strict ISO8601
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(value.replace("Z", "+0000") if fmt.endswith("%z") else value, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return None
        if parser == "mysql":
            return value[:10]
        if parser == "rss":
            dt = parsedate_to_datetime(value)
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return None
    return None