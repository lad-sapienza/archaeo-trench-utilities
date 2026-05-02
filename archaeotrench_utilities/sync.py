"""Style synchronisation logic for ArchaeoTrench Utilities.

Copies the styles/ directory from the template into each trench folder,
then updates _meta.template_version in the GeoPackage.

This replaces the old approach of swapping embedded .db files inside QGZ archives.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from .styles import template_styles_dir

STATUS_UPDATED = "updated"
STATUS_SKIPPED = "skipped"
STATUS_ERROR   = "error"


def sync_styles(trench_dirs: list, target_version: str | None = None) -> list:
    """Sync styles for a list of trench folder paths.

    Args:
        trench_dirs: list of Path | str pointing to trench root folders
                     (each must contain a vectors.gpkg with a _meta table).
        target_version: version string to write to _meta after sync
                        (defaults to changelog current_version).

    Returns:
        List of dicts: {trench_dir, status, error, from_version, to_version}
    """
    plugin_dir = Path(__file__).parent
    changelog = _load_changelog(plugin_dir)
    resolved_target = target_version or changelog["current_version"]

    results = []
    for raw in trench_dirs:
        trench_dir = Path(raw)
        entry = {
            "trench_dir":   trench_dir,
            "status":       STATUS_ERROR,
            "error":        None,
            "from_version": None,
            "to_version":   resolved_target,
        }
        try:
            gpkg = _find_gpkg(trench_dir)
            project_type, current_ver = _read_meta(gpkg)
            entry["from_version"] = current_ver

            src_styles = template_styles_dir(project_type)
            if not src_styles.is_dir():
                raise FileNotFoundError(f"Template styles not found: {src_styles}")

            dest_styles = trench_dir / "styles"
            if dest_styles.exists():
                shutil.rmtree(dest_styles)
            shutil.copytree(src_styles, dest_styles)

            _update_meta_version(gpkg, resolved_target)
            entry["status"] = STATUS_UPDATED
        except Exception as exc:
            entry["error"] = str(exc)
        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_gpkg(trench_dir: Path) -> Path:
    gpkg = trench_dir / "vectors.gpkg"
    if gpkg.exists():
        return gpkg
    # Fallback: first .gpkg found
    candidates = list(trench_dir.glob("*.gpkg"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"No GeoPackage found in {trench_dir}")


def _read_meta(gpkg: Path) -> tuple:
    """Return (project_type, template_version) from _meta table."""
    con = sqlite3.connect(gpkg)
    try:
        cur = con.cursor()
        cur.execute("SELECT key, value FROM _meta WHERE key IN ('project_type','template_version')")
        rows = dict(cur.fetchall())
    finally:
        con.close()
    return rows.get("project_type", "plan"), rows.get("template_version", "1.0")


def _update_meta_version(gpkg: Path, version: str):
    con = sqlite3.connect(gpkg)
    try:
        con.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES ('template_version', ?)",
            (version,)
        )
        con.commit()
    finally:
        con.close()


def _load_changelog(plugin_dir: Path) -> dict:
    import json
    with open(plugin_dir / "template" / "changelog.json", encoding="utf-8") as f:
        return json.load(f)
