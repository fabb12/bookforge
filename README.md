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
L'app cerca la API key da variabili d'ambiente o dal pannello **Motore** nell'interfaccia:

```bash
export BOOKFORGE_PROVIDER=openai      # openai | anthropic | google
export BOOKFORGE_MODEL=gpt-4o-mini
export BOOKFORGE_API_KEY=sk-...
```

Senza API key l'app parte in **modalità offline**: genera testo simulato, utile per
provare interfaccia e flusso di compilazione senza costi.

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
    compiler.py              .tex, compilazione PDF, apertura TeXstudio/PDF
  agents/
    engine.py                4 agenti datapizza-ai + orchestrazione + fallback offline
  gui/
    startup.py               dialog Crea/Modifica
    main_window.py           editor capitoli, stile, motore, toolbar
    worker.py                QThread per la generazione non bloccante
    theme.py                 tema dark (QSS)
```
