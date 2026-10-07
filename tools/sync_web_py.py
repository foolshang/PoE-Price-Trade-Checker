"""Copy the shared filter logic into web/py/ so the browser build runs the exact
same Python as the desktop apps. poe_price_trade/ stays the only source of truth.

    python tools/sync_web_py.py        (dev: run before serving web/; CI: before deploy)
"""
from __future__ import annotations
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ("filter_gen.py", "filter_core.py", "filter_style.py")


def main() -> None:
    dest = ROOT / "web" / "py"
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copyfile(ROOT / "poe_price_trade" / name, dest / name)
        print(f"web/py/{name}")


if __name__ == "__main__":
    main()
