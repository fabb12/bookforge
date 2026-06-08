@echo off
REM ===========================================================================
REM  BookForge - Installazione dipendenze (Windows)
REM
REM  Installa TUTTO il necessario per far girare "python main.py":
REM    - Dipendenze Python (pip)            -> requirements.txt
REM    - pandoc      (EPUB / Word -> LaTeX) -> winget
REM    - MiKTeX      (compilazione PDF)      -> winget
REM    - Graphviz    (diagrammi DOT)         -> winget
REM    - Node.js + Mermaid CLI (diagrammi)   -> winget + npm
REM
REM  Richiede Windows 10/11 (winget incluso) e una connessione a Internet.
REM  Esegui questo file con un DOPPIO CLIC oppure da un prompt dei comandi.
REM  Suggerito: tasto destro -> "Esegui come amministratore" per installare
REM  i programmi di sistema senza intoppi.
REM ===========================================================================

setlocal enableextensions
cd /d "%~dp0"

echo.
echo ======================================================================
echo   BookForge - Installazione dipendenze
echo ======================================================================
echo.

REM --------------------------------------------------------------- Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRORE] Python non trovato nel PATH.
    echo          Installa Python 3.10-3.12 da https://www.python.org/downloads/
    echo          ricordandoti di spuntare "Add python.exe to PATH", poi rilancia.
    goto :fine_errore
)
echo [OK] Python trovato:
python --version

echo.
echo --- Aggiornamento di pip e installazione delle dipendenze Python ---
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRORE] Installazione delle dipendenze Python fallita.
    goto :fine_errore
)
echo [OK] Dipendenze Python installate.

REM ---------------------------------------------------------------- winget ---
where winget >nul 2>nul
if errorlevel 1 (
    echo.
    echo [ATTENZIONE] winget non e' disponibile: salto pandoc/MiKTeX/Graphviz/Node.
    echo              Installali manualmente:
    echo                pandoc   -^> https://pandoc.org/installing.html
    echo                MiKTeX   -^> https://miktex.org/download
    echo                Graphviz -^> https://graphviz.org/download/
    echo                Node.js  -^> https://nodejs.org/  ^(poi: npm i -g @mermaid-js/mermaid-cli^)
    goto :riepilogo
)

echo.
echo --- Strumenti di sistema (winget) ---

REM pandoc
where pandoc >nul 2>nul
if errorlevel 1 (
    echo Installo pandoc...
    winget install -e --id JohnMacFarlane.Pandoc --accept-source-agreements --accept-package-agreements
) else (
    echo [OK] pandoc gia' presente.
)

REM MiKTeX (LaTeX -> compilazione PDF)
where pdflatex >nul 2>nul
if errorlevel 1 (
    echo Installo MiKTeX ^(distribuzione LaTeX^)...
    winget install -e --id ChristianSchenk.MiKTeX --accept-source-agreements --accept-package-agreements
) else (
    echo [OK] LaTeX ^(pdflatex^) gia' presente.
)

REM Graphviz (dot)
where dot >nul 2>nul
if errorlevel 1 (
    echo Installo Graphviz...
    winget install -e --id Graphviz.Graphviz --accept-source-agreements --accept-package-agreements
) else (
    echo [OK] Graphviz ^(dot^) gia' presente.
)

REM Node.js (serve per Mermaid CLI)
where npm >nul 2>nul
if errorlevel 1 (
    echo Installo Node.js LTS...
    winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
) else (
    echo [OK] Node.js/npm gia' presente.
)

REM Mermaid CLI (mmdc) - richiede npm nel PATH della sessione corrente.
where mmdc >nul 2>nul
if errorlevel 1 (
    where npm >nul 2>nul
    if errorlevel 1 (
        echo [ATTENZIONE] npm non e' ancora nel PATH di questa sessione.
        echo              Chiudi e riapri il terminale, poi esegui:
        echo                  npm install -g @mermaid-js/mermaid-cli
    ) else (
        echo Installo Mermaid CLI ^(mmdc^)...
        call npm install -g @mermaid-js/mermaid-cli
    )
) else (
    echo [OK] Mermaid CLI ^(mmdc^) gia' presente.
)

:riepilogo
echo.
echo ======================================================================
echo   Installazione completata.
echo.
echo   IMPORTANTE: gli strumenti appena installati con winget potrebbero
echo   non essere ancora visibili in QUESTO terminale. Chiudi e riapri il
echo   prompt dei comandi prima di avviare l'app, poi:
echo.
echo       python main.py
echo ======================================================================
echo.
pause
goto :eof

:fine_errore
echo.
echo Installazione interrotta. Correggi l'errore sopra e riprova.
echo.
pause
endlocal
