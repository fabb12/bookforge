"""Export del libro in Markdown ed EPUB.

Markdown: sempre disponibile (puro). EPUB: usa `pandoc` se presente (resa
migliore), altrimenti scrive un EPUB minimale valido senza dipendenze esterne.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import uuid
import zipfile
from html import escape
from pathlib import Path

from .model import Book


# --------------------------------------------------------------- Markdown
def _chapter_body(ch) -> str:
    return (ch.text or "").strip() or ""


def build_markdown(book: Book) -> str:
    lines: list[str] = [f"# {book.title}"]
    if book.subtitle:
        lines.append(f"## {book.subtitle}")
    if book.author:
        lines.append(f"\n*{book.author}*" + (f" — {book.year}" if book.year else ""))
    pref = (book.preface or book.abstract or "").strip()
    if pref:
        lines.append("\n## Prefazione\n")
        lines.append(pref)
    for ch in book.chapters:
        lines.append(f"\n# {ch.title}\n")
        body = _chapter_body(ch)
        lines.append(body if body else "_(capitolo ancora vuoto)_")
    if book.back_cover.strip():
        lines.append("\n---\n")
        lines.append(book.back_cover.strip())
    return "\n".join(lines).strip() + "\n"


def write_markdown(book: Book, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown(book), encoding="utf-8")
    return path


# --------------------------------------------------------------- EPUB
def _paras_to_html(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "<p></p>"
    parts = re.split(r"\n\s*\n", text)
    return "\n".join(f"<p>{escape(p.strip()).replace(chr(10), '<br/>')}</p>"
                     for p in parts if p.strip())


def build_epub(book: Book, path: str | Path) -> Path:
    """Scrive un EPUB. Usa pandoc se disponibile, altrimenti un writer minimale."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("pandoc"):
        try:
            return _epub_via_pandoc(book, path)
        except Exception:  # noqa: BLE001 - ripiega sul writer interno
            pass
    return _epub_minimal(book, path)


def _epub_via_pandoc(book: Book, path: Path) -> Path:
    md = build_markdown(book)
    cmd = ["pandoc", "-f", "markdown", "-o", str(path),
           "--metadata", f"title={book.title}",
           "--metadata", f"author={book.author}"]
    subprocess.run(cmd, input=md, text=True, capture_output=True, timeout=120, check=True)
    if not path.exists():
        raise RuntimeError("pandoc non ha prodotto l'EPUB")
    return path


def _epub_minimal(book: Book, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    uid = f"urn:uuid:{uuid.uuid4()}"
    chapters = []  # (id, filename, title, xhtml)

    # prefazione come "capitolo 0"
    pref = (book.preface or book.abstract or "").strip()
    idx = 0
    if pref:
        chapters.append(("pref", "pref.xhtml", "Prefazione",
                         _xhtml("Prefazione", _paras_to_html(pref))))
    for i, ch in enumerate(book.chapters, 1):
        cid = f"chap{i}"
        chapters.append((cid, f"{cid}.xhtml", ch.title,
                         _xhtml(ch.title, _paras_to_html(_chapter_body(ch)))))

    manifest = "\n".join(
        f'    <item id="{cid}" href="{fn}" media-type="application/xhtml+xml"/>'
        for cid, fn, _t, _x in chapters)
    spine = "\n".join(f'    <itemref idref="{cid}"/>'
                      for cid, _fn, _t, _x in chapters)
    nav_items = "\n".join(
        f'      <li><a href="{fn}">{escape(t)}</a></li>'
        for _cid, fn, t, _x in chapters)

    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{uid}</dc:identifier>
    <dc:title>{escape(book.title)}</dc:title>
    <dc:creator>{escape(book.author)}</dc:creator>
    <dc:language>{escape(_lang_code(book.style.language))}</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{manifest}
  </manifest>
  <spine>
{spine}
  </spine>
</package>"""

    nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Indice</title></head>
<body>
  <nav epub:type="toc" id="toc"><h1>Indice</h1><ol>
{nav_items}
  </ol></nav>
</body>
</html>"""

    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    with zipfile.ZipFile(path, "w") as z:
        # il mimetype deve essere il primo file e NON compresso
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", content_opf)
        z.writestr("OEBPS/nav.xhtml", nav_xhtml)
        for _cid, fn, _t, xhtml in chapters:
            z.writestr(f"OEBPS/{fn}", xhtml)
    return path


def _xhtml(title: str, body_html: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>{escape(title)}</title></head>
<body>
<h1>{escape(title)}</h1>
{body_html}
</body>
</html>"""


def _lang_code(language: str) -> str:
    l = (language or "").lower()
    if "ital" in l:
        return "it"
    if "engl" in l or "ingl" in l:
        return "en"
    if "fran" in l or "franc" in l:
        return "fr"
    if "spagn" in l or "span" in l:
        return "es"
    return "it"
