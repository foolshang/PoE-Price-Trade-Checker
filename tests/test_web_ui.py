"""The web page in a real browser (Chromium via Playwright, tests/web_ui/ui.mjs): every part of the UI is driven,
screenshots are written, and the filter the page produced from its own settings is compared with the desktop
program's for the same settings. Skipped without node + playwright (`npm i` in tests/web_ui) + a Chromium."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from poe_price_trade import __version__, wl_embed
from tests.test_web_parity import body_of, desktop_file

HERE = Path(__file__).parent
UI = HERE / "web_ui"
NODE = shutil.which("node")


def _have_chrome() -> bool:
    if os.environ.get("PW_CHROME"):
        return Path(os.environ["PW_CHROME"]).exists()
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ms-playwright"
    return base.is_dir() and any(base.glob("chromium-*/chrome-win*/chrome.exe"))


pytestmark = pytest.mark.skipif(not NODE or not (UI / "node_modules" / "playwright").is_dir() or not _have_chrome(),
                                reason="node + tests/web_ui/node_modules (npm i) + a Chromium needed")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = Path(os.environ.get("WEB_UI_SHOTS") or tmp_path_factory.mktemp("webui"))
    proc = subprocess.run([NODE, str(UI / "ui.mjs"), str(out)], capture_output=True, text=True, encoding="utf-8", timeout=900)
    assert proc.returncode == 0, proc.stderr[-3000:]
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    data["out"] = Path(data["out"])
    return data


def test_every_ui_check_passes(run):
    failed = [(r["name"], r["detail"]) for r in run["results"] if not r["ok"]]
    assert not failed, failed
    assert len(run["results"]) >= 55


def test_the_page_asked_for_what_it_should(run):
    calls = run["calls"]
    assert "hub:poe2/prices/latest.json" in calls and "ns-api" in calls and "ns-file:poe2" in calls
    assert not any("trade_names" in c for c in calls)   # the names come from the snapshot only: no request, no 404
    assert not any("pathofexile.com" in c for c in calls)  # GGG's API is never called from the page (no CORS)


def test_screenshots_were_taken(run):
    shots = sorted(p.name for p in run["out"].glob("*.png"))
    assert len(shots) >= 15 and "09_result.png" in shots


def test_the_filter_the_page_made_equals_the_desktops_for_the_same_settings(run, tmp_path):
    cfg = json.loads((run["out"] / "parity" / "wl_cfg.json").read_text(encoding="utf-8"))
    web_text = (run["out"] / "parity" / "wl.filter").read_bytes().decode("utf-8").replace("\r\n", "\n")
    path = desktop_file(dict(cfg), "poe2", tmp_path, "my-wl", "whitelist")
    want = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert body_of(web_text) == body_of(want)
    a, b = wl_embed.extract(web_text), wl_embed.extract(want)
    assert a["app"] == "web-" + __version__ and b["app"] == __version__ and a["cfg"] == b["cfg"] and a["game"] == b["game"]
    # byte for byte the same settings lines once both record the same version
    assert wl_embed.embed_lines(a["cfg"], "poe2", __version__) == wl_embed.embed_lines(b["cfg"], "poe2", __version__)
