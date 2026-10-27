"""One service, both markets: a small front door that sends each request to the India or the US engine.

Why two worker processes behind one port, not one process: every engine module is bound to its market profile at
import (clock, universe, data directory, costs). That binding is also what guarantees India and US evidence never mix,
so the gateway keeps it: it starts one worker per market, picks the market per request (?market= switches it, a
cookie remembers it), forwards the request unchanged and streams the answer back. Pages keep every URL as it is;
the header shows India / US tabs when a page comes through here (the x-stock-picker-gateway header).

    ./serve.sh            both markets on :61287, tabs at the top
"""

import asyncio
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.background import BackgroundTask

from app.market import MARKET_ENV, NAMES

log = logging.getLogger("stock-picker.gateway")

COOKIE = "sp_market"
GATEWAY_HEADER = "x-stock-picker-gateway"   # the worker shows the market tabs when this is present
PORTS = {name: int(os.environ.get(f"SP_{name.upper()}_PORT", 61291 + i)) for i, name in enumerate(NAMES)}
# headers that describe one connection, not the message: never forwarded (RFC 9110 7.6.1), plus host / length,
# which the next hop sets itself
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
              "transfer-encoding", "upgrade", "host", "content-length"}
DROP_FROM_REPLY = (HOP_BY_HOP - {"content-length"}) | {"date", "server"}   # uvicorn adds its own date / server
# headers httpx adds to every request by itself; a client that did not send them must not appear to (an invented
# accept-encoding makes the worker gzip for a client that cannot read gzip)
CLIENT_DEFAULTS = {"accept", "accept-encoding", "user-agent"}
COOKIE_MAX_AGE = 365 * 86_400
# a refresh downloads for a minute or more: never time out a read; do time out a dead worker
TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=60.0, pool=10.0)


def choose(query_market: str | None, cookie_market: str | None) -> tuple[str, bool]:
    """(market for this request, whether to remember it). ?market= wins, then the cookie, then the first market."""
    if query_market in NAMES:
        return query_market, query_market != cookie_market
    if cookie_market in NAMES:
        return cookie_market, False
    return NAMES[0], False


def forward_headers(headers: list[tuple[bytes, bytes]], market: str) -> list[tuple[bytes, bytes]]:
    kept = [(k, v) for k, v in headers if k.decode("latin-1").lower() not in HOP_BY_HOP]
    return kept + [(GATEWAY_HEADER.encode(), market.encode())]


def start_workers() -> dict[str, subprocess.Popen]:
    """One uvicorn per market on its internal port, with that market's profile selected."""
    return {name: subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                    "--port", str(PORTS[name]), "--log-level", "warning"],
                                   env={**os.environ, MARKET_ENV: name})
            for name in NAMES}


async def wait_until_ready(client: httpx.AsyncClient, workers: dict[str, subprocess.Popen], seconds: float = 90) -> None:
    pending = set(workers)
    for _ in range(int(seconds * 4)):
        for name in list(pending):
            if workers[name].poll() is not None:
                raise RuntimeError(f"the {name} worker exited with code {workers[name].returncode}")
            try:
                if (await client.get(f"http://127.0.0.1:{PORTS[name]}/static/icon.svg")).status_code == 200:
                    pending.discard(name)
            except httpx.TransportError:
                pass
        if not pending:
            return
        await asyncio.sleep(0.25)
    raise RuntimeError(f"workers not ready after {seconds:.0f}s: {sorted(pending)}")


def create_app(transport: httpx.AsyncBaseTransport | None = None, spawn: bool = True) -> FastAPI:
    """The gateway. Tests pass a fake `transport` and spawn=False; production starts the real workers."""
    state: dict = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        state["client"] = httpx.AsyncClient(transport=transport, timeout=TIMEOUT, follow_redirects=False)
        workers = start_workers() if spawn else {}
        try:
            if workers:
                await wait_until_ready(state["client"], workers)
                log.info("workers ready: %s", ", ".join(f"{n}:{PORTS[n]}" for n in workers))
            yield
        finally:
            for proc in workers.values():
                proc.terminate()
            for proc in workers.values():
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            await state["client"].aclose()

    app = FastAPI(title="Stock Picker", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def proxy(request: Request, path: str):
        market, remember = choose(request.query_params.get("market"), request.cookies.get(COOKIE))
        client: httpx.AsyncClient = state["client"]
        upstream = client.build_request(
            request.method, httpx.URL(f"http://127.0.0.1:{PORTS[market]}/{path}", query=request.url.query.encode()),
            headers=forward_headers(request.headers.raw, market), content=await request.body())
        for name in CLIENT_DEFAULTS - {k.decode("latin-1").lower() for k, _ in request.headers.raw}:
            upstream.headers.pop(name, None)
        try:
            reply = await client.send(upstream, stream=True)
        except httpx.TransportError as exc:
            log.warning("%s worker unreachable: %s", market, exc)
            return HTMLResponse(f"<h1>The {market} engine is not answering</h1><p>It may still be starting: "
                                "try again in a few seconds.</p>", status_code=503)
        response = StreamingResponse(reply.aiter_raw(), status_code=reply.status_code, background=BackgroundTask(reply.aclose))
        # raw bytes are passed through, so the worker's content-encoding and content-length stay true
        response.raw_headers = [(k, v) for k, v in reply.headers.raw if k.decode("latin-1").lower() not in DROP_FROM_REPLY]
        if remember:
            response.set_cookie(COOKIE, market, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
        return response

    return app


app = create_app()
