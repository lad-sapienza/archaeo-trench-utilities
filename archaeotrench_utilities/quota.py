"""Auto-elevation logic for ArchaeoTrench Utilities.

Samples a DEM raster and writes the result to a user-selected numeric field
of a user-selected vector layer whenever a point is added or moved.

Layer references are never stored — only layer IDs (plain strings) are kept.
Layers are looked up from QgsProject on demand, which returns None safely
if the layer has been deleted.
"""

from __future__ import annotations

PROJECT_VAR_DEM      = "at_dem_layer"
PROJECT_VAR_ELEV     = "at_elevation_layer"
PROJECT_VAR_FIELD    = "at_elevation_field"
PROJECT_VAR_DECIMALS = "at_elevation_decimals"


class QuotaManager:
    """Manages automatic DEM sampling for a selected layer and field."""

    def __init__(self, iface):
        self._iface = iface
        self._elev_layer_id: str | None = None
        self._dem_layer_id:  str | None = None
        self._field_name: str = ""
        self._decimals: int = 2
        self._connected = False
        from qgis.core import QgsProject
        QgsProject.instance().readProject.connect(self._on_project_loaded)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate(
        self,
        dem_layer_name: str,
        elev_layer_name: str,
        field_name: str,
        decimals: int = 2,
    ) -> bool:
        """Activate auto-elevation. Returns True on success."""
        from qgis.core import QgsProject, QgsExpressionContextUtils

        project = QgsProject.instance()

        elev_layers = project.mapLayersByName(elev_layer_name)
        if not elev_layers:
            self._iface.messageBar().pushWarning(
                "ArchaeoTrench", f"Layer '{elev_layer_name}' not found in project."
            )
            return False

        elev_layer = elev_layers[0]
        if elev_layer.fields().indexOf(field_name) < 0:
            self._iface.messageBar().pushWarning(
                "ArchaeoTrench",
                f"Field '{field_name}' not found in layer '{elev_layer_name}'."
            )
            return False

        dem_layers = project.mapLayersByName(dem_layer_name)
        if not dem_layers:
            self._iface.messageBar().pushWarning(
                "ArchaeoTrench", f"DEM layer '{dem_layer_name}' not found in project."
            )
            return False

        self._disconnect_signals()

        # Store IDs only — never hold a direct layer reference
        self._elev_layer_id = elev_layer.id()
        self._dem_layer_id  = dem_layers[0].id()
        self._field_name    = field_name
        self._decimals      = decimals

        QgsExpressionContextUtils.setProjectVariable(project, PROJECT_VAR_DEM,      dem_layer_name)
        QgsExpressionContextUtils.setProjectVariable(project, PROJECT_VAR_ELEV,     elev_layer_name)
        QgsExpressionContextUtils.setProjectVariable(project, PROJECT_VAR_FIELD,    field_name)
        QgsExpressionContextUtils.setProjectVariable(project, PROJECT_VAR_DECIMALS, str(decimals))

        self._connect_signals()
        return True

    def deactivate(self):
        # Just clear state — no qgis.core access.
        # Signal handlers all guard on _elev_layer_id, so they become no-ops.
        # Qt disconnects signals automatically when layer objects are destroyed.
        self._connected     = False
        self._elev_layer_id = None
        self._dem_layer_id  = None
        self._field_name    = ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _elev_layer(self):
        """Look up the elevation layer by ID. Returns None if not found."""
        if not self._elev_layer_id:
            return None
        from qgis.core import QgsProject
        return QgsProject.instance().mapLayer(self._elev_layer_id)

    def _dem_layer(self):
        """Look up the DEM layer by ID. Returns None if not found."""
        if not self._dem_layer_id:
            return None
        from qgis.core import QgsProject
        return QgsProject.instance().mapLayer(self._dem_layer_id)

    def _connect_signals(self):
        layer = self._elev_layer()
        if not layer:
            return
        layer.featureAdded.connect(self._on_feature_added)
        layer.geometryChanged.connect(self._on_geometry_changed)
        self._connected = True

    def _disconnect_signals(self):
        """Disconnect signals. Safe to call even after the layer is deleted."""
        if not self._connected:
            self._connected = False
            return
        self._connected = False
        layer = self._elev_layer()  # returns None if already deleted — no crash
        if layer:
            try:
                layer.featureAdded.disconnect(self._on_feature_added)
                layer.geometryChanged.disconnect(self._on_geometry_changed)
            except Exception:
                pass

    def _on_project_loaded(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils
        scope = QgsExpressionContextUtils.projectScope(QgsProject.instance())
        dem_name   = scope.variable(PROJECT_VAR_DEM)
        elev_name  = scope.variable(PROJECT_VAR_ELEV)
        field_name = scope.variable(PROJECT_VAR_FIELD)
        decimals   = scope.variable(PROJECT_VAR_DECIMALS)
        if dem_name and elev_name and field_name:
            try:
                dec = int(decimals) if decimals else 2
            except (ValueError, TypeError):
                dec = 2
            self.activate(dem_name, elev_name, field_name, dec)

    def _on_feature_added(self, fid: int):
        layer = self._elev_layer()
        if not layer:
            return
        feature = layer.getFeature(fid)
        if feature.isValid():
            self._write_elevation(fid, feature.geometry())

    def _on_geometry_changed(self, fid: int, geom):
        self._write_elevation(fid, geom)

    def _write_elevation(self, fid: int, geom):
        if not self._field_name or geom.isNull():
            return
        dem = self._dem_layer()
        layer = self._elev_layer()
        if not dem or not layer:
            return

        elevation = self._sample_dem(geom, layer, dem)
        if elevation is None:
            self._iface.messageBar().pushWarning(
                "ArchaeoTrench",
                f"Point fid={fid} is outside the DEM extent or has no-data — elevation not written."
            )
            return

        field_idx = layer.fields().indexOf(self._field_name)
        if field_idx < 0:
            return

        layer.beginEditCommand("Auto-elevation")
        layer.changeAttributeValue(fid, field_idx, round(float(elevation), self._decimals))
        layer.endEditCommand()

    def _sample_dem(self, geom, elev_layer, dem_layer) -> float | None:
        from qgis.core import QgsPointXY, QgsCoordinateTransform, QgsProject

        point = geom.asPoint()
        if not point:
            return None

        src_crs = elev_layer.crs()
        dem_crs = dem_layer.crs()
        if src_crs != dem_crs:
            transform = QgsCoordinateTransform(src_crs, dem_crs, QgsProject.instance())
            point = transform.transform(QgsPointXY(point))

        from .compat import raster_identify_format_value
        provider = dem_layer.dataProvider()
        result = provider.identify(QgsPointXY(point), raster_identify_format_value())

        if not result.isValid():
            return None

        value = result.results().get(1)
        if value is None:
            return None

        if value == provider.sourceNoDataValue(1):
            return None

        return float(value)
