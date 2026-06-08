"""Widget riutilizzabile per scegliere un modello LLM in modo semplice e chiaro.

Mostra una tendina **non editabile** con i modelli noti del provider, etichettati
con nomi leggibili (il consigliato in cima, marcato con ★). In fondo c'è la voce
«Altro (personalizzato)…» che rivela un campo di testo per digitare un id non in
elenco: così la scelta resta immediata ma sempre completa.

Usato sia dal dialog Impostazioni sia dal pannello «Motore» della finestra
principale, per avere la stessa interazione ovunque.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QComboBox, QLineEdit

from ..core.settings import models_for, model_label, DEFAULT_MODELS

# valore-sentinella della voce «Altro»: distingue la scelta personalizzata dagli
# identificativi reali dei modelli.
_CUSTOM = "__custom__"


class ModelSelector(QWidget):
    """Selettore di modello per un provider: tendina leggibile + campo libero."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(lambda *_: self._sync_custom())
        self.custom = QLineEdit()
        self.custom.setPlaceholderText(
            "Identificativo del modello (es. claude-opus-4-8)")
        self.custom.setVisible(False)

        lay.addWidget(self.combo)
        lay.addWidget(self.custom)

    # --------------------------------------------------------------- API
    def set_provider(self, provider: str, selected: str = "") -> None:
        """Ripopola l'elenco per il provider e seleziona il modello indicato.

        Se `selected` non è tra i modelli noti, attiva la voce «Altro» e vi
        precompila l'identificativo, così nessuna scelta va persa.
        """
        self.combo.blockSignals(True)
        self.combo.clear()
        recommended = DEFAULT_MODELS.get(provider, "")
        for mid in models_for(provider):
            label = model_label(mid)
            if mid == recommended:
                label = f"★ {label}  (consigliato)"
            self.combo.addItem(label, mid)
        self.combo.addItem("✏️ Altro (modello personalizzato)…", _CUSTOM)

        idx = self.combo.findData(selected) if selected else -1
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
            self.custom.clear()
        elif selected:
            self.combo.setCurrentIndex(self.combo.count() - 1)  # «Altro»
            self.custom.setText(selected)
        else:
            self.combo.setCurrentIndex(0)
            self.custom.clear()
        self.combo.blockSignals(False)
        self._sync_custom()

    def current_model(self) -> str:
        """Identificativo del modello scelto (dal campo libero se «Altro»)."""
        if self.combo.currentData() == _CUSTOM:
            return self.custom.text().strip()
        return self.combo.currentData() or ""

    # ----------------------------------------------------------- interni
    def _sync_custom(self) -> None:
        """Mostra il campo libero solo quando è selezionata la voce «Altro»."""
        is_custom = self.combo.currentData() == _CUSTOM
        self.custom.setVisible(is_custom)
        if is_custom:
            self.custom.setFocus()
