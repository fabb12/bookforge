"""Dialog «Impostazioni»: gestione centralizzata di API e parametri dei modelli LLM.

Le chiavi sono memorizzate per-provider (così basta configurarle una volta e poi
cambiare modello al volo) e persistite tramite `core.settings.AppSettings`.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QPushButton,
    QLineEdit, QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QMessageBox,
    QWidget, QApplication,
)
from PyQt6.QtCore import Qt

from ..core.settings import (
    AppSettings, PROVIDERS, DEFAULT_MODELS, PROVIDER_LABELS, is_local,
    default_base_url,
    IMAGE_PROVIDERS, IMAGE_PROVIDER_LABELS, default_image_model,
    image_models_for,
)
from ..agents.engine import list_local_models
from .model_selector import ModelSelector
from .icons import app_icon


class SettingsDialog(QDialog):
    """Modifica e salva le impostazioni globali dei modelli LLM.

    Dopo `accept()`, `self.settings` contiene la configurazione aggiornata e già
    salvata su disco; il chiamante la usa per ricostruire il motore.
    """

    def __init__(self, parent=None, settings: AppSettings | None = None):
        super().__init__(parent)
        self.settings = settings or AppSettings.load()
        self._keys = dict(self.settings.api_keys)         # copia di lavoro per-provider
        self._base_urls = dict(self.settings.base_urls)   # endpoint per provider locale

        self.setWindowTitle("Impostazioni — API e modelli LLM")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(560)
        self._build_ui()
        self._load_provider(self.settings.provider)
        self._load_image_provider(self.settings.image_provider or "google")

    def _build_ui(self):
        outer = QVBoxLayout(self)

        info = QLabel("Configura qui i provider LLM: provider attivo, modello, "
                      "chiave API e parametri di campionamento. Puoi usare provider "
                      "cloud (Anthropic, OpenAI, Google) oppure motori LOCALI come "
                      "Ollama e LM Studio, che girano sul tuo computer senza chiave né "
                      "rete: basta indicarne l'endpoint.")
        info.setObjectName("Subtitle"); info.setWordWrap(True)
        outer.addWidget(info)

        box = QGroupBox("Provider e modello")
        self.form = form = QFormLayout(box)
        self.provider = QComboBox()
        # mostra nomi leggibili ma conserva l'id tecnico come dato della voce
        for p in PROVIDERS:
            self.provider.addItem(PROVIDER_LABELS.get(p, p), p)
        self.provider.currentIndexChanged.connect(
            lambda *_: self._on_provider_changed(self.provider.currentData()))
        # modello: selettore chiaro con nomi leggibili e voce «Altro» per gli id
        # non in elenco (vedi ModelSelector). Si aggiorna al cambio di provider.
        self.model = ModelSelector()
        self.detect_btn = QPushButton("🔄 Rileva")
        self.detect_btn.setToolTip(
            "Interroga il server locale per elencare i modelli disponibili")
        self.detect_btn.clicked.connect(self._detect_models)
        model_row = QHBoxLayout(); model_row.setContentsMargins(0, 0, 0, 0)
        model_row.addWidget(self.model, 1); model_row.addWidget(self.detect_btn)
        model_wrap = QWidget(); model_wrap.setLayout(model_row)

        # endpoint dei provider locali (visibile solo per Ollama/LM Studio)
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("http://localhost:11434/v1")

        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Lascia vuoto per la modalità offline (test)")
        show = QPushButton("Mostra"); show.setCheckable(True)
        show.toggled.connect(lambda on: self.key.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        key_row = QHBoxLayout(); key_row.addWidget(self.key); key_row.addWidget(show)
        self.key_wrap = QWidget(); self.key_wrap.setLayout(key_row)

        self.temperature = QDoubleSpinBox(); self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1); self.temperature.setValue(self.settings.temperature)
        self.max_tokens = QSpinBox(); self.max_tokens.setRange(0, 200000)
        self.max_tokens.setSingleStep(256); self.max_tokens.setValue(self.settings.max_tokens)
        self.max_tokens.setSpecialValueText("default")

        form.addRow("Provider attivo", self.provider)
        form.addRow("Modello", model_wrap)
        form.addRow("Endpoint locale", self.base_url)
        form.addRow("API key", self.key_wrap)
        form.addRow("Temperatura", self.temperature)
        form.addRow("Max token", self.max_tokens)
        outer.addWidget(box)

        outer.addWidget(self._build_image_box())

        note = QLabel("Le impostazioni sono salvate in ~/.bookforge/settings.json. "
                      "La chiave API è memorizzata in chiaro su questo computer. "
                      "I motori locali non richiedono alcuna chiave.")
        note.setObjectName("Subtitle"); note.setWordWrap(True)
        outer.addWidget(note)

        btn_row = QHBoxLayout(); btn_row.addStretch(1)
        cancel = QPushButton("Annulla"); cancel.clicked.connect(self.reject)
        save = QPushButton("Salva"); save.setObjectName("Primary"); save.clicked.connect(self._save)
        btn_row.addWidget(cancel); btn_row.addWidget(save)
        outer.addLayout(btn_row)

    def _build_image_box(self) -> QGroupBox:
        """Riquadro per la generazione immagini (provider, modello, chiave).

        Capacità separata dal motore di testo: si può usare Google (Imagen /
        Gemini) o Ideogram. Google riusa la chiave del provider «google» qui
        sopra; Ideogram ha una propria chiave."""
        box = QGroupBox("Generazione immagini")
        self.img_form = form = QFormLayout(box)

        self.img_provider = QComboBox()
        for p in IMAGE_PROVIDERS:
            self.img_provider.addItem(IMAGE_PROVIDER_LABELS.get(p, p), p)
        self.img_provider.currentIndexChanged.connect(
            lambda *_: self._on_image_provider_changed(self.img_provider.currentData()))

        # modello immagine: combo editabile con i modelli noti del provider
        self.img_model = QComboBox(); self.img_model.setEditable(True)

        # chiave Ideogram (Google riusa la chiave del provider «google»)
        self.img_key = QLineEdit(); self.img_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.img_key.setPlaceholderText("Chiave Ideogram (IDEOGRAM_API_KEY)")
        img_show = QPushButton("Mostra"); img_show.setCheckable(True)
        img_show.toggled.connect(lambda on: self.img_key.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        img_key_row = QHBoxLayout(); img_key_row.addWidget(self.img_key); img_key_row.addWidget(img_show)
        self.img_key_wrap = QWidget(); self.img_key_wrap.setLayout(img_key_row)

        self.img_key_note = QLabel("Google riusa la chiave del provider «Google» "
                                   "configurata qui sopra.")
        self.img_key_note.setObjectName("Subtitle"); self.img_key_note.setWordWrap(True)

        form.addRow("Provider immagini", self.img_provider)
        form.addRow("Modello immagini", self.img_model)
        form.addRow("Chiave immagini", self.img_key_wrap)
        form.addRow("", self.img_key_note)
        return box

    def _load_image_provider(self, provider: str):
        """Popola modello/chiave per il provider immagini selezionato."""
        self._current_image_provider = provider
        self.img_provider.blockSignals(True)
        idx = self.img_provider.findData(provider)
        if idx >= 0:
            self.img_provider.setCurrentIndex(idx)
        self.img_provider.blockSignals(False)
        # modello: quello salvato se è il provider attivo, altrimenti il default
        if provider == self.settings.image_provider and self.settings.image_model:
            target = self.settings.image_model
        else:
            target = default_image_model(provider)
        self.img_model.clear()
        self.img_model.addItems(image_models_for(provider))
        self.img_model.setEditText(target)
        # Ideogram ha una chiave propria; Google riusa la chiave del provider testo
        ideogram = provider == "ideogram"
        if ideogram:
            self.img_key.setText(self._keys.get("ideogram", ""))
        self.img_form.setRowVisible(self.img_key_wrap, ideogram)
        self.img_form.setRowVisible(self.img_key_note, not ideogram)

    def _on_image_provider_changed(self, provider: str):
        # memorizza la chiave Ideogram del provider precedente prima di cambiare
        self._stash_image_key()
        self._load_image_provider(provider)

    def _stash_image_key(self):
        prev = getattr(self, "_current_image_provider", None)
        if prev == "ideogram":
            self._keys["ideogram"] = self.img_key.text().strip()

    # --------------------------------------------------------------- logica
    def _on_provider_changed(self, provider: str):
        # memorizza chiave/endpoint del provider precedente prima di cambiare vista
        self._stash_current_key()
        self._load_provider(provider)

    def _stash_current_key(self):
        prev = getattr(self, "_current_provider", None)
        if prev:
            self._keys[prev] = self.key.text().strip()
            if is_local(prev):
                self._base_urls[prev] = self.base_url.text().strip()

    def _load_provider(self, provider: str):
        self._current_provider = provider
        self.provider.blockSignals(True)
        idx = self.provider.findData(provider)
        if idx >= 0:
            self.provider.setCurrentIndex(idx)
        self.provider.blockSignals(False)
        # modello: quello salvato se è il provider attivo, altrimenti il default
        if provider == self.settings.provider and self.settings.model:
            target = self.settings.model
        else:
            target = DEFAULT_MODELS.get(provider, "")
        self.model.set_provider(provider, target)
        self.key.setText(self._keys.get(provider, ""))
        local = is_local(provider)
        # endpoint: quello salvato per il provider o il predefinito
        self.base_url.setText(self._base_urls.get(provider) or default_base_url(provider))
        # i provider locali mostrano l'endpoint + «Rileva» e nascondono la chiave
        self.form.setRowVisible(self.base_url, local)
        self.form.setRowVisible(self.key_wrap, not local)
        self.detect_btn.setVisible(local)

    def _detect_models(self):
        """Interroga il server locale e popola i modelli rilevati."""
        url = self.base_url.text().strip() or default_base_url(
            self.provider.currentData())
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            models = list_local_models(url)
        finally:
            QApplication.restoreOverrideCursor()
        if not models:
            QMessageBox.warning(
                self, "Nessun modello",
                f"Nessun modello rilevato su {url}.\n\n"
                "Verifica che Ollama o LM Studio sia in esecuzione e che "
                "l'endpoint sia corretto, poi riprova.")
            return
        self.model.set_models(models, self.model.current_model())
        QMessageBox.information(
            self, "Modelli rilevati",
            f"Trovati {len(models)} modelli su {url}.")

    def _save(self):
        self._stash_current_key()
        self._stash_image_key()
        provider = self.provider.currentData()
        self.settings.provider = provider
        self.settings.model = self.model.current_model() or DEFAULT_MODELS.get(
            provider, "")
        # provider/modello per la generazione immagini
        img_provider = self.img_provider.currentData()
        self.settings.image_provider = img_provider
        self.settings.image_model = (self.img_model.currentText().strip()
                                     or default_image_model(img_provider))
        self.settings.api_keys = {p: k for p, k in self._keys.items() if k}
        # endpoint locali: conserva solo quelli diversi dal predefinito
        self.settings.base_urls = {}
        for p, u in self._base_urls.items():
            self.settings.set_base_url(p, u)
        self.settings.temperature = self.temperature.value()
        self.settings.max_tokens = self.max_tokens.value()
        try:
            self.settings.save()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Impossibile salvare:\n{e}")
            return
        self.accept()
