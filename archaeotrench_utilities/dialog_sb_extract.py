"""SectionBuilder — Extract profile dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout,
)

from .compat import (
    BTN_OK, BTN_CANCEL, MSGBOX_YES, MSGBOX_NO, HORIZONTAL,
    ITEM_USER_CHECKABLE, ITEM_ENABLED, CHECKED, UNCHECKED,
)
from .sb_project import PROJECT_VAR_DEMS, PROJECT_VAR_SECTION_NAME

PROJECT_VAR_INTERVAL = "sb_sample_interval"


class SbExtractDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("Section Builder — Extract profile")
        self.setMinimumWidth(420)
        self._section_name: str | None = None
        self._build_ui()

    def _build_ui(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils

        layout = QVBoxLayout(self)
        scope = QgsExpressionContextUtils.projectScope(QgsProject.instance())
        self._section_name = scope.variable(PROJECT_VAR_SECTION_NAME)

        form = QFormLayout()
        form.addRow("Section:", QLabel(self._section_name or "— not initialised —"))

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setDecimals(3)
        self._interval_spin.setRange(0.001, 100.0)
        self._interval_spin.setSingleStep(0.01)
        self._interval_spin.setSuffix(" m")
        self._interval_spin.setValue(0.05)
        saved_interval = scope.variable(PROJECT_VAR_INTERVAL)
        if saved_interval:
            try:
                self._interval_spin.setValue(float(saved_interval))
            except (ValueError, TypeError):
                pass
        form.addRow("Sampling interval:", self._interval_spin)

        layout.addLayout(form)

        layout.addWidget(QLabel("DEM layers to sample (one per stratum):"))
        self._dem_list = QListWidget()
        layout.addWidget(self._dem_list)
        self._populate_dem_list()

        info = QLabel(
            "All selected DEMs are sampled at the same stations along the "
            "profile line, so the resulting profiles are vertically comparable. "
            "Stations outside a DEM's extent are skipped for that DEM."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Extract")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_dem_list(self):
        from qgis.core import QgsProject, QgsRasterLayer, QgsExpressionContextUtils

        scope = QgsExpressionContextUtils.projectScope(QgsProject.instance())
        saved = scope.variable(PROJECT_VAR_DEMS)
        saved_names = set(saved.split(";")) if saved else set()

        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsRasterLayer):
                continue
            item = QListWidgetItem(layer.name())
            item.setFlags(ITEM_USER_CHECKABLE | ITEM_ENABLED)
            item.setCheckState(CHECKED if layer.name() in saved_names else UNCHECKED)
            self._dem_list.addItem(item)

    def _checked_dems(self) -> list:
        return [
            self._dem_list.item(i).text()
            for i in range(self._dem_list.count())
            if self._dem_list.item(i).checkState() == CHECKED
        ]

    def _on_ok(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils
        from . import sb_project, sb_extract

        if not self._section_name:
            QMessageBox.warning(
                self, "No section",
                "No section is initialised in this project.\n"
                "Run 'Section Builder → New section…' first."
            )
            return

        dem_names = self._checked_dems()
        if not dem_names:
            if not self._dem_list.count():
                QMessageBox.warning(
                    self, "No DEM",
                    "No raster layers are loaded in the current project."
                )
            else:
                QMessageBox.warning(
                    self, "No DEM selected",
                    "Check at least one DEM layer to sample."
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
            conflicts = sb_extract.existing_dem_sources(gpkg_path) & set(dem_names)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Extraction failed", str(exc))
            return

        if conflicts:
            answer = QMessageBox.question(
                self, "Replace existing profiles?",
                "sb_profile_pts_raw already contains profiles for:\n\n"
                + "\n".join(f"  • {c}" for c in sorted(conflicts))
                + "\n\nThese will be replaced (rows of other DEMs are kept, "
                "including any 'part' classification). Continue?",
                MSGBOX_YES | MSGBOX_NO, MSGBOX_NO,
            )
            if answer != MSGBOX_YES:
                return

        try:
            n_stations, counts = sb_extract.extract_profiles(
                gpkg_path, dem_names, self._interval_spin.value()
            )
        except RuntimeError as exc:
            QMessageBox.critical(self, "Extraction failed", str(exc))
            return

        project = QgsProject.instance()
        QgsExpressionContextUtils.setProjectVariable(
            project, PROJECT_VAR_DEMS, ";".join(dem_names))
        QgsExpressionContextUtils.setProjectVariable(
            project, PROJECT_VAR_INTERVAL, str(self._interval_spin.value()))

        summary = "\n".join(
            f"  • {name}: {counts[name]} points"
            + ("" if counts[name] == n_stations
               else f"  ({n_stations - counts[name]} stations skipped)")
            for name in dem_names
        )
        QMessageBox.information(
            self, "Profile extracted",
            f"{n_stations} stations sampled along the profile line.\n\n{summary}\n\n"
            "Points written to sb_profile_pts_raw (backup) and "
            "sb_profile_pts (working copy)."
        )
        self.accept()
