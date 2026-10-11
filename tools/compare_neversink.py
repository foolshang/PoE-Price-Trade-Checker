"""Compare what NeverSink strictness 2 shows with what the untouched Whitelist tab shows, item by item.

    python tools/compare_neversink.py poe1|poe2 [--stacks 1,3,20] [--area 70] [--list N]

A small first-match evaluator runs the same synthetic items (every name of the whitelist's universe, as the
class NeverSink files it under, at several stack sizes) through both filters and lists the names whose
Show / Hide answer differs. Only the conditions that matter for such items are evaluated (BaseType, Class,
Rarity, StackSize, AreaLevel, ItemLevel, Quality, DropLevel, GemLevel, MapTier / WaystoneTier); a block with
any other condition is treated as not matching for BOTH filters, so the comparison stays fair. Uses the test
fixtures (tests/sample_data) - no network.
"""
from __future__ import annotations
import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from poe_price_trade import filter_gen, filter_whitelist as w          # noqa: E402
from poe_price_trade.wl_model import WlModel                             # noqa: E402

SAMPLE = ROOT / "tests" / "sample_data"
RARITY = ["Normal", "Magic", "Rare", "Unique"]
_OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b, ">": lambda a, b: a > b,
        "==": lambda a, b: a == b, "=": lambda a, b: a == b}
_KNOWN = {"BaseType", "Class", "Rarity", "StackSize", "AreaLevel", "ItemLevel", "Quality", "DropLevel", "GemLevel",
          "MapTier", "WaystoneTier"}
_NOT_COND = w._STYLE_TOKENS | {"DisableDropSound", "CustomAlertSound", "CustomAlertSoundOptional", "Continue",
                               "SetFontSize"}


def parse_blocks(text: str) -> list:
    """[(Show|Hide, [(keyword, op, [values])], has_continue)] in file order."""
    out = []
    cur = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip() if not raw.lstrip().startswith(("Show", "Hide")) else raw.split("#", 1)[0].strip()
        if not line:
            continue
        kw = line.split(None, 1)[0]
        if kw in ("Show", "Hide"):
            cur = [kw, [], False]
            out.append(cur)
            continue
        if cur is None:
            continue
        if kw == "Continue":
            cur[2] = True
            continue
        if kw in _NOT_COND:
            continue
        rest = line[len(kw):].strip()
        op = None
        m = re.match(r"^(==|>=|<=|<|>|=)\s*(.*)$", rest)
        if m:
            op, rest = m.group(1), m.group(2)
        vals = re.findall(r'"([^"]*)"', rest) or rest.split()
        cur[1].append((kw, op, vals, rest.startswith('"') or '"' in rest))
    return [(b[0], b[1], b[2]) for b in out]


def matches(conds: list, item: dict) -> bool:
    for kw, op, vals, _q in conds:
        if kw not in _KNOWN:
            return False
        if kw == "BaseType":
            if op in ("==", "="):
                ok = item["base"] in vals
            else:
                ok = any(v.lower() in item["base"].lower() for v in vals)
        elif kw == "Class":
            ok = item["cls"] in vals if op in ("==", "=") else any(v.lower() in item["cls"].lower() for v in vals)
        elif kw == "Rarity":
            if op in _OPS and vals:
                ok = _OPS[op](RARITY.index(item["rarity"]), RARITY.index(vals[0]))
            else:
                ok = item["rarity"] in vals
        else:
            key = {"StackSize": "stack", "AreaLevel": "area", "ItemLevel": "ilvl", "Quality": "quality",
                   "DropLevel": "drop", "GemLevel": "gem", "MapTier": "maptier", "WaystoneTier": "maptier"}[kw]
            try:
                ok = _OPS[op or "=="](item.get(key, 0), int(vals[0]))
            except (KeyError, ValueError, IndexError):
                return False
        if not ok:
            return False
    return True


def visible(blocks: list, item: dict) -> tuple:
    """(shown, block index) of the first block that decides the item (no match = the game shows it)."""
    for i, (kind, conds, cont) in enumerate(blocks):
        if cont:
            continue
        if matches(conds, item):
            return kind == "Show", i
    return True, -1


def load(game: str) -> tuple:
    base = (SAMPLE / f"neversink_{game}_s2.filter").read_text(encoding="utf-8")
    with gzip.open(SAMPLE / f"hub_{game}.json.gz", "rt", encoding="utf-8") as fh:
        hub = {"currency": [], "items": json.load(fh)["items"]}
    with gzip.open(SAMPLE / f"trade_names_{game}.json.gz", "rt", encoding="utf-8") as fh:
        extra = set(json.load(fh))
    return hub, base, extra


def name_classes(base_text: str) -> dict:
    """{name: first Class of a NeverSink block listing it} (what the item really is)."""
    lines, blocks = w.scan(base_text)
    out: dict = {}
    for b in blocks:
        names = w.exact_names(lines, b)
        if not names:
            continue
        cls = [c for l in lines[b.start + 1:b.end] if re.match(r"\s*Class", l) for c in re.findall(r'"([^"]*)"', l)]
        if cls:
            for n in names:
                out.setdefault(n, cls[0])
    return out


# (name, class) of items that are in no list: NeverSink's catch-all ("restex") blocks decide them
PROBES = {"poe1": [("Runegraft of Zzz Not Yet Listed", "Stackable Currency"), ("Vial of Zzz Not Yet Listed", "Stackable Currency"),
                   ("Zzz Not Yet Listed", "Corpses"), ("Zzz Not Yet Listed Wombgift", "Wombgifts")],
          "poe2": []}


def compare(game: str, stacks=(1, 3, 20), area: int = 70, model: WlModel = None) -> dict:
    hub, base, extra = load(game)
    m = model or WlModel(game)
    m.set_data(hub, base, extra)
    ns = parse_blocks(base)
    wl = parse_blocks(m.build()["text"])
    classes = name_classes(base)
    universe = w.universe(game, hub, base)
    diffs = collections.defaultdict(list)
    total = same = 0
    for name, cat in sorted(universe.items()):
        cls = classes.get(name) or "Stackable Currency"
        if w.is_tablet(game, name):
            cls = "Tablet"
        elif cat == "Relic":
            cls = "Relics"
        for stack in stacks:
            item = {"base": name, "cls": cls, "rarity": "Normal", "stack": stack, "area": area, "ilvl": 80,
                    "quality": 0, "drop": 80, "gem": 1}
            a, ia = visible(ns, item)
            b, ib = visible(wl, item)
            total += 1
            if a == b:
                same += 1
            else:
                diffs[(cat, "NeverSink shows" if a else "NeverSink hides")].append((name, stack))
    for name, cls in PROBES.get(game, []):          # names no list has: only a class / fragment rule can show them
        item = {"base": name, "cls": cls, "rarity": "Normal", "stack": 1, "area": 70, "ilvl": 80, "quality": 0,
                "drop": 80, "gem": 1}
        a, b = visible(ns, item)[0], visible(wl, item)[0]
        total += 1
        if a == b:
            same += 1
        else:
            diffs[("probe", "NeverSink shows" if a else "NeverSink hides")].append((name, 1))
    return {"total": total, "same": same, "diffs": diffs}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("game", choices=["poe1", "poe2"])
    ap.add_argument("--stacks", default="1,3,20")
    ap.add_argument("--area", type=int, default=70)
    ap.add_argument("--list", type=int, default=6)
    a = ap.parse_args()
    res = compare(a.game, tuple(int(x) for x in a.stacks.split(",")), a.area)
    print(f"{a.game}: {res['same']}/{res['total']} (name, stack) answers equal")
    for (cat, kind), items in sorted(res["diffs"].items()):
        names = sorted({n for n, _s in items})
        print(f"  {cat:15s} {kind:16s} {len(names):4d} names  e.g. {names[:a.list]}")


if __name__ == "__main__":
    main()
