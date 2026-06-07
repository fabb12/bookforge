# Manuale d'uso di BookForge

BookForge ti accompagna nella scrittura di un saggio: dai concetti grezzi alla prosa,
all'impaginazione LaTeX/PDF, fino a EPUB e Word. L'AI è un **mentore e un assistente**,
non un sostituto: tu mantieni il controllo e la voce del testo.

---

## 1. Installazione

Requisiti: **Python 3.10+**.

```bash
pip install -r requirements.txt
python main.py
```

Strumenti **opzionali** (l'app funziona anche senza, con funzioni ridotte):
- **LaTeX** (`latexmk` + una distribuzione TeX) — per compilare il PDF.
- **TeXstudio** — per modificare il `.tex` in un editor esterno.
- **pandoc** — per un EPUB di qualità migliore.
- **mermaid-cli** (`npm i -g @mermaid-js/mermaid-cli`) e **Graphviz** (`dot`) — per
  trasformare i diagrammi in immagini.

## 2. Configurazione dell'AI

BookForge legge la configurazione da variabili d'ambiente:

| Variabile | Significato | Default |
|-----------|-------------|---------|
| `BOOKFORGE_API_KEY` | Chiave del provider (o `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`) | — |
| `BOOKFORGE_PROVIDER` | `anthropic` / `openai` / `google` | `anthropic` |
| `BOOKFORGE_MODEL` | Modello da usare | `claude-opus-4-8` |

```bash
export BOOKFORGE_API_KEY="la-tua-chiave"
python main.py
```

> **Senza chiave** BookForge parte in **modalità offline**: tutte le funzioni restano
> disponibili ma i testi AI sono simulati in modo deterministico. Utile per provare
> l'interfaccia o lavorare sull'impaginazione.

## 3. Avvio: la schermata iniziale

All'apertura puoi:
- **Creare** un nuovo progetto (scegli una cartella vuota).
- **Aprire** un progetto esistente (una cartella con `book.json`).
- **Aprire una cartella LaTeX** qualsiasi (editor di file `.tex`, senza modello libro).
- Accedere agli **strumenti Word**.

Un progetto è una semplice cartella: dentro troverai `book.json`, e man mano
`book.tex`, `references.bib`, `progress.json`, la cartella `.bookforge_versions/` e gli
export.

## 4. La finestra principale

A sinistra l'elenco dei **capitoli** (aggiungi, rinomina, riordina, elimina). Al centro
le **schede** del capitolo selezionato:

1. **Concetti** — i tuoi appunti/idee grezze, punto di partenza per la generazione.
2. **Testo** — la prosa del capitolo (generata o scritta da te).
3. **LaTeX** — il corpo LaTeX impaginato (con evidenziazione della sintassi).
4. **Riassunto** — un sunto breve, usato dall'AI per la coerenza tra capitoli.

Nel pannello **Stile** imposti tono, pubblico, lingua, persona, la classe del
documento e — importante — il **prompt di stile** e la **modalità di lavoro**.

### Il prompt di stile
Il campo *prompt di stile* ti permette di descrivere con parole tue la voce del libro
(es. «tono ironico, frasi brevi, esempi concreti dalla vita quotidiana»). Quando è
valorizzato, guida la generazione mantenendo lo **stile coerente** in tutti i capitoli.

## 5. Modalità di lavoro — la scelta è tua

Nel pannello Stile scegli **come** vuoi lavorare:

- **🎓 mentore** *(default)* — l'AI ti dà feedback e strumenti, ma **scrivi tu**.
- **⚖️ bilanciata** — generi con un clic, sempre con anteprima e conferma.
- **🚀 autopilota** — autogenerazione rapida con il minimo sforzo, mantenendo lo stile
  del tuo prompt.

Puoi cambiare modalità quando vuoi: lo strumento serve sia chi vuole crescere come
autore sia chi vuole produrre velocemente.

## 6. Generare i contenuti

### Capitolo singolo
Scrivi i concetti nella scheda **Concetti** e premi **🧩 Genera capitolo**. BookForge
esegue la pipeline: prosa → coerenza con i capitoli vicini → LaTeX → riassunto.

### Autopilota (menu 🚀 Autogenera)
- **Autogenera capitolo corrente**
- **Autogenera capitoli vuoti** — riempie solo quelli ancora senza testo.
- **Rigenera tutti i capitoli** — rifà tutto (con backup automatico di una versione).

Se un capitolo non ha concetti, l'autopilota ne ricava prima una **scaletta dal titolo**:
ti basta scrivere i titoli dei capitoli.

### Scrittura assistita (menu 🤖 con il tasto destro nell'editor)
Seleziona del testo e scegli un'azione: **Riscrivi, Espandi, Accorcia, Continua, Più
formale, Più divulgativo, Correggi**, oltre a diagrammi e immagini. Ogni proposta passa
da un'**anteprima**: puoi **Accettare, Rifiutare o Rigenerare**.

## 7. Il Mentore (menu 🎓) — crescere come autore

Quattro strumenti pensati per l'apprendimento, non per riscrivere al posto tuo:

- **🔎 Revisione** — note di stile **con il perché** (frasi lunghe, passivo,
  ripetizioni, riempitivi, leggibilità Gulpease), **domande socratiche** per sviluppare
  il pensiero, e **claim da verificare/citare**. Funziona offline; «Approfondisci con
  AI» aggiunge note più ricche.
- **📈 Dashboard di crescita** — metriche per capitolo (Gulpease, lunghezza media frasi,
  passivo, varietà lessicale…). Salva **istantanee** e confrontale nel tempo (delta).
- **🧭 Mappa dell'argomentazione** — struttura **tesi → argomenti → prove → obiezioni →
  repliche** prima di scrivere. Generala con l'AI, modificala, ed **esportala nei
  Concetti** del capitolo.
- **📚 Bibliografia** — gestisci `references.bib` (BibTeX) e inserisci `\cite{...}` nel
  LaTeX con un clic.

## 8. Versioni e confronto (menu 🕓 Versioni)

- **Salva versione** — crea un'istantanea etichettata dell'opera.
- **Diff visuale colorato** — selezionando una versione vedi le differenze rispetto allo
  stato attuale: **verde = aggiunto, rosso = rimosso**, per capitolo, con riepilogo
  (righe aggiunte/rimosse, sezioni cambiate).
- **Ripristina** — torna a una versione precedente (lo stato attuale viene prima salvato
  automaticamente come backup, così non perdi nulla).

Le versioni sono file nella cartella `.bookforge_versions/`.

## 9. Diagrammi e immagini

Dal menu 🤖 puoi generare:
- **Diagrammi** in **TikZ** (compilati direttamente in LaTeX, nessuno strumento esterno),
  **Mermaid** o **Graphviz** (resi come immagine se hai `mmdc`/`dot`).
- **Immagini** raster da descrizione testuale (richiede un provider di immagini
  configurato).
- **Didascalie** per figure.

## 10. Impaginazione e PDF

- **📄 Esporta .tex** — genera `book.tex` completo (preambolo, copertina, capitoli).
- **🛠 Compila PDF** — compila con LaTeX (serve la distribuzione TeX).
- **📖 Apri in TeXstudio** — per rifiniture manuali.
- **👁 Apri PDF** — **anteprima integrata** con zoom (se QtPdf è disponibile),
  altrimenti apre il PDF con l'app di sistema.

## 11. Export Markdown ed EPUB (menu 📤 Esporta)

- **Markdown (.md)** — sempre disponibile.
- **EPUB (.epub)** — con `pandoc` se installato, altrimenti con il generatore interno.

I file vengono salvati nella cartella del progetto.

## 12. Sistemare un documento Word (.docx)

Lo strumento **📝 Sistema Word** uniforma un `.docx`: normalizza i titoli, formatta le
didascalie e le sposta **sotto** le immagini, centra le immagini, ripulisce gli spazi e
prepara l'aggiornamento dell'indice. Scegli il file di ingresso e quello di uscita.

## 13. Editor di cartelle LaTeX

Se apri una cartella LaTeX (anziché un progetto), hai un editor con browser dei file,
evidenziazione della sintassi sui file `.tex`, scrittura assistita dall'AI, e i comandi
per compilare/aprire il PDF.

## 14. Risoluzione dei problemi

- **«Modalità offline»** — manca la API key: imposta `BOOKFORGE_API_KEY` e riavvia.
- **La compilazione PDF fallisce** — verifica di avere `latexmk` e una distribuzione TeX
  installati e nel PATH.
- **L'anteprima PDF apre l'app esterna** — il tuo PyQt6 non include QtPdf; è normale, il
  PDF si apre comunque.
- **I diagrammi Mermaid/Graphviz non diventano immagini** — installa `mmdc` o `dot`; in
  alternativa usa TikZ, che non richiede strumenti esterni.
- **EPUB poco curato** — installa `pandoc` per una resa migliore.
- **Ho perso delle modifiche** — controlla le **Versioni**: prima delle operazioni
  importanti BookForge salva un backup automatico.

---

Buona scrittura. Ricorda: l'AI è qui per farti crescere e andare più veloce, ma il
libro resta **tuo**.
