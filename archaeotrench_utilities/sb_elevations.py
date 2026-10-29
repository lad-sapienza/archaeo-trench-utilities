"""SectionBuilder — elevation label population for ArchaeoTrench Utilities.

Fills the 'elev' field of sb_section_elevations from the nearest point on
sb_section_ln, found by closest-segment search in section space (lin_x, elev).
With multiple overlapping profiles a label placed near a specific profile
picks up THAT profile's elevation — no explicit DEM choice needed.

Only features with NULL elev are filled (an existing value is a manual
override and is never touched). Values are rounded to 2 decimal places.

If sb_section_elevations is in editing mode, writes go through the edit
buffer wrapped in an undo command; otherwise straight to the provider.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

_DECIMALS = 2


def _is_null(val) -> bool:
    return val is None or str(val) in ("NULL", "")


def _open_table(gpkg_path: Path, table: str) -> QgsVectorLayer:
    for layer in QgsProject.instance().mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        src = layer.source()
        if (Path(src.split("|")[0]) == gpkg_path
                and f"layername={table}" in src):
            return layer
    layer = QgsVectorLayer(f"{gpkg_path}|layername={table}", table, "ogr")
    if not layer.isValid():
        raise RuntimeError(
            f"Table '{table}' not found in {gpkg_path}.\n"
            "Run 'Section Builder → New section…' first."
        )
    return layer


def _refresh(layer: QgsVectorLayer) -> None:
    layer.reload()
    layer.triggerRepaint()


def populate_labels(gpkg_path: Path) -> dict:
    """Fill NULL elev values on sb_section_elevations from the nearest point
    on sb_section_ln (closest-segment search in 2D section space).

    Returns a stats dict:
        populated — number of labels filled
        skipped   — number of labels that already had an elev (untouched)
        total     — total features in sb_section_elevations

    Raises RuntimeError on any precondition failure.
    """
    ln_layer    = _open_table(gpkg_path, "sb_section_ln")
    label_layer = _open_table(gpkg_path, "sb_section_elevations")

    if ln_layer.featureCount() == 0:
        raise RuntimeError(
            "sb_section_ln is empty.\n"
            "Run 'Section Builder → Generate section…' first."
        )

    # Preload all section linestrings for closest-point search
    ln_geoms = [
        f.geometry()
        for f in ln_layer.getFeatures()
        if f.geometry() and not f.geometry().isNull()
    ]

    targets = []
    skipped = 0
    total = 0
    for f in label_layer.getFeatures():
        total += 1
        if not _is_null(f["elev"]):
            skipped += 1
            continue
        geom = f.geometry()
        if geom is None or geom.isNull():
            continue
        targets.append((f.id(), geom.asPoint()))

    if total == 0:
        raise RuntimeError(
            "sb_section_elevations is empty.\n"
            "Place label points in the section view first."
        )

    elev_idx = label_layer.fields().indexOf("elev")
    changes = {}

    for fid, point in targets:
        pt = QgsPointXY(point)
        best_sqr_dist = float("inf")
        best_elev = None
        for ln_geom in ln_geoms:
            # closestSegmentWithContext returns (sqrDist, closestPt, afterVertex, leftOf)
            result = ln_geom.closestSegmentWithContext(pt)
            sqr_dist = result[0]
            closest_pt = result[1]
            if sqr_dist < best_sqr_dist:
                best_sqr_dist = sqr_dist
                best_elev = closest_pt.y()   # Y = elev in section space
        if best_elev is not None:
            changes[fid] = round(best_elev, _DECIMALS)

    if changes:
        if label_layer.isEditable():
            label_layer.beginEditCommand("Populate elevation labels")
            ok = all(
                label_layer.changeAttributeValue(fid, elev_idx, value)
                for fid, value in changes.items()
            )
            if not ok:
                label_layer.destroyEditCommand()
                raise RuntimeError("Could not write elevation values (edit buffer).")
            label_layer.endEditCommand()
        else:
            attr_changes = {fid: {elev_idx: value} for fid, value in changes.items()}
            if not label_layer.dataProvider().changeAttributeValues(attr_changes):
                raise RuntimeError("Could not write elevation values.")
            _refresh(label_layer)

    return {
        "populated": len(changes),
        "skipped": skipped,
        "total": total,
    }
