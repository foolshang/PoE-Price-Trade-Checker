"""Debug logging — เปิด/ปิดด้วย DEBUG flag. ตอน build จริงตั้ง DEBUG=False บรรทัดเดียว."""
from __future__ import annotations
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path

DEBUG = False  # ตั้ง True ระหว่าง dev เพื่อเปิด session log

log = logging.getLogger("poe.debug")
_session: list[str] = []


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "nogit"


def setup(debug_dir: Path) -> None:
    """เรียกครั้งเดียวตอนเปิดโปรแกรม."""
    if not DEBUG:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logfile = debug_dir / f"session_{ts}.log"
    handler = logging.FileHandler(logfile, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    header = f"=== SESSION {ts} | git={_git_hash()} ==="
    log.info(header)
    _session.append(header)


def event(msg: str) -> None:
    """บันทึก event สำคัญสำหรับ summary (F4/F5/ninja/ลีก/จอ)."""
    if not DEBUG:
        return
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    _session.append(line)
    log.info(msg)


def write_summary(debug_dir: Path) -> None:
    """เรียกตอนปิดโปรแกรม — เขียนสรุปสั้นๆ ให้ Claude อ่านง่าย."""
    if not DEBUG:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    out = debug_dir / "last_session.md"
    body = "# Session Summary\n\n```\n" + "\n".join(_session) + "\n```\n"
    out.write_text(body, encoding="utf-8")
