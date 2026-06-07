# Architettura di BookForge

Documento tecnico dell'architettura. Per la guida d'uso vedi `MANUALE.md`; per il
contesto sintetico destinato agli agenti AI vedi `../CLAUDE.md` e `../.claude/`.

## 1. Visione d'insieme

BookForge è un'applicazione desktop **PyQt6** per scrivere saggistica assistiti
dall'AI, dalla raccolta dei concetti fino all'output impaginato (LaTeX/PDF, EPUB,
Word). Il principio guida è **potenziare l'autore, non sostituirlo**: l'AI propone,
l'autore decide; tutto funziona anche **senza connessione né API key**.

```
            ┌──────────────────────────────────────────────┐
            │                   GUI (PyQt6)                  │  bookforge/gui/
            │  StartupDialog · MainWindow · LatexBrowser     │
            │  dialog (mentore, metriche, versioni, …)       │
            │  worker QThread · anteprime · highlighter      │
            └───────────────┬───────────────┬───────────────┘
                            │ usa           │ usa
            ┌───────────────▼──────┐  ┌─────▼──────────────────┐
            │   AGENTS (AI)        │  │   CORE (logica pura)    │
            │  bookforge/agents/   │  │  bookforge/core/        │
            │  engine + commands   │  │  model, latex, export,  │
            │  reale ⇄ offline     │  │  versioning, analysis…  │
            └───────────────┬──────┘  └─────┬──────────────────┘
                            │                │
                   ┌────────▼────────┐  ┌────▼─────────────────────┐
                   │  datapizza-ai   │  │  filesystem del progetto  │
                   │ (Claude/GPT/…)  │  │  book.json, *.tex, …       │
                   └─────────────────┘  └───────────────────────────┘
```

## 2. Architettura a strati

Tre strati con dipendenze a senso unico (`gui → agents → core`; `core` non dipende da
nessuno degli altri):

### 2.1 Core (`bookforge/core/`) — logica pura
Nessun import di PyQt, nessuna chiamata di rete, nessuno stato globale. Funzioni e
dataclass deterministiche, testabili in isolamento. Contiene:
- **Modello e persistenza** (`model.py`).
- **Resa**: LaTeX (`latex_builder.py`), compilazione (`compiler.py`), diagrammi
  (`diagram.py`), Word (`docx_formatter.py`), immagini (`image_gen.py`),
  export Markdown/EPUB (`export.py`).
- **Mentore/qualità**: metriche e note (`analysis.py`), argomentazione
  (`structure.py`), bibliografia (`biblio.py`), progressi (`progress.py`),
  versioni e diff (`versioning.py`).

### 2.2 Agents (`bookforge/agents/`) — orchestrazione AI
Astrae il provider di linguaggio e definisce la pipeline di generazione. È l'unico
strato che conosce `datapizza-ai`, ma il suo fallback offline non ne dipende.

### 2.3 GUI (`bookforge/gui/`) — presentazione
Guscio sottile: raccoglie input, invoca core/agents (le operazioni lente in thread) e
mostra i risultati. Nessuna logica di dominio significativa.

## 3. Modello dati e persistenza

Un **progetto** è semplicemente una **cartella** che contiene `book.json`.

```
Project(folder)
└── Book
    ├── metadati (title, subtitle, author, year, topic, abstract, preface, back_cover)
    ├── BookStyle (tone, audience, language, person, style_prompt, mode, doc_class, …)
    └── [Chapter]  (id, title, raw_concepts, text, latex, summary, argument, order)
```

- Serializzazione JSON via `to_dict()`/`from_dict()` su ogni entità.
- `from_dict` **ignora i campi sconosciuti e applica default ai mancanti**: i file
  salvati da versioni precedenti restano caricabili (compatibilità in avanti) senza
  codice di migrazione.
- Altri artefatti nella cartella: `book.tex` (output), `progress.json` (storico
  metriche), `references.bib` (bibliografia), `.bookforge_versions/` (istantanee
  versionate), eventuali export `.md`/`.epub` e immagini.

## 4. Astrazione del motore AI

Cuore della resilienza del sistema. Due implementazioni con **interfaccia identica**:

- `DatapizzaEngine` — usa `datapizza-ai` con il provider scelto (Anthropic/OpenAI/Google).
- `MockEngine` — offline, **deterministico**: euristiche reali (non placeholder) che
  rendono l'app utilizzabile e i test eseguibili senza chiave.

```python
engine, is_real, msg = build_engine(EngineConfig.from_env())
# senza API key  → (MockEngine, False, "Modalità offline…")
# con API key    → (DatapizzaEngine, True, "Motore datapizza-ai attivo…")
```

Interfaccia (entrambe le classi la rispettano): `write`, `coherence`, `format_latex`,
`summarize`, `proofread`, `edit_text`, `outline`, `transitions`, `bridge`,
`generate_diagram`, `caption`, `image_prompt`, `review_notes`, `socratic_questions`,
`claim_notes`, `argument_map`.

**Stile dell'autore**: `writer_prompt(book)` costruisce il system prompt dai campi di
`BookStyle`; se `style_prompt` è valorizzato, sovrascrive interamente il prompt di
default — è la leva che mantiene la "voce" coerente anche in autopilota.

## 5. Pipeline di generazione di un capitolo

A livello di modulo (`engine.py`), indipendente dall'implementazione del motore:

```
process_chapter(engine, book, ch):
   write(book, ch)            → prosa grezza            (usa concetti + stile + contesto)
   coherence(book, ch, text)  → raccordo coi vicini     (riassunti dei capitoli adiacenti)
   format_latex(text)         → corpo LaTeX             (ch.latex)
   summarize(text)            → riassunto breve         (ch.summary, risparmia token dopo)
```

L'**autopilota** aggiunge un passo iniziale:

```
autodraft_chapter:  se mancano i concetti → outline(book, ch) per ricavarne una scaletta
                    poi → process_chapter
autodraft_book:     autodraft_chapter su tutti i capitoli (o solo quelli vuoti)
```

I `summary` dei capitoli sono il meccanismo chiave di **economia di token**: il
controllo di coerenza usa i riassunti dei vicini invece dell'intero testo.

## 6. Concorrenza nella GUI

Le operazioni potenzialmente lente (chiamate AI, compilazione, formattazione Word) non
girano mai nel thread della UI. Worker dedicati su `QThread` con segnali
`progress/finished/failed`:

| Worker | Scopo |
|--------|-------|
| `worker.GenerateWorker` | pipeline di un capitolo |
| `autogen_worker.AutogenWorker` | autopilota (uno o tutti i capitoli) |
| `docx_worker` | sistemazione `.docx` |
| `ai_worker.AiWorker` | chiamata AI generica (mentore, mappa, ecc.) |

Le proposte AI sull'editor passano dall'anteprima **Accetta/Rifiuta/Rigenera**
(`ai_preview`): nessuna modifica al testo senza conferma.

## 7. Integrazioni esterne (opzionali, con fallback)

Rilevate a runtime; assenti = funzionalità degrada con grazia, l'app non si rompe:
- **datapizza-ai + client provider** — generazione AI (assente → offline).
- **LaTeX/latexmk** — compilazione PDF.
- **TeXstudio** — editing esterno (`find_texstudio`).
- **QtPdf** — anteprima PDF integrata (assente → apertura con l'app di sistema).
- **pandoc** — EPUB di qualità (assente → writer EPUB interno minimale).
- **mermaid-cli (`mmdc`) / Graphviz (`dot`)** — render diagrammi a immagine.
- **google-genai** — generazione immagini raster.

## 8. Decisioni di progetto

- **Core puro + GUI sottile** → testabilità alta e logica riusabile fuori dalla GUI.
- **Doppio engine con interfaccia identica** → l'app è sempre usabile e i test non
  richiedono rete/chiavi; il fallback offline è una feature, non un ripiego.
- **Progetto = cartella di file leggibili** (JSON, .tex, .bib) → trasparenza,
  versionabilità con git, nessun database.
- **Compatibilità in avanti via `from_dict` tollerante** → evoluzione del modello senza
  rompere i progetti esistenti.
- **Strumenti esterni opzionali** → installazione minima, degradazione graziosa.
- **LaTeX come formato di impaginazione** → qualità tipografica della saggistica;
  EPUB/Markdown/Word come export complementari.

## 9. Punti di estensione

- **Nuovo comando di editing**: aggiungi un `TextCommand` a `TEXT_COMMANDS`
  (`agents/commands.py`); appare nel menu 🤖 e usa `engine.edit_text`.
- **Nuova capacità AI**: metodo su `DatapizzaEngine` **e** `MockEngine` (stessa firma).
- **Nuovo formato di export**: funzione pura in `core/export.py` + azione nel menu
  "📤 Esporta" di `main_window.py`.
- **Nuovo pannello/strumento**: `gui/<nome>_dialog.py` + voce in toolbar/menu, con AI in
  un worker.
- **Nuovo provider di linguaggio**: estendi `_make_client` in `engine.py`.

## 10. Test

`pytest` copre lo strato core e l'engine offline senza GUI né rete
(`tests/conftest.py` mette la radice del repo su `sys.path`). I test della GUI vanno
eseguiti headless (`QT_QPA_PLATFORM=offscreen`) evitando i dialog modali. La suite è il
contratto che protegge la logica di dominio durante le evoluzioni.
