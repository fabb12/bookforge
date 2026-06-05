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


def open_in_texstudio(project: Project) -> tuple[bool, str]:
    tex_path = write_tex(project)
    ts = find_texstudio()
    if not ts:
        return False, ("TeXstudio non trovato. Il file .tex è stato salvato in:\n"
                       f"{tex_path}\nAprilo manualmente in TeXstudio.")
    try:
        subprocess.Popen([ts, str(tex_path)])
        return True, f"Aperto in TeXstudio: {tex_path}"
    except Exception as e:
        return False, f"Impossibile avviare TeXstudio: {e}\nFile salvato in {tex_path}"


def compile_pdf(project: Project) -> tuple[bool, str]:
    """Compila il PDF con latexmk (se presente) o pdflatex. Restituisce (ok, log)."""
    tex_path = write_tex(project)
    cwd = str(project.folder)
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
        pdf = project.folder / (tex_path.stem + ".pdf")
        ok = pdf.exists() and (r is None or r.returncode == 0 or pdf.exists())
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
