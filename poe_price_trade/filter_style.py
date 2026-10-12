"""Item style (colours, size, minimap icon, beam, alert sound) -> filter lines.

Pure (stdlib only, runs in Pyodide too). One style dict is edited by the style
editor widget and turned into filter text here, for every thing the user can
style (quest items today; gold / tablet / map / S / A / B in the whitelist tab).

    {"text": [r, g, b, a] | None, "border": [...] | None, "bg": [...] | None,
     "size": 18..45 | None,
     "icon": {"size": 0..2, "color": "Red", "shape": "Star"} | None,
     "effect": {"color": "Red", "temp": False} | None,
     "sound": {"kind": "none" | "game" | "file", "id": 1..16, "file": "x.mp3", "volume": 0..300},
     "off": ["text", "sound", ...]}       (whitelist tiers only, see merge_styles)

Everything missing / None is simply not written (the game's own look stays). "off" lists the parts the
player switched OFF on top of a base look (NeverSink's): they are removed from it instead of following it.
"""
from __future__ import annotations
from typing import Optional

COLORS = ["Red", "Green", "Blue", "Brown", "White", "Yellow", "Cyan", "Grey", "Orange", "Pink", "Purple"]
SHAPES = ["Circle", "Diamond", "Hexagon", "Square", "Star", "Triangle", "Cross", "Moon", "Raindrop", "Kite",
          "Pentagon", "UpsideDownHouse"]
SOUND_IDS = list(range(1, 17))
FONT_MIN, FONT_MAX = 18, 45
VOLUME_MAX = 300
DEFAULT_VOLUME = 300
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg")
PARTS = ("text", "border", "bg", "size", "icon", "effect", "sound")
# filter keywords each part writes (what "off" removes from a base look)
PART_KEYWORDS = {"text": ("SetTextColor",), "border": ("SetBorderColor",), "bg": ("SetBackgroundColor",),
                 "size": ("SetFontSize",), "icon": ("MinimapIcon",), "effect": ("PlayEffect",),
                 "sound": ("PlayAlertSound", "CustomAlertSound", "CustomAlertSoundOptional")}

# rough sRGB values of the filter's colour names, for the editor preview only
COLOR_RGB = {
    "Red": (255, 40, 40), "Green": (40, 200, 60), "Blue": (60, 100, 255), "Brown": (150, 90, 40),
    "White": (255, 255, 255), "Yellow": (255, 220, 40), "Cyan": (40, 220, 220), "Grey": (160, 160, 160),
    "Orange": (255, 140, 30), "Pink": (255, 130, 190), "Purple": (170, 70, 220),
}


def _rgba(v) -> Optional[list]:
    """[r, g, b] or [r, g, b, a] clamped to 0..255; anything else -> None."""
    if not isinstance(v, (list, tuple)) or len(v) not in (3, 4):
        return None
    try:
        out = [max(0, min(255, int(x))) for x in v]
    except (TypeError, ValueError):
        return None
    return out if len(out) == 4 else out + [255]


def normalize_style(raw) -> dict:
    """A clean style dict from whatever is stored in a config (unknown keys dropped,
    numbers clamped, bad values -> None). Never raises."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {"text": _rgba(raw.get("text")), "border": _rgba(raw.get("border")), "bg": _rgba(raw.get("bg"))}
    try:
        size = raw.get("size")
        out["size"] = None if size in (None, "") else max(FONT_MIN, min(FONT_MAX, int(size)))
    except (TypeError, ValueError):
        out["size"] = None
    icon = raw.get("icon")
    if isinstance(icon, dict) and icon.get("color") in COLORS and icon.get("shape") in SHAPES:
        try:
            out["icon"] = {"size": max(0, min(2, int(icon.get("size", 0)))), "color": icon["color"],
                           "shape": icon["shape"]}
        except (TypeError, ValueError):
            out["icon"] = None
    else:
        out["icon"] = None
    eff = raw.get("effect")
    out["effect"] = ({"color": eff["color"], "temp": bool(eff.get("temp"))}
                     if isinstance(eff, dict) and eff.get("color") in COLORS else None)
    snd = raw.get("sound") if isinstance(raw.get("sound"), dict) else {}
    kind = snd.get("kind") if snd.get("kind") in ("game", "file") else "none"
    try:
        volume = max(0, min(VOLUME_MAX, int(snd.get("volume", DEFAULT_VOLUME))))
    except (TypeError, ValueError):
        volume = DEFAULT_VOLUME
    try:
        sid = int(snd.get("id", 1))
        sid = sid if sid in SOUND_IDS else 1
    except (TypeError, ValueError):
        sid = 1
    out["sound"] = {"kind": kind, "id": sid, "file": str(snd.get("file") or ""), "volume": volume}
    off = raw.get("off")
    if isinstance(off, (list, tuple)):
        parts = sorted({p for p in off if p in PARTS})
        if parts:
            out["off"] = parts
    return out


def is_empty(style) -> bool:
    """True when the style would write nothing at all (= keep NeverSink's / the game's own)."""
    s = normalize_style(style)
    return (not any(s[k] for k in ("text", "border", "bg", "icon", "effect")) and s["size"] is None
            and s["sound"]["kind"] == "none" and not s.get("off"))


def uses_sound_file(style) -> Optional[str]:
    """The source file name/path of a file sound, else None."""
    snd = normalize_style(style)["sound"]
    return snd["file"] if snd["kind"] == "file" and snd["file"] else None


def style_lines(style, sound_file: Optional[str] = None, indent: str = "    ") -> list:
    """Filter lines for the style, in NeverSink's order. `sound_file` is the file name the sound
    was copied under (the caller resolves it); a file sound without one is left out. A game sound
    is a plain PlayAlertSound; a file sound is CustomAlertSoundOptional (a missing file must not
    stop the whole filter from loading)."""
    s = normalize_style(style)
    out = []
    if s["size"] is not None:
        out.append(f"{indent}SetFontSize {s['size']}")
    for key, kw in (("text", "SetTextColor"), ("border", "SetBorderColor"), ("bg", "SetBackgroundColor")):
        if s[key]:
            out.append(f"{indent}{kw} " + " ".join(str(x) for x in s[key]))
    snd = s["sound"]
    if snd["kind"] == "game":
        out.append(f"{indent}PlayAlertSound {snd['id']} {snd['volume']}")
    elif snd["kind"] == "file" and sound_file:
        out.append(f'{indent}CustomAlertSoundOptional "{sound_file}" {snd["volume"]}')
    if s["effect"]:
        out.append(f"{indent}PlayEffect {s['effect']['color']}" + (" Temp" if s["effect"]["temp"] else ""))
    if s["icon"]:
        out.append(f"{indent}MinimapIcon {s['icon']['size']} {s['icon']['color']} {s['icon']['shape']}")
    return out


def lines_to_style(lines) -> dict:
    """The style dict of filter style lines (SetFontSize / Set*Color / PlayAlertSound / PlayEffect /
    MinimapIcon) - e.g. NeverSink's own look of a tier, so an editor can start from it. Unknown lines are
    ignored; never raises."""
    raw: dict = {"sound": {"kind": "none"}}
    for line in lines or []:
        toks = str(line).split()
        if not toks:
            continue
        kw, vals = toks[0], toks[1:]
        try:
            if kw == "SetFontSize":
                raw["size"] = int(vals[0])
            elif kw == "SetTextColor":
                raw["text"] = [int(x) for x in vals]
            elif kw == "SetBorderColor":
                raw["border"] = [int(x) for x in vals]
            elif kw == "SetBackgroundColor":
                raw["bg"] = [int(x) for x in vals]
            elif kw == "PlayAlertSound":
                raw["sound"] = {"kind": "game", "id": int(vals[0]),
                                "volume": int(vals[1]) if len(vals) > 1 else DEFAULT_VOLUME}
            elif kw == "PlayEffect":
                raw["effect"] = {"color": vals[0], "temp": "Temp" in vals[1:]}
            elif kw == "MinimapIcon":
                raw["icon"] = {"size": int(vals[0]), "color": vals[1], "shape": vals[2]}
        except (ValueError, IndexError):
            continue
    return normalize_style(raw)


def merge_styles(base, over) -> dict:
    """`over` on top of `base`: every part `over` sets replaces the one of `base` (an unset part keeps
    base's); the sound of `over` wins only when it plays something; a part listed in over's "off" is
    removed from the result. Mirrors how the whitelist engine lays a player's style over NeverSink's own look."""
    b, o = normalize_style(base), normalize_style(over)
    out = dict(b)
    out.pop("off", None)
    for k in ("text", "border", "bg", "size", "icon", "effect"):
        if o[k] is not None and o[k] != []:
            out[k] = o[k]
    if o["sound"]["kind"] != "none":
        out["sound"] = o["sound"]
    for part in o.get("off") or ():
        out[part] = normalize_style({})["sound"] if part == "sound" else None
    return out


def default_quest_style() -> dict:
    """What the Q (quest items) editor starts from: green text, nothing else."""
    s = normalize_style({})
    s["text"] = [74, 230, 58, 255]
    return s


def _preset(**kw) -> dict:
    s = normalize_style({})
    s.update(kw)
    return s


# What the whitelist tab starts from for the things NeverSink has no matching block for
# (S / A / B start as copies of NeverSink's own tier 1 / 2 / 3 look, taken from its base filter; C is the faded preset).
DEFAULT_STYLES = {
    # tier C: shown, but fainter than B (small, muted text on a near-black background, no beam, a small grey icon)
    "C": _preset(text=[190, 178, 135, 255], border=[120, 112, 85, 255], bg=[20, 20, 0, 255], size=36,
                 icon={"size": 2, "color": "Grey", "shape": "Circle"}),
    "G": _preset(text=[255, 215, 0, 255], border=[255, 215, 0, 255], bg=[40, 30, 0, 255], size=40),
    "Tablet": _preset(text=[0, 230, 230, 255], border=[0, 230, 230, 255], bg=[0, 30, 40, 255], size=40,
                      icon={"size": 1, "color": "Cyan", "shape": "Square"}),
    "Map": _preset(text=[255, 255, 255, 255], border=[200, 200, 200, 255], bg=[30, 30, 30, 255], size=40,
                   icon={"size": 1, "color": "White", "shape": "Diamond"}),
}
