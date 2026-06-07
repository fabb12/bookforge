# Codemap — dove vive ogni cosa

Riferimento per agenti: evita di ri-esplorare il codice. Aggiornare quando si
aggiungono/spostano moduli. (~5.500 righe Python, PyQt6.)

## Entry point
- `main.py` — crea `QApplication`, applica il tema, mostra `StartupDialog`, poi apre
  `MainWindow` (progetto) **oppure** `LatexBrowserWindow` (cartella LaTeX libera).

## `bookforge/core/` — logica pura (no PyQt, no rete)
| File | Cosa fa | API principali |
|------|---------|----------------|
| `model.py` | Modello dati + persistenza | `Book`, `Chapter`, `BookStyle`, `Project`; `Project.save/load/is_project`; `Book.add_chapter/move_chapter/neighbors/to_dict/from_dict` |
| `latex_builder.py` | Genera il documento LaTeX completo | `build_latex(book)`, `escape_latex(s)`, `PREAMBLE`, `COVER` |
| `compiler.py` | Compila/apre PDF e TeXstudio | `compile_pdf`, `compile_tex`, `open_pdf`, `open_pdf_path`, `open_in_texstudio`, `find_main_tex`, `write_tex` |
| `diagram.py` | Snippet figure + render diagrammi | `tikz_figure`, `image_figure`, `render_mermaid`, `render_graphviz`, `strip_fences` |
| `docx_formatter.py` | Sistema file .docx (Word) | `format_docx(src,dst,rules)`, `DocxFormatRules`, `FormatReport` |
| `image_gen.py` | Generazione immagini raster | `generate_image`, `image_available`, `ImageGenConfig` |
| `analysis.py` | Metriche + note di stile + claim | `analyze`, `heuristic_notes`, `flag_claims`, `gulpease_label`, `TextMetrics`, `Note`, `ClaimFlag` |
| `structure.py` | Mappa dell'argomentazione | `ArgumentMap`, `Argument`, `parse_ai_map`; `to_dict/from_dict/to_ai_format/to_concepts/to_outline` |
| `biblio.py` | Bibliografia BibTeX | `BibEntry`, `parse_bibtex`, `load_bib`, `save_bib`, `suggest_key`, `cite_command` |
| `progress.py` | Istantanee metriche nel tempo | `snapshot`, `save_snapshot`, `load_history`, `delta` (file `progress.json`) |
| `versioning.py` | Versioni opera + diff | `save_version`, `list_versions`, `load_version_book`, `diff_books`, `diff_html`, `diff_stats` (dir `.bookforge_versions/`) |
| `export.py` | Export Markdown/EPUB | `build_markdown`, `write_markdown`, `build_epub` (pandoc o writer interno) |

## `bookforge/agents/` — orchestrazione AI
- `engine.py`:
  - `EngineConfig` (+`from_env`), `build_engine(config, force_offline=False) -> (engine, is_real, msg)`.
  - `writer_prompt(book)` costruisce il system prompt dallo stile (`style_prompt` lo sovrascrive).
  - `DatapizzaEngine` (reale via `datapizza-ai`) e `MockEngine` (offline). **Stessa interfaccia**:
    `write, coherence, format_latex, summarize, proofread, edit_text, outline, transitions,
    bridge, generate_diagram, caption, image_prompt, review_notes, socratic_questions,
    claim_notes, argument_map`.
  - Pipeline a livello modulo: `process_chapter`, `autodraft_chapter`, `autodraft_book`.
  - Parser: `_parse_review`, `_parse_claims`, `_strip_code_fences`.
- `commands.py`: `TEXT_COMMANDS` (lista `TextCommand`) + `command(key)`. Ogni comando è
  un'istruzione NL passata a `engine.edit_text`.

## `bookforge/gui/` — interfaccia (PyQt6)
- `startup.py` — `StartupDialog`: crea/apri progetto, apri cartella LaTeX, strumenti Word.
- `main_window.py` — `MainWindow`: lista capitoli, schede (Concetti/Testo/LaTeX/Riassunto),
  pannello Stile, toolbar. Hub che apre tutti i dialog e avvia i worker.
- `latex_browser.py` — `LatexBrowserWindow`: editor di una cartella LaTeX qualsiasi.
- Dialog: `mentor_dialog`, `metrics_dialog`, `argument_dialog`, `biblio_dialog`,
  `versions_dialog`, `docx_dialog`.
- Supporto: `ai_menu` (menu 🤖 a tasto destro), `ai_preview` (Accetta/Rifiuta/Rigenera),
  `latex_highlighter` (sintassi LaTeX), `pdf_view` (anteprima QtPdf + fallback), `theme` (QSS).
- Worker (QThread): `worker` (generazione capitolo), `autogen_worker` (autopilota),
  `docx_worker` (Word), `ai_worker` (chiamata AI generica).

## Test
- `tests/test_core.py` — moduli core puri (analisi, struttura, biblio, progressi,
  versioning incl. diff, export incl. validità EPUB, diagram, LaTeX, modello).
- `tests/test_engine_offline.py` — `MockEngine` + autopilota + parser.
- `tests/test_docx_formatter.py` — sistemazione .docx (richiede python-docx).
- `tests/conftest.py` — mette la radice del repo su `sys.path`.

## Artefatti su disco di un progetto
`book.json` (modello) · `book.tex` (output) · `progress.json` (metriche) ·
`references.bib` (bibliografia) · `.bookforge_versions/` (versioni) · export `.md`/`.epub`.
