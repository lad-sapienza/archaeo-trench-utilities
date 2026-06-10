"""SectionBuilder — elevation label population for ArchaeoTrench Utilities.

Fills the 'elev' field of sb_section_elevations from the nearest point of
sb_profile_pts, matched by 2D distance in section space (lin_x AND elev
together). With multiple overlapping profiles (one per DEM/stratum) this
means a label placed near a profile picks up THAT profile's elevation —
no explicit DEM choice needed.

Only features with NULL elev are filled (an existing value is a manual
override and is never touched). Values are rounded to 2 decimal places.

If sb_section_elevations is in editing mode, writes go through the edit
buffer wrapped in an undo command; otherwise straight to the provider.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsSpatialIndex

from .sb_extract import _is_null, _open_table, _refresh

_DECIMALS = 2


def populate_labels(gpkg_path: Path) -> dict:
    """Fill NULL elev values on sb_section_elevations from sb_profile_pts.

    Returns a stats dict:
        populated — number of labels filled
        skipped   — number of labels that already had an elev (untouched)
        total     — total features in sb_section_elevations

    Raises RuntimeError on any precondition failure.
    """
    pts_layer   = _open_table(gpkg_path, "sb_profile_pts")
    label_layer = _open_table(gpkg_path, "sb_section_elevations")

    profile_elevs = {}
    for f in pts_layer.getFeatures():
        profile_elevs[f.id()] = float(f["elev"])
    if not profile_elevs:
        raise RuntimeError(
            "sb_profile_pts is empty.\n"
            "Run 'Section Builder → Extract profile…' first."
        )
    index = QgsSpatialIndex(pts_layer.getFeatures())

    # Collect the labels to fill
    targets = []   # (fid, QgsPointXY)
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
        nearest = index.nearestNeighbor(point, 1)
        if not nearest:
            continue
        changes[fid] = round(profile_elevs[nearest[0]], _DECIMALS)

    if changes:
        if label_layer.isEditable():
            # Undoable: one edit command covering all labels
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
