# CLAUDE.md — Contesto per agenti AI

> File auto-caricato da Claude Code. Tenuto **conciso di proposito**: i dettagli
> approfonditi stanno in `.claude/codemap.md`, `.claude/conventions.md`,
> `docs/ARCHITETTURA.md` e `docs/MANUALE.md` — leggili **solo quando servono**.

## Cos'è BookForge
App desktop (PyQt6) che aiuta a scrivere **saggistica**: dai concetti grezzi alla
prosa, al LaTeX, al PDF/EPUB/Word. Filosofia: **potenziare l'autore, non sostituirlo**.
Italiano come lingua di prodotto (UI, prompt, docstring).

## Regole d'oro (non negoziabili)
1. **Tutto funziona offline.** Ogni capacità AI ha un equivalente deterministico in
   `MockEngine`. `build_engine()` ripiega su `MockEngine` se manca la API key. Mai
   introdurre un percorso che si rompe senza rete/chiave.
2. **Logica core = pura e testabile.** `bookforge/core/` non importa PyQt né fa rete.
   La GUI (`bookforge/gui/`) è un guscio sottile sopra core+agents.
3. **Le chiamate AI nella GUI passano da un thread.** Usa `AiWorker`/`worker` (QThread):
   mai bloccare la UI. Le proposte AI passano da anteprima **Accetta/Rifiuta/Rigenera**.
4. **L'AI non riscrive di nascosto.** Modalità Mentore = feedback. L'autopilota
   genera solo su azione esplicita dell'utente.
5. **Parità engine.** Se aggiungi un metodo a `DatapizzaEngine`, aggiungilo **anche** a
   `MockEngine` con la stessa firma.

## Comandi
```bash
python main.py                              # avvia l'app (richiede display)
QT_QPA_PLATFORM=offscreen python main.py    # avvio headless (smoke test)
pytest -q                                   # suite di test (core + engine offline + docx)
python -m py_compile bookforge/**/*.py      # controllo sintattico rapido
```
Test GUI headless: prefissa **sempre** `QT_QPA_PLATFORM=offscreen`. Attenzione: i
`QMessageBox`/`QInputDialog` modali **bloccano** in headless — non chiamarli nei test.

## Configurazione (env)
- `BOOKFORGE_PROVIDER` (anthropic|openai|google, default anthropic)
- `BOOKFORGE_MODEL` (default `claude-opus-4-8`)
- `BOOKFORGE_API_KEY` (o `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GOOGLE_API_KEY`)
- Senza chiave → modalità offline (`MockEngine`).
- In alternativa all'env: menu **⚙ Impostazioni** → salva provider/modello/chiavi (per-provider)
  e parametri in `~/.bookforge/settings.json` (`core/settings.py`; override path con `BOOKFORGE_CONFIG`).

## Mappa rapida (dettagli in `.claude/codemap.md`)
- `core/model.py` — `Book`, `Chapter`, `BookStyle`, `Project`. Persistenza = cartella
  con `book.json`. Round-trip via `to_dict`/`from_dict` (ignora campi sconosciuti).
- `agents/engine.py` — `DatapizzaEngine` (reale) + `MockEngine` (offline) + pipeline
  `process_chapter`/`autodraft_*` + parser. `build_engine(config) -> (engine, is_real, msg)`.
- `agents/commands.py` — registro `TEXT_COMMANDS` dei comandi di editing (menu ↔ engine).
- `core/{latex_builder,compiler,diagram,docx_formatter,export,versioning,analysis,structure,biblio,progress}.py`
  — funzioni pure per LaTeX/PDF, diagrammi, Word, export, versioni, mentore.
- `gui/main_window.py` — finestra principale (capitoli, schede, toolbar, tutti i dialog).

## Convenzioni (dettagli in `.claude/conventions.md`)
- Codice in inglese minimale; **commenti e docstring in italiano**, densità come il
  codice circostante.
- Dataclass con `to_dict`/`from_dict` per ogni entità persistita; `from_dict` tollera
  campi mancanti/extra (compatibilità in avanti).
- Aggiungere un campo al modello: dargli un default, e basta — `from_dict` lo gestisce.
- Nuovo dialog GUI: file `gui/<nome>_dialog.py`, agganciato da `main_window.py`,
  AI via worker, nessun blocco della UI.
- Test: ogni nuova funzione core va in `tests/`; restano puri e headless.

## Workflow git
- Sviluppo sul branch indicato dalla sessione; `git push -u origin <branch>`.
- Messaggi di commit in italiano, descrittivi. **Niente PR** se non richiesta.
- Non inserire identificatori di modello negli artefatti del repo.
