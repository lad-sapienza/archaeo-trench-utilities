"""Add-context logic for ArchaeoTrench Utilities.

Creates a layer group containing duplicate instances of the per-context
layers, named {context_name} {Layer Type}.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Tables pre-checked by default in the dialog, in top-to-bottom display order.
DEFAULT_CONTEXT_TABLES = ["elevations", "detail", "contexts"]


def add_context(context_name: str, selected_tables: list):
    """Add a layer group for context_name to the current QGIS project.

    Args:
        context_name:     Name of the group and layer prefix (e.g. "c100").
        selected_tables:  Ordered list of GPKG table names to include.

    Raises RuntimeError if no GeoPackage datasource is found in the project.
    """
    from qgis.core import QgsProject, QgsVectorLayer
    from qgis.PyQt.QtCore import QTimer
    from .styles import apply_style_set  # noqa: import triggers fallback logic

    project = QgsProject.instance()
    gpkg_path = _find_gpkg_path(project)
    if not gpkg_path:
        raise RuntimeError(
            "No GeoPackage datasource found in the current project. "
            "Is a trench project open?"
        )

    root = project.layerTreeRoot()
    group = root.insertGroup(0, context_name)

    for table_name in selected_tables:
        display_name = f"{context_name} {_table_to_display(table_name)}"
        layer = QgsVectorLayer(
            f"{gpkg_path}|layername={table_name}", display_name, "ogr"
        )
        if not layer.isValid():
            continue
        project.addMapLayer(layer, addToLegend=False)
        group.addLayer(layer)

    # Defer style application so it runs after QGIS finishes its own
    # post-addMapLayer style initialisation (which would otherwise overwrite ours).
    QTimer.singleShot(0, apply_style_set)


def list_gpkg_layers(project) -> list:
    """Return list of (table_name, display_name) for all vector layers in the GPKG.

    Returns an empty list if no GeoPackage is found.
    """
    gpkg_path = _find_gpkg_path(project)
    if not gpkg_path:
        return []
    try:
        con = sqlite3.connect(gpkg_path)
        cur = con.cursor()
        cur.execute(
            "SELECT table_name FROM gpkg_contents "
            "WHERE data_type='features' ORDER BY table_name"
        )
        return [
            (row[0], _table_to_display(row[0]))
            for row in cur.fetchall()
        ]
    except Exception:
        return []
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _table_to_display(table_name: str) -> str:
    """Convert a snake_case table name to a Title Case display label."""
    return " ".join(word.capitalize() for word in table_name.split("_"))


def _find_gpkg_path(project) -> str | None:
    """Return the GeoPackage path from an existing vector layer datasource."""
    from qgis.core import QgsVectorLayer

    fallback = None
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        gpkg = layer.source().split("|")[0]
        if gpkg.endswith(".gpkg"):
            if Path(gpkg).name == "vectors.gpkg":
                return gpkg
            if fallback is None:
                fallback = gpkg
    return fallback
