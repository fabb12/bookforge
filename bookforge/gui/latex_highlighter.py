"""Evidenziazione della sintassi LaTeX per gli editor (QSyntaxHighlighter).

Leggera: comandi \\foo, ambienti begin/end, argomenti in graffe, matematica $…$,
e commenti %. Pensata per rendere leggibili le modifiche rapide, non per essere
un IDE completo (per quello c'è TeXstudio).
"""
from __future__ import annotations

import re

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont


def _fmt(color: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class LatexHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        cmd = _fmt("#7aa2f7", bold=True)       # \comandi
        env = _fmt("#bb9af7", bold=True)       # \begin{...}/\end{...}
        arg = _fmt("#9ece6a")                  # {argomenti}
        opt = _fmt("#e0af68")                  # [opzioni]
        math = _fmt("#7dcfff")                 # $...$
        comment = _fmt("#5c6370", italic=True)  # % commenti

        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = [
            (QRegularExpression(r"\\(begin|end)\s*\{[^}]*\}"), env),
            (QRegularExpression(r"\\[A-Za-z@]+\*?"), cmd),
            (QRegularExpression(r"\{[^{}]*\}"), arg),
            (QRegularExpression(r"\[[^\[\]]*\]"), opt),
            (QRegularExpression(r"\$[^$]*\$"), math),
        ]
        self._comment = comment

    def highlightBlock(self, text: str):
        for rx, fmt in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)
        # commenti % (ignorando \% sfuggito) fino a fine riga
        for m in re.finditer(r"(?<!\\)%.*$", text):
            self.setFormat(m.start(), len(text) - m.start(), self._comment)


def attach_latex_highlighter(editor) -> LatexHighlighter:
    """Aggancia l'evidenziatore al documento di un QPlainTextEdit/QTextEdit."""
    return LatexHighlighter(editor.document())
