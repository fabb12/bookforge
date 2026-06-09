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
        provider = self.provider.currentData()
        self.settings.provider = provider
        self.settings.model = self.model.current_model() or DEFAULT_MODELS.get(
            provider, "")
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
