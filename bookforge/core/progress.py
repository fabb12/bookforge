"""Storico dei progressi di scrittura: istantanee delle metriche nel tempo.

Persistito in `progress.json` nella cartella del progetto. Serve alla Dashboard
di crescita per mostrare l'andamento (delta vs istantanea precedente).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .analysis import analyze, TextMetrics

PROGRESS_FILE = "progress.json"


def _book_text_metrics(book) -> tuple[TextMetrics, dict]:
    """Metriche aggregate sull'intero libro + per capitolo."""
    full = "\n\n".join((c.text or "") for c in book.chapters)
    overall = analyze(full)
    per_chapter = {c.title: analyze(c.text or "").to_dict() for c in book.chapters}
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
