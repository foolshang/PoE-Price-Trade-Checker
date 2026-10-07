"""Tests for filter_gen.py: whitelist builders and the tier-mode custom sounds
(NeverSink's own sound numbers, no prices)."""
from pathlib import Path

import pytest

from poe_price_trade import filter_gen


def test_whitelist_section_contains_selected_and_trailing_hide():
    out = filter_gen.build_whitelist_section(["Divine Orb", "Mirror of Kalandra"])
    assert out.startswith("# ") and "Show" in out
    assert '"Divine Orb"' in out and '"Mirror of Kalandra"' in out
    assert out.rstrip().splitlines()[-1] == "Hide"


def test_whitelist_section_empty_selection_returns_empty():
    assert filter_gen.build_whitelist_section([]) == ""


def test_gold_basetypes():
    assert filter_gen.GOLD_BASETYPES == ["Gold"]


def test_whitelist_two_blocks_when_unique_bases_given():
    out = filter_gen.build_whitelist_section(["Divine Orb"], ["Shortsword"])
    assert out.count("Show") == 2
    assert "Rarity Unique" in out and '"Shortsword"' in out
    assert out.rstrip().splitlines()[-1] == "Hide"
    assert filter_gen.build_whitelist_section([], []) == ""


def test_names_in_categories_ignores_price_and_case():
    hub = {"currency": [
        {"category": "Rune", "name": "Adept Rune", "divine_value": 0.0},
        {"category": "Omen", "name": "Omen of Chance"},
    ]}
    assert filter_gen.names_in_categories(hub, ["rune"]) == ["Adept Rune"]


def test_whitelist_three_blocks_with_typed_contains():
    out = filter_gen.build_whitelist_section(["Divine Orb"], ["Shortsword"], ["Heavy Belt"])
    assert out.count("Show") == 3
    assert '    BaseType "Heavy Belt"' in out          # no == -> substring match
    assert '    BaseType == "Divine Orb"' in out
    assert out.rstrip().splitlines()[-1] == "Hide"
    assert filter_gen.build_whitelist_section([], [], ["x"]) != ""


def test_expand_categories_applies_exclude_per_category():
    hub = {"currency": [
        {"category": "Rune", "name": "Adept Rune"},
        {"category": "Rune", "name": "Lesser Rune"},
        {"category": "Omen", "name": "Omen of Chance"},
    ]}
    got = filter_gen.expand_categories(hub, ["Rune", "Omen"], {"Rune": ["Adept Rune"]})
    assert sorted(got) == ["Lesser Rune", "Omen of Chance"]


def test_expand_categories_without_exclude_shows_whole_category():
    hub = {"currency": [{"category": "Rune", "name": "Adept Rune"},
                        {"category": "Rune", "name": "Lesser Rune"}]}
    assert sorted(filter_gen.expand_categories(hub, ["Rune"])) == ["Adept Rune", "Lesser Rune"]
    assert sorted(filter_gen.expand_categories(hub, ["Rune"], {})) == ["Adept Rune", "Lesser Rune"]


def test_typed_names_legacy_strings_have_no_rarity_line():
    out = filter_gen.build_whitelist_section([], None, ["Heavy Belt", "Sapphire"])
    assert out.count("Show") == 1
    assert '    BaseType "Heavy Belt" "Sapphire"' in out
    assert "Rarity" not in out


def test_typed_names_split_blocks_by_rarity_set():
    out = filter_gen.build_whitelist_section([], None, [
        {"name": "Heavy Belt", "rarities": ["Normal"]},
        {"name": "Vaal Regalia", "rarities": ["Unique", "Rare"]},
    ])
    assert out.count("Show") == 2
    assert "    Rarity Normal" in out and "    Rarity Rare Unique" in out
    assert out.index('"Heavy Belt"') < out.index('"Vaal Regalia"')
    assert out.rstrip().splitlines()[-1] == "Hide"


def test_typed_names_empty_rarities_fall_back_to_any():
    out = filter_gen.build_whitelist_section([], None, [{"name": "Heavy Belt", "rarities": []}])
    assert "Rarity" not in out and '"Heavy Belt"' in out


def test_gem_uncut_block_has_basetype_and_gemlevel():
    out = filter_gen.build_whitelist_section([], None, None, gem_uncut=[("Uncut Spirit Gem", 20)])
    assert '    BaseType "Uncut Spirit Gem"' in out and "    GemLevel >= 20" in out
    assert out.count("Show") == 1 and out.rstrip().splitlines()[-1] == "Hide"


def test_gem_uncut_alone_is_not_empty_but_all_empty_is():
    assert filter_gen.build_whitelist_section([], None, None, gem_uncut=[]) == ""
    assert filter_gen.build_whitelist_section([], None, None, gem_uncut=[("Uncut Skill Gem", 1)]) != ""


def test_gem_uncut_constants_poe2_three_types_poe1_none():
    assert filter_gen.WHITELIST_GEM_UNCUT["poe2"] == [
        "Uncut Skill Gem", "Uncut Support Gem", "Uncut Spirit Gem"]
    assert filter_gen.WHITELIST_GEM_UNCUT["poe1"] == []


def test_gold_block_without_min_has_no_stacksize():
    out = filter_gen.build_whitelist_section([], gold=True)
    assert 'BaseType == "Gold"' in out and "StackSize" not in out
    assert out.rstrip().splitlines()[-1] == "Hide"


def test_gold_min_stacksize_only_in_gold_block():
    out = filter_gen.build_whitelist_section(["Divine Orb"], gold=True, gold_min=25)
    assert out.count("StackSize >= 25") == 1
    gold_block = out.split("# gold")[1].split("\n\n")[0]
    assert "StackSize >= 25" in gold_block and "Divine Orb" not in gold_block
    assert out.count("Show") == 2


def test_gold_alone_is_not_empty():
    assert filter_gen.build_whitelist_section([], gold=True, gold_min=0) != ""
    assert filter_gen.build_whitelist_section([], gold=False, gold_min=25) == ""


def test_unique_all_block_before_hide_and_off_by_default():
    out = filter_gen.build_whitelist_section([], unique_all=True)
    assert "    Rarity Unique" in out and "BaseType" not in out
    assert out.index("Rarity Unique") < out.rindex("Hide")
    off = filter_gen.build_whitelist_section(["Divine Orb"])
    assert off == filter_gen.build_whitelist_section(["Divine Orb"], unique_all=False)
    assert "Rarity Unique" not in off
    assert filter_gen.build_whitelist_section([], unique_all=False) == ""


def test_unique_is_not_a_hub_category():
    for cats in filter_gen.WHITELIST_CATEGORIES.values():
        assert "Unique" not in cats


def _poe1_hub():
    def cur(cat, name, value):
        return {"category": cat, "name": name, "base": None, "value": value, "value_currency": "chaos",
                "divine_value": value / 371.8, "listing_count": 100}
    return {"schema_version": 2, "generated_at": datetime.now(timezone.utc).isoformat(), "league": "L",
            "currency": [cur("Currency", "Divine Orb", 371.8), cur("Currency", "Exalted Orb", 2.98),
                         cur("Currency", "Chaos Orb", 1.0), cur("Fragment", "Sacrifice Fragment", 90.0),
                         cur("Scarab", "Cheap Scarab", 0.3)],
            "items": [{"category": "UniqueWeapon", "name": "Widowmaker", "base": "Royal Axe", "value": 300.0,
                       "value_currency": "chaos", "divine_value": 0.8},
                      {"category": "UniqueArmour", "name": "Kaom's Heart", "base": "Glorious Plate", "value": 80.0,
                       "value_currency": "chaos", "divine_value": 0.2}]}




# ---------------------------------------------------------------------------
# Custom sounds follow NeverSink's own value ladders (6 -> S, 1 -> A, 2 -> B)
# ---------------------------------------------------------------------------

_SOUND_BASE = """Show # $type->currency $tier->t1exalted
\tClass == "Stackable Currency"
\tBaseType == "Divine Orb"
\tSetFontSize 45
\tPlayAlertSound 6 300
\tMinimapIcon 0 Red Star

Show # %D9 $type->currency->stackedsix $tier->t1
\tClass == "Stackable Currency"
\tStackSize >= 6
\tBaseType == "Fertile Catalyst"
\tPlayAlertSound 6 300

Show # $type->currency $tier->t2divine
\tClass == "Stackable Currency"
\tBaseType == "Exalted Orb"
\tPlayAlertSound 1 300

Show # $type->currency $tier->t4chaos
\tClass == "Stackable Currency"
\tBaseType == "Chaos Orb"
\tPlayAlertSound 2 300

Show # $type->currency $tier->t7chance
\tClass == "Stackable Currency"
\tBaseType == "Orb of Chance"

Hide # $type->currency $tier->t9junk
\tClass == "Stackable Currency"
\tBaseType == "Scroll of Wisdom"

Show # $type->fragments->scarabs $tier->t1
\tClass == "Map Fragments"
\tBaseType == "Top Scarab"
\tPlayAlertSound 6 300

Show # $type->sockets->general $tier->s
\tClass == "Augment"
\tBaseType == "Top Rune"
\tPlayAlertSound 6 300

Show # $type->6l $tier->hightier
\tLinkedSockets 6
\tPlayAlertSound 1 300

Show # $type->exoticbases $tier->kalandrabases
\tBaseType == "Fancy Base"
\tPlayAlertSound 6 300

Show # $type->currency->leveling $tier->rare
\tClass == "Stackable Currency"
\tAreaLevel <= 64
\tBaseType == "Lesser Thing"
\tPlayAlertSound 2 300

Show # $type->uniques $tier->t1
\tRarity Unique
\tBaseType == "Glorious Plate"
\tPlayAlertSound 6 300

Show # $type->uniques $tier->exkaom
\tRarity Unique
\tBaseType == "Strapped Mitts"
\tPlayAlertSound 6 300

Show # $type->uniques $tier->t3
\tRarity Unique
\tBaseType == "Plain Base"
\tPlayAlertSound 3 300
"""


def _block(text, name):
    lines = text.split("\n")
    for b in filter_gen._parse_blocks(lines):
        if name in b.basetype_names:
            return "\n".join(lines[b.start:b.end])
    return None


def test_no_sounds_means_the_text_is_returned_untouched():
    for sm in (None, {}, {"S": None, "A": "", "B": None}, {"C": "c.mp3"}):
        assert filter_gen.apply_ladder_sounds(_SOUND_BASE, sm) == (_SOUND_BASE, 0)


def test_s_only_touches_the_value_ladders_that_use_sound_6():
    out, n = filter_gen.apply_ladder_sounds(_SOUND_BASE, {"S": "poe-checker-S.mp3"})
    want = 'CustomAlertSoundOptional "poe-checker-S.mp3" 300'
    for name in ("Divine Orb", "Fertile Catalyst", "Top Scarab", "Top Rune", "Glorious Plate"):
        blk = _block(out, name)
        assert blk.rstrip().endswith(want), name                 # appended after the block's own lines
        assert "PlayAlertSound 6 300" in blk                     # NeverSink's sound stays as the fallback
    assert n == 5
    for name in ("Exalted Orb", "Chaos Orb", "Orb of Chance", "Scroll of Wisdom",     # sound 1/2, none, Hide
                 "Fancy Base", "Lesser Thing", "Strapped Mitts", "Plain Base"):         # gear, leveling, unique special/t3
        assert "CustomAlertSound" not in _block(out, name), name
    assert "CustomAlertSound" not in "\n".join(b for b in out.split("Show") if "$type->6l" in b)   # 6-link: sound 1, other type


def test_a_and_b_follow_sounds_1_and_2_and_tier_c_never_gets_one():
    out, n = filter_gen.apply_ladder_sounds(_SOUND_BASE, {"S": "s.mp3", "A": "a.wav", "B": "b.ogg", "C": "c.mp3"})
    assert 'CustomAlertSoundOptional "a.wav" 300' in _block(out, "Exalted Orb")
    assert 'CustomAlertSoundOptional "b.ogg" 300' in _block(out, "Chaos Orb")
    assert 'CustomAlertSoundOptional "s.mp3" 300' in _block(out, "Divine Orb")
    assert "c.mp3" not in out and n == 7
    assert "CustomAlertSound" not in _block(out, "Orb of Chance") and "CustomAlertSound" not in _block(out, "Scroll of Wisdom")


def test_block_order_and_everything_else_stay_byte_identical():
    out, _n = filter_gen.apply_ladder_sounds(_SOUND_BASE, {"S": "s.mp3", "A": "a.wav", "B": "b.ogg"})
    stripped = "\n".join(l for l in out.split("\n") if "CustomAlertSoundOptional" not in l)
    assert stripped == _SOUND_BASE                                # only added lines, nothing moved or rewritten
    assert [b.start for b in filter_gen._parse_blocks(_SOUND_BASE.split("\n"))] != []
    h = lambda t: [l for l in t.split("\n") if l.startswith(("Show", "Hide"))]
    assert h(out) == h(_SOUND_BASE)


def test_existing_custom_sound_line_is_replaced_not_duplicated():
    base = _SOUND_BASE.replace("\tBaseType == \"Exalted Orb\"\n", "\tBaseType == \"Exalted Orb\"\n\tCustomAlertSound \"old.mp3\" 200\n")
    out, _n = filter_gen.apply_ladder_sounds(base, {"A": "a.wav"})
    blk = _block(out, "Exalted Orb")
    assert "old.mp3" not in blk and blk.count("CustomAlertSound") == 1


def _real_base(game):
    name = {"poe1": "neversink_poe1_base.filter", "poe2": "neversink_poe2_base.filter"}[game]
    return (Path(__file__).parent / "sample_data" / name).read_text(encoding="utf-8")


def test_real_base_files_sound_s_only_lands_on_value_ladders_with_sound_6():
    for game in ("poe1", "poe2"):
        base = _real_base(game)
        out, n = filter_gen.apply_ladder_sounds(base, {"S": "poe-checker-S.mp3"})
        lines = out.split("\n")
        found = 0
        for b in filter_gen._parse_blocks(lines):
            body = lines[b.start + 1:b.end]
            if not any(l.strip().startswith("CustomAlertSoundOptional") for l in body):
                continue
            found += 1
            ty, tier = filter_gen._header_tags(lines, b)
            assert filter_gen._sound_type_ok(ty or "", tier), ty
            assert any(l.strip().startswith("PlayAlertSound 6 ") for l in body)
        assert found == n and n >= 5
        assert "\n".join(l for l in lines if "CustomAlertSoundOptional" not in l) == base   # nothing but added lines


# ---- _override_sound directly (the helper every custom sound goes through) -------------------

def test_override_sound_keeps_play_alert_sound_and_appends_optional_after_it():
    style = ["    SetBorderColor 0 0 0 255", "    PlayAlertSound 6 300", "    PlayEffect Red"]
    out = filter_gen._override_sound(style, "S", {"S": "poe-checker-S.mp3"})
    assert out[:3] == style and out[3] == '    CustomAlertSoundOptional "poe-checker-S.mp3" 300' and len(out) == 4


def test_override_sound_adds_nothing_extra_when_block_has_no_sound_line():
    out = filter_gen._override_sound(["    SetBorderColor 0 0 0 255"], "A", {"A": "a.mp3"})
    assert out == ["    SetBorderColor 0 0 0 255", '    CustomAlertSoundOptional "a.mp3" 300']


def test_override_sound_replaces_existing_custom_lines_ignores_tier_c_and_uses_the_given_indent():
    style = ['    CustomAlertSound "old.mp3" 100', '    CustomAlertSoundOptional "older.mp3"', "    PlayAlertSound 1 100"]
    out = filter_gen._override_sound(style, "B", {"B": "new.mp3"})
    assert out == ["    PlayAlertSound 1 100", '    CustomAlertSoundOptional "new.mp3" 300']
    assert filter_gen._override_sound(style, "C", {"C": "c.mp3"}) == style
    assert filter_gen._override_sound(style, "S", {}) == style
    assert filter_gen._override_sound(["\tPlayAlertSound 6 300"], "S", {"S": "s.mp3"}, indent="\t")[-1] == \
        '\tCustomAlertSoundOptional "s.mp3" 300'
