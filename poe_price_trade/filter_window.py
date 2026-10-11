"""Filter Generator window — same visual style/helpers as settings.py."""
from __future__ import annotations
import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from . import (__version__, filter_core, filter_gen, filter_output, filter_service, filter_style, hub_client,
               ui_theme, wl_embed, wl_import)
from .wl_model import WlModel
from .wl_panel import WhitelistPanel
from .filter_style_editor import open_style_dialog
from .config import AppConfig
from .neversink_source import LEVELS

log = logging.getLogger(__name__)

_BG = "#1C1C1C"
_FG = "#E8D5A0"
_ACCENT = "#C8A050"
_INPUT_BG = "#2A2A2A"
_BUTTON_BG = "#3A3020"
_PANEL_FONT = ("Segoe UI", 9)
_SMALL_FONT = ("Segoe UI", 8)
_RARITIES = ["Normal", "Magic", "Rare", "Unique"]
_MONO_FONT = ("Consolas", 8)

_STRICTNESS_VALUES = [f"{i} - {lvl}" for i, lvl in enumerate(LEVELS)]


class FilterGenWindow:
    def __init__(self, parent: tk.Misc, config: AppConfig, game_version: str,
                 on_generate: Optional[Callable[[bool, str], None]] = None,
                 hub_loader: Optional[Callable[[], dict]] = None,
                 *, as_toplevel: bool = True):
        self._config = config
        self._game_version = game_version
        self._on_generate = on_generate
        self._as_toplevel = as_toplevel
        self._hub_loader = hub_loader
        self._model = WlModel(game_version)          # the whitelist tab's state (see wl_model)
        self._panel: Optional[WhitelistPanel] = None
        self._wl_tab: Optional[tk.Frame] = None
        self._wl_panel_row = 1
        self._wl_data: Optional[tuple] = None        # (hub, base_text, extra_names) once loaded
        self._opened_path: Optional[Path] = None     # a filter file opened for editing (Generate overwrites it)
        self._wl_loading = False
        self._style_q: Optional[dict] = None        # None = keep NeverSink's own quest blocks

        if as_toplevel:
            self._win = tk.Toplevel(parent)
            self._win.title(f"PoE Price & Trade Checker — Filter Generator v{__version__}")
            self._win.configure(bg=_BG)
            self._win.resizable(False, False)
            self._win.protocol("WM_DELETE_WINDOW", self._win.destroy)
        else:
            self._win = parent          # build into the frame/root handed in
        ui_theme.apply(self._win)

        self._vars: dict[str, tk.Variable] = {}
        self._pending_notes = self._init_model()
        self._build()
        self._load_from_config()
        for n in self._pending_notes:
            self.log("ℹ " + n, "warn")
        if self._on_generate is not None or self._hub_loader is not None:
            self._win.after(200, self._load_wl_data)      # lists fill in the background

    def _init_model(self) -> list:
        """The whitelist model from config; an old-style whitelist config is converted once (old keys stay)."""
        fg = dict(self._config.get("filter_gen", {}) or {})
        updates, notes = WlModel.convert_legacy(fg, self._game_version)
        if updates:
            fg.update(updates)
            self._config.set("filter_gen", fg)
            self._config.save()
        self._model = WlModel.from_config(fg, self._game_version)
        return notes

    # ------------------------------------------------------------------

    def _lbl(self, parent, text, row, col, **kw):
        tk.Label(parent, text=text, bg=_BG, fg=_FG, font=_PANEL_FONT, **kw).grid(
            row=row, column=col, sticky="w", padx=6, pady=3)

    def _entry(self, parent, key: str, row, col, width=10):
        var = tk.StringVar()
        self._vars[key] = var
        e = tk.Entry(parent, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                     relief=tk.FLAT, font=_PANEL_FONT, width=width)
        e.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return e

    def _combo(self, parent, key: str, values: list, row, col, width=18):
        var = tk.StringVar()
        self._vars[key] = var
        cb = ttk.Combobox(parent, textvariable=var, values=values, width=width,
                          state="readonly", font=_PANEL_FONT)
        cb.grid(row=row, column=col, sticky="w", padx=6, pady=3)
        return cb

    def _check(self, parent, key: str, text: str, row, col, columnspan=2):
        var = tk.BooleanVar()
        self._vars[key] = var
        tk.Checkbutton(parent, text=text, variable=var,
                       bg=_BG, fg=_FG, selectcolor="#2A2020", activebackground=_BG,
                       font=_PANEL_FONT).grid(row=row, column=col, columnspan=columnspan,
                                              sticky="w", padx=6, pady=3)
        return var

    def _btn(self, parent, text, cmd, side=None, **grid_kw):
        b = tk.Button(parent, text=text, command=cmd, bg=_BUTTON_BG, fg=_FG,
                     activebackground=_ACCENT, activeforeground="#000",
                     relief=tk.FLAT, font=_PANEL_FONT, padx=8, pady=3, cursor="hand2")
        if side is not None:
            b.pack(side=side, padx=4)
        elif grid_kw:
            b.grid(**grid_kw)
        return b

    def _sound_row(self, parent, key: str, label: str, row: int) -> None:
        self._lbl(parent, label, row, 0)
        var = tk.StringVar()
        self._vars[key] = var
        tk.Entry(parent, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                 readonlybackground=_INPUT_BG, disabledforeground=_FG,
                 relief=tk.FLAT, font=_PANEL_FONT, width=28, state="readonly").grid(
            row=row, column=1, sticky="w", padx=6, pady=3)
        btn_frame = tk.Frame(parent, bg=_BG)
        btn_frame.grid(row=row, column=2, sticky="w")
        self._btn(btn_frame, "Browse…", lambda k=key: self._browse_sound(k), side=tk.LEFT)
        self._btn(btn_frame, "Clear", lambda k=key: self._vars[k].set(""), side=tk.LEFT)

    def _browse_sound(self, key: str) -> None:
        path = filedialog.askopenfilename(
            title="Select alert sound",
            filetypes=[("Sound files", "*.mp3 *.wav"), ("All files", "*.*")])
        if path:
            self._vars[key].set(path)

    # ------------------------------------------------------------------

    def _build(self) -> None:
        f = tk.Frame(self._win, bg=_BG, padx=10, pady=8)
        f.pack(fill=tk.BOTH, expand=True)

        tk.Label(f, text=f"Filter Generator — {self._game_version.upper()}", bg=_BG, fg=_ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(pady=(0, 6))

        top = tk.Frame(f, bg=_BG)
        top.pack(fill=tk.X)
        self._lbl(top, "Game folder override:", 0, 0)
        var = tk.StringVar()
        self._vars["game_dir"] = var
        tk.Entry(top, textvariable=var, bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                 relief=tk.FLAT, font=_PANEL_FONT, width=28).grid(row=0, column=1, sticky="w", padx=6, pady=3)
        self._btn(top, "Browse…", self._browse_game_dir, row=0, column=2)
        tk.Label(top, text="(leave blank to auto-detect Documents\\My Games\\...)", bg=_BG, fg="#666",
                 font=_SMALL_FONT).grid(row=1, column=0, columnspan=3, sticky="w", padx=6)

        style = ttk.Style()
        try:
            style.configure("TNotebook.Tab", padding=(14, 4), font=_PANEL_FONT)
        except tk.TclError:
            pass
        self._nb = ttk.Notebook(f)
        self._nb.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        t1 = tk.Frame(self._nb, bg=_BG, padx=6, pady=6)
        t2 = tk.Frame(self._nb, bg=_BG, padx=6, pady=6)
        self._nb.add(t1, text="NeverSink")
        self._nb.add(t2, text="Whitelist")
        self._build_tier_tab(t1)
        self._build_whitelist_tab(t2)

        tk.Label(f, text="Status:", bg=_BG, fg=_FG, font=_PANEL_FONT).pack(anchor="w", pady=(8, 2))
        log_frame = tk.Frame(f, bg="#111")
        log_frame.pack(fill=tk.X)
        self._log_text = tk.Text(log_frame, bg="#111", fg="#AADDAA", font=_MONO_FONT,
                                 width=40, height=6, relief=tk.FLAT, state=tk.DISABLED, wrap=tk.WORD)
        self._log_text.pack(fill=tk.BOTH)
        self._log_text.tag_config("ok", foreground="#88DD88")
        self._log_text.tag_config("err", foreground="#DD6666")
        self._log_text.tag_config("warn", foreground="#DDCC66")
        self._log_text.tag_config("info", foreground="#AACCFF")

        btn_frame = tk.Frame(f, bg=_BG)
        btn_frame.pack(pady=(8, 0))
        self._btn(btn_frame, "Save Settings", self._save, side=tk.LEFT)
        if self._as_toplevel:
            self._btn(btn_frame, "Close", self._win.destroy, side=tk.LEFT)

    # ---- tab 1: NeverSink -------------------------------------------------

    def _name_row(self, f, key: str, row: int, extra: Optional[Callable[[tk.Frame], None]] = None) -> int:
        self._lbl(f, "ชื่อ filter:", row, 0)
        box = tk.Frame(f, bg=_BG)
        box.grid(row=row, column=1, columnspan=2, sticky="w")
        e = tk.Entry(box, textvariable=self._name_var(key), bg=_INPUT_BG, fg=_FG, insertbackground=_FG,
                     relief=tk.FLAT, font=_PANEL_FONT, width=30)
        e.pack(side=tk.LEFT, padx=6)
        tk.Label(box, text=".filter", bg=_BG, fg="#666", font=_SMALL_FONT).pack(side=tk.LEFT)
        if extra is not None:
            extra(box)
        return row + 1

    def _name_var(self, key: str) -> tk.StringVar:
        var = tk.StringVar()
        self._vars[key] = var
        return var

    def _build_tier_tab(self, f: tk.Frame) -> None:
        row = 0
        row = self._name_row(f, "filter_name_tier", row)
        self._lbl(f, "NeverSink Strictness:", row, 0)
        self._combo(f, "strictness", _STRICTNESS_VALUES, row, 1, width=18)
        row += 1

        self._lbl(f, "ของเควส (Q):", row, 0)
        qbox = tk.Frame(f, bg=_BG)
        qbox.grid(row=row, column=1, columnspan=2, sticky="w")
        self._btn(qbox, "ตั้งสไตล์…", self._open_quest_style, side=tk.LEFT)
        self._quest_lbl = tk.Label(qbox, text="", bg=_BG, fg="#888", font=_SMALL_FONT)
        self._quest_lbl.pack(side=tk.LEFT, padx=6)
        row += 1

        tk.Label(f, text="Alert sounds (S/A/B — C is always silent):", bg=_BG, fg=_FG,
                 font=_PANEL_FONT).grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=(8, 2))
        row += 1
        tk.Label(f, text="(เสียง S/A/B = tier สูงสุด/รอง/กลาง ของ NeverSink · ไฟล์ mp3/wav/ogg ใช้ชื่อเดิมของไฟล์)",
                 bg=_BG, fg="#666", font=_SMALL_FONT).grid(row=row, column=0, columnspan=3, sticky="w", padx=6)
        row += 1
        self._sound_row(f, "sound_s", "Tier S sound:", row); row += 1
        self._sound_row(f, "sound_a", "Tier A sound:", row); row += 1
        self._sound_row(f, "sound_b", "Tier B sound:", row); row += 1

        self._check(f, "auto_regen_neversink", "regenerate อัตโนมัติเมื่อ NeverSink ออกเวอร์ชันใหม่",
                    row, 0, columnspan=3)
        row += 1
        btns = tk.Frame(f, bg=_BG)
        btns.grid(row=row, column=0, columnspan=3, pady=(8, 0))
        self._btn(btns, "Generate Now", lambda: self._on_generate_clicked(False, "tier"), side=tk.LEFT)
        self._btn(btns, "Refresh NeverSink Base", lambda: self._on_generate_clicked(True, "tier"), side=tk.LEFT)

    # ---- tab 2: Whitelist ---------------------------------------------------

    def _new_panel(self) -> WhitelistPanel:
        return WhitelistPanel(self._wl_tab, self._model, on_changed=None,
                              goto_sound_tab=lambda: self._nb.select(0), get_sounds=self._shared_sounds)

    def _build_whitelist_tab(self, f: tk.Frame) -> None:
        self._wl_tab = f
        row = self._name_row(f, "filter_name_whitelist", 0,
                             extra=lambda box: self._btn(box, "เปิด filter…", self._open_filter_clicked, side=tk.LEFT))
        self._panel = self._new_panel()
        self._wl_panel_row = row
        self._panel.grid(row=row, column=0, columnspan=3, sticky="nsew")
        f.rowconfigure(row, weight=1)
        btns = tk.Frame(f, bg=_BG)
        btns.grid(row=row + 1, column=0, columnspan=3, pady=(6, 0))
        self._btn(btns, "Generate Now", lambda: self._on_generate_clicked(False, "whitelist"), side=tk.LEFT)
        self._btn(btns, "โหลดรายการใหม่", self._load_wl_data, side=tk.LEFT)

    def _shared_sounds(self) -> dict:
        """S / A / B / Q sounds as set on the NeverSink tab (shown read-only on the whitelist tab)."""
        out = {k: self._vars[f"sound_{k.lower()}"].get() for k in ("S", "A", "B")}
        if self._style_q:
            out["Q"] = filter_style.uses_sound_file(self._style_q) or ""
        return out

    def _load_wl_data(self) -> None:
        """Fetch hub + NeverSink + real names in a worker thread, then fill the lists on the Tk thread."""
        if self._wl_loading:
            return
        self._wl_loading = True
        self.log("⟳ โหลดรายการ whitelist (hub + NeverSink)…", "info")

        def work() -> None:
            try:
                data = filter_service.load_whitelist_inputs(
                    self._config, self._game_version, self._hub_loader,
                    log=lambda m, t="info": self._win.after(0, lambda: self.log(m, t)))
            except Exception as e:
                data = None
                err = str(e)
            try:
                self._win.after(0, lambda: self._wl_data_ready(data, None if data else err))
            except Exception:
                self._wl_loading = False

        threading.Thread(target=work, daemon=True).start()

    def _wl_data_ready(self, data, err) -> None:
        self._wl_loading = False
        if not data:
            self.log(f"✗ โหลดรายการไม่สำเร็จ: {err}", "err")
            return
        self.set_wl_data(*data)

    # ---- open an old filter -----------------------------------------------------

    def _out_dir(self) -> Path:
        return filter_output.game_filter_dir(self._game_version, self._vars["game_dir"].get().strip())

    def _open_filter_clicked(self) -> None:
        d = self._out_dir()
        path = filedialog.askopenfilename(
            parent=self._win, title="เปิด filter ที่สร้างจากโปรแกรมนี้", initialdir=str(d) if d.is_dir() else None,
            filetypes=[("Path of Exile filter", "*.filter"), ("All files", "*.*")])
        if path:
            self.open_filter(Path(path))

    def open_filter(self, path: Path) -> bool:
        """Load the settings embedded in a whitelist filter file into the tab (and its name into the name
        box); the next Generate overwrites that file after asking. False (and a message) when the file is
        not one this tab can edit."""
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self.log(f"✗ เปิดไฟล์ไม่ได้: {e}", "err")
            return False
        kind = wl_embed.classify(text)
        name = Path(path).stem
        _n, err = filter_core.validate_filter_name(name)
        if kind in ("ok", "no_config") and err:
            self.log(f"✗ ชื่อไฟล์ใช้เป็นชื่อ filter ไม่ได้: {err}", "err")
            return False
        if kind == "no_config":
            return self._open_old_filter(Path(path), text)
        if kind != "ok":
            self.log("✗ เปิดแก้ไม่ได้: ไฟล์นี้ไม่ได้สร้างจากแท็บ Whitelist ของโปรแกรมนี้"
                     if kind == "foreign" else
                     "✗ เปิดแก้ไม่ได้: ไฟล์นี้สร้างจากแท็บ NeverSink ไม่ใช่ Whitelist", "warn")
            return False
        data = wl_embed.extract(text)
        if data["game"] != self._game_version:
            self.log(f"✗ ไฟล์นี้เป็นของ {data['game'].upper()} แต่หน้าต่างนี้เป็น {self._game_version.upper()}", "warn")
            return False
        model = WlModel.from_config(data["cfg"], self._game_version)
        self._adopt(Path(path), model)
        made = f" (ค่าฝังจากรุ่น {data['app']})" if data.get("app") else " (ค่าฝังไม่ได้บันทึกรุ่น)"
        self.log(f"✓ เปิด {Path(path).name} แล้ว{made} — แก้แล้วกด Generate Now เพื่อเขียนทับไฟล์นี้", "ok")
        return True

    def _open_old_filter(self, path: Path, text: str) -> bool:
        """A whitelist file of this program from before settings were embedded (v1 / v2 engine): read its blocks
        back into settings (wl_import); what a block cannot say keeps the remembered value and is named in the log."""
        if wl_import.version_of(text) is None:
            self.log("✗ เปิดแก้ไม่ได้: ไฟล์นี้ไม่ได้สร้างจากแท็บ Whitelist ของโปรแกรมนี้", "warn")
            return False
        guess = wl_import.guess_game(text)
        if guess and guess != self._game_version:
            self.log(f"✗ ไฟล์นี้ดูเป็นของ {guess.upper()} แต่หน้าต่างนี้เป็น {self._game_version.upper()}", "warn")
            return False
        if self._wl_data is None:
            self.log("✗ ยังโหลดรายการ whitelist ไม่เสร็จ — รอให้โหลดเสร็จแล้วเปิดไฟล์อีกครั้ง "
                     "(ใช้ชื่อไอเท็มจริงอ่านไฟล์เก่ากลับ)", "warn")
            return False
        res = wl_import.read(text, self._game_version, self._model, folder=path.parent)
        if res is None or res["overlap"] < 0.2:
            self.log("✗ เปิดแก้ไม่ได้: ชื่อในไฟล์ไม่ตรงกับรายการของเกมนี้ — ไฟล์น่าจะเป็นของอีกเกมหรืออีกลีก", "warn")
            return False
        self._adopt(path, res["model"])
        ver = "v1 (โชว์เฉพาะแบบเก่า)" if res["version"] == "v1" else "v2 (ก่อนฝังค่าที่ตั้ง)"
        self.log(f"✓ เปิด {path.name} แล้ว — ไฟล์รุ่น {ver} ไม่มีค่าที่ฝังไว้ จึงอ่านกลับจาก block "
                 f"(แก้แล้วกด Generate Now เพื่อเขียนทับไฟล์นี้ แล้วไฟล์จะมีค่าฝังตามปกติ)", "ok")
        for note in res["notes"]:
            self.log("⚠ เดา/ปรับ: " + note, "warn")
        for label, fname in res["sounds"].items():
            self._adopt_sound(label, fname, path.parent)
        return True

    def _adopt_sound(self, label: str, fname: str, folder: Path) -> None:
        """Tier S / A / B sound = the file the old filter played (found next to it); Q is left to the NeverSink tab."""
        if label not in ("S", "A", "B"):
            return
        var = self._vars[f"sound_{label.lower()}"]
        found = folder / fname
        if Path(var.get() or "").name == fname:
            return
        if found.is_file():
            var.set(str(found))
            self.log(f"⚠ เสียง tier {label} ตั้งเป็น {fname} ตามไฟล์ที่เปิด (ใช้ร่วมกับแท็บ NeverSink)", "warn")
        else:
            self.log(f'⚠ เสียง tier {label} ในไฟล์คือ "{fname}" แต่ไม่พบไฟล์นี้ข้างๆ filter — ไม่ได้ตั้งเสียง', "warn")

    def _log_model_notes(self) -> None:
        for note in self._model.take_notes():
            self.log("⚠ " + note, "warn")

    def _adopt(self, path: Path, model: WlModel) -> None:
        """Make `model` the tab's settings, the file's name the filter name, and Generate write back to this file."""
        self._model = model
        if self._wl_data is not None:
            self._model.set_data(*self._wl_data)
            self._log_model_notes()
        old = self._panel
        if old is not None:
            old.destroy()
        self._panel = self._new_panel()
        self._panel.grid(row=self._wl_panel_row, column=0, columnspan=3, sticky="nsew")
        self._vars["filter_name_whitelist"].set(path.stem)
        parent = str(path.resolve().parent)
        if Path(parent) != self._out_dir().resolve():
            self._vars["game_dir"].set(parent)          # Generate writes back next to the opened file
        self._opened_path = path

    def set_wl_data(self, hub, base_text, extra_names) -> None:
        """Give the whitelist tab its data (also used by tests / callers that already have it)."""
        self._wl_data = (hub, base_text, extra_names)
        self._model.set_data(hub, base_text, extra_names)
        self._log_model_notes()
        if self._panel is not None:
            self._panel.data_loaded()
        self.log("✓ โหลดรายการ whitelist แล้ว" if base_text else
                 "⚠ ไม่มี NeverSink base filter — ไม่มี tier เริ่มต้น", "ok" if base_text else "warn")

    # ---- Q style ------------------------------------------------------------

    def _open_quest_style(self) -> None:
        def _save_q(style) -> None:
            self._style_q = None if style is None else style
            self._refresh_quest_label()
        start = self._style_q or filter_style.default_quest_style()
        open_style_dialog(self._win, "สไตล์ของเควส (Q)", start, _save_q, sample_text="Quest Item",
                          clear_text="ล้าง (ใช้ของ NeverSink)")

    def _refresh_quest_label(self) -> None:
        if self._style_q and not filter_style.is_empty(self._style_q):
            self._quest_lbl.configure(text="ตั้งสไตล์เองแล้ว", fg=_ACCENT)
        else:
            self._quest_lbl.configure(text="ใช้ของ NeverSink", fg="#888")

    # ---- sound file conflict (asked from the generate thread) ---------------------

    def ask_sound_conflict(self, name: str, new_name: str) -> str:
        """"overwrite" | "keep". Safe to call from a worker thread: the question is shown on the
        Tk thread and the caller waits (no answer in 5 minutes = keep the old file)."""
        answer: dict = {}
        done = threading.Event()

        def _ask() -> None:
            try:
                yes = messagebox.askyesno(
                    "ไฟล์เสียงชื่อซ้ำ",
                    f'ในโฟลเดอร์ filter มีไฟล์ "{name}" อยู่แล้ว แต่เป็นคนละไฟล์กับที่เลือก\n\n'
                    f'ใช่ = ทับไฟล์เดิม\nไม่ = เก็บไฟล์เดิมไว้ แล้วใช้ชื่อ "{new_name}" สำหรับไฟล์ใหม่',
                    parent=self._win)
                answer["v"] = "overwrite" if yes else "keep"
            except Exception:
                answer["v"] = "keep"
            finally:
                done.set()
        try:
            self._win.after(0, _ask)
        except Exception:
            return "keep"
        done.wait(300)
        return answer.get("v", "keep")

    def _browse_game_dir(self) -> None:
        path = filedialog.askdirectory(title="Select the game's filter folder")
        if path:
            self._vars["game_dir"].set(path)

    # ------------------------------------------------------------------

    def log(self, msg: str, tag: str = "info") -> None:
        try:
            widget = self._log_text
            widget.configure(state=tk.NORMAL)
            widget.insert(tk.END, msg + "\n", tag)
            widget.see(tk.END)
            widget.configure(state=tk.DISABLED)
        except Exception:
            pass

    # ------------------------------------------------------------------

    def _load_from_config(self) -> None:
        fg = dict(self._config.get("filter_gen", {}) or {})
        strictness = fg.get(f"strictness_{self._game_version}", 2)
        strictness = strictness if 0 <= strictness < len(_STRICTNESS_VALUES) else 2
        self._vars["strictness"].set(_STRICTNESS_VALUES[strictness])

        self._vars["sound_s"].set(fg.get("sound_s", ""))
        self._vars["sound_a"].set(fg.get("sound_a", ""))
        self._vars["sound_b"].set(fg.get("sound_b", ""))
        self._vars["game_dir"].set(fg.get(f"game_dir_{self._game_version}", ""))
        self._vars["filter_name_tier"].set(fg.get("filter_name_tier") or filter_core.DEFAULT_TIER_NAME)
        self._vars["filter_name_whitelist"].set(fg.get("filter_name_whitelist") or filter_core.DEFAULT_WHITELIST_NAME)
        self._vars["auto_regen_neversink"].set(bool(fg.get("auto_regen_neversink", False)))
        self._style_q = filter_style.normalize_style(fg["style_q"]) if fg.get("style_q") else None
        self._refresh_quest_label()
        try:
            self._nb.select(1 if fg.get("last_tab") == "whitelist" else 0)
        except tk.TclError:
            pass
    def _mode(self) -> str:
        """"tier" | "whitelist" - the tab that is open."""
        try:
            return "whitelist" if self._nb.index(self._nb.select()) == 1 else "tier"
        except tk.TclError:
            return "tier"

    def _save(self, mode: Optional[str] = None) -> dict:
        """Persist all fields (config.json's filter_gen dict) and return the
        resolved settings dict the caller needs to actually generate."""
        fg = dict(self._config.get("filter_gen", {}) or {})

        strictness_str = self._vars["strictness"].get()
        strictness = int(strictness_str.split(" - ")[0]) if strictness_str else 2
        fg[f"strictness_{self._game_version}"] = strictness

        fg["sound_s"] = self._vars["sound_s"].get()
        fg["sound_a"] = self._vars["sound_a"].get()
        fg["sound_b"] = self._vars["sound_b"].get()
        fg[f"game_dir_{self._game_version}"] = self._vars["game_dir"].get()
        mode = mode or self._mode()
        fg["whitelist_enabled"] = (mode == "whitelist")
        fg["last_tab"] = mode
        fg["filter_name_tier"] = self._vars["filter_name_tier"].get().strip() or filter_core.DEFAULT_TIER_NAME
        fg["filter_name_whitelist"] = (self._vars["filter_name_whitelist"].get().strip()
                                       or filter_core.DEFAULT_WHITELIST_NAME)
        fg["auto_regen_neversink"] = bool(self._vars["auto_regen_neversink"].get())
        fg["style_q"] = self._style_q          # None = never set; an emptied style is kept (reopens unticked)
        if self._panel is not None:
            self._panel.read_parts()
        self._model.to_config(fg)            # wl_v2 + every wl_* / whitelist_* key of the new engine
        self._config.set("filter_gen", fg)
        self._config.save()
        return fg

    def _on_generate_clicked(self, force_base: bool = False, mode: Optional[str] = None) -> None:
        mode = mode or self._mode()
        fg = self._save(mode)
        key = "filter_name_whitelist" if mode == "whitelist" else "filter_name_tier"
        _n, err = filter_core.validate_filter_name(fg[key])
        if err:
            self.log(f"✗ ชื่อ filter ใช้ไม่ได้: {err}", "err")
            return
        if mode == "whitelist" and self._opened_path is not None:
            target = filter_output.filter_path(self._out_dir(), fg[key])
            if target.resolve() == self._opened_path.resolve():
                if not messagebox.askyesno("เขียนทับ filter เดิม",
                                           f"จะเขียนทับไฟล์\n{target}\nด้วยค่าที่ตั้งอยู่ตอนนี้ — ต้องการต่อหรือไม่?",
                                           parent=self._win):
                    return
            self._opened_path = None
        if self._on_generate:
            self._on_generate(force_base, mode)
