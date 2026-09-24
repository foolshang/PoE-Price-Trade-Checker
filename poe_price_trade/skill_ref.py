"""Skill Mod Reference — data layer for the new F4 mode (config.f4_mode ==
"skill_ref", default off). Sits behind the flag and is never reached in the
default "price" mode (see app.py's _on_f4_scan).

v2 rewrite (2026-09-22): earlier "mods grouped by archetype" design (v0.7.5/
v0.7.6) assumed a hub shape that doesn't exist in production. Confirmed
against the real hub 2026-09-22: there is no archetype field anywhere and no
{game}/meta/latest.json per-exact-skill endpoint. Mods for a skill live in a
per-skill file, routed to by {game}/skills/index.json, keyed by
(skill_type, skill) — the same skill name can appear once as "main" and once
as "spirit" (e.g. Herald of Ice, Wolf Pack), so every lookup here takes both.
Passive popularity ({game}/passives/latest.json) joins on the same key.

No mock mode anymore — hub has real production data, so this module is
hub-only. mod_db.py is NOT used for text resolution here (unlike mod_badge.py)
— stat_id -> text comes entirely from {game}/skills/dictionary.json, with the
raw stat_id itself as a last-resort fallback instead of throwing.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import hub_client

log = logging.getLogger(__name__)

# Schema versions this module knows how to read. A mismatch (hub shipped a
# breaking schema change) degrades that payload to empty instead of crashing
# or silently misreading fields — see _check_schema().
SKILLS_SCHEMA_VERSION = 1
PASSIVES_SCHEMA_VERSION = 3
DICTIONARY_SCHEMA_VERSION = 1

_REMOVED_SKILL = "Removed Skill"


@dataclass
class Skill:
    skill_type: str
    skill: str
    slug: str
    facet_count: int
    populations: dict = field(default_factory=dict)   # {"75-90": 4, "90-100": 96}
    path: str = ""
    tags: list[str] = field(default_factory=list)     # from hub (joined from gems.json) — may be [] (e.g. Companion: X)


@dataclass
class SlotMod:
    slot: str
    stat_id: str
    mod_kind: str
    text: str
    usage_pct: float
    population: int
    value_min: Optional[float]
    value_max: Optional[float]


@dataclass
class Passive:
    keypassive: str
    level_bracket: str
    usage_pct: float
    population: int


def _strip_option_suffix(stat_id: str) -> str:
    """"explicit.stat_2422708892|51749" -> "explicit.stat_2422708892" — the
    "|N" suffix is an option index (e.g. which corrupted implicit variant)."""
    return stat_id.split("|", 1)[0]


class SkillRefDB:
    """Hub-only data layer. skills/index.json + skills/dictionary.json +
    passives/latest.json load eagerly in load(); a skill's own mod file loads
    lazily on first selection (via mods_for_skill) and is cached in memory
    for the rest of the session so switching between already-picked skills
    doesn't refetch."""

    def __init__(self, app_dir: Path, game_version: str = "poe2"):
        self._app_dir = app_dir
        self._game_version = game_version
        self._skills: list[Skill] = []
        self._skill_index: dict[tuple[str, str], Skill] = {}
        self._dictionary: dict = {}
        self._passives_by_key: dict[tuple[str, str], list[dict]] = {}
        self._skill_file_cache: dict[str, dict] = {}
        self._index_loaded = False

    def load(self) -> None:
        index = hub_client.get_skills_index(self._game_version)
        dictionary_payload = hub_client.get_skills_dictionary(self._game_version)
        passives_payload = hub_client.get_passives(self._game_version)

        self._dictionary = {}
        if dictionary_payload and self._check_schema(
                dictionary_payload, DICTIONARY_SCHEMA_VERSION, "skills/dictionary.json"):
            for row in dictionary_payload.get("stat_dictionary", []):
                sid = row.get("stat_id")
                template = row.get("template")
                if sid and template:
                    self._dictionary[sid] = template

        self._skills = []
        self._skill_index = {}
        self._index_loaded = bool(
            index and self._check_schema(index, SKILLS_SCHEMA_VERSION, "skills/index.json"))
        if self._index_loaded:
            for s in index.get("skills", []):
                name = s.get("skill")
                if not name or name == _REMOVED_SKILL:
                    continue
                skill = Skill(
                    skill_type=s.get("skill_type", ""),
                    skill=name,
                    slug=s.get("slug", ""),
                    facet_count=int(s.get("facet_count") or 0),
                    populations=s.get("populations") or {},
                    path=s.get("path", ""),
                    tags=[str(t).lower() for t in (s.get("tags") or [])],
                )
                self._skills.append(skill)
                self._skill_index[(skill.skill_type, skill.skill)] = skill
            self._skills.sort(key=lambda sk: sk.facet_count, reverse=True)

        self._passives_by_key = {}
        if passives_payload and self._check_schema(
                passives_payload, PASSIVES_SCHEMA_VERSION, "passives/latest.json"):
            for p in passives_payload.get("passives", []):
                key = (p.get("skill_type", ""), p.get("skill", ""))
                if not key[1]:
                    continue
                self._passives_by_key.setdefault(key, []).append(p)

        self._skill_file_cache = {}
        log.info("skill_ref loaded (%s): %d skills, %d dictionary entries, %d passive skill(s)",
                  self._game_version, len(self._skills), len(self._dictionary),
                  len(self._passives_by_key))

    def available(self) -> bool:
        return self._index_loaded

    @staticmethod
    def _check_schema(data: dict, expected: int, name: str) -> bool:
        got = data.get("schema_version")
        if got != expected:
            log.warning("skill_ref: %s schema_version=%r (expected %d) — treating as empty",
                        name, got, expected)
            return False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_skills(self, prefix: str) -> list[Skill]:
        p = prefix.strip().lower()
        if not p:
            return list(self._skills)
        # Match rank: name prefix (0) > name contains (1) > tag contains (2);
        # within a rank, higher facet_count (popular skills) first.
        ranked: list[tuple[int, int, Skill]] = []
        for s in self._skills:
            name = s.skill.lower()
            if name.startswith(p):
                rank = 0
            elif p in name:
                rank = 1
            elif any(p in t for t in s.tags):     # tags are lowercased in load()
                rank = 2
            else:
                continue
            ranked.append((rank, -s.facet_count, s))
        ranked.sort(key=lambda x: (x[0], x[1]))
        return [s for _, _, s in ranked]

    def skill_meta(self, skill_type: str, skill: str) -> Optional[Skill]:
        return self._skill_index.get((skill_type, skill))

    def mods_for_skill(self, skill_type: str, skill: str) -> dict[str, dict[str, list[SlotMod]]]:
        meta = self._skill_index.get((skill_type, skill))
        if meta is None or not meta.path:
            return {}
        data = self._load_skill_file(meta.path)
        if not data:
            return {}
        result: dict[str, dict[str, list[SlotMod]]] = {}
        for bracket, slots in data.get("mods", {}).items():
            bracket_out: dict[str, list[SlotMod]] = {}
            for slot, mods in slots.items():
                rows = []
                for m in mods:
                    stat_id = m.get("stat_id", "")
                    text = self._resolve_text(stat_id)
                    rows.append(SlotMod(
                        slot=slot,
                        stat_id=stat_id,
                        mod_kind=m.get("mod_kind", ""),
                        text=text,
                        usage_pct=float(m.get("usage_pct") or 0.0),
                        population=int(m.get("population") or 0),
                        value_min=m.get("value_min"),
                        value_max=m.get("value_max"),
                    ))
                bracket_out[slot] = rows
            result[bracket] = bracket_out
        return result

    def passives_for_skill(self, skill_type: str, skill: str) -> dict[str, list[Passive]]:
        rows = self._passives_by_key.get((skill_type, skill), [])
        by_bracket: dict[str, list[Passive]] = {}
        for p in rows:
            bracket = p.get("level_bracket", "")
            by_bracket.setdefault(bracket, []).append(Passive(
                keypassive=p.get("keypassive", ""),
                level_bracket=bracket,
                usage_pct=float(p.get("usage_pct") or 0.0),
                population=int(p.get("population") or 0),
            ))
        for bucket in by_bracket.values():
            bucket.sort(key=lambda pv: pv.usage_pct, reverse=True)
        return by_bracket

    # ------------------------------------------------------------------

    def _resolve_text(self, stat_id: str) -> str:
        """dictionary.json keeps a "|N" option-suffixed stat_id as its own
        entry with option-specific text (e.g. "...|5" -> "Legacy of Gold"),
        so the exact id is tried first; only a stat_id with no per-option
        entry at all falls back to the stripped (bare) form, and a stat_id
        found in neither falls back to itself instead of throwing."""
        if stat_id in self._dictionary:
            return self._dictionary[stat_id]
        stripped = _strip_option_suffix(stat_id)
        return self._dictionary.get(stripped, stat_id)

    def _load_skill_file(self, path: str) -> dict:
        if path in self._skill_file_cache:
            return self._skill_file_cache[path]
        data = hub_client.get_skill_file(path) or {}
        if data and not self._check_schema(data, SKILLS_SCHEMA_VERSION, path):
            data = {}
        self._skill_file_cache[path] = data
        return data
