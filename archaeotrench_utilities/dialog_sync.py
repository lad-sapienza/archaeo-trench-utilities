"""Sync from template dialog for ArchaeoTrench Utilities.

Inspects the active QGIS project and shows a per-layer diff against the
plugin template (schema.sql + QML styles). The user selects which layers
to sync; changes are applied immediately in the open project.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from . import sync as sync_mod
from .compat import (
    BTN_OK, BTN_CANCEL, HORIZONTAL, NO_EDIT_TRIGGERS, SELECTION_ROWS,
    ITEM_USER_CHECKABLE, ITEM_ENABLED, CHECKED, UNCHECKED,
    COLOR_DARK_YELLOW, COLOR_DARK_GREEN,
)
from .styles import DEFAULT_STYLE_SET


_COL_CHECK  = 0
_COL_LAYER  = 1
_COL_SCHEMA = 2
_COL_STYLE  = 3
_HEADERS    = ("", "Layer", "Schema", "Style QML")

_NO_STYLE = "(none)"


class SyncDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Sync from template")
        self.setMinimumWidth(620)
        self._statuses: list = []
        self._qml_index: dict = {}   # stem → Path for the current style set
        self._build_ui()
        self._populate_style_sets()
        self._load_layers()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Select layers to sync from the template.\n"
            "Schema changes add missing columns; styles are reloaded from the selected style set."
        ))

        form = QFormLayout()
        self._style_combo = QComboBox()
        self._style_combo.currentTextChanged.connect(self._on_style_set_changed)
        form.addRow("Style set:", self._style_combo)
        layout.addLayout(form)

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

    def _populate_style_sets(self):
        """Fill the style-set dropdown from the template (called after project is known)."""
        from qgis.core import QgsProject
        from .styles import _find_gpkg_for_project
        project = QgsProject.instance()
        gpkg = _find_gpkg_for_project(project)
        from .styles import _read_meta_value
        project_type = (_read_meta_value(gpkg, "project_type") if gpkg else None) or "plan"
        sets = sync_mod.available_style_sets(project_type)
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
        self._statuses, error = sync_mod.inspect_project(style_set)

        # Build the QML index for the current style set
        from qgis.core import QgsProject
        from .styles import _find_gpkg_for_project
        from .styles import _build_qml_index
        from . import git_manager
        gpkg = _find_gpkg_for_project(QgsProject.instance())
        from .styles import _read_meta_value
        project_type = (_read_meta_value(gpkg, "project_type") if gpkg else None) or "plan"
        styles_dir = git_manager.get_template_dir(project_type) / "styles" / style_set
        self._qml_index = _build_qml_index(styles_dir) if styles_dir.is_dir() else {}
        qml_options = [_NO_STYLE] + sorted(
            p.name for p in self._qml_index.values()
        )

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

            # Style column — editable combo pre-set to auto-matched QML
            style_combo = QComboBox()
            style_combo.addItems(qml_options)
            if st.style_qml:
                style_combo.setCurrentText(st.style_qml.name)
            else:
                style_combo.setCurrentText(_NO_STYLE)
            self._table.setCellWidget(row, _COL_STYLE, style_combo)

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
        selected_ids = []
        qml_overrides = {}

        for row in range(self._table.rowCount()):
            chk = self._table.item(row, _COL_CHECK)
            if not chk or chk.checkState() != CHECKED:
                continue
            st = self._statuses[row]
            selected_ids.append(st.layer_id)

            combo = self._table.cellWidget(row, _COL_STYLE)
            if combo:
                chosen = combo.currentText()
                if chosen == _NO_STYLE:
                    qml_overrides[st.layer_id] = None
                else:
                    # Look up Path by filename from the index
                    qml_overrides[st.layer_id] = next(
                        (p for p in self._qml_index.values() if p.name == chosen), None
                    )

        if not selected_ids:
            QMessageBox.warning(self, "Nothing selected", "Select at least one layer to sync.")
            return

        style_set = self._style_combo.currentText() or DEFAULT_STYLE_SET
        success, message = sync_mod.sync_layers(selected_ids, style_set, qml_overrides)

        if success:
            QMessageBox.information(self, "Sync complete", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Sync completed with errors", message)
            self.accept()
