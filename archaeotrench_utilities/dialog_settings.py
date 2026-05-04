"""Project & template settings dialog for ArchaeoTrench Utilities.

Two sections:
  Project   — per-project values stored in the GeoPackage aTrench_settings table.
              Writing these marks an unmanaged project as an aTrench project.
  Template  — global values stored in ~/.archaeotrench/config.json.
              URL fields that were previously in the publish dialog live here.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QToolButton, QVBoxLayout,
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

        # ---- Diagnostics (collapsible, closed by default) ------------
        layout.addWidget(self._build_diagnostics_section())

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Save")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Diagnostics section
    # ------------------------------------------------------------------

    def _build_diagnostics_section(self) -> QFrame:
        """Return a collapsible diagnostics panel (closed by default)."""
        wrapper = QFrame()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        # Toggle button acts as the section header
        self._diag_toggle = QToolButton()
        self._diag_toggle.setText("▶  Diagnostics")
        self._diag_toggle.setCheckable(True)
        self._diag_toggle.setChecked(False)
        self._diag_toggle.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; padding: 4px 0; }"
        )
        self._diag_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly
            if hasattr(Qt.ToolButtonStyle, "ToolButtonTextOnly")
            else Qt.ToolButtonTextOnly)
        self._diag_toggle.toggled.connect(self._on_diag_toggled)
        wrapper_layout.addWidget(self._diag_toggle)

        # Content widget — hidden until toggled open
        self._diag_content = QFrame()
        self._diag_content.setFrameShape(QFrame.Shape.StyledPanel
            if hasattr(QFrame.Shape, "StyledPanel") else QFrame.StyledPanel)
        content_layout = QVBoxLayout(self._diag_content)

        self._diag_form = QFormLayout()
        self._diag_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight
            if hasattr(Qt.AlignmentFlag, "AlignRight") else Qt.AlignRight)
        content_layout.addLayout(self._diag_form)

        refresh_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._run_diagnostics)
        refresh_row.addStretch()
        refresh_row.addWidget(refresh_btn)
        content_layout.addLayout(refresh_row)

        self._diag_content.setVisible(False)
        wrapper_layout.addWidget(self._diag_content)
        return wrapper

    def _on_diag_toggled(self, checked: bool):
        self._diag_toggle.setText("▼  Diagnostics" if checked else "▶  Diagnostics")
        self._diag_content.setVisible(checked)
        if checked and self._diag_form.rowCount() == 0:
            self._run_diagnostics()
        self.adjustSize()

    def _run_diagnostics(self):
        """Populate the diagnostics form with current environment info."""
        # Clear existing rows
        while self._diag_form.rowCount():
            self._diag_form.removeRow(0)

        def row(label, value, *, ok=None):
            """Add a form row; colour value green/red if ok is set."""
            lbl = QLabel(value)
            lbl.setWordWrap(True)
            if ok is True:
                lbl.setStyleSheet("color: green;")
            elif ok is False:
                lbl.setStyleSheet("color: red;")
            else:
                lbl.setStyleSheet("color: grey;")
            self._diag_form.addRow(label, lbl)

        # ---- GeoPackage ----
        self._diag_form.addRow(QLabel("<b>GeoPackage</b>"))
        gpkg = getattr(self, "_gpkg_path", None)
        if gpkg:
            row("Path:", gpkg)
            from .deploy import read_all_settings, SETTINGS_TABLE
            import sqlite3
            try:
                con = sqlite3.connect(gpkg)
                tables = {r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()}
                con.close()
                has_settings = SETTINGS_TABLE in tables
                row("aTrench_settings:", "found" if has_settings else "not found",
                    ok=has_settings)
                if has_settings:
                    s = read_all_settings(gpkg)
                    for k, v in s.items():
                        row(f"  {k}:", v)
            except Exception as exc:
                row("Error:", str(exc), ok=False)
        else:
            row("Path:", "No GeoPackage in current project", ok=False)

        # ---- Template ----
        self._diag_form.addRow(QLabel("<b>Template</b>"))
        has_tmpl = git_manager.is_template_available()
        row("Local path:", str(git_manager.USER_DIR), ok=has_tmpl)

        if has_tmpl:
            has_git = git_manager.is_repo_initialized()
            row("Type:", "git repository" if has_git else "ZIP download",
                ok=has_git)
            if has_git:
                row("Branch:", git_manager.get_current_branch())
                last = git_manager.get_last_commit_info()
                row("Last commit:", last or "—")
                changes = git_manager.get_changed_files()
                row("Uncommitted:", f"{len(changes)} file(s)" if changes else "none",
                    ok=not changes)

            # Schema version
            from . import schema as schema_mod
            project_type = getattr(self, "_type_combo", None)
            ptype = project_type.currentText() if project_type else "plan"
            schema_path = git_manager.get_template_dir(ptype) / "schema.sql"
            if schema_path.exists():
                ver = schema_mod.get_template_version(str(schema_path))
                row("Schema version:", ver or "—")
            else:
                row("schema.sql:", "not found", ok=False)
        else:
            row("Status:", "Template not set up — use Template repository…", ok=False)

        # ---- Plugin ----
        self._diag_form.addRow(QLabel("<b>Plugin</b>"))
        from .deploy import _plugin_version
        row("Installed version:", _plugin_version())

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
