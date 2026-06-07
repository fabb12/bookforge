"""Inserimento di diagrammi e immagini nel sorgente LaTeX.

Due strade, entrambe supportate:
  • diagrammi *come codice* — TikZ (nativo) o Mermaid/Graphviz renderizzati a file;
  • immagini raster — inserite con \\includegraphics.

Le funzioni qui sono pure (costruiscono snippet LaTeX) tranne i renderer, che
invocano strumenti esterni (mmdc / dot) se presenti, in modo best-effort.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def strip_fences(s: str) -> str:
    """Rimuove eventuali recinti di codice ```...``` attorno a uno snippet."""
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    return s.strip()


def _label_from(caption: str, prefix: str = "fig") -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (caption or "").lower()).strip("-")
    base = base[:40] or "figura"
    return f"{prefix}:{base}"


def tikz_figure(tikz_code: str, caption: str = "", label: str = "",
                center: bool = True) -> str:
    """Avvolge un blocco tikzpicture in un ambiente figure con didascalia."""
    tikz_code = strip_fences(tikz_code).strip()
    label = label or _label_from(caption)
    lines = ["\\begin{figure}[htbp]"]
    if center:
        lines.append("  \\centering")
    lines.append("  " + tikz_code.replace("\n", "\n  "))
    if caption:
        lines.append(f"  \\caption{{{caption}}}")
    lines.append(f"  \\label{{{label}}}")
    lines.append("\\end{figure}")
    return "\n".join(lines)


def image_figure(rel_path: str, caption: str = "", label: str = "",
                 width: str = r"0.8\textwidth", center: bool = True) -> str:
    """Snippet figure con \\includegraphics. `rel_path` relativo al .tex.

    La didascalia va SOTTO l'immagine (ordine \\includegraphics → \\caption),
    come da convenzione tipografica."""
    rel_path = rel_path.replace("\\", "/")
    label = label or _label_from(caption, prefix="img")
    lines = ["\\begin{figure}[htbp]"]
    if center:
        lines.append("  \\centering")
    lines.append(f"  \\includegraphics[width={width}]{{{rel_path}}}")
    if caption:
        lines.append(f"  \\caption{{{caption}}}")     # sotto l'immagine
    lines.append(f"  \\label{{{label}}}")
    lines.append("\\end{figure}")
    return "\n".join(lines)


def render_mermaid(code: str, out_path: str | Path) -> Path:
    """Renderizza codice Mermaid in PNG/SVG con `mmdc` (mermaid-cli), se presente."""
    out_path = Path(out_path)
    mmdc = shutil.which("mmdc")
    if not mmdc:
        raise RuntimeError(
            "Mermaid CLI (mmdc) non trovato. Installa con:\n"
            "  npm install -g @mermaid-js/mermaid-cli\n"
            "oppure usa un diagramma TikZ (non richiede strumenti esterni).")
    src = out_path.with_suffix(".mmd")
    src.write_text(strip_fences(code), encoding="utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([mmdc, "-i", str(src), "-o", str(out_path)],
                       capture_output=True, text=True, timeout=120)
    if not out_path.exists():
        raise RuntimeError(f"Render Mermaid fallito:\n{r.stderr[:1000]}")
    return out_path


def render_graphviz(code: str, out_path: str | Path, fmt: str = "png") -> Path:
    """Renderizza codice Graphviz (DOT) con `dot`, se presente."""
    out_path = Path(out_path)
    dot = shutil.which("dot")
    if not dot:
        raise RuntimeError("Graphviz (dot) non trovato. Installa Graphviz oppure usa TikZ.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([dot, f"-T{fmt}", "-o", str(out_path)],
                       input=strip_fences(code), capture_output=True, text=True, timeout=120)
    if not out_path.exists():
        raise RuntimeError(f"Render Graphviz fallito:\n{r.stderr[:1000]}")
    return out_path
