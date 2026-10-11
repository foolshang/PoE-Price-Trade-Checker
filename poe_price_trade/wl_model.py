"""Whitelist tab model (no Tk): what the player has changed, how it maps to config keys, and the rows the
item list shows. Everything about tiers is delegated to filter_whitelist - the list shows exactly what the
generator will write, never a second opinion.

Only changes are stored (an item / category / block / class the player did not touch keeps NeverSink's
starting tier). Config keys (all per game where it matters), read by filter_whitelist:
    wl_item_tier_<g> {name: S|A|B|C}      wl_cat_tier_<g> {category: S|A|B|C}   (Unique / Tablet / "gear:<id>" too)
    wl_block_tier_<g> {gear block key: tier}   wl_rarity_tier_<g> {jewel/flask category: {rarity: tier}}   wl_class_tier_<g> {class: tier}   wl_unique_tier_<g> {name: tier}
    wl_tier_stack {S|A|B: N}              wl_item_stack_<g> {name: N}           (stack-size minimums)
    wl_tier_style {S|A|B|G|Tablet|Map: style}
    whitelist_gold / whitelist_gold_min, wl_map_on / wl_map_tier_min / wl_map_rarity_min,
    whitelist_gem_uncut_<g> / whitelist_gem_names_<g> / whitelist_gem_tier, whitelist_custom_<g>
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
from typing import Optional

from . import filter_gen, filter_style, filter_whitelist as w

TIER_CHOICES = ("S", "A", "B")
ALL_CHOICES = ("S", "A", "B", "C")
TABLET_CATEGORY = w.TABLET_CATEGORY
SPECIAL_CATEGORY = "Special"
UNIQUE = w.UNIQUE_CATEGORY
GEAR_PREFIX = w.GEAR_PREFIX
STYLE_LABELS = ("S", "A", "B", "G", "Tablet", "Map")
RARITIES = ("Normal", "Magic", "Rare", "Unique")


def _count(v) -> int:
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return 1


def tier_label(tier: str) -> str:
    """What the list shows after a name: S / A / B, nothing-shown C, and Tablet for a tablet nobody tiered."""
    return "Tablet" if tier == w.TABLET_DEFAULT else tier


@dataclass
class Row:
    key: str             # what the setters take (item name / unique name / class / group id)
    label: str           # text shown
    tier: str            # effective S / A / B / C / T
    default: str         # NeverSink's starting tier for this row
    user_set: bool       # the player changed it (item / unique / class / block level)
    note: str = ""       # warning / hint shown next to the row
    stackable: bool = False   # the name can stack (a minimum stack size applies)
    stack: int = 1       # the stack size needed to show it (1 = every one)
    stack_set: bool = False   # the player set this name's own minimum


class WlModel:
    def __init__(self, game: str):
        self.game = game
        self.item_tier: dict = {}
        self.cat_tier: dict = {}
        self.class_tier: dict = {}
        self.unique_tier: dict = {}
        self.block_tier: dict = {}
        self.rarity_tier: dict = {}          # {category id: {Normal|Magic|Rare: S|A|B|C}} (absent = by NeverSink)
        self.tier_stack: dict = {}
        self.item_stack: dict = {}
        self.tier_style: dict = {}
        self.gold = False
        self.gold_min = 0
        self.map_on = False
        self.map_tier = 1
        self.map_rarity = "Normal"
        self.gem_uncut: dict = {}
        self.gem_names: list = []
        self.gem_tier = "B"
        self.custom: list = []          # [{"name", "rarities", "tier"}]
        # data (set_data)
        self.hub: Optional[dict] = None
        self.base_text = ""
        self.extra_names: set = set()
        self._names: dict = {}
        self._defaults: dict = {}
        self._stack_defaults: dict = {}
        self._stackable: set = set()
        self._gear_items: list = []
        self._entries: list = []
        self._unique_defaults: dict = {}
        self._loaded = False
        # the lists (category ids) the settings were written with: None = a file / config from before this was
        # recorded (v0.10.0 - v0.10.2); a list newer than that was never offered to the player, so what it holds
        # was filled in by the program (see _settle)
        self.known_lists: Optional[list] = None
        self._settle_pending = False
        self._notes: list = []

    # ------------------------------------------------------------------ data

    @property
    def loaded(self) -> bool:
        return self._loaded

    def set_data(self, hub: Optional[dict], base_text: str, extra_names=None) -> None:
        self.hub, self.base_text, self.extra_names = hub, base_text or "", set(extra_names or ())
        self._names = w.universe(self.game, hub, self.base_text)
        self._defaults, self._stack_defaults = w.start_tiers(self.base_text)
        self._stackable = w.stack_info(self.base_text)[1]
        self._gear_items = w.gear_block_items(self.game, self.base_text) if self.base_text else []
        self._unique_defaults = w.unique_base_defaults(self.base_text)
        real = w.known_names(self.base_text) | self.extra_names
        self._entries = [(n, b) for n, b in w.unique_entries(hub) if b in real]
        self._default_lines = w.default_tier_lines(self.base_text) if self.base_text else {}
        self._loaded = True
        if self._settle_pending:
            self._settle()

    # ------------------------------------------------------------------ lists newer than the settings

    def lists_now(self) -> list:
        """Every list the tab offers: the category ids, plus the name-fragment rows of the special category."""
        return [c for c, _l in self.categories()] + [w.BASE_PREFIX + f for f in w.SPECIAL_BASE.get(self.game, [])]

    def _new_list_ids(self) -> list:
        """The lists that appeared after v0.10.2: the name categories, the generic-gem group, the fragment rows."""
        return ([c for c, _p in w.NAMED_CATEGORIES.get(self.game, [])]
                + [w.gear_cat(g) for g in w.NEW_GEAR_GROUPS if any(g == x for x, _n, _d in w.GEAR_GROUPS.get(self.game, []))]
                + [w.BASE_PREFIX + f for f in w.SPECIAL_BASE.get(self.game, [])])

    def _list_rows(self, lst: str) -> list:
        """[(store, key)] of what the player's setting for a list is made of."""
        if lst.startswith(w.BASE_PREFIX):
            return [(self.class_tier, lst)]
        if self.is_gear(lst):
            return [(self.block_tier, k) for k in self._gear_keys(lst)]
        return [(self.item_tier, n) for n in self._names_of(lst)]

    def _list_is_all_c(self, lst: str) -> bool:
        """True when every row of the list is C (by its own tier or the whole category's)."""
        rows = self._list_rows(lst)
        whole = self.cat_tier.get(lst) == "C"
        return bool(rows) and all(st.get(k) == "C" or (whole and k not in st) for st, k in rows)

    def _clear_list(self, lst: str) -> None:
        for st, k in self._list_rows(lst):
            st.pop(k, None)
        self.cat_tier.pop(lst, None)
        if not lst.startswith(w.BASE_PREFIX) and not self.is_gear(lst):
            for n in self._names_of(lst):
                self.item_stack.pop(n, None)

    def _settle(self) -> None:
        """Lists newer than the settings hold values the player never chose. A file that recorded its lists
        (known_lists) simply lacks the new ones -> NeverSink's defaults. A file from v0.10.0 - v0.10.2 recorded
        nothing, and its old-file import filled every new list with C: a new list that is C all through is taken
        as filled by the program (a list the player emptied on purpose is told apart by known_lists, which every
        file since then carries)."""
        self._settle_pending = False
        fresh = []
        for lst in self._new_list_ids():
            if self.known_lists is not None:
                if lst in self.known_lists or lst not in self.lists_now():
                    continue
            elif not self._list_is_all_c(lst):
                continue
            self._clear_list(lst)
            fresh.append(lst)
        self.known_lists = self.lists_now()
        if fresh:
            labels = dict(self.categories())
            names = [labels.get(c) or (f'ชื่อที่มีคำว่า "{c[len(w.BASE_PREFIX):]}"' if c.startswith(w.BASE_PREFIX) else c)
                     for c in fresh]
            self._notes.append("หมวดที่ไฟล์/ค่าที่เปิดมายังไม่มี หรือเป็น C ทั้งหมวดที่โปรแกรมเติมให้เอง ใช้ค่าเริ่มต้น"
                               "ของ NeverSink แทน: " + ", ".join(names))

    def adopt_known_lists(self, known: Optional[list]) -> None:
        """Remember which lists the settings were written with; the check runs when the data is (or already is) loaded."""
        self.known_lists = list(known) if isinstance(known, (list, tuple)) else None
        self._settle_pending = True
        if self._loaded:
            self._settle()

    def take_notes(self) -> list:
        out, self._notes = self._notes, []
        return out

    def _real(self) -> set:
        return w.known_names(self.base_text) | self.extra_names

    # ------------------------------------------------------------------ config

    def cfg(self) -> dict:
        """The config dict the generator reads - exactly what to_config writes."""
        return self.to_config({})

    @classmethod
    def from_config(cls, fg: dict, game: str) -> "WlModel":
        m = cls(game)
        g = game
        m.item_tier = dict(fg.get(f"wl_item_tier_{g}") or {})
        m.cat_tier = dict(fg.get(f"wl_cat_tier_{g}") or {})
        m.class_tier = dict(fg.get(f"wl_class_tier_{g}") or {})
        m.unique_tier = dict(fg.get(f"wl_unique_tier_{g}") or {})
        m.block_tier = dict(fg.get(f"wl_block_tier_{g}") or {})
        m.rarity_tier = {c: {r: t for r, t in (v or {}).items() if r in w.RARITY_CHOICES and t in ALL_CHOICES}
                         for c, v in (fg.get(f"wl_rarity_tier_{g}") or {}).items()
                         if c in w.RARITY_CATEGORIES.get(g, {}) and isinstance(v, dict)}
        m.rarity_tier = {c: v for c, v in m.rarity_tier.items() if v}
        m.tier_stack = {k: n for k, n in ((k, _count(v)) for k, v in (fg.get("wl_tier_stack") or {}).items())
                        if k in TIER_CHOICES and n > 1}
        m.item_stack = {str(k): _count(v) for k, v in (fg.get(f"wl_item_stack_{g}") or {}).items()}
        # the old equipment settings (one tier per group / for all gear) become the gear categories' tiers
        legacy_groups = fg.get(f"wl_gear_tier_{g}") or {}
        whole = m.cat_tier.pop(w.GEAR_CATEGORY, None)
        for gid, _name, _d in w.GEAR_GROUPS.get(g, []):
            tier = legacy_groups.get(gid) if legacy_groups.get(gid) in ALL_CHOICES else whole
            if tier in ALL_CHOICES and w.gear_cat(gid) not in m.cat_tier:
                m.cat_tier[w.gear_cat(gid)] = tier
        m.tier_style = {k: filter_style.normalize_style(v) for k, v in (fg.get("wl_tier_style") or {}).items()
                        if k in STYLE_LABELS and isinstance(v, dict)}
        m.gold = bool(fg.get("whitelist_gold"))
        try:
            m.gold_min = max(0, int(fg.get("whitelist_gold_min") or 0))
        except (TypeError, ValueError):
            m.gold_min = 0
        m.known_lists = fg.get(f"wl_lists_{g}") if isinstance(fg.get(f"wl_lists_{g}"), list) else None
        m._settle_pending = True
        m.map_on = bool(fg.get("wl_map_on"))
        try:
            m.map_tier = max(1, min(16, int(fg.get("wl_map_tier_min") or 1)))
        except (TypeError, ValueError):
            m.map_tier = 1
        m.map_rarity = fg.get("wl_map_rarity_min") if fg.get("wl_map_rarity_min") in RARITIES else "Normal"
        m.gem_uncut = {str(b): max(1, int(lv)) for b, lv in (fg.get(f"whitelist_gem_uncut_{g}") or {}).items()
                       if str(lv).isdigit() or isinstance(lv, int)}
        m.gem_names = [str(n) for n in (fg.get(f"whitelist_gem_names_{g}") or []) if n]
        m.gem_tier = fg.get("whitelist_gem_tier") if fg.get("whitelist_gem_tier") in ALL_CHOICES else "B"
        m.custom = []
        for e in fg.get(f"whitelist_custom_{g}") or []:
            if isinstance(e, str):
                m.custom.append({"name": e, "rarities": list(RARITIES), "tier": "B"})
            elif isinstance(e, dict) and e.get("name"):
                rs = [r for r in RARITIES if r in set(e.get("rarities") or [])] or ["Normal"]
                m.custom.append({"name": e["name"], "rarities": rs,
                                 "tier": e.get("tier") if e.get("tier") in ALL_CHOICES else "B"})
        return m

    def to_config(self, fg: dict) -> dict:
        g = self.game
        fg["wl_v2"] = True
        fg[f"wl_item_tier_{g}"] = dict(self.item_tier)
        fg[f"wl_cat_tier_{g}"] = dict(self.cat_tier)
        fg[f"wl_class_tier_{g}"] = dict(self.class_tier)
        fg[f"wl_unique_tier_{g}"] = dict(self.unique_tier)
        fg.pop(f"wl_gear_tier_{g}", None)               # folded into wl_cat_tier_<g>["gear:<id>"]
        fg[f"wl_block_tier_{g}"] = dict(self.block_tier)
        fg[f"wl_rarity_tier_{g}"] = {c: dict(v) for c, v in self.rarity_tier.items() if v}
        lists = self.lists_now() if self._loaded else self.known_lists      # unknown stays unknown (not written)
        if lists is None:
            fg.pop(f"wl_lists_{g}", None)
        else:
            fg[f"wl_lists_{g}"] = lists
        fg["wl_tier_stack"] = dict(self.tier_stack)
        fg[f"wl_item_stack_{g}"] = dict(self.item_stack)
        fg["wl_tier_style"] = {k: copy.deepcopy(v) for k, v in self.tier_style.items()
                               if v and not filter_style.is_empty(v)}
        fg["whitelist_gold"] = bool(self.gold)
        fg["whitelist_gold_min"] = int(self.gold_min)
        fg["wl_map_on"] = bool(self.map_on)
        fg["wl_map_tier_min"] = int(self.map_tier)
        fg["wl_map_rarity_min"] = self.map_rarity
        if filter_gen.WHITELIST_GEM_UNCUT.get(g):
            fg[f"whitelist_gem_uncut_{g}"] = dict(self.gem_uncut)
        else:
            fg[f"whitelist_gem_names_{g}"] = list(self.gem_names)
        fg["whitelist_gem_tier"] = self.gem_tier
        fg[f"whitelist_custom_{g}"] = [{"name": e["name"], "rarities": list(e["rarities"]), "tier": e["tier"]}
                                       for e in self.custom]
        return fg

    # ------------------------------------------------------------------ categories

    def categories(self) -> list:
        """[(id, label)] in the order the list offers them."""
        out = [(c, c) for c in filter_gen.WHITELIST_CATEGORIES.get(self.game, [])]
        out += [(c, c) for c, _p in w.NAMED_CATEGORIES.get(self.game, [])]      # Runegraft, Vial, Corpse ...
        out.append((w.OTHER_CATEGORY, "อื่นๆ (NeverSink จัด tier ให้)"))
        out.append((UNIQUE, "Unique"))
        if self.game == "poe2":
            out.append((TABLET_CATEGORY, "Tablet"))
        if self._special_keys():
            out.append((SPECIAL_CATEGORY, "กุญแจ/ของพิเศษ (class)"))
        for gid, name, _d in w.GEAR_GROUPS.get(self.game, []):      # every gear group is a category of its own
            out.append((w.gear_cat(gid), name))
        return out

    @staticmethod
    def is_gear(cat: str) -> bool:
        return cat.startswith(GEAR_PREFIX)

    def _gear_keys(self, cat: str) -> list:
        gid = cat[len(GEAR_PREFIX):]
        return [k for k, g, _ty, _tag, _c in self._gear_items if g == gid]

    def _special_keys(self) -> list:
        return list(w.SPECIAL_CLASSES.get(self.game, [])) + [w.BASE_PREFIX + f for f in w.SPECIAL_BASE.get(self.game, [])]

    def _names_of(self, cat: str) -> list:
        tab = lambda n: w.is_tablet(self.game, n)
        if cat == TABLET_CATEGORY:
            return sorted(n for n in self._names if tab(n))
        return sorted(n for n, c in self._names.items() if c == cat and not tab(n))

    def _resolved(self) -> dict:
        return w.resolve_tiers(self.game, self.cfg(), self._names, self._defaults)

    def default_of(self, name: str) -> str:
        if w.is_tablet(self.game, name):
            return w.TABLET_DEFAULT
        return self._defaults.get(name) or "B"

    # ------------------------------------------------------------------ rows

    def rows(self, cat: str, query: str = "") -> list:
        q = (query or "").strip().lower()
        out: list = []
        if self.is_gear(cat):
            gid = cat[len(GEAR_PREFIX):]
            group_tier = w.gear_tiers(self.game, self.cfg())[gid]
            block_tiers = w.gear_block_tiers(self.game, self.cfg(), self._gear_items)
            for key, g, ty, _tag, conds in self._gear_items:
                if g != gid:
                    continue
                label = w.block_label(ty, conds)
                if q and q not in label.lower():
                    continue
                out.append(Row(key, label, block_tiers[key], group_tier, key in self.block_tier))
            return out
        if cat == SPECIAL_CATEGORY:
            for c in w.SPECIAL_CLASSES.get(self.game, []):
                if q and q not in c.lower():
                    continue
                t = self.class_tier.get(c) if self.class_tier.get(c) in ALL_CHOICES else "B"
                out.append(Row(c, c, t, "B", c in self.class_tier))
            for f in w.SPECIAL_BASE.get(self.game, []):
                key, label = w.BASE_PREFIX + f, f'ชื่อที่มีคำว่า "{f}" (ที่ยังไม่อยู่ในรายการ)'
                if q and q not in label.lower():
                    continue
                t = self.class_tier.get(key) if self.class_tier.get(key) in ALL_CHOICES else "B"
                out.append(Row(key, label, t, "B", key in self.class_tier))
            return out
        if cat == UNIQUE:
            base_tier, conflicts = w.resolve_unique_tiers(self.game, self.cfg(), self._entries, self._unique_defaults)
            clash = {b for b, _t in conflicts}
            user = self.unique_tier
            whole = self.cat_tier.get(UNIQUE) if self.cat_tier.get(UNIQUE) in ALL_CHOICES else None
            for name, base in sorted(self._entries, key=lambda e: (e[0].lower(), e[1])):
                label = f"{name} ({base})"
                if q and q not in label.lower():
                    continue
                default = self._unique_defaults.get(base) or "B"
                tier = user.get(name) if user.get(name) in ALL_CHOICES else (whole or default)
                note = "⚠ ฐานเดียวกันตั้ง tier ต่างกัน — ใช้ tier สูงสุด" if base in clash else ""
                out.append(Row(name, label, tier, default, name in user, note))
            return out
        tiers = self._resolved()
        mins = w.stack_minimums(self.cfg(), self.game, tiers, self._stack_defaults, self._stackable)
        for name in self._names_of(cat):
            if q and q not in name.lower():
                continue
            out.append(Row(name, name, tiers[name], self.default_of(name), name in self.item_tier,
                           stackable=name in self._stackable, stack=mins.get(name, 1),
                           stack_set=name in self.item_stack))
        return out

    def unique_conflicts(self) -> list:
        return w.resolve_unique_tiers(self.game, self.cfg(), self._entries, self._unique_defaults)[1]

    # ------------------------------------------------------------------ setters

    def _store(self, cat: str) -> dict:
        if self.is_gear(cat):
            return self.block_tier
        return {SPECIAL_CATEGORY: self.class_tier, UNIQUE: self.unique_tier}.get(cat, self.item_tier)

    def set_row(self, cat: str, key: str, tier: str) -> None:
        if tier in ALL_CHOICES:
            self._store(cat)[key] = tier

    def reset_row(self, cat: str, key: str) -> None:
        self._store(cat).pop(key, None)
        self.item_stack.pop(key, None)

    def set_stack(self, keys, n: int) -> None:
        """The player's own stack minimum for these names (1 = show every one, whatever NeverSink says)."""
        for k in keys:
            self.item_stack[k] = max(1, int(n))

    def has_rarity(self, cat: str) -> bool:
        """The category can also be tiered by rarity (jewels, flasks / charms)."""
        return cat in w.RARITY_CATEGORIES.get(self.game, {})

    def get_rarity(self, cat: str, rarity: str) -> Optional[str]:
        """The player's tier for this rarity of the category, None = by NeverSink's blocks."""
        t = (self.rarity_tier.get(cat) or {}).get(rarity)
        return t if t in ALL_CHOICES else None

    def set_rarity(self, cat: str, rarity: str, tier: Optional[str]) -> None:
        if not self.has_rarity(cat) or rarity not in w.RARITY_CHOICES:
            return
        if tier in ALL_CHOICES:
            self.rarity_tier.setdefault(cat, {})[rarity] = tier
        else:
            self.rarity_tier.get(cat, {}).pop(rarity, None)
            if not self.rarity_tier.get(cat):
                self.rarity_tier.pop(cat, None)

    def set_tier_stack(self, tier: str, n: int) -> None:
        if tier in TIER_CHOICES:
            if int(n) > 1:
                self.tier_stack[tier] = int(n)
            else:
                self.tier_stack.pop(tier, None)

    def toggle_row(self, cat: str, key: str, active: str) -> None:
        """Tick = into the active tier, untick = C (hidden)."""
        row = next((r for r in self.rows(cat) if r.key == key), None)
        if row is None:
            return
        self.set_row(cat, key, "C" if row.tier != "C" else active)

    def set_category(self, cat: str, tier: str) -> None:
        """Every row of the category to `tier`; rows the player set one by one are cleared (the whole-category
        tier would lose against them)."""
        if tier not in ALL_CHOICES:
            return
        if self.is_gear(cat):
            self.cat_tier[cat] = tier
            self.rarity_tier.pop(cat, None)              # a rarity tier would win over the whole-category tier
            for k in self._gear_keys(cat):
                self.block_tier.pop(k, None)
        elif cat == UNIQUE:
            self.cat_tier[cat] = tier
            self._store(cat).clear()
        elif cat == SPECIAL_CATEGORY:
            for c in self._special_keys():
                self.class_tier[c] = tier
        elif cat == TABLET_CATEGORY:
            for n in self._names_of(cat):
                self.item_tier[n] = tier
        else:
            self.cat_tier[cat] = tier
            for n in self._names_of(cat):
                self.item_tier.pop(n, None)

    def reset_category(self, cat: str) -> None:
        """Back to NeverSink's values for the whole category."""
        if self.is_gear(cat):
            self.cat_tier.pop(cat, None)
            self.rarity_tier.pop(cat, None)
            for k in self._gear_keys(cat):
                self.block_tier.pop(k, None)
        elif cat == UNIQUE:
            self.cat_tier.pop(cat, None)
            self._store(cat).clear()
        elif cat == SPECIAL_CATEGORY:
            for c in self._special_keys():
                self.class_tier.pop(c, None)
        else:
            self.cat_tier.pop(cat, None)
            for n in self._names_of(cat):
                self.item_tier.pop(n, None)
                self.item_stack.pop(n, None)

    def category_tier(self, cat: str) -> Optional[str]:
        return self.cat_tier.get(cat) if self.cat_tier.get(cat) in ALL_CHOICES else None

    def changed_count(self, cat: str) -> int:
        """How many rows of the category differ from the starting values (list header hint)."""
        n = sum(1 for r in self.rows(cat) if r.user_set)
        return n + (1 if self.category_tier(cat) else 0) + len(self.rarity_tier.get(cat) or {})

    # ------------------------------------------------------------------ styles

    def base_style(self, label: str) -> dict:
        """NeverSink's own look of a tier (or our preset for G / Tablet / Map)."""
        default_lines = (getattr(self, "_default_lines", {}) or {}).get(label)
        return (filter_style.lines_to_style(default_lines) if default_lines
                else filter_style.normalize_style(filter_style.DEFAULT_STYLES.get(label)))

    def effective_style(self, label: str) -> dict:
        """The base look with the player's changes on top."""
        return filter_style.merge_styles(self.base_style(label), self.tier_style.get(label))

    def set_style_from_editor(self, label: str, style: dict) -> None:
        """Keep only what differs from the base look: a part equal to the base keeps following NeverSink, a
        part with another value is stored, a part the editor has unticked while the base has it is stored as
        OFF (it must not come back). The S / A / B sound is shared with the NeverSink tab and never stored."""
        base, new = self.base_style(label), filter_style.normalize_style(style)
        out: dict = {}
        off: list = []
        for k in ("text", "border", "bg", "size", "icon", "effect"):
            if new[k] is None:
                if base[k] is not None:
                    off.append(k)
            elif new[k] != base[k]:
                out[k] = new[k]
        if label not in TIER_CHOICES:
            if new["sound"]["kind"] == "none":
                if base["sound"]["kind"] != "none":
                    off.append("sound")
            elif new["sound"] != base["sound"]:
                out["sound"] = new["sound"]
        if off:
            out["off"] = off
        self.set_style(label, out or None)

    def set_style(self, label: str, style: Optional[dict]) -> None:
        if style is None or filter_style.is_empty(style):
            self.tier_style.pop(label, None)
        else:
            self.tier_style[label] = filter_style.normalize_style(style)

    # ------------------------------------------------------------------ legacy

    @staticmethod
    def legacy_present(fg: dict, game: str) -> bool:
        return any(k in fg for k in (f"whitelist_cats_{game}", f"whitelist_cat_exclude_{game}", "whitelist_unique_all"))

    @classmethod
    def convert_legacy(cls, fg: dict, game: str) -> tuple:
        """(updates, notes): the old "show these categories / these names only" settings as wl_* keys.
        Nothing is removed from fg; `wl_converted_<game>` says it was done. Nothing to do -> ({}, [])."""
        if fg.get(f"wl_converted_{game}") or not cls.legacy_present(fg, game):
            return {}, []
        if any(k in fg for k in (f"wl_cat_tier_{game}", f"wl_item_tier_{game}", f"wl_gear_tier_{game}",
                                 f"wl_block_tier_{game}")):
            return {f"wl_converted_{game}": True}, []
        cats = set(fg.get(f"whitelist_cats_{game}") or [])
        cat_tier = {c: "C" for c in filter_gen.WHITELIST_CATEGORIES.get(game, []) if c not in cats}
        cat_tier[w.OTHER_CATEGORY] = "C"                  # the old whitelist never showed these
        item_tier = {}
        for c, names in (fg.get(f"whitelist_cat_exclude_{game}") or {}).items():
            if c in cats:
                for n in names or []:
                    item_tier[str(n)] = "C"
        if not fg.get("whitelist_unique_all"):
            cat_tier[UNIQUE] = "C"
        if game == "poe2" and "Fragment" not in cats:
            cat_tier[TABLET_CATEGORY] = "C"
        for gid, _name, _d in w.GEAR_GROUPS.get(game, []):
            cat_tier[w.gear_cat(gid)] = "C"               # the old whitelist had no equipment
        updates = {f"wl_cat_tier_{game}": cat_tier, f"wl_item_tier_{game}": item_tier, f"wl_converted_{game}": True}
        notes = ["แปลง whitelist เดิมเข้าแบบใหม่แล้ว: หมวดที่ไม่ได้ติ๊ก = tier C (ซ่อน), ชื่อที่เอาออก = C, "
                 "อุปกรณ์ทั้งหมวด = C เหมือนเดิม (ค่าเดิมไม่ถูกลบ)",
                 "แปลงไม่ได้ตรงตัว: ชื่อที่ NeverSink ซ่อน (tier C) จะยังซ่อนต่อ แม้เคยติ๊กทั้งหมวด, "
                 "map/waystone กลับเป็นโชว์ตามเกม (ตั้งใหม่ในส่วนแยก)"]
        return updates, notes

    # ------------------------------------------------------------------ build

    def build(self, quest_text: str = "", sound_names: Optional[dict] = None) -> dict:
        return w.build_whitelist_filter(self.game, self.cfg(), self.base_text, self.hub, quest_text,
                                        sound_names, self.extra_names)
