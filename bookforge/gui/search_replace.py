from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton,
    QCheckBox, QLabel, QMessageBox
)
from PyQt6.QtGui import QTextDocument, QTextCursor
from PyQt6.QtCore import Qt

class SearchReplaceWidget(QWidget):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Riga 1: Cerca
        row1 = QHBoxLayout()
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Cerca...")
        self.find_input.returnPressed.connect(self.find_next)

        self.btn_find_next = QPushButton("Trova successivo")
        self.btn_find_next.clicked.connect(self.find_next)

        self.btn_find_prev = QPushButton("Trova precedente")
        self.btn_find_prev.clicked.connect(self.find_prev)

        self.btn_close = QPushButton("X")
        self.btn_close.setFixedWidth(30)
        self.btn_close.clicked.connect(self.hide)

        row1.addWidget(QLabel("Cerca:"))
        row1.addWidget(self.find_input)
        row1.addWidget(self.btn_find_prev)
        row1.addWidget(self.btn_find_next)
        row1.addWidget(self.btn_close)

        # Riga 2: Sostituisci
        row2 = QHBoxLayout()
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Sostituisci con...")
        self.replace_input.returnPressed.connect(self.replace)

        self.btn_replace = QPushButton("Sostituisci")
        self.btn_replace.clicked.connect(self.replace)

        self.btn_replace_all = QPushButton("Sostituisci tutto")
        self.btn_replace_all.clicked.connect(self.replace_all)

        row2.addWidget(QLabel("Sostituisci:"))
        row2.addWidget(self.replace_input)
        row2.addWidget(self.btn_replace)
        row2.addWidget(self.btn_replace_all)

        # Riga 3: Opzioni
        row3 = QHBoxLayout()
        self.chk_case = QCheckBox("Maiuscole/minuscole")
        self.chk_whole = QCheckBox("Parola intera")
        self.chk_regex = QCheckBox("Espressione regolare")

        row3.addWidget(self.chk_case)
        row3.addWidget(self.chk_whole)
        row3.addWidget(self.chk_regex)
        row3.addStretch()

        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addLayout(row3)

    def showEvent(self, event):
        self.find_input.setFocus()
        self.find_input.selectAll()
        super().showEvent(event)

    def _get_find_flags(self, backward=False):
        flags = QTextDocument.FindFlag(0)
        if self.chk_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.chk_whole.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        return flags

    def find_next(self):
        self._find(backward=False)

    def find_prev(self):
        self._find(backward=True)

    def _find(self, backward=False):
        term = self.find_input.text()
        if not term:
            return False

        if self.chk_regex.isChecked():
            from PyQt6.QtCore import QRegularExpression
            opts = QRegularExpression.PatternOption.NoPatternOption
            if not self.chk_case.isChecked():
                opts |= QRegularExpression.PatternOption.CaseInsensitiveOption

            pattern = term
            if self.chk_whole.isChecked():
                pattern = r'\b' + pattern + r'\b'

            rx = QRegularExpression(pattern, opts)

            flags = QTextDocument.FindFlag(0)
            if backward:
                flags |= QTextDocument.FindFlag.FindBackward

            found = self.editor.find(rx, flags)
        else:
            flags = self._get_find_flags(backward)
            found = self.editor.find(term, flags)

        if not found:
            # Riparti dall'inizio o dalla fine (wrap around)
            cur = self.editor.textCursor()
            if backward:
                cur.movePosition(QTextCursor.MoveOperation.End)
            else:
                cur.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cur)

            if self.chk_regex.isChecked():
                found = self.editor.find(rx, flags)
            else:
                found = self.editor.find(term, self._get_find_flags(backward))

        return found

    def replace(self):
        cur = self.editor.textCursor()
        if cur.hasSelection():
            self.editor.insertPlainText(self.replace_input.text())
            self.find_next()
        else:
            self.find_next()

    def replace_all(self):
        term = self.find_input.text()
        if not term:
            return

        cur = self.editor.textCursor()
        cur.beginEditBlock()
        cur.movePosition(QTextCursor.MoveOperation.Start)
        self.editor.setTextCursor(cur)

        count = 0
        # Continua a cercare dal punto corrente senza wrap around per evitare cicli infiniti
        while True:
            if self.chk_regex.isChecked():
                from PyQt6.QtCore import QRegularExpression
                opts = QRegularExpression.PatternOption.NoPatternOption
                if not self.chk_case.isChecked():
                    opts |= QRegularExpression.PatternOption.CaseInsensitiveOption
                pattern = term
                if self.chk_whole.isChecked():
                    pattern = r'\b' + pattern + r'\b'
                rx = QRegularExpression(pattern, opts)
                found = self.editor.find(rx)
            else:
                found = self.editor.find(term, self._get_find_flags(False))

            if not found:
                break

            self.editor.insertPlainText(self.replace_input.text())
            count += 1

        cur.endEditBlock()
        QMessageBox.information(self, "Sostituisci tutto", f"{count} occorrenze sostituite.")
