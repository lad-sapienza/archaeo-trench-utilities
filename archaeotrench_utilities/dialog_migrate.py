"""Schema migration dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QLabel, QListWidget, QMessageBox, QPushButton,
    QVBoxLayout, QAbstractItemView,
)

from . import migrate as migrate_mod
from .compat import BTN_OK, BTN_CANCEL, BTN_YES, BTN_NO, HORIZONTAL, EXTENDED_SELECTION
from .version import load_changelog


class MigrateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Schema migration")
        self.setMinimumWidth(540)
        self._gpkg_paths: list = []
        self._changelog = load_changelog(Path(__file__).parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        add_btn = QPushButton("Add GPKG file(s)…")
        add_btn.clicked.connect(self._add_gpkgs)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(remove_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # List
        self._list = QListWidget()
        self._list.setSelectionMode(EXTENDED_SELECTION)
        layout.addWidget(self._list)

        # Migration info
        target = self._changelog.get("current_version", "?")
        info_label = QLabel(f"Will migrate each GPKG to version <b>{target}</b>.")
        layout.addWidget(info_label)

        # Descriptions of pending steps
        self._desc_label = QLabel()
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label)

        warn = QLabel(
            "<b style='color:red'>Warning:</b> This operation cannot be undone. "
            "A timestamped backup will be created automatically."
        )
        warn.setWordWrap(True)
        layout.addWidget(warn)

        buttons = QDialogButtonBox(
            BTN_OK | BTN_CANCEL,
            HORIZONTAL, self
        )
        buttons.button(BTN_OK).setText("Migrate")
        buttons.accepted.connect(self._on_migrate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_gpkgs(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select GPKG files", str(Path.home()),
            "GeoPackage (*.gpkg)"
        )
        for p in paths:
            path = Path(p)
            if path not in self._gpkg_paths:
                self._gpkg_paths.append(path)
        self._refresh_list()

    def _remove_selected(self):
        rows = sorted(
            {self._list.row(i) for i in self._list.selectedItems()},
            reverse=True
        )
        for row in rows:
            self._gpkg_paths.pop(row)
        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        descriptions = []
        for gpkg in self._gpkg_paths:
            current = migrate_mod.get_trench_version(gpkg)
            pending = migrate_mod.get_pending_migrations(gpkg, self._changelog)
            target = self._changelog.get("current_version", "?")
            status = f"{current} → {target}" if pending else f"{current} (up to date)"
            self._list.addItem(f"{gpkg.name}  [{status}]")
            for entry in pending:
                for pt in ("plan", "section"):
                    desc = entry.get("changes", {}).get(pt, {}).get("description")
                    if desc:
                        descriptions.append(f"v{entry['version']} ({pt}): {desc}")
        self._desc_label.setText("\n".join(descriptions) if descriptions else "No pending migrations.")

    def _on_migrate(self):
        if not self._gpkg_paths:
            QMessageBox.warning(self, "No files", "Add at least one GPKG file.")
            return

        reply = QMessageBox.question(
            self, "Confirm migration",
            "Proceed with schema migration? Backups will be created.",
            BTN_YES | BTN_NO
        )
        if reply != BTN_YES:
            return

        results = []
        for gpkg in self._gpkg_paths:
            ok, msg = migrate_mod.migrate_trench(gpkg, self._changelog)
            results.append((gpkg.name, ok, msg))

        errors = [(n, m) for n, ok, m in results if not ok]
        summary_lines = [f"{'OK' if ok else 'FAIL'}  {n}: {m}" for n, ok, m in results]

        if errors:
            QMessageBox.warning(
                self, "Migration completed with errors",
                "\n\n".join(summary_lines)
            )
        else:
            QMessageBox.information(
                self, "Migration complete",
                "\n\n".join(summary_lines)
            )
        self._refresh_list()
