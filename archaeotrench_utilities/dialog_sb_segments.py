"""SectionBuilder — Generate segments dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, HORIZONTAL
from .sb_project import PROJECT_VAR_SECTION_NAME


class SbSegmentsDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("Section Builder — Generate segments")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils

        layout = QVBoxLayout(self)
        self._section_name = QgsExpressionContextUtils.projectScope(
            QgsProject.instance()
        ).variable(PROJECT_VAR_SECTION_NAME)

        layout.addWidget(QLabel(
            f"Section: {self._section_name or '— not initialised —'}"
        ))

        info = QLabel(
            "Rebuilds sb_section_ln from the points of sb_profile_pts: "
            "consecutive points sharing the same 'part' value become one "
            "linestring (grouped per DEM, ordered by distance). Unclassified "
            "stretches are drawn too, with an empty 'part'.\n\n"
            "Lines connect at classification boundaries and break at real "
            "gaps in the profile. Existing content of sb_section_ln is replaced."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Generate")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self):
        from . import sb_project, sb_segments

        if not self._section_name:
            QMessageBox.warning(
                self, "No section",
                "No section is initialised in this project.\n"
                "Run 'Section Builder → New section…' first."
            )
            return

        gpkg_path = sb_project.get_section_gpkg(self._section_name)
        if gpkg_path is None:
            QMessageBox.critical(
                self, "GeoPackage not found",
                "Could not locate the section GeoPackage.\n"
                "Run 'Section Builder → New section…' first."
            )
            return

        try:
            stats = sb_segments.generate_segments(gpkg_path)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Generation failed", str(exc))
            return

        lines = [
            f"  • {part or '(unclassified)'}"
            + (f"  [{dem}]" if dem else "") + f": {n} points"
            for dem, part, n in stats["segments"]
        ]
        notes = []
        if stats["skipped_single"]:
            notes.append(
                f"{stats['skipped_single']} single-point run(s) skipped "
                "(a line needs at least 2 points)."
            )
        if stats["unclassified"]:
            notes.append(
                f"{stats['unclassified']} of {stats['total_points']} points "
                "are unclassified (drawn with empty 'part')."
            )

        QMessageBox.information(
            self, "Segments generated",
            f"{len(stats['segments'])} segment(s) written to sb_section_ln:\n\n"
            + "\n".join(lines)
            + ("\n\n" + "\n".join(notes) if notes else "")
        )
        self.accept()
