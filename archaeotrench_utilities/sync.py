"""Sync a trench project from the plugin template.

Performs two operations in one pass:
  1. Schema sync  — adds any tables or columns present in schema.sql that
                    are missing from the trench GeoPackage (additive-only;
                    existing data is never removed or modified).
  2. Styles sync  — replaces the trench styles/ directory with the latest
                    QML files from the template.

After a successful sync the trench _meta.template_version is updated to
match the version recorded in the template's schema.sql header.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from . import schema as schema_mod
from .styles import template_styles_dir

STATUS_UPDATED = "updated"
STATUS_SKIPPED = "skipped"
STATUS_ERROR   = "error"


def sync_trench(trench_dirs: list) -> list:
    """Sync schema and styles for a list of trench folder paths.

    Args:
        trench_dirs: list of Path | str pointing to trench root folders
                     (each must contain a vectors.gpkg with a _meta table).

    Returns:
        List of dicts: {trench_dir, status, error, schema_changes, styles_updated, version}
    """
    results = []
    for raw in trench_dirs:
        trench_dir = Path(raw)
        entry = {
            "trench_dir":     trench_dir,
            "status":         STATUS_ERROR,
            "error":          None,
            "schema_changes": [],
            "styles_updated": False,
            "version":        None,
        }
        try:
            gpkg = _find_gpkg(trench_dir)
            project_type = _read_project_type(gpkg)

            plugin_dir = Path(__file__).parent
            template_dir = plugin_dir / "template" / "types" / project_type
            schema_path = template_dir / "schema.sql"

            if not schema_path.exists():
                raise FileNotFoundError(
                    f"Template schema not found for type '{project_type}': {schema_path}"
                )

            # --- Schema sync ---
            changes = _sync_schema(gpkg, schema_path)
            entry["schema_changes"] = changes

            # --- Styles sync ---
            src_styles = template_styles_dir(project_type)
            if src_styles.is_dir():
                dest_styles = trench_dir / "styles"
                if dest_styles.exists():
                    shutil.rmtree(dest_styles)
                shutil.copytree(src_styles, dest_styles)
                entry["styles_updated"] = True

            # --- Update version in _meta ---
            version = schema_mod.get_template_version(str(schema_path))
            if version:
                _update_meta_version(gpkg, version)
                entry["version"] = version

            entry["status"] = STATUS_UPDATED
        except Exception as exc:
            entry["error"] = str(exc)

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Schema diff and apply
# ---------------------------------------------------------------------------

def _sync_schema(gpkg_path: Path, schema_path: Path) -> list:
    """Add missing tables and columns from schema.sql to the GeoPackage.

    Returns a list of human-readable change descriptions.
    """
    layers = schema_mod.parse_schema(str(schema_path))
    changes = []

    con = sqlite3.connect(gpkg_path)
    try:
        existing_tables = {
            r[0].lower()
            for r in con.execute(
                "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
            ).fetchall()
        }
    finally:
        con.close()

    for layer_def in layers:
        name = layer_def['name']
        geom_col = layer_def.get('geometry_column', 'geom')

        if name.lower() not in existing_tables:
            # Entire table is missing — create it via QGIS API
            schema_mod.add_layer_to_gpkg(layer_def, str(gpkg_path))
            changes.append(f"Added table: {name}")
        else:
            # Table exists — check for missing columns
            con = sqlite3.connect(gpkg_path)
            try:
                existing_cols = {
                    r[1].lower()
                    for r in con.execute(f"PRAGMA table_info({name})").fetchall()
                }
                for field in layer_def.get('fields', []):
                    if field['name'].lower() not in existing_cols:
                        sql = f"ALTER TABLE {name} ADD COLUMN {field['name']} {field['sql_type']}"
                        con.execute(sql)
                        changes.append(f"{name}: added column {field['name']} {field['sql_type']}")
                con.commit()
            finally:
                con.close()

    return changes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_gpkg(trench_dir: Path) -> Path:
    gpkg = trench_dir / "vectors.gpkg"
    if gpkg.exists():
        return gpkg
    candidates = list(trench_dir.glob("*.gpkg"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"No GeoPackage found in {trench_dir}")


def _read_project_type(gpkg: Path) -> str:
    con = sqlite3.connect(gpkg)
    try:
        cur = con.cursor()
        cur.execute("SELECT value FROM _meta WHERE key='project_type'")
        row = cur.fetchone()
        return row[0] if row else "plan"
    finally:
        con.close()


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
