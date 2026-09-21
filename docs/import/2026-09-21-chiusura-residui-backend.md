# Chiusura obbligatoria dei residui nel backend PDF

Branch `feat/import-analytical-details`; parser `analytical-residuals-v4-2026-09-21`.

## Intervento sul punto 1

`importers/residual_finalization.py` aggiunge una fase obbligatoria dell'orchestratore PDF, dopo estrazione, prove sulla fonte e ricerca analitica, prima di validazione e salvataggio. Si applica a corrente e comparativo, indipendentemente dalla rotta di estrazione e dall'esito del secondo lettore.

La chiusura non dipende da proposte accettate: funziona anche con lettore disabilitato, documento senza celle utilizzabili, nessuna proposta, proposte tutte rifiutate e timeout LLM. Le altre modalità di importazione (XBRL/CSV) mantengono i propri percorsi esistenti.

## Regole

- Per ogni famiglia additiva con macrovoce presente, calcolare esattamente macrovoce meno somma dettagli.
- Se il residuo è positivo, aggiungerlo al solo contenitore convenzionale della stessa famiglia, anche se vale un centesimo. Nessuna soglia di arrotondamento lascia residui non allocati.
- Conservare macrovoci, dettagli specifici, scadenze, totali SP e risultato CE/SP. Nessun riproporzionamento o aggiustamento della cassa.
- Non compensare una somma dei dettagli superiore alla macrovoce con un nuovo importo negativo. Conservare i valori e registrare un conflitto, con revisione richiesta anche per un centesimo.
- Non ricavare una macrovoce assente dai suoi dettagli: anche questo è un conflitto da verificare.
- Una macrovoce negativa priva di dettagli viene conservata integralmente nel contenitore convenzionale; una partizione negativa già presente ma incompleta resta da verificare. I dettagli negativi documentati non vengono azzerati.
- Non confondere dettagli di segno opposto che si annullano con assenza di dettagli.
- La funzione lavora su copie ed è idempotente: una seconda esecuzione non aggiunge nuovamente il residuo.

### Destinazioni convenzionali, non fatti ricavati dalla fonte

Per lo SP si riutilizza la politica di `residual_bucket`: senza dettagli, rimanenze in materie prime e crediti brevi in clienti, come già previsto dal progetto; con dettaglio parziale, residui nei contenitori previsti per ciascuna famiglia. Crediti/debiti a lungo restano a lungo. Le famiglie già chiuse dal passaggio analitico non vengono riclassificate.

Per il personale il residuo va in altri costi del personale, senza inventare salari, contributi o TFR. Per ammortamenti/svalutazioni il modello non ha un campo «non classificati»: viene usato `ce09c_svalutazioni`, già contenitore convenzionale dell'interfaccia PDF, con provenienza esplicitamente convenzionale. Non viene fatta la ripartizione proporzionale fra ammortamenti materiali e immateriali del diverso percorso XBRL/CSV.

Questi contenitori non provano la natura dell'importo non riconosciuto. La famiglia non additiva delle rettifiche finanziarie `ce17` rimane affidata ai propri controlli: non si inventano rivalutazioni/svalutazioni per chiuderla.

## Audit e Rettifiche

`validation_report.residual_finalization` conserva per famiglia: macrovoce, somma dettagli prima/dopo, differenza, contenitore, importo allocato, natura convenzionale dell'allocazione e motivi dei conflitti. Non modifica né sovrascrive l'audit delle prove documentali o della ricerca analitica.

Un conflitto impedisce `forecastable=True` anche quando rientra nella tolleranza generale di quadratura. Le Rettifiche conservano l'audit storico e verificano nuovamente i conflitti sui valori correnti: un salvataggio senza modifiche non cancella il blocco; una correzione effettiva può rimuoverlo. La verifica sulle Rettifiche non applica automaticamente nuove allocazioni.

Un nuovo comparativo con conflitti nei residui non sostituisce un anno precedente già salvato e valido. Se non esiste uno storico, il comparativo può essere salvato come da verificare, senza abilitarne la proiezione.

Gli altri blocchi di affidabilità/fonte restano attivi. Completare i sottocampi non risolve uno sbilancio fra attivo e passivo, un risultato CE diverso da SP o un documento incoerente.

## Verifiche

- 42 nuovi test in `tests/test_residual_finalization.py`, inclusi salvataggio effettivo in SQLite in memoria, Rettifiche per corrente/comparativo e conservazione dello storico valido.
- Suite estesa finale: 338 test superati, 3 saltati; comprende anche ciclo HTTP, XBRL/CSV, adattatore MinerU e politica dei contenitori residuali. `git diff --check` senza errori.
- Reimportati i PDF reali 623, 636, 637 e 682 con database in memoria e secondo lettore disabilitato: tutti verificati, inclusi i comparativi disponibili; SP e risultati invariati. Questa prova verifica specificamente l'indipendenza della chiusura dall'LLM, non la qualità di una nuova lettura LLM.
- Nessuna migrazione, modifica all'interfaccia o scrittura sui bilanci dell'utente. Nessun nuovo tentativo di risolvere i problemi documentali di 624/FTC in questo intervento.

Il codice aggiornato deve essere caricato dal backend; i bilanci già importati richiedono una nuova importazione per ricevere questa fase e il relativo audit.
