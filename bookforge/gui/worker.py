"""Worker QThread per eseguire la pipeline degli agenti senza bloccare la GUI."""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from ..agents.engine import process_chapter
from ..core.model import Book, Chapter


class GenerateWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(object)   # Chapter aggiornato
    failed = pyqtSignal(str)

    def __init__(self, engine, book: Book, chapter: Chapter):
        super().__init__()
        self.engine = engine
        self.book = book
        self.chapter = chapter

    def run(self):
        try:
            ch = process_chapter(self.engine, self.book, self.chapter,
                                 progress=self.progress.emit)
            self.finished_ok.emit(ch)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
