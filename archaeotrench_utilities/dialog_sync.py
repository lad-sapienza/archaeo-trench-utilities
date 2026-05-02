"""Sync from template dialog for ArchaeoTrench Utilities.

Inspects the active QGIS project and shows a per-layer diff against the
plugin template (schema.sql + QML styles). The user selects which layers
to sync; changes are applied immediately in the open project.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from . import sync as sync_mod
from .compat import (
    BTN_OK, BTN_CANCEL, HORIZONTAL, NO_EDIT_TRIGGERS, SELECTION_ROWS,
    ITEM_USER_CHECKABLE, ITEM_ENABLED, CHECKED, UNCHECKED,
    COLOR_DARK_YELLOW, COLOR_DARK_GREEN, COLOR_DARK_BLUE, COLOR_GRAY,
)


_COL_CHECK  = 0
_COL_LAYER  = 1
_COL_SCHEMA = 2
_COL_STYLE  = 3
_HEADERS    = ("", "Layer", "Schema", "Style")


class SyncDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Sync from template")
        self.setMinimumWidth(560)
        self._statuses: list = []
        self._build_ui()
        self._load_layers()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Select layers to sync from the template.\n"
            "Schema changes add missing columns; styles are reloaded from the template QML."
        ))

        # Select-all / select-none toolbar
        toolbar = QHBoxLayout()
        all_btn  = QPushButton("Select all")
        none_btn = QPushButton("Select none")
        all_btn.clicked.connect(lambda: self._set_all_checked(True))
        none_btn.clicked.connect(lambda: self._set_all_checked(False))
        toolbar.addWidget(all_btn)
        toolbar.addWidget(none_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Layer table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setEditTriggers(NO_EDIT_TRIGGERS)
        self._table.setSelectionBehavior(SELECTION_ROWS)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(_COL_CHECK,  28)
        self._table.setColumnWidth(_COL_LAYER, 160)
        self._table.setColumnWidth(_COL_SCHEMA, 180)
        layout.addWidget(self._table)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #888;")
        layout.addWidget(self._status_label)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Sync selected")
        buttons.accepted.connect(self._on_sync)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_layers(self):
        self._table.setRowCount(0)
        self._statuses, error = sync_mod.inspect_project()

        if error:
            self._status_label.setText(error)
            return

        if not self._statuses:
            self._status_label.setText("No syncable layers found in the current project.")
            return

        self._status_label.setText(
            f"{len(self._statuses)} layer(s) found. "
            "Check the ones you want to sync."
        )

        self._table.setRowCount(len(self._statuses))
        for row, st in enumerate(self._statuses):
            # Checkbox column
            chk = QTableWidgetItem()
            chk.setFlags(ITEM_USER_CHECKABLE | ITEM_ENABLED)
            chk.setCheckState(CHECKED)
            self._table.setItem(row, _COL_CHECK, chk)

            # Layer name
            self._table.setItem(row, _COL_LAYER, QTableWidgetItem(st.layer_name))

            # Schema status
            if st.missing_columns:
                cols_text = ", ".join(f"{n} ({t})" for n, t in st.missing_columns)
                schema_item = QTableWidgetItem(f"+ {cols_text}")
                schema_item.setForeground(COLOR_DARK_YELLOW)
            else:
                schema_item = QTableWidgetItem("up to date")
                schema_item.setForeground(COLOR_DARK_GREEN)
            self._table.setItem(row, _COL_SCHEMA, schema_item)

            # Style status
            if st.style_qml:
                style_item = QTableWidgetItem("template QML available")
                style_item.setForeground(COLOR_DARK_BLUE)
            else:
                style_item = QTableWidgetItem("no template QML")
                style_item.setForeground(COLOR_GRAY)
            self._table.setItem(row, _COL_STYLE, style_item)

        self._table.resizeRowsToContents()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _set_all_checked(self, checked: bool):
        state = CHECKED if checked else UNCHECKED
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_CHECK)
            if item:
                item.setCheckState(state)

    def _on_sync(self):
        selected_ids = [
            self._statuses[row].layer_id
            for row in range(self._table.rowCount())
            if self._table.item(row, _COL_CHECK) and
               self._table.item(row, _COL_CHECK).checkState() == CHECKED
        ]

        if not selected_ids:
            QMessageBox.warning(self, "Nothing selected", "Select at least one layer to sync.")
            return

        success, message = sync_mod.sync_layers(selected_ids)

        if success:
            QMessageBox.information(self, "Sync complete", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Sync completed with errors", message)
            self.accept()
