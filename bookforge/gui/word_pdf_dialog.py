"""Dialog «Word → LaTeX → PDF».

L'utente sceglie un .docx, decide come sistemarlo (margini, immagini, didascalie,
indice, correzione ortografica) e ottiene un sorgente LaTeX impaginato e — se è
installato LaTeX — il PDF compilato. Pensato per partire da un Word già scritto e
arrivare in un colpo solo a un documento pronto.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QPushButton,
    QLineEdit, QLabel, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QMessageBox, QProgressBar, QWidget,
)

from ..core.word_to_latex import WordFixOptions, pandoc_available
from .word_worker import WordToPdfWorker
from .icons import icon, app_icon


class WordToPdfDialog(QDialog):
    """Dialog non bloccante per la pipeline Word → LaTeX → PDF."""

    def __init__(self, parent=None, engine=None, engine_real: bool = False):
        super().__init__(parent)
        self.engine = engine
        self.engine_real = engine_real
        self.worker: WordToPdfWorker | None = None
        self._last_pdf: Path | None = None

        self.setWindowTitle("Word → LaTeX → PDF")
        self.setWindowIcon(app_icon())
        self.resize(620, 640)
        self._build_ui()

    # --------------------------------------------------------------- UI
    def _build_ui(self):
        outer = QVBoxLayout(self)

        intro = QLabel(
            "Converte un documento Word in LaTeX con pandoc, ne sistema "
            "l'impaginazione e genera il PDF.")
        intro.setObjectName("Subtitle"); intro.setWordWrap(True)
        outer.addWidget(intro)

        if not pandoc_available():
            warn = QLabel("⚠ pandoc non è installato: la conversione non sarà "
                          "possibile finché non lo installi (https://pandoc.org).")
            warn.setObjectName("Subtitle"); warn.setWordWrap(True)
            outer.addWidget(warn)

        # --- file ---
        files = QGroupBox("File")
        ff = QFormLayout(files)
        self.in_edit = QLineEdit(); self.in_edit.setPlaceholderText("Seleziona un file .docx…")
        in_btn = QPushButton("Sfoglia…"); in_btn.clicked.connect(self._pick_input)
        in_row = QHBoxLayout(); in_row.addWidget(self.in_edit); in_row.addWidget(in_btn)
        in_wrap = QWidget(); in_wrap.setLayout(in_row)
        ff.addRow("Documento", in_wrap)

        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Cartella di destinazione del progetto LaTeX")
        out_btn = QPushButton("Sfoglia…"); out_btn.clicked.connect(self._pick_output)
        out_row = QHBoxLayout(); out_row.addWidget(self.out_edit); out_row.addWidget(out_btn)
        out_wrap = QWidget(); out_wrap.setLayout(out_row)
        ff.addRow("Cartella uscita", out_wrap)
        outer.addWidget(files)

        # --- metadati ---
        meta = QGroupBox("Metadati (opzionali)")
        mf = QFormLayout(meta)
        self.m_title = QLineEdit(); self.m_author = QLineEdit()
        self.m_lang = QComboBox()
        self.m_lang.addItems(["italiano", "inglese", "francese", "spagnolo", "tedesco"])
        mf.addRow("Titolo", self.m_title)
        mf.addRow("Autore", self.m_author)
        mf.addRow("Lingua", self.m_lang)
        outer.addWidget(meta)

        # --- sistemazioni ---
        fix = QGroupBox("Sistemazioni d'impaginazione")
        fl = QFormLayout(fix)
        self.c_center = QCheckBox("Centra le immagini"); self.c_center.setChecked(True)
        self.c_fit = QCheckBox("Adatta le immagini alla larghezza della pagina")
        self.c_fit.setChecked(True)
        self.c_caption = QCheckBox("Sistema le didascalie (piccole, etichetta in grassetto)")
        self.c_caption.setChecked(True)
        self.c_toc = QCheckBox("Genera l'indice"); self.c_toc.setChecked(True)
        self.c_margins = QCheckBox("Imposta i margini"); self.c_margins.setChecked(True)
        self.c_margin = QDoubleSpinBox(); self.c_margin.setRange(0.5, 6.0)
        self.c_margin.setSingleStep(0.5); self.c_margin.setValue(2.5); self.c_margin.setSuffix(" cm")
        fl.addRow("", self.c_center)
        fl.addRow("", self.c_fit)
        fl.addRow("", self.c_caption)
        fl.addRow("", self.c_toc)
        fl.addRow("", self.c_margins)
        fl.addRow("Margine", self.c_margin)
        outer.addWidget(fix)

        # --- AI ---
        ai = QGroupBox("Correzione del testo (AI)")
        al = QVBoxLayout(ai)
        self.c_proof = QCheckBox("Correggi l'ortografia dei paragrafi con il motore AI")
        al.addWidget(self.c_proof)
        note = QLabel("Corregge solo i paragrafi di prosa pura (senza comandi LaTeX), "
                      "per non rischiare di rompere il codice.")
        note.setObjectName("Subtitle"); note.setWordWrap(True)
        al.addWidget(note)
        if not self.engine_real:
            warn = QLabel("Motore offline: la correzione si limita alla pulizia degli spazi.")
            warn.setObjectName("Subtitle"); warn.setWordWrap(True)
            al.addWidget(warn)
        outer.addWidget(ai)

        self.c_compile = QCheckBox("Compila il PDF al termine (richiede LaTeX installato)")
        self.c_compile.setChecked(True)
        outer.addWidget(self.c_compile)

        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.hide()
        outer.addWidget(self.progress)
        self.progress_label = QLabel(""); self.progress_label.setObjectName("Subtitle")
        outer.addWidget(self.progress_label)

        btn_row = QHBoxLayout(); btn_row.addStretch(1)
        self.open_btn = QPushButton(icon("eye"), " Apri PDF"); self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_pdf)
        close_btn = QPushButton("Chiudi"); close_btn.clicked.connect(self.reject)
        self.run_btn = QPushButton(icon("wrench"), " Converti e genera")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._run)
        btn_row.addWidget(self.open_btn); btn_row.addWidget(close_btn); btn_row.addWidget(self.run_btn)
        outer.addLayout(btn_row)

    # --------------------------------------------------------------- pickers
    def _pick_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Scegli il documento Word", "", "Word (*.docx);;Tutti i file (*)")
        if not path:
            return
        self.in_edit.setText(path)
        p = Path(path)
        if not self.out_edit.text().strip():
            self.out_edit.setText(str(p.with_suffix("")) + "_latex")
        if not self.m_title.text().strip():
            self.m_title.setText(p.stem.replace("_", " "))

    def _pick_output(self):
        d = QFileDialog.getExistingDirectory(self, "Cartella di destinazione")
        if d:
            self.out_edit.setText(d)

    # --------------------------------------------------------------- run
    def _collect_options(self) -> WordFixOptions:
        return WordFixOptions(
            center_images=self.c_center.isChecked(),
            fit_images=self.c_fit.isChecked(),
            format_captions=self.c_caption.isChecked(),
            add_toc=self.c_toc.isChecked(),
            set_margins=self.c_margins.isChecked(),
            margin_cm=self.c_margin.value(),
            language=self.m_lang.currentText(),
            proofread=self.c_proof.isChecked(),
            title=self.m_title.text().strip(),
            author=self.m_author.text().strip(),
        )

    def _run(self):
        if self.worker and self.worker.isRunning():
            return
        src = self.in_edit.text().strip()
        out = self.out_edit.text().strip()
        if not src or not Path(src).exists():
            QMessageBox.warning(self, "File mancante", "Seleziona un file .docx valido.")
            return
        if not out:
            out = str(Path(src).with_suffix("")) + "_latex"
            self.out_edit.setText(out)
        if not pandoc_available():
            QMessageBox.warning(self, "pandoc mancante",
                                "Installa pandoc per usare questa funzione.")
            return

        options = self._collect_options()
        corrector = self.engine.proofread if (options.proofread and self.engine) else None

        self.run_btn.setEnabled(False); self.open_btn.setEnabled(False)
        self.progress.show(); self.progress_label.setText("Avvio…")
        self.worker = WordToPdfWorker(src, out, options, corrector,
                                      compile_pdf=self.c_compile.isChecked())
        self.worker.progress.connect(self.progress_label.setText)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_done(self, payload: dict):
        self.progress.hide(); self.run_btn.setEnabled(True)
        res = payload["result"]
        tex = res.tex_path
        if payload["pdf_ok"]:
            self._last_pdf = Path(tex).with_suffix(".pdf")
            self.open_btn.setEnabled(True)
            self.progress_label.setText("Documento pronto ✓")
            QMessageBox.information(self, "Fatto",
                                    f"PDF generato:\n{self._last_pdf}\n\nLaTeX in:\n{tex}")
        else:
            extra = ("\n\n" + payload["pdf_log"][:1500]) if payload["pdf_log"] else ""
            self.progress_label.setText("LaTeX pronto (PDF non compilato)")
            QMessageBox.information(
                self, "LaTeX pronto",
                f"Sorgente LaTeX sistemato:\n{tex}\n\n"
                f"Il PDF non è stato compilato (LaTeX assente o errore).{extra}")

    def _on_failed(self, err: str):
        self.progress.hide(); self.run_btn.setEnabled(True)
        self.progress_label.setText("")
        QMessageBox.critical(self, "Errore", err)

    def _open_pdf(self):
        if not self._last_pdf or not self._last_pdf.exists():
            return
        from ..core import compiler
        ok, msg = compiler.open_pdf_path(self._last_pdf)
        if not ok:
            QMessageBox.warning(self, "PDF", msg)
