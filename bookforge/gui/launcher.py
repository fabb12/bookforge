"""Costruisce la finestra giusta a partire da uno `StartupDialog` completato.

Condiviso tra `main.py` (avvio dell'app) e «Chiudi progetto» della finestra
principale, così la logica di apertura vive in un solo posto. Mantiene un
riferimento alle finestre aperte per evitare che il garbage collector le chiuda
quando si passa da un progetto all'altro.
"""
from __future__ import annotations

import logging

from PyQt6.QtWidgets import QMessageBox

log = logging.getLogger("bookforge")

# finestre tenute in vita finché restano aperte (evita la chiusura da GC)
_WINDOWS: list = []


def _track(win):
    if win is not None:
        _WINDOWS.append(win)
        win.destroyed.connect(lambda *_: _WINDOWS.remove(win)
                              if win in _WINDOWS else None)
    return win


def window_for_startup(startup):
    """Restituisce la finestra da mostrare (MainWindow) o None.

    La costruzione della finestra è avvolta in try/except: se l'apertura del
    progetto fallisce con un'eccezione Python, la registriamo nel log e la
    mostriamo all'utente invece di lasciar terminare il processo senza spiegazioni.
    (Un crash *nativo* di Qt resta intercettato da faulthandler → crash.log.)
    """
    from .main_window import MainWindow
    if startup.project is None:
        return None
    folder = getattr(startup.project, "folder", "?")
    try:
        log.info("Apertura progetto: %s", folder)
        win = _track(MainWindow(startup.project))
        log.info("Progetto aperto correttamente: %s", folder)
        return win
    except Exception:  # noqa: BLE001 - meglio un errore visibile che un crash muto
        log.exception("Errore durante l'apertura del progetto: %s", folder)
        QMessageBox.critical(
            None, "Impossibile aprire il progetto",
            "Si è verificato un errore durante l'apertura del progetto.\n\n"
            "I dettagli completi sono nel file di log "
            "(~/.bookforge/bookforge.log).")
        return None
