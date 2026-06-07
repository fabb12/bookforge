"""Versioning dell'opera: istantanee di book.json + diff testuale tra versioni.

Le versioni vivono in `.bookforge_versions/` nella cartella del progetto, come
copie datate di book.json. Permettono di salvare punti di ripristino e di vedere
cosa è cambiato (diff per capitolo) — sicurezza per il lavoro dell'autore.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .model import Book

VERSIONS_DIR = ".bookforge_versions"


@dataclass
class Version:
    path: Path
    date: str
    label: str

    def display(self) -> str:
        when = self.date.replace("T", " ")
        return f"{when}  —  {self.label}" if self.label else when


def _dir(folder: str | Path) -> Path:
    return Path(folder) / VERSIONS_DIR


def save_version(folder: str | Path, book: Book, label: str = "") -> Version:
    d = _dir(folder)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-")[:40]
    fname = f"{ts}__{safe}.json" if safe else f"{ts}.json"
    payload = {"_saved_at": datetime.now().isoformat(timespec="seconds"),
               "_label": label, "book": book.to_dict()}
    (d / fname).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return Version(d / fname, payload["_saved_at"], label)


def list_versions(folder: str | Path) -> list[Version]:
    d = _dir(folder)
    if not d.is_dir():
        return []
    out: list[Version] = []
    for p in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out.append(Version(p, data.get("_saved_at", p.stem), data.get("_label", "")))
    return out


def load_version_book(path: str | Path) -> Book:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Book.from_dict(data.get("book", data))


def diff_books(old: Book, new: Book) -> str:
    """Diff unificato per capitolo (titolo + testo) tra due versioni del libro."""
    def blocks(b: Book) -> dict[str, str]:
        d = {"§ metadati": f"Titolo: {b.title}\nAutore: {b.author}\n"
                            f"Sottotitolo: {b.subtitle}\nPrefazione:\n{b.preface}"}
        for i, c in enumerate(b.chapters, 1):
            d[f"{i}. {c.title}"] = c.text or c.latex or ""
        return d

    old_b, new_b = blocks(old), blocks(new)
    keys = list(dict.fromkeys(list(old_b) + list(new_b)))
    chunks: list[str] = []
    for k in keys:
        a = old_b.get(k, "").splitlines()
        b = new_b.get(k, "").splitlines()
        if a == b:
            continue
        diff = difflib.unified_diff(a, b, fromfile=f"vecchia/{k}",
                                    tofile=f"nuova/{k}", lineterm="")
        chunks.append("\n".join(diff))
    return "\n\n".join(chunks).strip() or "Nessuna differenza nei contenuti."
