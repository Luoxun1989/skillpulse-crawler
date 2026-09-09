from contextlib import contextmanager
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


@contextmanager
def create_client(timeout: int = 30):
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        yield SkillPulseHTTP(c)