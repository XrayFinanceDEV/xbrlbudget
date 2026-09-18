// Gruppo DATI (v4 pagine 3-6, solo workflow infrannuale): bilancio
// infrannuale e fonti, rettifiche apportate, dall'infrannuale alla chiusura,
// indicatori dell'infrannuale. `dossier_catalog/dati.py` compone ogni pagina
// con solo `kind: "table"`/`"chart"`/`"note"` — blocchi generici che
// `pagine/comuni.typ` già dispatcha — quindi questo file non serve a nessun
// componente di resa: nessun import da qui in `editorial.typ`.
//
// Il confronto «prima → dopo» (pag. 4), «rettificato → stimato → chiusura»
// (pag. 5) e «rettificato → chiusura» degli indicatori (pag. 6), che nella
// v4 sono un grafico a barre raggruppate/dumbbell, sono qui grafici a barre
// raggruppate standard (`kind: "chart"`, id registrato in
// `chart-layout.json`'s `bars`): un vero dumbbell con due punti connessi per
// categoria non esiste ancora nell'infrastruttura condivisa
// (`pagine/comuni.typ`/`charts.typ`), e costruirlo avrebbe richiesto
// toccare quei file di dispatch comuni a tutti i gruppi — anche
// `pagine/indicatori.typ`, che ha lo stesso bisogno alle pagine 12-17. Chi
// costruisce quel componente condiviso può sostituire qui i tre grafici a
// barre con il vero dumbbell, senza toccare `dossier_catalog/dati.py`.
