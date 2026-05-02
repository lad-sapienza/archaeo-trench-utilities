"""Add context dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL
from .context import DEFAULT_CONTEXT_TABLES, list_gpkg_layers


class AddContextDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Add context")
        self.setMinimumWidth(320)
        self._checkboxes: list = []  # list of (QCheckBox, table_name)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. c100")
        self._name_edit.textChanged.connect(self._update_preview)
        form.addRow("Context name:", self._name_edit)
        layout.addLayout(form)

        # Dynamic layer list from GPKG
        box = QGroupBox("Layers to include")
        box_layout = QVBoxLayout(box)

        from qgis.core import QgsProject
        available = list_gpkg_layers(QgsProject.instance())

        if available:
            for table_name, display_name in available:
                cb = QCheckBox(display_name)
                cb.setChecked(table_name in DEFAULT_CONTEXT_TABLES)
                cb.stateChanged.connect(self._update_preview)
                box_layout.addWidget(cb)
                self._checkboxes.append((cb, table_name))
        else:
            box_layout.addWidget(QLabel("No layers found — is a trench project open?"))

        layout.addWidget(box)

        self._preview = QLabel()
        self._preview.setWordWrap(True)
        self._preview.setStyleSheet("color: grey; font-style: italic;")
        layout.addWidget(self._preview)
        self._update_preview()

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Add")
        buttons.accepted.connect(self._on_add)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_preview(self):
        name = self._name_edit.text().strip() or "…"
        selected = [
            cb.text() for cb, _ in self._checkboxes if cb.isChecked()
        ]
        if selected:
            self._preview.setText(
                "Will create: " + ", ".join(f"{name} {s}" for s in selected)
            )
        else:
            self._preview.setText("No layers selected.")

    def _on_add(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Input required", "Please enter a context name.")
            return

        selected_tables = [t for cb, t in self._checkboxes if cb.isChecked()]
        if not selected_tables:
            QMessageBox.warning(self, "Nothing selected", "Select at least one layer.")
            return

        from . import context as context_mod
        try:
            context_mod.add_context(name, selected_tables)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        self.accept()
