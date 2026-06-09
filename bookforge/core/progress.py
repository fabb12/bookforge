"""Storico dei progressi di scrittura: istantanee delle metriche nel tempo.

Persistito in `progress.json` nella cartella del progetto. Serve alla Dashboard
di crescita per mostrare l'andamento (delta vs istantanea precedente).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .analysis import analyze, readable_text, TextMetrics

PROGRESS_FILE = "progress.json"


def _book_text_metrics(book) -> tuple[TextMetrics, dict]:
    """Metriche aggregate sull'intero libro + per capitolo.

    Analizza il risultato finale di ogni capitolo (LaTeX ripulito se presente,
    altrimenti la prosa): vedi `analysis.readable_text`.
    """
    per_text = {c.title: readable_text(c.text, c.latex) for c in book.chapters}
    full = "\n\n".join(per_text.values())
    overall = analyze(full)
    per_chapter = {title: analyze(txt).to_dict() for title, txt in per_text.items()}
    return overall, per_chapter


def snapshot(book) -> dict:
    overall, per_chapter = _book_text_metrics(book)
    return {
        "date": datetime.now().isoformat(timespec="seconds"),
        "overall": overall.to_dict(),
        "chapters": per_chapter,
        "total_words": overall.words,
    }


def load_history(folder: str | Path) -> list[dict]:
    path = Path(folder) / PROGRESS_FILE
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def save_snapshot(folder: str | Path, book) -> dict:
    folder = Path(folder)
    history = load_history(folder)
    snap = snapshot(book)
    history.append(snap)
    (folder / PROGRESS_FILE).write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap


def delta(curr: dict, prev: dict | None, field: str) -> float | None:
    """Differenza di una metrica «overall» rispetto all'istantanea precedente."""
    if not prev:
        return None
    try:
        return round(curr["overall"][field] - prev["overall"][field], 3)
    except (KeyError, TypeError):
        return None
