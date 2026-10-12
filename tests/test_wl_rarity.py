"""The "Flask / Charm" (poe1: "Flask / Tincture") category: per row the default is NeverSink's blocks; "set myself" sets
Normal / Magic / Rare to NeverSink / S / A / B / C. A set rarity is written ahead of every block NeverSink wrote
(it wins); Unique is never touched. The old jewel / flask rarity settings are dropped / converted with a Status note."""
from __future__ import annotations
import re

import pytest

from poe_price_trade import filter_whitelist as w, wl_embed, wl_import
from poe_price_trade.wl_model import FLASK_CATEGORY, WlModel
from tests.test_filter_vocabulary import lint
from tests.test_wl_phase3b import _generate, cfg, data, make_window, model, root       # noqa: F401  (fixtures)
from tools import compare_neversink as cmp

ROWS = [("poe1", "Flask", "Life Flasks"), ("poe1", "Flask", "Utility Flasks"), ("poe1", "Tincture", "Tinctures"),
        ("poe2", "Flask", "Life Flasks"), ("poe2", "Flask", "Mana Flasks"), ("poe2", "Charm", "Charms")]


def probe(text, cls, rarity, base="Test Base"):
    """(shown, index) of the first block that decides the item."""
    blocks = cmp.parse_blocks(text)
    return cmp.visible(blocks, {"base": base, "cls": cls, "rarity": rarity, "stack": 1, "area": 70, "ilvl": 80,
                                "quality": 0, "drop": 80, "gem": 1})


def titles(text):
    """Title comment of every Show / Hide block, in order (the comment line right above it)."""
    out, last = [], ""
    for l in text.splitlines():
        s = l.strip()
        if s.startswith("#"):
            last = s
        elif s.split(" ")[0] in ("Show", "Hide"):
            out.append(last)
            last = ""
        elif not s:
            last = ""
    return out


def test_the_classes_used_are_the_ones_neversink_s2_uses_in_both_games():
    for game, rows in w.RARITY_ROWS.items():
        base = data(game)[1]
        in_file = set(re.findall(r'"([^"]+)"', "\n".join(l for l in base.split("\n") if l.strip().startswith("Class"))))
        for _rid, _label, classes in rows:
            assert set(classes) <= in_file, (game, classes)
    classes = {g: [(r, c) for r, _l, c in rows] for g, rows in w.RARITY_ROWS.items()}
    assert classes["poe1"] == [("Flask", ["Life Flasks", "Mana Flasks", "Hybrid Flasks", "Utility Flasks"]), ("Tincture", ["Tinctures"])]
    assert classes["poe2"] == [("Flask", ["Life Flasks", "Mana Flasks"]), ("Charm", ["Charms"])]


@pytest.mark.parametrize("game,expect", [("poe1", ["Flask", "Tincture"]), ("poe2", ["Flask", "Charm"])])
def test_one_category_with_two_rows_and_no_block_list(game, expect):
    m = model(game)
    cats = dict(m.categories())
    assert cats[FLASK_CATEGORY] == ("Flask / Tincture" if game == "poe1" else "Flask / Charm")
    assert [r["id"] for r in m.flask_rows()] == expect
    assert m.rows(FLASK_CATEGORY) == []                                       # no ticking per NeverSink block
    assert all(not r["custom"] and set(r["tiers"].values()) == {"B"} for r in m.flask_rows())       # shown value when set myself


@pytest.mark.parametrize("game,row,cls", ROWS)
def test_default_is_neversinks_blocks_and_the_text_has_no_rarity_block(game, row, cls):
    m = model(game)
    assert "# rarity:" not in m.build()["text"]
    m.set_flask_custom(row, True)                                             # "set myself": every rarity starts at B
    row_d = next(r for r in m.flask_rows() if r["id"] == row)
    assert row_d["custom"] and row_d["tiers"] == {"Normal": "B", "Magic": "B"}
    text = m.build()["text"]
    assert f"# rarity: {row} - Normal - tier B" in text and f"# rarity: {row} - Magic - tier B" in text
    assert text.count("# rarity:") == 2
    m.set_flask_custom(row, False)                                            # back to the default: nothing written
    assert m.build()["text"] == model(game).build()["text"]


@pytest.mark.parametrize("game,row,cls", ROWS)
def test_a_rarity_set_to_D_hides_it_and_nothing_else(game, row, cls):
    m = model(game)
    plain = m.build()["text"]
    m.set_flask_custom(row, True)
    m.set_flask_rarity(row, "Magic", "D")
    text = m.build()["text"]
    assert lint(text, data(game)[1]) == []
    assert probe(text, cls, "Magic")[0] is False
    for rar in ("Rare", "Unique"):                                            # the rarities not in the row: the same block decides
        (sa, ia), (sb, ib) = probe(plain, cls, rar), probe(text, cls, rar)
        assert sa == sb
        if ia >= 0:
            assert titles(plain)[ia] == titles(text)[ib]
    other = "Rings" if game == "poe1" else "Amulets"
    assert probe(text, other, "Magic")[0] == probe(plain, other, "Magic")[0]


@pytest.mark.parametrize("game,row,cls", ROWS)
def test_a_rarity_set_to_a_tier_uses_that_tiers_style_and_wins_over_neversinks_blocks(game, row, cls):
    m = model(game)
    m.set_style_from_editor("B", dict(m.effective_style("B"), size=31))
    m.set_flask_custom(row, True)
    m.set_flask_rarity(row, "Normal", "B")
    text = m.build()["text"]
    shown, i = probe(text, cls, "Normal")
    ts = titles(text)
    assert shown and ts[i].startswith("# rarity:") and "Normal - tier B" in ts[i]
    lines = text.splitlines()
    block = "\n".join(lines[lines.index(ts[i]):]).split("\n\n")[0]
    assert "SetFontSize 31" in block and "Class == " in block and "Rarity Normal" in block
    first_ns = min(k for k, t in enumerate(ts) if t.startswith("# neversink ("))
    assert i < first_ns                                                       # before every block NeverSink wrote
    assert lint(text, data(game)[1]) == []


def test_normal_charm_B_flask_stays_neversinks_and_the_rows_are_independent():
    m = model("poe2")
    m.set_flask_custom("Charm", True)
    m.set_flask_rarity("Charm", "Normal", "B")
    text, plain = m.build()["text"], model("poe2").build()["text"]
    assert probe(text, "Charms", "Normal")[0] and titles(text)[probe(text, "Charms", "Normal")[1]] == "# rarity: Charm - Normal - tier B"
    # the Flask row was never set: its classes follow NeverSink exactly as before
    for rar in ("Normal", "Magic", "Rare"):
        a, b = probe(plain, "Life Flasks", rar), probe(text, "Life Flasks", rar)
        assert a[0] == b[0] and (a[1] < 0 or titles(plain)[a[1]] == titles(text)[b[1]])
    assert "Class == \"Charms\"" in text and "Class == \"Life Flasks\"" not in text.split("# neversink (")[0]


def test_unique_flasks_and_jewels_are_not_touched():
    m = model("poe1")
    m.set_flask_custom("Flask", True)
    for rar in ("Normal", "Magic", "Rare"):
        m.set_flask_rarity("Flask", rar, "D")
    text = m.build()["text"]
    flask_base = next(b for _n, b in m._entries if b.endswith("Flask"))
    shown, i = probe(text, "Utility Flasks", "Unique", flask_base)
    assert shown and titles(text)[i].startswith("# uniques")                  # unique flasks go by the Unique category
    assert all("Rarity Unique" not in b for b in text.split("\n\n") if b.startswith("# rarity:"))
    # jewels have no rarity setting any more: NeverSink's blocks decide, as in the default file
    plain = model("poe1").build()["text"]
    for rar in ("Normal", "Magic", "Rare"):
        a, b = probe(plain, "Jewels", rar), probe(text, "Jewels", rar)
        assert a[0] == b[0] and (a[1] < 0 or titles(plain)[a[1]] == titles(text)[b[1]])


def test_going_back_to_the_default_keeps_the_values_but_does_not_write_them():
    m = model("poe2")
    m.set_flask_custom("Flask", True)
    m.set_flask_rarity("Flask", "Magic", "D")
    assert "# rarity:" in m.build()["text"]
    m.set_flask_custom("Flask", False)
    assert "# rarity:" not in m.build()["text"]
    assert m.flask_rows()[0]["tiers"]["Magic"] == "D" and not m.flask_rows()[0]["custom"]       # remembered
    cfg_ = m.to_config({})
    assert cfg_["wl_rarity_rows_poe2"]["Flask"] == {"custom": False, "tiers": {"Normal": "B", "Magic": "D"}}
    back = WlModel.from_config(cfg_, "poe2")
    back.set_data(*data("poe2"))
    assert back.flask_rows()[0]["tiers"]["Magic"] == "D"
    back.set_flask_custom("Flask", True)                                      # the way back: the value is there
    assert "tier D" in back.build()["text"] and back.flask_rows()[0]["tiers"]["Magic"] == "D"
    back.set_flask_rarity("Flask", "Magic", None)                             # "NeverSink" is not a choice of a rarity any more
    assert back.flask_rows()[0]["tiers"]["Magic"] == "D"
    back.set_flask_custom("Flask", False)
    assert "# rarity:" not in back.build()["text"]


def test_the_flask_category_buttons():
    m = model("poe1")
    m.set_flask_custom("Flask", True); m.set_flask_rarity("Tincture", "Normal", "A")      # a rarity set = "set myself"
    assert m.changed_count(FLASK_CATEGORY) == 2
    m.set_category(FLASK_CATEGORY, "S")                                       # nothing to tier as a whole
    assert m.changed_count(FLASK_CATEGORY) == 2
    m.reset_category(FLASK_CATEGORY)
    assert m.rarity_rows == {} and m.changed_count(FLASK_CATEGORY) == 0


# ---------------------------------------------------------------- old settings: dropped / converted with a note

@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_old_rarity_of_flasks_becomes_set_myself_and_jewel_rarity_is_dropped_with_notes(game):
    old = {f"wl_rarity_tier_{game}": {"gear:flask": {"Magic": "D", "Normal": "B"}, "gear:jewel": {"Rare": "S"}},
           f"wl_cat_tier_{game}": {"gear:story": "D", "gear:flask": "A", "gear:jewel": "S", "Currency": "S"},
           f"wl_block_tier_{game}": {("endgameflasks" if game == "poe1" else "endgame->flasks") + "|t1|1": "D", "leveling->flasks|x|1": "A"},
           f"wl_class_tier_{game}": {"Vault Keys": "D"}}
    m = WlModel.from_config(old, game)
    m.set_data(*data(game))
    rows = {r["id"]: r for r in m.flask_rows()}
    assert all(r["custom"] and r["tiers"]["Magic"] == "D" and r["tiers"]["Normal"] == "B" and set(r["tiers"]) == {"Normal", "Magic"}
               for r in rows.values())                                        # the old box covered every flask / charm class
    assert m.cat_tier == {"Currency": "S"}                                    # the cut categories' tiers are gone
    notes = " ".join(m.take_notes())
    assert "Jewel (rarity)" in notes and "กุญแจ/ของพิเศษ" in notes and "เนื้อเรื่อง" in notes
    assert "Flask / Charm (ทั้งหมวด)" in notes and "แปลงเป็น \"ตั้งค่าเอง\"" in notes
    cfg_ = m.to_config({})
    assert "wl_rarity_tier_" + game not in cfg_ and "wl_class_tier_" + game not in cfg_
    assert cfg_[f"wl_block_tier_{game}"] == {}
    again = WlModel.from_config(cfg_, game)                                   # saved once: the notes do not come back
    again.set_data(*data(game))
    assert again.take_notes() == []


def test_a_row_that_was_never_set_stays_the_default_and_the_new_layout_round_trips(tmp_path):
    m = model("poe2")
    m.set_flask_custom("Charm", True); m.set_flask_rarity("Charm", "Normal", "B")
    fg = m.to_config({})
    assert fg["wl_rarity_rows_poe2"] == {"Charm": {"custom": True, "tiers": {"Normal": "B", "Magic": "B"}}}
    junk = dict(fg, wl_rarity_rows_poe2={"Charm": {"custom": True, "tiers": {"Unique": "D", "Magic": "Z", "Rare": "A"}}, "Nope": {"custom": True}})
    got = WlModel.from_config(junk, "poe2")
    assert got.rarity_rows == {"Charm": {"custom": True, "tiers": {"Normal": "B", "Magic": "B"}}}   # Rare skipped, rest B
    notes = " ".join(got.take_notes())
    assert "Rare" in notes and "ตาม NeverSink" in notes
    path = _generate(fg, "poe2", tmp_path, name="rows")["path"]
    text = path.read_text(encoding="utf-8")
    assert wl_embed.extract(text)["cfg"]["wl_rarity_rows_poe2"] == fg["wl_rarity_rows_poe2"]
    from poe_price_trade import wl_session
    out = wl_session.open_text(text, path.name, "poe2", model("poe2"), data("poe2"))
    assert out.ok and out.model.flask_rows()[1]["custom"] and out.model.flask_rows()[0]["custom"] is False


def test_the_panel_shows_the_two_rows_with_radios_and_the_warning(root, cfg):
    win = make_window(root, cfg, "poe2")
    p = win._panel
    p.active.set("B"); p._on_tier_picked()
    labels = dict(win._model.categories())
    p.cat_var.set(labels[FLASK_CATEGORY]); p.refresh_list(); root.update()
    assert p._flask_box.winfo_manager() and not p._list_box.winfo_manager()
    assert set(p.v_flask_mode) == {"Flask", "Charm"} and all(v.get() == "default" for v in p.v_flask_mode.values())
    assert not p._flask_custom_frames["Flask"].winfo_manager()                # the rarity boxes show only for "set myself"
    p.v_flask_mode["Flask"].set("custom"); p._flask_mode("Flask")
    assert p._flask_custom_frames["Flask"].winfo_manager() and win._model.flask_rows()[0]["custom"]
    assert all(v.get() == "B" for v in p.v_flask_rar["Flask"].values())       # "set myself" starts every rarity at B
    p.v_flask_rar["Flask"]["Magic"].set("D"); p._flask_rarity("Flask", "Magic")
    assert win._model.flask_rows()[0]["tiers"]["Magic"] == "D"
    p.v_flask_mode["Flask"].set("default"); p._flask_mode("Flask")           # back to the default: remembered, not written
    assert "# rarity:" not in win._model.build()["text"] and win._model.flask_rows()[0]["tiers"]["Magic"] == "D"
    p.cat_var.set(labels["Currency"]); p.refresh_list()
    assert p._list_box.winfo_manager() and not p._flask_box.winfo_manager()


# ---------------------------------------------------------------- no Rare box: flasks / charms / tinctures are never Rare

@pytest.mark.parametrize("game,row", [("poe1", "Flask"), ("poe1", "Tincture"), ("poe2", "Flask"), ("poe2", "Charm")])
def test_no_rare_choice_and_an_old_embedded_rare_is_skipped_with_a_note(game, row):
    m = model(game)
    m.set_flask_custom(row, True)
    m.set_flask_rarity(row, "Rare", "S")                                      # not offered any more: ignored
    assert all(set(r["tiers"]) == {"Normal", "Magic"} for r in m.flask_rows())
    assert "Rarity Rare" not in m.build()["text"].split("# neversink (")[0]
    old = {f"wl_rarity_rows_{game}": {row: {"custom": True, "tiers": {"Rare": "S", "Magic": "D"}}}}
    got = WlModel.from_config(old, game)
    got.set_data(*data(game))
    assert got.rarity_rows == {row: {"custom": True, "tiers": {"Normal": "B", "Magic": "D"}}}
    notes = " ".join(got.take_notes())
    assert "Rare" in notes and "ข้ามค่า" in notes
    text = got.build()["text"]
    assert "Rarity Rare" not in text.split("# neversink (")[0] and "Rarity Magic" in text


def test_a_clean_file_has_no_rare_note():
    got = WlModel.from_config({"wl_rarity_rows_poe2": {"Flask": {"custom": True, "tiers": {"Magic": "D", "Normal": "A"}}}}, "poe2")
    got.set_data(*data("poe2"))
    assert got.take_notes() == [] and got.rarity_rows["Flask"]["tiers"] == {"Magic": "D", "Normal": "A"}


def test_an_old_set_myself_row_with_a_neversink_rarity_becomes_B_with_a_status_note():
    old = {"wl_rarity_rows_poe2": {"Flask": {"custom": True, "tiers": {"Magic": "D"}}},
           "wl_equip_rows_poe2": {"Boots": {"custom": True, "tiers": {"Rare": "S"}},
                                  "Wands": {"custom": False, "tiers": {"Rare": "A"}}}}
    got = WlModel.from_config(old, "poe2")
    got.set_data(*data("poe2"))
    assert got.rarity_rows["Flask"] == {"custom": True, "tiers": {"Magic": "D", "Normal": "B"}}
    assert got.equip_rows["Boots"] == {"custom": True, "tiers": {"Rare": "S", "Normal": "B", "Magic": "B"}}
    assert got.equip_rows["Wands"] == {"custom": False, "tiers": {"Rare": "A"}}      # a default row: nothing converted
    notes = got.take_notes()
    assert len(notes) == 1 and "ตาม NeverSink" in notes[0] and "B" in notes[0]
    again = WlModel.from_config(got.to_config({}), "poe2")                    # saved once: the note does not come back
    assert again.take_notes() == []
