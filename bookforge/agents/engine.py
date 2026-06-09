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

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from ..core import image_gen
from ..core.model import Book, Chapter
from ..core.settings import LOCAL_PROVIDERS, default_base_url


class GenerationCancelled(Exception):
    """Sollevata per interrompere in modo cooperativo la pipeline di generazione.

    I worker della GUI passano un callback di `progress` che la solleva quando
    l'utente preme «Interrompi»: la pipeline si ferma al successivo confine di passo
    senza lasciare il modello in uno stato incoerente.
    """


# ---------------------------------------------------------------- client factory
def _accepts_temperature(provider: str, model: str) -> bool:
    """Indica se il modello accetta il parametro `temperature`.

    Anthropic ha rimosso i parametri di campionamento (temperature/top_p/top_k)
    a partire da Claude Opus 4.7: passarli a questi modelli causa un errore
    `invalid_request_error` («temperature is deprecated for this model»).
    Per gli altri provider/modelli il parametro resta valido.
    """
    if provider == "anthropic":
        m = re.search(r"opus-4-(\d+)", model or "")
        if m and int(m.group(1)) >= 7:
            return False
    return True


def _make_client(provider: str, api_key: str, model: str,
                 temperature: float | None = None, max_tokens: int = 0):
    provider = provider.lower()
    # ulteriore rete di sicurezza: la chiave deve arrivare pulita all'header HTTP
    # (vedi EngineConfig.__post_init__) anche se _make_client viene chiamato altrove.
    api_key = (api_key or "").strip()
    if provider == "openai":
        from datapizza.clients.openai import OpenAIClient as Cls
        model = model or "gpt-4o-mini"
    elif provider == "anthropic":
        from datapizza.clients.anthropic import AnthropicClient as Cls
        model = model or "claude-opus-4-8"
    elif provider == "google":
        from datapizza.clients.google import GoogleClient as Cls
        model = model or "gemini-2.5-pro"
    else:
        raise ValueError(f"Provider non supportato: {provider}")
    # i parametri di campionamento sono opzionali: alcuni client non li accettano,
    # in quel caso si ripiega sulla costruzione minimale. La `temperature` viene
    # omessa anche per i modelli che la rifiutano (es. Claude Opus 4.7+).
    extra: dict = {}
    if temperature is not None and _accepts_temperature(provider, model):
        extra["temperature"] = temperature
    if max_tokens:
        extra["max_tokens"] = max_tokens
    try:
        return Cls(api_key=api_key, model=model, **extra)
    except TypeError:
        return Cls(api_key=api_key, model=model)


@dataclass
class EngineConfig:
    provider: str = "anthropic"
    model: str = "claude-opus-4-8"
    api_key: str = ""
    base_url: str = ""          # endpoint per i provider locali (Ollama/LM Studio)
    temperature: float = 0.7
    max_tokens: int = 0

    def __post_init__(self):
        # Normalizza la chiave: spazi e «a capo» invisibili (tipici di un copia-incolla
        # o di `export KEY=$(cat file)`) finirebbero nell'header `x-api-key` e farebbero
        # rifiutare la chiave dal provider con un 401 «invalid x-api-key». Qui passano
        # tutte le sorgenti (env, impostazioni, dialog), quindi la pulizia è centralizzata.
        if self.api_key:
            self.api_key = self.api_key.strip()
        if self.provider:
            self.provider = self.provider.strip().lower()
        if self.model:
            self.model = self.model.strip()
        if self.base_url:
            self.base_url = self.base_url.strip()

    @property
    def is_local(self) -> bool:
        """Indica se la configurazione punta a un motore locale."""
        return self.provider in LOCAL_PROVIDERS

    @staticmethod
    def from_env() -> "EngineConfig":
        return EngineConfig(
            provider=os.getenv("BOOKFORGE_PROVIDER", "anthropic"),
            model=os.getenv("BOOKFORGE_MODEL", "claude-opus-4-8"),
            api_key=os.getenv("BOOKFORGE_API_KEY", "")
                    or os.getenv("ANTHROPIC_API_KEY", "")
                    or os.getenv("OPENAI_API_KEY", "")
                    or os.getenv("GOOGLE_API_KEY", ""),
            base_url=os.getenv("BOOKFORGE_BASE_URL", ""),
        )

    @staticmethod
    def from_settings(settings) -> "EngineConfig":
        """Costruisce la configurazione dalle impostazioni persistenti.

        La chiave del provider scelto ha la precedenza; se manca, si ripiega
        sulle variabili d'ambiente (così l'avvio resta comodo da terminale).
        """
        # per i provider locali la chiave non serve: conta l'endpoint.
        key = settings.api_key_for() or EngineConfig.from_env().api_key
        return EngineConfig(
            provider=settings.provider,
            model=settings.model,
            api_key=key,
            base_url=settings.base_url_for(),
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
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

# Le infografiche non illustrano una scena: organizzano *il contenuto* del testo.
# Il prompt va quindi scritto in modo da estrarre i punti chiave e da imporre la
# lingua delle scritte (deve coincidere con quella del libro).
INFOGRAPHIC_PROMPT_PROMPT = (
    "Sei un assistente che progetta infografiche. Dal testo dell'autore estrai i "
    "concetti chiave, i dati, i passaggi o le relazioni e scrivi UN prompt in inglese "
    "per un generatore di immagini che produca un'infografica DETTAGLIATA e FEDELE al "
    "contenuto: sezioni etichettate, titoli, brevi didascalie, icone e, dove utile, "
    "frecce o numeri di sequenza. Descrivi quali testi compaiono e dove. "
    "VINCOLO IMPORTANTE: tutte le scritte, le etichette e i titoli dell'infografica "
    "devono essere in {lingua} (riporta nel prompt il testo esatto in {lingua}). "
    "Restituisci SOLO il prompt, senza virgolette."
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

# --- sezioni speciali del libro (premessa, prologo, epilogo, quarta di copertina) ---
SECTION_PROMPTS = {
    "premessa": (
        "Scrivi la PREMESSA di un saggio: una pagina in cui l'autore spiega l'origine "
        "del libro, le motivazioni e il patto col lettore. Tono personale ma sobrio."),
    "prologo": (
        "Scrivi un PROLOGO che introduca il lettore nel mondo del libro con un'immagine, "
        "una scena o una domanda forte, anticipando il tema senza esaurirlo."),
    "epilogo": (
        "Scrivi un EPILOGO che chiuda il libro: tira le fila del percorso, lascia al "
        "lettore un pensiero conclusivo e un'apertura. Non riassumere capitolo per capitolo."),
    "quarta": (
        "Scrivi il testo della QUARTA DI COPERTINA: 2-4 frasi promozionali che incuriosiscano "
        "il lettore e sintetizzino il valore del libro. Niente spoiler, niente titoli."),
}

SECTION_PROMPT_BASE = (
    "Sei un autore professionista che scrive in {lingua}. {compito}\n"
    "Restituisci SOLO il testo in prosa, senza intestazioni, virgolette o commenti."
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
        self._client = _make_client(config.provider, config.api_key, config.model,
                                    temperature=config.temperature,
                                    max_tokens=config.max_tokens)

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

    def image_prompt(self, request: str, book: Book | None = None,
                     style: str = "") -> str:
        lingua = book.style.language if book is not None else "italiano"
        # Le infografiche (e gli stili con testo) richiedono un prompt costruito sul
        # contenuto e nella lingua del libro: scelgo il system prompt di conseguenza.
        if image_gen.style_needs_text(style):
            sys = INFOGRAPHIC_PROMPT_PROMPT.format(lingua=lingua)
        else:
            sys = IMAGE_PROMPT_PROMPT
        a = self._agent("imageprompter", sys)
        ctx = (f"Contesto: libro «{book.title}» — argomento «{book.topic or book.title}».\n\n"
               if book is not None else "")
        base = _strip_code_fences(a.run(ctx + "Richiesta: " + request).text.strip())
        # Rinforzo deterministico: stile + vincolo di lingua per le scritte.
        return image_gen.compose_prompt(base, style, lingua)

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
        from ..core.analysis import readable_text
        a = self._agent("argmapper", ARGMAP_PROMPT)
        # se mancano i concetti, lavora sul risultato finale (LaTeX ripulito o prosa)
        content = ch.raw_concepts or readable_text(ch.text, ch.latex) or "(nessuno)"
        task = (f"Titolo del capitolo: «{ch.title}».\n"
                f"Argomento del libro: «{book.topic or book.title}».\n"
                f"Concetti:\n{content}")
        return a.run(task).text.strip()

    # -- sezioni speciali (premessa/prologo/epilogo/quarta) ----------------
    def book_section(self, book: Book, kind: str) -> str:
        compito = SECTION_PROMPTS.get(kind, SECTION_PROMPTS["premessa"])
        prompt = SECTION_PROMPT_BASE.format(lingua=book.style.language, compito=compito)
        a = self._agent("sectioner", prompt)
        task = (f"Libro: «{book.title}»"
                + (f" — «{book.subtitle}»" if book.subtitle else "")
                + f"\nArgomento: «{book.topic or book.title}».\n"
                f"Abstract: {book.abstract or '(nessuno)'}.")
        return _strip_code_fences(a.run(task).text.strip())


# ---------------------------------------------------------------- motori locali
class _LocalResponse:
    """Risposta minimale compatibile con quanto si aspetta `DatapizzaEngine`."""
    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


class _LocalAgent:
    """Agente per endpoint OpenAI-compatibili (Ollama, LM Studio).

    Replica l'unica interfaccia che la pipeline usa — `.run(task).text` — ma parla
    con l'endpoint `/chat/completions` via `urllib` (libreria standard): nessuna
    dipendenza esterna, così i modelli locali funzionano anche senza `datapizza`
    installato. I server locali NON espongono la Responses API di OpenAI, quindi
    qui si usa apposta il vecchio contratto `chat/completions` che entrambi servono.
    """

    def __init__(self, base_url: str, model: str, system_prompt: str,
                 temperature: float | None = None, max_tokens: int = 0,
                 timeout: float = 600.0):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._system = system_prompt
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

    def run(self, task: str) -> _LocalResponse:
        messages = []
        if self._system:
            messages.append({"role": "system", "content": self._system})
        messages.append({"role": "user", "content": task})
        payload: dict = {"model": self._model, "messages": messages, "stream": False}
        if self._temperature is not None:
            payload["temperature"] = self._temperature
        if self._max_tokens:
            payload["max_tokens"] = self._max_tokens
        data = json.dumps(payload).encode("utf-8")
        # l'header Authorization è ignorato dai server locali ma li tiene felici
        req = urllib.request.Request(
            self._url, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer local"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body["choices"][0]["message"].get("content") or ""
        return _LocalResponse(text.strip())


class LocalEngine(DatapizzaEngine):
    """Motore per modelli locali (Ollama, LM Studio) via API OpenAI-compatibile.

    Eredita l'intera pipeline di `DatapizzaEngine`: l'unica differenza è la fonte
    delle risposte, fornita da `_LocalAgent` al posto degli agenti `datapizza`.
    Così la parità dei metodi resta automatica (regola d'oro #5) e non serve
    duplicare la logica di scrittura/coerenza/formattazione.
    """

    def __init__(self, config: EngineConfig):
        # niente import di datapizza né client reale: si parla HTTP col server locale.
        self.config = config
        self._base_url = (config.base_url or default_base_url(config.provider)
                          or "http://localhost:11434/v1")
        if not (config.model or "").strip():
            raise ValueError(
                "Specifica il modello locale da usare (es. llama3.1:8b per Ollama).")

    def _agent(self, name: str, system_prompt: str):
        return _LocalAgent(self._base_url, self.config.model, system_prompt,
                           temperature=self.config.temperature,
                           max_tokens=self.config.max_tokens)


def list_local_models(base_url: str, timeout: float = 3.0) -> list[str]:
    """Interroga l'endpoint `/models` di un server locale OpenAI-compatibile.

    Restituisce gli identificativi dei modelli disponibili, o una lista vuota se
    il server non risponde: così la GUI può proporli senza farli digitare a mano,
    senza però rompersi se Ollama/LM Studio non sono in esecuzione.
    """
    url = base_url.rstrip("/") + "/models"
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer local"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - server spento o irraggiungibile: nessun modello
        return []
    data = body.get("data") if isinstance(body, dict) else None
    ids = [m.get("id") for m in (data or [])
           if isinstance(m, dict) and m.get("id")]
    return [i for i in ids if i]


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

    def image_prompt(self, request: str, book: Book | None = None,
                     style: str = "") -> str:
        lingua = book.style.language if book is not None else "italiano"
        if image_gen.style_needs_text(style):
            base = f"detailed infographic about: {request.strip()}, labeled sections"
        else:
            base = f"{request.strip()} — detailed illustration, book figure, clean style"
        return image_gen.compose_prompt(base, style, lingua)

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
        from ..core.analysis import readable_text
        src = ch.raw_concepts or readable_text(ch.text, ch.latex)
        pts = [c.strip() for c in re.split(r"[\n;.]", src) if c.strip()]
        lines = [f"TESI: {ch.title}"]
        for p in pts[:4]:
            lines.append(f"ARGOMENTO: {p}")
            lines.append("PROVA: (aggiungi un'evidenza a sostegno)")
        if len(lines) == 1:
            lines.append("ARGOMENTO: (primo argomento)")
        return "\n".join(lines)

    # -- sezioni speciali (offline: bozza deterministica) ------------------
    def book_section(self, book: Book, kind: str) -> str:
        nomi = {"premessa": "premessa", "prologo": "prologo",
                "epilogo": "epilogo", "quarta": "quarta di copertina"}
        nome = nomi.get(kind, kind)
        tema = book.topic or book.title
        if kind == "quarta":
            return (f"«{book.title}» accompagna il lettore dentro {tema}, "
                    f"tra domande aperte e prospettive nuove. Un percorso per "
                    f"chi vuole capire più a fondo.")
        return (f"[bozza offline — {nome}] In queste pagine, dedicate al libro "
                f"«{book.title}», l'autore prepara il terreno al tema di {tema}. "
                f"Sostituisci questo testo con la tua {nome}, oppure rigenerala con "
                f"un motore AI reale.")


# ---------------------------------------------------------------- orchestrazione
# pacchetto pip del client per ciascun provider (per messaggi d'errore utili)
_PROVIDER_PACKAGES = {
    "anthropic": "datapizza-ai-clients-anthropic",
    "openai": "datapizza-ai-clients-openai",
    "google": "datapizza-ai-clients-google",
}


def build_engine(config: EngineConfig, force_offline: bool = False):
    """Restituisce (engine, is_real, message)."""
    if force_offline:
        return MockEngine(), False, "Modalità offline forzata: testo simulato."
    # provider locali (Ollama/LM Studio): non serve una chiave, serve l'endpoint.
    if config.is_local:
        try:
            eng = LocalEngine(config)
        except Exception as e:  # es. modello non specificato
            return MockEngine(), False, f"Fallback offline ({e})."
        nome = "Ollama" if config.provider == "ollama" else "LM Studio"
        return eng, True, (f"Motore locale {nome} attivo "
                           f"({eng._base_url}, modello {config.model}). "
                           f"Assicurati che il server sia in esecuzione.")
    if not config.api_key:
        return MockEngine(), False, "Modalità offline (nessuna API key): testo simulato."
    try:
        eng = DatapizzaEngine(config)
        return eng, True, f"Motore datapizza-ai attivo ({config.provider}/{config.model})."
    except ModuleNotFoundError as e:
        # tipicamente manca il client del provider scelto (es. datapizza.clients.google)
        pkg = _PROVIDER_PACKAGES.get((config.provider or "").lower())
        hint = (f" Installa il client del provider:  pip install {pkg}" if pkg
                else " Installa il client del provider.")
        return MockEngine(), False, f"Fallback offline ({e}).{hint}"
    except Exception as e:  # altra libreria mancante o errore di init
        return MockEngine(), False, f"Fallback offline ({e})."


def autodraft_chapter(engine, book: Book, ch: Chapter,
                      progress: Callable[[str], None] | None = None) -> Chapter:
    """Autopilota: genera un capitolo con il minimo sforzo, mantenendo lo stile.

    Se mancano i concetti, ne ricava prima una scaletta (così resta traccia) e
    poi esegue l'intera pipeline. Lo stile è quello del prompt impostato sul libro.
    """
    def step(msg):
        if progress:
            progress(msg)
    if not ch.raw_concepts.strip():
        step("Ricavo una scaletta dal titolo…")
        try:
            ch.raw_concepts = engine.outline(book, ch)
        except Exception:  # noqa: BLE001 - se fallisce, prosegui comunque
            pass
    return process_chapter(engine, book, ch, progress)


def autodraft_book(engine, book: Book, only_empty: bool = True,
                   progress: Callable[[str], None] | None = None) -> int:
    """Autopilota su tutto il libro. Restituisce il numero di capitoli generati."""
    done = 0
    targets = [c for c in book.chapters if (not only_empty or not c.text.strip())]
    for i, ch in enumerate(targets, 1):
        if progress:
            progress(f"[{i}/{len(targets)}] «{ch.title}»…")
        autodraft_chapter(engine, book, ch, progress)
        done += 1
    return done


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


def friendly_engine_error(exc: Exception) -> str:
    """Traduce un errore del provider LLM in un messaggio chiaro in italiano.

    In particolare riconosce l'errore di autenticazione (HTTP 401 / `x-api-key`
    non valida) e suggerisce all'utente come rimediare, invece di mostrare il
    tracciato grezzo dell'API.
    """
    msg = str(exc)
    low = msg.lower()
    if ("connection refused" in low or "failed to establish" in low
            or "actively refused" in low or "max retries" in low
            or "urlopen error" in low or "name or service not known" in low
            or isinstance(exc, (urllib.error.URLError, ConnectionError))
            and "401" not in low):
        return ("Server locale non raggiungibile: avvia Ollama o LM Studio e "
                "verifica l'endpoint in ⚙ Impostazioni (es. "
                "http://localhost:11434/v1 per Ollama, "
                "http://localhost:1234/v1 per LM Studio).")
    if ("401" in low or "authentication" in low or "invalid x-api-key" in low
            or "invalid api key" in low or "unauthorized" in low):
        return ("Chiave API non valida o assente: il provider ha rifiutato "
                "l'autenticazione (401). Controlla la chiave in ⚙ Impostazioni "
                "(occhio a spazi o «a capo» incollati per errore) e che corrisponda "
                "al provider selezionato.")
    return msg


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
