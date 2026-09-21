# Ricerca dei dettagli senza rinunce silenziose

Branch: `feat/import-analytical-details`. Parser: `analytical-search-v5-2026-09-21`.

Questo intervento realizza il punto 3: la ricerca analitica non salta più un documento perché supera il precedente limite di 150.000 caratteri. Non modifica la prima classificazione, né riapre dettagli iniziali specifici in conflitto; restano separati i controlli di fonte e la chiusura finale dei residui.

## Lettura per blocchi

`importers/detail_search.py` pianifica blocchi di massimo 45.000 caratteri di testo annotato, riservandone fino a 6.000 al contesto. Sono incluse tutte le righe estratte, anche narrative, senza filtrare le note per parole chiave. Una riga eccezionalmente più lunga del limite è segnalata, non troncata; i blocchi successivi continuano.

Ogni riga ha un solo blocco proprietario. Intestazioni, conti antenati e righe immediatamente precedenti possono ricomparire come contesto non citabile, escluso dalle celle ammesse nello schema LLM. I riferimenti originali di pagina/riga/cella restano stabili.

Due letture possono procedere in parallelo; partono dall'ultimo e dal primo blocco per non rimandare sistematicamente le note alla fine del budget. Tutte le proposte valide vengono poi unite nell'ordine della fonte e riconciliate insieme: i frammenti di una famiglia possono quindi provenire da blocchi diversi. Un errore non annulla gli altri blocchi né le prove locali.

`PDF_DETAIL_SEARCH_SECONDS` imposta il budget per avviare nuovi blocchi (default 240 secondi; valori validi maggiori di zero e non superiori a 3.600). Non è un limite rigido alla durata complessiva: le richieste già avviate terminano con il timeout del client, eventuale retry e correzione dei riferimenti. Restano timeout di 90 secondi, un retry del client e al massimo una correzione strutturata per blocco. Numero di chiamate, costo e latenza possono quindi aumentare rispetto alla singola lettura.

## Esiti e conservazione

Il rapporto `validation_report.detail_enrichment` aggiunge:

- `search`: stato `complete`, `partial`, `not_searched` o `not_applicable`; righe e blocchi previsti/completati; pagine, riferimenti di confine ed errori per blocco.
- `search_families`: per famiglia e periodo, copertura e risultato distinto tra dettagli accettati, proposte non accettate, nessun dettaglio trovato nella ricerca o esito sconosciuto perché incompleta.
- `warnings`: avvisi per ricerca incompleta o famiglie con sole proposte non accettate. Sono esposti tra gli avvisi dell'importazione, persistiti e conservati nelle Rettifiche.

Timeout, risposte troncate, riferimenti estranei al blocco, budget esaurito, assenza di chiave/API, disabilitazione e assenza di celle non diventano più «nessun dettaglio trovato». Gli errori persistiti non contengono messaggi grezzi del client o credenziali.

Copertura completa significa lettura di tutte le righe **estratte**, non verifica visiva di tutte le pagine né garanzia di avere trovato ogni dettaglio. Pagine senza testo nativo impediscono di dichiarare la copertura completa, anche se un OCR globale non attribuito alle pagine fornisce del testo. Questo intervento non aggiunge un nuovo OCR; una pagina senza testo può anche essere semplicemente vuota.

La ricerca incompleta non invalida da sola un bilancio contabilmente corretto: resta un avviso di copertura. Le verifiche contabili, della fonte e dei residui mantengono i loro blocchi separati. Il residuo non spiegato resta nel contenitore convenzionale senza modificare gli aggregati.

## Rappresentazioni ripetute

La prova reale ha mostrato che blocchi diversi possono proporre sia la voce del prospetto sia la stessa posta ripetuta nelle note. Il solo identificativo di cella non basta a evitare questo doppio conteggio.

Quando le celle tipizzate di una nota ricostruiscono **integralmente ed esattamente** una famiglia, senza conflitti nel riduttore, quella rappresentazione viene mantenuta e le alternative sono registrate come tali, non sommate. `reconciled_note_families` identifica questi casi. Una nota parziale non chiude la famiglia: gli ulteriori dettagli restano ricercabili e utilizzabili. Questa protezione non è una deduplicazione semantica universale di ogni possibile tabella parziale ripetuta.

## Verifiche

Suite di regressione: **362 passati, 3 saltati**. I 24 casi di `tests/test_detail_search.py` coprono documenti oltre il vecchio limite, note finali, contesto, errori intermedi, budget, risposte troncate, conservazione delle prove locali, risultati corrente/comparativo, doppie rappresentazioni, avvisi e persistenza attraverso importazione e Rettifiche.

Prova reale con LLM su FORMETAL 2025: 829 righe, 26 pagine, tre blocchi completati, cinque famiglie ricostruite dalle note, aggregati invariati. Dopo la correzione delle rappresentazioni ripetute sono stati verificati:

- crediti brevi: clienti 455.145; tributari 97.048; imposte anticipate 5.042; altri 22.644;
- crediti lunghi: tributari 95.428;
- debiti brevi: banche 710.247; soci/altri finanziatori 34.450; fornitori 364.665; tributari 16.709; previdenziali 31.961; altri 97.624;
- debiti lunghi: banche 459.080; rimanenze: materie prime 79.135.

La prova reale riguarda il secondo lettore sugli aggregati noti, non una nuova importazione completa della pratica. I test d'integrazione esercitano invece l'orchestratore e la persistenza con risposte LLM controllate e database in memoria. Nessuna modifica ai bilanci salvati dell'utente. I problemi specifici di FTC e della leggibilità di Budget 624 non vengono dichiarati risolti da questo intervento.
