"""Filter generation core - pure, no I/O.

Everything between "data fetched" and "file written": URL building for the
NeverSink source, file-body composition, and the whitelist / tier builders.
Side effects (network, files, sound copy) come in through parameters and
callbacks, so the same code runs on desktop (sync fetch + file write) and in
the browser (Pyodide, JS fetch + download).

Imports are limited to the stdlib and filter_gen - never urllib, ctypes,
shutil, config, filter_output, hub_client, neversink_source or tkinter.
"""
from __future__ import annotations
import re
from typing import Callable, Optional

from . import filter_gen, filter_style, filter_whitelist


def _noop(msg: str, tag: str = "info") -> None:
    pass


# ---------------------------------------------------------------------------
# NeverSink source: names and URLs (fetching itself stays in neversink_source)
# ---------------------------------------------------------------------------

NEVERSINK_REPO = {
    "poe1": "NeverSinkDev/NeverSink-Filter",
    "poe2": "NeverSinkDev/NeverSink-Filter-for-PoE2",
}
NEVERSINK_LEVELS = ["SOFT", "REGULAR", "SEMI-STRICT", "STRICT", "VERY-STRICT", "UBER-STRICT",
                    "UBER-PLUS-STRICT"]
LEVELS = NEVERSINK_LEVELS     # neversink_source re-exports this (filter_window imports it from there)

_URL_SAFE = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~/")


def _quote(s: str) -> str:
    """Percent-encode like urllib.parse.quote(s) (safe="/"), without importing urllib."""
    return "".join(chr(b) if b in _URL_SAFE else f"%{b:02X}" for b in s.encode("utf-8"))


def neversink_filename(game: str, strictness: int) -> str:
    level = NEVERSINK_LEVELS[strictness]
    prefix = "NeverSink's filter 2" if game == "poe2" else "NeverSink's filter"
    return f"{prefix} - {strictness}-{level}.filter"


def neversink_latest_api_url(game: str) -> str:
    return f"https://api.github.com/repos/{NEVERSINK_REPO[game]}/releases/latest"


def neversink_file_url(game: str, tag: str, strictness: int) -> str:
    fn = neversink_filename(game, strictness)
    return f"https://raw.githubusercontent.com/{NEVERSINK_REPO[game]}/{tag}/{_quote(fn)}"


# ---------------------------------------------------------------------------
# File body
# ---------------------------------------------------------------------------

def compose_filter_body(generated_section: str, base_text: Optional[str]) -> str:
    """generated_section (hub-tiered rules, may be "") + base_text (NeverSink,
    may be None). Raises ValueError if both are empty - per the failure-mode
    table ("ทั้งคู่ไม่มี -> ไม่เขียนทับไฟล์เดิม") the caller must not touch the
    existing file in that case."""
    if not generated_section.strip() and not base_text:
        raise ValueError("nothing to write — no NeverSink base filter available")
    body = generated_section
    if base_text:
        body += "\n# ===== base filter below =====\n" + base_text
    return body


# ---------------------------------------------------------------------------
# Filter name / sound file names (the rules the game and Windows impose)
# ---------------------------------------------------------------------------

DEFAULT_TIER_NAME = "poe-checker"
DEFAULT_WHITELIST_NAME = "poe-checker-whitelist"
MAX_FILTER_NAME = 100
_BAD_NAME_CHARS = set('<>:"/\\|?*')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def validate_filter_name(name) -> tuple:
    """(name, None) when usable as a Windows file name (without ".filter"), else (name, reason).
    Forbidden: < > : double quote, slash, backslash, | ? *, control characters, a trailing dot or space, Windows' reserved
    names (CON PRN AUX NUL COM1-9 LPT1-9), more than 100 characters."""
    n = "" if name is None else str(name)
    if not n.strip():
        return n, "ชื่อ filter ว่างอยู่"
    bad = sorted({c for c in n if c in _BAD_NAME_CHARS})
    if bad:
        return n, "ชื่อ filter ห้ามมีตัวอักษร " + " ".join(bad)
    if any(ord(c) < 32 for c in n):
        return n, "ชื่อ filter ห้ามมีตัวควบคุม (ขึ้นบรรทัดใหม่/tab ฯลฯ)"
    if n != n.rstrip(" ."):
        return n, "ชื่อ filter ห้ามลงท้ายด้วยจุดหรือช่องว่าง"
    if n.split(".")[0].strip().upper() in _RESERVED_NAMES:
        return n, f"“{n}” เป็นชื่อสงวนของ Windows (CON, PRN, AUX, NUL, COM1-9, LPT1-9)"
    if len(n) > MAX_FILTER_NAME:
        return n, f"ชื่อ filter ยาวเกิน {MAX_FILTER_NAME} ตัวอักษร (ตอนนี้ {len(n)})"
    return n, None


def safe_sound_name(name: str) -> tuple:
    """(file name the game can play, explanation or None). The game does not play a file whose name
    has a "#" (tested in PoE1 + PoE2: the filter loads, the sound is ignored) and reads ";" as a
    separator between several files - both become "_"."""
    reasons = []
    new = name
    if "#" in new:
        new = new.replace("#", "_")
        reasons.append("เกมเล่นไฟล์ที่ชื่อมี # ไม่ได้")
    if ";" in new:
        new = new.replace(";", "_")
        reasons.append("เกมใช้ ; คั่นหลายไฟล์")
    if not reasons:
        return name, None
    return new, f'เปลี่ยนชื่อ "{name}" เป็น "{new}" เพราะ' + " และ".join(reasons)


def _free_name(name: str, taken) -> str:
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    else:
        ext = "." + ext
    n = 2
    while f"{stem}-{n}{ext}" in taken:
        n += 1
    return f"{stem}-{n}{ext}"


def plan_sound_files(requests: list, existing: dict) -> dict:
    """Decide the destination name of every sound file before anything is copied.

    requests: [(label, original file name, content hash)] in the order they are used (the same
    file chosen for several tiers/slots has the same hash). existing: {file name: content hash}
    of what the game's filter folder already holds (every file name there; None = present but
    not hashed, which is fine for names that are not a candidate).
    Returns {"dest": {label: name}, "items": [...], "notes": [str]}; every item is
    {"dest", "label", "hash", "status": "new" | "same" | "conflict"}:
      new      - not in the folder yet: copy
      same     - same name and same content: nothing to copy ("use the existing file")
      conflict - same name, different content: the caller asks overwrite / keep the old one
                 (if the old one is kept, resolve_sound_plan gives the new file a free name)
    A file used by several slots is one item (copied once); two different files that share a name
    inside this selection are told apart automatically (stem-2.ext) without asking."""
    used: dict = {}
    items, dest, notes = [], {}, []
    for label, name, h in requests:
        cand, msg = safe_sound_name(name)
        if msg and msg not in notes:
            notes.append(msg)
        if cand in used:
            if used[cand] == h:
                dest[label] = cand
                continue
            other = _free_name(cand, set(used) | set(existing))
            notes.append(f'ไฟล์เสียง "{name}" ชื่อซ้ำกับอีกไฟล์ที่เลือกไว้ (คนละเนื้อหา) ใช้ชื่อ "{other}"')
            cand = other
            used[cand] = h
            items.append({"dest": cand, "label": label, "hash": h, "status": "new", "alt": None})
            dest[label] = cand
            continue
        status = "new" if cand not in existing else "same" if existing[cand] == h else "conflict"
        used[cand] = h
        items.append({"dest": cand, "label": label, "hash": h, "status": status})
        dest[label] = cand
    return {"dest": dest, "items": items, "notes": notes, "taken": set(existing) | set(used)}


def resolve_sound_plan(plan: dict, decide=None) -> tuple:
    """(dest map, copies, messages) from plan_sound_files. decide(name, alt) -> "overwrite" |
    "keep" is asked once per conflicting name (default: keep the old file, new one gets alt).
    copies: [(label, final name)] - what actually has to be copied; messages: what to tell the user."""
    dest = dict(plan["dest"])
    taken = set(plan["taken"])
    copies, msgs = [], list(plan["notes"])
    for it in plan["items"]:
        final = it["dest"]
        if it["status"] == "same":
            msgs.append(f'ใช้ไฟล์เดิม "{final}" (เนื้อไฟล์ตรงกัน ไม่ก๊อปซ้ำ)')
            continue
        if it["status"] == "conflict":
            alt = _free_name(final, taken)
            choice = decide(final, alt) if decide else "keep"
            if choice == "overwrite":
                msgs.append(f'ทับไฟล์เสียง "{final}"')
            else:
                final = alt
                taken.add(final)
                msgs.append(f'เก็บไฟล์เดิม "{it["dest"]}" ไว้ ไฟล์ใหม่ใช้ชื่อ "{final}"')
        copies.append((it["label"], final))
        for lab, d in list(dest.items()):
            if d == it["dest"]:
                dest[lab] = final
    return dest, copies, msgs


# ---------------------------------------------------------------------------
# Quest items (Q): the game never hides them (tested), so they only get a style
# ---------------------------------------------------------------------------

QUEST_CLASSES = {
    "poe1": ["Quest Items", "Cursed Ducat", "Pantheon Souls", "Labyrinth Items", "Labyrinth Trinkets"],
    "poe2": ["Quest Items", "Instance Local Items"],
}
QUEST_BASETYPES = {"poe1": [], "poe2": ["Bronze Key", "Gold Key", "Silver Key"]}


def build_quest_blocks(game: str, style, sound_file: Optional[str] = None) -> str:
    """The Q blocks ("" when the style writes nothing, i.e. NeverSink's own quest blocks stay)."""
    lines = filter_style.style_lines(style, sound_file)
    if not lines:
        return ""
    quote = lambda names: " ".join(f'"{n}"' for n in names)
    out = ["# quest items (poe-checker)", "Show", f"    Class == {quote(QUEST_CLASSES.get(game, ['Quest Items']))}"]
    out += lines + [""]
    if QUEST_BASETYPES.get(game):
        out += ["Show", f"    BaseType == {quote(QUEST_BASETYPES[game])}"] + lines + [""]
    return "\n".join(out) + "\n"


def tier_sound_requests(fg_cfg: dict) -> dict:
    """{label: source file or None} the tier tab wants copied: S/A/B plus Q's file sound."""
    sm = {
        "S": fg_cfg.get("sound_s") or None,
        "A": fg_cfg.get("sound_a") or None,
        "B": fg_cfg.get("sound_b") or None,
    }
    sm["Q"] = filter_style.uses_sound_file(fg_cfg.get("style_q")) if fg_cfg.get("style_q") else None
    return sm


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

def plan_fetch(fg_cfg: dict, game: str) -> dict:
    """What the caller has to fetch before build_filter_text."""
    if fg_cfg.get("whitelist_enabled") and fg_cfg.get("wl_v2"):
        return {"mode": "whitelist", "hub": True, "neversink": True}
    if fg_cfg.get("whitelist_enabled"):
        return {"mode": "whitelist", "hub": bool(fg_cfg.get(f"whitelist_cats_{game}", [])),
                "neversink": False}
    return {"mode": "tier", "hub": False, "neversink": True}


TIER_HEADER = "# Generated by PoE Price & Trade Checker (Filter Generator) - NeverSink base filter, no price data\n"


def build_filter_text(fg_cfg: dict, game: str, *,
                      hub_data: Optional[dict] = None,
                      base_text: Optional[str] = None,
                      base_tag: Optional[str] = None,
                      copy_sounds_fn: Optional[Callable[[dict], dict]] = None,
                      extra_names: Optional[set] = None,
                      log: Callable[[str, str], None] = _noop) -> Optional[dict]:
    """Returns:
      whitelist : {"mode": "whitelist", "generated_section", "base_text": None, "count"}
      tier      : {"mode": "tier", "generated_section", "base_text", "base_tag"}
      None      : whitelist with nothing selected (warning already logged)

    Whitelist mode uses hub_data only for the item NAMES of the ticked categories
    (None = hub unavailable, the caller logged why). Tier mode never uses prices: it is
    NeverSink's base filter for the chosen strictness, our header, and - for the tiers the
    user gave a sound - CustomAlertSoundOptional next to NeverSink's own sound numbers
    (filter_gen.apply_ladder_sounds). No base filter -> nothing to write."""
    gv = game
    if fg_cfg.get("whitelist_enabled") and fg_cfg.get("wl_v2"):
        return _build_whitelist_v2(fg_cfg, gv, hub_data, base_text, copy_sounds_fn, extra_names, log)
    if fg_cfg.get("whitelist_enabled"):
        return _build_whitelist(fg_cfg, gv, hub_data, log, copy_sounds_fn)
    return _build_tier(fg_cfg, gv, base_text, base_tag, copy_sounds_fn, log)


_PLAY_ALERT = re.compile(r"^(\s*)PlayAlertSound\s+(\d+)")
_SOUND_LABEL = {"6": "S", "1": "A", "2": "B"}      # NeverSink's sound numbers: top / second / middle


def add_shared_tier_sounds(section: str, copied: dict) -> str:
    """The user's S / A / B sound (shared with the NeverSink tab) next to the PlayAlertSound 6 / 1 / 2 of
    the old whitelist's blocks, as filter_gen does for NeverSink's own blocks: the custom file plays when
    it is there, the built-in sound is the fallback."""
    out = []
    for line in section.splitlines():
        out.append(line)
        m = _PLAY_ALERT.match(line)
        f = copied.get(_SOUND_LABEL.get(m.group(2))) if m else None
        if f:
            out.append(f'{m.group(1)}CustomAlertSoundOptional "{f}" {filter_gen.SOUND_VOLUME}')
    return "\n".join(out) + ("\n" if section.endswith("\n") else "")


def _build_whitelist(fg_cfg: dict, gv: str, hub_data: Optional[dict], log, copy_sounds_fn=None) -> Optional[dict]:
    exact = []
    gold_on = bool(fg_cfg.get("whitelist_gold"))
    unique_all = bool(fg_cfg.get("whitelist_unique_all"))
    try:
        gold_min = max(0, int(fg_cfg.get("whitelist_gold_min", 0) or 0))
    except (TypeError, ValueError):
        gold_min = 0
    contains = list(fg_cfg.get(f"whitelist_custom_{gv}", []))
    # poe2: uncut gem + level per type | poe1: gem names -> contains
    gem_uncut = [(b, int(lv)) for b, lv in
                 (fg_cfg.get(f"whitelist_gem_uncut_{gv}", {}) or {}).items()]
    contains += list(fg_cfg.get(f"whitelist_gem_names_{gv}", []))
    cats = fg_cfg.get(f"whitelist_cats_{gv}", [])
    uniq_bases: list[str] = []

    if cats and hub_data is not None:
        try:
            exact += filter_gen.expand_categories(
                hub_data, cats, fg_cfg.get(f"whitelist_cat_exclude_{gv}", {}))
        except Exception as e:
            log(f"⚠ ดึง hub ไม่ได้ ใช้เฉพาะ currency/ชื่อที่ติ๊ก: {e}", "warn")

    if not exact and not uniq_bases and not contains and not gem_uncut and not gold_on and not unique_all:
        log("⚠ โหมดโชว์เฉพาะ: ยังไม่ได้เลือกอะไร — ไม่ generate", "warn")
        return None
    section = filter_gen.build_whitelist_section(exact, uniq_bases, contains,
                                                 gem_uncut=gem_uncut,
                                                 gold=gold_on, gold_min=gold_min,
                                                 unique_all=unique_all)
    count = (len(set(exact)) + len(set(uniq_bases)) + len(contains) + len(gem_uncut)
             + int(gold_on) + int(unique_all))
    wanted = {k: v for k, v in tier_sound_requests(fg_cfg).items() if v}        # S / A / B / Q files
    copied = copy_sounds_fn(wanted) if wanted and copy_sounds_fn else {}
    if copied:
        section = add_shared_tier_sounds(section, copied)
    quest = build_quest_blocks(gv, fg_cfg.get("style_q"), copied.get("Q")) if fg_cfg.get("style_q") else ""
    if quest:           # quest items are never hidden by the game, but they still get their own look / sound
        head, _, rest = section.partition("\n")
        section = head + "\n" + quest + rest
    return {"mode": "whitelist", "generated_section": section, "base_text": None, "count": count}


def _build_whitelist_v2(fg_cfg, gv, hub_data, base_text, copy_sounds_fn, extra_names, log) -> Optional[dict]:
    """The new whitelist: our own tiers, starting tiers from NeverSink strictness 2 (filter_whitelist).
    Needs the base filter for the starting tiers; without it nothing is written."""
    if not base_text:
        log("⚠ ไม่มี NeverSink base filter — whitelist ไม่มี tier เริ่มต้น ไม่ generate", "warn")
        return None
    sound_map = filter_whitelist.sound_requests(fg_cfg, gv)
    sound_map["Q"] = filter_style.uses_sound_file(fg_cfg.get("style_q")) if fg_cfg.get("style_q") else None
    copied = copy_sounds_fn(sound_map) if copy_sounds_fn else {}
    quest = build_quest_blocks(gv, fg_cfg.get("style_q"), copied.get("Q")) if fg_cfg.get("style_q") else ""
    res = filter_whitelist.build_whitelist_filter(gv, fg_cfg, base_text, hub_data, quest, copied, extra_names)
    for base, tiers in res["unique_conflicts"]:
        log(f"⚠ unique หลายตัวบน base {base} มี tier ไม่เท่ากัน — ใช้ tier สูงสุด: "
            + ", ".join(f"{n}={t}" for n, t in sorted(tiers.items())), "warn")
    if res["skipped"]:
        shown = ", ".join(f"{n} ({where})" for n, where in res["skipped"][:8])
        more = f" … +{len(res['skipped']) - 8}" if len(res["skipped"]) > 8 else ""
        log(f"⚠ ข้าม {len(res['skipped'])} ชื่อที่ไม่ยืนยันว่าเป็นชื่อจริงของเกม (ไม่เขียนลงไฟล์): {shown}{more}", "warn")
    return {"mode": "whitelist", "generated_section": res["text"], "base_text": None,
            "count": res["count"], "report": res["report"], "skipped": res["skipped"]}


def _build_tier(fg_cfg, gv, base_text, base_tag, copy_sounds_fn, log) -> dict:
    if not base_text:
        return {"mode": "tier", "generated_section": "", "base_text": None, "base_tag": base_tag}
    sound_map = tier_sound_requests(fg_cfg)
    copied = copy_sounds_fn(sound_map) if copy_sounds_fn else {}
    base_text, n_blocks = filter_gen.apply_ladder_sounds(base_text, copied)
    if n_blocks:
        log(f"✓ ใส่เสียง custom ใน {n_blocks} block ตาม tier ของ NeverSink "
            f"(S/A/B = เสียง 6/1/2 ของ NeverSink)", "ok")
    quest = build_quest_blocks(gv, fg_cfg.get("style_q"), copied.get("Q")) if fg_cfg.get("style_q") else ""
    section = TIER_HEADER + ("\n" + quest if quest else "")
    return {"mode": "tier", "generated_section": section, "base_text": base_text, "base_tag": base_tag}
