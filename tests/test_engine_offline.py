"""Test del motore in modalità offline (MockEngine) e dell'autopilota."""
import pytest

from bookforge.agents.engine import (
    build_engine, EngineConfig, autodraft_book, autodraft_chapter,
    process_chapter, _parse_review, _parse_claims, _accepts_temperature,
    GenerationCancelled, friendly_engine_error, LocalEngine, list_local_models,
)
from bookforge.core.model import Book


def test_api_key_normalizzata():
    # spazi e «a capo» incollati per errore romperebbero l'header x-api-key (401)
    cfg = EngineConfig(provider=" Anthropic ", model=" claude-opus-4-8 ",
                       api_key="  sk-ant-abc\n")
    assert cfg.api_key == "sk-ant-abc"
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-opus-4-8"


def test_chiave_di_soli_spazi_resta_offline():
    # una chiave fatta di soli spazi va trattata come assente → MockEngine
    eng, real, _ = build_engine(EngineConfig(provider="anthropic", api_key="   \n"))
    assert real is False


def test_friendly_error_autenticazione():
    msg = friendly_engine_error(Exception(
        "Error code: 401 - {'type': 'authentication_error', "
        "'message': 'invalid x-api-key'}"))
    assert "401" in msg and "Impostazioni" in msg
    # gli altri errori restano invariati
    assert friendly_engine_error(ValueError("boom")) == "boom"


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


def test_book_section_offline():
    eng = _engine()
    b = Book(title="T", topic="argomento")
    for kind in ("premessa", "prologo", "epilogo", "quarta"):
        out = eng.book_section(b, kind)
        assert isinstance(out, str) and out.strip()


def test_progress_callback_can_cancel_pipeline():
    # un callback di progresso che solleva GenerationCancelled interrompe la pipeline
    eng = _engine()
    b = Book(title="T")
    ch = b.add_chapter("C"); ch.raw_concepts = "Un concetto."

    def cancel(_msg):
        raise GenerationCancelled()

    with pytest.raises(GenerationCancelled):
        process_chapter(eng, b, ch, progress=cancel)


def test_friendly_error_server_locale_giu():
    import urllib.error
    msg = friendly_engine_error(urllib.error.URLError("Connection refused"))
    assert "locale" in msg.lower() and "11434" in msg


def test_build_engine_locale_senza_chiave_e_reale():
    # un provider locale non richiede chiave: il motore reale deve attivarsi
    eng, real, msg = build_engine(
        EngineConfig(provider="ollama", model="llama3.1:8b"))
    assert real is True
    assert isinstance(eng, LocalEngine)
    assert "Ollama" in msg


def test_build_engine_locale_senza_modello_ripiega_offline():
    eng, real, _ = build_engine(EngineConfig(provider="lmstudio", model=""))
    assert real is False  # senza modello non si può procedere → MockEngine


def test_local_engine_usa_endpoint_predefinito():
    eng = LocalEngine(EngineConfig(provider="ollama", model="llama3.1:8b"))
    assert eng._base_url == "http://localhost:11434/v1"
    eng2 = LocalEngine(EngineConfig(provider="lmstudio", model="x"))
    assert eng2._base_url == "http://localhost:1234/v1"


@pytest.fixture
def _local_server():
    """Server fittizio OpenAI-compatibile per testare LocalEngine senza rete reale."""
    import json, threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silenzia il log del server di test
            pass

        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # /models
            self._send({"data": [{"id": "llama3.1:8b"}, {"id": "mistral"}]})

        def do_POST(self):  # /chat/completions: fa l'eco dell'ultimo messaggio
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n))
            last = req["messages"][-1]["content"]
            self._send({"choices": [{"message": {"content": "ECO " + last}}]})

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1"
    srv.shutdown()


def test_local_engine_pipeline_contro_server_fittizio(_local_server):
    eng = LocalEngine(EngineConfig(
        provider="ollama", model="llama3.1:8b", base_url=_local_server))
    b = Book(title="T", topic="x")
    ch = b.add_chapter("Cap"); ch.raw_concepts = "Un concetto."
    out = eng.write(b, ch)
    assert out.startswith("ECO ") and "Cap" in out
    # la pipeline completa gira interamente sull'endpoint locale
    autodraft_chapter(eng, b, ch)
    assert ch.text.strip() and ch.latex.strip() and ch.summary.strip()


def test_list_local_models(_local_server):
    assert list_local_models(_local_server) == ["llama3.1:8b", "mistral"]
    # server irraggiungibile → lista vuota, nessuna eccezione
    assert list_local_models("http://127.0.0.1:1/v1", timeout=0.5) == []


def test_parse_helpers():
    notes = _parse_review("PROBLEMA: x | PERCHÉ: y | SUGGERIMENTO: z")
    assert notes and notes[0]["issue"] == "x" and notes[0]["suggestion"] == "z"
    claims = _parse_claims("CLAIM: il 90% | MOTIVO: dato")
    assert claims and claims[0]["text"] == "il 90%"
