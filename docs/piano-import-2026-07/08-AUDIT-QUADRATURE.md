# 08 — Audit quadrature end-to-end (2026-07-15)

Audit completo di DOVE avvengono le quadrature (attivo==passivo, utile CE==sp13) lungo tutte le vie di ingresso dati e il flusso infrannuale, con i fix applicati in questa sessione. Legenda: **ENFORCED** = forzata (plug/reconcile), **CHECKED** = verificata con gate/warning, **ASSENTE**.

## Mappa finale (post-fix)

| Fase | Attivo==Passivo | CE↔SP (utile==sp13) | Note |
|---|---|---|---|
| **PDF route A/B/C** (pieno e parziale) | ENFORCED (reconcile cap 5%) + CHECKED (validate_balance = hard gate, `pdf_importer.py:617`) | ENFORCED (`enforce_ce_sp_identity`) | ✅ già solido; **FIX: i warning di check_quadratura (plug/masking) ora arrivano all'UTENTE anche su route A/B** (prima solo log; `pdf_importer.py:631-647`) |
| **PDF vision/scansionati** | idem (stessa catena) | idem | verificato: nessuna scorciatoia |
| **PDF prior-year** | CHECKED debole (warning `BILANCIO NON QUADRATO [anno]`, non gate) | ENFORCED senza arbitro declared | accettato: il prior comparativo è informativo, il flag c'è |
| **XBRL** (pieno e parziale) | ~~ASSENTE~~ → **CHECKED (FIX)**: `check_quadratura` per ogni anno, warnings nel result (`xbrl_parser_enhanced.py`) | ENFORCED (già presente) | non bloccante by design (un deposito ufficiale taggato deve aprirsi; correzione in Rettifiche) |
| **CSV/TEBE** | ~~ASSENTE~~ → **CHECKED (FIX)**: `check_quadratura` entrambi gli anni, warnings nel result | ~~ASSENTE~~ → **ENFORCED (FIX)**: `enforce_ce_sp_identity` aggiunto (`csv_importer.py`) | era la via meno protetta in assoluto |
| **Rettifiche PUT /adjustments** | ~~ASSENTE~~ → **CHECKED (FIX)**: gate server-side 400 se il salvataggio PEGGIORA lo sbilancio oltre 5€ (`financial_years.py`, `_bs_imbalance`) | — (il CE non ha identità da solo qui) | merge payload-su-record → robusto a payload parziali; NON blocca record già sbilanciati all'import (lavorabili) |
| **Comparison (infrannuale)** | ASSENTE (vista read-only) | ASSENTE | accettato: trasformazione riga-per-riga, nessuna persistenza |
| **Proiezione intra_year_engine** | ENFORCED by-construction (cash plug sp09, `intra_year_engine.py:730/899`; cassa negativa → sp16) | ENFORCED (`sp13 = _net_profit_from_ce(proiezione)`, `:699/878`) | ✅ solido |
| **Promote** | ~~ASSENTE~~ → **CHECKED (FIX)**: gate `ValueError` se la proiezione ha sbilancio > 5€ (`promote_service.py`, `_forecast_bs_imbalance`) | copia verbatim (identità garantita a monte) | **doc corretta in CLAUDE.md**: promote SOSTITUISCE un full-year esistente (non fallisce) |
| **Servizi post-import** (analysis/calculation) | ASSENTE (si fidano del DB) | ASSENTE | accettato: i totali a DB sono proprietà calcolate (=Σ campi, auto-coerenti); l'ingresso è ora sempre almeno CHECKED |

## Fix applicati (questa sessione)

1. **XBRL — check quadratura per anno** (`importers/xbrl_parser_enhanced.py`): dopo `enforce_ce_sp_identity`, `check_quadratura(bs, ce)` per ogni anno; warning `[anno] BILANCIO NON QUADRATO …` nel dict di ritorno (`warnings`) e nello schema `XBRLImportResponse`. Prima un XBRL sbilanciato (anche reso tale dalla riconciliazione debiti/crediti che aggiusta sp06/sp16) entrava in silenzio.
2. **XBRL — match parziale esclude 12**: il filtro dei record parziali (`period_months.isnot(None)`) ora esclude `12` (full-year per convenzione) — prima un import parziale poteva sovrascrivere un full-year storico salvato con 12.
3. **CSV — enforce + check** (`importers/csv_importer.py`): `enforce_ce_sp_identity` (mancava del tutto) + `check_quadratura` su entrambi gli anni; `warnings` nel result e in `CSVImportResponse`.
4. **PDF A/B — flag visibili**: i warning di `check_quadratura` (es. `QUADRATURA MASCHERATA` per plug ≤5% da `reconcile_ivcee_balance`) ora entrano nei warning utente, non solo nel log (`pdf_importer.py`).
5. **PUT /adjustments — validazione server** (`backend/app/api/v1/financial_years.py`): rifiuta (400) salvataggi che peggiorano lo sbilancio oltre `ADJUSTMENTS_BALANCE_TOL` (5€ = plug frontend `reconcileSubfields`). Il confronto è "nuovo vs corrente" (mai assoluto), quindi record già sbilanciati restano lavorabili e la partita doppia del frontend passa sempre.
6. **Promote — gate quadratura** (`backend/app/services/promote_service.py`): mai promuovere una proiezione sbilanciata (>5€) a FinancialYear base per i budget. Il motore è plug-balanced, quindi scatta solo su bug a monte — ma prima sarebbe passato in silenzio.
7. **CLAUDE.md**: doc promote allineata al comportamento reale (sostituisce il full-year esistente + gate quadratura).

Test: `tests/test_quadratura_gates.py` (7 test: `_bs_imbalance`, regola adjustments, `_forecast_bs_imbalance`, gate promote via stub DB, check_quadratura sui dict import). Suite completa: 61 passed. Corpus route-C invariato (19 quadra / 13 mask / 0 err / 0 negativi).

## Lacune note ACCETTATE (documentate, non fixate — motivazione)

- **Aggregato vs sotto-campi tipizzati** (Σ sp16a..g ≠ sp16 mai verificato): i tipizzati sono additivi/display-only per design; MA `financial_debt_*`/`operating_debt_*` (`database/models.py:294-340`) usano i sotto-campi mentre `total_debt` usa gli aggregati → un cashflow può divergere dai totali SP senza flag. Fix corretto = riconciliazione al load (come frontend `reconcileSubfields`) portata a livello modello/servizio — intervento di design, da pianificare a parte.
- **Prior-year PDF senza gate né arbitro declared**: il prior è comparativo/informativo, viene flaggato (`BILANCIO NON QUADRATO [anno]`) e non alimenta i motori senza passare dal flusso pieno.
- **`totale_attivo/passivo` dichiarati non persistiti**: i totali a DB sono proprietà calcolate → il DB è auto-coerente by-construction; la fedeltà al documento è responsabilità delle validazioni d'import (ora presenti ovunque).
- **Pannello quadratura solo nel wizard infrannuale**: `/analysis` e `/report` non mostrano lo stato di quadratura dello storico. Miglioria UI possibile (badge sbilancio in `/analysis`), non un buco dati: con i fix di questa sessione nessun dato sbilanciato entra più senza warning nel result dell'import.
- **Comparison senza check**: vista pura, nessuna persistenza.

---

## Addendum — fix classe budget_337 (commit 05924ab)

Dalla domanda "perché le immateriali escono 680 e non 3.239?" sono emersi e sono stati chiusi 3 difetti:

1. **Ammortamenti CE nettati come fondi (il "680")**: il CoGe-LLM sottraeva dalle immobilizzazioni anche le QUOTE di ammortamento del Conto Economico (826003 AMMORTAMENTO SOFTWARE 340,00 + 826007 AMM.TO ALTRI ONERI PLURIENNALI 2.219,10): 3.239,12 − 2.559,10 = 680,02. Fix nel prompt (`TRIAL_BALANCE_SP_SYSTEM_PROMPT`): nettano SOLO i conti FONDO patrimoniali; il discriminatore è la SEZIONE (SP vs costi CE), robusto ai prefissi corrotti. Verificato live su 337: sp02 → 3.239,12.
2. **Ancora pareggio dal CE**: `_declared_control_totals` prendeva il "Totale a Pareggio" più GRANDE — che nelle aziende a basso margine è quello del CE (337: 372.733,17 > SP 315.121,19). Ora il pareggio si cerca solo PRIMA dell'header "CONTO ECONOMICO" (fallback full-text). Vale per tutti i file route-C, non solo per i corrotti.
3. **Text-layer corrotto ora dichiarato all'utente**: nuovo detector `_text_layer_is_garbled` (numeri spezzati attorno alla virgola; calibrato sul corpus: 337 = 60,7%, tutti gli altri < 5%) → warning "TESTO PDF CORROTTO … verificare TUTTI i valori in Rettifiche" su ogni route. Lo switch a vision è stato PROVATO e scartato (su questi layout densi la vision perde blocchi interi — non migliore del testo).

**Stato finale 337**: resta non auto-importabile in modo affidabile (input illeggibile per qualunque estrattore), ma ora (a) l'errore sistematico 680 è eliminato per la classe di file leggibili, (b) l'ancora dichiarata è giusta, (c) l'utente è avvisato esplicitamente che il file va verificato riga per riga.
