"""Deploy new trench dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QComboBox, QCheckBox,
)

from . import deploy as deploy_mod
from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL


class DeployDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("ArchaeoTrench — Deploy new trench")
        self.setMinimumWidth(460)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._trench_edit = QLineEdit()
        self._trench_edit.setPlaceholderText("e.g. T23")
        form.addRow("Trench name:", self._trench_edit)

        self._year_edit = QLineEdit()
        self._year_edit.setPlaceholderText("e.g. 2025")
        import datetime
        self._year_edit.setText(str(datetime.date.today().year))
        form.addRow("Year:", self._year_edit)

        self._operator_edit = QLineEdit()
        self._operator_edit.setPlaceholderText("Your name")
        form.addRow("Operator:", self._operator_edit)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["plan", "section"])
        form.addRow("Project type:", self._type_combo)

        # Output folder row
        folder_layout = QHBoxLayout()
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select output folder…")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self._folder_edit)
        folder_layout.addWidget(browse_btn)
        form.addRow("Output folder:", folder_layout)

        self._open_check = QCheckBox("Open project in QGIS after deploy")
        self._open_check.setChecked(True)

        layout.addLayout(form)
        layout.addWidget(self._open_check)

        buttons = QDialogButtonBox(
            BTN_OK | BTN_CANCEL,
            HORIZONTAL, self
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select output folder", str(Path.home())
        )
        if folder:
            self._folder_edit.setText(folder)

    def _on_ok(self):
        trench = self._trench_edit.text().strip()
        year = self._year_edit.text().strip()
        operator = self._operator_edit.text().strip()
        project_type = self._type_combo.currentText()
        folder = self._folder_edit.text().strip()

        if not trench:
            QMessageBox.warning(self, "Input required", "Please enter a trench name.")
            return
        if not folder:
            QMessageBox.warning(self, "Input required", "Please select an output folder.")
            return

        try:
            qgz_path = deploy_mod.deploy_trench(
                project_type, trench, year, operator, folder
            )
        except Exception as exc:
            QMessageBox.critical(self, "Deploy failed", str(exc))
            return

        if self._open_check.isChecked():
            from qgis.core import QgsProject
            QgsProject.instance().read(str(qgz_path))

        QMessageBox.information(
            self, "Deploy complete",
            f"Project deployed to:\n{qgz_path}"
        )
        self.accept()
