"""Finestra principale di BookForge: editor capitoli + agenti + compilazione."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QLineEdit, QTextEdit, QPlainTextEdit,
    QTabWidget, QFormLayout, QComboBox, QGroupBox, QMessageBox, QProgressBar,
    QInputDialog, QFileDialog, QToolButton, QMenu, QProgressDialog,
)

from ..core.model import Project, Chapter
from ..core import compiler
from ..core.settings import (
    AppSettings, PROVIDERS, PROVIDER_LABELS, is_local, default_base_url,
)
from ..agents.engine import EngineConfig, build_engine
from .worker import GenerateWorker
from .model_selector import ModelSelector
from .icons import icon, app_icon


class MainWindow(QMainWindow):
    def __init__(self, project: Project):
        super().__init__()
        self.project = project
        self.book = project.book
        self.worker: GenerateWorker | None = None
        self._dirty = False

        self.app_settings = AppSettings.load()
        self.engine_config = EngineConfig.from_settings(self.app_settings)
        self.engine, self.engine_real, msg = build_engine(self.engine_config)

        # registra il progetto tra i recenti (per la schermata iniziale e il menu)
        self.app_settings.add_recent_project(self.project.folder)
        try:
            self.app_settings.save()
        except Exception:  # noqa: BLE001 - non bloccante
            pass

        self.setWindowTitle(f"BookForge — {self.book.title}")
        self.setWindowIcon(app_icon())
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

        self._build_menubar()
        self._build_toolbar()

    def _build_menubar(self):
        bar = self.menuBar()

        # --- Progetto: apertura, recenti e chiusura ---
        self.project_menu = bar.addMenu(icon("folder"), "Progetto")
        self._rebuild_project_menu()

        # --- Strumenti: conversione progetti e pipeline Word ---
        tools = bar.addMenu(icon("wrench"), "Strumenti")
        tools.addAction(icon("download"), "Converti progetto LaTeX in progetto BookForge…",
                        self._convert_latex_project)
        tools.addSeparator()
        tools.addAction(icon("note"), "Sistema Word → LaTeX → PDF…", self._open_word_pdf)
        tools.addAction(icon("file-text"), "Formatta documento Word (.docx)…",
                        self._open_docx_formatter)

        # --- Impostazioni: API e modelli LLM ---
        settings = bar.addMenu(icon("settings"), "Impostazioni")
        settings.addAction(icon("key"), "API e modelli LLM…", self._open_settings)

        # --- Info: presentazione e autore ---
        info = bar.addMenu(icon("info"), "Info")
        info.addAction(icon("info"), "Informazioni su BookForge…", self._open_about)

    def _build_toolbar(self):
        tb = self.addToolBar("Azioni")
        tb.setMovable(False)

        def add(text, slot, icon_name=None, primary=False, danger=False):
            b = QPushButton(text)
            if icon_name:
                b.setIcon(icon(icon_name))
            if primary: b.setObjectName("Primary")
            if danger: b.setObjectName("Danger")
            b.clicked.connect(slot)
            tb.addWidget(b)
            return b

        def tool_button(text, icon_name):
            btn = QToolButton()
            btn.setText(text)
            btn.setIcon(icon(icon_name))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            return btn

        add("Salva", self._save, "save")
        add("Genera capitolo", self._generate_current, "sparkles", primary=True)
        # tasto per interrompere la generazione in corso (capitolo o autopilota)
        self.stop_btn = add("Interrompi", self._stop_generation, "x", danger=True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("Interrompe la generazione AI in corso")

        # menu dei comandi AI a livello di capitolo
        chap_btn = tool_button("Capitolo (AI)", "wand")
        menu = QMenu(chap_btn)
        menu.addAction(icon("list"), "Genera scaletta", self._chapter_outline)
        menu.addAction(icon("link"), "Migliora raccordi", self._chapter_transitions)
        menu.addAction(icon("arrow-left"), "Ponte col capitolo precedente",
                       lambda: self._chapter_bridge("prev"))
        menu.addAction(icon("arrow-right"), "Ponte col capitolo successivo",
                       lambda: self._chapter_bridge("next"))
        menu.addAction(icon("note"), "Rigenera riassunto", self._chapter_resummarize)
        chap_btn.setMenu(menu)
        tb.addWidget(chap_btn)

        # menu del mentore / strumenti di crescita e rigore
        mentor_btn = tool_button("Mentore", "cap")
        mmenu = QMenu(mentor_btn)
        mmenu.addAction(icon("search"), "Revisione (feedback)", self._open_mentor)
        mmenu.addAction(icon("chart"), "Dashboard di crescita", self._open_metrics)
        mmenu.addAction(icon("compass"), "Mappa argomentazione", self._open_argument_map)
        mmenu.addAction(icon("book"), "Bibliografia", self._open_biblio)
        mentor_btn.setMenu(mmenu)
        tb.addWidget(mentor_btn)

        # menu autogenerazione (autopilota)
        auto_btn = tool_button("Autogenera", "rocket")
        amenu = QMenu(auto_btn)
        amenu.addAction(icon("sparkles"), "Autogenera capitolo corrente", self._autogen_current)
        amenu.addAction(icon("book"), "Autogenera capitoli vuoti", lambda: self._autogen_all(True))
        amenu.addAction(icon("refresh"), "Rigenera TUTTI i capitoli", lambda: self._autogen_all(False))
        auto_btn.setMenu(amenu)
        tb.addWidget(auto_btn)

        # menu sezioni speciali del libro (premessa, prologo, epilogo, quarta, copertina)
        sec_btn = tool_button("Sezioni libro", "book")
        smenu = QMenu(sec_btn)
        smenu.addAction(icon("sparkles"), "Genera premessa (AI)",
                        lambda: self._gen_section("premessa"))
        smenu.addAction(icon("sparkles"), "Genera prologo (AI)",
                        lambda: self._gen_section("prologo"))
        smenu.addAction(icon("sparkles"), "Genera epilogo / fine libro (AI)",
                        lambda: self._gen_section("epilogo"))
        smenu.addAction(icon("sparkles"), "Genera quarta di copertina (AI)",
                        lambda: self._gen_section("quarta"))
        smenu.addSeparator()
        smenu.addAction(icon("image"), "Genera immagine di copertina (AI)…",
                        self._gen_cover_image)
        sec_btn.setMenu(smenu)
        tb.addWidget(sec_btn)

        tb.addSeparator()
        add("Esporta .tex", self._export_tex, "file")
        add("Compila PDF", self._compile_pdf, "wrench")
        add("Apri in TeXstudio", self._open_texstudio, "book-open")
        add("Apri PDF", self._open_pdf, "eye")

        # menu export (Markdown / EPUB) + versioni
        exp_btn = tool_button("Esporta", "upload")
        xmenu = QMenu(exp_btn)
        xmenu.addAction(icon("note"), "Markdown (.md)", self._export_markdown)
        xmenu.addAction(icon("book-open"), "EPUB (.epub)", self._export_epub)
        exp_btn.setMenu(xmenu)
        tb.addWidget(exp_btn)
        add("Versioni", self._open_versions, "clock")

    def _left_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lbl = QLabel("CAPITOLI"); lbl.setObjectName("SectionLabel")
        lay.addWidget(lbl)
        self.chapter_list = QListWidget()
        self.chapter_list.currentRowChanged.connect(self._on_chapter_selected)
        lay.addWidget(self.chapter_list)

        row = QHBoxLayout()
        b_add = QPushButton(icon("plus"), ""); b_add.setToolTip("Aggiungi capitolo")
        b_add.clicked.connect(self._add_chapter)
        b_up = QPushButton(icon("chevron-up"), ""); b_up.setToolTip("Sposta su")
        b_up.clicked.connect(lambda: self._move(-1))
        b_dn = QPushButton(icon("chevron-down"), ""); b_dn.setToolTip("Sposta giù")
        b_dn.clicked.connect(lambda: self._move(1))
        b_del = QPushButton(icon("trash"), ""); b_del.setObjectName("Danger")
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

        # evidenziazione sintassi LaTeX sulla scheda 3
        from .latex_highlighter import attach_latex_highlighter
        self._latex_hl = attach_latex_highlighter(self.latex_edit)

        # scrittura assistita dall'AI sul testo e sul LaTeX (tasto destro → 🤖 AI)
        from .ai_menu import AiEditingController
        self._ai_text = AiEditingController(
            self.text_edit, get_engine=lambda: self.engine,
            get_book=lambda: self.book,
            get_base_dir=lambda: self.project.folder,
            get_image_config=self._image_config, parent=self)
        self._ai_latex = AiEditingController(
            self.latex_edit, get_engine=lambda: self.engine,
            get_book=lambda: self.book,
            get_base_dir=lambda: self.project.folder,
            get_image_config=self._image_config, parent=self)

        # riassunto
        self.summary_edit = QPlainTextEdit()
        self.tabs.addTab(self.summary_edit, "4 · Riassunto")

        # intermezzo: testo interstiziale reso DOPO il capitolo
        self.intermezzo_edit = QPlainTextEdit()
        self.intermezzo_edit.setPlaceholderText(
            "Intermezzo (opzionale): breve testo interstiziale reso DOPO questo "
            "capitolo, in corsivo e centrato. Utile per stacchi, citazioni o respiri "
            "tra un capitolo e il successivo.")
        self.tabs.addTab(self.intermezzo_edit, "5 · Intermezzo")

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
        self.m_abstract = QPlainTextEdit(); self.m_abstract.setMaximumHeight(80)
        self.m_premise = QPlainTextEdit(); self.m_premise.setMaximumHeight(70)
        self.m_preface = QPlainTextEdit(); self.m_preface.setMaximumHeight(70)
        self.m_prologue = QPlainTextEdit(); self.m_prologue.setMaximumHeight(70)
        self.m_epilogue = QPlainTextEdit(); self.m_epilogue.setMaximumHeight(70)
        self.m_back = QPlainTextEdit(); self.m_back.setMaximumHeight(70)
        # metadati editoriali (usati dal layout "editoriale")
        self.m_subtitle_b = QLineEdit()
        self.m_subtitle_b.setPlaceholderText("Seconda riga di sottotitolo (frontespizio editoriale)")
        self.m_publisher = QLineEdit()
        self.m_isbn = QLineEdit()
        self.m_price = QLineEdit(); self.m_price.setPlaceholderText("es. 18,00")
        self.m_back_quote = QPlainTextEdit(); self.m_back_quote.setMaximumHeight(50)
        self.m_back_quote_author = QLineEdit()
        self.m_back_blurb = QPlainTextEdit(); self.m_back_blurb.setMaximumHeight(70)
        self.m_back_blurb.setPlaceholderText("Descrizione di quarta (layout editoriale; vuoto = usa l'abstract)")
        # copertina: percorso immagine + selettore file
        self.m_cover = QLineEdit()
        self.m_cover.setPlaceholderText("images/copertina.png (relativo al progetto)")
        cover_browse = QPushButton("Sfoglia…"); cover_browse.clicked.connect(self._choose_cover_image)
        cover_row = QHBoxLayout(); cover_row.addWidget(self.m_cover); cover_row.addWidget(cover_browse)
        cover_wrap = QWidget(); cover_wrap.setLayout(cover_row)
        mform.addRow("Titolo", self.m_title)
        mform.addRow("Sottotitolo", self.m_subtitle)
        mform.addRow("Autore", self.m_author)
        mform.addRow("Anno", self.m_year)
        mform.addRow("Argomento", self.m_topic)
        mform.addRow("Abstract", self.m_abstract)
        mform.addRow("Copertina (img)", cover_wrap)
        mform.addRow("Premessa", self.m_premise)
        mform.addRow("Prefazione", self.m_preface)
        mform.addRow("Prologo", self.m_prologue)
        mform.addRow("Epilogo", self.m_epilogue)
        mform.addRow("Quarta cop. (classico)", self.m_back)
        # --- sezione metadati editoriali ---
        mform.addRow("Sottotitolo 2", self.m_subtitle_b)
        mform.addRow("Editore", self.m_publisher)
        mform.addRow("ISBN", self.m_isbn)
        mform.addRow("Prezzo", self.m_price)
        mform.addRow("Citazione quarta", self.m_back_quote)
        mform.addRow("Autore citazione", self.m_back_quote_author)
        mform.addRow("Descr. quarta (editoriale)", self.m_back_blurb)
        tabs.addTab(meta, "Libro")

        # --- stile ---
        style = QWidget(); sform = QFormLayout(style)
        self.s_tone = QLineEdit(); self.s_audience = QLineEdit()
        self.s_language = QLineEdit(); self.s_person = QLineEdit()
        self.s_extra = QPlainTextEdit(); self.s_extra.setMaximumHeight(80)
        self.s_mode = QComboBox(); self.s_mode.addItems(["mentore", "bilanciata", "autopilota"])
        self.s_mode.setToolTip(
            "mentore: l'AI dà feedback, scrivi tu · bilanciata: generi con conferma · "
            "autopilota: autogenerazione rapida mantenendo lo stile del prompt")
        self.s_class = QComboBox(); self.s_class.addItems(["book", "report", "article"])
        self.s_font = QComboBox(); self.s_font.addItems(["10pt", "11pt", "12pt"])
        self.s_paper = QComboBox(); self.s_paper.addItems(["a4paper", "a5paper", "letterpaper"])
        self.s_layout = QComboBox(); self.s_layout.addItems(["classico", "editoriale"])
        self.s_layout.setToolTip(
            "classico: copertina semplice · editoriale: frontespizio a tutta pagina, "
            "pagina di copyright e quarta professionale (richiede tikz/eso-pic e un'immagine di copertina)")
        sform.addRow("Tono", self.s_tone)
        sform.addRow("Pubblico", self.s_audience)
        sform.addRow("Lingua", self.s_language)
        sform.addRow("Persona", self.s_person)
        sform.addRow("Istruzioni extra", self.s_extra)
        sform.addRow("Modalità di lavoro", self.s_mode)
        sform.addRow("Classe doc.", self.s_class)
        sform.addRow("Corpo", self.s_font)
        sform.addRow("Formato", self.s_paper)
        sform.addRow("Impaginazione", self.s_layout)

        self.s_prompt = QPlainTextEdit()
        self.s_prompt.setPlaceholderText(
            "Prompt di stile personalizzato (opzionale).\n"
            "Se compilato, sostituisce il system prompt del Writer: i campi qui sopra "
            "(Tono, Pubblico, Lingua, Persona, Istruzioni extra) verranno ignorati.\n"
            "Puoi incollarlo a mano oppure caricarlo da un file con il pulsante qui sotto."
        )
        self.s_prompt.setMinimumHeight(160)
        sform.addRow("Prompt stile", self.s_prompt)
        prow = QHBoxLayout()
        b_load = QPushButton("Carica da file…"); b_load.clicked.connect(self._load_style_prompt)
        b_clear = QPushButton("Pulisci"); b_clear.clicked.connect(lambda: self.s_prompt.setPlainText(""))
        prow.addWidget(b_load); prow.addWidget(b_clear); prow.addStretch(1)
        pwrap = QWidget(); pwrap.setLayout(prow)
        sform.addRow("", pwrap)

        tabs.addTab(style, "Stile")

        # --- motore AI ---
        eng = QWidget(); self.e_form = eform = QFormLayout(eng)
        self.e_provider = QComboBox()
        for p in PROVIDERS:
            self.e_provider.addItem(PROVIDER_LABELS.get(p, p), p)
        # modello: selettore chiaro con nomi leggibili e voce «Altro» (ModelSelector)
        self.e_model = ModelSelector()
        self.e_provider.currentIndexChanged.connect(
            lambda *_: self._on_engine_provider_changed(self.e_provider.currentData()))
        idx = self.e_provider.findData(self.engine_config.provider)
        if idx >= 0:
            self.e_provider.setCurrentIndex(idx)
        self._reload_engine_models(self.engine_config.provider, self.engine_config.model)
        # endpoint per i motori locali (Ollama/LM Studio)
        self.e_base_url = QLineEdit(
            self.engine_config.base_url or default_base_url(self.engine_config.provider))
        self.e_base_url.setPlaceholderText("http://localhost:11434/v1")
        self.e_key = QLineEdit(self.engine_config.api_key)
        self.e_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_key.setPlaceholderText("Lascia vuoto per modalità offline (test)")
        apply_btn = QPushButton("Applica motore"); apply_btn.clicked.connect(self._apply_engine)
        eform.addRow("Provider", self.e_provider)
        eform.addRow("Modello", self.e_model)
        eform.addRow("Endpoint locale", self.e_base_url)
        eform.addRow("API key", self.e_key)
        eform.addRow(apply_btn)
        self.e_status = QLabel(""); self.e_status.setObjectName("Subtitle")
        self.e_status.setWordWrap(True)
        eform.addRow(self.e_status)
        self._update_engine_provider_rows(self.engine_config.provider)
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
            self.intermezzo_edit.setPlainText(ch.intermezzo)

    def _commit_current_editors(self):
        ch = self._current_chapter()
        if not ch:
            return
        ch.title = self.ch_title.text().strip() or ch.title
        ch.raw_concepts = self.concepts_edit.toPlainText()
        ch.text = self.text_edit.toPlainText()
        ch.latex = self.latex_edit.toPlainText()
        ch.summary = self.summary_edit.toPlainText()
        ch.intermezzo = self.intermezzo_edit.toPlainText()

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
        self.m_cover.setText(b.cover_image)
        self.m_premise.setPlainText(b.premise)
        self.m_preface.setPlainText(b.preface)
        self.m_prologue.setPlainText(b.prologue)
        self.m_epilogue.setPlainText(b.epilogue)
        self.m_back.setPlainText(b.back_cover)
        self.m_subtitle_b.setText(b.subtitle_b)
        self.m_publisher.setText(b.publisher); self.m_isbn.setText(b.isbn)
        self.m_price.setText(b.price)
        self.m_back_quote.setPlainText(b.back_quote)
        self.m_back_quote_author.setText(b.back_quote_author)
        self.m_back_blurb.setPlainText(b.back_blurb)
        self.s_tone.setText(s.tone); self.s_audience.setText(s.audience)
        self.s_language.setText(s.language); self.s_person.setText(s.person)
        self.s_extra.setPlainText(s.extra_instructions)
        self.s_prompt.setPlainText(s.style_prompt)
        self.s_mode.setCurrentText(s.mode or "mentore")
        self.s_class.setCurrentText(s.document_class)
        self.s_font.setCurrentText(s.font_size); self.s_paper.setCurrentText(s.paper)
        self.s_layout.setCurrentText(s.layout or "classico")

    def _commit_book_meta(self):
        b = self.book; s = b.style
        b.title = self.m_title.text().strip() or b.title
        b.subtitle = self.m_subtitle.text(); b.author = self.m_author.text().strip()
        b.year = self.m_year.text().strip(); b.topic = self.m_topic.text().strip()
        b.abstract = self.m_abstract.toPlainText(); b.preface = self.m_preface.toPlainText()
        b.cover_image = self.m_cover.text().strip()
        b.premise = self.m_premise.toPlainText()
        b.prologue = self.m_prologue.toPlainText()
        b.epilogue = self.m_epilogue.toPlainText()
        b.back_cover = self.m_back.toPlainText()
        b.subtitle_b = self.m_subtitle_b.text()
        b.publisher = self.m_publisher.text().strip(); b.isbn = self.m_isbn.text().strip()
        b.price = self.m_price.text().strip()
        b.back_quote = self.m_back_quote.toPlainText()
        b.back_quote_author = self.m_back_quote_author.text().strip()
        b.back_blurb = self.m_back_blurb.toPlainText()
        s.tone = self.s_tone.text(); s.audience = self.s_audience.text()
        s.language = self.s_language.text(); s.person = self.s_person.text()
        s.extra_instructions = self.s_extra.toPlainText()
        s.style_prompt = self.s_prompt.toPlainText()
        s.mode = self.s_mode.currentText()
        s.document_class = self.s_class.currentText()
        s.font_size = self.s_font.currentText(); s.paper = self.s_paper.currentText()
        s.layout = self.s_layout.currentText()
        self.setWindowTitle(f"BookForge — {b.title}")
        self.statusBar().showMessage("Dati libro/stile applicati.", 3000)

    def _load_style_prompt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Carica prompt di stile", "",
            "Testo (*.txt *.md *.prompt);;Tutti i file (*)")
        if not path:
            return
        try:
            content = open(path, "r", encoding="utf-8").read()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore caricamento", str(e))
            return
        self.s_prompt.setPlainText(content)
        self.statusBar().showMessage(f"Prompt di stile caricato da {path}", 4000)

    # ============================================================ sezioni speciali / copertina
    def _image_config(self):
        """Config per la generazione immagini: chiave Google dalle Impostazioni
        (o dalle variabili d'ambiente come fallback)."""
        from ..core.image_gen import ImageGenConfig
        cfg = ImageGenConfig.from_env()
        key = self.app_settings.api_key_for("google") or cfg.api_key
        if key:
            cfg.api_key = key
        return cfg

    def _gen_section(self, kind: str):
        """Genera con l'AI una sezione speciale (premessa/prologo/epilogo/quarta)."""
        self._commit_book_meta()
        targets = {"premessa": self.m_premise, "prologo": self.m_prologue,
                   "epilogo": self.m_epilogue, "quarta": self.m_back}
        labels = {"premessa": "Premessa", "prologo": "Prologo",
                  "epilogo": "Epilogo / fine libro", "quarta": "Quarta di copertina"}
        w = targets[kind]

        def accept(text):
            w.setPlainText(text)
            self._commit_book_meta()

        self._run_chapter_ai(labels[kind],
                             lambda: self.engine.book_section(self.book, kind),
                             accept, original=w.toPlainText())

    def _choose_cover_image(self):
        """Seleziona un'immagine di copertina; se è fuori dal progetto la copia in images/."""
        import shutil
        path, _ = QFileDialog.getOpenFileName(
            self, "Scegli immagine di copertina", str(self.project.folder),
            "Immagini (*.png *.jpg *.jpeg *.pdf);;Tutti i file (*)")
        if not path:
            return
        src = Path(path)
        try:
            rel = src.resolve().relative_to(self.project.folder.resolve())
            self.m_cover.setText(str(rel).replace("\\", "/"))
        except ValueError:
            images = self.project.folder / "images"
            images.mkdir(parents=True, exist_ok=True)
            dst = images / src.name
            try:
                shutil.copyfile(src, dst)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Copertina", f"Impossibile copiare l'immagine:\n{e}")
                return
            self.m_cover.setText(f"images/{src.name}")
        self._commit_book_meta()

    def _gen_cover_image(self):
        """Genera con l'AI un'immagine di copertina e la salva in images/copertina.png."""
        self._commit_book_meta()
        from ..core import image_gen
        cfg = self._image_config()
        ok, msg = image_gen.image_available(cfg)
        if not ok:
            QMessageBox.warning(self, "Copertina", msg)
            return
        desc, ok = QInputDialog.getMultiLineText(
            self, "Immagine di copertina", "Descrivi la copertina da generare:",
            self.book.topic or self.book.title)
        if not ok or not desc.strip():
            return
        out = self.project.folder / "images" / "copertina.png"
        from .ai_worker import AiWorker
        busy = QProgressDialog("Genero la copertina…", None, 0, 0, self)
        busy.setWindowTitle("AI"); busy.setCancelButton(None)
        busy.setMinimumDuration(0); busy.show()

        def fn():
            prompt = self.engine.image_prompt(desc, self.book)
            image_gen.generate_image(prompt, out, cfg)
            return str(out)

        def done(_res):
            busy.close()
            self.m_cover.setText("images/copertina.png")
            self._commit_book_meta()
            QMessageBox.information(self, "Copertina", f"Immagine salvata in:\n{out}")

        def fail(err):
            busy.close()
            QMessageBox.critical(self, "Copertina", err)

        self._cover_worker = AiWorker(fn)
        self._cover_worker.done.connect(done)
        self._cover_worker.failed.connect(fail)
        self._cover_worker.start()

    def _reload_engine_models(self, provider: str, selected: str = ""):
        """Popola il selettore dei modelli del pannello «Motore» per il provider."""
        self.e_model.set_provider(provider, selected)

    def _on_engine_provider_changed(self, provider: str):
        self._reload_engine_models(provider)
        self._update_engine_provider_rows(provider)

    def _update_engine_provider_rows(self, provider: str):
        """Mostra l'endpoint per i motori locali e la chiave per quelli cloud."""
        local = is_local(provider)
        if local and not self.e_base_url.text().strip():
            self.e_base_url.setText(default_base_url(provider))
        self.e_form.setRowVisible(self.e_base_url, local)
        self.e_form.setRowVisible(self.e_key, not local)

    def _apply_engine(self):
        provider = self.e_provider.currentData()
        model = self.e_model.current_model()
        key = self.e_key.text().strip()
        base_url = self.e_base_url.text().strip()
        local = is_local(provider)
        # mantiene i parametri di campionamento dalle impostazioni globali
        self.engine_config = EngineConfig(
            provider=provider, model=model, api_key=key, base_url=base_url,
            temperature=self.app_settings.temperature,
            max_tokens=self.app_settings.max_tokens,
        )
        self.engine, self.engine_real, msg = build_engine(self.engine_config)
        self.e_status.setText(msg)
        self.statusBar().showMessage(msg, 5000)
        # persiste la scelta così resta valida al prossimo avvio
        self.app_settings.provider = provider
        self.app_settings.model = model
        if key:
            self.app_settings.set_api_key(provider, key)
        if local:
            self.app_settings.set_base_url(provider, base_url)
        try:
            self.app_settings.save()
        except Exception:  # noqa: BLE001 - non bloccante
            pass
        # per i motori locali non serve una chiave: l'avviso «offline» non si applica
        if not local:
            self._warn_if_offline(key)

    def _warn_if_offline(self, key: str):
        """Se è stata fornita una chiave ma il motore reale non parte, spiega perché.

        Evita il malinteso «ho impostato un LLM ma le funzioni restano simulate»:
        il fallback offline ora è esplicito invece di passare inosservato.
        """
        if key and not self.engine_real:
            QMessageBox.warning(
                self, "Modello non attivo",
                "È stata impostata una chiave API ma il modello reale non è stato "
                "attivato: le funzioni AI useranno il motore offline (testo simulato).\n\n"
                f"Dettaglio: {self.e_status.text()}\n\n"
                "Verifica che il client del provider sia installato "
                "(es. datapizza-ai-clients-…) e che chiave/modello siano corretti.")

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
        self.stop_btn.setEnabled(True)
        self.worker = GenerateWorker(self.engine, self.book, ch)
        self.worker.progress.connect(self.progress_label.setText)
        self.worker.finished_ok.connect(self._on_generated)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.start()

    def _stop_generation(self):
        """Richiede l'interruzione cooperativa della generazione in corso."""
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.progress_label.setText("Interruzione in corso…")
            self.stop_btn.setEnabled(False)

    def _on_cancelled(self):
        self.progress.hide()
        self.stop_btn.setEnabled(False)
        self.progress_label.setText("Generazione interrotta.")
        self._on_chapter_selected(self.chapter_list.currentRow())
        self._refresh_chapter_list()
        self._save(silent=True)

    def _on_generated(self, ch: Chapter):
        self.progress.hide()
        self.stop_btn.setEnabled(False)
        self.progress_label.setText("Capitolo generato ✓")
        self._on_chapter_selected(self.chapter_list.currentRow())
        self._refresh_chapter_list()
        self.tabs.setCurrentIndex(1)
        self._save(silent=True)

    def _on_failed(self, err: str):
        self.progress.hide()
        self.stop_btn.setEnabled(False)
        self.progress_label.setText("")
        QMessageBox.critical(self, "Errore generazione", err)

    # ============================================================ comandi AI capitolo
    def _run_chapter_ai(self, label, fn, on_accept, original=""):
        """Esegue una funzione AI off-thread, mostra l'anteprima e applica se accettata."""
        from .ai_worker import AiWorker
        from .ai_preview import AiPreviewDialog
        if getattr(self, "_chap_worker", None) and self._chap_worker.isRunning():
            return
        busy = QProgressDialog(label, None, 0, 0, self)
        busy.setWindowTitle("AI"); busy.setCancelButton(None)
        busy.setMinimumDuration(0); busy.show()

        def done(result):
            busy.close()
            text = str(result).strip()
            if not text:
                QMessageBox.information(self, label, "Nessun risultato.")
                return
            dlg = AiPreviewDialog(self, f"AI — {label}", original=original, proposed=text)
            dlg.exec()
            if dlg.action == "accept":
                on_accept(dlg.result_text)
            elif dlg.action == "regenerate":
                self._run_chapter_ai(label, fn, on_accept, original)

        def fail(err):
            busy.close()
            QMessageBox.critical(self, "Errore AI", err)

        self._chap_worker = AiWorker(fn)
        self._chap_worker.done.connect(done)
        self._chap_worker.failed.connect(fail)
        self._chap_worker.start()

    def _chapter_outline(self):
        self._commit_current_editors()
        ch = self._current_chapter()
        if not ch:
            return
        def accept(text):
            self.concepts_edit.setPlainText(text)
            self.tabs.setCurrentIndex(0)
        self._run_chapter_ai("Scaletta",
                             lambda: self.engine.outline(self.book, ch),
                             accept, original=ch.raw_concepts)

    def _chapter_transitions(self):
        self._commit_current_editors()
        ch = self._current_chapter()
        if not ch:
            return
        if not ch.text.strip():
            QMessageBox.information(self, "Raccordi",
                                   "Genera prima il testo del capitolo.")
            return
        def accept(text):
            self.text_edit.setPlainText(text)
            self.tabs.setCurrentIndex(1)
        self._run_chapter_ai("Raccordi",
                             lambda: self.engine.transitions(self.book, ch.text),
                             accept, original=ch.text)

    def _chapter_bridge(self, where: str):
        self._commit_current_editors()
        ch = self._current_chapter()
        if not ch:
            return
        prev, nxt = self.book.neighbors(ch.id)
        if (where == "prev" and prev is None) or (where == "next" and nxt is None):
            QMessageBox.information(self, "Ponte",
                                   "Non c'è un capitolo " +
                                   ("precedente." if where == "prev" else "successivo."))
            return
        def accept(text):
            cur = self.text_edit.toPlainText()
            self.text_edit.setPlainText(
                (text + "\n\n" + cur) if where == "prev" else (cur + "\n\n" + text))
            self.tabs.setCurrentIndex(1)
        self._run_chapter_ai("Ponte",
                             lambda: self.engine.bridge(self.book, ch, where), accept)

    def _chapter_resummarize(self):
        self._commit_current_editors()
        ch = self._current_chapter()
        if not ch:
            return
        if not ch.text.strip():
            QMessageBox.information(self, "Riassunto",
                                   "Genera prima il testo del capitolo.")
            return
        def accept(text):
            self.summary_edit.setPlainText(text)
            self.tabs.setCurrentIndex(3)
        self._run_chapter_ai("Riassunto",
                             lambda: self.engine.summarize(ch.text),
                             accept, original=ch.summary)

    # ============================================================ autogenerazione (autopilota)
    def _autogen_current(self):
        if self.worker and self.worker.isRunning():
            return
        self._commit_current_editors(); self._commit_book_meta()
        ch = self._current_chapter()
        if not ch:
            QMessageBox.information(self, "Autogenera", "Aggiungi prima un capitolo.")
            return
        self._start_autogen(chapter=ch)

    def _autogen_all(self, only_empty: bool):
        if self.worker and self.worker.isRunning():
            return
        self._commit_current_editors(); self._commit_book_meta()
        if not self.book.chapters:
            QMessageBox.information(self, "Autogenera", "Aggiungi prima dei capitoli.")
            return
        n = sum(1 for c in self.book.chapters if (not only_empty or not c.text.strip()))
        if n == 0:
            QMessageBox.information(self, "Autogenera", "Nessun capitolo da generare.")
            return
        msg = (f"Autogenerare {n} capitoli vuoti?" if only_empty
               else f"Rigenerare TUTTI i {n} capitoli? Il testo esistente sarà sostituito.")
        if QMessageBox.question(self, "Autogenera", msg) != QMessageBox.StandardButton.Yes:
            return
        # sicurezza: salva una versione prima di una generazione massiva
        try:
            from ..core import versioning
            versioning.save_version(self.project.folder, self.book, "pre-autogenera")
        except Exception:  # noqa: BLE001
            pass
        self._start_autogen(chapter=None, only_empty=only_empty)

    def _start_autogen(self, chapter, only_empty: bool = True):
        from .autogen_worker import AutogenWorker
        self.progress.show()
        self.progress_label.setText("Autopilota in corso…")
        self.stop_btn.setEnabled(True)
        self.worker = AutogenWorker(self.engine, self.book, chapter, only_empty)
        self.worker.progress.connect(self.progress_label.setText)
        self.worker.finished_ok.connect(self._on_autogen_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.start()

    def _on_autogen_done(self, n: int):
        self.progress.hide()
        self.stop_btn.setEnabled(False)
        self.progress_label.setText(f"Autogenerati {n} capitolo/i ✓")
        self._on_chapter_selected(self.chapter_list.currentRow())
        self._refresh_chapter_list()
        self.tabs.setCurrentIndex(1)
        self._save(silent=True)

    # ============================================================ export / versioni
    def _export_markdown(self):
        self._save(silent=True)
        from ..core import export
        path = self.project.folder / (self._safe_stem() + ".md")
        export.write_markdown(self.book, path)
        self.statusBar().showMessage(f"Markdown esportato: {path}", 5000)
        QMessageBox.information(self, "Esportato", f"Markdown salvato in:\n{path}")

    def _export_epub(self):
        self._save(silent=True)
        from ..core import export
        path = self.project.folder / (self._safe_stem() + ".epub")
        try:
            export.build_epub(self.book, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "EPUB", f"Esportazione fallita:\n{e}")
            return
        self.statusBar().showMessage(f"EPUB esportato: {path}", 5000)
        QMessageBox.information(self, "Esportato", f"EPUB salvato in:\n{path}")

    def _safe_stem(self) -> str:
        import re
        s = re.sub(r"[^A-Za-z0-9_-]+", "_", self.book.title).strip("_")
        return s or "libro"

    def _open_versions(self):
        self._save(silent=True)
        from .versions_dialog import VersionsDialog

        def restore(book):
            self.project.book = book
            self.book = book
            self._refresh_chapter_list()
            self._load_book_meta()
            if self.book.chapters:
                self.chapter_list.setCurrentRow(0)
            self._save(silent=True)

        VersionsDialog(self, self.project, on_restore=restore).exec()

    # ============================================================ mentore/crescita/rigore
    def _open_mentor(self):
        self._commit_current_editors()
        ch = self._current_chapter()
        if not ch:
            return
        from .mentor_dialog import MentorDialog
        from ..core import analysis
        # la revisione lavora sul risultato finale: il LaTeX scritto se presente,
        # altrimenti la prosa generata (vedi analysis.readable_text)
        MentorDialog(self, self.engine, self.book,
                     analysis.readable_text(ch.text, ch.latex)).exec()

    def _open_metrics(self):
        self._commit_current_editors()
        from .metrics_dialog import MetricsDialog
        MetricsDialog(self, self.project).exec()

    def _open_argument_map(self):
        self._commit_current_editors()
        ch = self._current_chapter()
        if not ch:
            return
        from .argument_dialog import ArgumentMapDialog

        def export(concepts):
            self.concepts_edit.setPlainText(concepts)
            self.tabs.setCurrentIndex(0)

        ArgumentMapDialog(self, self.engine, self.book, ch,
                          on_export_concepts=export).exec()

    def _open_biblio(self):
        from .biblio_dialog import BiblioDialog

        def insert_cite(cmd):
            w = self.latex_edit
            cur = w.textCursor(); cur.insertText(cmd); w.setTextCursor(cur)
            self.tabs.setCurrentIndex(2)

        BiblioDialog(self, self.project.folder, on_insert_cite=insert_cite).exec()

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
        pdf = self.project.folder / (self.project.tex_path.stem + ".pdf")
        if not pdf.exists():
            QMessageBox.information(self, "PDF",
                                   "PDF non ancora generato. Compila prima il documento.")
            return
        from .pdf_view import show_pdf
        if show_pdf(self, pdf):
            return
        ok, msg = compiler.open_pdf(self.project)   # fallback: app di sistema
        if not ok:
            QMessageBox.warning(self, "PDF", msg)

    def _open_docx_formatter(self):
        from .docx_dialog import DocxFormatDialog
        dlg = DocxFormatDialog(self, engine=self.engine, engine_real=self.engine_real)
        dlg.exec()

    def _open_word_pdf(self):
        from .word_pdf_dialog import WordToPdfDialog
        dlg = WordToPdfDialog(self, engine=self.engine, engine_real=self.engine_real)
        dlg.exec()

    # ============================================================ progetto
    def _rebuild_project_menu(self):
        """Ricostruisce il menu «Progetto»: apri, recenti, chiudi."""
        m = self.project_menu
        m.clear()
        m.addAction(icon("folder-open"), "Apri progetto…", self._open_project)

        # sottomenu dei recenti: sempre presente (così è scopribile), ma
        # disabilitato quando non c'è altro progetto recente oltre a quello aperto
        recents = [p for p in self.app_settings.clean_recent_projects()
                   if str(p) != str(self.project.folder.resolve())]
        sub = m.addMenu(icon("clock"), "Progetti recenti")
        if recents:
            for path in recents:
                name = Path(path).name
                act = sub.addAction(icon("book-open"), name,
                                    lambda _=False, fp=str(path): self._open_recent_project(fp))
                act.setToolTip(str(path))
        else:
            sub.setEnabled(False)
        m.addSeparator()
        m.addAction(icon("x"), "Chiudi progetto", self._close_project)

    def _open_project(self):
        d = QFileDialog.getExistingDirectory(self, "Apri cartella progetto")
        if not d:
            return
        if not Project.is_project(d):
            QMessageBox.warning(self, "Non valido",
                                "La cartella selezionata non contiene un progetto BookForge.")
            return
        try:
            project = Project.load(d)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Impossibile aprire il progetto:\n{e}")
            return
        self._switch_to_project(project)

    def _open_recent_project(self, folder: str):
        if not Project.is_project(folder):
            QMessageBox.warning(self, "Non disponibile",
                                "Il progetto non esiste più o è stato spostato.")
            return
        try:
            project = Project.load(folder)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Impossibile aprire il progetto:\n{e}")
            return
        self._switch_to_project(project)

    def _switch_to_project(self, project: Project):
        """Salva il progetto corrente e apre quello indicato in una nuova finestra."""
        self._save(silent=True)
        win = MainWindow(project)
        win.show()
        self.close()

    def _close_project(self):
        """Chiude il progetto e torna alla schermata iniziale."""
        self._save(silent=True)
        from .startup import StartupDialog
        from .launcher import window_for_startup
        dlg = StartupDialog(self)
        if dlg.exec() != StartupDialog.DialogCode.Accepted:
            return  # l'utente ha annullato: resta sul progetto corrente
        win = window_for_startup(dlg)
        if win is not None:
            win.show()
            self.close()

    # ============================================================ strumenti
    def _convert_latex_project(self):
        """Importa una cartella LaTeX esistente come nuovo progetto BookForge."""
        from ..core.latex_import import convert_latex_to_project   # import pigro
        src = QFileDialog.getExistingDirectory(
            self, "Scegli la cartella del progetto LaTeX da convertire")
        if not src:
            return
        dest = QFileDialog.getExistingDirectory(
            self, "Scegli dove salvare il nuovo progetto BookForge")
        if not dest:
            return
        try:
            project = convert_latex_to_project(src, dest)
        except FileNotFoundError as e:
            QMessageBox.warning(self, "Nessun LaTeX", str(e))
            return
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Conversione fallita", str(e))
            return
        n = len(project.book.chapters)
        if QMessageBox.question(
                self, "Progetto creato",
                f"Convertiti {n} capitoli in:\n{project.folder}\n\n"
                "Aprire ora il nuovo progetto BookForge?") == \
                QMessageBox.StandardButton.Yes:
            self._win = MainWindow(project)
            self._win.show()

    def _open_settings(self):
        from .settings_dialog import SettingsDialog
        dlg = SettingsDialog(self, settings=self.app_settings)
        if dlg.exec() != SettingsDialog.DialogCode.Accepted:
            return
        self.app_settings = dlg.settings
        self.engine_config = EngineConfig.from_settings(self.app_settings)
        self.engine, self.engine_real, msg = build_engine(self.engine_config)
        # tiene allineata la scheda «Motore» del pannello destro
        idx = self.e_provider.findData(self.engine_config.provider)
        if idx >= 0:
            self.e_provider.setCurrentIndex(idx)
        self._reload_engine_models(self.engine_config.provider, self.engine_config.model)
        self.e_key.setText(self.engine_config.api_key)
        self.e_base_url.setText(self.engine_config.base_url
                                or default_base_url(self.engine_config.provider))
        self._update_engine_provider_rows(self.engine_config.provider)
        self.e_status.setText(msg)
        self.statusBar().showMessage(msg, 5000)
        if not self.engine_config.is_local:
            self._warn_if_offline(self.engine_config.api_key)

    def _open_about(self):
        from .about_dialog import AboutDialog
        AboutDialog(self).exec()

    def closeEvent(self, event):
        self._save(silent=True)
        event.accept()
