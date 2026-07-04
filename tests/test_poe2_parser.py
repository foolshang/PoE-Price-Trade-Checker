"""Tests parser กับ clipboard PoE2 จริง (header + Tier + hybrid + rune + quality)."""
from pathlib import Path
from poe_price_trade.item_parser import parse_item

TEXT = (Path(__file__).parent / "sample_data" / "sample_poe2_rare.txt").read_text(
    encoding="utf-8")


def _item():
    it = parse_item(TEXT, "poe2")
    assert it is not None
    return it


def test_base_not_eaten_by_quality():
    # BUG 2: เดิม quality>0 ตัดคำแรกของ base → "Mitts" → trade query พัง
    assert _item().base_type == "Knightly Mitts"


def test_hybrid_two_lines_same_group():
    # BUG 1: เดิมบรรทัดที่สองของ hybrid ถูกทิ้งเงียบๆ
    it = _item()
    ex = [m for m in it.mods if m.mod_type == "explicit"]
    assert len(ex) == 7                               # 6 header, hybrid มี 2 บรรทัด
    g0 = [m for m in ex if m.group == ex[0].group]
    assert len(g0) == 2
    assert any("maximum Life" in m.text for m in g0)


def test_tier_from_header():
    it = _item()
    tiers = [m.tier for m in it.mods if m.mod_type == "explicit"]
    assert tiers[:2] == [1, 1]                        # hybrid สองบรรทัด tier เดียวกัน
    assert 6 in tiers                                 # Studded T6


def test_values_strip_roll_range():
    it = _item()
    m = next(m for m in it.mods if "maximum Mana" in m.text)
    assert m.values == (82.0,)
    assert m.value == 82.0                            # ไม่ใช่ 80 จากช่วง (80-89)


def test_rune_mods_captured():
    it = _item()
    assert len([m for m in it.mods if m.mod_type == "rune"]) == 2


def test_affix_counts():
    it = _item()
    assert it.prefix_count == 3
    assert it.suffix_count == 3


def test_identified_and_corrupted():
    it = _item()
    assert it.identified is True
    assert it.corrupted is True
