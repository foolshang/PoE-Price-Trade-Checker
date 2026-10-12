"""What the Whitelist tab says and decides when a filter file is opened or the item lists arrive - kept here, in
pure Python, so the desktop window (Tk) and the web page (Pyodide) show the same messages and make the same
choices. No Tk, no file or network access: the caller reads the file and answers the two small questions about
sound files (what is set now, is there such a file next to the filter) through callbacks.

Messages are (tag, text) pairs, tag = "ok" | "warn" | "err" | "info", in the order they are to be shown."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import filter_core, filter_style, wl_embed, wl_import
from .wl_model import WlModel


@dataclass
class Opened:
    ok: bool
    messages: list = field(default_factory=list)
    model: Optional[WlModel] = None
    name: str = ""                                   # the filter name = the file name without ".filter"
    sounds: dict = field(default_factory=dict)       # S|A|B -> what to put in that sound slot (a path / name)
    kind: str = ""                                   # "embedded" | "old"
    app: str = ""                                    # program version that wrote the embedded settings ("" = not recorded)


def _fail(tag: str, text: str) -> Opened:
    return Opened(False, [(tag, text)])


def data_loaded_messages(model: WlModel, base_text: str) -> list:
    """After the item lists were given to the model: its notes (lists the saved settings did not know yet), then
    the "loaded" line."""
    out = [("warn", "⚠ " + n) for n in model.take_notes()]
    out.append(("ok", "✓ โหลดรายการ whitelist แล้ว") if base_text else
               ("warn", "⚠ ไม่มี NeverSink base filter — ไม่มี tier เริ่มต้น"))
    return out


def open_text(text: str, filename: str, game: str, current: WlModel, data: Optional[tuple], *,
              current_sound: Callable[[str], str] = lambda label: "",
              sound_file: Callable[[str], Optional[str]] = lambda name: None, folder=None) -> Opened:
    """Open the text of a whitelist filter file for the tab of `game`.
    `filename` = the file's name with its extension ("my.filter"); `current` = the settings now (remembered values
    for what an old file cannot say); `data` = (hub, base text, real names) or None when the lists are not loaded;
    `current_sound(label)` = (unused now: the tier sound is read from the model); `sound_file(name)` = a path / handle when a
    file of that name sits next to the opened filter, else None; `folder` = that folder (a pathlib.Path) when the
    caller has one: the file sounds of an old file's styles are then resolved to real paths."""
    stem = filename[:-len(".filter")] if filename.lower().endswith(".filter") else filename
    kind = wl_embed.classify(text)
    _n, err = filter_core.validate_filter_name(stem)
    if kind in ("ok", "no_config") and err:
        return _fail("err", f"✗ ชื่อไฟล์ใช้เป็นชื่อ filter ไม่ได้: {err}")
    if kind == "no_config":
        return _open_old(text, stem, filename, game, current, data, current_sound, sound_file, folder)
    if kind != "ok":
        return _fail("warn", "✗ เปิดแก้ไม่ได้: ไฟล์นี้ไม่ได้สร้างจากแท็บ Whitelist ของโปรแกรมนี้"
                     if kind == "foreign" else "✗ เปิดแก้ไม่ได้: ไฟล์นี้สร้างจากแท็บ NeverSink ไม่ใช่ Whitelist")
    emb = wl_embed.extract(text)
    if emb["game"] != game:
        return _fail("warn", f"✗ ไฟล์นี้เป็นของ {emb['game'].upper()} แต่หน้าต่างนี้เป็น {game.upper()}")
    model = WlModel.from_config(emb["cfg"], game)
    msgs: list = []
    if data is not None:
        model.set_data(*data)
        msgs += [("warn", "⚠ " + n) for n in model.take_notes()]
    made = f" (ค่าฝังจากรุ่น {emb['app']})" if emb.get("app") else " (ค่าฝังไม่ได้บันทึกรุ่น)"
    msgs.append(("ok", f"✓ เปิด {filename} แล้ว{made} — แก้แล้วกด Generate Now เพื่อเขียนทับไฟล์นี้"))
    return Opened(True, msgs, model, stem, {}, "embedded", emb.get("app") or "")


def _open_old(text, stem, filename, game, current, data, current_sound, sound_file, folder) -> Opened:
    """A whitelist file of this program from before settings were embedded (v1 / v2 engine): read its blocks back
    into settings (wl_import); what a block cannot say keeps the remembered value and is named in the messages."""
    if wl_import.version_of(text) is None:
        return _fail("warn", "✗ เปิดแก้ไม่ได้: ไฟล์นี้ไม่ได้สร้างจากแท็บ Whitelist ของโปรแกรมนี้")
    guess = wl_import.guess_game(text)
    if guess and guess != game:
        return _fail("warn", f"✗ ไฟล์นี้ดูเป็นของ {guess.upper()} แต่หน้าต่างนี้เป็น {game.upper()}")
    if data is None:
        return _fail("warn", "✗ ยังโหลดรายการ whitelist ไม่เสร็จ — รอให้โหลดเสร็จแล้วเปิดไฟล์อีกครั้ง "
                     "(ใช้ชื่อไอเท็มจริงอ่านไฟล์เก่ากลับ)")
    res = wl_import.read(text, game, current, folder=folder)
    if res is None or res["overlap"] < 0.2:
        return _fail("warn", "✗ เปิดแก้ไม่ได้: ชื่อในไฟล์ไม่ตรงกับรายการของเกมนี้ — ไฟล์น่าจะเป็นของอีกเกมหรืออีกลีก")
    model = res["model"]
    msgs: list = [("warn", "⚠ " + n) for n in model.take_notes()]
    ver = "v1 (โชว์เฉพาะแบบเก่า)" if res["version"] == "v1" else "v2 (ก่อนฝังค่าที่ตั้ง)"
    msgs.append(("ok", f"✓ เปิด {filename} แล้ว — ไฟล์รุ่น {ver} ไม่มีค่าที่ฝังไว้ จึงอ่านกลับจาก block "
                       f"(แก้แล้วกด Generate Now เพื่อเขียนทับไฟล์นี้ แล้วไฟล์จะมีค่าฝังตามปกติ)"))
    msgs += [("warn", "⚠ เดา/ปรับ: " + n) for n in res["notes"]]
    sounds: dict = {}
    for label, fname in res["sounds"].items():            # tier S / A / B sound = the file the old filter played
        if label not in ("S", "A", "B"):
            continue                                       # Q is left to the NeverSink tab
        cur_style = model.tier_style.get(label) or {}
        cur_sound = (cur_style.get("sound") or {})
        found = sound_file(fname)
        if found:
            sounds[label] = found
            style = dict(cur_style, sound={"kind": "file", "id": 1, "file": str(found), "volume": 300})
            model.tier_style[label] = filter_style.normalize_style(style)
            msgs.append(("warn", f"⚠ เสียง tier {label} ของแท็บ Whitelist ตั้งเป็น {fname} ตามไฟล์ที่เปิด"))
        else:
            if cur_sound.get("kind") == "file":            # the importer kept the bare name: no file, so no sound
                model.tier_style[label] = filter_style.normalize_style(dict(cur_style, sound={"kind": "none"}))
            msgs.append(("warn", f'⚠ เสียง tier {label} ในไฟล์คือ "{fname}" แต่ไม่พบไฟล์นี้ข้างๆ filter — ไม่ได้ตั้งเสียง'))
    return Opened(True, msgs, model, stem, sounds, "old")
