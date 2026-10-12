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

from . import filter_gen, filter_style, filter_whitelist, wl_embed


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


def build_quest_blocks(game: str, style, sound_file: Optional[str] = None, default_lines: Optional[list] = None) -> str:
    """The Q blocks ("" when the style writes nothing and there are no `default_lines` to fall back on, i.e.
    NeverSink's own quest blocks stay). `default_lines` = style lines used when the player's style is empty."""
    lines = filter_style.style_lines(style, sound_file) or list(default_lines or [])
    if not lines:
        return ""
    quote = lambda names: " ".join(f'"{n}"' for n in names)
    out = ["# quest items (poe-checker)", "Show", f"    Class == {quote(QUEST_CLASSES.get(game, ['Quest Items']))}"]
    out += lines + [""]
    if QUEST_BASETYPES.get(game):
        out += ["Show", f"    BaseType == {quote(QUEST_BASETYPES[game])}"] + lines + [""]
    return "\n".join(out) + "\n"


def tier_sound_requests(fg_cfg: dict) -> dict:
    """{label: source file or None} the NeverSink tab wants copied: its six numbered sounds ("1".."6", config keys
    sound_1 .. sound_6) plus Q's file sound. The Whitelist tab has sounds of its own (filter_whitelist.sound_requests);
    Q is the only one both tabs use."""
    sm = {n: fg_cfg.get(f"sound_{n}") or None for n in filter_gen.SOUND_SLOTS}
    sm["Q"] = filter_style.uses_sound_file(fg_cfg.get("style_q")) if fg_cfg.get("style_q") else None
    return sm


SOUND_FORMAT = 2        # `sound_format` of a config with sound_1 .. sound_6 (before: sound_s / sound_a / sound_b / sound_c)


def migrate_sounds(fg: dict) -> tuple:
    """(config, notes): a config from before the sounds were split has the NeverSink tab's S / A / B files in
    sound_s / sound_a / sound_b (and v0.12.0's C in sound_c) and the Whitelist tab shared them. Converted once:
      NeverSink tab: sound_s -> sound_1, sound_a -> sound_2, sound_b -> sound_3 (sound 4-6 empty; the old S / A / B were
                     NeverSink's numbers 6 / 1 / 2 = slots 1 / 2 / 3, so every block sounds as it did);
      Whitelist tab: the same files become the sound of its tiers S / A / B (sound_c -> C) when that tier has none.
    The result carries `sound_format` = 2 so nothing is converted twice. Nothing to convert -> (fg, [])."""
    if fg.get("sound_format") == SOUND_FORMAT:
        return fg, []
    out = dict(fg)
    old = {t: (fg.get(f"sound_{t.lower()}") or "") for t in ("S", "A", "B", "C")}
    moved = []
    for t, n in (("S", "1"), ("A", "2"), ("B", "3")):
        if old[t] and not out.get(f"sound_{n}"):
            out[f"sound_{n}"] = old[t]
            moved.append(t)
    styles = {k: dict(v) if isinstance(v, dict) else v for k, v in (fg.get("wl_tier_style") or {}).items()}
    for t in ("S", "A", "B", "C"):
        if not old[t]:
            continue
        cur = styles.get(t) if isinstance(styles.get(t), dict) else {}
        snd = cur.get("sound") if isinstance(cur.get("sound"), dict) else {}
        if snd.get("kind") in ("file", "game"):
            continue                                              # the tier already has a sound of its own
        styles[t] = dict(cur, sound={"kind": "file", "id": 1, "file": old[t], "volume": filter_gen.SOUND_VOLUME})
    if styles:
        out["wl_tier_style"] = styles
    for k in ("sound_s", "sound_a", "sound_b", "sound_c"):
        out.pop(k, None)
    out["sound_format"] = SOUND_FORMAT
    notes = []
    if any(old.values()):
        notes.append("เสียงเดิม " + " / ".join(f"{t}: {old[t].replace(chr(92), '/').rsplit('/', 1)[-1]}"
                                               for t in ("S", "A", "B", "C") if old[t])
                     + " ถูกแปลงแล้ว — แท็บ NeverSink: เสียง 1 / 2 / 3 (= เสียง 6 / 1 / 2 ของ NeverSink) · "
                       "แท็บ Whitelist: เสียงของ tier S / A / B (C) ชุดเดิม · สองแท็บแยกกันแล้ว")
    return out, notes


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
                      app_version: str = "",
                      log: Callable[[str, str], None] = _noop) -> Optional[dict]:
    """Returns:
      whitelist : {"mode": "whitelist", "generated_section", "base_text": None, "count"}
      tier      : {"mode": "tier", "generated_section", "base_text", "base_tag"}
      None      : whitelist with nothing selected (warning already logged)

    Whitelist mode uses hub_data only for the item NAMES of the ticked categories
    (None = hub unavailable, the caller logged why). Tier mode never uses prices: it is
    NeverSink's base filter for the chosen strictness, our header, and - for the tiers the
    user gave a sound - CustomAlertSoundOptional next to NeverSink's own sound numbers
    (filter_gen.apply_numbered_sounds). No base filter -> nothing to write."""
    gv = game
    fg_cfg, _moved = migrate_sounds(fg_cfg)       # a config that still has sound_s / sound_a / sound_b (read once)
    if fg_cfg.get("whitelist_enabled") and fg_cfg.get("wl_v2"):
        return _build_whitelist_v2(fg_cfg, gv, hub_data, base_text, copy_sounds_fn, extra_names, log, app_version)
    if fg_cfg.get("whitelist_enabled"):
        return _build_whitelist(fg_cfg, gv, hub_data, log, copy_sounds_fn)
    return _build_tier(fg_cfg, gv, base_text, base_tag, copy_sounds_fn, log)


_PLAY_ALERT = re.compile(r"^(\s*)PlayAlertSound\s+(\d+)")


def add_shared_tier_sounds(section: str, copied: dict) -> str:
    """The NeverSink tab's numbered sound (slot per PlayAlertSound id, filter_gen.SOUND_SLOT_OF_ID) next to the
    PlayAlertSound of the old whitelist's blocks, as filter_gen does for NeverSink's own blocks: the custom file plays
    when it is there, the built-in sound is the fallback."""
    out = []
    for line in section.splitlines():
        out.append(line)
        m = _PLAY_ALERT.match(line)
        f = copied.get(filter_gen.SOUND_SLOT_OF_ID.get(m.group(2))) if m else None
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


def _build_whitelist_v2(fg_cfg, gv, hub_data, base_text, copy_sounds_fn, extra_names, log,
                        app_version: str = "") -> Optional[dict]:
    """The new whitelist: our own tiers, starting tiers from NeverSink strictness 2 (filter_whitelist).
    Needs the base filter for the starting tiers; without it nothing is written. `app_version` (the caller's
    program version; filter_core stays free of the package's own modules) is recorded in the embedded settings."""
    if not base_text:
        log("⚠ ไม่มี NeverSink base filter — whitelist ไม่มี tier เริ่มต้น ไม่ generate", "warn")
        return None
    sound_map = filter_whitelist.sound_requests(fg_cfg, gv)
    sound_map["Q"] = filter_style.uses_sound_file(fg_cfg.get("style_q")) if fg_cfg.get("style_q") else None
    copied = copy_sounds_fn(sound_map) if copy_sounds_fn else {}
    # the whitelist ends in `Hide`, so the quest blocks are always written: the player's Q style, else NeverSink's own look
    quest = build_quest_blocks(gv, fg_cfg.get("style_q"), copied.get("Q"),
                               default_lines=filter_whitelist.neversink_quest_lines(base_text))
    res = filter_whitelist.build_whitelist_filter(gv, fg_cfg, base_text, hub_data, quest, copied, extra_names)
    for base, tiers in res["unique_conflicts"]:
        log(f"⚠ unique หลายตัวบน base {base} มี tier ไม่เท่ากัน — ใช้ tier สูงสุด: "
            + ", ".join(f"{n}={t}" for n, t in sorted(tiers.items())), "warn")
    if res["skipped"]:
        shown = ", ".join(f"{n} ({where})" for n, where in res["skipped"][:8])
        more = f" … +{len(res['skipped']) - 8}" if len(res["skipped"]) > 8 else ""
        log(f"⚠ ข้าม {len(res['skipped'])} ชื่อที่ไม่ยืนยันว่าเป็นชื่อจริงของเกม (ไม่เขียนลงไฟล์): {shown}{more}", "warn")
    if res.get("bad_names"):
        shown = ", ".join(f"{n} ({where})" for n, where in res["bad_names"][:8])
        more = f" … +{len(res['bad_names']) - 8}" if len(res["bad_names"]) > 8 else ""
        log(f"⚠ ข้าม {len(res['bad_names'])} ชื่อที่รู้ว่าไม่ใช่ชื่อไอเท็ม (เช่น [DNT], INCOMPLETE) ไม่เขียนลงไฟล์: {shown}{more}", "warn")
    # the settings go into the file too (comment lines), so the Whitelist tab can open and edit it again
    return {"mode": "whitelist", "generated_section": wl_embed.embed(res["text"], fg_cfg, gv, app_version),
            "base_text": None, "count": res["count"], "report": res["report"], "skipped": res["skipped"], "bad_names": res.get("bad_names", [])}


def _build_tier(fg_cfg, gv, base_text, base_tag, copy_sounds_fn, log) -> dict:
    if not base_text:
        return {"mode": "tier", "generated_section": "", "base_text": None, "base_tag": base_tag}
    sound_map = tier_sound_requests(fg_cfg)
    copied = copy_sounds_fn(sound_map) if copy_sounds_fn else {}
    base_text, done = filter_gen.apply_numbered_sounds(base_text, copied)
    if done:
        log(f"✓ ใส่เสียง custom ใน {sum(done.values())} block ตามเลขเสียงของ NeverSink "
            f"({', '.join(f'เสียง {k}: {v}' for k, v in sorted(done.items()))})", "ok")
    quest = build_quest_blocks(gv, fg_cfg.get("style_q"), copied.get("Q")) if fg_cfg.get("style_q") else ""
    section = TIER_HEADER + ("\n" + quest if quest else "")
    return {"mode": "tier", "generated_section": section, "base_text": base_text, "base_tag": base_tag}
