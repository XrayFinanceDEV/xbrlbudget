# 10 — Piano delle correzioni alla pipeline IV CEE e infrannuale

Data piano: 2026-07-15  
Stato: **approvato ed eseguito il 2026-07-15; esiti e limiti nel documento 12**.

## 1. Obiettivo e regole non negoziabili

Obiettivo: ottenere una pipeline in cui la quadratura sia una conseguenza dei fatti
estratti e classificati, non il risultato di un plug.

Regole guida:

1. una validazione non modifica mai il bilancio;
2. una riga senza fonte non può diventare utile, cassa, debito, riserva, ricavo o
   costo;
3. il risultato CE è calcolato da una sola funzione canonica;
4. lordo e fondo si nettano solo nella stessa classe patrimoniale;
5. aggregato e dettagli sono validati insieme;
6. ogni valore stimato conserva fonte, regola, confidenza e importo;
7. un import dubbio può essere salvato come `review_required`, ma non usato nel
   forecast finché non viene approvato;
8. la copertura del corpus locale precede qualunque nuova chiamata API.

## 2. Architettura obiettivo

```text
RawFact[]
  ├─ testo/glifi/coordinate/pagina/riga
  ├─ importo originale e normalizzato
  └─ fonte + confidenza
          ↓
ClassifiedFact[]                  (nessun plug)
          ↓
NettingResult                    (lordo ↔ fondo specifico)
          ↓
IvCeeStatement                   (gerarchia canonica)
          ↓
ValidationReport                 (immutabile, multi-invariante)
          ↓
Accepted | ReviewRequired | Rejected
          ↓
Persistenza + provenienza
          ↓
Forecast gate → motore infrannuale per classe e periodo esatto
```

Il modello può essere introdotto progressivamente: prima funzioni pure e report,
poi sostituzione delle mutazioni, infine persistenza della provenienza.

## 3. Sequenza di implementazione proposta

### Fase 0 — Congelare le prove e rendere affidabile la suite

Modifiche:

- creare il manifest deduplicato descritto nel documento 11;
- correggere la raccolta di `tests/test_hierarchical_import.py` senza alterare le
  aspettative contabili;
- aggiungere il 337 al ground truth bloccante;
- separare test «classifica la route», «estrae i fatti», «costruisce IV CEE»,
  «persiste» e «proietta»;
- archiviare l'output baseline corrente per misurare ogni variazione.

Gate di uscita:

- suite completa raccoglibile;
- ogni file Test identificato da hash e stato;
- nessuna API invocata dai test di regressione;
- baseline riproducibile con un solo comando.

File probabili: `tests/`, `Test/_analysis/`, nuovo manifest JSON e runner locale.

### Fase 1 — Algebra contabile unica e validazione immutabile

Modifiche:

- introdurre una funzione pura canonica per risultato ante imposte e utile netto,
  comprensiva di `ce03a`, `ce11b`, `ce17a/b` e segni definiti una volta;
- farla usare da modelli ORM, importatori, quadratura, infrannuale e cash flow;
- sostituire il significato di `quadra` con un `ValidationReport` composto;
- vietare a `check_quadratura` di mutare input;
- rilevare negativi non ammessi, totali, dettagli e CE↔SP prima di qualsiasi
  riconciliazione.

Test obbligatori:

- `ce03a=100` produce risultato +100 senza toccare `ce04`;
- `ce11b=100` riduce il risultato di 100 in tutti gli strati;
- `ce17 = ce17a - ce17b` con segni coerenti;
- input immutato dopo ogni validazione;
- stessa formula su dict, ORM e forecast.

Gate: nessuna delle formule duplicate rimane attiva nei flussi di produzione.

File probabili: nuovo modulo di dominio in `calculations/` o `importers/`,
`database/models.py`, `importers/iv_cee_hierarchy.py`,
`importers/pdf_extractor_llm.py`, `calculations/intra_year_engine.py`.

### Fase 2 — Eliminare le compensazioni economiche automatiche

Modifiche:

- trasformare `enforce_ce_sp_identity` da mutatore in diagnostica/selettore di
  candidato;
- eliminare plug automatici in `sp13`, `sp09`, `sp16`, riserve, `ce04` e `ce12`;
- mantenere l'eventuale scarto come `unexplained_difference` fuori dai dati
  contabili;
- se esistono più candidati, scegliere quello che soddisfa più fatti e invarianti,
  senza correggerlo;
- introdurre soglie di stato: accettato, da revisionare, rifiutato.

Compatibilità:

- durante la transizione si può calcolare il vecchio risultato in shadow mode e
  confrontarlo, ma non persisterlo;
- i record storici non vanno migrati automaticamente: occorre prima rieseguirli e
  produrre un report delle differenze.

Test metamorfici:

- rimuovere una riga dalla fonte deve aumentare lo scarto, non cambiare una voce
  sensibile;
- cambiare ordine alle righe non cambia la classificazione;
- applicare il netting due volte non cambia il risultato;
- nessun valore senza provenance può comparire in un campo IV CEE.

### Fase 3 — Route C, contrapposte e testo corrotto

Modifiche:

- introdurre un ricostruttore di righe basato su coordinate con tolleranza verticale
  calibrata sul corpus;
- ricomporre token monetari separati (`3.239`, `,`, `12`) prima del parsing;
- normalizzare soltanto confusioni di glifi supportate dal contesto numerico,
  conservando originale e normalizzato;
- associare Dare/Avere, codice e descrizione usando colonne e geometria, non solo
  regex sulla stringa lineare;
- estrarre subtotali e totali come fatti di controllo, non come valori che comandano
  una voce;
- classificare lordo e fondo per classe; quote CE escluse dal netting;
- impedire clamp silenziosi e riduzioni residuali dei debiti;
- calcolare coverage per righe e per massa monetaria.

Strategia scansioni:

- stessa interfaccia `RawFact`, indipendentemente da testo PDF o OCR;
- OCR/vision produce candidati con coordinate e confidenza, non direttamente IV
  CEE;
- un secondo estrattore non vince «perché quadra»: vince soltanto se migliora
  copertura e invarianti rispetto alla fonte;
- nessuna chiamata esterna automatica durante i test. Le cache esistenti possono
  essere riusate come fixture.

Gate specifico 337:

```text
sp02 = 3.239,12
sp03 = 5.184,73
sp13 = +4.287,23
totale netto = 253.076,09
fondo immateriali = 0
nessun plug economico
```

Gate corpus: nessuna regressione sui 27 route C; riduzione esplicita dei casi
`review_required`, senza convertirli artificialmente in «OK».

File probabili: `importers/situazione_contabile_parser.py`, modulo nuovo per righe e
importi, `importers/pdf_importer.py`, fixture/test route C.

### Fase 4 — Classificazione IV CEE e netting comune a tutte le route

Modifiche:

- centralizzare la tassonomia e le regole side-aware;
- sostituire i default semantici con `unclassified`;
- separare conti patrimoniali, fondi, quote CE e conti d'ordine;
- costruire il netto da fatti tipizzati, mai dal residuo di quadratura;
- introdurre una costruzione aggregato/dettagli comune a PDF, XBRL e CSV;
- gap positivo solo in un bucket dichiarato «altro/non classificato» se la fonte lo
  supporta; overshoot = conflitto, non scala proporzionale.

Attenzione: un helper denominato `reconcile_typed_to_aggregates` è accettabile solo
se costruisce la gerarchia da fatti documentati. Non deve modificare valori per far
tornare una somma.

Test: fondi per classe, segni, scadenze, side-aware bank/cash, unknown, idempotenza,
ordine delle righe e aggregati completi.

### Fase 5 — XBRL e CSV nativi

XBRL:

- indicizzare i facts per entità, instant/duration, date, unità, dimensioni e
  scenario;
- selezionare esplicitamente il periodo richiesto;
- richiedere coerenza tra instant SP e duration CE;
- non fare overwrite per solo anno/tag;
- applicare la stessa gerarchia e gli stessi invarianti delle route PDF.

CSV:

- rilevare encoding in modo controllato;
- riconoscere schema TEBE/BILAQ dall'intestazione;
- mappare per nome colonna, non posizione fissa;
- rifiutare schema ambiguo con errore leggibile.

Gate: fixture XBRL con annuale e 9 mesi nello stesso anno; import del CSV reale del
corpus; nessun mismatch aggregato/dettaglio nascosto.

### Fase 6 — Mapping e persistenza lossless

Modifiche:

- sostituire i costruttori PDF manuali incompleti con un registro di campi validato
  rispetto alle colonne ORM;
- aggiungere un test round-trip `statement → ORM → DB → statement`;
- persistere `ValidationReport`, provenienza, regole applicate, importi stimati,
  coverage, versione parser e hash sorgente;
- distinguere stato upload da stato contabile: `success` tecnico non implica
  `forecastable`;
- evitare confidenza fissa `0.95` e conservare quella effettiva per sezione/campo.

Gate: nessun campo supportato perso nel round-trip; impossibile marcare forecastable
un record con conflitti materiali.

File probabili: `importers/pdf_importer.py`, `database/models.py`, migration,
serializer/API e test di integrazione DB.

### Fase 7 — Rifacimento della logica infrannuale

Modifiche:

- query esatta per `(company, year, period_months)` e mesi 1–11;
- nessun fallback da annuale a parziale;
- il fattore deriva dal record verificato;
- il CE parte dal consuntivo YTD e proietta soltanto i mesi residui;
- lo SP parte integralmente dal saldo parziale effettivo;
- roll-forward immobilizzazioni per classe con investimenti, dismissioni e quota
  residua coerente (`ce09a→sp02`, `ce09b→sp03`, `ce09d→crediti`; `sp04` esclusa);
- capitale, riserve, TFR, crediti e debiti cambiano solo con driver/movimenti
  espliciti;
- nessuna assunzione automatica di destinazione utile a riserve;
- nessuna ripartizione debiti 40/60;
- fabbisogno finanziario esposto e coperto soltanto da una scelta di scenario;
- tutti gli override accettati dall'API devono essere usati oppure rifiutati.

Test:

- scenario 6 mesi con solo record 9 mesi o annuale: rifiuto;
- `sp02=3.000`, `ce09a=0`, `ce09b>0`: `sp02` invariata;
- `sp04` invariata senza movimento esplicito;
- movimenti YTD patrimoniali preservati;
- utile CE proiettato = `sp13` senza plug;
- fabbisogno non coperto resta diagnostico.

File probabili: `database/queries.py`, schemi e API budget,
`calculations/intra_year_engine.py`, `calculations/forecast_engine.py`, servizio di
promozione.

### Fase 8 — Gate downstream, cash flow e storico

Modifiche:

- vietare promote e forecast se `forecastable=false`;
- estendere rettifiche server-side a CE↔SP, gerarchie e provenance;
- nel cash flow mostrare differenza non spiegata invece di assorbirla nel debito;
- separare CAPEX materiale/immateriale/finanziario e svalutazioni crediti;
- riesaminare i record storici con il nuovo validator, senza riscriverli in massa.

Gate: nessun servizio downstream può rendere invisibile un errore upstream.

## 4. Ordine dei commit e controllo del rischio

Ordine consigliato, un commit verificabile per blocco:

1. harness/manifest senza variazioni produttive;
2. formula canonica e test;
3. validator immutabile in shadow mode;
4. rimozione plug CE/SP;
5. ricostruttore route C;
6. tassonomia/netting comune;
7. XBRL/CSV;
8. mapping/persistenza e migration;
9. infrannuale;
10. gate downstream e audit storico.

Ogni commit deve produrre: suite, report corpus, diff per file e conteggio degli
stati. Non va usata la diminuzione dei `MASK` come unico KPI: un file rifiutato
onestamente è migliore di un file falso ma quadrato.

## 5. Criteri finali di accettazione

- 337 corretto sui valori bloccanti senza regole legate al nome file;
- 100% dei contenuti unici presenti nel manifest;
- nessun import accettato con plug economico non documentato;
- risultato identico fra fonte, formula canonica, DB e `sp13`;
- aggregati e dettagli coerenti oppure conflitto esplicito;
- nessun negativo fuori whitelist;
- nessuna perdita di campo nel round-trip;
- periodo infrannuale esatto e nessun fallback annuale;
- immobilizzazioni proiettate per classe;
- XBRL multi-contesto deterministico;
- CSV del corpus gestito o dichiarato esplicitamente non supportato;
- forecast/promote consentiti solo a dati semanticamente validi.

## 6. Punto di approvazione

Approvazione ricevuta con il comando «vai» del 2026-07-15. L'implementazione ha
seguito i gate del piano senza invocare API esterne. I casi senza evidenza locale
sufficiente sono rimasti `review_required`, `rejected` o `not_reexecuted_no_api`.
