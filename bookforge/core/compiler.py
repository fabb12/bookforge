"""Scrittura del .tex, compilazione (latexmk/pdflatex) e apertura in TeXstudio."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .latex_builder import build_latex
from .model import Project


def write_tex(project: Project) -> Path:
    project.folder.mkdir(parents=True, exist_ok=True)
    tex = build_latex(project.book)
    project.tex_path.write_text(tex, encoding="utf-8")
    return project.tex_path


def find_texstudio() -> str | None:
    for name in ("texstudio", "TeXstudio", "texstudio.exe"):
        p = shutil.which(name)
        if p:
            return p
    # percorsi tipici
    candidates = [
        r"C:\Program Files\texstudio\texstudio.exe",
        r"C:\Program Files (x86)\texstudio\texstudio.exe",
        "/Applications/texstudio.app/Contents/MacOS/texstudio",
        "/usr/bin/texstudio",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def find_main_tex(folder: str | Path) -> Path | None:
    """Trova il .tex principale di una cartella LaTeX.

    Preferisce i nomi convenzionali (main/book/...), poi il primo .tex che
    contiene `\\documentclass`, infine il primo .tex trovato.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return None
    tex_files = sorted(folder.glob("*.tex"))
    if not tex_files:
        return None
    preferred = ("main.tex", "book.tex", "libro.tex", "tesi.tex", "thesis.tex")
    by_name = {p.name.lower(): p for p in tex_files}
    for name in preferred:
        if name in by_name:
            return by_name[name]
    for p in tex_files:
        try:
            if "\\documentclass" in p.read_text(encoding="utf-8", errors="ignore"):
                return p
        except Exception:  # noqa: BLE001
            continue
    return tex_files[0]


def open_in_texstudio(project: Project) -> tuple[bool, str]:
    tex_path = write_tex(project)
    return open_tex_in_texstudio(tex_path)


def open_tex_in_texstudio(tex_path: str | Path) -> tuple[bool, str]:
    """Apre un qualsiasi file .tex (anche fuori da un progetto) in TeXstudio."""
    tex_path = Path(tex_path)
    ts = find_texstudio()
    if not ts:
        return False, ("TeXstudio non trovato. Il file .tex si trova in:\n"
                       f"{tex_path}\nAprilo manualmente in TeXstudio.")
    try:
        subprocess.Popen([ts, str(tex_path)])
        return True, f"Aperto in TeXstudio: {tex_path}"
    except Exception as e:
        return False, f"Impossibile avviare TeXstudio: {e}\nFile salvato in {tex_path}"


def compile_pdf(project: Project) -> tuple[bool, str]:
    """Compila il PDF con latexmk (se presente) o pdflatex. Restituisce (ok, log)."""
    tex_path = write_tex(project)
    return compile_tex(tex_path)


def compile_tex(tex_path: str | Path) -> tuple[bool, str]:
    """Compila un file .tex arbitrario con latexmk (se presente) o pdflatex.

    La compilazione avviene nella cartella del file, così funzionano i percorsi
    relativi (immagini, capitoli inclusi con \\input, bibliografie, ...).
    """
    tex_path = Path(tex_path)
    if not tex_path.exists():
        return False, f"File .tex non trovato: {tex_path}"
    cwd = str(tex_path.parent)
    latexmk = shutil.which("latexmk")
    try:
        if latexmk:
            r = subprocess.run(
                [latexmk, "-pdf", "-f", "-interaction=nonstopmode",
                 tex_path.name],
                cwd=cwd, capture_output=True, text=True, timeout=300)
        else:
            pdflatex = shutil.which("pdflatex")
            if not pdflatex:
                return False, ("Né latexmk né pdflatex trovati. Installa una "
                               "distribuzione LaTeX (TeX Live / MiKTeX) oppure "
                               "compila direttamente in TeXstudio.")
            r = None
            for _ in range(2):  # due passate per indice e riferimenti
                r = subprocess.run(
                    [pdflatex, "-interaction=nonstopmode", "-halt-on-error",
                     tex_path.name],
                    cwd=cwd, capture_output=True, text=True, timeout=300)
        pdf = tex_path.with_suffix(".pdf")
        log = (r.stdout[-4000:] if r else "") + (r.stderr[-2000:] if r else "")
        if pdf.exists():
            return True, f"PDF generato: {pdf}\n\n--- log ---\n{log}"
        return False, f"Compilazione fallita.\n\n--- log ---\n{log}"
    except subprocess.TimeoutExpired:
        return False, "Timeout durante la compilazione."
    except Exception as e:
        return False, f"Errore di compilazione: {e}"


def open_pdf(project: Project) -> tuple[bool, str]:
    pdf = project.folder / (project.tex_path.stem + ".pdf")
    return open_pdf_path(pdf)


def open_pdf_path(pdf: str | Path) -> tuple[bool, str]:
    """Apre un PDF con l'applicazione predefinita del sistema."""
    pdf = Path(pdf)
    if not pdf.exists():
        return False, "PDF non ancora generato. Compila prima il documento."
    try:
        if sys.platform.startswith("darwin"):
            subprocess.Popen(["open", str(pdf)])
        elif sys.platform.startswith("win"):
            import os
            os.startfile(str(pdf))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(pdf)])
        return True, f"Aperto: {pdf}"
    except Exception as e:
        return False, f"Impossibile aprire il PDF: {e}"
