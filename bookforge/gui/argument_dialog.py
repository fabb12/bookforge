"""Mappa dell'argomentazione: struttura il ragionamento prima della prosa.

Editor a righe TESI / ARGOMENTO / PROVA / OBIEZIONE / REPLICA, generabile con l'AI
ed esportabile come concetti per il Writer. Aiuta a *ragionare*, non a scrivere.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QProgressDialog, QMessageBox,
)

from ..core import structure
from .ai_worker import AiWorker


_HELP = ("Una voce per riga. Etichette riconosciute:  TESI:  ARGOMENTO:  PROVA:  "
         "OBIEZIONE:  REPLICA:\nRipeti ARGOMENTO/PROVA/OBIEZIONE/REPLICA per ogni "
         "argomento. «Genera con AI» propone una bozza da rifinire.")


class ArgumentMapDialog(QDialog):
    def __init__(self, parent, engine, book, chapter, on_export_concepts=None):
        super().__init__(parent)
        self.engine = engine
        self.book = book
        self.chapter = chapter
        self.on_export_concepts = on_export_concepts
        self._worker: AiWorker | None = None

        self.setWindowTitle(f"🧭 Mappa argomentazione — {chapter.title}")
        self.resize(680, 600)
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        help_lbl = QLabel(_HELP); help_lbl.setObjectName("Subtitle"); help_lbl.setWordWrap(True)
        lay.addWidget(help_lbl)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("monospace", 11))
        lay.addWidget(self.editor, 1)

        row = QHBoxLayout()
        gen = QPushButton("🤖 Genera con AI"); gen.clicked.connect(self._generate)
        exp = QPushButton("➡ Esporta in Concetti"); exp.clicked.connect(self._export)
        row.addWidget(gen); row.addWidget(exp); row.addStretch(1)
        save = QPushButton("💾 Salva"); save.setObjectName("Primary"); save.clicked.connect(self._save)
        close = QPushButton("Chiudi"); close.clicked.connect(self.reject)
        row.addWidget(close); row.addWidget(save)
        lay.addLayout(row)

    def _load(self):
        amap = structure.ArgumentMap.from_dict(self.chapter.argument)
        if amap.is_empty():
            self.editor.setPlainText("TESI: \nARGOMENTO: \nPROVA: \nOBIEZIONE: \nREPLICA: ")
        else:
            self.editor.setPlainText(amap.to_ai_format())

    def _current_map(self) -> structure.ArgumentMap:
        return structure.parse_ai_map(self.editor.toPlainText())

    def _generate(self):
        if self._worker and self._worker.isRunning():
            return
        busy = QProgressDialog("Genero la mappa…", None, 0, 0, self)
        busy.setWindowTitle("AI"); busy.setCancelButton(None); busy.show()
        eng, book, ch = self.engine, self.book, self.chapter

        def fn():
            return eng.argument_map(book, ch)

        def done(res):
            busy.close()
            amap = structure.parse_ai_map(str(res))
            self.editor.setPlainText(amap.to_ai_format())

        def fail(err):
            busy.close(); QMessageBox.critical(self, "Errore AI", err)

        self._worker = AiWorker(fn)
        self._worker.done.connect(done)
        self._worker.failed.connect(fail)
        self._worker.start()

    def _save(self):
        self.chapter.argument = self._current_map().to_dict()
        QMessageBox.information(self, "Mappa", "Mappa salvata nel capitolo.")
        self.accept()

    def _export(self):
        concepts = self._current_map().to_concepts()
        if not concepts.strip():
            QMessageBox.information(self, "Concetti", "La mappa è vuota.")
            return
        self.chapter.argument = self._current_map().to_dict()
        if self.on_export_concepts:
            self.on_export_concepts(concepts)
        QMessageBox.information(self, "Concetti",
                               "Mappa esportata nella scheda «Concetti».")
        self.accept()
