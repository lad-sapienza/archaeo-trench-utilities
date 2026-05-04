"""Adopt project dialog for ArchaeoTrench Utilities.

Writes a _meta table into an existing GeoPackage so the plugin can manage it,
then optionally runs Sync from template to bring schema and styles up to date.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QComboBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL


class AdoptProjectDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("ArchaeoTrench — Adopt project")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        from qgis.core import QgsProject
        from .context import _find_gpkg_path

        layout = QVBoxLayout(self)

        gpkg = _find_gpkg_path(QgsProject.instance())

        form = QFormLayout()

        # Detected GeoPackage (read-only)
        gpkg_label = QLabel(gpkg if gpkg else "No GeoPackage found in the current project.")
        gpkg_label.setWordWrap(True)
        gpkg_label.setStyleSheet("color: grey; font-style: italic;")
        form.addRow("GeoPackage:", gpkg_label)
        self._gpkg_path = gpkg

        # Project type
        self._type_combo = QComboBox()
        self._type_combo.addItems(["plan", "section"])
        form.addRow("Project type:", self._type_combo)

        # Trench name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. trench_1")
        form.addRow("Trench name:", self._name_edit)

        # Operator
        self._operator_edit = QLineEdit()
        self._operator_edit.setPlaceholderText("optional")
        form.addRow("Operator:", self._operator_edit)

        layout.addLayout(form)

        # Optional sync
        self._sync_check = QCheckBox("Run Sync from template after adoption")
        self._sync_check.setChecked(True)
        layout.addWidget(self._sync_check)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Adopt")
        buttons.button(BTN_OK).setEnabled(bool(gpkg))
        buttons.accepted.connect(self._on_adopt)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_adopt(self):
        if not self._gpkg_path:
            QMessageBox.warning(self, "No GeoPackage", "No GeoPackage found in the current project.")
            return

        trench_name = self._name_edit.text().strip()
        if not trench_name:
            QMessageBox.warning(self, "Input required", "Please enter a trench name.")
            return

        project_type = self._type_combo.currentText()
        operator = self._operator_edit.text().strip()

        from pathlib import Path
        from .deploy import _add_meta_table
        try:
            _add_meta_table(Path(self._gpkg_path), project_type, trench_name, operator)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to write _meta table:\n{exc}")
            return

        if self._sync_check.isChecked():
            from .compat import exec_dialog
            from .dialog_sync import SyncDialog
            QMessageBox.information(
                self, "Adopted",
                f"Project adopted as '{project_type}' — trench '{trench_name}'.\n\n"
                "The Sync dialog will open next."
            )
            exec_dialog(SyncDialog(self._iface.mainWindow()))
        else:
            QMessageBox.information(
                self, "Adopted",
                f"Project adopted as '{project_type}' — trench '{trench_name}'.\n"
                "You can now use Sync from template and Save schema to template."
            )

        self.accept()
