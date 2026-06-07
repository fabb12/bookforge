"""Finestra per sfogliare e modificare i file di un progetto LaTeX.

Pensata per aprire una cartella *qualsiasi* che contiene un libro/saggio in LaTeX
(non serve un progetto BookForge con book.json): mostra l'albero dei file a
sinistra, apre il file selezionato in un editor a destra e permette di salvarlo,
compilarlo e aprirlo in TeXstudio. Da qui è anche raggiungibile «Sistema Word».
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

try:  # in Qt6 QFileSystemModel vive in QtGui, ma teniamo un fallback
    from PyQt6.QtGui import QFileSystemModel
except ImportError:  # pragma: no cover - dipende dalla build di PyQt6
    from PyQt6.QtWidgets import QFileSystemModel

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView,
    QPlainTextEdit, QPushButton, QLabel, QMessageBox, QFileDialog,
)

from ..core import compiler


# Estensioni che apriamo come testo nell'editor interno.
_TEXT_SUFFIXES = {
    ".tex", ".txt", ".bib", ".cls", ".sty", ".md", ".log", ".toc", ".idx",
    ".aux", ".out", ".bbl", ".blg", ".cfg", ".json", ".csv", ".bat", ".ist",
    ".gls", ".nlo", ".tikz", ".sub", ".def", ".clo", ".krc", ".ini", ".yml",
    ".yaml", ".xml", ".html",
}
# Estensioni che, se aperte, deleghiamo all'applicazione di sistema.
_OPEN_EXTERNAL_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
                          ".tiff", ".svg", ".eps", ".docx", ".doc", ".odt"}


class LatexBrowserWindow(QMainWindow):
    """Browser/editor di file per una cartella LaTeX."""

    def __init__(self, folder: str | Path, engine=None, engine_real: bool = False):
        super().__init__()
        self.folder = Path(folder)
        self.engine = engine
        self.engine_real = engine_real
        self.current_path: Path | None = None
        self._dirty = False

        self.setWindowTitle(f"BookForge — File LaTeX: {self.folder}")
        self.resize(1120, 740)
        self._build_ui()
        self.statusBar().showMessage(f"Cartella: {self.folder}")

    # --------------------------------------------------------------- UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        # --- albero dei file ---
        self.model = QFileSystemModel()
        self.model.setRootPath(str(self.folder))
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(self.folder)))
        self.tree.setHeaderHidden(True)
        for col in (1, 2, 3):  # nascondi dimensione/tipo/data: lasciamo solo il nome
            self.tree.hideColumn(col)
        self.tree.setAnimated(True)
        self.tree.clicked.connect(self._on_tree_clicked)
        self.tree.doubleClicked.connect(self._on_tree_double_clicked)
        splitter.addWidget(self.tree)

        # --- editor ---
        right = QWidget()
        rlay = QVBoxLayout(right)
        self.path_label = QLabel("Seleziona un file dall'albero a sinistra.")
        self.path_label.setObjectName("Subtitle")
        self.path_label.setWordWrap(True)
        rlay.addWidget(self.path_label)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("monospace", 11))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setPlaceholderText(
            "Apri un file di testo (es. .tex) dall'albero per modificarlo qui.\n"
            "Inserisci i tuoi punti/sezioni e premi «Salva».\n"
            "Tasto destro → 🤖 AI per riscrivere, generare diagrammi o immagini.")
        self.editor.setEnabled(False)
        self.editor.textChanged.connect(self._on_text_changed)
        rlay.addWidget(self.editor)
        splitter.addWidget(right)

        # menu contestuale di scrittura assistita
        from .ai_menu import AiEditingController
        self._ai = AiEditingController(
            self.editor,
            get_engine=lambda: self.engine,
            get_base_dir=self._image_base_dir,
            parent=self,
        )

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 800])

        self._build_toolbar()

    def _build_toolbar(self):
        tb = self.addToolBar("Azioni")
        tb.setMovable(False)

        def add(text, slot, primary=False):
            b = QPushButton(text)
            if primary:
                b.setObjectName("Primary")
            b.clicked.connect(slot)
            tb.addWidget(b)
            return b

        add("💾 Salva", self._save, primary=True)
        tb.addSeparator()
        add("🛠 Compila PDF", self._compile_pdf)
        add("📖 Apri in TeXstudio", self._open_texstudio)
        add("👁 Apri PDF", self._open_pdf)
        tb.addSeparator()
        add("📝 Sistema Word", self._open_docx_formatter)
        add("📂 Cambia cartella", self._change_folder)

    def _image_base_dir(self) -> Path | None:
        """Cartella rispetto a cui risolvere immagini/diagrammi: quella del .tex aperto."""
        if self.current_path is not None:
            return self.current_path.parent
        return self.folder

    # --------------------------------------------------------------- file tree
    def _path_for_index(self, index) -> Path | None:
        if not index.isValid():
            return None
        return Path(self.model.filePath(index))

    def _on_tree_clicked(self, index):
        path = self._path_for_index(index)
        if path and path.is_file():
            self._open_file(path)

    def _on_tree_double_clicked(self, index):
        path = self._path_for_index(index)
        if path and path.is_file() and path.suffix.lower() in _OPEN_EXTERNAL_SUFFIXES:
            self._open_external(path)

    def _open_file(self, path: Path):
        if path == self.current_path:
            return
        if not self._maybe_save_current():
            return
        suffix = path.suffix.lower()
        if suffix in _OPEN_EXTERNAL_SUFFIXES:
            self._open_external(path)
            return
        if suffix and suffix not in _TEXT_SUFFIXES:
            # file non riconosciuto come testo: prova comunque, ma avvisa se binario
            if not self._looks_like_text(path):
                self.path_label.setText(
                    f"{path.name} — file non testuale: usa doppio clic per aprirlo "
                    "con l'applicazione di sistema.")
                return
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore apertura", str(e))
            return
        self.editor.blockSignals(True)
        self.editor.setPlainText(content)
        self.editor.blockSignals(False)
        self.editor.setEnabled(True)
        self.current_path = path
        self._dirty = False
        self._update_title()

    @staticmethod
    def _looks_like_text(path: Path) -> bool:
        try:
            chunk = path.read_bytes()[:2048]
        except Exception:  # noqa: BLE001
            return False
        if b"\x00" in chunk:
            return False
        return True

    def _open_external(self, path: Path):
        ok, msg = compiler.open_pdf_path(path) if path.suffix.lower() == ".pdf" \
            else self._open_with_system(path)
        if not ok:
            QMessageBox.warning(self, "Apertura", msg)
        else:
            self.statusBar().showMessage(msg, 4000)

    @staticmethod
    def _open_with_system(path: Path) -> tuple[bool, str]:
        import sys, subprocess
        try:
            if sys.platform.startswith("darwin"):
                subprocess.Popen(["open", str(path)])
            elif sys.platform.startswith("win"):
                import os
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
            return True, f"Aperto: {path}"
        except Exception as e:  # noqa: BLE001
            return False, f"Impossibile aprire: {e}"

    # --------------------------------------------------------------- editor
    def _on_text_changed(self):
        if self.current_path is not None:
            self._dirty = True
            self._update_title()

    def _update_title(self):
        if self.current_path is None:
            self.path_label.setText("Seleziona un file dall'albero a sinistra.")
            return
        mark = " •" if self._dirty else ""
        self.path_label.setText(f"{self.current_path}{mark}")

    def _maybe_save_current(self) -> bool:
        """Chiede se salvare le modifiche correnti. Ritorna False se annullato."""
        if not self._dirty or self.current_path is None:
            return True
        resp = QMessageBox.question(
            self, "Modifiche non salvate",
            f"Salvare le modifiche a «{self.current_path.name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel)
        if resp == QMessageBox.StandardButton.Cancel:
            return False
        if resp == QMessageBox.StandardButton.Yes:
            return self._save()
        return True

    def _save(self) -> bool:
        if self.current_path is None:
            return True
        try:
            self.current_path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore salvataggio", str(e))
            return False
        self._dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Salvato: {self.current_path}", 4000)
        return True

    # --------------------------------------------------------------- azioni LaTeX
    def _tex_to_build(self) -> Path | None:
        """Il .tex da compilare: quello aperto se è un .tex, altrimenti il principale."""
        if self.current_path and self.current_path.suffix.lower() == ".tex":
            return self.current_path
        return compiler.find_main_tex(self.folder)

    def _compile_pdf(self):
        self._save()
        tex = self._tex_to_build()
        if not tex:
            QMessageBox.information(
                self, "Nessun .tex",
                "Non ho trovato un file .tex da compilare in questa cartella.")
            return
        self.statusBar().showMessage(f"Compilo {tex.name}…")
        ok, log = compiler.compile_tex(tex)
        if ok:
            self.statusBar().showMessage("PDF compilato.", 4000)
            QMessageBox.information(self, "Compilazione", log[:1500])
        else:
            QMessageBox.warning(self, "Compilazione", log[:3000])

    def _open_texstudio(self):
        self._save()
        tex = self._tex_to_build()
        if not tex:
            QMessageBox.information(
                self, "Nessun .tex",
                "Non ho trovato un file .tex da aprire in questa cartella.")
            return
        ok, msg = compiler.open_tex_in_texstudio(tex)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "TeXstudio", msg)

    def _open_pdf(self):
        tex = self._tex_to_build()
        candidates = []
        if tex:
            candidates.append(tex.with_suffix(".pdf"))
        candidates.extend(sorted(self.folder.glob("*.pdf")))
        for pdf in candidates:
            if pdf.exists():
                ok, msg = compiler.open_pdf_path(pdf)
                if not ok:
                    QMessageBox.warning(self, "PDF", msg)
                return
        QMessageBox.information(self, "PDF",
                                "Nessun PDF trovato. Compila prima il documento.")

    def _open_docx_formatter(self):
        from .docx_dialog import DocxFormatDialog
        dlg = DocxFormatDialog(self, engine=self.engine, engine_real=self.engine_real)
        dlg.exec()

    def _change_folder(self):
        if not self._maybe_save_current():
            return
        d = QFileDialog.getExistingDirectory(self, "Apri cartella LaTeX",
                                             str(self.folder))
        if not d:
            return
        self.folder = Path(d)
        self.model.setRootPath(str(self.folder))
        self.tree.setRootIndex(self.model.index(str(self.folder)))
        self.current_path = None
        self._dirty = False
        self.editor.blockSignals(True)
        self.editor.clear()
        self.editor.blockSignals(False)
        self.editor.setEnabled(False)
        self.setWindowTitle(f"BookForge — File LaTeX: {self.folder}")
        self.statusBar().showMessage(f"Cartella: {self.folder}")
        self._update_title()

    # --------------------------------------------------------------- chiusura
    def closeEvent(self, event):
        if self._maybe_save_current():
            event.accept()
        else:
            event.ignore()
