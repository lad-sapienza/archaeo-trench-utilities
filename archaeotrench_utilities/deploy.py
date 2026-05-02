"""Deploy a new trench QGIS project from the plugin template."""

from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import date
from pathlib import Path


def deploy_trench(
    project_type: str,
    trench_name: str,
    year: str,
    operator: str,
    output_folder: str | Path,
    open_project: bool = False,
) -> Path:
    """Create a new trench project folder from the plugin template.

    Returns the Path to the created .qgz file.
    Raises FileNotFoundError if the template files are missing.
    """
    plugin_dir = Path(__file__).parent
    template_dir = plugin_dir / "template" / "types" / project_type

    src_gpkg = template_dir / "vectors.gpkg"
    src_qgs = template_dir / "template.qgs"

    if not src_gpkg.exists():
        raise FileNotFoundError(
            f"Template GeoPackage not found: {src_gpkg}\n"
            "See README.txt in the template directory."
        )
    if not src_qgs.exists():
        raise FileNotFoundError(
            f"Template QGIS project not found: {src_qgs}\n"
            "See README.txt in the template directory."
        )

    dest_dir = Path(output_folder) / trench_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_gpkg = dest_dir / "vectors.gpkg"
    dest_qgz = dest_dir / f"{trench_name}.qgz"

    shutil.copy2(src_gpkg, dest_gpkg)
    _add_meta_table(dest_gpkg, project_type, trench_name, operator)

    _pack_qgz(src_qgs, dest_qgz)

    src_styles = template_dir / "styles"
    if src_styles.is_dir():
        shutil.copytree(src_styles, dest_dir / "styles")

    return dest_qgz


def _pack_qgz(src_qgs: Path, dest_qgz: Path):
    """Zip a .qgs file into a .qgz archive, using the source filename inside."""
    with zipfile.ZipFile(dest_qgz, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src_qgs, src_qgs.name)


def _add_meta_table(gpkg_path: Path, project_type: str, trench_name: str, operator: str):
    """Create and populate the _meta table in the deployed GeoPackage."""
    changelog = _load_changelog()
    current_version = changelog.get("current_version", "1.0")

    con = sqlite3.connect(gpkg_path)
    try:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS _meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        rows = [
            ("template_version", current_version),
            ("project_type",     project_type),
            ("trench_name",      trench_name),
            ("deploy_date",      date.today().isoformat()),
            ("operator",         operator),
        ]
        cur.executemany(
            "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)", rows
        )
        con.commit()
    finally:
        con.close()


def _load_changelog() -> dict:
    import json
    changelog_path = Path(__file__).parent / "template" / "changelog.json"
    with open(changelog_path, encoding="utf-8") as f:
        return json.load(f)
