from contextlib import contextmanager
import json
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


class SkillPulseHTTP:
    def __init__(self, client: httpx.Client):
        self.client = client

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def fetch(self, url: str, headers: dict | None = None, timeout: int = 30) -> httpx.Response:
        kwargs = {"timeout": timeout}
        if headers:
            kwargs["headers"] = headers
        r = self.client.get(url, **kwargs)
        if r.status_code >= 500:
            r.raise_for_status()
        return r


class PlaywrightHTTP:
    """For JS-rendered / Cloudflare-challenged pages. Returns HTML after JS settles.

    Usage: same as SkillPulseHTTP.fetch() — returns object with .text and .status_code.
    """

    def __init__(self, headless: bool = True, wait_ms: int = 2500):
        self.headless = headless
        self.wait_ms = wait_ms

    def fetch(self, url: str, headers: dict | None = None, timeout: int = 30) -> "httpx.Response":
        import asyncio
        from playwright.sync_api import sync_playwright
        ua = (headers or {}).get("User-Agent") or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # async context — delegate to async helper
            return self._afetch(url, ua, timeout)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            try:
                ctx = browser.new_context(user_agent=ua, ignore_https_errors=True)
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                page.wait_for_timeout(self.wait_ms)
                html = page.content()
            finally:
                browser.close()
        return _FakeResponse(html, 200, url)

    def _afetch(self, url, ua, timeout):
        import asyncio
        from playwright.async_api import async_playwright
        async def _run():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                try:
                    ctx = await browser.new_context(user_agent=ua, ignore_https_errors=True)
                    page = await ctx.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                    await page.wait_for_timeout(self.wait_ms)
                    return await page.content()
                finally:
                    await browser.close()
        html = asyncio.run(_run())
        return _FakeResponse(html, 200, url)


class _FakeResponse:
    """Duck-typed httpx.Response that exposes .text/.status_code for extractor pipeline."""

    def __init__(self, html: str, status_code: int, url: str):
        self.text = html
        self.status_code = status_code
        self.url = url


@contextmanager
def create_client(timeout: int = 30):
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        yield SkillPulseHTTP(c)