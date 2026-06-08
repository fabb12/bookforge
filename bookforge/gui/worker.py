"""Worker QThread per eseguire la pipeline degli agenti senza bloccare la GUI."""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from ..agents.engine import process_chapter, GenerationCancelled, friendly_engine_error
from ..core.model import Book, Chapter


class GenerateWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(object)   # Chapter aggiornato
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()           # generazione interrotta dall'utente

    def __init__(self, engine, book: Book, chapter: Chapter):
        super().__init__()
        self.engine = engine
        self.book = book
        self.chapter = chapter

    def _progress(self, msg: str):
        # punto di interruzione cooperativa: se l'utente ha premuto «Interrompi»
        # la pipeline si ferma qui, al confine del passo successivo.
        if self.isInterruptionRequested():
            raise GenerationCancelled()
        self.progress.emit(msg)

    def run(self):
        try:
            ch = process_chapter(self.engine, self.book, self.chapter,
                                 progress=self._progress)
            self.finished_ok.emit(ch)
        except GenerationCancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(friendly_engine_error(e))
