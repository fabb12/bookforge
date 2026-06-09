"""Test delle impostazioni applicative persistenti (provider/modello/chiavi LLM)."""
from pathlib import Path

from bookforge.core.settings import (
    AppSettings, AVAILABLE_MODELS, PROVIDERS, models_for, model_label,
    MODEL_LABELS, DEFAULT_MODELS, MAX_RECENT_PROJECTS,
    LOCAL_PROVIDERS, DEFAULT_BASE_URLS, is_local, default_base_url,
)
from bookforge.agents.engine import EngineConfig


def test_roundtrip_su_file(tmp_path: Path):
    path = tmp_path / "settings.json"
    s = AppSettings(provider="openai", model="gpt-4o", temperature=0.3, max_tokens=2048)
    s.set_api_key("openai", "sk-test")
    s.save(path)
    loaded = AppSettings.load(path)
    assert loaded.provider == "openai"
    assert loaded.model == "gpt-4o"
    assert loaded.temperature == 0.3
    assert loaded.max_tokens == 2048
    assert loaded.api_key_for("openai") == "sk-test"


def test_from_dict_tollerante():
    s = AppSettings.from_dict({"provider": "google", "sconosciuto": 1, "api_keys": None})
    assert s.provider == "google"
    assert s.api_keys == {}


def test_load_assente_da_default(tmp_path: Path):
    s = AppSettings.load(tmp_path / "non_esiste.json")
    assert s.provider == "anthropic"


def test_modello_ritirato_viene_rimappato():
    # i Gemini 1.5 sono ritirati: una config salvata su di essi va aggiornata
    s = AppSettings.from_dict({"provider": "google", "model": "gemini-1.5-pro"})
    assert s.model == "gemini-2.5-pro"


def test_set_api_key_rimuove_se_vuota():
    s = AppSettings()
    s.set_api_key("anthropic", "k")
    assert s.api_key_for("anthropic") == "k"
    s.set_api_key("anthropic", "")
    assert "anthropic" not in s.api_keys


def test_engine_config_da_settings():
    s = AppSettings(provider="openai", model="gpt-4o", temperature=0.5, max_tokens=100)
    s.set_api_key("openai", "sk-abc")
    cfg = EngineConfig.from_settings(s)
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4o"
    assert cfg.api_key == "sk-abc"
    assert cfg.temperature == 0.5
    assert cfg.max_tokens == 100


def test_models_for_copre_i_provider():
    for p in PROVIDERS:
        assert p in AVAILABLE_MODELS
        modelli = models_for(p)
        assert modelli and isinstance(modelli, list)
    # provider sconosciuto → lista vuota, non un errore
    assert models_for("inesistente") == []


def test_model_label_leggibile_o_fallback():
    # i modelli noti hanno un nome leggibile diverso dall'id tecnico
    assert model_label("claude-opus-4-8") == MODEL_LABELS["claude-opus-4-8"]
    assert model_label("claude-opus-4-8") != "claude-opus-4-8"
    # un id sconosciuto ripiega su se stesso, senza errori
    assert model_label("modello-misterioso") == "modello-misterioso"


def test_default_models_hanno_etichetta():
    # ogni modello consigliato dev'essere etichettato e in elenco per il provider
    for provider, mid in DEFAULT_MODELS.items():
        assert mid in MODEL_LABELS
        assert mid in models_for(provider)


def test_recent_projects_ordine_e_dedup(tmp_path: Path):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    s = AppSettings()
    s.add_recent_project(a)
    s.add_recent_project(b)
    s.add_recent_project(a)          # ri-aperto: torna in cima senza duplicati
    assert s.recent_projects[0] == str(a.resolve())
    assert s.recent_projects.count(str(a.resolve())) == 1
    assert len(s.recent_projects) == 2


def test_recent_projects_limite(tmp_path: Path):
    s = AppSettings()
    for i in range(MAX_RECENT_PROJECTS + 3):
        d = tmp_path / f"p{i}"; d.mkdir()
        s.add_recent_project(d)
    assert len(s.recent_projects) == MAX_RECENT_PROJECTS


def test_recent_projects_clean_rimuove_inesistenti(tmp_path: Path):
    esiste = tmp_path / "vivo"; esiste.mkdir()
    s = AppSettings(recent_projects=[str(esiste), str(tmp_path / "fantasma")])
    assert s.clean_recent_projects() == [str(esiste)]


def test_provider_locali_in_elenco():
    # i provider locali sono supportati e hanno modello/endpoint predefiniti
    for p in LOCAL_PROVIDERS:
        assert p in PROVIDERS
        assert is_local(p)
        assert p in DEFAULT_MODELS and DEFAULT_MODELS[p] in models_for(p)
        assert DEFAULT_BASE_URLS[p].startswith("http")
    # i provider cloud non sono locali
    assert not is_local("anthropic")
    assert default_base_url("anthropic") == ""


def test_base_url_default_e_override():
    s = AppSettings(provider="ollama")
    # senza override usa il predefinito del provider
    assert s.base_url_for("ollama") == DEFAULT_BASE_URLS["ollama"]
    # un endpoint personalizzato viene memorizzato e riletto
    s.set_base_url("ollama", "http://192.168.1.10:11434/v1")
    assert s.base_url_for("ollama") == "http://192.168.1.10:11434/v1"
    # impostare il predefinito non sporca il dizionario (resta pulito)
    s.set_base_url("ollama", DEFAULT_BASE_URLS["ollama"])
    assert "ollama" not in s.base_urls


def test_base_urls_roundtrip_e_tolleranza(tmp_path: Path):
    path = tmp_path / "settings.json"
    s = AppSettings(provider="lmstudio", model="local-model")
    s.set_base_url("lmstudio", "http://localhost:9999/v1")
    s.save(path)
    loaded = AppSettings.load(path)
    assert loaded.base_url_for("lmstudio") == "http://localhost:9999/v1"
    # from_dict tollera base_urls assente o di tipo errato
    assert AppSettings.from_dict({"base_urls": None}).base_urls == {}


def test_engine_config_locale_porta_endpoint():
    s = AppSettings(provider="ollama", model="llama3.1:8b")
    s.set_base_url("ollama", "http://host:11434/v1")
    cfg = EngineConfig.from_settings(s)
    assert cfg.provider == "ollama"
    assert cfg.is_local
    assert cfg.base_url == "http://host:11434/v1"


def test_recent_projects_roundtrip(tmp_path: Path):
    d = tmp_path / "proj"; d.mkdir()
    path = tmp_path / "settings.json"
    s = AppSettings()
    s.add_recent_project(d)
    s.save(path)
    assert AppSettings.load(path).recent_projects == [str(d.resolve())]
