"""Version parsing and comparison utilities for ArchaeoTrench Utilities."""

from __future__ import annotations


def parse_version(v: str) -> tuple:
    """Parse 'MAJOR.MINOR' string into (int, int) tuple."""
    parts = str(v).split(".")
    return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def compare_versions(v1: str, v2: str) -> int:
    """Return -1 if v1 < v2, 0 if equal, 1 if v1 > v2."""
    a, b = parse_version(v1), parse_version(v2)
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def is_major_bump(from_v: str, to_v: str) -> bool:
    return parse_version(to_v)[0] > parse_version(from_v)[0]


def versions_between(from_v: str, to_v: str, history: list) -> list:
    """Return ordered changelog entries strictly after from_v up to and including to_v.

    Only forward migrations are supported (from_v < to_v).
    Each returned entry is a dict from changelog['history'].
    """
    if compare_versions(from_v, to_v) >= 0:
        return []
    result = []
    for entry in sorted(history, key=lambda e: parse_version(e["version"])):
        ev = entry["version"]
        if compare_versions(ev, from_v) > 0 and compare_versions(ev, to_v) <= 0:
            result.append(entry)
    return result


def load_changelog(plugin_dir) -> dict:
    """Load and return the changelog.json from the template directory."""
    import json
    from pathlib import Path
    path = Path(plugin_dir) / "template" / "changelog.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)
