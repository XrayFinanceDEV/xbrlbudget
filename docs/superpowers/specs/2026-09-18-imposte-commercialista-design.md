# Imposte secondo il commercialista — design

Data: 2026-09-18. Approvato dal proprietario in chat lo stesso giorno.

## Il commento recepito

1. Debito IRES/IRAP = 100% delle imposte correnti dell'anno. Credito «acconti versati» = imposte
   correnti dell'anno precedente (primo anno di budget: le imposte del consuntivo). Ogni anno debito
   e credito dell'anno prima si chiudono e non si accumulano. Nello SP il netto: debito > acconti →
   debiti tributari, altrimenti crediti tributari. Il rendiconto considera debiti e crediti tributari.
2. L'aliquota non viene dall'ultimo infrannuale ma dall'ultimo consuntivo depositato.
3. Le imposte anticipate non si movimentano a conto economico: solo modifica manuale, con
   contropartita nel patrimonio netto.

## Stato di partenza (misurato sul codice)

- `projection_common.tax_settlement_saldo_acconto` fa gia' imposta 100%, acconti = imposta
  dell'anno prima (primo anno: `ce20` del consuntivo), netto in `sp16e` o `sp06e`.
- **Difetto**: il credito dell'anno N si consuma solo contro il saldo di N+1, che e' zero quando
  N chiude a credito; il resto (`opening_credit_left`) si trascina e si accumula.
- **Difetto**: nel primo anno tutto `sp06e` del consuntivo (IVA, ritenute…) e' trattato come
  credito d'imposta.
- Il rendiconto (`backend/app/calculations/cashflow_detailed.py`) include gia' `sp06e` in
  `delta_receivables` e `sp16e`/`sp17e` in `delta_payables`, senza riga propria.
- `ForecastEngine._tax_components` usa l'aliquota effettiva dell'anno base e ignora `tax_rate`
  quando l'effettiva e' derivabile; con base promossa l'effettiva e' quella della proiezione.
- La griglia delle differenze temporanee (`tax_temporary_differences`) muove le anticipate in CE;
  `sp06f_growth_pct` e la crescita di `sp07` le muovono contro cassa.

## Decisioni del proprietario

| Tema | Decisione |
|---|---|
| Credito da acconti | Compensato **per intero** l'anno dopo (anche oltre gli acconti): riduce le uscite per imposte, mai accumulo. |
| `sp06e` del consuntivo | **Fuori dal meccanismo**: resta costante per tutto il piano; il credito da acconti si somma sopra. |
| Debito tributario del consuntivo | Invariato: saldo nel primo anno (rateizzato col suo piano). |
| Aliquota | **Proposta** = effettiva dell'ultimo bilancio annuale depositato; l'utente la tiene, mette 27,9 o altro. Il motore usa sempre `tax_rate` (salvo `ce20_override`). |
| Imposte anticipate | Niente griglia, niente effetto in CE, `sp06f`/`sp07f` costanti; un override SP ha contropartita `sp12e` (altre riserve), non la cassa. |
| Rendiconto | Riga propria «Variazione debiti/crediti tributari», tolta da crediti e debiti; totale invariato. |

## Design

### 1. Kernel (`calculations/projection_common.py`)
`tax_settlement_saldo_acconto` chiude sempre la posizione di apertura: `saldo_paid = saldo_due`,
`credito_compensato = opening_credit`, `cash_out = saldo_paid + acconti + rate − credito_compensato`
(puo' essere negativo: compensazione con altri tributi), `opening_credit_left = 0` sempre. Il campo
resta nel `TaxYear` a zero per non rompere chi lo legge; si aggiunge `credito_compensato`.
L'infrannuale (`posizione_tributaria_fine_anno`) chiude gia' tutto entro il 31/12: invariato.

### 2. Motore budget (`calculations/forecast_engine.py`)
- `sp06e = crediti_tributari_consuntivo + generated_credit`, dove
  `crediti_tributari_consuntivo = base sp06e` (costante; `sp06e_growth_pct` si applica solo a
  questa parte, come oggi alla riga intera).
- Primo anno: `opening_credit = 0`. Anni dopo un anno manuale: `opening_credit =
  max(0, prev sp06e − crediti_tributari_consuntivo)`.
- `details['imposte']` dichiara `credito_compensato` e `crediti_tributari_consuntivo`;
  `_realign_sp_declarations` riallinea `generated_credit = max(0, sp06e − consuntivo)`.
- `_tax_components`: `rate = tax_rate / 100`, niente effettiva.
- Anticipate: `deferred_tax_position` non si chiama piu' (griglia ignorata); `sp06f = prev`;
  `sp07f = prev` (la crescita di `sp07` si applica solo al resto); un override su `sp06f`/`sp07f`
  sposta la differenza su `sp12e`/`sp12` invece che sulla cassa.

### 3. Aliquota proposta
- Python: `aliquota_effettiva(inc)` in `projection_common` (regola di oggi: `ce20/pbt`, scartata se
  non positiva o > 60%), `aliquota_proposta(db, company_id, base_year)` in
  `backend/app/services/aliquota_service.py`: ultimo `FinancialYear` con `period_months` NULL/12,
  `promoted_from_scenario_id` NULL, `year <= base_year`; ripiego 27,9.
- Frontend: **nessuna copia della regola** (deviazione dal primo disegno, decisa in esecuzione:
  il wizard conosce gli anni solo come numeri e non sa quali siano promossi). La proposta arriva da
  `GET /companies/{id}/years/{anno}/aliquota-proposta`, che chiama la funzione Python. Il passo
  Imposte mostra «Aliquota proposta X% (effettiva del bilancio AAAA)», «Usa la proposta» e il campo
  aliquota; uno scenario nuovo nasce con la proposta, gli anni aggiunti ereditano quella del piano.
- Infrannuale: al posto del letterale 27,9 la Proiezione invia l'aliquota proposta del consuntivo
  di riferimento.
- Migrazione una tantum (`scripts/migra_imposte_commercialista.py`): per ogni scenario budget,
  `tax_rate =` aliquota che il motore applicava (effettiva dell'anno base se derivabile) — oppure
  quella proposta se l'anno base e' promosso; azzera `tax_temporary_differences` e
  `sp06f_growth_pct`, e stampa gli scenari toccati.

### 4. Rendiconto
`WorkingCapitalChanges.delta_tax = (sp16e+sp17e)ₜ − (sp16e+sp17e)ₜ₋₁ − (sp06e+sp07e)ₜ + (sp06e+sp07e)ₜ₋₁`;
`delta_receivables` senza `sp06e`, `delta_payables` senza `sp16e/sp17e`, altre variazioni senza
`sp07e`. Totale identico. Riga nuova in `/cashflow` e nel report.

## Test
Kernel (debito, credito compensato, apertura mista); motore su tre anni con acconti > imposta
(il credito non si accumula, la cassa lo incassa); `sp06e` del consuntivo costante; `tax_rate`
applicato anche con storico; override `sp06f` → `sp12e`, cassa invariata; rendiconto con riga
tributaria e totale invariato; aliquota proposta con base promossa (TS e Python).
