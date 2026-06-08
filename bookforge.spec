# -*- mode: python ; coding: utf-8 -*-
"""Spec di PyInstaller per creare l'eseguibile standalone di BookForge.

Uso::

    pip install -r requirements-dev.txt
    pyinstaller bookforge.spec            # crea dist/BookForge[.exe]

Note:
- Molte dipendenze sono importate "pigramente" dentro le funzioni (QtPdf,
  python-docx, i client datapizza, google-genai): PyInstaller non le vede con
  l'analisi statica, quindi le dichiariamo a mano in `hiddenimports`.
- `python-docx` porta con sé un template `default.docx` che va incluso fra i
  `datas`, altrimenti la formattazione Word fallisce nell'eseguibile.
- Gli strumenti di sistema (pandoc, LaTeX, mmdc, dot) NON vengono impacchettati:
  restano dipendenze esterne, rilevate a runtime con shutil.which().
- L'eseguibile è "onefile" e senza console (app GUI). Per un avvio più rapido e
  un bundle più snello si può passare a "onedir" (vedi in fondo).
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# --- Raccolta difensiva di moduli/dati delle dipendenze opzionali -----------
datas = []
hiddenimports = [
    # Moduli PyQt6 importati pigramente nel codice.
    "PyQt6.QtPdf",
    "PyQt6.QtPdfWidgets",
    "PyQt6.QtSvg",
]

# python-docx: include il template default.docx e i sottomoduli.
try:
    datas += collect_data_files("docx")
    hiddenimports += collect_submodules("docx")
except Exception:
    pass

# datapizza-ai: i client del provider sono importati a runtime.
try:
    hiddenimports += collect_submodules("datapizza")
except Exception:
    pass
for _client in (
    "datapizza.clients.anthropic",
    "datapizza.clients.openai",
    "datapizza.clients.google",
    "datapizza.agents",
):
    if _client not in hiddenimports:
        hiddenimports.append(_client)

# google-genai: opzionale (generazione immagini).
try:
    hiddenimports += collect_submodules("google.genai")
except Exception:
    pass


block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy"],  # non usati: alleggeriscono il bundle
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BookForge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # app GUI: nessuna finestra di console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="icona.ico",       # opzionale: aggiungi un'icona se disponibile
)

# --- Variante "onedir" (avvio più rapido, cartella invece di un solo file) ---
# Per produrre una cartella dist/BookForge/ commenta l'EXE "onefile" qui sopra
# (rimuovendo a.binaries/a.zipfiles/a.datas dall'EXE) e abilita il COLLECT:
#
# exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BookForge",
#           console=False)
# coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True,
#                name="BookForge")
