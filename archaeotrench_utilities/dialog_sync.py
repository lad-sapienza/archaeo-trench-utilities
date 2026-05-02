"""Sync styles dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QListWidget, QMessageBox, QPushButton,
    QVBoxLayout, QAbstractItemView,
)
from qgis.PyQt.QtGui import QColor

from . import sync as sync_mod
from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL, EXTENDED_SELECTION
from .version import load_changelog


class SyncDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Sync styles")
        self.setMinimumWidth(500)
        self._trench_dirs: list = []
        self._changelog = load_changelog(Path(__file__).parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Select trench folders to update with the latest styles from the template."
        ))

        toolbar = QHBoxLayout()
        add_btn = QPushButton("Add trench folder(s)…")
        add_btn.clicked.connect(self._add_folders)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._list = QListWidget()
        self._list.setSelectionMode(EXTENDED_SELECTION)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Sync styles")
        buttons.accepted.connect(self._on_sync)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_folders(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select trench root folder", str(Path.home())
        )
        if not folder:
            return
        root = Path(folder)
        # Accept either a single trench folder or a root containing multiple trenches
        candidates = [root] + [d for d in root.iterdir() if d.is_dir()]
        for d in candidates:
            if (d / "vectors.gpkg").exists() or list(d.glob("*.gpkg")):
                if d not in self._trench_dirs:
                    self._trench_dirs.append(d)
        self._refresh_list()

    def _remove_selected(self):
        rows = sorted(
            {self._list.row(i) for i in self._list.selectedItems()},
            reverse=True
        )
        for row in rows:
            self._trench_dirs.pop(row)
        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        for d in self._trench_dirs:
            self._list.addItem(str(d))

    def _on_sync(self):
        if not self._trench_dirs:
            QMessageBox.warning(self, "No folders", "Add at least one trench folder.")
            return

        results = sync_mod.sync_styles(self._trench_dirs)

        errors = [r for r in results if r["status"] == sync_mod.STATUS_ERROR]
        updated = [r for r in results if r["status"] == sync_mod.STATUS_UPDATED]

        if errors:
            details = "\n".join(
                f"{r['trench_dir'].name}: {r['error']}" for r in errors
            )
            QMessageBox.warning(
                self, "Sync completed with errors",
                f"{len(updated)} updated, {len(errors)} failed:\n\n{details}"
            )
        else:
            QMessageBox.information(
                self, "Sync complete",
                f"{len(updated)} trench folder(s) updated with latest styles."
            )
        self.accept()
