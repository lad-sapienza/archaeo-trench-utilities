"""SectionBuilder — section segment generation for ArchaeoTrench Utilities.

Builds section linestrings (sb_section_ln) from the points of
sb_profile_pts. The WHOLE profile is drawn: consecutive points sharing the
same 'part' value — including NULL, i.e. unclassified — become one
linestring, with run-length grouping done per dem_source so that profiles
of different strata never mix.

Continuity rules:
  - where two runs meet, the boundary vertex is shared (the next run starts
    at the last point of the previous one), so the drawn profile has no
    gaps at classification boundaries;
  - a lin_x jump larger than 1.5× the median point spacing breaks the line
    even within one part — these are real gaps (DEM nodata, deleted noise
    points) and must stay open.

sb_section_ln is fully derived data: every run regenerates it from scratch.

Geometries are written in the local section space (x = lin_x, y = elev),
same nominal CRS as sb_profile_pts — see the sb_project docstring.
"""

from __future__ import annotations

from pathlib import Path
from statistics import median

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
)

from .sb_extract import _is_null, _open_table, _refresh

# A lin_x jump beyond this multiple of the median spacing is a real gap.
_GAP_FACTOR = 1.5


def _split_runs(points: list) -> list:
    """Split one DEM's points into runs of constant part.

    points: [(lin_x, elev, part_or_None, fid), …] sorted by (lin_x, fid).
    Returns [(part_or_None, [(lin_x, elev), …]), …].

    Runs break where part changes (sharing the boundary vertex) and at
    lin_x jumps larger than _GAP_FACTOR × median spacing (no sharing).
    """
    diffs = [
        b[0] - a[0]
        for a, b in zip(points, points[1:])
        if b[0] - a[0] > 0
    ]
    gap_threshold = _GAP_FACTOR * median(diffs) if diffs else float("inf")

    runs = []
    current_part = points[0][2]
    current_run = [(points[0][0], points[0][1])]
    prev = points[0]

    for pt in points[1:]:
        lin_x, elev, part, _fid = pt
        if lin_x - prev[0] > gap_threshold:
            # real gap: close without sharing the vertex
            runs.append((current_part, current_run))
            current_part = part
            current_run = [(lin_x, elev)]
        elif part != current_part:
            # classification boundary: share the vertex for continuity
            runs.append((current_part, current_run))
            current_part = part
            current_run = [(prev[0], prev[1]), (lin_x, elev)]
        else:
            current_run.append((lin_x, elev))
        prev = pt

    runs.append((current_part, current_run))
    return runs


def generate_segments(gpkg_path: Path) -> dict:
    """Regenerate sb_section_ln from the current sb_profile_pts.

    Returns a stats dict:
        segments       — list of (dem_source, part_or_None, n_points) written
        skipped_single — number of 1-point runs skipped
        unclassified   — number of points with NULL part (drawn, but unlabelled)
        total_points   — total points read from sb_profile_pts

    Raises RuntimeError on any precondition failure.
    """
    pts_layer = _open_table(gpkg_path, "sb_profile_pts")
    ln_layer  = _open_table(gpkg_path, "sb_section_ln")

    for layer in (pts_layer, ln_layer):
        if layer.isEditable():
            raise RuntimeError(
                f"Layer '{layer.name()}' is in editing mode.\n"
                "Toggle editing off before generating segments."
            )

    # Collect ALL points grouped by dem_source (part NULL included)
    by_dem: dict = {}
    total_points = 0
    unclassified = 0
    for f in pts_layer.getFeatures():
        total_points += 1
        part = None if _is_null(f["part"]) else str(f["part"])
        if part is None:
            unclassified += 1
        dem = "" if _is_null(f["dem_source"]) else str(f["dem_source"])
        by_dem.setdefault(dem, []).append(
            (float(f["lin_x"]), float(f["elev"]), part, f.id())
        )

    if total_points == 0:
        raise RuntimeError(
            "sb_profile_pts is empty.\n"
            "Run 'Section Builder → Extract profile…' first."
        )

    fields = ln_layer.fields()
    feats = []
    segments = []
    skipped_single = 0
    for dem in sorted(by_dem):
        points = sorted(by_dem[dem], key=lambda t: (t[0], t[3]))
        for part, run in _split_runs(points):
            if len(run) < 2:
                skipped_single += 1
                continue
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(x, y) for x, y in run]
            ))
            f.setAttribute(fields.indexOf("part"), part)
            f.setAttribute(fields.indexOf("dem_source"), dem or None)
            feats.append(f)
            segments.append((dem, part, len(run)))

    # Full rebuild: sb_section_ln is derived data
    provider = ln_layer.dataProvider()
    if not provider.truncate():
        old_ids = [f.id() for f in ln_layer.getFeatures()]
        if old_ids and not provider.deleteFeatures(old_ids):
            raise RuntimeError("Could not clear the old features of sb_section_ln.")
    if feats:
        ok, _ = provider.addFeatures(feats)
        if not ok:
            raise RuntimeError("Could not write the new segments to sb_section_ln.")
    _refresh(ln_layer)

    return {
        "segments": segments,
        "skipped_single": skipped_single,
        "unclassified": unclassified,
        "total_points": total_points,
    }
