# CAjDeployer — QGIS Plugin for Çuka e Ajtoit

## Project overview

**CAjDeployer** is a QGIS plugin for the archaeological excavation at Çuka e Ajtoit (Albania), developed at LAD-Sapienza. It automates the creation of standardised QGIS projects for new trenches, manages style updates across existing projects, and tracks schema migrations on the reference GeoPackage.

The plugin is fully self-contained: the reference GeoPackage, styles, and template project all live inside the plugin directory itself. No external folder dependencies. It is specific to the Çuka e Ajtoit project and not intended for general distribution.

---

## Template update workflow

To update the template after the plugin is built:

1. Open `caj_deployer/template/types/plan/template.qgs` (or `section/`) directly in QGIS
2. Make changes — styles, layer configuration, etc.
3. Save the project in place (overwrites the file inside the plugin folder)
4. Edit `changelog.json`: add a new entry, bump the version
   - Style changes only → bump `MINOR`, set `type: "minor"`
   - Schema changes → bump `MAJOR`, set `type: "major"`, add `migration_sql`
5. Reload the plugin in QGIS (Plugin Reloader) — new deployments will use the updated template

No rebuild or reinstall required for template/style updates.

---

## Plugin structure

```
caj_deployer/
├── metadata.txt
├── __init__.py
├── plugin.py                  ← QGIS plugin entry point
├── compat.py                  ← Qt5/Qt6 compatibility shim
├── dialog_deploy.py           ← Deploy new trench dialog
├── dialog_sync.py             ← Sync styles dialog
├── dialog_migrate.py          ← Schema migration dialog
├── dialog_quota.py            ← Auto-elevation activation dialog
├── dialog_styles.py           ← Switch style set dialog
├── dialog_context.py          ← Add context dialog
├── deploy.py                  ← Deploy logic
├── sync.py                    ← Style sync logic
├── migrate.py                 ← Schema migration logic
├── quota.py                   ← Auto-elevation sampling logic
├── styles.py                  ← QML style application logic
├── context.py                 ← Add-context logic
├── version.py                 ← Version parsing utilities
└── template/
    ├── changelog.json         ← Template versioning and changelog
    ├── types/
    │   ├── plan/
    │   │   ├── vectors.gpkg   ← Reference GeoPackage (plan view)
    │   │   ├── template.qgs   ← Reference QGIS project (plan view)
    │   │   └── styles/
    │   │       ├── default/   ← Default style set
    │   │       │   ├── contexts.qml
    │   │       │   ├── detail.qml
    │   │       │   ├── elevations.qml
    │   │       │   └── elev_change.qml
    │   │       └── print/     ← (example additional style set)
    │   └── section/
    │       ├── vectors.gpkg   ← Reference GeoPackage (section/elevation view)
    │       ├── template.qgs   ← Reference QGIS project (section/elevation view)
    │       └── styles/
    │           └── default/
```

---

## Project types

The plugin supports two project types, selectable at deploy time:

| Type | Description | Template folder |
|---|---|---|
| `plan` | Plan view (horizontal sections, features, US) | `template/types/plan/` |
| `section` | Section / elevation view | `template/types/section/` |

Each type has its own GeoPackage and QGIS project template. Both share the same versioning and changelog system.

---

## GeoPackage schema (plan — from actual template)

CRS: **EPSG:6870** (ETRS89 / Albania TM 2010) for all layers in both project types.

The template GPKG (`vectors.gpkg`) contains the following layers. This is the real schema extracted from the template file — use these exact table and field names throughout the plugin code.

### `contexts` — Polygon
| Field | Type | Notes |
|---|---|---|
| `fid` | INTEGER | Primary key |
| `geom` | POLYGON | |
| `context` | TEXT(30) | US identifier |
| `context_type` | TEXT(100) | Type/interpretation |

### `detail` — Polygon
| Field | Type | Notes |
|---|---|---|
| `fid` | INTEGER | Primary key |
| `geom` | POLYGON | |
| `context` | TEXT(30) | US reference |
| `material` | TEXT(255) | |

### `elev_change` — LineString
| Field | Type | Notes |
|---|---|---|
| `fid` | INTEGER | Primary key |
| `geometry` | LINESTRING | |
| `context` | TEXT(30) | US reference |

### `elevations` — Point
| Field | Type | Notes |
|---|---|---|
| `fid` | INTEGER | Primary key |
| `geom` | POINT | |
| `elevation` | REAL | Auto-populated from DEM (see Feature 4) |
| `context` | TEXT(20) | US reference |

### `limits` — Polygon
| Field | Type | Notes |
|---|---|---|
| `fid` | INTEGER | Primary key |
| `geom` | POLYGON | |
| `trench` | TEXT(30) | Trench name |

### `_meta` — Key-value store (added by plugin at deploy time)
```sql
CREATE TABLE _meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT INTO _meta VALUES ('template_version', '1.0');
INSERT INTO _meta VALUES ('project_type', 'plan');
INSERT INTO _meta VALUES ('trench_name', 'T23');
INSERT INTO _meta VALUES ('deploy_date', '2025-05-01');
INSERT INTO _meta VALUES ('operator', 'Julian');
```

---

## QGIS project structure (plan — from actual template)

The template project (`RENAME_plan.qgz`) has the following layer setup. Layers are loaded **multiple times from the same GPKG table** to support alternative visualisations (e.g. different context filters, different styles). The project file is renamed to `{trench_name}.qgz` at deploy time.

### Layer tree groups
- `Gen` — general/reference layers
- `c100` — context-100 visualisation group (example of alternative view)

### Layer instances

| Display name | GPKG table | Notes |
|---|---|---|
| `c100 Contexts` | `contexts` | Alternative view, filtered by context |
| `contexts` | `contexts` | Default view |
| `detail` | `detail` | |
| `c100 Detail` | `detail` | Alternative view |
| `elev_change` | `elev_change` | |
| `c100 Elevations` | `elevations` | Alternative view |
| `elevations` | `elevations` | Default view — **this is the quota layer** |
| `limits` | `limits` | |

Multiple instances of the same table are standard QGIS practice here. The deploy script must update **all** datasource paths when renaming the GPKG, not just the first occurrence.

### Styles
Styles are stored as external **QML files** in `styles/{set_name}/*.qml`, not embedded in the QGZ. The plugin applies them programmatically via `layer.loadNamedStyle()` every time a project is loaded (`readProject` signal). This makes styles fully versionable and diff-able in git.

**Layer → QML matching:** the QML filename stem (e.g. `elevations`) is matched case-insensitively as a substring of the layer name (e.g. `c100 Elevations` → `elevations.qml`). The longest-stem match wins to avoid false positives.

**Multiple style sets** are supported via subdirectories: `styles/default/`, `styles/print/`, etc. The active set is stored in the project variable `caj_active_style` and can be switched via **Plugins → CAjDeployer → Switch style set…**.

---

## Auto-quota layer and field names (real values)

| Setting | Value |
|---|---|
| Quota layer name | `elevations` (exact match, default view instance) |
| Quota field name | `elevation` |

---

## Versioning and changelog

`template/changelog.json` tracks versions for both project types. Each entry has a `type` field (`minor` or `major`) and per-type changes with a human-readable `description` and, for major versions, `migration_sql` steps.

```json
{
  "current_version": "1.0",
  "history": [
    {
      "version": "1.0",
      "date": "2026-05-01",
      "type": "minor",
      "changes": {
        "plan": {
          "description": "Initial release."
        },
        "section": {
          "description": "Initial release."
        }
      }
    }
  ]
}
```

Version format: `MAJOR.MINOR`
- `minor` bump: style changes only — reversible, any version can be applied in any direction
- `major` bump: schema changes — forward only, backup created automatically before migration

The `description` field is the human-readable changelog shown in the plugin UI and usable as release notes.

---

## Plugin features

### 1. Deploy new trench project

**Dialog inputs:**
- Trench name (e.g. `T23`)
- Year (e.g. `2025`)
- Operator name
- Project type: `plan` or `section`
- Output folder (file picker)

**Logic (`deploy.py`):**
1. Copy `template/types/{type}/vectors.gpkg` → `{output}/{trench_name}/vectors.gpkg`
2. Add `_meta` table to new GPKG and populate it
3. Copy `template/types/{type}/template.qgs` → `{output}/{trench_name}/{trench_name}.qgz`
4. Copy `template/types/{type}/styles/` → `{output}/{trench_name}/styles/`
5. Optionally open the new project in QGIS

### 2. Sync styles

Styles are external QML files in `styles/{set_name}/`. Sync replaces the entire `styles/` folder in each trench with the one from the template.

**Dialog inputs:**
- Select one or more existing trench folders (or scan a root folder)

**Logic (`sync.py`):**
1. Read `_meta.project_type` from `vectors.gpkg` to determine which template to use
2. For each trench folder: replace `{trench_dir}/styles/` with `template/types/{type}/styles/` via `shutil.copytree`
3. Update `_meta.template_version` in the GPKG
4. Downgrade is allowed: any version can be applied in any direction

**UI shows:** list of selected trench folders, status after sync

### 3. Schema migration (forward only)

**Dialog inputs:**
- Select one or more existing trench GPKG files
- Shows available migrations from current version to latest

**Logic (`migrate.py`):**
1. Read `_meta.template_version` from each GPKG
2. Determine which migration steps are needed (sequential)
3. Show warning: "This operation cannot be undone"
4. Before migrating: create a backup copy `{trench_name}_backup_{date}.gpkg`
5. Apply SQL migration steps in order
6. Update `_meta.template_version`

Migration steps are defined inline in `changelog.json` under `migration_sql` (array of SQL strings, executed in order).

### 4. Auto-populate elevation from DEM

Automatically samples a DEM raster and writes the elevation value to the `elevation` field of the `elevations` layer whenever a point is added or moved.

**Activation dialog inputs:**
- Select DEM layer (dropdown of raster layers currently loaded in the project)
- Layer name and field shown read-only for confirmation: `elevations` / `elevation`

**Persistence:**
- The selected DEM layer name is saved to project variable `caj_dem_layer`
- On project load, the plugin re-connects the signal automatically

**Logic (`quota.py`):**
1. On activation: save DEM layer name to project variable; connect signals
2. On `featureAdded` or `geometryChanged` on the `elevations` layer:
   - Get point geometry in layer CRS (EPSG:6870)
   - Reproject to DEM CRS if different (via `QgsCoordinateTransform`)
   - Sample DEM with `QgsRasterDataProvider.identify(point, QgsRaster.IdentifyFormatValue)`
   - If valid: write value to `elevation` field via `layer.changeAttributeValue()`
   - If outside DEM extent or nodata: show `QgsMessageBar` warning; do not write
3. On project load (`QgsProject.instance().readProject` signal): re-connect if `caj_dem_layer` is set

**Implementation notes:**
- Use `layer.beginEditCommand()` / `endEditCommand()` for undoable writes
- Guard against duplicate signal connections: disconnect before reconnect

### 5. Add context

Adds a layer group for a new excavation context to the currently open trench project.

**Dialog inputs:**
- Context name (e.g. `c100`)

**Logic (`context.py`):**
1. Find the project's GeoPackage path from any existing vector layer datasource (prefers `vectors.gpkg`)
2. Insert a new group named `{context_name}` at the top of the layer tree
3. For each entry in `CONTEXT_LAYERS` = `[("Elevations", "elevations"), ("Detail", "detail"), ("Contexts", "contexts")]`:
   - Create a `QgsVectorLayer` pointing to `{gpkg_path}|layername={table}`
   - Name it `{context_name} {Layer Type}` (e.g. `c100 Elevations`)
   - Add to project (not to legend), then add to the group
   - Apply matching QML from the active style set via the same `_match_qml` logic used by `styles.py`

---

## Project variables

| Variable | Feature | Description |
|---|---|---|
| `caj_dem_layer` | Auto-quota | Name of the DEM raster layer to sample elevations from |

Read/write via `QgsExpressionContextUtils`, using `caj_` prefix to avoid collisions with other plugins.

```python
# Write
QgsExpressionContextUtils.setProjectVariable(
    QgsProject.instance(), 'caj_dem_layer', layer_name)

# Read
QgsExpressionContextUtils.projectScope(
    QgsProject.instance()).variable('caj_dem_layer')
```

---

## Key constraints

- **Self-contained**: no external folder dependencies; everything ships inside the plugin zip
- **No third-party Python dependencies**: use only QGIS API (`qgis.core`, `qgis.PyQt`) and Python stdlib (`shutil`, `sqlite3`, `json`, `os`, `pathlib`, `zipfile`)
- **SQLite/GPKG access**: Python `sqlite3` directly for schema operations and `_meta`; QGIS vector API for feature read/write during quota population
- **QGZ manipulation**: Python `zipfile` to unpack/repack `.qgz` for path updates (deploy) and style replacement (sync)
- **CRS**: EPSG:6870 for all layers in both project types
- **Path handling**: `pathlib.Path` throughout; cross-platform (Windows + Linux/Mac)
- **Layer datasource update**: must replace all occurrences of the template GPKG filename in the QGS XML, not just the first

---

## Development notes

- Target QGIS versions: 3.16 LTR and above, including QGIS 4.x
- Developed iteratively with Claude Code
- Logic modules (`deploy.py`, `sync.py`, `migrate.py`, `quota.py`) are isolated from QGIS API where possible for easier testing
- UI: inline PyQt5/PyQt6 widgets via `qgis.PyQt` shim; Qt Designer `.ui` files not required
- Not intended for QGIS Plugin Repository — distributed as zip directly to team

### Qt5/Qt6 compatibility

QGIS 3.x uses Qt5/PyQt5; QGIS 4.x uses Qt6/PyQt6. The main breaking change is that Qt6 requires **fully-scoped enums** (e.g. `QDialogButtonBox.StandardButton.Ok` instead of `QDialogButtonBox.Ok`).

All Qt enum constants and renamed methods are centralised in `compat.py`, which detects the Qt version at import time and exposes version-neutral names:

```python
from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL, SELECTION_ROWS, exec_dialog, ...
```

Key renames handled by `compat.py`:

| QGIS 3 / PyQt5 | QGIS 4 / PyQt6 | compat name |
|---|---|---|
| `QDialogButtonBox.Ok` | `QDialogButtonBox.StandardButton.Ok` | `BTN_OK` |
| `Qt.Horizontal` | `Qt.Orientation.Horizontal` | `HORIZONTAL` |
| `QAbstractItemView.SelectRows` | `QAbstractItemView.SelectionBehavior.SelectRows` | `SELECTION_ROWS` |
| `QAbstractItemView.NoEditTriggers` | `QAbstractItemView.EditTrigger.NoEditTriggers` | `NO_EDIT_TRIGGERS` |
| `QAbstractItemView.ExtendedSelection` | `QAbstractItemView.SelectionMode.ExtendedSelection` | `EXTENDED_SELECTION` |
| `QHeaderView.Stretch` | `QHeaderView.ResizeMode.Stretch` | `HEADER_STRETCH` |
| `dlg.exec_()` | `dlg.exec()` | `exec_dialog(dlg)` |

The QGIS raster identify format constant also changed namespace in QGIS 4 (`QgsRaster.IdentifyFormatValue` → `Qgis.RasterIdentifyFormat.Value`); `compat.raster_identify_format_value()` handles both.

`metadata.txt` declares `qgisMinimumVersion=3.16` and `qgisMaximumVersion=4.99`.

---

## Open questions / future work

- Prospetto template: not yet provided — same process applies once available
- Multi-type sync: plugin reads `_meta.project_type` from each GPKG and routes to correct template automatically
- Master project integration: out of scope for now; trenches are imported manually
