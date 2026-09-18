# Imposte secondo il commercialista — Implementation Plan

> **For agentic workers:** eseguito inline dal coordinatore, senza subagenti (richiesta del
> proprietario, 2026-09-18). Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** credito da acconti compensato per intero l'anno dopo, `sp06e` del consuntivo fuori dal
meccanismo, aliquota proposta dall'ultimo consuntivo depositato e applicata come scritta, imposte
anticipate senza effetto in CE (override → riserve), riga tributaria nel rendiconto.

**Architecture:** il kernel condiviso `tax_settlement_saldo_acconto` cambia la chiusura del
credito; il motore budget separa la quota costante di `sp06e`; `_tax_components` smette di
sostituire l'aliquota; le anticipate diventano costanti e il loro override passa da `sp12e`;
il rendiconto dettagliato separa la variazione tributaria. Frontend: passo Imposte (proposta,
niente griglia), Proiezione infrannuale (aliquota proposta), rendiconto e report (riga nuova).

**Tech Stack:** Python 3.12 / SQLAlchemy / pytest; Next.js 15 / TypeScript / Vitest.

**Spec:** `docs/superpowers/specs/2026-09-18-imposte-commercialista-design.md`

## Global Constraints

- Money is `Decimal`, never float; percentages absolute (27,9 = 27,9%).
- Messaggi utente in italiano.
- `uvicorn --reload` non ricarica `calculations/`: riavviare il backend per il collaudo.
- Nessun test pinzato si aggiorna per «far tornare verde»: ogni numero che cambia si spiega con
  la regola nuova, nel commit.
- Commit solo su richiesta del proprietario; nell'albero ci sono modifiche altrui (report).

---

### Task 1: Kernel — il credito si compensa per intero

**Files:** Modify `calculations/projection_common.py` (`TaxYear`, `tax_settlement_saldo_acconto`);
Test `tests/test_tax_kernel_compensazione.py` (nuovo).

**Produces:** `TaxYear.credito_compensato: Decimal`; `opening_credit_left` sempre `0`.

- [x] Test: debito puro (saldo 1.000, acconti 800 su imposta 1.200 → debito 400, cash 1.800);
  credito compensato (opening_credit 500, saldo 0, acconti 800, imposta 600 → cash 800+0−500=300,
  credito generato 200, `opening_credit_left` 0); apertura mista (credito 300 e saldo 1.000 →
  saldo pagato 1.000, compensato 300, cash 1.000+acconti−300).
- [x] Run → FAIL. Implement: `saldo_paid = saldo_due`, `credito_compensato = opening_credit`,
  `cash_out = saldo_paid + acconti + rate_due − opening_credit`, `opening_credit_left = ZERO`.
- [x] Run → PASS.

### Task 2: Motore budget — `sp06e` del consuntivo costante, credito che non si accumula

**Files:** Modify `calculations/forecast_engine.py` (blocco `saldo_acconto` ~3860-3975, dettagli
`imposte` ~4470, `_realign_sp_declarations` ~1425); Test `tests/test_imposte_commercialista.py`.

- [x] Test (kit `tests/e2e_kit.py`, base di `test_forecast_override_tributario._base_tributi`,
  credito consuntivo 20.000): su 2027-2028 `sp06e` = 20.000 + credito generato dell'anno, mai
  più grande di 20.000 + acconti − imposta; con `tax_advances_paid` alto nel 2027 (credito 2027) il
  2028 ha `details['imposte']['credito_compensato']` = credito 2027 e `sp06e` 2028 non lo contiene.
- [x] Implement: `consuntivo = _base('sp06e_crediti_tributari_breve') * (1 + sp06e_growth)`
  (costante), `opening_credit = 0` al primo anno, `max(0, prev sp06e − consuntivo)` dopo un anno
  manuale, `prev generated_credit` dopo un anno `saldo_acconto`; `sp06e = consuntivo +
  generated_credit`; dettagli `credito_compensato`, `crediti_tributari_consuntivo`; realign:
  `generated_credit = max(0, sp06e − consuntivo)`.
- [x] Run nuovo test + `tests/test_forecast_override_tributario.py`,
  `tests/test_forecast_dichiarato_vs_persistito.py`: aggiornare i numeri pinzati spiegandoli.

### Task 3: L'aliquota scritta è quella applicata; aliquota proposta

**Files:** Modify `calculations/forecast_engine.py:_tax_components`, `calculations/projection_common.py`
(`aliquota_effettiva`); Create `backend/app/services/aliquota_service.py`; Create
`scripts/migra_imposte_commercialista.py`; Test `tests/test_aliquota_proposta.py`.

**Produces:** `aliquota_effettiva(inc) -> Optional[Decimal]` (percentuale);
`aliquota_proposta(db, company_id, base_year) -> tuple[Decimal, Optional[int]]`.

- [x] Test: con storico vero e `tax_rate` 27,9 il `ce20` previsto = pbt × 27,9% (oggi usa
  l'effettiva); `aliquota_proposta` salta un anno promosso e un parziale, ripiega su 27,9.
- [x] Implement e migrazione (dry-run di default, `--apply` per scrivere, backup consigliato).

### Task 4: Imposte anticipate costanti, override contro riserve

**Files:** Modify `calculations/forecast_engine.py` (sp06f/sp07f ~3515-3610, alloc ~4395,
`_apply_sp_overrides`); Test in `tests/test_imposte_commercialista.py`.

- [x] Test: con `tax_temporary_differences` e `sp06f_growth_pct` valorizzati `ce20` = imposta
  corrente e `sp06f` = base; override `sp06f` +5.000 → `sp12e` +5.000, cassa invariata rispetto al
  gemello.
- [x] Implement.

### Task 5: Rendiconto — riga tributaria

**Files:** Modify `backend/app/calculations/cashflow_detailed.py`,
`backend/app/schemas/cashflow_detailed.py`, `frontend/types/api.ts`, `frontend/app/cashflow/page.tsx`,
`frontend/components/report/report-cashflow.tsx`; Test `tests/test_cashflow_tributi.py`.

- [x] Test: `delta_tax` = variazione (sp16e+sp17e) − variazione (sp06e+sp07e); totale capitale
  circolante identico a prima.
- [x] Implement backend + righe frontend.

### Task 6: Frontend — passo Imposte e Proiezione infrannuale

> Eseguito con una deviazione: niente `lib/aliquota-proposta.ts`; la proposta arriva dalla rotta
> `GET …/years/{anno}/aliquota-proposta` (una sola regola, in Python). Vedi la spec §3.

**Files:** Modify `frontend/lib/budget-tax-rate.ts` (+test), `frontend/components/budget/wizard/steps/StepImposte.tsx`,
`frontend/app/budget/page.tsx` (griglia startup), `frontend/lib/budget-circolante-step.ts`
(riga `sp06f_growth_pct`), `frontend/app/pratica/page.tsx` (27,9 letterali); Create
`frontend/lib/aliquota-proposta.ts` (+test).

- [x] Test `aliquotaProposta(years, incomes, baseYear)`: salta promossi e parziali, ripiego 27,9.
- [x] `planTaxRate`: niente più «effettiva vince»; sorgenti `forzata`/`proposta`/`sostituita`.
- [x] Passo Imposte: riga «Aliquota proposta X% (bilancio AAAA)», campo aliquota precompilato,
  griglia rimossa; riga anticipate rimossa dal circolante.

### Task 7: Documentazione, suite, collaudo

- [x] CLAUDE.md (tax rate, saldo+acconto, anticipate), `docs/budget/API-PREVISIONALE.md`.
- [x] Suite Python e Vitest; `tsc`; migrazione in dry-run sul DB locale e lista scenari toccati.
