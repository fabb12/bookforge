"""Scrittura del .tex, compilazione (latexmk/pdflatex) e apertura in TeXstudio."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .latex_builder import build_latex
from .model import Project


def _latex_search_dirs() -> list[Path]:
    """Cartelle bin tipiche di MiKTeX / TeX Live, oltre al PATH.

    Serve su Windows: dopo l'installazione MiKTeX spesso non è ancora nel PATH
    (o lo è solo dopo un riavvio), quindi `shutil.which` da solo non lo trova.
    """
    home = Path.home()
    dirs = [
        # MiKTeX (installazione per-utente e di sistema)
        home / "AppData/Local/Programs/MiKTeX/miktex/bin/x64",
        home / "AppData/Local/Programs/MiKTeX/miktex/bin",
        Path(r"C:/Program Files/MiKTeX/miktex/bin/x64"),
        Path(r"C:/Program Files (x86)/MiKTeX/miktex/bin/x64"),
        Path(r"C:/Program Files/MiKTeX 2.9/miktex/bin/x64"),
        Path(r"C:/Program Files (x86)/MiKTeX 2.9/miktex/bin"),
    ]
    # TeX Live: annate e piattaforme diverse
    for base in (Path(r"C:/texlive"), Path("/usr/local/texlive"),
                 Path("/opt/texlive")):
        if base.is_dir():
            for year in sorted(base.glob("20*"), reverse=True):
                bins = year / "bin"
                if bins.is_dir():
                    dirs.extend(p for p in bins.iterdir() if p.is_dir())
    return dirs


def find_latex_tool(name: str) -> str | None:
    """Trova un eseguibile LaTeX (`latexmk`/`pdflatex`) nel PATH o, in mancanza,
    nelle posizioni tipiche di MiKTeX / TeX Live. Restituisce il percorso o None."""
    p = shutil.which(name)
    if p:
        return p
    exe = name + (".exe" if sys.platform.startswith("win") else "")
    for d in _latex_search_dirs():
        cand = d / exe
        if cand.exists():
            return str(cand)
    return None


def _perl_available() -> bool:
    """Indica se un interprete Perl è raggiungibile.

    `latexmk` è uno script Perl: senza Perl non parte (tipico di MiKTeX su
    Windows, che non lo include). In quel caso conviene usare `pdflatex`.
    """
    return shutil.which("perl") is not None or shutil.which("perl.exe") is not None


def _env_with_tool(tool_path: str) -> dict:
    """Ambiente con la cartella dello strumento in testa al PATH.

    Così `latexmk` trovato fuori dal PATH riesce comunque a invocare `pdflatex`
    (e gli altri programmi) della stessa distribuzione.
    """
    env = os.environ.copy()
    bindir = str(Path(tool_path).parent)
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    return env


def write_tex(project: Project) -> Path:
    project.folder.mkdir(parents=True, exist_ok=True)
    # Se il progetto ha un references.bib, attiva la bibliografia nel .tex così
    # che BibTeX abbia qualcosa da elaborare (vedi _run_pdflatex).
    bib = "references" if (project.folder / "references.bib").exists() else None
    tex = build_latex(project.book, bib_database=bib)
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


def _pdflatex_pass(pdflatex: str, tex_path: Path, cwd: str,
                   env: dict) -> subprocess.CompletedProcess:
    """Una passata di `pdflatex` in `nonstopmode` (come TeXstudio).

    Niente `-halt-on-error`: un errore recuperabile non deve impedire la
    generazione del PDF (è il motivo per cui in TeXstudio compila e qui no).
    """
    return subprocess.run(
        [pdflatex, "-interaction=nonstopmode", tex_path.name],
        cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300, env=env)


def _needs_bibtex(tex_path: Path) -> bool:
    """Vero se l'.aux generato contiene citazioni/bibliografia da risolvere.

    Dopo la prima passata di pdflatex, l'.aux riporta `\\citation` e `\\bibdata`
    solo se il documento usa davvero una bibliografia BibTeX: in tal caso va
    eseguito `bibtex`.
    """
    aux = tex_path.with_suffix(".aux")
    try:
        txt = aux.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "\\bibdata" in txt or "\\citation" in txt


def _run_pdflatex(tex_path: Path, cwd: str) -> tuple[bool, str] | None:
    """Compila con `pdflatex`, eseguendo `bibtex` se serve. Restituisce
    (ok, log) o None se `pdflatex` non è installato.

    Sequenza: pdflatex → (bibtex + 2 passate) se c'è bibliografia, altrimenti
    una seconda passata per indice e riferimenti incrociati.
    """
    pdflatex = find_latex_tool("pdflatex")
    if not pdflatex:
        return None
    env = _env_with_tool(pdflatex)
    bib_log = ""

    r = _pdflatex_pass(pdflatex, tex_path, cwd, env)
    if _needs_bibtex(tex_path):
        bibtex = find_latex_tool("bibtex")
        if bibtex:
            rb = subprocess.run(
                [bibtex, tex_path.stem],
                cwd=cwd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300, env=env)
            bib_log = "--- bibtex ---\n" + (rb.stdout or "") + (rb.stderr or "")
        else:
            bib_log = ("--- bibtex ---\nbibtex non trovato: la bibliografia "
                       "non sarà risolta. Installa BibTeX (incluso in MiKTeX/"
                       "TeX Live).\n")
        for _ in range(2):  # due passate perché le citazioni si stabilizzino
            r = _pdflatex_pass(pdflatex, tex_path, cwd, env)
    else:
        r = _pdflatex_pass(pdflatex, tex_path, cwd, env)  # indice e riferimenti

    pdf = tex_path.with_suffix(".pdf")
    log = bib_log + (r.stdout[-4000:] if r else "") + (r.stderr[-2000:] if r else "")
    if pdf.exists():
        return True, f"PDF generato: {pdf}\n\n--- log ---\n{log}"
    return False, f"Compilazione fallita.\n\n--- log ---\n{log}"


def compile_tex(tex_path: str | Path) -> tuple[bool, str]:
    """Compila un file .tex arbitrario con latexmk (se presente) o pdflatex.

    La compilazione avviene nella cartella del file, così funzionano i percorsi
    relativi (immagini, capitoli inclusi con \\input, bibliografie, ...).

    `latexmk` è uno script Perl: se Perl non è installato (caso tipico di MiKTeX
    su Windows) non viene usato e si ripiega direttamente su `pdflatex`. Anche se
    `latexmk` parte ma fallisce senza produrre il PDF, si tenta `pdflatex` come
    riserva prima di arrendersi.
    """
    tex_path = Path(tex_path)
    if not tex_path.exists():
        return False, f"File .tex non trovato: {tex_path}"
    cwd = str(tex_path.parent)
    # Usa latexmk solo se è presente *e* Perl è disponibile per eseguirlo.
    latexmk = find_latex_tool("latexmk") if _perl_available() else None
    try:
        if latexmk:
            r = subprocess.run(
                [latexmk, "-pdf", "-f", "-interaction=nonstopmode",
                 tex_path.name],
                cwd=cwd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300,
                env=_env_with_tool(latexmk))
            pdf = tex_path.with_suffix(".pdf")
            log = (r.stdout[-4000:] if r else "") + (r.stderr[-2000:] if r else "")
            if pdf.exists():
                return True, f"PDF generato: {pdf}\n\n--- log ---\n{log}"
            # latexmk ha fallito: ritenta con pdflatex prima di arrendersi.
            fallback = _run_pdflatex(tex_path, cwd)
            if fallback is not None:
                return fallback
            return False, f"Compilazione fallita.\n\n--- log ---\n{log}"
        result = _run_pdflatex(tex_path, cwd)
        if result is None:
            return False, ("Né latexmk (eseguibile via Perl) né pdflatex trovati. "
                           "Installa una distribuzione LaTeX (TeX Live / MiKTeX) — "
                           "se l'hai appena installata, riavvia BookForge perché il "
                           "PATH venga aggiornato — oppure compila in TeXstudio.")
        return result
    except subprocess.TimeoutExpired:
        return False, "Timeout durante la compilazione."
    except Exception as e:
        return False, f"Errore di compilazione: {e}"


def extract_latex_errors(log: str, max_chars: int = 2500) -> str:
    """Estrae dal log di compilazione i blocchi di errore significativi.

    Funzione pura: serve a passare all'LLM un riassunto compatto del problema
    invece dell'intero log (spesso lungo migliaia di righe). Cattura le righe
    che iniziano con `!` (gli errori di TeX/LaTeX) insieme al loro contesto —
    in particolare le righe `l.NN` che indicano dove si è interrotto — e gli
    avvisi rilevanti (`Undefined`, `Missing`, `Runaway argument`).

    Restituisce stringa vuota se non trova errori riconoscibili.
    """
    lines = log.splitlines()
    blocks: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("!"):
            # un errore: prendi la riga e il contesto fino alla riga `l.NN`
            block = [line]
            j = i + 1
            saw_line_marker = False
            while j < n and j - i <= 8:
                nxt = lines[j]
                block.append(nxt)
                if re.match(r"^l\.\d+", nxt):
                    saw_line_marker = True
                    # includi anche la riga successiva (il resto del costrutto)
                    if j + 1 < n:
                        block.append(lines[j + 1])
                        j += 1
                    break
                j += 1
            if not saw_line_marker:
                # errore senza marcatore di riga: limita a poche righe utili
                block = block[:4]
            blocks.append("\n".join(block).rstrip())
            i = j + 1
            continue
        # avvisi tipici che spesso accompagnano un errore
        if re.search(r"Runaway argument|Undefined control sequence|"
                     r"Missing .* inserted|Emergency stop", line):
            blocks.append(line.strip())
        i += 1

    # dedup mantenendo l'ordine
    seen: set[str] = set()
    unique: list[str] = []
    for b in blocks:
        if b and b not in seen:
            seen.add(b)
            unique.append(b)
    out = "\n\n".join(unique).strip()
    if len(out) > max_chars:
        out = out[:max_chars] + "\n…(troncato)"
    return out


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
