# Rilievi AMBIENTA 2027–2029, secondo giro (issue #61, #62) — design

Data: 2026-10-05. Fonte: issue GitHub #61 e #62, verificate su `main` `445e7ee`. Decisioni del
proprietario raccolte in sessione il 2026-10-05 (sotto, «Decisione»).

Ogni voce dice **che cosa cambia**, **dove**, **quali numeri si muovono sugli scenari esistenti** e
**l'accettazione**. Regola di sempre: ogni cambio di regola del motore porta la propria diagnostica in
`details`, e una chiave assente non vale «tutto regolare».

`ENGINE_VERSION` sale a `"3"`: i rilievi M1–M4 cambiano i numeri del motore.

---

## Parte M — Motore budget (`calculations/forecast_engine.py`, `projection_common.py`)

### M1 · S03 — Il DSO governa i soli crediti verso clienti

**Decisione:** i giorni si applicano ai soli clienti; le altre sotto-voci commerciali hanno una regola
propria.

- Oggi il motore calcola il commerciale a breve da DSO × ricavi / 360 e lo ripartisce con `_alloc` su
  `sp06a/b/c/d/g` (`forecast_engine.py` ~4804). Il report misura invece il DSO su `sp06a + sp07a`
  (C02). Con 90 gg in input, il report mostra ~87.
- Nuova regola: **`sp06a + sp07a` = DSO × ricavi / 360**. `sp07a` resta quello che il motore già
  calcola (crescita del lato oltre, o il piano `crediti_commerciali`), e `sp06a` è la differenza, mai
  sotto zero. Se il lato oltre supera da solo il target, `sp06a` = 0 e lo scarto si dichiara
  (`details['dso_clienti']`: `target`, `sp07a`, `sp06a`, `scarto`).
- `sp06b/c/d/g` diventano **costanti salvo la propria variazione %** (`sp06g_growth_pct` e le
  analoghe, se esistono; altrimenti costanti), come dichiara già il passo 6 (`budget-circolante-step.ts`
  :249). Questo chiude anche la seconda metà di **S27**.
- Il DSO **derivato** (non impostato) si misura dall'anno base sulla stessa base, `sp06a + sp07a`: a
  crescita zero, senza un input, i clienti non saltano.
- Col piano `crediti_commerciali` la regola «generato + residuo pregresso» resta: il generato
  dall'anno si applica alla stessa base clienti. L'interazione si fissa nel piano di esecuzione, con
  un test dedicato.
- Si muovono: gli scenari con altri crediti commerciali (`sp06b/c/d/g`) diversi da zero, perché
  prima quelle voci seguivano i ricavi e ora restano ferme. La cassa assorbe la differenza.
- Accettazione: DSO = 90 gg nel passo 4 ⇒ DSO del report 2027 = 90,0 gg (anche Indici). Il ciclo di
  conversione si ricalcola di conseguenza.

### M2 · S06 — Gli «Altri costi del personale» crescono col personale

**Decisione:** `ce08d` è un costo monetario che cresce col personale; il totale `ce08` diventa la
somma delle componenti. La regola B03 sul TFR resta (`ce08a = ce08b / 13,5`).

- Senza `ce08_override`, quando l'anno prima ha il dettaglio (`ce08b + ce08c + ce08d > 0`):
  `ce08b`, `ce08c`, `ce08d` = anno prima × (1 + `personnel_growth_pct`); `ce08a` = TFR di legge;
  **`ce08` = somma delle quattro**. Il totale non è più «anno prima × crescita»: cresce in più del
  delta del TFR, e lo si dichiara in `details['personale']` (`modo: "componenti"`, `ce08_ipotesi`,
  `ce08`, `differenza`). `personale_ricomposto` sparisce da questo ramo: non c'è più nulla da
  ricomporre.
- Senza dettaglio nell'anno prima (import per soli aggregati): come oggi. `ce08` cresce, `ce08a` è il
  TFR col ripiego del 70%, `ce08d` è il resto, e quando il resto è negativo si ricompone
  (`modo: "aggregato"`).
- Con `ce08_override` il totale vince come oggi: le componenti si scalano sul totale forzato, e se non
  ci stanno cala prima `ce08d`, poi `ce08a` (`tfr_limitato: true`). Gli override delle singole
  componenti vincono sempre.
- Si muovono: ogni scenario con il dettaglio del personale, perché il totale sale del delta del TFR
  e `ce08d` non va più a zero. AMBIENTA: `ce08d` 2027–2029 ≈ 12.236 / 12.726 / 13.235 con crescita 4%
  (Ricalcoli sez. 8).

### M3 · S29 — Accantonamento a riserva legale (art. 2430 c.c.)

**Decisione:** sì, nel motore.

- A ogni anno di piano, l'utile dell'anno prima (`previous_profit`), se positivo, va per il **5% a
  riserva legale** finché questa non raggiunge **il 20% del capitale** (`sp11`):
  `quota = min(5% × utile, max(0, 20% × sp11 − sp12c_prev))`; `sp12c = sp12c_prev + quota`;
  `sp12g = sp12g_prev + utile − quota`. Una perdita non accantona nulla.
- `sp12c` legge l'anno prima (`_prev`), non più la base. Il totale `sp12` non cambia: il movimento
  resta tutto dentro il PN, e la cassa non si muove. Diagnostica: `details['riserva_legale']`
  (`utile`, `quota`, `tetto`, `raggiunto`).
- Il motore infrannuale non si tocca: lì nessun risultato passa a riserva senza una delibera (CLAUDE.md).
- Accettazione (tester): riserva legale 2027 = 3.506 + 1.417 = 4.923.

### M4 · S14 + S18 — Compensazione del credito tributario del consuntivo, a scelta dell'utente

**Decisione:** non tutti i crediti fiscali sono incassabili o compensabili, quindi decide l'utente.
L'incasso per anno si scrive come oggi nel piano `crediti_tributari_breve` (passo 5); **del residuo
che il piano lascia, l'utente può scegliere di compensarlo con i debiti tributari generati dalle
imposte.** Nessuna riclassifica automatica a oltre 12 mesi.

- Nuova colonna: `BudgetAssumptions.compensa_crediti_tributari` (Boolean, default `False`, letta
  solo sulla riga del primo anno di piano, come `pregresso`), con la migrazione in `migrate_db.py` e
  nello schema bulk (`BudgetAssumptionsBulkRow`), poi in `frontend/types/api.ts`.
- UI: una casella nel passo 5 «Patrimoniale pregresso», accanto al piano dei crediti tributari:
  «Compensa il credito residuo con le imposte dell'anno (F24)», con una riga di spiegazione.
- Kernel (`tax_settlement_saldo_acconto`): un nuovo argomento `credito_storico_compensabile`.
  L'ordine è questo: il credito da acconti si compensa per primo, esattamente come oggi; poi il
  credito storico compensa ciò che resta di `saldo + acconti + rate`, fino a capienza.
  `TaxYear.credito_storico_compensato` lo dichiara.
- Effetto: `cash_out` e il credito storico (`crediti_tributari_consuntivo`, quindi `sp06e`) scendono
  dello **stesso importo**. Il debito d'imposta generato non cambia: gli acconti risultano versati,
  in compensazione. Col piano acceso, il residuo da compensare è quello che resta **dopo** l'incasso
  dell'anno.
- Casella spenta = comportamento di oggi, al centesimo. Nessuno scenario esistente si muove.
- Via manuale delle imposte (`sp16e_growth_pct` impostato): il kernel non gira, e la casella è
  inerte e lo dichiara (`details['imposte']['compensazione_ignorata']`), come fa già un piano
  ignorato.
- Risposta ai tester su **S14**: la compensazione «orizzontale» del credito da acconti resta, come
  da decisione del commercialista del 2026-09-18. Il debito d'imposta di fine anno è imposta − acconti
  per costruzione: gli acconti compensati sono acconti versati.

### M5 · S28 — Avviso sugli acconti sotto il minimo

- Quando `tax_advances_paid` > 0 è **inferiore sia** all'imposta dell'anno prima (metodo storico) **sia**
  all'imposta dell'anno (metodo previsionale), il motore lo dichiara:
  `details['imposte']['avviso_acconti']` = `{acconti, minimo_storico, minimo_previsionale}`.
- Il numero non si tocca: l'utente può volerlo. L'avviso si vede nell'anteprima del passo Imposte del
  wizard e nella sezione 10 del Business plan.
- Accettazione: acconti 2028 = 10.000 contro un minimo storico di 23.957 ⇒ avviso visibile.

### M6 · S18 (seconda parte) — Avviso sugli altri debiti passati da oltre a entro 12 mesi

- Quando nell'anno base la quota oltre 12 mesi degli altri debiti (`sp17g`) è **scesa** rispetto al
  bilancio che la precede (l'anno annuale prima, o il riferimento dell'infrannuale da cui il base è
  stato promosso), e il piano `altri_debiti` non la scadenzia, `details['avviso_altri_debiti_breve']`
  dichiara gli importi.
- Senza un bilancio precedente da confrontare non c'è alcun avviso: «non lo so».
- Visibile nel passo 6 e nella sezione 10 del Business plan, col suggerimento di scadenziarli al
  passo 5.

---

## Parte I — Indici (`calculations/ratios.py`, `calculations/report_indicators.py`)

### I1 · S11 — ROD sul debito finanziario medio

**Decisione:** il denominatore è la media fra inizio e fine anno; il perimetro resta quello della PFN
(banche + altri finanziatori + obbligazioni).

- `rod` = oneri finanziari / media(`financial_debt_total` di inizio e di fine anno). Sulla prima
  colonna, che non ha un inizio, si usa la fine anno con reason `rod_saldo_fine_anno`. La regola
  «`None` a perimetro zero» e la regola F1 (dettaglio mancante) restano.
- Vale in Indici e nel report, con la stessa formula in un solo punto. Si muove: il ROD di ogni
  scenario.
- Accettazione: il ROD di ogni colonna = OF / media. I numeri dei tester (5,53 / 5,61 / 4,93 / 5,00)
  escludono gli altri finanziatori a tasso 0 e qui **non** torneranno uno a uno: lo diciamo nella
  risposta all'issue.

### I2 · S20 — «Leva finanziaria» = totale attivo / patrimonio netto

- `financial_leverage_effect` diventa **totale attivo / PN**, con l'etichetta «Totale attivo /
  patrimonio netto». L'«Indice di indebitamento» resta debiti totali / PN. Nell'Allegato E i due
  indici non coincidono più.
- Accettazione (tester): leva 2026 = 11,50×.

### I3 · S22 — Indicatori del periodo infrannuale: entrambe le versioni

**Decisione:** si mostrano tutte e due.

- PFN/EBITDA e ROI del periodo parziale escono con il valore **del periodo** (come oggi) **e**
  quello **annualizzato** (flussi × 12 / mesi), con le etichette «periodo (n mesi)» e «annualizzato».
  I punti sono `report_indicators.py` :148, :178, :308, e le superfici che li rendono (report
  infrannuale, Allegato E). Gli indici di stock (PFN) non si annualizzano.
- Accettazione (tester): PFN/EBITDA 6M = 10,76× (periodo) e 5,38× (annualizzato).

---

## Parte R — Rendiconto, report e testi

### R1 · S13 — «Imposte pagate» = versamenti effettivi

- `cashflow_detailed.py:271` oggi scrive `taxes_paid = -ce20`. Sugli anni di piano col kernel
  saldo + acconto diventa **`-(saldo + acconti + rate − credito compensato − credito storico
  compensato)`**, dal motore. La riga `delta_tax` del circolante si riduce della stessa differenza, e
  la variazione di cassa non cambia.
- Il dato passa per `ForecastYear.engine_meta['imposte_versate']`. Senza (scenari pre-`"3"`, anni
  infrannuale, via manuale, colonna storica) si resta a `ce20`, come oggi. Vale su entrambe le
  pagine del rendiconto (`/analysis` e `/detailed-cashflow`), con la stessa regola di F3.
- Accettazione: rendiconto 2027, «imposte pagate» = versamenti (tester: 50.000); totale della
  variazione di cassa invariato.

### R2 · S15 — Sezione 10 «Assunzioni» completa

- Il catalogo `final_report_assumptions.py` aggiunge il **tasso del finanziamento esistente** (per
  contratto) e i **proventi finanziari**, oltre alla compensazione del credito tributario (M4).
- Le righe con valore zero non dichiarato non escono: «Rimborso debito 2027: 0» sparisce.
- Il piano di esecuzione fa prima l'inventario degli input dei passi 1–7 e verifica quali righe del
  catalogo arrivano davvero nel PDF (`sections_partenza.py`): l'accettazione è che **ogni input non
  vuoto compaia**.

### R3 · S17 — Testi automatici (`renderers/business_plan/narrative.py`)

- «deleveraging» (:160) e «rapido deleveraging» (:222) solo se scende il **debito finanziario lordo**.
  Se scende la PFN a debito lordo invariato o in crescita, il testo dice «riduzione della PFN per
  accumulo di liquidità».
- «genera cassa … sufficiente a finanziare investimenti e rimborsi» (:388) solo se il flusso
  operativo copre investimenti + rimborsi. Se la cassa regge grazie a un nuovo finanziamento, il testo
  lo nomina con l'importo.

### R4 · S24 — Base IVA dei giorni

- Una nota fissa nel passo 4 e nella sezione 10: «I giorni si applicano a ricavi e acquisti al netto
  dell'IVA; i saldi di crediti e debiti del bilancio sono al lordo. Un DSO/DPO misurato sui saldi
  storici risulta quindi più alto di quello effettivo». Nessun parametro IVA (YAGNI).

### R5 · S27 — Etichette del wizard

- Passo 4: la riga che vale `-(ccn - prevCcn)` si chiama «Cassa liberata (+) / assorbita (−) dal
  circolante» (`budget-preview-rows.ts` :291, :302). Il valore non cambia.
- Passo 6: «Altri crediti a breve» dice «Costante» ed è vero dopo M1. Va solo verificato.

### R6 · Nota di #61 — `engine_meta` NULL = da rigenerare

**Decisione:** i dati vecchi non contano e un previsionale senza firma è di sicuro anteriore al lotto
del 26/09.

- `engine_version_stale` è vero anche quando un `ForecastYear` di uno scenario **budget** ha
  `engine_meta` NULL o senza `engine_version`. L'infrannuale resta escluso, come oggi.
- Il bullet di CLAUDE.md «`engine_meta` è `NULL` … è «non lo so»» e A01-bis si aggiornano nello
  stesso commit.

---

## Fuori perimetro

- **S04, l'avviso sul DIO**: un avviso per una variazione di magazzino molto grande rispetto alla base
  resta da valutare, e non è chiesto.
- La riclassifica automatica del credito tributario a oltre 12 mesi (prima metà di S18): sostituita
  dalla compensazione a scelta (M4).

## Documentazione

CLAUDE.md: aggiornare i bullet toccati («Un solo DSO», «Indice di indebitamento», ROD, imposte a
saldo + acconto, TFR/B03, `engine_meta`), più `docs/budget/FORECASTING_GUIDE.md` e
`docs/budget/API-PREVISIONALE.md` per la nuova colonna.

## Test

Ogni voce M/I/R ha almeno un test che fallisce prima e passa dopo, sui numeri d'accettazione dove sono
riproducibili, e un test «casella spenta = identico a prima» per M4. La suite backend, Vitest e
`next build` restano verdi. La revisione finale del lotto si fa con opus (memoria
«scelta-modello-subagenti»).
