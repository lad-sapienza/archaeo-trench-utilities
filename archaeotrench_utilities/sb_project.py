"""SectionBuilder — new section initialisation for ArchaeoTrench Utilities.

Creates sb_* tables in a GeoPackage and registers the corresponding layers
in the current QGIS project under a "Section — {name}" group.

Section-space layers (sb_profile_pts, sb_section_ln, sb_section_elevations,
sb_section_plg) hold local 2D coordinates: x = lin_x (cumulative distance in
metres along the useful segments), y = elev (elevation in metres). They are
NOT georeferenced — the CRS assigned to them is nominal. A projected CRS
(defaulting to the project CRS, user-overridable at init time) is used so
that the section view and measure tools work in metres; a geographic CRS
would render the section space in degrees and is rejected.

A section may sample multiple DEMs (one per excavation stratum). Profiles
from different DEMs share the same lin_x stations and are distinguished by
the dem_source field on sb_profile_pts / sb_profile_pts_raw / sb_section_ln.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsExpressionContextUtils,
    QgsField,
    QgsFields,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

PROJECT_VAR_DEMS         = "sb_dem_layers"   # semicolon-separated raster layer names
PROJECT_VAR_SECTION_NAME = "sb_section_name"

SB_TABLES = [
    "sb_section_line",
    "sb_profile_pts_raw",
    "sb_profile_pts",
    "sb_section_ln",
    "sb_section_elevations",
    "sb_section_plg",
]


# ---------------------------------------------------------------------------
# GPKG path resolution
# ---------------------------------------------------------------------------

def _find_vectors_gpkg() -> Path | None:
    """Return the path to vectors.gpkg if any loaded layer uses it."""
    for layer in QgsProject.instance().mapLayers().values():
        if not hasattr(layer, "dataProvider"):
            continue
        src = layer.dataProvider().dataSourceUri()
        path_part = src.split("|")[0].strip()
        if path_part.lower().endswith("vectors.gpkg"):
            p = Path(path_part)
            if p.exists():
                return p
    return None


def resolve_gpkg_path(section_name: str) -> Path:
    """Determine the target GeoPackage path.

    Prefers an existing vectors.gpkg (ATU project); otherwise creates
    {section_name}.gpkg next to the current project file.

    Raises RuntimeError if the project is unsaved and no vectors.gpkg is found.
    """
    existing = _find_vectors_gpkg()
    if existing:
        return existing

    project_file = QgsProject.instance().fileName()
    if not project_file:
        raise RuntimeError(
            "The project has not been saved yet.\n"
            "Please save the project (Project → Save As…) before initialising a section."
        )
    return Path(project_file).parent / f"{section_name}.gpkg"


# ---------------------------------------------------------------------------
# Existing-table handling
# ---------------------------------------------------------------------------

def existing_sb_tables(gpkg_path: Path) -> list:
    """Return the names of sb_* tables already present in the GeoPackage."""
    if not gpkg_path.exists():
        return []
    import sqlite3
    con = sqlite3.connect(gpkg_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        con.close()
    names = {r[0] for r in rows}
    return [t for t in SB_TABLES if t in names]


def _remove_section_layers(gpkg_path: Path, project: QgsProject) -> None:
    """Remove loaded layers pointing to sb_* tables of this GPKG, then prune
    any 'Section — …' group left empty. Releases QGIS handles on the tables
    so they can be dropped cleanly."""
    to_remove = []
    for layer_id, layer in project.mapLayers().items():
        src = layer.source() if hasattr(layer, "source") else ""
        if (Path(src.split("|")[0]) == gpkg_path
                and any(f"layername={t}" in src for t in SB_TABLES)):
            to_remove.append(layer_id)
    if to_remove:
        project.removeMapLayers(to_remove)

    root = project.layerTreeRoot()
    for child in list(root.children()):
        if child.name().startswith("Section — ") and not child.findLayers():
            root.removeChildNode(child)


def _drop_sb_tables(gpkg_path: Path) -> None:
    """Drop all sb_* tables from the GeoPackage via OGR, which also cleans up
    gpkg_contents, gpkg_geometry_columns, spatial indexes and triggers."""
    from osgeo import ogr
    ds = ogr.Open(str(gpkg_path), update=1)
    if ds is None:
        raise RuntimeError(
            f"Could not open {gpkg_path} to remove the old section tables.\n"
            "The file may be locked by another application."
        )
    try:
        for i in reversed(range(ds.GetLayerCount())):
            if ds.GetLayer(i).GetName() in SB_TABLES:
                ds.DeleteLayer(i)
    finally:
        ds = None


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

def _fields(*specs: tuple) -> QgsFields:
    """Build QgsFields from (name, QVariant.Type) pairs."""
    qf = QgsFields()
    for name, qtype in specs:
        qf.append(QgsField(name, qtype))
    return qf


def _write_gpkg_layer(
    gpkg_path: Path,
    table_name: str,
    fields: QgsFields,
    wkb_type,
    crs: QgsCoordinateReferenceSystem,
    *,
    overwrite_file: bool,
) -> None:
    """Create or replace a single layer in a GeoPackage."""
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName   = "GPKG"
    options.layerName    = table_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile
        if overwrite_file
        else QgsVectorFileWriter.CreateOrOverwriteLayer
    )
    writer = QgsVectorFileWriter.create(
        str(gpkg_path), fields, wkb_type, crs,
        QgsCoordinateTransformContext(), options,
    )
    if writer is None:
        raise RuntimeError(f"Failed to create layer '{table_name}' in {gpkg_path}")
    err = writer.hasError()
    del writer
    if err != QgsVectorFileWriter.NoError:
        raise RuntimeError(
            f"Error creating layer '{table_name}' in {gpkg_path}: code {err}"
        )


def create_tables(
    gpkg_path: Path,
    plan_crs: QgsCoordinateReferenceSystem,
    section_crs: QgsCoordinateReferenceSystem,
) -> None:
    """Create all sb_* tables in the GeoPackage.

    plan_crs is used for sb_section_line (drawn in plan view);
    section_crs (projected, metres) for all local-space layers.

    Uses CreateOrOverwriteFile only for the very first table when the file does
    not yet exist, so that an existing vectors.gpkg is never truncated.
    """
    D, I, S = QVariant.Double, QVariant.Int, QVariant.String
    new_file = not gpkg_path.exists()

    # (table_name, fields, wkb_type, crs)
    # sb_profile_pts_raw is created but not shown in the project — permanent backup.
    # The 'id' field on sb_section_line is an OPTIONAL ordering override:
    # when left NULL on every segment, drawing order (fid) is used instead.
    tables = [
        (
            "sb_section_line",
            _fields(("id", I), ("section_name", S), ("exclude_from_profile", I)),
            QgsWkbTypes.LineString,
            plan_crs,
        ),
        (
            "sb_profile_pts_raw",
            _fields(("lin_x", D), ("geo_x", D), ("geo_y", D), ("elev", D),
                    ("part", S), ("dem_source", S)),
            QgsWkbTypes.Point,
            section_crs,
        ),
        (
            "sb_profile_pts",
            _fields(("lin_x", D), ("geo_x", D), ("geo_y", D), ("elev", D),
                    ("part", S), ("dem_source", S)),
            QgsWkbTypes.Point,
            section_crs,
        ),
        (
            "sb_section_ln",
            _fields(("part", S), ("dem_source", S)),
            QgsWkbTypes.LineString,
            section_crs,
        ),
        (
            "sb_section_elevations",
            _fields(("elev", D), ("label", S)),
            QgsWkbTypes.Point,
            section_crs,
        ),
        (
            "sb_section_plg",
            _fields(("part", S),),
            QgsWkbTypes.Polygon,
            section_crs,
        ),
    ]

    for i, (table_name, fields, wkb_type, crs) in enumerate(tables):
        _write_gpkg_layer(
            gpkg_path, table_name, fields, wkb_type, crs,
            overwrite_file=(i == 0 and new_file),
        )


# ---------------------------------------------------------------------------
# Layer registration
# ---------------------------------------------------------------------------

def _open_layer(gpkg_path: Path, table_name: str, display_name: str) -> QgsVectorLayer:
    uri = f"{gpkg_path}|layername={table_name}"
    layer = QgsVectorLayer(uri, display_name, "ogr")
    if not layer.isValid():
        raise RuntimeError(
            f"Could not open layer '{table_name}' from {gpkg_path}.\n"
            "The GeoPackage may be locked by another process."
        )
    return layer


def _add_layers_to_project(
    gpkg_path: Path,
    section_name: str,
    project: QgsProject,
) -> None:
    """Insert a layer group and populate it with sb_* layers."""
    root = project.layerTreeRoot()
    section_group = root.insertGroup(0, f"Section — {section_name}")
    plan_sub    = section_group.addGroup("Plan")
    section_sub = section_group.addGroup("Section")

    # sb_profile_pts_raw is not added here — it is a hidden backup layer.
    layer_specs = [
        ("sb_section_line",       "Section line",      plan_sub),
        ("sb_profile_pts",        "Profile points",    section_sub),
        ("sb_section_ln",         "Section segments",  section_sub),
        ("sb_section_elevations", "Elevation labels",  section_sub),
        ("sb_section_plg",        "Interpreted areas", section_sub),
    ]

    for table_name, display_name, group in layer_specs:
        layer = _open_layer(gpkg_path, table_name, display_name)
        project.addMapLayer(layer, False)   # addToLegend=False — we place it manually
        group.addLayer(layer)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_section(
    section_name: str,
    section_crs: QgsCoordinateReferenceSystem,
) -> Path:
    """Initialise a new section.

    1. Resolves (or creates) the target GeoPackage.
    2. If sb_* tables already exist: removes their loaded layers from the
       project and DROPS the tables. The caller must have asked the user
       for confirmation first (see existing_sb_tables()).
    3. Creates all sb_* tables fresh (local-space layers in section_crs).
    4. Adds layers to the project under "Section — {section_name}".
    5. Saves sb_section_name as a project variable.

    section_crs must be a projected CRS (metres) — the dialog validates this.
    The DEMs to sample are chosen later, at extraction time (a section may
    cut multiple strata, each with its own DEM).

    Returns the GeoPackage path used.
    Raises RuntimeError on any failure.
    """
    if not section_crs.isValid() or section_crs.isGeographic():
        raise RuntimeError(
            "The section CRS must be a projected CRS (units in metres)."
        )

    project  = QgsProject.instance()
    gpkg_path = resolve_gpkg_path(section_name)

    if existing_sb_tables(gpkg_path):
        _remove_section_layers(gpkg_path, project)
        _drop_sb_tables(gpkg_path)

    create_tables(gpkg_path, project.crs(), section_crs)
    _add_layers_to_project(gpkg_path, section_name, project)

    QgsExpressionContextUtils.setProjectVariable(
        project, PROJECT_VAR_SECTION_NAME, section_name)

    return gpkg_path


def get_section_gpkg(section_name: str | None = None) -> Path | None:
    """Return the GeoPackage that holds sb_* tables, or None if not determinable.

    Tries vectors.gpkg first; falls back to {section_name}.gpkg in the project folder.
    Used by the other SB modules to locate the data without re-running init.
    """
    existing = _find_vectors_gpkg()
    if existing:
        return existing

    project_file = QgsProject.instance().fileName()
    if not project_file or not section_name:
        return None

    candidate = Path(project_file).parent / f"{section_name}.gpkg"
    return candidate if candidate.exists() else None
