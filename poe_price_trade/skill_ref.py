"""Skill Mod Reference — data layer for the new F4 mode (config.f4_mode ==
"skill_ref", default off). Prep work only: this whole module sits behind the
flag and is never reached in the default "price" mode (see app.py's
_on_f4_scan). MOCK ONLY right now per spec — never calls hub_client /
Firebase — hub doesn't publish skills[]/passives[] yet.

Shape mirrors {game}/meta/latest.json's mods[] (SPEC.md section 8.2) plus a
skills[] field the hub doesn't send yet, so switching MOCK -> HUB later is a
source swap, not a rewrite.

TODO(hub): meta/latest.json ยังไม่มี field เหล่านี้ รอ hub เพิ่ม:
  - skills[]  (ชื่อสกิล + archetype)  -> สำหรับ autocomplete + map
  - passives[] (keystone/notable ยอดนิยม ต่อ archetype) -> เฟส 2
  - ยังไม่เคาะ: archetype พอ หรือต้องแยกตามสกิลเป๊ะ
    (รอ hub บอกว่าดึงได้เท่าไหร่ / ข้อมูลหนาแค่ไหน ก่อนตัดสิน)
เมื่อ hub พร้อม: เปลี่ยน source ใน SkillRefDB จาก "mock" -> "hub"
  (จะเรียก hub_client.get_meta() จริง) แล้วเปิด flag config.f4_mode = "skill_ref"
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_MOCK_SUBDIR = "mock"
_MOCK_FILENAME = "skill_meta_mock.json"

_EMPTY: dict = {"schema_version": 1, "league": "MOCK", "skills": [], "mods": [], "passives": []}


@dataclass
class SkillMeta:
    name: str
    archetype: str


@dataclass
class SlotMod:
    slot: str
    stat_id: str
    text: str
    usage_pct: float
    rank: int


class SkillRefDB:
    """source="mock" (default, only implemented path) reads
    %LOCALAPPDATA%\\PoePriceTrade\\mock\\skill_meta_mock.json. source="hub" is an
    intentional stub — raises until the hub ships skills[] (see TODO(hub) above)."""

    def __init__(self, app_dir: Path, source: str = "mock"):
        self._app_dir = app_dir
        self._source = source
        self._skills: list[SkillMeta] = []
        self._skill_by_name: dict[str, SkillMeta] = {}
        self._mods_by_archetype: dict[str, dict[str, list[SlotMod]]] = {}

    def load(self) -> None:
        if self._source == "hub":
            self._load_hub_stub()
            return
        self._load_mock()

    # ------------------------------------------------------------------

    def _mock_path(self) -> Path:
        return self._app_dir / _MOCK_SUBDIR / _MOCK_FILENAME

    def _load_mock(self) -> None:
        path = self._mock_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            log.warning("skill_ref mock file not found: %s", path)
            data = dict(_EMPTY)
        except Exception as e:
            log.warning("skill_ref mock load failed: %s", e)
            data = dict(_EMPTY)
        self._index(data)

    def _load_hub_stub(self) -> None:
        raise NotImplementedError(
            "skill_ref hub source not wired up yet — hub has no skills[]/passives[] "
            "(see TODO(hub) at the top of skill_ref.py). Use source='mock' until then."
        )

    def _index(self, data: dict) -> None:
        skills = [
            SkillMeta(name=s["name"], archetype=s["archetype"])
            for s in data.get("skills", []) if s.get("name") and s.get("archetype")
        ]
        by_archetype: dict[str, dict[str, list[SlotMod]]] = {}
        for m in data.get("mods", []):
            archetype = m.get("archetype", "")
            slot = m.get("slot", "")
            if not archetype or not slot:
                continue
            mod = SlotMod(
                slot=slot,
                stat_id=m.get("stat_id", ""),
                text=m.get("text", ""),
                usage_pct=float(m.get("usage_pct") or 0.0),
                rank=int(m.get("rank_in_slot") or 0),
            )
            by_archetype.setdefault(archetype, {}).setdefault(slot, []).append(mod)
        for slots in by_archetype.values():
            for mods in slots.values():
                mods.sort(key=lambda m: m.rank)

        self._skills = skills
        self._skill_by_name = {s.name: s for s in skills}
        self._mods_by_archetype = by_archetype
        log.info("skill_ref mock loaded: %d skills, %d archetypes", len(skills), len(by_archetype))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_skills(self, prefix: str) -> list[SkillMeta]:
        p = prefix.strip().lower()
        if not p:
            return list(self._skills)
        return [s for s in self._skills if s.name.lower().startswith(p)]

    def mods_for_skill(self, name: str) -> dict[str, list[SlotMod]]:
        skill = self._skill_by_name.get(name)
        if skill is None:
            return {}
        return self._mods_by_archetype.get(skill.archetype, {})

    def passives_for_skill(self, name: str) -> list:
        return []   # เฟส 2: รอ hub ส่ง passives[] — stub คืน [] เสมอตอนนี้
