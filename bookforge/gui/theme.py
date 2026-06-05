"""Foglio di stile (QSS) dark theme per l'app."""

DARK_QSS = """
* { font-family: 'Segoe UI', 'Helvetica Neue', sans-serif; font-size: 14px; }

QWidget { background-color: #1e1f26; color: #e6e6e6; }

QMainWindow, QDialog { background-color: #1a1b21; }

QLabel#Title { font-size: 22px; font-weight: 700; color: #ffffff; }
QLabel#Subtitle { color: #9aa0aa; font-size: 13px; }
QLabel#SectionLabel { color: #7aa2f7; font-weight: 600; font-size: 12px;
                      text-transform: uppercase; letter-spacing: 1px; }

QPushButton {
    background-color: #2a2d37; color: #e6e6e6; border: 1px solid #3a3d49;
    border-radius: 8px; padding: 8px 16px;
}
QPushButton:hover { background-color: #353944; border-color: #4a4f5e; }
QPushButton:pressed { background-color: #232630; }
QPushButton:disabled { color: #5a5e69; background-color: #232530; }

QPushButton#Primary {
    background-color: #7aa2f7; color: #11131a; border: none; font-weight: 600;
}
QPushButton#Primary:hover { background-color: #8fb3ff; }
QPushButton#Primary:disabled { background-color: #3c4660; color: #7c849c; }

QPushButton#Danger { color: #ff7b8a; border-color: #5a3540; }
QPushButton#Danger:hover { background-color: #3a2730; }

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background-color: #15161c; color: #e6e6e6; border: 1px solid #2f323d;
    border-radius: 8px; padding: 7px; selection-background-color: #7aa2f7;
    selection-color: #11131a;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border-color: #7aa2f7;
}

QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #15161c; border: 1px solid #2f323d;
    selection-background-color: #7aa2f7; selection-color: #11131a;
}

QListWidget {
    background-color: #15161c; border: 1px solid #2f323d; border-radius: 8px;
    padding: 4px;
}
QListWidget::item { padding: 9px; border-radius: 6px; }
QListWidget::item:selected { background-color: #2d3550; color: #ffffff; }
QListWidget::item:hover { background-color: #23252f; }

QTabWidget::pane { border: 1px solid #2f323d; border-radius: 8px; top: -1px; }
QTabBar::tab {
    background: #1e1f26; color: #9aa0aa; padding: 9px 18px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px;
}
QTabBar::tab:selected { background: #2a2d37; color: #ffffff; }

QGroupBox {
    border: 1px solid #2f323d; border-radius: 10px; margin-top: 14px; padding-top: 8px;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #7aa2f7; }

QScrollBar:vertical { background: #15161c; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #3a3d49; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4a4f5e; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }

QStatusBar { background: #15161c; color: #9aa0aa; }
QSplitter::handle { background: #2f323d; }

QProgressBar {
    border: 1px solid #2f323d; border-radius: 8px; background: #15161c;
    text-align: center; color: #e6e6e6; height: 18px;
}
QProgressBar::chunk { background-color: #7aa2f7; border-radius: 7px; }

QMenu { background: #1e1f26; border: 1px solid #2f323d; }
QMenu::item:selected { background: #2d3550; }
"""
