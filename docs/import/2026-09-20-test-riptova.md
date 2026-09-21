# Test reali dell'importatore: inbox/riptova

> Questo documento conserva la diagnosi della prima versione. L'integrazione successiva e gli esiti aggiornati sono in [riconciliazione con la fonte](2026-09-20-integrazione-riconciliazione-fonte.md).

Branch `feat/import-analytical-details`. Importazioni complete con LLM reale, senza risposte simulate, usando lo stesso orchestratore dell'endpoint PDF. Ogni documento è stato importato in un processo con SQLite in memoria attraverso `tests/_import_probe.py`. Nessuna scrittura nel database delle aziende dell'utente.

## Esito

**I sei documenti vengono salvati, ma il test di correttezza complessiva non è superato.** La quadratura da sola continua a non certificare la classificazione. Il nuovo passaggio recupera dettagli e scadenze, ma non corregge gli aggregati sbagliati prodotti dalla prima estrazione, né sostituisce automaticamente dettagli specifici incompatibili già presenti.

La passata completa successiva alle correzioni del lettore delle righe ha prodotto:

| Documento | Periodo richiesto | Stato applicativo | Attivo − passivo | Verifica sulla fonte |
|---|---|---|---:|---|
| 623 — FERROLEGNOMARKET | 2025 | review_required | €0,00 | Rimanenze stampate €1.405.556,94, aggregate rimanenze importate a zero; crediti sovradimensionati già prima del secondo passaggio |
| 624 — FERROLEGNOMARKET | 2024 | verified | €0,00 | Rimanenze stampate €1.468.999,24, aggregate rimanenze importate a zero. È un falso positivo sostanziale del criterio di verifica |
| 636 — FACCHINETTI | aprile 2026, 4 mesi | review_required | €0,00 | Dettagli crediti presenti, comprese rettifiche negative; risultato non stabile nelle ripetizioni |
| 637 — FACCHINETTI | 2025 + comparativo 2024 | unbalanced | €1.000,00 | La fonte stampa attivo/passivo entrambi €3.329.271,63; la prima estrazione produce passivo €3.328.271,63 |
| 680 — FTC | maggio 2026, 5 mesi | unbalanced | €236.896,29 | Incoerenze importanti già nella prima estrazione; risultato CE €569.550,18 contro risultato SP €140.832,76 |
| 682 — PHARMA HUB | 2025 + comparativo 2024 | review_required | €0,00 | Totale crediti €2.158.149, ma somma dettagli iniziali maggiore di €937.000; il secondo passaggio non può confermare la famiglia |

Questi sono **stati restituiti dal software**, non giudizi di correttezza. In particolare `verified` per il documento 624 non è un esito accettabile del test sulla fonte.

## Cosa è stato verificato sul nuovo passaggio

Sono stati registrati gli input e gli output immediatamente prima/dopo `enrich_pdf_details`, per corrente e comparativo. In tutti e sei i casi:

- il totale combinato dei crediti è conservato;
- il totale combinato dei debiti è conservato;
- l'aggregato rimanenze è conservato;
- lo sbilancio SP è identico prima e dopo: i problemi di quadratura riportati non sono introdotti dal secondo passaggio.

Le imposte anticipate dei due FERROLEGNOMARKET sono riconosciute come **oltre esercizio**, rispettando il marcatore esplicito `(OE)`: €39.852,12 nel 2025 ed €29.816,28 nel 2024. L'assenza di rimanenze nella prima classificazione resta invece irrisolta: la seconda lettura non ha autorizzazione a prelevare milioni dai crediti per ricostruire un'altra famiglia patrimoniale.

FACCHINETTI mostra crediti verso altri a breve negativi per €12.050,69. Questi importi devono essere conservati, non azzerati. È stata aggiunta una regressione specifica per confermare dettagli già presenti anche quando il contenitore residuale è negativo.

PHARMA HUB rende evidente un altro limite: un dettaglio specifico iniziale errato viene attualmente protetto dal riduttore conservativo. La fonte distingue controllate €937.202, controllanti €938 e imprese sotto comune controllo €121.286; una prima estrazione ha prodotto €1.059.224 nelle controllanti, incompatibile con la fonte e con il totale della famiglia.

## Correzioni emerse durante i test

1. **Rotazione del PDF 623:** le coordinate native non corrispondevano all'orientamento visualizzato; le righe venivano fuse in colonne verticali. Il nuovo lettore normalizza le coordinate prima di ricostruire righe e lati.
2. **Codici e numerazioni scambiati per importi:** esclusi i codici AGO a 8 cifre e i sottoconti a 6+3 cifre; conservati i rapporti padre/figlio. Escluse numerazioni come `1)` e durate come `12 mesi`.
3. **Riferimenti LLM non validi:** lo schema elenca gli ID di riga effettivamente disponibili; è ammesso un tentativo aggiuntivo di correzione di indici, ID o struttura della risposta. Nessuna conversione arbitraria degli indici.
4. **Scadenze EE/OE:** riconosciute come indicazioni documentate e prioritarie rispetto ai default gestionali.
5. **Contenitore negativo:** una conferma esatta non consuma nuovamente disponibilità e può documentare anche crediti residuali negativi.

## Variabilità osservata

Sono state effettuate più esecuzioni reali. Le risposte della prima estrazione LLM non sono identiche: FACCHINETTI aprile 2026 ha prodotto inizialmente uno sbilancio di €11.950,69, poi zero e successivamente −€200. FACCHINETTI dicembre 2025 ha prodotto €998, poi €1.000 e nell'ultimo ricontrollo −€44.996,26; anche quest'ultimo scarto è invariato prima/dopo il passaggio analitico. FTC ha prodotto inizialmente uno sbilancio di €2.085.812, poi €236.896,29. Le differenze non sono prove di correzione del problema a monte: vanno trattate come instabilità del processo di estrazione/selezione.

Nel ricontrollo di PHARMA HUB il secondo lettore termina correttamente e recupera le rimanenze (materie €16.860, lavori su ordinazione €646.820, prodotti finiti €50.366), ma rifiuta la famiglia crediti già sovra-allocata. Non è quindi un'importazione complessivamente corretta.

## Passo successivo necessario

La prima classificazione deve diventare **un'ipotesi verificabile**, non un vincolo intoccabile perché il totale SP quadra:

1. verificare ogni macrovoce contro il totale e la gerarchia stampati, inclusi segni, scadenze e anni;
2. riaprire una famiglia assente o contraddetta dalla fonte, evitando che tutto finisca nei crediti o in altre voci residuali;
3. consentire la sostituzione di un dettaglio specifico errato soltanto con una riconciliazione documentata completa della famiglia;
4. subordinare `verified` alla coerenza con la fonte e alla gerarchia, non soltanto alla quadratura;
5. usare questi sei PDF come casi di accettazione, separando successo tecnico, quadratura e correttezza dei conti.

## Riproduzione e artefatti

Comando esistente, con database isolato in memoria:

```bash
backend/venv/bin/python tests/_import_probe.py "inbox/riptova/budget_636_Facchinetti_Apr_26.pdf" --fiscal-year 2026 --period-months 4
```

Log, campi persistiti, metadati e input/output analitici di questa sessione sono in `/tmp/budget-riptova-audit.TSwcTH/`, sottocartelle `final` e `recheck`. Sono artefatti temporanei locali, non baseline di correttezza. I test automatici delle nuove regole sono in `tests/test_detail_enrichment.py`; i PDF privati sono saltati quando non disponibili.

Suite mirata finale: **162 test superati**, inclusi 33 casi del passaggio analitico. Questo esito tecnico è distinto dai problemi riscontrati nelle importazioni reali sopra elencate.
