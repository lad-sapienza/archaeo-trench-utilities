"""Main QGIS plugin class for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import QAction, QMenu

from .compat import exec_dialog


class ArchaeoTrenchPlugin:
    def __init__(self, iface):
        self._iface = iface
        self._actions: list = []
        self._template_actions: list = []   # disabled until template is available
        self._menu: QMenu | None = None
        self._quota_manager = None

    # ------------------------------------------------------------------
    # QGIS plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self):
        from .quota import QuotaManager
        self._quota_manager = QuotaManager(self._iface)

        plugins_menu = self._iface.pluginMenu()
        self._menu = QMenu("ArchaeoTrench Utilities", self._iface.mainWindow())
        plugins_menu.addMenu(self._menu)

        self._template_actions.append(self._add_action(
            "Deploy new trench…",
            "Create a new trench QGIS project from the template",
            self.run_deploy,
        ))
        self._menu.addSeparator()
        self._template_actions.append(self._add_action(
            "Add context…",
            "Add a layer group for a new excavation context to the current project",
            self.run_add_context,
        ))
        self._add_action(
            "Auto-elevation…",
            "Activate automatic DEM-based elevation population for the elevations layer",
            self.run_quota,
        )
        self._menu.addSeparator()
        self._template_actions.append(self._add_action(
            "Sync from template…",
            "Update existing trench GeoPackages and styles from the current template",
            self.run_sync,
        ))
        self._template_actions.append(self._add_action(
            "Save schema to template…",
            "Export the current project's GeoPackage schema and styles to the plugin template",
            self.run_export_schema,
        ))
        self._menu.addSeparator()
        self._add_action(
            "Template repository…",
            "Download or update the template, and publish changes to GitHub",
            self.run_publish,
        )

        # Apply styles and reconnect quota whenever a project is loaded
        from qgis.core import QgsProject
        QgsProject.instance().readProject.connect(self._on_project_loaded)

        self._update_actions_state()

    def unload(self):
        from qgis.core import QgsProject
        try:
            QgsProject.instance().readProject.disconnect(self._on_project_loaded)
        except Exception:
            pass
        if self._quota_manager:
            try:
                self._quota_manager.deactivate()
            except Exception:
                pass
        if self._menu:
            self._iface.pluginMenu().removeAction(self._menu.menuAction())
            self._menu = None
        self._actions.clear()
        self._template_actions.clear()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _update_actions_state(self):
        from . import git_manager
        available = git_manager.is_template_available()
        for action in self._template_actions:
            action.setEnabled(available)

    # ------------------------------------------------------------------
    # Project load handler
    # ------------------------------------------------------------------

    def _on_project_loaded(self):
        from .styles import apply_style_set
        apply_style_set()

    # ------------------------------------------------------------------
    # Action runners
    # ------------------------------------------------------------------

    def run_deploy(self):
        from .dialog_deploy import DeployDialog
        exec_dialog(DeployDialog(self._iface, self._iface.mainWindow()))

    def run_sync(self):
        from .dialog_sync import SyncDialog
        exec_dialog(SyncDialog(self._iface.mainWindow()))

    def run_add_context(self):
        from .dialog_context import AddContextDialog
        exec_dialog(AddContextDialog(self._iface.mainWindow()))

    def run_quota(self):
        from .dialog_quota import QuotaDialog
        exec_dialog(QuotaDialog(self._quota_manager, self._iface.mainWindow()))

    def run_export_schema(self):
        from .dialog_export_schema import ExportSchemaDialog
        exec_dialog(ExportSchemaDialog(self._iface.mainWindow()))

    def run_publish(self):
        from .dialog_publish import PublishDialog
        exec_dialog(PublishDialog(self._iface.mainWindow()))
        self._update_actions_state()   # re-enable actions if setup just completed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_action(self, text: str, tooltip: str, callback) -> QAction:
        action = QAction(text, self._iface.mainWindow())
        action.setToolTip(tooltip)
        action.triggered.connect(callback)
        self._menu.addAction(action)
        self._actions.append(action)
        return action
