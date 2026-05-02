MANUAL SETUP REQUIRED
=====================

Place the following files in this directory before using the plugin:

  vectors.gpkg  — Reference GeoPackage (plan view)
                   Schema: contexts (Polygon), detail (Polygon),
                           elev_change (LineString), elevations (Point),
                           limits (Polygon)
                   CRS: EPSG:6870 (ETRS89 / Albania TM 2010)

  template.qgs   — Reference QGIS project (plan view)
                   Must reference vectors.gpkg via relative path.
                   Layer tree: Gen group + c100 group as per spec.

These files are not distributed with the plugin source and must be
created in QGIS then placed here.
