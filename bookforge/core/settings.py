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

# provider supportati e modello predefinito di ciascuno.
# Oltre ai provider cloud (anthropic/openai/google) sono supportati i motori
# LOCALI: Ollama e LM Studio espongono un'API OpenAI-compatibile su localhost,
# così si può scrivere senza rete né chiave (vedi `LOCAL_PROVIDERS`).
PROVIDERS = ("anthropic", "openai", "google", "ollama", "lmstudio")

# provider che girano in locale: non richiedono una chiave API, ma un endpoint
# (`base_url`) verso il server OpenAI-compatibile in ascolto sulla macchina.
LOCAL_PROVIDERS = ("ollama", "lmstudio")

# etichette leggibili dei provider (per la UI)
PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI (GPT)",
    "google": "Google (Gemini)",
    "ollama": "Ollama (locale)",
    "lmstudio": "LM Studio (locale)",
}

DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-4o-mini",
    "google": "gemini-2.5-pro",
    "ollama": "llama3.1:8b",
    "lmstudio": "local-model",
}

# endpoint predefinito dei provider locali (API OpenAI-compatibile).
DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}

# provider per la GENERAZIONE IMMAGINI (capacità separata dal motore di testo).
# Google riusa la chiave del provider «google»; Ideogram ha una propria chiave.
IMAGE_PROVIDERS = ("google", "ideogram")
IMAGE_PROVIDER_LABELS = {
    "google": "Google (Imagen / Gemini)",
    "ideogram": "Ideogram (ideogram.ai)",
}
DEFAULT_IMAGE_MODELS = {
    "google": "imagen-3.0-generate-002",
    "ideogram": "V_2",
}
# modelli immagine noti per provider (campo editabile: l'elenco non è esaustivo)
AVAILABLE_IMAGE_MODELS = {
    "google": [
        "imagen-3.0-generate-002",
        "gemini-2.5-flash-image",
    ],
    "ideogram": [
        "V_2",
        "V_2_TURBO",
        "V_1",
        "V_1_TURBO",
    ],
}


def image_provider_label(provider: str) -> str:
    """Nome leggibile di un provider immagini; ripiega sull'id se non in mappa."""
    return IMAGE_PROVIDER_LABELS.get(provider, provider)


def default_image_model(provider: str) -> str:
    """Modello immagine predefinito per un provider (vuoto se sconosciuto)."""
    return DEFAULT_IMAGE_MODELS.get((provider or "").strip().lower(), "")


def image_models_for(provider: str) -> list[str]:
    """Elenco dei modelli immagine noti per un provider (vuoto se sconosciuto)."""
    return list(AVAILABLE_IMAGE_MODELS.get(provider, []))


def is_local(provider: str) -> bool:
    """Indica se il provider è un motore locale (Ollama/LM Studio)."""
    return (provider or "").strip().lower() in LOCAL_PROVIDERS


def provider_label(provider: str) -> str:
    """Nome leggibile di un provider; ripiega sull'id se non in mappa."""
    return PROVIDER_LABELS.get(provider, provider)


def default_base_url(provider: str) -> str:
    """Endpoint predefinito per un provider locale (vuoto se non locale)."""
    return DEFAULT_BASE_URLS.get((provider or "").strip().lower(), "")

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
    # Per i provider locali l'elenco è solo indicativo: i modelli dipendono da
    # ciò che l'utente ha scaricato/caricato. Il campo resta editabile e la GUI
    # può rilevarli interrogando il server (vedi `agents.engine.list_local_models`).
    "ollama": [
        "llama3.1:8b",
        "llama3.1:70b",
        "qwen2.5:14b",
        "mistral",
        "gemma2",
        "phi4",
    ],
    "lmstudio": [
        "local-model",
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
    # modelli locali (etichette indicative)
    "llama3.1:8b": "Llama 3.1 8B — locale, leggero",
    "llama3.1:70b": "Llama 3.1 70B — locale, qualità (molta RAM)",
    "qwen2.5:14b": "Qwen 2.5 14B — locale, equilibrato",
    "mistral": "Mistral 7B — locale, leggero",
    "gemma2": "Gemma 2 — locale",
    "phi4": "Phi-4 — locale, compatto",
    "local-model": "Modello caricato in LM Studio — locale",
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
    base_urls: dict = field(default_factory=dict)  # provider locale -> endpoint
    temperature: float = 0.7
    max_tokens: int = 0                            # 0 = lascia il default del provider
    recent_projects: list = field(default_factory=list)  # percorsi progetti recenti (più recente prima)
    image_provider: str = "google"                 # provider per la generazione immagini
    image_model: str = ""                          # modello immagine (vuoto = default del provider)

    # ---------- accesso comodo ----------
    def api_key_for(self, provider: str | None = None) -> str:
        return self.api_keys.get(provider or self.provider, "")

    def image_model_for(self, provider: str | None = None) -> str:
        """Modello immagine salvato per il provider, o il suo predefinito."""
        p = provider or self.image_provider
        if self.image_model and p == self.image_provider:
            return self.image_model
        return default_image_model(p)

    def set_api_key(self, provider: str, key: str) -> None:
        if key:
            self.api_keys[provider] = key
        else:
            self.api_keys.pop(provider, None)

    def base_url_for(self, provider: str | None = None) -> str:
        """Endpoint del provider locale: quello salvato o il predefinito.

        Per i provider cloud restituisce stringa vuota (non hanno un endpoint
        configurabile lato BookForge).
        """
        p = provider or self.provider
        return self.base_urls.get(p) or default_base_url(p)

    def set_base_url(self, provider: str, url: str) -> None:
        url = (url or "").strip()
        # memorizza solo se diverso dal predefinito, così l'elenco resta pulito
        if url and url != default_base_url(provider):
            self.base_urls[provider] = url
        else:
            self.base_urls.pop(provider, None)

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
        if not isinstance(data.get("base_urls"), dict):
            data["base_urls"] = {}
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
