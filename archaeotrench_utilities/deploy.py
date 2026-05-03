"""Deploy a new trench QGIS project from the plugin template.

The template is now fully text-based:
  - vectors.gpkg is built from schema.sql via schema.build_gpkg()
  - the .qgz project file is generated programmatically via project_builder
"""

from __future__ import annotations

import shutil
import sqlite3
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
    from . import schema as schema_mod
    from . import project_builder
    from . import git_manager

    template_dir = git_manager.get_template_dir(project_type)

    src_schema = template_dir / "schema.sql"
    if not src_schema.exists():
        raise FileNotFoundError(
            f"Template schema not found: {src_schema}\n"
            "See README.txt in the template directory."
        )

    dest_dir = Path(output_folder) / trench_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_gpkg = dest_dir / "vectors.gpkg"
    dest_qgz = dest_dir / f"{trench_name}.qgz"

    # Build GeoPackage from text schema
    schema_mod.build_gpkg(str(src_schema), str(dest_gpkg))
    _add_meta_table(dest_gpkg, project_type, trench_name, operator, str(src_schema))

    # Copy styles directory
    src_styles = template_dir / "styles"
    if src_styles.is_dir():
        shutil.copytree(src_styles, dest_dir / "styles")

    # Generate QGIS project programmatically
    style_dir = dest_dir / "styles" / "default"
    if not style_dir.is_dir():
        style_dir = src_styles / "default"
    project_builder.build_project(
        gpkg_path=dest_gpkg,
        trench_name=trench_name,
        project_type=project_type,
        output_qgz_path=dest_qgz,
        style_dir=style_dir,
    )

    return dest_qgz


def _add_meta_table(
    gpkg_path: Path, project_type: str, trench_name: str, operator: str,
    schema_sql_path: str | None = None,
):
    """Create and populate the _meta table in the deployed GeoPackage."""
    from . import schema as schema_mod
    current_version = (
        schema_mod.get_template_version(schema_sql_path)
        if schema_sql_path else None
    ) or "unknown"

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


