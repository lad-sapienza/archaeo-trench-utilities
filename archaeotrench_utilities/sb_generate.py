"""SectionBuilder — section generation from annotations for ArchaeoTrench Utilities.

Samples every registered DEM along the entire sb_section_line and writes the
resulting linestrings to sb_section_ln.

Workflow:
  Annotations (sb_annotations) label interpretive stretches of the section line.
  They are NOT tied to a specific DEM — all registered DEMs are sampled everywhere.
  The dem_layer field on sb_annotations is kept in the schema for reference but is
  not used during generation.

Annotation semantics:
  exclude = 1            — jog segment: skipped, does NOT advance lin_x
  exclude = null/0, part set   — named stretch: label assigned to output
  exclude = null/0, part null  — unnamed stretch: output part = NULL

lin_x calculation:
  lin_x is the cumulative distance along the section line, excluding jog segments.
  For a station at distance d: lin_x(d) = d − Σ(jog lengths before d).

Nodata handling:
  DEM nodata or out-of-extent → break the current run for that DEM.
  A run of fewer than 2 points is silently discarded.

sb_section_ln is fully derived data and is rebuilt from scratch on every run.
"""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import (
    QgsCoordinateTransform,
    QgsExpressionContextUtils,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from .compat import raster_identify_format_value
from .sb_project import PROJECT_VAR_REGISTERED_DEMS


def _is_null(val) -> bool:
    """True for NULL attribute values (None, invalid QVariant, qgis NULL)."""
    return val is None or str(val) in ("NULL", "")


def _open_table(gpkg_path: Path, table: str) -> QgsVectorLayer:
    """Return the project's loaded instance of a sb_* table, or open fresh."""
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


def _stations(length: float, interval: float) -> list:
    """Regular sampling distances along a linestring; endpoint always included."""
    n = int(length / interval)
    pts = [i * interval for i in range(n + 1)]
    if length - pts[-1] > 1e-9:
        pts.append(length)
    return pts


class _DemSampler:
    """Samples one DEM, building the coordinate transform once at construction."""

    def __init__(self, dem_layer: QgsRasterLayer, ann_crs):
        self._provider = dem_layer.dataProvider()
        self._format = raster_identify_format_value()
        self._nodata = self._provider.sourceNoDataValue(1)
        self._transform = None
        if ann_crs != dem_layer.crs():
            self._transform = QgsCoordinateTransform(
                ann_crs, dem_layer.crs(), QgsProject.instance())

    def sample(self, point: QgsPointXY) -> float | None:
        """Return the DEM value at a plan point, or None for nodata/no coverage."""
        if self._transform:
            point = self._transform.transform(point)
        result = self._provider.identify(point, self._format)
        if not result.isValid():
            return None
        value = result.results().get(1)
        if value is None or value == self._nodata:
            return None
        return float(value)


def _merge_section_line(line_layer: QgsVectorLayer) -> QgsGeometry:
    """Merge sb_section_line features into a single ordered polyline.

    Uses the 'id' field for ordering when all features have it; fid otherwise.
    Consecutive features that share an endpoint have the duplicate removed.
    """
    with_id, without_id = [], []
    for f in line_layer.getFeatures():
        geom = f.geometry()
        if geom is None or geom.isNull():
            continue
        seg_id = f["id"] if not _is_null(f["id"]) else None
        pts = geom.asPolyline()
        if seg_id is not None:
            with_id.append((int(seg_id), pts))
        else:
            without_id.append((f.id(), pts))

    ordered = with_id or without_id
    if not ordered:
        raise RuntimeError(
            "sb_section_line is empty. Draw the profile polyline first."
        )
    ordered.sort(key=lambda t: t[0])

    all_vertices = []
    for _, pts in ordered:
        if all_vertices and pts:
            prev = all_vertices[-1]
            if abs(prev.x() - pts[0].x()) < 1e-9 and abs(prev.y() - pts[0].y()) < 1e-9:
                pts = pts[1:]
        all_vertices.extend(pts)

    return QgsGeometry.fromPolylineXY(all_vertices)


def _build_annotation_intervals(ann_features, merged_line):
    """Project each annotation onto the section line.

    Returns:
        jog_intervals:   sorted list of (start_d, end_d) for exclude=1 annotations
        named_intervals: sorted list of (start_d, end_d, part) for named annotations
    """
    jog_intervals = []
    named_intervals = []

    for f in ann_features:
        geom = f.geometry()
        if geom is None or geom.isNull():
            continue
        verts = geom.asPolyline()
        if not verts:
            continue

        ds = [
            merged_line.lineLocatePoint(QgsGeometry.fromPointXY(v))
            for v in verts
        ]
        start_d, end_d = min(ds), max(ds)
        if end_d - start_d < 1e-9:
            continue

        if f["exclude"] == 1:
            jog_intervals.append((start_d, end_d))
        elif not _is_null(f["part"]):
            label_val = None if _is_null(f["label"]) else str(f["label"])
            named_intervals.append((start_d, end_d, str(f["part"]), label_val))

    jog_intervals.sort()
    named_intervals.sort()
    return jog_intervals, named_intervals


def _in_jog(d: float, jog_intervals: list) -> bool:
    for s, e in jog_intervals:
        if s <= d <= e:
            return True
        if s > d:
            break
    return False


def _compute_lin_x(d: float, jog_intervals: list) -> float:
    """lin_x = section-line distance minus total jog length before d."""
    removed = 0.0
    for s, e in jog_intervals:
        if e <= d:
            removed += e - s
        elif s < d:
            removed += d - s
        else:
            break
    return d - removed


def _find_annotation(d: float, named_intervals: list) -> tuple:
    """Return (part, label) of the first named annotation covering d, else (None, None)."""
    for s, e, part, label in named_intervals:
        if s <= d <= e:
            return part, label
        if s > d:
            break
    return None, None


def has_existing_sections(gpkg_path: Path) -> bool:
    """Return True if sb_section_ln already contains features."""
    layer = _open_table(gpkg_path, "sb_section_ln")
    return layer.featureCount() > 0


def generate_section(gpkg_path: Path, interval: float) -> dict:
    """Generate sb_section_ln by sampling all registered DEMs along sb_section_line.

    For each station along the section line:
      - Jog annotations (exclude = 1): skipped; do not advance lin_x.
      - All other stations: sample every registered DEM; label with the
        annotation part where one exists.

    lin_x is cumulative distance along the section line, excluding jog segments.

    Returns stats dict: segments, skipped, errors, total_annotations.
    Raises RuntimeError on any precondition failure.
    """
    if interval <= 0:
        raise RuntimeError("Sampling interval must be positive.")

    project = QgsProject.instance()

    line_layer = _open_table(gpkg_path, "sb_section_line")
    ann_layer  = _open_table(gpkg_path, "sb_annotations")
    ln_layer   = _open_table(gpkg_path, "sb_section_ln")

    for layer in (ann_layer, ln_layer):
        if layer.isEditable():
            raise RuntimeError(
                f"Layer '{layer.name()}' is in editing mode.\n"
                "Toggle editing off before generating."
            )

    merged_line = _merge_section_line(line_layer)

    # Registered DEMs (user-selected via Manage DEMs)
    raw = QgsExpressionContextUtils.projectScope(project).variable(
        PROJECT_VAR_REGISTERED_DEMS)
    try:
        registered_dems = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        registered_dems = []

    if not registered_dems:
        raise RuntimeError(
            "No DEMs registered.\n"
            "Use 'Section Builder → Manage DEMs…' to select the DEMs to sample."
        )

    # Build samplers
    samplers = {}
    missing_dems = []
    for name in registered_dems:
        candidates = [
            l for l in project.mapLayersByName(name)
            if isinstance(l, QgsRasterLayer)
        ]
        if candidates:
            samplers[name] = _DemSampler(candidates[0], line_layer.crs())
        else:
            missing_dems.append(name)

    if missing_dems:
        raise RuntimeError(
            "These registered DEM layers are not loaded:\n"
            + "\n".join(f"  • {n}" for n in sorted(missing_dems))
            + "\nLoad the DEMs or update the registered list."
        )

    # Build annotation intervals for jogs and part labels
    ann_features = list(ann_layer.getFeatures())
    jog_intervals, named_intervals = _build_annotation_intervals(ann_features, merged_line)
    n_named = len(named_intervals)

    # Main sampling loop
    fields = ln_layer.fields()
    feats_to_write = []
    segments = []
    errors = []
    n_discarded = 0

    # current_runs: (part, label, dem_name) -> [(lin_x, elev), ...]
    current_runs: dict[tuple, list] = {}
    prev_part = "<<start>>"  # sentinel that never equals a real part or None

    def flush_key(key):
        nonlocal n_discarded
        run = current_runs.pop(key, [])
        if len(run) >= 2:
            part, label, dem_name = key
            feat = QgsFeature(fields)
            feat.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(x, y) for x, y in run]
            ))
            feat.setAttribute(fields.indexOf("part"), part)
            feat.setAttribute(fields.indexOf("dem_source"), dem_name)
            label_idx = fields.indexOf("label")
            if label_idx >= 0:
                feat.setAttribute(label_idx, label)
            feats_to_write.append(feat)
            segments.append((dem_name, part, len(run)))
        elif run:
            n_discarded += 1

    def flush_all():
        for key in list(current_runs.keys()):
            flush_key(key)

    for d in _stations(merged_line.length(), interval):
        if _in_jog(d, jog_intervals):
            flush_all()
            prev_part = "<<jog>>"
            continue

        lin_x = _compute_lin_x(d, jog_intervals)
        plan_pt = QgsPointXY(merged_line.interpolate(d).asPoint())
        part, label = _find_annotation(d, named_intervals)

        if part != prev_part:
            flush_all()
            prev_part = part

        for dem_name, sampler in samplers.items():
            elev = sampler.sample(plan_pt)
            key = (part, label, dem_name)
            if elev is None:
                flush_key(key)
            else:
                current_runs.setdefault(key, []).append((lin_x, elev))

    flush_all()

    # Full rebuild of sb_section_ln
    provider = ln_layer.dataProvider()
    if not provider.truncate():
        old_ids = [f.id() for f in ln_layer.getFeatures()]
        if old_ids and not provider.deleteFeatures(old_ids):
            raise RuntimeError("Could not clear old features from sb_section_ln.")

    if feats_to_write:
        ok, _ = provider.addFeatures(feats_to_write)
        if not ok:
            raise RuntimeError("Could not write section features to sb_section_ln.")

    _refresh(ln_layer)

    return {
        "segments": segments,
        "skipped": n_discarded,
        "errors": errors,
        "total_annotations": n_named,
    }
