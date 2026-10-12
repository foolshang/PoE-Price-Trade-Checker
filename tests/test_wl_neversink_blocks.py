"""Equipment and special classes are NeverSink strictness-2's own blocks in the whitelist file (the tab lists none of
them): every line of every such block equals NeverSink's, in NeverSink's order, with the S / A / B sounds laid over
the value-ladder blocks like the NeverSink tab does."""
from __future__ import annotations
import re

import pytest

from poe_price_trade import filter_gen, filter_whitelist as w
from poe_price_trade.wl_model import WlModel
from tests.test_filter_vocabulary import lint
from tests.test_wl_phase3b import data, model

COMMENT = re.compile(r"^\s*#")


def body_lines(lines):
    """Keyword lines of a block (no comments, no blanks), stripped."""
    return [l.strip() for l in lines if l.strip() and not COMMENT.match(l)]


def written_copies(text):
    """[(header comment, kind, [keyword lines])] of the blocks the file took over from NeverSink, in file order."""
    out = []
    for chunk in text.split("\n\n"):
        lines = chunk.split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].startswith("# neversink ("):
            out.append((lines[0], lines[1].strip(), body_lines(lines[2:])))
    return out


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_every_block_of_the_cut_categories_is_neversinks_line_for_line(game):
    hub, base, _extra = data(game)
    text = model(game).build()["text"]
    want = [e for e in w.gear_sequence(game, base) if e[0] == "copy"]
    got = written_copies(text)
    assert len(got) == len(want) > 200                                       # nothing left out, nothing added
    for (header, kind, body), e in zip(got, want):
        _k, reason, ty, tag, nkind, nbody = e
        assert header == f"# neversink ({reason}): {ty} {tag or ''}".rstrip()
        assert kind == nkind and body == body_lines(nbody)                   # conditions, look, sound: every line
    assert lint(text, base) == []


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_the_copies_keep_neversinks_relative_order(game):
    base = data(game)[1]
    seq = [e for e in w.gear_sequence(game, base) if e[0] == "copy"]
    lines, blocks = w.scan(base)
    headers = [(filter_gen._header_tags(lines, b)[0], filter_gen._header_tags(lines, b)[1]) for b in blocks]
    positions = [headers.index((e[2], e[3])) for e in seq]
    assert positions == sorted(positions)


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_special_classes_are_all_covered_by_a_neversink_block(game):
    """No class the tab used to catch is lost: each one has at least one block NeverSink wrote for it."""
    base = data(game)[1]
    covered = set()
    for _h, _kind, body in written_copies(model(game).build()["text"]):
        for l in body:
            if l.startswith("Class"):
                covered |= set(re.findall(r'"([^"]*)"', l))
    assert set(w.SPECIAL_CLASSES[game]) <= covered, set(w.SPECIAL_CLASSES[game]) - covered
    assert base


def test_name_fragment_fallbacks_of_neversink_are_copied_too():
    text = model("poe1").build()["text"]
    assert 'BaseType "Runegraft"' in text and 'BaseType "Vial of"' in text


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_the_copies_keep_neversinks_own_sounds_whatever_sounds_the_tab_holds(game):
    hub, base, extra = data(game)
    m = WlModel(game)
    m.set_data(hub, base, extra)
    sounds = {"S": "s.mp3", "A": "a.mp3", "B": "b.mp3"}
    res = w.build_whitelist_filter(game, m.cfg(), base, hub, "", sounds, extra)
    want = [e for e in w.gear_sequence(game, base) if e[0] == "copy"]            # the base filter as NeverSink wrote it
    got = written_copies(res["text"])
    assert len(got) == len(want)
    for (_h, kind, body), e in zip(got, want):
        assert kind == e[4] and body == body_lines(e[5])                     # exactly NeverSink's blocks, no custom sound
    assert lint(res["text"], base) == []


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_the_categories_the_tab_still_offers(game):
    labels = [l for _c, l in model(game).categories()]
    assert not any(x in labels for x in ("เนื้อเรื่อง/เลเวลลิ่ง", "6-link / 5-link", "Heist (cloak/brooch/gear/tool)", "Influenced",
                                         "Gem ทั่วไป", "กุญแจ/ของพิเศษ (class)", "Jewel", "Memory Strand / Gear พิเศษ"))
    assert not any(c.startswith("gear:") or c == "Special" for c, _l in model(game).categories())
    names = [c for c, _l in model(game).categories()]
    assert "Currency" in names and "Unique" in names and ("Tablet" in names) == (game == "poe2")
    assert names[-2:] == ["flaskcharm", "equipclass"]
    assert "อื่นๆ (NeverSink จัด tier ให้)" in labels


def test_a_name_list_still_wins_over_neversinks_class_blocks_that_follow():
    """A tier-D name (Corpse) is hidden ahead of NeverSink's class-wide block; the others keep NeverSink's tier."""
    from tests.test_wl_a3 import shown
    m = model("poe1")
    m.set_row("Corpse", "Perfect Warlord", "D")
    text = m.build()["text"]
    assert not shown(text, "Perfect Warlord", "Corpses") and shown(text, "Perfect Hydra", "Corpses")


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_a_crlf_base_filter_gives_the_same_file_without_stray_carriage_returns(game):
    """The base filter the programs download keeps its CRLF: the copied blocks must not carry the CR into the file."""
    hub, base, extra = data(game)
    crlf = base.replace("\n", "\r\n")
    a = WlModel(game); a.set_data(hub, base, extra)
    b = WlModel(game); b.set_data(hub, crlf, extra)
    ta, tb = a.build()["text"], b.build()["text"]
    assert "\r" not in "".join(c for _h, _k, body in written_copies(tb) for c in body)
    assert [x for x in written_copies(ta)] == [x for x in written_copies(tb)]
