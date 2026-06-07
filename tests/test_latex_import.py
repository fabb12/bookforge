"""Test dell'importazione di progetti LaTeX in un modello Book."""
from pathlib import Path

from bookforge.core.model import Book, Project
from bookforge.core.latex_builder import build_latex
from bookforge.core.latex_import import (
    latex_to_book, import_latex_project, convert_latex_to_project,
)


def _sample_book() -> Book:
    b = Book(title="Il mio saggio", author="Mario Rossi", year="2021")
    b.style.document_class = "book"
    b.style.font_size = "12pt"
    b.style.paper = "a4paper"
    ch1 = b.add_chapter("Le origini")
    ch1.latex = "Questo è il corpo del primo capitolo."
    ch2 = b.add_chapter("Gli sviluppi")
    ch2.latex = "Corpo del secondo capitolo con \\emph{enfasi}."
    return b


def test_roundtrip_metadati_e_capitoli():
    src = build_latex(_sample_book())
    book = latex_to_book(src)
    assert book.title == "Il mio saggio"
    assert book.author == "Mario Rossi"
    assert book.year == "2021"
    assert book.style.document_class == "book"
    assert book.style.font_size == "12pt"
    assert [c.title for c in book.chapters] == ["Le origini", "Gli sviluppi"]
    assert "primo capitolo" in book.chapters[0].latex
    assert "secondo capitolo" in book.chapters[1].latex


def test_prefazione_da_chapter_stellato():
    src = r"""
\documentclass{book}
\begin{document}
\chapter*{Prefazione}
Una breve nota di apertura.
\chapter{Primo}
Corpo del primo.
\end{document}
"""
    book = latex_to_book(src)
    assert "nota di apertura" in book.preface
    assert [c.title for c in book.chapters] == ["Primo"]


def test_fallback_a_section_quando_mancano_i_chapter():
    src = r"""
\documentclass{article}
\begin{document}
\section{Alpha}
Testo alpha.
\section{Beta}
Testo beta.
\end{document}
"""
    book = latex_to_book(src)
    assert [c.title for c in book.chapters] == ["Alpha", "Beta"]


def test_commenti_ignorati():
    src = r"""
\documentclass{book}
\begin{document}
% \chapter{Falso capitolo in commento}
\chapter{Vero}
Corpo.
\end{document}
"""
    book = latex_to_book(src)
    assert [c.title for c in book.chapters] == ["Vero"]


def test_import_da_cartella_con_input(tmp_path: Path):
    (tmp_path / "cap1.tex").write_text(
        "\\chapter{Incluso}\nCorpo incluso.", encoding="utf-8")
    (tmp_path / "main.tex").write_text(
        "\\documentclass{book}\n\\title{Da File}\n\\begin{document}\n"
        "\\input{cap1}\n\\end{document}\n", encoding="utf-8")
    book = import_latex_project(tmp_path)
    assert book.title == "Da File"
    assert [c.title for c in book.chapters] == ["Incluso"]
    assert "Corpo incluso" in book.chapters[0].latex


def test_convert_latex_to_project(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.tex").write_text(
        "\\documentclass{book}\n\\title{Convertito}\n\\begin{document}\n"
        "\\chapter{Uno}\nCorpo.\n\\end{document}\n", encoding="utf-8")
    dest = tmp_path / "dest"
    project = convert_latex_to_project(src, dest)
    assert Project.is_project(project.folder)
    reopened = Project.load(project.folder)
    assert reopened.book.title == "Convertito"
    assert [c.title for c in reopened.book.chapters] == ["Uno"]
