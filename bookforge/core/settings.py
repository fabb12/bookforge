"""Impostazioni applicative persistenti: provider, modello e chiavi API dei LLM.

Puro rispetto all'architettura: fa solo I/O su un file JSON locale, niente rete
né PyQt. Le chiavi sono memorizzate per-provider, così l'utente può configurarle
una volta sola e cambiare modello al volo. Il file vive in `~/.bookforge/settings.json`
(sovrascrivibile con la variabile d'ambiente `BOOKFORGE_CONFIG`, utile nei test).
"""
from __future__ import annotations

import json
import os
import dataclasses
from dataclasses import dataclass, field, asdict
from pathlib import Path

# provider supportati e modello predefinito di ciascuno
PROVIDERS = ("anthropic", "openai", "google")
DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-4o-mini",
    "google": "gemini-1.5-pro",
}


def settings_path() -> Path:
    """Percorso del file di impostazioni (override via `BOOKFORGE_CONFIG`)."""
    override = os.getenv("BOOKFORGE_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".bookforge" / "settings.json"


@dataclass
class AppSettings:
    """Configurazione globale dell'app, indipendente dal singolo progetto."""
    provider: str = "anthropic"
    model: str = "claude-opus-4-8"
    api_keys: dict = field(default_factory=dict)   # provider -> chiave API
    temperature: float = 0.7
    max_tokens: int = 0                            # 0 = lascia il default del provider

    # ---------- accesso comodo ----------
    def api_key_for(self, provider: str | None = None) -> str:
        return self.api_keys.get(provider or self.provider, "")

    def set_api_key(self, provider: str, key: str) -> None:
        if key:
            self.api_keys[provider] = key
        else:
            self.api_keys.pop(provider, None)

    # ---------- serializzazione ----------
    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AppSettings":
        known = {f.name for f in dataclasses.fields(AppSettings)}
        data = {k: v for k, v in (d or {}).items() if k in known}
        if not isinstance(data.get("api_keys"), dict):
            data["api_keys"] = {}
        return AppSettings(**data)

    # ---------- persistenza ----------
    @staticmethod
    def load(path: str | Path | None = None) -> "AppSettings":
        p = Path(path) if path else settings_path()
        if not p.exists():
            return AppSettings()
        try:
            return AppSettings.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - file corrotto: riparti dai default
            return AppSettings()

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path) if path else settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p
