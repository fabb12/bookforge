# Convenzioni di codice — BookForge

Per mantenere qualità e coerenza. Segui lo stile **già presente** nei file vicini.

## Lingua e stile
- Identificatori in inglese essenziale; **commenti e docstring in italiano**.
- Densità di commento come il codice circostante: spiega il *perché*, non l'ovvio.
- Docstring di modulo in cima a ogni file, una frase che dice scopo e vincoli
  (es. "puro e deterministico, nessuna rete").
- Niente emoji nel codice salvo che nelle stringhe della UI (label, pulsanti).

## Architettura a strati (rispettarla rigorosamente)
1. `core/` — **puro**: niente PyQt, niente I/O di rete, niente stato globale. Funzioni
   e dataclass testabili in isolamento. È qui che va la logica vera.
2. `agents/` — orchestrazione AI: engine reale + offline, prompt, pipeline. Può usare
   `datapizza-ai`, ma il fallback offline non deve dipenderne.
3. `gui/` — guscio sottile: raccoglie input, chiama core/agents, mostra risultati.
   Nessuna logica di dominio non banale qui dentro.

Regola pratica: se stai scrivendo un algoritmo dentro `gui/`, probabilmente va in `core/`.

## Modello dati e persistenza
- Ogni entità persistita è una `@dataclass` con `to_dict()` e `from_dict()`.
- `from_dict` **deve tollerare** campi mancanti o sconosciuti (usa il pattern
  `known = {f.name for f in fields(...)}` o `d.get(...)`). Garantisce compatibilità
  con `book.json` salvati da versioni precedenti.
- Aggiungere un campo: dagli un default sensato. Non serve migrazione: i vecchi file
  si caricano con il default, i nuovi lo salvano.

## Engine AI (parità obbligatoria)
- `DatapizzaEngine` e `MockEngine` espongono **la stessa interfaccia**. Aggiungi un
  metodo a uno → aggiungilo all'altro con identica firma e tipo di ritorno.
- L'offline deve essere **deterministico e utile** (euristiche), non un placeholder
  inutile: alimenta i test e l'uso senza chiave.
- Output AI testuali che vanno parsati: prevedi un parser tollerante (vedi
  `_parse_review`/`_parse_claims`) e ripulisci i code fence con `_strip_code_fences`.
- I prompt di sistema sono costanti maiuscole in `engine.py`. Lo stile dell'autore
  arriva da `writer_prompt(book)`; `book.style.style_prompt` lo sovrascrive del tutto.

## GUI (PyQt6)
- Le chiamate AI (potenzialmente lente) girano in un **QThread** (`AiWorker` o un worker
  dedicato). Mai chiamare l'engine nel thread della UI.
- Mostra avanzamento (`QProgressDialog`) e gestisci `failed` con un messaggio chiaro.
- Le proposte AI sull'editor passano dall'anteprima `ai_preview` (Accetta/Rifiuta/Rigenera).
- Un nuovo dialog: `gui/<nome>_dialog.py`, una classe `QDialog`, import "pigro" dentro il
  metodo di `main_window.py` che lo apre (evita import circolari e velocizza l'avvio).
- Salva lo stato degli editor prima di operazioni importanti (vedi `_commit_*`).
- Operazioni distruttive (rigenera tutto, ripristina versione) → salva prima una
  versione di sicurezza con `versioning.save_version`.

## Test
- Ogni funzione `core/` nuova ha un test in `tests/`. Restano **puri e headless**.
- Per testare pezzi di GUI: `QT_QPA_PLATFORM=offscreen`, istanzia i widget, **non**
  invocare dialog modali (`QMessageBox.*`, `QInputDialog.*`) che bloccano: verifica
  invece i metodi/side-effect sottostanti.
- Esegui `pytest -q` prima di committare; tutto deve restare verde.

## Dipendenze esterne
- Mantieni il core privo di dipendenze pesanti. Strumenti opzionali (pandoc, mmdc, dot,
  TeXstudio, QtPdf) vanno **rilevati a runtime** con fallback grazioso, mai assunti.

## Git
- Branch della sessione; commit in italiano, corpo che spiega cosa e perché.
- Niente pull request salvo richiesta esplicita dell'utente.
