"""Punto di ingresso di BookForge."""
import sys

from PyQt6.QtWidgets import QApplication

from bookforge.gui.theme import DARK_QSS
from bookforge.gui.startup import StartupDialog
from bookforge.gui.launcher import window_for_startup
from bookforge.gui.icons import app_icon


def main():
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
