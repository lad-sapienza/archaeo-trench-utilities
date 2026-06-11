"""Deploy a new trench QGIS project from the plugin template.

The template is now fully text-based:
  - vectors.gpkg is built from schema.sql via schema.build_gpkg()
  - the .qgz project file is generated programmatically via project_builder
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

SETTINGS_TABLE = "aTrench_settings"


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
    write_project_settings(dest_gpkg, project_type, trench_name, operator, str(src_schema))

    # Styles are applied from the template directory — no local copy is made.
    # A trench-local styles/ folder would take priority at every project load
    # (see styles.py), shadowing the template and silently reverting any
    # future "Sync from template" style update.
    style_dir = template_dir / "styles" / "default"
    project_builder.build_project(
        gpkg_path=dest_gpkg,
        trench_name=trench_name,
        project_type=project_type,
        output_qgz_path=dest_qgz,
        style_dir=style_dir,
    )

    return dest_qgz


def write_project_settings(
    gpkg_path: Path, project_type: str, trench_name: str, operator: str,
    schema_sql_path: str | None = None,
):
    """Create/update the aTrench_settings table in a GeoPackage."""
    from . import schema as schema_mod
    current_version = (
        schema_mod.get_template_version(schema_sql_path)
        if schema_sql_path else None
    ) or "unknown"

    con = sqlite3.connect(gpkg_path)
    try:
        _migrate_if_needed(con)
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS {SETTINGS_TABLE} (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        rows = [
            ("project_type",     project_type),
            ("trench_name",      trench_name),
            ("operator",         operator),
            ("deploy_date",      date.today().isoformat()),
            ("plugin_version",   _plugin_version()),
            ("template_version", current_version),
        ]
        con.executemany(
            f"INSERT OR REPLACE INTO {SETTINGS_TABLE} (key, value) VALUES (?, ?)", rows
        )
        con.commit()
    finally:
        con.close()


def read_setting(gpkg_path: str | Path, key: str) -> str | None:
    """Read one value from the aTrench_settings table (migrates _meta if needed)."""
    try:
        con = sqlite3.connect(gpkg_path)
        _migrate_if_needed(con)
        row = con.execute(
            f"SELECT value FROM {SETTINGS_TABLE} WHERE key=?", (key,)
        ).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def write_setting(gpkg_path: str | Path, key: str, value: str):
    """Write one key/value pair into the aTrench_settings table."""
    try:
        con = sqlite3.connect(gpkg_path)
        _migrate_if_needed(con)
        con.execute(
            f"INSERT OR REPLACE INTO {SETTINGS_TABLE} (key, value) VALUES (?, ?)",
            (key, value),
        )
        con.commit()
        con.close()
    except Exception:
        pass


def read_all_settings(gpkg_path: str | Path) -> dict:
    """Return all rows of aTrench_settings as a dict (empty if table absent)."""
    try:
        con = sqlite3.connect(gpkg_path)
        _migrate_if_needed(con)
        rows = con.execute(f"SELECT key, value FROM {SETTINGS_TABLE}").fetchall()
        con.close()
        return dict(rows)
    except Exception:
        return {}


def _migrate_if_needed(con: sqlite3.Connection):
    """Rename legacy _meta table to aTrench_settings if the new name doesn't exist yet."""
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if SETTINGS_TABLE not in tables and "_meta" in tables:
        con.execute(f"ALTER TABLE _meta RENAME TO {SETTINGS_TABLE}")
        con.commit()


def _plugin_version() -> str:
    try:
        import configparser
        p = configparser.ConfigParser()
        p.read(Path(__file__).parent / "metadata.txt")
        return p["general"]["version"]
    except Exception:
        return "unknown"


