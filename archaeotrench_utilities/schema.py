"""Parse schema.sql and build a GeoPackage from it.

schema.sql format:
    -- template_version: YYYY-MM-DD   (optional header)

    -- layer: <name>
    -- geometry: <Point|Polygon|LineString>
    -- crs: <EPSG:NNNN>
    -- geometry_column: <column_name>
    CREATE TABLE <name> (
        field1 TYPE1,
        field2 TYPE2(length)
    );
"""

import re

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransformContext,
    QgsField,
    QgsFields,
    QgsVectorFileWriter,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant


# ---------------------------------------------------------------------------
# Field type mapping: SQL type token → (QVariant.Type, length)
# ---------------------------------------------------------------------------

def _sql_type_to_qvariant(sql_type: str):
    """Return (QVariant.Type, length) from a SQL type string like TEXT(20) or REAL."""
    upper = sql_type.strip().upper()
    m = re.match(r'(\w+)(?:\((\d+)\))?', upper)
    base = m.group(1) if m else upper
    length = int(m.group(2)) if m and m.group(2) else 0

    if base in ('TEXT', 'VARCHAR', 'CHAR', 'CHARACTER'):
        return QVariant.String, length
    if base in ('INTEGER', 'INT', 'BIGINT', 'SMALLINT'):
        return QVariant.Int, length
    if base in ('REAL', 'FLOAT', 'DOUBLE', 'NUMERIC', 'DECIMAL'):
        return QVariant.Double, length
    return QVariant.String, length  # safe fallback


# ---------------------------------------------------------------------------
# Geometry type mapping: string → QgsWkbTypes constant
# ---------------------------------------------------------------------------

_GEOM_MAP = {
    'POINT':      QgsWkbTypes.Point,
    'MULTIPOINT': QgsWkbTypes.MultiPoint,
    'LINESTRING': QgsWkbTypes.LineString,
    'MULTILINESTRING': QgsWkbTypes.MultiLineString,
    'POLYGON':    QgsWkbTypes.Polygon,
    'MULTIPOLYGON': QgsWkbTypes.MultiPolygon,
}


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_schema(schema_sql_path: str) -> list:
    """Parse a schema.sql file and return a list of layer definition dicts.

    Each dict has keys:
        name, geometry, crs, geometry_column, fields
    where fields is a list of {name, sql_type} dicts.
    """
    with open(schema_sql_path, encoding='utf-8') as fh:
        content = fh.read()

    layers = []
    current_meta = {}

    for line in content.splitlines():
        stripped = line.strip()

        # Metadata comment lines
        meta_match = re.match(r'^--\s+(\w+):\s+(.+)$', stripped)
        if meta_match:
            current_meta[meta_match.group(1)] = meta_match.group(2).strip()
            continue

        # CREATE TABLE opens a layer block
        ct_match = re.match(r'^CREATE TABLE\s+(\w+)\s*\(', stripped, re.IGNORECASE)
        if ct_match:
            name = ct_match.group(1)
            current_meta['name'] = name
            current_meta['fields'] = []
            continue

        # End of CREATE TABLE block
        if stripped == ');':
            if 'name' in current_meta:
                layers.append(dict(current_meta))
            current_meta = {}
            continue

        # Field line inside CREATE TABLE
        if 'name' in current_meta and stripped and not stripped.startswith('--'):
            field_line = stripped.rstrip(',').strip()
            parts = field_line.split(None, 1)
            if len(parts) == 2:
                current_meta['fields'].append({
                    'name': parts[0],
                    'sql_type': parts[1],
                })

    return layers


# ---------------------------------------------------------------------------
# GeoPackage builder
# ---------------------------------------------------------------------------

def build_gpkg(schema_sql_path: str, output_path: str) -> None:
    """Create a GeoPackage at output_path from a schema.sql definition.

    Uses QgsVectorFileWriter so OGR handles all GeoPackage system tables,
    spatial indexes, and CRS registration automatically.
    """
    layers = parse_schema(schema_sql_path)
    if not layers:
        raise ValueError(f"No layers found in {schema_sql_path}")

    for i, layer_def in enumerate(layers):
        name = layer_def['name']
        geom_str = layer_def.get('geometry', 'POINT').upper()
        crs_str = layer_def.get('crs', 'EPSG:4326')
        geom_type = _GEOM_MAP.get(geom_str, QgsWkbTypes.Point)
        crs = QgsCoordinateReferenceSystem(crs_str)

        fields = QgsFields()
        for field_def in layer_def.get('fields', []):
            qtype, length = _sql_type_to_qvariant(field_def['sql_type'])
            f = QgsField(field_def['name'], qtype)
            if length:
                f.setLength(length)
            fields.append(f)

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = 'GPKG'
        options.layerName = name
        options.fileEncoding = 'UTF-8'
        if i == 0:
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        else:
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

        writer = QgsVectorFileWriter.create(
            output_path,
            fields,
            geom_type,
            crs,
            QgsCoordinateTransformContext(),
            options,
        )
        # writer being None or having an error means failure
        if writer is None:
            raise RuntimeError(f"Failed to create layer '{name}' in {output_path}")
        error = writer.hasError()
        del writer
        if error != QgsVectorFileWriter.NoError:
            raise RuntimeError(
                f"Error writing layer '{name}' to {output_path}: error code {error}"
            )


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def get_template_version(schema_sql_path: str) -> str | None:
    """Read the template_version from the schema.sql header comment.

    Returns the version string (e.g. '2026-05-02') or None if not present.
    """
    with open(schema_sql_path, encoding='utf-8') as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            m = re.match(r'^--\s+template_version:\s+(.+)$', stripped)
            if m:
                return m.group(1).strip()
            # Stop scanning once we hit a non-comment line
            if not stripped.startswith('--'):
                break
    return None


# ---------------------------------------------------------------------------
# Add a single layer to an existing GeoPackage
# ---------------------------------------------------------------------------

def add_layer_to_gpkg(layer_def: dict, gpkg_path: str) -> None:
    """Add a single layer defined by layer_def to an existing GeoPackage.

    layer_def has the same structure as returned by parse_schema().
    Uses CreateOrOverwriteLayer so the file itself is preserved.
    """
    name = layer_def['name']
    geom_str = layer_def.get('geometry', 'POINT').upper()
    crs_str = layer_def.get('crs', 'EPSG:4326')
    geom_type = _GEOM_MAP.get(geom_str, QgsWkbTypes.Point)
    crs = QgsCoordinateReferenceSystem(crs_str)

    fields = QgsFields()
    for field_def in layer_def.get('fields', []):
        qtype, length = _sql_type_to_qvariant(field_def['sql_type'])
        f = QgsField(field_def['name'], qtype)
        if length:
            f.setLength(length)
        fields.append(f)

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = 'GPKG'
    options.layerName = name
    options.fileEncoding = 'UTF-8'
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

    writer = QgsVectorFileWriter.create(
        gpkg_path,
        fields,
        geom_type,
        crs,
        QgsCoordinateTransformContext(),
        options,
    )
    if writer is None:
        raise RuntimeError(f"Failed to add layer '{name}' to {gpkg_path}")
    error = writer.hasError()
    del writer
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(
            f"Error adding layer '{name}' to {gpkg_path}: error code {error}"
        )
