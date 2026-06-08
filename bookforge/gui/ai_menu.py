"""Controller per la scrittura assistita dall'AI dentro un editor di testo.

`AiEditingController` aggancia un menu contestuale «🤖 AI» a un QPlainTextEdit /
QTextEdit e gestisce:
  • comandi sulla selezione (riscrivi, espandi, accorcia, continua, …);
  • generazione di diagrammi come codice (TikZ) o immagine (Mermaid renderizzato);
  • generazione di immagini raster (Google Imagen) con didascalia automatica.

Ogni proposta passa dall'anteprima (Accetta/Rifiuta/Rigenera): l'AI non
sovrascrive mai senza conferma.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMenu, QMessageBox, QInputDialog, QProgressDialog, QLineEdit,
)

from ..agents.commands import TEXT_COMMANDS, TextCommand
from ..core import diagram, image_gen
from .ai_worker import AiWorker
from .ai_preview import AiPreviewDialog
from .icons import icon

# icona minimale associata a ciascun comando di editing testuale (per chiave)
_COMMAND_ICONS = {
    "rewrite": "edit", "expand": "plus", "shorten": "minus", "continue": "play",
    "formal": "cap", "plain": "chat", "fix": "check",
}


class AiEditingController:
    def __init__(self, widget, get_engine: Callable, get_book: Callable | None = None,
                 get_base_dir: Callable[[], Path | None] | None = None,
                 get_image_config: Callable | None = None, parent=None):
        self.w = widget
        self.get_engine = get_engine
        self.get_book = get_book or (lambda: None)
        self.get_base_dir = get_base_dir or (lambda: None)
        # config immagini: di default dall'ambiente, ma la GUI può iniettare
        # quella costruita dalle Impostazioni (chiave salvata in-app).
        self.get_image_config = get_image_config or (lambda: image_gen.ImageGenConfig.from_env())
        self.parent = parent or widget
        self._worker: AiWorker | None = None
        self._busy: QProgressDialog | None = None

        self.w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.w.customContextMenuRequested.connect(self._show_menu)

    # ------------------------------------------------------------------ menu
    def _selected_text(self) -> str:
        # QTextEdit usa U+2029 come separatore di paragrafo nelle selezioni
        return self.w.textCursor().selectedText().replace(" ", "\n")

    def _show_menu(self, pos):
        menu = self.w.createStandardContextMenu()
        menu.addSeparator()
        ai = menu.addMenu(icon("cpu"), "AI")
        has_sel = bool(self._selected_text().strip())
        for cmd in TEXT_COMMANDS:
            act = ai.addAction(icon(_COMMAND_ICONS.get(cmd.key, "wand")), cmd.label)
            act.setEnabled(has_sel or not cmd.needs_selection)
            act.triggered.connect(lambda _checked=False, c=cmd: self.run_command(c))
        ai.addSeparator()
        ai.addAction(icon("chart"), "Genera diagramma…", self.generate_diagram)
        ai.addAction(icon("image"), "Genera immagine…", self.generate_image)
        menu.exec(self.w.mapToGlobal(pos))

    # ------------------------------------------------------------------ infra
    def _engine_or_warn(self):
        eng = self.get_engine()
        if eng is None:
            QMessageBox.information(self.parent, "Motore AI",
                                   "Nessun motore AI disponibile.")
        return eng

    def _start(self, label: str, fn, on_done):
        if self._worker and self._worker.isRunning():
            return
        self._busy = QProgressDialog(label, None, 0, 0, self.parent)
        self._busy.setWindowTitle("AI")
        self._busy.setMinimumDuration(0)
        self._busy.setCancelButton(None)
        self._busy.show()
        self._worker = AiWorker(fn)
        self._worker.done.connect(lambda res: self._finish(res, on_done))
        self._worker.failed.connect(self._fail)
        self._worker.start()

    def _finish(self, result, on_done):
        if self._busy:
            self._busy.close(); self._busy = None
        on_done(result)

    def _fail(self, err: str):
        if self._busy:
            self._busy.close(); self._busy = None
        QMessageBox.critical(self.parent, "Errore AI", err)

    def _insert_at_cursor(self, text: str):
        cur = self.w.textCursor()
        cur.insertText(text)
        self.w.setTextCursor(cur)

    # ------------------------------------------------------------------ comandi testo
    def run_command(self, cmd: TextCommand):
        eng = self._engine_or_warn()
        if eng is None:
            return
        book = self.get_book()
        cursor = self.w.textCursor()
        selected = self._selected_text()

        if cmd.needs_selection and not selected.strip():
            QMessageBox.information(self.parent, cmd.label,
                                   "Seleziona prima il testo su cui operare.")
            return

        if not selected.strip():  # es. «Continua»: usa il testo che precede
            doc_text = self.w.toPlainText()
            pos = cursor.position()
            source = doc_text[max(0, pos - 1500):pos]
            replace = False
        else:
            source = selected
            replace = True

        def fn():
            return eng.edit_text(cmd.instruction, source, book)

        def on_done(result):
            dlg = AiPreviewDialog(self.parent, f"AI — {cmd.label}",
                                  original=(selected if replace else ""),
                                  proposed=str(result))
            dlg.exec()
            if dlg.action == "accept":
                out = dlg.result_text
                self.w.setTextCursor(cursor)
                if replace:
                    cursor.insertText(out)
                else:
                    self._insert_at_cursor(("\n\n" if not out.startswith("\n") else "") + out)
            elif dlg.action == "regenerate":
                self.run_command(cmd)

        self._start(f"{cmd.label}…", fn, on_done)

    # ------------------------------------------------------------------ diagrammi
    def generate_diagram(self):
        eng = self._engine_or_warn()
        if eng is None:
            return
        desc, ok = QInputDialog.getMultiLineText(
            self.parent, "Genera diagramma",
            "Descrivi lo schema da generare:", "")
        if not ok or not desc.strip():
            return
        kind, ok = QInputDialog.getItem(
            self.parent, "Tipo di diagramma",
            "Formato:", ["tikz (codice LaTeX nativo)", "mermaid (immagine)"], 0, False)
        if not ok:
            return
        kind = "mermaid" if kind.startswith("mermaid") else "tikz"
        book = self.get_book()

        def fn():
            code = eng.generate_diagram(desc, kind, book)
            caption = eng.caption(desc, book)
            return (code, caption)

        def on_done(result):
            code, caption = result
            if kind == "tikz":
                snippet = diagram.tikz_figure(code, caption)
            else:
                snippet = self._mermaid_snippet(code, caption, desc)
                if snippet is None:
                    return
            dlg = AiPreviewDialog(self.parent, "AI — Diagramma", original="",
                                  proposed=snippet, allow_regenerate=True)
            dlg.exec()
            if dlg.action == "accept":
                self._insert_at_cursor("\n" + dlg.result_text + "\n")
            elif dlg.action == "regenerate":
                self.generate_diagram()

        self._start("Genero il diagramma…", fn, on_done)

    def _mermaid_snippet(self, code: str, caption: str, desc: str):
        base = self.get_base_dir()
        if base is None:
            QMessageBox.warning(self.parent, "Diagramma",
                                "Salva prima il file: serve una cartella per l'immagine.")
            return None
        images = Path(base) / "images"
        name = re.sub(r"[^a-z0-9]+", "_", desc.lower()).strip("_")[:30] or "diagramma"
        out = images / f"{name}.png"
        try:
            diagram.render_mermaid(code, out)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self.parent, "Mermaid", str(e))
            return None
        rel = f"images/{out.name}"
        return diagram.image_figure(rel, caption)

    # ------------------------------------------------------------------ immagini
    def generate_image(self):
        eng = self._engine_or_warn()
        if eng is None:
            return
        cfg = self.get_image_config()
        ok, msg = image_gen.image_available(cfg)
        if not ok:
            QMessageBox.warning(self.parent, "Generazione immagini", msg)
            return
        base = self.get_base_dir()
        if base is None:
            QMessageBox.warning(self.parent, "Immagine",
                                "Salva prima il file: serve una cartella per l'immagine.")
            return
        desc, ok = QInputDialog.getMultiLineText(
            self.parent, "Genera immagine",
            "Descrivi l'immagine da generare:", "")
        if not ok or not desc.strip():
            return
        name, ok = QInputDialog.getText(
            self.parent, "Nome file", "Nome del file (senza estensione):",
            QLineEdit.EchoMode.Normal,
            re.sub(r"[^a-z0-9]+", "_", desc.lower()).strip("_")[:30] or "immagine")
        if not ok or not name.strip():
            return
        book = self.get_book()
        out = Path(base) / "images" / f"{name.strip()}.png"

        def fn():
            prompt = eng.image_prompt(desc, book)
            image_gen.generate_image(prompt, out, cfg)
            caption = eng.caption(desc, book)
            return caption

        def on_done(caption):
            rel = f"images/{out.name}"
            snippet = diagram.image_figure(rel, caption)
            dlg = AiPreviewDialog(self.parent, "AI — Immagine", original="",
                                  proposed=snippet, allow_regenerate=False)
            dlg.exec()
            if dlg.action == "accept":
                self._insert_at_cursor("\n" + dlg.result_text + "\n")

        self._start("Genero l'immagine…", fn, on_done)
