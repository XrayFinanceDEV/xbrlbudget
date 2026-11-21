"""Il suggerimento che accompagna un import PDF rifiutato: che cosa caricare al suo posto.

Il motivo del rifiuto lo scrive chi solleva `PDFImportError`, in decine di punti; qui, in un punto solo, lo si
riconosce dal testo e gli si affianca una categoria e un'indicazione per l'utente, cosi' che si accorga del
problema e carichi il file giusto. Un messaggio che non si riconosce non ha suggerimento: si mostra com'e'.
"""
from __future__ import annotations

import re

_RICARICA_BILANCIO = ("Carica il bilancio o la situazione contabile esportata dal gestionale, con stato "
                      "patrimoniale e conto economico.")

# (categoria, espressione sul messaggio, suggerimento), nell'ordine: vince la prima che si riconosce.
_RIFIUTI: tuple[tuple[str, re.Pattern, str], ...] = (
    ("xbrl", re.compile(r"istanza XBRL nativa", re.I),
     "Scegli il tipo di import «XBRL» e carica lo stesso file."),
    ("solo_conto_economico", re.compile(r"solo Conto Economico", re.I),
     "Il file contiene solo il conto economico. Carica un documento che abbia anche lo stato patrimoniale "
     "(attivo e passivo): il bilancio completo o la situazione contabile."),
    ("contabilita_semplificata", re.compile(r"contabilit[aà] semplificata", re.I),
     "Serve lo stato patrimoniale completo (cassa, crediti, debiti, patrimonio netto). Carica una situazione "
     "patrimoniale completa o il bilancio."),
    ("riepilogo", re.compile(r"riepilogo aggregato", re.I),
     "Il file riassume il bilancio in poche macro-voci. Carica il prospetto completo di stato patrimoniale e "
     "conto economico, o la situazione contabile esportata dal gestionale."),
    ("scansione", re.compile(r"scansione contabile|PDF e' un'immagine|PDF è un'immagine", re.I),
     "Il file e' una scansione che non si legge in modo affidabile. Carica il PDF esportato direttamente dal "
     "gestionale (con il testo selezionabile), non una scansione o una foto."),
    ("movimenti_senza_saldo", re.compile(r"movimenti dare/avere senza la colonna del saldo finale", re.I),
     "Il file elenca saldo iniziale e movimenti dare/avere, ma non il saldo finale di ogni conto (nella stampa la "
     "colonna del saldo e' finita su pagine separate, o manca). Ristampa dal gestionale la situazione contabile o "
     "il bilancio di verifica con il saldo finale accanto a ogni conto."),
    ("lettura_incompleta", re.compile(r"Lettura del passivo mancante", re.I),
     "E' un errore di lettura, non del file: riprova l'import."),
    ("lettura_non_riuscita", re.compile(r"Lettura non riuscita", re.I),
     "Riprova l'import. Se si ripete, carica il PDF esportato direttamente dal gestionale (bilancio o situazione "
     "contabile con stato patrimoniale e conto economico), non una scansione o un prospetto rielaborato."),
    ("non_bilancio", re.compile(r"Stato Patrimoniale risulta vuoto|nessun dato contabile|nessuno scheletro di "
                                r"legge|non riconosciuto|non importabile come bilancio completo", re.I),
     "Nel file non c'e' un prospetto di bilancio leggibile: controlla che sia il bilancio o la situazione "
     "contabile, e non per esempio una relazione, un'analisi di bilancio o la sola nota integrativa. "
     + _RICARICA_BILANCIO),
)


def suggerimento_rifiuto(messaggio: str) -> dict | None:
    """{"categoria", "suggerimento"} per il messaggio di un rifiuto, o None se non si riconosce."""
    for categoria, espressione, suggerimento in _RIFIUTI:
        if espressione.search(messaggio or ""):
            return {"categoria": categoria, "suggerimento": suggerimento}
    return None
