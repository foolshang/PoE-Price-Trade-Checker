"""Whitelist tab model (no Tk): what the player has changed, how it maps to config keys, and the rows the
item list shows. Everything about tiers is delegated to filter_whitelist - the list shows exactly what the
generator will write, never a second opinion.

Only changes are stored (an item / category / block / class the player did not touch keeps NeverSink's
starting tier). Config keys (all per game where it matters), read by filter_whitelist:
    wl_item_tier_<g> {name: S|A|B|C|D}    wl_cat_tier_<g> {category: S|A|B|C|D} (Unique / Tablet / "gear:<id>" too)
        (S / A / B / C are shown, each with a style; D = hidden. `wl_tier_format` = 2 says so: a config without it
        was written when C was the hidden tier, so its C values become D on load - see _migrate_hidden)
    wl_block_tier_<g> {gear block key: tier}   wl_unique_tier_<g> {name: tier}
    wl_rarity_rows_<g> {"Flask" | "Charm": {"custom": bool, "tiers": {Normal|Magic|Rare: S|A|B|C|D}}}
        (equipment NeverSink writes - story, rare by ilvl, craft, exotic, jewels, keys / special classes ... - is not a
        setting any more: the file carries NeverSink's own blocks; keys of the old layout are dropped on load with a note)
    wl_equip_rows_<g> {item class: {"custom": bool, "tiers": {Normal|Magic|Rare: S|A|B|C|D}}}   (equipment by class)
    wl_tier_stack {S|A|B|C: N}            wl_item_stack_<g> {name: N}           (stack-size minimums)
    wl_tier_style {S|A|B|C|G|Tablet|Map|Gem: style}   (a style's sound is its own: the tabs share only Q)
    whitelist_gold / whitelist_gold_min, wl_map_on / wl_map_tier_min / wl_map_rarity_min,
    whitelist_gem_uncut_<g> / whitelist_gem_names_<g> / whitelist_gem_tier, whitelist_custom_<g>
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
from typing import Optional

from . import filter_core, filter_gen, filter_style, filter_whitelist as w

TIER_CHOICES = w.TIERS                 # the shown tiers (S A B C): each has a style, a stack minimum, a sound
ALL_CHOICES = w.ALL_TIERS              # ... and D, hidden
HIDE = w.HIDE_TIER
TABLET_CATEGORY = w.TABLET_CATEGORY
FLASK_CATEGORY = w.FLASK_CATEGORY
EQUIP_CATEGORY = w.EQUIP_CATEGORY
UNIQUE = w.UNIQUE_CATEGORY
GEAR_PREFIX = w.GEAR_PREFIX
STYLE_LABELS = ("S", "A", "B", "C", "G", "Tablet", "Map", "Gem")
RARITIES = ("Normal", "Magic", "Rare", "Unique")
DEFAULT_CUSTOM_TIER = "B"      # a row set "myself" starts every rarity at B (NeverSink is the "default" mode, not a choice)
_AUTO_NOTE = ("ช่อง \"ตาม NeverSink\" ของแถวที่ตั้งค่าเอง (Flask/Charm/Tincture หรืออุปกรณ์ตาม class) ถูกแปลงเป็น B แล้ว "
              "— ถ้าต้องการ NeverSink ให้เลือก \"ค่าเริ่มต้น\" ของแถวนั้น")
_HIDDEN_NOTE = ("tier C เดิม (ซ่อน) {n} ค่า ถูกแปลงเป็น D (ซ่อน) แล้ว — tier C ใหม่คือ tier ที่โชว์ด้วยสไตล์ของตัวเอง "
                "(จางกว่า B) · S/A/B ที่ตั้งไว้คงเดิม")
_RARE_NOTE = ("ข้ามค่า Rare ของ Flask / Charm / Tincture ที่เคยตั้งไว้ (ในเกมของพวกนี้ไม่มี Rare — "
              "ใช้ block ของ NeverSink ตามเดิม)")


def _count(v) -> int:
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return 1


def tier_label(tier: str) -> str:
    """What the list shows after a name: S / A / B / C, D for hidden, and Tablet for a tablet nobody tiered."""
    return "Tablet" if tier == w.TABLET_DEFAULT else tier


@dataclass
class Row:
    key: str             # what the setters take (item name / unique name / class / group id)
    label: str           # text shown
    tier: str            # effective S / A / B / C / D / T
    default: str         # NeverSink's starting tier for this row
    user_set: bool       # the player changed it (item / unique / class / block level)
    note: str = ""       # warning / hint shown next to the row
    stackable: bool = False   # the name can stack (a minimum stack size applies)
    stack: int = 1       # the stack size needed to show it (1 = every one)
    stack_set: bool = False   # the player set this name's own minimum


def _migrate_hidden(fg: dict, game: str) -> tuple:
    """(config, n): a config written before tier D has no `wl_tier_format`, and its C is the hidden tier. C is a shown
    tier now, so every C of that config (item / category / unique / block tiers, rarity and equipment rows, the gem
    tier, typed names) becomes D - once: the config is saved with wl_tier_format = 2, and the file / config that has
    it is never converted again. S / A / B values the player set stay as they are. n = how many values became D."""
    if fg.get("wl_tier_format") == w.TIER_FORMAT:
        return fg, 0
    out = dict(fg)
    n = 0

    def conv(v):
        nonlocal n
        if v == "C":
            n += 1
            return HIDE
        return v

    def tiers_of(d):
        return {k: conv(v) for k, v in d.items()} if isinstance(d, dict) else d

    for key in (f"wl_item_tier_{game}", f"wl_cat_tier_{game}", f"wl_unique_tier_{game}", f"wl_block_tier_{game}",
                f"wl_gear_tier_{game}"):
        if isinstance(fg.get(key), dict):
            out[key] = tiers_of(fg[key])
    for key in (f"wl_rarity_rows_{game}", f"wl_equip_rows_{game}"):
        raw = fg.get(key)
        if isinstance(raw, dict):
            rows = {}
            for rid, row in raw.items():
                if isinstance(row, dict) and isinstance(row.get("tiers"), dict):
                    row = dict(row, tiers=tiers_of(row["tiers"]))
                rows[rid] = row
            out[key] = rows
    legacy = fg.get(f"wl_rarity_tier_{game}")
    if isinstance(legacy, dict):
        out[f"wl_rarity_tier_{game}"] = {k: tiers_of(v) if isinstance(v, dict) else v for k, v in legacy.items()}
    if fg.get("whitelist_gem_tier") == "C":
        out["whitelist_gem_tier"] = conv("C")
    custom = fg.get(f"whitelist_custom_{game}")
    if isinstance(custom, list):
        out[f"whitelist_custom_{game}"] = [dict(e, tier=conv(e.get("tier"))) if isinstance(e, dict) else e
                                           for e in custom]
    return out, n


def _fill_custom(row: dict, choices) -> None:
    """A row set "myself" has a tier (S / A / B / C / D) for every rarity: the missing ones start at B."""
    if row.get("custom"):
        for r in choices:
            row["tiers"].setdefault(r, DEFAULT_CUSTOM_TIER)


class WlModel:
    def __init__(self, game: str):
        self.game = game
        self.item_tier: dict = {}
        self.cat_tier: dict = {}
        self.unique_tier: dict = {}
        self.block_tier: dict = {}
        self.rarity_rows: dict = {}          # {"Flask"|"Charm": {"custom": bool, "tiers": {Normal|Magic|Rare: S|A|B|C|D}}}
        self.equip_rows: dict = {}           # {class: {"custom": bool, "tiers": {Normal|Magic|Rare: S|A|B|C|D}}}
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
        self._entries = [(n, b) for n, b in w.unique_entries(hub) if b in real and not w.bad_name(b)]
        self._default_lines = w.default_tier_lines(self.base_text) if self.base_text else {}
        self._loaded = True
        if self._settle_pending:
            self._settle()

    # ------------------------------------------------------------------ lists newer than the settings

    def lists_now(self) -> list:
        """Every list the tab offers (the category ids)."""
        return [c for c, _l in self.categories()]

    def _new_list_ids(self) -> list:
        """The lists that appeared after v0.10.2: the name categories and the generic-gem group."""
        return ([c for c, _p in w.NAMED_CATEGORIES.get(self.game, [])]
                + [w.gear_cat(g) for g in w.NEW_GEAR_GROUPS if any(g == x for x, _n, _d in w.listed_gear_groups(self.game))])

    def _list_rows(self, lst: str) -> list:
        """[(store, key)] of what the player's setting for a list is made of."""
        if self.is_gear(lst):
            return [(self.block_tier, k) for k in self._gear_keys(lst)]
        return [(self.item_tier, n) for n in self._names_of(lst)]

    def _list_is_all_c(self, lst: str) -> bool:
        """True when every row of the list is hidden (D; by its own tier or the whole category's)."""
        rows = self._list_rows(lst)
        whole = self.cat_tier.get(lst) == HIDE
        return bool(rows) and all(st.get(k) == HIDE or (whole and k not in st) for st, k in rows)

    def _clear_list(self, lst: str) -> None:
        for st, k in self._list_rows(lst):
            st.pop(k, None)
        self.cat_tier.pop(lst, None)
        if not self.is_gear(lst):
            for n in self._names_of(lst):
                self.item_stack.pop(n, None)

    def _settle(self) -> None:
        """Lists newer than the settings hold values the player never chose. A file that recorded its lists
        (known_lists) simply lacks the new ones -> NeverSink's defaults. A file from v0.10.0 - v0.10.2 recorded
        nothing, and its old-file import filled every new list with hidden (C then, D now): a new list hidden all through is taken
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
            names = [labels.get(c) or c for c in fresh]
            self._notes.append("หมวดที่ไฟล์/ค่าที่เปิดมายังไม่มี หรือซ่อน (D) ทั้งหมวดที่โปรแกรมเติมให้เอง ใช้ค่าเริ่มต้น"
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
        fg, hidden_n = _migrate_hidden(fg, g)
        if hidden_n:
            m._notes.append(_HIDDEN_NOTE.format(n=hidden_n))
        fg, sound_notes = filter_core.migrate_sounds(fg)         # the S / A / B files of the NeverSink tab -> tier sounds
        m._notes += sound_notes
        m.item_tier = dict(fg.get(f"wl_item_tier_{g}") or {})
        m.cat_tier = dict(fg.get(f"wl_cat_tier_{g}") or {})
        m.unique_tier = dict(fg.get(f"wl_unique_tier_{g}") or {})
        m.block_tier = dict(fg.get(f"wl_block_tier_{g}") or {})
        m.rarity_rows = cls._read_rarity_rows(fg.get(f"wl_rarity_rows_{g}"), g)
        m.equip_rows = cls._read_equip_rows(fg.get(f"wl_equip_rows_{g}"), g)
        if (any(r.get("custom") and any(x not in r["tiers"] for x in w.RARITY_CHOICES) for r in m.rarity_rows.values())
                or any(r.get("custom") and any(x not in r["tiers"] for x in w.EQUIP_CHOICES) for r in m.equip_rows.values())):
            m._notes.append(_AUTO_NOTE)                         # an old "set myself" row with a rarity left on NeverSink
        for r in m.rarity_rows.values():
            _fill_custom(r, w.RARITY_CHOICES)
        for r in m.equip_rows.values():
            _fill_custom(r, w.EQUIP_CHOICES)
        if any(isinstance(r, dict) and w.RARITY_REMOVED in (r.get("tiers") or {})
               for rid, r in (fg.get(f"wl_rarity_rows_{g}") or {}).items()):
            m._notes.append(_RARE_NOTE)
        m.tier_stack = {k: n for k, n in ((k, _count(v)) for k, v in (fg.get("wl_tier_stack") or {}).items())
                        if k in TIER_CHOICES and n > 1}
        m.item_stack = {str(k): _count(v) for k, v in (fg.get(f"wl_item_stack_{g}") or {}).items()}
        # the old equipment settings (one tier per group / for all gear) become the gear categories' tiers
        legacy_groups = fg.get(f"wl_gear_tier_{g}") or {}
        whole = m.cat_tier.pop(w.GEAR_CATEGORY, None)
        for gid, _name, _d in w.listed_gear_groups(g):
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
        m._drop_removed_settings(fg)
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

    @staticmethod
    def _read_rarity_rows(raw, game: str) -> dict:
        ids = {rid for rid, _l, _c in w.rarity_rows(game)}
        out: dict = {}
        for rid, row in (raw or {}).items():
            if rid not in ids or not isinstance(row, dict):
                continue
            tiers = {r: t for r, t in (row.get("tiers") or {}).items() if r in w.RARITY_CHOICES and t in ALL_CHOICES}
            if tiers or row.get("custom"):
                out[rid] = {"custom": bool(row.get("custom")), "tiers": tiers}
        return out

    @staticmethod
    def _read_equip_rows(raw, game: str) -> dict:
        ids = set(w.equip_classes(game))
        out: dict = {}
        for cid, row in (raw or {}).items():
            if cid not in ids or not isinstance(row, dict):
                continue
            tiers = {r: t for r, t in (row.get("tiers") or {}).items() if r in w.EQUIP_CHOICES and t in ALL_CHOICES}
            if tiers or row.get("custom"):
                out[cid] = {"custom": bool(row.get("custom")), "tiers": tiers}
        return out

    def _drop_removed_settings(self, fg: dict) -> None:
        """Settings of categories the tab no longer has (the file now carries NeverSink's own blocks for them) are
        dropped once, with a note; the old Flask / Charm rarity values become the new "set myself" rows."""
        g = self.game
        removed: list = []
        names = {gid: n for gid, n, _d in w.GEAR_GROUPS.get(g, [])}
        cut = [gid for gid in names if gid not in w.GEAR_LISTED.get(g, ())]
        for gid in cut:
            if self.cat_tier.pop(w.gear_cat(gid), None) is not None:
                removed.append(names[gid] if gid != w.FLASK_GROUP else "Flask / Charm (ทั้งหมวด)")
        for key in list(self.block_tier):
            gid = w.gear_group_of(g, key.split("|")[0])
            if gid in cut:
                del self.block_tier[key]
                label = names.get(gid, gid) if gid != w.FLASK_GROUP else "Flask / Charm (ราย block)"
                if label not in removed:
                    removed.append(label)
        if fg.get(f"wl_class_tier_{g}"):
            removed.append("กุญแจ/ของพิเศษ (class)")
        legacy = fg.get(f"wl_rarity_tier_{g}") or {}
        if isinstance(legacy, dict):
            if legacy.get("gear:jewel"):
                removed.append("Jewel (rarity)")
            old_flask = legacy.get("gear:flask")
            if isinstance(old_flask, dict) and old_flask and not self.rarity_rows:
                tiers = {r: t for r, t in old_flask.items() if r in w.RARITY_CHOICES and t in ALL_CHOICES}
                if w.RARITY_REMOVED in old_flask:
                    self._notes.append(_RARE_NOTE)
                if tiers:
                    for rid, _l, _c in w.rarity_rows(g):          # the old box covered flasks and charms together
                        self.rarity_rows[rid] = {"custom": True, "tiers": dict(tiers)}
                        if any(x not in tiers for x in w.RARITY_CHOICES) and _AUTO_NOTE not in self._notes:
                            self._notes.append(_AUTO_NOTE)
                        _fill_custom(self.rarity_rows[rid], w.RARITY_CHOICES)
                    self._notes.append("rarity ของ Flask/Charm เดิมถูกแปลงเป็น \"ตั้งค่าเอง\" พร้อมค่าเดิมแล้ว")
        if removed:
            self._notes.append("ข้ามค่าที่เคยตั้งของหมวดที่ตัดออกแล้ว (ใช้ NeverSink แทน): " + ", ".join(removed))

    def to_config(self, fg: dict) -> dict:
        g = self.game
        fg["wl_v2"] = True
        fg["wl_tier_format"] = w.TIER_FORMAT
        fg["sound_format"] = filter_core.SOUND_FORMAT
        for k in ("sound_s", "sound_a", "sound_b", "sound_c"):     # now sound_1 .. sound_3 (NeverSink tab) / tier styles
            fg.pop(k, None)
        fg[f"wl_item_tier_{g}"] = dict(self.item_tier)
        fg[f"wl_cat_tier_{g}"] = dict(self.cat_tier)
        fg.pop(f"wl_class_tier_{g}", None)               # special classes are NeverSink's blocks now
        fg.pop(f"wl_rarity_tier_{g}", None)              # old jewel / flask rarity: see wl_rarity_rows
        fg[f"wl_unique_tier_{g}"] = dict(self.unique_tier)
        fg.pop(f"wl_gear_tier_{g}", None)               # folded into wl_cat_tier_<g>["gear:<id>"]
        fg[f"wl_block_tier_{g}"] = dict(self.block_tier)
        fg[f"wl_rarity_rows_{g}"] = {r: {"custom": bool(v.get("custom")), "tiers": dict(v.get("tiers") or {})}
                                     for r, v in self.rarity_rows.items() if v.get("custom") or v.get("tiers")}
        fg[f"wl_equip_rows_{g}"] = {c: {"custom": bool(v.get("custom")), "tiers": dict(v.get("tiers") or {})}
                                    for c, v in self.equip_rows.items() if v.get("custom") or v.get("tiers")}
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
        for gid, name, _d in w.listed_gear_groups(self.game):       # the gear groups the tab lists block by block
            out.append((w.gear_cat(gid), name))
        if w.rarity_rows(self.game):
            out.append((FLASK_CATEGORY, w.FLASK_LABEL[self.game]))
        if w.equip_classes(self.game):
            out.append((EQUIP_CATEGORY, w.EQUIP_LABEL))
        return out

    @staticmethod
    def is_gear(cat: str) -> bool:
        return cat.startswith(GEAR_PREFIX)

    def _gear_keys(self, cat: str) -> list:
        gid = cat[len(GEAR_PREFIX):]
        return [k for k, g, _ty, _tag, _c in self._gear_items if g == gid]

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
        if cat in (FLASK_CATEGORY, EQUIP_CATEGORY):    # no list: rows with their own controls (flask_rows / equip_groups)
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
        return {UNIQUE: self.unique_tier}.get(cat, self.item_tier)

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

    def has_flask(self) -> bool:
        return bool(w.rarity_rows(self.game))

    def flask_rows(self) -> list:
        """[{"id", "label", "custom", "tiers": {Normal|Magic|Rare: tier or None}}] of the Flask / Charm category: the
        default (custom False) is NeverSink's blocks; "set myself" shows the three rarities, each NeverSink until set."""
        out = []
        for rid, label, _classes in w.rarity_rows(self.game):
            row = self.rarity_rows.get(rid) or {}
            tiers = row.get("tiers") or {}
            out.append({"id": rid, "label": label, "custom": bool(row.get("custom")),
                        "tiers": {r: (tiers.get(r) if tiers.get(r) in ALL_CHOICES else DEFAULT_CUSTOM_TIER)
                                  for r in w.RARITY_CHOICES}})
        return out

    def set_flask_custom(self, row_id: str, custom: bool) -> None:
        """Default <-> set myself. Going back to the default keeps the values (not written) for the way back."""
        if row_id not in {r for r, _l, _c in w.rarity_rows(self.game)}:
            return
        row = self.rarity_rows.setdefault(row_id, {"custom": False, "tiers": {}})
        row["custom"] = bool(custom)
        _fill_custom(row, w.RARITY_CHOICES)
        if not row["custom"] and not row["tiers"]:
            self.rarity_rows.pop(row_id, None)

    def set_flask_rarity(self, row_id: str, rarity: str, tier: Optional[str]) -> None:
        if row_id not in {r for r, _l, _c in w.rarity_rows(self.game)} or rarity not in w.RARITY_CHOICES:
            return
        if tier not in ALL_CHOICES:
            return
        row = self.rarity_rows.setdefault(row_id, {"custom": True, "tiers": {}})
        row["tiers"][rarity] = tier
        row["custom"] = True
        _fill_custom(row, w.RARITY_CHOICES)

    # ---- equipment by class (EQUIP_CATEGORY)

    def has_equip(self) -> bool:
        return bool(w.equip_classes(self.game))

    def equip_groups(self) -> list:
        """[{"id", "label", "classes": [{"id", "label", "custom", "tiers": {Normal|Magic|Rare: tier or None}}]}] in
        display order; a row is NeverSink's blocks (custom False) or "set myself" (each rarity NeverSink until set)."""
        out = []
        for gid, gname, classes in w.equip_groups(self.game):
            rows = []
            for c in classes:
                row = self.equip_rows.get(c) or {}
                tiers = row.get("tiers") or {}
                rows.append({"id": c, "label": w.equip_label(c), "custom": bool(row.get("custom")),
                             "tiers": {r: (tiers.get(r) if tiers.get(r) in ALL_CHOICES else DEFAULT_CUSTOM_TIER)
                                       for r in w.EQUIP_CHOICES}})
            out.append({"id": gid, "label": gname, "classes": rows})
        return out

    def set_equip_custom(self, cls_id: str, custom: bool) -> None:
        """Default <-> set myself; going back keeps the values (not written) for the way back."""
        if cls_id not in set(w.equip_classes(self.game)):
            return
        row = self.equip_rows.setdefault(cls_id, {"custom": False, "tiers": {}})
        row["custom"] = bool(custom)
        _fill_custom(row, w.EQUIP_CHOICES)
        if not row["custom"] and not row["tiers"]:
            self.equip_rows.pop(cls_id, None)

    def set_equip_rarity(self, cls_id: str, rarity: str, tier: Optional[str]) -> None:
        if cls_id not in set(w.equip_classes(self.game)) or rarity not in w.EQUIP_CHOICES:
            return
        if tier not in ALL_CHOICES:
            return
        row = self.equip_rows.setdefault(cls_id, {"custom": True, "tiers": {}})
        row["tiers"][rarity] = tier
        row["custom"] = True
        _fill_custom(row, w.EQUIP_CHOICES)

    def set_equip_group(self, group_id: str, rarity: str, tier: Optional[str]) -> None:
        """One rarity of every class of the group at once, written into each row (no separate group value): every row
        becomes "set myself" with that tier (its other rarities keep their value, B when new). tier None = every row of
        the group back to the default (NeverSink); the values stay for the way back."""
        classes = next((c for g, _n, c in w.equip_groups(self.game) if g == group_id), [])
        for c in classes:
            if tier is None:
                self.set_equip_custom(c, False)
            else:
                self.set_equip_rarity(c, rarity, tier)

    def set_tier_stack(self, tier: str, n: int) -> None:
        if tier in TIER_CHOICES:
            if int(n) > 1:
                self.tier_stack[tier] = int(n)
            else:
                self.tier_stack.pop(tier, None)

    def toggle_row(self, cat: str, key: str, active: str) -> None:
        """Tick = into the active tier, untick = D (hidden)."""
        row = next((r for r in self.rows(cat) if r.key == key), None)
        if row is None:
            return
        self.set_row(cat, key, HIDE if row.tier != HIDE else active)

    def set_category(self, cat: str, tier: str) -> None:
        """Every row of the category to `tier`; rows the player set one by one are cleared (the whole-category
        tier would lose against them)."""
        if tier not in ALL_CHOICES:
            return
        if self.is_gear(cat):
            self.cat_tier[cat] = tier
            for k in self._gear_keys(cat):
                self.block_tier.pop(k, None)
        elif cat == UNIQUE:
            self.cat_tier[cat] = tier
            self._store(cat).clear()
        elif cat in (FLASK_CATEGORY, EQUIP_CATEGORY):
            return                                       # nothing to tier as a whole: the rows have their own controls
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
            for k in self._gear_keys(cat):
                self.block_tier.pop(k, None)
        elif cat == UNIQUE:
            self.cat_tier.pop(cat, None)
            self._store(cat).clear()
        elif cat == FLASK_CATEGORY:
            self.rarity_rows.clear()
        elif cat == EQUIP_CATEGORY:
            self.equip_rows.clear()
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
        if cat == FLASK_CATEGORY:
            return sum(1 for v in self.rarity_rows.values() if v.get("custom"))
        if cat == EQUIP_CATEGORY:
            return sum(1 for v in self.equip_rows.values() if v.get("custom"))
        return n + (1 if self.category_tier(cat) else 0)

    # ------------------------------------------------------------------ styles

    def base_style(self, label: str) -> dict:
        """NeverSink's own look of a tier (or our preset for G / Tablet / Map). Gem: the look of the tier the gems are in."""
        if label == "Gem":
            return self.effective_style(self.gem_tier if self.gem_tier in TIER_CHOICES else "B")
        default_lines = (getattr(self, "_default_lines", {}) or {}).get(label)
        return (filter_style.lines_to_style(default_lines) if default_lines
                else filter_style.normalize_style(filter_style.DEFAULT_STYLES.get(label)))

    def effective_style(self, label: str) -> dict:
        """The base look with the player's changes on top."""
        return filter_style.merge_styles(self.base_style(label), self.tier_style.get(label))

    def set_style_from_editor(self, label: str, style: dict) -> None:
        """Keep only what differs from the base look: a part equal to the base keeps following NeverSink, a
        part with another value is stored, a part the editor has unticked while the base has it is stored as
        OFF (it must not come back). The sound is stored like the rest (each label has its own)."""
        base, new = self.base_style(label), filter_style.normalize_style(style)
        out: dict = {}
        off: list = []
        for k in ("text", "border", "bg", "size", "icon", "effect"):
            if new[k] is None:
                if base[k] is not None:
                    off.append(k)
            elif new[k] != base[k]:
                out[k] = new[k]
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
        cat_tier = {c: HIDE for c in filter_gen.WHITELIST_CATEGORIES.get(game, []) if c not in cats}
        cat_tier[w.OTHER_CATEGORY] = HIDE                 # the old whitelist never showed these
        item_tier = {}
        for c, names in (fg.get(f"whitelist_cat_exclude_{game}") or {}).items():
            if c in cats:
                for n in names or []:
                    item_tier[str(n)] = HIDE
        if not fg.get("whitelist_unique_all"):
            cat_tier[UNIQUE] = HIDE
        if game == "poe2" and "Fragment" not in cats:
            cat_tier[TABLET_CATEGORY] = HIDE
        for gid, _name, _d in w.listed_gear_groups(game):
            cat_tier[w.gear_cat(gid)] = HIDE              # the old whitelist had no equipment
        updates = {f"wl_cat_tier_{game}": cat_tier, f"wl_item_tier_{game}": item_tier, f"wl_converted_{game}": True,
                   "wl_tier_format": w.TIER_FORMAT}
        notes = ["แปลง whitelist เดิมเข้าแบบใหม่แล้ว: หมวดที่ไม่ได้ติ๊ก = tier D (ซ่อน), ชื่อที่เอาออก = D, "
                 "อุปกรณ์ทั้งหมวด = D เหมือนเดิม (ค่าเดิมไม่ถูกลบ)",
                 "แปลงไม่ได้ตรงตัว: ชื่อที่ NeverSink ซ่อน (tier D) จะยังซ่อนต่อ แม้เคยติ๊กทั้งหมวด, "
                 "map/waystone กลับเป็นโชว์ตามเกม (ตั้งใหม่ในส่วนแยก)"]
        return updates, notes

    # ------------------------------------------------------------------ build

    def build(self, quest_text: str = "", sound_names: Optional[dict] = None) -> dict:
        return w.build_whitelist_filter(self.game, self.cfg(), self.base_text, self.hub, quest_text,
                                        sound_names, self.extra_names)
