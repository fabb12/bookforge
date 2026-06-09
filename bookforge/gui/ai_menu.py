"""Controller per la scrittura assistita dall'AI dentro un editor di testo.

`AiEditingController` aggancia un menu contestuale «🤖 AI» a un QPlainTextEdit /
QTextEdit e gestisce:
  • comandi sulla selezione (riscrivi, espandi, accorcia, continua, …);
  • generazione di diagrammi come codice (TikZ) o immagine (Mermaid renderizzato);
  • generazione di immagini raster (Google/Ideogram) con scelta dello stile di
    disegno, varianti multiple e selezione dell'immagine prima dell'inserimento.
    Per gli stili con scritte (infografica, lavagna) propone il generatore di
    diagrammi, che rende testo leggibile e frecce coerenti.

Ogni proposta passa dall'anteprima (Accetta/Rifiuta/Rigenera): l'AI non
sovrascrive mai senza conferma.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMenu, QMessageBox, QInputDialog, QProgressDialog,
)

from dataclasses import replace

from ..agents.commands import TEXT_COMMANDS, TextCommand
from ..core import diagram, image_gen
from .ai_worker import AiWorker
from .ai_preview import AiPreviewDialog
from .image_dialog import ImageOptionsDialog, ImagePreviewDialog
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

        self._init_actions()

        self.w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.w.customContextMenuRequested.connect(self._show_menu)
        self.w.selectionChanged.connect(self._update_action_state)
        # Inizializziamo lo stato corretto all'avvio
        self._update_action_state()

    def _init_actions(self):
        self._actions = {}

        shortcuts = {
            "rewrite": "Ctrl+Shift+R",
            "expand": "Ctrl+Shift+E",
            "shorten": "Ctrl+Shift+S",
            "continue": "Ctrl+Shift+C",
            "formal": "Ctrl+Shift+F",
            "plain": "Ctrl+Shift+P",
            "fix": "Ctrl+Shift+X",
        }

        for cmd in TEXT_COMMANDS:
            act = QAction(icon(_COMMAND_ICONS.get(cmd.key, "wand")), cmd.label, self.w)
            if cmd.key in shortcuts:
                act.setShortcut(QKeySequence(shortcuts[cmd.key]))
                act.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            act.triggered.connect(lambda _checked=False, c=cmd: self.run_command(c))
            self.w.addAction(act)
            self._actions[cmd.key] = act

        self._action_diagram = QAction(icon("chart"), "Genera diagramma dalla selezione", self.w)
        self._action_diagram.setShortcut(QKeySequence("Ctrl+Shift+D"))
        self._action_diagram.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._action_diagram.triggered.connect(self.generate_diagram)
        self.w.addAction(self._action_diagram)

        self._action_image = QAction(icon("image"), "Genera immagine dalla selezione", self.w)
        self._action_image.setShortcut(QKeySequence("Ctrl+Shift+I"))
        self._action_image.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._action_image.triggered.connect(self.generate_image)
        self.w.addAction(self._action_image)

    def _update_action_state(self):
        has_sel = bool(self._selected_text().strip())
        for cmd in TEXT_COMMANDS:
            if cmd.key in self._actions:
                self._actions[cmd.key].setEnabled(has_sel or not cmd.needs_selection)

        self._action_diagram.setEnabled(has_sel)
        self._action_image.setEnabled(has_sel)

    # ------------------------------------------------------------------ menu
    def _selected_text(self) -> str:
        # QTextEdit usa U+2029 come separatore di paragrafo nelle selezioni
        return self.w.textCursor().selectedText().replace(" ", "\n")

    def _show_menu(self, pos):
        menu = self.w.createStandardContextMenu()
        first_action = menu.actions()[0] if menu.actions() else None

        ai = QMenu("AI", menu)
        ai.setIcon(icon("cpu"))

        for cmd in TEXT_COMMANDS:
            act = self._actions[cmd.key]
            ai.addAction(act)

        ai.addSeparator()

        # Diagrammi e immagini operano sul testo selezionato (è quello la
        # descrizione): senza selezione le azioni restano disabilitate.
        ai.addAction(self._action_diagram)

        ai.addAction(self._action_image)

        if first_action:
            menu.insertMenu(first_action, ai)
            menu.insertSeparator(first_action)
        else:
            menu.addMenu(ai)

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
        desc = self._selected_text().strip()
        if not desc:
            QMessageBox.information(self.parent, "Genera diagramma",
                                   "Seleziona prima il testo che descrive il diagramma.")
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

    def _unique_path(self, folder: Path, stem: str, ext: str = ".png") -> Path:
        """Percorso `folder/stem.ext` reso univoco aggiungendo un suffisso
        numerico se il file esiste già (così non si sovrascrivono immagini)."""
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"{stem}{ext}"
        i = 2
        while out.exists():
            out = folder / f"{stem}_{i}{ext}"
            i += 1
        return out

    def _mermaid_snippet(self, code: str, caption: str, desc: str):
        base = self.get_base_dir()
        if base is None:
            QMessageBox.warning(self.parent, "Diagramma",
                                "Salva prima il file: serve una cartella per l'immagine.")
            return None
        name = re.sub(r"[^a-z0-9]+", "_", desc.lower()).strip("_")[:30] or "diagramma"
        out = self._unique_path(Path(base) / "images", name)
        try:
            diagram.render_mermaid(code, out)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self.parent, "Mermaid", str(e))
            return None
        rel = f"images/{out.name}"
        return diagram.image_figure(rel, caption)

    # ------------------------------------------------------------------ immagini
    def _suggest_diagram_instead(self, style: str) -> str:
        """Propone il generatore di diagrammi per gli stili con scritte.

        Un'infografica (o una lavagna) vive di etichette leggibili e frecce che
        collegano i concetti giusti: cose che i generatori di immagini raster non
        sanno fare in modo affidabile. Suggeriamo quindi il diagramma — che
        compone testo reale e collegamenti coerenti — senza imporlo: l'autore può
        sempre generare comunque l'immagine. Ritorna «diagram» | «image» | «cancel».
        """
        box = QMessageBox(self.parent)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Infografica: meglio un diagramma")
        box.setText(f"Lo stile «{style}» ha bisogno di scritte leggibili e di "
                    "frecce che colleghino davvero i concetti.")
        box.setInformativeText(
            "I generatori di immagini disegnano le parole come forme: spesso le "
            "scritte escono illeggibili e le frecce non corrispondono alle "
            "etichette. Il generatore di diagrammi (TikZ/Mermaid) compone testo "
            "reale e collegamenti coerenti, ed è vettoriale.\n\n"
            "Vuoi creare un diagramma invece di un'immagine?")
        b_diag = box.addButton("Usa diagramma (consigliato)",
                               QMessageBox.ButtonRole.AcceptRole)
        b_img = box.addButton("Genera comunque immagine",
                              QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Annulla", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(b_diag)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_diag:
            return "diagram"
        if clicked is b_img:
            return "image"
        return "cancel"

    def generate_image(self):
        eng = self._engine_or_warn()
        if eng is None:
            return
        desc = self._selected_text().strip()
        if not desc:
            QMessageBox.information(self.parent, "Genera immagine",
                                   "Seleziona prima il testo che descrive l'immagine.")
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
        # Opzioni sotto il controllo dell'autore: descrizione, stile, proporzioni
        # e quante varianti generare (poi ne sceglierà una).
        opts = ImageOptionsDialog(self.parent, desc, default_aspect=cfg.aspect_ratio)
        if not opts.exec():
            return
        description = opts.description or desc
        style = opts.style_label
        count = opts.variants
        # Gli stili con scritte (infografica, lavagna) hanno bisogno di testo
        # ESATTO e di frecce che colleghino davvero i concetti: i modelli
        # text-to-image disegnano le parole come forme e spesso escono
        # illeggibili, con frecce scollegate dalle etichette. Per questi stili
        # proponiamo il generatore di diagrammi (testo reale + collegamenti
        # coerenti, per giunta vettoriale). L'autore resta libero di proseguire.
        if image_gen.style_needs_text(style):
            choice = self._suggest_diagram_instead(style)
            if choice == "cancel":
                return
            if choice == "diagram":
                self.generate_diagram()
                return
            # choice == "image": prosegue con la generazione raster
        cfg = replace(cfg, aspect_ratio=opts.aspect_ratio)
        # L'immagine va inserita SOTTO il testo selezionato (la sua descrizione),
        # senza sovrascriverlo: ricordiamo la fine della selezione come punto
        # d'inserimento, così la prosa di partenza resta intatta.
        insert_pos = self.w.textCursor().selectionEnd()
        self._run_image_generation(description, style, count, cfg, Path(base), insert_pos)

    def _run_image_generation(self, description: str, style: str, count: int,
                              cfg, base: Path, insert_pos: int):
        """Genera le immagini, le mostra in anteprima e inserisce quella scelta.

        Tenuto separato dalla raccolta opzioni così che «Rigenera» possa rilanciare
        la stessa configurazione senza richiedere di nuovo all'utente le scelte.
        `insert_pos` è la posizione (fine della selezione originale) dove va messa
        l'immagine, così resta sotto il testo da cui è partito il prompt.
        """
        eng = self._engine_or_warn()
        if eng is None:
            return
        book = self.get_book()
        name = re.sub(r"[^a-z0-9]+", "_", description.lower()).strip("_")[:30] or "immagine"

        def fn():
            # lo stile (e la lingua del libro, per le infografiche) è gestito
            # dentro image_prompt: il prompt risultante è già completo.
            prompt = eng.image_prompt(description, book, style)
            paths: list[Path] = []
            for _ in range(max(1, count)):
                out = self._unique_path(base / "images", name)
                image_gen.generate_image(prompt, out, cfg, style)
                paths.append(out)
            caption = eng.caption(description, book)
            return paths, caption

        def on_done(result):
            paths, caption = result
            dlg = ImagePreviewDialog(self.parent, paths, caption, allow_regenerate=True)
            dlg.exec()
            if dlg.action == "accept":
                chosen = dlg.selected_path or paths[0]
                self._cleanup_unused(paths, keep=chosen)
                rel = f"images/{chosen.name}"
                snippet = diagram.image_figure(rel, dlg.caption_text)
                # posiziona il cursore alla fine del testo selezionato e inserisce
                # lì sotto, senza toccare la selezione di partenza.
                cur = self.w.textCursor()
                pos = min(insert_pos, len(self.w.toPlainText()))
                cur.setPosition(pos)
                self.w.setTextCursor(cur)
                self._insert_at_cursor("\n" + snippet + "\n")
            else:
                # rifiuto o rigenera: scarta tutte le immagini prodotte
                self._cleanup_unused(paths, keep=None)
                if dlg.action == "regenerate":
                    self._run_image_generation(description, style, count, cfg, base, insert_pos)

        self._start("Genero l'immagine…", fn, on_done)

    def _cleanup_unused(self, paths: list[Path], keep: Path | None):
        """Rimuove le immagini non scelte per non lasciare file orfani in `images/`."""
        for p in paths:
            if p != keep:
                try:
                    p.unlink()
                except OSError:
                    pass
