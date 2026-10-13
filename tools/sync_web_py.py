"""Copy the shared filter logic into web/py/ so the browser build runs the exact
same Python as the desktop apps. poe_price_trade/ stays the only source of truth.

    python tools/sync_web_py.py        (dev: run before serving web/; CI: before deploy)
"""
from __future__ import annotations
import json
import re
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
    stamp_index()


def version() -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', (ROOT / "poe_price_trade" / "__init__.py").read_text(encoding="utf-8"))
    return m.group(1) if m else "0"


_ASSET = re.compile(r'((?:src|href)=")((?:js/\w+\.js)|app\.js|style\.css)(?:\?v=[^"]*)?(")')


def stamp_index() -> None:
    """The page's own scripts / stylesheet carry `?v=<program version>` in index.html: a browser that kept an older copy of one of
    them (a plain static server sends no Cache-Control, so browsers keep files for hours) cannot mix two versions of the page."""
    p = ROOT / "web" / "index.html"
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    out = _ASSET.sub(lambda m: f"{m.group(1)}{m.group(2)}?v={version()}{m.group(3)}", text)
    if out != text:
        p.write_bytes(out.encode("utf-8"))
        print("web/index.html (asset versions)")


if __name__ == "__main__":
    main()
