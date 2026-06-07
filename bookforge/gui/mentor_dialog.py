"""Modalità Mentore: feedback per crescere, non riscrittura.

Mostra subito un'analisi euristica (offline) del capitolo corrente — note di
stile, domande socratiche, claim da verificare e metriche — e permette di
«Approfondire con AI» per note più ricche. Nessun testo viene riscritto: è uno
strumento di apprendimento.
"""
from __future__ import annotations

from html import escape

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QTextBrowser,
    QPushButton, QProgressDialog, QMessageBox, QWidget,
)

from ..core import analysis
from .ai_worker import AiWorker


class MentorDialog(QDialog):
    def __init__(self, parent, engine, book, text: str):
        super().__init__(parent)
        self.engine = engine
        self.book = book
        self.text = text or ""
        self._worker: AiWorker | None = None

        self.setWindowTitle("🎓 Modalità Mentore")
        self.resize(720, 640)
        self._build_ui()
        self._render_offline()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        self.header = QLabel(""); self.header.setObjectName("Subtitle")
        self.header.setWordWrap(True)
        lay.addWidget(self.header)

        self.tabs = QTabWidget()
        self.notes_view = QTextBrowser()
        self.questions_view = QTextBrowser()
        self.claims_view = QTextBrowser()
        self.tabs.addTab(self.notes_view, "Revisione")
        self.tabs.addTab(self.questions_view, "Domande")
        self.tabs.addTab(self.claims_view, "Claim da verificare")
        lay.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        self.ai_btn = QPushButton("🤖 Approfondisci con AI"); self.ai_btn.setObjectName("Primary")
        self.ai_btn.clicked.connect(self._enrich_with_ai)
        close = QPushButton("Chiudi"); close.clicked.connect(self.accept)
        row.addStretch(1); row.addWidget(close); row.addWidget(self.ai_btn)
        lay.addLayout(row)

    # ---------------------------------------------------------- rendering
    def _render_offline(self):
        if not self.text.strip():
            self.header.setText("Nessun testo da analizzare nel capitolo corrente.")
            self.ai_btn.setEnabled(False)
            return
        m = analysis.analyze(self.text)
        self.header.setText(
            f"<b>Leggibilità Gulpease:</b> {m.gulpease} ({analysis.gulpease_label(m.gulpease)}) · "
            f"<b>parole:</b> {m.words} · <b>frasi:</b> {m.sentences} · "
            f"<b>media parole/frase:</b> {m.avg_sentence_len} · "
            f"<b>passivo:</b> ~{int(m.passive_ratio*100)}% · "
            f"<b>varietà lessicale:</b> {m.lexical_diversity}")
        self._notes = [_note_dict(n) for n in analysis.heuristic_notes(self.text, m)]
        self._questions = []  # popolate dall'AI; offline usiamo quelle dell'engine
        self._claims = [{"text": c.text, "reason": c.reason, "source": "euristica"}
                        for c in analysis.flag_claims(self.text)]
        # domande socratiche offline (dall'engine, sempre disponibili)
        try:
            self._questions = self.engine.socratic_questions(self.text, self.book)
        except Exception:  # noqa: BLE001
            self._questions = []
        self._refresh_views()

    def _refresh_views(self):
        self.notes_view.setHtml(_notes_html(self._notes))
        self.questions_view.setHtml(_questions_html(self._questions))
        self.claims_view.setHtml(_claims_html(self._claims))

    # ---------------------------------------------------------- AI
    def _enrich_with_ai(self):
        if self._worker and self._worker.isRunning():
            return
        busy = QProgressDialog("Il mentore sta leggendo…", None, 0, 0, self)
        busy.setWindowTitle("AI"); busy.setCancelButton(None); busy.show()

        text, book, eng = self.text, self.book, self.engine

        def fn():
            return {
                "notes": eng.review_notes(text, book),
                "questions": eng.socratic_questions(text, book),
                "claims": eng.claim_notes(text, book),
            }

        def done(res):
            busy.close()
            # le note AI vanno in cima, le euristiche restano sotto
            ai_notes = res.get("notes", [])
            self._notes = ai_notes + [n for n in self._notes if n.get("source") != "ai"]
            if res.get("questions"):
                self._questions = res["questions"]
            ai_claims = res.get("claims", [])
            self._claims = ai_claims + [c for c in self._claims if c.get("source") != "ai"]
            self._refresh_views()

        def fail(err):
            busy.close()
            QMessageBox.critical(self, "Errore AI", err)

        self._worker = AiWorker(fn)
        self._worker.done.connect(done)
        self._worker.failed.connect(fail)
        self._worker.start()


# ------------------------------------------------------------------ helpers HTML
def _note_dict(n) -> dict:
    return {"issue": n.issue, "detail": n.detail, "suggestion": n.suggestion,
            "severity": n.severity, "excerpt": n.excerpt, "source": n.source}


def _badge(source: str) -> str:
    return "🤖 AI" if source == "ai" else "🔎 euristica"


def _notes_html(notes: list[dict]) -> str:
    if not notes:
        return "<p>Nessun rilievo. Ottimo lavoro ✨</p>"
    out = []
    for n in notes:
        out.append(
            f"<p><b>{escape(n.get('issue',''))}</b> "
            f"<span style='color:#888'>· {_badge(n.get('source',''))}</span><br>")
        if n.get("detail"):
            out.append(f"<i>Perché:</i> {escape(n['detail'])}<br>")
        if n.get("suggestion"):
            out.append(f"<i>Suggerimento:</i> {escape(n['suggestion'])}<br>")
        if n.get("excerpt"):
            out.append(f"<span style='color:#888'>«{escape(n['excerpt'])}…»</span>")
        out.append("</p>")
    return "".join(out)


def _questions_html(questions: list[str]) -> str:
    if not questions:
        return "<p>Premi «Approfondisci con AI» per ricevere domande di sviluppo.</p>"
    items = "".join(f"<li>{escape(q)}</li>" for q in questions)
    return ("<p>Domande per sviluppare e rafforzare il pensiero "
            "(rispondile scrivendo, non te le risolve l'AI):</p>"
            f"<ul>{items}</ul>")


def _claims_html(claims: list[dict]) -> str:
    if not claims:
        return "<p>Nessuna affermazione fattuale da verificare individuata.</p>"
    out = ["<p>Affermazioni che converrebbe <b>citare o verificare</b> "
           "(l'AI non inventa fonti):</p>"]
    for c in claims:
        out.append(f"<p>• {escape(c.get('text',''))}<br>"
                   f"<span style='color:#888'>{escape(c.get('reason',''))} "
                   f"· {_badge(c.get('source',''))}</span></p>")
    return "".join(out)
