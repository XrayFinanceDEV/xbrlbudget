# 03 — Quadratura: motore, arbitraggi, allineamento harness↔produzione

Il motore è già solido (check diagnostico + anti-masking + enforce CE↔SP + reconcile con cap). Gli interventi qui sono mirati: arbitraggi sbagliati, ancore fragili, e il fatto che l'harness misura una cosa diversa da ciò che fa la produzione.

---

## Q1 — Arbitraggio utile/perdita nel dichiarato (= 01-N2, riportato qui per completezza)

`_reconcile_trial_to_declared` (`pdf_extractor_llm.py:2269-2272`) fa vincere il candidato "utile" quando trova sia una perdita esplicita sia un conto PN "RISULTATO D'ESERCIZIO". Arbitrare con: (a) quale candidato riconcilia `attivo + risultato == pareggio`; (b) risultato ricostruito dal CE (`_net_profit_from_ce`, `iv_cee_hierarchy.py:322`). Caso di test: budget_211.

## Q2 — Validazione dell'ancora dichiarata (= 02-V8)

Prima di ancorare a un totale dichiarato: richiedere coerenza tra almeno 2 dei 3 valori letti (pareggio/attivo/passivo) oppure scarto < 20% dalla somma estratta. Un'ancora mal letta oggi genera spostamenti di massa arbitrari con flag ma senza diagnosi.

## Q3 — Allineare l'harness alla produzione (flag `--production`)

**Problema.** `Test/_quadratura_harness.py` fa `extract → check_quadratura` e basta:
- route A/B: mancano `reconcile_ivcee_balance` + `enforce_ce_sp_identity` → harness PESSIMISTA (falsi NO: budget_152/254/289/336 importano);
- route C: mancano `net_contra_accounts` + `_reconcile_trial_to_declared` → harness OTTIMISTA (falsi SI: budget_131 "SI" con il 35% di attivo mancante; budget_395 "SI" con sp02/sp03 sbagliati).

**Fix.** Aggiungere all'harness un flag `--production` che replica la catena completa di `pdf_importer` route C (extract → `_map_sc_keys` → `overlay_debt_typing` → `net_contra_accounts` → riduzione ancora → `_reconcile_trial_to_declared` → `enforce_ce_sp_identity` → `validate_balance` → `check_quadratura`), riusando le stesse funzioni (nessuna duplicazione: estrarre da `pdf_importer` una funzione `run_route_c_pipeline(bs, ce, file_path, text, declared)` chiamata sia dall'import vero sia dall'harness). Idem per A/B con `reconcile_ivcee_balance` + `enforce`. Output: per ogni file ANCHE sp02/sp03/sp13 finali e composizione plug, non solo SI/NO.

**Beneficio.** Da oggi in avanti il numero di baseline "X/28 quadrano" misura la stessa cosa che vede l'utente, e i bug silenti tipo budget_395 diventano visibili come diff sui campi.

## Q4 — Test di verità campo-per-campo (oltre la quadratura)

**Problema strutturale emerso da budget_395**: la quadratura NON è sufficiente — un file può quadrare con sp02/sp03 entrambi sbagliati. Serve un secondo asse di misura.

**Fix.** Creare `Test/_ground_truth/` con un file YAML/JSON per i PDF del corpus a valori noti (compilati a mano dai documenti: attivo, sp02, sp03, sp13, ed eventuali altri campi sensibili). L'harness `--production` confronta i campi estratti con la ground truth quando disponibile e riporta gli scostamenti. Partire dai 9 file di sez-contrapposte (i valori veri sono già nel report di audit, vedi 01) e dai casi storici (budget_210/211/337/343/348/395/405, LIO, Bilancino).

## Q5 — Bug scala "miliardi vs milioni" (G6 di update.md — unico pending dichiarato)

**Dove (sospetto).** `pdf_mapper.parse_italian_number` — separatori migliaia/decimali italiani su importi grandi. `update.md` righe 70-72 lo lascia aperto "ad alto rischio regressione".

**Fix proposto (a rischio controllato).**
1. Prima SOLO diagnosi: test unitario esaustivo su `parse_italian_number` con la casistica reale (`1.234.567`, `1.234.567,89`, `1 234 567`, `1.234`, `1,234` — quest'ultimo è ambiguo: 1,234 decimale vs mille), inclusi importi > 1 mld. Individuare il caso esatto che scala male.
2. Fix col vincolo: mai cambiare il risultato per input che oggi parsano correttamente (la suite del punto 1 congelata come regression).
3. Guardia di plausibilità a valle: se `totale_attivo` di una PMI supera una soglia configurabile (es. 10 mld), warning esplicito nel result — intercetta errori di scala di QUALSIASI origine.

## Q6 — `enforce_ce_sp_identity`: plug CE dichiarati all'utente

**Dove.** `iv_cee_hierarchy.py:386` — plug in `ce12_oneri_diversi`/`ce04_altri_ricavi` con flag interno `_ce_sp_plug`.

**Fix.** Il flag oggi è interno: propagarlo nel messaggio di import ("Il CE è stato allineato al risultato dello SP: +X su oneri diversi") così l'utente sa che ce12/ce04 contengono un plug e può correggerlo in Rettifiche. Nessun cambio di logica.

---

## Criterio di accettazione della fase quadratura

Dopo Q1-Q4 + i fix del file 01, sul corpus `Test/sez-contrapposte` con harness `--production`:
- 343, 348, 395, 210, 211: quadratura piena (plug < 1%) E campi sp02/sp03/sp13 == ground truth;
- 405: plug < 1% dopo gli alias di 01-N4;
- 131: attivo == 355.878,76 dopo 01-N5;
- 337, Bilancino: dichiarati onestamente non-deterministici (via LLM/vision), con ground truth verificata quando la chiave API è disponibile.
