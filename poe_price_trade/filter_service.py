"""Generate a loot filter from config — checker-independent core.

No Tk, no app state: takes config + game + league path + a log callback and
returns what was produced, so the caller can persist state / notify. The
checker (app.py) and any standalone front-end share this one implementation."""
from __future__ import annotations
import errno
import logging
import sys
from pathlib import Path
from typing import Callable, Optional

from . import debug, filter_gen, filter_output, hub_client, neversink_source

log_ = logging.getLogger(__name__)


def _noop(msg: str, tag: str = "info") -> None:
    pass


# errno / winerror values Windows hands back when something refuses the write.
# Controlled Folder Access (Defender's anti-ransomware) surfaces as EBADF /
# EACCES / ENOENT depending on the caller, so the raw text alone is useless.
_BLOCKED_ERRNOS = {errno.EBADF, errno.EACCES, errno.ENOENT, errno.EPERM}
_BLOCKED_WINERRORS = {5, 6}          # ERROR_ACCESS_DENIED, ERROR_INVALID_HANDLE


def _write_fail_msg(err: BaseException, out_dir) -> str:
    """User-facing text for a failed filter write. Points at Controlled Folder
    Access for the errors it is known to cause, keeps the raw error visible."""
    code = getattr(err, "errno", None)
    winerr = getattr(err, "winerror", None)
    if code in _BLOCKED_ERRNOS or winerr in _BLOCKED_WINERRORS:
        exe = Path(sys.executable).name if getattr(sys, "frozen", False) else "โปรแกรมนี้"
        return (f"✗ เขียน filter ลงโฟลเดอร์ไม่ได้: {out_dir}\n"
                f"   Windows อาจบล็อกการเขียน (Controlled Folder Access / Ransomware protection) — "
                f"อนุญาต {exe} ใน Windows Security → Ransomware protection "
                f"หรือเลือก Game folder override เป็นโฟลเดอร์อื่น\n"
                f"   ({err})")
    return f"✗ เขียน filter ไม่ได้: {err}"


def generate_filter(config, game_version: str, league_path: str,
                    *, force_base: bool = False,
                    league: str = "",
                    log: Callable[[str, str], None] = _noop) -> Optional[dict]:
    """Build + write the filter for one game. Returns:
      whitelist ok : {"mode": "whitelist", "path": Path, "count": int}
      tier ok      : {"mode": "tier", "path": Path, "signature": ...,
                      "mapping": ..., "base_tag": str}
      nothing written (nothing selected / error already logged): None

    `log(msg, tag)` is called synchronously — the caller decides whether to
    thread-hop. `league` is only used for the debug event text."""
    gv = game_version
    path = league_path
    app_dir = config.app_dir()
    cache_dir = app_dir / "cache"
    fg_cfg = dict(config.get("filter_gen", {}) or {})
    out_dir = filter_output.game_filter_dir(gv, fg_cfg.get(f"game_dir_{gv}", ""))

    if fg_cfg.get("whitelist_enabled"):
        cur_map = dict(filter_gen.WHITELIST_CURRENCIES.get(gv, []))
        exact = [bt for lb in fg_cfg.get(f"whitelist_selected_{gv}", [])
                 for bt in cur_map.get(lb, [])]
        if fg_cfg.get("whitelist_gold"):
            exact += filter_gen.GOLD_BASETYPES
        contains = list(fg_cfg.get(f"whitelist_custom_{gv}", []))
        # poe2: uncut gem + level per type | poe1: gem names -> contains
        gem_uncut = [(b, int(lv)) for b, lv in
                     (fg_cfg.get(f"whitelist_gem_uncut_{gv}", {}) or {}).items()]
        contains += list(fg_cfg.get(f"whitelist_gem_names_{gv}", []))
        cats = fg_cfg.get(f"whitelist_cats_{gv}", [])
        uniq_bases: list[str] = []

        if cats:
            try:
                hub_data = hub_client.get_prices(path)
                exact += filter_gen.expand_categories(
                    hub_data, cats, fg_cfg.get(f"whitelist_cat_exclude_{gv}", {}))
            except Exception as e:
                log(f"⚠ ดึง hub ไม่ได้ ใช้เฉพาะ currency/ชื่อที่ติ๊ก: {e}", "warn")

        if not exact and not uniq_bases and not contains and not gem_uncut:
            log("⚠ โหมดโชว์เฉพาะ: ยังไม่ได้เลือกอะไร — ไม่ generate", "warn")
            return None
        section = filter_gen.build_whitelist_section(exact, uniq_bases, contains,
                                                     gem_uncut=gem_uncut)
        try:
            out_path = filter_output.write_filter(out_dir, section, base_text=None)
        except OSError as e:
            log_.exception("whitelist filter write error")
            log(_write_fail_msg(e, out_dir), "err")
            return None
        except Exception as e:
            log_.exception("whitelist filter write error")
            log(f"✗ generate ล้มเหลว: {e}", "err")
            return None
        count = len(set(exact)) + len(set(uniq_bases)) + len(contains) + len(gem_uncut)
        debug.event(f"whitelist filter generated gv={gv} items={count} path={out_path}")
        log(f"✓ filter โหมดโชว์เฉพาะ ({count} รายการ) → {out_path}", "ok")
        log("Filter updated — reload in game (Options → Game)", "ok")
        return {"mode": "whitelist", "path": out_path, "count": count}

    log(f"⟳ ดึง NeverSink base filter ({gv})…", "info")
    strictness = int(fg_cfg.get(f"strictness_{gv}", 2))
    base_text, tag = neversink_source.fetch_base_filter(gv, strictness, cache_dir, force=force_base)
    if base_text is None:
        log("⚠ ไม่มี NeverSink base filter ให้ใช้ (GitHub ล่ม + ไม่มี cache)", "warn")
    else:
        log(f"✓ NeverSink base filter พร้อม (tag={tag})", "ok")

    hub_data = None
    try:
        hub_data = hub_client.get_prices(path)
    except Exception as e:
        log(f"⚠ ดึงราคาจาก hub ไม่ได้: {e}", "warn")

    generated_section = ""
    new_sig = None
    new_mapping = None
    if hub_data is not None:
        staleness_hours = float(fg_cfg.get("staleness_hours", 24))
        if filter_gen.is_stale(hub_data, staleness_hours):
            log("⚠ hub snapshot เก่าเกินกำหนด — ข้าม section ราคา ใช้ NeverSink ล้วน", "warn")
        else:
            rules = filter_gen.load_rules(app_dir)
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
            copied = filter_output.copy_sounds(out_dir, sound_map)
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

    try:
        written = filter_output.write_filter(out_dir, generated_section, base_text)
        debug.event(f"filter generated gv={gv} league={league} base_tag={tag} "
                    f"hub={'ok' if hub_data is not None else 'unavailable'} path={written}")
        log(f"✓ เขียน filter แล้ว: {written}", "ok")
        log("Filter updated — reload in game (Options → Game)", "ok")
        return {"mode": "tier", "path": written, "signature": new_sig,
                "mapping": new_mapping, "base_tag": tag}
    except ValueError as e:
        log(f"✗ {e} — ไฟล์เดิมไม่ถูกแตะ", "err")
    except OSError as e:
        log_.exception("filter generate error")
        log(_write_fail_msg(e, out_dir), "err")
    except Exception as e:
        log_.exception("filter generate error")
        log(f"✗ generate ล้มเหลว: {e}", "err")
    return None
