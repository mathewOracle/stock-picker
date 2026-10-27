#!/bin/sh
# Start the stock picker for one market. Usage: ./serve.sh [india|us] [port]
#   ./serve.sh            India on 61287 (as before)     ./serve.sh 61290      India on 61290 (as before)
#   ./serve.sh us         US on 61288                    ./serve.sh us 61299   US on 61299
# Each market has its own data dir (data/ or data-us/), so both can run side by side.
# Proxy defaults to the corporate sysproxy; override HTTPS_PROXY to change, or set it empty off-network.
cd "$(dirname "$0")" || exit 1

case "$1" in
  us|US)        MARKET=us;    DEFAULT_PORT=61288; shift ;;
  india|INDIA)  MARKET=india; DEFAULT_PORT=61287; shift ;;
  *)            MARKET=india; DEFAULT_PORT=61287 ;;
esac
PORT="${1:-$DEFAULT_PORT}"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is busy. Pick another: ./serve.sh $MARKET $((PORT + 10))" >&2
  exit 1
fi

export STOCK_PICKER_MARKET="$MARKET"
export HTTPS_PROXY="${HTTPS_PROXY-http://sysproxy.wal-mart.com:8080}"
export HTTP_PROXY="$HTTPS_PROXY"
echo "Stock picker ($MARKET) -> http://127.0.0.1:$PORT"
exec .venv/bin/uvicorn app.main:app --port "$PORT" --log-level info
