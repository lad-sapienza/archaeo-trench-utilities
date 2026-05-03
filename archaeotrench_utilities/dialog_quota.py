"""Auto-elevation activation dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QMessageBox, QSpinBox, QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL
from .quota import PROJECT_VAR_DEM, PROJECT_VAR_ELEV, PROJECT_VAR_FIELD, PROJECT_VAR_DECIMALS


class QuotaDialog(QDialog):
    def __init__(self, quota_manager, parent=None):
        super().__init__(parent)
        self._manager = quota_manager
        self.setWindowTitle("ArchaeoTrench — Auto-elevation")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._elev_combo = QComboBox()
        self._elev_combo.currentIndexChanged.connect(self._on_elev_layer_changed)
        form.addRow("Elevation layer:", self._elev_combo)

        self._field_combo = QComboBox()
        form.addRow("Elevation field:", self._field_combo)

        self._dem_combo = QComboBox()
        form.addRow("DEM raster layer:", self._dem_combo)

        self._decimals_spin = QSpinBox()
        self._decimals_spin.setMinimum(0)
        self._decimals_spin.setMaximum(10)
        self._decimals_spin.setValue(2)
        form.addRow("Decimal places:", self._decimals_spin)

        layout.addLayout(form)

        info = QLabel(
            "When activated, the selected field will be automatically sampled "
            "from the DEM whenever a point is added or moved."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Activate")
        buttons.accepted.connect(self._on_activate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate_elev_layers()
        self._populate_dem_layers()

    # ------------------------------------------------------------------
    # Population helpers
    # ------------------------------------------------------------------

    def _populate_elev_layers(self):
        from qgis.core import QgsProject, QgsVectorLayer, QgsExpressionContextUtils

        self._elev_combo.blockSignals(True)
        self._elev_combo.clear()
        project = QgsProject.instance()
        saved_layer = QgsExpressionContextUtils.projectScope(project).variable(PROJECT_VAR_ELEV)

        for layer in project.mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                self._elev_combo.addItem(layer.name(), layer.id())

        if saved_layer:
            idx = self._elev_combo.findText(saved_layer)
            if idx >= 0:
                self._elev_combo.setCurrentIndex(idx)

        self._elev_combo.blockSignals(False)
        self._populate_elev_fields()

    def _populate_elev_fields(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils
        from qgis.PyQt.QtCore import QVariant

        self._field_combo.clear()
        layer_id = self._elev_combo.currentData()
        if not layer_id:
            return

        project = QgsProject.instance()
        layer = project.mapLayer(layer_id)
        if not layer:
            return

        saved_field = QgsExpressionContextUtils.projectScope(project).variable(PROJECT_VAR_FIELD)

        numeric_types = {QVariant.Double, QVariant.Int, QVariant.LongLong, QVariant.UInt, QVariant.ULongLong}
        for field in layer.fields():
            if field.type() in numeric_types and field.name().lower() != "fid":
                self._field_combo.addItem(field.name())

        if saved_field:
            idx = self._field_combo.findText(saved_field)
            if idx >= 0:
                self._field_combo.setCurrentIndex(idx)

        # Restore decimals
        saved_dec = QgsExpressionContextUtils.projectScope(project).variable(PROJECT_VAR_DECIMALS)
        if saved_dec:
            try:
                self._decimals_spin.setValue(int(saved_dec))
            except (ValueError, TypeError):
                pass

    def _populate_dem_layers(self):
        from qgis.core import QgsProject, QgsRasterLayer, QgsExpressionContextUtils

        self._dem_combo.clear()
        project = QgsProject.instance()
        saved = QgsExpressionContextUtils.projectScope(project).variable(PROJECT_VAR_DEM)

        for layer in project.mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                self._dem_combo.addItem(layer.name())

        if saved:
            idx = self._dem_combo.findText(saved)
            if idx >= 0:
                self._dem_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_elev_layer_changed(self):
        self._populate_elev_fields()

    def _on_activate(self):
        elev_name  = self._elev_combo.currentText()
        field_name = self._field_combo.currentText()
        dem_name   = self._dem_combo.currentText()
        decimals   = self._decimals_spin.value()

        if not elev_name:
            QMessageBox.warning(self, "No layer", "No vector layers found in the project.")
            return
        if not field_name:
            QMessageBox.warning(self, "No field", "No numeric fields found in the selected layer.")
            return
        if not dem_name:
            QMessageBox.warning(self, "No DEM", "No raster layers are loaded in the current project.")
            return

        ok = self._manager.activate(dem_name, elev_name, field_name, decimals)
        if ok:
            QMessageBox.information(
                self, "Auto-elevation active",
                f"Sampling <b>{dem_name}</b> → "
                f"<b>{elev_name}</b> / <b>{field_name}</b> "
                f"(rounded to {decimals} decimal places)"
            )
            self.accept()
