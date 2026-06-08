"""Worker per l'autogenerazione (autopilota) di uno o più capitoli."""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from ..agents.engine import (autodraft_chapter, autodraft_book,
                             GenerationCancelled, friendly_engine_error)


class AutogenWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(int)     # numero di capitoli generati
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()          # autogenerazione interrotta dall'utente

    def __init__(self, engine, book, chapter=None, only_empty: bool = True):
        super().__init__()
        self.engine = engine
        self.book = book
        self.chapter = chapter        # se None → tutto il libro
        self.only_empty = only_empty

    def _progress(self, msg: str):
        # punto di interruzione cooperativa (vedi GenerateWorker._progress).
        if self.isInterruptionRequested():
            raise GenerationCancelled()
        self.progress.emit(msg)

    def run(self):
        try:
            if self.chapter is not None:
                autodraft_chapter(self.engine, self.book, self.chapter,
                                  progress=self._progress)
                self.finished_ok.emit(1)
            else:
                n = autodraft_book(self.engine, self.book, self.only_empty,
                                   progress=self._progress)
                self.finished_ok.emit(n)
        except GenerationCancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(friendly_engine_error(e))
