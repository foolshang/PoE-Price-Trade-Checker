"""The whitelist ends in `Hide`, so the quest-item blocks (Q) are always written: the player's Q style when one is
set, else NeverSink's own look of its quest-item block - never left to fall through to the final Hide."""
from __future__ import annotations
import re

import pytest

from poe_price_trade import filter_core, filter_style, filter_whitelist as w
from tests.test_filter_vocabulary import lint
from tests.test_wl_phase3b import _generate, data
from tests.test_wl_rarity import probe, titles

QUEST_ITEMS = {
    "poe1": [("Quest Items", "Quest Item"), ("Cursed Ducat", "Cursed Ducat"), ("Pantheon Souls", "Soul of Arakaali"),
             ("Labyrinth Items", "Golden Key"), ("Labyrinth Trinkets", "Aureate Trinket")],
    "poe2": [("Quest Items", "Quest Item"), ("Instance Local Items", "Local Thing"), ("Keys", "Bronze Key"),
             ("Keys", "Silver Key"), ("Keys", "Gold Key")],
}


def quest_lines(text):
    """Style lines of the first quest block."""
    lines = text.splitlines()
    i = lines.index("# quest items (poe-checker)")
    block = "\n".join(lines[i + 1:]).split("\n\n")[0].splitlines()
    return [l for l in block if l.split()[0] in w._STYLE_TOKENS]


def neversink_quest(game):
    base = data(game)[1]
    lines, blocks = w.scan(base)
    from poe_price_trade import filter_gen
    b = next(b for b in blocks if filter_gen._header_tags(lines, b)[1] == "questitems")
    return ["    " + l.strip() for l in lines[b.start + 1:b.end] if l.strip() and l.split()[0] in w._STYLE_TOKENS]


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_without_a_q_style_every_quest_class_goes_to_the_q_block_with_neversinks_look(game, tmp_path):
    text = _generate({}, game, tmp_path)["path"].read_text(encoding="utf-8")
    assert quest_lines(text) == neversink_quest(game)
    assert lint(text, data(game)[1]) == []
    ts = titles(text)
    for cls, base in QUEST_ITEMS[game]:
        shown, i = probe(text, cls, "Normal", base)
        assert shown, (cls, base)
        assert i < len(ts) - 1 and ts[i] in ("# quest items (poe-checker)", ""), (cls, base, ts[i])    # not the final Hide
        assert i <= 1                                                       # the first two blocks of the file


def test_every_quest_class_of_the_program_is_in_the_block(tmp_path):
    for game in ("poe1", "poe2"):
        text = _generate({}, game, tmp_path)["path"].read_text(encoding="utf-8")
        first = text[text.index("# quest items"):].split("\n\n")[0]
        for cls in filter_core.QUEST_CLASSES[game]:
            assert f'"{cls}"' in first
        if filter_core.QUEST_BASETYPES[game]:
            assert all(f'"{b}"' in text[text.index("# quest items"):].split("\n\n")[1]
                       for b in filter_core.QUEST_BASETYPES[game])


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_a_q_style_the_player_set_is_used(game, tmp_path):
    style = dict(filter_style.default_quest_style(), size=33)
    text = _generate({"style_q": style}, game, tmp_path)["path"].read_text(encoding="utf-8")
    assert "    SetFontSize 33" in quest_lines(text)
    assert quest_lines(text) != neversink_quest(game)
    for cls, base in QUEST_ITEMS[game]:
        assert probe(text, cls, "Normal", base)[0]


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_an_emptied_q_style_counts_as_not_set(game, tmp_path):
    empty = filter_style.normalize_style({})
    text = _generate({"style_q": empty}, game, tmp_path)["path"].read_text(encoding="utf-8")
    assert quest_lines(text) == neversink_quest(game)


def test_the_neversink_tab_file_is_unchanged_when_q_is_not_set():
    """The tier tab keeps NeverSink's own quest blocks: no extra Q block there."""
    assert filter_core.build_quest_blocks("poe1", filter_style.normalize_style({})) == ""
    assert "# quest items" in filter_core.build_quest_blocks("poe1", {}, None, default_lines=["    SetFontSize 45"])
