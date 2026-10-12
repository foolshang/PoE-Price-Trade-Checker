"""Copy the shared filter logic into web/py/ so the browser build runs the exact
same Python as the desktop apps. poe_price_trade/ stays the only source of truth.

    python tools/sync_web_py.py        (dev: run before serving web/; CI: before deploy)
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ("__init__.py", "filter_gen.py", "filter_core.py", "filter_style.py", "filter_whitelist.py", "wl_embed.py", "wl_model.py",
         "wl_import.py", "wl_session.py")


def main() -> None:
    dest = ROOT / "web" / "py"
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(ROOT / "poe_price_trade" / name, dest / name)
        print(f"web/py/{name}")
    # the page loads exactly these files into Pyodide (a new shared module only needs to be added to FILES)
    (dest / "manifest.json").write_text(json.dumps({"files": list(FILES)}), encoding="utf-8")


if __name__ == "__main__":
    main()
