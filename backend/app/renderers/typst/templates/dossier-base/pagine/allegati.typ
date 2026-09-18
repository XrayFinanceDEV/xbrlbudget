// Gruppo ALLEGATI (v4 pagine 19-33): indice, A/B/C (prospetti completi),
// D/E/F/G, metodologia — tutti implementati (`dossier_catalog/allegati.py`)
// e resi con il dispatch generico di `comuni.typ`, nessun componente nuovo:
// - indice: `index-block` (link-list con risoluzione live della pagina via
//   `query`) — elenca anche D/E/F/G, non solo A/B/C.
// - A/B/C: `table-block`/`data-table` come ogni altra tabella (una pagina
//   per parte, righe accorpate lato Python — `APPENDIX_ROWS_PER_PART`).
// - D (registro rettifiche), E (matrice ipotesi), F/G (indicatori della
//   pratica/indici analitici): stesso `table-block`, tabelle semplici senza
//   voci annidate — E si ferma alle ipotesi scalari dichiarate
//   (`assumption_sections`), mai ai campi con tabella nidificata
//   (finanziamenti, pregresso, differenze temporanee): quelli restano fuori,
//   dichiarato in `allegati.py`, non spacchettati riga per riga come faceva
//   il vecchio `editorial_inventory.py` (rimosso, non recuperabile da git
//   blame come fosse ancora valido).
// - metodologia: `text-block`/`table-block`/`note-block`, testo editoriale
//   statico più una tabella di sole fonti-progetto (nessun dato di report).
//
// Le tabelle F/G portano l'unità nella cella del valore (`7,57×`, `17,75%`)
// invece che nell'intestazione: non serve un componente nuovo, perché quella
// stringa arriva già formattata da `shared.format_unit` come un token
// (`unit: none` in `row()`) — `cell()` la rende verbatim, esattamente come
// farebbe con un'etichetta qualsiasi.
