"""Versioning dell'opera: salva istantanee, confronta (diff) e ripristina."""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QPlainTextEdit, QInputDialog, QMessageBox,
)

from ..core import versioning


class VersionsDialog(QDialog):
    def __init__(self, parent, project, on_restore=None):
        super().__init__(parent)
        self.project = project
        self.on_restore = on_restore
        self.versions: list = []

        self.setWindowTitle("🕓 Versioni dell'opera")
        self.resize(760, 560)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Istantanee salvate (la più recente in alto):"))
        body = QHBoxLayout(); lay.addLayout(body, 1)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show_diff)
        body.addWidget(self.list, 1)
        self.diff = QPlainTextEdit(); self.diff.setReadOnly(True)
        self.diff.setFont(QFont("monospace", 10))
        body.addWidget(self.diff, 2)

        row = QHBoxLayout()
        save = QPushButton("📸 Salva versione"); save.setObjectName("Primary")
        save.clicked.connect(self._save)
        restore = QPushButton("↩ Ripristina selezionata"); restore.clicked.connect(self._restore)
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
            self.diff.setPlainText(f"Impossibile leggere la versione: {e}")
            return
        self.diff.setPlainText(versioning.diff_books(old, self.project.book))

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
