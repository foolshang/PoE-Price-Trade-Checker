"""Filter Generator - pure helpers (stdlib only, runs in Pyodide too).

Two jobs:
  * custom alert sounds in tier mode: NeverSink's own sound numbers mark its value
    ladders (6 = top step, 1 = second, 2 = middle); apply_ladder_sounds puts the
    user's S / A / B sound next to them (CustomAlertSoundOptional, the block's own
    PlayAlertSound stays as the fallback). No prices involved.
  * whitelist ("show only") mode: build_whitelist_section and the category helpers.

Tier mode itself is just NeverSink's base filter for the chosen strictness
(filter_core.build_filter_text adds a header and the sounds).
"""
from __future__ import annotations
import re
from collections import OrderedDict
from typing import Optional

SOUND_VOLUME = 300


# ---------------------------------------------------------------------------
# Block parsing (NeverSink's filter text)
# ---------------------------------------------------------------------------

_BASETYPE_LINE = re.compile(r'^\s*BaseType\s*(?:==)?\s*((?:"[^"]*"\s*)+)$')
_PLAY_ALERT_LINE = re.compile(r'^\s*PlayAlertSound\s+(.+?)\s*$')
_CUSTOM_ALERT_LINE = re.compile(r'^\s*(CustomAlertSound(?:Optional)?)\s+(.+?)\s*$')


class _Block:
    """One active (non-commented) Show/Hide block, located within some
    `lines = text.split("\\n")` list. `start`/`end` are indices into that
    list: `lines[start]` is the "Show"/"Hide" header line itself, `end` is
    exclusive. `basetype_line`/`basetype_names` describe its BaseType
    condition line, if it has one (a block can have none, e.g. a Class-only
    catch-all)."""
    __slots__ = ("block_type", "start", "end", "basetype_line", "basetype_names")

    def __init__(self, block_type, start, end, basetype_line, basetype_names):
        self.block_type = block_type
        self.start = start
        self.end = end
        self.basetype_line = basetype_line
        self.basetype_names = basetype_names


def _parse_blocks(lines: list) -> list:
    """Locate Show/Hide blocks. A block starts at a line whose first token -
    unindented - is exactly "Show" or "Hide"; everything indented under it
    belongs to that block until the next such line."""
    blocks: list = []
    block_type = None
    start = None
    basetype_line = None
    basetype_names: list = []
    for i, raw_line in enumerate(lines):
        first_token = raw_line.split(None, 1)[0] if raw_line.strip() else ""
        is_block_start = (not raw_line[:1].isspace()) and first_token in ("Show", "Hide")
        if is_block_start:
            if block_type is not None:
                blocks.append(_Block(block_type, start, i, basetype_line, basetype_names))
            block_type, start = first_token, i
            basetype_line, basetype_names = None, []
            continue
        if block_type is not None:
            m = _BASETYPE_LINE.match(raw_line)
            if m:
                basetype_line = i
                basetype_names = re.findall(r'"([^"]*)"', m.group(1))
    if block_type is not None:
        blocks.append(_Block(block_type, start, len(lines), basetype_line, basetype_names))
    return blocks


def _block_sound_directive(lines: list) -> Optional[tuple]:
    """(kind, raw text) of the first PlayAlertSound / CustomAlertSound[Optional] line."""
    for line in lines:
        m = _PLAY_ALERT_LINE.match(line)
        if m:
            return "PlayAlertSound", m.group(1)
        m = _CUSTOM_ALERT_LINE.match(line)
        if m:
            return m.group(1), m.group(2)
    return None


# ---------------------------------------------------------------------------
# Custom sounds by NeverSink's own ladder (tier mode)
# ---------------------------------------------------------------------------
# NeverSink tags every block with "$type->category $tier->step" in its header comment.

_TYPE_TAG = re.compile(r"\$type->(\S+)")
_TIER_TAG = re.compile(r"\$tier->(\S+)")
_STEP_TIER = re.compile(r"^(?:t\d+\w*|s|a|b|c|d|e)$")
# NeverSink's sound numbers on its value ladders: 6 = top step, 1 = second, 2 = middle steps
_SOUND_BY_NUMBER = {"6": "S", "1": "A", "2": "B"}
_SOUND_TYPE_PREFIXES = ("currency", "fragments", "divination", "sockets->general", "xenotiering")


def _header_tags(lines: list, block: "_Block") -> tuple:
    m_type = _TYPE_TAG.search(lines[block.start])
    m_tier = _TIER_TAG.search(lines[block.start])
    return (m_type.group(1) if m_type else None, m_tier.group(1) if m_tier else None)


def _sound_type_ok(ty: str, tier_tag: Optional[str] = None) -> bool:
    """Blocks that belong to a value ladder: currency*, fragments*, divination,
    sockets->general (runes etc.), xenotiering; not leveling; for uniques only the
    tier steps (t1, t2 ...), not the special per-item blocks (ex*, multispecial ...).
    Gear, 6-link, chancing, jewels, gems and maps are never included."""
    if "leveling" in ty:
        return False
    if ty.startswith("uniques"):
        return bool(tier_tag and _STEP_TIER.match(tier_tag))
    return ty.startswith(_SOUND_TYPE_PREFIXES)


def _override_sound(style_lines: list, tier_name: str, sound_map: Optional[dict],
                    indent: str = "    ") -> list:
    """Adds the user's own sound (S/A/B only) to `style_lines`.

    Written as CustomAlertSoundOptional, not CustomAlertSound: with a missing
    file the game refuses to load the whole filter for the plain form ("Invalid
    sound filepath", verified in PoE1 + PoE2), while the Optional form is
    skipped. The block's own PlayAlertSound stays as the fallback sound - it
    plays when the custom file is absent and is overridden when it is present.
    Any CustomAlertSound[Optional] line already in the style is replaced."""
    custom = (sound_map or {}).get(tier_name) if tier_name in ("S", "A", "B") else None
    if not custom:
        return style_lines
    filtered = [l for l in style_lines
                if not (l.split(None, 1) or [""])[0] in ("CustomAlertSound", "CustomAlertSoundOptional")]
    filtered.append(f'{indent}CustomAlertSoundOptional "{custom}" {SOUND_VOLUME}')
    return filtered


def apply_ladder_sounds(base_text: str, sound_map: Optional[dict]) -> tuple:
    """(new_text, blocks_changed). In every Show block of a value ladder (see
    _sound_type_ok) whose PlayAlertSound is 6 / 1 / 2, add the user's S / A / B
    sound - only for tiers that have one - through _override_sound. StackSize
    blocks of those types are included. No sounds set -> (base_text, 0)."""
    if not any((sound_map or {}).get(t) for t in ("S", "A", "B")):
        return base_text, 0
    lines = base_text.split("\n")
    edits = []
    for b in _parse_blocks(lines):
        if b.block_type != "Show":
            continue
        ty, tier_tag = _header_tags(lines, b)
        if not ty or not _sound_type_ok(ty, tier_tag):
            continue
        play = next((m.group(1) for m in map(_PLAY_ALERT_LINE.match, lines[b.start + 1:b.end]) if m), None)
        if not play or not play.split():
            continue
        tier = _SOUND_BY_NUMBER.get(play.split()[0])
        if not tier or not (sound_map or {}).get(tier):
            continue
        end = b.end
        while end - 1 > b.start and (not lines[end - 1].strip() or not lines[end - 1][:1].isspace()):
            end -= 1
        body = lines[b.start + 1:end]
        indent = next((re.match(r"\s*", l).group(0) for l in body if l.strip()), "    ")
        edits.append((b.start + 1, end, _override_sound(body, tier, sound_map, indent=indent)))
    for start, end, new in reversed(edits):
        lines[start:end] = new
    return "\n".join(lines), len(edits)


# ---------------------------------------------------------------------------
# Whitelist ("show only") mode — standalone filter, no NeverSink involved.
# Currency comes from the "Currency" category; only Gold needs its own checkbox.
GOLD_BASETYPES = ["Gold"]   # BaseType == "Gold" (verified in NeverSink poe2 + poe1)

# Uncut gems (poe2 only) - BaseType as in the game; level gated by GemLevel >= N.
# "Uncut Spirit Gem" is the source of meta gems (no separate 4th BaseType).
WHITELIST_GEM_UNCUT = {
    "poe2": ["Uncut Skill Gem", "Uncut Support Gem", "Uncut Spirit Gem"],
    "poe1": [],
}

# Whole-category checkboxes (hub category ids).
WHITELIST_CATEGORIES = {
    "poe2": ["Currency", "Fragment", "Rune", "Essence", "SoulCore", "Omen",
             "Catalyst", "Delirium", "Verisium", "AbyssalBone", "Artifact",
             "LineageGem", "Idol"],
    "poe1": ["Currency", "Fragment", "Essence", "Fossil", "Resonator", "Oil",
             "Scarab", "Artifact", "DeliriumOrb", "DivinationCard"],
}

# Hub categories NOT offered as whole-category checkboxes (verified against live
# hub payloads): basetype / clusterjewel (poe1) are priced crafting bases and
# enchant-text names; skillgem (both) is priced per level/quality variant but a
# filter would show every copy; uncutgem (poe2) names look like
# "Uncut Spirit Gem (Level 4)" (not a BaseType); map (poe1) name format unverified.


def _iter_hub_items(hub_data: dict):
    """Yield every entry of a hub prices payload (currency[] + items[]) —
    same sections repository._entries_from_hub_payload merges."""
    for section in ("currency", "items"):
        for it in (hub_data or {}).get(section, []) or []:
            if isinstance(it, dict):
                yield it


def names_in_categories(hub_data: dict, categories) -> list[str]:
    """Every entry name (= BaseType) in the chosen hub categories, regardless
    of price (show the whole category)."""
    want = {str(c).lower() for c in (categories or [])}
    out = []
    for it in _iter_hub_items(hub_data):
        name = (it.get("name") or "").strip()
        if name and str(it.get("category") or "").lower() in want:
            out.append(name)
    return out


def expand_categories(hub_data: dict, categories, exclude: Optional[dict] = None) -> list[str]:
    """names_in_categories per category minus that category's exclude list
    (exclude = {"Rune": ["Adept Rune", ...]}; a category with no key is shown whole)."""
    exclude = exclude or {}
    out: list[str] = []
    for cat in categories or []:
        skip = set(exclude.get(cat, []))
        out += [n for n in names_in_categories(hub_data, [cat]) if n not in skip]
    return out


_RARITY_ORDER = ["Normal", "Magic", "Rare", "Unique"]


def _normalize_custom(contains_names):
    """Accepts list[str] (pre-0.8.2 = any rarity) and list[{name, rarities}].
    Returns [(name, tuple(rarities in canonical order))]. Empty/invalid
    rarities fall back to every rarity so a name never silently vanishes."""
    out = []
    for e in (contains_names or []):
        if isinstance(e, str):
            nm, rar = e.strip(), tuple(_RARITY_ORDER)
        elif isinstance(e, dict):
            nm = str(e.get("name", "")).strip()
            rs = [r for r in _RARITY_ORDER if r in set(e.get("rarities") or [])]
            rar = tuple(rs) if rs else tuple(_RARITY_ORDER)
        else:
            continue
        if nm:
            out.append((nm, rar))
    return out


def build_whitelist_section(exact_basetypes, unique_bases=None, contains_names=None,
                            gem_uncut=None, gold=False, gold_min=0,
                            unique_all=False) -> str:
    """Show exact BaseTypes + Show typed names (BaseType without `==` =
    substring match, any rarity) + Show unique bases (+ Rarity Unique) + Hide
    catch-all. Standalone. "" when all inputs are empty - the caller must
    guard (an all-Hide filter blanks the screen)."""
    exact = sorted({b for b in (exact_basetypes or []) if b})
    uniq = sorted({b for b in (unique_bases or []) if b})
    cont = _normalize_custom(contains_names)
    gems = [(str(b), int(lv)) for b, lv in (gem_uncut or []) if b]
    if not exact and not uniq and not cont and not gems and not gold and not unique_all:
        return ""
    lines = ["# === PoE Checker - Whitelist (show only) ==="]
    if gold:
        # own block: StackSize must not constrain the other exact BaseTypes
        gold_min = max(0, int(gold_min or 0))
        lines += ["# gold" + (f" (stack >= {gold_min})" if gold_min > 0 else ""),
                  "Show",
                  f'    BaseType == "{GOLD_BASETYPES[0]}"']
        if gold_min > 0:
            lines.append(f"    StackSize >= {gold_min}")
        lines += [
            "    SetFontSize 45",
            "    SetTextColor 255 255 255 255",
            "    SetBorderColor 255 200 0 255",
            "    SetBackgroundColor 75 50 0 255",
            "    PlayAlertSound 6 300",
            "    MinimapIcon 0 Yellow Star",
            "    PlayEffect Yellow",
            "",
        ]
    if exact:
        names = " ".join(f'"{b}"' for b in exact)
        lines += [
            "Show",
            f"    BaseType == {names}",
            "    SetFontSize 45",
            "    SetTextColor 255 255 255 255",
            "    SetBorderColor 255 200 0 255",
            "    SetBackgroundColor 75 50 0 255",
            "    PlayAlertSound 6 300",
            "    MinimapIcon 0 Yellow Star",
            "    PlayEffect Yellow",
            "",
        ]
    if cont:
        # one Show block per rarity set (a block carries one BaseType + one Rarity line)
        groups = OrderedDict()
        for nm, rar in cont:
            groups.setdefault(rar, set()).add(nm)
        allset = set(_RARITY_ORDER)
        for rar, names_set in sorted(
                groups.items(), key=lambda kv: [_RARITY_ORDER.index(r) for r in kv[0]]):
            joined = " ".join(f'"{c}"' for c in sorted(names_set))
            tag = "any rarity" if set(rar) == allset else "/".join(rar)
            lines += [
                f"# typed names (contains match, {tag})",
                "Show",
                f"    BaseType {joined}",
            ]
            if set(rar) != allset:
                lines.append(f"    Rarity {' '.join(rar)}")
            lines += [
                "    SetFontSize 45",
                "    SetTextColor 0 255 255 255",
                "    SetBorderColor 0 255 255 255",
                "    SetBackgroundColor 0 50 60 255",
                "    PlayAlertSound 2 300",
                "    MinimapIcon 0 Cyan Star",
                "    PlayEffect Cyan",
                "",
            ]
    if uniq:
        names = " ".join(f'"{b}"' for b in uniq)
        lines += [
            "# uniques above the value threshold (shows every unique on these bases)",
            "Show",
            f"    BaseType == {names}",
            "    Rarity Unique",
            "    SetFontSize 45",
            "    SetTextColor 175 96 37 255",
            "    SetBorderColor 175 96 37 255",
            "    SetBackgroundColor 50 30 10 255",
            "    PlayAlertSound 3 300",
            "    MinimapIcon 0 Brown Star",
            "    PlayEffect Brown",
            "",
        ]
    for base, lvl in gems:
        lines += [
            f"# uncut gem: {base} (GemLevel >= {lvl})",
            "Show",
            f'    BaseType "{base}"',
            f"    GemLevel >= {lvl}",
            "    SetFontSize 45",
            "    SetTextColor 255 255 255 255",
            "    SetBorderColor 60 220 120 255",
            "    SetBackgroundColor 10 50 25 255",
            "    PlayAlertSound 1 300",
            "    MinimapIcon 0 Green Star",
            "    PlayEffect Green",
            "",
        ]
    if unique_all:
        lines += [
            "# all uniques",
            "Show",
            "    Rarity Unique",
            "    SetFontSize 45",
            "    SetTextColor 175 96 37 255",
            "    SetBorderColor 175 96 37 255",
            "    SetBackgroundColor 50 30 10 255",
            "    PlayAlertSound 3 300",
            "    MinimapIcon 0 Brown Star",
            "    PlayEffect Brown",
            "",
        ]
    lines += ["# hide everything else", "Hide", ""]
    return "\n".join(lines)
