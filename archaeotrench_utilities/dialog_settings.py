"""Project & template settings dialog for ArchaeoTrench Utilities.

Two sections:
  Project   — per-project values stored in the GeoPackage aTrench_settings table.
              Writing these marks an unmanaged project as an aTrench project.
  Template  — global values stored in ~/.archaeotrench/config.json.
              URL fields that were previously in the publish dialog live here.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from . import git_manager
from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL


class SettingsDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("ArchaeoTrench — Settings")
        self.setMinimumWidth(480)
        self._build_ui()
        self._load()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- Project settings ----------------------------------------
        proj_box = QGroupBox("Project settings")
        proj_form = QFormLayout()

        self._gpkg_label = QLabel()
        self._gpkg_label.setWordWrap(True)
        self._gpkg_label.setStyleSheet("color: grey; font-style: italic;")
        proj_form.addRow("GeoPackage:", self._gpkg_label)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["plan", "section"])
        proj_form.addRow("Project type:", self._type_combo)

        self._trench_edit = QLineEdit()
        self._trench_edit.setPlaceholderText("e.g. trench_1")
        proj_form.addRow("Trench name:", self._trench_edit)

        self._operator_edit = QLineEdit()
        self._operator_edit.setPlaceholderText("optional")
        proj_form.addRow("Operator:", self._operator_edit)

        self._deploy_label  = QLabel("—")
        self._sync_label    = QLabel("—")
        self._tmpl_ver_label = QLabel("—")
        self._plugin_ver_label = QLabel("—")
        proj_form.addRow("Deployed:", self._deploy_label)
        proj_form.addRow("Last sync:", self._sync_label)
        proj_form.addRow("Template version:", self._tmpl_ver_label)
        proj_form.addRow("Plugin version:", self._plugin_ver_label)

        self._sync_check = QCheckBox("Run Sync from template after saving")
        proj_box.setLayout(proj_form)
        layout.addWidget(proj_box)
        layout.addWidget(self._sync_check)

        # ---- Template / repository settings --------------------------
        tmpl_box = QGroupBox("Template repository")
        tmpl_form = QFormLayout()

        self._repo_edit = QLineEdit()
        self._repo_edit.setPlaceholderText(git_manager.UPSTREAM_URL)
        self._repo_edit.editingFinished.connect(self._auto_save_urls)
        tmpl_form.addRow("Shared repo URL:", self._repo_edit)

        self._fork_edit = QLineEdit()
        self._fork_edit.setPlaceholderText(
            "https://github.com/yourname/caj-archeo-trench  (optional)"
        )
        self._fork_edit.editingFinished.connect(self._auto_save_urls)
        tmpl_form.addRow("Push / fork URL:", self._fork_edit)

        path_label = QLabel(str(git_manager.USER_DIR))
        path_label.setStyleSheet("color: grey; font-style: italic;")
        tmpl_form.addRow("Local template path:", path_label)

        tmpl_box.setLayout(tmpl_form)
        layout.addWidget(tmpl_box)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Save")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Load current values
    # ------------------------------------------------------------------

    def _load(self):
        from qgis.core import QgsProject
        from .context import _find_gpkg_path
        from .deploy import read_all_settings

        gpkg = _find_gpkg_path(QgsProject.instance())
        self._gpkg_path = gpkg
        self._gpkg_label.setText(gpkg or "No GeoPackage found in the current project.")

        if gpkg:
            s = read_all_settings(gpkg)
            self._type_combo.setCurrentText(s.get("project_type", "plan"))
            self._trench_edit.setText(s.get("trench_name", ""))
            self._operator_edit.setText(s.get("operator", ""))
            self._deploy_label.setText(s.get("deploy_date", "—"))
            self._sync_label.setText(s.get("last_sync_date", "—"))
            self._tmpl_ver_label.setText(s.get("template_version", "—"))
            self._plugin_ver_label.setText(s.get("plugin_version", "—"))
            is_managed = bool(s)
            self._sync_check.setChecked(not is_managed)
        else:
            for w in (self._type_combo, self._trench_edit, self._operator_edit,
                      self._sync_check):
                w.setEnabled(False)
            buttons = self.findChild(QDialogButtonBox)
            if buttons:
                buttons.button(BTN_OK).setEnabled(False)

        cfg = git_manager.load_config()
        self._repo_edit.setText(cfg.get("repo_url", "") or git_manager.UPSTREAM_URL)
        self._fork_edit.setText(cfg.get("fork_url", ""))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _auto_save_urls(self):
        repo = self._repo_edit.text().strip()
        fork = self._fork_edit.text().strip()
        if repo:
            git_manager.set_repo_url(repo)
        git_manager.set_fork_url(fork)

    def _on_save(self):
        if not self._gpkg_path:
            self.reject()
            return

        trench_name = self._trench_edit.text().strip()
        if not trench_name:
            QMessageBox.warning(self, "Input required", "Please enter a trench name.")
            return

        from pathlib import Path
        from .deploy import write_project_settings
        try:
            write_project_settings(
                Path(self._gpkg_path),
                project_type=self._type_combo.currentText(),
                trench_name=trench_name,
                operator=self._operator_edit.text().strip(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to write settings:\n{exc}")
            return

        self._auto_save_urls()

        if self._sync_check.isChecked():
            from .compat import exec_dialog
            from .dialog_sync import SyncDialog
            exec_dialog(SyncDialog(self._iface.mainWindow()))

        self.accept()
