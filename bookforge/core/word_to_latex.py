"""Pipeline «Word → LaTeX → PDF»: converte un .docx in LaTeX con pandoc, ne
sistema l'impaginazione (margini, immagini, didascalie, indice) e prepara il
sorgente pronto per la compilazione del PDF.

Le trasformazioni sul LaTeX (`postprocess_latex`, `proofread_latex`) sono pure e
deterministiche, quindi testabili senza pandoc. L'invocazione di pandoc e la
compilazione sono strumenti esterni rilevati a runtime con fallback grazioso
(in linea con le convenzioni: nessuna dipendenza pesante assunta nel core).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# mappa lingua di prodotto -> opzione di babel
_BABEL = {"italiano": "italian", "inglese": "english", "francese": "french",
          "spagnolo": "spanish", "tedesco": "german"}


@dataclass
class WordFixOptions:
    """Scelte di sistemazione applicate al LaTeX prodotto da pandoc."""
    center_images: bool = True       # centra le immagini fuori da una figure
    fit_images: bool = True          # limita la larghezza alla riga di testo
    format_captions: bool = True     # didascalie piccole, etichetta in grassetto
    add_toc: bool = True             # genera l'indice (\tableofcontents)
    set_margins: bool = True
    margin_cm: float = 2.5
    language: str = "italiano"
    proofread: bool = False          # correzione ortografica del testo (via callback)
    title: str = ""
    author: str = ""


@dataclass
class WordFixResult:
    tex_path: Path
    media_dir: Path | None = None
    messages: list = field(default_factory=list)


# --------------------------------------------------------------------- pandoc
def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def docx_to_latex(docx_path: str | Path, out_dir: str | Path,
                  options: WordFixOptions) -> str:
    """Converte un .docx in sorgente LaTeX standalone con pandoc.

    Le immagini vengono estratte in `out_dir/media` (percorsi relativi al .tex).
    Solleva `RuntimeError` se pandoc non è disponibile o fallisce.
    """
    if not pandoc_available():
        raise RuntimeError(
            "pandoc non è installato: è necessario per convertire il Word in LaTeX. "
            "Installa pandoc (https://pandoc.org) e riprova.")
    docx_path = Path(docx_path).resolve()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["pandoc", str(docx_path), "-f", "docx", "-t", "latex",
           "--standalone", "--extract-media=media"]
    if options.add_toc:
        cmd.append("--toc")
    if options.title:
        cmd += ["--metadata", f"title={options.title}"]
    if options.author:
        cmd += ["--metadata", f"author={options.author}"]
    babel = _BABEL.get(options.language.lower())
    if babel:
        cmd += ["--metadata", f"lang={babel}"]

    try:
        r = subprocess.run(cmd, cwd=str(out_dir), capture_output=True,
                           text=True, timeout=240)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Timeout durante la conversione con pandoc.") from e
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"pandoc ha restituito un errore:\n{r.stderr[-1500:]}")
    return r.stdout


# --------------------------------------------------------------------- post-processing (puro)
def _injection(options: WordFixOptions) -> str:
    """Righe da aggiungere al preambolo per attuare le opzioni di sistemazione."""
    lines: list[str] = []
    if options.set_margins:
        lines.append(r"\usepackage{geometry}")
        lines.append(r"\geometry{margin=%.2gcm}" % options.margin_cm)
    if options.fit_images:
        # limita ogni immagine alla larghezza utile mantenendo le proporzioni
        lines.append(r"\usepackage{graphicx}")
        lines.append(r"\setkeys{Gin}{width=\linewidth,keepaspectratio}")
    if options.format_captions:
        lines.append(r"\usepackage{caption}")
        lines.append(r"\captionsetup{font=small,labelfont=bf,justification=centering}")
    return "\n".join(lines)


def _center_bare_images(body: str) -> str:
    """Centra le `\\includegraphics` che stanno da sole su una riga (fuori da figure)."""
    pattern = re.compile(
        r"^([ \t]*)(\\includegraphics(?:\[[^\]]*\])?\{[^}]*\})[ \t]*$", re.MULTILINE)
    return pattern.sub(r"\1\\begin{center}\n\1\2\n\1\\end{center}", body)


def postprocess_latex(source: str, options: WordFixOptions) -> str:
    """Applica le sistemazioni d'impaginazione al sorgente LaTeX prodotto da pandoc."""
    begin = re.search(r"\\begin\s*\{document\}", source)
    if not begin:
        # sorgente non standalone: avvolgiamolo in un documento minimale
        source = (r"\documentclass[11pt,a4paper]{article}" "\n"
                  r"\usepackage[utf8]{inputenc}" "\n"
                  r"\begin{document}" "\n" + source + "\n" r"\end{document}")
        begin = re.search(r"\\begin\s*\{document\}", source)

    preamble = source[:begin.start()]
    body = source[begin.end():]

    # inietta nel preambolo solo ciò che non c'è già (evita doppioni)
    inject = _injection(options)
    if inject:
        needed = "\n".join(l for l in inject.splitlines() if l not in preamble)
        if needed:
            preamble = preamble.rstrip() + "\n" + needed + "\n"

    if options.center_images:
        body = _center_bare_images(body)

    if options.add_toc and r"\tableofcontents" not in body:
        body = "\n\\tableofcontents\n\\clearpage\n" + body

    # `body` conserva già il `\end{document}` originale del sorgente standalone
    return preamble + r"\begin{document}" + body


def proofread_latex(source: str, corrector: Callable[[str], str],
                    progress: Callable[[str], None] | None = None) -> str:
    """Corregge l'ortografia dei soli paragrafi di prosa «pura» (senza comandi LaTeX).

    Conservativo per costruzione: qualunque blocco che contenga un backslash
    viene lasciato intatto, così non si rischia di corrompere i comandi LaTeX.
    """
    begin = re.search(r"\\begin\s*\{document\}", source)
    head = source[:begin.end()] if begin else ""
    body = source[begin.end():] if begin else source

    blocks = re.split(r"(\n\s*\n)", body)   # mantiene i separatori
    total = sum(1 for b in blocks if _is_plain_prose(b))
    done = 0
    for i, block in enumerate(blocks):
        if not _is_plain_prose(block):
            continue
        done += 1
        if progress:
            progress(f"Correzione paragrafo {done}/{total}…")
        try:
            blocks[i] = corrector(block)
        except Exception:  # noqa: BLE001 - una correzione fallita non blocca il resto
            pass
    return head + "".join(blocks)


def _is_plain_prose(block: str) -> bool:
    """Vero se il blocco è prosa semplice abbastanza lunga da valere una correzione."""
    s = block.strip()
    return len(s) >= 40 and "\\" not in s and "}" not in s and "{" not in s


# --------------------------------------------------------------------- orchestrazione
def convert_word(docx_path: str | Path, out_dir: str | Path,
                 options: WordFixOptions,
                 corrector: Callable[[str], str] | None = None,
                 progress: Callable[[str], None] | None = None) -> WordFixResult:
    """Esegue l'intera pipeline e scrive il `.tex` sistemato in `out_dir`.

    Restituisce un `WordFixResult` con il percorso del `.tex`. La compilazione
    del PDF è lasciata al chiamante (vedi `core.compiler.compile_tex`).
    """
    def step(msg: str) -> None:
        if progress:
            progress(msg)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    messages: list[str] = []

    step("Conversione del Word con pandoc…")
    source = docx_to_latex(docx_path, out_dir, options)

    step("Sistemazione dell'impaginazione LaTeX…")
    source = postprocess_latex(source, options)

    if options.proofread and corrector is not None:
        step("Correzione ortografica dei paragrafi…")
        source = proofread_latex(source, corrector, progress)
    elif options.proofread:
        messages.append("Correzione ortografica saltata: nessun motore disponibile.")

    tex_path = out_dir / (Path(docx_path).stem + ".tex")
    tex_path.write_text(source, encoding="utf-8")
    media = out_dir / "media"
    return WordFixResult(tex_path=tex_path,
                         media_dir=media if media.exists() else None,
                         messages=messages)
