"""filter_core - pure core shared by desktop and the web (Pyodide) build."""
from __future__ import annotations
import ast
import subprocess
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from poe_price_trade import filter_core, neversink_source

_CORE = Path(filter_core.__file__)
_BANNED = {"urllib", "ctypes", "shutil", "tkinter", "poe_price_trade.config", "poe_price_trade.filter_output",
           "poe_price_trade.hub_client", "poe_price_trade.neversink_source"}


def test_core_imports_only_stdlib_and_filter_gen():
    tree = ast.parse(_CORE.read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(("." * n.level) + (n.module or ""))
            if n.level:
                mods |= {"." + a.name for a in n.names}
    assert mods <= {"__future__", "typing", ".", ".filter_gen"}, mods


def test_core_imports_with_io_modules_blocked():
    """Fresh interpreter: stdlib already loaded, then every I/O module is made
    unimportable (None in sys.modules) before filter_core is imported and used."""
    code = (
        "import sys, copy, hashlib, json, logging, re, collections, datetime, pathlib, typing\n"
        "for m in %r: sys.modules[m] = None\n"
        "from poe_price_trade import filter_core\n"
        "assert filter_core.compose_filter_body('a', None) == 'a'\n"
        "r = filter_core.build_filter_text({'whitelist_enabled': True, 'whitelist_gold': True}, 'poe2')\n"
        "assert r['mode'] == 'whitelist' and 'Gold' in r['generated_section']\n"
        "assert filter_core.neversink_file_url('poe2', 't', 2).startswith('https://raw.')\n"
        % sorted(_BANNED | {"winrt", "pystray"})
    )
    root = _CORE.parent.parent
    res = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr


def test_neversink_urls_match_what_urllib_would_build():
    for game in ("poe1", "poe2"):
        for strictness in range(len(filter_core.NEVERSINK_LEVELS)):
            fn = filter_core.neversink_filename(game, strictness)
            assert filter_core._quote(fn) == urllib.parse.quote(fn)
            assert filter_core.neversink_file_url(game, "1.2.3", strictness) == (
                f"https://raw.githubusercontent.com/{filter_core.NEVERSINK_REPO[game]}/1.2.3/"
                + urllib.parse.quote(fn))
        assert filter_core.neversink_latest_api_url(game) == (
            f"https://api.github.com/repos/{filter_core.NEVERSINK_REPO[game]}/releases/latest")
    assert filter_core.neversink_filename("poe2", 0) == "NeverSink's filter 2 - 0-SOFT.filter"
    assert neversink_source._filename("poe1", 2) == "NeverSink's filter - 2-SEMI-STRICT.filter"


def test_compose_filter_body():
    assert filter_core.compose_filter_body("SEC", None) == "SEC"
    assert filter_core.compose_filter_body("SEC", "BASE") == "SEC\n# ===== base filter below =====\nBASE"
    assert filter_core.compose_filter_body("", "BASE") == "\n# ===== base filter below =====\nBASE"
    with pytest.raises(ValueError, match="nothing to write — both hub and base filter sources unavailable"):
        filter_core.compose_filter_body("  \n", None)


def test_plan_fetch():
    assert filter_core.plan_fetch({}, "poe2") == {"mode": "tier", "hub": True, "neversink": True}
    wl = {"whitelist_enabled": True}
    assert filter_core.plan_fetch(wl, "poe2") == {"mode": "whitelist", "hub": False, "neversink": False}
    assert filter_core.plan_fetch(dict(wl, whitelist_cats_poe2=["Rune"]), "poe2")["hub"] is True
    assert filter_core.plan_fetch(dict(wl, whitelist_cats_poe2=["Rune"]), "poe1")["hub"] is False


def _hub(hours_old=1):
    return {"schema_version": 2, "league": "L",
            "generated_at": (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat(),
            "currency": [
                {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 200.0},
                {"category": "Rune", "name": "Adept Rune", "base": None, "chaos_value": 0.5},
                {"category": "Rune", "name": "Iron Rune", "base": None, "chaos_value": 0.2}],
            "items": []}


_BASE = ('Show # %D5 $type->currency $tier->t1\n\tBaseType == "Chaos Orb"\n\tSetFontSize 40\n\n'
         'Show # %D1\n\tBaseType == "Divine Orb"\n\tSetFontSize 30\n')


def test_whitelist_build_with_and_without_hub():
    cfg = {"whitelist_enabled": True, "whitelist_cats_poe2": ["Rune"],
           "whitelist_cat_exclude_poe2": {"Rune": ["Iron Rune"]}, "whitelist_gold": True,
           "whitelist_gold_min": 25}
    logs = []
    res = filter_core.build_filter_text(cfg, "poe2", hub_data=_hub(), log=lambda m, t="info": logs.append(m))
    assert res["mode"] == "whitelist" and res["base_text"] is None and res["count"] == 2
    assert '"Adept Rune"' in res["generated_section"] and "Iron Rune" not in res["generated_section"]
    assert "StackSize >= 25" in res["generated_section"] and logs == []
    res = filter_core.build_filter_text(cfg, "poe2", hub_data=None)      # hub down: categories skipped
    assert res["count"] == 1 and "Adept Rune" not in res["generated_section"]


def test_whitelist_nothing_selected_returns_none_and_warns():
    logs = []
    assert filter_core.build_filter_text({"whitelist_enabled": True}, "poe2",
                                         log=lambda m, t="info": logs.append((t, m))) is None
    assert [t for t, _ in logs] == ["warn"]


def test_tier_build_merges_into_base_and_reports_state():
    logs, sounds = [], []
    res = filter_core.build_filter_text(
        {}, "poe2", hub_data=_hub(), base_text=_BASE, base_tag="t1",
        copy_sounds_fn=lambda m: sounds.append(m) or {},
        log=lambda m, t="info": logs.append((t, m)))
    assert res["mode"] == "tier" and res["base_tag"] == "t1"
    assert res["signature"] and res["mapping"]
    assert sounds == [{"S": None, "A": None, "B": None}]
    assert filter_core.compose_filter_body(res["generated_section"], res["base_text"])
    assert len(logs) == 1 and logs[0][0] in ("ok", "warn")


def test_tier_stale_or_missing_hub_leaves_base_alone():
    logs = []
    res = filter_core.build_filter_text({}, "poe2", hub_data=_hub(hours_old=100), base_text=_BASE,
                                        base_tag="t", log=lambda m, t="info": logs.append(t))
    assert res["generated_section"] == "" and res["base_text"] == _BASE and res["signature"] is None
    assert logs == ["warn"]
    res = filter_core.build_filter_text({}, "poe2", hub_data=None, base_text=_BASE, base_tag="t")
    assert res["generated_section"] == "" and res["mapping"] is None


def test_tier_rules_loader_only_called_for_fresh_hub():
    calls = []

    def loader():
        calls.append(1)
        return filter_core.filter_gen.load_rules(None)
    filter_core.build_filter_text({}, "poe2", hub_data=_hub(hours_old=100), base_text=_BASE, rules_loader=loader)
    filter_core.build_filter_text({}, "poe2", hub_data=None, base_text=_BASE, rules_loader=loader)
    assert calls == []
    filter_core.build_filter_text({}, "poe2", hub_data=_hub(), base_text=_BASE, rules_loader=loader)
    assert calls == [1]
