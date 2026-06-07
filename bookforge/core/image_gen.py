"""Generazione di immagini raster tramite servizi pluggable.

Provider supportato: Google (Imagen / Gemini), via il pacchetto `google-genai`.
La generazione di immagini è una capacità distinta dal motore di testo, quindi
vive qui e non in `agents/engine.py`. Se la libreria o la API key non ci sono,
le funzioni degradano con un messaggio chiaro invece di rompere l'app.

Installazione del provider Google:
    pip install google-genai
Chiave: variabile d'ambiente GOOGLE_API_KEY (o BOOKFORGE_IMAGE_API_KEY).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
        return False, ("Nessuna API key per le immagini. Imposta GOOGLE_API_KEY "
                       "(o BOOKFORGE_IMAGE_API_KEY).")
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False, ("Pacchetto 'google-genai' non installato.\n"
                       "Installa con:  pip install google-genai")
    return True, f"Immagini: Google {config.model}."


def generate_image(prompt: str, out_path: str | Path,
                   config: ImageGenConfig | None = None) -> Path:
    """Genera un'immagine dal `prompt` e la salva in `out_path` (PNG).

    Restituisce il percorso del file. Solleva RuntimeError con un messaggio
    leggibile se la libreria/chiave mancano o la generazione fallisce.
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
    try:
        resp = client.models.generate_images(
            model=config.model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=config.aspect_ratio,
            ),
        )
    except Exception as e:  # noqa: BLE001 - errori di rete/quota/API
        raise RuntimeError(f"Generazione immagine fallita: {e}") from e

    images = getattr(resp, "generated_images", None) or []
    if not images:
        raise RuntimeError("Il servizio non ha restituito immagini "
                           "(prompt rifiutato o quota esaurita?).")

    img = images[0].image
    # google-genai espone .save(path) e/o .image_bytes
    if hasattr(img, "save"):
        img.save(str(out_path))
    else:
        data = getattr(img, "image_bytes", None)
        if not data:
            raise RuntimeError("Formato immagine non riconosciuto dalla risposta.")
        out_path.write_bytes(data)
    return out_path
