"""Importazione di un progetto LaTeX esistente in un modello `Book` di BookForge.

Puro e deterministico: nessuna rete, nessun PyQt. Legge i sorgenti `.tex`
(risolvendo gli `\\input`/`\\include`), ne estrae i metadati dal preambolo e
divide il corpo in capitoli, così l'autore ottiene subito un progetto BookForge
già pronto da modificare. Il corpo LaTeX di ogni capitolo finisce in
`Chapter.latex` (che `build_latex` riusa direttamente).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .model import Book, Project

# parole che, in un capitolo *stellato*, indicano materiale di apertura (prefazione)
_PREFACE_HINTS = ("prefaz", "preface", "premessa", "avvertenz")

# estensioni di file che consideriamo «immagini» (per includegraphics e copia asset)
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".pdf", ".eps", ".gif",
               ".bmp", ".tif", ".tiff", ".svg")
# riferimenti a immagini nel sorgente LaTeX
_GRAPHICS_RE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")


# --------------------------------------------------------------------- utilità
def _strip_comments(source: str) -> str:
    """Rimuove i commenti LaTeX (% non preceduto da backslash) riga per riga."""
    return re.sub(r"(?<!\\)%.*", "", source)


def _braced_arg(source: str, brace_index: int) -> tuple[str, int]:
    """Legge l'argomento `{...}` che inizia a `brace_index`, gestendo le graffe annidate.

    Restituisce (contenuto_senza_graffe_esterne, indice_dopo_la_chiusura).
    """
    depth = 0
    for i in range(brace_index, len(source)):
        c = source[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return source[brace_index + 1:i], i + 1
    return source[brace_index + 1:], len(source)


def _command_arg(source: str, command: str) -> str | None:
    """Restituisce l'argomento del primo `\\command{...}`, o None se assente."""
    m = re.search(r"\\" + command + r"\s*\{", source)
    if not m:
        return None
    content, _ = _braced_arg(source, m.end() - 1)
    return content.strip()


def _clean_title(title: str) -> str:
    """Ripulisce un titolo dal markup tipografico più comune (\\\\, \\LARGE, ...)."""
    title = re.sub(r"\\\\", " ", title)
    title = re.sub(r"\\[A-Za-z]+\b", "", title)   # comandi senza argomento
    title = re.sub(r"[{}]", "", title)
    return re.sub(r"\s+", " ", title).strip()


# --------------------------------------------------------------------- risoluzione file
def _inline_inputs(source: str, base: Path, depth: int = 0) -> str:
    """Sostituisce `\\input{f}`/`\\include{f}` con il contenuto del file, ricorsivamente."""
    if depth > 8:
        return source

    def repl(m: re.Match) -> str:
        name = m.group(1).strip()
        candidate = base / name
        if candidate.suffix.lower() != ".tex":
            candidate = candidate.with_suffix(".tex") if candidate.suffix == "" \
                else base / (name + ".tex")
        if not candidate.exists():
            candidate = base / (name + ".tex")
        if candidate.exists():
            try:
                inner = candidate.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001 - file illeggibile: lascia un segnaposto
                return f"% [bookforge] impossibile leggere {name}"
            return _inline_inputs(inner, candidate.parent, depth + 1)
        return f"% [bookforge] file non trovato: {name}"

    return re.sub(r"\\(?:input|include)\s*\{([^}]+)\}", repl, source)


# --------------------------------------------------------------------- metadati
def _detect_doc_class(preamble: str) -> tuple[str, str, str]:
    """Da `\\documentclass[opts]{class}` ricava (classe, corpo, formato)."""
    doc_class, font_size, paper = "book", "11pt", "a4paper"
    m = re.search(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}", preamble)
    if m:
        opts = [o.strip() for o in (m.group(1) or "").split(",") if o.strip()]
        cls = m.group(2).strip()
        if cls in ("book", "report", "article"):
            doc_class = cls
        for o in opts:
            if re.fullmatch(r"\d+pt", o):
                font_size = o
            elif o in ("a4paper", "a5paper", "letterpaper"):
                paper = o
    return doc_class, font_size, paper


def _detect_language(preamble: str) -> str:
    """Mappa l'opzione di babel sulla lingua di prodotto (testo umano)."""
    m = re.search(r"\\usepackage\s*\[([^\]]*)\]\s*\{babel\}", preamble)
    code = ""
    if m:
        opts = [o.strip().lower() for o in m.group(1).split(",") if o.strip()]
        code = opts[-1] if opts else ""
    mapping = {"italian": "italiano", "english": "inglese",
               "french": "francese", "spanish": "spagnolo", "german": "tedesco"}
    return mapping.get(code, "italiano")


# --------------------------------------------------------------------- corpo → capitoli
def _split_document(source: str) -> tuple[str, str]:
    """Separa preambolo e corpo attorno a `\\begin{document}`/`\\end{document}`."""
    begin = re.search(r"\\begin\s*\{document\}", source)
    if not begin:
        return source, source
    preamble = source[:begin.start()]
    body = source[begin.end():]
    end = re.search(r"\\end\s*\{document\}", body)
    if end:
        body = body[:end.start()]
    return preamble, body


def _abstract_block(body: str) -> str:
    """Estrae il testo di un eventuale ambiente abstract (usato come prefazione)."""
    m = re.search(r"\\begin\s*\{abstract\}(.*?)\\end\s*\{abstract\}", body, re.DOTALL)
    return m.group(1).strip() if m else ""


def _chapter_units(body: str) -> list[tuple[int, int, str, bool]]:
    """Trova i punti di taglio del corpo: preferisce `\\chapter`, altrimenti `\\section`.

    Ogni voce è (inizio_comando, inizio_corpo, titolo, stellato).
    """
    for unit in ("chapter", "section"):
        pattern = re.compile(r"\\" + unit + r"(\*)?\s*(?:\[[^\]]*\])?\s*\{")
        units: list[tuple[int, int, str, bool]] = []
        for m in pattern.finditer(body):
            title, title_end = _braced_arg(body, m.end() - 1)
            units.append((m.start(), title_end, _clean_title(title), bool(m.group(1))))
        if units:
            return units
    return []


def latex_to_book(source: str) -> Book:
    """Converte un sorgente LaTeX (già con gli `\\input` risolti) in un `Book`."""
    source = _strip_comments(source)
    preamble, body = _split_document(source)

    book = Book()
    doc_class, font_size, paper = _detect_doc_class(preamble)
    book.style.document_class = doc_class
    book.style.font_size = font_size
    book.style.paper = paper
    book.style.language = _detect_language(preamble)

    title = _command_arg(preamble, "title")
    if title:
        book.title = _clean_title(title)
    author = _command_arg(preamble, "author")
    if author:
        book.author = _clean_title(author)
    date = _command_arg(preamble, "date")
    if date and date != r"\today":
        year = re.search(r"\d{4}", date)
        if year:
            book.year = year.group(0)
    subtitle = _command_arg(preamble, "subtitle")
    if subtitle:
        book.subtitle = _clean_title(subtitle)

    abstract = _abstract_block(body)
    if abstract:
        book.preface = abstract

    units = _chapter_units(body)
    if not units:
        # nessuna struttura riconosciuta: un unico capitolo con tutto il corpo
        text = body.strip()
        if text:
            ch = book.add_chapter("Capitolo 1")
            ch.latex = text
        else:
            book.add_chapter("Capitolo 1")
        return book

    for i, (_start, body_start, title, star) in enumerate(units):
        next_start = units[i + 1][0] if i + 1 < len(units) else len(body)
        chunk = body[body_start:next_start].strip()
        chunk = re.sub(r"\\(?:back|main|front)matter\b", "", chunk).strip()
        if star and any(h in title.lower() for h in _PREFACE_HINTS):
            # capitolo di apertura: lo usiamo come prefazione, non come capitolo
            book.preface = (book.preface + "\n\n" + chunk).strip() if book.preface else chunk
            continue
        ch = book.add_chapter(title or f"Capitolo {len(book.chapters) + 1}")
        ch.latex = chunk

    if not book.chapters:
        book.add_chapter("Capitolo 1")
    return book


def import_latex_project(folder: str | Path) -> Book:
    """Legge la cartella di un progetto LaTeX e ne ricava un `Book`.

    Trova il `.tex` principale, risolve gli `\\input`/`\\include` e delega a
    `latex_to_book`. Solleva `FileNotFoundError` se non c'è alcun `.tex`.
    """
    from .compiler import find_main_tex

    folder = Path(folder)
    main = find_main_tex(folder)
    if main is None:
        raise FileNotFoundError(
            f"Nessun file .tex trovato nella cartella: {folder}")
    raw = main.read_text(encoding="utf-8", errors="ignore")
    inlined = _inline_inputs(raw, main.parent)
    book = latex_to_book(inlined)
    if book.title in ("", "Titolo del libro"):
        # nessun \title: usa il nome del file come ripiego
        book.title = main.stem.replace("_", " ").strip() or book.title
    return book


# --------------------------------------------------------------------- copia immagini
def _referenced_images(book: Book) -> list[str]:
    """Percorsi citati da `\\includegraphics` in tutto il libro, senza duplicati.

    Mantiene l'ordine d'apparizione (utile per messaggi/diagnostica) e normalizza
    i separatori di percorso a `/` come li scrive LaTeX.
    """
    fields = [book.preface, book.premise, book.prologue, book.epilogue,
              book.back_cover, book.cover_image or ""]
    fields += [ch.latex for ch in book.chapters]
    seen: dict[str, None] = {}
    for text in fields:
        for m in _GRAPHICS_RE.finditer(text or ""):
            ref = m.group(1).strip().replace("\\", "/")
            if ref:
                seen.setdefault(ref, None)
    return list(seen)


def _resolve_image(ref: str, src_root: Path) -> Path | None:
    """Trova il file reale per un riferimento `\\includegraphics`.

    Prova il percorso così com'è, poi (se manca l'estensione) le estensioni note;
    come ultimo ripiego cerca per nome/base in tutto l'albero — così gestisce
    anche i `\\graphicspath` (riferimenti senza cartella) che l'import non conserva.
    """
    direct = src_root / ref
    if direct.is_file():
        return direct
    if direct.suffix == "":
        for ext in _IMAGE_EXTS:
            cand = direct.with_suffix(ext)
            if cand.is_file():
                return cand
    name, stem = Path(ref).name, Path(ref).stem
    for cand in src_root.rglob("*"):
        if not cand.is_file():
            continue
        if cand.name == name:
            return cand
        if cand.stem == stem and cand.suffix.lower() in _IMAGE_EXTS:
            return cand
    return None


def copy_referenced_images(book: Book, src_root: str | Path,
                           dest_root: str | Path) -> int:
    """Copia in `dest_root` le immagini citate dal libro, ai *percorsi relativi*
    usati nel LaTeX, così che `\\includegraphics{images/...}` compili nel progetto.

    Restituisce quante immagini sono state effettivamente copiate. Best-effort:
    un'immagine non trovata o non copiabile viene saltata senza interrompere.
    """
    src_root, dest_root = Path(src_root), Path(dest_root)
    copied = 0
    for ref in _referenced_images(book):
        found = _resolve_image(ref, src_root)
        if not found:
            continue
        target = dest_root / ref
        if target.suffix == "":            # riferimento senza estensione
            target = target.with_suffix(found.suffix)
        try:
            if found.resolve() == target.resolve():
                continue                   # già al posto giusto (src == dest)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(found, target)
            copied += 1
        except OSError:
            continue
    return copied


def convert_latex_to_project(src_folder: str | Path, dest_folder: str | Path) -> Project:
    """Converte una cartella LaTeX in un progetto BookForge salvato in `dest_folder`.

    Se `dest_folder` non è vuota e non è già un progetto, crea al suo interno una
    sottocartella col titolo del libro, per non mescolare i file. Copia anche le
    immagini citate dai capitoli, mantenendo i percorsi relativi, così il PDF le
    mostra. Restituisce il `Project` già salvato su disco, pronto da aprire.
    """
    from .compiler import find_main_tex

    src = Path(src_folder)
    book = import_latex_project(src)
    dest = Path(dest_folder)
    if dest.exists() and any(dest.iterdir()) and not Project.is_project(dest):
        safe = "".join(c for c in book.title if c.isalnum() or c in " -_").strip()
        dest = dest / (safe or "progetto_convertito")
    project = Project(dest, book)
    project.save()
    # le immagini sono relative al .tex principale: copiale a partire da lì
    main = find_main_tex(src)
    copy_referenced_images(book, main.parent if main else src, dest)
    return project

