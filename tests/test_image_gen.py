"""Test della generazione immagini, in particolare il provider Ideogram.

Restano puri e headless: la rete è simulata sostituendo `urllib.request.urlopen`,
così la pipeline Ideogram è verificabile offline senza chiave né servizio reale.
"""
import json
import urllib.request

import pytest

from bookforge.core import image_gen
from bookforge.core.image_gen import ImageGenConfig


# --------------------------------------------------------- disponibilità
def test_ideogram_disponibile_con_chiave():
    ok, msg = image_gen.image_available(
        ImageGenConfig(provider="ideogram", model="V_2", api_key="k"))
    assert ok
    assert "Ideogram" in msg


def test_ideogram_senza_chiave_degrada_con_messaggio():
    ok, msg = image_gen.image_available(
        ImageGenConfig(provider="ideogram", api_key=""))
    assert not ok
    assert "IDEOGRAM_API_KEY" in msg


def test_provider_sconosciuto_resta_non_supportato():
    ok, msg = image_gen.image_available(ImageGenConfig(provider="dall-e"))
    assert not ok
    assert "non supportato" in msg


# --------------------------------------------------------- from_env
def test_from_env_ideogram_usa_modello_e_chiave(monkeypatch):
    monkeypatch.setenv("BOOKFORGE_IMAGE_PROVIDER", "ideogram")
    monkeypatch.delenv("BOOKFORGE_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("BOOKFORGE_IMAGE_API_KEY", raising=False)
    monkeypatch.setenv("IDEOGRAM_API_KEY", "secret")
    cfg = ImageGenConfig.from_env()
    assert cfg.provider == "ideogram"
    assert cfg.model == "V_2"          # default specifico per Ideogram
    assert cfg.api_key == "secret"


def test_from_env_google_resta_invariato(monkeypatch):
    # nessuna regressione: senza override il default resta Google/Imagen
    for var in ("BOOKFORGE_IMAGE_PROVIDER", "BOOKFORGE_IMAGE_MODEL",
                "BOOKFORGE_IMAGE_API_KEY", "IDEOGRAM_API_KEY",
                "GOOGLE_API_KEY", "GEMINI_API_KEY", "BOOKFORGE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    cfg = ImageGenConfig.from_env()
    assert cfg.provider == "google"
    assert cfg.model == "imagen-3.0-generate-002"


# --------------------------------------------------------- generate_image (rete simulata)
class _FakeResp:
    """Minimo context manager con `.read()`, come la risposta di urlopen."""
    def __init__(self, data: bytes):
        self._data = data
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False
    def read(self):
        return self._data


def test_generate_ideogram_scarica_e_salva(monkeypatch, tmp_path):
    calls = []

    def fake_urlopen(req, timeout=0):
        # prima chiamata: POST all'API → risposta JSON con l'URL dell'immagine
        url = getattr(req, "full_url", req)
        calls.append(url)
        if url == image_gen._IDEOGRAM_URL:
            body = json.loads(req.data.decode("utf-8"))["image_request"]
            assert body["prompt"] == "un faro al tramonto"
            assert body["aspect_ratio"] == "ASPECT_16_9"
            assert body["model"] == "V_2"
            return _FakeResp(json.dumps(
                {"data": [{"url": "https://img.example/out.png"}]}).encode("utf-8"))
        # seconda chiamata: download dei byte immagine
        return _FakeResp(b"PNGDATA")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    out = tmp_path / "images" / "fig.png"
    cfg = ImageGenConfig(provider="ideogram", model="V_2",
                         api_key="k", aspect_ratio="16:9")
    res = image_gen.generate_image("un faro al tramonto", out, cfg)

    assert res == out
    assert out.read_bytes() == b"PNGDATA"
    assert calls == [image_gen._IDEOGRAM_URL, "https://img.example/out.png"]


def test_generate_ideogram_senza_immagini_solleva(monkeypatch, tmp_path):
    def fake_urlopen(req, timeout=0):
        return _FakeResp(json.dumps({"data": []}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    cfg = ImageGenConfig(provider="ideogram", api_key="k")
    with pytest.raises(RuntimeError, match="non ha restituito immagini"):
        image_gen.generate_image("x", tmp_path / "o.png", cfg)


def test_generate_ideogram_senza_chiave_solleva(tmp_path):
    cfg = ImageGenConfig(provider="ideogram", api_key="")
    with pytest.raises(RuntimeError, match="IDEOGRAM_API_KEY"):
        image_gen.generate_image("x", tmp_path / "o.png", cfg)
