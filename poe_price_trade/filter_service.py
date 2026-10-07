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

from . import debug, filter_core, filter_gen, filter_output, hub_client, neversink_source, trade_names

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


def filter_name_for(fg_cfg: dict, mode: str) -> str:
    """The file name (without .filter) of the tier tab / the whitelist tab."""
    if mode == "whitelist":
        return fg_cfg.get("filter_name_whitelist") or filter_core.DEFAULT_WHITELIST_NAME
    return fg_cfg.get("filter_name_tier") or filter_core.DEFAULT_TIER_NAME


def remember_result(config, game_version: str, res: Optional[dict]) -> None:
    """Persist what a successful generate tells the next one: the name just used (so a rename can
    point at the old file) and, for the tier tab, the NeverSink tag it was built from."""
    if not res:
        return
    fg = dict(config.get("filter_gen", {}) or {})
    fg[f"last_filter_name_{res['mode']}"] = res.get("filter_name")
    if res["mode"] == "tier" and res.get("base_tag"):
        fg[f"neversink_tag_{game_version}"] = res["base_tag"]
    config.set("filter_gen", fg)
    config.save()


def check_neversink_update(config, game_version: str, get_latest=None) -> Optional[dict]:
    """None when there is nothing to do (no tier filter generated yet for this game, already on
    the latest tag, or GitHub unreachable); else {"old", "new", "auto"} where auto = the user wants
    it regenerated."""
    fg = dict(config.get("filter_gen", {}) or {})
    last = fg.get(f"neversink_tag_{game_version}")
    if not last:
        return None
    latest = (get_latest or neversink_source.get_latest_tag)(game_version)
    if not latest or latest == last:
        return None
    return {"old": last, "new": latest, "auto": bool(fg.get("auto_regen_neversink"))}


def neversink_update_message(info: dict, regenerated: bool) -> str:
    if regenerated:
        return f"NeverSink อัปเดต {info['old']} → {info['new']} สร้าง filter ใหม่แล้ว"
    return (f"NeverSink มีเวอร์ชันใหม่ {info['new']} (filter ปัจจุบันสร้างจาก {info['old']}) "
            f"— กด Generate เพื่ออัปเดต")


def generate_filter(config, game_version: str, league_path: str,
                    *, force_base: bool = False,
                    league: str = "",
                    log: Callable[[str, str], None] = _noop,
                    mode: Optional[str] = None,
                    ask_sound: Optional[Callable[[str, str], str]] = None) -> Optional[dict]:
    """Build + write the filter for one game. Returns:
      whitelist ok : {"mode": "whitelist", "path": Path, "count": int, "filter_name": str}
      tier ok      : {"mode": "tier", "path": Path, "base_tag": str, "filter_name": str}
      nothing written (nothing selected / error already logged): None

    mode "tier" | "whitelist" picks the tab (default: the saved whitelist_enabled flag); each tab
    has its own file name. ask_sound(name, new_name) -> "overwrite" | "keep" is asked when a sound
    file of the same name but different content is already in the folder (default: keep).
    `log(msg, tag)` is called synchronously — the caller decides whether to
    thread-hop. `league` is only used for the debug event text."""
    gv = game_version
    path = league_path
    app_dir = config.app_dir()
    cache_dir = app_dir / "cache"
    fg_cfg = dict(config.get("filter_gen", {}) or {})
    if mode in ("tier", "whitelist"):
        fg_cfg["whitelist_enabled"] = (mode == "whitelist")
    mode = "whitelist" if fg_cfg.get("whitelist_enabled") else "tier"
    out_dir = filter_output.game_filter_dir(gv, fg_cfg.get(f"game_dir_{gv}", ""))
    fname = filter_name_for(fg_cfg, mode)
    _n, name_err = filter_core.validate_filter_name(fname)
    if name_err:
        log(f"✗ ชื่อ filter ใช้ไม่ได้: {name_err}", "err")
        return None
    last_name = fg_cfg.get(f"last_filter_name_{mode}")
    if last_name and last_name != fname and filter_output.filter_path(out_dir, last_name).exists():
        log(f"ℹ ไฟล์เดิม {last_name}.filter ยังอยู่ในโฟลเดอร์ (ไม่ลบ ไม่ทับ)", "info")

    plan = filter_core.plan_fetch(fg_cfg, gv)

    if plan["mode"] == "whitelist":
        hub_data = None
        if plan["hub"]:
            try:
                hub_data = hub_client.get_prices(path)
            except Exception as e:
                log(f"⚠ ดึง hub ไม่ได้ ใช้เฉพาะ currency/ชื่อที่ติ๊ก: {e}", "warn")
        wl_base = None
        if plan["neversink"]:       # starting tiers come from NeverSink strictness 2, whatever the tier tab uses
            wl_base, _tag = neversink_source.fetch_base_filter(gv, 2, cache_dir, force=force_base)
            if wl_base is None:
                log("⚠ ไม่มี NeverSink base filter ให้ใช้ (GitHub ล่ม + ไม่มี cache)", "warn")
        res = filter_core.build_filter_text(
            fg_cfg, gv, hub_data=hub_data, base_text=wl_base,
            extra_names=trade_names.get_names(gv, cache_dir) if plan["neversink"] else None,
            copy_sounds_fn=lambda sound_map: filter_output.copy_sounds(
                out_dir, sound_map, decide=ask_sound, notify=lambda text: log(text, "info")),
            log=log)
        if res is None:
            return None
        try:
            out_path = filter_output.write_filter(out_dir, res["generated_section"], base_text=None, name=fname)
        except OSError as e:
            log_.exception("whitelist filter write error")
            log(_write_fail_msg(e, out_dir), "err")
            return None
        except Exception as e:
            log_.exception("whitelist filter write error")
            log(f"✗ generate ล้มเหลว: {e}", "err")
            return None
        count = res["count"]
        debug.event(f"whitelist filter generated gv={gv} items={count} path={out_path}")
        log(f"✓ filter โหมดโชว์เฉพาะ ({count} รายการ) → {out_path}", "ok")
        log("Filter updated — reload in game (Options → Game)", "ok")
        return {"mode": "whitelist", "path": out_path, "count": count, "filter_name": fname}

    log(f"⟳ ดึง NeverSink base filter ({gv})…", "info")
    strictness = int(fg_cfg.get(f"strictness_{gv}", 2))
    base_text, tag = neversink_source.fetch_base_filter(gv, strictness, cache_dir, force=force_base)
    if base_text is None:
        log("⚠ ไม่มี NeverSink base filter ให้ใช้ (GitHub ล่ม + ไม่มี cache)", "warn")
    else:
        log(f"✓ NeverSink base filter พร้อม (tag={tag})", "ok")

    res = filter_core.build_filter_text(
        fg_cfg, gv, base_text=base_text, base_tag=tag,
        copy_sounds_fn=lambda sound_map: filter_output.copy_sounds(
            out_dir, sound_map, decide=ask_sound, notify=lambda text: log(text, "info")),
        log=log)

    try:
        written = filter_output.write_filter(out_dir, res["generated_section"], res["base_text"], name=fname)
        debug.event(f"filter generated gv={gv} league={league} base_tag={tag} path={written}")
        log(f"✓ เขียน filter แล้ว: {written}", "ok")
        log("Filter updated — reload in game (Options → Game)", "ok")
        return {"mode": "tier", "path": written, "base_tag": res["base_tag"], "filter_name": fname}
    except ValueError as e:
        log(f"✗ {e} — ไฟล์เดิมไม่ถูกแตะ", "err")
    except OSError as e:
        log_.exception("filter generate error")
        log(_write_fail_msg(e, out_dir), "err")
    except Exception as e:
        log_.exception("filter generate error")
        log(f"✗ generate ล้มเหลว: {e}", "err")
    return None
