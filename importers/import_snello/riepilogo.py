"""Riepilogo a macro-voci che non e' un bilancio (Task 27, decisione del proprietario, 2026-10-03):
«riepiloghi che sembrano esportati da xlsx che non sono bilanci non li importiamo».

Una o due pagine di righe «etichetta: importo» con le sole macro-voci (Immobilizzazioni, Attivo
circolante, Patrimonio netto...) non contengono le sotto-voci che il modello richiede (sp02..sp09
per CCN e current ratio, ce05..ce12 per l'EBITDA): qualunque destinazione sarebbe un plug sulle
macro. Si riconosce dal testo, in modo deterministico, PRIMA della struttura (vision): niente
numerazione di legge a sotto-livelli, niente righe-conto, niente scadenze, niente voci di
dettaglio dell'attivo circolante o delle immobilizzazioni, pochi importi. Misurato sul corpus:
budget_133, 137 e 150, nient'altro (vedi il rapporto del Task 27)."""
from __future__ import annotations

import re

MESSAGGIO = (
    "Il documento è un riepilogo di sintesi (poche macro-voci di Stato Patrimoniale e Conto "
    "Economico), non un bilancio importabile: mancano le voci di dettaglio. Carica il bilancio "
    "completo (schema di legge o bilancio di verifica)."
)

_MAX_PAGINE = 2
_MIN_IMPORTI, _MAX_IMPORTI = 8, 30

_IMPORTO = re.compile(r"-?\d[\d.,]*[.,]\d{2}\b")
_ROMANO = re.compile(r"(?im)^\s*(?:[A-D][.)]\s*)?(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[-).]")
_NUMERATA = re.compile(r"(?m)^\s*\d{1,2}(?:\s*bis)?\)")
_CODICE = re.compile(r"(?m)^\s*\d{4,}\b")
_SCADENZA = re.compile(r"esigibili\s+(?:entro|oltre)", re.I)
# Le sotto-voci che un riepilogo a sole macro non ha: se il documento le nomina, e' un bilancio
# (anche se sintetico) e prende la strada di sempre.
_DETTAGLIO = re.compile(
    r"rimanenz|crediti|disponibilit[aà]\s+liquide|immobilizzazioni\s+(?:immateriali|materiali|finanziarie)"
    r"|debiti\s+verso|fornitori|banche|ammortament|\bservizi\b|\bpersonale\b|materie", re.I)


def riconosci_riepilogo_testo(testo: str, n_pagine: int) -> bool:
    if not testo or n_pagine > _MAX_PAGINE:
        return False
    t = testo.lower()
    if "stato patrimoniale" not in t or "conto economico" not in t:
        return False
    if not (_MIN_IMPORTI <= len(_IMPORTO.findall(testo)) <= _MAX_IMPORTI):
        return False
    if _ROMANO.search(testo) or _NUMERATA.search(testo) or _CODICE.search(testo) or _SCADENZA.search(testo):
        return False
    return not _DETTAGLIO.search(testo)


def riconosci_riepilogo(file_path: str) -> bool:
    """True se il PDF e' un riepilogo a macro-voci. Solo testo nativo (nessuna scansione, nessun
    modello); un errore di lettura e' «non lo so»: False."""
    try:
        import fitz
        with fitz.open(file_path) as doc:
            n = len(doc)
            if n > _MAX_PAGINE:
                return False
            testo = "\n".join(p.get_text() for p in doc)
    except Exception:
        return False
    return riconosci_riepilogo_testo(testo, n)
