# ArchaeoTrench Utilities

QGIS plugin for the **Çuka e Ajtoit** archaeological excavation (LAD-Sapienza, Sapienza University of Rome). Automates trench project creation, schema/style management, and git-based template sharing.

---

## Features

| Menu item | Description |
|---|---|
| **Deploy new trench…** | Create a new trench folder with a GeoPackage and QGIS project from the template |
| **Add context…** | Add a new excavation-context layer group to the currently open project |
| **Auto-elevation…** | Activate automatic DEM-based elevation sampling for the `elevations` layer |
| **Sync from template…** | Pull schema additions and style updates from the template into the current project |
| **Save schema to template…** | Push the current project's GeoPackage schema and layer styles back to the template |
| **Publish to repository…** | Commit template changes and open a GitHub pull request *(shown only when git is available)* |

---

## Installation

1. Clone or download this repository.
2. Copy (or symlink) the `archaeotrench_utilities/` folder into your QGIS plugins directory:
   - Linux/macOS: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
3. Enable the plugin in QGIS → *Plugins → Manage and Install Plugins*.

Requires QGIS 3.16 or above (including QGIS 4.x).

---

## Template data

The bundled template lives in `archaeotrench_utilities/template/types/`. It contains:
- `schema.sql` — text-based layer definitions (DDL)
- `styles/` — QML style files organised by style set (e.g. `default/`, `print/`)

The template is **text-based** by design: every file is plain text, fully diff-able and trackable in git.

### User-managed template (git workflow)

A shared template can be maintained in a git repository and stored locally at `~/.archaeotrench/`. When that folder exists and contains a valid `schema.sql`, the plugin uses it in preference to the bundled fallback.

```
~/.archaeotrench/
└── types/
    ├── plan/
    │   ├── schema.sql
    │   └── styles/
    │       └── default/
    │           ├── contexts.qml
    │           └── ...
    └── section/
        ├── schema.sql
        └── styles/
```

Use **Publish to repository…** to commit local changes and open a GitHub pull request against the shared upstream.

---

## Project types

| Type | Description |
|---|---|
| `plan` | Top-down plan view — contexts, detail, elevations, elev_change, limits |
| `section` | Section / elevation view |

The type is stored in `_meta.project_type` inside each deployed GeoPackage and drives all subsequent sync and export operations.

---

## GeoPackage schema (plan)

CRS: **EPSG:6870** (ETRS89 / Albania TM 2010)

| Layer | Geometry | Key fields |
|---|---|---|
| `contexts` | Polygon | `context TEXT(30)`, `context_type TEXT(100)` |
| `detail` | Polygon | `context TEXT(30)`, `material TEXT(255)` |
| `elev_change` | LineString | `context TEXT(30)` *(geometry column: `geometry`)* |
| `elevations` | Point | `elevation REAL`, `context TEXT(20)` |
| `limits` | Polygon | `trench TEXT(30)` |
| `_meta` | — | key/value store added at deploy time |

The full authoritative schema is defined in `schema.sql` inside each type folder (see `template/types/plan/README.md`).

---

## QGIS project structure

Each deployed project contains two layer-tree groups:

- **Gen** — all base layers (limits, elev_change, contexts, detail, elevations)
- **c100** *(and one group per context added later)* — same tables, display names prefixed with the context number, for independent styling and filtering

Layer → QML matching: the QML file stem (e.g. `elevations`) is matched case-insensitively as a substring of the layer name (`c100 Elevations` → `elevations.qml`). Longest stem wins.

---

## Style sets

Styles are external QML files in `styles/{set_name}/`. The active set is persisted in the project variable `at_active_style`. On every project load the plugin re-applies the active set automatically.

Multiple style sets are supported (e.g. `default`, `print`). New sets can be created directly from the **Save schema to template** dialog by typing a new name in the style-set field.

---

## Auto-elevation

When activated, the plugin samples a DEM raster and writes the elevation value to the `elevation` field of the `elevations` layer whenever a point is added or moved. The selected DEM layer name is stored in the project variable `at_dem_layer` and reconnected automatically on project load.

---

## Versioning

Each template export writes the current ISO date as the template version into the header of `schema.sql`:

```sql
-- template_version: 2026-05-03
```

Each deployed GeoPackage records the template version it was built from in `_meta.template_version`. The **Sync from template** dialog shows the current template version for reference.

---

## Module overview

| Module | Role |
|---|---|
| `plugin.py` | QGIS entry point, menu construction |
| `deploy.py` | Build GeoPackage from SQL, generate QgsProject |
| `sync.py` | Schema diff + style sync (template → project) |
| `export_schema.py` | Schema + style export (project → template) |
| `schema.py` | Parse `schema.sql`, build GeoPackage via `QgsVectorFileWriter` |
| `project_builder.py` | Programmatic QGIS project generation |
| `styles.py` | QML style application and resolution |
| `context.py` | Add-context logic (new layer group) |
| `quota.py` | DEM-based elevation auto-population |
| `git_manager.py` | Template directory resolution, git operations |
| `compat.py` | Qt5 / Qt6 compatibility constants |

---

## Development notes

- No third-party Python dependencies — stdlib + QGIS API only
- Qt5/Qt6 compatibility is centralised in `compat.py`
- Not intended for the QGIS Plugin Repository — distributed directly to the team
- Developed at LAD-Sapienza, Sapienza University of Rome
