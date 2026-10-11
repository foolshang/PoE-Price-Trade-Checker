"""Open old whitelist filters of this program (no embedded settings): v1 ("show only") and v2 (tiers, before the
settings were embedded) files are read back block by block into settings. Samples are real files from Winai's
game folders (tests/sample_data/old_filters). Opening one and generating again must keep every tier / look the
old file had; what the file cannot say is named in the notes."""
from __future__ import annotations
import gzip
import tkinter as tk
from pathlib import Path

import pytest

from poe_price_trade import filter_style, filter_whitelist as w, wl_embed, wl_import
from poe_price_trade.wl_model import WlModel
from tests.test_filter_vocabulary import lint
from tests.test_wl_phase3b import _generate, cfg, data, make_window, model, root       # noqa: F401  (fixtures)

OLD = Path(__file__).parent / "sample_data" / "old_filters"
V2 = [("v2_poe1_wl_sample", "poe1"), ("v2_poe2_checker_whitelist", "poe2"), ("v2_poe2_bus", "poe2"),
      ("v2_poe2_wl_sample", "poe2")]


def old_text(name):
    with gzip.open(OLD / f"{name}.filter.gz", "rt", encoding="utf-8") as fh:
        return fh.read()


def look(lines):
    return filter_style.lines_to_style(lines or [])


def differences(a: wl_import.Summary, b: wl_import.Summary) -> list:
    """What the old file (a) says that the regenerated one (b) does not - the report of the mismatches."""
    out = []
    for f in ("shown", "unique_bases", "tablet_own", "classes"):
        x, y = getattr(a, f), getattr(b, f)
        out += [f"{f}: {k} {x.get(k)} -> {y.get(k)}" for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)]
    for f in ("gold_on", "gold_min", "map_on", "map_tier", "map_rarity", "gem_uncut", "gem_names", "custom"):
        if getattr(a, f) != getattr(b, f):
            out.append(f"{f}: {getattr(a, f)!r} -> {getattr(b, f)!r}")
    for t in ("S", "A", "B"):
        if t in a.tier_lines and look(a.tier_lines[t]) != look(b.tier_lines.get(t)):
            out.append(f"look of tier {t}")
    for f in ("gold_block", "tablet_block", "map_block"):
        x, y = getattr(a, f), getattr(b, f)
        if x is not None and (y is None or look(x.style) != look(y.style)):
            out.append(f"look of {f}")
    new_gear = {}
    for g in b.gear:
        new_gear[g] = new_gear.get(g, 0) + 1
    old_gear = {}
    for g in a.gear:
        old_gear[g] = old_gear.get(g, 0) + 1
    out += [f"gear block lost or changed: {g[0]}" for g in old_gear if new_gear.get(g, 0) < old_gear[g]]
    return out


def reopen(name, game):
    hub, base, extra = data(game)
    cur = WlModel(game)
    cur.set_data(hub, base, extra)
    res = wl_import.read(old_text(name), game, cur)
    return res, res["model"].build()["text"]


@pytest.mark.parametrize("name,game", V2)
def test_a_v2_file_reads_back_and_generates_the_same_tiers_and_looks(name, game):
    res, new = reopen(name, game)
    assert res["version"] == "v2"
    assert differences(res["summary"], wl_import.summarize(new)) == []
    assert lint(new, data(game)[1]) == []
    assert wl_embed.classify(wl_embed.embed(new, res["model"].cfg(), game)) == "ok"       # generate -> embedded settings


@pytest.mark.parametrize("name,game", V2)
def test_a_v2_file_reopened_twice_is_stable(name, game):
    """read -> build -> embed -> open the embedded file gives the same model and the same file."""
    res, new = reopen(name, game)
    again = WlModel.from_config(wl_embed.extract(wl_embed.embed(new, res["model"].cfg(), game))["cfg"], game)
    again.set_data(*data(game))
    assert again.build()["text"] == new


def test_v2_new_blocks_the_old_file_lacks_are_hidden_and_reported():
    res, _new = reopen("v2_poe1_wl_sample", "poe1")
    notes = " ".join(res["notes"])
    assert "Runegraft" in notes and "29 block" in notes                   # new lists / the generic gems
    assert res["model"].cat_tier[w.gear_cat("gems")] == "C"


def test_v1_file_keeps_exactly_the_names_it_showed():
    res, new = reopen("v1_poe1_checker_whitelist", "poe1")
    assert res["version"] == "v1"
    sm = res["summary"]
    shown_new = set(wl_import.summarize(new).shown)
    universe = set(res["model"]._names)
    assert sm.names_v1 and (sm.names_v1 & universe) <= shown_new
    assert not (shown_new - sm.names_v1)                                  # nothing the old file hid is shown now
    assert res["model"].gold and res["model"].gold_min == 10
    notes = " ".join(res["notes"])
    assert "v1" in notes and "สไตล์ tier S" in notes and "map" in notes
    assert lint(new, data("poe1")[1]) == []


def test_unreadable_parts_keep_the_remembered_values():
    hub, base, extra = data("poe1")
    cur = WlModel("poe1")
    cur.set_data(hub, base, extra)
    cur.set_style_from_editor("S", dict(cur.effective_style("S"), size=33))
    res = wl_import.read(old_text("v1_poe1_checker_whitelist"), "poe1", cur)
    assert res["model"].tier_style["S"]["size"] == 33                     # no tier block in a v1 file: kept
    assert "สไตล์ tier S" in " ".join(res["notes"])
    cur.gold, cur.gold_min = False, 0                                     # what the file says wins over what was remembered
    assert wl_import.read(old_text("v1_poe1_checker_whitelist"), "poe1", cur)["model"].gold_min == 10


def test_not_a_whitelist_file_of_ours_is_not_read():
    cur = model("poe1")
    assert wl_import.read("Show\n    Class \"Gems\"\n", "poe1", cur) is None
    assert wl_import.read("# Generated by PoE Price & Trade Checker\nShow\n", "poe1", cur) is None
    assert wl_import.guess_game(old_text("v2_poe2_bus")) == "poe2"


def test_stackable_names_the_old_file_showed_stay_shown_at_every_stack():
    """The old engine wrote no StackSize: a card NeverSink shows from 3 must keep showing at 1 (minimum 1)."""
    hub, base, extra = data("poe1")
    cur = WlModel("poe1")
    cur.set_data(hub, base, extra)
    card = next(iter(sorted(cur._stack_defaults)))
    text = old_text("v2_poe1_wl_sample")
    text = text.replace("# tier B\nShow\n    BaseType == ", f'# tier B\nShow\n    BaseType == "{card}" ', 1)
    res = wl_import.read(text, "poe1", cur)
    assert res["model"].item_stack.get(card) == 1
    assert "StackSize" in " ".join(res["notes"])
    assert f'"{card}"' in res["model"].build()["text"].split("# tier B")[1].split("\n\n")[0]


def _drop(root_dir: Path, name: str, game: str, sounds=()) -> Path:
    folder = root_dir / "old" / game
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{name}.filter"
    f.write_bytes(old_text(name).encode("utf-8"))
    for s in sounds:
        (folder / s).write_bytes(b"x")
    return f


def test_window_opens_an_old_v2_file_then_generate_writes_embedded_settings(root, cfg, tmp_path):
    f = _drop(tmp_path, "v2_poe2_checker_whitelist", "poe2",
              sounds=("sound-S.mp3", "sound-A.mp3"))
    win = make_window(root, cfg, "poe2")
    assert win.open_filter(f) is True
    log = win._log_text.get("1.0", tk.END)
    assert "ไม่มีค่าที่ฝังไว้" in log
    assert win._vars["filter_name_whitelist"].get() == "v2_poe2_checker_whitelist"
    assert win._opened_path == f and win._model.loaded and win._panel.model is win._model
    assert Path(win._vars["sound_s"].get()).name == "sound-S.mp3"
    assert win._model.gold and win._model.gold_min == 500 and win._model.map_on and win._model.map_tier == 15
    res = _generate(win._save("whitelist"), "poe2", tmp_path / "gen", name="reopened")
    new = res["path"].read_text(encoding="utf-8")
    assert wl_embed.classify(new) == "ok"
    assert differences(wl_import.summarize(old_text("v2_poe2_checker_whitelist")), wl_import.summarize(new)) == []


def test_window_opens_a_v1_file_and_refuses_the_wrong_game(root, cfg, tmp_path):
    f1 = _drop(tmp_path, "v1_poe1_checker_whitelist", "poe1")
    f2 = _drop(tmp_path, "v2_poe2_bus", "poe2")
    win = make_window(root, cfg, "poe1")
    assert win.open_filter(f2) is False and "POE2" in win._log_text.get("1.0", tk.END)
    assert win.open_filter(f1) is True
    assert "v1" in win._log_text.get("1.0", tk.END) and win._model.gold_min == 10


def test_opening_an_old_file_waits_for_the_item_lists(root, cfg, tmp_path):
    f = _drop(tmp_path, "v2_poe2_bus", "poe2")
    win = make_window(root, cfg, "poe2")
    win._wl_data = None
    assert win.open_filter(f) is False and "ยังโหลดรายการ" in win._log_text.get("1.0", tk.END)
