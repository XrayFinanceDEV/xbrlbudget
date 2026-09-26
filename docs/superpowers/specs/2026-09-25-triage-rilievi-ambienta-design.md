# Banco di triage dei rilievi AMBIENTA — design

**Data:** 2026-09-25 · **Branch:** `test/rilievi-ambienta` (worktree `../budget-rilievi`, da main 92c7270)
**Fonte:** `inbox/Verifica_piano_Ambienta_problemi.xlsx` (gitignorato), foglio «Elenco problemi» (30 rilievi) e
«Ricalcoli».

## 1. Perché

Un consulente ha verificato il piano AMBIENTA 2027–2029 su staging e ha aperto 30 rilievi, 21 per il software. Il
proprietario vuole sapere, per ciascuno, se è **vero**, se era **già risolto** quando il consulente guardava, o se
**non si riproduce** (previsionale vecchio o respinto a schermo, input diverso). Lo scenario esatto non esiste più:
il proprietario l'ha modificato dopo.

Questo lavoro produce **solo test e un verdetto**, nessun fix. I fix hanno un piano loro, dopo il triage.

## 2. Che cosa sappiamo già

- Il Business plan (il report citato nel foglio: sezioni 1–10, Allegati A–E) è arrivato su staging con **541d52c**
  (push 2026-09-24 13:08). Dopo, solo 92c7270 (arrotondamento delle quadrature nel report). Il consulente ha quindi
  visto il **codice** di oggi, ma forse un `ForecastYear` generato da un motore precedente: il report legge il
  previsionale persistito, non lo ricalcola.
- La verifica sul codice (2026-09-25) ipotizza che A01, A04 e B04 siano il difetto «bulk 200 su generazione
  respinta» (CLAUDE.md, Invarianti › Previsionale): a schermo resta il previsionale vecchio, il wizard mostra
  l'anteprima coi nuovi input.

## 3. Architettura del banco

- `tests/test_rilievi_ambienta.py` — pytest, un test per rilievo software (A, B, C, E05), nome `test_<ID>_<cosa>`,
  docstring con la riga del foglio. DB in memoria (`tests/e2e_kit.memory_sessions`), generazione dal percorso di
  produzione (`assumptions_service.bulk_upsert_assumptions(auto_generate=True)`), report dal percorso di produzione
  (`assemble_final_report` → `business_plan.data.from_report`).
- `frontend/lib/rilievi-ambienta.test.ts` — Vitest per i rilievi che vivono solo nel wizard (A01 lato salvataggio,
  A03 campo acconti per anno, A05 regola Manuale, A06 doppio comando), sulle funzioni pure di `lib/budget-*`.
- **Base:** `tests/fixtures/ambienta_2026.json`, l'AMBIENTA 2026 **vero** (anno 493 del DB locale) congelato una
  volta: niente bilanci inventati (regola del proprietario in `tests/test_bp_data.py`), e nessuna dipendenza dal DB
  vivo, che è già cambiato sotto altri test. Il foglio del consulente parte da un 2026 diverso (ricavi 4.209.510
  contro 4.109.510): per questo l'**oracolo si calcola dalla base con la formula del consulente**, non si copia il
  suo numero. Dove il rilievo dipende da un importo del consulente (acconto 50.000, fidi 311.000, incasso 1.000),
  quell'importo entra come input.
- **Oracolo = comportamento che il consulente si aspetta.** Test rosso ⇒ il difetto c'è. Le scelte di merito ancora
  aperte (⚖ sotto) non servono al triage: servono al fix.

## 4. I test

| ID | Input sulla base | Oracolo |
|---|---|---|
| A01 | ricavi +5/6/7, materie variabili 0/1/2 (`variable_materials_growth_auto=False`), fisso materie 0% | `ce05` 2027 = base × 1,00; 2028 = ×1,01; 2029 = ×1,02. Vitest: il salvataggio del passo Costi scrive ricavi + scostamento anche se i ricavi cambiano dopo |
| A01-bis | come A01, poi un salvataggio che il motore respinge | la risposta dice `forecast_generated: false`; il `ForecastYear` precedente non viene letto dal report senza avviso |
| A02 | servizi fissi 50%, materie variabili | costi variabili del BEP nel report = `details['pareggio']` del motore; ≠ 60% dei costi operativi |
| A03 | `tax_advances_paid` 2027 = 50.000 | acconto 2027 = 50.000 nel credito tributario. Vitest: il passo Imposte espone un campo per anno collegato a `tax_advances_paid` |
| A04 | pregresso: incasso 1.000 nel 2027 sugli altri crediti oltre 12 mesi | voce 2027 = apertura − 1.000; generazione riuscita |
| A05 | regola «Manuale» su `sp04` con i campi vuoti | `sp04` non cresce coi ricavi; nessuna uscita di cassa per investimenti finanziari. Vitest: passare a Manuale non scrive in `sp_overrides` i valori della regola precedente |
| A06 | `sp_indexing.sp16f = "personale"`, casella spenta, personale +3/4/4 | `sp16f` cresce come il personale |
| B01 | `dio_days` 22 | `ce10` di ogni anno = −Δ rimanenze materie dello SP |
| B02 | nessun investimento, poi 250.000 nel 2027 al 10% | `ce09b` limitato al residuo dei cespiti esistenti: 2029 = quota nuovi + residuo |
| B03 | retribuzioni della base | `ce08a` = `ce08b` / 13,5 (formula dichiarata dal wizard) |
| B04 | fidi + residui ≠ debito bancario di base (scarto 11.000) | `forecast_generated: false`, messaggio con lo scarto; mai un previsionale coi fidi ridotti |
| B05 | contratto pregresso con rata anche nell'anno dopo l'orizzonte | `sp16a` dell'ultimo anno comprende quella rata |
| C01 | piano con rimborsi | il report ha un DSCR con quota capitale; l'indicatore senza quota capitale non si chiama DSCR |
| C02 | base | DSO del report = clienti / ricavi × 360 |
| C03 | base | ROD = oneri finanziari / debiti finanziari |
| C04 | base con altri finanziatori | PFN del report = PFN del wizard (`budget-piano-step.ts`) |
| C05 | base | current ratio della sezione 8 = current ratio dell'Allegato E |
| C06 | base | «indice di indebitamento» = debiti / PN |
| C07 | base | copertura immobilizzazioni con il TFR fra le fonti consolidate |
| C08 | nuovo finanziamento e rimborsi nello stesso anno | rendiconto con erogazioni e rimborsi su righe separate; la sintesi cita i rimborsi del primo anno |
| C09 | base | il testo oneri finanziari/MOL parte dalla colonna base |
| E05 | investimento nel 2027; `ce18`/`ce19` nella base | registra lo stato: aliquota piena nel primo anno, straordinari ripetuti (test di caratterizzazione, non verdetto) |

⚖ Scelte del proprietario rinviate al piano dei fix: semantica di «Manuale» con campo vuoto (A05); B01 solo materie o
anche prodotti; rata oltre l'orizzonte non scadenziata (B05); PFN con o senza altri finanziatori (C04); metà
aliquota nel primo anno e straordinari nel previsionale (E05).

## 5. Verdetto

Lo stesso banco gira in due worktree staccati: **62bfed1** (staging prima dei lavori del 2026-09-24) e **92c7270**
(staging e main di oggi). Uno script, `tools/triage_rilievi.py`, legge i due report JUnit e scrive una copia del
foglio (`inbox/Verifica_piano_Ambienta_triage.xlsx`) con le colonne Stato e Note:

| 62bfed1 | 92c7270 | Stato |
|---|---|---|
| rosso | rosso | Confermato |
| rosso | verde | Risolto (2026-09-24) |
| verde | verde | Non riprodotto |
| verde | rosso | Regressione |

Un test che su 62bfed1 non si può nemmeno eseguire (API assente) vale «rosso» per quel commit, e la nota lo dice.
I test del banco restano nella suite dopo i fix: quando un rilievo si chiude, il suo test diventa verde e ci resta.
Fino ad allora i test rossi sono marcati `xfail(strict=True)` **solo dopo** il verdetto, così la suite torna verde
senza nascondere nulla: un fix che li fa passare rompe lo `strict` e obbliga a togliere il marcatore.

## 6. Fuori perimetro

Parte D (input del consulente), E01–E03 (plausibilità del piano), E04 (base IVA: diventa una nota nel piano dei
fix). Qualunque fix. La firma del motore sul `ForecastYear`, perché la domanda «guardava una versione vecchia?»
abbia risposta in futuro: va nel piano dei fix.
