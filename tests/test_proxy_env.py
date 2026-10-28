"""serve.sh has no built-in proxy: an exported one is used only while reachable, so the same command works on and off
a corporate network (off it, the old hardcoded default made every Yahoo refresh fail)."""

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
needs_nc = pytest.mark.skipif(shutil.which("nc") is None, reason="nc (netcat) is how the script probes the proxy")


def run_proxy_env(**proxy_vars) -> tuple[str, str, str]:
    """Source scripts/proxy_env.sh in a clean environment; returns (HTTPS_PROXY, HTTP_PROXY, stderr), 'unset' if absent."""
    env = {"PATH": os.environ["PATH"], **proxy_vars}
    result = subprocess.run(["sh", "-c", '. scripts/proxy_env.sh; printf "%s|%s" "${HTTPS_PROXY-unset}" "${HTTP_PROXY-unset}"'],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    https, http = result.stdout.split("|")
    return https, http, result.stderr


def test_nothing_is_set_when_you_did_not_ask_for_a_proxy():
    assert run_proxy_env() == ("unset", "unset", "")


@needs_nc
def test_a_proxy_you_exported_is_used_while_it_is_reachable():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        assert run_proxy_env(HTTPS_PROXY=url) == (url, url, "")
        assert run_proxy_env(https_proxy=url)[:2] == (url, url)            # the lower-case spelling counts too


@needs_nc
@pytest.mark.parametrize("dead", ["http://sysproxy.invalid:8080", "http://127.0.0.1:1"])   # unresolvable host, closed port
def test_an_unreachable_proxy_is_dropped_with_a_notice_so_the_app_goes_direct(dead):
    https, http, stderr = run_proxy_env(HTTPS_PROXY=dead, HTTP_PROXY=dead)
    assert (https, http) == ("unset", "unset") and "going direct" in stderr


def test_no_corporate_proxy_is_hardcoded_anywhere_in_the_launcher():
    for script in ("serve.sh", "scripts/proxy_env.sh"):
        text = (ROOT / script).read_text().lower()
        assert "sysproxy" not in text and "wal-mart" not in text
