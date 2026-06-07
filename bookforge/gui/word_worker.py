"""Worker QThread per la pipeline «Word → LaTeX → PDF» (non blocca la GUI)."""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.word_to_latex import WordFixOptions


class WordToPdfWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(object)   # dict: result, pdf_ok, pdf_log
    failed = pyqtSignal(str)

    def __init__(self, docx_path: str, out_dir: str, options: WordFixOptions,
                 corrector: Callable[[str], str] | None = None,
                 compile_pdf: bool = True):
        super().__init__()
        self.docx_path = docx_path
        self.out_dir = out_dir
        self.options = options
        self.corrector = corrector
        self.compile_pdf = compile_pdf

    def run(self):
        try:
            from ..core import word_to_latex, compiler
            res = word_to_latex.convert_word(
                self.docx_path, self.out_dir, self.options,
                corrector=self.corrector, progress=self.progress.emit)
            pdf_ok, pdf_log = False, ""
            if self.compile_pdf:
                self.progress.emit("Compilazione del PDF…")
                pdf_ok, pdf_log = compiler.compile_tex(res.tex_path)
            self.finished_ok.emit({"result": res, "pdf_ok": pdf_ok, "pdf_log": pdf_log})
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
