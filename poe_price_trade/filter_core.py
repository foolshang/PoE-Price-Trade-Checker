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
from typing import Callable, Optional

from . import filter_gen


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
        raise ValueError("nothing to write — both hub and base filter sources unavailable")
    body = generated_section
    if base_text:
        body += "\n# ===== base filter below =====\n" + base_text
    return body


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

def plan_fetch(fg_cfg: dict, game: str) -> dict:
    """What the caller has to fetch before build_filter_text."""
    if fg_cfg.get("whitelist_enabled"):
        return {"mode": "whitelist", "hub": bool(fg_cfg.get(f"whitelist_cats_{game}", [])),
                "neversink": False}
    return {"mode": "tier", "hub": True, "neversink": True}


def build_filter_text(fg_cfg: dict, game: str, *,
                      hub_data: Optional[dict] = None,
                      base_text: Optional[str] = None,
                      base_tag: Optional[str] = None,
                      rules: Optional[dict] = None,
                      rules_loader: Optional[Callable[[], dict]] = None,
                      copy_sounds_fn: Optional[Callable[[dict], dict]] = None,
                      log: Callable[[str, str], None] = _noop) -> Optional[dict]:
    """Returns:
      whitelist : {"mode": "whitelist", "generated_section", "base_text": None, "count"}
      tier      : {"mode": "tier", "generated_section", "base_text", "signature",
                   "mapping", "base_tag"}
      None      : whitelist with nothing selected (warning already logged)

    hub_data=None means "hub unavailable" (the caller logged why). `rules` wins
    over `rules_loader`; with neither, the code defaults are used. rules_loader is
    only called when the tier section is actually built (fresh hub data), so a
    desktop caller keeps reading its rules file exactly as often as before."""
    gv = game
    if fg_cfg.get("whitelist_enabled"):
        return _build_whitelist(fg_cfg, gv, hub_data, log)
    return _build_tier(fg_cfg, gv, hub_data, base_text, base_tag, rules, rules_loader,
                       copy_sounds_fn, log)


def _build_whitelist(fg_cfg: dict, gv: str, hub_data: Optional[dict], log) -> Optional[dict]:
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
    return {"mode": "whitelist", "generated_section": section, "base_text": None, "count": count}


def _build_tier(fg_cfg, gv, hub_data, base_text, base_tag, rules, rules_loader,
                copy_sounds_fn, log) -> dict:
    generated_section = ""
    new_sig = None
    new_mapping = None
    if hub_data is not None:
        staleness_hours = float(fg_cfg.get("staleness_hours", 24))
        if filter_gen.is_stale(hub_data, staleness_hours):
            log("⚠ hub snapshot เก่าเกินกำหนด — ข้าม section ราคา ใช้ NeverSink ล้วน", "warn")
        else:
            if rules is None:
                rules = rules_loader() if rules_loader else filter_gen.load_rules(None)
            # last-resort fallback only: if a unique tier's real style can't be
            # ripped from base_text (resolve_real_styles, inside build_filter),
            # its hardcoded style still needs *some* sound value. Currency itself
            # never touches this — it's 100% surgically merged or left alone.
            rules = filter_gen.apply_base_filter_sounds(rules, base_text)
            sound_map = {
                "S": fg_cfg.get("sound_s") or None,
                "A": fg_cfg.get("sound_a") or None,
                "B": fg_cfg.get("sound_b") or None,
            }
            copied = copy_sounds_fn(sound_map) if copy_sounds_fn else {}
            generated_section, base_text, surgery_applied, anchor_status = filter_gen.build_filter(
                hub_data, rules, base_text, copied)
            new_mapping = filter_gen.tier_mapping(hub_data, rules)
            new_sig = filter_gen.signature(hub_data, rules)
            resolved_tiers = [t for t, a in anchor_status.items() if a]
            unresolved_tiers = [t for t, a in anchor_status.items() if not a]
            if surgery_applied:
                msg = ("✓ รวม currency เข้ากับ NeverSink base โดยตรง — ใช้เสียง/สไตล์ของ NeverSink เอง "
                       f"(tier {'/'.join(resolved_tiers)} resolve ได้")
                if unresolved_tiers:
                    msg += f", tier {'/'.join(unresolved_tiers)} หา anchor ไม่เจอ — ข้ามเฉพาะ tier นั้น)"
                else:
                    msg += ")"
                log(msg, "ok")
            else:
                log("⚠ รวม currency เข้ากับ base ไม่ได้เลยสักตัว (หา anchor block ไม่เจอทุก tier) — "
                    "ปล่อย currency ในไฟล์เดิมไว้ตามเดิม ไม่เติม style ของเราเอง", "warn")
    return {"mode": "tier", "generated_section": generated_section, "base_text": base_text,
            "signature": new_sig, "mapping": new_mapping, "base_tag": base_tag}
