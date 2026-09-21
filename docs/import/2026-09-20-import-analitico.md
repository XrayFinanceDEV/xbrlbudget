# Importazione analitica: primo intervento

> Seguito implementato: [riconciliazione con la fonte](2026-09-20-integrazione-riconciliazione-fonte.md). Il secondo lettore descritto qui resta conservativo; una nuova fase indipendente può invece correggere gli aggregati e i dettagli iniziali contraddetti da prospetti riconciliati.

> Aggiornamento 21 settembre: [ricerca per blocchi senza rinunce silenziose](2026-09-21-ricerca-dettagli-per-blocchi.md). Supera la singola lettura e il salto dei documenti lunghi descritti nella versione iniziale.

Branch: `feat/import-analytical-details`.

Questa implementazione aggiunge una seconda lettura dopo la selezione dell'estrattore e il netting. Si attiva anche quando il bilancio quadra e quando ha vinto il candidato deterministico. La prima applicazione riguarda rimanenze, crediti e debiti, correnti e comparativi. Gli altri dettagli continuano a seguire i percorsi esistenti.

## Regola di conservazione

Il recupero dei dettagli conserva gli aggregati, il conto economico e il risultato. Recupera sottocampi documentati e lascia la differenza nella destinazione iniziale. Non richiede una ricostruzione completa al centesimo. Una fase distinta applica la regola gestionale delle scadenze richiesta dall'utente: può spostare importi fra breve e lungo, ma conserva esattamente i totali combinati dei crediti e dei debiti.

Esempio verificato: rimanenze inizialmente tutte in materie prime per €231.250,03; la fonte prova merci €170.000, lavori su ordinazione €40.000 e materie prime €21.250. Il risultato conserva €21.250,03 nelle materie prime, con €0,03 dichiarati ancora irrisolti. Non viene modificato il totale.

I dettagli specifici già presenti sono protetti: una proposta incompatibile viene registrata come conflitto. Le proposte che superano il residuo disponibile vengono rifiutate senza riproporzionamento; le altre voci utilizzabili vengono comunque conservate. Il contenitore convenzionale singolo può invece essere suddiviso.

## Lettura e interpretazione

`importers/detail_enrichment.py`:

1. Legge tutte le pagine, comprese le note; conserva riferimenti di riga, pagina, lato, codici conto, importi e coordinate delle celle. Normalizza le coordinate dei PDF ruotati; esclude codici conto, numerazione delle voci e durate dalle celle monetarie. Può usare il testo OCR già disponibile se manca il testo nativo.
2. Identifica le colonne delle tabelle standard della nota: inizio, variazione, fine, entro e oltre. Sulle sezioni contrapposte usa il saldo finale delle righe patrimoniali, escludendo movimenti e righe economiche.
3. Recupera i dettagli espliciti dai conti e dalle tabelle. Un padre omogeneo può essere utilizzato; un padre con banche e soci viene aperto nei componenti. Il codice non decide la natura di un conto dal solo numero.
4. Chiede all'LLM una seconda interpretazione del documento, con le famiglie iniziali. La risposta indica campi e riferimenti alle celle, non nuovi importi da accettare sulla fiducia.
5. Unisce le prove locali e le proposte LLM. Verifica appartenenza alla famiglia, esistenza della cella, ruolo della colonna, periodo, sovrapposizioni padre/figlio, duplicati e capienza.

### Scadenze: regola gestionale richiesta

Le scadenze esplicite prevalgono sempre, comprese quelle nelle tabelle della nota. Sui saldi patrimoniali a sezioni contrapposte, quando mancano scadenze esplicite:

- crediti e debiti non dettagliati: **entro 12 mesi**;
- mutui e finanziamenti bancari, soci o altri finanziatori: **oltre 12 mesi**;
- un conto corrente bancario, da solo, resta a breve.

La fase `reclassify_ledger_maturities` ricostruisce la natura delle poste con prove non sovrapposte, attribuisce al lungo le quote identificate e lascia a breve il residuo non spiegato. Non riproporziona valori. Le scadenze convenzionali sono registrate come `management_default_short` o `management_financing_long`, distinte da `documented`. Quando manca persino una famiglia di fonte identificabile o ci sono conflitti, conserva l'estrazione iniziale. La regola non viene applicata al comparativo usando i saldi correnti.

Le colonne iniziali dei crediti/debiti nella nota non vengono usate per inventare le scadenze dell'anno precedente. Possono invece dettagliare le rimanenze comparative, che non richiedono quella suddivisione.

### Dettagli dei crediti

Il secondo lettore cerca clienti (incluse fatture da emettere), controllate, collegate, controllanti, tributari, imposte anticipate e altri crediti, sia a breve sia a lungo. Apre anche mastri misti come «CREDITI VARI» e «CONTI ERARIALI» e legge le tabelle della nota integrativa.

I crediti immobilizzati e le disponibilità liquide sono esclusi, anche quando una voce figlia ha una descrizione generica. Un saldo clienti lordo con un fondo svalutazione separato non viene speso come se fosse un credito netto: resta il netto iniziale/residuo, senza sottrazioni inventate. Le imposte anticipate senza quota entro/oltre usano il saldo finale in `sp06f`, secondo la convenzione del modello dati; gli altri saldi finali delle tabelle non vengono scambiati per quote a breve.

## Correzione preliminare del patrimonio netto TM

Il recupero gerarchico in `situazione_contabile_parser.py` ora apre i mastri ambigui «CAPITALE E RISERVE» e «RISULTATI DELL'ESERCIZIO» quando i figli diretti ricostruiscono il padre. Questo impedisce che gli utili portati a nuovo finiscano nei debiti. La modifica precede l'arricchimento e corregge la classificazione fra aggregati; il secondo passaggio resta invece confinato ai sottocampi.

## Provenienza e disponibilità

Il `validation_report.detail_enrichment` conserva stato della lettura, famiglie elaborate, totale, contenitore, importi documentati e irrisolti, riferimenti di riga/pagina/cella e motivi delle proposte rifiutate. La sezione `maturity` conserva valori prima/dopo e motivazione delle scadenze. La traccia dell'importazione sopravvive alle successive Rettifiche.

`residual_in_bucket` include anche l'importo realmente documentato nella categoria residuale; `unresolved` misura invece la quota non spiegata dalle prove accettate in questo passaggio. Quest'ultima non implica che eventuali dettagli preesistenti siano errati.

La lettura LLM usa il modello Anthropic già configurato, ora con una chiamata per blocco che copre entrambi gli anni, timeout di 90 secondi e un retry del client. Lo schema elenca gli ID di riga disponibili. Se il modello restituisce riferimenti inesistenti o indici fuori intervallo, è ammessa una sola chiamata ulteriore per blocco con gli errori da correggere. I riferimenti ancora errati vengono rifiutati, mai interpretati arbitrariamente. Se il modello non è disponibile, le prove locali restano utilizzabili. Nessuna nuova dipendenza o migrazione del database.

`PDF_DETAIL_ENRICHMENT=0` disabilita il secondo passaggio. Senza chiave API viene eseguito soltanto il recupero locale. I documenti oltre 150.000 caratteri di testo annotato non vengono più saltati: sono suddivisi in blocchi, con copertura ed eventuali errori espliciti. Su scansioni prive anche di testo OCR non si aggiungono dettagli privi di prove.

## Verifiche

Test in `tests/test_detail_enrichment.py`: residui non nulli, conservazione degli aggregati, idempotenza, conflitti, segni, duplicazioni, riferimenti inesistenti, somme eccedenti, periodi, colonne di movimento, indisponibilità del modello, OCR, salvataggio su database in memoria per corrente/comparativo e conservazione della provenienza dopo Rettifiche.

Le regressioni sui PDF privati vengono saltate negli ambienti in cui `inbox/import-test` non è disponibile; i test sintetici e di persistenza restano eseguibili.

Le prove dal vivo del secondo passaggio, con chiamate LLM e senza scritture sui bilanci dell'utente, hanno verificato:

| Fonte | Risultato |
|---|---|
| TM 2025 | Rimanenze 21.250 / 170.000 / 40.000; debiti oltre 12 mesi: banche 268.242,15, soci 2.455,95; breve: fornitori 133.144,56, tributi 1.971,81, previdenza 14.300,34, altri 27.118,02 |
| TM maggio 2026 | Stesse tre componenti delle rimanenze; oltre 12 mesi: banche 349.991,50, soci 6.455,95; breve: fornitori 310.448,41, tributi 23.113,67, previdenza 18.817,63, altri 28.547,26 |
| FORMETAL 2025 | Tutti i debiti delle pagine 18–19: breve 1.255.656, lungo 459.080, correttamente suddivisi; rimanenze 79.135 in materie prime |
| FORMETAL comparativo 2024 | Materie prime 70.835 e merci 53.415, senza introdurre scadenze dei debiti dedotte dalla nota 2025 |

Regressioni aggiunte sui crediti: TM 2025 clienti €271.202,44, tributari €129.413,95, altri €6.020,18; TM maggio 2026 clienti €501.823,05, tributari €147.807,76, altri €6.020,42. FORMETAL 2025: clienti €455.145, tributari brevi €97.048 e lunghi €95.428, imposte anticipate €5.042, altri €22.644. La nota conserva le proprie scadenze esplicite, senza applicare il default dei finanziamenti a lungo.

Il test di integrazione esegue l'orchestratore reale e il salvataggio in SQLite in memoria, sostituendo soltanto le risposte LLM per renderlo ripetibile. Le prove dal vivo verificano invece il secondo passaggio sugli aggregati dei casi reali. Non sono reimportazioni complete delle pratiche e non certificano l'assenza di altri problemi nelle famiglie fuori da questo intervento.

Successivamente sono state eseguite importazioni complete sui sei PDF nuovi di `inbox/riptova`. Vedere [esiti e limiti riscontrati](2026-09-20-test-riptova.md): la suite tecnica passa, ma i test reali mostrano ancora errori nella prima estrazione e falsi positivi della sola quadratura.
