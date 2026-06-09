"""Dialog per la generazione di immagini con controllo da parte dell'autore.

Due passaggi, entrambi sotto controllo dell'utente:
  • `ImageOptionsDialog` — prima di generare: descrizione (precompilata con la
    selezione), stile del disegno (infografica, disegno di un bambino, …),
    proporzioni e numero di varianti da produrre.
  • `ImagePreviewDialog` — dopo aver generato: mostra le immagini reali come
    miniature, l'autore ne seleziona una e ne modifica la didascalia prima di
    inserirla. L'AI non inserisce mai nulla senza questa conferma.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QPlainTextEdit, QLineEdit, QComboBox, QSpinBox, QListWidget, QListWidgetItem,
    QScrollArea,
)

from ..core.image_gen import IMAGE_STYLES
from .icons import icon, app_icon

# proporzioni offerte (chiavi accettate da ImageGenConfig.aspect_ratio)
_ASPECTS = ["1:1", "3:4", "4:3", "16:9", "9:16"]


class ImageZoomDialog(QDialog):
    """Mostra una singola immagine a grandezza piena, in una vista scorribile.

    Aperta dal doppio click su una miniatura dell'anteprima: serve per ispezionare
    il dettaglio prima di scegliere quale variante inserire.
    """

    def __init__(self, parent, path: Path):
        super().__init__(parent)
        self.setWindowTitle(path.name)
        self.setWindowIcon(app_icon())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        pix = QPixmap(str(path))
        # non superare lo spazio disponibile sullo schermo: se l'immagine è
        # enorme la rimpiccioliamo mantenendo le proporzioni.
        screen = QGuiApplication.primaryScreen()
        if screen is not None and not pix.isNull():
            avail = screen.availableGeometry()
            max_w, max_h = int(avail.width() * 0.9), int(avail.height() * 0.9)
            if pix.width() > max_w or pix.height() > max_h:
                pix = pix.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)

        label = QLabel()
        label.setPixmap(pix)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(scroll)

        self.resize(min(pix.width() + 40, 1200) if not pix.isNull() else 800,
                    min(pix.height() + 40, 900) if not pix.isNull() else 600)


class ImageOptionsDialog(QDialog):
    """Raccoglie le opzioni di generazione prima di chiamare il modello."""

    def __init__(self, parent, description: str, default_aspect: str = "4:3"):
        super().__init__(parent)
        self.setWindowTitle("Genera immagine")
        self.setWindowIcon(app_icon())
        self.resize(560, 460)

        lay = QVBoxLayout(self)

        lbl = QLabel("Descrizione (dal testo selezionato, modificabile)")
        lbl.setObjectName("SectionLabel")
        lay.addWidget(lbl)
        self.desc = QPlainTextEdit(description.strip())
        self.desc.setMinimumHeight(120)
        lay.addWidget(self.desc, 1)

        form = QFormLayout()
        self.style = QComboBox()
        self.style.addItems(list(IMAGE_STYLES.keys()))
        form.addRow("Stile del disegno", self.style)

        self.aspect = QComboBox()
        self.aspect.addItems(_ASPECTS)
        if default_aspect in _ASPECTS:
            self.aspect.setCurrentText(default_aspect)
        form.addRow("Proporzioni", self.aspect)

        self.count = QSpinBox()
        self.count.setRange(1, 4)
        self.count.setValue(1)
        self.count.setToolTip("Quante varianti generare: poi ne sceglierai una.")
        form.addRow("Varianti da generare", self.count)
        lay.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        b_cancel = QPushButton(icon("x"), " Annulla")
        b_cancel.clicked.connect(self.reject)
        b_ok = QPushButton(icon("image"), " Genera")
        b_ok.setObjectName("Primary")
        b_ok.clicked.connect(self.accept)
        row.addWidget(b_cancel)
        row.addWidget(b_ok)
        lay.addLayout(row)

    # -- accesso comodo ai valori scelti --
    @property
    def description(self) -> str:
        return self.desc.toPlainText().strip()

    @property
    def style_label(self) -> str:
        return self.style.currentText()

    @property
    def aspect_ratio(self) -> str:
        return self.aspect.currentText()

    @property
    def variants(self) -> int:
        return self.count.value()


class ImagePreviewDialog(QDialog):
    """Mostra le immagini generate; l'autore ne sceglie una e conferma."""

    def __init__(self, parent, paths: list[Path], caption: str,
                 allow_regenerate: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Anteprima immagine")
        self.setWindowIcon(app_icon())
        self.resize(720, 620)
        self.action = "reject"                       # reject | accept | regenerate
        self.selected_path: Path | None = paths[0] if paths else None
        self.caption_text = caption

        lay = QVBoxLayout(self)
        hint = ("Seleziona l'immagine da inserire (doppio click per ingrandirla)."
                if len(paths) > 1 else "Immagine generata (doppio click per ingrandirla).")
        lbl = QLabel(hint)
        lbl.setObjectName("SectionLabel")
        lay.addWidget(lbl)

        # griglia di miniature: la selezione è il modo per «scegliere» l'immagine
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(QSize(320, 320))
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setSpacing(8)
        self.gallery.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for p in paths:
            item = QListWidgetItem(QIcon(QPixmap(str(p))), p.name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.gallery.addItem(item)
        if paths:
            self.gallery.setCurrentRow(0)
        self.gallery.currentItemChanged.connect(self._on_select)
        self.gallery.itemDoubleClicked.connect(self._open_large)
        lay.addWidget(self.gallery, 1)

        lay.addWidget(QLabel("Didascalia (modificabile)"))
        self.caption_edit = QLineEdit(caption)
        lay.addWidget(self.caption_edit)

        row = QHBoxLayout()
        if allow_regenerate:
            b_regen = QPushButton(icon("refresh"), " Rigenera")
            b_regen.clicked.connect(self._regen)
            row.addWidget(b_regen)
        row.addStretch(1)
        b_reject = QPushButton(icon("x"), " Rifiuta")
        b_reject.clicked.connect(self.reject)
        b_accept = QPushButton(icon("check"), " Inserisci")
        b_accept.setObjectName("Primary")
        b_accept.clicked.connect(self._accept)
        row.addWidget(b_reject)
        row.addWidget(b_accept)
        lay.addLayout(row)

    def _on_select(self, current, _previous=None):
        if current is not None:
            self.selected_path = current.data(Qt.ItemDataRole.UserRole)

    def _open_large(self, item):
        """Doppio click su una miniatura: apre l'immagine a grandezza piena."""
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path is not None:
            ImageZoomDialog(self, path).exec()

    def _accept(self):
        self.action = "accept"
        self.caption_text = self.caption_edit.text().strip()
        item = self.gallery.currentItem()
        if item is not None:
            self.selected_path = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _regen(self):
        self.action = "regenerate"
        self.accept()
