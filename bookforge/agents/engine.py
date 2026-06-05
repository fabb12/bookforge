"""Motore multi-agente basato su datapizza-ai.

Quattro sotto-agenti coordinati da un orchestratore:
  - WriterAgent      : trasforma i concetti grezzi in prosa secondo lo stile
  - CoherenceAgent   : verifica/aggiusta la coerenza con i capitoli vicini (usa i RIASSUNTI)
  - FormatterAgent   : converte il testo in corpo LaTeX pulito (senza \\chapter)
  - SummaryAgent     : produce un riassunto breve del capitolo (risparmio token)

Se datapizza-ai o la API key non sono disponibili, si attiva un motore di
fallback offline così l'app resta utilizzabile per provare l'interfaccia.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable

from ..core.model import Book, Chapter

# ---------------------------------------------------------------- client factory
def _make_client(provider: str, api_key: str, model: str):
    provider = provider.lower()
    if provider == "openai":
        from datapizza.clients.openai import OpenAIClient
        return OpenAIClient(api_key=api_key, model=model or "gpt-4o-mini")
    if provider == "anthropic":
        from datapizza.clients.anthropic import AnthropicClient
        return AnthropicClient(api_key=api_key, model=model or "claude-sonnet-4-20250514")
    if provider == "google":
        from datapizza.clients.google import GoogleClient
        return GoogleClient(api_key=api_key, model=model or "gemini-1.5-pro")
    raise ValueError(f"Provider non supportato: {provider}")


@dataclass
class EngineConfig:
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: str = ""

    @staticmethod
    def from_env() -> "EngineConfig":
        return EngineConfig(
            provider=os.getenv("BOOKFORGE_PROVIDER", "openai"),
            model=os.getenv("BOOKFORGE_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("BOOKFORGE_API_KEY", "")
                    or os.getenv("OPENAI_API_KEY", "")
                    or os.getenv("ANTHROPIC_API_KEY", ""),
        )


# ---------------------------------------------------------------- system prompts
def writer_prompt(book: Book) -> str:
    s = book.style
    return (
        f"Sei un autore professionista. Scrivi in {s.language}, in {s.person}, "
        f"con tono {s.tone}, per un pubblico di {s.audience}.\n"
        f"Argomento generale del libro: «{book.topic or book.title}».\n"
        f"Trasforma i CONCETTI grezzi che ricevi in prosa scorrevole e ben strutturata, "
        f"adatta a un capitolo di libro. Non inventare fatti non impliciti nei concetti. "
        f"Non aggiungere titoli di capitolo né intestazioni: solo il corpo del testo, "
        f"diviso in paragrafi. {s.extra_instructions}"
    ).strip()


COHERENCE_PROMPT = (
    "Sei un editor che cura la coerenza narrativa e argomentativa di un libro. "
    "Ricevi il testo di un capitolo e i RIASSUNTI dei capitoli adiacenti e del libro. "
    "Correggi salti logici, ripetizioni e raccordi con ciò che precede e segue, "
    "mantenendo intatto lo stile e i contenuti. Restituisci SOLO il testo del capitolo "
    "revisionato, senza commenti né intestazioni."
)

FORMATTER_PROMPT = (
    "Sei un esperto di tipografia LaTeX. Ricevi testo in prosa e lo converti nel CORPO "
    "LaTeX di un capitolo. NON includere \\documentclass, \\begin{document}, né \\chapter. "
    "Usa \\section{} e \\subsection{} solo se nel testo emergono sezioni evidenti; "
    "usa \\emph{} per le enfasi, \\begin{itemize}/\\enumerate per gli elenchi, "
    "\\begin{quote} per le citazioni. Esegui l'escape dei caratteri speciali "
    "(&, %, $, #, _, {, }). Restituisci SOLO codice LaTeX, nessun commento."
)

SUMMARY_PROMPT = (
    "Riassumi il capitolo in 3-5 frasi che ne catturino tesi e passaggi chiave. "
    "Il riassunto serve come contesto compatto per altri agenti: sii denso e fattuale. "
    "Restituisci solo il riassunto."
)


# ---------------------------------------------------------------- real engine
class DatapizzaEngine:
    def __init__(self, config: EngineConfig):
        from datapizza.agents import Agent  # import qui per gestire l'assenza della libreria
        self._Agent = Agent
        self.config = config
        self._client = _make_client(config.provider, config.api_key, config.model)

    def _agent(self, name: str, system_prompt: str):
        return self._Agent(name=name, client=self._client,
                           system_prompt=system_prompt, terminate_on_text=True)

    # -- singoli passaggi -------------------------------------------------
    def write(self, book: Book, ch: Chapter) -> str:
        a = self._agent("writer", writer_prompt(book))
        task = (f"Titolo del capitolo: {ch.title}\n\nConcetti da sviluppare:\n"
                f"{ch.raw_concepts}")
        return a.run(task).text.strip()

    def coherence(self, book: Book, ch: Chapter, text: str) -> str:
        prev, nxt = book.neighbors(ch.id)
        ctx = [f"Riassunto generale del libro (abstract): {book.abstract or '(nessuno)'}"]
        ctx.append(f"Capitolo PRECEDENTE: {prev.summary or '(nessun riassunto)'}"
                   if prev else "Questo è il PRIMO capitolo.")
        ctx.append(f"Capitolo SUCCESSIVO: {nxt.summary or '(nessun riassunto)'}"
                   if nxt else "Questo è l'ULTIMO capitolo.")
        a = self._agent("coherence", COHERENCE_PROMPT)
        task = "\n".join(ctx) + f"\n\nTESTO DEL CAPITOLO «{ch.title}»:\n{text}"
        return a.run(task).text.strip()

    def format_latex(self, text: str) -> str:
        a = self._agent("formatter", FORMATTER_PROMPT)
        out = a.run(text).text.strip()
        return _strip_code_fences(out)

    def summarize(self, text: str) -> str:
        a = self._agent("summary", SUMMARY_PROMPT)
        return a.run(text).text.strip()


# ---------------------------------------------------------------- offline fallback
class MockEngine:
    """Motore che non chiama nessun LLM: utile senza API key, per testare la GUI."""
    def write(self, book: Book, ch: Chapter) -> str:
        concepts = [c.strip() for c in re.split(r"[\n;.]", ch.raw_concepts) if c.strip()]
        if not concepts:
            return "(nessun concetto fornito)"
        intro = (f"In questo capitolo, dal titolo «{ch.title}», si sviluppano alcuni "
                 f"nodi centrali dell'argomento.")
        paras = [intro]
        for c in concepts:
            paras.append(f"Un aspetto rilevante riguarda {c[0].lower() + c[1:]}. "
                         f"Questo punto merita un approfondimento che ne chiarisca "
                         f"portata e implicazioni.")
        return "\n\n".join(paras)

    def coherence(self, book: Book, ch: Chapter, text: str) -> str:
        return text  # nessuna modifica in modalità offline

    def format_latex(self, text: str) -> str:
        from ..core.latex_builder import escape_latex
        return "\n\n".join(escape_latex(p.strip())
                           for p in text.split("\n\n") if p.strip())

    def summarize(self, text: str) -> str:
        first = text.strip().split("\n\n")[0]
        return (first[:280] + "…") if len(first) > 280 else first


# ---------------------------------------------------------------- orchestrazione
def build_engine(config: EngineConfig, force_offline: bool = False):
    """Restituisce (engine, is_real, message)."""
    if force_offline or not config.api_key:
        return MockEngine(), False, "Modalità offline (nessuna API key): testo simulato."
    try:
        eng = DatapizzaEngine(config)
        return eng, True, f"Motore datapizza-ai attivo ({config.provider}/{config.model})."
    except Exception as e:  # libreria mancante o errore di init
        return MockEngine(), False, f"Fallback offline ({e})."


def process_chapter(engine, book: Book, ch: Chapter,
                    progress: Callable[[str], None] | None = None) -> Chapter:
    """Pipeline completa su un singolo capitolo. Aggiorna ch in-place e lo restituisce."""
    def step(msg):
        if progress:
            progress(msg)

    step("Scrittura della prosa…")
    text = engine.write(book, ch)

    step("Controllo coerenza con i capitoli vicini…")
    text = engine.coherence(book, ch, text)
    ch.text = text

    step("Formattazione LaTeX…")
    ch.latex = engine.format_latex(text)

    step("Generazione riassunto…")
    ch.summary = engine.summarize(text)

    step("Completato.")
    return ch


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    return s.strip()
