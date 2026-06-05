"""Punto di ingresso di BookForge."""
import sys

from PyQt6.QtWidgets import QApplication

from bookforge.gui.theme import DARK_QSS
from bookforge.gui.startup import StartupDialog
from bookforge.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("BookForge")
    app.setStyleSheet(DARK_QSS)

    startup = StartupDialog()
    if startup.exec() != StartupDialog.DialogCode.Accepted or startup.project is None:
        return 0

    win = MainWindow(startup.project)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
