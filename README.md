![archaeoTrench Utilities by LAD](assets/at-banner-750×250.png)

# archaeoTrench Utilities

A QGIS plugin for managing archaeological excavation projects. It automates the full lifecycle of a trench project: creating a standardised GeoPackage and QGIS project from a shared text-based template, keeping projects in sync as the template evolves, adding new excavation-context layer groups, and publishing template changes back to a shared GitHub repository.

Developed at [LAD — Laboratorio di Archeologia Digitale](https://lad.saras.uniroma1.it), Sapienza University of Rome.

---

## How it works

The plugin separates **template** from **project**:

- The **template** (stored in `~/.archaeotrench/`) defines the layer schema (`schema.sql`) and visual styles (QML files). It is text-based, fully diff-able, and can be shared via a git repository.
- A **trench project** is a self-contained folder with a GeoPackage (`vectors.gpkg`) and a QGIS project file (`.qgz`), generated from the template at deploy time.

The two can diverge as fieldwork progresses and the schema evolves. The plugin provides tools to reconcile them in both directions.

---

## Features

| Menu item | What it does |
|---|---|
| **Deploy new trench…** | Create a GeoPackage + QGIS project from the template |
| **Add context…** | Add a context layer group to the current project |
| **Settings…** | View/edit per-project settings and template repository URLs |
| **Auto-elevation…** | Auto-populate an elevation field by sampling a DEM raster |
| **Sync from template…** | Add missing fields and refresh styles from the template |
| **Save schema to template…** | Export the current schema and styles back to the template |
| **Template repository…** | Download, update, or publish the shared template via git / ZIP |

---

### Deploy new trench

Creates a new trench project from scratch:

1. Parses `schema.sql` from the template to get layer definitions (geometry type, CRS, fields).
2. Builds a fresh GeoPackage using QGIS's `QgsVectorFileWriter` — one layer per table.
3. Writes a `aTrench_settings` table inside the GeoPackage recording the trench name, project type, and template version.
4. Generates a `.qgz` QGIS project programmatically: adds all layers in a **Gen** group, applies styles from the template, and saves.

The output is a portable, self-contained project folder ready to be opened in QGIS.

### Settings

A central panel with two sections:

**Project settings** — stored in the `aTrench_settings` table inside the GeoPackage:

| Field | Notes |
|---|---|
| `project_type` | `plan` or `section` — drives template selection everywhere |
| `trench_name` | Human-readable project identifier |
| `operator` | Person responsible for the project |
| `deploy_date` | Date the project was first created or adopted |
| `plugin_version` | Plugin version that last wrote the settings |
| `template_version` | Template version at last deploy or sync |
| `last_sync_date` | Date of the most recent Sync from template |

Opening Settings on a project that has no `aTrench_settings` table (e.g. an externally created GeoPackage) writes the table from scratch, effectively **adopting** that project into the plugin ecosystem. Saving can optionally trigger Sync from template immediately after.

**Template repository settings** — stored in `~/.archaeotrench/config.json`:

| Field | Notes |
|---|---|
| Shared repo URL | Upstream template repository (default: LAD upstream) |
| Push / fork URL | Optional fork URL for publishing via pull request |

URL fields auto-save on focus-out. These settings were previously split across the publish dialog.

### Add context

Each excavation context (e.g. `c100`, `c101`) gets its own layer group pointing to the same GeoPackage tables. The plugin:

1. Inserts a new group at the top of the layer tree.
2. Adds one vector layer per selected table (e.g. `elevations`, `detail`, `contexts`).
3. Applies the matching QML style from the template, deferred via `QTimer` so QGIS's own post-load style initialisation does not overwrite it.

Multiple style sets are supported. If more than one is available, the dialog offers a dropdown; otherwise it reports the single set being used.

### Auto-elevation

When a point is added to or moved within a designated vector layer, the plugin:

1. Reprojects the point geometry to the DEM's CRS if needed.
2. Samples the raster value at that location via `QgsRasterDataProvider.identify()`.
3. Writes the rounded elevation value to a user-selected numeric field.

Settings (DEM layer, elevation layer, field name, decimal precision) are stored as project variables and restored automatically when the project is re-opened.

### Sync from template

Brings an existing trench project up to date with the current template without touching any field data:

- **Schema sync**: compares the template's `schema.sql` against each layer in the open project. Fields present in the template but missing from a layer are added via `QgsVectorLayerUtils`. Fields that exist only in the project are left untouched.
- **Style sync**: for each layer in the project, finds the best-matching QML file in the selected style set and reloads it.

The dialog lists every layer with its pending field additions and the QML file that will be applied, so the user can review before committing.

### Save schema to template

Exports the current project's schema and styles back to the template:

- Reads `gpkg_contents`, `gpkg_geometry_columns`, and `PRAGMA table_info()` from the project's GeoPackage via `sqlite3`.
- Writes a new `schema.sql` in the canonical comment-annotated format.
- Calls `layer.saveNamedStyle()` for every base layer (non-context-prefixed) to export QML files into the selected style set folder.

New style sets can be created by typing a new name into the editable combo — the folder is created only when the export is actually triggered, not on each keystroke.

### Template repository

Manages the `~/.archaeotrench/` template directory and its connection to a shared GitHub repository:

| Scenario | Available actions |
|---|---|
| No template yet | **Download template** (ZIP, no git required) · **Clone with git** |
| Template present, no git | **Update template** (re-download ZIP) |
| Git repo, no local changes | **Pull latest** |
| Git repo, local changes | **Pull latest** · **Commit & Push** |

**Commit & Push** behaviour:
- If no fork URL is configured (or it matches the shared repo URL), changes are pushed directly to `origin` — useful for team members with write access.
- If a separate fork URL is set, changes are pushed to the fork remote and a browser tab opens the GitHub compare page to start a pull request.

URL fields auto-save on focus-out — no explicit "Save" button needed.

---

## Installation

1. Clone or download this repository.
2. Copy (or symlink) the `archaeotrench_utilities/` folder into your QGIS plugins directory:
   - **macOS / Linux**: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - **Windows**: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
3. Enable the plugin in QGIS → *Plugins → Manage and Install Plugins*.
4. Open **Plugins → ArchaeoTrench Utilities → Template repository…** to download or clone the template.

Requires QGIS **3.16** or above (including QGIS 4.x). No additional Python dependencies — stdlib and the QGIS API only.

---

## Template directory layout

```
~/.archaeotrench/
└── types/
    ├── plan/
    │   ├── schema.sql          ← layer definitions (text DDL)
    │   └── styles/
    │       ├── default/
    │       │   ├── contexts.qml
    │       │   ├── detail.qml
    │       │   ├── elev_change.qml
    │       │   ├── elevations.qml
    │       │   └── limits.qml
    │       └── <custom-set>/   ← additional style sets
    │           └── ...
    └── section/
        ├── schema.sql
        └── styles/
```

The template is maintained in a separate repository ([lad-sapienza/caj-archeo-trench](https://github.com/lad-sapienza/caj-archeo-trench)) and is downloaded or cloned into `~/.archaeotrench/` on first use.

---

## schema.sql format

Each layer is declared with SQL comments carrying its spatial metadata, followed by a `CREATE TABLE` for the non-geometry fields:

```sql
-- template_version: 2026-05-03

-- layer: elevations
-- geometry: Point
-- crs: EPSG:6870
-- geometry_column: geom
CREATE TABLE elevations (
    elevation REAL,
    context TEXT(20)
);

-- layer: contexts
-- geometry: Polygon
-- crs: EPSG:6870
-- geometry_column: geom
CREATE TABLE contexts (
    context TEXT(30),
    context_type TEXT(100)
);
```

Field types map to QGIS/OGR types: `TEXT(n)` → string, `REAL` → double, `INTEGER` → int. The geometry column is handled by OGR; the SQL comment tells the plugin which column name to use.

---

## GeoPackage schema (plan type)

CRS: **EPSG:6870** (ETRS89 / Albania TM 2010)

| Layer | Geometry | Fields |
|---|---|---|
| `contexts` | Polygon | `context TEXT(30)`, `context_type TEXT(100)` |
| `detail` | Polygon | `context TEXT(30)`, `material TEXT(255)` |
| `elev_change` | LineString | `context TEXT(30)` |
| `elevations` | Point | `elevation REAL`, `context TEXT(20)` |
| `limits` | Polygon | `trench TEXT(30)` |
| `_meta` | — | key/value store (see Settings) |

---

## Project types

| Type | Description |
|---|---|
| `plan` | Top-down plan view |
| `section` | Stratigraphic section / elevation view |

The type is written to `aTrench_settings` → `project_type` inside the GeoPackage at deploy time and drives all subsequent sync and export operations.

---

## QGIS project structure

Each deployed project has a single **Gen** group containing all base layers in draw order (limits → elev_change → contexts → detail → elevations). Additional context groups (e.g. **c100**) are added later via *Add context…* — they share the same GeoPackage tables with context-prefixed display names.

QML matching uses longest-stem substring: `elevations.qml` matches both `Elevations` and `c100 Elevations`.

---

## Module overview

| Module | Role |
|---|---|
| `plugin.py` | QGIS entry point, menu construction, action state management |
| `deploy.py` | Orchestrates GeoPackage creation and project generation |
| `schema.py` | Parses `schema.sql`, builds GeoPackage via `QgsVectorFileWriter` |
| `project_builder.py` | Programmatic QGIS project generation (layers, groups, styles, save) |
| `sync.py` | Schema diff + style sync: template → open project |
| `export_schema.py` | Schema + style export: open project → template |
| `context.py` | Add-context logic (new layer group + deferred style application) |
| `dialog_settings.py` | Settings dialog (project + template config, adopt flow) |
| `styles.py` | QML file resolution and application; style-set enumeration |
| `quota.py` | DEM-based elevation auto-population; safe layer-ID pattern |
| `git_manager.py` | Template directory resolution, ZIP download, git operations |
| `compat.py` | Qt5 / Qt6 / QGIS 3 / QGIS 4 compatibility shims |

---

## Notes

- All template files are plain text — `schema.sql` and QML files can be reviewed and merged in any git client.
- The plugin never stores direct layer references across Qt event boundaries; it uses layer IDs and looks layers up from `QgsProject` on demand, avoiding crashes during QGIS shutdown.
- Developed at [LAD-Sapienza](https://lad.saras.uniroma1.it) for the Çuka e Ajtoit excavation project. Not intended for the QGIS Plugin Repository — distributed directly to the team.
