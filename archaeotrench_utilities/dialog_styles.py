"""Switch style set dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QMessageBox, QVBoxLayout, QComboBox,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL
from .styles import (
    available_style_sets, set_active_style_set,
    PROJECT_VAR_STYLE, DEFAULT_STYLE_SET,
)


class StyleSetDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Switch style set")
        self.setMinimumWidth(340)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._combo = QComboBox()
        self._populate_sets()
        form.addRow("Style set:", self._combo)
        layout.addLayout(form)

        info = QLabel(
            "Styles will be applied immediately to all matching layers "
            "in the current project and remembered for future loads."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Apply")
        buttons.accepted.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_sets(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils

        self._combo.clear()
        project_path = Path(QgsProject.instance().fileName())
        sets = available_style_sets(project_path.parent) if project_path.exists() else []

        if not sets:
            self._combo.addItem(DEFAULT_STYLE_SET)
        else:
            self._combo.addItems(sets)

        # Pre-select the currently active set
        current = (
            QgsExpressionContextUtils.projectScope(
                QgsProject.instance()
            ).variable(PROJECT_VAR_STYLE)
            or DEFAULT_STYLE_SET
        )
        idx = self._combo.findText(current)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)

    def _on_apply(self):
        style_set = self._combo.currentText()
        if not style_set:
            return
        set_active_style_set(style_set)
        QMessageBox.information(
            self, "Styles applied",
            f"Style set <b>{style_set}</b> applied to the current project."
        )
        self.accept()
