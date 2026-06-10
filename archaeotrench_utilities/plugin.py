"""Main QGIS plugin class for ArchaeoTrench Utilities."""

from __future__ import annotations

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu

from .compat import exec_dialog
from .icons import themed_icon

_ICON = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))


class ArchaeoTrenchPlugin:
    def __init__(self, iface):
        self._iface = iface
        self._actions: list = []
        self._template_actions: list = []   # disabled until template is available
        self._menu: QMenu | None = None
        self._toolbar = None
        self._sb_menu: QMenu | None = None
        self._quota_manager = None

    # ------------------------------------------------------------------
    # QGIS plugin lifecycle
    # ------------------------------------------------------------------

    def initGui(self):
        from .quota import QuotaManager
        self._quota_manager = QuotaManager(self._iface)

        plugins_menu = self._iface.pluginMenu()
        self._menu = QMenu("ArchaeoTrench Utilities", self._iface.mainWindow())
        self._menu.setIcon(_ICON)
        plugins_menu.addMenu(self._menu)

        self._toolbar = self._iface.addToolBar("ArchaeoTrench Utilities")
        self._toolbar.setObjectName("ArchaeoTrenchUtilitiesToolBar")

        self._template_actions.append(self._add_action(
            "Deploy new trench…",
            "Create a new trench QGIS project from the template",
            self.run_deploy,
            "shovel",
        ))
        self._template_actions.append(self._add_action(
            "Settings…",
            "View and edit project and template repository settings",
            self.run_settings,
            "settings",
        ))
        self._menu.addSeparator()
        self._toolbar.addSeparator()
        self._template_actions.append(self._add_action(
            "Add context…",
            "Add a layer group for a new excavation context to the current project",
            self.run_add_context,
            "library-plus",
        ))
        self._add_action(
            "Auto-elevation…",
            "Activate automatic DEM-based elevation population for the elevations layer",
            self.run_quota,
            "mountain",
        )
        self._menu.addSeparator()
        self._toolbar.addSeparator()
        self._template_actions.append(self._add_action(
            "Sync from template…",
            "Update existing trench GeoPackages and styles from the current template",
            self.run_sync,
            "refresh",
        ))
        self._template_actions.append(self._add_action(
            "Save schema to template…",
            "Export the current project's GeoPackage schema and styles to the plugin template",
            self.run_export_schema,
            "database-export",
        ))
        self._menu.addSeparator()
        self._toolbar.addSeparator()
        self._add_action(
            "Template repository…",
            "Download or update the template, and publish changes to GitHub",
            self.run_publish,
            "brand-git",
        )

        # Section Builder submenu — independent of the ATU template system
        self._menu.addSeparator()
        self._toolbar.addSeparator()
        self._sb_menu = QMenu("Section Builder", self._iface.mainWindow())
        self._sb_menu.setIcon(themed_icon("section-sign"))
        self._menu.addMenu(self._sb_menu)

        self._add_sb_action(
            "New section…",
            "Initialise a new section: create sb_* tables and add layers to the project",
            self.run_sb_project,
            "square-plus",
        )
        self._add_sb_action(
            "Extract profile…",
            "Sample the DEM along the profile line and write elevation points",
            self.run_sb_extract,
            "chart-line",
        )
        self._add_sb_action(
            "Generate segments…",
            "Build section linestrings from classified profile points",
            self.run_sb_segments,
            "vector-spline",
        )
        self._add_sb_action(
            "Populate elevation labels…",
            "Auto-fill elev field on sb_section_elevations from nearest profile point",
            self.run_sb_elevations,
            "tag",
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
        if self._toolbar:
            self._iface.mainWindow().removeToolBar(self._toolbar)
            self._toolbar.deleteLater()
            self._toolbar = None
        if self._menu:
            self._iface.pluginMenu().removeAction(self._menu.menuAction())
            self._menu = None
        self._sb_menu = None
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

    def run_settings(self):
        from .dialog_settings import SettingsDialog
        exec_dialog(SettingsDialog(self._iface, self._iface.mainWindow()))

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
    # Section Builder runners
    # ------------------------------------------------------------------

    def run_sb_project(self):
        from .dialog_sb_project import SbProjectDialog
        exec_dialog(SbProjectDialog(self._iface, self._iface.mainWindow()))

    def run_sb_extract(self):
        from .dialog_sb_extract import SbExtractDialog
        exec_dialog(SbExtractDialog(self._iface, self._iface.mainWindow()))

    def run_sb_segments(self):
        from .dialog_sb_segments import SbSegmentsDialog
        exec_dialog(SbSegmentsDialog(self._iface, self._iface.mainWindow()))

    def run_sb_elevations(self):
        from .dialog_sb_elevations import SbElevationsDialog
        exec_dialog(SbElevationsDialog(self._iface, self._iface.mainWindow()))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_action(self, text: str, tooltip: str, callback, icon_name: str | None = None) -> QAction:
        icon = themed_icon(icon_name) if icon_name else _ICON
        action = QAction(icon, text, self._iface.mainWindow())
        action.setToolTip(tooltip)
        action.triggered.connect(callback)
        self._menu.addAction(action)
        self._toolbar.addAction(action)
        self._actions.append(action)
        return action

    def _add_sb_action(self, text: str, tooltip: str, callback, icon_name: str | None = None) -> QAction:
        """Add an action to the Section Builder submenu and the toolbar."""
        icon = themed_icon(icon_name) if icon_name else _ICON
        action = QAction(icon, text, self._iface.mainWindow())
        action.setToolTip(f"Section Builder — {tooltip}")
        action.triggered.connect(callback)
        self._sb_menu.addAction(action)
        self._toolbar.addAction(action)
        self._actions.append(action)
        return action
