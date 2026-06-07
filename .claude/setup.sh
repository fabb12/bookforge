#!/usr/bin/env bash
# Setup per le sessioni Claude Code on the web: prepara l'ambiente per i test.
# Resiliente: un fallimento di rete non deve interrompere la sessione.
echo "BookForge · preparo l'ambiente di test…"
python -m pip install --quiet --disable-pip-version-check pytest python-docx \
  >/dev/null 2>&1 && echo "  pytest e python-docx pronti." \
  || echo "  Avviso: pip non riuscito (rete?). I test core potrebbero non girare."
exit 0
