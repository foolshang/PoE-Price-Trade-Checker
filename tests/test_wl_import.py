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
from poe_price_trade.config import AppConfig
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


def differences(a: wl_import.Summary, b: wl_import.Summary, fresh=frozenset(), skip_bases=frozenset()) -> list:
    """What the old file (a) says that the regenerated one (b) does not - the report of the mismatches.
    skip_bases = unique bases the import itself named as not reproducible (a name on two bases)."""
    out = []
    for f in ("shown", "unique_bases", "tablet_own"):
        x, y = getattr(a, f), getattr(b, f)
        out += [f"{f}: {k} {x.get(k)} -> {y.get(k)}" for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)
                and not (f == "shown" and k not in x and k in fresh)
                and not (f == "unique_bases" and k in skip_bases)
                and not w.bad_name(k)]                    # an old file may carry names that are never written any more
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
    # (gear blocks and special classes are NeverSink's own blocks now: nothing of an old file is carried over)
    return out


def _fresh(m, game):
    """Names of the lists that did not exist when the old file was written."""
    cats = {c for c, _p in w.NAMED_CATEGORIES.get(game, [])}
    return {n for n, c in m._names.items() if c in cats}


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
    assert differences(res["summary"], wl_import.summarize(new), _fresh(res["model"], game),
                       res["unique_mismatch"]) == []
    assert len(res["unique_mismatch"]) <= 20                       # a name on two bases: only a handful, and named in the notes
    assert (not res["unique_mismatch"]) or any("ไม่ตรงไฟล์เดิม" in n for n in res["notes"])
    assert lint(new, data(game)[1]) == []
    assert wl_embed.classify(wl_embed.embed(new, res["model"].cfg(), game)) == "ok"       # generate -> embedded settings


@pytest.mark.parametrize("name,game", V2)
def test_a_v2_file_reopened_twice_is_stable(name, game):
    """read -> build -> embed -> open the embedded file gives the same model and the same file."""
    res, new = reopen(name, game)
    again = WlModel.from_config(wl_embed.extract(wl_embed.embed(new, res["model"].cfg(), game))["cfg"], game)
    again.set_data(*data(game))
    assert again.build()["text"] == new


def test_lists_newer_than_the_file_open_with_neversinks_defaults_and_the_status_says_so():
    res, new = reopen("v2_poe1_wl_sample", "poe1")
    notes = " ".join(res["notes"])
    assert "ใช้ค่าเริ่มต้นของ NeverSink" in notes
    for c in ("Runegraft", "Vial", "Corpse", "Wombgift", "Relic"):
        assert c in notes
    assert "ใช้ block ของ NeverSink แทนค่าในไฟล์เก่า" in notes       # the cut categories of the old file are named
    m = res["model"]
    fresh = {n for n, c in m._names.items() if c in {x for x, _p in w.NAMED_CATEGORIES["poe1"]}}
    assert fresh and not (fresh & set(m.item_tier))                       # untouched = NeverSink's own tier
    assert all(m.rows(c) and all(not r.user_set for r in m.rows(c)) for c in ("Runegraft", "Vial", "Corpse"))
    shown = wl_import.summarize(new).shown
    assert "Runegraft of Gemcraft" in shown and shown["Runegraft of Gemcraft"][0] == "S"
    assert any(l.startswith("# neversink (gems): gems->") for l in new.splitlines())      # the generic gems: NeverSink's own blocks
    # names of a list the file does have stay C when it does not list them
    assert "# neversink (" in new and any(n not in shown for n in m._names if m._names[n] == "Currency")


def test_v1_file_keeps_exactly_the_names_it_showed():
    res, new = reopen("v1_poe1_checker_whitelist", "poe1")
    assert res["version"] == "v1"
    sm = res["summary"]
    shown_new = set(wl_import.summarize(new).shown)
    universe = set(res["model"]._names)
    assert sm.names_v1 and (sm.names_v1 & universe) <= shown_new
    assert not (shown_new - sm.names_v1 - _fresh(res["model"], "poe1"))   # nothing the old file hid is shown now (new lists aside)
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
    assert Path(win._model.tier_style["S"]["sound"]["file"]).name == "sound-S.mp3"      # the Whitelist tab's tier S sound
    assert win._vars["sound_1"].get() == ""                                                 # ... not the NeverSink tab's
    assert win._model.gold and win._model.gold_min == 500 and win._model.map_on and win._model.map_tier == 15
    res = _generate(win._save("whitelist"), "poe2", tmp_path / "gen", name="reopened")
    new = res["path"].read_text(encoding="utf-8")
    assert wl_embed.classify(new) == "ok"
    assert differences(wl_import.summarize(old_text("v2_poe2_checker_whitelist")), wl_import.summarize(new),
                       _fresh(win._model, "poe2")) == []


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


# ---------------------------------------------------------------- lists newer than the settings (v0.10.3 report)

NEW_LISTS = {"poe1": ("Runegraft", "Vial", "Corpse", "Wombgift", "Relic"), "poe2": ("Relic",)}


def _filled_with_d(game):
    """The config v0.10.2 wrote after importing an old file: every new list hidden, no record of the lists."""
    m = model(game)
    for c in NEW_LISTS[game]:
        for n in m._names_of(c):
            m.item_tier[n] = "D"
    m.set_style_from_editor("A", dict(m.effective_style("A"), size=36))        # something the player really set
    m.set_row("Currency", "Chaos Orb", "S")
    fg = m.to_config({})
    fg.pop(f"wl_lists_{game}")                                                 # v0.10.0 - v0.10.2 did not record it
    return m, fg


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_a_file_from_0_10_2_with_every_new_list_D_gets_neversinks_defaults(root, cfg, tmp_path, game):
    m, fg = _filled_with_d(game)
    path = _generate(fg, game, tmp_path, name="from-0102")["path"]
    assert wl_embed.extract(path.read_text(encoding="utf-8"))["cfg"].get(f"wl_lists_{game}") is None
    win = make_window(root, cfg, game)
    assert win.open_filter(path) is True
    opened = win._model
    fresh = model(game)                                                        # nothing changed: NeverSink's own values
    for c in NEW_LISTS[game]:
        assert [(r.key, r.tier) for r in opened.rows(c)] == [(r.key, r.tier) for r in fresh.rows(c)]
        assert not any(r.user_set for r in opened.rows(c))
    log = win._log_text.get("1.0", tk.END)
    assert "ใช้ค่าเริ่มต้นของ NeverSink" in log and "Relic" in log
    assert opened.item_tier["Chaos Orb"] == "S" and opened.tier_style["A"]["size"] == 36        # the player's own values stay
    again = opened.to_config({})                                               # saved again: the lists are recorded
    assert again[f"wl_lists_{game}"] and "Relic" in again[f"wl_lists_{game}"]
    assert not any(n in again[f"wl_item_tier_{game}"] for n in opened._names_of("Relic"))


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_a_list_the_player_sets_to_D_in_the_new_version_stays_D(root, cfg, tmp_path, game):
    m = model(game)
    for c in NEW_LISTS[game]:
        m.set_category(c, "D")
    path = _generate(m.to_config({}), game, tmp_path, name="player-c")["path"]
    assert wl_embed.extract(path.read_text(encoding="utf-8"))["cfg"][f"wl_lists_{game}"]      # recorded
    win = make_window(root, cfg, game)
    assert win.open_filter(path) is True
    for c in NEW_LISTS[game]:
        assert all(r.tier == "D" for r in win._model.rows(c)), c
    assert "ใช้ค่าเริ่มต้นของ NeverSink" not in win._log_text.get("1.0", tk.END)


def test_a_list_partly_set_in_an_unrecorded_config_is_the_players_own():
    m = model("poe2")
    m.item_tier["Coffer Relic"] = "D"                                          # one relic only: the player's choice
    fg = m.to_config({})
    fg.pop("wl_lists_poe2")
    back = WlModel.from_config(fg, "poe2")
    back.set_data(*data("poe2"))
    assert back.item_tier == {"Coffer Relic": "D"} and back.take_notes() == []


def test_the_saved_settings_of_the_window_are_repaired_too_and_unknown_lists_are_not_written(root, cfg):
    m, fg = _filled_with_d("poe2")
    cfg.set("filter_gen", dict(fg))
    win = make_window(root, cfg, "poe2")                                       # starts from the saved settings
    assert all(r.tier != "D" for r in win._model.rows("Relic"))
    saved = win._save("whitelist")
    assert "Relic" in saved["wl_lists_poe2"]
    never = WlModel.from_config(fg, "poe2")                                    # data never loaded: nothing to say about lists
    assert "wl_lists_poe2" not in never.to_config({})


def test_a_new_list_in_a_file_that_recorded_its_lists_gets_defaults():
    """Schema of the record: the lists the file knew. A list it does not know is new, whatever the file holds for it."""
    m = model("poe1")
    fg = m.to_config({})
    fg["wl_lists_poe1"] = [x for x in fg["wl_lists_poe1"] if x != "Vial"]
    fg["wl_item_tier_poe1"]["Vial of Fate"] = "D"
    back = WlModel.from_config(fg, "poe1")
    back.set_data(*data("poe1"))
    assert "Vial of Fate" not in back.item_tier and "Vial" in " ".join(back.take_notes())


# ---------------------------------------------------------------- the program version is recorded in the settings

def test_embedded_settings_record_the_program_version_every_time(tmp_path):
    from poe_price_trade import __version__, filter_core
    for game in ("poe1", "poe2"):
        path = _generate({}, game, tmp_path, name=f"ver-{game}")["path"]
        emb = wl_embed.extract(path.read_text(encoding="utf-8"))
        assert emb["app"] == __version__ and emb["game"] == game
    hub, base, extra = data("poe2")
    kw = dict(hub_data=hub, base_text=base, extra_names=extra)
    fg = dict(model("poe2").to_config({}), whitelist_enabled=True)
    assert wl_embed.extract(filter_core.build_filter_text(fg, "poe2", app_version="web", **kw)["generated_section"])["app"] == "web"
    assert wl_embed.extract(filter_core.build_filter_text(fg, "poe2", **kw)["generated_section"])["app"] == ""   # a caller that gives none


def test_opening_says_which_version_wrote_the_settings(root, cfg, tmp_path):
    from poe_price_trade import __version__
    path = _generate({}, "poe1", tmp_path, name="says")["path"]
    win = make_window(root, cfg, "poe1")
    assert win.open_filter(path) is True
    assert f"ค่าฝังจากรุ่น {__version__}" in win._log_text.get("1.0", tk.END)
    text = path.read_text(encoding="utf-8")
    old = tmp_path / "game" / "norecord.filter"
    old.write_text(wl_embed.embed(text.split("# settings of this filter")[0], {}, "poe1"), encoding="utf-8")
    win2 = make_window(root, AppConfig("PoeFilterGen2"), "poe1")
    assert win2.open_filter(old) is True and "ค่าฝังไม่ได้บันทึกรุ่น" in win2._log_text.get("1.0", tk.END)
