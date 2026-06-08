"""Versioning dell'opera: salva istantanee, confronta (diff) e ripristina."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTextBrowser, QInputDialog, QMessageBox,
)

from ..core import versioning
from .icons import icon, app_icon


class VersionsDialog(QDialog):
    def __init__(self, parent, project, on_restore=None):
        super().__init__(parent)
        self.project = project
        self.on_restore = on_restore
        self.versions: list = []

        self.setWindowTitle("Versioni dell'opera")
        self.setWindowIcon(app_icon())
        self.resize(760, 560)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Istantanee salvate (la più recente in alto):"))
        body = QHBoxLayout(); lay.addLayout(body, 1)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show_diff)
        left.addWidget(self.list)
        self.stats = QLabel(""); self.stats.setObjectName("Subtitle"); self.stats.setWordWrap(True)
        left.addWidget(self.stats)
        body.addLayout(left, 1)
        self.diff = QTextBrowser()
        body.addWidget(self.diff, 2)

        row = QHBoxLayout()
        save = QPushButton(icon("camera"), " Salva versione"); save.setObjectName("Primary")
        save.clicked.connect(self._save)
        restore = QPushButton(icon("undo"), " Ripristina selezionata")
        restore.clicked.connect(self._restore)
        close = QPushButton("Chiudi"); close.clicked.connect(self.accept)
        row.addWidget(save); row.addWidget(restore); row.addStretch(1); row.addWidget(close)
        lay.addLayout(row)

    def _refresh(self):
        self.versions = versioning.list_versions(self.project.folder)
        self.list.clear()
        for v in self.versions:
            self.list.addItem(QListWidgetItem(v.display()))
        if self.versions:
            self.list.setCurrentRow(0)
        else:
            self.diff.setPlainText("Nessuna versione salvata.")

    def _show_diff(self, row: int):
        if not (0 <= row < len(self.versions)):
            return
        try:
            old = versioning.load_version_book(self.versions[row].path)
        except Exception as e:  # noqa: BLE001
            self.diff.setHtml(f"<i>Impossibile leggere la versione: {e}</i>")
            self.stats.setText("")
            return
        self.diff.setHtml(versioning.diff_html(old, self.project.book))
        s = versioning.diff_stats(old, self.project.book)
        self.stats.setText(
            f"Confronto: questa versione → stato attuale\n"
            f"➕ {s['added']} righe · ➖ {s['removed']} righe · "
            f"{s['changed_blocks']} sezioni cambiate")

    def _save(self):
        label, ok = QInputDialog.getText(self, "Salva versione",
                                         "Etichetta (facoltativa):")
        if not ok:
            return
        versioning.save_version(self.project.folder, self.project.book, label.strip())
        self._refresh()

    def _restore(self):
        row = self.list.currentRow()
        if not (0 <= row < len(self.versions)):
            return
        if QMessageBox.question(
                self, "Ripristina",
                "Ripristinare questa versione? Lo stato attuale verrà prima "
                "salvato come nuova istantanea.") != QMessageBox.StandardButton.Yes:
            return
        # salva lo stato attuale prima di sovrascrivere (sicurezza)
        versioning.save_version(self.project.folder, self.project.book,
                                "auto-backup pre-ripristino")
        book = versioning.load_version_book(self.versions[row].path)
        if self.on_restore:
            self.on_restore(book)
        self._refresh()
        QMessageBox.information(self, "Ripristino", "Versione ripristinata.")
