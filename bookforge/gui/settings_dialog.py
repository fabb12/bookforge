"""Dialog «Impostazioni»: gestione centralizzata di API e parametri dei modelli LLM.

Le chiavi sono memorizzate per-provider (così basta configurarle una volta e poi
cambiare modello al volo) e persistite tramite `core.settings.AppSettings`.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QPushButton,
    QLineEdit, QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QMessageBox,
)

from ..core.settings import AppSettings, PROVIDERS, DEFAULT_MODELS


class SettingsDialog(QDialog):
    """Modifica e salva le impostazioni globali dei modelli LLM.

    Dopo `accept()`, `self.settings` contiene la configurazione aggiornata e già
    salvata su disco; il chiamante la usa per ricostruire il motore.
    """

    def __init__(self, parent=None, settings: AppSettings | None = None):
        super().__init__(parent)
        self.settings = settings or AppSettings.load()
        self._keys = dict(self.settings.api_keys)   # copia di lavoro per-provider

        self.setWindowTitle("Impostazioni — API e modelli LLM")
        self.setMinimumWidth(560)
        self._build_ui()
        self._load_provider(self.settings.provider)

    def _build_ui(self):
        outer = QVBoxLayout(self)

        info = QLabel("Configura qui i provider LLM: provider attivo, modello, "
                      "chiave API e parametri di campionamento. La chiave è salvata "
                      "per ogni provider, così puoi passare dall'uno all'altro senza "
                      "reinserirla.")
        info.setObjectName("Subtitle"); info.setWordWrap(True)
        outer.addWidget(info)

        box = QGroupBox("Provider e modello")
        form = QFormLayout(box)
        self.provider = QComboBox(); self.provider.addItems(list(PROVIDERS))
        self.provider.currentTextChanged.connect(self._on_provider_changed)
        self.model = QLineEdit()
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Lascia vuoto per la modalità offline (test)")
        show = QPushButton("Mostra"); show.setCheckable(True)
        show.toggled.connect(lambda on: self.key.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        key_row = QHBoxLayout(); key_row.addWidget(self.key); key_row.addWidget(show)
        from PyQt6.QtWidgets import QWidget
        key_wrap = QWidget(); key_wrap.setLayout(key_row)

        self.temperature = QDoubleSpinBox(); self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1); self.temperature.setValue(self.settings.temperature)
        self.max_tokens = QSpinBox(); self.max_tokens.setRange(0, 200000)
        self.max_tokens.setSingleStep(256); self.max_tokens.setValue(self.settings.max_tokens)
        self.max_tokens.setSpecialValueText("default")

        form.addRow("Provider attivo", self.provider)
        form.addRow("Modello", self.model)
        form.addRow("API key", key_wrap)
        form.addRow("Temperatura", self.temperature)
        form.addRow("Max token", self.max_tokens)
        outer.addWidget(box)

        note = QLabel("Le impostazioni sono salvate in ~/.bookforge/settings.json. "
                      "La chiave API è memorizzata in chiaro su questo computer.")
        note.setObjectName("Subtitle"); note.setWordWrap(True)
        outer.addWidget(note)

        btn_row = QHBoxLayout(); btn_row.addStretch(1)
        cancel = QPushButton("Annulla"); cancel.clicked.connect(self.reject)
        save = QPushButton("Salva"); save.setObjectName("Primary"); save.clicked.connect(self._save)
        btn_row.addWidget(cancel); btn_row.addWidget(save)
        outer.addLayout(btn_row)

    # --------------------------------------------------------------- logica
    def _on_provider_changed(self, provider: str):
        # memorizza la chiave del provider precedente prima di cambiare vista
        self._stash_current_key()
        self._load_provider(provider)

    def _stash_current_key(self):
        prev = getattr(self, "_current_provider", None)
        if prev:
            self._keys[prev] = self.key.text().strip()

    def _load_provider(self, provider: str):
        self._current_provider = provider
        self.provider.blockSignals(True)
        self.provider.setCurrentText(provider)
        self.provider.blockSignals(False)
        # modello: quello salvato se è il provider attivo, altrimenti il default
        if provider == self.settings.provider and self.settings.model:
            self.model.setText(self.settings.model)
        else:
            self.model.setText(DEFAULT_MODELS.get(provider, ""))
        self.key.setText(self._keys.get(provider, ""))

    def _save(self):
        self._stash_current_key()
        self.settings.provider = self.provider.currentText()
        self.settings.model = self.model.text().strip() or DEFAULT_MODELS.get(
            self.settings.provider, "")
        self.settings.api_keys = {p: k for p, k in self._keys.items() if k}
        self.settings.temperature = self.temperature.value()
        self.settings.max_tokens = self.max_tokens.value()
        try:
            self.settings.save()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Errore", f"Impossibile salvare:\n{e}")
            return
        self.accept()
