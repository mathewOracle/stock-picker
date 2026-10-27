#!/bin/sh
# Start the stock picker. Usage: ./serve.sh [india|us] [port]
#   ./serve.sh            India + US in one service on 61287, with market tabs at the top (app/gateway.py)
#   ./serve.sh 61290      the same, on 61290
#   ./serve.sh india      India only on 61287          ./serve.sh us        US only on 61288
#   ./serve.sh us 61299   US only on 61299
# The combined service runs each market's engine as an internal worker (India 61291, US 61292; override with
# SP_INDIA_PORT / SP_US_PORT). Each market keeps its own data dir (data/ or data-us/), so evidence never mixes.
# Proxy defaults to the corporate sysproxy; override HTTPS_PROXY to change, or set it empty off-network.
cd "$(dirname "$0")" || exit 1

busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

case "$1" in
  us|US)        MARKET=us;    DEFAULT_PORT=61288; shift ;;
  india|INDIA)  MARKET=india; DEFAULT_PORT=61287; shift ;;
  *)            MARKET=both;  DEFAULT_PORT=61287 ;;
esac
PORT="${1:-$DEFAULT_PORT}"

if busy "$PORT"; then
  echo "Port $PORT is busy. Pick another: ./serve.sh $([ "$MARKET" = both ] || echo "$MARKET ")$((PORT + 10))" >&2
  exit 1
fi

export HTTPS_PROXY="${HTTPS_PROXY-http://sysproxy.wal-mart.com:8080}"
export HTTP_PROXY="$HTTPS_PROXY"

if [ "$MARKET" = both ]; then
  for WORKER_PORT in "${SP_INDIA_PORT:-61291}" "${SP_US_PORT:-61292}"; do
    if busy "$WORKER_PORT"; then
      echo "Worker port $WORKER_PORT is busy (set SP_INDIA_PORT / SP_US_PORT to move it)." >&2
      exit 1
    fi
  done
  echo "Stock picker (India + US) -> http://127.0.0.1:$PORT"
  exec .venv/bin/uvicorn app.gateway:app --port "$PORT" --log-level info
fi

export STOCK_PICKER_MARKET="$MARKET"
echo "Stock picker ($MARKET) -> http://127.0.0.1:$PORT"
exec .venv/bin/uvicorn app.main:app --port "$PORT" --log-level info
