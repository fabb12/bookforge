"""Modello dati del libro e persistenza su disco (progetto = cartella con book.json)."""
from __future__ import annotations

import json
import dataclasses
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime


@dataclass
class Chapter:
    id: str                      # identificativo stabile (es. "ch_1")
    title: str = "Capitolo senza titolo"
    raw_concepts: str = ""       # i concetti grezzi inseriti dall'utente
    text: str = ""               # prosa generata dal WriterAgent
    latex: str = ""              # corpo LaTeX (senza \chapter) prodotto dal FormatterAgent
    summary: str = ""            # riassunto breve per risparmiare token nei passaggi futuri
    order: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Chapter":
        known = {f.name for f in dataclasses.fields(Chapter)}
        return Chapter(**{k: v for k, v in d.items() if k in known})


@dataclass
class BookStyle:
    """Impostazioni di stile, iniettate nel system prompt del WriterAgent."""
    tone: str = "saggistico, chiaro e divulgativo"
    audience: str = "lettore colto ma non specialista"
    language: str = "italiano"
    person: str = "terza persona"
    extra_instructions: str = ""
    document_class: str = "book"        # book | article | report
    font_size: str = "11pt"
    paper: str = "a4paper"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "BookStyle":
        known = {f.name for f in dataclasses.fields(BookStyle)}
        return BookStyle(**{k: v for k, v in d.items() if k in known})


@dataclass
class Book:
    title: str = "Titolo del libro"
    subtitle: str = ""
    author: str = "Autore"
    year: str = field(default_factory=lambda: str(datetime.now().year))
    abstract: str = ""              # usato per la prefazione / quarta di copertina
    topic: str = ""                 # argomento generale, dato di contesto agli agenti
    preface: str = ""               # testo della prefazione (LaTeX)
    back_cover: str = ""            # quarta di copertina (LaTeX)
    style: BookStyle = field(default_factory=BookStyle)
    chapters: list[Chapter] = field(default_factory=list)

    # ---------- gestione capitoli ----------
    def next_chapter_id(self) -> str:
        n = 1
        existing = {c.id for c in self.chapters}
        while f"ch_{n}" in existing:
            n += 1
        return f"ch_{n}"

    def add_chapter(self, title: str = "") -> Chapter:
        ch = Chapter(id=self.next_chapter_id(),
                     title=title or f"Capitolo {len(self.chapters) + 1}",
                     order=len(self.chapters))
        self.chapters.append(ch)
        self._reorder()
        return ch

    def remove_chapter(self, chapter_id: str) -> None:
        self.chapters = [c for c in self.chapters if c.id != chapter_id]
        self._reorder()

    def move_chapter(self, chapter_id: str, delta: int) -> None:
        idx = next((i for i, c in enumerate(self.chapters) if c.id == chapter_id), None)
        if idx is None:
            return
        new = idx + delta
        if 0 <= new < len(self.chapters):
            self.chapters[idx], self.chapters[new] = self.chapters[new], self.chapters[idx]
            self._reorder()

    def get(self, chapter_id: str) -> Chapter | None:
        return next((c for c in self.chapters if c.id == chapter_id), None)

    def neighbors(self, chapter_id: str) -> tuple[Chapter | None, Chapter | None]:
        idx = next((i for i, c in enumerate(self.chapters) if c.id == chapter_id), None)
        if idx is None:
            return None, None
        prev = self.chapters[idx - 1] if idx > 0 else None
        nxt = self.chapters[idx + 1] if idx < len(self.chapters) - 1 else None
        return prev, nxt

    def _reorder(self) -> None:
        for i, c in enumerate(self.chapters):
            c.order = i

    # ---------- serializzazione ----------
    def to_dict(self) -> dict:
        return {
            "title": self.title, "subtitle": self.subtitle, "author": self.author,
            "year": self.year, "abstract": self.abstract, "topic": self.topic,
            "preface": self.preface, "back_cover": self.back_cover,
            "style": self.style.to_dict(),
            "chapters": [c.to_dict() for c in self.chapters],
        }

    @staticmethod
    def from_dict(d: dict) -> "Book":
        b = Book(
            title=d.get("title", "Titolo del libro"),
            subtitle=d.get("subtitle", ""),
            author=d.get("author", "Autore"),
            year=d.get("year", str(datetime.now().year)),
            abstract=d.get("abstract", ""),
            topic=d.get("topic", ""),
            preface=d.get("preface", ""),
            back_cover=d.get("back_cover", ""),
            style=BookStyle.from_dict(d.get("style", {})),
        )
        b.chapters = [Chapter.from_dict(c) for c in d.get("chapters", [])]
        b._reorder()
        return b


class Project:
    """Un progetto è una cartella che contiene book.json e l'output .tex."""
    BOOK_FILE = "book.json"

    def __init__(self, folder: str | Path, book: Book | None = None):
        self.folder = Path(folder)
        self.book = book or Book()

    @property
    def book_path(self) -> Path:
        return self.folder / self.BOOK_FILE

    @property
    def tex_path(self) -> Path:
        return self.folder / "book.tex"

    def save(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self.book_path.write_text(
            json.dumps(self.book.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")

    @staticmethod
    def load(folder: str | Path) -> "Project":
        folder = Path(folder)
        data = json.loads((folder / Project.BOOK_FILE).read_text(encoding="utf-8"))
        return Project(folder, Book.from_dict(data))

    @staticmethod
    def is_project(folder: str | Path) -> bool:
        return (Path(folder) / Project.BOOK_FILE).exists()
