"""Punto di ingresso di BookForge."""
import sys
import logging

from PyQt6.QtWidgets import QApplication

from bookforge.core.logging_setup import setup_logging
from bookforge.gui.theme import DARK_QSS
from bookforge.gui.startup import StartupDialog
from bookforge.gui.launcher import window_for_startup
from bookforge.gui.icons import app_icon


def main():
    # logging su file + cattura di eccezioni Python e crash nativi (vedi
    # core/logging_setup.py): un crash all'avvio lascia sempre una traccia.
    log_file = setup_logging()
    log = logging.getLogger("bookforge")
    log.info("Avvio BookForge")

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
    log.info("Finestra principale mostrata; log in %s", log_file)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
