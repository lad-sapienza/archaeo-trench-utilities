"""SectionBuilder — Populate elevation labels dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL
from .sb_project import PROJECT_VAR_SECTION_NAME


class SbElevationsDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("Section Builder — Populate elevation labels")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils

        layout = QVBoxLayout(self)
        self._section_name = QgsExpressionContextUtils.projectScope(
            QgsProject.instance()
        ).variable(PROJECT_VAR_SECTION_NAME)

        layout.addWidget(QLabel(
            f"Section: {self._section_name or '— not initialised —'}"
        ))

        info = QLabel(
            "Fills the 'elev' field of sb_section_elevations from the nearest "
            "profile point (2D distance: a label placed near a profile takes "
            "that profile's elevation, also with multiple overlapping strata).\n\n"
            "Only empty 'elev' values are filled — existing values are kept "
            "as manual overrides. Values are rounded to 2 decimals."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Populate")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self):
        from . import sb_project, sb_elevations

        if not self._section_name:
            QMessageBox.warning(
                self, "No section",
                "No section is initialised in this project.\n"
                "Run 'Section Builder → New section…' first."
            )
            return

        gpkg_path = sb_project.get_section_gpkg(self._section_name)
        if gpkg_path is None:
            QMessageBox.critical(
                self, "GeoPackage not found",
                "Could not locate the section GeoPackage.\n"
                "Run 'Section Builder → New section…' first."
            )
            return

        try:
            stats = sb_elevations.populate_labels(gpkg_path)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Population failed", str(exc))
            return

        msg = f"{stats['populated']} label(s) populated."
        if stats["skipped"]:
            msg += f"\n{stats['skipped']} label(s) already had a value — kept."
        QMessageBox.information(self, "Labels populated", msg)
        self.accept()
