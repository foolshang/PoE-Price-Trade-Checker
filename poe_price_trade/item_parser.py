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
_HEADER_TIER = re.compile(r"\(Tier:\s*(\d+)\)", re.IGNORECASE)
# ช่วง roll ที่เกมพิมพ์ต่อท้ายค่า เช่น 40(39-42)% หรือ +47(42-49) → ตัดทิ้งก่อนดึงตัวเลข
_ROLL_RANGE = re.compile(r"\(\d+(?:\.\d+)?-\d+(?:\.\d+)?\)")
_RUNE_LINE = re.compile(r"^(.*)\s\(rune\)$", re.IGNORECASE)


def _extract_mod_value(text: str) -> Optional[float]:
    m = _VALUE_PATTERN.search(_ROLL_RANGE.sub("", text))
    return float(m.group()) if m else None


def _extract_mod_values(text: str) -> tuple:
    return tuple(float(x) for x in _VALUE_PATTERN.findall(_ROLL_RANGE.sub("", text)))


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
    pending_tier = 0             # Tier จาก header ล่าสุด (0 = ไม่มี)
    group_no = -1                # หมายเลข header block (hybrid หลายบรรทัด = group เดียว)
    prefix_count = 0
    suffix_count = 0

    for section in sections[1:]:
        pending = None               # header block ไม่ข้าม separator
        for line in section:
            if not line:
                continue
            # ── rune mod: อยู่ section แยกก่อน header block, ลงท้ายด้วย (rune) ──
            if (rn := _RUNE_LINE.match(line)):
                group_no += 1
                mods.append(ModValue(
                    stat_id="", text=rn.group(1).strip(),
                    value=_extract_mod_value(line),
                    values=_extract_mod_values(line),
                    mod_type="rune", group=group_no,
                ))
                pending = None
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
                if "prefix" in low:
                    prefix_count += 1
                elif "suffix" in low:
                    suffix_count += 1
                tm = _HEADER_TIER.search(line)
                pending_tier = int(tm.group(1)) if tm else 0
                group_no += 1
                continue

            # ── บรรทัด mod ที่ตามหลัง header → เก็บทุก type (รวม desecrated) พร้อม type ──
            if pending is not None:
                mods.append(ModValue(
                    stat_id="",  # Filled in later by ModDatabase
                    text=line.strip(),
                    value=_extract_mod_value(line),
                    values=_extract_mod_values(line),
                    mod_type=pending,
                    tier=pending_tier,
                    group=group_no,
                ))
                # ไม่ reset pending — hybrid mod มีได้หลายบรรทัดใต้ header เดียว
                # (พิสูจน์จาก clipboard จริง: Crocodile's = Armour% + Life สองบรรทัด)
                # จบ block เมื่อเจอ header ใหม่ / separator / จบ section
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
    real_mods = [m for m in mods if m.mod_type != "rune"]
    if rarity in (Rarity.RARE, Rarity.UNIQUE) and len(name_lines) <= 1 and not real_mods:
        identified = False

    # ตัด quality prefix เฉพาะเมื่อขึ้นต้นด้วยคำ prefix จริงเท่านั้น — rare ที่มี quality
    # เกมไม่เติม "Superior" ใน base line (พิสูจน์จาก clipboard จริง: "Knightly Mitts"
    # + Quality 20% ไม่มีคำนำหน้า) → ตัดคำแรกแบบเดิมทำชื่อ base พัง ("Mitts")
    for _qp in ("Superior ", "Anomalous ", "Divergent ", "Phantasmal "):
        if base_type.startswith(_qp):
            base_type = base_type[len(_qp):].strip()
            break

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
        prefix_count=prefix_count,
        suffix_count=suffix_count,
    )
