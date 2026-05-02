"""Layer-level sync of the active QGIS project from the plugin template.

Workflow:
  1. inspect_project()  — diff each loaded layer against schema.sql and
                          the template QML files; return a list of LayerStatus
  2. sync_layers()      — apply selected changes (ALTER TABLE + style reload)
                          directly on QgsProject.instance()
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import schema as schema_mod
from .styles import _build_qml_index, _match_qml, template_styles_dir, DEFAULT_STYLE_SET

STATUS_OK       = "ok"
STATUS_SCHEMA   = "schema"   # missing columns
STATUS_STYLE    = "style"    # style differs / not yet applied from template
STATUS_BOTH     = "both"
STATUS_UNKNOWN  = "unknown"  # layer table not in schema.sql (e.g. _meta)


@dataclass
class LayerStatus:
    layer_id:        str
    layer_name:      str
    table_name:      str
    missing_columns: list = field(default_factory=list)   # [(name, sql_type)]
    style_qml:       Optional[Path] = None                # template QML path
    style_differs:   bool = False


def available_style_sets(project_type: str) -> list[str]:
    """Return sorted list of style set names available in the template for project_type."""
    styles_root = template_styles_dir(project_type)
    if not styles_root.is_dir():
        return [DEFAULT_STYLE_SET]
    sets = sorted(d.name for d in styles_root.iterdir() if d.is_dir())
    return sets or [DEFAULT_STYLE_SET]


def inspect_project(style_set: str = DEFAULT_STYLE_SET) -> tuple[list, str | None]:
    """Inspect the active QGIS project and return per-layer sync status.

    Returns (statuses, error_message).
    error_message is None on success, or a string describing why inspection failed.
    """
    from qgis.core import QgsProject, QgsVectorLayer

    project = QgsProject.instance()

    # Locate the GeoPackage and derive project type
    gpkg_path = _find_gpkg(project)
    if not gpkg_path:
        return [], "No GeoPackage (vectors.gpkg) found in the current project."

    project_type = _read_meta(gpkg_path, "project_type") or "plan"
    schema_path = (
        Path(__file__).parent / "template" / "types" / project_type / "schema.sql"
    )
    if not schema_path.exists():
        return [], f"Template schema not found: {schema_path}"

    # Build lookup structures from the template
    schema_layers = {ld['name'].lower(): ld for ld in schema_mod.parse_schema(str(schema_path))}
    styles_dir = template_styles_dir(project_type) / style_set
    qml_index  = _build_qml_index(styles_dir) if styles_dir.is_dir() else {}

    statuses = []

    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue

        table_name = _layer_table_name(layer)
        if not table_name or table_name.lower() not in schema_layers:
            continue

        key = table_name.lower()
        layer_def = schema_layers[key]

        # Schema diff: find columns present in schema.sql but not in the GPKG
        geom_col = layer_def.get('geometry_column', 'geom')
        existing_cols = _gpkg_columns(gpkg_path, table_name, exclude={geom_col, 'fid'})
        missing = [
            (f['name'], f['sql_type'])
            for f in layer_def.get('fields', [])
            if f['name'].lower() not in existing_cols
        ]

        # Style diff: match a template QML to this layer
        qml = _match_qml(layer.name(), qml_index)
        style_differs = qml is not None  # always offer template style as an option

        statuses.append(LayerStatus(
            layer_id=layer.id(),
            layer_name=layer.name(),
            table_name=table_name,
            missing_columns=missing,
            style_qml=qml,
            style_differs=style_differs,
        ))

    return statuses, None


def sync_layers(layer_ids: list[str], style_set: str = DEFAULT_STYLE_SET) -> tuple[bool, str]:
    """Apply schema and style sync for the given layer IDs.

    Operates on QgsProject.instance(). Applies ALTER TABLE for missing columns
    and reloads the template QML style for each selected layer.

    Returns (success, summary_message).
    """
    from qgis.core import QgsProject, QgsVectorLayer

    project = QgsProject.instance()
    gpkg_path = _find_gpkg(project)
    if not gpkg_path:
        return False, "No GeoPackage found in the current project."

    project_type = _read_meta(gpkg_path, "project_type") or "plan"
    schema_path = (
        Path(__file__).parent / "template" / "types" / project_type / "schema.sql"
    )
    schema_layers = {ld['name'].lower(): ld for ld in schema_mod.parse_schema(str(schema_path))}
    styles_dir = template_styles_dir(project_type) / style_set
    qml_index  = _build_qml_index(styles_dir) if styles_dir.is_dir() else {}

    id_set = set(layer_ids)
    schema_changes = []
    style_changes  = []
    errors         = []
    synced_tables: set = set()

    for layer in project.mapLayers().values():
        if layer.id() not in id_set:
            continue
        if not isinstance(layer, QgsVectorLayer):
            continue

        table_name = _layer_table_name(layer)
        if not table_name or table_name.lower() not in schema_layers:
            continue

        layer_def = schema_layers[table_name.lower()]
        geom_col  = layer_def.get('geometry_column', 'geom')

        # --- Schema: ALTER TABLE for each missing column (once per table) ---
        if table_name.lower() not in synced_tables:
            synced_tables.add(table_name.lower())
            existing_cols = _gpkg_columns(gpkg_path, table_name, exclude={geom_col, 'fid'})
            con = sqlite3.connect(gpkg_path)
            try:
                for f in layer_def.get('fields', []):
                    if f['name'].lower() not in existing_cols:
                        con.execute(
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN {f['name']} {f['sql_type']}"
                        )
                        schema_changes.append(
                            f"{table_name}: + {f['name']} {f['sql_type']}"
                        )
                con.commit()
            except Exception as exc:
                errors.append(f"{table_name} schema: {exc}")
            finally:
                con.close()

        # --- Style: load template QML ---
        qml = _match_qml(layer.name(), qml_index)
        if qml:
            try:
                layer.loadNamedStyle(str(qml))
                layer.triggerRepaint()
                style_changes.append(layer.name())
            except Exception as exc:
                errors.append(f"{layer.name()} style: {exc}")

    # Update _meta.template_version
    version = schema_mod.get_template_version(str(schema_path))
    if version:
        _write_meta(gpkg_path, "template_version", version)

    # Persist active style set so it is re-applied on every project load
    if style_changes:
        from qgis.core import QgsProject, QgsExpressionContextUtils
        from .styles import PROJECT_VAR_STYLE
        QgsExpressionContextUtils.setProjectVariable(
            QgsProject.instance(), PROJECT_VAR_STYLE, style_set
        )

    lines = []
    if schema_changes:
        lines.append("Schema changes applied:")
        lines.extend(f"  • {c}" for c in schema_changes)
    else:
        lines.append("Schema: already up to date.")
    if style_changes:
        lines.append(f"Styles updated: {', '.join(style_changes)}")
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


def _layer_table_name(layer) -> str | None:
    """Extract the GeoPackage table name from a layer's datasource string."""
    source = layer.source()
    if "|layername=" in source:
        return source.split("|layername=")[1].split("|")[0]
    return None


def _read_meta(gpkg_path: str, key: str) -> str | None:
    try:
        con = sqlite3.connect(gpkg_path)
        row = con.execute("SELECT value FROM _meta WHERE key=?", (key,)).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def _write_meta(gpkg_path: str, key: str, value: str):
    try:
        con = sqlite3.connect(gpkg_path)
        con.execute(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)", (key, value)
        )
        con.commit()
        con.close()
    except Exception:
        pass


def _gpkg_columns(gpkg_path: str, table_name: str, exclude: set) -> set:
    """Return lowercase column names for a GeoPackage table, minus excluded names."""
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
