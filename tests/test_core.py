"""Test della logica core pura (nessuna GUI, nessuna rete)."""
import zipfile

from bookforge.core import (
    analysis, structure, biblio, progress, versioning, export, diagram,
    latex_builder, compiler,
)
from bookforge.core.model import Book, Project


# --------------------------------------------------------------- analysis
def test_analyze_basic_metrics():
    text = "Questa è una frase. Questa è un'altra frase un poco più lunga di prima."
    m = analysis.analyze(text)
    assert m.words > 0 and m.sentences == 2
    assert 0 <= m.gulpease <= 100
    assert analysis.gulpease_label(95) == "molto facile"
    assert analysis.analyze("").words == 0


def test_heuristic_notes_flags_long_and_passive():
    long_sentence = "parola " * 40
    notes = analysis.heuristic_notes(long_sentence + ".")
    assert any("lung" in n.issue.lower() for n in notes)


def test_flag_claims_detects_numbers_and_dates():
    flags = analysis.flag_claims("Nel 1995 il 90% degli esperti era d'accordo.")
    assert flags and any("numer" in f.reason or "tempor" in f.reason for f in flags)


# --------------------------------------------------------------- structure
def test_argument_map_parse_and_roundtrip():
    text = "TESI: t\nARGOMENTO: a1\nPROVA: p1\nOBIEZIONE: o1\nREPLICA: r1\nARGOMENTO: a2"
    amap = structure.parse_ai_map(text)
    assert amap.thesis == "t"
    assert len(amap.arguments) == 2
    assert amap.arguments[0].evidence == ["p1"]
    again = structure.ArgumentMap.from_dict(amap.to_dict())
    assert again.thesis == amap.thesis and len(again.arguments) == 2
    # round-trip via formato editabile
    reparsed = structure.parse_ai_map(amap.to_ai_format())
    assert reparsed.thesis == "t" and len(reparsed.arguments) == 2


def test_argument_map_to_concepts():
    amap = structure.parse_ai_map("TESI: x\nARGOMENTO: a\nPROVA: p")
    concepts = amap.to_concepts()
    assert "x" in concepts and "a" in concepts and "p" in concepts


# --------------------------------------------------------------- biblio
def test_bibtex_roundtrip_and_cite():
    e = biblio.BibEntry("smith2020", "article",
                        {"author": "Smith, John", "title": "On X", "year": "2020"})
    parsed = biblio.parse_bibtex(e.to_bibtex())
    assert parsed[0].key == "smith2020"
    assert parsed[0].get("title") == "On X"
    assert biblio.cite_command(["a", "b"]) == "\\cite{a,b}"


def test_suggest_key_uses_surname():
    assert biblio.suggest_key("Rossi, Mario", "2021", set()) == "rossi2021"
    # collisione → suffisso
    k = biblio.suggest_key("Rossi, Mario", "2021", {"rossi2021"})
    assert k != "rossi2021" and k.startswith("rossi2021")


# --------------------------------------------------------------- progress
def test_progress_snapshot_and_save(tmp_path):
    b = Book(title="T")
    b.add_chapter("C1").text = "Una frase. Due frasi."
    snap = progress.save_snapshot(tmp_path, b)
    assert snap["total_words"] > 0
    hist = progress.load_history(tmp_path)
    assert len(hist) == 1


# --------------------------------------------------------------- versioning
def test_versioning_save_list_diff(tmp_path):
    b = Book(title="T")
    b.add_chapter("C1").text = "Originale."
    versioning.save_version(tmp_path, b, "v1")
    vers = versioning.list_versions(tmp_path)
    assert len(vers) == 1 and vers[0].label == "v1"
    old = versioning.load_version_book(vers[0].path)
    b.chapters[0].text = "Modificato."
    d = versioning.diff_books(old, b)
    assert "Modificato" in d and "Originale" in d


def test_versioning_diff_html_and_stats():
    old = Book(title="T")
    old.add_chapter("C1").text = "riga uno\nriga due"
    new = Book(title="T")
    new.add_chapter("C1").text = "riga uno\nriga due modificata\nriga tre"
    html = versioning.diff_html(old, new)
    assert "background" in html and "riga tre" in html  # righe colorate
    stats = versioning.diff_stats(old, new)
    assert stats["added"] >= 2 and stats["removed"] >= 1 and stats["changed_blocks"] == 1
    # nessuna differenza → stats a zero
    assert versioning.diff_stats(old, old) == {"added": 0, "removed": 0, "changed_blocks": 0}


# --------------------------------------------------------------- export
def test_markdown_export_contains_chapters():
    b = Book(title="Titolo", author="Aut")
    b.add_chapter("Intro").text = "Testo."
    md = export.build_markdown(b)
    assert "# Titolo" in md and "# Intro" in md and "Testo." in md


def test_epub_minimal_is_valid_zip(tmp_path):
    b = Book(title="T & T", author="A")
    b.add_chapter("Cap").text = "Uno.\n\nDue."
    out = export.build_epub(b, tmp_path / "out.epub")
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert names[0] == "mimetype"
        assert z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype").decode() == "application/epub+zip"
        assert "OEBPS/content.opf" in names and "OEBPS/nav.xhtml" in names
        assert z.testzip() is None


# --------------------------------------------------------------- diagram
def test_diagram_snippets():
    fig = diagram.tikz_figure("\\begin{tikzpicture}\\end{tikzpicture}", "Una figura")
    assert "\\begin{figure}" in fig and "\\caption{Una figura}" in fig
    img = diagram.image_figure("images/x.png", "Did.")
    # didascalia DOPO includegraphics (sotto l'immagine)
    assert img.index("includegraphics") < img.index("caption")
    assert diagram.strip_fences("```tikz\nX\n```") == "X"


# --------------------------------------------------------------- latex
def test_latex_escape_and_build():
    assert latex_builder.escape_latex("a & b_%") == r"a \& b\_\%"
    b = Book(title="T")
    b.add_chapter("Cap").latex = "Corpo."
    tex = latex_builder.build_latex(b)
    assert "\\documentclass" in tex and "\\chapter{Cap}" in tex and "\\end{document}" in tex


def test_latex_special_sections_and_cover():
    # premessa, prologo, epilogo, intermezzo e immagine di copertina nel .tex
    b = Book(title="T", cover_image="images/cop.png")
    b.premise = "La mia premessa."
    b.prologue = "Il mio prologo."
    b.epilogue = "Il mio epilogo."
    ch = b.add_chapter("Cap"); ch.latex = "Corpo."
    ch.intermezzo = "Un respiro tra i capitoli."
    tex = latex_builder.build_latex(b)
    assert r"\chapter*{Premessa}" in tex and "La mia premessa." in tex
    assert r"\chapter*{Prologo}" in tex and "Il mio prologo." in tex
    assert r"\chapter*{Epilogo}" in tex and "Il mio epilogo." in tex
    assert "Un respiro tra i capitoli." in tex
    assert r"\includegraphics" in tex and "images/cop.png" in tex


# --------------------------------------------------------------- compiler
def test_find_latex_tool_handles_missing(monkeypatch):
    # se l'eseguibile non è da nessuna parte, la ricerca non deve sollevare eccezioni
    monkeypatch.setattr(compiler.shutil, "which", lambda name: None)
    assert compiler.find_latex_tool("pdflatex-inesistente-xyz") is None


# --------------------------------------------------------------- model
def test_model_roundtrip_with_new_fields(tmp_path):
    b = Book(title="T", cover_image="images/c.png")
    b.style.mode = "autopilota"
    b.premise = "pre"; b.prologue = "pro"; b.epilogue = "epi"
    c = b.add_chapter("Cap")
    c.argument = {"thesis": "x", "arguments": []}
    c.intermezzo = "interludio"
    b2 = Book.from_dict(b.to_dict())
    assert b2.style.mode == "autopilota"
    assert b2.chapters[0].argument == {"thesis": "x", "arguments": []}
    assert b2.cover_image == "images/c.png"
    assert b2.premise == "pre" and b2.prologue == "pro" and b2.epilogue == "epi"
    assert b2.chapters[0].intermezzo == "interludio"
    # persistenza su disco
    p = Project(tmp_path, b); p.save()
    assert Project.is_project(tmp_path)
    p2 = Project.load(tmp_path)
    assert p2.book.style.mode == "autopilota"
    assert p2.book.premise == "pre" and p2.book.chapters[0].intermezzo == "interludio"
