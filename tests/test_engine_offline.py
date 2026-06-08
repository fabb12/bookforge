"""Test del motore in modalità offline (MockEngine) e dell'autopilota."""
from bookforge.agents.engine import (
    build_engine, EngineConfig, autodraft_book, autodraft_chapter,
    process_chapter, _parse_review, _parse_claims, _accepts_temperature,
)
from bookforge.core.model import Book


def test_temperature_omessa_per_claude_recenti():
    # Opus 4.7+ rifiuta `temperature`: va omessa per evitare l'errore 400
    assert _accepts_temperature("anthropic", "claude-opus-4-8") is False
    assert _accepts_temperature("anthropic", "claude-opus-4-7") is False
    # i modelli che la accettano ancora restano invariati
    assert _accepts_temperature("anthropic", "claude-sonnet-4-6") is True
    assert _accepts_temperature("anthropic", "claude-haiku-4-5-20251001") is True
    assert _accepts_temperature("openai", "gpt-4o-mini") is True
    assert _accepts_temperature("google", "gemini-2.5-pro") is True


def _engine():
    eng, real, _ = build_engine(EngineConfig(provider="anthropic", model="x", api_key=""))
    assert real is False   # senza chiave → offline
    return eng


def test_writing_commands_offline():
    eng = _engine()
    b = Book(title="T", topic="x")
    assert eng.edit_text("Espandi", "Frase.", b)
    assert eng.outline(b, b.add_chapter("C")).strip()
    assert "tikzpicture" in eng.generate_diagram("schema", "tikz", b)
    assert eng.generate_diagram("flusso", "mermaid", b).startswith("flowchart")
    assert eng.caption("una rete", b)
    assert eng.image_prompt("una rete", b)


def test_mentor_commands_offline():
    eng = _engine()
    b = Book(title="T")
    text = "Nel 1995 il 90% degli esperti era d'accordo. " + "parola " * 35 + "."
    assert isinstance(eng.review_notes(text, b), list)
    assert len(eng.socratic_questions(text, b)) >= 3
    assert eng.claim_notes(text, b)  # rileva il claim numerico/temporale


def test_chapter_commands_offline():
    eng = _engine()
    b = Book(title="T")
    c1 = b.add_chapter("Uno"); c1.summary = "s1"; c1.text = "Testo uno."
    c2 = b.add_chapter("Due"); c2.summary = "s2"
    assert eng.transitions(b, c1.text) == c1.text       # offline: identità
    assert eng.bridge(b, c1, "next")                    # esiste il successivo
    assert eng.bridge(b, c1, "prev") == ""              # non esiste il precedente


def test_autodraft_fills_empty_chapters():
    eng = _engine()
    b = Book(title="T", topic="y")
    b.add_chapter("A"); b.add_chapter("B")
    n = autodraft_book(eng, b, only_empty=True)
    assert n == 2
    assert all(c.text.strip() for c in b.chapters)
    # i capitoli senza concetti ricevono una scaletta
    assert all(c.raw_concepts.strip() for c in b.chapters)


def test_autodraft_chapter_runs_pipeline():
    eng = _engine()
    b = Book(title="T")
    ch = b.add_chapter("C")
    autodraft_chapter(eng, b, ch)
    assert ch.text.strip() and ch.latex.strip() and ch.summary.strip()


def test_parse_helpers():
    notes = _parse_review("PROBLEMA: x | PERCHÉ: y | SUGGERIMENTO: z")
    assert notes and notes[0]["issue"] == "x" and notes[0]["suggestion"] == "z"
    claims = _parse_claims("CLAIM: il 90% | MOTIVO: dato")
    assert claims and claims[0]["text"] == "il 90%"
