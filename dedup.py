#!/usr/bin/env python3
"""
dedup.py — Automated duplicate mover for /Volumes/toshiba

Runs jdupes to find duplicates, keeps the first copy in each group,
and moves all others to /Volumes/toshiba/_deleted/ for later review.

Usage:
    python dedup.py --dry-run   # preview what would be moved
    python dedup.py             # move duplicates to _deleted/
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DRIVE_PATH = Path("/Volumes/toshiba")
DELETED_PATH = DRIVE_PATH / "_deleted"

# Directories jdupes should skip
SKIP_DIRS = ["_deleted", "_Organized"]


def run_jdupes() -> str:
    skip_args = []
    for d in SKIP_DIRS:
        skip_args += ["-X", f"nostr:/{d}/"]

    print("Running jdupes — scanning drive (progress below)...")
    # stderr=None lets jdupes print its own scanning progress to the terminal
    proc = subprocess.Popen(
        ["jdupes", "-r"] + skip_args + [str(DRIVE_PATH)],
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
    )

    stdout, _ = proc.communicate()

    if proc.returncode not in (0, 1):
        sys.exit("jdupes failed — check the output above for details.")

    return stdout


def parse_groups(jdupes_output: str) -> list[list[Path]]:
    """Parse jdupes output into groups of duplicate paths."""
    groups = []
    current: list[Path] = []
    for line in jdupes_output.splitlines():
        line = line.strip()
        if line:
            current.append(Path(line))
        else:
            if len(current) > 1:
                groups.append(current)
            current = []
    if len(current) > 1:
        groups.append(current)
    return groups


def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    counter = 1
    while True:
        candidate = dest.parent / f"{dest.stem}_{counter}{dest.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Move duplicate files to _deleted/ for review"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be moved without touching any files",
    )
    args = parser.parse_args()

    if not DRIVE_PATH.exists():
        sys.exit(f"Error: {DRIVE_PATH} not found. Is the drive mounted?")

    raw = run_jdupes()
    groups = parse_groups(raw)

    if not groups:
        print("No duplicates found.")
        return

    total_dupes = sum(len(g) - 1 for g in groups)
    print(f"Found {len(groups)} duplicate groups, {total_dupes} files to move.\n")

    if args.dry_run:
        print("DRY RUN — no files will be moved\n")
    else:
        DELETED_PATH.mkdir(exist_ok=True)

    moved = errors = 0

    for i, group in enumerate(groups, 1):
        keeper = group[0]
        duplicates = group[1:]

        if args.dry_run:
            print(f"[keep]  {keeper}")
            for dup in duplicates:
                dest = DELETED_PATH / dup.name
                print(f"[move]  {dup}")
                print(f"     -> {unique_dest(dest)}")
            print()
        else:
            for dup in duplicates:
                dest = unique_dest(DELETED_PATH / dup.name)
                try:
                    shutil.move(str(dup), str(dest))
                    moved += 1
                except Exception as e:
                    print(f"ERROR moving {dup}: {e}")
                    errors += 1

            if i % 500 == 0:
                print(f"  Progress: {i}/{len(groups)} groups processed...")

    if args.dry_run:
        print(f"Would move {total_dupes} files to {DELETED_PATH}")
    else:
        print(f"\nDone. Moved: {moved} files | Errors: {errors}")
        print(f"Duplicates are in: {DELETED_PATH}")
        print("Review that folder, then delete it when satisfied.")


if __name__ == "__main__":
    main()
