"""Gestione minimale di una bibliografia BibTeX (references.bib del progetto).

Niente dipendenze esterne: parsing/serializzazione essenziale di voci @type{key,...}.
Pensata per il rigore della saggistica: raccogli le fonti e inserisci \\cite{key}.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BibEntry:
    key: str
    entry_type: str = "article"          # article | book | inproceedings | misc ...
    fields: dict[str, str] = field(default_factory=dict)

    def get(self, name: str, default: str = "") -> str:
        return self.fields.get(name, default)

    def to_bibtex(self) -> str:
        lines = [f"@{self.entry_type}{{{self.key},"]
        items = [f"  {k} = {{{v}}}" for k, v in self.fields.items() if v]
        lines.append(",\n".join(items))
        lines.append("}")
        return "\n".join(lines)

    def label(self) -> str:
        a = self.get("author").split(" and ")[0].strip()
        y = self.get("year")
        t = self.get("title")
        bits = [b for b in (a, y, t) if b]
        return f"[{self.key}] " + " · ".join(bits)


_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,]+),(.*?)\n\}", re.DOTALL)
_FIELD_RE = re.compile(r"(\w+)\s*=\s*[\{\"](.*?)[\}\"]\s*,?\s*(?=\n\s*\w+\s*=|\Z)",
                       re.DOTALL)


def parse_bibtex(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    for m in _ENTRY_RE.finditer(text or ""):
        etype, key, body = m.group(1).lower(), m.group(2).strip(), m.group(3)
        fields = {f.group(1).lower(): " ".join(f.group(2).split())
                  for f in _FIELD_RE.finditer(body)}
        entries.append(BibEntry(key=key, entry_type=etype, fields=fields))
    return entries


def load_bib(path: str | Path) -> list[BibEntry]:
    path = Path(path)
    if not path.exists():
        return []
    return parse_bibtex(path.read_text(encoding="utf-8", errors="replace"))


def save_bib(path: str | Path, entries: list[BibEntry]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(e.to_bibtex() for e in entries) + "\n",
                    encoding="utf-8")
    return path


def suggest_key(author: str, year: str, existing: set[str]) -> str:
    first = (author or "").split(" and ")[0].strip()
    if "," in first:                      # formato BibTeX «Cognome, Nome»
        raw = first.split(",", 1)[0]
    else:                                  # «Nome Cognome» → ultimo token
        raw = first.split()[-1] if first.split() else "ref"
    surname = re.sub(r"[^A-Za-z]", "", raw).lower() or "ref"
    base = f"{surname}{year}".strip() or "ref"
    key, n = base, 1
    while key in existing:
        n += 1
        key = f"{base}{chr(ord('a') + n - 2)}"   # ref2020, ref2020a, ref2020b…
    return key


def cite_command(keys: list[str] | str) -> str:
    if isinstance(keys, str):
        keys = [keys]
    return "\\cite{" + ",".join(k for k in keys if k) + "}"
