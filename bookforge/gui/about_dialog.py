"""Dialog «Info»: presentazione minimale dell'app con autore (FFA)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)

from .icons import app_icon

#: Versione mostrata nella schermata Info.
APP_VERSION = "1.0"


class AboutDialog(QDialog):
    """Piccola finestra «Informazioni su BookForge» — sviluppato da FFA."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Informazioni su BookForge")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(26, 26, 26, 26)

        # intestazione: logo + titolo
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(64, 64))
        head.addWidget(logo)
        titles = QVBoxLayout()
        name = QLabel("BookForge"); name.setObjectName("Title")
        ver = QLabel(f"Versione {APP_VERSION}"); ver.setObjectName("Subtitle")
        titles.addWidget(name); titles.addWidget(ver); titles.addStretch(1)
        head.addLayout(titles); head.addStretch(1)
        root.addLayout(head)

        desc = QLabel(
            "Scrittura e manutenzione di saggistica assistita da agenti AI: "
            "dai concetti grezzi alla prosa, al LaTeX, al PDF/EPUB/Word.")
        desc.setWordWrap(True); desc.setObjectName("Subtitle")
        root.addWidget(desc)

        author = QLabel("Sviluppato da <b>FFA</b>")
        author.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(author)

        # pulsante di chiusura
        row = QHBoxLayout(); row.addStretch(1)
        close = QPushButton("Chiudi"); close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        wrap = QWidget(); wrap.setLayout(row)
        root.addWidget(wrap)
