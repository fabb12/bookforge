"""Test delle trasformazioni pure della pipeline Word → LaTeX (senza pandoc)."""
from bookforge.core.word_to_latex import (
    WordFixOptions, postprocess_latex, proofread_latex, _is_plain_prose,
)

SAMPLE = r"""\documentclass{article}
\begin{document}
Questo è un paragrafo di prosa lungo abbastanza da essere corretto davvero.

\includegraphics{media/foo.png}

\section{Titolo}
Corpo della sezione.
\end{document}
"""


def test_postprocess_centra_immagini_e_margini_e_toc():
    out = postprocess_latex(SAMPLE, WordFixOptions())
    assert r"\begin{center}" in out
    assert r"\includegraphics{media/foo.png}" in out
    assert r"\geometry{margin=2.5cm}" in out
    assert r"\tableofcontents" in out


def test_postprocess_opzioni_disattivate():
    opts = WordFixOptions(center_images=False, set_margins=False, add_toc=False,
                          fit_images=False, format_captions=False)
    out = postprocess_latex(SAMPLE, opts)
    assert r"\begin{center}" not in out
    assert r"\geometry" not in out
    assert r"\tableofcontents" not in out


def test_postprocess_non_duplica_iniezioni():
    once = postprocess_latex(SAMPLE, WordFixOptions())
    twice = postprocess_latex(once, WordFixOptions())
    assert twice.count(r"\geometry{margin=2.5cm}") == 1


def test_proofread_solo_prosa_pura():
    out = proofread_latex(SAMPLE, str.upper)
    assert "QUESTO È UN PARAGRAFO" in out
    # le righe con comandi LaTeX restano intatte
    assert r"\includegraphics{media/foo.png}" in out
    assert r"\section{Titolo}" in out


def test_is_plain_prose():
    assert _is_plain_prose("Una frase semplice ma sufficientemente lunga da contare.")
    assert not _is_plain_prose("\\includegraphics{x.png}")
    assert not _is_plain_prose("corta")
