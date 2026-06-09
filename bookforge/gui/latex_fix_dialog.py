"""Anteprima di una correzione LaTeX proposta dall'AI.

A differenza dell'anteprima generica, qui l'obiettivo è far capire *cosa*
cambia: in cima il riepilogo delle modifiche dichiarate dal motore, poi un
**diff** colorato (righe rimosse in rosso, aggiunte in verde) così l'autore
vede esattamente l'intervento prima di accettarlo. Il sorgente completo resta
modificabile in fondo. Accetta / Rifiuta / Rigenera, come ogni proposta AI.
"""
from __future__ import annotations

import difflib

from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QSplitter,
)
from PyQt6.QtCore import Qt

from .icons import icon, app_icon


class _DiffHighlighter(QSyntaxHighlighter):
    """Colora le righe di un unified diff (+ aggiunte, - rimozioni, @@ contesto)."""

    def __init__(self, document):
        super().__init__(document)
        self._add = self._fmt("#9ece6a")
        self._del = self._fmt("#f7768e")
        self._hunk = self._fmt("#7aa2f7", bold=True)

    @staticmethod
    def _fmt(color: str, *, bold: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        return f

    def highlightBlock(self, text: str):
        if text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk)
        elif text.startswith("+") and not text.startswith("+++"):
            self.setFormat(0, len(text), self._add)
        elif text.startswith("-") and not text.startswith("---"):
            self.setFormat(0, len(text), self._del)


def _build_diff(original: str, proposed: str) -> str:
    """Unified diff compatto tra sorgente originale e proposta."""
    diff = difflib.unified_diff(
        original.splitlines(), proposed.splitlines(),
        fromfile="originale", tofile="corretto", lineterm="", n=2)
    text = "\n".join(diff)
    return text or "(nessuna differenza testuale rilevata)"


class LatexFixDialog(QDialog):
    """Mostra la correzione proposta (riepilogo + diff) e il sorgente modificabile."""

    def __init__(self, parent, original: str, proposed: str, summary: str,
                 attempt: int = 1, allow_regenerate: bool = True):
        super().__init__(parent)
        self.setWindowTitle(f"Correzione LaTeX — tentativo {attempt}")
        self.setWindowIcon(app_icon())
        self.resize(860, 640)
        self.action = "reject"            # reject | accept | regenerate
        self.result_text = proposed

        lay = QVBoxLayout(self)

        head = QLabel(f"Tentativo {attempt} — modifiche proposte dall'AI per "
                      "risolvere gli errori di compilazione:")
        head.setObjectName("SectionLabel")
        head.setWordWrap(True)
        lay.addWidget(head)

        self.summary = QPlainTextEdit(summary or "(il motore non ha descritto le modifiche)")
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(120)
        lay.addWidget(self.summary)

        splitter = QSplitter(Qt.Orientation.Vertical)

        diff_box = QPlainTextEdit(_build_diff(original, proposed))
        diff_box.setReadOnly(True)
        diff_box.setFont(QFont("monospace", 10))
        diff_box.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._diff_hl = _DiffHighlighter(diff_box.document())
        splitter.addWidget(self._labeled("Differenze (rosso = tolto, verde = aggiunto)", diff_box))

        self.proposed = QPlainTextEdit(proposed)
        self.proposed.setFont(QFont("monospace", 10))
        self.proposed.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        splitter.addWidget(self._labeled("Sorgente .tex corretto (modificabile)", self.proposed))
        splitter.setSizes([260, 320])
        lay.addWidget(splitter, 1)

        row = QHBoxLayout()
        if allow_regenerate:
            b_regen = QPushButton(icon("refresh"), " Riprova")
            b_regen.setToolTip("Chiedi all'AI un'altra proposta")
            b_regen.clicked.connect(self._regen)
            row.addWidget(b_regen)
        row.addStretch(1)
        b_reject = QPushButton(icon("x"), " Rifiuta"); b_reject.clicked.connect(self.reject)
        b_accept = QPushButton(icon("check"), " Accetta e ricompila")
        b_accept.setObjectName("Primary"); b_accept.clicked.connect(self._accept)
        row.addWidget(b_reject); row.addWidget(b_accept)
        lay.addLayout(row)

    @staticmethod
    def _labeled(text: str, widget) -> "QWidget":
        from PyQt6.QtWidgets import QWidget
        w = QWidget()
        v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(text); lbl.setObjectName("SectionLabel")
        v.addWidget(lbl); v.addWidget(widget, 1)
        return w

    def _accept(self):
        self.action = "accept"
        self.result_text = self.proposed.toPlainText()
        self.accept()

    def _regen(self):
        self.action = "regenerate"
        self.accept()
