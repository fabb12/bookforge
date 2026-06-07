# 📚 BookForge

Strumento desktop (PyQt6, tema dark) per **scrivere e mantenere libri / saggi / articoli**
con l'aiuto di un sistema **multi-agente** basato su [datapizza-ai](https://github.com/datapizza-labs/datapizza-ai).

Tu inserisci i **concetti grezzi** di un capitolo; gli agenti li trasformano in prosa
secondo lo **stile** che imposti, ne curano la **coerenza** con i capitoli vicini, li
**formattano in LaTeX** e ne generano un **riassunto**. Il risultato è un file `.tex`
completo (copertina, prefazione, indice, capitoli, quarta di copertina) pronto da
compilare in **TeXstudio**.

---

## Installazione

```bash
pip install -r requirements.txt
```

Requisiti:
- Python 3.10 – 3.12
- Una distribuzione LaTeX (TeX Live o MiKTeX) — per la compilazione del PDF
- TeXstudio (opzionale, per aprire/compilare manualmente)

## Avvio

```bash
python main.py
```

### Configurare il motore AI
L'app cerca la API key da variabili d'ambiente o dal pannello **Motore** nell'interfaccia.
Il provider consigliato è **Anthropic (Claude Opus 4.8)** per la qualità di scrittura:

```bash
export BOOKFORGE_PROVIDER=anthropic   # anthropic | openai | google
export BOOKFORGE_MODEL=claude-opus-4-8
export BOOKFORGE_API_KEY=sk-ant-...
```

Per la **generazione di immagini** (Google Imagen / Gemini):

```bash
export GOOGLE_API_KEY=...             # oppure BOOKFORGE_IMAGE_API_KEY
export BOOKFORGE_IMAGE_MODEL=imagen-3.0-generate-002
```

Senza API key l'app parte in **modalità offline**: genera testo simulato, utile per
provare interfaccia e flusso di compilazione senza costi.

### Scrittura assistita dall'AI
Negli editor (testo del capitolo, LaTeX, e browser dei file) il **tasto destro → 🤖 AI**
offre comandi sulla selezione e strumenti di generazione:

- **Comandi sul testo**: Riscrivi, Espandi, Accorcia, Continua, Più formale, Più
  divulgativo, Correggi. Ogni proposta passa da un'**anteprima Accetta / Rifiuta /
  Rigenera** — l'AI non sovrascrive mai senza conferma, e la proposta è modificabile.
- **Genera diagramma**: l'AI produce **codice TikZ** (LaTeX nativo, vettoriale ed
  editabile) oppure un diagramma **Mermaid** renderizzato a immagine. Inserito come
  `figure` con didascalia automatica.
- **Genera immagine**: l'AI scrive il prompt, **Google Imagen** genera l'immagine in
  `images/`, e viene inserita con `\includegraphics` e **didascalia generata** sotto.

Nella finestra principale, il menu **🧠 Capitolo (AI)** offre comandi sull'intero
capitolo corrente (anche questi con anteprima Accetta/Rifiuta/Rigenera):

- **Genera scaletta** — produce una scaletta puntata dal titolo e dai concetti, e la
  inserisce nella scheda «Concetti».
- **Migliora raccordi** — rivede le transizioni tra paragrafi/sezioni del testo senza
  cambiarne i contenuti.
- **Ponte col capitolo precedente / successivo** — genera un paragrafo di raccordo che
  collega il capitolo a quello adiacente, usando i riassunti (risparmio di token).
- **Rigenera riassunto** — riscrive il riassunto del capitolo nella scheda «Riassunto».

### 🎓 Mentore — crescere come autore (non solo generare)
Il menu **🎓 Mentore** mette al centro l'apprendimento: dà feedback e strumenti, non
riscrive al posto tuo.

- **Revisione (feedback)** — analizza il capitolo e mostra **note di stile con il
  *perché*** (frasi troppo lunghe, passivo, ripetizioni, riempitivi, leggibilità),
  **domande socratiche** per sviluppare il pensiero, e **claim da verificare/citare**.
  Funziona già offline (euristiche deterministiche) e con **«Approfondisci con AI»**
  aggiunge note più ricche. Non riscrive il testo: lo migliori tu.
- **Dashboard di crescita** — metriche per capitolo (indice **Gulpease**, lunghezza
  media delle frasi, passivo, varietà lessicale, frasi lunghe). Salva un'**istantanea**
  in `progress.json` e confronta con la precedente per **vedere i progressi nel tempo**.
- **Mappa dell'argomentazione** — struttura tesi → argomenti → prove → obiezioni →
  repliche *prima* di scrivere. Generabile con l'AI, modificabile, ed **esportabile nei
  «Concetti»** del capitolo per la stesura.
- **Bibliografia** — gestione di `references.bib` (BibTeX) con aggiunta/modifica voci e
  inserimento di `\cite{...}` nel LaTeX.

> Filosofia: BookForge è pensato come **potenziamento della creatività** e mentore di
> scrittura, non come sostituto dell'autore. Ogni proposta dell'AI passa da
> un'anteprima e da una tua conferma.

### Modalità di lavoro — la scelta è tua
Nella scheda **Stile** puoi impostare la **Modalità di lavoro**:

- **🎓 mentore** — l'AI dà feedback e strumenti, scrivi tu (default).
- **⚖️ bilanciata** — generi con un clic, ma con anteprima/conferma.
- **🚀 autopilota** — autogenerazione rapida con il minimo sforzo, **mantenendo lo
  stile del tuo prompt**.

Il menu **🚀 Autogenera** offre: *capitolo corrente*, *capitoli vuoti*, *rigenera tutti*.
Se un capitolo non ha concetti, l'autopilota ne ricava prima una scaletta dal titolo.
Prima di una generazione massiva viene salvata automaticamente una versione di sicurezza.

### Versioni ed export
- **🕓 Versioni** — salva istantanee dell'opera, **confronta le differenze con un diff
  visuale colorato** (verde = aggiunto, rosso = rimosso) per capitolo, con riepilogo
  righe aggiunte/rimosse, e **ripristina** una versione precedente (con backup
  automatico prima del ripristino). Le versioni vivono in `.bookforge_versions/`.
- **📤 Esporta** — oltre a LaTeX/PDF/Word, esporta in **Markdown** e **EPUB** (EPUB via
  `pandoc` se installato, altrimenti con un writer interno senza dipendenze).

### Editor ed anteprima
- **Evidenziazione sintassi LaTeX** nell'editor LaTeX e nei file `.tex` aperti dal
  browser di progetto (comandi, ambienti, argomenti, matematica, commenti).
- **Anteprima PDF integrata** (👁 Apri PDF): se è disponibile QtPdf il PDF si apre in una
  finestra interna con zoom; altrimenti ripiega sull'app di sistema.

## Documentazione

- **[docs/MANUALE.md](docs/MANUALE.md)** — manuale d'uso completo (installazione,
  configurazione, flusso di lavoro, tutte le funzioni).
- **[docs/ARCHITETTURA.md](docs/ARCHITETTURA.md)** — architettura tecnica (strati,
  modello dati, pipeline, motore AI, decisioni di progetto, estensibilità).
- **[CLAUDE.md](CLAUDE.md)** + **`.claude/`** — contesto sintetico per gli agenti AI
  (regole, codemap, convenzioni) per sessioni di sviluppo più efficienti.

## Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

I test coprono la logica core (analisi, struttura, bibliografia, progressi, versioning,
export, diagrammi, LaTeX, modello), il motore offline e la sistemazione `.docx`.

---

## Le modalità di avvio

All'avvio compare un dialog con:
- **Crea un nuovo libro** — scegli titolo, autore, argomento e cartella del progetto.
- **Modifica un libro esistente** — apri la cartella di un progetto (contiene `book.json`).
- **Apri una cartella di file LaTeX** — apri una cartella *qualsiasi* che contiene un
  libro/saggio in LaTeX (file `.tex`, immagini, capitoli inclusi con `\input`…). Si
  apre un **browser dei file**: a sinistra l'albero della cartella, a destra l'editor.
  Scegli quale file aprire, inserisci i tuoi punti/sezioni e salva. Da qui puoi anche
  compilare il PDF, aprire in TeXstudio e usare «Sistema Word». **Non serve** un
  progetto BookForge con `book.json`.
- **Strumenti → Sistema documento Word** — formatta/impagina/corregge un `.docx`
  **senza aprire alcun progetto**.

Un *progetto* è semplicemente una cartella con `book.json` (lo stato del libro) e
`book.tex` (l'output generato).

### Browser dei file LaTeX
Anche dentro un progetto, il pulsante **📂 File progetto** apre lo stesso browser
sulla cartella del progetto: utile per vedere ed editare a mano `book.tex`, i file
inclusi, le immagini e gli ausiliari della compilazione.

---

## Sistemazione di documenti Word (.docx)

Il pulsante **📝 Sistema Word** (dalla finestra principale, dal browser file o
direttamente dall'avvio) apre un dialog che lavora *direttamente* sul `.docx` con
`python-docx` — modifiche chirurgiche e *lossless*. Oltre a titoli, corpo, margini e
pulizia, sistema:

- **Indice / sommario** — le voci dell'indice (stili `TOC N` / `Indice N` / `Sommario`)
  **non** vengono toccate dalla formattazione del corpo, e viene impostato
  `updateFields` così Word **aggiorna l'indice** (voci e numeri di pagina) all'apertura
  del documento.
- **Didascalie** — riconosce le didascalie dallo stile (`Didascalia`/`Caption`) o dal
  testo (`Figura N…`, `Tabella N…`), le stila (corpo più piccolo, corsivo, centrate) e
  le **sposta sotto l'immagine** a cui si riferiscono se erano sopra.
- **Modifiche applicate correttamente** — oltre ai singoli paragrafi viene aggiornato
  anche lo stile base (`Normale/Normal`), così la formattazione del corpo «tiene» anche
  dove i paragrafi non hanno formattazione diretta.

---

## Architettura multi-agente

Un orchestratore coordina quattro sotto-agenti `datapizza.agents.Agent`
(collegati anche tramite `can_call`). La pipeline su ogni capitolo:

| # | Agente | Compito |
|---|--------|---------|
| 1 | **WriterAgent** | trasforma i concetti grezzi in prosa, usando un *system prompt* che codifica tono, pubblico, lingua, persona e istruzioni extra |
| 2 | **CoherenceAgent** | verifica e raccorda il testo con i capitoli adiacenti — riceve solo i **riassunti** dei vicini, non i testi interi → **risparmio di token** |
| 3 | **FormatterAgent** | converte la prosa nel **corpo LaTeX** del capitolo (sezioni, enfasi, elenchi, escape dei caratteri speciali) |
| 4 | **SummaryAgent** | produce un **riassunto breve** del capitolo, salvato per i passaggi futuri |

I riassunti sono persistiti in `book.json`: i passaggi successivi non rileggono i
capitoli interi, contenendo drasticamente il consumo di token.

## Collegamento con TeXstudio / PDF

Il modulo `core/compiler.py`:
- **Esporta .tex** — assembla l'intero documento con `core/latex_builder.py`.
- **Compila PDF** — usa `latexmk` (o `pdflatex` in due passate) per generare il PDF.
- **Apri in TeXstudio** — cerca l'eseguibile `texstudio` nel PATH e nei percorsi
  tipici di Windows/macOS/Linux e apre il `.tex`. Da lì compili con il tasto di
  TeXstudio per la massima compatibilità con la tua installazione.

Il preambolo LaTeX carica i pacchetti non essenziali (`lmodern`, `microtype`,
`emptypage`) solo se presenti, così il documento compila anche su installazioni minime.

## Struttura del documento generato

```
Copertina (titlepage)
Prefazione           ← da campo "Prefazione" o "Abstract"
Indice (tableofcontents)
Capitolo 1, 2, …     ← \chapter{titolo} + corpo LaTeX
Quarta di copertina  ← da campo "Quarta cop."
```

## Struttura del codice

```
main.py                      entry point
bookforge/
  core/
    model.py                 Book / Chapter / BookStyle / Project (+ persistenza JSON)
    latex_builder.py         assemblaggio .tex + escape LaTeX
    compiler.py              .tex, compilazione PDF, apertura TeXstudio/PDF (Project + path)
    docx_formatter.py        formattazione .docx: titoli, corpo, immagini, didascalie, indice
    diagram.py               snippet LaTeX per diagrammi/immagini + render Mermaid/Graphviz
    image_gen.py             generazione immagini raster (Google Imagen, pluggable)
    analysis.py              metriche di leggibilità, note di stile, segnalazione claim
    structure.py             mappa dell'argomentazione (tesi/argomenti/prove/obiezioni)
    biblio.py                gestione bibliografia BibTeX (references.bib)
    progress.py              istantanee delle metriche nel tempo (progress.json)
    versioning.py            versioni dell'opera (.bookforge_versions) + diff
    export.py                export Markdown ed EPUB (pandoc o writer interno)
  agents/
    engine.py                agenti datapizza-ai + comandi AI (edit/diagram/caption/mentore) + fallback
    commands.py              registro dei comandi di scrittura assistita (menu ↔ engine)
  gui/
    startup.py               dialog Crea/Modifica/Apri cartella LaTeX/Strumenti Word
    main_window.py           editor capitoli, stile, motore, toolbar (AI + Capitolo + Mentore)
    latex_browser.py         browser file + editor per cartelle LaTeX qualsiasi
    docx_dialog.py           dialog «Sistema Word»
    ai_menu.py               controller del menu 🤖 AI (comandi, diagrammi, immagini)
    ai_preview.py            anteprima Accetta/Rifiuta/Rigenera delle proposte AI
    ai_worker.py             QThread generico per le chiamate AI
    mentor_dialog.py         Modalità Mentore: revisione, domande, claim
    metrics_dialog.py        Dashboard di crescita (metriche + istantanee)
    argument_dialog.py       editor della mappa dell'argomentazione
    biblio_dialog.py         gestione bibliografia + inserimento \cite
    versions_dialog.py       versioni dell'opera: salva/diff colorato/ripristina
    latex_highlighter.py     evidenziazione sintassi LaTeX (QSyntaxHighlighter)
    pdf_view.py              anteprima PDF integrata (QtPdf) con fallback esterno
    worker.py                QThread per la generazione non bloccante
    autogen_worker.py        QThread per l'autogenerazione (autopilota)
    docx_worker.py           QThread per la formattazione .docx
    theme.py                 tema dark (QSS)
tests/                       suite pytest della logica core + motore offline
```
