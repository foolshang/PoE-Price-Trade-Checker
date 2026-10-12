"""Equipment by class (v0.11.7): per class the default is NeverSink's blocks; "set myself" sets Normal / Magic / Rare to
NeverSink / S / A / B / C. A set rarity is written as `Class == X` + `Rarity R` ahead of every block NeverSink wrote, so it wins
for every piece of that class + rarity (the good ones included). Plus the `==` rule: only names NeverSink itself writes with
`==` are written with `==`, the rest as NeverSink writes its other names (bare)."""
from __future__ import annotations
import re

import pytest

from poe_price_trade import filter_whitelist as w, wl_embed, wl_session
from poe_price_trade.wl_model import EQUIP_CATEGORY, WlModel
from tests.test_filter_vocabulary import lint
from tests.test_wl_phase3b import _generate, data, model
from tests.test_wl_rarity import probe, titles
from tools import compare_neversink as cmp

GAMES = ["poe1", "poe2"]


def item(base, cls, rarity, ilvl=86, area=70, quality=0):
    return {"base": base, "cls": cls, "rarity": rarity, "stack": 1, "area": area, "ilvl": ilvl, "quality": quality,
            "drop": ilvl, "gem": 1}


_META_CLASS = {"Boots": "Boots", "Gloves": "Gloves", "Helmets": "Helmet", "Rings": "Ring", "Wands": "Wand", "Quivers": "Quiver"}


def class_names(game, cls):
    """Real bases of the class: the names NeverSink lists with it, plus the RePoE bases (mod_meta.json) of that class."""
    import json
    from pathlib import Path
    base = data(game)[1]
    out = {n for n, c in cmp.name_classes(base).items() if c == cls}
    meta = json.loads((Path(__file__).resolve().parent.parent / "mod_meta.json").read_text(encoding="utf-8"))["bases"]
    out |= {n for n, v in meta.items() if v.get("class") == _META_CLASS.get(cls)}
    return sorted(out)


def visible_set(text, game, cls, rarity, **kw):
    blocks = cmp.parse_blocks(text)
    names = class_names(game, cls) + ["Zzz Unknown Base"]
    return {n for n in names if cmp.visible(blocks, item(n, cls, rarity, **kw))[0]}


def same_decision(a_text, b_text, cls, rarity, base="Zzz Unknown Base"):
    a, b = probe(a_text, cls, rarity, base), probe(b_text, cls, rarity, base)
    return a[0] == b[0] and (a[1] < 0 or titles(a_text)[a[1]] == titles(b_text)[b[1]])


# ---------------------------------------------------------------- structure

def test_groups_are_weapon_armour_jewellery_other_and_quivers_are_weapons():
    for game in GAMES:
        g = {gid: cs for gid, _n, cs in w.equip_groups(game)}
        assert list(g) == ["weapon", "armour", "jewellery", "other"]
        assert "Quivers" in g["weapon"] and "Quivers" not in g["armour"]
        assert set(g["jewellery"]) == {"Amulets", "Rings", "Belts"}
        assert all(not set(cs) & {"Life Flasks", "Charms", "Tinctures", "Skill Gems"} for cs in g.values())
    assert {"Bucklers", "Foci"} <= set(dict((a, c) for a, _n, c in w.equip_groups("poe2"))["armour"])
    assert "Warstaves" in dict((a, c) for a, _n, c in w.equip_groups("poe1"))["weapon"]


def test_every_class_is_one_neversink_names_in_its_gear_blocks():
    for game in GAMES:
        text = data(game)[1]
        named = set(re.findall(r'"([^"]*)"', " ".join(l for l in text.splitlines() if re.match(r"\s*Class\b", l))))
        assert set(w.equip_classes(game)) <= named


@pytest.mark.parametrize("game", GAMES)
def test_category_and_group_rows(game):
    m = model(game)
    assert (EQUIP_CATEGORY, w.EQUIP_LABEL) in m.categories()
    groups = m.equip_groups()
    assert [g["id"] for g in groups] == ["weapon", "armour", "jewellery", "other"]
    # no "NeverSink" value: a row is the default or set myself with S / A / B / C per rarity (B until chosen)
    assert all(not c["custom"] and c["tiers"] == {"Normal": "B", "Magic": "B", "Rare": "B"}
               for g in groups for c in g["classes"])
    assert m.rows(EQUIP_CATEGORY) == []


# ---------------------------------------------------------------- the file

@pytest.mark.parametrize("game", GAMES)
def test_untouched_or_default_rows_write_nothing_and_set_myself_starts_at_B(game):
    plain = model(game).build()["text"]
    assert "# equipment:" not in plain
    m = model(game)
    cls = w.equip_classes(game)[0]
    m.set_equip_custom(cls, True)                                             # set myself: every rarity starts at B
    assert m.equip_rows[cls] == {"custom": True, "tiers": {"Normal": "B", "Magic": "B", "Rare": "B"}}
    text = m.build()["text"]
    for rar in ("Normal", "Magic", "Rare"):
        assert f"# equipment: {cls} - {rar} - tier B" in text
    assert text.count("# equipment:") == 3
    m.set_equip_rarity(cls, "Rare", "D")
    m.set_equip_custom(cls, False)                                            # back to the default: nothing written, values kept
    assert m.build()["text"] == plain and m.equip_rows[cls]["tiers"]["Rare"] == "D"
    m.set_equip_rarity(cls, "Magic", None)                                    # "NeverSink" is not a choice of a rarity
    assert m.equip_rows[cls]["tiers"]["Magic"] == "B"


@pytest.mark.parametrize("game", GAMES)
def test_rare_boots_D_hides_every_rare_boots_good_ones_included(game):
    plain = model(game).build()["text"]
    assert visible_set(plain, game, "Boots", "Rare")                          # NeverSink shows some (exotic / ilvl ...)
    m = model(game)
    m.set_equip_custom("Boots", True)
    m.set_equip_rarity("Boots", "Rare", "D")
    text = m.build()["text"]
    for ilvl in (1, 30, 68, 82, 86):
        assert visible_set(text, game, "Boots", "Rare", ilvl=ilvl, area=ilvl) == set()
        # the other two rarities of the row are B now (set myself starts at B): every one shown, whatever it is
        for rar in ("Normal", "Magic"):
            assert "Zzz Unknown Base" in visible_set(text, game, "Boots", rar, ilvl=ilvl, area=ilvl)
    # other classes: exactly what NeverSink did
    for cls, rar in (("Gloves", "Rare"), ("Rings", "Rare"), ("Helmets", "Normal")):
        assert visible_set(text, game, cls, rar) == visible_set(plain, game, cls, rar)
        assert same_decision(plain, text, cls, rar)
    assert lint(text, data(game)[1]) == []


@pytest.mark.parametrize("game", GAMES)
def test_magic_wand_B_uses_the_B_style_and_normal_helmets_stay_neversinks(game):
    m = model(game)
    m.set_style_from_editor("B", dict(m.effective_style("B"), size=33))
    m.set_equip_custom("Wands", True)
    m.set_equip_rarity("Wands", "Magic", "B")
    text = m.build()["text"]
    shown, i = probe(text, "Wands", "Magic", "Zzz Unknown Base")
    ts = titles(text)
    assert shown and ts[i] == "# equipment: Wands - Magic - tier B"
    lines = text.splitlines()
    blk = "\n".join(lines[lines.index(ts[i]):]).split("\n\n")[0]
    assert "SetFontSize 33" in blk and 'Class == "Wands"' in blk and "Rarity Magic" in blk
    plain = model(game).build()["text"]
    assert same_decision(plain, text, "Helmets", "Normal") and same_decision(plain, text, "Helmets", "Rare")


@pytest.mark.parametrize("game", GAMES)
def test_unique_is_not_touched_and_not_offered(game):
    m = model(game)
    m.set_equip_custom("Boots", True)
    for r in ("Normal", "Magic", "Rare"):
        m.set_equip_rarity("Boots", r, "D")
    text = m.build()["text"]
    assert all("Rarity Unique" not in b for b in text.split("\n\n") if b.startswith("# equipment:"))
    plain = model(game).build()["text"]
    assert same_decision(plain, text, "Boots", "Unique", "Zzz Unique Base")
    m.set_equip_rarity("Boots", "Unique", "S")                                # not offered: ignored
    assert "Unique" not in m.equip_rows["Boots"]["tiers"]


@pytest.mark.parametrize("game", GAMES)
def test_position_after_names_uniques_tablets_maps_gold_typed_before_every_neversink_block(game):
    m = model(game)
    m.gold, m.map_on = True, True
    m.custom = [{"name": "Heavy Belt", "rarities": ["Rare"], "tier": "A"}]
    for c in ("Boots", "Rings"):
        m.set_equip_custom(c, True)
        m.set_equip_rarity(c, "Rare", "S")
    ts = titles(m.build()["text"])
    eq = [i for i, t in enumerate(ts) if t.startswith("# equipment:")]
    ns = [i for i, t in enumerate(ts) if t.startswith("# neversink (")]
    assert len(eq) == 6 and ns and max(eq) < min(ns)
    before = [i for i, t in enumerate(ts) if t.startswith(("# quest", "# tier S", "# tier A", "# tier B", "# uniques", "# tablets",
                                                           "# typed names", "# gold", "# maps", "# waystones"))]
    assert before and max(before) < min(eq)
    assert ts[-1] == "# hide everything else" and max(eq) < len(ts) - 1


@pytest.mark.parametrize("game", GAMES)
def test_group_setter_makes_every_row_set_myself_with_that_tier_and_has_a_default_choice(game):
    m = model(game)
    armour = next(cs for g, _n, cs in w.equip_groups(game) if g == "armour")
    m.set_equip_group("armour", "Rare", "D")
    assert all(m.equip_rows[c] == {"custom": True, "tiers": {"Rare": "D", "Normal": "B", "Magic": "B"}} for c in armour)
    cfg_ = m.to_config({})
    assert set(cfg_[f"wl_equip_rows_{game}"]) == set(armour)                  # written into each row, no group value
    assert not any("group" in k for k in cfg_)
    m.set_equip_rarity("Boots", "Rare", "S")                                  # one row can differ afterwards
    m.set_equip_group("armour", "Magic", "A")
    assert m.equip_rows["Boots"]["tiers"] == {"Rare": "S", "Normal": "B", "Magic": "A"}
    assert m.build()["text"].count("# equipment:") == 3 * len(armour)
    m.set_equip_group("armour", "Rare", None)                                 # "ค่าเริ่มต้น": every row of the group default
    assert all(not m.equip_rows[c]["custom"] for c in armour)
    assert m.equip_rows["Boots"]["tiers"]["Magic"] == "A"                     # values kept for the way back
    assert "# equipment:" not in m.build()["text"]
    assert not any(c["custom"] for g in m.equip_groups() if g["id"] == "armour" for c in g["classes"])


def test_group_default_leaves_the_other_groups_alone():
    m = model("poe2")
    m.set_equip_group("armour", "Rare", "D")
    m.set_equip_group("weapon", "Magic", "S")
    m.set_equip_group("armour", "Normal", None)
    assert not any(m.equip_rows[c]["custom"] for c in ("Boots", "Gloves"))
    assert m.equip_rows["Wands"]["custom"] and m.equip_rows["Wands"]["tiers"]["Magic"] == "S"


def test_poe2_quiver_in_weapons_set_with_the_weapon_group():
    m = model("poe2")
    m.set_equip_group("weapon", "Rare", "D")
    assert m.equip_rows["Quivers"]["tiers"]["Rare"] == "D" and "Boots" not in m.equip_rows
    assert visible_set(m.build()["text"], "poe2", "Quivers", "Rare") == set()


# ---------------------------------------------------------------- settings: embedded, reopened, junk

@pytest.mark.parametrize("game", GAMES)
def test_embedded_and_reopened(game, tmp_path):
    m = model(game)
    m.set_equip_custom("Boots", True)
    m.set_equip_rarity("Boots", "Rare", "D")
    m.set_equip_rarity("Boots", "Magic", "A")
    fg = m.to_config({})
    assert fg[f"wl_equip_rows_{game}"] == {"Boots": {"custom": True, "tiers": {"Normal": "B", "Magic": "A", "Rare": "D"}}}
    assert f"wl_equip_rows_{game}" in wl_embed.config_keys(game)
    path = _generate(fg, game, tmp_path, name="equip")["path"]
    text = path.read_text(encoding="utf-8")
    assert wl_embed.extract(text)["cfg"][f"wl_equip_rows_{game}"] == fg[f"wl_equip_rows_{game}"]
    out = wl_session.open_text(text, path.name, game, model(game), data(game))
    assert out.ok and out.model.equip_rows == m.equip_rows
    assert out.model.build()["text"] == m.build()["text"]
    junk = dict(fg, **{f"wl_equip_rows_{game}": {"Boots": {"custom": True, "tiers": {"Unique": "D", "Rare": "Z", "Magic": "A"}},
                                                  "Flasks": {"custom": True}, "Wands": "x"}})
    got = WlModel.from_config(junk, game)
    assert got.equip_rows == {"Boots": {"custom": True, "tiers": {"Magic": "A", "Normal": "B", "Rare": "B"}}}


def test_a_file_without_the_key_opens_with_nothing_set():
    got = WlModel.from_config({"wl_v2": True}, "poe2")
    assert got.equip_rows == {} and got.to_config({})["wl_equip_rows_poe2"] == {}


# ---------------------------------------------------------------- `==` only for names NeverSink writes with `==`

@pytest.mark.parametrize("game", GAMES)
def test_bare_basetype_only_for_names_neversink_never_writes_with_equals(game):
    base = data(game)[1]
    ok = w.known_names(base) | set(w.filter_gen.GOLD_BASETYPES)
    m = model(game)
    if game == "poe2":
        m.gem_uncut = {"Uncut Skill Gem": 17}
    m.gold = True
    head = m.build()["text"].split("# neversink (")[0]
    bare = 0
    for blk in head.split("\n\n"):
        if blk.startswith("# typed names") or blk.startswith("# uncut gem"):
            continue
        for l in blk.splitlines():
            mm = re.match(r'\s*BaseType\s*(==)?\s*((?:"[^"]*"\s*)+)$', l)
            if not mm:
                continue
            names = re.findall(r'"([^"]*)"', mm.group(2))
            if mm.group(1):
                assert set(names) <= ok, [n for n in names if n not in ok][:5]
            else:
                bare += len(names)
                assert not set(names) & ok, [n for n in names if n in ok][:5]
    assert bare > 0                                                           # the names NeverSink does not write exist


def test_poe2_tablet_class_is_written_as_neversink_does():
    text = model("poe2").build()["text"]
    assert '    Class "Tablet"' in text and 'Class == "Tablet"' not in text.split("# neversink (")[0]


@pytest.mark.parametrize("game", GAMES)
def test_first_match_is_the_same_as_with_every_name_written_with_equals(game, monkeypatch):
    """The bare form only widens a match to names that contain the name: no name of GGG's list / the hub / NeverSink
    changes its answer (shown + the block's title) against the all-`==` file."""
    hub, base, trade = data(game)
    new = model(game).build()["text"]
    monkeypatch.setattr(w, "_bt_groups", lambda names, ok: ([f"BaseType == {w._quote(list(names))}"] if list(names) else []))
    old = model(game).build()["text"]
    nb, ob = cmp.parse_blocks(new), cmp.parse_blocks(old)
    nt, ot = titles(new), titles(old)
    cls = cmp.name_classes(base)
    universe = set(trade) | w.known_names(base)
    for n in sorted(universe):
        for rar in ("Normal", "Rare"):
            it = item(n, cls.get(n, "Stackable Currency"), rar, ilvl=80)
            a, b = cmp.visible(ob, it), cmp.visible(nb, it)
            assert a[0] == b[0], (n, rar)
            assert (ot[a[1]] if a[1] >= 0 else "") == (nt[b[1]] if b[1] >= 0 else ""), (n, rar)


# ---------------------------------------------------------------- the desktop panel

from tests.test_wl_phase3b import cfg, make_window, root      # noqa: E402,F401  (fixtures)


def test_the_panel_lists_groups_rows_radios_group_setters_and_the_warning(root, cfg):
    win = make_window(root, cfg, "poe2")
    p = win._panel
    p.active.set("B"); p._on_tier_picked()
    labels = dict(win._model.categories())
    p.cat_var.set(labels[EQUIP_CATEGORY]); p.refresh_list(); root.update()
    assert p._equip_box.winfo_manager() and not p._list_box.winfo_manager() and not p._flask_box.winfo_manager()
    assert set(p.v_eq_mode) == set(w.equip_classes("poe2")) and all(v.get() == "default" for v in p.v_eq_mode.values())
    assert all(str(c.cget("state")) == "disabled" for cs in p._eq_combos.values() for c in cs)
    assert list(p._eq_combos["Boots"][0].cget("values")) == ["S", "A", "B", "C", "D"]      # no NeverSink choice
    p.v_eq_mode["Boots"].set("custom"); p._equip_mode("Boots")
    assert win._model.equip_groups()[1]["classes"][1]["custom"] and str(p._eq_combos["Boots"][0].cget("state")) == "readonly"
    assert all(p.v_eq_rar["Boots"][r].get() == "B" for r in ("Normal", "Magic", "Rare"))   # starts at B
    p.v_eq_rar["Boots"]["Rare"].set("D"); p._equip_rarity("Boots", "Rare")
    assert win._model.equip_rows["Boots"]["tiers"]["Rare"] == "D"
    assert not hasattr(p, "_eq_warn")                      # what D means is said once, above the tabs (no per-row warning)
    assert [p._equip_nb.tab(i, "text") for i in range(len(p._equip_nb.tabs()))] == ["อาวุธ", "เกราะ", "เครื่องประดับ", "อื่นๆ"]
    focus = next(r for g in win._model.equip_groups() for r in g["classes"] if r["id"] == "Foci")
    assert focus["label"] == "Focus"                      # shown as Focus, the file keeps the game's class name
    assert list(p._eq_grp_combos["armour"]["Magic"].cget("values"))[:2] == ["ตั้งทั้งกลุ่ม…", "ค่าเริ่มต้น"]
    p.v_eq_grp["armour"]["Magic"].set("A"); p._equip_group("armour", "Magic")
    assert all(win._model.equip_rows[c]["custom"] and win._model.equip_rows[c]["tiers"]["Magic"] == "A"
               for c in ("Body Armours", "Boots", "Gloves", "Helmets", "Shields", "Bucklers", "Foci"))
    assert p.v_eq_grp["armour"]["Magic"].get() == "ตั้งทั้งกลุ่ม…"            # the header select goes back to its prompt
    assert p.v_eq_rar["Gloves"]["Magic"].get() == "A" and p.v_eq_mode["Gloves"].get() == "custom"
    p.v_eq_grp["armour"]["Normal"].set("ค่าเริ่มต้น"); p._equip_group("armour", "Normal")
    assert all(not win._model.equip_rows[c]["custom"] for c in ("Body Armours", "Boots", "Gloves"))
    assert p.v_eq_mode["Boots"].get() == "default" and str(p._eq_combos["Boots"][0].cget("state")) == "disabled"
    p.cat_var.set(labels["Currency"]); p.refresh_list()
    assert p._list_box.winfo_manager() and not p._equip_box.winfo_manager()
