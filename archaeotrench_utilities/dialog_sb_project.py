"""SectionBuilder — New section dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, MSGBOX_YES, MSGBOX_NO, HORIZONTAL
from .sb_project import PROJECT_VAR_SECTION_NAME


class SbProjectDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("Section Builder — New section")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils
        from qgis.gui import QgsProjectionSelectionWidget

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. F5-07")
        saved_name = QgsExpressionContextUtils.projectScope(
            QgsProject.instance()
        ).variable(PROJECT_VAR_SECTION_NAME)
        if saved_name:
            self._name_edit.setText(saved_name)
        form.addRow("Section name:", self._name_edit)

        # Nominal CRS for the local section space — must be projected (metres)
        # so that the section view and measure tools work in metres.
        self._crs_widget = QgsProjectionSelectionWidget()
        project_crs = QgsProject.instance().crs()
        if project_crs.isValid() and not project_crs.isGeographic():
            self._crs_widget.setCrs(project_crs)
        form.addRow("Section CRS:", self._crs_widget)

        layout.addLayout(form)

        info = QLabel(
            "Creates sb_* tables in the project GeoPackage (vectors.gpkg if present, "
            "otherwise {name}.gpkg) and adds all section layers to the current project.\n\n"
            "Section CRS is nominal: section coordinates are local "
            "(x = distance along the line, y = elevation). Pick any projected CRS "
            "in metres — the project CRS is usually fine.\n\n"
            "The DEM layers to sample are selected later, in Extract profile… — "
            "a section may cut multiple strata, each with its own DEM."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Initialise")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self):
        section_name = self._name_edit.text().strip()

        if not section_name:
            QMessageBox.warning(self, "Input required", "Please enter a section name.")
            return

        section_crs = self._crs_widget.crs()
        if not section_crs.isValid() or section_crs.isGeographic():
            QMessageBox.warning(
                self, "Invalid CRS",
                "Please select a projected CRS (units in metres).\n"
                "A geographic CRS would render the section space in degrees."
            )
            return

        from . import sb_project as sb

        try:
            gpkg_path = sb.resolve_gpkg_path(section_name)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Initialisation failed", str(exc))
            return

        existing = sb.existing_sb_tables(gpkg_path)
        if existing:
            answer = QMessageBox.question(
                self, "Replace existing section?",
                f"The GeoPackage already contains section tables:\n\n"
                + "\n".join(f"  • {t}" for t in existing)
                + "\n\nThey will be DROPPED and recreated. All extracted "
                "profiles, classifications and drawn geometries in these "
                "tables will be lost. Continue?",
                MSGBOX_YES | MSGBOX_NO, MSGBOX_NO,
            )
            if answer != MSGBOX_YES:
                return

        try:
            gpkg_path = sb.init_section(section_name, section_crs)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Initialisation failed", str(exc))
            return

        QMessageBox.information(
            self,
            "Section initialised",
            f"Section layers added to project.\nGeoPackage: {gpkg_path}",
        )
        self.accept()
