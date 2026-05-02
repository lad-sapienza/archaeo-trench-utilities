"""Save Schema to Template dialog for ArchaeoTrench Utilities.

Mirrors dialog_sync.py in structure: shows a per-layer table with schema diff
(columns in the GPKG not yet in schema.sql) and the QML file that will be
written. Style set dropdown selects the destination styles/ subdirectory.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from . import export_schema as export_mod
from .compat import (
    BTN_OK, BTN_CANCEL, HORIZONTAL, NO_EDIT_TRIGGERS, SELECTION_ROWS,
    ITEM_USER_CHECKABLE, ITEM_ENABLED, CHECKED, UNCHECKED,
    COLOR_DARK_YELLOW, COLOR_DARK_GREEN, COLOR_DARK_BLUE, COLOR_GRAY,
)
from .styles import DEFAULT_STYLE_SET

_COL_CHECK  = 0
_COL_LAYER  = 1
_COL_SCHEMA = 2
_COL_STYLE  = 3
_HEADERS    = ("", "Layer", "Schema (new columns)", "Style QML")


class ExportSchemaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Save schema to template")
        self.setMinimumWidth(580)
        self._statuses: list = []
        self._build_ui()
        self._populate_style_sets()
        self._load_layers()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Select layers whose styles to save to the template.\n"
            "schema.sql is always rebuilt from the full GeoPackage schema.\n"
            "New columns (in GPKG but not yet in schema.sql) are highlighted."
        ))

        form = QFormLayout()
        self._style_combo = QComboBox()
        self._style_combo.setEditable(True)
        self._style_combo.currentTextChanged.connect(self._on_style_set_changed)
        form.addRow("Style set:", self._style_combo)
        layout.addLayout(form)

        toolbar = QHBoxLayout()
        all_btn  = QPushButton("Select all")
        none_btn = QPushButton("Select none")
        all_btn.clicked.connect(lambda: self._set_all_checked(True))
        none_btn.clicked.connect(lambda: self._set_all_checked(False))
        toolbar.addWidget(all_btn)
        toolbar.addWidget(none_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

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
        buttons.button(BTN_OK).setText("Export to template")
        buttons.accepted.connect(self._on_export)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _populate_style_sets(self):
        from qgis.core import QgsProject
        from .styles import _find_gpkg_for_project, _read_meta_value
        project = QgsProject.instance()
        gpkg = _find_gpkg_for_project(project)
        project_type = (_read_meta_value(gpkg, "project_type") if gpkg else None) or "plan"
        sets = export_mod.available_style_sets(project_type)
        self._style_combo.blockSignals(True)
        self._style_combo.clear()
        self._style_combo.addItems(sets)
        if DEFAULT_STYLE_SET in sets:
            self._style_combo.setCurrentText(DEFAULT_STYLE_SET)
        self._style_combo.blockSignals(False)

    def _on_style_set_changed(self):
        self._load_layers()

    def _load_layers(self):
        self._table.setRowCount(0)
        style_set = self._style_combo.currentText() or DEFAULT_STYLE_SET
        self._statuses, error = export_mod.inspect_project_for_export(style_set)

        if error:
            self._status_label.setText(error)
            return

        if not self._statuses:
            self._status_label.setText(
                "No exportable base layers found in the current project."
            )
            return

        self._status_label.setText(
            f"{len(self._statuses)} base layer(s) found. "
            "Check the ones whose styles you want to export."
        )

        self._table.setRowCount(len(self._statuses))
        for row, st in enumerate(self._statuses):
            # Checkbox
            chk = QTableWidgetItem()
            chk.setFlags(ITEM_USER_CHECKABLE | ITEM_ENABLED)
            chk.setCheckState(CHECKED)
            self._table.setItem(row, _COL_CHECK, chk)

            # Layer name
            self._table.setItem(row, _COL_LAYER, QTableWidgetItem(st.layer_name))

            # Schema column: highlight new columns not yet in schema.sql
            if st.extra_columns:
                cols_text = ", ".join(f"{n} ({t})" for n, t in st.extra_columns)
                schema_item = QTableWidgetItem(f"+ {cols_text}")
                schema_item.setForeground(COLOR_DARK_YELLOW)
            else:
                schema_item = QTableWidgetItem("up to date")
                schema_item.setForeground(COLOR_DARK_GREEN)
            self._table.setItem(row, _COL_SCHEMA, schema_item)

            # Style column: destination QML filename
            if st.style_qml_dest:
                style_item = QTableWidgetItem(st.style_qml_dest.name)
                style_item.setForeground(COLOR_DARK_BLUE)
            else:
                style_item = QTableWidgetItem("—")
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

    def _on_export(self):
        selected_ids = [
            self._statuses[row].layer_id
            for row in range(self._table.rowCount())
            if self._table.item(row, _COL_CHECK) and
               self._table.item(row, _COL_CHECK).checkState() == CHECKED
        ]

        style_set = self._style_combo.currentText() or DEFAULT_STYLE_SET
        success, message = export_mod.export_layers(selected_ids, style_set)

        if success:
            QMessageBox.information(self, "Export complete", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Export completed with errors", message)
            self.accept()
