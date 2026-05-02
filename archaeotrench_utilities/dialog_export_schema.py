"""Save Schema to Template dialog for ArchaeoTrench Utilities.

Lets the user export the current project's GeoPackage schema (as schema.sql)
and base-layer styles (as QML files) back into the plugin template folder.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL
from . import export_schema


class ExportSchemaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Save Schema to Template")
        self.setMinimumWidth(420)
        self._build_ui()
        self._refresh_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._type_combo = QComboBox()
        self._type_combo.addItems(["plan", "section"])
        self._type_combo.currentTextChanged.connect(self._refresh_preview)
        form.addRow("Project type:", self._type_combo)

        layout.addLayout(form)

        info = QLabel(
            "The following base layers will be exported to the template. "
            "Their current styles will be saved as QML files."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._preview_list = QListWidget()
        self._preview_list.setMinimumHeight(120)
        layout.addWidget(self._preview_list)

        self._warning_label = QLabel()
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #cc6600;")
        layout.addWidget(self._warning_label)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Export")
        buttons.accepted.connect(self._on_export)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_preview(self):
        self._preview_list.clear()
        self._warning_label.setText("")

        project_type = self._type_combo.currentText()
        items = export_schema.get_exportable_layers(project_type)

        if not items:
            self._warning_label.setText(
                "No base layers found in the current project. "
                "Open a trench project first."
            )
            return

        for layer_name, qml_path in items:
            self._preview_list.addItem(f"{layer_name}  →  {qml_path}")

    def _on_export(self):
        project_type = self._type_combo.currentText()

        reply = QMessageBox.question(
            self,
            "Confirm export",
            f"This will overwrite <b>schema.sql</b> and QML style files in the "
            f"<b>{project_type}</b> template folder.\n\nProceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        success, message = export_schema.export_to_template(project_type)

        if success:
            QMessageBox.information(self, "Export complete", message)
            self.accept()
        else:
            QMessageBox.critical(self, "Export failed", message)
