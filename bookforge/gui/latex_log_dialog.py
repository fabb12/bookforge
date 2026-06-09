"""Finestra dedicata al log di compilazione LaTeX.

Si apre dopo ogni compilazione e resta riapribile su richiesta dalla toolbar
(«Log LaTeX»). È **non modale**: l'autore può tenerla aperta accanto all'editor
mentre lavora. In caso di errore mette in evidenza i blocchi `!` del log e offre
il pulsante «Correggi con AI», che inoltra il problema al motore per un tentativo
di riparazione (con anteprima Accetta/Rifiuta, come ogni altra proposta AI).
"""
from __future__ import annotations

import re
from typing import Callable

from PyQt6.QtGui import (
    QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QTextCursor,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
)

from .icons import icon, app_icon


class _LogHighlighter(QSyntaxHighlighter):
    """Colora gli errori (`!`, `l.NN`) e gli avvisi nel log di compilazione."""

    def __init__(self, document):
        super().__init__(document)
        self._error = self._fmt("#f7768e", bold=True)     # righe di errore `!`
        self._line = self._fmt("#e0af68", bold=True)      # marcatori `l.NN`
        self._warn = self._fmt("#e0af68")                 # avvisi
        self._ok = self._fmt("#9ece6a", bold=True)        # esito positivo

    @staticmethod
    def _fmt(color: str, *, bold: bool = False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Weight.Bold)
        return f

    def highlightBlock(self, text: str):
        n = len(text)
        if text.startswith("!"):
            self.setFormat(0, n, self._error)
        elif re.match(r"^l\.\d+", text):
            self.setFormat(0, n, self._line)
        elif text.startswith("PDF generato"):
            self.setFormat(0, n, self._ok)
        elif re.search(r"Warning|Undefined|Missing|Runaway|non trovato", text):
            self.setFormat(0, n, self._warn)


class LatexLogDialog(QDialog):
    """Finestra riutilizzabile per mostrare l'esito di una compilazione.

    Istanziata una sola volta e riusata: `set_log()` ne aggiorna il contenuto,
    `show_log()` la porta in primo piano. Il callback `on_fix` (se fornito) viene
    invocato quando l'utente preme «Correggi con AI».
    """

    def __init__(self, parent, on_fix: Callable[[], None] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Log compilazione LaTeX")
        self.setWindowIcon(app_icon())
        self.resize(820, 560)
        # Non modale: resta consultabile mentre si lavora nell'editor.
        self.setModal(False)
        self._on_fix = on_fix

        lay = QVBoxLayout(self)

        self.status = QLabel("Nessuna compilazione eseguita.")
        self.status.setObjectName("SectionLabel")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont("monospace", 10))
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._highlighter = _LogHighlighter(self.view.document())
        lay.addWidget(self.view, 1)

        row = QHBoxLayout()
        self.fix_btn = QPushButton(icon("wand"), " Correggi con AI")
        self.fix_btn.setObjectName("Primary")
        self.fix_btn.clicked.connect(self._fix_clicked)
        self.fix_btn.setVisible(False)
        row.addWidget(self.fix_btn)
        row.addStretch(1)
        b_close = QPushButton(icon("x"), " Chiudi")
        b_close.clicked.connect(self.hide)
        row.addWidget(b_close)
        lay.addLayout(row)

    # -- API usata dalla finestra principale ------------------------------
    def set_log(self, ok: bool, log: str, can_fix: bool = False):
        """Aggiorna l'esito e il testo del log. `can_fix` mostra il pulsante AI."""
        if ok:
            self.status.setText("✓ Compilazione riuscita — PDF generato.")
        else:
            self.status.setText("✗ Compilazione fallita — controlla gli errori "
                                "evidenziati qui sotto.")
        self.view.setPlainText(log or "(log vuoto)")
        # porta la vista all'inizio (gli errori principali sono in cima al riassunto)
        self.view.moveCursor(QTextCursor.MoveOperation.Start)
        self.fix_btn.setVisible(bool(can_fix) and not ok)

    def show_log(self):
        """Mostra la finestra portandola in primo piano (senza rubare il focus a forza)."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _fix_clicked(self):
        if self._on_fix is not None:
            self._on_fix()
