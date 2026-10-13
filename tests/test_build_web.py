"""tools/build_web.py: the site that goes to GitHub Pages holds only what the page needs, and is refused when it is not the
tag's version. The deploy workflow files keep the guarantees the release relies on."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

import pytest

from poe_price_trade import __version__

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_web  # noqa: E402


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site") / "_site"
    files = build_web.build(out, f"v{__version__}")
    return out, files


def test_only_the_pages_files_are_published(site):
    out, files = site
    assert {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()} == set(files) | {".nojekyll"}
    py_top = {f for f in files if f.endswith(".py") and "/" not in f}
    assert py_top == {"glue.py"}                                  # no other program source beside web/py/
    assert not [f for f in files if f.split("/")[0] in ("tests", "tools", "release", "poe_price_trade", "node_modules", "build")]
    assert {f for f in files if f.startswith("py/")} == {f"py/{n}" for n in build_web.sync.FILES} | {"py/manifest.json"}


def test_every_script_of_index_html_is_in_the_site(site):
    import re
    out, _ = site
    html = (out / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r'(?:src|href)="((?:js/\w+\.js|app\.js|style\.css))\?v=([^"]+)"', html)
    assert len(refs) >= 9 and all(v == __version__ for _, v in refs)
    assert all((out / r).is_file() for r, _ in refs)


def test_a_tag_that_is_not_the_version_is_refused(tmp_path):
    with pytest.raises(SystemExit):
        build_web.build(tmp_path / "x", "v99.0.0")
    assert build_web.build(tmp_path / "y", f"v{__version__}-test")      # a suffix is ignored, like the exe check


def test_the_workflows(tmp_path):
    yaml = pytest.importorskip("yaml")
    wf = ROOT / ".github" / "workflows"
    deploy = yaml.safe_load((wf / "deploy-web.yml").read_text(encoding="utf-8"))
    release = yaml.safe_load((wf / "release.yml").read_text(encoding="utf-8"))
    triggers = deploy.get(True) or deploy["on"]                     # YAML 1.1 reads `on` as True
    assert "workflow_call" in triggers and "workflow_dispatch" in triggers
    web = release["jobs"]["web"]
    assert web["uses"] == "./.github/workflows/deploy-web.yml" and "'-'" in web["if"]      # a prerelease never deploys
    build = release["jobs"]["build-release"]
    assert build["needs"] == "web" and "cancelled" in build["if"]                          # the exe ships when the deploy failed
    readme = [s for s in build["steps"] if s.get("name") == "Update README in public repo"][0]
    assert "needs.web.result == 'success'" in readme["if"] and "'-'" in readme["if"]
