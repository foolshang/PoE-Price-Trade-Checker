"""Economy Filter Generator — tiering/emit logic.

Reads poe-data-hub's raw prices payload (hub_client.get_prices()) directly,
bypassing PriceRepository/PriceEntry entirely: those flatten currency[]+
items[] together and drop the `base` field, both of which this module needs
(per-category bucketing, unique-by-basetype). Zero coupling to the F4/F5
pricing pipeline — see CLAUDE.md.

Matches on `BaseType` only (no `Class` condition) — verified against a real
downloaded NeverSink PoE2 filter that currency-type rules use BaseType alone,
and Class names don't map 1:1 onto hub category labels anyway.
"""
from __future__ import annotations
import copy
import hashlib
import json
import logging
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# poe2's UncutGem/LineageGem/SkillGem categories bake the gem level into
# `name` ("Uncut Skill Gem (Level 20)" vs "...(Level 1)") for pricing
# purposes — that's poe.ninja's display disambiguation, not the item's real
# in-game BaseType ("Uncut Skill Gem", level is a separate GemLevel filter
# condition this generator doesn't emit). A BaseType=="...(Level N)" rule
# would never match a real item, and colliding names down to the bare base
# would tier every level (including worthless level-1 drops) by whichever
# level's price is highest, sound-spamming junk early league. Left to
# NeverSink's own gem handling instead. Verified live 2026-07-24.
EXCLUDE_CATEGORIES = {"UncutGem", "LineageGem", "SkillGem"}

_DEFAULT_RULES: dict = {
    # min_divine_pct is the *primary* tiering signal (fraction of the
    # snapshot's own live Divine Orb chaos_value) — self-scales with the
    # league's economy instead of a fixed chaos amount, so a 30-40c item on
    # day 1 (when Divine itself might only be worth ~40c) can reach tier S
    # immediately instead of waiting for Divine to inflate to the point
    # where 30-40c is still a small fraction of it, and later in the league
    # when Divine is worth 300c+ the same tiers keep meaning "roughly this
    # fraction of a Divine" instead of quietly becoming too generous. Each
    # tier's own min_chaos is kept only as the fallback used when Divine
    # Orb's price can't be resolved from the snapshot at all (see
    # _resolve_divine_chaos) — not the normal path.
    #
    # max_count guards against a real failure mode found live 2026-07-25:
    # Divine Orb's own chaos_value isn't always "the top of the economy" —
    # checked against a real hub snapshot where Divine sat at 8.76c while
    # Mirror of Kalandra was ~4800x that. A pure percent-of-Divine threshold
    # in that snapshot put 169 names in tier S alone, diluting NeverSink's
    # curated anchor block (14 items in the real file) into a wall of noise
    # and defeating the entire point of a "prominent" tier. max_count keeps
    # the top N by chaos value per tier; the rest cascade down to the next
    # tier (_apply_max_count) rather than disappearing.
    "tiers": [
        {"name": "S", "min_divine_pct": 0.20, "min_chaos": 150, "max_count": 20,
         "border": "255 0 0", "text": "255 0 0",
         "bg": "255 255 255", "size": 45, "sound": "6 300",
         "beam": "Red", "icon": "0 Red Star"},
        {"name": "A", "min_divine_pct": 0.05, "min_chaos": 20, "max_count": 40,
         "border": "255 170 0", "text": "255 170 0",
         "bg": "0 0 0", "size": 45, "sound": "1 300",
         "beam": "Yellow", "icon": "1 Yellow Circle"},
        {"name": "B", "min_divine_pct": 0.01, "min_chaos": 5, "max_count": 80,
         "border": "0 200 255", "text": "0 200 255",
         "bg": "0 0 0", "size": 40, "sound": None,
         "beam": None, "icon": "2 Blue Circle"},
        {"name": "C", "min_divine_pct": 0.002, "min_chaos": 1, "max_count": None,
         "border": "150 150 150", "text": "200 200 200",
         "bg": "0 0 0", "size": 35, "sound": None,
         "beam": None, "icon": None},
    ],
    # Below this, tier_of() never returns S/A/B/C for a currency name — and
    # unlike the pre-2026-07-27 "hide_below" bucket, that no longer routes it
    # into a self-generated dim block either. It's simply left wherever
    # NeverSink's own base filter already has it (see bucket_currency):
    # currency's own tiering is NeverSink's call, not ours to override
    # downward. See CLAUDE.md-adjacent incident: a dead-league snapshot
    # (Divine 8.76c) reported Chaos Orb's own chaos_value near 0, which used
    # to fall into the dim bucket and visually override NeverSink's real
    # (prominent) Chaos Orb block, since generated_section is always written
    # before base_text (first-match-wins).
    #
    # divine_sanity_floor guards the *tiering* side of the same incident:
    # Divine Orb's own chaos_value is the denominator for every
    # min_divine_pct threshold (see below), so a crashed/anomalous Divine
    # price collapses every tier threshold toward zero and can flood tiers
    # with spurious promotions (observed live: 8.76c Divine put 169 names in
    # tier S alone). Below this floor, tiering for that generate run falls
    # back to each tier's absolute min_chaos instead of trusting the
    # snapshot's own Divine price — see _resolve_divine_chaos_for_tiering.
    # 15c is a conservative heuristic (real live leagues essentially never
    # sit below this outside a dying league); override via
    # filter_gen_rules.json if a particular league's economy runs unusually
    # cheap.
    "divine_sanity_floor": 15.0,
    "sound_volume": 300,
    # tier -> representative item used to (a) inherit S/A/B's default sound
    # from the loaded NeverSink base filter (apply_base_filter_sounds, the
    # "sound" fields above are only its fallback) and (b) locate each tier's
    # target block for merge_currency_into_base (Plan B — relocating hub
    # BaseTypes directly into NeverSink's own blocks instead of emitting our
    # own).
    #
    # Each tier maps to an *ordered list* of candidate BaseTypes, not one
    # fixed name — changed 2026-08-08 after a second, more general anchor
    # failure: switching PoE1 to strictness 3 (STRICT) broke tier C's single
    # "Orb of Transmutation" anchor again, the same failure mode as the
    # 2026-07-27 "Orb of Augmentation" incident (see git history), just at a
    # different strictness. A single anchor name for a tier is inherently
    # fragile across 14 real NeverSink files (2 games x 7 strictness levels,
    # verified live 2026-08-08 — see tools/verify_anchors.py): NeverSink
    # reshuffles which BaseTypes share a block, and higher strictness levels
    # genuinely Hide low-value currency outright (no ordinary Show block for
    # it at all), so any single fixed name can and will stop resolving on
    # some (game, strictness) combination sooner or later. _resolve_anchor
    # tries each tier's candidates in order and uses the first that resolves
    # to a real Show block (_find_anchor_block); a bare string is still
    # accepted everywhere an anchor is passed (single-candidate list of one).
    #
    # Ordered "closest semantic fit" first, then progressively safer
    # fallbacks confirmed to still land in a reasonable (same-or-more-
    # prominent, never a *lower* tier's block) Show block on every one of the
    # 14 real files: S/A/B's first candidate alone already resolves on all
    # 14 (Divine/Exalted/Chaos Orb are never hidden at any real strictness
    # level), so their extra entries are pure defensive slack. C is the tier
    # that actually needs the fallback chain in practice — "Orb of
    # Transmutation" only holds through SEMI-STRICT (0-2) on both games;
    # STRICT+ (3-5) falls through to "Orb of Alchemy" (still an ordinary,
    # if less cheap, currency block on both games at those levels); PoE1's
    # UBER-PLUS-STRICT (6) hides every dedicated low-currency block, so C
    # only resolves there via "Chromatic Orb", which UBER-PLUS-STRICT still
    # bundles into the same Show block as Chaos/Exalted Orb rather than
    # hiding — landing tier C's currency there is preferable to skipping it
    # outright (see merge_currency_into_base's per-tier skip: a tier is only
    # ever left untouched when *none* of its candidates resolve at all).
    "anchors": {
        "S": ["Divine Orb", "Mirror of Kalandra"],
        "A": ["Exalted Orb", "Chaos Orb"],
        "B": ["Chaos Orb", "Vaal Orb", "Regal Orb"],
        "C": ["Orb of Transmutation", "Orb of Augmentation", "Scroll of Wisdom",
              "Orb of Alchemy", "Chromatic Orb"],
    },
}


def load_rules(config_dir: Optional[Path]) -> dict:
    """Current code defaults (_DEFAULT_RULES) with only each tier's
    min_chaos fallback threshold overridden from filter_gen_rules.json, if
    present — the one field the Filter Generator UI actually lets the user
    edit ("Tier thresholds (chaos, fallback)"). Every other field (anchors,
    colors, sound, min_divine_pct, max_count, divine_sanity_floor, ...)
    always comes from the current code, never frozen from an old save.

    This is a merge, not a wholesale replace — changed 2026-07-27 after a
    live incident: the old wholesale-replace behavior meant that on any
    machine where the user had ever clicked "Save Settings" or "Generate"
    (which also calls save), the *entire* rules dict loaded at that moment —
    including anchors, which the UI has never exposed at all — got frozen to
    disk. That silently re-broke a since-fixed anchor default on every
    subsequent load/save cycle, on every affected machine, with no way to
    recover short of manually deleting the file. Never raises; a file that's
    missing, unreadable, or not a JSON object is treated the same as
    "no overrides"."""
    rules = copy.deepcopy(_DEFAULT_RULES)
    if config_dir is None:
        return rules
    path = config_dir / "filter_gen_rules.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return rules
    except Exception as e:
        log.warning("filter_gen_rules load fail: %s", e)
        return rules
    if not isinstance(loaded, dict):
        log.warning("filter_gen_rules.json malformed (not an object) — using defaults")
        return rules
    loaded_tiers = loaded.get("tiers")
    if isinstance(loaded_tiers, list):
        by_name = {t.get("name"): t for t in loaded_tiers if isinstance(t, dict) and t.get("name")}
        for tier_cfg in rules["tiers"]:
            override = by_name.get(tier_cfg["name"])
            if not override or "min_chaos" not in override:
                continue
            try:
                tier_cfg["min_chaos"] = float(override["min_chaos"])
            except (TypeError, ValueError):
                log.warning("filter_gen_rules.json: ignoring invalid min_chaos override for tier %s",
                           tier_cfg["name"])
    return rules


def save_rules(config_dir: Path, rules: dict) -> None:
    """Persists only each tier's min_chaos fallback threshold — deliberately
    not a wholesale dump of `rules` (which also carries anchors, colors,
    sound, min_divine_pct, max_count, divine_sanity_floor — all code-owned,
    never user-edited). See load_rules' docstring for why a full dump used
    to silently freeze a stale value across every future code fix."""
    path = config_dir / "filter_gen_rules.json"
    payload = {"tiers": [{"name": t["name"], "min_chaos": t.get("min_chaos")}
                         for t in rules.get("tiers", [])]}
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning("filter_gen_rules.json save failed: %s", e)


# ---------------------------------------------------------------------------
# Inherit default S/A/B sounds from the loaded NeverSink base filter
# ---------------------------------------------------------------------------

_BASETYPE_LINE = re.compile(r'^\s*BaseType\s*(?:==)?\s*((?:"[^"]*"\s*)+)$')
_PLAY_ALERT_LINE = re.compile(r'^\s*PlayAlertSound\s+(.+?)\s*$')
_CUSTOM_ALERT_LINE = re.compile(r'^\s*(CustomAlertSound(?:Optional)?)\s+(.+?)\s*$')
_STACKSIZE_LINE = re.compile(r'^\s*StackSize\s*(>=|<=|==|>|<)?\s*(\d+)\s*$')

# Style/action keywords — everything else non-blank/non-comment in a block is
# a *condition*. Deliberately not exhaustive on the condition side: an
# unrecognized condition keyword is treated the same as a known-narrowing one
# (AreaLevel/ItemLevel/Sockets/Quality/...) — conservatively excluded rather
# than assumed harmless, since a false "this is a plain item" would silently
# borrow a sound from a rule that doesn't actually apply to an ordinary drop.
_ACTION_KEYWORDS = {
    "SetBorderColor", "SetTextColor", "SetBackgroundColor", "SetFontSize",
    "PlayAlertSound", "PlayAlertSoundPositional", "CustomAlertSound",
    "CustomAlertSoundOptional", "MinimapIcon", "PlayEffect",
    "DisableDropSound", "EnableDropSound", "DropSound", "DropSoundIf", "Continue",
}
_ALLOWED_CONDITION_KEYWORDS = {"Class", "BaseType", "Rarity"}


class _Block:
    """One active (non-commented) Show/Hide block, located within some
    `lines = text.split("\\n")` list. `start`/`end` are indices into that
    list: `lines[start]` is the "Show"/"Hide" header line itself, `end` is
    exclusive. `basetype_line`/`basetype_names` describe its BaseType
    condition line, if it has one (a block can have none, e.g. a Class-only
    catch-all)."""
    __slots__ = ("block_type", "start", "end", "basetype_line", "basetype_names")

    def __init__(self, block_type, start, end, basetype_line, basetype_names):
        self.block_type = block_type
        self.start = start
        self.end = end
        self.basetype_line = basetype_line
        self.basetype_names = basetype_names


def _parse_blocks(lines: list) -> list:
    """Single source of truth for locating Show/Hide blocks in a filter's
    text (used by both the sound-inheritance and the currency block-surgery
    features, so they always agree on where a block starts/ends and what its
    BaseType condition currently says). A block starts at a line whose first
    token — unindented — is exactly "Show" or "Hide"; everything indented
    under it belongs to that block until the next such line."""
    blocks: list = []
    block_type = None
    start = None
    basetype_line = None
    basetype_names: list = []
    for i, raw_line in enumerate(lines):
        first_token = raw_line.split(None, 1)[0] if raw_line.strip() else ""
        is_block_start = (not raw_line[:1].isspace()) and first_token in ("Show", "Hide")
        if is_block_start:
            if block_type is not None:
                blocks.append(_Block(block_type, start, i, basetype_line, basetype_names))
            block_type, start = first_token, i
            basetype_line, basetype_names = None, []
            continue
        if block_type is not None:
            m = _BASETYPE_LINE.match(raw_line)
            if m:
                basetype_line = i
                basetype_names = re.findall(r'"([^"]*)"', m.group(1))
    if block_type is not None:
        blocks.append(_Block(block_type, start, len(lines), basetype_line, basetype_names))
    return blocks


def _iter_filter_blocks(text: str):
    """Yield (block_type, condition/action lines) for each block — the
    lines *after* the Show/Hide header, up to (not including) the next
    block. Convenience wrapper around _parse_blocks for callers that only
    need to read a block's contents, not mutate it."""
    lines = text.split("\n")
    for b in _parse_blocks(lines):
        yield b.block_type, lines[b.start + 1:b.end]


def _find_anchor_block(blocks: list, lines: list, anchor_name: str) -> Optional[_Block]:
    """The first block (file order) whose BaseType condition contains
    `anchor_name` AND could actually match a plain single-item drop (see
    _block_matches_plain_single_item) — the shared resolution logic behind
    both _find_anchor_sound and merge_currency_into_base, so a tier's
    "representative block" always means the same thing for both features.
    None if no such block exists, or the first qualifying one is Hide (an
    anchor that's only reachable via Hide never actually shows/sounds for a
    plain drop, so treat it the same as "not found")."""
    for b in blocks:
        if anchor_name not in b.basetype_names:
            continue
        if not _block_matches_plain_single_item(lines[b.start + 1:b.end]):
            continue
        return b if b.block_type == "Show" else None
    return None


def _resolve_anchor(blocks: list, lines: list, candidates) -> Optional[tuple]:
    """(block, resolved_name) for the first of `candidates` (tried in file-
    declaration order) that resolves via _find_anchor_block — the shared
    fallback-chain logic behind every anchor consumer (apply_base_filter_sounds,
    resolve_real_styles, merge_currency_into_base, resolve_anchors), so
    "which candidate a tier actually resolved to" always means the same
    thing everywhere. `candidates` may be a single anchor name (back-compat
    with plain-string overrides, e.g. in tests) or an ordered list — see
    _DEFAULT_RULES["anchors"] for why a single name per tier isn't resilient
    across real NeverSink files. None if none of the candidates resolve."""
    if isinstance(candidates, str):
        candidates = [candidates]
    for name in candidates or []:
        block = _find_anchor_block(blocks, lines, name)
        if block is not None:
            return block, name
    return None


def resolve_anchors(base_text: Optional[str], anchors: dict) -> dict:
    """{tier_name: resolved_anchor_name_or_None} — the per-tier candidate
    resolution merge_currency_into_base/apply_base_filter_sounds/
    resolve_real_styles each perform internally, exposed standalone so a
    caller can report *which* tier(s) failed instead of one lumped pass/
    fail (the Filter Generator's status log, tools/verify_anchors.py). A
    tier mapping to None here means every one of its candidates failed to
    resolve on this base filter — merge_currency_into_base leaves that
    tier's currency wherever NeverSink's own filter already has it rather
    than failing the whole merge. {every tier: None} if base_text is
    falsy."""
    if not base_text:
        return {name: None for name in anchors}
    lines = base_text.split("\n")
    blocks = _parse_blocks(lines)
    status: dict = {}
    for tier_name, candidates in anchors.items():
        resolved = _resolve_anchor(blocks, lines, candidates)
        status[tier_name] = resolved[1] if resolved else None
    return status


def _stacksize_excludes_single_item(op: Optional[str], n: int) -> bool:
    """Whether a lone (StackSize 1) item drop would fail this StackSize
    condition — e.g. "StackSize >= 2" excludes it, "StackSize <= 1" or
    "StackSize == 1" don't. No operator defaults to "==" (PoE filter
    convention for numeric conditions)."""
    op = op or "=="
    if op == "==":
        return n != 1
    if op == ">=":
        return n > 1
    if op == ">":
        return n >= 1
    if op == "<=":
        return n < 1
    if op == "<":
        return n <= 1
    return True


def _block_matches_plain_single_item(lines: list) -> bool:
    """True iff a bare, unremarkable single item (StackSize 1, no special
    tags) could actually match this block's conditions. Only Class/BaseType/
    Rarity conditions are allowed unconditionally; a StackSize condition that
    a lone item still satisfies (e.g. "StackSize <= 1") is fine too. Any
    other condition — StackSize >= n for n>1, AreaLevel, ItemLevel, Sockets,
    Quality, or anything else — means this block only ever applies to some
    special-cased drop, not the item as it'd actually be seen dropping
    normally, so it must be skipped when inferring a tier's "real" sound
    (a StackSize>=n/AreaLevel/etc.-gated block appearing before the item's
    ordinary rule was reported to give the wrong inherited sound)."""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        first_token = stripped.split(None, 1)[0]
        if first_token in _ACTION_KEYWORDS or first_token in _ALLOWED_CONDITION_KEYWORDS:
            continue
        if first_token == "StackSize":
            m = _STACKSIZE_LINE.match(line)
            if m and not _stacksize_excludes_single_item(m.group(1), int(m.group(2))):
                continue
            return False
        return False  # unrecognized/known-narrowing condition keyword
    return True


def _block_sound_directive(lines: list) -> Optional[tuple]:
    for line in lines:
        m = _PLAY_ALERT_LINE.match(line)
        if m:
            return "PlayAlertSound", m.group(1)
        m = _CUSTOM_ALERT_LINE.match(line)
        if m:
            return m.group(1), m.group(2)       # kind: CustomAlertSound | CustomAlertSoundOptional
    return None


def _find_anchor_sound(base_text: str, anchor_candidates) -> Optional[tuple]:
    """(kind, raw_directive_text) from the first candidate's resolved block
    (see _resolve_anchor) — None if no candidate resolves to a qualifying
    Show block at all, or that block has no sound line. `anchor_candidates`
    is a single name or an ordered fallback list, same as everywhere else."""
    lines = base_text.split("\n")
    resolved = _resolve_anchor(_parse_blocks(lines), lines, anchor_candidates)
    if resolved is None:
        return None
    block, _name = resolved
    return _block_sound_directive(lines[block.start + 1:block.end])


def apply_base_filter_sounds(rules: dict, base_text: Optional[str],
                              anchors: Optional[dict] = None) -> dict:
    """Returns a copy of `rules` where each of S/A/B's default "sound" is
    replaced by whatever PlayAlertSound/CustomAlertSound the loaded NeverSink
    base filter actually uses for that tier's anchor item (rules["anchors"],
    e.g. S -> "Divine Orb") — added after a user reported the hardcoded S/A/B
    defaults were too quiet compared to what NeverSink itself uses for real
    top-end currency drops. Falls back to the rules file's own "sound" value
    (left untouched) + a log.warning when: base_text is unavailable, the
    anchor isn't found anywhere in the base filter, the first block matching
    it is Hide, or a matching Show block has no sound line. Never touches
    tier C (not in the anchors map) or the emit-time user sound_map override
    (that's applied later in _style_lines and always wins over this)."""
    result = copy.deepcopy(rules)
    anchor_map = anchors if anchors is not None else rules.get("anchors", _DEFAULT_RULES["anchors"])

    for tier_cfg in result.get("tiers", []):
        name = tier_cfg["name"]
        if name not in ("S", "A", "B"):
            continue  # C is silent by design — anchors["C"] exists only for merge_currency_into_base
        if name not in anchor_map:
            continue
        anchor = anchor_map[name]
        if not base_text:
            log.warning("Filter sound inherit: no base filter loaded — tier %s keeps rules-file default", name)
            continue
        found = _find_anchor_sound(base_text, anchor)
        if found is None:
            log.warning("Filter sound inherit: no candidate of %r for tier %s resolved (not found, "
                       "or only in a Hide rule) in base filter — using rules-file default", anchor, name)
            continue
        kind, raw = found
        tier_cfg["sound"] = {"kind": kind, "raw": raw}
    return result


# ---------------------------------------------------------------------------
# Plan B: relocate currency BaseTypes directly into NeverSink's own blocks
# ---------------------------------------------------------------------------

_BASETYPE_PREFIX = re.compile(r'^(\s*)BaseType\s*(==)?\s*')

# Lower = more prominent. Fixed to exactly the four anchor tiers merge always
# resolves (the `for tier_name in ("S", "A", "B", "C")` loop below) — not
# derived from rules["tiers"] order, since the never-demote guard has to mean
# the same ranking regardless of what a filter_gen_rules.json override does
# to tier definitions.
_TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3}


def merge_currency_into_base(base_text: str, currency_tiers: dict, rules: dict,
                              anchors: Optional[dict] = None) -> tuple:
    """Relocates each currency BaseType name in `currency_tiers` (S/A/B/C
    from bucket_currency) directly into NeverSink's own base filter in-place,
    instead of emitting our own separate currency Show blocks — replaces the
    old approach after a user reported the sounds we emitted didn't match
    NeverSink's real ones, even after inheriting the anchor's sound
    (apply_base_filter_sounds only copies the *sound value*, not the item's
    actual position in NeverSink's own tier ladder — surgically moving the
    BaseType itself is the only way the item ends up under NeverSink's *own*
    rule, sound and all, with zero copying/drift risk).

    For each tier's anchor block (same resolution as apply_base_filter_sounds
    — _find_anchor_block, so "the representative block for a tier" always
    means the same thing everywhere): every name assigned to that tier is
    (a) removed from every earlier-in-file block that currently lists it —
    otherwise that earlier block would still win first-match-wins and our
    move would silently do nothing — and (b) added to the target block's
    BaseType list if not already present. A name in a block *after* the
    target is left alone: first-match-wins means it can never fire anyway,
    so touching it would just be a no-op edit that grows the diff for
    nothing. Only BaseType lines are ever rewritten — no style/sound/other
    condition on any block is touched, and a block that ends up unchanged
    (item was already correctly placed, nowhere earlier) is never rewritten
    at all, byte-for-byte.

    Never-demote guard: if `name` already sits in one of the four S/A/B/C
    anchor blocks *before* any relocation this call makes, and the hub-
    computed tier for it is *less* prominent than that (_TIER_RANK), the
    move is refused — it stays at its current (more prominent) block instead.
    Added after a live incident (2026-07-27) where a dead/end-of-league
    snapshot reported near-zero chaos_value for ordinary top-shelf currency
    (Chaos Orb itself), which — before the dim-bucket fix in bucket_currency
    — got dimmed outright, and even with that fixed, bad economy data could
    still have demoted it to a lower real NeverSink tier than its curated
    default. This tool's job is to raise prices NeverSink might be
    under-valuing, never to push an item below whatever prominence NeverSink
    already gives it by default — a crashed/noisy price snapshot must not be
    able to make an item *less* visible than the pristine base filter would.
    Only checked against the baseline captured from the *original*,
    unmutated `base_text` (each _Block.basetype_names is set once during
    parsing) — so this never ratchets across repeated generate runs, since
    `base_text` is always freshly (re-)fetched from NeverSink upstream, not
    our own previously-merged output.

    Per-tier resolution, not all-or-nothing (changed 2026-08-08 — see
    _DEFAULT_RULES["anchors"] for the incident this fixes): each of S/A/B/C
    tries its own candidate list independently via _resolve_anchor. A tier
    whose candidates all fail to resolve is simply skipped — its currency is
    left wherever NeverSink's base filter already has it, exactly like an
    untiered name — while every other tier that *did* resolve still merges
    normally. Use resolve_anchors(base_text, anchor_map) if a caller needs to
    know *which* tier(s) were skipped, e.g. for a status message.

    Returns (new_text, applied). applied=False (new_text == base_text,
    completely unmodified) only when *none* of S/A/B/C's candidates resolve
    to a qualifying Show block at all — nothing to merge into."""
    anchor_map = anchors if anchors is not None else rules.get("anchors", _DEFAULT_RULES["anchors"])
    lines = base_text.split("\n")
    blocks = _parse_blocks(lines)

    target_blocks: dict = {}
    for tier_name in ("S", "A", "B", "C"):
        candidates = anchor_map.get(tier_name)
        resolved = _resolve_anchor(blocks, lines, candidates) if candidates else None
        if resolved is None:
            log.warning("Currency surgery: no anchor candidate resolved for tier %s (tried %r) — "
                       "that tier's currency is left wherever NeverSink's base filter already has "
                       "it; any other tier that did resolve still merges normally",
                       tier_name, candidates)
            continue
        target_blocks[tier_name], _resolved_name = resolved

    if not target_blocks:
        return base_text, False

    # Baseline placement, read from the anchor blocks' original (unmutated)
    # basetype_names — see never-demote guard above.
    baseline_tier_by_name: dict = {}
    for tier_name, block in target_blocks.items():
        for name in block.basetype_names:
            baseline_tier_by_name[name] = tier_name

    # mutable per-block working copy of BaseType names, keyed by block.start
    block_names: dict = {b.start: list(b.basetype_names) for b in blocks if b.basetype_line is not None}
    changed: set = set()
    demoted_count = 0

    for tier_name, names in currency_tiers.items():
        for name in names:
            effective_tier = tier_name
            baseline_tier = baseline_tier_by_name.get(name)
            if (baseline_tier is not None
                    and _TIER_RANK.get(tier_name, 0) > _TIER_RANK.get(baseline_tier, 0)):
                effective_tier = baseline_tier
                demoted_count += 1
            target = target_blocks.get(effective_tier)
            if target is None:
                continue
            for b in blocks:
                if b.start >= target.start:
                    break  # blocks are in file order — nothing at/after target matters
                if b.basetype_line is None:
                    continue
                current = block_names[b.start]
                if name in current:
                    current.remove(name)
                    changed.add(b.start)
            target_names = block_names[target.start]
            if name not in target_names:
                target_names.append(name)
                changed.add(target.start)

    if demoted_count:
        log.warning("Currency guard: kept %d item(s) at their existing NeverSink tier instead of "
                 "the hub-computed lower tier — never reducing prominence below NeverSink's own "
                 "default placement", demoted_count)

    if not changed:
        return base_text, True

    for b in blocks:
        if b.start not in changed:
            continue
        m = _BASETYPE_PREFIX.match(lines[b.basetype_line])
        leading_ws = m.group(1) if m else ""
        op = " ==" if (m and m.group(2)) else ""
        names_text = " ".join(f'"{n}"' for n in sorted(block_names[b.start]))
        lines[b.basetype_line] = f"{leading_ws}BaseType{op} {names_text}"

    return "\n".join(lines), True


def _quote_list(names: list) -> str:
    return " ".join(f'"{n}"' for n in sorted(names))


def _resolve_divine_chaos(data: dict) -> Optional[float]:
    """Divine Orb's own chaos_value from this snapshot — the reference point
    for min_divine_pct tiering (tier_of). None if Divine Orb isn't in this
    snapshot's currency[] at all or reports a non-positive value, so callers
    fall back to each tier's absolute min_chaos instead of dividing by zero/
    a meaningless reference."""
    for entry in data.get("currency", []):
        if (entry.get("name") or "").strip() != "Divine Orb":
            continue
        try:
            value = float(entry.get("chaos_value") or 0.0)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None
    return None


def _resolve_divine_chaos_for_tiering(data: dict, rules: dict) -> Optional[float]:
    """_resolve_divine_chaos's raw value, downgraded to None (forcing
    tier_of()'s absolute min_chaos fallback for every tier) when the
    snapshot's Divine Orb price is below rules["divine_sanity_floor"] — see
    that field's docstring in _DEFAULT_RULES for the live incident this
    guards against. Logs once per call so a dead-economy generate run always
    leaves a trace of why %-of-Divine tiering was skipped."""
    divine_chaos = _resolve_divine_chaos(data)
    if divine_chaos is None:
        return None
    floor = rules.get("divine_sanity_floor", _DEFAULT_RULES["divine_sanity_floor"])
    if divine_chaos < floor:
        log.warning(
            "Dead/anomalous economy snapshot detected: Divine Orb = %.2fc is below the sanity "
            "floor (%.2fc) — %%-of-Divine tiering disabled for this generate run, falling back "
            "to absolute min_chaos thresholds instead", divine_chaos, floor)
        return None
    return divine_chaos


def tier_of(chaos: float, tiers_cfg: list, divine_chaos: Optional[float] = None) -> Optional[dict]:
    """First tier (in tiers_cfg order, i.e. highest first) `chaos` qualifies
    for. Prefers each tier's min_divine_pct * divine_chaos (self-scaling
    with the league's current economy — see _DEFAULT_RULES) when
    divine_chaos is known and the tier defines a pct; falls back to that
    tier's absolute min_chaos otherwise (no Divine Orb price this snapshot,
    or a rules override that only sets min_chaos)."""
    for t in tiers_cfg:
        threshold = None
        pct = t.get("min_divine_pct")
        if pct is not None and divine_chaos:
            threshold = pct * divine_chaos
        if threshold is None:
            threshold = t.get("min_chaos")
        if threshold is not None and chaos >= threshold:
            return t
    return None


def _apply_max_count(bucketed: dict, chaos_by_name: dict, tiers_cfg: list) -> dict:
    """Enforces each tier's optional max_count (top-N by chaos value,
    highest tier first) — see _DEFAULT_RULES for why this exists. A tier
    without max_count (None) is left as-is. Overflow from one tier cascades
    into the next tier's own pool *before* that tier's own max_count is
    applied, so a chain of small caps still resolves in one pass; overflow
    from the lowest tier (nowhere further down to go) is kept there rather
    than dropped."""
    result: dict = {}
    carry: list = []
    for t in tiers_cfg:
        name = t["name"]
        pool = list(bucketed.get(name, [])) + carry
        carry = []
        if not pool:
            continue
        max_count = t.get("max_count")
        if max_count and len(pool) > max_count:
            pool.sort(key=lambda n: -chaos_by_name.get(n, 0.0))
            result[name] = pool[:max_count]
            carry = pool[max_count:]
        else:
            result[name] = pool
    if carry and tiers_cfg:
        lowest = tiers_cfg[-1]["name"]
        result.setdefault(lowest, [])
        result[lowest].extend(carry)
    return result


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------

def bucket_currency(data: dict, rules: dict) -> dict:
    """{tier_name: [BaseType, ...]} — every entry in currency[] regardless of
    `category` (see module docstring for why the hub's category taxonomy
    isn't hardcoded here), except EXCLUDE_CATEGORIES. Multiple sources
    reporting the same name are deduped by max chaos_value.

    A name that doesn't clearly qualify for any tier (tier_of() returns None)
    is simply absent from the result — not merged, not dimmed, not bucketed
    into a fallback tier. It's left 100% as-is wherever NeverSink's own base
    filter already has it. Currency below the lowest tier's threshold used to
    fall into a self-generated "dim" block (pre-2026-07-27); that block was
    written into generated_section *before* base_text, so on a snapshot
    where cheap/dead-economy prices pushed even ordinary top-shelf currency
    (Chaos Orb itself, in the incident that prompted this) below the dim
    cutoff, our own dim styling silently overrode NeverSink's real,
    prominent block for it. Currency tiering is additive-only now: we only
    ever tell NeverSink's base filter to make something *more* prominent
    (merge_currency_into_base), never less — see that function's
    never-demote guard for the other half of this fix."""
    tiers_cfg = rules.get("tiers", _DEFAULT_RULES["tiers"])
    divine_chaos = _resolve_divine_chaos_for_tiering(data, rules)

    seen: dict[str, float] = {}
    for entry in data.get("currency", []):
        if entry.get("category") in EXCLUDE_CATEGORIES:
            continue
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        chaos = float(entry.get("chaos_value") or 0.0)
        if name not in seen or chaos > seen[name]:
            seen[name] = chaos

    tiers: dict[str, list] = {}
    for name, chaos in seen.items():
        t = tier_of(chaos, tiers_cfg, divine_chaos)
        if t:
            tiers.setdefault(t["name"], []).append(name)
    return _apply_max_count(tiers, seen, tiers_cfg)


def bucket_uniques(data: dict, rules: dict) -> dict:
    """{tier_name: [base_type, ...]} keyed by hub's `base` field, max
    chaos_value per basetype (a basetype can host several uniques). Only
    items[] categories starting with "Unique" — poe1's items[] also carries
    non-unique SkillGem/ClusterJewel/BaseType/Map pricing (thousands of
    entries) that's out of scope for this generator."""
    tiers_cfg = rules.get("tiers", _DEFAULT_RULES["tiers"])
    divine_chaos = _resolve_divine_chaos_for_tiering(data, rules)

    bases: dict[str, float] = {}
    for entry in data.get("items", []):
        category = entry.get("category") or ""
        if not category.startswith("Unique"):
            continue
        base = (entry.get("base") or "").strip()
        if not base:
            continue
        chaos = float(entry.get("chaos_value") or 0.0)
        if base not in bases or chaos > bases[base]:
            bases[base] = chaos

    tiers: dict[str, list] = {}
    for base, chaos in bases.items():
        t = tier_of(chaos, tiers_cfg, divine_chaos)
        if t:
            tiers.setdefault(t["name"], []).append(base)
    return _apply_max_count(tiers, bases, tiers_cfg)


# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------

_STYLE_KEYWORDS = (
    "SetBorderColor", "SetTextColor", "SetBackgroundColor", "SetFontSize",
    "PlayAlertSound", "CustomAlertSound", "CustomAlertSoundOptional", "PlayEffect",
    "MinimapIcon",
)


def _block_style_lines(lines: list, block: "_Block") -> list:
    """Style/action lines only (see _STYLE_KEYWORDS) from inside `block`,
    verbatim except re-indented to 4 spaces — the raw material
    resolve_real_styles rips out of a real NeverSink block."""
    out = []
    for line in lines[block.start + 1:block.end]:
        stripped = line.strip()
        if not stripped:
            continue
        first_token = stripped.split(None, 1)[0]
        if first_token in _STYLE_KEYWORDS:
            out.append(f"    {stripped}")
    return out


def resolve_real_styles(base_text: Optional[str], anchors: dict) -> dict:
    """{tier_name: [style_line, ...]} ripped verbatim (full color set + font
    size + beam + minimap icon + sound) from each tier's real anchor block in
    the loaded NeverSink filter — same anchor resolution as
    merge_currency_into_base/apply_base_filter_sounds, so "tier X's real
    look" always means the same block everywhere.

    Added after the 2026-07-25 diagnostic (history.md) found our own
    hardcoded per-tier colors/background/beam/icon only matched NeverSink's
    real block by coincidence for tier S — A/B/C were wrong on nearly every
    axis. Used by emit_unique_section, which (unlike currency) still has to
    be self-generated rather than surgically merged, since hub's
    unique-by-basetype-ceiling bucketing isn't granular enough to relocate
    exact NeverSink unique-name blocks the way merge_currency_into_base does
    for currency.

    Per-tier, not all-or-nothing: a tier whose anchor doesn't resolve is
    just absent from the result, so callers fall back to their own hardcoded
    style for that tier alone (unlike merge_currency_into_base, there's no
    single in-place edit that would be left half-applied)."""
    if not base_text:
        return {}
    lines = base_text.split("\n")
    blocks = _parse_blocks(lines)
    styles: dict = {}
    for tier_name, candidates in (anchors or {}).items():
        resolved = _resolve_anchor(blocks, lines, candidates)
        if resolved is None:
            continue
        block, _name = resolved
        style_lines = _block_style_lines(lines, block)
        if style_lines:
            styles[tier_name] = style_lines
    return styles


def _style_lines(tier_cfg: dict, sound_map: Optional[dict]) -> list:
    """Last-resort hardcoded style — only reached when resolve_real_styles
    couldn't rip a real block for this tier (no base filter loaded at all,
    or this particular anchor didn't resolve)."""
    lines = [
        f"    SetBorderColor {tier_cfg['border']}",
        f"    SetTextColor {tier_cfg['text']}",
        f"    SetBackgroundColor {tier_cfg['bg']}",
        f"    SetFontSize {tier_cfg['size']}",
    ]
    name = tier_cfg["name"]
    custom = (sound_map or {}).get(name) if name in ("S", "A", "B") else None
    if custom:
        volume = tier_cfg.get("sound_volume") or _DEFAULT_RULES["sound_volume"]
        lines.append(f'    CustomAlertSoundOptional "{custom}" {volume}')
    else:
        default_sound = tier_cfg.get("sound")
        if isinstance(default_sound, dict):
            # inherited from the NeverSink base filter via apply_base_filter_sounds
            lines.append(f"    {default_sound['kind']} {default_sound['raw']}")
        elif default_sound:
            lines.append(f"    PlayAlertSound {default_sound}")
    if tier_cfg.get("beam"):
        lines.append(f"    PlayEffect {tier_cfg['beam']}")
    if tier_cfg.get("icon"):
        lines.append(f"    MinimapIcon {tier_cfg['icon']}")
    return lines


def _override_sound(style_lines: list, tier_name: str, sound_map: Optional[dict],
                     rules: dict) -> list:
    """Adds the user's own sound (Filter Generator UI, S/A/B only) to
    `style_lines`, uniformly whether the style came from a real ripped block or
    the hardcoded fallback.

    Written as CustomAlertSoundOptional, not CustomAlertSound: with a missing
    file the game refuses to load the whole filter for the plain form ("Invalid
    sound filepath", verified in PoE1 + PoE2), while the Optional form is
    skipped. The block's own PlayAlertSound stays as the fallback sound — it
    plays when the custom file is absent and is overridden when it is present.
    Any CustomAlertSound[Optional] line already in the style is replaced."""
    custom = (sound_map or {}).get(tier_name) if tier_name in ("S", "A", "B") else None
    if not custom:
        return style_lines
    volume = rules.get("sound_volume", _DEFAULT_RULES["sound_volume"])
    filtered = [l for l in style_lines
                if not l.strip().split(None, 1)[0] in ("CustomAlertSound", "CustomAlertSoundOptional")]
    filtered.append(f'    CustomAlertSoundOptional "{custom}" {volume}')
    return filtered


def _tier_style(tier_cfg: dict, real_styles: dict, sound_map: Optional[dict],
                 rules: dict) -> list:
    name = tier_cfg["name"]
    style = real_styles.get(name)
    if style is None:
        style = _style_lines(tier_cfg, None)  # sound override applied uniformly below
    return _override_sound(style, name, sound_map, rules)


def emit_unique_section(tiers: dict, rules: dict, real_styles: Optional[dict] = None,
                        sound_map: Optional[dict] = None) -> list:
    """Uniques by basetype-ceiling — still self-generated (see
    resolve_real_styles docstring for why this can't be surgically merged
    like currency), styled after the matching tier's real currency block.

    No more blanket "Unique fallback" block for untiered bases: that
    unconditional `Rarity == Unique` (no BaseType) rule used to sit ahead of
    base_text and intercept *every* unique in the game before NeverSink's
    own real per-item rules (T1/T2 named lists, TwiceCorrupted/
    HasVaalUniqueMod special beams, etc. — all real, all verified live) ever
    ran, since generated_section is written before base_text and PoE
    filters are first-match-wins (see 2026-07-25 diagnostic in history.md).
    Bases we don't have price-tier info for are simply left to NeverSink's
    own filter, same principle as currency: only override where we actually
    have better information."""
    tiers_cfg = rules.get("tiers", _DEFAULT_RULES["tiers"])
    real_styles = real_styles or {}
    out = ["# ===== Uniques by basetype ceiling (generated) ====="]
    # exclude the lowest tier — spec: only S/A/B get a dedicated unique tier.
    for tier_cfg in tiers_cfg[:-1]:
        names = tiers.get(tier_cfg["name"])
        if not names:
            continue
        out.append(f"Show # Unique potential tier {tier_cfg['name']}")
        out.append("    Rarity == Unique")
        out.append(f"    BaseType == {_quote_list(names)}")
        out.extend(_tier_style(tier_cfg, real_styles, sound_map, rules))
        out.append("")
    return out


def build_filter(hub_data: dict, rules: dict, base_text: Optional[str],
                  sound_map: Optional[dict] = None) -> tuple:
    """Top-level Generate-run orchestrator. Currency tiers are *only* ever
    applied by relocating BaseTypes directly into the loaded NeverSink base
    filter (merge_currency_into_base) — there is no fallback that emits our
    own currency Show blocks any more (Plan B, in full: see 2026-07-25 entry
    in history.md). If an anchor can't be resolved, currency BaseTypes are
    simply left wherever they already are in the base filter and a warning
    is logged; no generated currency styling is emitted in that case either
    — a half-generated-half-real currency section would be worse than
    leaving it alone entirely.

    Uniques are still self-generated (hub's unique bucketing isn't granular
    enough to relocate real NeverSink unique blocks the way currency's can),
    but now styled from real ripped NeverSink blocks (resolve_real_styles)
    instead of hardcoded guesses, and with no unconditional catch-all left to
    shadow NeverSink's own rules. There is no self-generated low-value/dim
    section any more either — see bucket_currency's docstring for why: a
    generated block (always written before base_text) that dims currency
    based on price risked overriding NeverSink's own prominent placement for
    that same BaseType whenever the price data was misleadingly low.

    Returns (generated_section, merged_base_text, currency_surgery_applied,
    anchor_status). merged_base_text equals base_text unchanged whenever
    surgery wasn't applied (including when base_text is None).
    anchor_status is resolve_anchors' {tier_name: resolved_anchor_or_None} —
    per-tier detail for a caller's status message, since
    currency_surgery_applied alone can't distinguish "every tier resolved"
    from "only some did" (see merge_currency_into_base's per-tier skip,
    2026-08-08)."""
    tiers = bucket_currency(hub_data, rules)
    uniq_tiers = bucket_uniques(hub_data, rules)

    anchors = rules.get("anchors", _DEFAULT_RULES["anchors"])
    merged_base_text = base_text
    applied = False
    real_styles: dict = {}
    anchor_status = resolve_anchors(base_text, anchors)
    if base_text:
        real_styles = resolve_real_styles(base_text, anchors)
        merged_base_text, applied = merge_currency_into_base(base_text, tiers, rules, anchors)

    lines = ["# Generated by PoE Price & Trade Checker (Filter Generator) from poe-data-hub snapshot", ""]
    lines += emit_unique_section(uniq_tiers, rules, real_styles, sound_map)
    return "\n".join(lines), merged_base_text, applied, anchor_status


# ---------------------------------------------------------------------------
# Staleness / change detection
# ---------------------------------------------------------------------------

def is_stale(hub_data: dict, staleness_hours: float) -> bool:
    """Compares the hub's own generated_at (true snapshot age), not our local
    fetch time — a snapshot the hub itself hasn't refreshed in a while must
    not be used to generate/regenerate the filter, per spec."""
    ts = hub_data.get("generated_at")
    if not ts:
        return True
    try:
        gen = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return True
    age_hours = (datetime.now(timezone.utc) - gen).total_seconds() / 3600.0
    return age_hours > staleness_hours


def tier_mapping(hub_data: dict, rules: dict) -> dict[str, str]:
    """{"c:"/"u:" + name: tier_name} for every currency/unique bucketed into
    a tier (currency ∪ uniques) — the raw material both signature() (hashed,
    for cheap "did anything change" checks) and diff_mapping_count() (for
    "how many things changed", used by the auto-regen notification) build
    on top of."""
    tiers = bucket_currency(hub_data, rules)
    uniq_tiers = bucket_uniques(hub_data, rules)
    mapping: dict[str, str] = {}
    for tier_name, names in tiers.items():
        for n in names:
            mapping[f"c:{n}"] = tier_name
    for tier_name, names in uniq_tiers.items():
        for n in names:
            mapping[f"u:{n}"] = tier_name
    return mapping


def signature(hub_data: dict, rules: dict) -> str:
    """sha256 of tier_mapping() — lets the auto-regen poll detect "did
    anything actually change tier" so a chaos price wobbling a percent
    doesn't retrigger a regen."""
    blob = json.dumps(tier_mapping(hub_data, rules), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def diff_mapping_count(old: dict[str, str], new: dict[str, str]) -> int:
    """Number of names whose tier differs between two tier_mapping()
    results, counting a name that only appears on one side (newly
    tiered/dropped out of a tier) as changed too. Used for the auto-regen
    notification's "N items changed tier" — deliberately not exposed via
    signature() alone, since a hash only tells you *whether* something
    changed, not how many."""
    keys = set(old) | set(new)
    return sum(1 for k in keys if old.get(k) != new.get(k))


# ---------------------------------------------------------------------------
# Whitelist ("show only") mode — standalone filter, no NeverSink involved.
# Currency comes from the "Currency" category; only Gold needs its own checkbox.
GOLD_BASETYPES = ["Gold"]   # BaseType == "Gold" (verified in NeverSink poe2 + poe1)

# Uncut gems (poe2 only) - BaseType as in the game; level gated by GemLevel >= N.
# "Uncut Spirit Gem" is the source of meta gems (no separate 4th BaseType).
WHITELIST_GEM_UNCUT = {
    "poe2": ["Uncut Skill Gem", "Uncut Support Gem", "Uncut Spirit Gem"],
    "poe1": [],
}

# Whole-category checkboxes (hub category ids).
WHITELIST_CATEGORIES = {
    "poe2": ["Currency", "Fragment", "Rune", "Essence", "SoulCore", "Omen",
             "Catalyst", "Delirium", "Verisium", "AbyssalBone", "Artifact",
             "LineageGem", "Idol"],
    "poe1": ["Currency", "Fragment", "Essence", "Fossil", "Resonator", "Oil",
             "Scarab", "Artifact", "DeliriumOrb", "DivinationCard"],
}

# Hub categories NOT offered as whole-category checkboxes (verified against live
# hub payloads): basetype / clusterjewel (poe1) are priced crafting bases and
# enchant-text names; skillgem (both) is priced per level/quality variant but a
# filter would show every copy; uncutgem (poe2) names look like
# "Uncut Spirit Gem (Level 4)" (not a BaseType); map (poe1) name format unverified.


def _iter_hub_items(hub_data: dict):
    """Yield every entry of a hub prices payload (currency[] + items[]) —
    same sections repository._entries_from_hub_payload merges."""
    for section in ("currency", "items"):
        for it in (hub_data or {}).get(section, []) or []:
            if isinstance(it, dict):
                yield it


def names_in_categories(hub_data: dict, categories) -> list[str]:
    """Every entry name (= BaseType) in the chosen hub categories, regardless
    of price (show the whole category)."""
    want = {str(c).lower() for c in (categories or [])}
    out = []
    for it in _iter_hub_items(hub_data):
        name = (it.get("name") or "").strip()
        if name and str(it.get("category") or "").lower() in want:
            out.append(name)
    return out


def expand_categories(hub_data: dict, categories, exclude: Optional[dict] = None) -> list[str]:
    """names_in_categories per category minus that category's exclude list
    (exclude = {"Rune": ["Adept Rune", ...]}; a category with no key is shown whole)."""
    exclude = exclude or {}
    out: list[str] = []
    for cat in categories or []:
        skip = set(exclude.get(cat, []))
        out += [n for n in names_in_categories(hub_data, [cat]) if n not in skip]
    return out


_RARITY_ORDER = ["Normal", "Magic", "Rare", "Unique"]


def _normalize_custom(contains_names):
    """Accepts list[str] (pre-0.8.2 = any rarity) and list[{name, rarities}].
    Returns [(name, tuple(rarities in canonical order))]. Empty/invalid
    rarities fall back to every rarity so a name never silently vanishes."""
    out = []
    for e in (contains_names or []):
        if isinstance(e, str):
            nm, rar = e.strip(), tuple(_RARITY_ORDER)
        elif isinstance(e, dict):
            nm = str(e.get("name", "")).strip()
            rs = [r for r in _RARITY_ORDER if r in set(e.get("rarities") or [])]
            rar = tuple(rs) if rs else tuple(_RARITY_ORDER)
        else:
            continue
        if nm:
            out.append((nm, rar))
    return out


def build_whitelist_section(exact_basetypes, unique_bases=None, contains_names=None,
                            gem_uncut=None, gold=False, gold_min=0,
                            unique_all=False) -> str:
    """Show exact BaseTypes + Show typed names (BaseType without `==` =
    substring match, any rarity) + Show unique bases (+ Rarity Unique) + Hide
    catch-all. Standalone. "" when all inputs are empty - the caller must
    guard (an all-Hide filter blanks the screen)."""
    exact = sorted({b for b in (exact_basetypes or []) if b})
    uniq = sorted({b for b in (unique_bases or []) if b})
    cont = _normalize_custom(contains_names)
    gems = [(str(b), int(lv)) for b, lv in (gem_uncut or []) if b]
    if not exact and not uniq and not cont and not gems and not gold and not unique_all:
        return ""
    lines = ["# === PoE Checker - Whitelist (show only) ==="]
    if gold:
        # own block: StackSize must not constrain the other exact BaseTypes
        gold_min = max(0, int(gold_min or 0))
        lines += ["# gold" + (f" (stack >= {gold_min})" if gold_min > 0 else ""),
                  "Show",
                  f'    BaseType == "{GOLD_BASETYPES[0]}"']
        if gold_min > 0:
            lines.append(f"    StackSize >= {gold_min}")
        lines += [
            "    SetFontSize 45",
            "    SetTextColor 255 255 255 255",
            "    SetBorderColor 255 200 0 255",
            "    SetBackgroundColor 75 50 0 255",
            "    PlayAlertSound 6 300",
            "    MinimapIcon 0 Yellow Star",
            "    PlayEffect Yellow",
            "",
        ]
    if exact:
        names = " ".join(f'"{b}"' for b in exact)
        lines += [
            "Show",
            f"    BaseType == {names}",
            "    SetFontSize 45",
            "    SetTextColor 255 255 255 255",
            "    SetBorderColor 255 200 0 255",
            "    SetBackgroundColor 75 50 0 255",
            "    PlayAlertSound 6 300",
            "    MinimapIcon 0 Yellow Star",
            "    PlayEffect Yellow",
            "",
        ]
    if cont:
        # one Show block per rarity set (a block carries one BaseType + one Rarity line)
        groups = OrderedDict()
        for nm, rar in cont:
            groups.setdefault(rar, set()).add(nm)
        allset = set(_RARITY_ORDER)
        for rar, names_set in sorted(
                groups.items(), key=lambda kv: [_RARITY_ORDER.index(r) for r in kv[0]]):
            joined = " ".join(f'"{c}"' for c in sorted(names_set))
            tag = "any rarity" if set(rar) == allset else "/".join(rar)
            lines += [
                f"# typed names (contains match, {tag})",
                "Show",
                f"    BaseType {joined}",
            ]
            if set(rar) != allset:
                lines.append(f"    Rarity {' '.join(rar)}")
            lines += [
                "    SetFontSize 45",
                "    SetTextColor 0 255 255 255",
                "    SetBorderColor 0 255 255 255",
                "    SetBackgroundColor 0 50 60 255",
                "    PlayAlertSound 2 300",
                "    MinimapIcon 0 Cyan Star",
                "    PlayEffect Cyan",
                "",
            ]
    if uniq:
        names = " ".join(f'"{b}"' for b in uniq)
        lines += [
            "# uniques above the value threshold (shows every unique on these bases)",
            "Show",
            f"    BaseType == {names}",
            "    Rarity Unique",
            "    SetFontSize 45",
            "    SetTextColor 175 96 37 255",
            "    SetBorderColor 175 96 37 255",
            "    SetBackgroundColor 50 30 10 255",
            "    PlayAlertSound 3 300",
            "    MinimapIcon 0 Brown Star",
            "    PlayEffect Brown",
            "",
        ]
    for base, lvl in gems:
        lines += [
            f"# uncut gem: {base} (GemLevel >= {lvl})",
            "Show",
            f'    BaseType "{base}"',
            f"    GemLevel >= {lvl}",
            "    SetFontSize 45",
            "    SetTextColor 255 255 255 255",
            "    SetBorderColor 60 220 120 255",
            "    SetBackgroundColor 10 50 25 255",
            "    PlayAlertSound 1 300",
            "    MinimapIcon 0 Green Star",
            "    PlayEffect Green",
            "",
        ]
    if unique_all:
        lines += [
            "# all uniques",
            "Show",
            "    Rarity Unique",
            "    SetFontSize 45",
            "    SetTextColor 175 96 37 255",
            "    SetBorderColor 175 96 37 255",
            "    SetBackgroundColor 50 30 10 255",
            "    PlayAlertSound 3 300",
            "    MinimapIcon 0 Brown Star",
            "    PlayEffect Brown",
            "",
        ]
    lines += ["# hide everything else", "Hide", ""]
    return "\n".join(lines)
