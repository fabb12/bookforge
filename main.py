"""Punto di ingresso di BookForge."""
import sys

from PyQt6.QtWidgets import QApplication

from bookforge.gui.theme import DARK_QSS
from bookforge.gui.startup import StartupDialog
from bookforge.gui.main_window import MainWindow
from bookforge.gui.latex_browser import LatexBrowserWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("BookForge")
    app.setStyleSheet(DARK_QSS)

    startup = StartupDialog()
    if startup.exec() != StartupDialog.DialogCode.Accepted:
        return 0

    if startup.project is not None:
        win = MainWindow(startup.project)
    elif startup.latex_folder is not None:
        win = LatexBrowserWindow(startup.latex_folder)
    else:
        return 0

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
