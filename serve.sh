#!/bin/sh
# Start the stock picker. Usage: ./serve.sh [india|us|crypto] [port]
#   ./serve.sh            India + US + Crypto in one service on 61287, with market tabs at the top (app/gateway.py)
#   ./serve.sh 61290      the same, on 61290
#   ./serve.sh india      India only on 61287     ./serve.sh us   US only on 61288     ./serve.sh crypto   Crypto only on 61289
#   ./serve.sh us 61299   US only on 61299
# The combined service runs each market's engine as an internal worker (India 61291, US 61292, Crypto 61293; override
# with SP_INDIA_PORT / SP_US_PORT / SP_CRYPTO_PORT). Each market keeps its own data dir (data/, data-us/, data-crypto/),
# so evidence never mixes.
# No proxy is built in. Export HTTPS_PROXY yourself on a network that needs one; it is used only while reachable
# (scripts/proxy_env.sh), so the same command works on and off a corporate network.
cd "$(dirname "$0")" || exit 1

busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

case "$1" in
  us|US)            MARKET=us;     DEFAULT_PORT=61288; shift ;;
  india|INDIA)      MARKET=india;  DEFAULT_PORT=61287; shift ;;
  crypto|CRYPTO)    MARKET=crypto; DEFAULT_PORT=61289; shift ;;
  *)                MARKET=all;    DEFAULT_PORT=61287 ;;
esac
PORT="${1:-$DEFAULT_PORT}"

if busy "$PORT"; then
  echo "Port $PORT is busy. Pick another: ./serve.sh $([ "$MARKET" = all ] || echo "$MARKET ")$((PORT + 10))" >&2
  exit 1
fi

. scripts/proxy_env.sh

if [ "$MARKET" = all ]; then
  for WORKER_PORT in "${SP_INDIA_PORT:-61291}" "${SP_US_PORT:-61292}" "${SP_CRYPTO_PORT:-61293}"; do
    if busy "$WORKER_PORT"; then
      echo "Worker port $WORKER_PORT is busy (set SP_INDIA_PORT / SP_US_PORT / SP_CRYPTO_PORT to move it)." >&2
      exit 1
    fi
  done
  echo "Stock picker (India + US + Crypto) -> http://127.0.0.1:$PORT"
  exec .venv/bin/uvicorn app.gateway:app --port "$PORT" --log-level info
fi

export STOCK_PICKER_MARKET="$MARKET"
APP=$(.venv/bin/python -c "from app.market import MARKET; print(MARKET.worker)")   # the profile knows its app
echo "Stock picker ($MARKET) -> http://127.0.0.1:$PORT"
exec .venv/bin/uvicorn "$APP" --port "$PORT" --log-level info
