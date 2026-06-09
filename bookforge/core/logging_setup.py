"""Logging centralizzato di BookForge.

Scrive **tutti** i messaggi (errori, avvisi, passi diagnostici) su un file di
log persistente, così un crash all'avvio o all'apertura di un progetto lascia
sempre una traccia leggibile — anche quando la console di PyCharm non mostra
nulla (es. access violation nativo, exit code -1073741819 / 0xC0000005).

Dove finisce il log:
- `~/.bookforge/bookforge.log` (configurabile con `BOOKFORGE_LOG`).

Cosa cattura:
- i log applicativi via `logging` (root logger);
- le **eccezioni Python non gestite** (tramite `sys.excepthook`);
- i **crash nativi** di Qt/C (tramite `faulthandler`, che scrive lo stack su
  `~/.bookforge/crash.log` oltre che su stderr).

Modulo *core*: niente PyQt, niente rete. Usa solo la libreria standard.
"""
from __future__ import annotations

import logging
import os
import sys
import faulthandler
from logging.handlers import RotatingFileHandler
from pathlib import Path

# riferimenti tenuti vivi per tutta la durata del processo
_CRASH_FILE = None
_CONFIGURED = False


def log_dir() -> Path:
    """Cartella dei log: `~/.bookforge` (override con `BOOKFORGE_LOG` come file)."""
    override = os.environ.get("BOOKFORGE_LOG")
    if override:
        return Path(override).expanduser().parent
    return Path.home() / ".bookforge"


def log_path() -> Path:
    """Percorso completo del file di log principale."""
    override = os.environ.get("BOOKFORGE_LOG")
    if override:
        return Path(override).expanduser()
    return log_dir() / "bookforge.log"


def setup_logging(level: int = logging.INFO) -> Path:
    """Configura il logging su file (idempotente). Restituisce il percorso del log.

    Va chiamato il prima possibile in `main()`. Anche se la creazione del file
    fallisce (permessi, disco pieno) l'app non si blocca: si ripiega sul solo
    stream su stderr.
    """
    global _CONFIGURED, _CRASH_FILE
    path = log_path()
    if _CONFIGURED:
        return path

    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # handler su file rotante (mantiene qualche backup, evita file infiniti)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3,
                                 encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception as e:  # noqa: BLE001 - il file di log è un di più, mai bloccante
        print(f"[BookForge] impossibile aprire il file di log {path}: {e}",
              file=sys.stderr)

    # handler su console: utile in sviluppo e quando il file non è scrivibile
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    _install_excepthook()
    _CRASH_FILE = _enable_faulthandler()
    _CONFIGURED = True

    logging.getLogger("bookforge").info("Logging avviato → %s", path)
    return path


def _install_excepthook() -> None:
    """Registra un hook che logga ogni eccezione Python non gestita."""
    previous = sys.excepthook

    def handler(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        logging.getLogger("bookforge").critical(
            "Eccezione non gestita", exc_info=(exc_type, exc, tb))
        previous(exc_type, exc, tb)

    sys.excepthook = handler


def _enable_faulthandler():
    """Abilita faulthandler: i crash nativi finiscono su stderr e su crash.log."""
    faulthandler.enable()  # stack del crash su stderr
    try:
        crash = log_dir() / "crash.log"
        crash.parent.mkdir(parents=True, exist_ok=True)
        fh = open(crash, "w", encoding="utf-8")  # tenuto aperto: ci scrive al crash
        faulthandler.enable(file=fh)
        return fh
    except Exception:  # noqa: BLE001 - il crash log su file è opzionale
        return None


def get_logger(name: str = "bookforge") -> logging.Logger:
    """Scorciatoia per ottenere un logger applicativo già configurato."""
    return logging.getLogger(name)
