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

from . import debug, filter_core, filter_gen, filter_output, hub_client, neversink_source

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

    plan = filter_core.plan_fetch(fg_cfg, gv)

    if plan["mode"] == "whitelist":
        hub_data = None
        if plan["hub"]:
            try:
                hub_data = hub_client.get_prices(path)
            except Exception as e:
                log(f"⚠ ดึง hub ไม่ได้ ใช้เฉพาะ currency/ชื่อที่ติ๊ก: {e}", "warn")
        res = filter_core.build_filter_text(fg_cfg, gv, hub_data=hub_data, log=log)
        if res is None:
            return None
        try:
            out_path = filter_output.write_filter(out_dir, res["generated_section"], base_text=None)
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

    res = filter_core.build_filter_text(
        fg_cfg, gv, hub_data=hub_data, base_text=base_text, base_tag=tag,
        rules_loader=lambda: filter_gen.load_rules(app_dir),
        copy_sounds_fn=lambda sound_map: filter_output.copy_sounds(out_dir, sound_map),
        log=log)

    try:
        written = filter_output.write_filter(out_dir, res["generated_section"], res["base_text"])
        debug.event(f"filter generated gv={gv} league={league} base_tag={tag} "
                    f"hub={'ok' if hub_data is not None else 'unavailable'} path={written}")
        log(f"✓ เขียน filter แล้ว: {written}", "ok")
        log("Filter updated — reload in game (Options → Game)", "ok")
        return {"mode": "tier", "path": written, "signature": res["signature"],
                "mapping": res["mapping"], "base_tag": res["base_tag"]}
    except ValueError as e:
        log(f"✗ {e} — ไฟล์เดิมไม่ถูกแตะ", "err")
    except OSError as e:
        log_.exception("filter generate error")
        log(_write_fail_msg(e, out_dir), "err")
    except Exception as e:
        log_.exception("filter generate error")
        log(f"✗ generate ล้มเหลว: {e}", "err")
    return None
