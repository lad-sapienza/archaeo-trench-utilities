"""Add-context logic for ArchaeoTrench Utilities.

Creates a layer group containing duplicate instances of the per-context
layers, named {context_name} {Layer Type}.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .styles import DEFAULT_STYLE_SET

# Tables pre-checked by default in the dialog, in top-to-bottom display order.
DEFAULT_CONTEXT_TABLES = ["elevations", "detail", "contexts"]


def add_context(context_name: str, selected_tables: list, style_set: str = DEFAULT_STYLE_SET):
    """Add a layer group for context_name to the current QGIS project.

    Args:
        context_name:    Name of the group and layer prefix (e.g. "c100").
        selected_tables: Ordered list of GPKG table names to include.
        style_set:       Style set name to apply to the new layers.

    Raises RuntimeError if no GeoPackage datasource is found in the project.
    """
    from qgis.core import QgsProject, QgsVectorLayer
    from qgis.PyQt.QtCore import QTimer
    from .styles import _build_qml_index, _match_qml
    from . import git_manager

    project = QgsProject.instance()
    gpkg_path = _find_gpkg_path(project)
    if not gpkg_path:
        raise RuntimeError(
            "No GeoPackage datasource found in the current project. "
            "Is a trench project open?"
        )

    project_type = get_project_type(project) or "plan"
    styles_dir = git_manager.get_template_dir(project_type) / "styles" / style_set

    root = project.layerTreeRoot()
    group = root.insertGroup(0, context_name)
    new_layers = []

    for table_name in selected_tables:
        display_name = f"{context_name} {_table_to_display(table_name)}"
        layer = QgsVectorLayer(
            f"{gpkg_path}|layername={table_name}", display_name, "ogr"
        )
        if not layer.isValid():
            continue
        project.addMapLayer(layer, addToLegend=False)
        group.addLayer(layer)
        new_layers.append(layer)

    # Apply styles only to the new layers after QGIS finishes its own
    # post-addMapLayer style initialisation (which would otherwise overwrite ours).
    if styles_dir.is_dir():
        qml_index = _build_qml_index(styles_dir)

        def _apply():
            for layer in new_layers:
                qml = _match_qml(layer.name(), qml_index)
                if qml:
                    layer.loadNamedStyle(str(qml))
                    layer.triggerRepaint()

        QTimer.singleShot(0, _apply)


def get_project_type(project) -> str | None:
    """Read the project type from the _meta table of the project's GeoPackage."""
    gpkg_path = _find_gpkg_path(project)
    if not gpkg_path:
        return None
    try:
        con = sqlite3.connect(gpkg_path)
        row = con.execute("SELECT value FROM _meta WHERE key='project_type'").fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def list_gpkg_layers(project) -> list:
    """Return list of (table_name, display_name) for all vector layers in the GPKG."""
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
    return " ".join(word.capitalize() for word in table_name.split("_"))


def _find_gpkg_path(project) -> str | None:
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
