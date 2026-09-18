// Gruppo ALLEGATI (v4 pagine 19-33): indice, A/B/C (prospetti completi),
// D/E/F/G, metodologia. L'indice e A/B/C sono implementati in questa fase
// (`dossier_catalog/allegati.py`) e si rendono con il dispatch generico di
// `comuni.typ`: le tabelle A/B/C usano `table-block`/`data-table` come ogni
// altra tabella (una pagina per parte, righe accorpate lato Python — vedi
// `APPENDIX_ROWS_PER_PART` in `allegati.py`), l'indice usa `index-block`
// (link-list con risoluzione live della pagina via `query`).
//
// D (registro rettifiche), E (matrice ipotesi), F/G (indicatori) e
// metodologia restano da fare: nessun componente nuovo previsto per D/F/G
// (tabelle semplici, stesso `table-block`); E porta le voci annidate delle
// ipotesi (finanziamenti, pregresso, differenze temporanee) che il vecchio
// inventario generico spacchettava riga per riga — quel codice non esiste
// più in questo ramo (rimosso con `editorial_inventory.py`), chi implementa
// Allegato E lo riscrive da zero sul modello v2 attuale, non lo recupera da
// git blame come fosse ancora valido.
