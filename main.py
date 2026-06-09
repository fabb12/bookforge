"""Punto di ingresso di BookForge."""
import sys
import faulthandler
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from bookforge.gui.theme import DARK_QSS
from bookforge.gui.startup import StartupDialog
from bookforge.gui.launcher import window_for_startup
from bookforge.gui.icons import app_icon


def _enable_crash_log():
    """Trasforma un crash nativo (es. access violation 0xC0000005) in un traceback.

    Senza questo, un segfault dentro a Qt termina il processo *senza* messaggio
    Python (PyCharm mostra solo «exit code -1073741819»), rendendo il bug
    incomprensibile. `faulthandler` stampa lo stack al momento del crash su
    stderr e, in più, lo scrive su `~/.bookforge/crash.log` per poterlo
    recuperare anche quando l'output della console va perso.
    """
    faulthandler.enable()  # stack del crash su stderr
    try:
        log_dir = Path.home() / ".bookforge"
        log_dir.mkdir(parents=True, exist_ok=True)
        # tenuto aperto per tutta la vita del processo: faulthandler ci scrive al crash
        fh = open(log_dir / "crash.log", "w", encoding="utf-8")
        faulthandler.enable(file=fh)
        return fh
    except Exception:  # noqa: BLE001 - il logging su file è un di più, mai bloccante
        return None


def main():
    _enable_crash_log()

    app = QApplication(sys.argv)
    app.setApplicationName("BookForge")
    app.setWindowIcon(app_icon())
    app.setStyleSheet(DARK_QSS)

    startup = StartupDialog()
    if startup.exec() != StartupDialog.DialogCode.Accepted:
        return 0

    win = window_for_startup(startup)
    if win is None:
        return 0

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
