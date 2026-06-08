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
    "google": "gemini-2.5-pro",
}

# modelli attualmente disponibili per provider, mostrati nel menu a tendina delle
# impostazioni. La lista non è esaustiva: il campo resta editabile, così l'utente
# può digitare un identificativo non in elenco. Il primo elemento è il consigliato.
AVAILABLE_MODELS = {
    "anthropic": [
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "o3",
        "o4-mini",
    ],
    "google": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ],
}


# etichette leggibili dei modelli noti (id tecnico -> nome amichevole con una
# nota sul compromesso qualità/velocità). Servono a rendere la scelta del modello
# chiara nella UI: l'utente vede «Claude Opus 4.8 — massima qualità» invece del
# solo identificativo. I modelli non in mappa mostrano il loro id così com'è.
MODEL_LABELS = {
    "claude-opus-4-8": "Claude Opus 4.8 — massima qualità",
    "claude-sonnet-4-6": "Claude Sonnet 4.6 — equilibrato",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5 — veloce ed economico",
    "gpt-4o": "GPT-4o — qualità",
    "gpt-4o-mini": "GPT-4o mini — veloce ed economico",
    "gpt-4.1": "GPT-4.1 — qualità",
    "gpt-4.1-mini": "GPT-4.1 mini — veloce",
    "o3": "o3 — ragionamento avanzato",
    "o4-mini": "o4-mini — ragionamento veloce",
    "gemini-2.5-pro": "Gemini 2.5 Pro — qualità",
    "gemini-2.5-flash": "Gemini 2.5 Flash — veloce",
}


# modelli ritirati dai provider: vengono rimappati automaticamente al caricamento
# delle impostazioni, così le configurazioni salvate non restano bloccate su un id
# non più servito (es. i Gemini 1.5, ritirati da Google).
RETIRED_MODELS = {
    "gemini-1.5-pro": "gemini-2.5-pro",
    "gemini-1.5-flash": "gemini-2.5-flash",
}


def models_for(provider: str) -> list[str]:
    """Elenco dei modelli noti per un provider (vuoto se sconosciuto)."""
    return list(AVAILABLE_MODELS.get(provider, []))


def model_label(model_id: str) -> str:
    """Nome leggibile di un modello; ripiega sull'id tecnico se non in mappa."""
    return MODEL_LABELS.get(model_id, model_id)


# quanti progetti recenti tenere in memoria
MAX_RECENT_PROJECTS = 8


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
    recent_projects: list = field(default_factory=list)  # percorsi progetti recenti (più recente prima)

    # ---------- accesso comodo ----------
    def api_key_for(self, provider: str | None = None) -> str:
        return self.api_keys.get(provider or self.provider, "")

    def set_api_key(self, provider: str, key: str) -> None:
        if key:
            self.api_keys[provider] = key
        else:
            self.api_keys.pop(provider, None)

    # ---------- progetti recenti ----------
    def add_recent_project(self, folder) -> None:
        """Mette il progetto in cima alla lista dei recenti, senza duplicati."""
        p = str(Path(folder).resolve())
        recents = [str(x) for x in self.recent_projects if str(x) != p]
        self.recent_projects = [p] + recents
        del self.recent_projects[MAX_RECENT_PROJECTS:]

    def clean_recent_projects(self) -> list:
        """Filtra i recenti tenendo solo le cartelle che esistono ancora."""
        self.recent_projects = [
            str(x) for x in self.recent_projects if Path(x).exists()]
        return self.recent_projects

    # ---------- serializzazione ----------
    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "AppSettings":
        known = {f.name for f in dataclasses.fields(AppSettings)}
        data = {k: v for k, v in (d or {}).items() if k in known}
        if not isinstance(data.get("api_keys"), dict):
            data["api_keys"] = {}
        if not isinstance(data.get("recent_projects"), list):
            data["recent_projects"] = []
        # rimappa eventuali modelli ritirati salvati in precedenza
        if data.get("model") in RETIRED_MODELS:
            data["model"] = RETIRED_MODELS[data["model"]]
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
