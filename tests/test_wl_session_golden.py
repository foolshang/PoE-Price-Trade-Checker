"""The Whitelist tab's status messages come from wl_session (shared with the web page). This pins what the desktop
window says and does when a filter file is opened - the lines, the sound variables, the filter name, the model -
so moving the messages into Python did not change the program (the golden file was captured from the code before
the move: tests/sample_data/golden_open_messages.json). GOLDEN_WRITE=1 rewrites it."""
from __future__ import annotations
import json
import os
import tkinter as tk
from pathlib import Path

import pytest

from poe_price_trade import filter_core, filter_style, wl_embed
from poe_price_trade.config import AppConfig
from tests.test_filter_vocabulary import lint  # noqa: F401
from tests.test_wl_import import _drop, old_text
from tests.test_wl_phase3b import _generate, cfg, data, make_window, model, root  # noqa: F401  (fixtures)

GOLDEN = Path(__file__).parent / "sample_data" / "golden_open_messages.json"


def log_lines(win) -> list:
    return [l for l in win._log_text.get("1.0", tk.END).split("\n") if l.strip()]


def snapshot(win, ret, before=0) -> dict:
    m = win._model
    return {"ret": ret, "log": log_lines(win)[before:], "name": win._vars["filter_name_whitelist"].get(),
            "sounds": {k: Path(((m.tier_style.get(k) or {}).get("sound") or {}).get("file", "")).name for k in ("S", "A", "B")},
            "opened": win._opened_path.name if win._opened_path else None,
            "cfg": json.loads(json.dumps(m.cfg(), sort_keys=True))}


def scenarios(root, cfg, tmp_path) -> dict:
    out = {}

    def fresh(game, name="PoeFilterGen"):
        return make_window(root, AppConfig(name), game)

    # an embedded file (the program's own) - normal open
    m = model("poe1")
    m.set_row("Currency", "Chaos Orb", "S")
    m.gold, m.gold_min = True, 21
    emb = _generate(m.to_config({}), "poe1", tmp_path, name="embedded")["path"]
    win = fresh("poe1")
    out["embedded_ok"] = snapshot(win, win.open_filter(emb))
    # an embedded file of v0.10.2 (new lists filled with C, no record of the lists)
    m2 = model("poe2")
    for n in m2._names_of("Relic"):
        m2.item_tier[n] = "C"
    fg = m2.to_config({})
    fg.pop("wl_lists_poe2")
    fg.pop("wl_tier_format")                                   # v0.10.2 had no tier D: its C is the hidden tier
    legacy = _generate(fg, "poe2", tmp_path, name="legacy-c")["path"]
    win = fresh("poe2", "g2")
    out["embedded_legacy_relic_c"] = snapshot(win, win.open_filter(legacy))
    # old files (no settings)
    for key, name, game, sounds in (
            ("old_v2_poe2", "v2_poe2_checker_whitelist", "poe2", ("sound-S.mp3", "sound-A.mp3")),
            ("old_v2_poe2_no_sounds", "v2_poe2_bus", "poe2", ()),
            ("old_v1_poe1", "v1_poe1_checker_whitelist", "poe1", ()),
            ("old_v2_poe1", "v2_poe1_wl_sample", "poe1", ())):
        f = _drop(tmp_path / key, name, game, sounds=sounds)
        win = fresh(game, "g_" + key)
        out[key] = snapshot(win, win.open_filter(f))
    # refusals
    wrong = _drop(tmp_path / "wrong", "v2_poe2_bus", "poe2")
    win = fresh("poe1", "g_wrong")
    out["old_wrong_game"] = snapshot(win, win.open_filter(wrong))
    win = fresh("poe1", "g_wrong2")
    out["embedded_wrong_game"] = snapshot(win, win.open_filter(_generate({}, "poe2", tmp_path, name="p2")["path"]))
    for key, body in (("foreign", "Show\n    Class \"Gems\"\n"), ("tier_file", filter_core.TIER_HEADER + "Show\n")):
        f = tmp_path / f"{key}.filter"
        f.write_text(body, encoding="utf-8")
        win = fresh("poe1", "g_" + key)
        out[key] = snapshot(win, win.open_filter(f))
    # the item lists are not loaded yet
    f = _drop(tmp_path / "nodata", "v2_poe2_bus", "poe2")
    win = fresh("poe2", "g_nodata")
    win._wl_data = None
    out["old_no_data"] = snapshot(win, win.open_filter(f))
    # a name that cannot be a filter name
    bad = tmp_path / "bad<name>.filter"
    try:
        bad.write_text(_generate({}, "poe1", tmp_path, name="okname")["path"].read_text(encoding="utf-8"), encoding="utf-8")
        win = fresh("poe1", "g_bad")
        out["bad_name"] = snapshot(win, win.open_filter(bad))
    except OSError:
        pass
    # sound already set to the same file: not told again
    f = _drop(tmp_path / "samesound", "v2_poe2_checker_whitelist", "poe2", sounds=("sound-S.mp3", "sound-A.mp3"))
    win = fresh("poe2", "g_same")
    win._model.tier_style["S"] = {"sound": {"kind": "file", "id": 1, "file": str(f.parent / "sound-S.mp3"), "volume": 300}}
    out["old_sound_already_set"] = snapshot(win, win.open_filter(f))
    return out


def normalise(d, tmp_path) -> dict:
    """File names / paths that depend on the temporary folder, and the program version, do not matter."""
    from poe_price_trade import __version__
    text = json.dumps(d, ensure_ascii=False).replace(str(tmp_path).replace("\\", "\\\\"), "TMP")
    return json.loads(text.replace(f"ค่าฝังจากรุ่น {__version__}", "ค่าฝังจากรุ่น VER"))


def test_opening_files_says_and_does_what_it_did_before_the_messages_moved_to_python(root, cfg, tmp_path):
    got = normalise(scenarios(root, cfg, tmp_path), tmp_path)
    if os.environ.get("GOLDEN_WRITE"):
        GOLDEN.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    want = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert set(got) == set(want)
    for k in want:
        assert got[k] == want[k], k
