"""Theme-aware icon loading for ArchaeoTrench Utilities.

Icons are Tabler Icons (https://tabler.io/icons, MIT license — see
icons/LICENSE), stored as stroke="currentColor" SVGs in icons/.

At load time currentColor is replaced with the text colour of the active
Qt palette, so the icons follow light and dark QGIS themes with a single
SVG per icon. Icons are built when the plugin's GUI is initialised; a
theme change is picked up on the next plugin reload / QGIS restart.
"""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QByteArray
from qgis.PyQt.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer

from .compat import COLOR_TRANSPARENT

_ICON_DIR = Path(__file__).parent / "icons"
_SIZES = (16, 24, 32, 48)


def themed_icon(name: str) -> QIcon:
    """Return the Tabler icon `name` recoloured to the current palette.

    Falls back to an empty QIcon (button stays usable, just blank) if the
    SVG is missing, so a packaging mistake never breaks the plugin.
    """
    path = _ICON_DIR / f"{name}.svg"
    try:
        svg = path.read_text(encoding="utf-8")
    except OSError:
        return QIcon()

    color = QGuiApplication.palette().windowText().color().name()
    renderer = QSvgRenderer(QByteArray(svg.replace("currentColor", color).encode()))
    if not renderer.isValid():
        return QIcon()

    icon = QIcon()
    for size in _SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(COLOR_TRANSPARENT)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
