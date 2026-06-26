"""ตรวจ 'เดิน/แพนกล้อง' ด้วยการเทียบภาพย่อ — ทำงานเฉพาะตอนโชว์ราคาอยู่ จึงแทบไม่กิน CPU."""
from __future__ import annotations
import threading
import time

from .capture import capture_screen

_STEP = 64          # เทียบทุกๆ 64 px
_DIFF_THRESH = 28   # ค่าต่างเฉลี่ยต่อ channel ที่ถือว่า 'เปลี่ยนก้อนใหญ่'
_FRAC_THRESH = 0.35 # สัดส่วนจุดที่เปลี่ยน > 35% = เดิน
_CONSEC = 2         # ต้องเปลี่ยนค้าง 2 เฟรมติด (กันสกิลวาบ)
_POLL = 0.15        # 150ms


def _sample(bgra: bytes, w: int, h: int) -> list[int]:
    pts = []
    stride = w * 4
    for y in range(0, h, _STEP):
        row = y * stride
        for x in range(0, w, _STEP):
            i = row + x * 4
            pts.append((bgra[i] + bgra[i + 1] + bgra[i + 2]) // 3)
    return pts


class MotionWatcher(threading.Thread):
    def __init__(self, on_motion):
        super().__init__(daemon=True, name="MotionWatcher")
        self._on_motion = on_motion
        self._stop = threading.Event()
        try:
            bgra, w, h = capture_screen()
            self._base = _sample(bgra, w, h)
        except Exception:
            self._base = None

    def run(self):
        if self._base is None:
            return
        consec = 0
        while not self._stop.is_set():
            time.sleep(_POLL)
            try:
                bgra, w, h = capture_screen()
                cur = _sample(bgra, w, h)
            except Exception:
                continue
            if len(cur) != len(self._base):
                self._base = cur
                continue
            changed = sum(1 for a, b in zip(cur, self._base) if abs(a - b) > _DIFF_THRESH)
            frac = changed / max(1, len(cur))
            if frac > _FRAC_THRESH:
                consec += 1
                if consec >= _CONSEC:
                    self._on_motion()
                    return
            else:
                consec = 0
            self._base = cur

    def stop(self):
        self._stop.set()
