"""SectionBuilder — offset polygon creation for ArchaeoTrench Utilities.

For each selected feature in sb_section_ln, builds a closed polygon in
sb_section_plg by shifting the source linestring downward by a fixed offset
and joining the two ends with vertical segments:

    top line  →  (x₀,y₀) … (xₙ,yₙ)
    drop      →  (xₙ, yₙ−d)
    base line ←  (xₙ₋₁,yₙ₋₁−d) … (x₀,y₀−d)
    rise      →  (x₀,y₀)  ← close

The 'part' field from the source linestring is copied to the polygon.
One polygon per selected feature — no merging.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)


def _find_layer(gpkg_path: Path, table: str) -> QgsVectorLayer | None:
    for layer in QgsProject.instance().mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        src = layer.source()
        if Path(src.split("|")[0]) == gpkg_path and f"layername={table}" in src:
            return layer
    return None


def create_offset_polygons(gpkg_path: Path, offset: float) -> dict:
    """Build offset polygons from the current selection in sb_section_ln.

    Returns stats dict: n_written, n_skipped.
    Raises RuntimeError on precondition failure.
    """
    if offset <= 0:
        raise RuntimeError("Offset must be a positive number.")

    src_layer = _find_layer(gpkg_path, "sb_section_ln")
    if src_layer is None:
        raise RuntimeError(
            "Layer 'sb_section_ln' is not loaded.\n"
            "Run 'Section Builder → New section…' first."
        )

    dst_layer = _find_layer(gpkg_path, "sb_section_plg")
    if dst_layer is None:
        raise RuntimeError(
            "Layer 'sb_section_plg' is not loaded.\n"
            "Run 'Section Builder → New section…' first."
        )

    if dst_layer.isEditable():
        raise RuntimeError(
            "Layer 'sb_section_plg' is in editing mode.\n"
            "Toggle editing off before running this operation."
        )

    selected = list(src_layer.selectedFeatures())
    if not selected:
        raise RuntimeError(
            "No features selected in 'sb_section_ln'.\n"
            "Select one or more section segments first."
        )

    fields = dst_layer.fields()
    part_idx  = fields.indexOf("part")
    label_idx = fields.indexOf("label")

    feats_to_write = []
    n_skipped = 0

    for src_feat in selected:
        geom = src_feat.geometry()
        if geom is None or geom.isNull():
            n_skipped += 1
            continue

        verts = geom.asPolyline()
        if len(verts) < 2:
            n_skipped += 1
            continue

        top = list(verts)
        bottom = [QgsPointXY(p.x(), p.y() - offset) for p in reversed(verts)]
        ring = top + bottom  # QGIS closes the ring automatically

        poly_geom = QgsGeometry.fromPolygonXY([ring])
        if poly_geom is None or poly_geom.isNull():
            n_skipped += 1
            continue

        feat = QgsFeature(fields)
        feat.setGeometry(poly_geom)
        if part_idx >= 0:
            feat.setAttribute(part_idx, src_feat["part"])
        if label_idx >= 0:
            feat.setAttribute(label_idx, src_feat["label"])
        feats_to_write.append(feat)

    if feats_to_write:
        ok, _ = dst_layer.dataProvider().addFeatures(feats_to_write)
        if not ok:
            raise RuntimeError("Could not write polygons to 'sb_section_plg'.")
        dst_layer.reload()
        dst_layer.triggerRepaint()

    return {"n_written": len(feats_to_write), "n_skipped": n_skipped}
