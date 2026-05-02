"""Schema migration logic for ArchaeoTrench Utilities.

Applies forward-only SQL migrations from changelog.json to a trench GPKG,
creating a timestamped backup first.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path

from .version import load_changelog, versions_between, compare_versions


def get_trench_version(gpkg_path: Path | str) -> str:
    """Read template_version from _meta table."""
    con = sqlite3.connect(Path(gpkg_path))
    try:
        cur = con.cursor()
        cur.execute("SELECT value FROM _meta WHERE key='template_version'")
        row = cur.fetchone()
        return row[0] if row else "1.0"
    finally:
        con.close()


def get_pending_migrations(gpkg_path: Path | str, changelog: dict | None = None) -> list:
    """Return list of changelog entries pending for this GPKG.

    Each entry is a dict from changelog['history'] with version > current.
    """
    if changelog is None:
        changelog = load_changelog(Path(__file__).parent)
    current = get_trench_version(gpkg_path)
    target = changelog["current_version"]
    return versions_between(current, target, changelog["history"])


def migrate_trench(gpkg_path: Path | str, changelog: dict | None = None) -> tuple:
    """Apply all pending migrations to a trench GPKG.

    Returns (success: bool, message: str).
    A timestamped backup is created before any changes are made.
    """
    gpkg = Path(gpkg_path)
    if changelog is None:
        changelog = load_changelog(Path(__file__).parent)

    pending = get_pending_migrations(gpkg, changelog)
    if not pending:
        return True, "Already at the latest version — nothing to migrate."

    # Collect all SQL steps across pending entries
    all_steps = []
    for entry in pending:
        for project_type in ("plan", "section"):
            changes = entry.get("changes", {}).get(project_type, {})
            for sql in changes.get("migration_sql", []):
                all_steps.append((entry["version"], sql))

    # Backup
    backup_name = f"{gpkg.stem}_backup_{date.today().isoformat()}.gpkg"
    backup_path = gpkg.with_name(backup_name)
    shutil.copy2(gpkg, backup_path)

    # Apply
    con = sqlite3.connect(gpkg)
    try:
        cur = con.cursor()
        for version, sql in all_steps:
            cur.executescript(sql)
        # Update version
        target_version = pending[-1]["version"]
        cur.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('template_version', ?)",
            (target_version,)
        )
        con.commit()
    except Exception as exc:
        con.close()
        # Restore backup on failure
        shutil.copy2(backup_path, gpkg)
        return False, f"Migration failed: {exc}\nOriginal file restored from backup."
    finally:
        con.close()

    return True, (
        f"Migrated to version {target_version}.\n"
        f"Backup saved as: {backup_name}"
    )
