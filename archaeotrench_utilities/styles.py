"""QML style application logic for ArchaeoTrench Utilities.

Layer symbology is embedded in the .qgz like in any QGIS project: opening a
project never touches saved styles. Template QMLs are applied ONLY by
explicit plugin actions — deploy, Sync from template, Add context, and
set_active_style_set(). The active style set is persisted in the project
variable `at_active_style`.

Layer → QML matching rule:
  For each layer, find the QML file whose stem appears (case-insensitive)
  inside the layer name.  E.g.:
    "c100 Elevations"  →  elevations.qml
    "contexts"         →  contexts.qml
    "c100 Contexts"    →  contexts.qml

Style directory resolution order:
  1. {trench_dir}/styles/{set_name}/   — manual local override (NOT created by
     deploy: the template is the single source of truth; Sync from template
     renames a leftover local copy to styles_backup_* because it would shadow
     template updates)
  2. ~/.archaeotrench/types/{type}/styles/{set_name}/  — the normal case
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

STYLES_DIR_NAME = "styles"
DEFAULT_STYLE_SET = "default"
PROJECT_VAR_STYLE = "at_active_style"


def apply_style_set(style_set: str | None = None) -> list:
    """Apply a style set to all matching layers in the current QGIS project.

    If style_set is None, reads the project variable at_active_style,
    falling back to DEFAULT_STYLE_SET.

    Returns a list of (layer_name, qml_path | None) for reporting.
    """
    from qgis.core import QgsProject, QgsExpressionContextUtils

    project = QgsProject.instance()

    if style_set is None:
        style_set = (
            QgsExpressionContextUtils.projectScope(project).variable(PROJECT_VAR_STYLE)
            or DEFAULT_STYLE_SET
        )

    styles_dir = _resolve_styles_dir(project, style_set)
    if styles_dir is None:
        return []

    qml_index = _build_qml_index(styles_dir)
    report = []

    for layer in project.mapLayers().values():
        qml = _match_qml(layer.name(), qml_index)
        if qml:
            layer.loadNamedStyle(str(qml))
            layer.triggerRepaint()
        report.append((layer.name(), qml))

    return report


def set_active_style_set(style_set: str):
    """Persist the active style set name to the project variable and apply it."""
    from qgis.core import QgsProject, QgsExpressionContextUtils

    QgsExpressionContextUtils.setProjectVariable(
        QgsProject.instance(), PROJECT_VAR_STYLE, style_set
    )
    apply_style_set(style_set)


def available_style_sets(trench_dir: Path) -> list:
    """Return sorted list of style set names available for a trench folder.

    Merges sets from both the trench folder and the template (using the
    project type from vectors.gpkg), so the list is always complete.
    """
    sets = set()

    local_root = trench_dir / STYLES_DIR_NAME
    if local_root.is_dir():
        sets.update(d.name for d in local_root.iterdir() if d.is_dir())

    gpkg = trench_dir / "vectors.gpkg"
    if gpkg.exists():
        project_type = _read_meta_value(str(gpkg), "project_type") or "plan"
        from . import git_manager
        template_root = git_manager.get_template_dir(project_type) / STYLES_DIR_NAME
        if template_root.is_dir():
            sets.update(d.name for d in template_root.iterdir() if d.is_dir())

    return sorted(sets)


def template_styles_dir(project_type: str) -> Path:
    """Return the styles/ directory for the given template type."""
    from . import git_manager
    return git_manager.get_template_dir(project_type) / STYLES_DIR_NAME


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_styles_dir(project, style_set: str) -> Path | None:
    """Return the styles directory to use, with template fallback."""
    project_path = Path(project.fileName())

    # 1. Local trench styles
    if project_path.exists():
        local = project_path.parent / STYLES_DIR_NAME / style_set
        if local.is_dir():
            return local

    # 2. Template fallback — derive project type from the GPKG
    gpkg = _find_gpkg_for_project(project)
    if gpkg:
        project_type = _read_meta_value(gpkg, "project_type") or "plan"
        from . import git_manager
        template = git_manager.get_template_dir(project_type) / STYLES_DIR_NAME / style_set
        if template.is_dir():
            return template

    return None


def _find_gpkg_for_project(project) -> str | None:
    """Return the path to the project's GeoPackage, if any."""
    from qgis.core import QgsVectorLayer

    fallback = None
    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer):
            continue
        gpkg = layer.source().split("|")[0]
        if gpkg.endswith(".gpkg"):
            if Path(gpkg).name == "vectors.gpkg":
                return gpkg
            if fallback is None:
                fallback = gpkg
    return fallback


def _read_meta_value(gpkg_path: str, key: str) -> str | None:
    from .deploy import read_setting
    return read_setting(gpkg_path, key)


def _build_qml_index(styles_dir: Path) -> dict:
    """Return {stem_lower: Path} for every QML file in styles_dir."""
    return {p.stem.lower(): p for p in styles_dir.glob("*.qml")}


def _match_qml(layer_name: str, qml_index: dict) -> Path | None:
    """Find the best-matching QML for a layer name.

    Checks whether any QML stem is a substring of the layer name
    (case-insensitive).  Prefers longer stems to avoid false matches.
    """
    layer_lower = layer_name.lower()
    candidates = [
        (stem, path)
        for stem, path in qml_index.items()
        if stem in layer_lower
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda t: len(t[0]))[1]
