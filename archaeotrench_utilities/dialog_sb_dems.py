"""SectionBuilder — Manage DEMs dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

import json

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QVBoxLayout,
)

from .compat import (
    BTN_OK, BTN_CANCEL, HORIZONTAL,
    ITEM_USER_CHECKABLE, ITEM_ENABLED, CHECKED, UNCHECKED,
)
from .sb_project import PROJECT_VAR_REGISTERED_DEMS, PROJECT_VAR_SECTION_NAME


class SbDemsDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("Section Builder — Manage DEMs")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Select the raster layers to use as DEMs in this section.\n"
            "The checked layers will appear in the dem_layer dropdown when "
            "editing sb_annotations."
        ))

        self._dem_list = QListWidget()
        layout.addWidget(self._dem_list)
        self._populate_list()

        info = QLabel(
            "The selection is saved as project variable sb_registered_dems "
            "and applied immediately to the Annotations layer."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_list(self):
        from qgis.core import QgsProject, QgsRasterLayer, QgsExpressionContextUtils

        scope = QgsExpressionContextUtils.projectScope(QgsProject.instance())
        raw = scope.variable(PROJECT_VAR_REGISTERED_DEMS)
        try:
            saved_names = set(json.loads(raw)) if raw else set()
        except (ValueError, TypeError):
            saved_names = set()

        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsRasterLayer):
                continue
            item = QListWidgetItem(layer.name())
            item.setFlags(ITEM_USER_CHECKABLE | ITEM_ENABLED)
            item.setCheckState(CHECKED if layer.name() in saved_names else UNCHECKED)
            self._dem_list.addItem(item)

        if self._dem_list.count() == 0:
            self._dem_list.addItem(QListWidgetItem("— no raster layers in the project —"))

    def _checked_names(self) -> list:
        return [
            self._dem_list.item(i).text()
            for i in range(self._dem_list.count())
            if self._dem_list.item(i).checkState() == CHECKED
        ]

    def _on_ok(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils
        from . import sb_project

        checked = self._checked_names()

        project = QgsProject.instance()
        QgsExpressionContextUtils.setProjectVariable(
            project, PROJECT_VAR_REGISTERED_DEMS, json.dumps(checked))

        # Update the ValueMap widget on sb_annotations if available
        section_name = QgsExpressionContextUtils.projectScope(project).variable(
            PROJECT_VAR_SECTION_NAME)
        if section_name:
            gpkg = sb_project.get_section_gpkg(section_name)
            if gpkg:
                sb_project.configure_annotations_widget(gpkg)

        if checked:
            QMessageBox.information(
                self, "DEMs registered",
                f"{len(checked)} DEM(s) registered:\n"
                + "\n".join(f"  • {n}" for n in checked)
                + "\n\nThe dem_layer dropdown on Annotations is now updated.",
            )
        else:
            QMessageBox.information(
                self, "DEMs cleared",
                "No DEMs registered. The dem_layer dropdown will be empty."
            )
        self.accept()
