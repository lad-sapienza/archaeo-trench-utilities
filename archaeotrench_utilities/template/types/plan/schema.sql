-- template_version: 2026-05-02

-- layer: elevations
-- geometry: POINT
-- crs: EPSG:6870
-- geometry_column: geom
CREATE TABLE elevations (
    elevation REAL,
    context TEXT(20)
);

-- layer: contexts
-- geometry: POLYGON
-- crs: EPSG:6870
-- geometry_column: geom
CREATE TABLE contexts (
    context TEXT(30),
    context_type TEXT(100)
);

-- layer: detail
-- geometry: POLYGON
-- crs: EPSG:6870
-- geometry_column: geom
CREATE TABLE detail (
    context TEXT(30),
    material TEXT(255)
);

-- layer: elev_change
-- geometry: LINESTRING
-- crs: EPSG:6870
-- geometry_column: geometry
CREATE TABLE elev_change (
    context TEXT(30)
);

-- layer: limits
-- geometry: POLYGON
-- crs: EPSG:6870
-- geometry_column: geom
CREATE TABLE limits (
    trench TEXT(30)
);
