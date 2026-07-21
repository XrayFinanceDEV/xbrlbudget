# Piano consuntivo di adeguamento — Strumento Budget

Data chiusura tecnica: 20 luglio 2026  
Fonte requisiti: `Problematiche_Strumento_Budget (2).xlsx`  
Repository: `C:\DEV\xbrlbudget-main\xbrlbudget`

## Esito

Le 14 problematiche censite sono state implementate nel codice. Il perimetro comprende motori budget e infrannuale, API, persistenza, interfaccia, report e controlli automatici. Non è stata eseguita una distribuzione su un ambiente esterno: la migrazione è stata provata in modo idempotente su una copia locale e il collaudo funzionale reale resta un'attività di rilascio.

| N. | Requisito | Stato finale | Evidenza sintetica |
|---:|---|---|---|
| 1 | Crediti/debiti tributari | Completato | Mastrino saldo iniziale + imposta corrente − acconti; riclassifica automatica credito/debito e nessun valore negativo. |
| 2 | Infrannuale → budget lossless | Completato | Tutti gli override CE/SP persistono; promozione transazionale con confronto campo per campo prima del commit. |
| 3 | Modifica SP previsionale | Completato | Editor a valori assoluti; ricalcolo di aggregati e cassa; ripristino eliminando l'override. |
| 4 | TFR | Completato | Accantonamento coerente CE/SP, fallback su costo personale e opzione sospensione fondo interno. |
| 5 | Crediti oltre 12 mesi | Completato | Tutte le sottocategorie conservate nel forecast e nel report. |
| 6 | Catalogo SP unico | Completato | Pagina previsionale, report e maschera storica usano il catalogo IV-CEE condiviso. |
| 7 | Rendiconto nel report | Completato | Sezione OIC indiretta e riconciliazione cassa già presenti e mantenute nei test/build. |
| 8 | Imposte anticipate/differite | Completato | Mastrino per differenze temporanee deducibili/imponibili, scadenza breve/lunga e aliquota specifica/opzionale. |
| 9 | Bilancio abbreviato | Completato | Maschera di dettaglio SP storico con vincolo somma dettagli = aggregato e stato `forecastable`. |
| 10 | Debiti bancari totali | Completato | Rimborso su banche entro+oltre 12 mesi, quota breve prima, obbligazioni escluse. |
| 11 | Più finanziamenti | Completato | Contratti multipli con residuo iniziale, nuova erogazione, durata, tasso, preammortamento e balloon. |
| 12 | Override SP assoluti | Completato | Priorità override assoluto > driver > riporto; dettagli ricostruiscono il padre e la cassa. |
| 13 | Grafici infrannuali | Completato | Materie/ricavi, servizi/ricavi, EBITDA e margini finanziari/patrimoniali. |
| 14 | Nomenclature | Completato | Terminologia 3/5 anni e infrannuale/consuntivo uniformata; mapping `sp17d/e/f/g` corretto. |

## Logica implementata

### 1. Fiscalità corrente

Per ogni esercizio viene determinata la posizione netta:

`saldo netto finale = debito iniziale − credito iniziale + imposta corrente − acconti`

- se il risultato è positivo alimenta `sp16e_debiti_tributari_breve`;
- se è negativo viene riclassificato in `sp06e_crediti_tributari_breve`;
- credito e debito automatici sono mutuamente esclusivi e mai negativi;
- una crescita SP fiscale esplicita resta un override manuale;
- il regolamento usa solo l'imposta corrente, non l'effetto differito incluso in CE20.

### 2. Imposte anticipate e differite

Ogni riga del mastrino contiene descrizione, natura, scadenza, saldo imponibile iniziale, incrementi, riversamenti e aliquota. La formula è:

`differenza temporanea finale = max(0, apertura + incrementi − riversamenti)`

`imposta differita/anticipata finale = differenza temporanea finale × aliquota`

- differenza deducibile breve → `sp06f`;
- differenza deducibile lunga → `sp07f`;
- differenza imponibile → `sp14b`;
- variazione DTL positiva genera costo differito;
- variazione DTA positiva genera beneficio differito;
- `CE20 = imposta corrente + costo/beneficio differito`, salvo override assoluto.

### 3. Finanziamenti

I contratti sono normalizzati in un unico kernel usato dai due motori. Per ciascuna linea:

- capitale = nuova erogazione + eventuale residuo iniziale;
- durante il preammortamento si pagano solo interessi;
- capitale ordinario = `(capitale − balloon) / (durata − preammortamento)`;
- il balloon è rimborsato con l'ultima rata;
- interessi = residuo di apertura dell'anno × tasso;
- rimborso bancario applicato prima a `sp16a`, poi a `sp17a`;
- obbligazioni e altri finanziatori restano su piani separati;
- se sono indicati residui iniziali analitici, la loro somma deve coincidere con il debito bancario della fonte e il piano generico viene disattivato, evitando doppi rimborsi e doppi interessi.

### 4. Override e quadratura SP

Gli override sono memorizzati per anno e campo in `sp_overrides`. La precedenza è:

1. valore assoluto manuale;
2. calcolo da driver;
3. riporto dall'esercizio precedente.

Quando cambia una sottovoce, il relativo aggregato IV-CEE viene ricostruito. Se la cassa non è stata modificata esplicitamente, `sp09` rimane il plug di quadratura. Un fabbisogno di cassa negativo non genera debito bancario implicito: il motore restituisce un errore/diagnostica e richiede una fonte esplicita.

### 5. Bilanci abbreviati

La nuova maschera storica carica l'anno base tramite l'API Rettifiche, mostra otto gruppi gerarchici e conserva gli aggregati. Il salvataggio è consentito quando ogni dettaglio riconcilia il padre entro 0,01 euro. È disponibile un'allocazione assistita del residuo alla voce residuale esplicita, modificabile prima del salvataggio. Il backend ricalcola validità semantica e `forecastable`.

### 6. Promozione infrannuale

La promozione opera in un'unica transazione:

1. validazione semantica del forecast sorgente;
2. sostituzione dell'eventuale anno pieno precedente;
3. copia di tutti i campi comuni CE e SP;
4. flush e rilettura dal database;
5. confronto esatto campo per campo;
6. nuova validazione semantica del record copiato;
7. commit solo se tutti i controlli passano; altrimenti rollback completo.

### 7. Catalogo e report

Il catalogo `frontend/lib/ivcee-balance-catalog.ts` è la fonte unica per ordine, codici, totali e sottovoci SP. È consumato dalla pagina Proiezioni patrimoniali e dalle appendici del report; include rimanenze, crediti brevi/lunghi, fondi, riserve e debiti per natura/scadenza.

## Principali file interessati

- `calculations/projection_common.py`: kernel fiscalità, debito bancario, TFR e finanziamenti.
- `calculations/forecast_engine.py`: CE/SP pluriennale, override, DTA/DTL e piani finanziari.
- `calculations/intra_year_engine.py`: annualizzazione 3/6/9/12M con le stesse regole condivise.
- `backend/app/services/promote_service.py`: promozione transazionale verificata.
- `backend/app/schemas/budget.py`, `database/models.py`, `migrate_db.py`: nuovi input e persistenza.
- `frontend/app/budget/page.tsx`: mastrini fiscali e contratti finanziari.
- `frontend/components/budget/HistoricalBalanceDetailEditor.tsx`: dettaglio storico abbreviato.
- `frontend/app/forecast/balance/page.tsx`: override SP assoluti.
- `frontend/lib/ivcee-balance-catalog.ts`: catalogo unico.
- `frontend/components/report/report-appendices.tsx`: report allineato al catalogo.
- `frontend/app/infrannuale/page.tsx`: KPI e grafici richiesti.

## Verifiche eseguite

| Controllo | Esito |
|---|---|
| Suite Python completa | 186 superati, 3 saltati |
| E2E generazione → validazione → promozione | superato per 3, 6, 9 e 12 mesi |
| TypeScript | nessun errore (`tsc --noEmit`) |
| Build Next.js produzione | completata |
| Migrazione su copia database | eseguita due volte, idempotente; nuova colonna presente |
| Test temporanei | copia rimossa dopo la verifica |

La build segnala solo avvisi non bloccanti già presenti: una dipendenza mancante in un hook, tre usi di `<img>` e database Browserslist non aggiornato.

## Piano di rilascio

1. Salvare un backup verificato del database dell'ambiente di destinazione.
2. Applicare `python migrate_db.py <percorso-database>` una sola volta; il comando è idempotente.
3. Distribuire backend e frontend dalla stessa revisione.
4. Eseguire smoke test su login, import, Rettifiche, budget e report.
5. Ripetere i quattro casi 3/6/9/12M con dati reali dell'utente.
6. Verificare con il referente contabile almeno un caso con credito tributario, uno con DTA/DTL e uno con debito bancario misto.
7. Confrontare report web/PDF e registrare l'accettazione UAT.

## Criterio di chiusura

Il lavoro applicativo è chiuso perché codice, schema, UI, report, migrazione e test automatici sono completi. La messa in esercizio non è inclusa in questa esecuzione e dovrà seguire il piano di rilascio sopra, senza applicare modifiche direttamente al database di produzione senza backup.
