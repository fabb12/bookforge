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
    %(cover_image_block)s
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

# =============================================================================
# Layout "editoriale": impaginazione professionale (frontespizio a tutta pagina,
# pagina di copyright, quarta strutturata). Pacchetti, colori e macro dei
# metadati vengono aggiunti al preambolo solo quando questo layout è attivo.
# =============================================================================
EDITORIAL_PREAMBLE = r"""
%% --- Layout editoriale: pacchetti, colori e macro dei metadati ---
\usepackage{tikz}
\usepackage{eso-pic}
\usepackage{xcolor}
\definecolor{modernblack}{HTML}{0E0E12}
%% \textls (letterspacing) arriva da microtype; fallback inerte se assente.
\providecommand{\textls}[2][]{#2}
\newcommand{\booktitle}{%(title)s}
\newcommand{\subtitleA}{%(subtitle_a)s}
\newcommand{\subtitleB}{%(subtitle_b)s}
\newcommand{\authorname}{%(author)s}
\newcommand{\publisher}{%(publisher)s}
\newcommand{\isbn}{%(isbn)s}
\newcommand{\editionyear}{%(year)s}
"""

# Frontespizio: sfondo a tutta pagina + titolo/sottotitoli/autore in riquadro
# semi-trasparente e «chip» editore in basso. %(cover)s = percorso immagine,
# %(sub_sep)s = separatore tra le due righe di sottotitolo (vuoto se manca la 2ª).
EDITORIAL_TITLEPAGE = r"""\begin{titlepage}
    \thispagestyle{empty}
    \AddToShipoutPictureBG*{%%
        \AtPageLowerLeft{\IfFileExists{%(cover)s}{%%
            \includegraphics[width=\paperwidth,height=\paperheight]{%(cover)s}}{}}%%
    }
    \begin{tikzpicture}[remember picture,overlay]
        \node[
            anchor=north, align=center, yshift=-2.0cm,
            text=white, text opacity=1,
            fill=black, fill opacity=.30,
            rounded corners=10pt, inner xsep=18pt, inner ysep=14pt,
            text width=.82\paperwidth
        ] at (current page.north) {%%
            {\fontsize{34}{40}\selectfont\sffamily\bfseries\textls[100]{\MakeUppercase{\booktitle}}\par}
            \vspace{0.8em}
            {\normalsize\sffamily\itshape \subtitleA%(sub_sep)s\subtitleB\par}
            \vspace{0.9em}
            {\large\sffamily\textls[80]{\MakeUppercase{\authorname}}}
        };
        \node[
            anchor=south, fill=black, text=white,
            rounded corners=6pt, inner xsep=10pt, inner ysep=6pt
        ] at ([yshift=6mm]current page.south) {\large\sffamily\textls[50]{\MakeUppercase{\publisher}}};
    \end{tikzpicture}
\end{titlepage}
"""

# Pagina di copyright: testo legale + ISBN/editore/edizione, pilotati dalle macro.
EDITORIAL_COPYRIGHT = r"""\thispagestyle{empty}
\vspace*{\fill}

\noindent
Copyright \copyright\ \editionyear\ \authorname

\vspace{0.5em}
\noindent
Tutti i diritti riservati. Nessuna parte di questa pubblicazione può essere riprodotta,
memorizzata in sistemi di recupero o trasmessa in qualsiasi forma o con qualsiasi mezzo,
elettronico, meccanico, fotocopie, registrazioni o altro, senza il previo consenso
scritto dell'editore.

\vspace{1em}
\noindent
Prima edizione: \editionyear

\vspace{1em}
\noindent
ISBN: \isbn

\vspace{1em}
\noindent
Pubblicato da:\\
\publisher

\vspace{1em}
\noindent
\small
L'editore è a disposizione degli aventi diritto con i quali non è stato possibile
comunicare, nonché per eventuali omissioni o inesattezze nelle citazioni delle fonti.
\clearpage
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


def _starred_section(title: str, body: str) -> list[str]:
    """Blocco di una sezione non numerata (premessa, prologo, epilogo…) con voce nell'indice."""
    return [
        r"\chapter*{%s}" % escape_latex(title),
        r"\addcontentsline{toc}{chapter}{%s}" % escape_latex(title),
        body.strip(),
        "",
    ]


def _cover_image_block(book: Book) -> str:
    """Snippet \\includegraphics per l'immagine di copertina, se impostata."""
    path = (book.cover_image or "").strip().replace("\\", "/")
    if not path:
        return ""
    # \IfFileExists così un percorso errato non fa fallire la compilazione
    inc = (r"\includegraphics[width=\textwidth,height=0.45\textheight,"
           r"keepaspectratio]{%s}\par\vspace{1cm}" % path)
    return r"\IfFileExists{%s}{%s}{}" % (path, inc)


def _is_editorial(book: Book) -> bool:
    """True se il libro usa il layout editoriale (impaginazione professionale)."""
    return (book.style.layout or "").strip().lower().startswith("editor")


def _editorial_preamble(book: Book) -> str:
    """Pacchetti, colore e macro dei metadati per il layout editoriale."""
    return EDITORIAL_PREAMBLE % {
        "title": escape_latex(book.title),
        "subtitle_a": escape_latex(book.subtitle),
        "subtitle_b": escape_latex(book.subtitle_b),
        "author": escape_latex(book.author),
        "publisher": escape_latex(book.publisher or "Editore"),
        "isbn": escape_latex(book.isbn or "—"),
        "year": escape_latex(book.year),
    }


def _editorial_titlepage(book: Book) -> str:
    """Frontespizio editoriale; usa l'immagine di copertina se presente."""
    cover = (book.cover_image or "cover.png").strip().replace("\\", "/")
    # separatore tra le due righe di sottotitolo: solo se la seconda esiste
    sub_sep = r"\\[0.8em]" if book.subtitle_b.strip() else ""
    return EDITORIAL_TITLEPAGE % {"cover": cover, "sub_sep": sub_sep}


def _editorial_back_cover(book: Book) -> str:
    """Quarta di copertina editoriale (sfondo scuro, citazione, descrizione, ISBN, prezzo)."""
    blurb = (book.back_blurb.strip() or book.abstract.strip())
    nodes: list[str] = [
        r"\pagestyle{empty}",
        r"\cleardoublepage",
        r"\begin{tikzpicture}[remember picture,overlay]",
        r"  \fill[modernblack] (current page.south west) rectangle (current page.north east);",
    ]
    # ancoraggio della descrizione: sotto la citazione se c'è, altrimenti dal bordo
    blurb_anchor = r"([yshift=-1.5cm] current page.north)"
    if book.back_quote.strip():
        author = (r"\\[0.5em]{\sffamily\normalsize\textls[50]{%s}}"
                  % escape_latex(book.back_quote_author).upper()
                  if book.back_quote_author.strip() else "")
        nodes.append(
            r"  \node[name=topquote, anchor=north, text width=0.8\textwidth, align=center]"
            r" at ([yshift=-1.5cm] current page.north) {%%"
            "\n    \\color{white}{\\sffamily\\Large\\textit{``%s''}}%s};"
            % (escape_latex(book.back_quote), author))
        blurb_anchor = r"([yshift=-0.8cm] topquote.south)"
    if blurb:
        nodes.append(
            r"  \node[anchor=north, text width=0.8\textwidth, align=justify] at %s {%%"
            "\n    \\sffamily\\small\\color{white}\\setlength{\\parskip}{0.8em}\n    %s};"
            % (blurb_anchor, escape_latex(blurb)))
    if book.isbn.strip():
        nodes.append(
            r"  \node[fill=white, minimum width=1.5in, minimum height=0.8in, anchor=south east]"
            r" at ([xshift=-1cm, yshift=1cm] current page.south east) {%"
            "\n    \\color{modernblack}\\tiny ISBN \\isbn};")
    if book.price.strip():
        nodes.append(
            r"  \node[white, anchor=south west] at ([xshift=1cm, yshift=1.2cm] current page.south west)"
            r" {{\sffamily\small %s}};" % escape_latex(book.price))
    if book.topic.strip():
        nodes.append(
            r"  \node[white, rotate=90, anchor=south] at ([xshift=-0.5cm] current page.west)"
            r" {{\sffamily\tiny\textls[100]{%s}}};" % escape_latex(book.topic).upper())
    nodes.append(r"\end{tikzpicture}")
    return "\n".join(nodes)


def build_latex(book: Book, bib_database: str | None = None) -> str:
    """Assembla il .tex del libro.

    `bib_database` è il nome (senza estensione) del file BibTeX del progetto
    (tipicamente «references»): se passato, in fondo al libro vengono emessi
    `\\bibliographystyle`/`\\bibliography` perché BibTeX possa generare la
    bibliografia. Senza file .bib non si emette nulla, così la compilazione non
    fallisce per un database mancante.
    """
    style = book.style
    editorial = _is_editorial(book)
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

    if editorial:
        parts.append(_editorial_preamble(book))

    parts.append(r"\begin{document}")

    # --- COPERTINA / FRONTESPIZIO ---
    if editorial:
        parts.append(_editorial_titlepage(book))
        parts.append(EDITORIAL_COPYRIGHT)
    else:
        subtitle_block = (r"{\Large\itshape %s\par}" % escape_latex(book.subtitle)
                          if book.subtitle else "")
        parts.append(COVER % {
            "title": escape_latex(book.title),
            "subtitle_block": subtitle_block,
            "author": escape_latex(book.author),
            "year": escape_latex(book.year),
            "cover_image_block": _cover_image_block(book),
        })

    parts.append(r"\frontmatter" if style.document_class == "book" else "")

    # --- PREMESSA ---
    if book.premise.strip():
        parts += _starred_section("Premessa", book.premise)

    # --- PREFAZIONE ---
    preface = book.preface.strip() or (
        escape_latex(book.abstract) if book.abstract else "")
    if preface:
        parts += _starred_section("Prefazione", preface)

    # --- PROLOGO ---
    if book.prologue.strip():
        parts += _starred_section("Prologo", book.prologue)

    # --- INDICE ---
    parts.append(r"\tableofcontents")
    parts.append(r"\clearpage")

    parts.append(r"\mainmatter" if style.document_class == "book" else "")

    # --- CAPITOLI (con eventuale intermezzo dopo ciascuno) ---
    for ch in book.chapters:
        parts.append(r"\chapter{%s}" % escape_latex(ch.title))
        body = ch.latex.strip() or ch.text.strip()
        if not body:
            body = r"%% (capitolo ancora vuoto)"
        parts.append(body)
        parts.append("")
        if ch.intermezzo.strip():
            parts.append(r"\bigskip")
            parts.append(r"\begin{center}\itshape")
            parts.append(ch.intermezzo.strip())
            parts.append(r"\end{center}")
            parts.append(r"\bigskip")
            parts.append("")

    # --- FINE LIBRO / QUARTA DI COPERTINA ---
    parts.append(r"\backmatter" if style.document_class == "book" else "")

    # --- EPILOGO (fine libro) ---
    if book.epilogue.strip():
        parts += _starred_section("Epilogo", book.epilogue)

    # --- BIBLIOGRAFIA (BibTeX) ---
    if bib_database:
        parts.append(r"\bibliographystyle{%s}" % (style.bib_style or "plain"))
        parts.append(r"\bibliography{%s}" % bib_database)
        parts.append("")

    if editorial:
        parts.append(_editorial_back_cover(book))
    elif book.back_cover.strip():
        parts.append(r"\clearpage")
        parts.append(r"\thispagestyle{empty}")
        parts.append(r"\vspace*{\fill}")
        parts.append(r"\begin{center}")
        parts.append(book.back_cover.strip())
        parts.append(r"\end{center}")
        parts.append(r"\vspace*{\fill}")

    parts.append(r"\end{document}")
    return "\n".join(p for p in parts if p is not None)
