"""The single-service gateway: market choice, the cookie, forwarding and failure, with a fake transport for the workers."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import gateway
from app.market import NAMES

PORT_TO_MARKET = {port: name for name, port in gateway.PORTS.items()}


class Streamed(httpx.AsyncByteStream):
    """A body that arrives in chunks, like a real worker socket (httpx.Response(json=...) would be pre-read)."""

    def __init__(self, body: bytes):
        self.body = body

    async def __aiter__(self):
        yield self.body[: len(self.body) // 2]
        yield self.body[len(self.body) // 2:]


def fake_workers(request: httpx.Request) -> httpx.Response:
    """Answers like a worker: says which market it is, echoes what reached it."""
    market = PORT_TO_MARKET[request.url.port]
    seen = {"market": market, "path": request.url.path, "query": request.url.query.decode(),
            "gateway": request.headers.get(gateway.GATEWAY_HEADER), "host": request.headers.get("host"),
            "body": request.content.decode(), "cookie": request.headers.get("cookie", ""),
            "accept_encoding": request.headers.get("accept-encoding")}
    return httpx.Response(200, stream=Streamed(json.dumps(seen).encode()),
                          headers={"content-type": "application/json", "x-worker": market, "connection": "keep-alive"})


@pytest.fixture
def client():
    with TestClient(gateway.create_app(transport=httpx.MockTransport(fake_workers), spawn=False)) as test_client:
        yield test_client


def test_choose_query_then_cookie_then_default():
    assert gateway.choose("us", None) == ("us", True)            # a switch is remembered
    assert gateway.choose("us", "us") == ("us", False)           # already remembered
    assert gateway.choose(None, "us") == ("us", False)
    assert gateway.choose("mars", "us") == ("us", False)         # unknown values never pick a market
    assert gateway.choose(None, None) == (NAMES[0], False)


def test_default_market_is_india_and_no_cookie_is_set(client):
    reply = client.get("/")
    assert reply.json()["market"] == "india" and gateway.COOKIE not in reply.cookies


def test_switching_sets_the_cookie_and_later_requests_follow_it(client):
    reply = client.get("/?market=us")
    assert reply.json()["market"] == "us" and reply.cookies.get(gateway.COOKIE) == "us"
    # htmx partials carry the cookie, not ?market=, so they reach the same engine as the page
    assert client.get("/detail?tab=swing&symbol=AAPL").json()["market"] == "us"
    assert client.get("/?market=india").json()["market"] == "india"
    assert client.get("/detail").json()["market"] == "india"


def test_request_is_forwarded_unchanged_plus_the_gateway_header(client):
    client.cookies.set(gateway.COOKIE, "us")
    seen = client.post("/desk/order?mode=swing", data={"symbol": "AAPL", "qty": "3"}).json()
    assert seen["path"] == "/desk/order" and seen["query"] == "mode=swing"
    assert seen["body"] == "symbol=AAPL&qty=3"
    assert seen["gateway"] == "us"                      # the worker shows the market tabs
    assert seen["host"] == f"127.0.0.1:{gateway.PORTS['us']}"   # host is the worker's, never the browser's


def test_no_invented_headers(client):
    """curl caught this: httpx adds accept-encoding by itself, the worker then gzipped for a client without gzip."""
    del client.headers["accept-encoding"]
    assert client.get("/").json()["accept_encoding"] is None
    assert client.get("/", headers={"accept-encoding": "gzip"}).json()["accept_encoding"] == "gzip"   # a real one passes


def test_reply_headers_pass_through_without_hop_by_hop(client):
    reply = client.get("/")
    assert reply.headers["x-worker"] == "india"
    assert "keep-alive" not in reply.headers.get("connection", "")


def test_a_dead_worker_is_a_clear_503():
    def down(request):
        raise httpx.ConnectError("refused", request=request)
    with TestClient(gateway.create_app(transport=httpx.MockTransport(down), spawn=False)) as dead:
        reply = dead.get("/?market=us")
    assert reply.status_code == 503 and "us engine is not answering" in reply.text


def test_every_market_has_its_own_port():
    assert set(gateway.PORTS) == set(NAMES) and len(set(gateway.PORTS.values())) == len(NAMES)


def test_worker_shows_market_tabs_only_behind_the_gateway():
    """Standalone (./serve.sh us) has no tabs to nowhere; through the gateway both markets are offered."""
    from app.main import app as worker
    from app.market import MARKET, load
    page = TestClient(worker)
    alone = page.get("/market").text
    behind = page.get("/market", headers={gateway.GATEWAY_HEADER: MARKET.key}).text
    assert 'aria-label="Market"' not in alone
    assert 'aria-label="Market"' in behind
    for name in NAMES:
        assert f'href="/?market={name}"' in behind and load(name).short_name in behind
    assert behind.count('aria-current="page" class="segment') == 1   # exactly the active market is marked
