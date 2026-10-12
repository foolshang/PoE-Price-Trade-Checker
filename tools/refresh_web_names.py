"""Refresh the names snapshot the web page ships (web/data/trade_names_<game>.json) from GGG's trade data.

    python tools/refresh_web_names.py

The page cannot call GGG's API itself (no CORS), so it uses the hub's `{game}/trade_names.json` when that exists and
this snapshot otherwise. Run it before a web release; it refuses to write a list that shrank by more than 20%."""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from poe_price_trade import trade_names  # noqa: E402


def main() -> int:
    out_dir = ROOT / "web" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    code = 0
    for game, url in trade_names.URLS.items():
        req = urllib.request.Request(url, headers=trade_names._HEADERS)
        names = sorted(trade_names.names_from_payload(json.loads(urllib.request.urlopen(req, timeout=20).read())))
        path = out_dir / f"trade_names_{game}.json"
        old = len(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else 0
        if not names or (old and len(names) < old * 0.8):
            print(f"{game}: got {len(names)} names (had {old}) - not written")
            code = 1
            continue
        path.write_text(json.dumps(names, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{game}: {len(names)} names (had {old})")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
