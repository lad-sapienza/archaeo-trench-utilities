"""SectionBuilder — Generate section dialog for ArchaeoTrench Utilities."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
    QMessageBox, QVBoxLayout,
)

from .compat import BTN_OK, BTN_CANCEL, MSGBOX_YES, MSGBOX_NO, HORIZONTAL
from .sb_project import PROJECT_VAR_SECTION_NAME

PROJECT_VAR_INTERVAL = "sb_sample_interval"


class SbGenerateDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self._iface = iface
        self.setWindowTitle("Section Builder — Generate section")
        self.setMinimumWidth(420)
        self._section_name: str | None = None
        self._build_ui()

    def _build_ui(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils

        layout = QVBoxLayout(self)
        scope = QgsExpressionContextUtils.projectScope(QgsProject.instance())
        self._section_name = scope.variable(PROJECT_VAR_SECTION_NAME)

        form = QFormLayout()
        form.addRow("Section:", QLabel(self._section_name or "— not initialised —"))

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setDecimals(3)
        self._interval_spin.setRange(0.001, 100.0)
        self._interval_spin.setSingleStep(0.01)
        self._interval_spin.setSuffix(" m")
        self._interval_spin.setValue(0.05)
        saved = scope.variable(PROJECT_VAR_INTERVAL)
        if saved:
            try:
                self._interval_spin.setValue(float(saved))
            except (ValueError, TypeError):
                pass
        form.addRow("Sampling interval:", self._interval_spin)
        layout.addLayout(form)

        info = QLabel(
            "Samples all registered DEMs along the entire profile line and "
            "writes the resulting linestrings to sb_section_ln.\n\n"
            "• Annotations with exclude = 1 are jog segments: skipped entirely, "
            "they do not advance the section X axis.\n"
            "• All other stretches are sampled with every registered DEM. "
            "Annotations with a part label tag the output; unlabeled stretches "
            "produce segments with part = NULL.\n\n"
            "sb_section_ln is fully regenerated on every run."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(BTN_OK | BTN_CANCEL, HORIZONTAL, self)
        buttons.button(BTN_OK).setText("Generate")
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_ok(self):
        from qgis.core import QgsProject, QgsExpressionContextUtils
        from . import sb_project, sb_generate

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
            has_existing = sb_generate.has_existing_sections(gpkg_path)
        except RuntimeError as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return

        if has_existing:
            answer = QMessageBox.question(
                self, "Replace existing section?",
                "sb_section_ln already contains features.\n\n"
                "They will be replaced entirely. Continue?",
                MSGBOX_YES | MSGBOX_NO, MSGBOX_NO,
            )
            if answer != MSGBOX_YES:
                return

        try:
            stats = sb_generate.generate_section(
                gpkg_path, self._interval_spin.value()
            )
        except RuntimeError as exc:
            QMessageBox.critical(self, "Generation failed", str(exc))
            return

        QgsExpressionContextUtils.setProjectVariable(
            QgsProject.instance(), PROJECT_VAR_INTERVAL,
            str(self._interval_spin.value()))

        lines = [
            f"  • {part or '(unclassified)'}"
            + (f"  [{dem}]" if dem else "")
            + f": {n} points"
            for dem, part, n in stats["segments"]
        ]

        notes = []
        if stats["skipped"]:
            notes.append(
                f"{stats['skipped']} annotation(s) skipped "
                "(excluded, unclassified, or missing DEM)."
            )
        if stats["errors"]:
            notes.append("Warnings:")
            notes.extend(f"  ⚠ {e}" for e in stats["errors"])

        QMessageBox.information(
            self, "Section generated",
            f"{len(stats['segments'])} segment(s) written to sb_section_ln"
            + (f" from {stats['total_annotations']} annotation(s):\n\n"
               + "\n".join(lines)
               if lines else ".")
            + ("\n\n" + "\n".join(notes) if notes else "")
        )
        self.accept()
