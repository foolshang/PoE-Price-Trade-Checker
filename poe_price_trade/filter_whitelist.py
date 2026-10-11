"""Whitelist tab engine - the filter file is written entirely by us (no NeverSink blocks), but the
starting tier of every item comes from NeverSink's strictness-2 base filter.

Pure (stdlib + filter_gen + filter_style): runs in Pyodide, no I/O. Everything it needs comes in as
text / dicts; filter_core.build_filter_text wires it to the fetched base filter and hub payload.

Tiers: S, A, B are shown with their style; C = hidden (simply not written - the file ends with
Hide). Default tier of a name = the first Show / Hide block in the base filter that lists it (blocks with
StackSize / AreaLevel / Rarity ... conditions are skipped):
    S = t1 / s     A = t2-t3 / a-b     B = t4-t8 / c-e     C = a Hide block
    B = any other tag (supply*, any ...: NeverSink shows it, but not as a step of its ladder)
A name the base filter does not tier (hub-only names, names only in special blocks) starts at B.
A name NeverSink hides when it is alone but shows as a stack (its own block or a whole-class rule such as
"Divination Cards StackSize >= 3") starts at the tier it shows as, with that stack size as its minimum.
What the user changed wins: one item > a whole category > the default. Only changes are stored.

Config keys read here (all optional):
    wl_item_tier_<game>   {name: tier}          wl_cat_tier_<game>   {category: tier}
    wl_class_tier_<game>  {class: tier}         wl_unique_tier_<game> {unique name: tier}
    wl_block_tier_<game>  {gear block key: tier}  (wl_cat_tier_<game>["gear:<group id>"] = a whole gear category)
    wl_tier_stack         {"S"|"A"|"B": N}      show only stacks of N or more (stackable names only)
    wl_item_stack_<game>  {name: N}             per-name stack minimum (default: NeverSink's own)
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
# What NeverSink shows by a fragment of the name, for names its lists do not have yet (a new league's
# Runegraft / Vial ...): written as `BaseType "<fragment>"` at the class tier, like the special classes.
# Row key in wl_class_tier_<game>: "BaseType:<fragment>".
NEW_GEAR_GROUPS = ("gems",)      # gear groups added after v0.10.2 (the generic gems)
SPECIAL_BASE = {"poe1": ["Runegraft", "Vial of"], "poe2": []}
BASE_PREFIX = "BaseType:"
# Name lists NeverSink keeps outside its value ladders, one category each: (category, `$type` prefixes). The
# names come from its `BaseType ==` lines, the starting tier from the block's tag (t1 -> S ...).
NAMED_CATEGORIES = {
    "poe1": [("Runegraft", ("runesgrafts",)), ("Vial", ("vials",)), ("Corpse", ("corpses",)),
             ("Wombgift", ("exotic->wombgifts",)), ("Relic", ("artefact->sanctifiedrelics",))],
    "poe2": [("Relic", ("relics",))],
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

GEAR_CATEGORY = "Gear"       # legacy key in wl_cat_tier_<game>: every gear group at once (now one category per group)
GEAR_PREFIX = "gear:"        # category id of one gear group in wl_cat_tier_<game>: "gear:<group id>"
UNIQUE_CATEGORY = "Unique"   # same, for every unique
# (id, Thai name, default tier). Order = display order. Each group is a category of its own in the tab and
# lists NeverSink's gear blocks one by one (each block can be tiered alone: wl_block_tier_<game>).
GEAR_GROUPS = {
    "poe1": [
        ("story", "เนื้อเรื่อง/เลเวลลิ่ง", "B"), ("links", "6-link / 5-link", "A"),
        ("heist", "Heist (cloak/brooch/gear/tool)", "B"), ("jewel", "Jewel (abyss/cluster/ทั่วไป/พิเศษ)", "B"),
        ("flask", "Flask / Tincture endgame", "B"), ("influenced", "Influenced", "B"),
        ("rare_ilvl", "Rare ตาม ilvl (แหวน/สร้อย/เข็มขัด)", "B"), ("rare_mod", "Rare ที่ระบุแล้วมี mod ดี", "B"),
        ("magic_mod", "Magic ที่ระบุแล้วมี mod ดี", "B"), ("exotic", "Exotic base/mod", "B"),
        ("craft", "ฐานคราฟต์", "B"), ("special", "Memory Strand / Gear พิเศษ", "B"),
        ("gems", "Gem ทั่วไป", "B"),
    ],
    "poe2": [
        ("story", "เนื้อเรื่อง/เลเวลลิ่ง", "B"), ("zone", "Magic/Rare ตามเลเวลโซน", "B"),
        ("jewellery", "เครื่องประดับ", "B"), ("rare_ilvl", "Rare ตาม ilvl", "B"), ("jewel", "Jewel", "B"),
        ("flask", "Flask / Charm", "B"), ("craft", "Craft base", "B"), ("exotic", "Exotic base/mod", "B"),
        ("salvage", "Salvage (Quality/Sockets)", "B"), ("alwaysshow", "ของที่เกมบังคับโชว์ (AlwaysShow)", "B"),
    ],
}
# Categories the player can also tier by rarity (Normal / Magic / Rare): category id -> the item classes it is
# about (checked against NeverSink s2 of both games: every class below is one its gear blocks use). A rarity
# set to a tier is written as `Class == <classes>` + `Rarity X` ahead of the category's own blocks (it wins over
# one block, the whole category and NeverSink); Unique is not offered - uniques go by the Unique category.
# Key in the config: wl_rarity_tier_<game> {category id: {rarity: S|A|B|C}}.
RARITY_CHOICES = ("Normal", "Magic", "Rare")
RARITY_CATEGORIES = {
    "poe1": {"gear:jewel": ["Jewels", "Abyss Jewels"],
             "gear:flask": ["Life Flasks", "Mana Flasks", "Hybrid Flasks", "Utility Flasks", "Tinctures"]},
    "poe2": {"gear:jewel": ["Jewels"], "gear:flask": ["Life Flasks", "Mana Flasks", "Charms"]},
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
        ("gems", lambda t: t.startswith("gems")),
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


def gear_cat(gid: str) -> str:
    """The category id of a gear group (key in wl_cat_tier_<game>)."""
    return GEAR_PREFIX + gid


def gear_group_of(game: str, ty: Optional[str]) -> Optional[str]:
    if not ty or ty.startswith(_GEAR_NOT):
        return None
    for gid, rule in _GEAR_RULES.get(game, []):
        if rule(ty):
            return gid
    return None


def gear_block_items(game: str, base_text: str) -> list:
    """[(block key, group id, `$type` tag, tier tag, condition lines)] of NeverSink's gear Show blocks, in
    file order. Block key = "<type>|<tier tag>|<n>" (n = nth block with the same type + tag), what
    wl_block_tier_<game> is keyed by."""
    lines, blocks = scan(base_text)
    out = []
    seen: dict = {}
    for b in blocks:
        if b.block_type != "Show":
            continue
        ty, tag = filter_gen._header_tags(lines, b)
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
            k = (ty, tag or "")
            seen[k] = seen.get(k, 0) + 1
            out.append((f"{ty}|{tag or ''}|{seen[k]}", gid, ty, tag, conds))
    return out


def gear_blocks(game: str, base_text: str) -> list:
    """[(group id, `$type` tag, condition lines)] of NeverSink's gear Show blocks, in file order."""
    return [(gid, ty, conds) for _k, gid, ty, _tag, conds in gear_block_items(game, base_text)]


_WEAPON_CLASSES = {"Bows", "Claws", "Daggers", "One Hand Axes", "One Hand Maces", "One Hand Swords",
                   "Rune Daggers", "Sceptres", "Staves", "Thrusting One Hand Swords", "Two Hand Axes",
                   "Two Hand Maces", "Two Hand Swords", "Wands", "Warstaves", "Crossbows", "Quarterstaves",
                   "Spears", "Talismans", "Flails"}
_ARMOUR_CLASSES = {"Body Armours", "Boots", "Gloves", "Helmets", "Shields", "Bucklers", "Foci", "Quivers"}
_CLASS_THAI = {"Rings": "แหวน", "Amulets": "สร้อย", "Belts": "เข็มขัด", "Jewels": "Jewel",
               "Abyss Jewels": "Abyss Jewel", "Life Flasks": "Flask", "Mana Flasks": "Flask",
               "Utility Flasks": "Flask", "Hybrid Flasks": "Flask", "Tinctures": "Tincture", "Charms": "Charm",
               "Heist Cloaks": "Heist Cloak", "Heist Brooches": "Heist Brooch", "Skill Gems": "Gem",
               "Support Gems": "Gem"}
_RARITY_ORDER = ("Normal", "Magic", "Rare", "Unique")
_CMP = (">=", "<=", "<", ">", "==", "=")


def _short_list(names: list, limit: int = 2) -> str:
    return ", ".join(names[:limit]) + (f" +{len(names) - limit}" if len(names) > limit else "")


def block_label(ty: str, conds: list) -> str:
    """A readable name for one gear block, summed up from its conditions ("Rare แหวน ilvl ≥ 82",
    "Rare อาวุธ AreaLevel ≤ 30") - the `$type` goes after it so two blocks that read alike stay apart."""
    rar, cls, base, extra = "", "", "", []
    ilvl_lo = ilvl_hi = None
    for c in conds:
        kw, _, rest = c.strip().partition(" ")
        toks = rest.split()
        names = re.findall(r'"([^"]*)"', rest)
        if kw == "Rarity":
            ranks = [t for t in toks if t in _RARITY_ORDER]
            if toks and toks[0] in _CMP and ranks:
                rar = f"{toks[0]} {ranks[0]}"
            elif ranks and set(ranks) != {"Normal", "Magic", "Rare"}:
                rar = "/".join(ranks)
        elif kw == "Class":
            if names and set(names) <= _WEAPON_CLASSES:
                cls = "อาวุธ"
            elif names and set(names) <= _ARMOUR_CLASSES:
                cls = "เกราะ"
            else:
                cls = _short_list(list(dict.fromkeys(_CLASS_THAI.get(x, x) for x in names)), 2)
        elif kw == "BaseType":
            base = _short_list(names, 1)
        elif kw == "ItemLevel" and len(toks) == 2:
            if toks[0] == ">=":
                ilvl_lo = toks[1]
            elif toks[0] == "<=":
                ilvl_hi = toks[1]
            else:
                extra.append(f"ilvl {toks[0]} {toks[1]}")
        elif kw in ("AreaLevel", "Quality", "DropLevel", "LinkedSockets", "Sockets", "UnidentifiedItemTier",
                    "MemoryStrands", "GemLevel"):
            extra.append(f"{kw} {rest}".replace(">=", "≥").replace("<=", "≤"))
        elif kw == "HasInfluence":
            extra.append("influence")
        elif kw in ("Corrupted", "TwiceCorrupted") and rest.strip() == "True":
            extra.append("corrupted")
        elif kw == "Identified" and rest.strip() == "True":
            extra.append("ระบุแล้ว")
        elif kw == "HasExplicitMod":
            extra.append("มี mod ที่ระบุ")
        elif kw == "TransfiguredGem" and rest.strip() == "True":
            extra.append("Transfigured")
        elif kw in ("AnyEnchantment", "FracturedItem", "AlwaysShow") and rest.strip() == "True":
            extra.append(kw)
    if ilvl_lo and ilvl_hi:
        extra.insert(0, f"ilvl {ilvl_lo}–{ilvl_hi}")
    elif ilvl_lo:
        extra.insert(0, f"ilvl ≥ {ilvl_lo}")
    elif ilvl_hi:
        extra.insert(0, f"ilvl ≤ {ilvl_hi}")
    if cls and base:
        extra.append(f"base {base}")
    what = cls or (f"base {base}" if base else "")
    head = " ".join(x for x in (rar, what) if x) or "ทุกชิ้น"
    return head + ("  " + " · ".join(dict.fromkeys(extra)) if extra else "") + f"   [{ty}]"


def _legacy_gear_tier(game: str, cfg: dict, gid: str) -> Optional[str]:
    return (_valid((cfg.get(f"wl_gear_tier_{game}") or {}).get(gid))
            or _valid((cfg.get(f"wl_cat_tier_{game}") or {}).get(GEAR_CATEGORY)))


def gear_tiers(game: str, cfg: dict) -> dict:
    """{group id: tier}: the player's tier for the group's category (wl_cat_tier_<game>["gear:<id>"]; the old
    wl_gear_tier_ / "Gear" keys still count) > the group's default. A block set alone beats this."""
    cats = cfg.get(f"wl_cat_tier_{game}") or {}
    return {gid: _valid(cats.get(gear_cat(gid))) or _legacy_gear_tier(game, cfg, gid) or default
            for gid, _name, default in GEAR_GROUPS.get(game, [])}


def gear_block_tiers(game: str, cfg: dict, items: list) -> dict:
    """{block key: tier} for every gear block: the block's own tier > its group's tier."""
    group = gear_tiers(game, cfg)
    own = cfg.get(f"wl_block_tier_{game}") or {}
    return {key: _valid(own.get(key)) or group[gid] for key, gid, _ty, _tag, _c in items}


def neversink_quest_lines(base_text: str) -> list:
    """The style lines of NeverSink's own quest-item block (`$tier->questitems`), what the Q blocks of a whitelist
    use when the player set no Q style; the green quest look when the base filter has no such block."""
    lines, blocks = scan(base_text or "")
    for b in blocks:
        if b.block_type == "Show" and filter_gen._header_tags(lines, b)[1] == "questitems":
            got = ["    " + l.strip() for l in lines[b.start + 1:b.end]
                   if l.strip() and l.split(None, 1)[0] in _STYLE_TOKENS]
            if got:
                return got
    return filter_style.style_lines(filter_style.default_quest_style())


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
        if conds & set(_SPECIAL_CONDITIONS) or "Continue" in conds:
            continue
        if b.block_type == "Hide":
            tier = "C"
        else:               # a Show with a tag that is no ladder step (supply*, any ...) is shown as B
            tier = tier_of_step(filter_gen._header_tags(lines, b)[1]) or "B"
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


# Classes of stackable items: a name NeverSink lists under one of these takes the stack-size minimum.
STACKABLE_CLASSES = ("Stackable Currency", "Map Fragments", "Divination Cards", "Misc Map Items", "Augment", "Omen")
_STACK_GE = re.compile(r"^\s*StackSize\s*>=\s*(\d+)\s*$")


def _stack_blocks(lines: list, blocks: list) -> list:
    """The blocks a stack of items can be told apart by: [(idx, Show|Hide, classes, names, substrings, N, tier)]
    in file order. Blocks with a condition other than Class / BaseType / StackSize (AreaLevel, Rarity ...) and
    `Continue` blocks are left out, like in default_tiers; so are blocks that name neither a class nor a name."""
    out = []
    for i, b in enumerate(blocks):
        if _conds(lines, b) & (set(_SPECIAL_CONDITIONS) - {"StackSize"}):
            continue
        body = lines[b.start + 1:b.end]
        if any(l.strip() == "Continue" for l in body):
            continue
        classes = [c for l in body if re.match(r"\s*Class\b", l) for c in re.findall(r'"([^"]*)"', l)]
        names = exact_names(lines, b)
        subs = [x.lower() for l in body if re.match(r"\s*BaseType\b(?!\s*==)", l) for x in re.findall(r'"([^"]*)"', l)]
        if not (classes or names or subs):
            continue
        ns = [int(m.group(1)) for m in (_STACK_GE.match(l) for l in body) if m]
        tag = filter_gen._header_tags(lines, b)[1]
        out.append((i, b.block_type, classes, names, subs, ns[0] if ns else 1,
                    "C" if b.block_type == "Hide" else (tier_of_step(tag) or "B")))
    return out


def stack_info(base_text: str) -> tuple:
    """(defaults, stackable): defaults = {name: (N, tier)} for the names NeverSink hides when they are alone and
    shows from a stack of N, as that tier. First match decides, over the blocks _stack_blocks keeps - a block
    of the name itself or a whole-class rule ("Divination Cards" with StackSize >= 3). stackable = the names
    that can stack (listed under a STACKABLE_CLASSES class, or gated on StackSize)."""
    lines, blocks = scan(base_text)
    sb = _stack_blocks(lines, blocks)
    by_name: dict = {}
    by_class: dict = {}
    subs_blocks = []
    name_class: dict = {}
    for k, (_i, _kind, classes, names, subs, _n, _t) in enumerate(sb):
        for n in names:
            by_name.setdefault(n, []).append(k)
            for c in classes:
                name_class.setdefault(n, c)
        if not names and classes:
            for c in classes:
                by_class.setdefault(c, []).append(k)
        if subs and not names:
            subs_blocks.append(k)
    stackable = {n for n, c in name_class.items() if c in STACKABLE_CLASSES}
    # a name listed under several classes (rare) also counts as stackable when any of them is
    for k, (_i, _kind, classes, names, _s, _n, _t) in enumerate(sb):
        if any(c in STACKABLE_CLASSES for c in classes):
            stackable.update(names)
    defaults: dict = {}
    for n in by_name:
        cls = name_class.get(n)
        cand = set(by_name[n]) | set(by_class.get(cls, ()))
        low = n.lower()
        cand |= {k for k in subs_blocks if any(x in low for x in sb[k][4])
                 and (not sb[k][2] or cls in sb[k][2])}
        order = sorted(cand)
        if not order:
            continue

        def decide(stack):
            for k in order:
                _i, kind, classes, names, subs, need, tier = sb[k]
                if stack < need or (classes and cls not in classes):
                    continue
                if names and n not in names:
                    continue
                if subs and not any(x in low for x in subs):
                    continue
                return kind, tier
            return "Show", "B"                    # nothing matches: the game shows it

        if decide(1)[0] == "Show":
            continue
        for need in sorted({sb[k][5] for k in order if sb[k][5] > 1}):
            kind, tier = decide(need)
            if kind == "Show":
                defaults[n] = (need, tier)
                break
    stackable.update(defaults)                  # a name NeverSink gates on StackSize can obviously stack
    return defaults, stackable


def start_tiers(base_text: str) -> tuple:
    """(tiers, stack_defaults): NeverSink's starting tier of every name. A name NeverSink hides alone but
    shows as a stack (default_tiers says C) starts at the tier it shows as, with its stack minimum."""
    tiers = default_tiers(base_text)
    stack_defaults, _stackable = stack_info(base_text)
    for n, (_k, t) in stack_defaults.items():
        if tiers.get(n) in (None, "C"):
            tiers[n] = t
    return tiers, stack_defaults


def stack_minimums(cfg: dict, game: str, tiers: dict, defaults: dict, stackable: set) -> dict:
    """{name: N} (N > 1 only): the larger of the tier's minimum (wl_tier_stack) and the name's own (the
    player's wl_item_stack_<game>, else NeverSink's). Names that cannot stack never get one."""
    tier_n = cfg.get("wl_tier_stack") or {}
    own = cfg.get(f"wl_item_stack_{game}") or {}
    out = {}
    for n, t in tiers.items():
        if n not in stackable or t not in TIERS:
            continue
        item = own.get(n)
        item = (defaults.get(n) or (1,))[0] if item is None else item
        try:
            eff = max(int(tier_n.get(t) or 1), int(item or 1))
        except (TypeError, ValueError):
            eff = 1
        if eff > 1:
            out[n] = eff
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

# Names the hub does not list but NeverSink tiers join the category NeverSink itself files them under (its
# `$type` tag): a shard / orb is Currency, a small rune is Rune ... First matching prefix wins; a `$type` no
# row matches (tattoos, xenotiering ...) stays in OTHER_CATEGORY.
_TYPE_CATEGORY = {
    "poe1": [("currency->trial->tattoo", None), ("currency->essence", "Essence"), ("currency->splinter", "Fragment"),
             ("currency->stackedsplinters", "Fragment"), ("fragments->scarabs", "Scarab"),
             ("fragments", "Fragment"), ("divination", "DivinationCard"), ("currency", "Currency")],
    "poe2": [("currency->omen", "Omen"), ("currency->splinter", "Fragment"), ("sockets->general", "Rune"),
             ("fragments", "Fragment"), ("currency", "Currency")],
}


def type_category(game: str, ty: Optional[str]) -> Optional[str]:
    for prefix, cat in _TYPE_CATEGORY.get(game, []):
        if (ty or "").startswith(prefix):
            return cat
    return None


def ladder_name_types(base_text: str) -> dict:
    """{name: `$type` of the first value-ladder block that lists it} (same blocks as ladder_names)."""
    lines, blocks = scan(base_text)
    out: dict = {}
    for b in blocks:
        ty = filter_gen._header_tags(lines, b)[0] or ""
        if ty.startswith(_VALUE_PREFIXES) and "leveling" not in ty:
            for n in exact_names(lines, b):
                out.setdefault(n, ty)
    return out


def named_categories(game: str, base_text: str) -> dict:
    """{name: category} of the lists in NAMED_CATEGORIES (Runegraft, Vial, Corpse ...), first block wins."""
    rules = NAMED_CATEGORIES.get(game, [])
    out: dict = {}
    if not rules or not base_text:
        return out
    lines, blocks = scan(base_text)
    for b in blocks:
        ty = filter_gen._header_tags(lines, b)[0] or ""
        cat = next((c for c, prefixes in rules if ty.startswith(prefixes)), None)
        if cat:
            for n in exact_names(lines, b):
                out.setdefault(n, cat)
    return out


def universe(game: str, hub_data: Optional[dict], base_text: str) -> dict:
    """{name: category}: hub names of the whitelist categories, plus the names only NeverSink tiers (filed
    under the category of their NeverSink `$type`, else OTHER_CATEGORY) so nothing NeverSink would show
    silently disappears."""
    wanted = set(filter_gen.WHITELIST_CATEGORIES.get(game, []))
    out: dict = {}
    for it in filter_gen._iter_hub_items(hub_data or {}):
        cat = str(it.get("category") or "")
        name = (it.get("name") or "").strip()
        if name and cat in wanted and cat not in HUB_EXCLUDED:
            out.setdefault(name, cat)
    for n, ty in sorted(ladder_name_types(base_text).items()):
        cat = type_category(game, ty)
        out.setdefault(n, cat if cat in wanted else OTHER_CATEGORY)
    for n, cat in named_categories(game, base_text).items():
        out.setdefault(n, cat)
    return out


def _valid(t) -> Optional[str]:
    return t if t in ALL_TIERS else None


TABLET_DEFAULT = "T"        # a tablet nobody tiered: the Tablet block's look, always shown (the UI says "Tablet")
TABLET_CATEGORY = "Tablet"   # key in wl_cat_tier_<game>: every tablet at once (the only category tier that moves them)


def is_tablet(game: str, name: str) -> bool:
    """poe2 precursor tablets (Class "Tablet"): "Abyss Tablet", "Ritual Tablet" ..."""
    return game == "poe2" and name.endswith(" Tablet")


def resolve_tiers(game: str, cfg: dict, names: dict, defaults: dict) -> dict:
    """{name: tier}: the user's item tier > the user's category tier > NeverSink's default > B.
    A tablet is only moved by its own item tier or the "Tablet" category tier (neither another category's
    tier nor NeverSink's ladder restyles it); otherwise it stays TABLET_DEFAULT."""
    items = cfg.get(f"wl_item_tier_{game}") or {}
    cats = cfg.get(f"wl_cat_tier_{game}") or {}
    out = {}
    for n, cat in names.items():
        if is_tablet(game, n):
            out[n] = _valid(items.get(n)) or _valid(cats.get(TABLET_CATEGORY)) or TABLET_DEFAULT
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
    the UI warns about those. A unique's own tier > the whole Unique category's tier
    (wl_cat_tier_<game>["Unique"]) > the base default > B."""
    user = cfg.get(f"wl_unique_tier_{game}") or {}
    whole = _valid((cfg.get(f"wl_cat_tier_{game}") or {}).get(UNIQUE_CATEGORY))
    per_base: dict = {}
    for name, base in entries:
        per_base.setdefault(base, {})[name] = _valid(user.get(name)) or whole or base_defaults.get(base) or "B"
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
    if not user or filter_style.is_empty(user):
        return default
    lines = _merge_lines(default, filter_style.style_lines(user, (sound_names or {}).get(key)))
    drop = {kw for part in filter_style.normalize_style(user).get("off") or ()
            for kw in filter_style.PART_KEYWORDS[part]}
    return [l for l in lines if l.split(None, 1)[0] not in drop]


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
    start, stack_defaults = start_tiers(base_text)
    stackable = stack_info(base_text)[1]
    tiers = resolve_tiers(game, cfg, names, start)
    tiers = {n: t for n, t in tiers.items() if n in real or skipped.setdefault(n, "item") is None}
    stack_min = stack_minimums(cfg, game, tiers, stack_defaults, stackable)
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
        if not shown:
            return
        count += len(shown)
        groups: dict = {}
        for n in shown:
            groups.setdefault(stack_min.get(n, 1), []).append(n)
        for need in sorted(groups):
            if need == 1:
                out.extend([f"# tier {t}", "Show", f"    BaseType == {_quote(groups[need])}"] + style[t] + [""])
                continue
            # a stack under the minimum is hidden right here, so no later (broader) block can show it
            out.extend([f"# tier {t} - stack >= {need}", "Show", f"    BaseType == {_quote(groups[need])}",
                        f"    StackSize >= {need}"] + style[t] + [""])
            out.extend([f"# tier {t} - smaller stacks hidden", "Hide", f"    BaseType == {_quote(groups[need])}", ""])

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
        frags = [f for f in SPECIAL_BASE.get(game, []) if (_valid(class_tiers.get(BASE_PREFIX + f)) or "B") == t]
        if frags:       # names no list has yet (a new Runegraft / Vial): shown by a fragment of the name
            out += [f"# tier {t} - names by fragment", "Show", f"    BaseType {_quote(frags)}"] + style[t] + [""]
            count += len(frags)

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
    rarity_cfg = cfg.get(f"wl_rarity_tier_{game}") or {}
    for cat, classes in RARITY_CATEGORIES.get(game, {}).items():       # rarity first: it beats every block of the category
        for rar in RARITY_CHOICES:
            t = _valid((rarity_cfg.get(cat) or {}).get(rar))
            if not t:
                continue
            title = f"# rarity: {gear_names.get(cat[len(GEAR_PREFIX):], cat)} - {rar} - tier {t}"
            if t == "C":
                out += [title, "Hide", f"    Class == {_quote(classes)}", f"    Rarity {rar}", ""]
            else:
                out += [title, "Show", f"    Class == {_quote(classes)}", f"    Rarity {rar}"] + style[t] + [""]
                count += 1

    gear_items = gear_block_items(game, base_text)
    block_t = gear_block_tiers(game, cfg, gear_items)
    for key, gid, ty, _tag, conds in gear_items:
        t = block_t[key]
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
            "gear_tiers": gear_t, "block_tiers": block_t, "stack_min": stack_min}
