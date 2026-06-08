"""Worker generico per eseguire una funzione dell'AI fuori dal thread della GUI."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from ..agents.engine import friendly_engine_error


class AiWorker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(friendly_engine_error(e))
