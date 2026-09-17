"""Mappa condivisa dei controlli con cui il template rifiuta un contenuto che non entra.

La usano sia le rotte editoriali (`api/v1/editorial_notes.py`) sia l'endpoint PDF
del dossier (`api/v1/reports.py`): le due superfici devono dire la stessa cosa in
italiano, e un duplicato divergerebbe alla prima costante aggiunta nel template.
Sono solo costanti del nostro template: nessun dato del documento entra qui.
"""

#: Codice del panic → «che cosa non entra», in italiano. Mappa volutamente chiusa:
#: un panic sconosciuto non è un contenuto rifiutato, è un guasto del renderer.
NON_ENTRA = {
    "editorial-amount-does-not-fit": "un importo è più largo della sua colonna",
    "editorial-cell-token-does-not-fit": "il testo di una cella è più largo della sua colonna",
    "editorial-prose-token-does-not-fit": "una parola del testo è più larga della pagina",
    "editorial-note-does-not-fit": "un commento di pagina supera lo spazio che ha a disposizione",
}
