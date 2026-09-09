import respx
from httpx import Response
from skillpulse_crawler.http_client import create_client


@respx.mock
def test_fetch_success():
    respx.get("https://x.com/feed").mock(return_value=Response(200, text="ok"))
    with create_client() as client:
        r = client.fetch("https://x.com/feed")
    assert r.text == "ok"


@respx.mock
def test_fetch_retry_on_5xx():
    respx.get("https://x.com/feed").mock(side_effect=[
        Response(503, text="err"), Response(200, text="ok")
    ])
    with create_client() as client:
        r = client.fetch("https://x.com/feed")
    assert r.text == "ok"