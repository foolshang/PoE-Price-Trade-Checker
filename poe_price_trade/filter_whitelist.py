"""Whitelist tab engine - the filter file is written entirely by us (no NeverSink blocks), but the
starting tier of every item comes from NeverSink's strictness-2 base filter.

Pure (stdlib + filter_gen + filter_style): runs in Pyodide, no I/O. Everything it needs comes in as
text / dicts; filter_core.build_filter_text wires it to the fetched base filter and hub payload.

Tiers: S, A, B are shown with their style; C = hidden (simply not written - the file ends with
Hide). Default tier of a name = the first ordinary-step or Hide block in the base filter that
lists it (blocks with StackSize / AreaLevel / Rarity ... conditions are skipped):
    S = t1 / s     A = t2-t3 / a-b     B = t4-t8 / c-e     C = a Hide block
A name the base filter does not tier (hub-only names, names only in special blocks) starts at B.
What the user changed wins: one item > a whole category > the default. Only changes are stored.

Config keys read here (all optional):
    wl_item_tier_<game>   {name: tier}          wl_cat_tier_<game>   {category: tier}
    wl_class_tier_<game>  {class: tier}         wl_unique_tier_<game> {unique name: tier}
    wl_tier_style         {"S"|"A"|"B"|"G"|"Tablet"|"Map": style}  (filter_style dicts)
    whitelist_gold / whitelist_gold_min
    wl_map_on / wl_map_tier_min / wl_map_rarity_min
    whitelist_gem_uncut_<game> / whitelist_gem_names_<game> / whitelist_gem_tier
    whitelist_custom_<game>  [{name, rarities, tier}]
"""
from __future__ import annotations
import collections
import re
from typing import Optional

from . import filter_gen, filter_style

TIERS = ("S", "A", "B")
ALL_TIERS = ("S", "A", "B", "C")
_RANK = {"S": 0, "A": 1, "B": 2, "C": 3}
_STYLE_TOKENS = {"SetFontSize", "SetTextColor", "SetBorderColor", "SetBackgroundColor", "PlayAlertSound",
                 "PlayEffect", "MinimapIcon"}
_SPECIAL_CONDITIONS = ("StackSize", "AreaLevel", "Rarity", "ItemLevel", "Quality", "DropLevel",
                       "MapTier", "WaystoneTier")
_UNIQUE_BLOCKING = ("StackSize", "AreaLevel", "ItemLevel", "Quality", "DropLevel", "MapTier", "WaystoneTier")
_VALUE_PREFIXES = ("currency", "fragments", "divination", "sockets->general", "xenotiering")
OTHER_CATEGORY = "NeverSink"          # names the hub does not list but NeverSink tiers

# "Keys / special items" category: classes with no item names in the hub, matched by Class (default B).
# Left out on purpose, because the name categories already cover every name of the class (a Class block
# would also show the names the user tiered C): poe1 "Map Fragments" + "Misc Map Items" (all scarabs /
# fragments), poe2 "Incubators" (all Currency / AbyssalBone names).
SPECIAL_CLASSES = {
    "poe1": ["Vault Keys", "Incursion Items", "Relics", "Sanctum Research", "Blueprints", "Contracts",
             "Heist Targets", "Corpses", "Wombgifts", "Chart", "Pieces"],
    "poe2": ["Pinnacle Keys", "Vault Keys", "Expedition Logbook"],
}
# hub categories the tab lists as items (the existing whitelist categories; Expedition is new)
HUB_EXCLUDED = ("UncutGem", "SkillGem", "BaseType", "ClusterJewel", "Map", "PrecursorTablet")


# ---------------------------------------------------------------------------
# Equipment ("อุปกรณ์"): NeverSink's gear Show blocks copied with ALL their conditions (AreaLevel included -
# the game checks it), grouped by their `$type` tag. The player picks one tier per group; the block's own
# look is replaced by that tier's style. NeverSink's Hide blocks of gear are not copied (more shows than
# NeverSink is accepted); a group set to C is written as `Hide` with the same conditions, so first-match
# order (an item belongs to the first gear block it fits) stays what NeverSink had.
# ---------------------------------------------------------------------------

GEAR_CATEGORY = "Gear"       # key in wl_cat_tier_<game>: the "whole category" tier
# (id, Thai name, default tier). Order = display order.
GEAR_GROUPS = {
    "poe1": [
        ("story", "เนื้อเรื่อง/เลเวลลิ่ง", "B"), ("links", "6-link / 5-link", "A"),
        ("heist", "Heist (cloak/brooch/gear/tool)", "B"), ("jewel", "Jewel (abyss/cluster/ทั่วไป/พิเศษ)", "B"),
        ("flask", "Flask / Tincture endgame", "B"), ("influenced", "Influenced", "B"),
        ("rare_ilvl", "Rare ตาม ilvl (แหวน/สร้อย/เข็มขัด)", "B"), ("rare_mod", "Rare ที่ระบุแล้วมี mod ดี", "B"),
        ("magic_mod", "Magic ที่ระบุแล้วมี mod ดี", "B"), ("exotic", "Exotic base/mod", "B"),
        ("craft", "ฐานคราฟต์", "B"), ("special", "Memory Strand / Gear พิเศษ", "B"),
    ],
    "poe2": [
        ("story", "เนื้อเรื่อง/เลเวลลิ่ง", "B"), ("zone", "Magic/Rare ตามเลเวลโซน", "B"),
        ("jewellery", "เครื่องประดับ", "B"), ("rare_ilvl", "Rare ตาม ilvl", "B"), ("jewel", "Jewel", "B"),
        ("flask", "Flask / Charm", "B"), ("craft", "Craft base", "B"), ("exotic", "Exotic base/mod", "B"),
        ("salvage", "Salvage (Quality/Sockets)", "B"), ("alwaysshow", "ของที่เกมบังคับโชว์ (AlwaysShow)", "B"),
    ],
}
# `$type` tags that are not equipment (other categories / classes own them)
_GEAR_NOT = ("exoticmap", "exotic->wombgifts", "currency")      # currency->leveling* is currency, not gear
_GEAR_RULES = {
    "poe1": [
        ("story", lambda t: "leveling" in t),
        ("links", lambda t: t in ("6l", "socketslinks")),
        ("heist", lambda t: t.startswith("heist->") and not t.startswith(("heist->contract", "heist->blueprint"))),
        ("jewel", lambda t: t.startswith("jewels")),
        ("flask", lambda t: t.startswith(("endgameflasks", "endgametinctures"))),
        ("influenced", lambda t: t.startswith("influenced")),
        ("rare_ilvl", lambda t: t.startswith(("rr", "decorators->rareeg"))),
        ("rare_mod", lambda t: t.startswith(("rareid", "rareblendid"))),
        ("magic_mod", lambda t: t == "magicid"),
        ("exotic", lambda t: t.startswith(("exotic", "rare->exotic", "rare->eater", "rare->exarch", "corruptedid"))),
        ("craft", lambda t: t.startswith("crafting")),
        ("special", lambda t: t.startswith("gear->")),
    ],
    "poe2": [
        ("story", lambda t: "leveling" in t),
        ("zone", lambda t: t.startswith("ut->")),
        ("jewellery", lambda t: t.startswith(("endgame->jewellery", "rr->jewellery"))),
        ("rare_ilvl", lambda t: t == "rr" or t.startswith(("decorators->rareeg", "rare->salvagable"))),
        ("jewel", lambda t: t.startswith("jewels")),
        ("flask", lambda t: t.startswith(("endgame->flasks", "endgame->charms"))),
        ("craft", lambda t: t.startswith("endgame->normalcraft")),
        ("exotic", lambda t: t.startswith(("exotic", "chancing"))),
        ("salvage", lambda t: t.startswith("endgame->salvagable")),
        ("alwaysshow", lambda t: t == "special->alwaysshow"),
    ],
}
_NOT_CONDITION = _STYLE_TOKENS | {"DisableDropSound", "CustomAlertSound", "CustomAlertSoundOptional"}


def gear_group_of(game: str, ty: Optional[str]) -> Optional[str]:
    if not ty or ty.startswith(_GEAR_NOT):
        return None
    for gid, rule in _GEAR_RULES.get(game, []):
        if rule(ty):
            return gid
    return None


def gear_blocks(game: str, base_text: str) -> list:
    """[(group id, `$type` tag, condition lines)] of NeverSink's gear Show blocks, in file order."""
    lines, blocks = scan(base_text)
    out = []
    for b in blocks:
        if b.block_type != "Show":
            continue
        ty = filter_gen._header_tags(lines, b)[0]
        gid = gear_group_of(game, ty)
        if not gid:
            continue
        conds = []
        for l in lines[b.start + 1:b.end]:
            t = l.strip()
            if t and not t.startswith("#") and t.split(None, 1)[0] not in _NOT_CONDITION:
                conds.append("    " + t)
        # `Continue` blocks only decorate (size / colour tweaks) and carry on to later blocks: not a selection
        if conds and not any(c.strip() == "Continue" for c in conds):
            out.append((gid, ty, conds))
    return out


def gear_tiers(game: str, cfg: dict) -> dict:
    """{group id: tier}: the player's group tier > the player's whole-category tier > the default."""
    groups = cfg.get(f"wl_gear_tier_{game}") or {}
    whole = _valid((cfg.get(f"wl_cat_tier_{game}") or {}).get(GEAR_CATEGORY))
    return {gid: _valid(groups.get(gid)) or whole or default for gid, _name, default in GEAR_GROUPS.get(game, [])}


def tier_of_step(tag: Optional[str]) -> Optional[str]:
    """S = t1 / s, A = t2-t3 / a-b, B = t4-t8 / c-e; any other tag is not a step."""
    m = re.match(r"^(?:t(\d+)\w*|(s|a|b|c|d|e))$", tag or "")
    if not m:
        return None
    if m.group(1):
        n = int(m.group(1))
        return "S" if n == 1 else "A" if n in (2, 3) else "B" if 4 <= n <= 8 else None
    return {"s": "S", "a": "A", "b": "A", "c": "B", "d": "B", "e": "B"}[m.group(2)]


_EXACT_LINE = re.compile(r'^\s*BaseType\s*==\s*((?:"[^"]*"\s*)+)$')


def exact_names(lines: list, b) -> list:
    """The names of a block's `BaseType == ...` lines. A bare `BaseType "x"` line is a substring match
    ("Ducat", "Catalyst", "Scarab" ...) - not a name the game knows, so it must never be written back
    as `BaseType ==` (the game then rejects the whole filter)."""
    out = []
    for l in lines[b.start + 1:b.end]:
        m = _EXACT_LINE.match(l)
        if m:
            out += re.findall(r'"([^"]*)"', m.group(1))
    return out


def known_names(base_text: str) -> set:
    """Every name any `BaseType ==` line of the base filter uses (NeverSink writes only real ones there)."""
    lines, blocks = scan(base_text)
    return {n for b in blocks for n in exact_names(lines, b)}


def _conds(lines: list, b) -> set:
    out = set()
    for l in lines[b.start + 1:b.end]:
        t = l.strip()
        if t and not t.startswith("#"):
            out.add(t.split(None, 1)[0])
    return out


def scan(base_text: str) -> tuple:
    """(lines, blocks) of a NeverSink base filter."""
    lines = base_text.split("\n")
    return lines, filter_gen._parse_blocks(lines)


def default_tiers(base_text: str) -> dict:
    """{name: tier} by the rule in the module docstring (first ordinary-step / Hide block wins)."""
    lines, blocks = scan(base_text)
    out: dict = {}
    for b in blocks:
        names = exact_names(lines, b)
        if not names:
            continue
        conds = _conds(lines, b)
        if conds & set(_SPECIAL_CONDITIONS):
            continue
        if b.block_type == "Hide":
            tier = "C"
        else:
            tier = tier_of_step(filter_gen._header_tags(lines, b)[1])
            if tier is None:
                continue
        for n in names:
            out.setdefault(n, tier)
    return out


def ladder_names(base_text: str) -> set:
    """Every name NeverSink lists in its value-ladder blocks (currency, fragments, divination, runes ...)."""
    lines, blocks = scan(base_text)
    out = set()
    for b in blocks:
        ty = filter_gen._header_tags(lines, b)[0] or ""
        if ty.startswith(_VALUE_PREFIXES) and "leveling" not in ty:
            out.update(exact_names(lines, b))
    return out


def default_tier_lines(base_text: str) -> dict:
    """{"S"|"A"|"B": style lines} - copies of the look of NeverSink's currency ladder steps 1, 2, 3."""
    lines, blocks = scan(base_text)
    steps = []
    for b in blocks:
        ty, tag = filter_gen._header_tags(lines, b)
        if ty == "currency" and b.block_type == "Show" and bool(exact_names(lines, b)) \
                and tier_of_step(tag) and not (_conds(lines, b) & set(_SPECIAL_CONDITIONS)):
            steps.append(b)
    out = {}
    for tier, b in zip(TIERS, steps[:3]):
        out[tier] = ["    " + l.strip() for l in lines[b.start + 1:b.end]
                     if l.strip() and l.split(None, 1)[0] in _STYLE_TOKENS]
    for tier in TIERS:           # a base filter without that ladder: a plain readable fallback
        out.setdefault(tier, filter_style.style_lines(filter_style.DEFAULT_STYLES["Map"]))
    return out


def unique_base_defaults(base_text: str) -> dict:
    """{unique BaseType: tier} - the highest tier among NeverSink's unique tier steps listing the base
    (replica / foulborn variants count as the normal unique)."""
    lines, blocks = scan(base_text)
    out: dict = {}
    for b in blocks:
        ty, tag = filter_gen._header_tags(lines, b)
        names = exact_names(lines, b)
        if not (ty or "").startswith("uniques") or b.block_type != "Show" or not names:
            continue
        tier = tier_of_step(tag)
        if not tier or _conds(lines, b) & set(_UNIQUE_BLOCKING):
            continue
        for n in names:
            if n not in out or _RANK[tier] < _RANK[out[n]]:
                out[n] = tier
    return out


def poe1_special_map_bases(base_text: str) -> list:
    """BaseTypes of the maps NeverSink treats outside the tier ladder (legacy guardian / nightmare maps,
    Vaal temple map ...) - poe1 only."""
    lines, blocks = scan(base_text)
    out = []
    for b in blocks:
        ty = filter_gen._header_tags(lines, b)[0] or ""
        if ty in ("maps->nightmare", "maps->vaaltemple") and b.block_type == "Show":
            out += [n for n in exact_names(lines, b) if n not in out]
    return out


# ---------------------------------------------------------------------------
# What exists (the item universe) and what tier it ends up in
# ---------------------------------------------------------------------------

def universe(game: str, hub_data: Optional[dict], base_text: str) -> dict:
    """{name: category}: hub names of the whitelist categories, plus the names only NeverSink tiers
    (category OTHER_CATEGORY) so nothing NeverSink would show silently disappears."""
    wanted = set(filter_gen.WHITELIST_CATEGORIES.get(game, []))
    out: dict = {}
    for it in filter_gen._iter_hub_items(hub_data or {}):
        cat = str(it.get("category") or "")
        name = (it.get("name") or "").strip()
        if name and cat in wanted and cat not in HUB_EXCLUDED:
            out.setdefault(name, cat)
    for n in sorted(ladder_names(base_text)):
        out.setdefault(n, OTHER_CATEGORY)
    return out


def _valid(t) -> Optional[str]:
    return t if t in ALL_TIERS else None


TABLET_DEFAULT = "T"        # a tablet nobody tiered: the Tablet block's look, always shown (the UI says "Tablet")


def is_tablet(game: str, name: str) -> bool:
    """poe2 precursor tablets (Class "Tablet"): "Abyss Tablet", "Ritual Tablet" ..."""
    return game == "poe2" and name.endswith(" Tablet")


def resolve_tiers(game: str, cfg: dict, names: dict, defaults: dict) -> dict:
    """{name: tier}: the user's item tier > the user's category tier > NeverSink's default > B.
    A tablet is only ever moved by its own item tier (a whole-category tier or NeverSink's ladder never
    hides or restyles it); otherwise it stays TABLET_DEFAULT."""
    items = cfg.get(f"wl_item_tier_{game}") or {}
    cats = cfg.get(f"wl_cat_tier_{game}") or {}
    out = {}
    for n, cat in names.items():
        if is_tablet(game, n):
            out[n] = _valid(items.get(n)) or TABLET_DEFAULT
        else:
            out[n] = _valid(items.get(n)) or _valid(cats.get(cat)) or defaults.get(n) or "B"
    return out


def unique_entries(hub_data: Optional[dict]) -> list:
    """[(unique name, base)] from the hub's Unique* categories."""
    out, seen = [], set()
    for it in filter_gen._iter_hub_items(hub_data or {}):
        if str(it.get("category") or "").startswith("Unique"):
            name, base = (it.get("name") or "").strip(), (it.get("base") or "").strip()
            if name and base and (name, base) not in seen:
                seen.add((name, base))
                out.append((name, base))
    return out


def resolve_unique_tiers(game: str, cfg: dict, entries: list, base_defaults: dict) -> tuple:
    """({base: tier}, conflicts). A filter can only match a unique by its base, so the tier is per
    base: every unique's own tier (the user's, else the base default, else B) and the HIGHEST one on
    the base wins. conflicts = [(base, {unique name: tier})] where the uniques on a base disagree -
    the UI warns about those."""
    user = cfg.get(f"wl_unique_tier_{game}") or {}
    per_base: dict = {}
    for name, base in entries:
        per_base.setdefault(base, {})[name] = _valid(user.get(name)) or base_defaults.get(base) or "B"
    base_tier, conflicts = {}, []
    for base, tiers in per_base.items():
        base_tier[base] = min(tiers.values(), key=lambda t: _RANK[t])
        if len(set(tiers.values())) > 1:
            conflicts.append((base, dict(tiers)))
    return base_tier, conflicts


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------

def effective_style(cfg: dict, key: str) -> Optional[dict]:
    """The user's style for a label. S / A / B sounds are shared with the NeverSink tab: its sound_s /
    sound_a / sound_b file wins over a sound kept in this tab's own style (everything else - colours,
    icon ... - stays separate per tab)."""
    style = (cfg.get("wl_tier_style") or {}).get(key)
    shared = cfg.get(f"sound_{key.lower()}") if key in TIERS else None
    if not shared:
        return style
    style = filter_style.normalize_style(style)
    style["sound"] = {"kind": "file", "id": style["sound"]["id"], "file": shared,
                      "volume": style["sound"]["volume"]}
    return style


def sound_requests(cfg: dict, game: Optional[str] = None) -> dict:
    """{label: source file or None} for every tier style that plays a file. With `game`, labels the file
    never uses (Tablet outside poe2, gold / maps when switched off) are None, so no unused file is copied."""
    unused = set()
    if game:
        if game != "poe2":
            unused.add("Tablet")
        if not cfg.get("whitelist_gold"):
            unused.add("G")
        if not cfg.get("wl_map_on"):
            unused.add("Map")
    out = {}
    for k in ("S", "A", "B", "G", "Tablet", "Map"):
        st = effective_style(cfg, k)
        out[k] = filter_style.uses_sound_file(st) if st and k not in unused else None
    return out


def _quote(names) -> str:
    return " ".join(f'"{n}"' for n in names)


_STYLE_ORDER = ("SetFontSize", "SetTextColor", "SetBorderColor", "SetBackgroundColor", "PlayAlertSound",
                "CustomAlertSoundOptional", "PlayEffect", "MinimapIcon")


def _merge_lines(base: list, over: list) -> list:
    """`over` replaces the lines of `base` with the same keyword; the rest of `base` stays. So a style
    the user only partly filled keeps NeverSink's look (sound included) for everything left unset, and
    a user file sound is added next to NeverSink's PlayAlertSound (the fallback if the file is missing)."""
    by_key = {}
    for l in base + over:
        k = l.split(None, 1)[0]
        by_key[k] = l
    return [by_key[k] for k in _STYLE_ORDER if k in by_key]


def _style_for(key: str, cfg: dict, default_lines: dict, sound_names: dict) -> list:
    default = default_lines.get(key) or filter_style.style_lines(filter_style.DEFAULT_STYLES[key])
    user = effective_style(cfg, key)
    if user and not filter_style.is_empty(user):
        return _merge_lines(default, filter_style.style_lines(user, (sound_names or {}).get(key)))
    return default


def _map_blocks(game: str, cfg: dict, style: list, base_text: str) -> list:
    cls = "Maps" if game == "poe1" else "Waystones"
    tier_key = "MapTier" if game == "poe1" else "WaystoneTier"
    if not cfg.get("wl_map_on"):
        return [f"# {cls.lower()}: not filtered - the game's own look", "Show", f'    Class == "{cls}"', ""]
    try:
        n = max(1, min(16, int(cfg.get("wl_map_tier_min") or 1)))
    except (TypeError, ValueError):
        n = 1
    rar = cfg.get("wl_map_rarity_min")
    rar = rar if rar in ("Normal", "Magic", "Rare", "Unique") else "Normal"
    out = [f"# {cls.lower()}: tier >= {n} and rarity >= {rar}", "Show", f'    Class == "{cls}"',
           f"    {tier_key} >= {n}"]
    if rar != "Normal":
        out.append(f"    Rarity >= {rar}")
    out += style + [""]
    if game == "poe1":          # special maps never go through the tier / rarity test
        specials = [["Rarity Unique"], ["BlightedMap True"], ["UberBlightedMap True"], ["ZanaMemory True"],
                    ["HasInfluence Crusader Elder Hunter Redeemer Shaper Warlord"], ["AnyEnchantment True"]]
        names = poe1_special_map_bases(base_text)
        if names:
            specials.append([f"BaseType == {_quote(names)}"])
        for conds in specials:
            out += ["Show", f'    Class == "{cls}"'] + [f"    {c}" for c in conds] + style + [""]
    return out


def build_whitelist_filter(game: str, cfg: dict, base_text: str, hub_data: Optional[dict],
                           quest_text: str = "", sound_names: Optional[dict] = None,
                           extra_names: Optional[set] = None) -> dict:
    """The whole whitelist file. Returns {"text", "count", "tiers": {name: tier}, "categories",
    "unique_conflicts", "report": {tier: n}}. count = what the file shows (names + unique bases +
    special classes). Order, specific before general (first match wins):
    Q, uniques, tablet, maps, gold, gems, S / A / B (names, then special classes), typed names, Hide."""
    cfg = cfg or {}
    sound_names = sound_names or {}
    # a single unknown name in a `BaseType ==` line makes the game reject the whole filter, so only
    # names the base filter itself uses (or `extra_names`, e.g. GGG's item list) are ever written
    real = known_names(base_text) | set(extra_names or ()) | set(filter_gen.GOLD_BASETYPES) | set(filter_gen.WHITELIST_GEM_UNCUT.get(game, []))
    skipped: dict = {}

    def keep(names, where):
        good = []
        for n in names:
            if n in real:
                good.append(n)
            else:
                skipped.setdefault(n, where)
        return good

    default_lines = default_tier_lines(base_text)
    names = universe(game, hub_data, base_text)
    tiers = resolve_tiers(game, cfg, names, default_tiers(base_text))
    tiers = {n: t for n, t in tiers.items() if n in real or skipped.setdefault(n, "item") is None}
    # tablets the player gave a tier leave the Tablet block and follow that tier like any other item
    tablet_tier = {n: t for n, t in tiers.items() if is_tablet(game, n) and t != TABLET_DEFAULT}
    all_tiers = tiers
    tiers = {n: t for n, t in tiers.items() if n not in tablet_tier}
    entries = unique_entries(hub_data)
    base_tier, conflicts = resolve_unique_tiers(game, cfg, entries, unique_base_defaults(base_text))
    style = {k: _style_for(k, cfg, default_lines, sound_names) for k in ("S", "A", "B", "G", "Tablet", "Map")}
    out = ["# === PoE Checker - Whitelist (own tiers, starting tiers from NeverSink strictness 2) ===", ""]
    count = 0
    if quest_text:
        out += [quest_text.rstrip("\n"), ""]

    def names_block(t: str) -> None:
        nonlocal count
        shown = sorted(n for n, nt in tiers.items() if nt == t)
        if shown:
            out.extend([f"# tier {t}", "Show", f"    BaseType == {_quote(shown)}"] + style[t] + [""])
            count += len(shown)

    names_block("S")

    for t in TIERS:                                                   # uniques, by base
        bases = keep(sorted(b for b, bt in base_tier.items() if bt == t), "unique base")
        if bases:
            out += [f"# uniques - tier {t} (by base type)", "Show", "    Rarity Unique",
                    f"    BaseType == {_quote(bases)}"] + style[t] + [""]
            count += len(bases)

    if game == "poe2":                                                # tablets
        for t in ALL_TIERS:             # the ones with their own tier come first, then the generic Tablet block
            own = keep(sorted(n for n, nt in tablet_tier.items() if nt == t), "tablet")
            if own and t == "C":
                out += ["# tablets - tier C (hidden by the player)", "Hide", f"    BaseType == {_quote(own)}", ""]
            elif own:
                out += [f"# tablets - tier {t}", "Show", f"    BaseType == {_quote(own)}"] + style[t] + [""]
                count += len(own)
        out += ["# tablets", "Show", '    Class == "Tablet"', "    Rarity < Unique"] + style["Tablet"] + [""]
    out += _map_blocks(game, cfg, style["Map"], base_text)

    if cfg.get("whitelist_gold"):                                     # gold
        try:
            gmin = max(0, int(cfg.get("whitelist_gold_min") or 0))
        except (TypeError, ValueError):
            gmin = 0
        out += ["# gold" + (f" (stack >= {gmin})" if gmin else ""), "Show",
                f'    BaseType == "{filter_gen.GOLD_BASETYPES[0]}"']
        out += ([f"    StackSize >= {gmin}"] if gmin else []) + style["G"] + [""]
        count += 1
    else:
        out += ["# gold: the game's own look", "Show", f'    BaseType == "{filter_gen.GOLD_BASETYPES[0]}"', ""]

    names_block("A")

    gem_tier = _valid(cfg.get("whitelist_gem_tier")) or "B"
    if gem_tier != "C":
        for base, lvl in sorted((cfg.get(f"whitelist_gem_uncut_{game}") or {}).items()):
            if not keep([base], "uncut gem"):
                continue
            try:
                lvl = max(1, int(lvl))
            except (TypeError, ValueError):
                lvl = 1
            out += [f"# uncut gem: {base} (GemLevel >= {lvl})", "Show", f'    BaseType == "{base}"',
                    f"    GemLevel >= {lvl}"] + style[gem_tier] + [""]
            count += 1
        gem_names = keep([g for g in (cfg.get(f"whitelist_gem_names_{game}") or []) if g], "gem")
        if gem_names:
            out += ["# gems", "Show", f"    BaseType == {_quote(sorted(set(gem_names)))}"] + style[gem_tier] + [""]
            count += len(set(gem_names))

    names_block("B")

    hidden = keep(sorted(n for n, nt in tiers.items() if nt == "C"), "item")
    if hidden:      # tier C names are hidden before a broader block (special classes) below can show them
        out += ["# tier C (hidden before the class blocks below can show it)", "Hide",
                f"    BaseType == {_quote(hidden)}", ""]

    class_tiers = cfg.get(f"wl_class_tier_{game}") or {}
    for t in TIERS:                                                   # special classes, S then A then B
        classes = [c for c in SPECIAL_CLASSES.get(game, []) if (_valid(class_tiers.get(c)) or "B") == t]
        if classes:
            out += [f"# tier {t} - special classes", "Show", f"    Class == {_quote(classes)}"] + style[t] + [""]
            count += len(classes)

    by_rar: dict = {}                                                 # typed names (contains)
    for entry in cfg.get(f"whitelist_custom_{game}") or []:
        nm, rar = (filter_gen._normalize_custom([entry]) or [(None, None)])[0]
        t = _valid(entry.get("tier") if isinstance(entry, dict) else None) or "B"
        if nm and t != "C":
            by_rar.setdefault((t, rar), set()).add(nm)
    for (t, rar), nms in sorted(by_rar.items(), key=lambda kv: (_RANK[kv[0][0]], kv[0][1])):
        tag = "any rarity" if len(rar) == 4 else "/".join(rar)
        out += [f"# typed names (contains, {tag}) - tier {t}", "Show", f"    BaseType {_quote(sorted(nms))}"]
        if len(rar) != 4:
            out.append(f"    Rarity {' '.join(rar)}")
        out += style[t] + [""]
        count += len(nms)

    gear_t = gear_tiers(game, cfg)
    gear_names = {gid: name for gid, name, _d in GEAR_GROUPS.get(game, [])}
    for gid, ty, conds in gear_blocks(game, base_text):
        t = gear_t[gid]
        if t == "C":        # a Hide copy keeps NeverSink's first-match order (the names above already matched)
            out += [f"# gear: {gear_names[gid]} - tier C ({ty})", "Hide"] + conds + [""]
            continue
        out += [f"# gear: {gear_names[gid]} - tier {t} ({ty})", "Show"] + conds + style[t] + [""]
        count += 1

    out += ["# hide everything else (tier C)", "Hide", ""]
    skipped_list = sorted(skipped.items())
    report = {t: sum(1 for v in all_tiers.values() if v == t) for t in ALL_TIERS}
    report[TABLET_DEFAULT] = sum(1 for v in all_tiers.values() if v == TABLET_DEFAULT)
    return {"text": "\n".join(out), "count": count, "tiers": all_tiers, "categories": names,
            "unique_conflicts": conflicts, "report": report, "skipped": skipped_list,
            "gear_tiers": gear_t}
