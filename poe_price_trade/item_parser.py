"""Parse PoE item text (from Ctrl+C in-game) into a ParsedItem.
Handles both PoE1 and PoE2 clipboard formats. Both are nearly identical in structure."""
from __future__ import annotations
import re
import logging
from typing import Optional

from .models import GameVersion, ModValue, ParsedItem, Rarity

log = logging.getLogger(__name__)

_SEPARATOR = re.compile(r"^-{3,}$", re.MULTILINE)
_ITEM_CLASS = re.compile(r"^Item Class:\s*(.+)$", re.IGNORECASE)
_RARITY = re.compile(r"^Rarity:\s*(.+)$", re.IGNORECASE)
_ITEM_LEVEL = re.compile(r"^Item Level:\s*(\d+)$", re.IGNORECASE)
_QUALITY = re.compile(r"^Quality:\s*\+?(\d+)%", re.IGNORECASE)
_CORRUPTED = re.compile(r"^Corrupted$", re.IGNORECASE)
_UNIDENTIFIED = re.compile(r"^Unidentified$", re.IGNORECASE)
_NOTE = re.compile(r"^Note:")
_STACK_SIZE = re.compile(r"^Stack Size:\s*[\d,]+/[\d,]+$", re.IGNORECASE)

# Mod value extraction: matches "... +123 ..." or "... 45% ..."
_VALUE_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")

# Mod header ของ PoE2 clipboard: { Implicit Modifier }, { Prefix Modifier "..." }, { Desecrated ... }
_MOD_HEADER = re.compile(r"^\{.*\bModifier\b.*\}$", re.IGNORECASE)


def _extract_mod_value(text: str) -> Optional[float]:
    m = _VALUE_PATTERN.search(text)
    return float(m.group()) if m else None


def _is_section_header(line: str) -> bool:
    return bool(_ITEM_CLASS.match(line) or _RARITY.match(line))


def parse_item(text: str, game_version: str = GameVersion.POE2) -> Optional[ParsedItem]:
    """Parse clipboard item text. Returns None if text doesn't look like a PoE item."""
    if not text or "Rarity:" not in text:
        return None

    lines = [l.rstrip() for l in text.splitlines()]
    sections: list[list[str]] = [[]]
    for line in lines:
        if _SEPARATOR.match(line):
            sections.append([])
        else:
            sections[-1].append(line)

    # Section 0: Item Class + Rarity + Name
    header = sections[0] if sections else []
    item_class = ""
    rarity = ""
    name_lines: list[str] = []

    for line in header:
        cm = _ITEM_CLASS.match(line)
        if cm:
            item_class = cm.group(1).strip()
            continue
        rm = _RARITY.match(line)
        if rm:
            rarity = rm.group(1).strip()
            continue
        if line and not line.startswith("Note:"):
            name_lines.append(line)

    if not rarity:
        return None

    # PoE items have 1-line or 2-line names
    # For rare/unique: line 1 = rare name, line 2 = base type
    # For currency/gem: line 1 = item name
    item_name = name_lines[0].strip() if name_lines else ""
    base_type = name_lines[1].strip() if len(name_lines) > 1 else item_name

    # Scan remaining sections for metadata and mods
    item_level = 0
    quality = 0
    corrupted = False
    identified = True
    mods: list[ModValue] = []

    # เก็บ mod จาก header { ... Modifier } เป็นหลัก (ตรงกับ in-game search ของเกม)
    # mod = บรรทัดที่ตามหลัง header เท่านั้น → stat อาวุธ (Physical Damage ฯลฯ) ไม่ถูกเก็บ
    # desecrated → ข้าม (เกมไม่เอามาค้น) | ถ้า clipboard ไม่มี header → fallback heuristic เดิม
    has_mod_headers = any(_MOD_HEADER.match(ln) for s in sections[1:] for ln in s)
    pending: str | None = None   # ประเภท mod จาก header ล่าสุด (None = ไม่ใช่ mod)

    for section in sections[1:]:
        for line in section:
            if not line:
                continue
            # ── metadata ──
            if _CORRUPTED.match(line):
                corrupted = True; pending = None; continue
            if _UNIDENTIFIED.match(line):
                identified = False; pending = None; continue
            if (m := _ITEM_LEVEL.match(line)):
                item_level = int(m.group(1)); pending = None; continue
            if (m := _QUALITY.match(line)):
                quality = int(m.group(1)); pending = None; continue

            # ── header { ... Modifier ... } → อ่าน type ของ mod บรรทัดถัดไป ──
            if _MOD_HEADER.match(line):
                low = line.lower()
                if "implicit" in low:
                    pending = "implicit"
                elif "desecrated" in low:
                    pending = "desecrated"
                elif "enchant" in low:
                    pending = "enchant"
                elif "fractured" in low:
                    pending = "fractured"
                elif "rune" in low:
                    pending = "rune"
                else:
                    pending = "explicit"          # prefix / suffix
                continue

            # ── บรรทัด mod ที่ตามหลัง header → เก็บทุก type (รวม desecrated) พร้อม type ──
            if pending is not None:
                mods.append(ModValue(
                    stat_id="",  # Filled in later by ModDatabase
                    text=line.strip(),
                    value=_extract_mod_value(line),
                    mod_type=pending,
                ))
                pending = None            # 1 header = 1 mod line → consume แล้ว reset
                continue

            # ── fallback: clipboard ไม่มี header { } (copy โหมดธรรมดา) → heuristic เดิม ──
            if has_mod_headers:
                continue   # item นี้ใช้ header-driven → ไม่ใช้ fallback
            if _NOTE.match(line) or _STACK_SIZE.match(line):
                continue
            if (
                not line.startswith(("Requirements:", "Requires:", "Sockets:", "Level:",
                                     "Str:", "Dex:", "Int:")) and
                not re.match(r"^(Armour|Evasion|Energy Shield|Ward|Block):", line) and
                not re.match(r"^(Damage|APS|Critical|Attacks|Casts|DPS):", line, re.IGNORECASE) and
                not re.match(r"^(Physical|Elemental|Chaos|Cold|Fire|Lightning) Damage:", line, re.IGNORECASE) and
                _VALUE_PATTERN.search(line)
            ):
                mods.append(ModValue(
                    stat_id="",  # Filled in later by ModDatabase.resolve()
                    text=line.strip(),
                    value=_extract_mod_value(line),
                ))

    # Desecrated items may omit "Unidentified" text. Rare/unique with only
    # 1 name line (= no special rare name) AND no mods = truly unidentified.
    # Items with mods are identified even if they share name and base type.
    if rarity in (Rarity.RARE, Rarity.UNIQUE) and len(name_lines) <= 1 and not mods:
        identified = False

    # ไอเท็มที่มี quality เกมเติม prefix คุณภาพ (Superior/Anomalous/Divergent/...) ข้างหน้า base
    # ตัดคำแรกออกเมื่อมี quality — ไม่ต้องเดาว่า prefix คือคำอะไร
    if quality > 0 and " " in base_type:
        base_type = base_type.split(" ", 1)[1].strip()

    if not item_name:
        return None

    log.debug("Parsed item: '%s' rarity=%s ilvl=%d mods=%d", item_name, rarity, item_level, len(mods))

    return ParsedItem(
        item_name=item_name,
        base_type=base_type,
        rarity=rarity,
        item_level=item_level,
        quality=quality,
        mods=mods,
        game_version=game_version,
        raw_text=text,
        item_class=item_class,
        corrupted=corrupted,
        identified=identified,
    )
