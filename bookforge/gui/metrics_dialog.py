"""Dashboard di crescita: metriche di leggibilità per capitolo + andamento.

Mostra le metriche del libro capitolo per capitolo e permette di salvare
un'istantanea in progress.json, confrontando con la precedente (delta) per
rendere visibile il miglioramento nel tempo.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView,
)

from ..core import analysis, progress
from .icons import icon, app_icon


_COLS = [
    ("Capitolo", None),
    ("Parole", "words"),
    ("Frasi", "sentences"),
    ("Par./frase", "avg_sentence_len"),
    ("Gulpease", "gulpease"),
    ("Lessico", "lexical_diversity"),
    ("Passivo", "passive_ratio"),
    ("Frasi lunghe", "long_sentences"),
]


class MetricsDialog(QDialog):
    def __init__(self, parent, project):
        super().__init__(parent)
        self.project = project
        self.book = project.book
        self.setWindowTitle("Dashboard di crescita")
        self.setWindowIcon(app_icon())
        self.resize(760, 520)
        self._build_ui()
        self._populate()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        self.info = QLabel(""); self.info.setObjectName("Subtitle"); self.info.setWordWrap(True)
        lay.addWidget(self.info)

        self.table = QTableWidget()
        self.table.setColumnCount(len(_COLS))
        self.table.setHorizontalHeaderLabels([c[0] for c in _COLS])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 1)

        self.delta_lbl = QLabel(""); self.delta_lbl.setObjectName("Subtitle")
        self.delta_lbl.setWordWrap(True)
        lay.addWidget(self.delta_lbl)

        row = QHBoxLayout()
        save = QPushButton(icon("camera"), " Salva istantanea"); save.setObjectName("Primary")
        save.clicked.connect(self._save_snapshot)
        close = QPushButton("Chiudi"); close.clicked.connect(self.accept)
        row.addStretch(1); row.addWidget(close); row.addWidget(save)
        lay.addLayout(row)

    def _populate(self):
        rows = list(self.book.chapters)
        self.table.setRowCount(len(rows) + 1)
        for r, ch in enumerate(rows):
            txt = analysis.readable_text(ch.text, ch.latex)
            self._fill_row(r, ch.title, analysis.analyze(txt).to_dict())
        # riga totale (sul risultato finale di ogni capitolo)
        full = "\n\n".join(
            analysis.readable_text(c.text, c.latex) for c in self.book.chapters)
        self._fill_row(len(rows), "TUTTO IL LIBRO", analysis.analyze(full).to_dict(),
                       bold=True)
        self._show_delta()

    def _fill_row(self, r, title, metrics, bold=False):
        for c, (_, key) in enumerate(_COLS):
            if key is None:
                val = title
            else:
                v = metrics.get(key, 0)
                if key == "passive_ratio":
                    val = f"{int(v*100)}%"
                else:
                    val = str(v)
            item = QTableWidgetItem(val)
            if bold:
                f = item.font(); f.setBold(True); item.setFont(f)
            self.table.setItem(r, c, item)

    def _show_delta(self):
        history = progress.load_history(self.project.folder)
        if not history:
            self.delta_lbl.setText("Nessuna istantanea salvata: salvane una per "
                                   "iniziare a tracciare i progressi.")
            return
        last = history[-1]
        curr = progress.snapshot(self.book)
        bits = []
        for label, key in (("Parole", "words"), ("Gulpease", "gulpease"),
                           ("Passivo", "passive_ratio")):
            d = progress.delta(curr, last, key)
            if d is not None and d != 0:
                arrow = "▲" if d > 0 else "▼"
                bits.append(f"{label} {arrow}{abs(d)}")
        when = last.get("date", "")[:16].replace("T", " ")
        self.delta_lbl.setText(
            f"Rispetto all'ultima istantanea ({when}): " +
            (", ".join(bits) if bits else "nessuna variazione rilevante.") +
            f"   ·   istantanee totali: {len(history)}")

    def _save_snapshot(self):
        progress.save_snapshot(self.project.folder, self.book)
        self.info.setText("Istantanea salvata in progress.json.")
        self._show_delta()
