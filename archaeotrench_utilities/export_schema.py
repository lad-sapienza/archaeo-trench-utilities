"""Export GeoPackage schema and layer styles from the current QGIS project
back to the plugin template folder.

This enables a round-trip workflow:
  Deploy (schema.sql + QML → .gpkg + .qgz)
  Edit layers/styles in QGIS
  Export (running project → updated schema.sql + QML in template)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_to_template(project_type: str) -> tuple[bool, str]:
    """Export schema and styles from the current QGIS project to the template.

    Reads the GeoPackage path and layer styles from QgsProject.instance(),
    writes schema.sql and QML files to the plugin template directory.

    Returns (success, message).
    """
    from qgis.core import QgsProject

    project = QgsProject.instance()
    gpkg_path = _find_gpkg(project)
    if not gpkg_path:
        return False, "No GeoPackage (vectors.gpkg) found in the current project."

    template_dir = (
        Path(__file__).parent / "template" / "types" / project_type
    )
    if not template_dir.is_dir():
        return False, f"Template directory not found: {template_dir}"

    # Write schema.sql
    try:
        sql_content = _extract_schema_sql(gpkg_path)
    except Exception as exc:
        return False, f"Failed to extract schema: {exc}"

    schema_path = template_dir / "schema.sql"
    schema_path.write_text(sql_content, encoding="utf-8")

    # Save QML styles for base layers
    style_dir = template_dir / "styles" / "default"
    style_dir.mkdir(parents=True, exist_ok=True)
    exported_styles = _export_styles(project, gpkg_path, style_dir)

    lines = [f"Wrote {schema_path.name} ({len(sql_content.splitlines())} lines)"]
    if exported_styles:
        lines.append(f"Saved {len(exported_styles)} QML file(s): {', '.join(exported_styles)}")
    else:
        lines.append("No matching base-layer styles found to export.")

    return True, "\n".join(lines)


def get_exportable_layers(project_type: str) -> list[tuple[str, str]]:
    """Return (layer_name, qml_destination_path) pairs for a preview in the UI.

    Lists base layers from the current project that match tables in the
    existing schema (or the GeoPackage if available).
    """
    from qgis.core import QgsProject, QgsVectorLayer

    project = QgsProject.instance()
    gpkg_path = _find_gpkg(project)
    if not gpkg_path:
        return []

    table_names = _get_gpkg_table_names(gpkg_path)
    style_dir = (
        Path(__file__).parent / "template" / "types" / project_type / "styles" / "default"
    )

    result = []
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        if layer.name().lower() in table_names:
            qml_path = style_dir / f"{layer.name().lower()}.qml"
            result.append((layer.name(), str(qml_path)))
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_gpkg(project) -> str | None:
    """Return the absolute path to vectors.gpkg in the project, if any."""
    from qgis.core import QgsVectorLayer

    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        source = layer.source().split("|")[0]
        if source.endswith(".gpkg") and Path(source).name == "vectors.gpkg":
            return source
    # Fallback: any .gpkg
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        source = layer.source().split("|")[0]
        if source.endswith(".gpkg"):
            return source
    return None


def _get_gpkg_table_names(gpkg_path: str) -> set[str]:
    """Return the set of feature table names in a GeoPackage (lowercase)."""
    try:
        con = sqlite3.connect(gpkg_path)
        rows = con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'"
        ).fetchall()
        con.close()
        return {r[0].lower() for r in rows}
    except Exception:
        return set()


def _extract_schema_sql(gpkg_path: str) -> str:
    """Generate schema.sql content from a GeoPackage."""
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
            cols = con.execute(f"PRAGMA table_info({table_name})").fetchall()
            # (cid, name, type, notnull, dflt_value, pk)
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
            field_lines = [f"    {name} {typ}" for name, typ in fields]
            lines.append(",\n".join(field_lines))
            lines.append(");")
            lines.append("")

        return "\n".join(lines)
    finally:
        con.close()


def _export_styles(project, gpkg_path: str, style_dir: Path) -> list[str]:
    """Save QML style for each base layer to style_dir.

    A 'base layer' is one whose name exactly matches a GeoPackage table name
    (case-insensitive), e.g. 'elevations' but not 'c100 Elevations'.
    """
    from qgis.core import QgsVectorLayer

    table_names = _get_gpkg_table_names(gpkg_path)
    saved = []

    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        if layer.name().lower() not in table_names:
            continue

        qml_path = style_dir / f"{layer.name().lower()}.qml"
        msg, success = layer.saveNamedStyle(str(qml_path))
        if success:
            saved.append(qml_path.name)

    return saved
