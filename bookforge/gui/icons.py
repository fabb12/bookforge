"""Set di icone minimali (stile linea) per l'interfaccia di BookForge.

Filosofia: icone vettoriali essenziali — tratto sottile, angoli arrotondati,
colore d'accento del tema — disegnate inline come SVG. Niente file esterni né
rete: tutto è incorporato qui, coerente con la regola «funziona offline».

Uso tipico::

    from .icons import icon, app_icon
    button.setIcon(icon("save"))
    window.setWindowIcon(app_icon())

Robustezza: se il modulo SVG di Qt non è disponibile (o il rendering fallisce),
`icon()` restituisce una `QIcon` vuota. I pulsanti/menu mantengono comunque la
loro etichetta testuale, quindi l'app resta pienamente usabile.
"""
from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter

try:  # il modulo SVG fa parte di PyQt6, ma restiamo difensivi
    from PyQt6.QtSvg import QSvgRenderer
    _HAS_SVG = True
except Exception:  # noqa: BLE001 - senza SVG ripieghiamo su icone vuote
    _HAS_SVG = False

# Colore d'accento del tema scuro (vedi theme.py): le icone lo ereditano.
ACCENT = "#7aa2f7"

# Corpo SVG di ogni icona (viewBox 0 0 24 24). Stile uniforme: solo tratto,
# estremi e giunzioni arrotondati. Ispirate alle icone lineari essenziali.
_ICONS: dict[str, str] = {
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
            '<polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    "sparkles": '<path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3'
                'L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/>'
                '<path d="M5 3v3"/><path d="M3.5 4.5h3"/><path d="M18 17v3"/><path d="M16.5 18.5h3"/>',
    "wand": '<path d="m21.6 3.6-1.2-1.2a1.2 1.2 0 0 0-1.7 0L2.4 18.7a1.2 1.2 0 0 0 0 1.7'
            'l1.2 1.2a1.2 1.2 0 0 0 1.7 0L21.6 5.3a1.2 1.2 0 0 0 0-1.7Z"/>'
            '<path d="m14 7 3 3"/><path d="M5 6v3"/><path d="M3.5 7.5h3"/>',
    "list": '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>'
            '<line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/>'
            '<line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
            '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "arrow-left": '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    "arrow-right": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
    "note": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
            '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
            '<line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
            '<polyline points="14 2 14 8 20 8"/>',
    "cap": '<path d="M22 10 12 5 2 10l10 5 10-5z"/>'
           '<path d="M6 12v5c0 1 2 3 6 3s6-2 6-3v-5"/>',
    "search": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "chart": '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/>'
             '<line x1="6" y1="20" x2="6" y2="16"/>',
    "compass": '<circle cx="12" cy="12" r="10"/>'
               '<polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
            '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "book-open": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
                 '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "rocket": '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 '
              '2.18 0 0 0-2.91-.09z"/><path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 '
              '22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>'
              '<path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/>'
              '<path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
    "refresh": '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>'
               '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1'
              '-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 '
              '3.76z"/>',
    "eye": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
              '<polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "minus": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "chevron-up": '<polyline points="18 15 12 9 6 15"/>',
    "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
    "trash": '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6'
             'm3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/>'
             '<line x1="14" y1="11" x2="14" y2="17"/>',
    "folder": '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 '
              '2 2z"/>',
    "folder-open": '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 '
                   '0 1-1.94 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 '
                   '2 0 0 0 1.66.9H18a2 2 0 0 1 2 2v2"/>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06'
                'a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21'
                'a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 '
                '0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 '
                '0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83'
                '-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09'
                'a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83'
                'l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09'
                'a1.65 1.65 0 0 0-1.51 1z"/>',
    "key": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/>'
           '<path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
           '<line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/>'
           '<line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>'
           '<line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/>'
           '<line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
             '<circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
    "info": '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/>'
            '<line x1="12" y1="8" x2="12.01" y2="8"/>',
    "edit": '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>'
            '<path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
    "play": '<polygon points="5 3 19 12 5 21 5 3"/>',
    "chat": '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9'
            'L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5'
            'a8.48 8.48 0 0 1 8 8v.5z"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "camera": '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 '
              '1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    "undo": '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
    "paperclip": '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 '
                 '5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
}

# Alias semantici verso glifi esistenti (stesso disegno, nome diverso).
_ICONS["file-text"] = _ICONS["note"]

# Icona dell'applicazione/finestra: libro aperto su sfondo arrotondato d'accento.
_APP_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="3" y="3" width="58" height="58" rx="15" fill="{ACCENT}"/>
  <g fill="none" stroke="#11131a" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
    <path d="M32 19c-3-2.4-7-3.4-11-3.4-2.2 0-4.3.3-6 .9v26c1.7-.6 3.8-.9 6-.9 4 0 8 1 11 3.4"/>
    <path d="M32 19c3-2.4 7-3.4 11-3.4 2.2 0 4.3.3 6 .9v26c-1.7-.6-3.8-.9-6-.9-4 0-8 1-11 3.4z"/>
    <path d="M32 19v26"/>
  </g>
</svg>"""


def _wrap(body: str, color: str) -> str:
    """Avvolge il corpo dell'icona in un SVG completo con lo stile a tratto."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def _render(svg: str, size: int) -> QPixmap | None:
    """Renderizza una stringa SVG in un QPixmap quadrato; None se non possibile."""
    if not _HAS_SVG:
        return None
    try:
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        return pm
    except Exception:  # noqa: BLE001 - in caso di problemi: nessuna icona
        return None


@lru_cache(maxsize=None)
def icon(name: str, color: str = ACCENT) -> QIcon:
    """Restituisce la `QIcon` minimale per `name` (vuota se sconosciuta/non resa)."""
    body = _ICONS.get(name)
    if body is None:
        return QIcon()
    svg = _wrap(body, color)
    ic = QIcon()
    for s in (16, 20, 24, 32, 48):
        pm = _render(svg, s)
        if pm is not None:
            ic.addPixmap(pm)
    return ic


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """Icona dell'applicazione e delle finestre (libro stilizzato)."""
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = _render(_APP_SVG, s)
        if pm is not None:
            ic.addPixmap(pm)
    return ic
