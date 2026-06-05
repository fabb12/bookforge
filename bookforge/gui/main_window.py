"""Finestra principale di BookForge: editor capitoli + agenti + compilazione."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QLineEdit, QTextEdit, QPlainTextEdit,
    QTabWidget, QFormLayout, QComboBox, QGroupBox, QMessageBox, QProgressBar,
    QInputDialog, QFileDialog,
)

from ..core.model import Project, Chapter
from ..core import compiler
from ..agents.engine import EngineConfig, build_engine
from .worker import GenerateWorker


class MainWindow(QMainWindow):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.book = project.book
        self.worker: GenerateWorker | None = None
        self._dirty = False

        self.engine_config = EngineConfig.from_env()
        self.engine, self.engine_real, msg = build_engine(self.engine_config)

        self.setWindowTitle(f"BookForge — {self.book.title}")
        self.resize(1180, 760)
        self._build_ui()
        self._refresh_chapter_list()
        self._load_book_meta()
        self.statusBar().showMessage(msg)
        if self.book.chapters:
            self.chapter_list.setCurrentRow(0)

    # ============================================================ UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        splitter.addWidget(self._left_panel())
        splitter.addWidget(self._center_panel())
        splitter.addWidget(self._right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([240, 620, 320])

        self._build_toolbar()

    def _build_toolbar(self):
        tb = self.addToolBar("Azioni")
        tb.setMovable(False)

        def add(text, slot, primary=False, danger=False):
            b = QPushButton(text)
            if primary: b.setObjectName("Primary")
            if danger: b.setObjectName("Danger")
            b.clicked.connect(slot)
            tb.addWidget(b)
            return b

        add("💾 Salva", self._save)
        add("🧩 Genera capitolo", self._generate_current, primary=True)
        tb.addSeparator()
        add("📄 Esporta .tex", self._export_tex)
        add("🛠 Compila PDF", self._compile_pdf)
        add("📖 Apri in TeXstudio", self._open_texstudio)
        add("👁 Apri PDF", self._open_pdf)

    def _left_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lbl = QLabel("CAPITOLI"); lbl.setObjectName("SectionLabel")
        lay.addWidget(lbl)
        self.chapter_list = QListWidget()
        self.chapter_list.currentRowChanged.connect(self._on_chapter_selected)
        lay.addWidget(self.chapter_list)

        row = QHBoxLayout()
        b_add = QPushButton("➕"); b_add.setToolTip("Aggiungi capitolo")
        b_add.clicked.connect(self._add_chapter)
        b_up = QPushButton("▲"); b_up.setToolTip("Sposta su")
        b_up.clicked.connect(lambda: self._move(-1))
        b_dn = QPushButton("▼"); b_dn.setToolTip("Sposta giù")
        b_dn.clicked.connect(lambda: self._move(1))
        b_del = QPushButton("🗑"); b_del.setObjectName("Danger")
        b_del.setToolTip("Elimina capitolo")
        b_del.clicked.connect(self._delete_chapter)
        for b in (b_add, b_up, b_dn, b_del):
            row.addWidget(b)
        lay.addLayout(row)
        return w

    def _center_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        self.ch_title = QLineEdit()
        self.ch_title.setPlaceholderText("Titolo del capitolo")
        self.ch_title.editingFinished.connect(self._commit_title)
        lay.addWidget(self.ch_title)

        self.tabs = QTabWidget()

        # concetti
        self.concepts_edit = QPlainTextEdit()
        self.concepts_edit.setPlaceholderText(
            "Inserisci qui i concetti grezzi da sviluppare nel capitolo, uno per riga.\n"
            "Gli agenti li trasformeranno in prosa secondo lo stile impostato.")
        self.tabs.addTab(self.concepts_edit, "1 · Concetti")

        # prosa generata (editabile)
        self.text_edit = QTextEdit()
        self.tabs.addTab(self.text_edit, "2 · Testo generato")

        # latex
        self.latex_edit = QPlainTextEdit()
        self.tabs.addTab(self.latex_edit, "3 · LaTeX")

        # riassunto
        self.summary_edit = QPlainTextEdit()
        self.tabs.addTab(self.summary_edit, "4 · Riassunto")

        lay.addWidget(self.tabs)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("Subtitle")
        lay.addWidget(self.progress_label)
        return w

    def _right_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tabs = QTabWidget()

        # --- metadati ---
        meta = QWidget(); mform = QFormLayout(meta)
        self.m_title = QLineEdit(); self.m_subtitle = QLineEdit()
        self.m_author = QLineEdit(); self.m_year = QLineEdit()
        self.m_topic = QLineEdit()
        self.m_abstract = QPlainTextEdit(); self.m_abstract.setMaximumHeight(90)
        self.m_preface = QPlainTextEdit(); self.m_preface.setMaximumHeight(90)
        self.m_back = QPlainTextEdit(); self.m_back.setMaximumHeight(70)
        mform.addRow("Titolo", self.m_title)
        mform.addRow("Sottotitolo", self.m_subtitle)
        mform.addRow("Autore", self.m_author)
        mform.addRow("Anno", self.m_year)
        mform.addRow("Argomento", self.m_topic)
        mform.addRow("Abstract", self.m_abstract)
        mform.addRow("Prefazione", self.m_preface)
        mform.addRow("Quarta cop.", self.m_back)
        tabs.addTab(meta, "Libro")

        # --- stile ---
        style = QWidget(); sform = QFormLayout(style)
        self.s_tone = QLineEdit(); self.s_audience = QLineEdit()
        self.s_language = QLineEdit(); self.s_person = QLineEdit()
        self.s_extra = QPlainTextEdit(); self.s_extra.setMaximumHeight(80)
        self.s_class = QComboBox(); self.s_class.addItems(["book", "report", "article"])
        self.s_font = QComboBox(); self.s_font.addItems(["10pt", "11pt", "12pt"])
        self.s_paper = QComboBox(); self.s_paper.addItems(["a4paper", "a5paper", "letterpaper"])
        sform.addRow("Tono", self.s_tone)
        sform.addRow("Pubblico", self.s_audience)
        sform.addRow("Lingua", self.s_language)
        sform.addRow("Persona", self.s_person)
        sform.addRow("Istruzioni extra", self.s_extra)
        sform.addRow("Classe doc.", self.s_class)
        sform.addRow("Corpo", self.s_font)
        sform.addRow("Formato", self.s_paper)
        tabs.addTab(style, "Stile")

        # --- motore AI ---
        eng = QWidget(); eform = QFormLayout(eng)
        self.e_provider = QComboBox(); self.e_provider.addItems(["openai", "anthropic", "google"])
        self.e_provider.setCurrentText(self.engine_config.provider)
        self.e_model = QLineEdit(self.engine_config.model)
        self.e_key = QLineEdit(self.engine_config.api_key)
        self.e_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_key.setPlaceholderText("Lascia vuoto per modalità offline (test)")
        apply_btn = QPushButton("Applica motore"); apply_btn.clicked.connect(self._apply_engine)
        eform.addRow("Provider", self.e_provider)
        eform.addRow("Modello", self.e_model)
        eform.addRow("API key", self.e_key)
        eform.addRow(apply_btn)
        self.e_status = QLabel(""); self.e_status.setObjectName("Subtitle")
        self.e_status.setWordWrap(True)
        eform.addRow(self.e_status)
        tabs.addTab(eng, "Motore")

        lay.addWidget(tabs)
        save_meta = QPushButton("Applica dati libro/stile")
        save_meta.clicked.connect(self._commit_book_meta)
        lay.addWidget(save_meta)
        return w

    # ============================================================ capitoli
    def _refresh_chapter_list(self):
        cur = self.chapter_list.currentRow()
        self.chapter_list.blockSignals(True)
        self.chapter_list.clear()
        for i, ch in enumerate(self.book.chapters):
            mark = "●" if ch.text else "○"
            self.chapter_list.addItem(QListWidgetItem(f"{mark}  {i+1}. {ch.title}"))
        self.chapter_list.blockSignals(False)
        if 0 <= cur < self.chapter_list.count():
            self.chapter_list.setCurrentRow(cur)

    def _current_chapter(self) -> Chapter | None:
        i = self.chapter_list.currentRow()
        if 0 <= i < len(self.book.chapters):
            return self.book.chapters[i]
        return None

    def _on_chapter_selected(self, row: int):
        if 0 <= row < len(self.book.chapters):
            ch = self.book.chapters[row]
            self.ch_title.setText(ch.title)
            self.concepts_edit.setPlainText(ch.raw_concepts)
            self.text_edit.setPlainText(ch.text)
            self.latex_edit.setPlainText(ch.latex)
            self.summary_edit.setPlainText(ch.summary)

    def _commit_current_editors(self):
        ch = self._current_chapter()
        if not ch:
            return
        ch.title = self.ch_title.text().strip() or ch.title
        ch.raw_concepts = self.concepts_edit.toPlainText()
        ch.text = self.text_edit.toPlainText()
        ch.latex = self.latex_edit.toPlainText()
        ch.summary = self.summary_edit.toPlainText()

    def _commit_title(self):
        ch = self._current_chapter()
        if ch:
            ch.title = self.ch_title.text().strip() or ch.title
            self._refresh_chapter_list()

    def _add_chapter(self):
        self._commit_current_editors()
        title, ok = QInputDialog.getText(self, "Nuovo capitolo", "Titolo:")
        if not ok:
            return
        self.book.add_chapter(title.strip())
        self._refresh_chapter_list()
        self.chapter_list.setCurrentRow(len(self.book.chapters) - 1)

    def _delete_chapter(self):
        ch = self._current_chapter()
        if not ch:
            return
        if QMessageBox.question(self, "Elimina",
                                f"Eliminare «{ch.title}»?") == QMessageBox.StandardButton.Yes:
            self.book.remove_chapter(ch.id)
            self._refresh_chapter_list()

    def _move(self, delta: int):
        ch = self._current_chapter()
        if not ch:
            return
        self._commit_current_editors()
        self.book.move_chapter(ch.id, delta)
        self._refresh_chapter_list()
        new = next((i for i, c in enumerate(self.book.chapters) if c.id == ch.id), 0)
        self.chapter_list.setCurrentRow(new)

    # ============================================================ metadati/stile
    def _load_book_meta(self):
        b = self.book; s = b.style
        self.m_title.setText(b.title); self.m_subtitle.setText(b.subtitle)
        self.m_author.setText(b.author); self.m_year.setText(b.year)
        self.m_topic.setText(b.topic); self.m_abstract.setPlainText(b.abstract)
        self.m_preface.setPlainText(b.preface); self.m_back.setPlainText(b.back_cover)
        self.s_tone.setText(s.tone); self.s_audience.setText(s.audience)
        self.s_language.setText(s.language); self.s_person.setText(s.person)
        self.s_extra.setPlainText(s.extra_instructions)
        self.s_class.setCurrentText(s.document_class)
        self.s_font.setCurrentText(s.font_size); self.s_paper.setCurrentText(s.paper)

    def _commit_book_meta(self):
        b = self.book; s = b.style
        b.title = self.m_title.text().strip() or b.title
        b.subtitle = self.m_subtitle.text(); b.author = self.m_author.text().strip()
        b.year = self.m_year.text().strip(); b.topic = self.m_topic.text().strip()
        b.abstract = self.m_abstract.toPlainText(); b.preface = self.m_preface.toPlainText()
        b.back_cover = self.m_back.toPlainText()
        s.tone = self.s_tone.text(); s.audience = self.s_audience.text()
        s.language = self.s_language.text(); s.person = self.s_person.text()
        s.extra_instructions = self.s_extra.toPlainText()
        s.document_class = self.s_class.currentText()
        s.font_size = self.s_font.currentText(); s.paper = self.s_paper.currentText()
        self.setWindowTitle(f"BookForge — {b.title}")
        self.statusBar().showMessage("Dati libro/stile applicati.", 3000)

    def _apply_engine(self):
        self.engine_config = EngineConfig(
            provider=self.e_provider.currentText(),
            model=self.e_model.text().strip(),
            api_key=self.e_key.text().strip(),
        )
        self.engine, self.engine_real, msg = build_engine(self.engine_config)
        self.e_status.setText(msg)
        self.statusBar().showMessage(msg, 5000)

    # ============================================================ generazione
    def _generate_current(self):
        if self.worker and self.worker.isRunning():
            return
        self._commit_current_editors()
        self._commit_book_meta()
        ch = self._current_chapter()
        if not ch:
            QMessageBox.information(self, "Nessun capitolo", "Aggiungi prima un capitolo.")
            return
        if not ch.raw_concepts.strip():
            QMessageBox.information(self, "Concetti mancanti",
                                    "Inserisci dei concetti nella scheda «Concetti».")
            return
        self.progress.show()
        self.progress_label.setText("Avvio agenti…")
        self.worker = GenerateWorker(self.engine, self.book, ch)
        self.worker.progress.connect(self.progress_label.setText)
        self.worker.finished_ok.connect(self._on_generated)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_generated(self, ch: Chapter):
        self.progress.hide()
        self.progress_label.setText("Capitolo generato ✓")
        self._on_chapter_selected(self.chapter_list.currentRow())
        self._refresh_chapter_list()
        self.tabs.setCurrentIndex(1)
        self._save(silent=True)

    def _on_failed(self, err: str):
        self.progress.hide()
        self.progress_label.setText("")
        QMessageBox.critical(self, "Errore generazione", err)

    # ============================================================ salvataggio/output
    def _save(self, silent: bool = False):
        self._commit_current_editors()
        self._commit_book_meta()
        try:
            self.project.save()
            if not silent:
                self.statusBar().showMessage(f"Salvato in {self.project.book_path}", 4000)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore salvataggio", str(e))

    def _export_tex(self):
        self._save(silent=True)
        path = compiler.write_tex(self.project)
        self.statusBar().showMessage(f".tex esportato: {path}", 5000)
        QMessageBox.information(self, "Esportato", f"File LaTeX salvato in:\n{path}")

    def _compile_pdf(self):
        self._save(silent=True)
        ok, log = compiler.compile_pdf(self.project)
        if ok:
            self.statusBar().showMessage("PDF compilato.", 4000)
            QMessageBox.information(self, "Compilazione", log[:1500])
        else:
            QMessageBox.warning(self, "Compilazione", log[:3000])

    def _open_texstudio(self):
        self._save(silent=True)
        ok, msg = compiler.open_in_texstudio(self.project)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "TeXstudio", msg)

    def _open_pdf(self):
        ok, msg = compiler.open_pdf(self.project)
        if not ok:
            QMessageBox.warning(self, "PDF", msg)

    def closeEvent(self, event):
        self._save(silent=True)
        event.accept()
