"""SectionBuilder — profile extraction for ArchaeoTrench Utilities.

Samples one or more DEMs along the useful segments of sb_section_line and
writes elevation points to sb_profile_pts_raw and sb_profile_pts.

All selected DEMs are sampled at the SAME lin_x stations so that profiles
of different strata are vertically comparable. Sampling is done at a regular
interval with QgsRasterDataProvider.identify() rather than QgsProfileRequest:
the profile API generates per-layer stations and cannot guarantee alignment
across DEMs (and it requires QGIS 3.26+, while the plugin supports 3.16).

lin_x is the cumulative distance along included segments only — jog segments
(exclude_from_profile = 1) contribute nothing to the X axis. Segment endpoints
are always sampled, so consecutive unfolded segments share a lin_x boundary
station (same lin_x, different plan coordinates: the unfold line).

Stations where a DEM has nodata or no coverage produce NO row for that DEM:
profiles have natural gaps and generated segments will break there.

Point geometries are written in the local section space (x = lin_x, y = elev)
with the EPSG:4326 placeholder CRS — see the sb_project docstring.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)

from .compat import raster_identify_format_value


def _is_null(val) -> bool:
    """True for NULL attribute values (None, invalid QVariant, qgis NULL)."""
    return val is None or str(val) in ("NULL", "")


# ---------------------------------------------------------------------------
# Layer access
# ---------------------------------------------------------------------------

def _open_table(gpkg_path: Path, table: str) -> QgsVectorLayer:
    """Return the project's loaded instance of a sb_* table if present,
    otherwise open a fresh handle. Raises RuntimeError if the table is missing."""
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


def existing_dem_sources(gpkg_path: Path) -> set:
    """Return the set of dem_source values already present in sb_profile_pts_raw."""
    layer = _open_table(gpkg_path, "sb_profile_pts_raw")
    sources = set()
    for f in layer.getFeatures():
        val = f["dem_source"]
        if not _is_null(val):
            sources.add(str(val))
    return sources


# ---------------------------------------------------------------------------
# Section line reading
# ---------------------------------------------------------------------------

def _read_segments(line_layer: QgsVectorLayer) -> list:
    """Return [(order_key, QgsGeometry), …] of included segments, in section order.

    The 'id' field is an optional ordering override: if NO included segment
    has it set, drawing order (fid) is used; if ALL have it, id order is used.
    A mix of the two is ambiguous and raises RuntimeError, as does an empty
    segment list.
    """
    with_id, without_id = [], []
    for f in line_layer.getFeatures():
        if f["exclude_from_profile"] == 1:
            continue
        geom = f.geometry()
        if geom is None or geom.isNull() or geom.length() <= 0:
            continue
        seg_id = f["id"]
        if _is_null(seg_id):
            without_id.append((f.id(), QgsGeometry(geom)))
        else:
            with_id.append((int(seg_id), QgsGeometry(geom)))

    if not with_id and not without_id:
        raise RuntimeError(
            "No usable segments found in sb_section_line.\n"
            "Draw the profile polyline first (and check that not every "
            "segment is marked exclude_from_profile = 1)."
        )

    if with_id and without_id:
        raise RuntimeError(
            "Some segments of sb_section_line have an 'id' and some do not.\n"
            "Either fill 'id' on every included segment, or leave it empty "
            "everywhere (drawing order will be used)."
        )

    segments = with_id or without_id
    segments.sort(key=lambda t: t[0])
    return segments


def _stations(length: float, interval: float) -> list:
    """Regular sampling distances along one segment, endpoint always included."""
    n = int(length / interval)
    pts = [i * interval for i in range(n + 1)]
    if length - pts[-1] > 1e-9:
        pts.append(length)
    return pts


# ---------------------------------------------------------------------------
# DEM sampling
# ---------------------------------------------------------------------------

class _DemSampler:
    """Samples one DEM, with the line→DEM coordinate transform built once."""

    def __init__(self, dem_layer: QgsRasterLayer, line_crs):
        self._provider = dem_layer.dataProvider()
        self._format = raster_identify_format_value()
        self._nodata = self._provider.sourceNoDataValue(1)
        self._transform = None
        if line_crs != dem_layer.crs():
            self._transform = QgsCoordinateTransform(
                line_crs, dem_layer.crs(), QgsProject.instance())

    def sample(self, point: QgsPointXY) -> float | None:
        """Return the DEM value at a plan point, or None for nodata / no coverage."""
        if self._transform:
            point = self._transform.transform(point)
        result = self._provider.identify(point, self._format)
        if not result.isValid():
            return None
        value = result.results().get(1)
        if value is None or value == self._nodata:
            return None
        return float(value)


# ---------------------------------------------------------------------------
# Feature writing
# ---------------------------------------------------------------------------

def _delete_source_rows(layer: QgsVectorLayer, sources: set) -> None:
    ids = [
        f.id() for f in layer.getFeatures()
        if not _is_null(f["dem_source"]) and str(f["dem_source"]) in sources
    ]
    if ids:
        if not layer.dataProvider().deleteFeatures(ids):
            raise RuntimeError(f"Could not delete old rows from {layer.name()}.")


def _insert_rows(layer: QgsVectorLayer, rows: list) -> None:
    """rows: list of dicts with lin_x, geo_x, geo_y, elev, dem_source."""
    fields = layer.fields()
    feats = []
    for r in rows:
        f = QgsFeature(fields)
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(r["lin_x"], r["elev"])))
        for name in ("lin_x", "geo_x", "geo_y", "elev", "dem_source"):
            f.setAttribute(fields.indexOf(name), r[name])
        feats.append(f)
    ok, _ = layer.dataProvider().addFeatures(feats)
    if not ok:
        raise RuntimeError(f"Could not write profile points to {layer.name()}.")


def _refresh(layer: QgsVectorLayer) -> None:
    layer.reload()
    layer.triggerRepaint()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_profiles(
    gpkg_path: Path,
    dem_names: list,
    interval: float,
) -> tuple:
    """Extract elevation profiles for all DEMs in dem_names.

    Any rows of those dem_sources already present in sb_profile_pts_raw /
    sb_profile_pts are replaced; rows of other dem_sources (and any 'part'
    classification on them) are left untouched. The caller is expected to
    have asked the user for confirmation (see existing_dem_sources()).

    Returns (n_stations, {dem_name: n_points_written}).
    Raises RuntimeError on any precondition failure.
    """
    if interval <= 0:
        raise RuntimeError("Sampling interval must be positive.")

    project = QgsProject.instance()

    line_layer = _open_table(gpkg_path, "sb_section_line")
    raw_layer  = _open_table(gpkg_path, "sb_profile_pts_raw")
    pts_layer  = _open_table(gpkg_path, "sb_profile_pts")

    for layer in (raw_layer, pts_layer):
        if layer.isEditable():
            raise RuntimeError(
                f"Layer '{layer.name()}' is in editing mode.\n"
                "Toggle editing off before extracting."
            )

    segments = _read_segments(line_layer)

    samplers = {}
    for name in dem_names:
        dem_candidates = [
            l for l in project.mapLayersByName(name)
            if isinstance(l, QgsRasterLayer)
        ]
        if not dem_candidates:
            raise RuntimeError(f"DEM raster layer '{name}' not found in the project.")
        samplers[name] = _DemSampler(dem_candidates[0], line_layer.crs())

    # Sample all DEMs at the same stations
    rows_per_dem = {name: [] for name in dem_names}
    n_stations = 0
    offset = 0.0
    for _seg_id, geom in segments:
        seg_len = geom.length()
        for d in _stations(seg_len, interval):
            point = geom.interpolate(d).asPoint()
            plan_pt = QgsPointXY(point)
            lin_x = offset + d
            n_stations += 1
            for name, sampler in samplers.items():
                elev = sampler.sample(plan_pt)
                if elev is None:
                    continue   # nodata / outside extent → no row, natural gap
                rows_per_dem[name].append({
                    "lin_x": lin_x,
                    "geo_x": plan_pt.x(),
                    "geo_y": plan_pt.y(),
                    "elev":  elev,
                    "dem_source": name,
                })
        offset += seg_len

    replaced = set(dem_names)
    all_rows = [r for rows in rows_per_dem.values() for r in rows]

    _delete_source_rows(raw_layer, replaced)
    _insert_rows(raw_layer, all_rows)
    _refresh(raw_layer)

    _delete_source_rows(pts_layer, replaced)
    _insert_rows(pts_layer, all_rows)
    _refresh(pts_layer)

    return n_stations, {name: len(rows) for name, rows in rows_per_dem.items()}
