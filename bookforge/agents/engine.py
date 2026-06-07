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
        return AnthropicClient(api_key=api_key, model=model or "claude-opus-4-8")
    if provider == "google":
        from datapizza.clients.google import GoogleClient
        return GoogleClient(api_key=api_key, model=model or "gemini-1.5-pro")
    raise ValueError(f"Provider non supportato: {provider}")


@dataclass
class EngineConfig:
    provider: str = "anthropic"
    model: str = "claude-opus-4-8"
    api_key: str = ""

    @staticmethod
    def from_env() -> "EngineConfig":
        return EngineConfig(
            provider=os.getenv("BOOKFORGE_PROVIDER", "anthropic"),
            model=os.getenv("BOOKFORGE_MODEL", "claude-opus-4-8"),
            api_key=os.getenv("BOOKFORGE_API_KEY", "")
                    or os.getenv("ANTHROPIC_API_KEY", "")
                    or os.getenv("OPENAI_API_KEY", "")
                    or os.getenv("GOOGLE_API_KEY", ""),
        )


# ---------------------------------------------------------------- system prompts
def writer_prompt(book: Book) -> str:
    s = book.style
    if s.style_prompt and s.style_prompt.strip():
        ctx = (
            f"Contesto del libro (non ripeterlo nel testo):\n"
            f"Titolo: «{book.title}»\n"
            f"Argomento: «{book.topic or book.title}»\n\n"
        )
        return ctx + s.style_prompt.strip()
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

PROOFREAD_PROMPT = (
    "Sei un correttore di bozze professionista. Ricevi un paragrafo di testo e ne "
    "correggi ortografia, grammatica, punteggiatura e refusi, migliorando la scorrevolezza "
    "SENZA alterare il significato, il tono o la lunghezza in modo sostanziale. "
    "Non aggiungere commenti, virgolette o intestazioni. Non trasformarlo in elenco. "
    "Restituisci SOLO il paragrafo corretto, come testo semplice."
)

# --- comandi di scrittura assistita (editing sulla selezione) ---
EDITOR_PROMPT = (
    "Sei un editor di testi esperto al servizio di un autore. Ricevi un BRANO e "
    "un'ISTRUZIONE. Applica l'istruzione al brano e restituisci SOLO il testo "
    "risultante — niente commenti, virgolette, intestazioni o spiegazioni — nella "
    "stessa lingua del brano. Non inventare fatti non impliciti nel testo o nel contesto."
)

OUTLINE_PROMPT = (
    "Sei un autore. Genera una scaletta puntata (da 5 a 8 punti) per il capitolo "
    "indicato, coerente con l'argomento del libro. Ogni punto è una frase breve. "
    "Restituisci SOLO l'elenco, un punto per riga, senza numeri, trattini o commenti."
)

TRANSITIONS_PROMPT = (
    "Sei un editor che cura la coesione di un capitolo. Ricevi il testo completo del "
    "capitolo e ne migliori i RACCORDI tra paragrafi e sezioni: aggiungi o riscrivi le "
    "frasi di transizione perché il discorso scorra senza salti logici. NON cambiare i "
    "contenuti, i fatti o lo stile, non aggiungere o togliere sezioni. Restituisci SOLO "
    "il testo del capitolo revisionato, senza commenti né intestazioni."
)

BRIDGE_PROMPT = (
    "Sei un autore. Scrivi UN solo paragrafo breve di raccordo che colleghi il capitolo "
    "corrente al capitolo {dove} del libro, in modo fluido e coerente con lo stile. "
    "Usa i riassunti forniti come contesto. Restituisci SOLO il paragrafo, senza "
    "intestazioni né virgolette."
)

# --- generazione di diagrammi (come codice) ---
TIKZ_PROMPT = (
    "Sei un esperto di TikZ/LaTeX. Data una descrizione, genera SOLO il codice di un "
    "ambiente tikzpicture (da \\begin{tikzpicture} a \\end{tikzpicture}) che rappresenti "
    "lo schema. NON includere \\documentclass, \\usepackage, figure o didascalie. "
    "Puoi assumere i pacchetti tikz con le librerie arrows.meta e positioning. "
    "Restituisci SOLO codice LaTeX, nessun commento."
)

MERMAID_PROMPT = (
    "Sei un esperto di diagrammi Mermaid. Data una descrizione, genera SOLO il codice "
    "Mermaid (es. flowchart TD, sequenceDiagram, ...), senza backtick né commenti. "
    "Restituisci solo il codice del diagramma."
)

CAPTION_PROMPT = (
    "Genera una didascalia breve e chiara (una sola frase) per la figura descritta, "
    "in {lingua}. Non includere il prefisso «Figura N:». Restituisci SOLO la didascalia."
)

IMAGE_PROMPT_PROMPT = (
    "Sei un assistente che scrive prompt per un generatore di immagini. Data una "
    "richiesta dell'autore e il contesto del libro, scrivi UN prompt in inglese, "
    "dettagliato e descrittivo (soggetto, stile, composizione, illuminazione), adatto "
    "a un modello text-to-image. Restituisci SOLO il prompt, senza virgolette."
)

# --- modalità mentore: feedback, non riscrittura ---
REVIEW_PROMPT = (
    "Sei un mentore di scrittura, non un ghostwriter. Ricevi un brano e fornisci "
    "FEEDBACK per far crescere l'autore: NON riscrivere il testo. Individua al massimo "
    "5 punti migliorabili (chiarezza, struttura, logica, stile, ritmo). Per ciascuno "
    "scrivi una riga nel formato esatto:\n"
    "PROBLEMA: ... | PERCHÉ: ... | SUGGERIMENTO: ...\n"
    "Sii concreto e didattico; spiega il PERCHÉ così l'autore impara. Nessun'altra riga."
)

SOCRATIC_PROMPT = (
    "Sei un mentore socratico. Leggi il brano e poni da 3 a 5 DOMANDE aperte che aiutino "
    "l'autore a sviluppare e rafforzare il pensiero (tesi, prove, pubblico, obiezioni, "
    "esempi). Non dare risposte né riscrivere il testo. Una domanda per riga, senza numeri."
)

CLAIM_PROMPT = (
    "Sei un editor attento al rigore. Elenca le affermazioni FATTUALI del brano che "
    "andrebbero supportate da una fonte o verificate (dati, date, primati, "
    "generalizzazioni). Per ciascuna una riga nel formato:\n"
    "CLAIM: ... | MOTIVO: ...\n"
    "NON inventare fonti e non riscrivere il testo. Solo le righe richieste."
)

ARGMAP_PROMPT = (
    "Sei un mentore che aiuta a strutturare un saggio. Dato titolo, argomento e concetti, "
    "proponi una mappa dell'argomentazione. Usa ESATTAMENTE questo formato, una voce per riga:\n"
    "TESI: <una frase>\n"
    "ARGOMENTO: <affermazione>\n"
    "PROVA: <evidenza a sostegno>\n"
    "OBIEZIONE: <possibile contro-argomento>\n"
    "REPLICA: <risposta all'obiezione>\n"
    "Ripeti ARGOMENTO/PROVA/OBIEZIONE/REPLICA per ogni argomento (2-4 argomenti). "
    "Nessun commento, nessun'altra riga."
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

    def proofread(self, text: str) -> str:
        if not text.strip():
            return text
        a = self._agent("proofreader", PROOFREAD_PROMPT)
        out = a.run(text).text.strip()
        return _strip_code_fences(out) or text

    # -- scrittura assistita (comandi sulla selezione) --------------------
    def edit_text(self, instruction: str, text: str, book: Book | None = None) -> str:
        a = self._agent("editor", EDITOR_PROMPT)
        ctx = ""
        if book is not None:
            ctx = (f"Contesto del libro: «{book.title}» — argomento «{book.topic or book.title}», "
                   f"lingua {book.style.language}.\n\n")
        task = f"{ctx}ISTRUZIONE: {instruction}\n\nBRANO:\n{text}"
        return _strip_code_fences(a.run(task).text.strip())

    def outline(self, book: Book, ch: Chapter) -> str:
        a = self._agent("outliner", OUTLINE_PROMPT)
        task = (f"Libro: «{book.title}» (argomento: {book.topic or book.title}).\n"
                f"Capitolo: «{ch.title}».\n"
                f"Eventuali concetti già annotati:\n{ch.raw_concepts or '(nessuno)'}")
        return a.run(task).text.strip()

    def transitions(self, book: Book, text: str) -> str:
        a = self._agent("transitions", TRANSITIONS_PROMPT)
        return a.run(text).text.strip()

    def bridge(self, book: Book, ch: Chapter, where: str = "next") -> str:
        prev, nxt = book.neighbors(ch.id)
        if where == "prev":
            neighbor, dove = prev, "PRECEDENTE"
        else:
            neighbor, dove = nxt, "SUCCESSIVO"
        if neighbor is None:
            return ""
        a = self._agent("bridge", BRIDGE_PROMPT.format(dove=dove.lower()))
        task = (f"Capitolo corrente «{ch.title}» — riassunto: "
                f"{ch.summary or '(nessun riassunto)'}\n"
                f"Capitolo {dove} «{neighbor.title}» — riassunto: "
                f"{neighbor.summary or '(nessun riassunto)'}")
        return _strip_code_fences(a.run(task).text.strip())

    # -- diagrammi (come codice) ------------------------------------------
    def generate_diagram(self, description: str, kind: str = "tikz",
                         book: Book | None = None) -> str:
        prompt = MERMAID_PROMPT if kind == "mermaid" else TIKZ_PROMPT
        a = self._agent("diagrammer", prompt)
        ctx = f"Contesto: libro «{book.title}».\n\n" if book is not None else ""
        return _strip_code_fences(a.run(ctx + description).text.strip())

    # -- didascalie + prompt per immagini ---------------------------------
    def caption(self, subject: str, book: Book | None = None) -> str:
        lingua = book.style.language if book is not None else "italiano"
        a = self._agent("captioner", CAPTION_PROMPT.format(lingua=lingua))
        return _strip_code_fences(a.run(subject).text.strip())

    def image_prompt(self, request: str, book: Book | None = None) -> str:
        a = self._agent("imageprompter", IMAGE_PROMPT_PROMPT)
        ctx = (f"Contesto: libro «{book.title}» — argomento «{book.topic or book.title}».\n\n"
               if book is not None else "")
        return _strip_code_fences(a.run(ctx + "Richiesta: " + request).text.strip())

    # -- modalità mentore (feedback, non riscrittura) ---------------------
    def review_notes(self, text: str, book: Book | None = None) -> list[dict]:
        a = self._agent("mentor", REVIEW_PROMPT)
        out = a.run(text).text.strip()
        return _parse_review(out)

    def socratic_questions(self, text: str, book: Book | None = None) -> list[str]:
        a = self._agent("socratic", SOCRATIC_PROMPT)
        out = a.run(text).text.strip()
        return [l.strip(" -•*\t") for l in out.splitlines() if l.strip()]

    def claim_notes(self, text: str, book: Book | None = None) -> list[dict]:
        a = self._agent("claims", CLAIM_PROMPT)
        out = a.run(text).text.strip()
        return _parse_claims(out)

    def argument_map(self, book: Book, ch: Chapter) -> str:
        a = self._agent("argmapper", ARGMAP_PROMPT)
        task = (f"Titolo del capitolo: «{ch.title}».\n"
                f"Argomento del libro: «{book.topic or book.title}».\n"
                f"Concetti:\n{ch.raw_concepts or ch.text or '(nessuno)'}")
        return a.run(task).text.strip()


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

    def proofread(self, text: str) -> str:
        # offline: pulizia minima degli spazi, nessuna correzione linguistica
        return re.sub(r"[ \t]{2,}", " ", text).strip()

    # -- scrittura assistita (simulata) -----------------------------------
    def edit_text(self, instruction: str, text: str, book: Book | None = None) -> str:
        clean = re.sub(r"[ \t]{2,}", " ", text).strip()
        return f"% [offline] «{instruction}» applicata a:\n{clean}"

    def outline(self, book: Book, ch: Chapter) -> str:
        base = [c.strip() for c in re.split(r"[\n;.]", ch.raw_concepts) if c.strip()]
        if not base:
            base = ["Introduzione all'argomento", "Concetti chiave",
                    "Esempi e applicazioni", "Implicazioni", "Sintesi"]
        return "\n".join(base[:8])

    def transitions(self, book: Book, text: str) -> str:
        return text  # offline: nessuna modifica ai raccordi

    def bridge(self, book: Book, ch: Chapter, where: str = "next") -> str:
        prev, nxt = book.neighbors(ch.id)
        neighbor = prev if where == "prev" else nxt
        if neighbor is None:
            return ""
        verso = "quanto visto in" if where == "prev" else "quanto vedremo in"
        return (f"Prima di proseguire, conviene collegare questo capitolo a "
                f"{verso} «{neighbor.title}», così da non perdere il filo del discorso.")

    def generate_diagram(self, description: str, kind: str = "tikz",
                         book: Book | None = None) -> str:
        if kind == "mermaid":
            return ("flowchart TD\n"
                    "    A[Inizio] --> B[Elaborazione]\n"
                    "    B --> C[Fine]\n"
                    f"    %% offline: {description[:60]}")
        return ("\\begin{tikzpicture}[>=stealth, node distance=2cm]\n"
                "  \\node (a) [draw, rounded corners] {Inizio};\n"
                "  \\node (b) [draw, rounded corners, right=of a] {Fine};\n"
                "  \\draw[->] (a) -- (b);\n"
                f"  % offline: {description[:60]}\n"
                "\\end{tikzpicture}")

    def caption(self, subject: str, book: Book | None = None) -> str:
        s = subject.strip().rstrip(".")
        return (s[:120] + "…") if len(s) > 120 else (s or "Figura")

    def image_prompt(self, request: str, book: Book | None = None) -> str:
        return f"{request.strip()} — detailed illustration, book figure, clean style"

    # -- modalità mentore (offline: euristiche deterministiche) -----------
    def review_notes(self, text: str, book: Book | None = None) -> list[dict]:
        from ..core.analysis import heuristic_notes
        return [{"issue": n.issue, "detail": n.detail, "suggestion": n.suggestion,
                 "severity": n.severity, "excerpt": n.excerpt, "source": "euristica"}
                for n in heuristic_notes(text)]

    def socratic_questions(self, text: str, book: Book | None = None) -> list[str]:
        return [
            "Qual è la tesi centrale di questo brano, in una frase?",
            "Quali prove o esempi la sostengono?",
            "Che obiezione potrebbe sollevare un lettore critico?",
            "A chi ti stai rivolgendo, e questo testo è adatto a quel pubblico?",
            "Cosa puoi togliere senza perdere il significato?",
        ]

    def claim_notes(self, text: str, book: Book | None = None) -> list[dict]:
        from ..core.analysis import flag_claims
        return [{"text": f.text, "reason": f.reason, "source": "euristica"}
                for f in flag_claims(text)]

    def argument_map(self, book: Book, ch: Chapter) -> str:
        pts = [c.strip() for c in re.split(r"[\n;.]", ch.raw_concepts or ch.text)
               if c.strip()]
        lines = [f"TESI: {ch.title}"]
        for p in pts[:4]:
            lines.append(f"ARGOMENTO: {p}")
            lines.append("PROVA: (aggiungi un'evidenza a sostegno)")
        if len(lines) == 1:
            lines.append("ARGOMENTO: (primo argomento)")
        return "\n".join(lines)


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


def _parse_review(out: str) -> list[dict]:
    """Interpreta le righe «PROBLEMA: ... | PERCHÉ: ... | SUGGERIMENTO: ...»."""
    notes: list[dict] = []
    for line in out.splitlines():
        line = line.strip().lstrip("-•*").strip()
        if "problema" not in line.lower():
            continue
        parts = {p.split(":", 1)[0].strip().lower(): p.split(":", 1)[1].strip()
                 for p in line.split("|") if ":" in p}
        notes.append({
            "issue": parts.get("problema", line),
            "detail": parts.get("perché", parts.get("perche", "")),
            "suggestion": parts.get("suggerimento", ""),
            "severity": "warn", "excerpt": "", "source": "ai",
        })
    return notes


def _parse_claims(out: str) -> list[dict]:
    """Interpreta le righe «CLAIM: ... | MOTIVO: ...»."""
    claims: list[dict] = []
    for line in out.splitlines():
        line = line.strip().lstrip("-•*").strip()
        if "claim" not in line.lower():
            continue
        parts = {p.split(":", 1)[0].strip().lower(): p.split(":", 1)[1].strip()
                 for p in line.split("|") if ":" in p}
        claims.append({"text": parts.get("claim", line),
                       "reason": parts.get("motivo", ""), "source": "ai"})
    return claims
