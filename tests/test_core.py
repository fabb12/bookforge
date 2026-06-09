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


def test_latex_to_text_strips_markup():
    latex = (r"% commento da ignorare" "\n"
             r"\section{Titolo}" "\n"
             r"Il \textbf{concetto} chiave \cite{rossi2020} è "
             r"\emph{centrale}\footnote{nota}. Costa il 10\% in meno." "\n"
             r"\begin{itemize}\item primo \end{itemize}")
    out = analysis.latex_to_text(latex)
    assert "Titolo" in out and "concetto" in out and "centrale" in out
    assert "10%" in out                      # \% diventa %
    assert "\\" not in out and "{" not in out  # niente residui di markup
    assert "rossi2020" not in out            # le citazioni spariscono
    assert "commento" not in out


def test_readable_text_prefers_latex():
    # con LaTeX presente si analizza il risultato finale (ripulito)
    assert analysis.readable_text("prosa", r"\textbf{finale}") == "finale"
    # senza LaTeX si ripiega sulla prosa
    assert analysis.readable_text("prosa", "") == "prosa"
    assert analysis.readable_text("", "") == ""


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


def test_latex_editorial_layout():
    # layout editoriale: pacchetti, macro, frontespizio, copyright e quarta strutturata
    b = Book(title="T", subtitle="SubA", author="Autore", year="2026")
    b.style.layout = "editoriale"
    b.subtitle_b = "SubB"; b.publisher = "Editore"; b.isbn = "978-0"
    b.price = "18,00"; b.topic = "Saggistica"
    b.back_quote = "Citazione"; b.back_quote_author = "Tizio"; b.back_blurb = "Descrizione."
    b.cover_image = "cover.png"
    b.add_chapter("Cap").latex = "Corpo."
    tex = latex_builder.build_latex(b)
    # preambolo editoriale
    assert r"\usepackage{tikz}" in tex and r"\definecolor{modernblack}" in tex
    assert r"\newcommand{\booktitle}{T}" in tex
    assert r"\newcommand{\subtitleB}{SubB}" in tex
    # frontespizio + copyright + quarta
    assert r"\AddToShipoutPictureBG" in tex and "cover.png" in tex
    assert r"Copyright" in tex and r"ISBN: \isbn" in tex
    assert r"\fill[modernblack]" in tex
    assert "Citazione" in tex and "TIZIO" in tex  # autore citazione in maiuscolo
    assert "Descrizione." in tex
    # il layout classico non deve emettere i pacchetti editoriali
    b.style.layout = "classico"
    classic = latex_builder.build_latex(b)
    assert r"\usepackage{tikz}" not in classic
    assert r"\begin{titlepage}" in classic


def test_latex_editorial_back_blurb_falls_back_to_abstract():
    # senza descrizione esplicita la quarta editoriale usa l'abstract
    b = Book(title="T")
    b.style.layout = "editoriale"
    b.abstract = "Sintesi dal campo abstract."
    b.add_chapter("Cap").latex = "Corpo."
    assert "Sintesi dal campo abstract." in latex_builder.build_latex(b)


def test_latex_bibliography_emitted_only_with_database():
    # senza database BibTeX non si emette nulla; con database sì
    b = Book(title="T")
    b.add_chapter("Cap").latex = "Vedi \\cite{tizio2020}."
    assert "\\bibliography" not in latex_builder.build_latex(b)
    tex = latex_builder.build_latex(b, bib_database="references")
    assert r"\bibliographystyle{plain}" in tex
    assert r"\bibliography{references}" in tex


# --------------------------------------------------------------- compiler
def test_find_latex_tool_handles_missing(monkeypatch):
    # se l'eseguibile non è da nessuna parte, la ricerca non deve sollevare eccezioni
    monkeypatch.setattr(compiler.shutil, "which", lambda name: None)
    assert compiler.find_latex_tool("pdflatex-inesistente-xyz") is None


def test_write_tex_activates_bibliography_when_bib_present(tmp_path):
    # con references.bib nella cartella, il .tex generato include la bibliografia
    p = Project(tmp_path, Book(title="T"))
    p.book.add_chapter("Cap").latex = "Vedi \\cite{tizio2020}."
    (tmp_path / "references.bib").write_text(
        "@book{tizio2020, title={X}, author={Tizio}, year={2020}}\n",
        encoding="utf-8")
    tex = compiler.write_tex(p).read_text(encoding="utf-8")
    assert r"\bibliography{references}" in tex


def test_extract_latex_errors_captures_error_blocks():
    log = (
        "This is pdfTeX\n"
        "(./book.tex\n"
        "! Undefined control sequence.\n"
        "l.42 \\badcommand\n"
        "             {foo}\n"
        "Some more output\n"
        "! Missing $ inserted.\n"
        "l.51 a_b\n"
        "Output written\n"
    )
    errors = compiler.extract_latex_errors(log)
    assert "Undefined control sequence" in errors
    assert "l.42" in errors
    assert "Missing $ inserted" in errors
    assert "l.51" in errors
    # il rumore non-errore non finisce nel riassunto
    assert "This is pdfTeX" not in errors


def test_extract_latex_errors_empty_when_clean():
    assert compiler.extract_latex_errors("PDF generato: book.pdf\nNiente errori") == ""


def test_extract_latex_errors_respects_max_chars():
    log = "\n".join(f"! Errore numero {i} qui" for i in range(500))
    out = compiler.extract_latex_errors(log, max_chars=200)
    assert len(out) <= 200 + len("\n…(troncato)")
    assert out.endswith("…(troncato)")


def test_mock_engine_fix_latex_escapes_special_chars():
    from bookforge.agents.engine import MockEngine
    eng = MockEngine()
    fixed, summary = eng.fix_latex("Costo del 50% di A & B con x_1 e #1.", errors="")
    # `&`, `_`, `#` vengono scappati; `%` resta (commento valido)
    assert r"A \& B" in fixed
    assert r"x\_1" in fixed
    assert r"\#1" in fixed
    assert summary  # c'è sempre un riepilogo (anche se "nessuna modifica")
    # un carattere già scappato non viene raddoppiato
    again, _ = eng.fix_latex(r"gia\& scappato", errors="")
    assert again.count(r"\&") == 1


def test_error_line_numbers_from_log():
    log = ("! Undefined control sequence.\nl.177 \\pagestyle{mainmatter}\n"
           "blah\n! Undefined control sequence.\nl.214 \\color{moderngray}\n"
           "l.177 ripetuto\n")
    assert compiler.error_line_numbers(log) == [177, 214]


def test_error_regions_localizes_only_error_zones():
    # sorgente di 300 righe; gli errori sono a riga 177 e 214 (1-based)
    src_lines = [f"riga {i}" for i in range(1, 301)]
    src_lines[176] = "\\pagestyle{mainmatter}"   # riga 177
    src_lines[213] = "\\color{moderngray} testo"  # riga 214
    source = "\n".join(src_lines)
    log = "l.177 \\pagestyle{mainmatter}\nl.214 \\color{moderngray}"
    regions = compiler.error_regions(source, log, context=6)
    # due finestre distinte, ciascuna ~13 righe, lontane dai bordi
    assert len(regions) == 2
    (s1, e1), (s2, e2) = regions
    assert s1 <= 176 < e1 and s2 <= 213 < e2
    # copre solo una piccola frazione del documento, non tutto
    covered = sum(e - s for s, e in regions)
    assert covered < 30


def test_error_regions_locates_runaway_argument_by_text():
    source = ("\\chapter{Uno}\n"
              "\\caption{Il cervello umano è un paradosso metabolico che consuma il 20% del corpo}\n"
              "altro testo\n")
    log = ("Runaway argument?\n"
           "{Il cervello umano è un paradosso metabolico che consuma il 20\\label \\ETC.\n"
           "! File ended while scanning use of \\caption@xdblarg.")
    regions = compiler.error_regions(source, log, context=1)
    assert regions, "deve localizzare la riga del runaway dal testo"
    s, e = regions[0]
    assert s <= 1 < e  # la caption è alla riga indice 1


def test_parse_latex_fix_separates_summary_and_source():
    from bookforge.agents.engine import _parse_latex_fix
    out = ("MODIFICHE:\n- Scappato il carattere %\n- Bilanciate le graffe\n"
           "SORGENTE:\n\\documentclass{book}\n\\begin{document}\nciao\\end{document}")
    source, summary = _parse_latex_fix(out)
    assert source.startswith("\\documentclass")
    assert "Scappato il carattere" in summary
    assert "MODIFICHE" not in summary
    # senza marcatore: tutto è sorgente, riepilogo vuoto
    src2, sum2 = _parse_latex_fix("\\documentclass{book}")
    assert src2 == "\\documentclass{book}"
    assert sum2 == ""
    # accetta anche il marcatore FRAMMENTO (correzione localizzata)
    src3, sum3 = _parse_latex_fix("MODIFICHE:\n- x\nFRAMMENTO:\nciao mondo")
    assert src3 == "ciao mondo"
    assert "x" in sum3


def test_mock_engine_fix_latex_snippet_matches_signature():
    from bookforge.agents.engine import MockEngine
    eng = MockEngine()
    fixed, summary = eng.fix_latex_snippet("a & b con x_1", errors="l.5")
    assert r"a \& b" in fixed and r"x\_1" in fixed
    assert summary


def test_needs_bibtex_detects_citations(tmp_path):
    tex = tmp_path / "book.tex"
    tex.write_text("dummy", encoding="utf-8")
    aux = tmp_path / "book.aux"
    aux.write_text("\\relax\n", encoding="utf-8")
    assert compiler._needs_bibtex(tex) is False
    aux.write_text("\\citation{tizio2020}\n\\bibdata{references}\n", encoding="utf-8")
    assert compiler._needs_bibtex(tex) is True


# --------------------------------------------------------------- model
def test_model_roundtrip_with_new_fields(tmp_path):
    b = Book(title="T", cover_image="images/c.png")
    b.style.mode = "autopilota"
    b.premise = "pre"; b.prologue = "pro"; b.epilogue = "epi"
    # metadati editoriali
    b.style.layout = "editoriale"
    b.subtitle_b = "sub2"; b.publisher = "Ed"; b.isbn = "978"; b.price = "18,00"
    b.back_quote = "cit"; b.back_quote_author = "Tizio"; b.back_blurb = "descr"
    c = b.add_chapter("Cap")
    c.argument = {"thesis": "x", "arguments": []}
    c.intermezzo = "interludio"
    b2 = Book.from_dict(b.to_dict())
    assert b2.style.mode == "autopilota"
    assert b2.chapters[0].argument == {"thesis": "x", "arguments": []}
    assert b2.cover_image == "images/c.png"
    assert b2.premise == "pre" and b2.prologue == "pro" and b2.epilogue == "epi"
    assert b2.chapters[0].intermezzo == "interludio"
    assert b2.style.layout == "editoriale"
    assert b2.subtitle_b == "sub2" and b2.publisher == "Ed" and b2.isbn == "978"
    assert b2.price == "18,00" and b2.back_quote == "cit"
    assert b2.back_quote_author == "Tizio" and b2.back_blurb == "descr"
    # persistenza su disco
    p = Project(tmp_path, b); p.save()
    assert Project.is_project(tmp_path)
    p2 = Project.load(tmp_path)
    assert p2.book.style.mode == "autopilota"
    assert p2.book.premise == "pre" and p2.book.chapters[0].intermezzo == "interludio"
