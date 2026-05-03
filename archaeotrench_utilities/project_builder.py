"""Build a QGIS project programmatically from a GeoPackage and style directory.

This replaces the binary template.qgs file. On deploy, a fresh QgsProject is
created, populated with the correct layer tree, styled, and saved as a .qgz.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsLayerTreeGroup,
    QgsProject,
    QgsVectorLayer,
)


# ---------------------------------------------------------------------------
# Layer tree definition for each project type
# ---------------------------------------------------------------------------

# Gen group layers: listed top-to-bottom in the tree (= rendered top-to-bottom).
# addLayer() appends to the end, so we add them in display order to end up
# with the correct visual stack (first added = top of tree = rendered on top).
_GEN_LAYERS = [
    "elevations",
    "detail",
    "contexts",
    "elev_change",
    "limits",
]

_PROJECT_CRS = "EPSG:6870"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_project(
    gpkg_path: str | Path,
    trench_name: str,
    project_type: str,
    output_qgz_path: str | Path,
    style_dir: str | Path | None = None,
) -> None:
    """Create a new QGIS project (.qgz) from a GeoPackage and optional styles.

    The project is written to output_qgz_path.  The current QGIS session
    (QgsProject.instance()) is NOT modified.

    Args:
        gpkg_path: Absolute path to the already-created vectors.gpkg.
        trench_name: Display name of the trench (used for the project title).
        project_type: Template type ('plan' or 'section').
        output_qgz_path: Destination .qgz file path.
        style_dir: Directory containing *.qml files to apply. If None,
                   falls back to the plugin template styles/default/.
    """
    gpkg_path = Path(gpkg_path)
    output_qgz_path = Path(output_qgz_path)

    if style_dir is None:
        from . import git_manager
        style_dir = git_manager.get_template_dir(project_type) / "styles" / "default"
    style_dir = Path(style_dir)

    project = QgsProject()
    project.setCrs(QgsCoordinateReferenceSystem(_PROJECT_CRS))
    project.setTitle(trench_name)

    # Set the file name BEFORE adding layers so that relative path resolution
    # works correctly when writing.
    project.setFileName(str(output_qgz_path))

    root = project.layerTreeRoot()

    # ---- Gen group ----
    gen_group = root.addGroup("Gen")
    for table_name in _GEN_LAYERS:
        layer = _make_layer(gpkg_path, table_name, table_name)
        project.addMapLayer(layer, False)
        gen_group.addLayer(layer)

    # ---- Apply styles ----
    if style_dir.is_dir():
        _apply_styles(project, style_dir)

    project.write()
    del project


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_layer(gpkg_path: Path, table_name: str, display_name: str) -> QgsVectorLayer:
    source = f"{gpkg_path}|layername={table_name}"
    layer = QgsVectorLayer(source, display_name, "ogr")
    if not layer.isValid():
        raise RuntimeError(
            f"Could not load layer '{table_name}' from {gpkg_path}"
        )
    return layer


def _apply_styles(project: QgsProject, style_dir: Path) -> None:
    """Apply QML styles from style_dir to all layers in project."""
    from .styles import _build_qml_index, _match_qml

    qml_index = _build_qml_index(style_dir)
    for layer in project.mapLayers().values():
        qml = _match_qml(layer.name(), qml_index)
        if qml:
            layer.loadNamedStyle(str(qml))
