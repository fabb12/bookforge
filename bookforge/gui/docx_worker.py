"""Worker QThread per formattare un .docx senza bloccare la GUI."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.docx_formatter import DocxFormatRules, format_docx


class DocxFormatWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(object)   # FormatReport
    failed = pyqtSignal(str)

    def __init__(self, src_path: str, dst_path: str,
                 rules: DocxFormatRules,
                 text_corrector: Callable[[str], str] | None = None):
        super().__init__()
        self.src_path = src_path
        self.dst_path = dst_path
        self.rules = rules
        self.text_corrector = text_corrector

    def run(self):
        try:
            report = format_docx(
                self.src_path, self.dst_path, self.rules,
                text_corrector=self.text_corrector,
                progress=self.progress.emit,
            )
            self.finished_ok.emit(report)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
