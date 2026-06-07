"""Test delle impostazioni applicative persistenti (provider/modello/chiavi LLM)."""
from pathlib import Path

from bookforge.core.settings import AppSettings
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
