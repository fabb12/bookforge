"""Assemblaggio del file LaTeX completo del libro a partire dal modello dati."""
from __future__ import annotations

from .model import Book

# Caratteri che vanno protetti quando inseriamo testo "grezzo" (titoli, autore...)
_LATEX_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def escape_latex(s: str) -> str:
    if not s:
        return ""
    out = []
    for ch in s:
        out.append(_LATEX_SPECIAL.get(ch, ch))
    return "".join(out)


PREAMBLE = r"""\documentclass[%(font_size)s,%(paper)s]{%(doc_class)s}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[%(babel)s]{babel}
\IfFileExists{lmodern.sty}{\usepackage{lmodern}}{}
\IfFileExists{microtype.sty}{\usepackage{microtype}}{}
\usepackage{geometry}
\geometry{margin=2.5cm}
\usepackage{graphicx}
\usepackage{titlesec}
\usepackage{fancyhdr}
\IfFileExists{emptypage.sty}{\usepackage{emptypage}}{}
\usepackage{setspace}
\onehalfspacing
\usepackage[hidelinks]{hyperref}

\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE,RO]{\thepage}
\fancyhead[RE]{\leftmark}
\fancyhead[LO]{\rightmark}
\renewcommand{\headrulewidth}{0.4pt}

\title{%(title)s}
\author{%(author)s}
\date{%(year)s}
"""

COVER = r"""\begin{titlepage}
    \centering
    \vspace*{3cm}
    {\Huge\bfseries %(title)s\par}
    \vspace{1cm}
    %(subtitle_block)s
    \vspace{2cm}
    {\Large %(author)s\par}
    \vfill
    {\large %(year)s\par}
\end{titlepage}
"""


def _babel(lang: str) -> str:
    lang = (lang or "").lower()
    if "ital" in lang:
        return "italian"
    if "engl" in lang or "ingl" in lang:
        return "english"
    if "fran" in lang or "franc" in lang:
        return "french"
    if "spagn" in lang or "span" in lang:
        return "spanish"
    return "italian"


def build_latex(book: Book) -> str:
    style = book.style
    parts: list[str] = []

    parts.append(PREAMBLE % {
        "font_size": style.font_size,
        "paper": style.paper,
        "doc_class": style.document_class,
        "babel": _babel(style.language),
        "title": escape_latex(book.title),
        "author": escape_latex(book.author),
        "year": escape_latex(book.year),
    })

    parts.append(r"\begin{document}")

    # --- COPERTINA ---
    subtitle_block = (r"{\Large\itshape %s\par}" % escape_latex(book.subtitle)
                      if book.subtitle else "")
    parts.append(COVER % {
        "title": escape_latex(book.title),
        "subtitle_block": subtitle_block,
        "author": escape_latex(book.author),
        "year": escape_latex(book.year),
    })

    parts.append(r"\frontmatter" if style.document_class == "book" else "")

    # --- PREFAZIONE ---
    preface = book.preface.strip() or (
        escape_latex(book.abstract) if book.abstract else "")
    if preface:
        parts.append(r"\chapter*{Prefazione}")
        parts.append(r"\addcontentsline{toc}{chapter}{Prefazione}")
        parts.append(preface)
        parts.append("")

    # --- INDICE ---
    parts.append(r"\tableofcontents")
    parts.append(r"\clearpage")

    parts.append(r"\mainmatter" if style.document_class == "book" else "")

    # --- CAPITOLI ---
    for ch in book.chapters:
        parts.append(r"\chapter{%s}" % escape_latex(ch.title))
        body = ch.latex.strip() or ch.text.strip()
        if not body:
            body = r"%% (capitolo ancora vuoto)"
        parts.append(body)
        parts.append("")

    # --- FINE / QUARTA DI COPERTINA ---
    parts.append(r"\backmatter" if style.document_class == "book" else "")
    if book.back_cover.strip():
        parts.append(r"\clearpage")
        parts.append(r"\thispagestyle{empty}")
        parts.append(r"\vspace*{\fill}")
        parts.append(r"\begin{center}")
        parts.append(book.back_cover.strip())
        parts.append(r"\end{center}")
        parts.append(r"\vspace*{\fill}")

    parts.append(r"\end{document}")
    return "\n".join(p for p in parts if p is not None)
