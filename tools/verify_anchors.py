#!/usr/bin/env python3
"""verify_anchors.py — regression check for filter_gen.py's currency anchor
candidates (_DEFAULT_RULES["anchors"]) against every real NeverSink base
filter: 2 games x 7 strictness levels (0-6) = 14 files.

Added 2026-08-08 after a second anchor-resolution incident (switching PoE1
to strictness 3 broke tier C's anchor again, the same failure mode as the
2026-07-27 "Orb of Augmentation" incident, just at a different strictness).
A single anchor name per tier is fundamentally fragile across this many real
files — this script is the guardrail: run it whenever _DEFAULT_RULES
["anchors"] changes, or after a NeverSink release bump, to catch a broken
candidate list before a user does.

Uses the app's own fetch/cache path (neversink_source.fetch_base_filter) and
its own resolution logic (filter_gen.resolve_anchors) — never reimplements
either, so this script can't silently drift from what the app actually does.

Usage:
    python tools/verify_anchors.py                # use/populate the app's real cache
    python tools/verify_anchors.py --force         # bypass the 24h re-check throttle
    python tools/verify_anchors.py --cache-dir DIR # use a scratch cache instead

Exit code 0 iff every tier resolves on every one of the 14 files; non-zero
otherwise, with the full per-file/per-tier matrix always printed first (never
reports success from a partial run — see CLAUDE.md-adjacent incident where a
previous anchor fix was verified against a single cached file only)."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from poe_price_trade import filter_gen, neversink_source  # noqa: E402

STRICTNESS_LEVELS = range(len(neversink_source.LEVELS))  # 0-6


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", type=Path, default=None,
                     help="Cache dir to use (default: the real app cache dir)")
    ap.add_argument("--force", action="store_true",
                     help="Bypass the 24h GitHub release re-check throttle")
    args = ap.parse_args()

    if args.cache_dir is not None:
        cache_dir = args.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
    else:
        from poe_price_trade import config
        cache_dir = config.AppConfig().app_dir() / "cache"

    anchors = filter_gen._DEFAULT_RULES["anchors"]
    tier_names = list(anchors.keys())

    header = f"{'file':32s} " + " ".join(f"{t:>22s}" for t in tier_names)
    print(header)
    print("-" * len(header))

    failures: list[str] = []
    fetch_failures: list[str] = []
    checked = 0

    for game in ("poe1", "poe2"):
        for strictness in STRICTNESS_LEVELS:
            label = f"{game} {neversink_source.LEVELS[strictness]} ({strictness})"
            base_text, tag = neversink_source.fetch_base_filter(
                game, strictness, cache_dir, force=args.force)
            if base_text is None:
                print(f"{label:32s} FETCH FAILED (no cache, no network)")
                fetch_failures.append(label)
                continue

            checked += 1
            status = filter_gen.resolve_anchors(base_text, anchors)
            row = []
            for t in tier_names:
                resolved = status.get(t)
                cell = resolved if resolved else "UNRESOLVED"
                row.append(f"{cell:>22.22s}")
                if not resolved:
                    failures.append(f"{label} tier {t}: none of {anchors[t]!r} resolved")
            print(f"{label:32s} " + " ".join(row) + f"   (tag={tag})")

    print("-" * len(header))
    print(f"{checked} file(s) checked, {len(failures)} tier-resolution failure(s), "
          f"{len(fetch_failures)} fetch failure(s)")

    if fetch_failures:
        print("\nFETCH FAILURES (could not verify these at all):")
        for f in fetch_failures:
            print(f"  - {f}")

    if failures:
        print("\nANCHOR RESOLUTION FAILURES:")
        for f in failures:
            print(f"  - {f}")

    if checked < 14:
        print(f"\nFAIL: only {checked}/14 files were actually checked — "
              "fix fetch failures before trusting this run.")
        return 1
    if failures:
        print("\nFAIL: not every tier resolved on every file.")
        return 1
    print("\nOK: every tier resolved on all 14 real NeverSink files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
