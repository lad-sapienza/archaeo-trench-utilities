"""Export GeoPackage schema and layer styles from the active QGIS project
back to the plugin template folder.

Mirrors the layer-level sync logic in sync.py but in the opposite direction:
  inspect_project_for_export() — shows per-layer what would be written
  export_layers()              — writes schema.sql + selected QML files

Schema export is always full (schema.sql describes all tables); the per-layer
checkboxes in the dialog control which layer *styles* are exported.
The schema diff column shows columns present in the GPKG but missing from the
current schema.sql (i.e. additions made in QGIS that haven't been saved yet).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from . import schema as schema_mod
from . import git_manager
from .styles import _build_qml_index, _match_qml, DEFAULT_STYLE_SET


@dataclass
class ExportLayerStatus:
    layer_id:       str
    layer_name:     str
    table_name:     str
    extra_columns:  list = field(default_factory=list)  # [(name, sql_type)] in GPKG not in schema.sql
    style_qml_dest: Optional[Path] = None               # destination QML path in template


def available_style_sets(project_type: str) -> list[str]:
    """Return sorted list of style set names available in the template for project_type."""
    styles_root = git_manager.get_template_dir(project_type) / "styles"
    if not styles_root.is_dir():
        return [DEFAULT_STYLE_SET]
    sets = sorted(d.name for d in styles_root.iterdir() if d.is_dir())
    return sets or [DEFAULT_STYLE_SET]


def inspect_project_for_export(
    style_set: str = DEFAULT_STYLE_SET,
) -> tuple[list, str | None]:
    """Inspect the active project and return per-layer export status.

    Only 'base' layers are shown — those whose name exactly matches a table
    name in the GeoPackage (e.g. 'contexts', not 'c100 Contexts').

    Returns (statuses, error_message).
    """
    from qgis.core import QgsProject, QgsVectorLayer

    project = QgsProject.instance()
    gpkg_path = _find_gpkg(project)
    if not gpkg_path:
        return [], "No GeoPackage (vectors.gpkg) found in the current project."

    project_type = _read_meta(gpkg_path, "project_type") or "plan"
    template_dir = git_manager.get_template_dir(project_type)
    schema_path  = template_dir / "schema.sql"

    # Current schema.sql columns per table (may not exist yet)
    schema_cols: dict[str, set] = {}
    if schema_path.exists():
        for ld in schema_mod.parse_schema(str(schema_path)):
            schema_cols[ld['name'].lower()] = {
                f['name'].lower() for f in ld.get('fields', [])
            }

    # All table names in the GPKG
    gpkg_tables = _gpkg_table_names(gpkg_path)

    # Style destination directory (not created here — only at export time)
    styles_dest_dir = template_dir / "styles" / style_set

    statuses = []
    seen: set = set()

    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        # Base layers only: layer name must exactly match a GPKG table name
        if layer.name().lower() not in gpkg_tables:
            continue
        table_name = layer.name()
        if table_name.lower() in seen:
            continue
        seen.add(table_name.lower())

        # Reverse schema diff: columns in GPKG not yet in schema.sql
        geom_col = _gpkg_geom_column(gpkg_path, table_name) or "geom"
        gpkg_cols = _gpkg_columns(gpkg_path, table_name, exclude={geom_col.lower(), 'fid'})
        known_cols = schema_cols.get(table_name.lower(), set())
        extra = [
            (col, _gpkg_col_type(gpkg_path, table_name, col))
            for col in sorted(gpkg_cols - known_cols)
        ]

        # Destination QML path
        qml_dest = styles_dest_dir / f"{table_name.lower()}.qml"

        statuses.append(ExportLayerStatus(
            layer_id=layer.id(),
            layer_name=layer.name(),
            table_name=table_name,
            extra_columns=extra,
            style_qml_dest=qml_dest,
        ))

    return statuses, None


def export_layers(layer_ids: list[str], style_set: str = DEFAULT_STYLE_SET) -> tuple[bool, str]:
    """Export schema.sql (full) and selected layer styles to the template.

    schema.sql is always rebuilt from the full GPKG schema regardless of which
    layers are selected. Per-layer selection controls which QML files are written.

    Returns (success, summary_message).
    """
    from qgis.core import QgsProject, QgsVectorLayer

    project  = QgsProject.instance()
    gpkg_path = _find_gpkg(project)
    if not gpkg_path:
        return False, "No GeoPackage found in the current project."

    project_type = _read_meta(gpkg_path, "project_type") or "plan"
    template_dir = git_manager.get_template_dir(project_type)
    schema_path  = template_dir / "schema.sql"
    styles_dir   = template_dir / "styles" / style_set
    styles_dir.mkdir(parents=True, exist_ok=True)

    id_set = set(layer_ids)
    gpkg_tables = _gpkg_table_names(gpkg_path)
    style_changes = []
    errors = []

    # --- Schema: always export full schema.sql ---
    try:
        sql_content = _extract_schema_sql(gpkg_path)
        today = date.today().isoformat()
        schema_path.write_text(f"-- template_version: {today}\n\n{sql_content}", encoding="utf-8")
        schema_written = True
    except Exception as exc:
        errors.append(f"schema.sql: {exc}")
        schema_written = False

    # --- Styles: save QML for selected base layers ---
    for layer in project.mapLayers().values():
        if layer.id() not in id_set:
            continue
        if not isinstance(layer, QgsVectorLayer):
            continue
        if layer.name().lower() not in gpkg_tables:
            continue

        qml_path = styles_dir / f"{layer.name().lower()}.qml"
        try:
            msg, success = layer.saveNamedStyle(str(qml_path))
            if success:
                style_changes.append(qml_path.name)
            else:
                errors.append(f"{layer.name()} style: {msg}")
        except Exception as exc:
            errors.append(f"{layer.name()} style: {exc}")

    lines = []
    if schema_written:
        lines.append(f"Wrote schema.sql (template version: {date.today().isoformat()})")
    if style_changes:
        lines.append(f"Saved {len(style_changes)} QML file(s) to styles/{style_set}/:")
        lines.extend(f"  • {name}" for name in style_changes)
    if not style_changes and not errors:
        lines.append("No styles exported (no layers selected or no base layers checked).")
    if errors:
        lines.append("Errors:")
        lines.extend(f"  ✗ {e}" for e in errors)

    return not errors, "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_gpkg(project) -> str | None:
    from qgis.core import QgsVectorLayer
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        source = layer.source().split("|")[0]
        if source.endswith(".gpkg") and Path(source).name == "vectors.gpkg":
            return source
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        source = layer.source().split("|")[0]
        if source.endswith(".gpkg"):
            return source
    return None


def _read_meta(gpkg_path: str, key: str) -> str | None:
    from .deploy import read_setting
    return read_setting(gpkg_path, key)


def _gpkg_table_names(gpkg_path: str) -> set[str]:
    try:
        con = sqlite3.connect(gpkg_path)
        rows = con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        ).fetchall()
        con.close()
        return {r[0].lower() for r in rows}
    except Exception:
        return set()


def _gpkg_geom_column(gpkg_path: str, table_name: str) -> str | None:
    try:
        con = sqlite3.connect(gpkg_path)
        row = con.execute(
            "SELECT column_name FROM gpkg_geometry_columns WHERE table_name=?",
            (table_name,)
        ).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def _gpkg_columns(gpkg_path: str, table_name: str, exclude: set) -> set:
    try:
        con = sqlite3.connect(gpkg_path)
        cols = {
            r[1].lower()
            for r in con.execute(f"PRAGMA table_info({table_name})").fetchall()
            if r[1].lower() not in {e.lower() for e in exclude}
        }
        con.close()
        return cols
    except Exception:
        return set()


def _gpkg_col_type(gpkg_path: str, table_name: str, col_name: str) -> str:
    try:
        con = sqlite3.connect(gpkg_path)
        rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
        con.close()
        for r in rows:
            if r[1].lower() == col_name.lower():
                return r[2] or "TEXT"
    except Exception:
        pass
    return "TEXT"


def _extract_schema_sql(gpkg_path: str) -> str:
    con = sqlite3.connect(gpkg_path)
    try:
        layers = con.execute("""
            SELECT gc.table_name, ggc.geometry_type_name, ggc.column_name
            FROM gpkg_contents gc
            JOIN gpkg_geometry_columns ggc ON gc.table_name = ggc.table_name
            WHERE gc.data_type = 'features'
            ORDER BY gc.table_name
        """).fetchall()

        lines = []
        for table_name, geom_type, geom_col in layers:
            if table_name.startswith("_"):
                continue
            cols = con.execute(f"PRAGMA table_info({table_name})").fetchall()
            fields = [
                (c[1], c[2])
                for c in cols
                if c[1] not in ('fid', geom_col) and c[5] == 0
            ]
            lines.append(f"-- layer: {table_name}")
            lines.append(f"-- geometry: {geom_type}")
            lines.append("-- crs: EPSG:6870")
            lines.append(f"-- geometry_column: {geom_col}")
            lines.append(f"CREATE TABLE {table_name} (")
            lines.append(",\n".join(f"    {name} {typ}" for name, typ in fields))
            lines.append(");")
            lines.append("")
        return "\n".join(lines)
    finally:
        con.close()
