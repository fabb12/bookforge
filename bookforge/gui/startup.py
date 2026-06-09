"""Dialog iniziale: scelta tra modalità Crea libro e Modifica libro."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFileDialog, QFormLayout, QGroupBox, QMessageBox, QWidget, QMenu,
)

from ..core.model import Project, Book
from ..core.settings import AppSettings
from .icons import icon, app_icon


class StartupDialog(QDialog):
    """Restituisce un Project tramite self.project dopo accept()."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BookForge — Avvio")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(560)
        self.project: Project | None = None
        self.settings = AppSettings.load()

        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(28, 28, 28, 28)

        title = QLabel("BookForge")
        title.setObjectName("Title")
        sub = QLabel("Scrittura e manutenzione di libri assistita da agenti AI")
        sub.setObjectName("Subtitle")
        root.addWidget(title)
        root.addWidget(sub)

        recent = self._recent_box()
        if recent is not None:
            root.addWidget(recent)
        root.addWidget(self._create_box())
        root.addWidget(self._open_box())
        root.addWidget(self._tools_box())

        # firma: sviluppato da FFA
        foot = QLabel("Sviluppato da FFA")
        foot.setObjectName("Subtitle")
        foot.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(foot)

    # ---------------- PROGETTI RECENTI ----------------
    def _recent_box(self) -> QWidget | None:
        """Elenco cliccabile dei progetti aperti di recente (None se vuoto)."""
        recents = self.settings.clean_recent_projects()
        if not recents:
            return None
        box = QGroupBox("Progetti recenti")
        lay = QVBoxLayout(box)
        for path in recents:
            p = Path(path)
            btn = QPushButton(icon("book-open"), f"  {p.name}")
            btn.setToolTip(str(p))
            btn.clicked.connect(lambda _=False, fp=str(p): self._open_recent(fp))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn, fp=str(p), parent=box: self._show_recent_menu(pos, b, fp, parent)
            )
            lay.addWidget(btn)
        return box

    def _show_recent_menu(self, pos, btn, folder: str, parent_box):
        menu = QMenu(self)
        remove_action = menu.addAction(icon("trash"), "Rimuovi dai recenti")
        action = menu.exec(btn.mapToGlobal(pos))
        if action == remove_action:
            self._remove_recent(folder, btn, parent_box)

    def _remove_recent(self, folder: str, btn, parent_box):
        if folder in self.settings.recent_projects:
            self.settings.recent_projects.remove(folder)
            self.settings.save()

        parent_box.layout().removeWidget(btn)
        btn.deleteLater()

        if parent_box.layout().count() == 0:
            parent_box.hide()

    def _open_recent(self, folder: str):
        if not Project.is_project(folder):
            QMessageBox.warning(self, "Non disponibile",
                                "Il progetto non esiste più o è stato spostato.")
            return
        try:
            self.project = Project.load(folder)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Impossibile aprire il progetto:\n{e}")
            return
        self.accept()

    # ---------------- CREA ----------------
    def _create_box(self) -> QWidget:
        box = QGroupBox("Crea un nuovo libro")
        lay = QFormLayout(box)
        self.new_title = QLineEdit("Il mio libro")
        self.new_author = QLineEdit("Autore")
        self.new_topic = QLineEdit()
        self.new_topic.setPlaceholderText("Argomento generale del libro/saggio")
        self.new_folder = QLineEdit()
        self.new_folder.setPlaceholderText("Cartella di destinazione del progetto")
        pick = QPushButton("Sfoglia…")
        pick.clicked.connect(self._pick_new_folder)
        folder_row = QHBoxLayout()
        fw = QWidget(); fw.setLayout(folder_row)
        folder_row.setContentsMargins(0, 0, 0, 0)
        folder_row.addWidget(self.new_folder)
        folder_row.addWidget(pick)

        lay.addRow("Titolo", self.new_title)
        lay.addRow("Autore", self.new_author)
        lay.addRow("Argomento", self.new_topic)
        lay.addRow("Cartella", fw)

        btn = QPushButton("Crea libro")
        btn.setObjectName("Primary")
        btn.clicked.connect(self._do_create)
        lay.addRow(btn)
        return box

    def _pick_new_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Scegli cartella progetto")
        if d:
            self.new_folder.setText(d)

    def _do_create(self):
        folder = self.new_folder.text().strip()
        if not folder:
            QMessageBox.warning(self, "Attenzione", "Seleziona una cartella di destinazione.")
            return
        path = Path(folder)
        # se la cartella scelta non contiene già un progetto, creiamo una sottocartella col titolo
        safe = "".join(c for c in self.new_title.text() if c.isalnum() or c in " -_").strip()
        target = path if not any(path.iterdir()) else path / (safe or "nuovo_libro") \
            if path.exists() else path
        book = Book(title=self.new_title.text().strip() or "Titolo del libro",
                    author=self.new_author.text().strip() or "Autore",
                    topic=self.new_topic.text().strip())
        book.add_chapter("Capitolo 1")
        proj = Project(target, book)
        try:
            proj.save()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Impossibile creare il progetto:\n{e}")
            return
        self.project = proj
        self.accept()

    # ---------------- APRI ----------------
    def _open_box(self) -> QWidget:
        box = QGroupBox("Modifica un libro esistente")
        lay = QVBoxLayout(box)
        info = QLabel("Apri la cartella di un progetto BookForge (contiene book.json).")
        info.setObjectName("Subtitle")
        lay.addWidget(info)
        btn = QPushButton("Apri progetto…")
        btn.clicked.connect(self._do_open)
        lay.addWidget(btn)
        return box

    def _do_open(self):
        d = QFileDialog.getExistingDirectory(self, "Apri cartella progetto")
        if not d:
            return
        if not Project.is_project(d):
            QMessageBox.warning(self, "Non valido",
                                "La cartella selezionata non contiene un progetto BookForge.")
            return
        try:
            self.project = Project.load(d)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Impossibile aprire il progetto:\n{e}")
            return
        self.accept()

    # ---------------- STRUMENTI (senza aprire un progetto) ----------------
    def _tools_box(self) -> QWidget:
        box = QGroupBox("Strumenti")
        lay = QVBoxLayout(box)
        info = QLabel("Converti un progetto LaTeX esistente, sistema un documento "
                      "Word o gestisci le API dei modelli — senza aprire un progetto.")
        info.setObjectName("Subtitle"); info.setWordWrap(True)
        lay.addWidget(info)

        b_latex = QPushButton(icon("download"), " Converti progetto LaTeX in progetto BookForge…")
        b_latex.clicked.connect(self._do_convert_latex)
        lay.addWidget(b_latex)

        b_word_pdf = QPushButton(icon("note"), " Sistema Word → LaTeX → PDF…")
        b_word_pdf.clicked.connect(self._do_word_pdf)
        lay.addWidget(b_word_pdf)

        b_word = QPushButton(icon("file-text"), " Formatta documento Word (.docx)…")
        b_word.clicked.connect(self._do_word_tool)
        lay.addWidget(b_word)

        b_settings = QPushButton(icon("settings"), " Impostazioni — API e modelli LLM…")
        b_settings.clicked.connect(self._do_settings)
        lay.addWidget(b_settings)
        return box

    def _build_engine(self):
        """Costruisce il motore dalle impostazioni persistenti (per i tool senza progetto)."""
        from ..agents.engine import EngineConfig, build_engine
        from ..core.settings import AppSettings
        return build_engine(EngineConfig.from_settings(AppSettings.load()))

    def _do_convert_latex(self):
        # converte una cartella LaTeX e apre subito il nuovo progetto BookForge
        from ..core.latex_import import convert_latex_to_project
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
        QMessageBox.information(
            self, "Progetto creato",
            f"Convertiti {n} capitoli in:\n{project.folder}")
        self.project = project
        self.accept()

    def _do_word_pdf(self):
        from .word_pdf_dialog import WordToPdfDialog
        engine, engine_real, _ = self._build_engine()
        WordToPdfDialog(self, engine=engine, engine_real=engine_real).exec()

    def _do_settings(self):
        from .settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

    def _do_word_tool(self):
        # apre il formattatore Word come dialog modale, senza chiudere l'avvio
        from .docx_dialog import DocxFormatDialog
        engine, engine_real, _ = self._build_engine()
        dlg = DocxFormatDialog(self, engine=engine, engine_real=engine_real)
        dlg.exec()
