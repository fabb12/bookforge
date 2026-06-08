"""Registro dei comandi di scrittura assistita dall'AI.

Ogni comando è un'istruzione in linguaggio naturale che viene passata a
`engine.edit_text(instruction, testo_selezionato)`. Interfaccia ed engine
condividono questo registro, così il menu dell'editor resta allineato.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextCommand:
    key: str
    label: str
    instruction: str
    needs_selection: bool = True   # se False può operare anche senza testo selezionato


TEXT_COMMANDS: list[TextCommand] = [
    TextCommand("rewrite", "Riscrivi",
                "Riscrivi il brano migliorandone chiarezza e scorrevolezza, "
                "mantenendo significato, lingua e lunghezza simili."),
    TextCommand("expand", "Espandi",
                "Espandi il brano aggiungendo dettagli e approfondimenti pertinenti, "
                "senza inventare fatti non impliciti."),
    TextCommand("shorten", "Accorcia",
                "Accorcia il brano mantenendo i concetti chiave; rendilo più conciso."),
    TextCommand("continue", "Continua",
                "Continua il testo in modo coerente per uno o due paragrafi.",
                needs_selection=False),
    TextCommand("formal", "Più formale",
                "Riscrivi il brano con un tono più formale e accademico."),
    TextCommand("plain", "Più divulgativo",
                "Riscrivi il brano con un tono più divulgativo e accessibile."),
    TextCommand("fix", "Correggi",
                "Correggi ortografia, grammatica e punteggiatura del brano senza "
                "alterarne il significato."),
]


def command(key: str) -> TextCommand | None:
    return next((c for c in TEXT_COMMANDS if c.key == key), None)
