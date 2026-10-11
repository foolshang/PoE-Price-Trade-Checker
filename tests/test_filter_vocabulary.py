"""Lint: every line of a generated whitelist uses a keyword / operator / value the game knows.

"Known" = the official item-filter manual (https://www.pathofexile.com/item-filter/about, fetched 2026-10-08)
and, as a second opinion, what NeverSink's strictness-2 filter of the same game itself uses.
"""
import gzip
import json
import shlex
from pathlib import Path

import pytest

from poe_price_trade import filter_core, filter_style, filter_whitelist as w, wl_embed

SAMPLE = Path(__file__).parent / "sample_data"
OPS = {"==", "=", "!=", "<", ">", "<=", ">="}
# official manual
MANUAL_KEYWORDS = {
    "Rarity", "Class", "BaseType", "AreaLevel", "MapTier", "WaystoneTier", "GemLevel", "StackSize", "ItemLevel",
    "DropLevel", "Quality", "Height", "Width", "Sockets", "LinkedSockets", "SocketGroup", "HasExplicitMod",
    "HasInfluence", "AnyEnchantment", "AlwaysShow", "Corrupted", "Identified", "FracturedItem", "Mirrored",
    "SynthesisedItem", "TwiceCorrupted", "BlightedMap", "UberBlightedMap", "ZanaMemory", "MemoryStrands",
    "CorruptedMods", "HasCruciblePassiveTree", "Replica",
    "SetFontSize", "SetTextColor", "SetBorderColor", "SetBackgroundColor", "PlayAlertSound",
    "CustomAlertSound", "CustomAlertSoundOptional", "MinimapIcon", "PlayEffect", "DisableDropSound", "Continue",
}
MANUAL_RARITY_OPS = {"<", "<=", ">", ">=", "=", "==", "!="}
RARITIES = {"Normal", "Magic", "Rare", "Unique"}
# not used by NeverSink's s2 files, but in the manual / verified in game (Winai): allowed to be missing there
NOT_IN_NEVERSINK_OK = {"CustomAlertSoundOptional", ("Rarity", "<"), ("Rarity", ">="), ("Rarity", "<="),
                       ("GemLevel", ">="), ("WaystoneTier", ">="), ("MapTier", ">=")}
CLASSES_NOT_IN_NEVERSINK_OK = {"Tablet"}      # verified in game (Winai): Class == "Tablet"


def parse(text):
    """[(keyword, op, values)] of every active line; Show / Hide as ("Show", None, [])."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            toks = shlex.split(line)
        except ValueError:
            toks = line.split()
        kw, rest = toks[0], toks[1:]
        op = None
        if rest and rest[0] in OPS:
            op, rest = rest[0], rest[1:]
        out.append((kw, op, rest))
    return out


def lint(text, base_text):
    """List of problems (empty = clean)."""
    problems = []
    ns = parse(base_text)
    ns_kw = {k for k, _o, _v in ns}
    ns_pairs = {(k, o) for k, o, _v in ns}
    ns_classes = {c for k, _o, v in ns if k == "Class" for c in v}
    for kw, op, vals in parse(text):
        if kw in ("Show", "Hide"):
            continue
        if kw not in MANUAL_KEYWORDS and kw not in ns_kw:     # NeverSink's own lines (copied gear conditions) load in game
            problems.append(f"unknown keyword {kw}")
            continue
        if kw not in ns_kw and kw not in NOT_IN_NEVERSINK_OK:
            problems.append(f"keyword {kw} not used by NeverSink and not verified")
        if op and (kw, op) not in ns_pairs and (kw, op) not in NOT_IN_NEVERSINK_OK:
            problems.append(f"operator {kw} {op} not used by NeverSink and not verified")
        if kw == "Rarity":
            if op and op not in MANUAL_RARITY_OPS:
                problems.append(f"Rarity operator {op}")
            bad = [v for v in vals if v not in RARITIES]
            if bad:
                problems.append(f"Rarity value {bad}")
        elif kw == "Class":
            for c in vals:
                if c not in ns_classes and c not in CLASSES_NOT_IN_NEVERSINK_OK:
                    problems.append(f"Class {c!r} unknown to NeverSink")
        elif kw in ("SetTextColor", "SetBorderColor", "SetBackgroundColor"):
            if len(vals) not in (3, 4) or not all(v.isdigit() and 0 <= int(v) <= 255 for v in vals):
                problems.append(f"{kw} {vals}")
        elif kw == "SetFontSize":
            if not (vals and vals[0].isdigit() and 1 <= int(vals[0]) <= 45):
                problems.append(f"SetFontSize {vals}")
        elif kw == "PlayAlertSound":
            if not (len(vals) in (1, 2) and vals[0].isdigit() and 1 <= int(vals[0]) <= 16
                    and (len(vals) == 1 or (vals[1].isdigit() and 0 <= int(vals[1]) <= 300))):
                problems.append(f"PlayAlertSound {vals}")
        elif kw == "CustomAlertSoundOptional":
            if not (len(vals) in (1, 2) and vals[0].lower().endswith((".mp3", ".wav", ".ogg"))
                    and (len(vals) == 1 or (vals[1].isdigit() and 0 <= int(vals[1]) <= 300))):
                problems.append(f"CustomAlertSoundOptional {vals}")
        elif kw == "MinimapIcon":
            if not (len(vals) == 3 and vals[0] in {"0", "1", "2"} and vals[1] in filter_style.COLORS
                    and vals[2] in filter_style.SHAPES):
                problems.append(f"MinimapIcon {vals}")
        elif kw == "PlayEffect":
            if not (vals and vals[0] in filter_style.COLORS and (len(vals) == 1 or vals[1:] == ["Temp"])):
                problems.append(f"PlayEffect {vals}")
        elif kw in ("StackSize", "AreaLevel", "MapTier", "WaystoneTier", "GemLevel", "ItemLevel"):
            bare = op is None and (kw, None) in ns_pairs          # `GemLevel 1`: no operator = "equal", NeverSink writes it
            if not ((op in OPS or bare) and len(vals) == 1 and vals[0].isdigit()):
                problems.append(f"{kw} {op} {vals}")
        elif kw in ("AlwaysShow", "Corrupted", "Identified", "FracturedItem", "Mirrored", "AnyEnchantment"):
            if vals not in (["True"], ["False"]):
                problems.append(f"{kw} {vals}")
    return problems


def _snap(name):
    with gzip.open(SAMPLE / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def everything_on(game):
    """(base text, whitelist text) with every block kind switched on."""
    base = (SAMPLE / f"neversink_{game}_s2.filter").read_text(encoding="utf-8")
    hub = {"currency": [], "items": _snap(f"hub_{game}.json.gz")["items"]}
    trade = set(_snap(f"trade_names_{game}.json.gz"))
    full = {"icon": {"size": 1, "color": "Cyan", "shape": "Square"}, "effect": {"color": "Red", "temp": True},
            "sound": {"kind": "file", "file": "a.mp3", "volume": 300}, "text": [1, 2, 3, 255],
            "border": [1, 2, 3, 255], "bg": [1, 2, 3, 255], "size": 40}
    cfg = {"whitelist_gold": True, "whitelist_gold_min": 10, "wl_map_on": True, "wl_map_tier_min": 5,
           "wl_map_rarity_min": "Rare", "style_q": filter_style.default_quest_style(),
           f"whitelist_custom_{game}": [{"name": "x", "rarities": ["Magic"], "tier": "A"}],
           "wl_tier_style": {k: dict(full) for k in ("S", "A", "B", "G", "Tablet", "Map")},
           f"wl_item_tier_{game}": {"Chaos Orb": "S"}, "wl_tier_stack": {"S": 2, "A": 3, "B": 4},
           f"wl_item_stack_{game}": {"Divine Orb": 6}}
    cfg["wl_tier_style"]["B"] = dict(full, bg=[1, 2, 3, 0], off=["effect", "icon"])         # transparent + switched-off parts
    if game == "poe2":
        cfg["whitelist_gem_uncut_poe2"] = {"Uncut Skill Gem": 10}
    quest = filter_core.build_quest_blocks(game, cfg["style_q"], "q.mp3")
    res = w.build_whitelist_filter(game, cfg, base, hub, quest,
                                   {k: "a.mp3" for k in ("S", "A", "B", "G", "Tablet", "Map")}, trade)
    return base, wl_embed.embed(res["text"], cfg, game)       # with the settings comment lines


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_every_line_is_a_known_keyword_and_value(game):
    base, text = everything_on(game)
    assert lint(text, base) == []


@pytest.mark.parametrize("game", ["poe1", "poe2"])
def test_default_whitelist_has_no_unknown_lines(game):
    base = (SAMPLE / f"neversink_{game}_s2.filter").read_text(encoding="utf-8")
    hub = {"currency": [], "items": _snap(f"hub_{game}.json.gz")["items"]}
    res = w.build_whitelist_filter(game, {}, base, hub, "", None, set(_snap(f"trade_names_{game}.json.gz")))
    assert lint(res["text"], base) == []


def test_lint_catches_bad_lines():
    base = (SAMPLE / "neversink_poe1_s2.filter").read_text(encoding="utf-8")
    bad = "Show\n    Colour 1 2 3\n    SetFontSize 99\n    MinimapIcon 3 Teal Blob\n    Rarity Epic\n    PlayAlertSound 17\n"
    probs = lint(bad, base)
    assert len(probs) == 5, probs
