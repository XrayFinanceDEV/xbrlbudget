# Valutazione problematiche e piano di adeguamento — Strumento Budget

Data valutazione: 20 luglio 2026  
Fonte: `Problematiche_Strumento_Budget (2).xlsx`  
Perimetro tecnico: repository `xbrlbudget`

## Esito finale esecuzione — 20 luglio 2026

Le 14 richieste sono state implementate e verificate nel repository. Il consuntivo
tecnico completo, con formule, flussi, file modificati, test e piano di rilascio, è
disponibile in `PIANO_CONSUNTIVO_IMPLEMENTAZIONE.md` nella stessa cartella.

Il piano applicativo è stato implementato nel repository. In particolare:

- posizione fiscale riconciliata da saldo iniziale, imposte di competenza e acconti, con riclassifica automatica credito/debito e valori mai negativi;
- salvataggio infrannuale completo degli override CE e conservazione esatta dello SP nel percorso consuntivo 12M;
- override patrimoniali assoluti con editor delle voci di dettaglio, ricalcolo degli aggregati e della cassa;
- rimborso calcolato sui debiti bancari totali entro/oltre 12 mesi, con priorità alla quota breve ed esclusione delle obbligazioni;
- più finanziamenti nello stesso anno, ciascuno con importo, durata e tasso autonomi;
- dettaglio dei crediti oltre 12 mesi preservato nel forecast e allineato nel report;
- dashboard infrannuale con grafici di EBITDA/materie/servizi sui ricavi e di margine di tesoreria, margine di struttura e PFN;
- nomenclature 3/5 anni e infrannuale/consuntivo uniformate; mapping `sp17d/e/f/g` corretto.

Verifiche eseguite: **186 test Python passati, 3 esclusi**, E2E 3/6/9/12M superati, type-check TypeScript senza errori, build Next.js di produzione completata e migrazione verificata in modo idempotente su copia del database.

Restano attività di rilascio/collaudo, non modifiche funzionali al codice: backup e applicazione di `migrate_db.py` all'ambiente di destinazione, distribuzione e UAT su casi reali 3/6/9/12M.

## Sintesi esecutiva iniziale (prima dell'implementazione)

La tabella seguente conserva la fotografia usata per costruire il piano; non
rappresenta lo stato finale, che è riportato nel consuntivo collegato sopra.

| Stato | N. richieste |
|---|---:|
| Implementato, da collaudare | 2 |
| Parzialmente implementato | 9 |
| Non implementato / non conforme | 3 |
| Totale | 14 |

La priorità va data alla correttezza contabile e alla conservazione delle modifiche manuali. Le quattro aree più urgenti sono:

1. logica fiscale completa per crediti/debiti tributari;
2. passaggio infrannuale → budget senza perdita o ricalcolo inatteso dei valori manuali;
3. gestione dei debiti bancari totali e dei piani di finanziamento;
4. livello unico di override patrimoniale in valore assoluto, con quadratura automatica.

Stima complessiva, al netto delle sovrapposizioni tra richieste: **30–45 giornate/uomo**, più collaudo utente su casi reali.

## Valutazione puntuale iniziale

| N. | Stato | Priorità | Stima | Valutazione e intervento proposto |
|---:|---|---|---:|---|
| 1 | Parziale | P0 | 6–9 gg | I crediti tributari e le imposte anticipate non scalano più con i ricavi e sono modificabili tramite percentuale. Manca però il mastrino fiscale richiesto: saldo iniziale, acconti/pagamenti, imposte di competenza, compensazioni e saldo finale. Introdurre input annuali espliciti, calcolo lordo/netto, vincolo `debito >= 0`, riclassifica automatica dell'eccedenza a credito e override assoluti. Validare con il commercialista se credito e debito possano coesistere o debbano essere compensati. |
| 2 | Parziale, rischio perdita dati | P0 | 3–5 gg | La promozione copia il forecast infrannuale nel nuovo anno storico, ma il percorso 12M ricostruisce solo parte degli override e usa un'aliquota fiscale fissa del 27,9%. Rendere il passaggio transazionale e lossless: serializzare tutti gli override CE/SP, usare `ce20_override` per le imposte manuali, rileggere il record promosso e confrontarlo campo per campo prima di aprire il budget. Aggiungere test E2E per 3/6/9/12 mesi. |
| 3 | Non implementato | P1 | incluso nel n. 12 | La pagina Stato Patrimoniale previsionale è di sola lettura. Non esiste un endpoint analogo agli override CE. Realizzare un editor patrimoniale per crediti tributari, altri crediti e TFR, appoggiato al livello di override assoluto descritto al punto 12, con ricalcolo di aggregati, cassa/quadratura e tracciamento del valore manuale. |
| 4 | Implementato, da collaudare | P1 | 1–2 gg | Il motore budget calcola `sp15 = fondo precedente + accantonamento TFR`; il motore infrannuale aggiunge la quota residua dell'anno. Aggiungere test di regressione dedicati per: dettaglio salari presente/assente, sospensione versamento a fondo/INPS, crescita pluriennale e quadratura CE–SP. |
| 5 | Parziale | P1 | 1–2 gg | Il report finale espone il dettaglio IV-CEE di debiti e crediti, ma non replica tutte le sottocategorie dei crediti a lungo termine presenti nella proiezione (mancano controllate, collegate e controllanti). Allineare le righe a una definizione condivisa e aggiungere una verifica di completezza automatica. |
| 6 | Parziale | P1 | incluso nel n. 5 | Il report non è più limitato alle sole macro-voci, ma la struttura è duplicata rispetto alla pagina SP e può divergere. Estrarre un catalogo unico delle righe patrimoniali consumato da proiezione e report; criterio di accettazione: stesso insieme di codici, stesso ordine e stessi totali. |
| 7 | Implementato, da collaudare | P1 | 1–2 gg | Il report finale include il rendiconto finanziario OIC a metodo indiretto con sezioni A/B/C e grafico. Verificare presenza nel layout di stampa/PDF, riconciliazione cassa iniziale/finale e coerenza con la pagina Rendiconto su almeno tre casi reali. |
| 8 | Parziale | P1 | 2–3 gg per soluzione manuale; >8 gg per motore automatico | Le imposte anticipate non sono più collegate ai ricavi e restano costanti salvo variazione manuale percentuale. Manca una logica fiscale basata su differenze temporanee. Scelta raccomandata per la prima release: valore assoluto manuale, spiegazione in UI e nessun automatismo. Un calcolo automatico richiede nuove basi imponibili e regole fiscali non oggi disponibili. |
| 9 | Parziale | P1 | 3–5 gg incrementali | Nel flusso Rettifiche sono modificabili le sottovoci di crediti/debiti, ma non esiste un editor dedicato e persistente per segregare un bilancio abbreviato usato come base budget. Creare una maschera “Dettaglio SP storico” con righe entro/oltre, clienti/fornitori/tributari/banche, vincoli somma dettagli = aggregato e blocco del previsionale finché il dettaglio debiti è incoerente. |
| 10 | Non conforme | P0 | 3–5 gg | L'assunzione “rimborso debiti bancari” oggi ammortizza solo debiti finanziari a lungo termine (banche + obbligazioni), non i debiti verso banche totali entro+oltre. Correggere la base di calcolo secondo il requisito, separare banche da obbligazioni e modellare la riclassifica quota entro 12 mesi prima del rimborso. Testare debito solo breve, solo lungo, misto e bilancio abbreviato. |
| 11 | Parziale | P1 | 7–10 gg | È disponibile un solo nuovo finanziamento per anno; gli interessi del nuovo finanziamento alimentano correttamente `ce15` sul residuo. Mancano più mutui simultanei, capitale residuo iniziale e piano per singolo contratto. Introdurre entità `FinancingLoan` con descrizione, residuo, anno inizio, durata/anni di rimborso, tasso, eventuale preammortamento e scadenze; aggregare capitale in SP e interessi in CE, con tabella di riconciliazione. |
| 12 | Non implementato | P1 | 5–8 gg | Le assunzioni patrimoniali sono percentuali; la proiezione SP è read-only. Aggiungere un livello di override assoluto per anno e voce, distinto dai driver percentuali, con priorità `override assoluto > driver > riporto`, evidenza grafica del valore manuale, azione di ripristino e ricalcolo di aggregati/quadratura. Il punto 3 va realizzato su questa stessa infrastruttura. |
| 13 | Parziale | P2 | 3–5 gg | L'infrannuale calcola e mostra EBITDA margin, PFN, Margine di Tesoreria e Margine di Struttura in tabella, ma non contiene i due grafici richiesti né evidenzia i rapporti materie/ricavi e servizi/ricavi. Aggiungere: (1) trend Storico–Infrannuale–Proiezione per ricavi/EBITDA; (2) PFN e margini patrimoniali; più 5 KPI card con soglie e tooltip. Riutilizzare le stesse funzioni di calcolo, senza duplicarle nel componente grafico. |
| 14 | Parziale | P2 | 0,5–1 gg | Il budget supporta fino a 5 anni e alcune descrizioni citano già 3–5 anni, ma l'header globale è ancora “Simulatore di Scenari Economici Finanziari” e la pagina standard parla di 3 anni. Uniformare le stringhe approvate in AppHeader, pagina budget, stampa e navigazione; verificare se il selettore debba consentire solo 3/5 anni oppure 1–5. |

## Rilievo aggiuntivo P0

Nel file `frontend/components/budget/assumption-rows.ts` le etichette delle righe a lungo termine sono sfalsate rispetto ai campi:

- `sp17d_growth_pct` è debiti verso fornitori oltre 12 mesi, non debiti tributari;
- `sp17e_growth_pct` è debiti tributari oltre 12 mesi, non debiti previdenziali;
- `sp17f_growth_pct` è debiti previdenziali oltre 12 mesi, non altri debiti.

Correggere immediatamente le etichette e aggiungere un test di mapping UI → campo API, perché l'errore può salvare un valore nella categoria sbagliata.

## Roadmap originaria — completata nel codice

### Fase 0 — Correttezza e conservazione dati (2–3 settimane)

- Correzione etichette `sp17d/e/f`.
- N. 2: passaggio infrannuale → budget lossless.
- N. 10: debiti verso banche totali.
- Disegno contabile e tecnico del n. 1.
- Harness E2E con scenario campione e confronto campo-per-campo.

Gate di uscita: nessun valore manuale cambia senza conferma; debiti tributari e bancari non diventano negativi; quadratura rispettata.

### Fase 1 — Override patrimoniali e bilanci abbreviati (2–3 settimane)

- Infrastruttura comune n. 12.
- Campi richiesti dal n. 3.
- Maschera di segregazione n. 9.
- Soluzione manuale trasparente per imposte anticipate n. 8.

Gate di uscita: ogni override è visibile, reversibile, auditabile e riconciliato con gli aggregati.

### Fase 2 — Finanziamenti analitici (2 settimane)

- Modello multi-mutuo n. 11.
- Piano capitale/interessi per contratto.
- Riconciliazione automatica con debiti bancari SP, oneri finanziari CE e flussi di finanziamento.

Gate di uscita: somma residui = SP; somma interessi = quota generata in `ce15`; piano completamente ammortizzato entro la durata.

### Fase 3 — Report, grafica e nomenclature (1–2 settimane)

- Allineamento report/proiezione n. 5–6.
- Collaudo rendiconto n. 7 e TFR n. 4.
- Dashboard infrannuale n. 13.
- Nomenclature n. 14.

Gate di uscita: report web/PDF completo e coerente; KPI e grafici derivano dagli stessi calcoli delle tabelle.

## Criteri di collaudo trasversali

1. Test unitari del motore per ogni formula contabile e caso limite.
2. Test API round-trip: salva → genera → ricarica → confronto valori/override.
3. Test E2E dei percorsi infrannuale 3/6/9/12M → promozione → budget 3/5 anni.
4. Controlli di quadratura CE–SP, aggregato–dettaglio e cassa iniziale/finale.
5. Dataset reali: ordinario, abbreviato, solo debito breve, debito misto, credito tributario, perdita fiscale.
6. Confronto report web e PDF con lo stesso scenario.
7. Accettazione funzionale con checklist firmata dal referente contabile.

## Evidenze principali nel codice

- Crediti tributari/imposte anticipate non più legati ai ricavi: `calculations/forecast_engine.py:546`.
- TFR automatico: `calculations/forecast_engine.py:613` e `calculations/intra_year_engine.py:879`.
- Debito esistente limitato al lungo termine: `calculations/projection_common.py:25`.
- Interessi nuovi finanziamenti in CE: `calculations/forecast_engine.py:405`.
- Promozione forecast → anno storico: `backend/app/services/promote_service.py:16`.
- Aliquota 27,9% nel percorso infrannuale 12M: `frontend/app/infrannuale/page.tsx:3336`.
- Proiezione SP read-only: `frontend/app/forecast/balance/page.tsx:573`.
- Dettaglio report SP: `frontend/components/report/report-appendices.tsx:35`.
- Rendiconto nel report: `frontend/app/report/page.tsx:245`.
- Indicatori infrannuali senza grafici: `frontend/app/infrannuale/page.tsx:4758`.
- Titolo simulatore corrente: `frontend/components/AppHeader.tsx:15`.
