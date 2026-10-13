"""Build the site that goes to GitHub Pages: only the files the page needs, nothing else.

    python tools/build_web.py --out _site [--tag v0.13.5]

Runs tools/sync_web_py.py (web/py copies + `?v=<version>` in index.html), copies an allow-list of web/ into --out, adds
`.nojekyll`, and refuses to finish when the site's version is not the tag's or a file is missing / unexpected.
Used by .github/workflows/deploy-web.yml; run it locally to see exactly what would be published."""
from __future__ import annotations
import argparse
import fnmatch
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sync_web_py as sync  # noqa: E402
WEB = ROOT / "web"
# what a page needs to run (everything else in web/ never leaves the repo)
ALLOW = ("index.html", "app.js", "style.css", "glue.py", "js/*.js", "data/trade_names_poe1.json", "data/trade_names_poe2.json",
         "py/*.py", "py/manifest.json")
REQUIRED = ("index.html", "app.js", "style.css", "glue.py", "py/__init__.py", "py/manifest.json", "py/filter_gen.py",
            "data/trade_names_poe1.json", "data/trade_names_poe2.json")


def version_of(init: Path) -> str:
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def wanted(rel: str) -> bool:
    return any(fnmatch.fnmatchcase(rel, pat) for pat in ALLOW)


def build(out: Path, tag: str = "") -> list[str]:
    sync.main()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    copied = []
    for f in sorted(p for p in WEB.rglob("*") if p.is_file()):
        rel = f.relative_to(WEB).as_posix()
        if "__pycache__" in rel or "node_modules" in rel or not wanted(rel):
            continue
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dest)
        copied.append(rel)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    missing = [r for r in REQUIRED if not (out / r).is_file()]
    if missing:
        raise SystemExit(f"missing from the site: {missing}")
    ver = version_of(out / "py" / "__init__.py")
    src = version_of(ROOT / "poe_price_trade" / "__init__.py")
    if ver != src:
        raise SystemExit(f"site version {ver!r} != source {src!r}")
    if tag:
        want = tag.lstrip("v").split("-")[0]
        if want != ver:
            raise SystemExit(f"tag {tag} does not match the site's __version__ {ver}")
    html = (out / "index.html").read_text(encoding="utf-8")
    if f"app.js?v={ver}" not in html:
        raise SystemExit("index.html is not stamped with the version")
    return copied


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    files = build(Path(a.out).resolve(), a.tag)
    total = sum((Path(a.out) / f).stat().st_size for f in files)
    for f in files:
        print(f)
    print(f"{len(files)} files, {total // 1024} KB, version {version_of(Path(a.out) / 'py' / '__init__.py')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
