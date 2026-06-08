"""Dialog per formattare/impaginare/correggere un file Word (.docx).

L'utente sceglie il file di ingresso, regola le opzioni (titoli, corpo, immagini,
margini, pulizia, correzione AI opzionale) e produce un nuovo .docx sistemato.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QPushButton,
    QLineEdit, QLabel, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QMessageBox, QProgressBar, QPlainTextEdit, QWidget, QScrollArea,
)

from ..core.docx_formatter import DocxFormatRules
from .docx_worker import DocxFormatWorker
from .icons import icon, app_icon


class DocxFormatDialog(QDialog):
    """Dialog non bloccante per la formattazione di un .docx."""

    def __init__(self, parent=None, engine=None, engine_real: bool = False):
        super().__init__(parent)
        self.engine = engine
        self.engine_real = engine_real
        self.worker: DocxFormatWorker | None = None

        self.setWindowTitle("Sistema documento Word")
        self.setWindowIcon(app_icon())
        self.resize(640, 760)
        self._build_ui()

    # --------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)

        # --- file di ingresso/uscita ---
        files = QGroupBox("File")
        ff = QFormLayout(files)
        self.in_edit = QLineEdit(); self.in_edit.setPlaceholderText("Seleziona un file .docx…")
        in_btn = QPushButton("Sfoglia…"); in_btn.clicked.connect(self._pick_input)
        in_row = QHBoxLayout(); in_row.addWidget(self.in_edit); in_row.addWidget(in_btn)
        in_wrap = QWidget(); in_wrap.setLayout(in_row)
        ff.addRow("Documento", in_wrap)

        self.out_edit = QLineEdit(); self.out_edit.setPlaceholderText("…_formattato.docx")
        out_btn = QPushButton("Sfoglia…"); out_btn.clicked.connect(self._pick_output)
        out_row = QHBoxLayout(); out_row.addWidget(self.out_edit); out_row.addWidget(out_btn)
        out_wrap = QWidget(); out_wrap.setLayout(out_row)
        ff.addRow("Salva come", out_wrap)
        outer.addWidget(files)

        # contenuto scrollabile con le opzioni
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); cl = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        cl.addWidget(self._headings_group())
        cl.addWidget(self._body_group())
        cl.addWidget(self._images_group())
        cl.addWidget(self._captions_group())
        cl.addWidget(self._toc_group())
        cl.addWidget(self._page_group())
        cl.addWidget(self._ai_group())
        cl.addStretch(1)

        # progress + log
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.hide()
        outer.addWidget(self.progress)
        self.progress_label = QLabel(""); self.progress_label.setObjectName("Subtitle")
        outer.addWidget(self.progress_label)

        # pulsanti
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.run_btn = QPushButton(icon("wrench"), " Sistema documento")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._run)
        close_btn = QPushButton("Chiudi"); close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn); btn_row.addWidget(self.run_btn)
        outer.addLayout(btn_row)

    def _spin(self, val, lo, hi, step=0.5, suffix=""):
        sp = QDoubleSpinBox(); sp.setRange(lo, hi); sp.setSingleStep(step)
        sp.setValue(val)
        if suffix:
            sp.setSuffix(suffix)
        return sp

    def _headings_group(self) -> QGroupBox:
        d = DocxFormatRules()
        g = QGroupBox("Titoli"); g.setCheckable(True); g.setChecked(d.normalize_headings)
        self.g_headings = g
        f = QFormLayout(g)
        self.h_font = QLineEdit(); self.h_font.setPlaceholderText("(stesso font del corpo)")
        self.h1 = self._spin(d.heading1_size_pt, 8, 48, suffix=" pt")
        self.h2 = self._spin(d.heading2_size_pt, 8, 48, suffix=" pt")
        self.h3 = self._spin(d.heading3_size_pt, 8, 48, suffix=" pt")
        self.h_bold = QCheckBox("Grassetto"); self.h_bold.setChecked(d.heading_bold)
        f.addRow("Font titoli", self.h_font)
        f.addRow("Titolo 1", self.h1)
        f.addRow("Titolo 2", self.h2)
        f.addRow("Titolo 3", self.h3)
        f.addRow("", self.h_bold)
        return g

    def _body_group(self) -> QGroupBox:
        d = DocxFormatRules()
        g = QGroupBox("Corpo del testo"); g.setCheckable(True); g.setChecked(d.format_body)
        self.g_body = g
        f = QFormLayout(g)
        self.b_font = QComboBox(); self.b_font.setEditable(True)
        self.b_font.addItems(["Times New Roman", "Georgia", "Calibri", "Garamond",
                              "Arial", "Cambria", "Book Antiqua"])
        self.b_font.setCurrentText(d.body_font)
        self.b_size = self._spin(d.body_size_pt, 6, 24, suffix=" pt")
        self.b_spacing = QComboBox()
        self.b_spacing.addItems(["1.0", "1.15", "1.5", "2.0"])
        self.b_spacing.setCurrentText(str(d.line_spacing))
        self.b_justify = QCheckBox("Giustificato"); self.b_justify.setChecked(d.justify)
        self.b_indent = self._spin(d.first_line_indent_cm, 0, 3, step=0.1, suffix=" cm")
        self.b_after = self._spin(d.space_after_pt, 0, 24, suffix=" pt")
        f.addRow("Font", self.b_font)
        f.addRow("Corpo", self.b_size)
        f.addRow("Interlinea", self.b_spacing)
        f.addRow("Rientro 1ª riga", self.b_indent)
        f.addRow("Spazio dopo ¶", self.b_after)
        f.addRow("", self.b_justify)
        return g

    def _images_group(self) -> QGroupBox:
        d = DocxFormatRules()
        g = QGroupBox("Immagini"); g.setCheckable(True)
        g.setChecked(d.fit_images_to_page or d.center_images)
        self.g_images = g
        f = QFormLayout(g)
        self.i_fit = QCheckBox("Adatta alla larghezza della pagina")
        self.i_fit.setChecked(d.fit_images_to_page)
        self.i_max = self._spin(d.max_image_width_cm, 0, 30, step=0.5, suffix=" cm")
        self.i_center = QCheckBox("Centra le immagini"); self.i_center.setChecked(d.center_images)
        f.addRow("", self.i_fit)
        f.addRow("Larghezza max (0=auto)", self.i_max)
        f.addRow("", self.i_center)
        return g

    def _captions_group(self) -> QGroupBox:
        d = DocxFormatRules()
        g = QGroupBox("Didascalie"); g.setCheckable(True); g.setChecked(d.format_captions)
        self.g_captions = g
        f = QFormLayout(g)
        self.c_below = QCheckBox("Sposta la didascalia sotto l'immagine")
        self.c_below.setChecked(d.caption_below_image)
        self.c_size = self._spin(d.caption_size_pt, 6, 18, suffix=" pt")
        self.c_italic = QCheckBox("Corsivo"); self.c_italic.setChecked(d.caption_italic)
        self.c_center = QCheckBox("Centrata"); self.c_center.setChecked(d.caption_center)
        f.addRow("", self.c_below)
        f.addRow("Corpo", self.c_size)
        f.addRow("", self.c_italic)
        f.addRow("", self.c_center)
        note = QLabel("Riconosce le didascalie dallo stile «Didascalia/Caption» "
                      "o dal testo (Figura/Tabella N…).")
        note.setObjectName("Subtitle"); note.setWordWrap(True)
        f.addRow(note)
        return g

    def _toc_group(self) -> QGroupBox:
        d = DocxFormatRules()
        g = QGroupBox("Indice / Sommario"); g.setCheckable(True); g.setChecked(d.fix_toc)
        self.g_toc = g
        f = QVBoxLayout(g)
        note = QLabel(
            "Le voci dell'indice non vengono toccate dalla formattazione del corpo, "
            "e Word aggiornerà l'indice (voci e numeri di pagina) all'apertura del documento."
        )
        note.setObjectName("Subtitle"); note.setWordWrap(True)
        f.addWidget(note)
        return g

    def _page_group(self) -> QGroupBox:
        d = DocxFormatRules()
        g = QGroupBox("Pagina e pulizia")
        f = QFormLayout(g)
        self.p_margins = QCheckBox("Imposta margini"); self.p_margins.setChecked(d.set_margins)
        self.p_margin = self._spin(d.margin_cm, 0.5, 6, step=0.5, suffix=" cm")
        self.p_empty = QCheckBox("Rimuovi paragrafi vuoti multipli")
        self.p_empty.setChecked(d.remove_empty_paragraphs)
        self.p_spaces = QCheckBox("Comprimi spazi doppi"); self.p_spaces.setChecked(d.collapse_spaces)
        f.addRow("", self.p_margins)
        f.addRow("Margine", self.p_margin)
        f.addRow("", self.p_empty)
        f.addRow("", self.p_spaces)
        return g

    def _ai_group(self) -> QGroupBox:
        g = QGroupBox("Correzione del testo (AI)")
        f = QVBoxLayout(g)
        self.ai_correct = QCheckBox("Correggi ortografia/grammatica con il motore AI")
        self.ai_correct.setChecked(False)
        f.addWidget(self.ai_correct)
        note = QLabel(
            "Usa il motore configurato in BookForge per correggere ogni paragrafo. "
            "Più lento e — se attivo un provider reale — consuma token.\n"
            "⚠ La correzione lavora sul testo del paragrafo: la formattazione inline "
            "(grassetto/corsivo su singole parole) può andare persa."
        )
        note.setObjectName("Subtitle"); note.setWordWrap(True)
        f.addWidget(note)
        if not self.engine_real:
            warn = QLabel("Motore in modalità offline: verrà fatta solo la pulizia "
                          "degli spazi, nessuna correzione linguistica.")
            warn.setObjectName("Subtitle"); warn.setWordWrap(True)
            f.addWidget(warn)
        return g

    # --------------------------------------------------------------- file pickers
    def _pick_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Scegli il documento Word", "", "Word (*.docx);;Tutti i file (*)")
        if not path:
            return
        self.in_edit.setText(path)
        if not self.out_edit.text().strip():
            p = Path(path)
            self.out_edit.setText(str(p.with_name(f"{p.stem}_formattato{p.suffix}")))

    def _pick_output(self):
        start = self.out_edit.text().strip() or self.in_edit.text().strip()
        path, _ = QFileDialog.getSaveFileName(
            self, "Salva il documento sistemato", start, "Word (*.docx)")
        if path:
            if not path.lower().endswith(".docx"):
                path += ".docx"
            self.out_edit.setText(path)

    # --------------------------------------------------------------- run
    def _collect_rules(self) -> DocxFormatRules:
        return DocxFormatRules(
            format_body=self.g_body.isChecked(),
            body_font=self.b_font.currentText().strip() or "Times New Roman",
            body_size_pt=self.b_size.value(),
            line_spacing=float(self.b_spacing.currentText()),
            justify=self.b_justify.isChecked(),
            first_line_indent_cm=self.b_indent.value(),
            space_after_pt=self.b_after.value(),
            normalize_headings=self.g_headings.isChecked(),
            heading_font=self.h_font.text().strip(),
            heading1_size_pt=self.h1.value(),
            heading2_size_pt=self.h2.value(),
            heading3_size_pt=self.h3.value(),
            heading_bold=self.h_bold.isChecked(),
            fit_images_to_page=self.g_images.isChecked() and self.i_fit.isChecked(),
            max_image_width_cm=self.i_max.value(),
            center_images=self.g_images.isChecked() and self.i_center.isChecked(),
            format_captions=self.g_captions.isChecked(),
            caption_below_image=self.c_below.isChecked(),
            caption_size_pt=self.c_size.value(),
            caption_italic=self.c_italic.isChecked(),
            caption_center=self.c_center.isChecked(),
            fix_toc=self.g_toc.isChecked(),
            remove_empty_paragraphs=self.p_empty.isChecked(),
            collapse_spaces=self.p_spaces.isChecked(),
            set_margins=self.p_margins.isChecked(),
            margin_cm=self.p_margin.value(),
            correct_text=self.ai_correct.isChecked(),
        )

    def _run(self):
        if self.worker and self.worker.isRunning():
            return
        src = self.in_edit.text().strip()
        dst = self.out_edit.text().strip()
        if not src:
            QMessageBox.information(self, "Manca il file", "Seleziona un file .docx di ingresso.")
            return
        if not Path(src).exists():
            QMessageBox.warning(self, "File non trovato", f"Non esiste:\n{src}")
            return
        if not dst:
            p = Path(src)
            dst = str(p.with_name(f"{p.stem}_formattato{p.suffix}"))
            self.out_edit.setText(dst)
        if Path(dst).resolve() == Path(src).resolve():
            QMessageBox.warning(self, "Sovrascrittura",
                                "Il file di uscita coincide con quello di ingresso. "
                                "Scegli un nome diverso per non perdere l'originale.")
            return

        rules = self._collect_rules()
        corrector = None
        if rules.correct_text and self.engine is not None:
            corrector = self.engine.proofread

        self.run_btn.setEnabled(False)
        self.progress.show()
        self.progress_label.setText("Avvio…")
        self.worker = DocxFormatWorker(src, dst, rules, corrector)
        self.worker.progress.connect(self.progress_label.setText)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_done(self, report):
        self.progress.hide()
        self.run_btn.setEnabled(True)
        self.progress_label.setText("Documento sistemato ✓")
        QMessageBox.information(self, "Fatto", report.summary())

    def _on_failed(self, err: str):
        self.progress.hide()
        self.run_btn.setEnabled(True)
        self.progress_label.setText("")
        QMessageBox.critical(self, "Errore", err)
