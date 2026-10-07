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
    assert mods <= {"__future__", "typing", "re", ".", ".filter_gen", ".filter_style", ".filter_whitelist"}, mods


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
    with pytest.raises(ValueError, match="nothing to write — no NeverSink base filter available"):
        filter_core.compose_filter_body("  \n", None)


def test_plan_fetch():
    assert filter_core.plan_fetch({}, "poe2") == {"mode": "tier", "hub": False, "neversink": True}
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


def test_tier_mode_is_neversinks_base_plus_header_and_never_looks_at_prices():
    for hub in (None, _hub(), _hub(hours_old=500)):                       # whatever the hub holds is irrelevant
        res = filter_core.build_filter_text({}, "poe2", hub_data=hub, base_text=_BASE, base_tag="t1")
        assert res == {"mode": "tier", "generated_section": filter_core.TIER_HEADER, "base_text": _BASE,
                       "base_tag": "t1"}
    body = filter_core.compose_filter_body(filter_core.TIER_HEADER, _BASE)
    assert body == filter_core.TIER_HEADER + "\n# ===== base filter below =====\n" + _BASE


def test_tier_mode_without_a_base_filter_has_nothing_to_write():
    res = filter_core.build_filter_text({}, "poe2", hub_data=_hub(), base_text=None, base_tag=None)
    assert res["generated_section"] == "" and res["base_text"] is None
    with pytest.raises(ValueError):
        filter_core.compose_filter_body(res["generated_section"], res["base_text"])


def test_tier_mode_adds_custom_sounds_only_through_the_copied_names():
    logs, asked = [], []
    base = ('Show # $type->currency $tier->t1\n\tBaseType == "Divine Orb"\n\tPlayAlertSound 6 300\n\n'
            'Show # $type->6l $tier->x\n\tLinkedSockets 6\n\tPlayAlertSound 6 300\n')
    res = filter_core.build_filter_text(
        {"sound_s": "My Ping.MP3"}, "poe2", base_text=base, base_tag="t",
        copy_sounds_fn=lambda m: asked.append(m) or {"S": "poe-checker-S.MP3"},
        log=lambda m, t="info": logs.append((t, m)))
    assert asked == [{"S": "My Ping.MP3", "A": None, "B": None, "Q": None}]
    assert res["base_text"].count('CustomAlertSoundOptional "poe-checker-S.MP3" 300') == 1    # not on the 6-link block
    assert "My Ping" not in res["base_text"] and len(logs) == 1 and logs[0][0] == "ok"
    none = filter_core.build_filter_text({}, "poe2", base_text=base, base_tag="t", copy_sounds_fn=lambda m: {})
    assert none["base_text"] == base


def test_real_base_files_no_sounds_output_is_header_plus_base_byte_for_byte():
    from pathlib import Path
    for game, name in (("poe1", "neversink_poe1_base.filter"), ("poe2", "neversink_poe2_base.filter")):
        base = (Path(__file__).parent / "sample_data" / name).read_text(encoding="utf-8")
        res = filter_core.build_filter_text({"strictness_" + game: 2}, game, base_text=base, base_tag="t")
        assert filter_core.compose_filter_body(res["generated_section"], res["base_text"]) == (
            filter_core.TIER_HEADER + "\n# ===== base filter below =====\n" + base)
