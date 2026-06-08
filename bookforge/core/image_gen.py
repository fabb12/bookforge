"""Generazione di immagini raster tramite servizi pluggable.

Provider supportato: Google (Imagen / Gemini), via il pacchetto `google-genai`.
La generazione di immagini è una capacità distinta dal motore di testo, quindi
vive qui e non in `agents/engine.py`. Se la libreria o la API key non ci sono,
le funzioni degradano con un messaggio chiaro invece di rompere l'app.

Due percorsi tecnici, scelti automaticamente in base al modello:
  • modelli «imagen-*» → endpoint `predict` (`client.models.generate_images`);
  • modelli «gemini-*image*» → `client.models.generate_content` con modalità
    immagine. Questi ultimi funzionano con una semplice API key Google (anche
    sul piano gratuito), mentre Imagen via `predict` spesso non è disponibile e
    risponde «404 NOT_FOUND». Per questo, se il modello scelto fallisce, si
    ripiega in automatico sui modelli Gemini immagine.

Installazione del provider Google:
    pip install google-genai
Chiave: variabile d'ambiente GOOGLE_API_KEY (o BOOKFORGE_IMAGE_API_KEY).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Modelli Gemini con generazione immagini, usati come ripiego (funzionano con
# una semplice API key). In ordine di preferenza.
_GEMINI_IMAGE_FALLBACK = (
    "gemini-2.5-flash-image",
    "gemini-2.5-flash-image-preview",
    "gemini-2.0-flash-preview-image-generation",
)


@dataclass
class ImageGenConfig:
    provider: str = "google"
    model: str = "imagen-3.0-generate-002"
    api_key: str = ""
    aspect_ratio: str = "4:3"          # 1:1 | 3:4 | 4:3 | 9:16 | 16:9

    @staticmethod
    def from_env() -> "ImageGenConfig":
        return ImageGenConfig(
            provider=os.getenv("BOOKFORGE_IMAGE_PROVIDER", "google"),
            model=os.getenv("BOOKFORGE_IMAGE_MODEL", "imagen-3.0-generate-002"),
            api_key=os.getenv("BOOKFORGE_IMAGE_API_KEY", "")
                    or os.getenv("GOOGLE_API_KEY", "")
                    or os.getenv("GEMINI_API_KEY", "")
                    or os.getenv("BOOKFORGE_API_KEY", ""),
        )


def image_available(config: ImageGenConfig) -> tuple[bool, str]:
    """Verifica se il provider è utilizzabile (libreria + chiave)."""
    if config.provider != "google":
        return False, f"Provider immagini non supportato: {config.provider}"
    if not config.api_key:
        return False, ("Nessuna API key per le immagini. Imposta una chiave Google "
                       "in ⚙ Impostazioni (provider «google») oppure la variabile "
                       "d'ambiente GOOGLE_API_KEY / BOOKFORGE_IMAGE_API_KEY.")
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False, ("Pacchetto 'google-genai' non installato.\n"
                       "Installa con:  pip install google-genai")
    return True, f"Immagini: Google {config.model}."


def _candidate_models(model: str) -> list[tuple[str, str]]:
    """Sequenza di tentativi (tipo, modello) da provare in ordine.

    «tipo» è "imagen" (endpoint predict) o "gemini" (generate_content). Si parte
    dal modello configurato e si ripiega sui modelli Gemini immagine, che sono i
    più disponibili con una semplice API key.
    """
    model = (model or "").strip()
    attempts: list[tuple[str, str]] = []
    if model:
        kind = "gemini" if "gemini" in model.lower() else "imagen"
        attempts.append((kind, model))
    for m in _GEMINI_IMAGE_FALLBACK:
        if ("gemini", m) not in attempts:
            attempts.append(("gemini", m))
    return attempts


def _save_imagen(client, types, model: str, prompt: str,
                 aspect_ratio: str, out_path: Path) -> None:
    """Genera con Imagen (endpoint predict) e salva su `out_path`."""
    resp = client.models.generate_images(
        model=model,
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=aspect_ratio,
        ),
    )
    images = getattr(resp, "generated_images", None) or []
    if not images:
        raise RuntimeError("il servizio non ha restituito immagini "
                           "(prompt rifiutato o quota esaurita?)")
    img = images[0].image
    if hasattr(img, "save"):
        img.save(str(out_path))
    else:
        data = getattr(img, "image_bytes", None)
        if not data:
            raise RuntimeError("formato immagine non riconosciuto nella risposta")
        out_path.write_bytes(data)


def _save_gemini(client, types, model: str, prompt: str, out_path: Path) -> None:
    """Genera con un modello Gemini immagine (generate_content) e salva il PNG."""
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["TEXT", "IMAGE"],
        ),
    )
    data = _gemini_image_bytes(resp)
    if not data:
        raise RuntimeError("nessuna immagine nella risposta "
                           "(il modello potrebbe aver restituito solo testo)")
    out_path.write_bytes(data)


def _gemini_image_bytes(resp) -> bytes | None:
    """Estrae i byte della prima immagine inline da una risposta generate_content."""
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                return data
    return None


def generate_image(prompt: str, out_path: str | Path,
                   config: ImageGenConfig | None = None) -> Path:
    """Genera un'immagine dal `prompt` e la salva in `out_path` (PNG).

    Restituisce il percorso del file. Prova il modello configurato e, se non è
    disponibile (tipico 404 di Imagen su API key gratuita), ripiega sui modelli
    Gemini immagine. Solleva RuntimeError con un messaggio leggibile se la
    libreria/chiave mancano o tutti i tentativi falliscono.
    """
    config = config or ImageGenConfig.from_env()
    ok, msg = image_available(config)
    if not ok:
        raise RuntimeError(msg)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:  # già coperto da image_available, ma per sicurezza
        raise RuntimeError("Pacchetto 'google-genai' non installato "
                           "(pip install google-genai).") from e

    client = genai.Client(api_key=config.api_key)
    errors: list[str] = []
    for kind, model in _candidate_models(config.model):
        try:
            if kind == "imagen":
                _save_imagen(client, types, model, prompt,
                             config.aspect_ratio, out_path)
            else:
                _save_gemini(client, types, model, prompt, out_path)
            return out_path
        except Exception as e:  # noqa: BLE001 - errori di rete/quota/API/modello
            errors.append(f"• {model}: {e}")

    raise RuntimeError("Generazione immagine fallita con tutti i modelli "
                       "disponibili.\n" + "\n".join(errors))
