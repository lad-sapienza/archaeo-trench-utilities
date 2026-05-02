"""Auto-elevation activation dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QMessageBox, QVBoxLayout, QComboBox,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL
from .quota import QUOTA_FIELD_NAME, PROJECT_VAR_DEM, PROJECT_VAR_ELEV


class QuotaDialog(QDialog):
    def __init__(self, quota_manager, parent=None):
        super().__init__(parent)
        self._manager = quota_manager
        self.setWindowTitle("ArchaeoTrench — Auto-elevation")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._elev_combo = QComboBox()
        self._populate_elev_layers()
        form.addRow("Elevation layer:", self._elev_combo)

        form.addRow("Elevation field:", QLabel(f"<b>{QUOTA_FIELD_NAME}</b>"))

        self._dem_combo = QComboBox()
        self._populate_dem_layers()
        form.addRow("DEM raster layer:", self._dem_combo)

        layout.addLayout(form)

        info = QLabel(
            "When activated, the <b>elevation</b> field of the selected layer "
            "will be automatically sampled from the DEM whenever a point is "
            "added or moved."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Activate")
        buttons.accepted.connect(self._on_activate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_elev_layers(self):
        """Populate with all vector layers that have an 'elevation' field."""
        from qgis.core import QgsProject, QgsVectorLayer, QgsExpressionContextUtils

        self._elev_combo.clear()
        project = QgsProject.instance()

        # Restore previously saved selection
        saved = QgsExpressionContextUtils.projectScope(project).variable(PROJECT_VAR_ELEV)

        for layer in project.mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            if layer.fields().indexOf(QUOTA_FIELD_NAME) >= 0:
                self._elev_combo.addItem(layer.name(), layer.id())

        if saved:
            idx = self._elev_combo.findText(saved)
            if idx >= 0:
                self._elev_combo.setCurrentIndex(idx)

    def _populate_dem_layers(self):
        """Populate with all raster layers in the project."""
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

    def _on_activate(self):
        elev_name = self._elev_combo.currentText()
        dem_name  = self._dem_combo.currentText()

        if not elev_name:
            QMessageBox.warning(
                self, "No elevation layer",
                f"No vector layers with an '{QUOTA_FIELD_NAME}' field found in the project."
            )
            return
        if not dem_name:
            QMessageBox.warning(
                self, "No DEM",
                "No raster layers are loaded in the current project."
            )
            return

        ok = self._manager.activate(dem_name, elev_name)
        if ok:
            QMessageBox.information(
                self, "Auto-elevation active",
                f"Sampling <b>{dem_name}</b> → writing to <b>{elev_name}</b> / {QUOTA_FIELD_NAME}"
            )
            self.accept()
