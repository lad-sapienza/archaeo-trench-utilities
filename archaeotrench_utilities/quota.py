"""Auto-elevation logic for ArchaeoTrench Utilities.

Samples a DEM raster and writes the result to the `elevation` field of a
user-selected vector layer whenever a point is added or moved.
"""

from __future__ import annotations

QUOTA_FIELD_NAME = "elevation"
PROJECT_VAR_DEM   = "at_dem_layer"
PROJECT_VAR_ELEV  = "at_elevation_layer"


class QuotaManager:
    """Manages automatic DEM sampling for a selected elevations layer."""

    def __init__(self, iface):
        self._iface = iface
        self._elevations_layer = None
        self._dem_layer = None
        self._connected = False
        from qgis.core import QgsProject
        QgsProject.instance().readProject.connect(self._on_project_loaded)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate(self, dem_layer_name: str, elev_layer_name: str) -> bool:
        """Activate auto-elevation.

        Args:
            dem_layer_name:  Name of the raster DEM layer to sample from.
            elev_layer_name: Name of the vector layer to write elevation into.

        Both names are persisted as project variables so the connection
        survives save/load cycles.  Returns True on success.
        """
        from qgis.core import QgsProject, QgsExpressionContextUtils

        project = QgsProject.instance()

        # Locate the target elevation vector layer
        elev_layers = project.mapLayersByName(elev_layer_name)
        if not elev_layers:
            self._iface.messageBar().pushWarning(
                "ArchaeoTrench", f"Layer '{elev_layer_name}' not found in project."
            )
            return False
        self._elevations_layer = elev_layers[0]

        # Locate the DEM raster layer
        dem_layers = project.mapLayersByName(dem_layer_name)
        if not dem_layers:
            self._iface.messageBar().pushWarning(
                "ArchaeoTrench", f"DEM layer '{dem_layer_name}' not found in project."
            )
            return False
        self._dem_layer = dem_layers[0]

        # Persist both selections
        QgsExpressionContextUtils.setProjectVariable(project, PROJECT_VAR_DEM,  dem_layer_name)
        QgsExpressionContextUtils.setProjectVariable(project, PROJECT_VAR_ELEV, elev_layer_name)

        self._connect_signals()
        return True

    def deactivate(self):
        """Disconnect signals and clear state."""
        self._disconnect_signals()
        self._elevations_layer = None
        self._dem_layer = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _connect_signals(self):
        if not self._elevations_layer:
            return
        self._disconnect_signals()
        self._elevations_layer.featureAdded.connect(self._on_feature_added)
        self._elevations_layer.geometryChanged.connect(self._on_geometry_changed)
        self._connected = True

    def _disconnect_signals(self):
        if self._connected and self._elevations_layer:
            try:
                self._elevations_layer.featureAdded.disconnect(self._on_feature_added)
                self._elevations_layer.geometryChanged.disconnect(self._on_geometry_changed)
            except Exception:
                pass
        self._connected = False

    def _on_project_loaded(self):
        """Re-connect after project load if both variables are set."""
        from qgis.core import QgsProject, QgsExpressionContextUtils
        scope = QgsExpressionContextUtils.projectScope(QgsProject.instance())
        dem_name  = scope.variable(PROJECT_VAR_DEM)
        elev_name = scope.variable(PROJECT_VAR_ELEV)
        if dem_name and elev_name:
            self.activate(dem_name, elev_name)

    def _on_feature_added(self, fid: int):
        if not self._elevations_layer:
            return
        feature = self._elevations_layer.getFeature(fid)
        if feature.isValid():
            self._write_elevation(fid, feature.geometry())

    def _on_geometry_changed(self, fid: int, geom):
        self._write_elevation(fid, geom)

    def _write_elevation(self, fid: int, geom):
        if not self._dem_layer or geom.isNull():
            return

        elevation = self._sample_dem(geom)
        if elevation is None:
            self._iface.messageBar().pushWarning(
                "ArchaeoTrench",
                f"Point fid={fid} is outside the DEM extent or has no-data — elevation not written."
            )
            return

        layer = self._elevations_layer
        field_idx = layer.fields().indexOf(QUOTA_FIELD_NAME)
        if field_idx < 0:
            return

        layer.beginEditCommand("Auto-elevation")
        layer.changeAttributeValue(fid, field_idx, round(float(elevation), 2))
        layer.endEditCommand()

    def _sample_dem(self, geom) -> float | None:
        """Sample the DEM at the point geometry. Returns None if outside/nodata."""
        from qgis.core import (
            QgsPointXY, QgsCoordinateTransform, QgsProject,
            QgsRasterDataProvider
        )

        point = geom.asPoint()
        if not point:
            return None

        src_crs = self._elevations_layer.crs()
        dem_crs = self._dem_layer.crs()
        if src_crs != dem_crs:
            transform = QgsCoordinateTransform(src_crs, dem_crs, QgsProject.instance())
            point = transform.transform(QgsPointXY(point))

        from .compat import raster_identify_format_value
        provider: QgsRasterDataProvider = self._dem_layer.dataProvider()
        result = provider.identify(QgsPointXY(point), raster_identify_format_value())

        if not result.isValid():
            return None

        value = result.results().get(1)
        if value is None:
            return None

        no_data = provider.sourceNoDataValue(1)
        if value == no_data:
            return None

        return float(value)
