"""Bibliografia: gestione di references.bib del progetto e inserimento \\cite.

Rigore per la saggistica: raccogli le fonti, salvale in BibTeX e cita nel testo.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QListWidget,
    QListWidgetItem, QLineEdit, QComboBox, QPushButton, QMessageBox, QGroupBox,
)

from ..core import biblio
from .icons import icon, app_icon


_TYPES = ["article", "book", "inproceedings", "incollection", "misc", "online"]
_FIELDS = ["author", "title", "year", "journal", "booktitle", "publisher",
           "volume", "number", "pages", "doi", "url"]


class BiblioDialog(QDialog):
    def __init__(self, parent, folder, on_insert_cite=None):
        super().__init__(parent)
        self.folder = Path(folder)
        self.bib_path = self.folder / "references.bib"
        self.on_insert_cite = on_insert_cite
        self.entries = biblio.load_bib(self.bib_path)

        self.setWindowTitle("Bibliografia")
        self.setWindowIcon(app_icon())
        self.resize(720, 560)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"File: {self.bib_path}"))

        body = QHBoxLayout(); lay.addLayout(body, 1)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_select)
        body.addWidget(self.list, 1)

        form_box = QGroupBox("Voce")
        form = QFormLayout(form_box)
        self.f_type = QComboBox(); self.f_type.addItems(_TYPES)
        self.f_key = QLineEdit()
        form.addRow("Tipo", self.f_type)
        form.addRow("Chiave", self.f_key)
        self.f_fields: dict[str, QLineEdit] = {}
        for name in _FIELDS:
            le = QLineEdit(); self.f_fields[name] = le
            form.addRow(name.capitalize(), le)
        body.addWidget(form_box, 1)

        row = QHBoxLayout()
        new = QPushButton(icon("plus"), " Nuova"); new.clicked.connect(self._new)
        save = QPushButton(icon("save"), " Salva voce"); save.clicked.connect(self._save_entry)
        dele = QPushButton(icon("trash"), " Elimina"); dele.setObjectName("Danger")
        dele.clicked.connect(self._delete)
        row.addWidget(new); row.addWidget(save); row.addWidget(dele); row.addStretch(1)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        cite = QPushButton(icon("paperclip"), " Inserisci \\cite"); cite.setObjectName("Primary")
        cite.clicked.connect(self._insert_cite)
        close = QPushButton("Chiudi"); close.clicked.connect(self.accept)
        row2.addStretch(1); row2.addWidget(close); row2.addWidget(cite)
        lay.addLayout(row2)

    # ---------------------------------------------------------- list
    def _refresh_list(self):
        self.list.clear()
        for e in self.entries:
            self.list.addItem(QListWidgetItem(e.label()))

    def _on_select(self, row: int):
        if not (0 <= row < len(self.entries)):
            return
        e = self.entries[row]
        self.f_type.setCurrentText(e.entry_type)
        self.f_key.setText(e.key)
        for name, le in self.f_fields.items():
            le.setText(e.get(name))

    # ---------------------------------------------------------- CRUD
    def _new(self):
        self.list.setCurrentRow(-1)
        self.f_type.setCurrentText("article")
        self.f_key.clear()
        for le in self.f_fields.values():
            le.clear()

    def _save_entry(self):
        fields = {n: le.text().strip() for n, le in self.f_fields.items() if le.text().strip()}
        key = self.f_key.text().strip()
        if not key:
            key = biblio.suggest_key(fields.get("author", ""), fields.get("year", ""),
                                     {e.key for e in self.entries})
            self.f_key.setText(key)
        entry = biblio.BibEntry(key=key, entry_type=self.f_type.currentText(), fields=fields)
        # sostituisci se la chiave esiste, altrimenti aggiungi
        for i, e in enumerate(self.entries):
            if e.key == key:
                self.entries[i] = entry
                break
        else:
            self.entries.append(entry)
        biblio.save_bib(self.bib_path, self.entries)
        self._refresh_list()
        QMessageBox.information(self, "Bibliografia", f"Voce «{key}» salvata.")

    def _delete(self):
        row = self.list.currentRow()
        if not (0 <= row < len(self.entries)):
            return
        key = self.entries[row].key
        del self.entries[row]
        biblio.save_bib(self.bib_path, self.entries)
        self._refresh_list()
        QMessageBox.information(self, "Bibliografia", f"Voce «{key}» eliminata.")

    def _insert_cite(self):
        row = self.list.currentRow()
        if not (0 <= row < len(self.entries)):
            QMessageBox.information(self, "Cita", "Seleziona una voce.")
            return
        cmd = biblio.cite_command(self.entries[row].key)
        if self.on_insert_cite:
            self.on_insert_cite(cmd)
            self.accept()
        else:
            QMessageBox.information(self, "Cita", f"Comando: {cmd}")
