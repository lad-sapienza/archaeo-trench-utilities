"""Publish to Repository dialog for ArchaeoTrench Utilities.

Four states:
  A. Template not set up yet      → Download / Clone buttons visible.
  B. Template present, no git     → Update (re-download) button; Publish hidden.
  C. Template present, git repo,
     no local changes             → Pull button; Publish disabled.
  D. Template present, git repo,
     local changes present        → Pull + Publish buttons active.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QVBoxLayout,
)

from . import git_manager
from .compat import BTN_CLOSE, HORIZONTAL


class PublishDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ArchaeoTrench — Template repository")
        self.setMinimumWidth(540)
        self._build_ui()
        self._refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- Setup group ----
        self._setup_box = QGroupBox("Repository setup")
        form = QFormLayout()
        self._repo_edit = QLineEdit()
        self._repo_edit.setPlaceholderText(git_manager.UPSTREAM_URL)
        form.addRow("Shared repo URL:", self._repo_edit)
        self._fork_edit = QLineEdit()
        self._fork_edit.setPlaceholderText(
            "https://github.com/yourname/caj-archeo-trench.git  (optional — needed to publish)"
        )
        form.addRow("Your fork URL:", self._fork_edit)

        self._repo_edit.editingFinished.connect(self._auto_save_urls)
        self._fork_edit.editingFinished.connect(self._auto_save_urls)

        btn_row = QHBoxLayout()
        self._download_btn = QPushButton("Download template")
        self._download_btn.clicked.connect(self._on_download)
        self._clone_btn = QPushButton("Clone with git")
        self._clone_btn.clicked.connect(self._on_clone)
        btn_row.addWidget(self._download_btn)
        btn_row.addWidget(self._clone_btn)
        btn_row.addStretch()

        setup_wrapper = QVBoxLayout()
        setup_wrapper.addLayout(form)
        setup_wrapper.addLayout(btn_row)
        self._setup_box.setLayout(setup_wrapper)
        layout.addWidget(self._setup_box)

        # ---- Status group ----
        self._status_box = QGroupBox("Status")
        status_layout = QVBoxLayout()
        self._status_label = QLabel()
        self._status_label.setWordWrap(True)
        status_layout.addWidget(self._status_label)
        self._changed_list = QListWidget()
        self._changed_list.setMaximumHeight(120)
        status_layout.addWidget(self._changed_list)
        self._status_box.setLayout(status_layout)
        layout.addWidget(self._status_box)

        # ---- Action buttons ----
        action_row = QHBoxLayout()
        self._update_btn = QPushButton("Update template")
        self._update_btn.clicked.connect(self._on_update)
        self._pull_btn = QPushButton("Pull latest")
        self._pull_btn.clicked.connect(self._on_pull)
        self._publish_btn = QPushButton("Publish changes…")
        self._publish_btn.clicked.connect(self._on_publish)
        action_row.addWidget(self._update_btn)
        action_row.addWidget(self._pull_btn)
        action_row.addWidget(self._publish_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        buttons = QDialogButtonBox(BTN_CLOSE, HORIZONTAL, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Refresh — drives all visible state
    # ------------------------------------------------------------------

    def _refresh(self):
        git_manager.ensure_gitignore()

        cfg = git_manager.load_config()
        repo_url = cfg.get("repo_url") or git_manager.UPSTREAM_URL
        fork_url = cfg.get("fork_url", "")
        self._repo_edit.setText(repo_url)
        self._fork_edit.setText(fork_url)

        has_template = git_manager.is_template_available()
        has_git_repo = git_manager.is_repo_initialized()
        git_ok       = git_manager.is_git_available()
        changes      = git_manager.get_changed_files() if has_git_repo else []

        self._changed_list.clear()
        self._changed_list.addItems(changes)
        self._changed_list.setVisible(bool(changes))

        # Setup buttons: visible only when template not yet present
        self._download_btn.setVisible(not has_template)
        self._clone_btn.setVisible(not has_template and git_ok)

        # Action buttons
        self._update_btn.setVisible(has_template and not has_git_repo)
        self._pull_btn.setVisible(has_template and has_git_repo)
        self._publish_btn.setVisible(has_template and has_git_repo and git_ok)
        self._pull_btn.setEnabled(has_git_repo)
        self._publish_btn.setEnabled(bool(changes))

        # Status message
        if not has_template:
            lines = [
                "Template not set up yet.",
                "",
                "• «Download template» — downloads a ZIP from GitHub. No git required.",
            ]
            if git_ok:
                lines.append(
                    "• «Clone with git» — full git clone. Enables pull, commit and publish."
                )
            self._status_label.setText("\n".join(lines))

        elif not has_git_repo:
            self._status_label.setText(
                "Template is available (downloaded via ZIP).\n"
                "Use «Update template» to re-download the latest version.\n\n"
                "To enable git-based sync and publishing, clone the repo with git "
                "from a terminal:\n"
                f"  git clone {repo_url} ~/.archaeotrench"
            )

        elif changes:
            self._status_label.setText(
                f"{len(changes)} file(s) modified since last commit:"
            )

        else:
            self._status_label.setText("Template is up to date. No local changes.")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _auto_save_urls(self):
        repo = self._repo_edit.text().strip()
        fork = self._fork_edit.text().strip()
        if repo:
            git_manager.set_repo_url(repo)
        git_manager.set_fork_url(fork)

    def _on_download(self):
        repo = self._repo_edit.text().strip() or git_manager.UPSTREAM_URL
        ok, msg = git_manager.download_template(repo)
        if ok:
            if self._fork_edit.text().strip():
                git_manager.set_fork_url(self._fork_edit.text().strip())
            QMessageBox.information(self, "Done", msg)
        else:
            QMessageBox.critical(self, "Download failed", msg)
        self._refresh()

    def _on_clone(self):
        repo = self._repo_edit.text().strip() or git_manager.UPSTREAM_URL
        ok, msg = git_manager.clone(repo)
        if ok:
            git_manager.set_repo_url(repo)
            if self._fork_edit.text().strip():
                git_manager.set_fork_url(self._fork_edit.text().strip())
            QMessageBox.information(self, "Done", msg)
        else:
            QMessageBox.critical(self, "Clone failed", msg)
        self._refresh()

    def _on_update(self):
        repo = self._repo_edit.text().strip() or git_manager.UPSTREAM_URL
        ok, msg = git_manager.download_template(repo)
        if ok:
            QMessageBox.information(self, "Updated", msg)
        else:
            QMessageBox.critical(self, "Update failed", msg)
        self._refresh()

    def _on_pull(self):
        ok, msg = git_manager.pull()
        if ok:
            QMessageBox.information(self, "Pull", msg)
        else:
            QMessageBox.warning(self, "Pull failed", msg)
        self._refresh()

    def _on_publish(self):
        """Commit local changes and push. Opens a PR URL only when pushing to a fork."""
        repo_url = git_manager.get_repo_url() or git_manager.UPSTREAM_URL
        fork_url = (git_manager.get_fork_url() or "").strip()

        # Determine whether this is a fork push or a direct push to origin.
        using_fork = bool(fork_url) and fork_url.rstrip("/").rstrip(".git") != repo_url.rstrip("/").rstrip(".git")

        from datetime import date
        ok, out = git_manager.commit(f"Template update {date.today().isoformat()}")
        if not ok:
            QMessageBox.critical(self, "Commit failed", out)
            return

        if using_fork:
            git_manager.ensure_remote("fork", fork_url)
            ok, out = git_manager.push("fork")
            if not ok:
                QMessageBox.critical(self, "Push failed", out)
                return
            pr_url = git_manager.build_pr_url(repo_url, fork_url)
            from qgis.PyQt.QtGui import QDesktopServices
            from qgis.PyQt.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(pr_url))
            QMessageBox.information(
                self, "Published",
                "Changes pushed to your fork.\n"
                "A browser tab has been opened to create the pull request."
            )
        else:
            ok, out = git_manager.push("origin")
            if not ok:
                QMessageBox.critical(self, "Push failed", out)
                return
            QMessageBox.information(self, "Published", "Changes pushed to the shared repository.")

        self._refresh()
