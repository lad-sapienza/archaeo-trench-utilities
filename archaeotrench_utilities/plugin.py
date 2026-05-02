"""Main QGIS plugin class for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import QAction, QMenu

from .compat import exec_dialog
from .quota import QuotaManager


class ArchaeoTrenchPlugin:
    def __init__(self, iface):
        self._iface = iface
        self._actions: list = []
        self._menu: QMenu | None = None
        self._quota_manager = QuotaManager(iface)

    # ------------------------------------------------------------------
    # QGIS plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self):
        plugins_menu = self._iface.pluginMenu()
        self._menu = QMenu("ArchaeoTrench Utilities", self._iface.mainWindow())
        plugins_menu.addMenu(self._menu)

        self._add_action(
            "Deploy new trench…",
            "Create a new trench QGIS project from the template",
            self.run_deploy,
        )
        self._add_action(
            "Sync styles…",
            "Copy latest QML styles from the template into existing trench folders",
            self.run_sync,
        )
        self._add_action(
            "Migrate schema…",
            "Apply forward schema migrations to existing trench GeoPackages",
            self.run_migrate,
        )
        self._menu.addSeparator()
        self._add_action(
            "Add context…",
            "Add a layer group for a new excavation context to the current project",
            self.run_add_context,
        )
        self._menu.addSeparator()
        self._add_action(
            "Switch style set…",
            "Apply a named style set (e.g. default, print) to the current project",
            self.run_switch_styles,
        )
        self._add_action(
            "Auto-elevation…",
            "Activate automatic DEM-based elevation population for the elevations layer",
            self.run_quota,
        )

        # Apply styles and reconnect quota whenever a project is loaded
        from qgis.core import QgsProject
        QgsProject.instance().readProject.connect(self._on_project_loaded)

    def unload(self):
        from qgis.core import QgsProject
        try:
            QgsProject.instance().readProject.disconnect(self._on_project_loaded)
        except Exception:
            pass
        self._quota_manager.deactivate()
        if self._menu:
            self._iface.pluginMenu().removeAction(self._menu.menuAction())
            self._menu = None
        self._actions.clear()

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

    def run_migrate(self):
        from .dialog_migrate import MigrateDialog
        exec_dialog(MigrateDialog(self._iface.mainWindow()))

    def run_add_context(self):
        from .dialog_context import AddContextDialog
        exec_dialog(AddContextDialog(self._iface.mainWindow()))

    def run_switch_styles(self):
        from .dialog_styles import StyleSetDialog
        exec_dialog(StyleSetDialog(self._iface.mainWindow()))

    def run_quota(self):
        from .dialog_quota import QuotaDialog
        exec_dialog(QuotaDialog(self._quota_manager, self._iface.mainWindow()))

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
