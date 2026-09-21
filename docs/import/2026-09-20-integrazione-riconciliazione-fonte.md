# Integrazione: correggere le ipotesi con prove dalla fonte

> Aggiornamento del 21 settembre: [chiusura obbligatoria dei residui nel backend PDF](2026-09-21-chiusura-residui-backend.md), eseguita anche quando la ricerca analitica non produce dettagli.

Branch `feat/import-analytical-details`; parser `analytical-source-v3-2026-09-20`.

## Diagnosi

I problemi non erano soltanto nel prompt del secondo lettore. La prima estrazione produceva valori sbagliati che il passaggio conservativo, correttamente, non aveva autorità di cambiare:

- **Rimanenze AGO:** «Rim. prodotti finiti e merci» non riconosciuto dal classificatore dell'attivo; fallback nei crediti. Il parser per blocchi associava inoltre importi e sezioni sbagliati nei prospetti ruotati.
- **Patrimonio netto AGO:** perdite pregresse sul lato attivo scambiate per crediti; «Riserva contributi c/capitale» letta come capitale. Abbreviazioni CE `Rim.iniz`, `Rim.fin`, `Prov.fin` non riconosciute correttamente.
- **FACCHINETTI:** intestazioni comparative con date a trattini non riconosciute; schema dettagliato respinto dal lettore rigido, anche per sezioni a zero assenti. Il fallback LLM variava a ogni esecuzione. I crediti negativi e le riserve non erano ricostruiti stabilmente.
- **PHARMA:** intestazioni ATTIVITA'/PASSIVITA' e importi negativi con parentesi separata; confusione fra controllate, controllanti e imprese sotto comune controllo. La somma dei dettagli poteva superare il totale anche con SP quadrato.
- **FERROLEGNOMARKET 2024, pagina 4:** testo nativo incompleto, righe di mastro assenti e importi con sottolineature intercalate. Il solo lettore testuale non può certificare il CE completo.
- **FTC:** cinque colonne diverse (iniziale, Dare, Avere, movimento, finale), segni D/A e gerarchie ripetute. I lettori esistenti confondono ancora queste informazioni. In più, la fonte stessa presenta un saldo iniziale non riconciliato di €348.287,23: anche una lettura perfetta non autorizza a compensarlo nel risultato corrente.

## Logica aggiunta

`importers/source_reconciliation.py` separa due operazioni:

1. **Prova dello schema e dei totali.** Legge subtotali legali, celle nelle rispettive colonne annuali, scadenze esplicite e totali di controllo. Per AGO ricostruisce i mastri per coordinate/lato, senza sommare contemporaneamente padri e figli; riconcilia i quattro totali stampati, nettizza i fondi e tratta le perdite pregresse come patrimonio netto negativo.
2. **Correzione dell'ipotesi.** Solo una ricostruzione provata può sostituire lo stato patrimoniale iniziale, inclusi dettagli specifici errati e metadati di compensazioni riferiti al candidato scartato. Il CE viene sostituito soltanto se verificato separatamente contro valore/costi della produzione, risultato ante imposte, risultato finale e SP.

Se SP e CE sono entrambi provati, l'orchestratore li usa subito, evitando le estrazioni macro LLM e i relativi tentativi stocastici. Il secondo lettore analitico resta attivo: cerca ulteriori dettagli nelle pagine e nelle note, con residui conservativi e riferimenti alle celle. Non viene autorizzato a inventare importi o riequilibrare i totali.

Le prove incomplete/ambigue non sostituiscono i valori iniziali. Il supporto è intenzionalmente limitato agli schemi riconosciuti; non è un certificatore universale di PDF. Le somme dei prospetti con centesimi devono coincidere entro €0,01; per prospetti legali stampati in euro interi la tolleranza è €2. Le tolleranze non producono righe di compensazione.

### Scadenze e priorità delle prove

Rimane la convenzione richiesta: senza indicazioni esplicite, crediti/debiti a breve; finanziamenti e mutui, inclusi soci/altri finanziatori, a lungo. Le scadenze documentate prevalgono sempre.

La verifica finale ha individuato e corretto anche un conflitto tra le due fasi: una proposta di natura non accettata poteva far rientrare nel residuo a breve un debito `(OE)` già provato. Ora la partizione debiti ricostruita integralmente dalla fonte non viene azzerata dalla successiva rilettura parziale. Regressione specifica: conservazione di €35.000 verso altri finanziatori e €110.063,12 di altri debiti a lungo nel PDF 623.

### Provenienza e blocchi

`validation_report.source_reconciliation` registra metodo, prove di riga/pagina, controlli, errori, verifica separata SP/CE e campi prima/dopo quando sostituisce un'estrazione precedente. Corrente e comparativo hanno audit distinti.

Un'incoerenza provata della fonte o un CE non verificabile nel percorso parzialmente ricostruito imposta `requires_review` e impedisce `forecastable=True`. Il salvataggio resta possibile per consultazione. Le Rettifiche conservano audit e blocco: un salvataggio, anche senza modifiche, non è una prova che il problema documentale sia risolto. Per rimuovere questo blocco occorre al momento reimportare una fonte corretta/leggibile; non è stata aggiunta una nuova azione di attestazione manuale.

## Verifiche reali

Sei importazioni complete attraverso l'orchestratore usato dall'API, con SQLite in memoria e LLM reale per i passaggi che lo richiedono. Nessuna modifica al database delle aziende dell'utente.

| Documento | Esito dell'integrazione | Riscontro principale |
|---|---|---|
| 623 FERROLEGNOMARKET 2025 | SP/CE e gerarchia verificati | Rimanenze €1.405.556,94; clienti netti €46.854,35; capitale €51.480; perdita €34.590,25; attivo/passivo netti €1.921.252,80 |
| 624 FERROLEGNOMARKET 2024 | SP corretto; revisione CE ancora richiesta | Rimanenze €1.468.999,24; attivo/passivo netti €1.972.377,52. Il CE dell'import dal vivo coincide con l'utile stampato, ma la pagina incompleta impedisce la prova delle singole voci |
| 636 FACCHINETTI aprile 2026 | SP/CE e gerarchia verificati | Attivo/passivo €3.791.078,16; utile €140.513,78; conservati altri crediti brevi negativi €12.050,69 |
| 637 FACCHINETTI dicembre 2025 | Corrente e comparativo verificati | Attivo/passivo 2025 €3.329.271,63; utile €69.909,46; riserve €403.508,99. Comparativo 2024 €1.714.636,85 e perdita €88.850,42 |
| 680 FTC maggio 2026 | Non risolto; blocco affidabilità esplicito | Fonte: saldi finali attivi €11.458.889,38, passivi €11.666.343,85, utile CE €140.832,76; differenza non spiegata −€348.287,23. L'estrazione delle singole voci rimane inaffidabile |
| 682 PHARMA HUB 2025 | Corrente e comparativo verificati | Crediti correnti €2.158.149: clienti €978.403, controllate €937.202, controllanti €938, tributi €87.349, altri €154.257. Rimanenze €714.046; perdita €152.249 |

«Verificato» significa riconciliazione e corrispondenza delle famiglie lette dal software, non revisione contabile professionale. Per i due casi ancora problematici non viene dichiarata un'importazione completa corretta solo perché il salvataggio riesce o il risultato coincide.

## Copertura e riproduzione

Test sintetici e privati in `tests/test_source_reconciliation.py`: controlli mancanti, scarti ai centesimi, crediti negativi, celle comparative vuote, correzione di candidati già quadrati, rimozione di dettagli/metadati obsoleti, maturità documentate, import e persistenza del blocco dopo Rettifiche. I casi privati sono saltati se i PDF non sono presenti.

Suite mirata finale: **242 test superati, 3 saltati**; `git diff --check` senza errori. Comprende il secondo lettore, i lettori IV CEE, colonne comparative, riconciliazione CE/SP, netting, routing, affidabilità, persistenza e Rettifiche.

Artefatti della sessione: `/tmp/budget-riptova-audit.TSwcTH/integration-v3-final/` (JSON con campi salvati e audit, log separati per PDF). Sono file temporanei locali, non una baseline versionata.

Per ripetere un import isolato:

```bash
backend/venv/bin/python tests/_import_probe.py "inbox/riptova/budget_636_Facchinetti_Apr_26.pdf" --fiscal-year 2026 --period-months 4
```

Nessuna migrazione o dipendenza nuova. I bilanci già salvati non cambiano automaticamente: occorre una nuova importazione dopo aver caricato il codice aggiornato nel backend.

## Interventi rimasti

- **624:** recupero mirato della pagina incompleta via immagine/OCR e confronto delle voci CE con i totali, senza ricavare costi mancanti per differenza.
- **680:** lettore completo delle colonne Dare/Avere e saldo finale, con gerarchia di conti e contropartite coerente; richiesta di un prospetto corretto o chiarimento contabile dello sbilancio iniziale. Le due necessità sono distinte: migliorare il lettore non corregge i saldi della fonte.
- Estendere progressivamente gli adattatori di prova ad altri layout, mantenendo separate correzione degli aggregati e distribuzione dei residui analitici.
