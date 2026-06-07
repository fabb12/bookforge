"""Anteprima PDF integrata (QtPdf), con fallback all'apertura esterna.

QtPdf può non essere presente in tutte le installazioni di PyQt6: `pdf_view_available`
permette al chiamante di ripiegare sull'apertura con l'app di sistema.
"""
from __future__ import annotations

from pathlib import Path


def pdf_view_available() -> bool:
    try:
        from PyQt6 import QtPdf, QtPdfWidgets  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def show_pdf(parent, pdf_path) -> bool:
    """Apre l'anteprima integrata se possibile. Ritorna False se non disponibile."""
    if not pdf_view_available():
        return False
    try:
        PdfPreviewDialog(parent, pdf_path).exec()
        return True
    except Exception:  # noqa: BLE001 - qualsiasi problema → fallback esterno
        return False


def _build_dialog():
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    )
    from PyQt6.QtPdf import QPdfDocument
    from PyQt6.QtPdfWidgets import QPdfView

    class _PdfPreviewDialog(QDialog):
        def __init__(self, parent, pdf_path):
            super().__init__(parent)
            self.setWindowTitle(f"👁 Anteprima PDF — {Path(pdf_path).name}")
            self.resize(820, 940)
            lay = QVBoxLayout(self)

            self.doc = QPdfDocument(self)
            self.doc.load(str(pdf_path))
            self.view = QPdfView(self)
            self.view.setDocument(self.doc)
            self.view.setPageMode(QPdfView.PageMode.MultiPage)
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            lay.addWidget(self.view, 1)

            row = QHBoxLayout()
            self.page_lbl = QLabel("")
            zoom_out = QPushButton("➖"); zoom_out.clicked.connect(lambda: self._zoom(0.8))
            zoom_in = QPushButton("➕"); zoom_in.clicked.connect(lambda: self._zoom(1.25))
            fit = QPushButton("Adatta larghezza"); fit.clicked.connect(self._fit)
            close = QPushButton("Chiudi"); close.clicked.connect(self.accept)
            row.addWidget(self.page_lbl); row.addStretch(1)
            row.addWidget(zoom_out); row.addWidget(zoom_in); row.addWidget(fit)
            row.addWidget(close)
            lay.addLayout(row)
            self._update_pages()

        def _zoom(self, factor):
            from PyQt6.QtPdfWidgets import QPdfView
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.view.setZoomFactor(self.view.zoomFactor() * factor)

        def _fit(self):
            from PyQt6.QtPdfWidgets import QPdfView
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        def _update_pages(self):
            n = self.doc.pageCount()
            self.page_lbl.setText(f"{n} pagine" if n > 0 else "")

    return _PdfPreviewDialog


# Esposto come nome di classe per comodità del chiamante.
def PdfPreviewDialog(parent, pdf_path):  # noqa: N802 - factory che agisce da classe
    return _build_dialog()(parent, pdf_path)
