# M2-00C — commenti per pagina e client del dossier v2

La preparazione è un'operazione esplicita: misura il dossier canonico con Typst,
fissa il piano e fornisce un commento neutrale per ogni pagina fisica, comprese
copertina e continuazioni degli Allegati. Le note automatiche sono una proiezione
del backend; non richiedono né simulano una risposta AI.

## Persistenza e API

`report_editorial_states` conserva il piano e la revisione della sessione.
`report_editorial_notes` conserva le note utente/AI per pratica, identificativo
e hash del piano. Le note di un piano superato restano nell'archivio; il loro
testo può essere copiato e riassociato esplicitamente a una pagina corrente.
Queste operazioni non modificano bilanci, ipotesi o i sei blocchi narrativi M1.
L'eliminazione della pratica elimina anche lo storico editoriale.

Sotto `/final-report/editorial`:

- `GET`: dossier v2, revisione, note archiviate e avvisi. Nessuna generazione AI,
  misurazione Typst o scrittura durante la lettura.
- `POST /prepare`: verifica fonte e revisione, misura e prepara il piano.
- `PUT /notes`: salva testi manuali con hash della fonte, hash del piano,
  revisione della sessione e revisione di ciascuna nota.
- `POST /generate`: genera soltanto le note selezionate, da contenuti canonici
  di questa pratica; non sovrascrive note utente.

I conflitti restituiscono 409. Testi che superano lo spazio disponibile sono
rifiutati, senza troncamento. L'assenza del renderer restituisce un errore
esplicito. Il provider AI è facoltativo: errori e risultati parziali sono
segnalati per nota, mantenendo i commenti già disponibili.

Il piano è invalidato da cambiamenti nelle fonti economiche, nei testi principali
che possono provocare reflow, nel compilatore, nei font e negli asset di layout.
Le note precedenti rimangono recuperabili. Il controllo delle revisioni viene
ripetuto dopo misurazione/generazione, prima della scrittura atomica.

## Verifica nativa dello spazio

`NoteFitProbe` esegue un'unica query Typst per il gruppo di testi, con lo stesso
sandbox, compilatore e font del dossier. Misura stringhe letterali nello spazio
di 178 × 18 mm, font 9 pt, massimo quattro righe. Verifica identificativi e
metadati restituiti, limiti di input/asset/output e rimozione delle directory
temporanee. Non produce un piano alternativo o un conteggio sintetico di pagine.

## Database esistenti

La migrazione dedicata è ripetibile e aggiunge soltanto le due tabelle, l'indice e i trigger di eliminazione dello storico:

```sh
python tools/migrate_report_editorial.py /percorso/financial_analysis.db
```

Richiede un database già esistente con `budget_scenarios`; non crea un database
contabile vuoto per un percorso errato. Anche `migrate_db.py` include queste DDL,
e il Dockerfile copia il relativo modulo per la migrazione all'avvio.

## Limiti del modulo

Il client web visualizza il dossier v2; la stampa browser resta un'anteprima.
Il template editoriale definitivo e il servizio di export PDF seguono nei moduli
successivi. Questo modulo utilizza il catalogo canonico v2 corrente; non introduce
formule o indicatori aggiuntivi nei renderer.

## Validazione

Test HTTP con piano realmente misurato: preparazione senza provider, copertura
completa, salvataggio/revisione, overflow rifiutato e conservazione manuale alla
nuova preparazione. Test di generazione con provider simulato: risultati parziali,
identificativi estranei, nota manuale salvata mentre il provider risponde,
modifica contabile concorrente e archivio/riassociazione. Nessuna chiamata al
provider esterno durante i test.

Regressioni di contratto/API v1-v2 e narrazione M1, controlli Typst di runtime,
font, grafici e piano completo. Test frontend su boundary/API, grafici, indicatori,
Allegati, selezione AI e transizioni delle bozze; controllo TypeScript.

Il PDF locale `inbox/artifacts/2026-09-15-report-finale/m2-00c-commenti-typst.pdf`
è una BOZZA sintetica di verifica: include periodi infrannuali osservati e
rettificati di 9 mesi, chiusura stimata e tre anni di budget. Ogni pagina contiene
il proprio commento. Non è il template finale M2-02 né un export ufficiale.
Il packaging Typst/Bubblewrap nel container rimane M2-06; il Dockerfile in questo
modulo include soltanto il supporto alla migrazione editoriale.
