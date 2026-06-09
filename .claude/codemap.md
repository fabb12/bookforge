# Codemap — dove vive ogni cosa

Riferimento per agenti: evita di ri-esplorare il codice. Aggiornare quando si
aggiungono/spostano moduli. (~5.500 righe Python, PyQt6.)

## Entry point
- `main.py` — crea `QApplication`, applica il tema, mostra `StartupDialog`, poi apre la
  finestra giusta tramite `gui/launcher.window_for_startup`.
- `gui/launcher.py` — `window_for_startup(startup)` costruisce `MainWindow` (progetto).
  Condiviso da `main.py` e da «Chiudi progetto»; tiene in vita le finestre aperte.

## `bookforge/core/` — logica pura (no PyQt, no rete)
| File | Cosa fa | API principali |
|------|---------|----------------|
| `model.py` | Modello dati + persistenza | `Book`, `Chapter`, `BookStyle`, `Project`; `Project.save/load/is_project`; `Book.add_chapter/move_chapter/neighbors/to_dict/from_dict` |
| `latex_builder.py` | Genera il documento LaTeX completo | `build_latex(book)`, `escape_latex(s)`, `PREAMBLE`, `COVER`; layout editoriale (`style.layout == "editoriale"`): frontespizio TikZ, pagina copyright, quarta strutturata via `EDITORIAL_*` + `_editorial_*` (usa i campi `publisher`/`isbn`/`price`/`subtitle_b`/`back_quote*`/`back_blurb`) |
| `compiler.py` | Compila/apre PDF e TeXstudio | `compile_pdf`, `compile_tex`, `open_pdf`, `open_pdf_path`, `open_in_texstudio`, `find_main_tex`, `write_tex`, `find_latex_tool` (cerca latexmk/pdflatex nel PATH e nelle posizioni MiKTeX/TeX Live), `extract_latex_errors(log)` (riassunto compatto degli errori), `error_line_numbers(log)`/`error_regions(source, log)` (isolano le sole zone in errore per non mandare l'intero .tex all'LLM) |
| `diagram.py` | Snippet figure + render diagrammi | `tikz_figure`, `image_figure`, `render_mermaid`, `render_graphviz`, `strip_fences` |
| `docx_formatter.py` | Sistema file .docx (Word) | `format_docx(src,dst,rules)`, `DocxFormatRules`, `FormatReport` |
| `image_gen.py` | Generazione immagini raster (Google Imagen/Gemini, Ideogram) | `generate_image`, `image_available`, `ImageGenConfig` |
| `analysis.py` | Metriche + note di stile + claim | `analyze`, `heuristic_notes`, `flag_claims`, `gulpease_label`, `TextMetrics`, `Note`, `ClaimFlag` |
| `structure.py` | Mappa dell'argomentazione | `ArgumentMap`, `Argument`, `parse_ai_map`; `to_dict/from_dict/to_ai_format/to_concepts/to_outline` |
| `biblio.py` | Bibliografia BibTeX | `BibEntry`, `parse_bibtex`, `load_bib`, `save_bib`, `suggest_key`, `cite_command` |
| `progress.py` | Istantanee metriche nel tempo | `snapshot`, `save_snapshot`, `load_history`, `delta` (file `progress.json`) |
| `versioning.py` | Versioni opera + diff | `save_version`, `list_versions`, `load_version_book`, `diff_books`, `diff_html`, `diff_stats` (dir `.bookforge_versions/`) |
| `export.py` | Export Markdown/EPUB | `build_markdown`, `write_markdown`, `build_epub` (pandoc o writer interno) |
| `latex_import.py` | Importa un progetto LaTeX in un `Book` | `latex_to_book`, `import_latex_project`, `convert_latex_to_project` (risolve `\input`, estrae metadati e capitoli) |
| `word_to_latex.py` | Pipeline Word→LaTeX→PDF (pandoc + sistemazioni pure) | `WordFixOptions`, `convert_word`, `postprocess_latex`, `proofread_latex`, `pandoc_available` |
| `settings.py` | Impostazioni globali LLM persistenti (`~/.bookforge/settings.json`) | `AppSettings` (provider/modello/chiavi per-provider/temperatura/max_tokens/recent_projects + `add_recent_project`/`clean_recent_projects`), `PROVIDERS`, `DEFAULT_MODELS`, `AVAILABLE_MODELS`, `models_for`, `settings_path` |

## `bookforge/agents/` — orchestrazione AI
- `engine.py`:
  - `EngineConfig` (+`from_env`), `build_engine(config, force_offline=False) -> (engine, is_real, msg)`.
  - `writer_prompt(book)` costruisce il system prompt dallo stile (`style_prompt` lo sovrascrive).
  - `DatapizzaEngine` (reale via `datapizza-ai`) e `MockEngine` (offline). **Stessa interfaccia**:
    `write, coherence, format_latex, fix_latex, summarize, proofread, edit_text, outline, transitions,
    bridge, generate_diagram, caption, image_prompt, review_notes, socratic_questions,
    claim_notes, argument_map, book_section` (premessa/prologo/epilogo/quarta).
  - `GenerationCancelled`: eccezione di interruzione cooperativa (i worker la sollevano
    dal callback di progresso quando l'utente preme «Interrompi»).
  - Pipeline a livello modulo: `process_chapter`, `autodraft_chapter`, `autodraft_book`.
  - Parser: `_parse_review`, `_parse_claims`, `_strip_code_fences`.
- `commands.py`: `TEXT_COMMANDS` (lista `TextCommand`) + `command(key)`. Ogni comando è
  un'istruzione NL passata a `engine.edit_text`.

## `bookforge/gui/` — interfaccia (PyQt6)
- `startup.py` — `StartupDialog`: progetti recenti (cliccabili), crea/apri progetto,
  strumenti (converti LaTeX → BookForge, Word).
- `main_window.py` — `MainWindow`: lista capitoli, schede (Concetti/Testo/LaTeX/Riassunto),
  pannello Stile, toolbar. Hub che apre tutti i dialog e avvia i worker.
- Dialog: `mentor_dialog`, `metrics_dialog`, `argument_dialog`, `biblio_dialog`,
  `versions_dialog`, `docx_dialog`, `word_pdf_dialog` (Word→LaTeX→PDF), `settings_dialog` (API/LLM),
  `latex_log_dialog` (`LatexLogDialog`: finestra non modale col log di compilazione, errori
  evidenziati, pulsante «Correggi con AI»), `latex_fix_dialog` (`LatexFixDialog`: anteprima
  della correzione con riepilogo + diff colorato). Flusso in `main_window._run_latex_fix`:
  isola le zone in errore (`compiler.error_regions`) e manda all'AI SOLO quei frammenti
  (`engine.fix_latex_snippet`, fallback `fix_latex` per documenti piccoli) → splicing →
  anteprima → ricompila, in ciclo automatico fino a `_MAX_FIX_ATTEMPTS` finché il PDF non è generato.
- Menu della finestra: «🛠 Strumenti» (converti progetto LaTeX → BookForge, Word→LaTeX→PDF,
  formatta .docx) e «⚙ Impostazioni» (API e modelli LLM).
- Supporto: `ai_menu` (menu 🤖 a tasto destro), `ai_preview` (Accetta/Rifiuta/Rigenera),
  `latex_highlighter` (sintassi LaTeX), `pdf_view` (anteprima QtPdf + fallback), `theme` (QSS).
- Worker (QThread): `worker` (generazione capitolo), `autogen_worker` (autopilota),
  `docx_worker` (Word), `word_worker` (Word→LaTeX→PDF), `ai_worker` (chiamata AI generica).

## Test
- `tests/test_core.py` — moduli core puri (analisi, struttura, biblio, progressi,
  versioning incl. diff, export incl. validità EPUB, diagram, LaTeX, modello).
- `tests/test_engine_offline.py` — `MockEngine` + autopilota + parser.
- `tests/test_docx_formatter.py` — sistemazione .docx (richiede python-docx).
- `tests/conftest.py` — mette la radice del repo su `sys.path`.

## Artefatti su disco di un progetto
`book.json` (modello) · `book.tex` (output) · `progress.json` (metriche) ·
`references.bib` (bibliografia) · `.bookforge_versions/` (versioni) · export `.md`/`.epub`.
