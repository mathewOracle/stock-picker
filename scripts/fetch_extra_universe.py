"""Download / top up daily bars for Addendum A's independent universe U2 (docs/SWING_RESEARCH_PLAN.md).

The fixed candidate list lives in app/research/u2.py (moved there verbatim so the app and this script share it).

Needs the corporate proxy:  HTTPS_PROXY=http://sysproxy.wal-mart.com:8080 .venv/bin/python -m scripts.fetch_extra_universe
"""

from app.research import u2


def main() -> None:
    print(f"{len(u2.SYMBOLS)} candidates outside the app universe")
    missing = u2.refresh(lambda done, total, label: print(f"  [{done}/{total}] {label}", flush=True))
    have = [s for s in u2.SYMBOLS if u2.path(s).exists()]
    print(f"done: {len(have)} of {len(u2.SYMBOLS)} stored; not returned this run: {missing}")


if __name__ == "__main__":
    main()
