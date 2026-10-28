# Sourced by serve.sh. No proxy is built in: if HTTPS_PROXY (or https_proxy) is set in your environment it is used only
# while it is reachable; otherwise it is dropped and the app goes direct. So one command works on and off a corporate network.
PROXY="${HTTPS_PROXY:-${https_proxy:-}}"
if [ -n "$PROXY" ]; then
  PROXY_HOSTPORT="${PROXY#*://}"; PROXY_HOSTPORT="${PROXY_HOSTPORT%%/*}"; PROXY_HOSTPORT="${PROXY_HOSTPORT##*@}"
  PROXY_HOST="${PROXY_HOSTPORT%%:*}"
  case "$PROXY_HOSTPORT" in *:*) PROXY_PORT="${PROXY_HOSTPORT##*:}" ;; *) PROXY_PORT=8080 ;; esac
  if nc -z -w 2 "$PROXY_HOST" "$PROXY_PORT" >/dev/null 2>&1; then
    export HTTPS_PROXY="$PROXY" HTTP_PROXY="$PROXY"
  else
    echo "Proxy $PROXY is not reachable from here: going direct." >&2
    unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy ALL_PROXY all_proxy
  fi
fi
unset PROXY PROXY_HOSTPORT PROXY_HOST PROXY_PORT
