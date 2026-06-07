"""Analisi del testo: metriche di leggibilità, note di stile, segnalazione claim.

Tutto qui è *puro e deterministico* (nessuna chiamata di rete), così alimenta sia
la Modalità Mentore offline sia la Dashboard di crescita, ed è facilmente testabile.
Il motore AI può aggiungere note più ricche sopra a queste euristiche.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, asdict


# ------------------------------------------------------------------ dati
@dataclass
class Note:
    """Una nota di revisione: problema + spiegazione didattica + suggerimento."""
    issue: str
    detail: str = ""
    suggestion: str = ""
    severity: str = "info"        # info | warn
    excerpt: str = ""
    source: str = "euristica"     # euristica | ai


@dataclass
class ClaimFlag:
    """Un'affermazione fattuale che andrebbe citata o verificata."""
    text: str
    reason: str = ""
    source: str = "euristica"


@dataclass
class TextMetrics:
    words: int = 0
    sentences: int = 0
    chars_letters: int = 0
    avg_sentence_len: float = 0.0
    long_sentences: int = 0
    gulpease: float = 0.0
    lexical_diversity: float = 0.0
    passive_ratio: float = 0.0
    adverb_ratio: float = 0.0
    filler_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ costanti
_FILLERS = (
    "inoltre", "infatti", "ovviamente", "chiaramente", "sostanzialmente",
    "praticamente", "in realtà", "di fatto", "come detto", "appunto",
    "in effetti", "per così dire", "a dire il vero",
)
_STOPWORDS = set(
    "il lo la i gli le un uno una di a da in con su per tra fra e o ma se che "
    "non come più meno molto poco questo quello sono è era ha hanno del della "
    "dei delle al alla ai alle dal dalla nel nella sul sulla si ci ne anche "
    "quando dove perché mentre quindi cioè ossia ovvero".split()
)
_PASSIVE_RE = re.compile(
    r"\b(è|sono|era|erano|fu|furono|sarà|saranno|viene|vengono|venne|vennero|"
    r"venuto|stato|stati|state|stata)\s+\w+(ato|ata|ati|ate|ito|ita|iti|ite|uto|uta|uti|ute)\b",
    re.IGNORECASE,
)
_SUPERLATIVE_RE = re.compile(
    r"\b(il più|la più|i più|le più|sempre|mai|tutti|tutte|nessuno|nessuna|"
    r"il primo|la prima|l'unico|l'unica|ogni|qualsiasi|dimostra che|prova che)\b",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\b\d+([.,]\d+)?\s*%?\b")
_YEAR_RE = re.compile(r"\b(1[89]\d\d|20\d\d)\b")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿ']+", text)


# ------------------------------------------------------------------ metriche
def analyze(text: str) -> TextMetrics:
    text = (text or "").strip()
    if not text:
        return TextMetrics()
    sents = _sentences(text)
    words = _words(text)
    n_words = len(words)
    n_sents = max(1, len(sents))
    letters = sum(1 for c in text if c.isalpha())

    # Gulpease (italiano): 89 + (300*frasi - 10*lettere) / parole. 0..100, alto=facile
    gulpease = 89 + (300 * n_sents - 10 * letters) / max(1, n_words)
    gulpease = max(0.0, min(100.0, gulpease))

    lower = [w.lower() for w in words]
    content = [w for w in lower if w not in _STOPWORDS and len(w) > 2]
    diversity = (len(set(content)) / len(content)) if content else 0.0

    passive = len(_PASSIVE_RE.findall(text))
    adverbs = sum(1 for w in lower if w.endswith("mente") and len(w) > 6)
    fillers = sum(lower.count(f) for f in _FILLERS if " " not in f) + \
        sum(text.lower().count(f) for f in _FILLERS if " " in f)
    long_s = sum(1 for s in sents if len(_words(s)) > 30)

    return TextMetrics(
        words=n_words,
        sentences=len(sents),
        chars_letters=letters,
        avg_sentence_len=round(n_words / n_sents, 1),
        long_sentences=long_s,
        gulpease=round(gulpease, 1),
        lexical_diversity=round(diversity, 3),
        passive_ratio=round(passive / n_sents, 3),
        adverb_ratio=round(adverbs / max(1, n_words), 3),
        filler_count=fillers,
    )


def gulpease_label(g: float) -> str:
    if g >= 80:
        return "molto facile"
    if g >= 60:
        return "facile"
    if g >= 40:
        return "medio"
    return "difficile"


# ------------------------------------------------------------------ note di stile
def heuristic_notes(text: str, metrics: TextMetrics | None = None) -> list[Note]:
    text = (text or "").strip()
    if not text:
        return []
    m = metrics or analyze(text)
    notes: list[Note] = []

    if m.long_sentences:
        ex = next((s for s in _sentences(text) if len(_words(s)) > 30), "")
        notes.append(Note(
            issue=f"{m.long_sentences} frase/i molto lunga/e (>30 parole)",
            detail="Le frasi lunghe affaticano la lettura e nascondono il filo logico.",
            suggestion="Spezza in due o tre frasi più brevi, una idea per frase.",
            severity="warn", excerpt=ex[:160]))

    if m.passive_ratio > 0.25:
        notes.append(Note(
            issue=f"Uso elevato del passivo (~{int(m.passive_ratio*100)}% delle frasi)",
            detail="La forma attiva è più diretta e chiara, specie nella saggistica.",
            suggestion="Riporta il soggetto che compie l'azione: «X ha mostrato…» invece di «è stato mostrato…».",
            severity="warn"))

    if m.adverb_ratio > 0.03:
        notes.append(Note(
            issue="Molti avverbi in «-mente»",
            detail="Gli avverbi in -mente spesso indeboliscono il verbo o sono superflui.",
            suggestion="Scegli un verbo più preciso invece di verbo + avverbio.",
            severity="info"))

    if m.filler_count >= 3:
        notes.append(Note(
            issue=f"{m.filler_count} riempitivi/connettivi abusati",
            detail="Parole come «inoltre», «ovviamente», «in realtà» raramente aggiungono significato.",
            suggestion="Eliminali o sostituiscili con un nesso logico concreto.",
            severity="info"))

    if m.words >= 60 and m.lexical_diversity < 0.45:
        notes.append(Note(
            issue="Varietà lessicale bassa",
            detail="Molte ripetizioni delle stesse parole rendono il testo monotono.",
            suggestion="Varia i termini o riformula le frasi ripetitive.",
            severity="info"))

    for word, count in repeated_words(text):
        notes.append(Note(
            issue=f"«{word}» ripetuto {count} volte",
            detail="Una parola di contenuto ripetuta spesso salta all'occhio.",
            suggestion="Usa sinonimi o riformula alcune occorrenze.",
            severity="info"))

    if m.gulpease < 40:
        notes.append(Note(
            issue=f"Leggibilità difficile (Gulpease {m.gulpease})",
            detail="Indice Gulpease basso: il testo richiede uno sforzo di lettura alto.",
            suggestion="Accorcia le frasi e usa parole più comuni dove possibile.",
            severity="warn"))
    return notes


def repeated_words(text: str, top: int = 3, min_count: int = 4) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for w in _words(text):
        lw = w.lower()
        if len(lw) > 4 and lw not in _STOPWORDS:
            counts[lw] = counts.get(lw, 0) + 1
    ranked = sorted(((w, c) for w, c in counts.items() if c >= min_count),
                    key=lambda x: -x[1])
    return ranked[:top]


# ------------------------------------------------------------------ claim
def flag_claims(text: str) -> list[ClaimFlag]:
    """Segnala affermazioni fattuali che andrebbero citate/verificate (euristica)."""
    flags: list[ClaimFlag] = []
    for s in _sentences(text or ""):
        reasons = []
        if _NUMBER_RE.search(s):
            reasons.append("contiene dati numerici")
        if _YEAR_RE.search(s):
            reasons.append("riferimento temporale/storico")
        if _SUPERLATIVE_RE.search(s):
            reasons.append("affermazione assoluta o generalizzante")
        if reasons:
            flags.append(ClaimFlag(text=s.strip()[:200],
                                   reason="; ".join(reasons)))
    return flags
