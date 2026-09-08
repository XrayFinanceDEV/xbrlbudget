# Nota — i due costruttori di bilancio duplicati dell'infrannuale

**Data:** 2026-09-08 · **Stato:** da fare, in un lavoro a sé · **Chi:** il proprietario
**Origine:** emersa disegnando il lotto 2 dello scadenziamento del pregresso
(`specs/2026-09-08-scadenziamento-pregresso-design.md`, §9)

## Che cosa c'è

`calculations/intra_year_engine.py` (1808 righe) costruisce il bilancio proiettato **due
volte**, con due metodi quasi identici:

| Metodo | Riga | Usato per |
|---|---|---|
| `_project_income_statement` | 659 | CE proiettato a 12 mesi |
| `_project_income_statement_annualized` | 846 | CE annualizzato (confronto) |
| `_project_balance_sheet` | 1011 | SP proiettato |
| `_project_balance_sheet_annualized` | 1314 | SP annualizzato |

I due costruttori dello SP ripetono la stessa sequenza: circolante con
`_scaled_or_carried` (`:980-996`), debiti con `_apply_debt_repayment` (`:1551`),
posizione tributaria con `tax_closing_position`, ripartizione dei sotto-campi con
`_distribute_sp06` (`:1660`) e gemelli, plug di cassa clampato a zero con la diagnostica
`unfunded_financing_requirement`. Ogni regola nuova va scritta in entrambi, e i due
possono divergere senza che un test se ne accorga: l'infrannuale mostrerebbe un SP nel
confronto e un altro nella proiezione.

## Perché conta

- Il lotto 2 non porta lo scadenziamento del pregresso nell'infrannuale proprio per
  questo: la regola andrebbe innestata in due punti e tenuta allineata a mano.
- È lo stesso guasto già pagato sul frontend (memoria «un solo motore di proiezione»: il
  gemello TypeScript era divergito in quattro punti). Qui il gemello è dentro lo stesso
  file.

## Che cosa fare, quando si farà

1. Misurare la differenza reale fra i due costruttori (diff funzione per funzione), e
   scrivere un test di parità che, a parità di ingressi, li faccia coincidere al
   centesimo: è la rete prima di toccare.
2. Estrarre un unico costruttore parametrizzato sull'origine dei flussi (proiettato vs
   annualizzato), lasciando ai due metodi pubblici solo la preparazione degli ingressi.
3. Solo dopo, valutare se il kernel `runoff_schedule` del lotto 2 possa servire anche
   qui, con la stessa regola di compatibilità (nessun piano ⇒ formule di oggi).

Suite da tenere verdi: `tests/test_intra_year_semantics.py`,
`test_intra_year_plug_negativo.py`, `test_intra_year_end_to_end_periods.py`,
`test_infrannuale_dual_year.py`.
