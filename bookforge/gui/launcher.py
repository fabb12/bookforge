"""Costruisce la finestra giusta a partire da uno `StartupDialog` completato.

Condiviso tra `main.py` (avvio dell'app) e «Chiudi progetto» della finestra
principale, così la logica di apertura vive in un solo posto. Mantiene un
riferimento alle finestre aperte per evitare che il garbage collector le chiuda
quando si passa da un progetto all'altro.
"""
from __future__ import annotations

# finestre tenute in vita finché restano aperte (evita la chiusura da GC)
_WINDOWS: list = []


def _track(win):
    if win is not None:
        _WINDOWS.append(win)
        win.destroyed.connect(lambda *_: _WINDOWS.remove(win)
                              if win in _WINDOWS else None)
    return win


def window_for_startup(startup):
    """Restituisce la finestra da mostrare (MainWindow o LatexBrowser) o None."""
    from .main_window import MainWindow
    if startup.project is not None:
        return _track(MainWindow(startup.project))
    if startup.latex_folder is not None:
        from .latex_browser import LatexBrowserWindow
        from ..agents.engine import EngineConfig, build_engine
        from ..core.settings import AppSettings
        engine, engine_real, _ = build_engine(
            EngineConfig.from_settings(AppSettings.load()))
        return _track(LatexBrowserWindow(
            startup.latex_folder, engine=engine, engine_real=engine_real))
    return None
