"""Qt5/Qt6 compatibility constants for ArchaeoTrench Utilities.

QGIS 3.x ships PyQt5 (Qt5 unscoped enums).
QGIS 4.x ships PyQt6 (Qt6 fully-scoped enums).

Import all Qt enum constants from here so the rest of the plugin
doesn't need any version guards.
"""

from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QDialogButtonBox, QHeaderView,
)
from qgis.PyQt.QtCore import Qt

# ---------------------------------------------------------------------------
# Detect Qt version once
# ---------------------------------------------------------------------------
try:
    Qt.Orientation.Horizontal  # Only exists in PyQt6 scoped-enum style
    _QT6 = True
except AttributeError:
    _QT6 = False

# ---------------------------------------------------------------------------
# Qt.Orientation
# ---------------------------------------------------------------------------
if _QT6:
    HORIZONTAL = Qt.Orientation.Horizontal
    VERTICAL   = Qt.Orientation.Vertical
else:
    HORIZONTAL = Qt.Horizontal   # type: ignore[attr-defined]
    VERTICAL   = Qt.Vertical     # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# QDialogButtonBox.StandardButton
# ---------------------------------------------------------------------------
if _QT6:
    BTN_OK     = QDialogButtonBox.StandardButton.Ok
    BTN_CANCEL = QDialogButtonBox.StandardButton.Cancel
    BTN_YES    = QDialogButtonBox.StandardButton.Yes
    BTN_NO     = QDialogButtonBox.StandardButton.No
else:
    BTN_OK     = QDialogButtonBox.Ok      # type: ignore[attr-defined]
    BTN_CANCEL = QDialogButtonBox.Cancel  # type: ignore[attr-defined]
    BTN_YES    = QDialogButtonBox.Yes     # type: ignore[attr-defined]
    BTN_NO     = QDialogButtonBox.No      # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# QAbstractItemView
# ---------------------------------------------------------------------------
if _QT6:
    SELECTION_ROWS      = QAbstractItemView.SelectionBehavior.SelectRows
    NO_EDIT_TRIGGERS    = QAbstractItemView.EditTrigger.NoEditTriggers
    EXTENDED_SELECTION  = QAbstractItemView.SelectionMode.ExtendedSelection
else:
    SELECTION_ROWS      = QAbstractItemView.SelectRows           # type: ignore[attr-defined]
    NO_EDIT_TRIGGERS    = QAbstractItemView.NoEditTriggers       # type: ignore[attr-defined]
    EXTENDED_SELECTION  = QAbstractItemView.ExtendedSelection    # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# QHeaderView
# ---------------------------------------------------------------------------
if _QT6:
    HEADER_STRETCH = QHeaderView.ResizeMode.Stretch
else:
    HEADER_STRETCH = QHeaderView.Stretch  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# QDialog.exec — renamed from exec_() in PyQt6
# ---------------------------------------------------------------------------
def exec_dialog(dlg):
    """Call exec() or exec_() depending on the PyQt version."""
    if _QT6:
        return dlg.exec()
    return dlg.exec_()  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# QgsRaster identify format (moved to Qgis namespace in QGIS 4)
# ---------------------------------------------------------------------------
def raster_identify_format_value():
    """Return the correct identify-format constant for the running QGIS version."""
    try:
        from qgis.core import Qgis
        return Qgis.RasterIdentifyFormat.Value  # QGIS 4
    except AttributeError:
        from qgis.core import QgsRaster
        return QgsRaster.IdentifyFormatValue    # QGIS 3
