"""Session logger — always-on. DEBUG=True เพิ่ม verbose FileHandler สำหรับ dev."""
from __future__ import annotations
import logging
import subprocess
from datetime import datetime
from pathlib import Path

DEBUG = False  # True = verbose .log file; session_*.md เปิดอยู่เสมอ

log = logging.getLogger("poe.debug")
_session: list[str] = []
_session_ts: str = ""
_MAX_SESSIONS = 10
_debug_dir: "Path | None" = None


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "nogit"


def setup(debug_dir: Path) -> None:
    global _session_ts, _debug_dir
    debug_dir.mkdir(parents=True, exist_ok=True)
    _debug_dir = debug_dir
    _session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if DEBUG:
        logfile = debug_dir / f"session_{_session_ts}.log"
        handler = logging.FileHandler(logfile, mode="w", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        root.addHandler(handler)

    header = f"=== {_session_ts} | git={_git_hash()} ==="
    _session.append(header)
    log.info(header)


def event(msg: str) -> None:
    """บันทึก event สำคัญ — เรียกได้เสมอ ไม่ขึ้นกับ DEBUG."""
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    _session.append(line)
    log.info(msg)


def raw_item(text: str) -> None:
    """เขียน raw clipboard text ของ item ล่าสุดลง last_raw_item.txt (overwrite ทุกครั้ง)."""
    if _debug_dir is None:
        return
    try:
        (_debug_dir / "last_raw_item.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass


def write_summary(debug_dir: Path) -> None:
    """เรียกตอนปิดโปรแกรม — เขียน session_*.md + last_session.md เสมอ; rotate เก็บ 10 ไฟล์ล่าสุด."""
    debug_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(debug_dir.glob("session_*.md"))
    for old in existing[:max(0, len(existing) - (_MAX_SESSIONS - 1))]:
        try:
            old.unlink()
        except Exception:
            pass

    body = "# PoE Price & Trade Checker — Session Log\n\n```\n" + "\n".join(_session) + "\n```\n"
    fname = f"session_{_session_ts}.md" if _session_ts else "last_session.md"
    (debug_dir / fname).write_text(body, encoding="utf-8")
    (debug_dir / "last_session.md").write_text(body, encoding="utf-8")
