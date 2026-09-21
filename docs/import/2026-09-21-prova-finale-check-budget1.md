# Prova finale: importatore contro lettura visiva indipendente

Data: 21 settembre 2026. Branch `feat/import-analytical-details`, parser `analytical-search-v5-2026-09-21`.

Questo documento conserva la prova precedente alle correzioni. L'implementazione
successiva e la nuova verifica sono descritte in
[Ricostruzione dai conti documentati](2026-09-21-ricostruzione-conti-documentati.md).

## Metodo ed esito

Esaminati i quattro nuovi PDF di `inbox/check-budget1`: 948, 949, 967 e 972. Tutte le 16 pagine sono state renderizzate e lette visivamente. Ho trascritto un riferimento indipendente, poi calcolato le somme con `Decimal`, senza usare i classificatori dell'importatore per costruirlo. Le importazioni complete hanno usato l'orchestratore reale, chiamate LLM reali e database SQLite separati in memoria. Nessuna modifica alle pratiche salvate o al codice dell'importatore durante questa prova.

**La prova non è superata nel suo complesso.** La quadratura e lo stato `verified` non bastano ancora a certificare la corretta composizione.

| Documento | Risultato del sistema | Confronto indipendente |
|---|---|---|
| 948 — PMI, giugno 2026 | Verificato, proiezione abilitata; SP 2.888.604,35; utile 200.220,95 | Totali corretti; errori in capitale, crediti, scadenze, debiti e natura di un provento CE |
| 949 — PMI, giugno 2025 | Verificato, proiezione abilitata; SP 2.584.168,34 | Classificazioni errate e incoerenza reale CE–SP di 745,89 tollerata dal sistema |
| 967 — COMAP, 2025 e 2024 | Entrambi verificati e proiettabili | Campi SP confrontati corretti, inclusi dettagli e segni; CE arrotondato all'euro nonostante i centesimi leggibili |
| 972 — Gerevini, infrannuale 2026 | Salvato come sbilanciato, proiezione bloccata | Importazione gravemente errata; la fonte è invece riconciliabile |

Il file 972 si chiama «al 31-07-2026», ma l'intestazione riporta movimenti fino al **7 agosto 2026**. Il test usa sette mesi come ipotesi dal nome del file, non come periodo certificato. Va chiarito prima di usare i dati per una proiezione.

## 948 — PMI 30/06/2026

Il documento stampa attività lorde 4.994.029,04. Sottraendo fondi ammortamento immateriali 955,68 e materiali 2.104.469,01, lo SP netto è **2.888.604,35**, coerente con il risultato CE/SP **200.220,95**.

| Voce | Come la importerei dalla fonte | Importato |
|---|---:|---:|
| Capitale sociale | 50.000,00 | 0,00 |
| Riserve, escluso il capitale | 1.508.318,53 | 1.558.318,53 |
| Crediti clienti | 1.057.995,94 | 1.188.578,93 |
| Crediti tributari brevi | 106.722,63 | 106.722,63 |
| Altri crediti brevi | 21.894,56 | 7.161,98 |
| Altri crediti oltre esercizio successivo | 115.850,41 | 0,00 |
| Banche a breve | 42.674,24 | 88.008,91 |
| Mutui/finanziamenti bancari a lungo, regola gestionale | 37.177,67 | 0,00 |
| Fornitori a breve | 270.271,93 | 270.271,93 |
| Tributari a breve | 64.311,86 | 64.345,87 |
| Previdenziali a breve | 20.954,61 | 20.258,23 |
| Altri debiti a breve | 94.687,48 | 87.192,85 |

I crediti clienti sono 856.252,51 più gli altri crediti verso clienti 201.743,43: non tutto il residuo dei crediti appartiene ai clienti. La voce «CRED.DIV.ESIG.OLTRE ES.SUCC.» documenta direttamente la scadenza lunga. Crediti verso soci, previdenziali e saldi a credito verso fornitori restano distinti; questi ultimi non diventano automaticamente acconti su rimanenze senza ulteriori indicazioni.

Le rimanenze sono correttamente importate come **merci/prodotti finiti 293.286,60**, non materie prime.

Nel CE il sistema mette **18.668,91 di proventi finanziari** negli altri ricavi: il risultato finale non cambia, ma cambia la lettura della gestione operativa. La mia riclassificazione sposta inoltre le sopravvenienze passive di 13.883,40 negli oneri diversi; il sistema le conserva nel campo straordinario legacy. Quest'ultima è una scelta di rappresentazione da distinguere dall'errore sui proventi finanziari.

## 949 — PMI 30/06/2025

SP netto **2.584.168,34**. Rimanenze correttamente attribuite a merci per **196.644,70**.

| Voce | Come la importerei dalla fonte | Importato |
|---|---:|---:|
| Capitale sociale | 50.000,00 | 0,00 |
| Riserve | 1.492.664,46 | 1.542.664,46 |
| Crediti clienti | 737.433,90 | 909.465,28 |
| Crediti tributari brevi | 59.077,94 | 42.124,20 |
| Altri crediti brevi | 155.507,64 | 430,00 |
| Banche a breve | 50.693,19 | 180.783,99 |
| Mutui/finanziamenti bancari a lungo, regola gestionale | 120.995,21 | 0,00 |

Gli altri crediti comprendono soprattutto **139.484,00 di «SOCI C/RIMBORSI» sul lato attività**, oltre a INAIL e saldi a credito verso fornitori. Non sono crediti commerciali verso clienti.

La fonte contiene un'incoerenza reale:

- SP, pagina 2: utile **47.903,81**;
- CE, pagina 4: ricavi **1.069.479,13** meno costi **1.020.829,43** = utile **48.649,70**;
- differenza: **745,89**.

Io conserverei entrambi i risultati documentati e chiederei verifica, senza una scrittura compensativa. Il sistema conserva i numeri, ma li dichiara coerenti e abilita la proiezione. La causa è dimostrata: `check_quadratura` usa per CE–SP `max(2 euro, 0,1% dell'attivo)`, qui **2.584,16834 euro**. Il controllo separato registra lo scarto nei log, mentre il rapporto persistito indica `income_result_consistent=true`, `semantic_valid=true` e non riporta l'avviso CE–SP.

## 967 — COMAP 2025 e comparativo 2024

È il caso migliore della prova. I campi SP del riferimento coincidono per entrambi gli anni:

- totale 2025 **1.125.225,58**; 2024 **688.939,96**;
- rimanenze 2025: materie prime **35.825,00**, prodotti finiti **13.420,00**;
- crediti 2025: clienti netti **406.206,62**, tributari **44.844,33**, imposte anticipate **33.504,00**, altri **44.521,56**;
- debiti 2025 tutti a breve, come stampato: banche **−63.907,40**, altri finanziatori **2.346,38**, fornitori **418.498,00**, tributari **65.814,91**, previdenziali **33.067,36**, altri **8.533,47**.

Il saldo bancario negativo è esplicito: **−408.482,43 + 344.575,03 = −63.907,40**. Lo conserverei con il relativo dettaglio; non lo azzererei né lo trasformerei in positivo. L'eventuale riclassificazione gestionale di questa esposizione richiede una decisione separata e non deve alterare la trascrizione della fonte.

Il CE invece perde i centesimi in molte voci:

| Risultato CE | Fonte e mia ricostruzione | Importato |
|---|---:|---:|
| 2025 | 32.368,64 | 32.369,00 |
| 2024 | 220.177,52 | 220.176,00 |

Per esempio i servizi 2025 diventano 581.769,00 invece di 581.768,92. Il salvataggio supporta i centesimi: non è un limite del database. In questa prova non è stata catturata la risposta grezza della prima chiamata CE, quindi il punto esatto in cui avviene l'arrotondamento resta da isolare. Il controllo indipendente della fonte declina il documento con `ambiguous year columns`, anziché correggere il CE.

## 972 — Tipografia Litografia Gerevini

La fonte è riconciliabile:

- attività lorde **2.430.972,27**;
- passività prima dell'utile **2.321.889,23** + utile **109.083,04** = attività;
- fondi ammortamento **399.637,60** e fondo svalutazione clienti **8.036,89**;
- SP netto ricostruito **2.023.297,78**;
- CE: **1.094.381,01 − 985.297,97 = 109.083,04**.

Come ricostruirei lo SP:

| Famiglia | Importo e composizione |
|---|---|
| Immobilizzazioni immateriali nette | 22.353,57 |
| Immobilizzazioni materiali nette | 1.232.838,25 |
| Rimanenze | 191.524,62, tutte materie prime |
| Crediti brevi | 396.123,06: clienti netti 311.134,11; tributari 34.193,32; altri 50.795,63 |
| Liquidità | 178.825,52, senza aggiungere i conti bancari del passivo |
| Ratei/risconti attivi | 1.632,76 |
| Capitale | 2.700,00 |
| Riserve e risultati precedenti | 289.757,46, di cui 98.464,87 di eccedenza dell'esercizio precedente |
| Utile corrente | 109.083,04 |
| TFR | 95.394,62 |
| Debiti brevi | 741.211,64: banche 250.369,15; fornitori 329.766,49; tributari 9.957,31; previdenziali 5.913,96; altri 145.204,73 |
| Debiti lunghi | 785.059,38: banche 725.059,38; finanziamento socio 60.000,00 |
| Ratei/risconti passivi | 91,64 |

Le scadenze non documentate seguono la convenzione richiesta: mutui/finanziamenti a lungo, altri saldi a breve. Le anticipazioni bancarie 222.511,92 sono distinte dai mutui; i debiti bancari brevi includono anche c/c passivi 26.719,25 e interessi maturati 1.137,98. Il finanziamento socio non è un mutuo bancario. I debiti verso soci per utili assegnati restano distinti dal risultato precedente presentato separatamente nel patrimonio netto. La «Polizza Allianz» di 49.260,88 resta provvisoriamente tra gli altri crediti, seguendo il prospetto: non ne inventerei una diversa natura senza il contratto.

Nel CE distinguerei le rimanenze iniziali di prodotti finiti **24.830,70**, senza saldo finale, dalla variazione materie prime **86.923,08 − 191.524,62 = −104.601,54**. Non userei rimanenze iniziali CE come dettaglio delle rimanenze finali SP. Non aggiungerei ammortamenti CE assenti dal documento.

Il sistema invece salva attivo **1.653.893,97**, passivo **494.561,86**, utile CE **−177.422,46**. Le macro-voci crediti e debiti sono zero, pur essendoci sottoconti valorizzati; il socio da 60.000 è presente sia nel dettaglio banche lunghe sia in altri finanziatori. La liquidità include erroneamente anche i c/c passivi. Le rimanenze finali sono contaminate dalle iniziali CE.

Il blocco della proiezione funziona. È però errato l'avviso che attribuisce lo sbilancio al documento: confronta il totale attività con le passività **prima dell'utile**, ignorando l'utile stampato subito sotto.

## Cosa dimostra sulla logica dell'importatore

1. **Ricerca eseguita non significa classificazione corretta.** Nessun blocco LLM è fallito: PMI 318/318 e 292/292 righe, COMAP 239/239 in due blocchi, Gerevini 383/383. Tuttavia Gerevini ammette soltanto la famiglia rimanenze, perché crediti/debiti hanno macro-voci zero. Lo stato globale `complete` non certifica la copertura delle famiglie erroneamente escluse a monte.
2. **L'ipotesi iniziale resta troppo vincolante.** Nei PMI le correzioni dei debiti vengono rifiutate per «conflitto con dettaglio iniziale specifico». Anche il passaggio delle scadenze può trasformare un residuo non riconosciuto in un dettaglio clienti poi protetto. La chiusura aritmetica conserva questi errori di composizione.
3. **Esistono falsi positivi deterministici riproducibili.** `_debt_type('AMMINISTRATORI C/COMPENSI')` e il corrispondente conto collaboratori restituiscono banche: la sottostringa `C/C` intercetta anche `C/COMPENSI`. «RITENUTE SINDACALI» diventa tributario. FSBA/EBNA e SAN.ARTI non vengono riconosciuti come previdenziali. La forma abbreviata «CRED.DIV.ESIG.OLTRE ES.SUCC.» non viene riconosciuta né per natura né per scadenza.
4. **La certificazione è troppo permissiva.** La tolleranza CE–SP nasconde lo scarto reale di PMI 2025; la presenza di sottocampi bancari è inoltre utilizzata come prova di affidabilità anche quando tali sottocampi sono classificati male.
5. **I controlli indipendenti non coprono ancora questi layout.** La riconciliazione della fonte declina tutti e quattro i documenti di questa prova. In Gerevini, macro-voci nulle non vengono ricostruite prima della ricerca: sommare ciecamente i dettagli non sarebbe comunque sufficiente, perché esistono sovrapposizioni ed errori.

Priorità consigliata: prima rendere onesta la validazione dei risultati documentati; poi permettere a ricostruzioni provate di sostituire classificazioni iniziali errate, distinguendo importi documentati da residui convenzionali; infine normalizzare gerarchie/macro-voci e preservare la precisione della fonte. Non basta aggiungere altre parole chiave al lettore.

## Riproduzione e artefatti

Artefatti di questa esecuzione: `/tmp/budget-final-vision.iWzqfi/`.

- `run.py`: quattro importazioni isolate con trace prima/dopo l'arricchimento;
- `948.json`, `949.json`, `967.json`, `972.json`: valori effettivamente salvati e rapporti completi;
- file `.log`: diagnostica dell'importazione;
- `vision_reference.py` e `vision_reference.json`: trascrizione indipendente, macro-voci/sottocampi e calcoli esatti; lo script verifica cinque quadrature SP e i risultati CE stampati, mantenendo lo scarto reale di PMI 2025;
- `948-1.png` … `972-4.png`: le 16 pagine lette visivamente.

I risultati sono quelli di una singola esecuzione reale per PDF; la variabilità LLM non è stata misurata con ripetizioni. Il riferimento conserva separatamente i saldi debitori/creditori di controparti non identificabili: compensazioni ulteriori richiedono evidenza, non sono state usate per far tornare i conti.
