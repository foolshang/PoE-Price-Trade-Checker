"""Read a whitelist filter written by an older build of this program (no settings embedded in it) back into
whitelist settings, so the Whitelist tab can open and edit it.

Two kinds are known, both recognised by the first line of the file:
    v1  "# === PoE Checker - Whitelist (show only) ==="                   (up to v0.9.9: one look for every name)
    v2  "# === PoE Checker - Whitelist (own tiers, starting tiers ...) ===" (v0.9.10 / v0.10.0: tiers, gear blocks ...)
The file is read by the comment line above each block (`# tier S`, `# gold (stack >= 100)`, `# gear: ... - tier C
(type)` ...), the same lines the generator writes. `summarize` turns the text into plain sections; `read` maps them
onto a WlModel: whatever the file says wins, whatever it cannot say (a look no block carries, a tier nobody is in)
keeps the value the program remembered, and every such part is named in `notes` so the player knows it was guessed.

A name the file does not list is hidden (tier D) - that is what the file did - so the settings written back
reproduce what the old file showed, not what the newest NeverSink defaults would show.

Pure (stdlib + the whitelist modules): runs in the web build too.
"""
from __future__ import annotations
import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import filter_gen, filter_style, filter_whitelist as w
from .wl_model import HIDE, WlModel

V1_HEADER = "# === PoE Checker - Whitelist (show only)"
V2_HEADER = "# === PoE Checker - Whitelist (own tiers"
_STYLE_KW = set(w._STYLE_TOKENS) | {"CustomAlertSoundOptional"}
_TIERS = ("S", "A", "B")
_ALL_RAR = ["Normal", "Magic", "Rare", "Unique"]
NEW_GEAR_GROUPS = w.NEW_GEAR_GROUPS          # no file of these versions can have them: NeverSink's starting values


def version_of(text: str) -> Optional[str]:
    """"v1" | "v2" | None (not a whitelist file of this program)."""
    head = text[:600]
    if V2_HEADER in head:
        return "v2"
    if V1_HEADER in head:
        return "v1"
    return None


@dataclass
class FBlock:
    title: str
    kind: str
    conds: list = field(default_factory=list)      # [(keyword, rest of the line)]
    style: list = field(default_factory=list)      # the style lines, stripped

    def values(self, kw: str) -> list:
        return [r for k, r in self.conds if k == kw]

    def names(self) -> list:
        """BaseType == "a" "b" ... (exact names), and the bare `BaseType "a"` lines our own blocks use for the names
        NeverSink never writes with == (the title says what the block is; typed names read fragments())."""
        out = []
        for r in self.values("BaseType"):
            out += re.findall(r'"([^"]*)"', r)
        return out

    def fragments(self) -> list:
        """BaseType "a" "b" ... (a bare line = substring match)."""
        out = []
        for r in self.values("BaseType"):
            if not r.startswith("=="):
                out += re.findall(r'"([^"]*)"', r)
        return out

    def classes(self) -> list:
        return [c for r in self.values("Class") for c in re.findall(r'"([^"]*)"', r)]

    def sound_file(self) -> Optional[tuple]:
        for l in self.style:
            if l.startswith("CustomAlertSoundOptional"):
                m = re.match(r'CustomAlertSoundOptional\s+"([^"]+)"\s*(\d+)?', l)
                if m:
                    return m.group(1), int(m.group(2) or 300)
        return None


def guess_game(text: str) -> Optional[str]:
    """"poe2" / "poe1" when the file says so (waystones / tablets vs maps), else None."""
    if re.search(r'Waystone|"Tablet"|^# tablets', text, re.M):
        return "poe2"
    if re.search(r'Class == "Maps"|MapTier|^# maps:', text, re.M):
        return "poe1"
    return None


def parse_blocks(text: str) -> list:
    """[FBlock] of a filter file: the comment line right above Show / Hide is the block's title."""
    out: list = []
    cur: Optional[FBlock] = None
    title = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            cur, title = None, ""
            continue
        if s.startswith("#"):
            title = s
            cur = None
            continue
        kw, _, rest = s.partition(" ")
        if kw in ("Show", "Hide"):
            cur = FBlock(title, kw)
            out.append(cur)
            title = ""
        elif cur is not None:
            if kw in _STYLE_KW:
                cur.style.append(s)
            else:
                cur.conds.append((kw, rest.strip()))
    return out


def _cond_key(conds: list) -> tuple:
    """Conditions as comparable (keyword, normalised rest) pairs."""
    return tuple((k, " ".join(r.split())) for k, r in conds)


@dataclass
class Summary:
    version: str
    shown: dict = field(default_factory=dict)          # name -> (tier, stack minimum)   (S/A/B blocks)
    # (an old file's "tier C" is the hidden tier: it is D here - these files were written before C was a shown tier)
    tier_lines: dict = field(default_factory=dict)     # tier -> style lines of its first block
    tier_sound: dict = field(default_factory=dict)     # tier -> shared sound file name
    quest_sound: str = ""
    names_v1: set = field(default_factory=set)         # v1: the one block of names
    unique_bases: dict = field(default_factory=dict)   # base -> tier
    unique_all: bool = False
    tablet_own: dict = field(default_factory=dict)     # tablet name -> tier (S/A/B/D)
    tablet_block: Optional[FBlock] = None
    map_on: Optional[bool] = None
    map_tier: int = 1
    map_rarity: str = "Normal"
    map_block: Optional[FBlock] = None
    gold_on: Optional[bool] = None
    gold_min: int = 0
    gold_block: Optional[FBlock] = None
    gem_uncut: dict = field(default_factory=dict)
    gem_names: list = field(default_factory=list)
    gem_blocks: list = field(default_factory=list)
    custom: list = field(default_factory=list)         # (name, rarities, tier)
    classes: dict = field(default_factory=dict)        # class -> tier
    fragments: dict = field(default_factory=dict)      # name fragment -> tier
    gear: list = field(default_factory=list)           # (type, conds key, tier)
    hidden_c: set = field(default_factory=set)


def summarize(text: str) -> Optional[Summary]:
    """The sections of an old whitelist file, or None when it is not one."""
    ver = version_of(text)
    if not ver:
        return None
    sm = Summary(ver)
    for b in parse_blocks(text):
        t = b.title
        names = b.names()
        sound = b.sound_file()
        if t.startswith("# quest items"):
            if sound and not sm.quest_sound:
                sm.quest_sound = sound[0]
            continue
        m = re.match(r"^# tier ([SABC])(?: - stack >= (\d+))?$", t)       # (an old file's hidden "tier C (hidden" never matches)
        if m and b.kind == "Show":
            tier, need = m.group(1), int(m.group(2) or 1)
            for n in names:
                sm.shown[n] = (tier, need)
            sm.tier_lines.setdefault(tier, b.style)
            if sound:
                sm.tier_sound.setdefault(tier, sound[0])
            continue
        if t.startswith(("# tier C (hidden", "# tier D (hidden")):      # C = an old file's hidden tier, D = the new one's
            sm.hidden_c.update(names)
            continue
        m = re.match(r"^# tier ([SAB]) - special classes", t)
        if m:
            for c in b.classes():
                sm.classes[c] = m.group(1)
            continue
        m = re.match(r"^# tier ([SAB]) - names by fragment", t)
        if m:
            for f in b.fragments():
                sm.fragments[f] = m.group(1)
            continue
        m = re.match(r"^# uniques - tier ([SABC])", t)
        if m:
            for n in names:
                sm.unique_bases[n] = m.group(1)
            continue
        if t.startswith("# uniques above the value threshold"):          # v1
            for n in names:
                sm.unique_bases[n] = "B"
            continue
        if t.startswith("# all uniques"):
            sm.unique_all = True
            continue
        m = re.match(r"^# tablets - tier ([SABCD])( \(hidden)?", t)
        if m:
            hide = m.group(1) == "D" or bool(m.group(2))                # "tier C (hidden by the player)" of an old file = hidden
            for n in names:
                sm.tablet_own[n] = HIDE if hide else m.group(1)
            continue
        if t == "# tablets":
            sm.tablet_block = b
            continue
        m = re.match(r"^# (maps|waystones): tier >= (\d+) and rarity >= (\w+)", t)
        if m:
            sm.map_on, sm.map_tier, sm.map_rarity, sm.map_block = True, int(m.group(2)), m.group(3), b
            continue
        if re.match(r"^# (maps|waystones): not filtered", t):
            sm.map_on = False
            continue
        if t.startswith("# gold:"):
            sm.gold_on = False
            continue
        if t.startswith("# gold"):
            sm.gold_on, sm.gold_block = True, b
            mm = re.search(r"stack >= (\d+)", t)
            sm.gold_min = int(mm.group(1)) if mm else 0
            continue
        m = re.match(r"^# uncut gem: (.+) \(GemLevel >= (\d+)\)", t)
        if m:
            sm.gem_uncut[m.group(1)] = int(m.group(2))
            sm.gem_blocks.append(b)
            continue
        if t == "# gems":
            sm.gem_names += names
            sm.gem_blocks.append(b)
            continue
        m = re.match(r"^# typed names \(contains(?:,| match,) ?([^)]*)\)(?: - tier ([SABC]))?", t)
        if m:
            rar = [r for r in _ALL_RAR if any(r in " ".join(x.split()) for x in b.values("Rarity"))] or list(_ALL_RAR)
            for n in b.fragments():
                sm.custom.append((n, rar, m.group(2) or "B"))
            continue
        m = re.match(r"^# gear: .+ - tier ([SABCD]) \((.+)\)$", t)
        if m:                                                           # (gear groups are never listed: C / D = hidden)
            sm.gear.append((m.group(2), _cond_key(b.conds), HIDE if m.group(1) in "CD" else m.group(1)))
            continue
        if t.startswith("# hide everything"):
            continue
        if ver == "v1" and not t and b.kind == "Show" and names and not b.values("Rarity") \
                and not b.values("StackSize") and not b.values("Class"):
            sm.names_v1.update(names)                                     # v1: the one block of names
    return sm


# ---------------------------------------------------------------------------------------------------------
# onto a WlModel
# ---------------------------------------------------------------------------------------------------------

def _lines_style(lines: list, folder: Optional[Path]) -> dict:
    """The style dict of a block's style lines, the file sound included (CustomAlertSoundOptional)."""
    style = filter_style.lines_to_style(lines)
    for l in lines:
        m = re.match(r'CustomAlertSoundOptional\s+"([^"]+)"\s*(\d+)?', l)
        if m:
            p = (folder / m.group(1)) if folder else None
            style["sound"] = {"kind": "file", "id": 1, "file": str(p) if p and p.is_file() else m.group(1),
                              "volume": int(m.group(2) or 300)}
    return style


def _same_look(a: list, b: list) -> bool:
    la, lb = filter_style.lines_to_style(a), filter_style.lines_to_style(b)
    return la == lb


def read(text: str, game: str, current: WlModel, folder: Optional[Path] = None) -> Optional[dict]:
    """{"model": WlModel, "notes": [str], "sounds": {S|A|B|Q: file name}, "version": "v1"|"v2"} - the settings
    of the old file on top of `current` (the settings the program remembered, with its data loaded), or None
    when the text is not a whitelist file of this program."""
    sm = summarize(text)
    if sm is None:
        return None
    notes: list = []
    guessed: list = []
    base_cfg = current.cfg()
    wm = WlModel.from_config(base_cfg, game)
    wm.set_data(current.hub, current.base_text, current.extra_names)
    wm.item_tier, wm.cat_tier, wm.unique_tier, wm.block_tier = {}, {}, {}, {}
    wm.item_stack, wm.tier_stack = {}, {}
    wm.rarity_rows = {}                                     # no old file has them
    v1 = sm.version == "v1"
    stackable = wm._stackable
    # ---- names
    new_cat = {c for c, _p in w.NAMED_CATEGORIES.get(game, [])}
    for n, cat in wm._names.items():
        if cat in new_cat:
            continue                                    # a list the old file cannot have: NeverSink's own tiers
        if w.is_tablet(game, n):
            if n in sm.tablet_own:
                if sm.tablet_own[n] != "T":
                    wm.item_tier[n] = sm.tablet_own[n]
            elif v1 and n not in sm.names_v1:
                wm.item_tier[n] = HIDE
            elif not v1 and sm.tablet_block is None:
                wm.item_tier[n] = HIDE
            continue
        default = wm._defaults.get(n) or "B"
        if v1:
            tier, need = (default if default != HIDE else "B") if n in sm.names_v1 else HIDE, 1
        else:
            tier, need = sm.shown.get(n, (HIDE, 1))
        if tier != default:
            wm.item_tier[n] = tier
        if tier != HIDE and n in stackable:
            dflt = (wm._stack_defaults.get(n) or (1,))[0]
            if need != dflt:
                wm.item_stack[n] = need
    # ---- uniques
    if not sm.unique_bases and not sm.unique_all:
        wm.cat_tier[w.UNIQUE_CATEGORY] = HIDE
    elif not (v1 and sm.unique_all):
        by_base: dict = {}
        for name, base in wm._entries:
            by_base.setdefault(base, []).append(name)
        hidden = sum(1 for b in by_base if b not in sm.unique_bases)
        whole_c = hidden > len(by_base) / 2          # mostly hidden: one category tier + the few shown ones by name
        if whole_c:
            wm.cat_tier[w.UNIQUE_CATEGORY] = HIDE
        for base, names in by_base.items():
            tier = sm.unique_bases.get(base, HIDE)
            if (whole_c and tier != HIDE) or (not whole_c and tier != (wm._unique_defaults.get(base) or "B")):
                for nm in names:
                    wm.unique_tier[nm] = tier
    # a unique's tier is set by its name, so a name that sits on two bases cannot be given a different tier for each
    # one: the bases whose tier then differs from the file are named (new defaults make this show up now and then)
    unique_mismatch: set = set()
    if not v1 and sm.unique_bases:
        got, _c = w.resolve_unique_tiers(game, wm.cfg(), wm._entries, wm._unique_defaults)
        unique_mismatch = {b for b, t in sm.unique_bases.items() if b in got and got[b] != t}
        if unique_mismatch:
            notes.append(f"unique {len(unique_mismatch)} ฐานได้ tier ไม่ตรงไฟล์เดิม (ชื่อ unique ชื่อเดียวกันอยู่หลายฐาน "
                         f"ตั้ง tier ได้ทีละชื่อ — ตรวจที่หมวด Unique)")
    # ---- gear blocks (a block the file does not have was hidden by it)
    queues: dict = {}
    for ty, conds, tier in sm.gear:
        queues.setdefault((ty, conds), []).append(tier)
    per_group: dict = {}
    missing = 0
    for key, gid, ty, _tag, conds in wm._gear_items:
        if gid in NEW_GEAR_GROUPS:
            continue
        ck = _cond_key([tuple(c.strip().split(None, 1)) if " " in c.strip() else (c.strip(), "") for c in conds])
        q = queues.get((ty, ck))
        if q and not v1:
            per_group.setdefault(gid, []).append((key, q.pop(0)))
        else:
            per_group.setdefault(gid, []).append((key, HIDE))
            missing += 1
    for gid, items in per_group.items():
        tiers = [t for _k, t in items]
        top = max(set(tiers), key=tiers.count)
        default = next((d for g, _n, d in w.GEAR_GROUPS.get(game, []) if g == gid), "B")
        if top != default:
            wm.cat_tier[w.gear_cat(gid)] = top
        for key, t in items:
            if t != top:
                wm.block_tier[key] = t
    if missing and not v1:
        notes.append(f"อุปกรณ์ {missing} block ที่ไฟล์เก่าไม่มี (NeverSink รุ่นใหม่กว่าไฟล์) "
                     f"ตั้งเป็น D (ซ่อน) ตามไฟล์เดิม")
    # ---- what the tab does not set any more: NeverSink's own blocks (equipment groups, keys / special classes)
    names = {gid: n for gid, n, _d in w.GEAR_GROUPS.get(game, [])}
    cut = []
    for ty, _conds, _tier in sm.gear:
        gid = w.gear_group_of(game, ty)
        if gid and gid not in w.GEAR_LISTED.get(game, ()) and names.get(gid) not in cut:
            cut.append(names[gid] if gid != w.FLASK_GROUP else "Flask / Charm")
    if sm.classes or sm.fragments:
        cut.append("กุญแจ/ของพิเศษ (class)")
    if cut:
        notes.append("หมวดที่ตัดออกแล้ว ไฟล์ใหม่ใช้ block ของ NeverSink แทนค่าในไฟล์เก่า: " + ", ".join(cut))
    fresh = [c for c, _p in w.NAMED_CATEGORIES.get(game, [])]
    if fresh:
        notes.append("หมวดที่ไฟล์รุ่นนั้นยังไม่มี ใช้ค่าเริ่มต้นของ NeverSink (ไม่ใช่ D): " + ", ".join(fresh))
    # ---- gold / map / gems / typed names
    wm.gold = bool(sm.gold_on)
    if sm.gold_on:
        wm.gold_min = sm.gold_min
    wm.map_on = bool(sm.map_on)
    if sm.map_on:
        wm.map_tier, wm.map_rarity = max(1, min(16, sm.map_tier)), sm.map_rarity if sm.map_rarity in _ALL_RAR else "Normal"
    elif v1:
        notes.append("ไฟล์ v1 ซ่อน map/waystone ทั้งหมด (ไม่มีใน block) แต่แท็บนี้เลือกได้แค่ \"โชว์ตามเกม\" หรือ "
                     "\"โชว์ตามเกณฑ์\" — ตั้งเป็นโชว์ตามเกม")
    if filter_gen.WHITELIST_GEM_UNCUT.get(game):
        wm.gem_uncut = dict(sm.gem_uncut)
    else:
        wm.gem_names = list(sm.gem_names)
    wm.custom = [{"name": n, "rarities": list(r), "tier": t} for n, r, t in sm.custom]
    # ---- looks
    tier_lines = dict(sm.tier_lines)
    for tier in _TIERS + ("C",):
        if tier in tier_lines:
            wm.set_style_from_editor(tier, _lines_style(tier_lines[tier], folder))
        elif tier != "C":                                   # (a file from before tier C has no C look: nothing to guess)
            guessed.append(f"สไตล์ tier {tier}")
    if sm.gold_block is not None:
        wm.set_style_from_editor("G", _lines_style(sm.gold_block.style, folder))
    else:
        guessed.append("สไตล์ Gold")
    if game == "poe2":
        if sm.tablet_block is not None:
            wm.set_style_from_editor("Tablet", _lines_style(sm.tablet_block.style, folder))
        else:
            guessed.append("สไตล์ Tablet")
    if sm.map_block is not None:
        wm.set_style_from_editor("Map", _lines_style(sm.map_block.style, folder))
    else:
        guessed.append("สไตล์ Map/Waystone")
    if sm.gem_blocks:
        gem_lines = sm.gem_blocks[0].style
        hit = next((t for t in _TIERS + ("C",) if t in tier_lines and _same_look(tier_lines[t], gem_lines)), None)
        if hit:
            wm.gem_tier = hit
        else:
            wm.gem_tier = "B"
            guessed.append("tier ของ Gem")
    if v1:
        guessed = [g for g in guessed if g.startswith("สไตล์")]
        notes.append("ไฟล์ v1 ไม่มี tier: ชื่อที่โชว์ใช้ tier เริ่มต้นของ NeverSink (ถ้าเริ่มที่ D ใช้ B), ชื่ออื่นเป็น D, "
                     "อุปกรณ์/ของพิเศษทั้งหมด D เหมือนที่ไฟล์เดิมไม่มี")
    if guessed:
        notes.append("ส่วนที่อ่านกลับจากไฟล์ไม่ได้ ใช้ค่าที่โปรแกรมจำไว้ล่าสุด: " + ", ".join(guessed))
    stack_off = [n for n in wm.item_stack if wm.item_stack[n] == 1]
    if stack_off and not v1 and not any(need > 1 for _t, need in sm.shown.values()):
        notes.append(f"ไฟล์เก่าไม่มีเงื่อนไข StackSize: {len(stack_off)} ชื่อที่ NeverSink โชว์เฉพาะกอง "
                     f"ตั้ง \"จำนวนขั้นต่ำ\" เป็น 1 (โชว์ทุกกอง) ให้ตรงกับไฟล์เดิม")
    sounds = {t: n for t, n in sm.tier_sound.items()}
    if sm.quest_sound:
        sounds["Q"] = sm.quest_sound
    listed = set(sm.shown) | sm.names_v1
    overlap = len(listed & set(wm._names)) / len(listed) if listed else 1.0
    return {"model": wm, "notes": notes, "sounds": sounds, "version": sm.version, "summary": sm,
            "overlap": overlap, "unique_mismatch": unique_mismatch}
