"""Dialog di anteprima per le proposte dell'AI: Accetta / Rifiuta / Rigenera.

L'anteprima è il punto in cui l'autore mantiene il controllo: l'AI non
sovrascrive mai il testo senza una conferma esplicita, e la proposta è
modificabile prima di essere applicata.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
)


class AiPreviewDialog(QDialog):
    def __init__(self, parent, title: str, original: str, proposed: str,
                 allow_regenerate: bool = True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 560)
        self.action = "reject"            # reject | accept | regenerate
        self.result_text = proposed

        lay = QVBoxLayout(self)

        if original.strip():
            lbl_o = QLabel("Testo originale"); lbl_o.setObjectName("SectionLabel")
            lay.addWidget(lbl_o)
            self.orig = QPlainTextEdit(original); self.orig.setReadOnly(True)
            self.orig.setMaximumHeight(160)
            self.orig.setFont(QFont("monospace", 10))
            lay.addWidget(self.orig)

        lbl_p = QLabel("Proposta dell'AI (modificabile)"); lbl_p.setObjectName("SectionLabel")
        lay.addWidget(lbl_p)
        self.proposed = QPlainTextEdit(proposed)
        self.proposed.setFont(QFont("monospace", 11))
        lay.addWidget(self.proposed, 1)

        row = QHBoxLayout()
        if allow_regenerate:
            b_regen = QPushButton("🔄 Rigenera"); b_regen.clicked.connect(self._regen)
            row.addWidget(b_regen)
        row.addStretch(1)
        b_reject = QPushButton("Rifiuta"); b_reject.clicked.connect(self.reject)
        b_accept = QPushButton("Accetta"); b_accept.setObjectName("Primary")
        b_accept.clicked.connect(self._accept)
        row.addWidget(b_reject); row.addWidget(b_accept)
        lay.addLayout(row)

    def _accept(self):
        self.action = "accept"
        self.result_text = self.proposed.toPlainText()
        self.accept()

    def _regen(self):
        self.action = "regenerate"
        self.accept()
