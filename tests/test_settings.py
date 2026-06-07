"""Test delle impostazioni applicative persistenti (provider/modello/chiavi LLM)."""
from pathlib import Path

from bookforge.core.settings import (
    AppSettings, AVAILABLE_MODELS, PROVIDERS, models_for, MAX_RECENT_PROJECTS,
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


def test_recent_projects_roundtrip(tmp_path: Path):
    d = tmp_path / "proj"; d.mkdir()
    path = tmp_path / "settings.json"
    s = AppSettings()
    s.add_recent_project(d)
    s.save(path)
    assert AppSettings.load(path).recent_projects == [str(d.resolve())]
