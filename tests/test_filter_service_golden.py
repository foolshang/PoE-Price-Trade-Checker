"""Golden regression for filter_service.generate_filter (guards shared filter code).

Each scenario runs generate_filter with network/sound/write spied and records the
filter file, every log line, debug events, the return value and the order/count of
I/O calls. Outputs must match tests/sample_data/filter_service_golden.json exactly.
Intentional change: UPDATE_GOLDEN=1 python -m pytest tests/test_filter_service_golden.py,
then review the golden diff."""
import copy
import hashlib
import json
import os
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock

import pytest

from poe_price_trade import filter_service, filter_gen, filter_output, hub_client, neversink_source, debug

_DATA = Path(__file__).parent / "sample_data"
BASE = {"poe2": (_DATA / "neversink_poe2_base.filter").read_text(encoding="utf-8"),
        "poe1": (_DATA / "neversink_poe1_base.filter").read_text(encoding="utf-8")}
GOLDEN = _DATA / "filter_service_golden.json"


def hub(fresh=True):
    return {"schema_version": 2,
            "generated_at": (datetime.now(timezone.utc) - timedelta(hours=1 if fresh else 100)).isoformat(),
            "league": "L",
            "currency": [
                {"category": "Currency", "name": "Divine Orb", "base": None, "chaos_value": 200.0},
                {"category": "Currency", "name": "Exalted Orb", "base": None, "chaos_value": 30.0},
                {"category": "Currency", "name": "Chaos Orb", "base": None, "chaos_value": 1.0},
                {"category": "Fragment", "name": "Sacrifice Fragment", "base": None, "chaos_value": 25.0},
                {"category": "Rune", "name": "Adept Rune", "base": None, "chaos_value": 0.5},
                {"category": "Rune", "name": "Iron Rune", "base": None, "chaos_value": 0.2},
                {"category": "Essence", "name": "Deafening Essence of Greed", "base": None, "chaos_value": 0.1}],
            "items": [
                {"category": "UniqueWeapon", "name": "Widowmaker", "base": "Royal Axe", "chaos_value": 300.0},
                {"category": "UniqueArmour", "name": "Kaom's Heart", "base": "Glorious Plate", "chaos_value": 80.0}]}


S = {  # name: (fg overrides, game, hub mode, base mode, extra)
    "wl_empty": ({"whitelist_enabled": True}, "poe2", "ok", "ok", {}),
    "wl_gold": ({"whitelist_enabled": True, "whitelist_gold": True}, "poe2", "ok", "ok", {}),
    "wl_gold25": ({"whitelist_enabled": True, "whitelist_gold": True, "whitelist_gold_min": 25}, "poe2", "ok", "ok", {}),
    "wl_gold_bad": ({"whitelist_enabled": True, "whitelist_gold": True, "whitelist_gold_min": "x"}, "poe2", "ok", "ok", {}),
    "wl_unique": ({"whitelist_enabled": True, "whitelist_unique_all": True}, "poe2", "boom", "ok", {}),
    "wl_cats_excl": ({"whitelist_enabled": True, "whitelist_cats_poe2": ["Rune", "Currency"],
                      "whitelist_cat_exclude_poe2": {"Rune": ["Iron Rune"]}}, "poe2", "ok", "ok", {}),
    "wl_cats_hubfail": ({"whitelist_enabled": True, "whitelist_cats_poe2": ["Rune"], "whitelist_gold": True},
                        "poe2", "boom", "ok", {}),
    "wl_cats_hubfail_only": ({"whitelist_enabled": True, "whitelist_cats_poe2": ["Rune"]}, "poe2", "boom", "ok", {}),
    "wl_gem_poe2": ({"whitelist_enabled": True,
                     "whitelist_gem_uncut_poe2": {"Uncut Skill Gem": 15, "Uncut Spirit Gem": 20},
                     "whitelist_custom_poe2": [{"name": "Heavy Belt", "rarities": ["Normal", "Magic"]}, "Sapphire"],
                     "whitelist_gold": True, "whitelist_gold_min": 10, "whitelist_unique_all": True},
                    "poe2", "ok", "ok", {}),
    "wl_gem_poe1": ({"whitelist_enabled": True, "whitelist_gem_names_poe1": ["Fireball", "Vaal Grace"],
                     "whitelist_cats_poe1": ["Currency"]}, "poe1", "ok", "ok", {}),
    "wl_write_oserr": ({"whitelist_enabled": True, "whitelist_gold": True}, "poe2", "ok", "ok",
                       {"write": OSError(9, "boom")}),
    "wl_write_exc": ({"whitelist_enabled": True, "whitelist_gold": True}, "poe2", "ok", "ok",
                     {"write": RuntimeError("x")}),
    "tier_poe2": ({}, "poe2", "ok", "ok", {}),
    "tier_poe2_sounds": ({"sound_s": "SOUND", "sound_a": "SOUND", "strictness_poe2": 0}, "poe2", "ok", "ok",
                         {"sound": True}),
    "tier_poe2_force": ({}, "poe2", "ok", "ok", {"force": True, "league": "LeagueX"}),
    "tier_poe1": ({}, "poe1", "ok", "ok", {}),
    "tier_stale": ({"staleness_hours": 24}, "poe2", "stale", "ok", {}),
    "tier_hubfail": ({}, "poe2", "boom", "ok", {}),
    "tier_nobase_hubok": ({}, "poe2", "ok", "none", {}),
    "tier_nobase_hubfail": ({}, "poe2", "boom", "none", {}),
    "tier_rules_file": ({}, "poe2", "ok", "ok", {"rules": {"tiers": [{"name": "S", "min_chaos": 5000}]}}),
    "tier_write_oserr": ({}, "poe2", "ok", "ok", {"write": OSError(13, "denied")}),
    "tier_write_valueerr": ({}, "poe2", "ok", "ok", {"write": ValueError("nothing")}),
}


def run(name, tmp):
    fg, gv, hubmode, basemode, extra = S[name]
    fg = copy.deepcopy(fg)
    app = tmp / "app"
    game = tmp / "game"
    app.mkdir(parents=True)
    fg["game_dir_" + gv] = str(game)
    if extra.get("sound"):
        snd = tmp / "snd.mp3"
        snd.write_bytes(b"ID3x")
        for k in ("sound_s", "sound_a"):
            if k in fg:
                fg[k] = str(snd)
    if "rules" in extra:
        (app / "filter_gen_rules.json").write_text(json.dumps(extra["rules"]), encoding="utf-8")
    cfg = types.SimpleNamespace(get=lambda k, d=None: fg if k == "filter_gen" else d, app_dir=lambda: app)
    calls, logs, events = [], [], []

    def get_prices(path):
        calls.append(("get_prices", path))
        if hubmode == "boom":
            raise RuntimeError("hub down")
        return hub(fresh=(hubmode != "stale"))

    def fetch(g, s, cache_dir, force=False):
        calls.append(("fetch_base_filter", g, s, cache_dir.relative_to(tmp).as_posix(), force))
        return (None, None) if basemode == "none" else (BASE[g], "tagX")

    real_load, real_copy, real_write = filter_gen.load_rules, filter_output.copy_sounds, filter_output.write_filter

    def load_rules(d):
        calls.append(("load_rules", None if d is None else d.relative_to(tmp).as_posix()))
        return real_load(d)

    def copy_sounds(d, m):
        calls.append(("copy_sounds", d.relative_to(tmp).as_posix(), dict(sorted((k, bool(v)) for k, v in m.items()))))
        return real_copy(d, m)

    def write_filter(d, sec, base_text):
        base = base_text
        calls.append(("write_filter", d.relative_to(tmp).as_posix(), hashlib.sha256(sec.encode()).hexdigest()[:12],
                      None if base is None else hashlib.sha256(base.encode()).hexdigest()[:12]))
        if "write" in extra:
            raise extra["write"]
        return real_write(d, sec, base)

    with mock.patch.object(hub_client, "get_prices", get_prices), \
         mock.patch.object(neversink_source, "fetch_base_filter", fetch), \
         mock.patch.object(filter_gen, "load_rules", load_rules), \
         mock.patch.object(filter_output, "copy_sounds", copy_sounds), \
         mock.patch.object(filter_output, "write_filter", write_filter), \
         mock.patch.object(debug, "event", lambda m: events.append(m.replace(str(tmp), "<T>"))):
        res = filter_service.generate_filter(
            cfg, gv, f"{gv}/prices/latest.json",
            force_base=bool(extra.get("force")), league=extra.get("league", ""),
            log=lambda m, t="info": logs.append((t, m.replace(str(tmp), "<T>"))))
    out = None
    f = game / "poe-checker.filter"
    if f.exists():
        out = f.read_text(encoding="utf-8")
    sounds = sorted(p.name for p in game.glob("poe-checker-*")) if game.exists() else []

    def norm(v):
        if isinstance(v, Path):
            return str(v).replace(str(tmp), "<T>").replace("\\", "/")
        if isinstance(v, dict):
            return {k: norm(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [norm(x) for x in v]
        return v
    return {"return": norm(res), "logs": [[t, m.replace("\\", "/")] for t, m in logs],
            "events": [e.replace("\\", "/") for e in events], "calls": norm(calls),
            "file_len": None if out is None else len(out),
            "file_sha256": None if out is None else hashlib.sha256(out.encode("utf-8")).hexdigest(),
            "file": out if out is not None and len(out) < 5000 else None,   # small (whitelist) files in full
            "sounds": sounds}


def _run_all(tmp_root: Path) -> dict:
    out = {}
    for name in S:
        d = tmp_root / name
        d.mkdir()
        out[name] = run(name, d)
    return out


def test_filter_service_matches_golden(tmp_path):
    got = json.loads(json.dumps(_run_all(tmp_path), sort_keys=True, default=str))
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(json.dumps(got, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                          encoding="utf-8")
        pytest.skip("golden regenerated")
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert sorted(got) == sorted(want)
    for name in want:
        assert got[name] == want[name], f"scenario {name} changed"
