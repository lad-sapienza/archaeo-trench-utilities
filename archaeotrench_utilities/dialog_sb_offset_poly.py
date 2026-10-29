"""SectionBuilder — Create offset polygon dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QMessageBox, QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL
from .sb_project import PROJECT_VAR_SECTION_NAME

PROJECT_VAR_OFFSET = "sb_offset_poly_offset"


class SbOffsetPolyDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("Section Builder — Create offset polygon")
        self.setMinimumWidth(400)
        self._section_name: str | None = None
        self._build_ui()

    def _build_ui(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils
        from .sb_generate import _open_table
        from .sb_project import get_section_gpkg

        layout = QVBoxLayout(self)
        scope = QgsExpressionContextUtils.projectScope(QgsProject.instance())
        self._section_name = scope.variable(PROJECT_VAR_SECTION_NAME)

        form = QFormLayout()
        form.addRow("Section:", QLabel(self._section_name or "— not initialised —"))

        # Selection count
        n_selected = 0
        gpkg_path = get_section_gpkg(self._section_name)
        if gpkg_path:
            try:
                ln_layer = _open_table(gpkg_path, "sb_section_ln")
                n_selected = ln_layer.selectedFeatureCount()
            except RuntimeError:
                pass
        self._sel_label = QLabel(
            f"{n_selected} segment(s) selected in sb_section_ln"
        )
        form.addRow("Selection:", self._sel_label)

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setDecimals(3)
        self._offset_spin.setRange(0.001, 100.0)
        self._offset_spin.setSingleStep(0.1)
        self._offset_spin.setSuffix(" m")
        self._offset_spin.setValue(0.5)
        saved = scope.variable(PROJECT_VAR_OFFSET)
        if saved:
            try:
                self._offset_spin.setValue(float(saved))
            except (ValueError, TypeError):
                pass
        form.addRow("Downward offset:", self._offset_spin)
        layout.addLayout(form)

        info = QLabel(
            "For each selected segment in sb_section_ln, builds a closed polygon "
            "in sb_section_plg using the segment as the top edge and a copy "
            "shifted downward by the offset as the base.\n\n"
            "The part field is copied from the source segment. "
            "Polygons are appended — existing features are not removed."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Create polygon(s)")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils
        from . import sb_offset_poly
        from .sb_project import get_section_gpkg

        if not self._section_name:
            QMessageBox.warning(
                self, "No section",
                "No section is initialised in this project.\n"
                "Run 'Section Builder → New section…' first."
            )
            return

        gpkg_path = get_section_gpkg(self._section_name)
        if gpkg_path is None:
            QMessageBox.critical(
                self, "GeoPackage not found",
                "Could not locate the section GeoPackage.\n"
                "Run 'Section Builder → New section…' first."
            )
            return

        try:
            stats = sb_offset_poly.create_offset_polygons(
                gpkg_path, self._offset_spin.value()
            )
        except RuntimeError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        QgsExpressionContextUtils.setProjectVariable(
            QgsProject.instance(), PROJECT_VAR_OFFSET,
            str(self._offset_spin.value()))

        msg = f"{stats['n_written']} polygon(s) written to sb_section_plg."
        if stats["n_skipped"]:
            msg += f"\n{stats['n_skipped']} segment(s) skipped (empty geometry)."
        QMessageBox.information(self, "Done", msg)
        self.accept()
