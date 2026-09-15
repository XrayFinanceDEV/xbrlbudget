# Percorso ipotesi budget — giro di rilievi del 14/09 — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il wizard delle ipotesi passa ai sette passi approvati sull'artifact del 14/09 (Scenario · Fatturato · Costi · Capitale circolante · Patrimoniale pregresso · Patrimoniale piano · Imposte) e il motore impara quattro cose che quel percorso richiede: capitale rimborsato anno per anno sui contratti pregressi, fidi e anticipi separati dai mutui (con lo sweep solo su di loro), altri finanziatori scadenziati per anno, liquidazioni del TFR — più il punto di pareggio dichiarato nei `details`.

**Architecture:** Ogni intervento sul motore e' additivo e spento senza i campi nuovi: uno scenario salvato prima produce lo stesso `ForecastYear` al centesimo (banco di parita' a 0 divergenze su ogni profilo esistente). I campi nuovi vivono su `budget_assumptions` (otto colonne, due chiavi dentro JSON esistenti) e passano dallo stesso `build_assumption_row` di bulk e anteprima. Sul client ogni decisione sta in un modulo puro di `lib/` con la sua suite `environment: node`; i componenti rendono. Gli scenari gia' salvati si migrano alla prima apertura, in memoria, con una card che dichiara che cosa e' stato ricalcolato e che cosa manca.

**Tech Stack:** Python 3 + SQLAlchemy + FastAPI + Pydantic 2 (motore in `calculations/`, servizi in `backend/app/services/`), Next.js 15 + TypeScript + Vitest (`environment: node`, niente jsdom), SQLite in memoria nei test (`tests/e2e_kit.py`), banco di parita' `scripts/parita_motore.py`.

**Spec:** `docs/superpowers/specs/2026-09-15-percorso-ipotesi-rilievi-design.md` (vincolante; §4 il percorso, §5 il motore, §6 il modello dati) e il prototipo approvato `docs/superpowers/specs/2026-09-15-percorso-ipotesi-rilievi-prototipo.html` (testi a schermo, ordine delle card, stati «resta»).

**Branch di esecuzione:** `feat/percorso-ipotesi-rilievi`, staccato da `feat/report-finale-m1` (`12ecfb7`, 34 commit avanti a `main`, che li conterra' quando il proprietario unira' il report M1). I file **non committati** su quel branch (`frontend/app/budget/page.tsx`, `frontend/lib/budget-recovery*.ts`, `p2-put-assumptions.txt`) sono lavoro di un altro lotto: non si toccano, non si committano, non si stashano.

## Global Constraints

Copiati dalla spec (§2, §5) e dalle regole del repo:

- **Soldi in `Decimal`, mai `float`; percentuali assolute** (27,9 = 27,9%). Un divario si misura e si dichiara, mai si tappa.
- **I blocchi annidati dei `details` restano `Decimal`** (`debito_bancario`, `imposte`, `pareggio`, `tfr`, `altri_finanziatori`): l'anteprima converte in float solo il primo livello. Nei test si confronta con `D(str(valore)) == D("...")`. Un atteso scritto come float su un valore annidato e' un errore dell'oracolo, **mai** una ragione per convertire il motore in float (correzione del giro del Task 6).
- **Dichiarato = persistito:** ogni valore che il motore usa lo scrive nei `details`, al centesimo, e il persistito coincide.
- **Additivita':** senza i campi nuovi (`inflation_pct`, `bank_lines_amount`, `other_lenders`, `tfr_payments`, `repayments`, `non_incassato`) il motore produce numeri identici a prima. Il banco di parita' e' lo strumento di misura: ogni task del motore chiude con 0 divergenze sui profili esistenti; il caso nuovo lo esercita un profilo aggiunto nello stesso task (o nel Task 7).
- **Un solo motore di proiezione, e sta in Python:** nessun numero derivato dell'anteprima (pareggio compreso) si calcola in TypeScript; si legge dai `details`.
- **Messaggi in italiano alla fonte**, con le migliaia all'europea (`eur_it`), che nominano il passo con il nome nuovo: «Patrimoniale pregresso», «Patrimoniale piano», «Imposte».
- **Il kernel a saldo + acconto non cambia.** I debiti tributari rateizzati **passano al passo 5** e l'utente li scadenzia a mano anno per anno (decisione del proprietario, 2026-09-15; Task 13b per il passo 5, Task 16 per il passo 7 e i messaggi del motore). Il passo 7 tiene aliquota, differenze temporanee, via manuale e acconto.
- Una prova rossa vale solo se fallisce sulle **asserzioni**, non su un simbolo mancante.
- `CLAUDE.md`, `docs/budget/API-PREVISIONALE.md` e `docs/budget/FORECASTING_GUIDE.md` si aggiornano **nello stesso commit** del comportamento che descrivono; ogni `file:riga` scritto si apre e si controlla.
- **Terminatori:** file interamente CRLF da preservare: `database/models.py`, `docs/budget/FORECASTING_GUIDE.md`; file misti (si tocca solo con un editor che non normalizza, e si controlla `git diff --stat`): `backend/app/schemas/budget.py`, `frontend/types/api.ts`. Prima di toccare un file: `file <percorso>`; dopo: `git diff --stat` non deve mostrare un file intero riscritto.
- **Modelli:** sonnet su ogni task (decisione del proprietario, 2026-09-11: opus solo per escalation esplicita); pi (Orca) ammesso sui task marcati «pi ammesso». Revisione: sonnet, con opus solo sui Task 3 e 4 se la revisione sonnet trova un rilievo sul centesimo.
- **Git:** mai `git checkout`, `git stash`, `git reset --hard`, `git add -A`, `git add .`. Un commit per task, `git add` dei file per nome. Messaggio in italiano, prefisso `feat(ipotesi):`, `test(ipotesi):` o `docs(ipotesi):`.

## Convenzioni di esecuzione (ripetute dentro ogni task che le usa)

- **Radice.** Tutti i comandi partono dalla radice del worktree del task. Python sempre col percorso assoluto: `/home/peter/DEV/budget/backend/venv/bin/python`.
- **Test Python.** `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest <file> -q -p no:cacheprovider`. La suite intera: stesso comando su `tests/` (circa 1.000 test, 3-4 minuti).
- **Frontend.** Una volta per worktree: `test -e frontend/node_modules || ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules`. Poi `cd frontend && npx vitest run lib/<nome>.test.ts`, `cd frontend && npx vitest run` (suite intera, ~720 test) e `cd frontend && npx tsc --noEmit`.
- **Base del task.** Primo passo di ogni task: `git rev-parse HEAD > /tmp/rilievi-taskN-base` (N = numero del task).
- **Banco di parita'.** `/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-taskN-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-taskN-parita.json --log /tmp/rilievi-taskN-parita.log` (seconda versione omessa = albero di lavoro). Codici d'uscita: 0 nessuna divergenza, 1 divergenze, 3 controllo negativo fallito (banco da riparare: fermarsi e riferire). Nei task del motore l'atteso e' **0**: i profili esistenti non usano i campi nuovi.
- **Migrazione del DB di sviluppo.** Dopo il Task 1, chi avvia il backend su un DB esistente esegue `/home/peter/DEV/budget/backend/venv/bin/python migrate_db.py <percorso del db>` (il percorso e' il primo argomento: lo script ignora `DATABASE_PATH`) (altrimenti ogni `/analysis` risponde 500 per colonna mancante).

## Ordine e parallelismo

**Prima ondata (decisione del proprietario, 2026-09-15: «2 agenti pi e 2 sonnet in contemporanea»).** I task
del motore si separano per file e per regione, non per numero:

| Agente | Task | File di cui e' proprietario | Perche' puo' correre ora |
|---|---|---|---|
| pi A | T1 | `database/models.py`, `backend/app/schemas/budget.py` **tranne `FinancingLoanInput`**, `assumptions_service.py`, `migrate_db.py`, catalogo e schema del report (tranne `FinancingLoan`), `STEP_FIELDS`, `budget-field-rules.ts` | fondazione |
| pi B | T2 | `projection_common.py`, `FinancingLoanInput` in `schemas/budget.py`, `FinancingLoan` nel report, `assemble_financing` | kernel e schema dei contratti: nessuna colonna nuova |
| sonnet 1 | T6 | `forecast_engine.py` nelle sole regioni del pareggio, di `validate_pregresso`, di `details['pregresso']` e di `_PREGRESSO_PASSO_DEFAULT`; i due test dei messaggi | si prova dall'anteprima, che non passa dallo schema Pydantic |
| sonnet 2 | T12 | `budget-fornitori-zero.ts`, `StepCircolante.tsx` | solo client, nessun tipo nuovo |

Seconda ondata, quando T1 e T2 sono uniti: T3 (dopo T2), T5 (dopo T1), T8 (dopo T1), poi T4 dopo T3, T7 per ultimo
del motore; T9-T11 e T13-T16 come sotto.

```
Ondata A (motore):                T1 ‖ T2 ‖ T6  →  T3 ‖ T5  →  T4  →  T7
Ondata B (interfaccia):           T12 (subito) · T8 → T9 → T10 ‖ T11   (in parallelo dopo T9)
                                  T13 → T14   ‖   T15          (T13-14 in serie; T15 in parallelo dopo T8)
                                  T16 (dopo T10-T15)
Ondata C (da sola):               T17 (verifica di lotto)
```

| # | Task | Modello |
|---|---|---|
| 1 | Schema, modello, migrazione, `build_assumption_row`, catalogo del report | sonnet (pi ammesso) |
| 2 | Kernel `repayments` sui contratti pregressi | sonnet |
| 3 | Fidi e anticipi: regime esplicito, sweep, quota a breve, oneri | sonnet (revisione opus se serve) |
| 4 | Altri finanziatori per anno (`other_lenders`) | sonnet (revisione opus se serve) |
| 5 | Liquidazioni TFR (`tfr_payments`) | sonnet (pi ammesso) |
| 6 | `details['pareggio']`, `non_incassato`, nomi dei passi nei messaggi | sonnet (pi ammesso) |
| 7 | Profili nuovi del banco di parita' e giro completo | sonnet (pi ammesso) |
| 8 | Tipi, idratazione, passi, regole di campo, catalogo e fixture del report | sonnet |
| 9 | Migrazione degli scenari salvati (`budget-migrazione.ts`), card e badge | sonnet |
| 10 | Passi 1 e 2: inflazione salvata, niente seme, write-through sui variabili | sonnet (pi ammesso) |
| 11 | Passo 3 Costi: tabella nuova, pareggio, CE fino all'ante imposte | sonnet |
| 12 | Passo 4: avviso fornitori a zero, voci minori via | sonnet (pi ammesso) |
| 13 | Passo 5 (I): a breve, oltre 12 mesi, «Scadenziamento pregresso» | sonnet |
| 14 | Passo 5 (II): debiti verso banche, altri finanziatori | sonnet |
| 15 | Passo 6 Patrimoniale piano | sonnet |
| 16 | Passo 7, wizard, rail, documentazione utente | sonnet (pi ammesso) |
| 17 | Verifica di fine lotto | sonnet + collaudatore |

---

## Ondata A — motore

### Task 1: Schema, modello, migrazione, `build_assumption_row`, catalogo del report

**Files:**
- Modify: `database/models.py:656-665` (CRLF: preservare) — otto colonne nuove
- Modify: `backend/app/schemas/budget.py:203-235` (misto CRLF/LF) — `OtherLenderInput` (subito DOPO `TemporaryDifferenceInput`, mai accanto a `FinancingLoanInput`), `PregressoPlanInput.non_incassato`, otto campi su `BudgetAssumptionsBase`, otto su `BudgetAssumptionsUpdate`. **`FinancingLoanInput` non si tocca: e' del Task 2**, che corre in parallelo.
- Modify: `backend/app/services/assumptions_service.py:124-145` (`_senza_null`) e `:203-318` (`build_assumption_row`)
- Modify: `migrate_db.py:100-135` — otto `ALTER TABLE`
- Modify: `contracts/final_report_assumption_sections.json` — i campi scalari nuovi nelle sezioni di oggi (le chiavi si rinominano al Task 8)
- Modify: `backend/app/services/final_report_assumptions.py:111-113` e `FIELD_LABELS` — `other_lenders` nidificato, etichette
- Modify: `backend/app/schemas/final_report.py:310-400` — `OtherLender`, `AssumptionValue.other_lenders`, `RunoffPlan.non_incassato` (non `FinancingLoan`: Task 2)
- Modify: `frontend/lib/budget-wizard-steps.ts:23-50` — i campi nuovi in `STEP_FIELDS` delle sezioni di oggi (solo per la parita' del catalogo; il rinomina e' al Task 8)
- Test: `tests/test_ipotesi_schema_rilievi.py` (nuovo), `tests/test_m1_05b_assumption_sections.py`, `tests/test_final_report_contract.py`

**Interfaces:**
- Produces: colonne `BudgetAssumptions.inflation_pct`, `fixed_materials_growth_auto`, `fixed_services_growth_auto`, `bank_lines_amount`, `bank_lines_rule`, `bank_lines_rate`, `other_lenders`, `tfr_payments`; `OtherLenderInput(name, opening_residual, interest_rate, repayments)`; `PregressoPlanInput.non_incassato: bool`. Ogni task successivo li legge con `getattr(assumption, ...)`.

- [ ] **Step 1: Base del task e terminatori**

```bash
git rev-parse HEAD > /tmp/rilievi-task1-base
file database/models.py backend/app/schemas/budget.py
```
Atteso: `models.py` «with CRLF line terminators»; `budget.py` «with CRLF, LF line terminators». Ogni modifica a questi due file va fatta preservando i terminatori delle righe vicine (l'editor non deve normalizzare; a fine task `git diff --stat` mostra poche decine di righe, non il file intero).

- [ ] **Step 2: Scrivere il test rosso dello schema**

`tests/test_ipotesi_schema_rilievi.py`:

```python
"""Le otto colonne e le due chiavi JSON del giro di rilievi del 14/09 (spec 2026-09-15 §6).

Tutto additivo: una riga costruita da `build_assumption_row` con un dict di prima ha i default
di colonna (NULL, 0, False), e lo schema del bulk accetta e valida i campi nuovi.
"""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.schemas.budget import (
    BudgetAssumptionsBulkRow, OtherLenderInput, PregressoPlanInput,
)
from backend.app.services.assumptions_service import build_assumption_row
from database.models import BudgetAssumptions

COLONNE = {
    "inflation_pct": None, "fixed_materials_growth_auto": False, "fixed_services_growth_auto": False,
    "bank_lines_amount": None, "bank_lines_rule": None, "bank_lines_rate": None,
    "other_lenders": None, "tfr_payments": Decimal("0"),
}


def test_le_otto_colonne_esistono_con_i_default_di_prima():
    nomi = {c.name for c in BudgetAssumptions.__table__.columns}
    assert set(COLONNE) <= nomi
    riga = build_assumption_row(1, {"forecast_year": 2027, "revenue_growth_pct": 3})
    for colonna, atteso in COLONNE.items():
        assert getattr(riga, colonna) == atteso, colonna


def test_build_assumption_row_porta_i_campi_nuovi():
    riga = build_assumption_row(1, {
        "forecast_year": 2027, "inflation_pct": 2.5, "fixed_materials_growth_auto": True,
        "bank_lines_amount": 90000, "bank_lines_rule": "ricavi", "bank_lines_rate": 5,
        "other_lenders": [{"name": "Soci", "opening_residual": 150000, "interest_rate": 0, "repayments": [0, 50000]}],
        "tfr_payments": 50000,
    })
    assert riga.inflation_pct == Decimal("2.5")
    assert riga.fixed_materials_growth_auto is True
    assert riga.bank_lines_amount == Decimal("90000")
    assert riga.bank_lines_rule == "ricavi"
    assert riga.other_lenders[0]["repayments"] == [0, 50000]
    assert riga.tfr_payments == Decimal("50000")


def test_other_lender_e_non_incassato():
    o = OtherLenderInput(name="Finanziamento soci", opening_residual=150000, repayments=[])
    assert o.interest_rate == Decimal("0")
    with pytest.raises(ValidationError, match="supera il residuo"):
        OtherLenderInput(opening_residual=10, repayments=[11])
    p = PregressoPlanInput(opening=30000, amounts=[0, 0], non_incassato=True)
    assert p.non_incassato is True
    riga = BudgetAssumptionsBulkRow(forecast_year=2027, bank_lines_rule="costante", tfr_payments=0)
    assert riga.bank_lines_rule == "costante"
    with pytest.raises(ValidationError):
        BudgetAssumptionsBulkRow(forecast_year=2027, bank_lines_rule="altro")
```

- [ ] **Step 3: Eseguire il test e vederlo fallire sulle asserzioni**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_ipotesi_schema_rilievi.py -q -p no:cacheprovider
```
Atteso: `ImportError` su `OtherLenderInput` (simbolo mancante: va bene come primo rosso, ma il rosso che conta e' quello del passo 5 sulle asserzioni dei default).

- [ ] **Step 4: Modello ORM**

In `database/models.py`, subito dopo `previdenza_scales_with_personnel` (riga 664), preservando i CRLF:

```python
    # ── Giro di rilievi del 14/09 (spec 2026-09-15 §6): tutto additivo ──
    inflation_pct = Column(Numeric(10, 6), nullable=True)  # inflazione attesa del passo 1; NULL = scenario precedente
    fixed_materials_growth_auto = Column(Boolean, default=False, nullable=False)  # la parte fissa segue l'inflazione
    fixed_services_growth_auto = Column(Boolean, default=False, nullable=False)
    bank_lines_amount = Column(Numeric(15, 2), nullable=True)  # fidi e anticipi su fatture (prima riga); NULL = regime di prima
    bank_lines_rule = Column(String(16), nullable=True)        # 'costante' | 'ricavi'
    bank_lines_rate = Column(Numeric(10, 6), nullable=True)    # tasso % su fidi e scoperto
    other_lenders = Column(JSON, nullable=True)                 # altri finanziatori per anno (prima riga)
    tfr_payments = Column(Numeric(15, 2), default=0, nullable=False)  # liquidazioni TFR dell'anno
```
`String` e' gia' importato in `models.py` (controllare l'import in testa; altrimenti aggiungerlo alla riga `from sqlalchemy import ...`).

- [ ] **Step 5: Schemi Pydantic**

In `backend/app/schemas/budget.py`, subito DOPO la classe `TemporaryDifferenceInput` (non accanto a `FinancingLoanInput`, che il Task 2 modifica in parallelo: hunk adiacenti diventano un conflitto):

```python
class OtherLenderInput(BaseModel):
    """Un altro finanziatore (sp16b/sp17b) scadenziato per anno: spesso un finanziamento soci."""
    name: Optional[str] = Field(default=None, max_length=100)
    opening_residual: Decimal = Field(..., gt=0)
    interest_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    repayments: List[Decimal] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lender(self):
        if any(r < 0 for r in self.repayments):
            raise ValueError("un rimborso per anno è negativo")
        if sum(self.repayments, Decimal("0")) - self.opening_residual > Decimal("0.01"):
            raise ValueError("la somma dei rimborsi per anno supera il residuo iniziale")
        return self
```

In `PregressoPlanInput` aggiungere `non_incassato: bool = False  # solo crediti_commerciali: dichiarati non incassati nel piano`.

In `BudgetAssumptionsBase`, dopo `previdenza_scales_with_personnel` (riga 240 circa):

```python
    # ── Giro di rilievi del 14/09 (spec 2026-09-15 §6) ──
    inflation_pct: Optional[Decimal] = Field(default=None, ge=-50, le=100)
    fixed_materials_growth_auto: bool = False
    fixed_services_growth_auto: bool = False
    bank_lines_amount: Optional[Decimal] = Field(default=None, ge=0)
    bank_lines_rule: Optional[Literal["costante", "ricavi"]] = None
    bank_lines_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    other_lenders: Optional[List[OtherLenderInput]] = None
    tfr_payments: Decimal = Field(default=Decimal("0"), ge=0)
```
e gli stessi otto campi, tutti `Optional[...] = None`, in `BudgetAssumptionsUpdate` (riga 406 in poi). `Literal` e' gia' importato (lo usa `SpIndexingDriver`).

- [ ] **Step 6: Servizio delle ipotesi**

In `assumptions_service._senza_null` (riga 127) la tupla diventa `("financing_loans", "tax_temporary_differences", "other_lenders")`. In `build_assumption_row`, dopo `previdenza_scales_with_personnel=...`:

```python
        inflation_pct=data.get("inflation_pct", None),
        fixed_materials_growth_auto=data.get("fixed_materials_growth_auto", False) or False,
        fixed_services_growth_auto=data.get("fixed_services_growth_auto", False) or False,
        bank_lines_amount=data.get("bank_lines_amount", None),
        bank_lines_rule=data.get("bank_lines_rule", None),
        bank_lines_rate=data.get("bank_lines_rate", None),
        other_lenders=jsonable_encoder(data.get("other_lenders", None)),
        tfr_payments=data.get("tfr_payments", 0.0) or 0.0,
```
Controllare `_normalize_numeric_fields` (riga 36): se quantizza per elenco di colonne, aggiungere `inflation_pct`, `bank_lines_amount`, `bank_lines_rate`, `tfr_payments` all'elenco; se itera sulle colonne `Numeric` del modello, non serve nulla.

- [ ] **Step 7: Migrazione**

In `migrate_db.py`, in coda alla lista `"budget_assumptions"`:

```python
        # Giro di rilievi del 14/09 (spec 2026-09-15 §6): additive, NULL/0 = comportamento di prima.
        ("inflation_pct",                      "NUMERIC(10,6)"),
        ("fixed_materials_growth_auto",        "BOOLEAN DEFAULT 0 NOT NULL"),
        ("fixed_services_growth_auto",         "BOOLEAN DEFAULT 0 NOT NULL"),
        ("bank_lines_amount",                  "NUMERIC(15,2)"),
        ("bank_lines_rule",                    "VARCHAR(16)"),
        ("bank_lines_rate",                    "NUMERIC(10,6)"),
        ("other_lenders",                      "TEXT"),
        ("tfr_payments",                       "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
```
Prova su una copia: `cp /home/peter/DEV/budget/financial_analysis.db /tmp/rilievi-task1.db && /home/peter/DEV/budget/backend/venv/bin/python migrate_db.py /tmp/rilievi-task1.db` → otto righe `ADD budget_assumptions.<colonna>`; una seconda esecuzione le salta tutte.

- [ ] **Step 8: Catalogo del report (parita' dei campi morti)**

In `contracts/final_report_assumption_sections.json`: in `scenario` → `"fields": ["inflation_pct"]`; in `costi` aggiungere `"fixed_materials_growth_auto", "fixed_services_growth_auto"` in coda; in `pregresso-nuovo` aggiungere `"bank_lines_amount", "bank_lines_rule", "bank_lines_rate", "tfr_payments"` in coda ai `fields` e `"other_lenders"` ai `nested_fields`. Le stesse aggiunte, nello stesso ordine, in `STEP_FIELDS` di `frontend/lib/budget-wizard-steps.ts` (`scenario: ["inflation_pct"]`, ecc.): `tests/test_final_report_contract.py::test_assumption_catalog_is_exactly_the_current_wizard_without_dead_fields` confronta i due elenchi campo per campo. In quel test aggiornare l'insieme atteso dei `nested_fields` a `{"ce_overrides", "sp_indexing", "sp_overrides", "pregresso", "other_lenders"}`.

In `backend/app/services/final_report_assumptions.py`: `_PRESENCE_NESTED_FIELDS` include `"other_lenders"`; in `_nested_assumption` il builder `"other_lenders": _other_lenders`; nuova funzione accanto a `_financing_loans` (riga 413), stessa forma, che valida con `OtherLenderInput.model_validate(item)` e produce `OtherLender(name=..., opening_residual=..., interest_rate=..., repayments=[...])`; in `FIELD_LABELS`: `"inflation_pct": "Inflazione attesa %"`, `"fixed_materials_growth_auto": "Materie fissa: segue l'inflazione"`, `"fixed_services_growth_auto": "Servizi fissa: segue l'inflazione"`, `"bank_lines_amount": "Fidi e anticipi su fatture"`, `"bank_lines_rule": "Fidi: regola nel piano"`, `"bank_lines_rate": "Tasso fidi e scoperto %"`, `"other_lenders": "Altri finanziatori"`, `"tfr_payments": "Liquidazioni TFR"`. `_BOOLEAN_ASSUMPTION_FIELDS` in `schemas/final_report.py` (riga 84) include i due `*_growth_auto`; `bank_lines_rule` e' una stringa: `AssumptionScalar` deve ammetterla (controllare il tipo a riga ~290: se e' `Optional[PlainDecimal | bool]`, aggiungere `str` e nel validatore `nested_value_has_a_known_field` ammettere `str` per il solo campo `bank_lines_rule`).

In `backend/app/schemas/final_report.py` (NON la classe `FinancingLoan`, che e' del Task 2): nuova `class OtherLender(ContractModel): name: Optional[str] = None; opening_residual: PlainDecimal; interest_rate: PlainDecimal; repayments: list[PlainDecimal]`; `RunoffPlan.non_incassato: Optional[bool] = None`; `AssumptionValue.other_lenders: Optional[list[OtherLender]] = None`, contato in `nested` e con il vincolo «`other_lenders` data is only valid for the other_lenders field».

- [ ] **Step 9: Verde su schema, report e suite**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_ipotesi_schema_rilievi.py tests/test_m1_05b_assumption_sections.py tests/test_final_report_contract.py tests/test_forecast_preview.py -q -p no:cacheprovider
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/ -q -p no:cacheprovider
cd frontend && npx vitest run lib/budget-wizard-steps.test.ts lib/budget-field-rules.test.ts && npx tsc --noEmit
```
Atteso: tutto verde. Se `budget-field-rules.test.ts` chiede una regola per ogni campo di `STEP_FIELDS`, aggiungere in `frontend/lib/budget-field-rules.ts` (`RULES`): `inflation_pct: pct({ min: -50, max: 100, nullable: true })`, `fixed_materials_growth_auto: bool`, `fixed_services_growth_auto: bool`, `bank_lines_amount: eur({ nullable: true })`, `bank_lines_rate: pct({ min: 0, max: 30, nullable: true })`, `tfr_payments: eur()`; `bank_lines_rule` e `other_lenders` non sono scalari: se il test li pretende, escluderli come oggi si escludono `financing_loans` e `pregresso` (leggere il test e seguire la stessa esclusione).

- [ ] **Step 10: Banco di parita' e commit**

```bash
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-task1-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-task1-parita.json --log /tmp/rilievi-task1-parita.log
git diff --stat
git add database/models.py backend/app/schemas/budget.py backend/app/services/assumptions_service.py migrate_db.py contracts/final_report_assumption_sections.json backend/app/services/final_report_assumptions.py backend/app/schemas/final_report.py frontend/lib/budget-wizard-steps.ts frontend/lib/budget-field-rules.ts tests/test_ipotesi_schema_rilievi.py tests/test_final_report_contract.py
git commit -m "feat(ipotesi): otto colonne e due chiavi JSON del giro di rilievi, tutte additive"
```
Atteso: banco a 0 divergenze; `git diff --stat` senza file interi riscritti.

---

### Task 2: Kernel `repayments` sui contratti pregressi

**Files:**
- Modify: `backend/app/schemas/budget.py:184-201` (misto CRLF/LF: preservare) — la sola classe `FinancingLoanInput` (il Task 1, in parallelo, aggiunge `OtherLenderInput` dopo `TemporaryDifferenceInput` e i campi della riga: non toccarli)
- Modify: `backend/app/schemas/final_report.py:300-308` — la sola classe `FinancingLoan` (il Task 1 tocca altre classi dello stesso file); `backend/app/services/final_report_assumptions.py:413` (`_financing_loans`)
- Modify: `calculations/projection_common.py:185-232` (`new_financing_schedule`), `:437-462` (`contratti_da_riga_finanziamento`)
- Modify: `calculations/forecast_engine.py:2059-2108` (`assemble_financing`: durata facoltativa)
- Test: `tests/test_forecast_contratti_per_anno.py` (nuovo)
- Docs: `docs/budget/API-PREVISIONALE.md` §4-bis

**Interfaces:**
- Consumes: nulla dei task in corso (corre in parallelo al Task 1)
- Produces: un contratto del kernel con chiave `'repayments': List[Decimal]` e `'year'` = primo anno di piano; `new_financing_schedule(loans, target_year)` lo rimborsa di `repayments[target_year - year]` (zero oltre la lista, mai oltre il residuo), interessi = tasso × residuo di apertura. `contratti_da_riga_finanziamento` accetta `duration_years` assente quando `repayments` c'e'.

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task2-base
```

- [ ] **Step 2: Test rosso**

`tests/test_forecast_contratti_per_anno.py`:

```python
"""Capitale rimborsato anno per anno sui contratti pregressi (spec 2026-09-15 §5.1).

Oracolo a mano: residuo 330.000 al 3,8%, rimborsi [82.500, 82.500, 0] su 3 anni. Residuo di fine
anno 247.500 · 165.000 · 165.000 (oltre la lista non si rimborsa: il debito resta aperto, decisione
7). Interessi sul residuo di apertura: 12.540,00 · 9.405,00 · 6.270,00.
"""
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from backend.app.schemas.budget import FinancingLoanInput
from backend.app.services import assumptions_service, forecast_preview_service
from calculations.projection_common import contratti_da_riga_finanziamento, new_financing_schedule
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP16A, SP17A = "sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo"
CE15 = "ce15_oneri_finanziari"


def test_schema_repayments_solo_sul_pregresso_e_mai_oltre_il_residuo():
    ok = FinancingLoanInput(name="Mutuo", opening_residual=330000, interest_rate=3.8, repayments=[82500, 82500])
    assert ok.duration_years is None and ok.repayments == [D("82500"), D("82500")]
    with pytest.raises(ValidationError, match="supera il residuo"):
        FinancingLoanInput(opening_residual=100, repayments=[60, 60])
    with pytest.raises(ValidationError, match="negativo"):
        FinancingLoanInput(opening_residual=100, repayments=[-1])
    with pytest.raises(ValidationError, match="prestito nuovo"):
        FinancingLoanInput(amount=100, repayments=[50])
    with pytest.raises(ValidationError, match="durata"):
        FinancingLoanInput(amount=100)  # senza repayments la durata resta obbligatoria
    classico = FinancingLoanInput(amount=100, duration_years=4)
    assert classico.repayments is None and classico.duration_years == 4


def test_kernel_rimborsa_la_lista_e_poi_lascia_aperto():
    loan = {"year": 2027, "amount": D("0"), "opening_residual": D("330000"), "rate": D("0.038"),
            "repayments": [D("82500"), D("82500"), D("0")]}
    assert new_financing_schedule([loan], 2027) == (D("0"), D("82500"), D("12540.000"))
    assert new_financing_schedule([loan], 2028) == (D("0"), D("82500"), D("9405.000"))
    assert new_financing_schedule([loan], 2029) == (D("0"), D("0"), D("6270.000"))
    assert new_financing_schedule([loan], 2031) == (D("0"), D("0"), D("6270.000"))


def test_kernel_non_rimborsa_oltre_il_residuo():
    loan = {"year": 2027, "amount": D("0"), "opening_residual": D("100"), "rate": D("0"),
            "repayments": [D("60"), D("60")]}
    assert new_financing_schedule([loan], 2028)[1] == D("40")


def test_contratti_da_riga_porta_repayments_senza_durata():
    riga = {"opening_residual": 330000, "interest_rate": 3.8, "repayments": [82500, 82500]}
    (c,) = contratti_da_riga_finanziamento(riga, 2027)
    assert c["repayments"] == [D("82500"), D("82500")] and c["opening_residual"] == D("330000")
    assert c["year"] == 2027


def _genera(user, rows, breve, lungo):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            delta_lungo = lungo - b.sp17a_debiti_banche_lungo
            b.sp16a_debiti_banche_breve = breve; b.sp16_debiti_breve += breve
            b.sp17a_debiti_banche_lungo = lungo; b.sp17_debiti_lungo += delta_lungo
            b.sp09_disponibilita_liquide += breve + delta_lungo
            db.commit()
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            anni = {anno: (sp, ce) for anno, sp, ce in read_forecast_maps(db, sc.id)} if res["forecast_generated"] else {}
            return res, anni, prev
    finally:
        engine.dispose()


def test_il_previsionale_persiste_i_residui_della_lista():
    contratto = {"name": "Mutuo", "opening_residual": 330000, "interest_rate": 3.8, "repayments": [82500, 82500, 0]}
    rows = [{"forecast_year": 2027, "tax_rate": 27.9, "financing_loans": [contratto]},
            {"forecast_year": 2028, "tax_rate": 27.9}, {"forecast_year": 2029, "tax_rate": 27.9}]
    res, anni, prev = _genera("contratti-anno", rows, breve=D("82500"), lungo=D("247500"))
    assert res["forecast_generated"] is True, res["message"]
    assert [anni[a][0][SP16A] + anni[a][0][SP17A] for a in (2027, 2028, 2029)] == [D("247500.00"), D("165000.00"), D("165000.00")]
    assert [anni[a][1][CE15] for a in (2027, 2028, 2029)] == [D("12540.00"), D("9405.00"), D("6270.00")]
    contratti = prev["forecast_years"][0]["details"]["debito_bancario"]["contratti"]
    # i blocchi annidati dei details restano Decimal: si confronta con D (regola del lotto)
    assert D(str(contratti[0]["rimborso"])) == D("82500.00") and D(str(contratti[0]["interessi"])) == D("12540.00")
```

- [ ] **Step 3: Rosso sulle asserzioni**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_contratti_per_anno.py -q -p no:cacheprovider
```
Atteso: i test del kernel falliscono perche' `duration` manca (`continue` nel kernel → `(0, 0, 0)`); il test del previsionale fallisce con «gli anni di preammortamento…» o residuo fermo a 330.000.

- [ ] **Step 4: Schema dei contratti**

In `backend/app/schemas/budget.py` sostituire la sola classe `FinancingLoanInput` (righe 184-201), preservando i terminatori delle righe vicine, con:

```python
class FinancingLoanInput(BaseModel):
    """Financing contract raised or already outstanding in the parent year.

    Due modi di descrivere il rimborso: `duration_years` (+ `grace_years`, `balloon_pct`) per un
    prestito nuovo, oppure `repayments` — il capitale rimborsato in ciascun anno di piano, indice
    0 = primo anno — per un contratto PREGRESSO (`opening_residual` > 0, `amount` = 0). Oltre la
    lista il residuo resta aperto (spec 2026-09-15 §5.1, decisione 7).
    """
    name: Optional[str] = Field(default=None, max_length=100)
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    opening_residual: Decimal = Field(default=Decimal("0"), ge=0)
    duration_years: Optional[int] = Field(default=None, gt=0, le=50)
    interest_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    grace_years: int = Field(default=0, ge=0, le=49)
    balloon_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    repayments: Optional[List[Decimal]] = None

    @model_validator(mode="after")
    def validate_contract(self):
        if self.amount == 0 and self.opening_residual == 0:
            raise ValueError("l'importo o il residuo iniziale devono essere maggiori di zero")
        if self.repayments is None:
            if self.duration_years is None:
                raise ValueError("la durata in anni è obbligatoria senza i rimborsi per anno")
            if self.grace_years >= self.duration_years:
                raise ValueError("gli anni di preammortamento devono essere meno della durata")
            return self
        if self.amount > 0:
            raise ValueError("i rimborsi per anno valgono solo sul residuo pregresso, non su un prestito nuovo")
        if self.grace_years or self.balloon_pct:
            raise ValueError("con i rimborsi per anno non si usano preammortamento e maxirata")
        if any(r < 0 for r in self.repayments):
            raise ValueError("un rimborso per anno è negativo")
        if sum(self.repayments, Decimal("0")) - self.opening_residual > Decimal("0.01"):
            raise ValueError("la somma dei rimborsi per anno supera il residuo iniziale")
        return self
```
In `backend/app/schemas/final_report.py` (classe `FinancingLoan`, riga 300): `duration_years: Optional[StrictInt] = Field(default=None, gt=0)` e `repayments: Optional[list[PlainDecimal]] = None`. In `backend/app/services/final_report_assumptions.py`, `_financing_loans` (riga 413) passa `repayments=parsed.repayments` quando costruisce `FinancingLoan`.

- [ ] **Step 4b: Kernel**

In `projection_common.new_financing_schedule`, dopo il calcolo di `principal`/`rate` e PRIMA del `duration = int(...)`:

```python
        repayments = loan.get('repayments')
        if repayments is not None:
            # Contratto pregresso scadenziato a mano (spec 2026-09-15 §5.1): il capitale
            # dell'anno e' la voce della lista (zero oltre la lista: il residuo resta
            # aperto), mai oltre il residuo di apertura; interessi sul residuo di apertura.
            if principal <= ZERO:
                continue
            elapsed = target_year - raise_year
            if elapsed < 0:
                continue
            piano = [Decimal(str(r or 0)) for r in repayments]
            opening = max(ZERO, principal - sum(piano[:elapsed], ZERO))
            quota = piano[elapsed] if elapsed < len(piano) else ZERO
            repayment += min(opening, quota)
            interest += opening * rate
            continue
```
In `contratti_da_riga_finanziamento`: `durata` puo' essere `None`; il ritorno `[]` su durata nulla vale solo quando `repayments` e' assente:

```python
    repayments = loan.get('repayments')
    if repayments is None and durata <= ZERO:
        return []
    condizioni = {
        'year': anno,
        'duration': durata,
        'rate': ...,
        'grace_years': ...,
        'balloon_pct': ...,
    }
    if repayments is not None:
        condizioni['repayments'] = [Decimal(str(r or 0)) for r in repayments]
```
(`durata = Decimal(str(loan.get('duration_years') or 0))` resta com'e': `None` → 0.)

Aggiornare la docstring di `new_financing_schedule` con il paragrafo sui `repayments`. Nel motore, `_residuo_contratto` (riga 317) e `_contratti_dell_anno` usano `new_financing_schedule([loan], anno)`: funzionano senza modifiche. Verificare che `assemble_financing` non legga `duration_years` altrove (grep `duration` in `forecast_engine.py` righe 2059-2108).

- [ ] **Step 5: Verde, parita', suite**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_contratti_per_anno.py tests/test_final_report_contract.py tests/test_m1_05b_assumption_sections.py tests/test_forecast_finanziamento_pregresso.py tests/test_forecast_prestito_quota_breve.py tests/test_forecast_sweep_piani.py tests/test_vseg_financing_split.py -q -p no:cacheprovider
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-task2-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-task2-parita.json --log /tmp/rilievi-task2-parita.log
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
Atteso: verde; banco 0 divergenze. Se il previsionale del test rifiuta con «La somma dei residui iniziali … deve coincidere con il debito bancario»: il kit ha `sp17a` 50.000 sostituiti da `_genera` con 82.500 + 247.500 = 330.000, che coincide; controllare `_genera`.

- [ ] **Step 6: Documentazione e commit**

In `docs/budget/API-PREVISIONALE.md` §4-bis, dopo la frase sul contratto misto (riga ~394), un paragrafo: «**Capitale per anno.** Una riga di `financing_loans[]` con `opening_residual` puo' portare `repayments` — un importo per anno di piano, indice 0 = primo anno — al posto della durata: e' il capitale rimborsato in quell'anno, mai oltre il residuo; oltre la lista non si rimborsa nulla e il residuo resta in bilancio a fine piano. Interessi sul residuo di apertura, come per ogni contratto. `repayments` vale solo sul pregresso (`amount` = 0), senza preammortamento ne' maxirata; la somma non puo' superare il residuo (422 dal bulk).»

```bash
git add backend/app/schemas/budget.py backend/app/schemas/final_report.py backend/app/services/final_report_assumptions.py calculations/projection_common.py calculations/forecast_engine.py tests/test_forecast_contratti_per_anno.py docs/budget/API-PREVISIONALE.md
git commit -m "feat(ipotesi): capitale rimborsato anno per anno sui contratti pregressi"
```

---

### Task 3: Fidi e anticipi: regime esplicito, sweep, quota a breve, oneri

**Files:**
- Modify: `calculations/forecast_engine.py:2059-2108` (`assemble_financing`), `:2761-2800` (oneri in `_calculate_income_statement`), `:3266-3330` e `:3700-3810` (`_calculate_balance_sheet`: apertura, sweep, ricomposizione), `:385-436` (`_dichiara_debito_bancario`: la riga `fidi`), `:2320` (dichiarazione)
- Test: `tests/test_forecast_fidi.py` (nuovo)
- Docs: `docs/budget/API-PREVISIONALE.md` §4-ter, `CLAUDE.md` «Forecasting Engine» (paragrafo sullo sweep)

**Interfaces:**
- Consumes: `assumption.bank_lines_amount`, `bank_lines_rule`, `bank_lines_rate` (Task 1), contratti con `repayments` (Task 2)
- Produces: `details['debito_bancario']['fidi'] = {apertura, variazione_ricavi, rimborso_sweep, residuo, regola}` (o `None` fuori dal regime), `details['oneri_fidi']` (sempre, zero fuori dal regime), `details['regime_debito_bancario']` = `'esplicito' | 'contratti' | 'anni' | 'legacy'`; nel regime esplicito: `sp16a` = fidi residui + rata dell'anno dopo dei contratti pregressi + quota a breve dei nuovi + scoperto.

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task3-base
```

- [ ] **Step 2: Test rosso**

`tests/test_forecast_fidi.py`:

```python
"""Fidi e anticipi separati dai mutui (spec 2026-09-15 §5.2, decisioni 5 e 9).

Base: sp16a 172.500 (fidi 90.000 + rata 2027 del mutuo 82.500), sp17a 247.500. Un mutuo da
330.000 al 3,8% con rimborsi [82.500, 82.500, 82.500]. Oracolo a mano, senza sweep:
- 2027: mutuo 247.500 → a breve la rata 2028 (82.500), a lungo 165.000; fidi 90.000 costanti;
  sp16a = 172.500, sp17a = 165.000; oneri = 12.540 (mutuo) + 4.500 (fidi al 5%) = 17.040.
- 2028: mutuo 165.000 → breve 82.500, lungo 82.500; sp16a = 172.500; oneri 9.405 + 4.500.
Con regola «ricavi» e ricavi +10% i fidi 2027 valgono 99.000.
Con sweep (cassa minima 0) i fidi scendono della cassa in eccesso, il mutuo no.
"""
from decimal import Decimal as D

import pytest

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP09, SP16A, SP17A, CE15 = "sp09_disponibilita_liquide", "sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo", "ce15_oneri_finanziari"
MUTUO = {"name": "Mutuo", "opening_residual": 330000, "interest_rate": 3.8, "repayments": [82500, 82500, 82500]}


def _genera(user, rows, breve=D("172500"), lungo=D("247500")):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            delta_lungo = lungo - b.sp17a_debiti_banche_lungo
            b.sp16a_debiti_banche_breve = breve; b.sp16_debiti_breve += breve
            b.sp17a_debiti_banche_lungo = lungo; b.sp17_debiti_lungo += delta_lungo
            b.sp09_disponibilita_liquide += breve + delta_lungo
            db.commit()
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            anni = {anno: (sp, ce) for anno, sp, ce in read_forecast_maps(db, sc.id)} if res["forecast_generated"] else {}
            det = {y["year"]: y["details"] for y in prev["forecast_years"]}
            return res, anni, det, prev["error"]
    finally:
        engine.dispose()


def _rows(**primo):
    base = {"tax_rate": 27.9, "revenue_growth_pct": 0}
    r1 = {"forecast_year": 2027, "financing_loans": [MUTUO], "bank_lines_amount": 90000,
          "bank_lines_rule": "costante", "bank_lines_rate": 5, **base}
    r1.update(primo)
    return [r1, {"forecast_year": 2028, **base}, {"forecast_year": 2029, **base}]


def test_fidi_costanti_e_rata_dell_anno_dopo_a_breve():
    res, anni, det, err = _genera("fidi-costanti", _rows())
    assert res["forecast_generated"] is True, res["message"]
    assert (anni[2027][0][SP16A], anni[2027][0][SP17A]) == (D("172500.00"), D("165000.00"))
    assert (anni[2028][0][SP16A], anni[2028][0][SP17A]) == (D("172500.00"), D("82500.00"))
    assert anni[2027][1][CE15] == D("17040.00") and anni[2028][1][CE15] == D("13905.00")
    fidi = det[2027]["debito_bancario"]["fidi"]
    assert {k: (v if k == "regola" else D(str(v))) for k, v in fidi.items()} == {
        "apertura": D("90000.00"), "variazione_ricavi": D("0.00"), "rimborso_sweep": D("0.00"), "residuo": D("90000.00"), "regola": "costante"}
    assert det[2027]["oneri_fidi"] == 4500.0 and det[2027]["regime_debito_bancario"] == "esplicito"
    assert D(str(det[2027]["debito_bancario"]["contratti"][0]["breve"])) == D("82500.00")


def test_fidi_seguono_i_ricavi():
    res, anni, det, _ = _genera("fidi-ricavi", _rows(bank_lines_rule="ricavi", revenue_growth_pct=10))
    assert res["forecast_generated"] is True, res["message"]
    assert D(str(det[2027]["debito_bancario"]["fidi"]["residuo"])) == D("99000.00")
    assert D(str(det[2027]["debito_bancario"]["fidi"]["variazione_ricavi"])) == D("9000.00")


def test_lo_sweep_riduce_solo_i_fidi():
    senza = _genera("sweep-no", _rows())
    con = _genera("sweep-si", _rows(cash_sweep_enabled=True, cash_sweep_min_cash=0))
    assert con[0]["forecast_generated"] is True, con[0]["message"]
    fidi = con[2][2027]["debito_bancario"]["fidi"]
    assert D("0") < D(str(fidi["rimborso_sweep"])) <= D("90000.00")
    # il mutuo e' identico con e senza sweep: lo sweep non lo tocca
    assert con[2][2027]["debito_bancario"]["contratti"][0] == senza[2][2027]["debito_bancario"]["contratti"][0]
    assert con[1][2027][0][SP16A] == senza[1][2027][0][SP16A] - D(str(fidi["rimborso_sweep"]))
    assert con[1][2027][0][SP09] == senza[1][2027][0][SP09] - D(str(fidi["rimborso_sweep"]))


def test_rifiuti_in_italiano():
    res, *_ = _genera("fidi-troppi", _rows(bank_lines_amount=200000))
    assert res["forecast_generated"] is False and "superano i debiti verso banche a breve" in res["message"]
    res, *_ = _genera("fidi-non-quadra", _rows(bank_lines_amount=80000))
    assert res["forecast_generated"] is False and "devono coincidere con il debito bancario" in res["message"]


def test_senza_fidi_nulla_cambia():
    # `bank_lines_amount` assente: il contratto a durata di sempre, stessi numeri del Task 2.
    rows = [{"forecast_year": 2027, "tax_rate": 27.9, "financing_loans": [{"opening_residual": 330000, "interest_rate": 3.8, "duration_years": 4}]},
            {"forecast_year": 2028, "tax_rate": 27.9}]
    res, anni, det, _ = _genera("fidi-assenti", rows, breve=D("82500"), lungo=D("247500"))
    assert res["forecast_generated"] is True, res["message"]
    assert det[2027]["debito_bancario"]["fidi"] is None and det[2027]["oneri_fidi"] == 0.0
    assert det[2027]["regime_debito_bancario"] == "contratti"
```

- [ ] **Step 3: Rosso sulle asserzioni**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_fidi.py -q -p no:cacheprovider
```
Atteso: il primo test cade su «La somma dei residui iniziali (330.000,00) deve coincidere con il debito bancario dell'anno base (420.000,00)» (fidi non ancora contati); l'ultimo sul `KeyError: 'fidi'`.

- [ ] **Step 4: `assemble_financing`**

Nel ramo `use_detailed_existing_schedule`, prima del confronto:

```python
        first = assumptions[0]
        fidi = getattr(first, 'bank_lines_amount', None)
        regime_esplicito = fidi is not None
        if regime_esplicito:
            fidi = Decimal(str(fidi))
            base_sp16a = Decimal(str(getattr(base_bs, 'sp16a_debiti_banche_breve', None) or 0))
            if fidi - base_sp16a > Decimal('0.01'):
                raise ValueError(
                    f"Fidi e anticipi ({eur_it(fidi)}) superano i debiti verso banche a breve "
                    f"dell'anno base ({eur_it(base_sp16a)}): correggi al passo «Patrimoniale pregresso»"
                )
            for extra in assumptions[1:]:
                if getattr(extra, 'bank_lines_amount', None) is not None:
                    raise ValueError("Fidi e anticipi (bank_lines_amount) valgono solo sulla riga del primo anno di previsione")
        use_detailed_existing_schedule = detailed_opening_total > 0 or regime_esplicito
        if use_detailed_existing_schedule:
            getter = ...
            base_bank_total = base_bank_debt(getter)
            coperto = detailed_opening_total + (fidi if regime_esplicito else Decimal('0'))
            if abs(base_bank_total - coperto) > Decimal('0.01'):
                if regime_esplicito:
                    raise ValueError(
                        f"Fidi e anticipi ({eur_it(fidi)}) più i residui dei finanziamenti "
                        f"({eur_it(detailed_opening_total)}) devono coincidere con il debito bancario "
                        f"dell'anno base ({eur_it(base_bank_total)})"
                    )
                raise ValueError(<messaggio di oggi, invariato>)
        return financing_loans, use_detailed_existing_schedule
```
`assemble_financing` resta a due valori di ritorno; il regime lo rilegge `_calculate_balance_sheet` da `assumptions[0]`? No: `_calculate_balance_sheet` riceve `assumption` dell'anno. Aggiungere un parametro `fidi_apertura: Optional[Decimal] = None` a `_calculate_balance_sheet` e passarlo da `compute_forecast` (riga ~2235): per l'anno 1 `bank_lines_amount` della prima riga, per gli anni dopo `Decimal(str(prev_details['debito_bancario']['fidi']['residuo']))`; `None` fuori dal regime. Regola e tasso si leggono da `assumptions[0]` (`bank_lines_rule`, `bank_lines_rate`) e si passano come `fidi_regola: str`, `fidi_tasso: Decimal` — tre parametri nuovi, tutti facoltativi.

- [ ] **Step 5: Apertura, sweep e ricomposizione in `_calculate_balance_sheet`**

Dopo `apertura_pregresso = sp16a + sp17a_pregresso` (riga ~3326):

```python
        # ── FIDI E ANTICIPI (spec 2026-09-15 §5.2): uno stato, separato dai contratti ──
        fidi_residuo = None
        fidi_variazione = ZERO
        if fidi_apertura is not None:
            fidi_prev = Decimal(str(fidi_apertura))
            fidi_residuo = fidi_prev
            if fidi_regola == 'ricavi' and prev_revenue is not None and prev_revenue > ZERO:
                fidi_residuo = fidi_prev * forecast_revenue / prev_revenue
                fidi_variazione = fidi_residuo - fidi_prev
            # I fidi stanno dentro `sp16a` pregresso: la rata dei contratti non li tocca.
            sp16a = max(ZERO, sp16a - fidi_prev)
```
(`prev_revenue` e' il quarto parametro nuovo di `_calculate_balance_sheet`, `Optional[Decimal] = None`: `compute_forecast` lo passa come `ce01_ricavi_vendite` di `prev_inc` — l'anno base per il primo anno di piano, il CE previsto dell'anno prima poi. `forecast_revenue` e' la variabile locale che il metodo gia' usa per il DSO.)

Nel blocco dello sweep (riga ~3733): con `fidi_apertura is not None` → `sweep.attivo = bool(cash_sweep_enabled)`, `sweep.breve_disponibile = fidi_residuo`, `sweep.lungo_disponibile = ZERO`. Senza, il codice di oggi.

Dopo le rate dei contratti pregressi (riga ~3690, `sp17a_pregresso = max(ZERO, sp17a_pregresso - (es_repayment - short_es_repayment))`) e PRIMA della quota a breve dei nuovi (riga ~3770), nel solo regime esplicito ricomporre il pregresso: `residuo_pregresso = sp16a + sp17a_pregresso` (contratti gia' rimborsati, fidi esclusi); `quota_dopo = Σ new_financing_schedule([c], anno + 1)[1] per c in contratti_pregresso` (mai oltre `residuo_pregresso`); `sp16a = fidi_residuo + quota_dopo`; `sp17a_pregresso = residuo_pregresso - quota_dopo`. E' una riclassifica: cassa e interessi non cambiano. Documentare nel commento perche' vale solo nel regime esplicito (fuori, i numeri di oggi restano al centesimo).

`debito_bancario.contratti` gia' assegna `breve_pregresso` in ordine ai contratti: nel regime esplicito passare `quota_dopo` come `breve_pregresso` (non `breve_pregresso_fine`, che ora include i fidi) e aggiungere `debito_bancario.fidi = {'apertura': fidi_prev, 'variazione_ricavi': fidi_variazione, 'rimborso_sweep': ZERO, 'residuo': fidi_residuo, 'regola': fidi_regola or 'costante'}` (`None` fuori dal regime; `_DebitoBancarioAnno` prende il campo `fidi: Optional[Dict] = None`).

In `_dichiara_debito_bancario`: se `debito.fidi` c'e', `rimborso_sweep = sweep.rimborso_breve`, `residuo = _q2(fidi['residuo']) - rimborso_sweep`, e i fidi entrano in `tutte` sul lato `breve` (la «casa» degli aumenti e' la riga fidi nel regime esplicito). L'invariante resta: Σ`breve` (fidi + contratti) + `scoperto` = `sp16a`.

`details['regime_debito_bancario']`: `'esplicito'` se `fidi_apertura is not None`, altrimenti `'contratti'` se `use_detailed_existing_schedule`, `'anni'` se `piano_anni_attivo`, `'legacy'`. Scritto sempre, accanto a `details['debito_bancario']` (riga ~2320).

- [ ] **Step 6: Oneri e tasso dello scoperto in `_calculate_income_statement`**

Aggiungere i parametri `fidi_apertura: Optional[Decimal] = None`, `fidi_tasso: Decimal = ZERO` (passati da `compute_forecast` con gli stessi valori del passo 4). Dopo `oneri_scoperto`:

```python
        oneri_fidi = ZERO
        if fidi_apertura is not None:
            oneri_fidi = (Decimal(str(fidi_apertura)) * fidi_tasso / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            # Nel regime esplicito il tasso dello scoperto e' quello dei fidi: il wizard non scrive
            # piu' `financing_interest_rate`.
            tasso_scoperto = fidi_tasso
            oneri_scoperto = (scoperto_apertura * tasso_scoperto / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if assumption.ce15_override is None:
            ce15 = financing_interest if has_detailed_opening else ce15 + financing_interest
            ce15 = ce15 + oneri_scoperto + oneri_fidi
        else:
            oneri_scoperto = oneri_fidi = Decimal('0')
        if details is not None:
            details['oneri_scoperto'] = oneri_scoperto
            details['oneri_fidi'] = oneri_fidi
```
(`has_detailed_opening` deve valere anche nel regime esplicito con soli fidi e nessun contratto: `has_detailed_opening = any(...) or fidi_apertura is not None`.) Aggiungere `'oneri_fidi'` all'elenco dei `details` quantizzati/dichiarati sempre (cercare dove `oneri_scoperto` e' impostato a zero di default per l'anno senza scoperto e fare lo stesso).

- [ ] **Step 7: Verde, parita', suite**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_fidi.py tests/test_forecast_contratti_per_anno.py tests/test_forecast_sweep_piani.py tests/test_forecast_finanziamento_pregresso.py tests/test_forecast_prestito_quota_breve.py tests/test_forecast_dichiarato_vs_persistito.py tests/test_forecast_scoperto.py -q -p no:cacheprovider
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-task3-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-task3-parita.json --log /tmp/rilievi-task3-parita.log
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
Atteso: verde; banco 0. Una divergenza sui profili esistenti significa che il regime esplicito e' scattato senza `bank_lines_amount`: e' il difetto, non un'attesa da aggiornare.

- [ ] **Step 8: Documentazione e commit**

`docs/budget/API-PREVISIONALE.md` §4-ter: un paragrafo «**Fidi e anticipi (regime esplicito).**» con: i tre campi, il controllo `fidi + Σ residui = debito bancario base`, lo sweep che rimborsa solo i fidi, la ricomposizione (rata dell'anno dopo a breve), gli oneri (`oneri_fidi`, tasso dello scoperto = `bank_lines_rate`), le due chiavi nuove di `details` (`debito_bancario.fidi`, `regime_debito_bancario`). `CLAUDE.md`, sezione «Forecasting Engine», paragrafo «The cash sweep repays only what has no plan»: aggiungere una frase «**With `bank_lines_amount` set (explicit regime, lotto rilievi 14/09) the sweep repays only the credit lines (`details['debito_bancario']['fidi']`), never a contract; bank contracts reclassify next year's instalment into `sp16a`.**»

```bash
git add calculations/forecast_engine.py tests/test_forecast_fidi.py docs/budget/API-PREVISIONALE.md CLAUDE.md
git commit -m "feat(ipotesi): fidi e anticipi separati dai contratti, sweep solo su di loro"
```

---

### Task 4: Altri finanziatori per anno (`other_lenders`)

**Files:**
- Modify: `calculations/forecast_engine.py:2059-2108` (`assemble_financing`: validazione e assemblaggio), `:3292-3295` e `:3677-3684` (`sp16b`/`sp17b`), `:2761-2800` (interessi), dichiarazione `details['altri_finanziatori']`
- Test: `tests/test_forecast_altri_finanziatori.py` (nuovo)
- Docs: `docs/budget/API-PREVISIONALE.md` §4-ter

**Interfaces:**
- Consumes: `assumption.other_lenders` (Task 1), kernel `repayments` (Task 2), regime esplicito (Task 3: `fidi_apertura is not None`)
- **Attenzione (dubbio del Task 1):** `build_assumption_row` persiste `other_lenders` con `jsonable_encoder`, quindi nel sacco JSON gli importi sono `float`. In `assemble_financing` ogni voce si rilegge con `OtherLenderInput.model_validate(item)` e si usano i `Decimal` del modello validato, mai i float nudi.
- Produces: `details['altri_finanziatori'] = {apertura, rimborso, interessi, breve, lungo, mode, contratti: [{indice, nome, residuo_iniziale, rimborso, interessi, residuo}]}`, sempre presente (`mode` = `'contratti' | 'anni' | 'legacy'`, `contratti` vuoto fuori dal regime).

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task4-base
```

- [ ] **Step 2: Test rosso**

`tests/test_forecast_altri_finanziatori.py`:

```python
"""Altri finanziatori scadenziati per anno (spec 2026-09-15 §5.3).

Base: sp17b 150.000 (finanziamento soci, 0%). Rimborsi [0, 50.000, 0]. Oracolo: 2027 residuo
150.000 con 50.000 a breve (la rata 2028) e 100.000 a lungo; 2028 residuo 100.000, breve 0,
lungo 100.000; 2029 uguale (resta aperto). Al 2% gli interessi 2027 sono 3.000.
"""
from decimal import Decimal as D

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP16B, SP17B, CE15, SP09 = "sp16b_debiti_altri_finanz_breve", "sp17b_debiti_altri_finanz_lungo", "ce15_oneri_finanziari", "sp09_disponibilita_liquide"
SOCI = {"name": "Finanziamento soci", "opening_residual": 150000, "interest_rate": 0, "repayments": [0, 50000, 0]}


def _genera(user, rows, sp17b=D("150000")):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            b.sp17b_debiti_altri_finanz_lungo = sp17b; b.sp17_debiti_lungo += sp17b
            b.sp09_disponibilita_liquide += sp17b
            db.commit()
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            anni = {anno: (sp, ce) for anno, sp, ce in read_forecast_maps(db, sc.id)} if res["forecast_generated"] else {}
            det = {y["year"]: y["details"] for y in prev["forecast_years"]}
            return res, anni, det
    finally:
        engine.dispose()


def _rows(soci=SOCI, **primo):
    base = {"tax_rate": 27.9}
    # Regime esplicito con soli fidi a zero: il kit non ha banche a breve, e sp17a 50.000 e'
    # coperto da un contratto senza rimborsi.
    r1 = {"forecast_year": 2027, "bank_lines_amount": 0, "bank_lines_rule": "costante", "bank_lines_rate": 0,
          "financing_loans": [{"opening_residual": 50000, "interest_rate": 0, "repayments": []}],
          "other_lenders": [soci], **base}
    r1.update(primo)
    return [r1, {"forecast_year": 2028, **base}, {"forecast_year": 2029, **base}]


def test_rimborsi_per_anno_e_quota_a_breve():
    res, anni, det = _genera("soci", _rows())
    assert res["forecast_generated"] is True, res["message"]
    assert [(anni[a][0][SP16B], anni[a][0][SP17B]) for a in (2027, 2028, 2029)] == [
        (D("50000.00"), D("100000.00")), (D("0.00"), D("100000.00")), (D("0.00"), D("100000.00"))]
    a = det[2027]["altri_finanziatori"]
    assert a["mode"] == "contratti" and [D(str(a[k])) for k in ("apertura", "rimborso", "breve")] == [D("150000.00"), D("0.00"), D("50000.00")]
    b = det[2028]["altri_finanziatori"]
    assert [D(str(b[k])) for k in ("rimborso", "breve", "lungo")] == [D("50000.00"), D("0.00"), D("100000.00")]


def test_interessi_sul_residuo_di_apertura():
    res, anni, det = _genera("soci-2pct", _rows(soci={**SOCI, "interest_rate": 2}))
    assert res["forecast_generated"] is True, res["message"]
    # apertura 2028 ancora 150.000; 2029 100.000
    assert [D(str(det[y]["altri_finanziatori"]["interessi"])) for y in (2027, 2028, 2029)] == [D("3000.00"), D("3000.00"), D("2000.00")]


def test_rifiuti_in_italiano():
    res, *_ = _genera("soci-non-quadra", _rows(soci={**SOCI, "opening_residual": 100000, "repayments": []}))
    assert res["forecast_generated"] is False and "altri finanziatori" in res["message"] and "coincidere" in res["message"]
    rows = _rows(); rows[0].pop("bank_lines_amount")
    res, *_ = _genera("soci-senza-regime", rows)
    assert res["forecast_generated"] is False and "Patrimoniale pregresso" in res["message"]


def test_senza_lista_il_comportamento_di_prima():
    rows = [{"forecast_year": 2027, "tax_rate": 27.9, "altri_finanz_repayment_years": 3}, {"forecast_year": 2028, "tax_rate": 27.9}]
    res, anni, det = _genera("soci-anni", rows)
    assert res["forecast_generated"] is True, res["message"]
    assert anni[2027][0][SP17B] == D("100000.00") and det[2027]["altri_finanziatori"]["mode"] == "anni"
    assert det[2027]["altri_finanziatori"]["contratti"] == []
```
- [ ] **Step 3: Rosso sulle asserzioni**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_altri_finanziatori.py -q -p no:cacheprovider
```
Atteso: `KeyError: 'altri_finanziatori'` e `sp17b` fermo a 150.000.

- [ ] **Step 4: Assemblaggio e validazione**

In `assemble_financing`, dopo il blocco dei fidi (Task 3), restituendo un terzo valore `altri_finanziatori: List[dict]`:

```python
        altri = list(getattr(first, 'other_lenders', None) or [])
        for extra in assumptions[1:]:
            if getattr(extra, 'other_lenders', None):
                raise ValueError("Gli altri finanziatori per anno (other_lenders) valgono solo sulla riga del primo anno di previsione")
        if altri and not regime_esplicito:
            raise ValueError(
                "Gli altri finanziatori per anno richiedono la divisione dei debiti bancari a breve "
                "del passo «Patrimoniale pregresso» (fidi e anticipi)"
            )
        contratti_altri = []
        if altri:
            getter = lambda f: getattr(base_bs, f, None) or Decimal('0')
            base_altri = getter('sp16b_debiti_altri_finanz_breve') + getter('sp17b_debiti_altri_finanz_lungo')
            totale = sum((Decimal(str(a.get('opening_residual') or 0)) for a in altri), Decimal('0'))
            if abs(totale - base_altri) > Decimal('0.01'):
                raise ValueError(
                    f"La somma dei residui degli altri finanziatori ({eur_it(totale)}) deve coincidere "
                    f"con i debiti verso altri finanziatori dell'anno base ({eur_it(base_altri)})"
                )
            for indice, a in enumerate(altri):
                contratti_altri.append({
                    'indice': indice, 'nome': a.get('name') or f"Finanziatore {indice + 1}",
                    'year': first_forecast_year, 'amount': ZERO,
                    'opening_residual': Decimal(str(a.get('opening_residual') or 0)),
                    'rate': Decimal(str(a.get('interest_rate') or 0)) / Decimal('100'),
                    'duration': ZERO, 'grace_years': ZERO, 'balloon_pct': ZERO,
                    'repayments': [Decimal(str(r or 0)) for r in (a.get('repayments') or [])],
                })
        return financing_loans, use_detailed_existing_schedule, contratti_altri
```
Aggiornare i due chiamanti (`compute_forecast` riga 2134 e ogni altro `assemble_financing(`: `grep -n "assemble_financing" calculations/ tests/`) e passare `contratti_altri` a `_calculate_income_statement` e `_calculate_balance_sheet` come parametro `altri_finanziatori=None`.

- [ ] **Step 5: Bilancio e interessi**

In `_calculate_balance_sheet`, al posto del blocco `altri_repay_years` (riga ~3677):

```python
        altri_det = {'apertura': _prev('sp16b_debiti_altri_finanz_breve') + _prev('sp17b_debiti_altri_finanz_lungo'),
                     'rimborso': ZERO, 'interessi': ZERO, 'breve': ZERO, 'lungo': ZERO, 'mode': 'legacy', 'contratti': []}
        if altri_finanziatori:
            anno = assumption.forecast_year
            righe, tot_res, tot_breve, tot_rimb, tot_int = [], ZERO, ZERO, ZERO, ZERO
            for c in altri_finanziatori:
                _, rimborso, interessi = new_financing_schedule([c], anno)
                residuo = _residuo_contratto(c, anno)
                _, rata_dopo, _ = new_financing_schedule([c], anno + 1)
                breve = min(residuo, rata_dopo)
                righe.append({'indice': c['indice'], 'nome': c['nome'], 'residuo_iniziale': c['opening_residual'],
                              'rimborso': rimborso, 'interessi': interessi, 'residuo': residuo, 'breve': breve, 'lungo': residuo - breve})
                tot_res += residuo; tot_breve += breve; tot_rimb += rimborso; tot_int += interessi
            sp16b, sp17b = tot_breve, tot_res - tot_breve
            altri_det.update({'rimborso': tot_rimb, 'interessi': tot_int, 'breve': sp16b, 'lungo': sp17b,
                              'mode': 'contratti', 'contratti': righe})
        else:
            altri_repay_years = getattr(assumption, 'altri_finanz_repayment_years', None)
            if altri_repay_years is not None and D(str(altri_repay_years)) > 0:
                annual_altri = altri_finanz_repayment_instalment(_base, altri_repay_years)
                rimborsato = min(sp17b, annual_altri)
                sp17b = max(ZERO, sp17b - annual_altri)
                altri_det.update({'rimborso': rimborsato, 'mode': 'anni'})
            altri_det.update({'breve': sp16b, 'lungo': sp17b})
        if details is not None:
            details['altri_finanziatori'] = altri_det
```
`_residuo_contratto` (riga 317) funziona su un contratto con `repayments` grazie al Task 2. Gli interessi: in `_calculate_income_statement`, `interessi_altri = Σ new_financing_schedule([c], anno)[2]` sui `altri_finanziatori`, sommati a `ce15` nel ramo senza override e dichiarati `details['oneri_altri_finanziatori']` (sempre, zero senza lista). Le voci `altri_finanziatori` dei `details` si quantizzano al centesimo dove si quantizzano gli altri (`_quantize_values` o l'equivalente usato per `debito_bancario`).

- [ ] **Step 6: Verde, parita', suite, documentazione, commit**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_altri_finanziatori.py tests/test_forecast_fidi.py tests/test_forecast_dichiarato_vs_persistito.py -q -p no:cacheprovider
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-task4-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-task4-parita.json --log /tmp/rilievi-task4-parita.log
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
Atteso: verde, banco 0. In `docs/budget/API-PREVISIONALE.md` §4-ter aggiungere «**Altri finanziatori per anno (`other_lenders`).**» con campi, controllo sul totale base, quota a breve = rata dell'anno dopo, interessi, `details['altri_finanziatori']` e le tre `mode`.

```bash
git add calculations/forecast_engine.py tests/test_forecast_altri_finanziatori.py docs/budget/API-PREVISIONALE.md
git commit -m "feat(ipotesi): altri finanziatori scadenziati per anno con quota a breve e interessi"
```

---

### Task 5: Liquidazioni TFR (`tfr_payments`)

**Files:**
- Modify: `calculations/forecast_engine.py:3253-3262` (fondo TFR)
- Test: `tests/test_forecast_tfr_liquidazioni.py` (nuovo)
- Docs: `docs/budget/API-PREVISIONALE.md` (sezione nuova «TFR»), `CLAUDE.md` (una riga in «Invarianti e trappole › Previsionale»)

**Interfaces:**
- Consumes: `assumption.tfr_payments` (Task 1)
- Produces: `details['tfr'] = {apertura, accantonamento, liquidazioni, chiusura, sospeso}`, sempre; errore `Liquidazioni TFR {anno}: {X} superano il fondo disponibile ({Y}); correggi al passo «Patrimoniale piano»`.

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task5-base
```

- [ ] **Step 2: Test rosso**

`tests/test_forecast_tfr_liquidazioni.py`:

```python
"""Il fondo TFR si scarica con le liquidazioni (spec 2026-09-15 §5.4).

Kit: sp15 30.000, ce08 120.000 con ce08b 0 → accantonamento = 120.000 × 0,70 / 13,5 = 6.222,22
(personale a crescita zero). Oracolo: 2027 fondo 36.222,22 senza liquidazioni; con 20.000 di
liquidazioni 16.222,22 e la cassa scende di 20.000 rispetto al gemello.
"""
from decimal import Decimal as D

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BudgetScenario
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP15, SP09 = "sp15_tfr", "sp09_disponibilita_liquide"


def _genera(user, rows):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            anni = {anno: (sp, ce) for anno, sp, ce in read_forecast_maps(db, sc.id)} if res["forecast_generated"] else {}
            det = {y["year"]: y["details"] for y in prev["forecast_years"]}
            return res, anni, det
    finally:
        engine.dispose()


def _rows(**primo):
    r1 = {"forecast_year": 2027, "tax_rate": 27.9, "personnel_growth_pct": 0}
    r1.update(primo)
    return [r1, {"forecast_year": 2028, "tax_rate": 27.9, "personnel_growth_pct": 0}]


def test_liquidazione_scarica_il_fondo_e_la_cassa():
    senza = _genera("tfr-no", _rows())
    con = _genera("tfr-si", _rows(tfr_payments=20000))
    assert con[0]["forecast_generated"] is True, con[0]["message"]
    assert senza[1][2027][0][SP15] == D("36222.22") and con[1][2027][0][SP15] == D("16222.22")
    assert con[1][2027][0][SP09] == senza[1][2027][0][SP09] - D("20000.00")
    tfr = con[2][2027]["tfr"]
    assert {k: (v if k == "sospeso" else D(str(v))) for k, v in tfr.items()} == {
        "apertura": D("30000.00"), "accantonamento": D("6222.22"), "liquidazioni": D("20000.00"), "chiusura": D("16222.22"), "sospeso": False}
    assert D(str(senza[2][2027]["tfr"]["liquidazioni"])) == D("0.00")


def test_liquidazione_oltre_il_fondo_si_rifiuta():
    res, *_ = _genera("tfr-troppo", _rows(tfr_payments=40000))
    assert res["forecast_generated"] is False
    assert "Liquidazioni TFR 2027" in res["message"] and "Patrimoniale piano" in res["message"]


def test_sospeso_con_liquidazione():
    res, anni, det = _genera("tfr-sospeso", _rows(tfr_accrual_suspended=True, tfr_payments=10000))
    assert res["forecast_generated"] is True, res["message"]
    assert anni[2027][0][SP15] == D("20000.00") and det[2027]["tfr"]["sospeso"] is True
```

- [ ] **Step 3: Rosso**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_tfr_liquidazioni.py -q -p no:cacheprovider
```
Atteso: `KeyError: 'tfr'` e fondo a 36.222,22 anche con liquidazioni.

- [ ] **Step 4: Motore**

Sostituire il blocco (righe 3258-3262) con:

```python
        tfr_suspended = bool(getattr(assumption, 'tfr_accrual_suspended', False))
        tfr_apertura = _prev('sp15_tfr')
        tfr_accantonamento = ZERO if tfr_suspended else forecast_inc.get('ce08a_tfr_accrual', ZERO)
        tfr_liquidazioni = Decimal(str(getattr(assumption, 'tfr_payments', None) or 0))
        disponibile = tfr_apertura + tfr_accantonamento
        if tfr_liquidazioni - disponibile > Decimal('0.01'):
            raise ValueError(
                f"Liquidazioni TFR {assumption.forecast_year}: {eur_it(tfr_liquidazioni)} superano il fondo "
                f"disponibile ({eur_it(disponibile)}); correggi al passo «Patrimoniale piano»"
            )
        sp15 = disponibile - tfr_liquidazioni
        if details is not None:
            details['tfr'] = {'apertura': tfr_apertura, 'accantonamento': tfr_accantonamento,
                              'liquidazioni': tfr_liquidazioni, 'chiusura': sp15, 'sospeso': tfr_suspended}
```
Quantizzare le quattro cifre di `details['tfr']` dove si quantizzano gli altri `details` (l'accantonamento e' gia' al centesimo perche' `forecast_inc` e' normalizzato; `chiusura` deve coincidere con `sp15` persistito: verificare con `tests/test_forecast_dichiarato_vs_persistito.py`, aggiungendo `('tfr', 'chiusura', 'sp15_tfr')` alla sua tabella se ne ha una).

- [ ] **Step 5: Verde, parita', suite, documentazione, commit**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_tfr_liquidazioni.py tests/test_forecast_dichiarato_vs_persistito.py -q -p no:cacheprovider
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-task5-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-task5-parita.json --log /tmp/rilievi-task5-parita.log
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
`docs/budget/API-PREVISIONALE.md`: sezione «## 13. Fondo TFR e liquidazioni» (accantonamento salari/13,5, sospensione, `tfr_payments`, il rifiuto, `details['tfr']`, il rendiconto che legge le liquidazioni dal movimento del fondo). `CLAUDE.md` «Invarianti e trappole › Previsionale»: «**Una liquidazione TFR oltre il fondo disponibile si rifiuta** (`tfr_payments`, `details['tfr']`): clamparla lascerebbe in cassa un'uscita mai avvenuta.»

```bash
git add calculations/forecast_engine.py tests/test_forecast_tfr_liquidazioni.py tests/test_forecast_dichiarato_vs_persistito.py docs/budget/API-PREVISIONALE.md CLAUDE.md
git commit -m "feat(ipotesi): liquidazioni TFR per anno, dichiarate e rifiutate oltre il fondo"
```

---

### Task 6: `details['pareggio']`, `non_incassato`, nomi dei passi nei messaggi

**Files:**
- Modify: `calculations/forecast_engine.py:2800-2830` (dichiarazione del pareggio in `_calculate_income_statement`), `:3900-3915` (`non_incassato` in `details['pregresso']`), `:922-927` (`_PREGRESSO_PASSO_DEFAULT`)
- Modify: `calculations/forecast_engine.py:562-620` (`validate_pregresso`: `non_incassato` passa)
- Test: `tests/test_forecast_pareggio.py` (nuovo); `tests/test_forecast_override_crediti.py`, `tests/test_forecast_override_tributario.py` (i messaggi attesi)
- Docs: `docs/budget/API-PREVISIONALE.md`

**Interfaces:**
- Consumes: nulla dei task in corso. L'anteprima (`forecast_preview_service.preview_forecast`) costruisce le righe da `build_assumption_row` senza passare dallo schema Pydantic, quindi `pregresso.crediti_commerciali.non_incassato` arriva al motore anche prima che il Task 1 lo aggiunga a `PregressoPlanInput`. I test di questo task usano solo l'anteprima.
- Produces: `details['pareggio'] = {costi_variabili, costi_fissi, costi_fissi_operativi, margine_contribuzione_pct, fatturato_pareggio, margine_sicurezza, margine_sicurezza_pct}` (i quattro ultimi `None` quando non definiti; tutto `None` se `ce05_fixed` o `ce06_fixed` e' `None`); `details['pregresso']['crediti_commerciali']['non_incassato']: bool`; messaggi che dicono «Patrimoniale pregresso».

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task6-base
```

- [ ] **Step 2: Test rosso**

`tests/test_forecast_pareggio.py`:

```python
"""Il punto di pareggio sul MOL lo dichiara il motore (spec 2026-09-15 §4.3, decisione 4).

Kit a crescita zero e quota fissa 40%: ricavi 600.000; variabili = 0,6 × (200.000 + 150.000) =
210.000; fissi = 140.000 + 120.000 + 10.000 + 5.000 = 275.000; altri ricavi 0 → fissi operativi
275.000; margine di contribuzione 65% → pareggio 423.076,92; margine di sicurezza 176.923,08 (29,49%).
"""
from decimal import Decimal as D

from backend.app.services import forecast_preview_service
from database.models import BudgetScenario
from tests.e2e_kit import memory_sessions, seed_base_year


def _preview(user, rows):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            return forecast_preview_service.preview_forecast(db, sc.id, rows)
    finally:
        engine.dispose()


def test_pareggio_dichiarato():
    out = _preview("bep", [{"forecast_year": 2027, "tax_rate": 27.9}])
    p = out["forecast_years"][0]["details"]["pareggio"]
    assert p == {"costi_variabili": D("210000.00"), "costi_fissi": D("275000.00"), "costi_fissi_operativi": D("275000.00"),
                 "margine_contribuzione_pct": D("65.00"), "fatturato_pareggio": D("423076.92"),
                 "margine_sicurezza": D("176923.08"), "margine_sicurezza_pct": D("29.49")}


def test_pareggio_nullo_con_override_di_ce05():
    out = _preview("bep-override", [{"forecast_year": 2027, "tax_rate": 27.9, "ce05_override": 100000}])
    p = out["forecast_years"][0]["details"]["pareggio"]
    assert all(v is None for v in p.values())


def test_non_incassato_dichiarato():
    piano = {"crediti_commerciali": {"opening": 120000, "amounts": [120000], "non_incassato": True}}
    out = _preview("non-incassato", [{"forecast_year": 2027, "tax_rate": 27.9, "pregresso": piano}])
    assert out["error"] is None
    assert out["forecast_years"][0]["details"]["pregresso"]["crediti_commerciali"]["non_incassato"] is True
```

- [ ] **Step 3: Rosso**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_pareggio.py -q -p no:cacheprovider
```
Atteso: `KeyError: 'pareggio'`; `KeyError: 'non_incassato'`.

- [ ] **Step 4: Pareggio**

In `_calculate_income_statement`, dove si scrivono `details['ce05_fixed']` ecc. (cercare `'ce05_fixed'`), dopo:

```python
        if details is not None:
            fissi_def = all(details.get(k) is not None for k in ('ce05_fixed', 'ce05_variable', 'ce06_fixed', 'ce06_variable'))
            pareggio = {k: None for k in ('costi_variabili', 'costi_fissi', 'costi_fissi_operativi',
                                          'margine_contribuzione_pct', 'fatturato_pareggio',
                                          'margine_sicurezza', 'margine_sicurezza_pct')}
            if fissi_def:
                cv = details['ce05_variable'] + details['ce06_variable']
                cf = details['ce05_fixed'] + details['ce06_fixed'] + ce07 + ce08 + ce12
                cf_op = cf - ce04
                pareggio.update({'costi_variabili': cv, 'costi_fissi': cf, 'costi_fissi_operativi': cf_op})
                if ce01 > ZERO and ce01 - cv > ZERO:
                    mdc = (ce01 - cv) / ce01
                    bep = cf_op / mdc
                    pareggio.update({
                        'margine_contribuzione_pct': mdc * Decimal('100'),
                        'fatturato_pareggio': bep,
                        'margine_sicurezza': ce01 - bep,
                        'margine_sicurezza_pct': (ce01 - bep) / ce01 * Decimal('100'),
                    })
            details['pareggio'] = pareggio
```
(`ce01` e `ce04` sono le variabili locali gia' definite in testa al metodo — righe 2586-2593 —; `ce07`, `ce08`, `ce12` sono quelle che il metodo calcola subito dopo le due voci divise: verificarne i nomi con `grep -n "ce07 =\|ce08 =\|ce12 =" calculations/forecast_engine.py` fra le righe 2600 e 2700 e usare quelli; il blocco va DOPO la loro definizione, non dove oggi si scrive `details['ce05_fixed']` se quella riga precede `ce12`. I sette valori vanno quantizzati a due decimali con ROUND_HALF_UP nel punto in cui i `details` si quantizzano, e `None` deve restare `None`.)

- [ ] **Step 5: `non_incassato` e nomi dei passi**

In `validate_pregresso` (riga ~591) copiare la chiave nel piano normalizzato: `out[key]['non_incassato'] = bool(plan.get('non_incassato')) if key == 'crediti_commerciali' else False` (seguire la forma con cui `out[key]` viene costruito). Nella dichiarazione di `details['pregresso']` (riga ~3905) aggiungere `'non_incassato': bool((pregresso or {}).get(key, {}).get('non_incassato')) if key == 'crediti_commerciali' else False`.

`_PREGRESSO_PASSO_DEFAULT = "Patrimoniale pregresso"`; aggiornare il commento sopra (`StepPregressoNuovo.tsx:233` → «passo Patrimoniale pregresso»). Nei test `tests/test_forecast_override_crediti.py` e `tests/test_forecast_override_tributario.py` sostituire ogni «Pregresso e nuovo» atteso con «Patrimoniale pregresso» (`grep -n "Pregresso e nuovo" tests/`).

- [ ] **Step 6: Verde, parita', suite, documentazione, commit**

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_pareggio.py tests/test_forecast_override_crediti.py tests/test_forecast_override_tributario.py tests/test_budget_pregresso.py -q -p no:cacheprovider
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-task6-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-task6-parita.json --log /tmp/rilievi-task6-parita.log
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/ -q -p no:cacheprovider
```
`docs/budget/API-PREVISIONALE.md` §7 (anteprima): il blocco `details['pareggio']` con le sette chiavi e i casi `null`; §8: `non_incassato` (dichiarativo). Il banco: 0 divergenze (il pareggio e' solo dichiarato; se il banco confronta anche i `details`, la divergenza attesa e' la sola chiave `pareggio` aggiunta — ammetterla con `scripts/parita_riepilogo.py /tmp/rilievi-task6-parita.json --attese "details.pareggio"`; se il banco non confronta i `details`, l'atteso e' 0).

```bash
git add calculations/forecast_engine.py tests/test_forecast_pareggio.py tests/test_forecast_override_crediti.py tests/test_forecast_override_tributario.py docs/budget/API-PREVISIONALE.md
git commit -m "feat(ipotesi): pareggio sul MOL nei details, crediti non incassati dichiarati, passi rinominati nei messaggi"
```

---

### Task 7: Profili nuovi del banco di parita' e giro completo

**Files:**
- Modify: `scripts/parita_motore.py` (i profili della griglia: cercare la funzione che li genera, `grep -n "def _profili\|PROFILI\|profilo" scripts/parita_motore.py`)
- Test: il banco stesso

**Interfaces:**
- Consumes: tutti i campi dei Task 1-6
- Produces: tre profili nuovi — `fidi_contratti_anno` (fidi + un contratto con `repayments` + sweep), `altri_finanziatori_anno` (fidi 0 + `other_lenders`), `tfr_liquidazioni` — che il banco esercita da qui in poi.

- [ ] **Step 1: Base e lettura del banco**

```bash
git rev-parse HEAD > /tmp/rilievi-task7-base
sed -n 1,80p scripts/parita_motore.py
grep -n "def \|PROFILI\|profil" scripts/parita_motore.py | head -60
```
Leggere come un profilo dichiara la base (`seed_base_year` con scala/holding) e le righe di ipotesi; i tre profili nuovi seguono la stessa forma, con le righe dei test dei Task 3, 4 e 5 (`_rows()` di `test_forecast_fidi.py`, `test_forecast_altri_finanziatori.py`, `test_forecast_tfr_liquidazioni.py`), e la base modificata come in quei `_genera` (sp16a/sp17a, sp17b).

- [ ] **Step 2: Controllo negativo sui profili nuovi**

Il banco con `--controllo-negativo` deve trovare divergenze quando il motore cambia: eseguire il banco fra la base del Task 1 e l'albero corrente con i profili nuovi e verificare che le divergenze compaiano SOLO sui tre profili nuovi:

```bash
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-task1-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-task7-parita.json --log /tmp/rilievi-task7-parita.log; echo "exit $?"
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/rilievi-task7-parita.json --attese "fidi_contratti_anno" "altri_finanziatori_anno" "tfr_liquidazioni"
```
Atteso: exit 1 dal banco (divergenze), exit 0 dal riepilogo (tutte ammesse). Contro la base del Task 7 stessa (`/tmp/rilievi-task7-base`, motore invariato) il banco esce 0. Nota: sulla base del Task 1 i campi nuovi esistono ma il motore li ignora: i profili nuovi devono comunque GENERARE su quella base (altrimenti il banco segnala un errore, non una divergenza) — se un profilo non genera sulla base (es. «other_lenders richiedono…» non esiste ancora la' e il piano gira senza), va bene lo stesso: cio' che conta e' che generi sull'albero corrente e che la differenza sia attribuita al profilo.

- [ ] **Step 3: Commit**

```bash
git add scripts/parita_motore.py
git commit -m "test(ipotesi): tre profili del banco di parita' per fidi, altri finanziatori e TFR"
```

---

## Ondata B — interfaccia

### Task 8: Tipi, idratazione, passi, regole di campo, catalogo e fixture del report

**Files:**
- Modify: `frontend/types/api.ts:426-434, 500-600, 1160-1200` (misto CRLF/LF: preservare) — `FinancingLoanInput`, `OtherLenderInput`, `PregressoPlan.non_incassato`, otto campi su `BudgetAssumptions` e `BudgetAssumptionsCreate`, `ForecastYearDetails` (`pareggio`, `tfr`, `altri_finanziatori`, `oneri_fidi`, `regime_debito_bancario`, `debito_bancario.fidi`)
- Modify: `frontend/lib/budget-horizon.ts:79-200` (`hydrateAssumptions`), `:217-270` (`defaultAssumption`), nuova `withOtherLenders`
- Modify: `frontend/lib/budget-wizard-steps.ts` (chiavi, titoli, `STEP_FIELDS`, `stepLead`, `stepFooterHint`, `stepForErrorMessage`)
- Modify: `frontend/lib/budget-field-rules.ts` (regole dei campi nuovi)
- Modify: `frontend/hooks/use-scenario-assumptions.ts` (`updateOtherLenders`), `frontend/components/budget/wizard/types.ts` (`StepProps.updateOtherLenders`)
- Modify: `contracts/final_report_assumption_sections.json`, `frontend/types/final-report.ts:12`, `frontend/components/final-report/AssumptionsCatalog.test.ts:28-75`, `tests/test_final_report_contract.py:252-253`, `tests/fixtures/final_report/{bilancio,startup,infrannuale}.json`
- Test: `frontend/lib/budget-horizon.test.ts` (elenco congelato 91 → 99), `frontend/lib/budget-wizard-steps.test.ts`, `frontend/lib/budget-field-rules.test.ts`

**Interfaces:**
- Produces: `WizardStepKey = "scenario" | "fatturato" | "costi" | "circolante" | "patrimoniale-pregresso" | "patrimoniale-piano" | "imposte"`; `WizardStep.badge?: "nuovo"`; `StepProps.updateOtherLenders(lenders: OtherLenderInput[]): void` (scrive sul primo anno); tipi `OtherLenderInput`, `PareggioDetail`, `TfrDetail`, `AltriFinanziatoriDetail`, `DebitoBancarioFidi`.

- [ ] **Step 1: Base del task e terminatori**

```bash
git rev-parse HEAD > /tmp/rilievi-task8-base
file frontend/types/api.ts
test -e frontend/node_modules || ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules
```

- [ ] **Step 2: Test rossi (tre suite)**

In `frontend/lib/budget-wizard-steps.test.ts` sostituire il primo `it` e le asserzioni sui passi:

```ts
  it("ha sette passi numerati in ordine, in tre gruppi, con i due passi nuovi marcati", () => {
    expect(WIZARD_STEPS.map((s) => s.key)).toEqual([
      "scenario", "fatturato", "costi", "circolante", "patrimoniale-pregresso", "patrimoniale-piano", "imposte",
    ]);
    expect(WIZARD_STEPS.map((s) => s.group)).toEqual([
      "Impostazione", "Conto economico", "Conto economico",
      "Stato patrimoniale", "Stato patrimoniale", "Stato patrimoniale", "Stato patrimoniale",
    ]);
    expect(WIZARD_STEPS.filter((s) => s.badge === "nuovo").map((s) => s.n)).toEqual([5, 6]);
    expect(WIZARD_STEPS.map((s) => s.title)).toEqual([
      "Scenario", "Fatturato", "Costi", "Capitale circolante", "Patrimoniale pregresso", "Patrimoniale piano", "Imposte",
    ]);
  });
```
e nel test dei campi: `expect(seen.get("other_costs_growth_pct")).toBe("costi")`, `expect(seen.get("bank_lines_amount")).toBe("patrimoniale-pregresso")`, `expect(seen.get("tfr_payments")).toBe("patrimoniale-piano")`, `expect(seen.get("sp16g_growth_pct")).toBe("patrimoniale-piano")`, `expect(seen.get("inflation_pct")).toBe("scenario")`; nel test della navigazione: `stepForErrorMessage("Fabbisogno finanziario scoperto di …")` → `"patrimoniale-piano"`, `stepForErrorMessage("… al passo «Patrimoniale pregresso» …")` → `"patrimoniale-pregresso"`, `stepForErrorMessage("Liquidazioni TFR 2027: … Patrimoniale piano")` → `"patrimoniale-piano"`, `stepForErrorMessage("… al passo «Imposte» …")` → `"imposte"`; `stepLead("patrimoniale-pregresso", 2026)` → `"I saldi al 31/12/2026 e come si chiudono. Le voci a breve si liquidano nel primo anno del piano; quelle oltre 12 mesi le scadenzi tu, anno per anno."`.

In `frontend/lib/budget-horizon.test.ts`: aggiungere a `CHIAVI_ATTESE` le otto chiavi `"inflation_pct", "fixed_materials_growth_auto", "fixed_services_growth_auto", "bank_lines_amount", "bank_lines_rule", "bank_lines_rate", "other_lenders", "tfr_payments"` e portare l'atteso a `99`. Aggiungere:

```ts
  it("withOtherLenders scrive SEMPRE sul primo anno di piano e null svuota", () => {
    const map = asMap({ 2027: {}, 2028: {} });
    const out = withOtherLenders(map, [2027, 2028], [{ name: "Soci", opening_residual: 100, interest_rate: 0, repayments: [0, 50] }]);
    expect(out[2027].other_lenders).toEqual([{ name: "Soci", opening_residual: 100, interest_rate: 0, repayments: [0, 50] }]);
    expect(out[2028].other_lenders).toBeUndefined();
    expect(withOtherLenders(out, [2027, 2028], null)[2027].other_lenders).toBeNull();
  });
```
(`asMap` e' l'helper gia' presente nel file; se non c'e', `const asMap = (m: Record<number, Record<string, unknown>>) => m as unknown as AssumptionsMap;`).

- [ ] **Step 3: Rosso**

```bash
cd frontend && npx vitest run lib/budget-wizard-steps.test.ts lib/budget-horizon.test.ts
```
Atteso: rosso sulle chiavi dei passi e sull'elenco delle 99 chiavi.

- [ ] **Step 4: Tipi**

`frontend/types/api.ts`: in `FinancingLoanInput` → `duration_years?: number | null; repayments?: number[] | null;`; dopo di essa:

```ts
/** Un altro finanziatore (sp16b/sp17b) scadenziato per anno (spec 2026-09-15 §5.3). */
export interface OtherLenderInput {
  name?: string | null;
  opening_residual: number;
  interest_rate: number;
  /** Capitale rimborsato in ciascun anno di piano, indice 0 = primo anno. */
  repayments: number[];
}
```
`PregressoPlan.non_incassato?: boolean | null;`. Su `BudgetAssumptions` (dopo `previdenza_scales_with_personnel`) e su `BudgetAssumptionsCreate` (facoltativi):

```ts
  inflation_pct: number | null;
  fixed_materials_growth_auto: boolean;
  fixed_services_growth_auto: boolean;
  bank_lines_amount: number | null;
  bank_lines_rule: "costante" | "ricavi" | null;
  bank_lines_rate: number | null;
  other_lenders: OtherLenderInput[] | null;
  tfr_payments: number;
```
Su `ForecastYearDetails`:

```ts
  /** Il pareggio sul MOL, dichiarato dal motore (spec 2026-09-15 §4.3): tutto `null`
   *  quando la parte fissa/variabile non e' definita (override di ce05/ce06). */
  pareggio: PareggioDetail;
  tfr: TfrDetail;
  altri_finanziatori: AltriFinanziatoriDetail;
  oneri_fidi?: number;
  regime_debito_bancario?: "esplicito" | "contratti" | "anni" | "legacy";
```
con, sopra:

```ts
export interface PareggioDetail {
  costi_variabili: number | null; costi_fissi: number | null; costi_fissi_operativi: number | null;
  margine_contribuzione_pct: number | null; fatturato_pareggio: number | null;
  margine_sicurezza: number | null; margine_sicurezza_pct: number | null;
}
export interface TfrDetail { apertura: number; accantonamento: number; liquidazioni: number; chiusura: number; sospeso: boolean }
export interface AltriFinanziatoriContratto {
  indice: number; nome: string; residuo_iniziale: number; rimborso: number; interessi: number; residuo: number; breve: number; lungo: number;
}
export interface AltriFinanziatoriDetail {
  apertura: number; rimborso: number; interessi: number; breve: number; lungo: number;
  mode: "contratti" | "anni" | "legacy"; contratti: AltriFinanziatoriContratto[];
}
export interface DebitoBancarioFidi { apertura: number; variazione_ricavi: number; rimborso_sweep: number; residuo: number; regola: "costante" | "ricavi" }
```
e `DebitoBancarioAnno.fidi: DebitoBancarioFidi | null;`, `DebitoBancarioContratto.nome?: string | null` (il motore la scrive gia' se il contratto ha `name`: verificare in `_contratti_dell_anno`; se no, aggiungerla li' — una riga — nel Task 14, dove serve).

- [ ] **Step 5: Idratazione, default, setter**

`hydrateAssumptions`: dopo `previdenza_scales_with_personnel`:

```ts
      inflation_pct: a.inflation_pct ?? null,
      fixed_materials_growth_auto: a.fixed_materials_growth_auto ?? false,
      fixed_services_growth_auto: a.fixed_services_growth_auto ?? false,
      bank_lines_amount: a.bank_lines_amount ?? null,
      bank_lines_rule: a.bank_lines_rule ?? null,
      bank_lines_rate: a.bank_lines_rate ?? null,
      other_lenders: a.other_lenders ?? null,
      tfr_payments: a.tfr_payments ?? 0,
```
`defaultAssumption`: `inflation_pct: 2, fixed_materials_growth_auto: true, fixed_services_growth_auto: true, fixed_materials_growth_pct: 2, fixed_services_growth_pct: 2, bank_lines_amount: null, bank_lines_rule: null, bank_lines_rate: null, other_lenders: null, tfr_payments: 0` (i due `fixed_*_growth_pct` da 0 a 2: uno scenario nuovo parte dall'inflazione, spec §4.3; `financing_duration_years: 5` e `financing_interest_rate: 3` restano: il motore legge ancora i campi legacy). Aggiungere, accanto a `withPregresso`:

```ts
/** Gli altri finanziatori per anno vivono sulla riga del PRIMO anno di piano, come `pregresso`. */
export function withOtherLenders(
  current: AssumptionsMap, forecastYears: number[], next: OtherLenderInput[] | null,
): AssumptionsMap {
  const first = forecastYears[0];
  if (first === undefined) return current;
  const out: AssumptionsMap = { ...current, [first]: { ...current[first], other_lenders: next && next.length > 0 ? next : null } };
  for (const y of forecastYears.slice(1)) if (out[y]?.other_lenders != null) out[y] = { ...out[y], other_lenders: null };
  return out;
}
```
Nell'hook: `const updateOtherLenders = useCallback((next: OtherLenderInput[] | null) => setAssumptions((prev) => withOtherLenders(prev, forecastYears, next)), [forecastYears]);`, esportato e messo in `StepProps` e in `stepProps` di `BudgetWizard.tsx`.

- [ ] **Step 6: Passi**

`budget-wizard-steps.ts`:

```ts
export type WizardStepKey =
  | "scenario" | "fatturato" | "costi" | "circolante" | "patrimoniale-pregresso" | "patrimoniale-piano" | "imposte";

export interface WizardStep {
  n: number; key: WizardStepKey; title: string; subtitle: string;
  group: "Impostazione" | "Conto economico" | "Stato patrimoniale";
  /** «nuovo» sui due passi nati dal giro di rilievi del 14/09. */
  badge?: "nuovo";
}

export const WIZARD_STEPS: readonly WizardStep[] = [
  { n: 1, key: "scenario", title: "Scenario", subtitle: "nome, anno base, orizzonte, inflazione", group: "Impostazione" },
  { n: 2, key: "fatturato", title: "Fatturato", subtitle: "ricavi e altri ricavi", group: "Conto economico" },
  { n: 3, key: "costi", title: "Costi", subtitle: "quota fissa, inflazione, ipotesi manuali", group: "Conto economico" },
  { n: 4, key: "circolante", title: "Capitale circolante", subtitle: "giorni medi", group: "Stato patrimoniale" },
  { n: 5, key: "patrimoniale-pregresso", title: "Patrimoniale pregresso", subtitle: "come si chiude ciò che c'è già", group: "Stato patrimoniale", badge: "nuovo" },
  { n: 6, key: "patrimoniale-piano", title: "Patrimoniale piano", subtitle: "ciò che il previsionale genera", group: "Stato patrimoniale", badge: "nuovo" },
  { n: 7, key: "imposte", title: "Imposte", subtitle: "aliquota e pagamento", group: "Stato patrimoniale" },
];

export const STEP_FIELDS: Record<WizardStepKey, readonly string[]> = {
  scenario: ["inflation_pct"],
  fatturato: ["revenue_growth_pct", "other_revenue_growth_pct"],
  costi: [
    "fixed_materials_percentage", "fixed_services_percentage",
    "variable_materials_growth_pct", "variable_services_growth_pct",
    "fixed_materials_growth_pct", "fixed_services_growth_pct",
    "fixed_materials_growth_auto", "fixed_services_growth_auto",
    "personnel_growth_pct", "rent_growth_pct", "other_costs_growth_pct",
  ],
  circolante: ["dso_days", "dio_days", "dpo_days", "receivables_long_growth_pct"],
  "patrimoniale-pregresso": [
    "bank_lines_amount", "bank_lines_rule", "bank_lines_rate", "financing_loans", "other_lenders",
    "existing_debt_repayment_years", "altri_finanz_repayment_years",
  ],
  "patrimoniale-piano": [
    "sp01_growth_pct", "sp04_growth_pct", "sp06e_growth_pct", "sp06f_growth_pct",
    "sp08_growth_pct", "sp10_growth_pct", "sp14_growth_pct", "sp16f_growth_pct",
    "sp16g_growth_pct", "sp17d_growth_pct", "sp17f_growth_pct", "sp17g_growth_pct",
    "sp18_growth_pct", "previdenza_scales_with_personnel", "tfr_accrual_suspended", "tfr_payments",
    "financing_amount", "financing_duration_years", "financing_interest_rate",
    "tangible_investments", "intangible_investments", "depreciation_rate", "depreciation_rate_intangible",
    "asset_disposal_nbv", "asset_disposal_proceeds", "cash_sweep_enabled", "cash_sweep_min_cash",
    "overdraft_allowed", "overdraft_limit",
  ],
  imposte: ["tax_rate", "tax_advances_paid", "tax_temporary_differences", "sp16e_growth_pct", "sp17e_growth_pct"],
};
```
`stepLead` con i sette `<p class="lead">` del prototipo (anno base al posto del 2026; per il passo 5 la frase del test sopra; passo 6: «Ciò che il previsionale genera: voci minori, investimenti, nuova finanza. La cassa chiude il foglio.»; passo 3: «Quanto è fisso, e il resto segue da solo: la parte variabile cresce con i ricavi, la parte fissa con l'inflazione. A mano restano solo personale, godimento beni di terzi e oneri diversi.»; passo 2: «Quanto crescono i ricavi, anno per anno. È l'ipotesi principale del piano: tutto parte da 0 e lo decidi tu. La parte variabile dei costi segue questa curva senza altre ipotesi.»; passo 1 e 4 e 7 invariati). `stepForErrorMessage`:

```ts
export function stepForErrorMessage(message: string): WizardStepKey {
  if (/patrimoniale pregresso/i.test(message)) return "patrimoniale-pregresso";
  if (/patrimoniale piano|fabbisogno finanziario scoperto di|scoperto di conto corrente oltre il tetto|liquidazioni tfr/i.test(message))
    return "patrimoniale-piano";
  if (/passo\s*«?\s*imposte\b/i.test(message)) return "imposte";
  return "imposte";
}
```

- [ ] **Step 7: Regole di campo e catalogo del report**

`budget-field-rules.ts`: le regole dei campi scalari nuovi (se non gia' aggiunte al Task 1): `inflation_pct: pct({ min: -50, max: 100, nullable: true })`, `fixed_materials_growth_auto: bool`, `fixed_services_growth_auto: bool`, `bank_lines_amount: eur({ nullable: true })`, `bank_lines_rate: pct({ min: 0, max: 30, nullable: true })`, `tfr_payments: eur()`; il commento «Pregresso e nuovo» del gruppo diventa «Patrimoniale pregresso / piano». Se `budget-field-rules.test.ts` pretende una regola per OGNI voce di `STEP_FIELDS`, escludere `bank_lines_rule`, `other_lenders`, `financing_loans`, `tax_temporary_differences` come gia' fa per i campi non scalari (leggere il test).

`contracts/final_report_assumption_sections.json`: sette sezioni con chiavi, titoli e `fields` IDENTICI a `STEP_FIELDS` sopra (stesso ordine); `nested_fields`: `costi` → `["ce_overrides"]`, `patrimoniale-pregresso` → `["pregresso", "other_lenders"]`, `patrimoniale-piano` → `["sp_indexing", "sp_overrides"]`. `frontend/types/final-report.ts:12`: la union con le sette chiavi nuove. `AssumptionsCatalog.test.ts`: l'elenco delle chiavi (righe 28-36) e `sectionTitle("patrimoniale-pregresso", "Patrimoniale pregresso")`. `tests/test_final_report_contract.py:253`: la lista attesa delle sette chiavi nuove. Fixture `tests/fixtures/final_report/*.json`: in ogni `assumption_sections[]` rinominare `key`/`title` (`altre-voci-ce` si fonde in `costi`: le sue `assumptions` vanno in coda a quelle di `costi`; `pregresso-nuovo` diventa `patrimoniale-pregresso` e le assumptions di `financing_amount`, `financing_duration_years`, `financing_interest_rate`, `tangible_investments`, `intangible_investments`, `depreciation_rate*`, `asset_disposal_*`, `cash_sweep_*`, `overdraft_*` passano in una sezione nuova `patrimoniale-piano` insieme a quelle delle voci minori `sp*_growth_pct`, `previdenza_scales_with_personnel`, `tfr_accrual_suspended`, `sp_indexing`, `sp_overrides` prese da `circolante`). Poi:

```bash
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_final_report_contract.py tests/test_m1_05b_assumption_sections.py -q -p no:cacheprovider
```
Se un test fallisce su `source_hash`/`model_hash` di una fixture, ricalcolarli e riscriverli con:

```bash
/home/peter/DEV/budget/backend/venv/bin/python - <<'PY'
import json, sys
sys.path.insert(0, "backend")
from app.schemas.final_report import FinalReportModel
for name in ("bilancio", "startup", "infrannuale"):
    p = f"tests/fixtures/final_report/{name}.json"
    d = json.load(open(p, encoding="utf-8"))
    m = FinalReportModel.model_validate(d, context={"skip_hash_validation": True})
    d["source_hash"], d["model_hash"] = m.calculate_source_hash(), m.calculate_model_hash()
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2); open(p, "a").write("\n")
PY
```
(controllare prima, con `git diff`, che l'indentazione e il terminatore finale della fixture siano quelli di prima).

- [ ] **Step 8: Verde, tsc, commit**

```bash
cd frontend && npx vitest run lib/budget-wizard-steps.test.ts lib/budget-horizon.test.ts lib/budget-field-rules.test.ts components/final-report/AssumptionsCatalog.test.ts && npx tsc --noEmit
```
`tsc` fallira' su `BudgetWizard.tsx` (`altre-voci-ce` e `pregresso-nuovo` non esistono piu'): per questo task sostituire nel `switch` di `BudgetWizard.tsx` le due chiavi con `"patrimoniale-pregresso"` → `<StepPregressoNuovo …/>` (temporaneo, fino al Task 13) e `"patrimoniale-piano"` → `<StepPregressoNuovo …/>` (idem, fino al Task 15), togliendo il ramo di `StepAltreVociCE` (il file resta fino al Task 11). Poi `tsc` pulito e vitest verde.

```bash
git add frontend/types/api.ts frontend/lib/budget-horizon.ts frontend/lib/budget-horizon.test.ts frontend/lib/budget-wizard-steps.ts frontend/lib/budget-wizard-steps.test.ts frontend/lib/budget-field-rules.ts frontend/hooks/use-scenario-assumptions.ts frontend/components/budget/wizard/types.ts frontend/components/budget/wizard/BudgetWizard.tsx contracts/final_report_assumption_sections.json frontend/types/final-report.ts frontend/components/final-report/AssumptionsCatalog.test.ts tests/test_final_report_contract.py tests/fixtures/final_report/bilancio.json tests/fixtures/final_report/startup.json tests/fixtures/final_report/infrannuale.json
git commit -m "feat(ipotesi): sette passi nuovi nel client, campi idratati e catalogo del report allineato"
```

---

### Task 9: Migrazione degli scenari salvati (`budget-migrazione.ts`), card e badge

**Files:**
- Create: `frontend/lib/budget-migrazione.ts`, `frontend/lib/budget-migrazione.test.ts`
- Create: `frontend/components/budget/wizard/MigrazioneCard.tsx`
- Modify: `frontend/hooks/use-scenario-assumptions.ts:130-160` (dopo `hydrateAssumptions`), `frontend/components/budget/wizard/BudgetWizard.tsx`, `frontend/components/budget/wizard/WizardRail.tsx`

**Interfaces:**
- Consumes: `AssumptionsMap`, `baseBankDebt` (`lib/base-bank-debt.ts`), `withOtherLenders` (Task 8)
- Produces:
  ```ts
  export interface EsitoMigrazione { map: AssumptionsMap; ricalcolato: string[]; daIntegrare: { step: WizardStepKey; testo: string }[] }
  export function isScenarioPrecedente(map: AssumptionsMap, forecastYears: number[]): boolean  // inflation_pct null sul primo anno
  export function migraScenario(map: AssumptionsMap, forecastYears: number[], baseBs: Record<string, unknown> | null | undefined, baseYear: number): EsitoMigrazione
  ```
  `ScenarioAssumptionsState.migrazione: EsitoMigrazione | null` (null se non e' uno scenario precedente o dopo il primo salvataggio); `WizardRail` prop `badges: Partial<Record<WizardStepKey, "nuovo" | "da integrare">>`.

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task9-base
```

- [ ] **Step 2: Test rosso**

`frontend/lib/budget-migrazione.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { isScenarioPrecedente, migraScenario } from "./budget-migrazione";

const anni = [2027, 2028, 2029];
const base = {
  sp16_debiti_breve: "500000", sp16a_debiti_banche_breve: "172500", sp16d_debiti_fornitori_breve: "327500",
  sp17_debiti_lungo: "617500", sp17a_debiti_banche_lungo: "467500", sp17b_debiti_altri_finanz_lungo: "150000",
};
const vecchio = (over: Record<string, unknown> = {}): AssumptionsMap => {
  const out: AssumptionsMap = {};
  for (const y of anni) out[y] = {
    forecast_year: y, revenue_growth_pct: 5, variable_materials_growth_pct: 3, variable_services_growth_pct: 3,
    fixed_materials_growth_pct: 3, fixed_services_growth_pct: 2.5, inflation_pct: null,
    existing_debt_repayment_years: 4, altri_finanz_repayment_years: 5, financing_amount: y === 2028 ? 200000 : 0,
    financing_duration_years: 5, financing_interest_rate: 4, financing_loans: null, pregresso: null, ...over,
  } as AssumptionsMap[number];
  return out;
};

describe("budget-migrazione", () => {
  it("riconosce uno scenario precedente dall'inflazione assente sul primo anno", () => {
    expect(isScenarioPrecedente(vecchio(), anni)).toBe(true);
    expect(isScenarioPrecedente(vecchio({ inflation_pct: 2 }), anni)).toBe(false);
    expect(isScenarioPrecedente({}, anni)).toBe(false);
  });

  it("ricalcola le variabili sui ricavi e tiene le fisse come scritte", () => {
    const { map, ricalcolato } = migraScenario(vecchio(), anni, base, 2026);
    for (const y of anni) {
      expect(map[y].variable_materials_growth_pct).toBe(5);
      expect(map[y].variable_services_growth_pct).toBe(5);
      expect(map[y].fixed_materials_growth_pct).toBe(3);
      expect(map[y].fixed_materials_growth_auto).toBe(false);
      expect(map[y].inflation_pct).toBe(2);
    }
    expect(ricalcolato.some((r) => r.includes("parte variabile"))).toBe(true);
  });

  it("converte «rimborso in N anni» in un contratto con rate uguali e gli altri finanziatori allo stesso modo", () => {
    const { map } = migraScenario(vecchio(), anni, base, 2026);
    const [contratto] = map[2027].financing_loans ?? [];
    expect(contratto).toEqual({
      name: "Debiti verso banche · da «rimborso in 4 anni»", amount: 0, opening_residual: 640000,
      interest_rate: 4, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [160000, 160000, 160000],
    });
    expect(map[2027].existing_debt_repayment_years).toBeNull();
    expect(map[2027].bank_lines_amount).toBe(0);
    expect(map[2027].bank_lines_rule).toBe("costante");
    expect(map[2027].bank_lines_rate).toBe(4);
    expect(map[2027].other_lenders).toEqual([
      { name: "Altri finanziatori · da «rimborso in 5 anni»", opening_residual: 150000, interest_rate: 0, repayments: [30000, 30000, 30000] },
    ]);
    expect(map[2027].altri_finanz_repayment_years).toBeNull();
  });

  it("converte il finanziamento legacy dell'anno in un contratto nuovo con nome", () => {
    const { map } = migraScenario(vecchio(), anni, base, 2026);
    expect(map[2028].financing_loans).toEqual([
      { name: "Nuovo finanziamento 2028", amount: 200000, opening_residual: 0, duration_years: 5, interest_rate: 4, grace_years: 0, balloon_pct: 0 },
    ]);
    expect(map[2028].financing_amount).toBe(0);
  });

  it("segnala da integrare i passi 1 e 5", () => {
    const { daIntegrare } = migraScenario(vecchio(), anni, base, 2026);
    expect(daIntegrare.map((d) => d.step)).toEqual(["scenario", "patrimoniale-pregresso", "patrimoniale-pregresso"]);
  });

  it("senza debito bancario né altri finanziatori non inventa contratti", () => {
    const { map } = migraScenario(vecchio(), anni, { ...base, sp16a_debiti_banche_breve: "0", sp17a_debiti_banche_lungo: "0", sp16_debiti_breve: "327500", sp17_debiti_lungo: "150000" }, 2026);
    expect(map[2027].financing_loans).toBeNull();
    expect(map[2027].bank_lines_amount).toBe(0);
  });
});
```

- [ ] **Step 3: Rosso**

```bash
cd frontend && npx vitest run lib/budget-migrazione.test.ts
```
Atteso: modulo mancante (primo rosso); poi rosso sulle asserzioni una volta creato lo scheletro.

- [ ] **Step 4: Modulo**

`frontend/lib/budget-migrazione.ts`:

```ts
/**
 * La migrazione in memoria di uno scenario salvato PRIMA del giro di rilievi del 14/09
 * (spec 2026-09-15 §4.8, decisione 1). Modulo puro: nessun import da `app/` o `components/`.
 *
 * Ricalcola cio' che si puo' (parte variabile sui ricavi, «rimborso in N anni» in contratti per
 * anno, finanziamento legacy in contratto nuovo) e DICHIARA cio' che serve dall'utente. La mappa
 * restituita e' sporca: l'anteprima gira su quella, e si persiste al primo salvataggio.
 */
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { withOtherLenders } from "@/lib/budget-horizon";
import type { WizardStepKey } from "@/lib/budget-wizard-steps";
import { baseBankDebt } from "@/lib/base-bank-debt";
import { num } from "@/lib/budget-format";
import type { FinancingLoanInput, OtherLenderInput } from "@/types/api";

export const INFLAZIONE_PREDEFINITA = 2;

export interface EsitoMigrazione {
  map: AssumptionsMap;
  ricalcolato: string[];
  daIntegrare: { step: WizardStepKey; testo: string }[];
}

export function isScenarioPrecedente(map: AssumptionsMap, forecastYears: number[]): boolean {
  const first = forecastYears[0];
  if (first === undefined || !map[first]) return false;
  return map[first].inflation_pct === null || map[first].inflation_pct === undefined;
}

/** Rate uguali su `n` anni, troncate all'orizzonte: oltre l'orizzonte il residuo resta aperto. */
export function rateUguali(totale: number, anni: number, orizzonte: number): number[] {
  if (totale <= 0 || anni <= 0) return Array.from({ length: orizzonte }, () => 0);
  const rata = Math.round((totale / anni) * 100) / 100;
  return Array.from({ length: orizzonte }, (_, i) => (i < anni ? rata : 0));
}

export function migraScenario(
  map: AssumptionsMap, forecastYears: number[], baseBs: Record<string, unknown> | null | undefined, baseYear: number,
): EsitoMigrazione {
  const first = forecastYears[0];
  const out: AssumptionsMap = {};
  const ricalcolato: string[] = [];
  const daIntegrare: EsitoMigrazione["daIntegrare"] = [];
  let variabiliCambiate = false;
  let finanziamentiConvertiti = 0;

  for (const y of forecastYears) {
    const r = { ...map[y] };
    const rev = num(r.revenue_growth_pct ?? 0);
    if (num(r.variable_materials_growth_pct ?? 0) !== rev || num(r.variable_services_growth_pct ?? 0) !== rev) variabiliCambiate = true;
    r.variable_materials_growth_pct = rev;
    r.variable_services_growth_pct = rev;
    r.fixed_materials_growth_auto = false;
    r.fixed_services_growth_auto = false;
    r.inflation_pct = INFLAZIONE_PREDEFINITA;
    r.tfr_payments = r.tfr_payments ?? 0;
    const amt = num(r.financing_amount ?? 0), dur = num(r.financing_duration_years ?? 0);
    if (amt > 0 && dur > 0) {
      const nuovo: FinancingLoanInput = {
        name: `Nuovo finanziamento ${y}`, amount: amt, opening_residual: 0, duration_years: dur,
        interest_rate: num(r.financing_interest_rate ?? 0), grace_years: 0, balloon_pct: 0,
      };
      r.financing_loans = [...(r.financing_loans ?? []), nuovo];
      r.financing_amount = 0;
      finanziamentiConvertiti += 1;
    }
    out[y] = r;
  }
  if (variabiliCambiate) ricalcolato.push("Parte variabile di materie prime e servizi: le vecchie percentuali sono sostituite dalla crescita dei ricavi.");
  ricalcolato.push("Parte fissa: le vecchie percentuali restano, perché sono già un'ipotesi scritta dall'utente.");
  if (finanziamentiConvertiti > 0) ricalcolato.push(`Nuovo finanziamento: ${finanziamentiConvertiti === 1 ? "la riga legacy è diventata un contratto con nome" : `le ${finanziamentiConvertiti} righe legacy sono diventate contratti con nome`}.`);
  ricalcolato.push("Ricavi, personale, godimento e oneri diversi: tenuti come erano salvati.");

  if (first !== undefined && out[first]) {
    const p = out[first];
    const debito = baseBankDebt(baseBs);
    const breve = num(baseBs?.sp16a_debiti_banche_breve);
    const anniBanca = num(p.existing_debt_repayment_years ?? 0);
    const haContratti = (p.financing_loans ?? []).some((l) => num(l.opening_residual) > 0);
    p.bank_lines_amount = 0;
    p.bank_lines_rule = "costante";
    p.bank_lines_rate = num(p.financing_interest_rate ?? 0) || null;
    if (debito > 0 && !haContratti) {
      const contratto: FinancingLoanInput = {
        name: anniBanca > 0 ? `Debiti verso banche · da «rimborso in ${anniBanca} anni»` : "Debiti verso banche",
        amount: 0, opening_residual: debito, interest_rate: num(p.financing_interest_rate ?? 0),
        grace_years: 0, balloon_pct: 0, duration_years: null,
        repayments: rateUguali(debito, anniBanca, forecastYears.length),
      };
      p.financing_loans = [contratto, ...(p.financing_loans ?? [])];
      ricalcolato.push(anniBanca > 0
        ? `«Rimborso in ${anniBanca} anni» delle banche: convertito in un finanziamento, con rimborsi uguali per anno.`
        : "Debiti verso banche: un solo finanziamento senza rimborsi nel piano, da scadenziare.");
      daIntegrare.push({ step: "patrimoniale-pregresso", testo: `Debiti verso banche: dividi i ${breve.toLocaleString("it-IT")} € a breve fra fidi e anticipi (si rinnovano) e quota dei mutui; il resto è un solo finanziamento da ${debito.toLocaleString("it-IT")} €, da spacchettare nei contratti veri o confermare.` });
    }
    p.existing_debt_repayment_years = null;
    const altri = num(baseBs?.sp16b_debiti_altri_finanz_breve) + num(baseBs?.sp17b_debiti_altri_finanz_lungo);
    const anniAltri = num(p.altri_finanz_repayment_years ?? 0);
    if (altri > 0) {
      const voce: OtherLenderInput = {
        name: anniAltri > 0 ? `Altri finanziatori · da «rimborso in ${anniAltri} anni»` : "Altri finanziatori",
        opening_residual: altri, interest_rate: 0, repayments: rateUguali(altri, anniAltri, forecastYears.length),
      };
      Object.assign(out, withOtherLenders(out, forecastYears, [voce]));
      if (anniAltri > 0) ricalcolato.push(`«Rimborso in ${anniAltri} anni» degli altri finanziatori: convertito in un finanziatore con rimborsi uguali per anno.`);
    }
    out[first].altri_finanz_repayment_years = null;
    daIntegrare.unshift({ step: "scenario", testo: "Inflazione attesa: il vecchio scenario non la salvava; è impostata al 2%." });
    if (!p.pregresso) daIntegrare.push({ step: "patrimoniale-pregresso", testo: "Voci oltre 12 mesi: il vecchio scenario non le scadenziava. Verifica se tributari rateizzati, altri debiti e crediti hanno movimenti nel piano, o restano aperti." });
  }
  ricalcolato.push(`Il previsionale cambierà al prossimo salvataggio: CE Prev. e SP Prev. mostrano ancora quello calcolato sul bilancio ${baseYear}.`);
  return { map: out, ricalcolato, daIntegrare };
}
```
(Il test «senza debito bancario…» pretende `financing_loans` `null` quando non c'e' debito: con `debito === 0` il ramo non aggiunge nulla e `p.financing_loans` resta `null`. Il test sul contratto pretende `interest_rate: 4` e `bank_lines_rate: 4`: vengono da `financing_interest_rate` della prima riga.)

- [ ] **Step 5: Hook, card e badge**

Nell'hook, dopo `const assumptionsMap = hydrateAssumptions(data, scenarioId);` (riga 142): se `isScenarioPrecedente(assumptionsMap, years)` (gli anni previsti calcolati li' accanto) → `const esito = migraScenario(assumptionsMap, forecastYearsIdratati, historicalData[baseYear]?.balance as unknown as Record<string, unknown>, baseYear)`; usare `esito.map` come mappa idratata e `setMigrazione(esito)`; altrimenti `setMigrazione(null)`. Attenzione: `historicalData` arriva da un effetto separato — se al momento dell'idratazione il bilancio base non e' ancora caricato, la migrazione va rimandata: tenere `migrazioneInAttesa = true` e farla in un effetto su `[idratato, historicalData]` una volta sola (stesso schema del vecchio `seeded.current`). `migrazione` torna `null` dopo un salvataggio riuscito: `BudgetWizard.save` chiama `s.chiudiMigrazione()` (setter esposto) dentro `if (esito.ok)`.

`MigrazioneCard.tsx`: una `Card` a due colonne (`grid gap-0 md:grid-cols-2`), sinistra «ricalcolato · All'apertura» con `<ul>` di `ricalcolato`, destra «da integrare · Serve il tuo intervento» con `<ul>` di `daIntegrare` e un `<Button variant="link" size="sm" onClick={() => onGo(step)}>Passo N</Button>` per voce (N da `WIZARD_STEPS`). Resa in `BudgetWizard.tsx` sotto il `WizardRail` quando `s.migrazione` non e' `null`.

`WizardRail.tsx`: prop `badges: Partial<Record<WizardStepKey, "nuovo" | "da integrare">>`; accanto al titolo del passo un `<Badge variant="outline" className="ml-1 px-1 py-0 text-[9px]">` con il testo; «da integrare» in ambra (`text-amber-700 dark:text-amber-300 border-amber-400`), «nuovo» in viola (`text-violet-700 dark:text-violet-300 border-violet-400`). `BudgetWizard` compone i badge: `"nuovo"` da `WIZARD_STEPS[].badge`, sovrascritto da `"da integrare"` per gli `step` di `s.migrazione?.daIntegrare`. La funzione che compone i badge e' pura e sta in `budget-wizard-steps.ts`:

```ts
export function railBadges(daIntegrare: readonly WizardStepKey[]): Partial<Record<WizardStepKey, "nuovo" | "da integrare">> {
  const out: Partial<Record<WizardStepKey, "nuovo" | "da integrare">> = {};
  for (const s of WIZARD_STEPS) if (s.badge) out[s.key] = s.badge;
  for (const k of daIntegrare) out[k] = "da integrare";
  return out;
}
```
con un test in `budget-wizard-steps.test.ts`: `expect(railBadges(["scenario"])).toEqual({ scenario: "da integrare", "patrimoniale-pregresso": "nuovo", "patrimoniale-piano": "nuovo" })`.

- [ ] **Step 6: Verde, tsc, commit**

```bash
cd frontend && npx vitest run lib/budget-migrazione.test.ts lib/budget-wizard-steps.test.ts && npx tsc --noEmit
git add frontend/lib/budget-migrazione.ts frontend/lib/budget-migrazione.test.ts frontend/lib/budget-wizard-steps.ts frontend/lib/budget-wizard-steps.test.ts frontend/components/budget/wizard/MigrazioneCard.tsx frontend/hooks/use-scenario-assumptions.ts frontend/components/budget/wizard/BudgetWizard.tsx frontend/components/budget/wizard/WizardRail.tsx
git commit -m "feat(ipotesi): migrazione in memoria degli scenari salvati prima, con card e badge"
```

---

### Task 10: Passi 1 e 2: inflazione salvata, niente seme, write-through sui variabili

**Files:**
- Create: `frontend/lib/budget-inflazione.ts`, `frontend/lib/budget-inflazione.test.ts`
- Modify: `frontend/lib/budget-horizon.ts` (`withRevenueGrowth`), `frontend/lib/budget-horizon.test.ts`
- Modify: `frontend/hooks/use-scenario-assumptions.ts:210-218` (`updateAssumption`), effetto dei default
- Modify: `frontend/components/budget/wizard/steps/StepScenario.tsx`, `frontend/components/budget/wizard/steps/StepFatturato.tsx`, `frontend/components/budget/wizard/BudgetWizard.tsx` (via lo stato `inflation`)
- Modify: `frontend/lib/budget-trend.ts` (via `shouldSeedTrend`, `trendAssumptions`; resta `calculateTrend`, `TREND_ITEMS`, `blendedRate` per la tabella di riferimento), `frontend/lib/budget-trend.test.ts`

**Interfaces:**
- Produces:
  ```ts
  // budget-inflazione.ts
  export function inflazioneOf(map: AssumptionsMap, years: number[]): number          // primo anno, 2 se null
  export function withInflazione(map: AssumptionsMap, years: number[], v: number): AssumptionsMap  // scrive inflation_pct su ogni anno E riallinea le caselle auto
  export function applicaInflazioneAlleAuto(map: AssumptionsMap, years: number[]): AssumptionsMap // identita' se nulla cambia
  export function trendRicaviNota(historicalYears: number[], historical: HistoricalData): string | null
  // budget-horizon.ts
  export function withRevenueGrowth(map: AssumptionsMap, year: number, value: number | null): AssumptionsMap // scrive ricavi + le due variabili
  ```

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task10-base
```

- [ ] **Step 2: Test rosso**

`frontend/lib/budget-inflazione.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { applicaInflazioneAlleAuto, inflazioneOf, trendRicaviNota, withInflazione } from "./budget-inflazione";

const anni = [2027, 2028];
const m = (over: Record<number, Record<string, unknown>>): AssumptionsMap => over as unknown as AssumptionsMap;

describe("budget-inflazione", () => {
  it("legge l'inflazione dal primo anno, 2 quando manca", () => {
    expect(inflazioneOf(m({ 2027: { inflation_pct: 3 }, 2028: { inflation_pct: 3 } }), anni)).toBe(3);
    expect(inflazioneOf(m({ 2027: { inflation_pct: null } }), anni)).toBe(2);
    expect(inflazioneOf({}, anni)).toBe(2);
  });
  it("withInflazione scrive ogni anno e riallinea solo le caselle automatiche", () => {
    const out = withInflazione(m({
      2027: { fixed_materials_growth_pct: 2, fixed_materials_growth_auto: true, fixed_services_growth_pct: 1, fixed_services_growth_auto: false },
      2028: { fixed_materials_growth_pct: 2, fixed_materials_growth_auto: true, fixed_services_growth_pct: 2, fixed_services_growth_auto: true },
    }), anni, 3.5);
    expect(out[2027]).toMatchObject({ inflation_pct: 3.5, fixed_materials_growth_pct: 3.5, fixed_services_growth_pct: 1 });
    expect(out[2028]).toMatchObject({ inflation_pct: 3.5, fixed_materials_growth_pct: 3.5, fixed_services_growth_pct: 3.5 });
  });
  it("applicaInflazioneAlleAuto restituisce la mappa ricevuta quando nulla cambia", () => {
    const map = m({ 2027: { inflation_pct: 2, fixed_materials_growth_pct: 2, fixed_materials_growth_auto: true, fixed_services_growth_pct: 2, fixed_services_growth_auto: true } });
    expect(applicaInflazioneAlleAuto(map, [2027])).toBe(map);
  });
  it("la nota sulla tendenza dei ricavi c'e' solo con due anni storici", () => {
    const hist = { 2025: { income: { ce01_ricavi_vendite: "2000" } }, 2026: { income: { ce01_ricavi_vendite: "2120" } } } as never;
    expect(trendRicaviNota([2025, 2026], hist)).toBe("Per riferimento: tendenza storica 2025-2026 dei ricavi +6,0% annuo. Non viene applicata.");
    expect(trendRicaviNota([2026], hist)).toBeNull();
  });
});
```
In `budget-horizon.test.ts`:

```ts
  it("withRevenueGrowth scrive i ricavi e le due parti variabili dello stesso anno", () => {
    const out = withRevenueGrowth(asMap({ 2027: {}, 2028: { revenue_growth_pct: 1 } }), 2027, 4);
    expect(out[2027]).toMatchObject({ revenue_growth_pct: 4, variable_materials_growth_pct: 4, variable_services_growth_pct: 4 });
    expect(out[2028].revenue_growth_pct).toBe(1);
    expect(withRevenueGrowth(out, 2027, null)[2027]).toMatchObject({ revenue_growth_pct: null, variable_materials_growth_pct: 0, variable_services_growth_pct: 0 });
  });
```

- [ ] **Step 3: Rosso**

```bash
cd frontend && npx vitest run lib/budget-inflazione.test.ts lib/budget-horizon.test.ts
```

- [ ] **Step 4: Moduli**

`frontend/lib/budget-inflazione.ts`:

```ts
/**
 * L'inflazione attesa del passo 1 e le caselle «automatiche» della parte fissa del passo 3
 * (spec 2026-09-15 §4.1, §4.3, decisione 2). Modulo puro.
 *
 * Una casella e' automatica (`fixed_*_growth_auto`) finche' l'utente non la scrive: segue
 * l'inflazione, e cambia con lei. Il motore legge SOLO `fixed_*_growth_pct`: il flag e' un
 * marcatore del client, persistito perche' lo scenario si riapra come era.
 */
import type { AssumptionsMap } from "@/lib/budget-horizon";
import { calculateTrend, type HistoricalData } from "@/lib/budget-trend";
import { num } from "@/lib/budget-format";

export const INFLAZIONE_PREDEFINITA = 2;

export function inflazioneOf(map: AssumptionsMap, years: number[]): number {
  const raw = years[0] !== undefined ? map[years[0]]?.inflation_pct : null;
  return raw === null || raw === undefined ? INFLAZIONE_PREDEFINITA : num(raw);
}

export function applicaInflazioneAlleAuto(map: AssumptionsMap, years: number[]): AssumptionsMap {
  const infl = inflazioneOf(map, years);
  let out: AssumptionsMap | null = null;
  for (const y of years) {
    const r = map[y];
    if (!r) continue;
    const patch: Record<string, unknown> = {};
    if (r.fixed_materials_growth_auto && num(r.fixed_materials_growth_pct ?? 0) !== infl) patch.fixed_materials_growth_pct = infl;
    if (r.fixed_services_growth_auto && num(r.fixed_services_growth_pct ?? 0) !== infl) patch.fixed_services_growth_pct = infl;
    if (Object.keys(patch).length === 0) continue;
    out ??= { ...map };
    out[y] = { ...r, ...patch };
  }
  return out ?? map;
}

export function withInflazione(map: AssumptionsMap, years: number[], v: number): AssumptionsMap {
  const out: AssumptionsMap = { ...map };
  for (const y of years) if (out[y]) out[y] = { ...out[y], inflation_pct: v };
  return applicaInflazioneAlleAuto(out, years);
}

export function trendRicaviNota(historicalYears: number[], historical: HistoricalData): string | null {
  if (historicalYears.length < 2) return null;
  const y1 = historicalYears[historicalYears.length - 2], y2 = historicalYears[historicalYears.length - 1];
  const t = calculateTrend(historical, y1, y2, (i) => parseFloat(i.ce01_ricavi_vendite));
  if (t === null) return null;
  const pct = `${t >= 0 ? "+" : ""}${t.toLocaleString("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  return `Per riferimento: tendenza storica ${y1}-${y2} dei ricavi ${pct} annuo. Non viene applicata.`;
}
```
In `budget-horizon.ts`:

```ts
/** I ricavi trascinano la parte variabile di materie e servizi (spec 2026-09-15 §4.2): il
 *  motore non cambia, le due percentuali seguono i ricavi per costruzione. */
export function withRevenueGrowth(map: AssumptionsMap, year: number, value: number | null): AssumptionsMap {
  const v = value === null ? 0 : value;
  return { ...map, [year]: { ...map[year], revenue_growth_pct: value, variable_materials_growth_pct: v, variable_services_growth_pct: v } };
}
```
Nell'hook: `updateAssumption` → `if (field === "revenue_growth_pct") return setAssumptions((prev) => withRevenueGrowth(prev, year, value as number | null));` prima del ramo generico; `updateAll("inflation_pct", v)` → intercettato allo stesso modo con `withInflazione(prev, forecastYears, v as number)`. Nell'effetto dei default (riga ~200) avvolgere: `applicaInflazioneAlleAuto(withPregressoTrimmedToHorizon(withDefaultsForYears(...), forecastYears), forecastYears)` — restituisce la mappa ricevuta quando nulla cambia, quindi l'effetto non riparte.

- [ ] **Step 5: Componenti**

`StepScenario.tsx`: togliere `inflation`/`setInflation` dalle props (e da `BudgetWizard.tsx` lo `useState(2)`), leggere `const inflazione = inflazioneOf(assumptions, forecastYears)` e scrivere con `updateAll("inflation_pct", v)`; togliere `applyTrendToAssumptions`, l'effetto del seed, `seeded`, il pulsante «Riparti dalla tendenza» e il dialogo che lo conferma; la tabella della tendenza resta, con la didascalia «Solo per riferimento: il piano parte da 0 al passo 2» (le colonne `rates` calcolate con `blendedRate` si tolgono: mostrare la sola colonna «tendenza 2024-2026»). Sotto l'inflazione la nota del prototipo: «Precompila la crescita della parte fissa di materie prime e servizi (passo 3), dove puoi correggerla anno per anno. L'inflazione non tocca i ricavi: le ipotesi sul fatturato le scrivi al passo 2, partendo da 0.»

`StepFatturato.tsx`: sotto la nota esistente, `{nota && <p className="mt-1 text-xs text-muted-foreground">{nota}</p>}` con `const nota = useMemo(() => trendRicaviNota(p.historicalYears, p.historical), [p.historicalYears, p.historical])`.

`budget-trend.ts`: rimuovere `shouldSeedTrend` e `trendAssumptions` (e i loro test in `budget-trend.test.ts`); `grep -rn "shouldSeedTrend\|trendAssumptions" frontend/` deve restare vuoto (se `app/budget/page.tsx` — non committato, di un altro lotto — le usa, NON toccarlo: lasciare le due funzioni esportate e segnalarlo nel commit).

- [ ] **Step 6: Verde, tsc, commit**

```bash
cd frontend && npx vitest run lib/budget-inflazione.test.ts lib/budget-horizon.test.ts lib/budget-trend.test.ts && npx tsc --noEmit
git add frontend/lib/budget-inflazione.ts frontend/lib/budget-inflazione.test.ts frontend/lib/budget-horizon.ts frontend/lib/budget-horizon.test.ts frontend/lib/budget-trend.ts frontend/lib/budget-trend.test.ts frontend/hooks/use-scenario-assumptions.ts frontend/components/budget/wizard/steps/StepScenario.tsx frontend/components/budget/wizard/steps/StepFatturato.tsx frontend/components/budget/wizard/BudgetWizard.tsx
git commit -m "feat(ipotesi): inflazione salvata, nessun seme dalla tendenza, variabili che seguono i ricavi"
```

---

### Task 11: Passo 3 Costi: tabella nuova, pareggio, CE fino all'ante imposte

**Files:**
- Create: `frontend/lib/budget-pareggio.ts`, `frontend/lib/budget-pareggio.test.ts`
- Modify: `frontend/lib/budget-costi-step.ts` (`costiTableRows`, `calcolateAltrove`, `fixedGrowthChange`), `frontend/lib/budget-costi-step.test.ts`
- Modify: `frontend/lib/budget-preview-rows.ts` (`rowsCosti` etichette, nuova `rowsCeAnteImposte`), `frontend/lib/budget-preview-rows.test.ts`
- Modify: `frontend/components/budget/wizard/YearInputTable.tsx` (`autoYears`), `frontend/components/budget/wizard/steps/StepCosti.tsx`
- Delete: `frontend/components/budget/wizard/steps/StepAltreVociCE.tsx`, `frontend/lib/budget-altre-voci-step.ts`, `frontend/lib/budget-altre-voci-step.test.ts`

**Interfaces:**
- Consumes: `details.pareggio` (Task 6), `inflazioneOf` (Task 10)
- Produces:
  ```ts
  // budget-pareggio.ts
  export interface PareggioBarra { year: number; ricaviPct: number; pareggioPct: number; margineDaPct: number; margineAPct: number; ok: boolean; margine: number | null; marginePct: number | null; nd: boolean }
  export function pareggioBarre(years: ForecastPreviewYear[]): PareggioBarra[]
  export function pareggioFormula(first: ForecastPreviewYear | undefined): { anno: number; righe: { testo: string; calcolo: string }[] } | null
  export function rowsPareggio(years: ForecastPreviewYear[]): PreviewRow[]
  // budget-costi-step.ts
  export function fixedGrowthChange(raw: number | null, inflazione: number): { value: number; auto: boolean }
  export function autoYearsOf(map: AssumptionsMap, years: number[], field: "fixed_materials_growth_auto" | "fixed_services_growth_auto"): number[]
  export function calcolateAltrove(baseYear: number): { label: string; small: string; passo: string }[]
  // budget-preview-rows.ts
  export function rowsCeAnteImposte(baseInc: IncomeStatement, years: ForecastPreviewYear[]): PreviewRow[]
  ```
  `YearInputRow.autoYears?: number[]` e `autoNote?: string` (cella azzurra, `title` = nota).

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task11-base
```

- [ ] **Step 2: Test rosso**

`frontend/lib/budget-pareggio.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { ForecastPreviewYear } from "@/types/api";
import { pareggioBarre, pareggioFormula, rowsPareggio } from "./budget-pareggio";

const anno = (year: number, pareggio: Record<string, number | null>, ce01 = 600000): ForecastPreviewYear => ({
  year, income_statement: { ce01_ricavi_vendite: ce01, ce04_altri_ricavi: 0 }, balance_sheet: {},
  details: { pareggio } as never,
} as unknown as ForecastPreviewYear);
const ok = { costi_variabili: 210000, costi_fissi: 275000, costi_fissi_operativi: 275000, margine_contribuzione_pct: 65, fatturato_pareggio: 423076.92, margine_sicurezza: 176923.08, margine_sicurezza_pct: 29.49 };
const nd = { costi_variabili: null, costi_fissi: null, costi_fissi_operativi: null, margine_contribuzione_pct: null, fatturato_pareggio: null, margine_sicurezza: null, margine_sicurezza_pct: null };

describe("budget-pareggio", () => {
  it("le barre: ricavi, tacca del pareggio e segmento del margine, sulla scala del massimo", () => {
    const [b] = pareggioBarre([anno(2027, ok)]);
    expect(b.ok).toBe(true);
    expect(b.ricaviPct).toBeCloseTo(100 / 1.04, 2);
    expect(b.pareggioPct).toBeCloseTo(423076.92 / 624000 * 100, 2);
    expect(b.margineDaPct).toBe(b.pareggioPct);
    expect(b.margineAPct).toBe(b.ricaviPct);
    expect(b.marginePct).toBe(29.49);
  });
  it("sotto il pareggio il segmento va dai ricavi alla tacca e ok e' falso", () => {
    const [b] = pareggioBarre([anno(2027, { ...ok, fatturato_pareggio: 700000, margine_sicurezza: -100000, margine_sicurezza_pct: -16.67 })]);
    expect(b.ok).toBe(false);
    expect(b.margineDaPct).toBe(b.ricaviPct);
    expect(b.margineAPct).toBe(b.pareggioPct);
  });
  it("un anno non definito e' marcato nd", () => {
    const [b] = pareggioBarre([anno(2027, nd)]);
    expect(b.nd).toBe(true);
    expect(rowsPareggio([anno(2027, nd)]).find((r) => r.key === "pareggio")?.years[0].note).toBe("Non definito: materie prime o servizi forzati in CE Prev.");
  });
  it("la formula dell'anno 1", () => {
    const f = pareggioFormula(anno(2027, ok));
    expect(f?.anno).toBe(2027);
    expect(f?.righe[0]).toEqual({ testo: "Margine di contribuzione % = (ricavi − costi variabili) / ricavi", calcolo: "(600.000 − 210.000) / 600.000 = 65,0%" });
    expect(f?.righe[2].calcolo).toBe("275.000 / 65,0% = 423.077");
    expect(pareggioFormula(anno(2027, nd))).toBeNull();
  });
  it("le righe della tabella", () => {
    const rows = rowsPareggio([anno(2027, ok)]);
    expect(rows.map((r) => r.key)).toEqual(["ricavi", "mdc", "pareggio", "margine-pct", "margine"]);
    expect(rows[2].years[0].value).toBe(423076.92);
  });
});
```
In `budget-costi-step.test.ts` sostituire i test di `costiTableRows` con:

```ts
  it("due gruppi: parte fissa (con anni automatici) e ipotesi manuali", () => {
    const rows = costiTableRows({ mat: 1000, serv: 500, pers: 300, god: 100, od: 50 }, { value: 40, uneven: false }, { value: 60, uneven: false },
      { years: [2027, 2028], materials: [], services: [] }, { materials: [2027, 2028], services: [2028] });
    expect(rows.map((r) => ("group" in r ? `#${r.group}` : r.field))).toEqual([
      "#Parte fissa", "fixed_materials_growth_pct", "fixed_services_growth_pct",
      "#Ipotesi manuali", "personnel_growth_pct", "rent_growth_pct", "other_costs_growth_pct",
    ]);
    const mat = rows[1] as { autoYears?: number[]; baseLabel: string };
    expect(mat.autoYears).toEqual([2027, 2028]);
    expect(mat.baseLabel).toBe(euro(400));
  });
  it("fixedGrowthChange: vuoto torna all'inflazione e diventa automatico", () => {
    expect(fixedGrowthChange(null, 2.5)).toEqual({ value: 2.5, auto: true });
    expect(fixedGrowthChange(0, 2.5)).toEqual({ value: 0, auto: false });
  });
  it("autoYearsOf legge il flag per anno", () => {
    const map = asMap({ 2027: { fixed_materials_growth_auto: true }, 2028: { fixed_materials_growth_auto: false } });
    expect(autoYearsOf(map, [2027, 2028], "fixed_materials_growth_auto")).toEqual([2027]);
  });
```
(`CostiBase` prende il campo `od` — oneri diversi, `ce12_oneri_diversi` — e `costiBase` lo legge; `alignVariablesToRevenue` si rimuove con il suo test: le variabili seguono i ricavi dal Task 10.)

In `budget-preview-rows.test.ts`:

```ts
  it("rowsCeAnteImposte: dal valore della produzione all'ante imposte, dal motore", () => {
    const rows = rowsCeAnteImposte(baseInc, [year(2027, { income_statement: { ce01_ricavi_vendite: 1000, ce04_altri_ricavi: 10, ce05_materie_prime: 300, ce06_servizi: 100, ce07_godimento_beni: 20, ce08_costi_personale: 200, ce09_ammortamenti: 50, ce12_oneri_diversi: 5, ce15_oneri_finanziari: 15 }, details: { ...year(2027).details, ce05_fixed: 100, ce05_variable: 200, ce06_fixed: 60, ce06_variable: 40, pareggio: { costi_variabili: 240, costi_fissi: 385 } } })]);
    expect(rows.map((r) => r.key)).toEqual(["vdp", "variabili", "fissi", "mol", "amm", "ro", "of", "ebt"]);
    expect(rows.find((r) => r.key === "ebt")?.years[0].value).toBe(1010 - 240 - 385 - 50 - 15);
  });
```
(`baseInc` e `year` sono gli helper gia' presenti in quel file; se `year()` non accetta `details` parziali, comporli come fa il file.)

- [ ] **Step 3: Rosso**

```bash
cd frontend && npx vitest run lib/budget-pareggio.test.ts lib/budget-costi-step.test.ts lib/budget-preview-rows.test.ts
```

- [ ] **Step 4: Moduli**

`frontend/lib/budget-pareggio.ts`:

```ts
/**
 * Il punto di pareggio sul MOL (spec 2026-09-15 §4.3, decisione 4): lettura pura di
 * `details.pareggio`, che il motore dichiara anno per anno. Qui non si calcola nulla di
 * finanziario: solo la geometria del mini grafico e le frasi della formula.
 */
import type { ForecastPreviewYear } from "@/types/api";
import { num } from "@/lib/budget-format";
import { formatCurrency, formatPercentage } from "@/lib/formatters";
import type { PreviewRow } from "@/lib/budget-preview-rows";

const ND_NOTE = "Non definito: materie prime o servizi forzati in CE Prev.";
const eur0 = (v: number) => formatCurrency(v, { maximumFractionDigits: 0 }).replace(/\s?€/, "").trim();
const pct1 = (v: number) => formatPercentage(v / 100, 1);

export interface PareggioBarra {
  year: number; ricaviPct: number; pareggioPct: number; margineDaPct: number; margineAPct: number;
  ok: boolean; margine: number | null; marginePct: number | null; nd: boolean;
}

export function pareggioBarre(years: ForecastPreviewYear[]): PareggioBarra[] {
  const ricavi = years.map((y) => num((y.income_statement as Record<string, unknown>).ce01_ricavi_vendite));
  const bep = years.map((y) => y.details.pareggio?.fatturato_pareggio ?? null);
  const scala = Math.max(0, ...ricavi, ...bep.map((b) => b ?? 0)) * 1.04;
  const x = (v: number) => (scala > 0 ? Math.max(0, Math.min(100, (v / scala) * 100)) : 0);
  return years.map((y, i) => {
    const p = y.details.pareggio;
    const nd = !p || p.fatturato_pareggio === null;
    const r = x(ricavi[i]), b = nd ? 0 : x(bep[i] as number);
    const ok = !nd && (p.margine_sicurezza ?? 0) >= 0;
    return { year: y.year, ricaviPct: r, pareggioPct: b, margineDaPct: ok ? b : r, margineAPct: ok ? r : b,
      ok, margine: nd ? null : p.margine_sicurezza, marginePct: nd ? null : p.margine_sicurezza_pct, nd };
  });
}

export function pareggioFormula(first: ForecastPreviewYear | undefined) {
  const p = first?.details.pareggio;
  if (!first || !p || p.fatturato_pareggio === null || p.costi_variabili === null || p.costi_fissi === null || p.costi_fissi_operativi === null) return null;
  const inc = first.income_statement as Record<string, unknown>;
  const rev = num(inc.ce01_ricavi_vendite), altri = num(inc.ce04_altri_ricavi);
  const mdc = p.margine_contribuzione_pct ?? 0, bep = p.fatturato_pareggio;
  return { anno: first.year, righe: [
    { testo: "Margine di contribuzione % = (ricavi − costi variabili) / ricavi", calcolo: `(${eur0(rev)} − ${eur0(p.costi_variabili)}) / ${eur0(rev)} = ${pct1(mdc)}` },
    { testo: "Costi fissi operativi = costi fissi − altri ricavi", calcolo: `${eur0(p.costi_fissi)} − ${eur0(altri)} = ${eur0(p.costi_fissi_operativi)}` },
    { testo: "Fatturato di pareggio sul MOL = costi fissi / margine %", calcolo: `${eur0(p.costi_fissi_operativi)} / ${pct1(mdc)} = ${eur0(bep)}` },
    { testo: "Margine di sicurezza = (ricavi − pareggio) / ricavi", calcolo: `(${eur0(rev)} − ${eur0(bep)}) / ${eur0(rev)} = ${pct1(p.margine_sicurezza_pct ?? 0)}` },
  ] };
}

export function rowsPareggio(years: ForecastPreviewYear[]): PreviewRow[] {
  const cell = (f: (y: ForecastPreviewYear) => number | null, pct = false) =>
    years.map((y) => { const p = y.details.pareggio; const nd = !p || p.fatturato_pareggio === null;
      return nd ? { value: null, note: ND_NOTE } : pct ? { value: null, pct: f(y) } : { value: f(y) }; });
  const none = { value: null };
  return [
    { key: "ricavi", label: "Ricavi del piano", kind: "sub", base: none, years: years.map((y) => ({ value: num((y.income_statement as Record<string, unknown>).ce01_ricavi_vendite) })) },
    { key: "mdc", label: "Margine di contribuzione", kind: "sub", base: none, years: cell((y) => y.details.pareggio.margine_contribuzione_pct, true) },
    { key: "pareggio", label: "Pareggio sul MOL", kind: "kpi", base: none, years: cell((y) => y.details.pareggio.fatturato_pareggio) },
    { key: "margine-pct", label: "margine di sicurezza %", kind: "sub", base: none, years: cell((y) => y.details.pareggio.margine_sicurezza_pct, true) },
    { key: "margine", label: "margine di sicurezza €", kind: "sub", base: none, years: cell((y) => y.details.pareggio.margine_sicurezza) },
  ];
}
```
(`formatCurrency`/`formatPercentage` sono in `lib/formatters`; se `formatCurrency` non accetta opzioni, usare `new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(Math.round(v))` per `eur0`. La `PreviewCell` con `pct` e valore `null` e' resa come percentuale da `describeCell`: verificare in `budget-preview-cell.ts`, altrimenti mettere il valore percentuale in `value` e marcare la riga `kind: "sub"` con etichetta «%».)

`budget-costi-step.ts`: `CostiBase` con `od`; `costiTableRows(base, mat, serv, forced, auto: { materials: number[]; services: number[] })` che restituisce i due gruppi del test (etichette «Materie prime · fissa», «Servizi · fissa», «Personale», «Godimento beni di terzi», «Oneri diversi di gestione» con `sub: "spostata qui da «Altre voci CE»"`; sul gruppo «Parte fissa» `sub: "precompilata con l'inflazione del passo 1 · correggi se serve, anche a 0"`, sul gruppo «Ipotesi manuali» `sub: "partono da 0 · variazione % sull'anno precedente"` — `YearInputGroup` prende un `sub?: string`, da aggiungere se manca); le righe fisse portano `autoYears` e `autoNote: "Segue l'inflazione del passo 1: cambia se la cambi lì. Scrivi un valore per fissarlo; svuota la casella per tornare all'inflazione."` piu' `offYears`/`offYearsNote` di oggi. Le funzioni `fixedGrowthChange` e `autoYearsOf` come nei test. `calcolateAltrove(baseYear)` restituisce le tre righe della card piatta: `{ label: "Ammortamenti", small: "quote esistenti più i nuovi investimenti", passo: "passo 6" }`, `{ label: "Oneri finanziari", small: "mutui esistenti, nuovi finanziamenti, scoperto", passo: "passi 5 e 6" }`, `{ label: "Imposte", small: "aliquota effettiva o forzata", passo: "passo 7" }`. Rimuovere `alignVariablesToRevenue` e `AssumptionWrite`.

`budget-preview-rows.ts`: `rowsCosti` — etichette «variabili · materie prime e servizi», «fissi · parti fisse, personale, godimento, oneri diversi», «di cui personale», «MOL», i totali letti da `details.pareggio.costi_variabili` / `costi_fissi` (non piu' sommati qui: e' il motore a dichiararli; senza `pareggio` la cella e' `null` con nota); `rowsCeAnteImposte` con le otto righe del test (`vdp` = ce01 + ce04; `variabili` e `fissi` negativi da `pareggio`; `mol` = vdp − variabili − fissi; `amm` = −ce09; `ro` = mol − ce09; `of` = −ce15; `ebt` = ro − ce15; colonna base dall'anno base con la quota fissa dell'anno base per `variabili`/`fissi` — riusare la stessa aritmetica di `rowsCosti` per la sola colonna base).

- [ ] **Step 5: Componenti**

`YearInputTable.tsx`: `YearInputRow.autoYears?: number[]`, `autoNote?: string`; la cella con l'anno in `autoYears` prende `className="bg-blue-50 text-blue-900 dark:bg-blue-950 dark:text-blue-100"` e `title={autoNote}`. `YearInputGroup.sub?: string` reso in piccolo accanto al titolo del gruppo.

`StepCosti.tsx`: tabella con `rows = costiTableRows(base, mat, serv, forced, { materials: autoYearsOf(...), services: autoYearsOf(...) })` e un `update` intercettato: per `fixed_materials_growth_pct`/`fixed_services_growth_pct` → `const { value, auto } = fixedGrowthChange(v, inflazioneOf(p.assumptions, p.forecastYears)); p.update(y, field, value); p.update(y, field.replace("_pct", "_auto"), auto);`. Pulsante «Riallinea all'inflazione» sotto la tabella: per ogni anno `update(y, "fixed_*_growth_auto", true)` + `update(y, "fixed_*_growth_pct", inflazione)`. La legenda del prototipo sotto gli slider. La card piatta «Calcolate in altri passi» da `calcolateAltrove`. A destra: `PreviewPanel` «Costi e margine» (`costiPreview.tableRows`), «Punto di pareggio sul MOL» (mini grafico da `pareggioBarre` — una riga per anno: anno, traccia con `div` dei ricavi (`width: ricaviPct%`), segmento verde/rosso tratteggiato da `margineDaPct` a `margineAPct`, tacca scura a `pareggioPct`; valore `marginePct` e `margine`; legenda a quattro voci; `title` con ricavi/pareggio/margine), formula da `pareggioFormula`, tabella `rowsPareggio`), «Conto economico fino all'ante imposte» (`rowsCeAnteImposte`). Il blocco «Debiti verso fornitori con i giorni fermi» di oggi si toglie. Eliminare `StepAltreVociCE.tsx`, `budget-altre-voci-step.ts` e il suo test; `grep -rn "altre-voci\|AltreVoci" frontend/ --include=*.ts --include=*.tsx` deve restare vuoto (esclusa `AssumptionsCatalog`).

- [ ] **Step 6: Verde, tsc, commit**

```bash
cd frontend && npx vitest run lib/budget-pareggio.test.ts lib/budget-costi-step.test.ts lib/budget-preview-rows.test.ts && npx tsc --noEmit
git add -u frontend/components/budget/wizard/steps/StepAltreVociCE.tsx frontend/lib/budget-altre-voci-step.ts frontend/lib/budget-altre-voci-step.test.ts
git add frontend/lib/budget-pareggio.ts frontend/lib/budget-pareggio.test.ts frontend/lib/budget-costi-step.ts frontend/lib/budget-costi-step.test.ts frontend/lib/budget-preview-rows.ts frontend/lib/budget-preview-rows.test.ts frontend/components/budget/wizard/YearInputTable.tsx frontend/components/budget/wizard/steps/StepCosti.tsx
git commit -m "feat(ipotesi): passo Costi con parte fissa dall'inflazione, pareggio sul MOL e CE fino all'ante imposte"
```

---

### Task 12: Passo 4: avviso fornitori a zero, voci minori via

**Files:**
- Create: `frontend/lib/budget-fornitori-zero.ts`, `frontend/lib/budget-fornitori-zero.test.ts`
- Modify: `frontend/components/budget/wizard/steps/StepCircolante.tsx`, `frontend/lib/budget-circolante-step.ts` (resta tutto: `minorFieldsRows`, `spIndexingOf`, `pianiPregressoOf`, `DRIVERS` servono al Task 15), `frontend/lib/budget-circolante-step.test.ts`

**Interfaces:**
- Produces: `fornitoriZeroAvviso(baseYear: number, baseBs: BalanceSheet | null | undefined, baseInc: IncomeStatement | null | undefined): { titolo: string; dettaglio: string } | null`

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task12-base
```

- [ ] **Step 2: Test rosso**

`frontend/lib/budget-fornitori-zero.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { BalanceSheet, IncomeStatement } from "@/types/api";
import { fornitoriZeroAvviso } from "./budget-fornitori-zero";

const inc = { ce05_materie_prime: "980000", ce06_servizi: "420000", ce07_godimento_beni: "85000" } as unknown as IncomeStatement;
const bs = (forn: string, altri = "367000") => ({ sp16d_debiti_fornitori_breve: forn, sp16g_altri_debiti_breve: altri }) as unknown as BalanceSheet;

describe("fornitoriZeroAvviso", () => {
  it("avvisa quando i fornitori sono zero e i costi d'acquisto no", () => {
    expect(fornitoriZeroAvviso(2026, bs("0"), inc)).toEqual({
      titolo: "Non risultano debiti verso fornitori nell'anno di partenza. Controllare le riclassifiche dei debiti!",
      dettaglio: "I costi di acquisto del 2026 sono 1.485.000 €, i giorni di pagamento non si possono calcolare. Gli altri debiti a breve valgono 367.000 €.",
    });
  });
  it("tace con fornitori positivi, senza costi, o senza bilancio", () => {
    expect(fornitoriZeroAvviso(2026, bs("322000"), inc)).toBeNull();
    expect(fornitoriZeroAvviso(2026, bs("0"), { ce05_materie_prime: "0" } as unknown as IncomeStatement)).toBeNull();
    expect(fornitoriZeroAvviso(2026, null, inc)).toBeNull();
  });
});
```

- [ ] **Step 3: Rosso, modulo, componente**

```bash
cd frontend && npx vitest run lib/budget-fornitori-zero.test.ts
```
`frontend/lib/budget-fornitori-zero.ts`:

```ts
/** Decisione 8 del proprietario (2026-09-14): fornitori a zero nell'anno base sono un problema di
 *  riclassifica (PROVA AMBIENTA: `_distribute_sp16_operativo` dell'infrannuale li ha messi in
 *  «altri debiti»), non del percorso. Si segnala soltanto, ai passi 4 e 5. */
import type { BalanceSheet, IncomeStatement } from "@/types/api";
import { num } from "@/lib/budget-format";

const eur = (v: number) => `${new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 }).format(Math.round(v))} €`;

export function fornitoriZeroAvviso(baseYear: number, baseBs: BalanceSheet | null | undefined, baseInc: IncomeStatement | null | undefined) {
  if (!baseBs || !baseInc) return null;
  const bs = baseBs as unknown as Record<string, unknown>, inc = baseInc as unknown as Record<string, unknown>;
  const acquisti = num(inc.ce05_materie_prime) + num(inc.ce06_servizi) + num(inc.ce07_godimento_beni);
  if (num(bs.sp16d_debiti_fornitori_breve) !== 0 || acquisti <= 0) return null;
  return {
    titolo: "Non risultano debiti verso fornitori nell'anno di partenza. Controllare le riclassifiche dei debiti!",
    dettaglio: `I costi di acquisto del ${baseYear} sono ${eur(acquisti)}, i giorni di pagamento non si possono calcolare. Gli altri debiti a breve valgono ${eur(num(bs.sp16g_altri_debiti_breve))}.`,
  };
}
```
`StepCircolante.tsx`: in testa alla colonna sinistra, se `avviso` non e' `null`, un riquadro `rounded-md bg-destructive/10 p-3 text-sm text-destructive` con `<AlertTriangle>` , `<b>{titolo}</b>` e `<div className="text-xs">{dettaglio}</div>`. Togliere la card «Voci minori dello SP» e l'accordion dei driver (il codice va al Task 15: NON cancellare le funzioni di `budget-circolante-step.ts`; spostare i test che le coprono in un `describe` a parte, restano verdi). Nel `note` sotto la tabella: «I giorni del {anno} sono calcolati sui soli crediti verso clienti e debiti verso fornitori, su 360 giorni. Crediti e debiti del {anno} si chiudono nel {anno+1} (passo 5): questi giorni generano quelli nuovi.»

- [ ] **Step 4: Verde, tsc, commit**

```bash
cd frontend && npx vitest run lib/budget-fornitori-zero.test.ts lib/budget-circolante-step.test.ts && npx tsc --noEmit
git add frontend/lib/budget-fornitori-zero.ts frontend/lib/budget-fornitori-zero.test.ts frontend/components/budget/wizard/steps/StepCircolante.tsx frontend/lib/budget-circolante-step.ts frontend/lib/budget-circolante-step.test.ts
git commit -m "feat(ipotesi): passo Capitale circolante con l'avviso sui fornitori a zero, voci minori al passo 6"
```

---

### Task 13: Passo 5 (I): a breve, oltre 12 mesi, «Scadenziamento pregresso»

**Files:**
- Create: `frontend/lib/budget-pregresso-oltre.ts`, `frontend/lib/budget-pregresso-oltre.test.ts`, `frontend/lib/budget-pregresso-flussi.ts`, `frontend/lib/budget-pregresso-flussi.test.ts`
- Create: `frontend/components/budget/wizard/steps/StepPatrimonialePregresso.tsx` (in questo task: testata, colonna «A breve», anteprima «Scadenziamento pregresso», card «Altre voci oltre 12 mesi»; le due card delle banche e degli altri finanziatori arrivano col Task 14)
- Modify: `frontend/lib/budget-pregresso-circolante.ts` (accoglie `TabellaPregressoKey`, `TABELLA_KEYS` da `budget-pregresso-tabella.ts`), `frontend/lib/budget-preview-rows.ts` (import di `TabellaPregressoKey`), `frontend/lib/budget-pregresso-step.ts` (import)
- Modify: `frontend/components/budget/wizard/BudgetWizard.tsx` (il ramo `"patrimoniale-pregresso"` rende il componente nuovo)
- Delete: **nessuno in questo task.** `PregressoTable.tsx` e `budget-pregresso-tabella.ts` (+ test) li usano ancora `StepPregressoNuovo.tsx` (fino al Task 15) e `StepImposte.tsx` (fino al Task 16): li cancella il Task 16, l'ultimo che li libera. `StepPregressoNuovo.tsx` lo cancella il Task 15.

**Interfaces:**
- Consumes: `openingMasses`, `openingMassLong`, `validatePregresso` (`lib/budget-pregresso-circolante.ts`), `fornitoriZeroAvviso` (Task 12), `p.updatePregresso`, `details.pregresso[*].non_incassato` (Task 6), `details.altri_finanziatori`, `details.debito_bancario.fidi` (Task 3-4)
- Produces:
  ```ts
  // budget-pregresso-oltre.ts
  export type OltreKey = "crediti_commerciali" | "altri_debiti" | "debiti_fornitori" | "debiti_previdenziali";
  export const OLTRE_LABELS: Record<OltreKey, string>;
  export interface OltreRow { key: OltreKey; label: string; dir: "in" | "out"; opening: number; amounts: (number | null)[]; resta: number; stato: "chiuso" | "resta aperto" | "nessun movimento nel piano" | "oltre il saldo" | "oltre il piano"; nonIncassato: boolean; disabled: boolean }
  export function massaBreve(baseBs, key): number; export function massaOltre(baseBs, key): number
  export function oltreRows(baseBs, pregresso: Pregresso, years: number[]): OltreRow[]        // solo i saldi con massa oltre > 0, crediti e altri debiti sempre
  export function pianoBase(baseBs, years: number[], pregresso: Pregresso): Pregresso           // crediti e fornitori: amounts[0] = massa a breve; previdenziali/altri: solo se massa oltre > 0
  export function withOltreAmount(baseBs, pregresso, years, key, i, value: number | null): Pregresso
  export function withNonIncassato(baseBs, pregresso, years, on: boolean): Pregresso
  export interface BreveRow { label: string; importo: number; dir: "in" | "out"; small: string; alert?: string }
  export function breveRows(baseBs, baseYear: number, fornitoriAvviso: string | null): BreveRow[]
  // budget-pregresso-flussi.ts
  export function flussiPregresso(years: ForecastPreviewYear[], breve: Record<OltreKey, number>): PreviewRow[]  // `breve` = massa a breve dell'anno base per saldo (`massaBreve`): i `details` non la portano
  ```

**Regola di persistenza (spec §4.5, precisata qui).** Il motore rigenera dal driver solo crediti e fornitori: per questi due il piano c'e' sempre (`amounts[0]` = massa a breve + eventuale scadenza dell'anno 1 della parte oltre). Previdenziali e altri debiti con un piano si **estinguono** (`_net_of_pregresso`: il generato vale zero, Ruling 17): per loro il piano si scrive **solo se c'e' massa oltre 12 mesi da scadenziare**; senza, restano governati dalle regole del passo 6. Chi ha massa oltre lo legge nella nota di destino della riga («non si rigenera: cio' che scadenzi qui va a zero e ci resta»).

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task13-base
```

- [ ] **Step 2: Test rosso**

`frontend/lib/budget-pregresso-oltre.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { BalanceSheet, Pregresso } from "@/types/api";
import { breveRows, massaBreve, massaOltre, oltreRows, pianoBase, withNonIncassato, withOltreAmount } from "./budget-pregresso-oltre";

const bs = {
  sp06_crediti_breve: "440000", sp06e_crediti_tributari_breve: "18000", sp06f_imposte_anticipate_breve: "0",
  sp07_crediti_lungo: "30000", sp07e_crediti_tributari_lungo: "0", sp07f_imposte_anticipate_lungo: "0",
  sp16d_debiti_fornitori_breve: "322000", sp17d_debiti_fornitori_lungo: "0",
  sp16e_debiti_tributari_breve: "61000", sp17e_debiti_tributari_lungo: "35000",
  sp16f_debiti_previdenza_breve: "28000", sp17f_debiti_previdenza_lungo: "0",
  sp16g_altri_debiti_breve: "45000", sp17g_altri_debiti_lungo: "40000",
} as unknown as BalanceSheet;
const anni = [2027, 2028, 2029];

describe("budget-pregresso-oltre", () => {
  it("massa a breve e oltre dei saldi commerciali", () => {
    expect(massaBreve(bs, "crediti_commerciali")).toBe(422000);
    expect(massaOltre(bs, "crediti_commerciali")).toBe(30000);
    expect(massaOltre(bs, "altri_debiti")).toBe(40000);
    expect(massaOltre(bs, "debiti_fornitori")).toBe(0);
  });
  it("pianoBase: crediti e fornitori chiudono il breve nel primo anno; previdenziali senza oltre non hanno piano", () => {
    const p = pianoBase(bs, anni, {});
    expect(p.crediti_commerciali).toEqual({ opening: 452000, amounts: [422000, 0, 0], writeoff: null, non_incassato: false });
    expect(p.debiti_fornitori).toEqual({ opening: 322000, amounts: [322000, 0, 0], writeoff: null });
    expect(p.altri_debiti).toEqual({ opening: 85000, amounts: [45000, 0, 0], writeoff: null });
    expect(p.debiti_previdenziali).toBeUndefined();
    expect(pianoBase(bs, anni, p)).toBe(p);   // identita' quando il piano c'e' gia'
  });
  it("oltreRows: righe con massa oltre, stati neutri", () => {
    const rows = oltreRows(bs, pianoBase(bs, anni, {}), anni);
    expect(rows.map((r) => r.key)).toEqual(["crediti_commerciali", "altri_debiti"]);
    expect(rows[0]).toMatchObject({ opening: 30000, amounts: [0, 0, 0], resta: 30000, stato: "nessun movimento nel piano", dir: "in" });
  });
  it("withOltreAmount scrive nell'anno la sola parte oltre e aggiorna resta e stato", () => {
    let p = pianoBase(bs, anni, {});
    p = withOltreAmount(bs, p, anni, "crediti_commerciali", 0, 10000);
    expect(p.crediti_commerciali?.amounts).toEqual([432000, 0, 0]);
    const [r] = oltreRows(bs, p, anni);
    expect(r).toMatchObject({ amounts: [10000, 0, 0], resta: 20000, stato: "resta aperto" });
    p = withOltreAmount(bs, p, anni, "crediti_commerciali", 1, 20000);
    expect(oltreRows(bs, p, anni)[0].stato).toBe("chiuso");
    p = withOltreAmount(bs, p, anni, "crediti_commerciali", 2, 5000);
    expect(oltreRows(bs, p, anni)[0].stato).toBe("oltre il saldo");
  });
  it("non incassati: caselle spente, importi a zero, stato «oltre il piano»", () => {
    const p = withNonIncassato(bs, withOltreAmount(bs, pianoBase(bs, anni, {}), anni, "crediti_commerciali", 0, 10000), anni, true);
    const [r] = oltreRows(bs, p, anni);
    expect(p.crediti_commerciali?.amounts).toEqual([422000, 0, 0]);
    expect(r).toMatchObject({ nonIncassato: true, disabled: true, stato: "oltre il piano" });
  });
  it("breveRows: cinque saldi piu' banche e finanziatori, con l'avviso sui fornitori", () => {
    const rows = breveRows(bs, 2026, "non risultano debiti verso fornitori");
    expect(rows.map((r) => r.label)).toEqual(["Crediti verso clienti", "Debiti verso fornitori", "Debiti tributari a breve", "Debiti previdenziali", "Altri debiti a breve", "Debiti verso banche e altri finanziatori"]);
    expect(rows[0]).toMatchObject({ importo: 422000, dir: "in", small: "incassati nel 2027" });
    expect(rows[1].alert).toBe("non risultano debiti verso fornitori");
    expect(rows[2].small).toBe("saldo pagato nel 2027");
  });
});
```
`frontend/lib/budget-pregresso-flussi.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { ForecastPreviewYear } from "@/types/api";
import { flussiPregresso } from "./budget-pregresso-flussi";

const y = (year: number): ForecastPreviewYear => ({
  year, income_statement: {}, balance_sheet: {},
  details: {
    pregresso: {
      crediti_commerciali: { opening: 452000, closed: year === 2027 ? 432000 : 0, writeoff: 0, residual_short: 0, residual_long: 20000, generated: 0, mode: "runoff", non_incassato: false },
      debiti_fornitori: { opening: 322000, closed: year === 2027 ? 322000 : 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "runoff" },
      debiti_tributari: { opening: 96000, closed: 0, writeoff: 0, residual_short: 0, residual_long: 23000, generated: 0, mode: "runoff" },
      debiti_previdenziali: { opening: 28000, closed: 0, writeoff: 0, residual_short: 0, residual_long: 0, generated: 0, mode: "legacy" },
      altri_debiti: { opening: 85000, closed: year === 2027 ? 45000 : 0, writeoff: 0, residual_short: 0, residual_long: 40000, generated: 0, mode: "runoff" },
    },
    imposte: { saldo_paid: year === 2027 ? 61000 : 0, rate_paid: 12000, acconti_paid: 0, current_tax: 0, generated_debt: 0, generated_credit: 0, opening_credit_left: 0, mode: "saldo_acconto" },
    debito_bancario: { fidi: { apertura: 90000, variazione_ricavi: 0, rimborso_sweep: 0, residuo: 90000, regola: "costante" }, pregresso_senza_piano: null, pregresso_piano_anni: null,
      contratti: [{ indice: 0, anno: 2027, tasso: 3.8, erogato: 0, residuo_iniziale: 330000, rimborso: 82500, interessi: 0, breve: 82500, lungo: 165000 }] },
    altri_finanziatori: { apertura: 150000, rimborso: year === 2028 ? 50000 : 0, interessi: 0, breve: 0, lungo: 100000, mode: "contratti", contratti: [] },
  } as never,
} as unknown as ForecastPreviewYear);

const breve = { crediti_commerciali: 422000, debiti_fornitori: 322000, debiti_previdenziali: 28000, altri_debiti: 45000 };

describe("flussiPregresso", () => {
  it("una riga per flusso, segno per direzione, totale netto e debito aperto", () => {
    const rows = flussiPregresso([y(2027), y(2028)], breve);
    const by = (k: string) => rows.find((r) => r.key === k)!;
    expect(rows.map((r) => r.key)).toEqual(["h-breve", "crediti", "fornitori", "trib-saldo", "previd-altri", "h-oltre", "banche", "fidi", "altri-fin", "trib-rate", "altri-oltre", "crediti-oltre", "netto", "aperto"]);
    expect(by("crediti").years.map((c) => c.value)).toEqual([422000, 0]);
    expect(by("crediti-oltre").years.map((c) => c.value)).toEqual([10000, 0]);
    expect(by("fornitori").years[0].value).toBe(-322000);
    expect(by("banche").years[0].value).toBe(-82500);
    expect(by("altri-fin").years[1].value).toBe(-50000);
    expect(by("netto").years[0].value).toBe(422000 + 10000 - 322000 - 61000 - 45000 - 82500 - 0 - 0 - 12000 - 0);
    expect(by("aperto").years[0].value).toBe(90000 + 247500 + 100000 + 23000 + 40000);
  });
});
```
- [ ] **Step 3: Rosso**

```bash
cd frontend && npx vitest run lib/budget-pregresso-oltre.test.ts lib/budget-pregresso-flussi.test.ts
```

- [ ] **Step 4: Moduli**

`frontend/lib/budget-pregresso-oltre.ts` — le funzioni dell'interfaccia. Le masse: `massaBreve(bs, key)` = `openingMasses(bs)[key] − openingMassLong(bs, key)`, `massaOltre = openingMassLong` (entrambe in `budget-pregresso-circolante.ts`; per i crediti `openingMassLong` e' `sp07 − sp07e − sp07f`: verificarlo, altrimenti calcolarlo qui). `pianoBase`: per `crediti_commerciali` e `debiti_fornitori` sempre, per `altri_debiti` e `debiti_previdenziali` solo con `massaOltre > 0`: se `pregresso[key]` manca → `{ opening: massaBreve + massaOltre, amounts: [massaBreve, 0, …], writeoff: null }` (+ `non_incassato: false` sui crediti); se tutti presenti restituisce l'oggetto ricevuto (identita'). `oltreRows`: `amounts[i]` della riga = `plan.amounts[i] − (i === 0 ? massaBreve : 0)` (mai negativo); `resta = massaOltre − Σ`; `stato`: `nonIncassato` → «oltre il piano»; `Σ > massaOltre + 0,5` → «oltre il saldo»; `resta < 0,5` → «chiuso»; `Σ < 0,5` → «nessun movimento nel piano»; altrimenti «resta aperto». `withOltreAmount`: parte da `pianoBase`, scrive `amounts[i] = (i === 0 ? massaBreve : 0) + (value ?? 0)`. `withNonIncassato`: azzera la parte oltre su ogni anno e scrive `non_incassato`. `breveRows`: i sei elementi del test (small: «incassati nel {y1}», «pagati nel {y1}», «saldo pagato nel {y1}», «pagati nel {y1}», «pagati nel {y1}», «non si chiudono per regola: fidi e anticipi si rinnovano, i finanziamenti li scadenzi qui sotto»; importi: massa a breve dei quattro saldi, `sp16e`, e per l'ultima `baseBankDebt(bs) + sp16b + sp17b`).

`frontend/lib/budget-pregresso-flussi.ts` — `flussiPregresso(years, breve)`: le quattordici righe del test, in `PreviewRow` (`base: { value: null }` ovunque; `kind`: `"total"` per le due intestazioni e `netto`, `"sub"` per `aperto`, `"value"` per le altre); segno: entrate positive, uscite negative; `crediti` = anno 1: `min(closed, breve.crediti_commerciali)`, poi 0; `crediti-oltre` = `closed − crediti`; `fornitori`, `previd-altri` allo stesso modo (previdenziali + altri a breve); `trib-saldo` = `−imposte.saldo_paid`; `banche` = `−Σ contratti[residuo_iniziale > 0].rimborso`; `fidi` = `−(fidi.apertura − fidi.residuo)` (zero senza `fidi`); `altri-fin` = `−altri_finanziatori.rimborso`; `trib-rate` = `−imposte.rate_paid`; `altri-oltre` = parte oltre di `altri_debiti.closed`; `netto` = somma; `aperto` = `fidi.residuo + Σ contratti pregressi (breve + lungo) + altri_finanziatori (breve + lungo) + debiti_tributari.residual_long + altri_debiti.residual_long + debiti_fornitori.residual_long + debiti_previdenziali.residual_long`.

Spostare `TabellaPregressoKey` e `TABELLA_KEYS` in `budget-pregresso-circolante.ts` (con il commento sul perche' `debiti_tributari` e' escluso) e aggiornare gli import in `budget-preview-rows.ts` e `budget-pregresso-step.ts`; eliminare `budget-pregresso-tabella.ts` + test e `PregressoTable.tsx` (`grep -rn "pregresso-tabella\|PregressoTable" frontend/` vuoto).

- [ ] **Step 5: Componente**

`StepPatrimonialePregresso.tsx` (presentazionale): `const baseBs`, `baseInc`, `masse`, `pregresso = useMemo(() => pianoBase(baseBs, years, salvato ?? {}))`; un effetto **una tantum** per scenario che, se `pianoBase(...) !== salvato`, chiama `p.updatePregresso(pianoBase(...))` (cosi' il piano dei saldi a breve e' persistito alla prima visita; e' l'unica scrittura non innescata dall'utente, e la nota della card lo dice: «nessun piano da impostare»). Layout: `grid gap-5 lg:grid-cols-[1.4fr_1fr] items-start` con a sinistra la card «A breve · si chiudono nel {y1}» (`breveRows` rese come `ScheduleRow` con chip `incasso`/`pagamento` verde/rosso e l'importo; la riga con `alert` in rosso) e sotto il suggerimento sulle Rettifiche (prototipo); a destra `PreviewPanel` «Scadenziamento pregresso · flussi di cassa» con `flussiPregresso(previewYears, breve)`. Sotto, a tutta larghezza (`mt-4 space-y-4`): la card «Altre voci oltre 12 mesi · scadenziamento a mano» con una tabella (voce · al 31/12/{anno} · un `Input type="number"` per anno · «resta» con il chip dello stato; sui crediti la `Checkbox` «non incassati nel piano (es. infragruppo)»), la riga in sola lettura «Debiti tributari rateizzati · {sp17e} € · si scadenziano al passo 7» (segnaposto: la rende modificabile il Task 13b), e — dal Task 14 — le card delle banche e degli altri finanziatori. Gli errori di `validatePregresso` si mostrano sotto la tabella come oggi. `BudgetWizard.tsx`: `"patrimoniale-pregresso"` → `<StepPatrimonialePregresso {...stepProps} />`.

- [ ] **Step 6: Verde, tsc, commit**

```bash
cd frontend && npx vitest run lib/budget-pregresso-oltre.test.ts lib/budget-pregresso-flussi.test.ts lib/budget-pregresso-circolante.test.ts lib/budget-preview-rows.test.ts lib/budget-pregresso-step.test.ts && npx tsc --noEmit
git add -u frontend/components/budget/wizard/PregressoTable.tsx frontend/lib/budget-pregresso-tabella.ts frontend/lib/budget-pregresso-tabella.test.ts
git add frontend/lib/budget-pregresso-oltre.ts frontend/lib/budget-pregresso-oltre.test.ts frontend/lib/budget-pregresso-flussi.ts frontend/lib/budget-pregresso-flussi.test.ts frontend/lib/budget-pregresso-circolante.ts frontend/lib/budget-preview-rows.ts frontend/lib/budget-pregresso-step.ts frontend/components/budget/wizard/steps/StepPatrimonialePregresso.tsx frontend/components/budget/wizard/BudgetWizard.tsx
git commit -m "feat(ipotesi): passo Patrimoniale pregresso, prima parte: a breve, oltre 12 mesi, flussi del pregresso"
```

---

### Task 13b: Passo 5: debiti tributari rateizzati scadenziati a mano

Decisione del proprietario (2026-09-15, spec §3 e §9.1): i rateizzati lasciano il passo 7 e l'utente li scadenzia anno per anno nella card «Altre voci oltre 12 mesi». Parte dopo il merge del Task 13; puo' correre in parallelo al Task 14 (tocca solo la riga dei tributari e la riga a breve «Debiti tributari a breve»; le card del Task 14 si aggiungono in fondo, il coordinatore risolve l'eventuale conflitto).

**Files:**
- Modify: `frontend/lib/budget-pregresso-oltre.ts`, `frontend/lib/budget-pregresso-oltre.test.ts`
- Modify: `frontend/components/budget/wizard/steps/StepPatrimonialePregresso.tsx` (la riga segnaposto dei tributari diventa modificabile; gli errori di `validatePregresso` includono il piano tributario)
- Non si tocca: `StepImposte.tsx`, `budget-imposte-step.ts` (Task 16), il motore (Task 16)

**Interfaces:**
- Consumes: `tributariPlan`, `tributariPlanOrDefault`, `withRate` (`lib/budget-imposte-step.ts`, invariati); `openingMasses`, `validatePregresso` (`lib/budget-pregresso-circolante.ts`); `OltreRow`, `oltreRows`, `pianoBase`, `withOltreAmount`, `breveRows` (Task 13)
- Produces:
  ```ts
  // budget-pregresso-oltre.ts
  export interface TributariOltreRow { key: "debiti_tributari"; label: "Debiti tributari rateizzati"; dir: "out"; opening: number; amounts: (number | null)[]; resta: number; stato: OltreRow["stato"] }
  export function tributariOltreRow(baseBs, pregresso: Pregresso, years: number[]): TributariOltreRow | null   // null se sp17e = 0 e nessun piano salvato
  export function withTributariAmount(baseBs, pregresso: Pregresso, years: number[], i: number, value: number | null): Pregresso
  ```

**Regole.**
- **Piano di partenza:** `pianoBase` crea `debiti_tributari` **solo se** manca e `sp17e > 0`: `{ opening: sp16e + sp17e, saldo: sp16e, rateizzato: sp17e, amounts: [0, …] (lunghezza = anni), acconto_pct: 100 }`. Il saldo e' il debito a breve (cio' che scade entro l'esercizio si paga nel primo anno), il rateizzato il debito oltre: e' la stessa lettura del bilancio che fanno le altre voci, e chi vuole un'altra ripartizione la corregge in Rettifiche fra `sp16e` e `sp17e`. Con `sp17e = 0` nessun piano: il motore paga tutto il tributario come saldo nel primo anno, come oggi. Un piano gia' salvato (anche con un saldo diverso da `sp16e`, scritto dal vecchio passo 7) si rispetta cosi' com'e': identita'.
- **Riga:** `opening` = `plan.rateizzato`; `amounts[i]` = `plan.amounts[i]` (nessuno scarto di breve: il saldo non entra nel runoff, `forecast_engine.py` scadenzia il solo `rateizzato`); `resta = rateizzato − Σ amounts`; stati come `oltreRows` (senza «oltre il piano»). Resa **dopo** le quattro voci di `oltreRows`, con la stessa tabella.
- **Scrittura:** `withTributariAmount` parte da `pianoBase`, completa `amounts` alla lunghezza degli anni con zeri, scrive `amounts[i] = value ?? 0` e passa per `withRate` (saldo, rateizzato e acconto non si toccano).
- **Riga a breve:** `breveRows` riceve il `pregresso`; «Debiti tributari a breve · saldo pagato nel {y1}» mostra `plan.saldo` quando il piano c'e', altrimenti `sp16e + sp17e` se `sp17e = 0` (tutto saldo) — mai un importo diverso da quello che il motore paga.
- **Errori:** `validatePregresso` si chiama sul pregresso intero, tributari compresi (oggi il passo 7 validava il solo piano tributario): gli errori «le rate superano il rateizzato» compaiono sotto la tabella del passo 5.

- [ ] **Step 1: Base del task** — `git rev-parse HEAD > /tmp/rilievi-task13b-base`
- [ ] **Step 2: Test rosso** in `budget-pregresso-oltre.test.ts`, sul `bs` del Task 13 (`sp16e` 61000, `sp17e` 35000):

```ts
describe("tributari rateizzati al passo 5", () => {
  it("pianoBase: saldo = debito a breve, rateizzato = debito oltre, rate a zero", () => {
    const p = pianoBase(bs, anni, {});
    expect(p.debiti_tributari).toEqual({ opening: 96000, saldo: 61000, rateizzato: 35000, amounts: [0, 0, 0], acconto_pct: 100 });
  });
  it("senza debito oltre nessun piano tributario", () => {
    const bs0 = { ...bs, sp17e_debiti_tributari_lungo: "0" } as unknown as BalanceSheet;
    expect(pianoBase(bs0, anni, {}).debiti_tributari).toBeUndefined();
    expect(tributariOltreRow(bs0, pianoBase(bs0, anni, {}), anni)).toBeNull();
  });
  it("un piano salvato dal vecchio passo 7 si rispetta", () => {
    const salvato = { debiti_tributari: { opening: 96000, saldo: 50000, rateizzato: 46000, amounts: [23000, 23000], acconto_pct: 80 } } as Pregresso;
    const p = pianoBase(bs, anni, salvato);
    expect(p.debiti_tributari).toEqual(salvato.debiti_tributari);
    expect(tributariOltreRow(bs, p, anni)).toMatchObject({ opening: 46000, amounts: [23000, 23000, null], resta: 0, stato: "chiuso" });
    expect(breveRows(bs, 2026, null, p)[2]).toMatchObject({ importo: 50000, small: "saldo pagato nel 2027" });
  });
  it("withTributariAmount scrive la rata dell'anno e lascia saldo e acconto", () => {
    let p = pianoBase(bs, anni, {});
    p = withTributariAmount(bs, p, anni, 1, 20000);
    expect(p.debiti_tributari).toMatchObject({ saldo: 61000, rateizzato: 35000, amounts: [0, 20000, 0], acconto_pct: 100 });
    expect(tributariOltreRow(bs, p, anni)).toMatchObject({ resta: 15000, stato: "resta aperto" });
    p = withTributariAmount(bs, p, anni, 2, 20000);
    expect(tributariOltreRow(bs, p, anni)?.stato).toBe("oltre il saldo");
  });
});
```
(Il test del Task 13 su `pianoBase(bs, anni, p)` identita' resta; quello su `breveRows(bs, 2026, avviso)` passa con il quarto argomento opzionale.)

- [ ] **Step 3: Rosso** — `cd frontend && npx vitest run lib/budget-pregresso-oltre.test.ts` (atteso: fallisce sulle asserzioni dopo aver aggiunto gli export vuoti)
- [ ] **Step 4: Modulo e componente** secondo le regole sopra; nel componente la riga usa lo stesso `Input type="number"` per anno e il chip dello stato, con la nota «Rate della rateizzazione: escono di cassa nell'anno. Il saldo a breve si paga nel {y1}.»
- [ ] **Step 5: Verde, tsc, commit**

```bash
cd frontend && npx vitest run lib/budget-pregresso-oltre.test.ts lib/budget-pregresso-flussi.test.ts lib/budget-pregresso-circolante.test.ts lib/budget-imposte-step.test.ts && npx tsc --noEmit
git add frontend/lib/budget-pregresso-oltre.ts frontend/lib/budget-pregresso-oltre.test.ts frontend/components/budget/wizard/steps/StepPatrimonialePregresso.tsx
git commit -m "feat(ipotesi): tributari rateizzati scadenziati a mano al passo Patrimoniale pregresso"
```

---

### Task 14: Passo 5 (II): debiti verso banche, altri finanziatori

**Files:**
- Create: `frontend/lib/budget-finanziamenti-pregresso.ts`, `frontend/lib/budget-finanziamenti-pregresso.test.ts`
- Modify: `frontend/components/budget/wizard/steps/StepPatrimonialePregresso.tsx` (le due card), `calculations/forecast_engine.py:332-380` (`_contratti_dell_anno`: la chiave `nome` per contratto — una riga: `'nome': loan.get('name')`, e `'name'` va portato nel contratto da `contratti_da_riga_finanziamento`: `condizioni['name'] = loan.get('name')`)
- Test: anche `tests/test_forecast_contratti_per_anno.py` (asserzione su `contratti[0]["nome"] == "Mutuo"`)

**Interfaces:**
- Consumes: `baseBankDebt` (`lib/base-bank-debt.ts`), `p.updateFinancingLoans`, `p.updateOtherLenders`, `p.update(firstYear, "bank_lines_*", …)`
- Produces:
  ```ts
  export interface Scadenziabile { name?: string | null; opening_residual: number; interest_rate: number; repayments?: number[] | null }
  export interface ContrattoRow { index: number; name: string; residuo: number; tasso: number; rimborsi: number[]; resta: number; stato: "chiuso" | "resta aperto" | "nessun rimborso nel piano" | "oltre il residuo" }
  export function contrattiPregressi(loans: FinancingLoanInput[] | null | undefined): FinancingLoanInput[]   // opening_residual > 0
  export function prestitiNuovi(loans: FinancingLoanInput[] | null | undefined): FinancingLoanInput[]        // amount > 0
  export function contrattoRows(items: readonly Scadenziabile[], horizon: number): ContrattoRow[]
  export function restaStato(residuo: number, rimborsi: number[]): ContrattoRow["stato"]
  export function withCampo<T extends Scadenziabile>(items: T[], k: number, field: "name" | "opening_residual" | "interest_rate", value: string | number | null): T[]
  export function withRimborso<T extends Scadenziabile>(items: T[], k: number, i: number, value: number | null, horizon: number): T[]
  export function nuovoContratto(n: number, horizon: number): FinancingLoanInput      // «Finanziamento A», residuo 0, tasso 4, rimborsi a zero
  export function nuovoFinanziatore(n: number, horizon: number): OtherLenderInput      // «Finanziatore 1», tasso 0
  export function unisciContratti(items: FinancingLoanInput[], horizon: number): FinancingLoanInput[]  // uno solo: somma residui, tasso medio ponderato (1 decimale), rimborsi sommati
  export function quotaMutui(baseBs, fidi: number): number                              // sp16a − fidi
  export interface Controllo { ok: boolean; testo: string; esito: string }
  export function controlliBanche(baseBs, fidi: number, items: readonly Scadenziabile[], horizon: number, baseYear: number): { fidiOltre: Controllo | null; quadra: Controllo; rata: Controllo }
  export function controlloAltri(baseBs, items: readonly Scadenziabile[]): Controllo
  ```

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task14-base
```

- [ ] **Step 2: Test rosso**

`frontend/lib/budget-finanziamenti-pregresso.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { BalanceSheet, FinancingLoanInput } from "@/types/api";
import {
  contrattiPregressi, contrattoRows, controlliBanche, controlloAltri, nuovoContratto, prestitiNuovi,
  quotaMutui, restaStato, unisciContratti, withRimborso,
} from "./budget-finanziamenti-pregresso";

const bs = {
  sp16_debiti_breve: "172500", sp16a_debiti_banche_breve: "172500", sp17_debiti_lungo: "617500",
  sp17a_debiti_banche_lungo: "467500", sp17b_debiti_altri_finanz_lungo: "150000", sp16b_debiti_altri_finanz_breve: "0",
} as unknown as BalanceSheet;
const mutuo: FinancingLoanInput = { name: "Mutuo Intesa 2022", amount: 0, opening_residual: 330000, interest_rate: 3.8, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [82500, 82500, 82500] };
const mcc: FinancingLoanInput = { name: "Chirografario MCC 2024", amount: 0, opening_residual: 310000, interest_rate: 4.6, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [0, 55000, 55000] };
const nuovo: FinancingLoanInput = { name: "Nuovo finanziamento BPM", amount: 500000, opening_residual: 0, interest_rate: 4.5, grace_years: 1, balloon_pct: 0, duration_years: 6 };

describe("budget-finanziamenti-pregresso", () => {
  it("separa i contratti pregressi dai prestiti nuovi", () => {
    expect(contrattiPregressi([mutuo, nuovo, mcc]).map((l) => l.name)).toEqual(["Mutuo Intesa 2022", "Chirografario MCC 2024"]);
    expect(prestitiNuovi([mutuo, nuovo]).map((l) => l.name)).toEqual(["Nuovo finanziamento BPM"]);
  });
  it("righe: rimborsi riempiti all'orizzonte, resta e stato", () => {
    const [r] = contrattoRows([mutuo], 5);
    expect(r).toMatchObject({ name: "Mutuo Intesa 2022", residuo: 330000, tasso: 3.8, rimborsi: [82500, 82500, 82500, 0, 0], resta: 82500, stato: "resta aperto" });
    expect(restaStato(100, [100])).toBe("chiuso");
    expect(restaStato(100, [0, 0])).toBe("nessun rimborso nel piano");
    expect(restaStato(100, [60, 60])).toBe("oltre il residuo");
  });
  it("withRimborso scrive l'anno e tronca la lista all'orizzonte", () => {
    const out = withRimborso([mutuo], 0, 3, 82500, 3);
    expect(out[0].repayments).toEqual([82500, 82500, 82500]);
    expect(withRimborso([mutuo], 0, 1, null, 3)[0].repayments).toEqual([82500, 0, 82500]);
  });
  it("unisci: somma dei residui, tasso medio ponderato, rimborsi sommati", () => {
    const [u] = unisciContratti([mutuo, mcc], 3);
    expect(u).toMatchObject({ name: "Debiti verso banche", opening_residual: 640000, interest_rate: 4.2, repayments: [82500, 137500, 137500], amount: 0, duration_years: null });
  });
  it("nuovoContratto e' vuoto e nominato in sequenza", () => {
    expect(nuovoContratto(3, 3)).toEqual({ name: "Finanziamento C", amount: 0, opening_residual: 0, interest_rate: 4, grace_years: 0, balloon_pct: 0, duration_years: null, repayments: [0, 0, 0] });
  });
  it("quota dei mutui e controlli sulle banche", () => {
    expect(quotaMutui(bs, 90000)).toBe(82500);
    const c = controlliBanche(bs, 90000, [mutuo, mcc], 3, 2026);
    expect(c.fidiOltre).toBeNull();
    expect(c.quadra).toEqual({ ok: true, testo: "Fidi 90.000 € + residui dei finanziamenti 640.000 € · debiti verso banche nel bilancio: 640.000 €", esito: "quadra" });
    expect(c.rata).toEqual({ ok: true, testo: "Rimborsi 2027 dei finanziamenti: 82.500 € · quota dei mutui entro 12 mesi: 82.500 €", esito: "coerente" });
    const k = controlliBanche(bs, 200000, [mutuo], 3, 2026);
    expect(k.fidiOltre?.esito).toBe("da correggere");
    expect(k.quadra).toMatchObject({ ok: false, esito: "differenza 110.000 €" });
    expect(controlliBanche(bs, 90000, [{ ...mutuo, repayments: [100000, 0, 0] }, mcc], 3, 2026).rata.esito).toBe("17.500 € oltre la quota a breve");
    expect(controlliBanche(bs, 90000, [{ ...mutuo, repayments: [60000, 0, 0] }, mcc], 3, 2026).rata.esito).toBe("nel 2027 ne scadono 22.500 € in più");
  });
  it("controllo sugli altri finanziatori", () => {
    expect(controlloAltri(bs, [{ opening_residual: 150000, interest_rate: 0, repayments: [] }])).toMatchObject({ ok: true, esito: "quadra" });
    expect(controlloAltri(bs, [{ opening_residual: 100000, interest_rate: 0, repayments: [] }]).esito).toBe("differenza 50.000 €");
  });
});
```

- [ ] **Step 3: Rosso**

```bash
cd frontend && npx vitest run lib/budget-finanziamenti-pregresso.test.ts
```

- [ ] **Step 4: Modulo**

`frontend/lib/budget-finanziamenti-pregresso.ts` — le funzioni dell'interfaccia: `contrattoRows` riempie `repayments` con zeri fino a `horizon` e tronca oltre; `resta = residuo − Σ rimborsi`; `restaStato`: `Σ > residuo + 0,5` → «oltre il residuo», `resta < 0,5` → «chiuso», `Σ < 0,5` → «nessun rimborso nel piano», altrimenti «resta aperto»; `withRimborso` scrive `repayments[i] = value ?? 0` su una copia riempita/troncata a `horizon`; `unisciContratti`: `interest_rate = Math.round((Σ residuo × tasso / Σ residuo) × 10) / 10`, `repayments` sommati per indice; `nuovoContratto(n)` con la lettera `String.fromCharCode(64 + n)`; `controlliBanche`: `fidiOltre` = `fidi > sp16a + 0,5` → `{ ok: false, testo: "Fidi e anticipi (X €) superano i debiti a breve del bilancio (Y €)", esito: "da correggere" }`; `quadra` confronta `fidi + Σ residui` con `baseBankDebt(bs)` (`|differenza| < 1` → «quadra», altrimenti `differenza {baseBankDebt − fidi − Σ} €`); `rata`: `rep1 = Σ min(residuo, rimborsi[0])`, `quota = max(0, quotaMutui)`, `d = rep1 − quota`: `|d| < 1` → «coerente», `d < 0` → `nel {baseYear+1} ne scadono {−d} € in più`, `d > 0` → `{d} € oltre la quota a breve`. Gli importi con `new Intl.NumberFormat("it-IT", { maximumFractionDigits: 0 })`.

- [ ] **Step 5: Componente e motore (una riga)**

In `StepPatrimonialePregresso.tsx`, sotto la card «oltre 12 mesi»: la card **Debiti verso banche** (occhiello: «{baseBankDebt} € nel bilancio {anno} · di cui {sp16a} € a breve»): «1 · Dividi i debiti a breve» — `Select` regola (`Costanti`/`Seguono i ricavi`) + `Input` fidi + `Input` tasso % (scritti con `p.update(firstYear, "bank_lines_rule" | "bank_lines_amount" | "bank_lines_rate", v)`; alla prima visita senza valore, `bank_lines_amount` si scrive a 0 e la regola a «costante» — stessa scrittura una tantum del piano base del Task 13), la riga «Quota dei mutui entro 12 mesi» con `quotaMutui` (in rosso se negativa); «2 · Scadenzia i finanziamenti» — tabella `contrattoRows(contrattiPregressi(loans), horizon)` con `Input` nome/residuo/tasso e un `Input` per anno, colonna «resta» + chip stato, pulsante × (solo con piu' di una riga); pulsanti «+ Aggiungi finanziamento», «Unisci in un solo finanziamento», nota «Per fare in fretta…»; sotto, i tre controlli come righe `bg-muted` con il chip verde/ambra/rosso. Ogni scrittura ricompone `p.updateFinancingLoans(firstYear, [...contrattiAggiornati, ...prestitiNuovi(loansDelPrimoAnno)])`. La card **Altri finanziatori** allo stesso modo su `p.assumptions[firstYear].other_lenders` con `p.updateOtherLenders(list)` e `controlloAltri`; nota «Anni vuoti = nessun rimborso nel piano: il debito resta in bilancio oltre la fine del piano.». `FinancingLoansGrid` non e' piu' usata dal wizard (resta per `ScenarioFormStartup`, se la usa: `grep -rn FinancingLoansGrid frontend/`).

Motore: in `contratti_da_riga_finanziamento` `condizioni['name'] = loan.get('name')` e in `_contratti_dell_anno` `'nome': loan.get('name')` nella riga; in `tests/test_forecast_contratti_per_anno.py` aggiungere `assert contratti[0]["nome"] == "Mutuo"`; `DebitoBancarioContratto.nome?: string | null` nel tipo (Task 8 lo prevede).

- [ ] **Step 6: Verde, tsc, suite Python del contratto, commit**

```bash
cd frontend && npx vitest run lib/budget-finanziamenti-pregresso.test.ts && npx tsc --noEmit
cd .. && env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_forecast_contratti_per_anno.py tests/test_forecast_fidi.py -q -p no:cacheprovider
git add frontend/lib/budget-finanziamenti-pregresso.ts frontend/lib/budget-finanziamenti-pregresso.test.ts frontend/components/budget/wizard/steps/StepPatrimonialePregresso.tsx calculations/projection_common.py calculations/forecast_engine.py tests/test_forecast_contratti_per_anno.py
git commit -m "feat(ipotesi): passo Patrimoniale pregresso, seconda parte: banche per contratto con fidi separati, altri finanziatori per anno"
```

---

### Task 15: Passo 6 Patrimoniale piano

**Files:**
- Create: `frontend/lib/budget-piano-step.ts`, `frontend/lib/budget-piano-step.test.ts`
- Create: `frontend/components/budget/wizard/steps/StepPatrimonialePiano.tsx`
- Modify: `frontend/components/budget/wizard/BudgetWizard.tsx` (ramo `"patrimoniale-piano"`)
- Delete: `frontend/components/budget/wizard/steps/StepPregressoNuovo.tsx`, `frontend/lib/budget-pregresso-step.ts`, `frontend/lib/budget-pregresso-step.test.ts` (le funzioni ancora usate — `boolAssumption`, `singleYearValue`, `pregressoBase` — passano in `budget-piano-step.ts`)

**Interfaces:**
- Consumes: `details.tfr`, `details.debito_bancario` (con `fidi` e `contratti[].nome`), `details.altri_finanziatori`, `scopertoAvvisi`, `confermaCassaPositiva`, `ceAggregates` (`lib/budget-preview-rows.ts`), `minorFieldsRows`, `spIndexingOf`, `pianiPregressoOf`, `DRIVERS`, `DRIVER_LABELS` (`lib/budget-circolante-step.ts`), `p.updateFinancingLoans`, `p.updateSpIndexing`, `p.update`, `p.updateAll`
- Produces:
  ```ts
  export interface TfrRiga { year: number; accantonamento: number | null; liquidazione: number; chiusura: number | null; oltre: boolean; sospeso: boolean }
  export function tfrRighe(assumptions: AssumptionsMap, years: number[], data: ForecastPreviewResponse | null): TfrRiga[]
  export interface NuovoFinanziamento { year: number; index: number; loan: FinancingLoanInput }
  export function nuoviFinanziamenti(assumptions: AssumptionsMap, years: number[]): NuovoFinanziamento[]
  export function riepilogoNuovo(loan: FinancingLoanInput, year: number): string     // «500.000 € · 2027 · rata 100.000 €/anno dal 2029»
  export function annoLibero(years: number[], esistenti: readonly NuovoFinanziamento[]): number
  export function nuovoPrestito(year: number): FinancingLoanInput                    // «Nuovo finanziamento», 200.000, 5 anni, 0 preamm., 4,5%
  export function withNuovoCampo(loans: FinancingLoanInput[], index: number, field: keyof FinancingLoanInput, value: string | number | null): FinancingLoanInput[]
  export function rowsDebitoCassaPfn(baseBs: BalanceSheet, fidiBase: number | null, years: ForecastPreviewYear[]): PreviewRow[]
  export function rowsAltriCreditiDebiti(baseBs: BalanceSheet, years: ForecastPreviewYear[], regole: Record<string, string>): PreviewRow[]
  export function regoleVociMinori(assumptions: AssumptionsMap, years: number[]): Record<string, string>  // «costante» | «variazione +2,0%» | «segue i ricavi» | «segue gli acquisti» | «segue il personale»
  ```

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task15-base
```

- [ ] **Step 2: Test rosso**

`frontend/lib/budget-piano-step.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { AssumptionsMap } from "@/lib/budget-horizon";
import type { BalanceSheet, ForecastPreviewResponse, ForecastPreviewYear } from "@/types/api";
import {
  annoLibero, nuoviFinanziamenti, nuovoPrestito, regoleVociMinori, riepilogoNuovo, rowsAltriCreditiDebiti,
  rowsDebitoCassaPfn, tfrRighe,
} from "./budget-piano-step";

const asMap = (m: Record<number, Record<string, unknown>>): AssumptionsMap => m as unknown as AssumptionsMap;
const anni = [2027, 2028, 2029];
const y = (year: number, over: Record<string, unknown> = {}): ForecastPreviewYear => ({
  year,
  income_statement: { ce01_ricavi_vendite: 2500000, ce04_altri_ricavi: 35000, ce05_materie_prime: 1000000, ce06_servizi: 430000, ce07_godimento_beni: 86000, ce08_costi_personale: 620000, ce12_oneri_diversi: 41000 },
  balance_sheet: { sp16a_debiti_banche_breve: 262500, sp17a_debiti_banche_lungo: 565000, sp16b_debiti_altri_finanz_breve: 50000, sp17b_debiti_altri_finanz_lungo: 100000, sp02_immob_immateriali: 20000, sp03_immob_materiali: 1200000, sp09_disponibilita_liquide: 130000, sp06g_crediti_altri_breve: 48000, sp10_ratei_risconti_attivi: 12000, sp06e_crediti_tributari_breve: 18000, sp16f_debiti_previdenza_breve: 28000, sp16g_altri_debiti_breve: 45000, sp14_fondi_rischi: 20000, sp18_ratei_risconti_passivi: 10000 },
  details: {
    tfr: { apertura: 160000, accantonamento: 32148.15, liquidazioni: year === 2028 ? 50000 : 0, chiusura: 192148.15, sospeso: false },
    debito_bancario: { fidi: { apertura: 90000, variazione_ricavi: 0, rimborso_sweep: 0, residuo: 90000, regola: "costante" }, pregresso_senza_piano: null, pregresso_piano_anni: null,
      contratti: [
        { indice: 0, anno: 2027, nome: "Mutuo Intesa 2022", tasso: 3.8, erogato: 0, residuo_iniziale: 330000, rimborso: 82500, interessi: 12540, breve: 82500, lungo: 165000 },
        { indice: 1, anno: 2027, nome: "Nuovo finanziamento BPM", tasso: 4.5, erogato: 500000, residuo_iniziale: 0, rimborso: 0, interessi: 0, breve: 100000, lungo: 400000 },
      ] },
    altri_finanziatori: { apertura: 150000, rimborso: 0, interessi: 0, breve: 50000, lungo: 100000, mode: "contratti", contratti: [] },
    scoperto_residuo: 0,
    ...over,
  } as never,
} as unknown as ForecastPreviewYear);
const bs = { sp16a_debiti_banche_breve: "172500", sp17a_debiti_banche_lungo: "467500", sp16b_debiti_altri_finanz_breve: "0", sp17b_debiti_altri_finanz_lungo: "150000", sp02_immob_immateriali: "30000", sp03_immob_materiali: "1150000", sp09_disponibilita_liquide: "118000", sp15_tfr: "160000", sp06g_crediti_altri_breve: "48000", sp10_ratei_risconti_attivi: "12000", sp06e_crediti_tributari_breve: "18000", sp16f_debiti_previdenza_breve: "28000", sp16g_altri_debiti_breve: "45000", sp14_fondi_rischi: "20000", sp18_ratei_risconti_passivi: "10000" } as unknown as BalanceSheet;
const resp = (years: ForecastPreviewYear[], error: ForecastPreviewResponse["error"] = null): ForecastPreviewResponse => ({ scenario_id: 1, base_year: 2026, forecast_years: years, error });

describe("budget-piano-step", () => {
  it("tfrRighe legge i details e marca oltre il fondo", () => {
    const map = asMap({ 2027: { tfr_payments: 0 }, 2028: { tfr_payments: 50000 }, 2029: { tfr_payments: 300000 } });
    const errore = { year: 2029, message: "Liquidazioni TFR 2029: 300.000,00 superano il fondo disponibile (224.296,30); correggi al passo «Patrimoniale piano»" };
    const righe = tfrRighe(map, anni, resp([y(2027), y(2028)], errore));
    expect(righe[0]).toEqual({ year: 2027, accantonamento: 32148.15, liquidazione: 0, chiusura: 192148.15, oltre: false, sospeso: false });
    expect(righe[1].liquidazione).toBe(50000);
    expect(righe[2]).toMatchObject({ year: 2029, accantonamento: null, chiusura: null, liquidazione: 300000, oltre: true });
  });
  it("nuovi finanziamenti: per anno, con anno libero e riepilogo", () => {
    const map = asMap({ 2027: { financing_loans: [{ name: "Nuovo finanziamento BPM", amount: 500000, opening_residual: 0, duration_years: 6, grace_years: 1, interest_rate: 4.5, balloon_pct: 0 }, { name: "Mutuo", amount: 0, opening_residual: 330000, interest_rate: 3.8, repayments: [] }] }, 2028: {}, 2029: {} });
    const nf = nuoviFinanziamenti(map, anni);
    expect(nf.map((n) => [n.year, n.index, n.loan.name])).toEqual([[2027, 0, "Nuovo finanziamento BPM"]]);
    expect(riepilogoNuovo(nf[0].loan, 2027)).toBe("500.000 € · 2027 · rata 100.000 €/anno dal 2029");
    expect(annoLibero(anni, nf)).toBe(2028);
    expect(nuovoPrestito(2028)).toEqual({ name: "Nuovo finanziamento", amount: 200000, opening_residual: 0, duration_years: 5, grace_years: 0, interest_rate: 4.5, balloon_pct: 0 });
  });
  it("rowsDebitoCassaPfn: una riga per componente, una per nuovo finanziamento col nome", () => {
    const rows = rowsDebitoCassaPfn(bs, 90000, [y(2027)]);
    expect(rows.map((r) => r.key)).toEqual(["fidi", "contratti", "nuovo-1", "scoperto", "altri", "tfr-liq", "immob", "cassa", "pfn", "pfn-mol"]);
    expect(rows.find((r) => r.key === "nuovo-1")?.label).toBe("Nuovo finanziamento BPM");
    expect(rows.find((r) => r.key === "nuovo-1")?.years[0].value).toBe(500000);
    expect(rows.find((r) => r.key === "contratti")?.years[0].value).toBe(247500);
    expect(rows.find((r) => r.key === "pfn")?.years[0].value).toBe(262500 + 565000 + 50000 + 100000 - 130000);
    expect(rows.find((r) => r.key === "fidi")?.base.value).toBe(90000);
  });
  it("regole delle voci minori e tabella altri crediti e debiti", () => {
    const map = asMap({ 2027: { sp16f_growth_pct: 2, sp_indexing: { sp16g_altri_debiti_breve: "ricavi" }, previdenza_scales_with_personnel: false }, 2028: {} });
    const regole = regoleVociMinori(map, [2027, 2028]);
    expect(regole.sp16f_debiti_previdenza_breve).toBe("variazione +2,0%");
    expect(regole.sp16g_altri_debiti_breve).toBe("segue i ricavi");
    expect(regole.sp14_fondi_rischi).toBe("costante");
    const rows = rowsAltriCreditiDebiti(bs, [y(2027)], regole);
    expect(rows.map((r) => r.key)).toEqual(["h-attivo", "sp06g", "sp10", "sp06e", "tot-attivo", "h-passivo", "sp16f", "sp16g", "sp14", "sp18", "tot-passivo", "cassa"]);
    expect(rows.find((r) => r.key === "cassa")?.years[0].value).toBe((28000 + 45000 + 20000 + 10000 - 103000) - (48000 + 12000 + 18000 - 78000));
  });
});
```

- [ ] **Step 3: Rosso**

```bash
cd frontend && npx vitest run lib/budget-piano-step.test.ts
```

- [ ] **Step 4: Modulo**

`frontend/lib/budget-piano-step.ts` — `tfrRighe`: per ogni anno del piano, `accantonamento`/`chiusura` da `details.tfr` dell'anno prodotto (`null` se l'anteprima non lo ha), `liquidazione` dalla mappa, `oltre` = `liquidazione > apertura + accantonamento + 0,005` dei details **oppure** l'anno e' quello di `data.error.year` con un messaggio che inizia per «Liquidazioni TFR» (un anno non prodotto per un'altra ragione NON e' «oltre il fondo»); `nuoviFinanziamenti`: per anno, i `financing_loans` con `amount > 0`, con il loro indice nella lista dell'anno; `riepilogoNuovo`: `rata = amount / max(1, duration − grace)`, `dal = year + grace + 1`; `annoLibero`: il primo anno di piano senza nuovo finanziamento, altrimenti il primo; `withNuovoCampo`; `rowsDebitoCassaPfn`: `fidi` (base = `fidiBase`, anni = `debito_bancario.fidi.residuo`), riga `sweep` («ridotti con la cassa in eccesso», solo se un anno ha `rimborso_sweep > 0`, inserita dopo `fidi` — nel test non c'e'), `contratti` («Finanziamenti bancari esistenti», base = `baseBankDebt − fidiBase`, anni = Σ `breve + lungo` dei contratti con `residuo_iniziale > 0`), una riga `nuovo-{indice}` per ogni contratto con `residuo_iniziale === 0` (etichetta `nome` o «Nuovo finanziamento», base 0, valore `breve + lungo`), `scoperto` (`scoperto_residuo`), `altri` (`sp16b + sp17b`), `tfr-liq` («Fondo TFR · liquidazioni nell'anno», `−tfr.liquidazioni`), `immob`, `cassa` (`kind: "kpi"`), `pfn` (`kind: "total"`, = banche + altri + obbligazioni − cassa, come `finDebt` di `rowsPregressoNuovo`), `pfn-mol` (`pct` = PFN / MOL con `ceAggregates`); `regoleVociMinori`: per ciascuna delle sette voci (`sp06g`, `sp10`, `sp06e`, `sp16f`, `sp16g`, `sp14`, `sp18` → i campi `sp*_growth_pct` e le chiavi di `sp_indexing` di `minorFieldsRows`): driver → «segue i ricavi/gli acquisti/il personale», `previdenza_scales_with_personnel` → «segue il personale», crescita non nulla → «variazione +2,0%», altrimenti «costante»; `rowsAltriCreditiDebiti`: le dodici righe del test (le intestazioni `kind: "total"` con valori `null`, le voci `kind: "value"` con la regola in `note`, i totali, la riga `cassa` = (Δ passivo − Δ attivo) sull'anno prima, con l'anno base come apertura).

Portare qui `boolAssumption` (ri-esportata da `budget-horizon`), `singleYearValue`, `pregressoBase` da `budget-pregresso-step.ts` con i loro test; eliminare `budget-pregresso-step.ts`, il suo test e `StepPregressoNuovo.tsx` (`grep -rn "pregresso-step\|StepPregressoNuovo" frontend/` vuoto).

- [ ] **Step 5: Componente**

`StepPatrimonialePiano.tsx`, `grid gap-5 lg:grid-cols-2 items-start`. Sinistra: card **Voci minori · regola nel piano** (le righe di `minorFieldsRows` con il `Select` del driver e la percentuale, spostate da `StepCircolante` cosi' com'erano, piu' la riga in sola lettura «Crediti tributari · imposte anticipate · governati dalle imposte · passo 7»); card **Fondo TFR** (occhiello `{sp15} € al 31/12/{anno}`; riga «Accantonamento annuo · retribuzioni / 13,5» con la `Checkbox` `tfr_accrual_suspended` via `p.updateAll`; tabella `tfrRighe`: accantonamento in sola lettura («sospeso» se sospeso), `Input` liquidazioni per anno via `p.update(y, "tfr_payments", v)`, «Fondo a fine anno» con il chip rosso «oltre il fondo»; nota «Liquidazioni: pensionamenti, dimissioni, licenziamenti. Escono di cassa nell'anno e riducono il fondo.»); card **Nuovi investimenti** (`INVESTMENT_ROWS` e i due tassi, come oggi); card **Nuovi finanziamenti** (una card `border-l-2 border-l-primary` per `nuoviFinanziamenti`: `Input` nome in testa, riepilogo `riepilogoNuovo`, ×; cinque campi importo / erogato nel (`Select` sugli anni: cambiare anno = togliere dalla lista dell'anno vecchio e aggiungere a quella del nuovo, con `p.updateFinancingLoans` due volte) / durata / preammortamento / tasso; «+ Aggiungi finanziamento» → `p.updateFinancingLoans(annoLibero, [...loansDiQuellAnno, nuovoPrestito(anno)])`; note del prototipo); card **Cassa e scoperto** (le due `Checkbox` con i testi del prototipo, tetto e cassa minima accanto; accordion «Mostra tutte» con le cessioni). Destra: `PreviewPanel` «Debito, cassa e PFN» (`rowsDebitoCassaPfn(baseBs, fidiBase, previewYears)` con `fidiBase = p.assumptions[firstYear]?.bank_lines_amount ?? null`; sotto, gli avvisi di oggi da `StepPregressoNuovo`: `previewNotice`, `scopertoAvvisi`, `confermaCassaPositiva`) e `PreviewPanel` «Altri crediti e debiti del piano · dalle voci minori» (`rowsAltriCreditiDebiti`). `BudgetWizard.tsx`: `"patrimoniale-piano"` → `<StepPatrimonialePiano {...stepProps} />`.

- [ ] **Step 6: Verde, tsc, commit**

```bash
cd frontend && npx vitest run lib/budget-piano-step.test.ts lib/budget-circolante-step.test.ts && npx tsc --noEmit
git add -u frontend/components/budget/wizard/steps/StepPregressoNuovo.tsx frontend/lib/budget-pregresso-step.ts frontend/lib/budget-pregresso-step.test.ts
git add frontend/lib/budget-piano-step.ts frontend/lib/budget-piano-step.test.ts frontend/components/budget/wizard/steps/StepPatrimonialePiano.tsx frontend/components/budget/wizard/BudgetWizard.tsx
git commit -m "feat(ipotesi): passo Patrimoniale piano: voci minori, TFR con liquidazioni, nuovi finanziamenti multipli, debito cassa e PFN"
```

---

### Task 16: Passo 7, wizard, rail, documentazione utente

**Files:**
- Modify: `frontend/components/budget/wizard/steps/StepImposte.tsx` e `frontend/lib/budget-imposte-step.ts` (+ test): la card «Pagamento dei debiti tributari» perde saldo, rateizzato, «N rate uguali» e la `PregressoTable` (decisione del 2026-09-15: stanno al passo 5, Task 13b); resta l'acconto. Un rimando in fondo: «Debiti tributari al 31/12/{anno}: saldo e rate si scadenziano al passo 5 · Patrimoniale pregresso». Via gli export rimasti senza chiamanti (`withSaldo`, `withRateUguali`, `rateOptions`, `rateSelectValue`, `tributariMasses`, `tributariTabella`, `TRIBUTARI_KEYS`, `TRIBUTARI_TABELLA_NOTA`: `grep -rn` prima di togliere)
- Delete: `frontend/components/budget/wizard/PregressoTable.tsx`, `frontend/lib/budget-pregresso-tabella.ts`, `frontend/lib/budget-pregresso-tabella.test.ts` (dopo il Task 15 e la modifica sopra non li usa piu' nessuno: `grep -rn "pregresso-tabella\|PregressoTable" frontend/` vuoto; `TabellaPregressoKey`/`TABELLA_KEYS` gia' spostati dal Task 13)
- Modify: `calculations/forecast_engine.py` — `_PREGRESSO_PASSO` perde `"debiti_tributari": "Imposte"` (saldo e rate si scadenziano al passo «Patrimoniale pregresso»); il commento sopra si riscrive; i messaggi che nominano «Imposte» per il **piano** tributario (`grep -n "Imposte" calculations/forecast_engine.py`) passano a `_passo_pregresso("debiti_tributari")`; restano «Imposte» solo quelli su acconto e via manuale. Test: `tests/test_forecast_override_tributario.py` (le attese a `:525` e `:981`) e `frontend/lib/budget-wizard-steps*` / `stepForErrorMessage` se instrada i messaggi tributari a `imposte`. Parte dopo il merge del Task 4 (stesso file del motore).
- Modify: `frontend/components/budget/wizard/BudgetWizard.tsx` (gli import residui, `railBadges`, `MigrazioneCard`; `grep -n "inflation\|StepAltreVociCE\|StepPregressoNuovo" frontend/components/budget/wizard/BudgetWizard.tsx` vuoto)
- Modify: `docs/budget/FORECASTING_GUIDE.md` (CRLF: preservare) — le sezioni «Passo 3 · Costi principali», «Passo 4 · Altre voci CE», «Passo 5 · Capitale circolante», «Passo 6 · Pregresso e nuovo» riscritte come «Passo 3 · Costi», «Passo 4 · Capitale circolante», «Passo 5 · Patrimoniale pregresso», «Passo 6 · Patrimoniale piano» (che cosa inserisci / che cosa ne fa il motore / che cosa mostra l'anteprima, con i testi della spec §4.3-§4.6); «Passo 1» con l'inflazione salvata e senza seme; una sezione «Scenari salvati prima del 15/09/2026» (spec §4.8)
- Modify: `docs/frontend/PRATICA-PERCORSO.md` e `CLAUDE.md` (ogni «Pregresso e nuovo» / «Altre voci CE» / «Costi principali»: `grep -rn "Pregresso e nuovo\|Altre voci CE\|Costi principali" CLAUDE.md docs/frontend docs/budget`), in particolare la frase di CLAUDE.md «il passo del wizard che lo scadenzia (6 `Pregresso e nuovo`, 7 `Imposte` per i tributari)» → «(5 «Patrimoniale pregresso», tributari compresi)», e la via d'uscita «modificare il piano nel passo «Imposte»» del bullet «Un anno manuale non scarica il piano tributario» → «nel passo «Patrimoniale pregresso»»
- Modify: `docs/budget/API-PREVISIONALE.md` §7 (i passi che chiamano l'anteprima) dove nomina i passi

- [ ] **Step 1: Base del task**

```bash
git rev-parse HEAD > /tmp/rilievi-task16-base
file docs/budget/FORECASTING_GUIDE.md
```

- [ ] **Step 2: Componenti**

`StepImposte.tsx`: la card dei tributari ridotta all'acconto e il rimando al passo 5 (sopra); motore e test dei messaggi come nell'elenco dei file. `BudgetWizard.tsx`: i sette rami del `switch` sui componenti definitivi (`StepScenario`, `StepFatturato`, `StepCosti`, `StepCircolante`, `StepPatrimonialePregresso`, `StepPatrimonialePiano`, `StepImposte`), `badges={railBadges(s.migrazione?.daIntegrare.map((d) => d.step) ?? [])}` sul `WizardRail`, `MigrazioneCard` sotto il rail.

```bash
cd frontend && npx tsc --noEmit && npx vitest run
```
Atteso: `tsc` pulito, suite intera verde (~730 test).

- [ ] **Step 3: Documentazione**

Riscrivere le sezioni della guida elencate sopra preservando i CRLF (aprire con un editor che li mantiene; `git diff --stat docs/budget/FORECASTING_GUIDE.md` deve contare le righe cambiate, non il file intero). Ogni `file:riga` citato si apre e si controlla. `CLAUDE.md`: la frase sui passi e, in «Forecasting Engine», una riga finale al paragrafo del cash sweep gia' aggiunta al Task 3; nella sezione «Frontend pages» nessuna modifica (le rotte non cambiano).

- [ ] **Step 4: Commit**

```bash
git add -u frontend/components/budget/wizard/PregressoTable.tsx frontend/lib/budget-pregresso-tabella.ts frontend/lib/budget-pregresso-tabella.test.ts
git add frontend/components/budget/wizard/steps/StepImposte.tsx frontend/lib/budget-imposte-step.ts frontend/lib/budget-imposte-step.test.ts calculations/forecast_engine.py tests/test_forecast_override_tributario.py frontend/components/budget/wizard/BudgetWizard.tsx docs/budget/FORECASTING_GUIDE.md docs/frontend/PRATICA-PERCORSO.md CLAUDE.md docs/budget/API-PREVISIONALE.md
git commit -m "docs(ipotesi): guida e invarianti sui sette passi nuovi; passo Imposte con i rimandi"
```

---

## Ondata C — verifica di fine lotto

### Task 17: Verifica di fine lotto

**Files:**
- Modify (solo se il collaudo trova difetti): i file del task che li ha introdotti, con un commit `fix(ipotesi): …` per rilievo
- Create: `.superpowers/sdd/2026-09-15-percorso-ipotesi-rilievi/collaudo.md` (fuori dal repo: la cartella `.superpowers/` non e' tracciata, non si cancella)

- [ ] **Step 1: Suite, tipi, banco**

```bash
git rev-parse HEAD > /tmp/rilievi-task17-base
env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/ -q -p no:cacheprovider
cd frontend && npx vitest run && npx tsc --noEmit && cd ..
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/rilievi-task1-base)" --anni 4 --controllo-negativo --json /tmp/rilievi-task17-parita.json --log /tmp/rilievi-task17-parita.log
/home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/rilievi-task17-parita.json --attese "fidi_contratti_anno" "altri_finanziatori_anno" "tfr_liquidazioni"
```
Atteso: pytest tutto verde (i due test vision intermittenti passano al rilancio); vitest verde; `tsc` pulito; il banco fra la base del lotto e l'HEAD diverge SOLO sui tre profili nuovi.

- [ ] **Step 2: Collaudo a schermo**

Server di collaudo su una copia del DB, migrata (le porte 3000 e 8001 sono di Formula Finance; 8011/3002 sono quelle dei collaudi precedenti):

```bash
cp /home/peter/DEV/budget/financial_analysis.db /tmp/rilievi-collaudo.db
/home/peter/DEV/budget/backend/venv/bin/python migrate_db.py /tmp/rilievi-collaudo.db   # migrate_db.py legge il percorso da argv[1], NON da DATABASE_PATH
cd backend && DATABASE_PATH=/tmp/rilievi-collaudo.db DEV_USER_ID=dev-user-001 /home/peter/DEV/budget/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8011 &
cd frontend && NEXT_PUBLIC_API_URL=http://127.0.0.1:8011/api/v1 npx next dev -p 3002 &
```
(la variabile dell'URL dell'API: controllare il nome in `frontend/lib/api.ts`). Dispatch dell'agente `collaudatore` con questo mandato: «Scenario salvato prima del lotto (azienda con debito bancario e altri finanziatori): apri il wizard, verifica la card ricalcolato/da integrare e i badge sui passi 1 e 5; passo 3: le caselle azzurre seguono l'inflazione del passo 1, una scritta resta, il pareggio ha grafico, formula e tabella; passo 4: azienda con fornitori a zero (PROVA AMBIENTA, id 237) mostra l'avviso; passo 5: dividi i fidi, scadenzia due contratti, unisci, controlli che quadrano/non quadrano, altri finanziatori; passo 6: liquidazione TFR oltre il fondo → l'anteprima dice l'errore e il passo; due nuovi finanziamenti con nome → due righe nell'anteprima; sweep acceso riduce solo i fidi; salva e calcola → CE Prev./SP Prev. coerenti con l'anteprima (sp16a = fidi + rate dell'anno dopo + quota nuovi; sp15 dopo la liquidazione); riapri lo scenario: nessuna card di migrazione, valori come salvati. Restituisci il log e i rilievi riproducibili.» Registro in `.superpowers/sdd/2026-09-15-percorso-ipotesi-rilievi/collaudo.md`. Ogni rilievo bloccante si corregge nel task d'origine con un commit `fix(ipotesi): …` e si ripete la verifica del passo 1.

- [ ] **Step 3: Riallineamento della documentazione**

```bash
/home/peter/DEV/budget/backend/venv/bin/python scripts/riallinea.py --help
```
Eseguire `/riallinea` (skill `.claude/skills/riallinea/`) senza `--registra` sul diff `$(cat /tmp/rilievi-task1-base)..HEAD`: ogni affermazione falsa trovata in `CLAUDE.md`, `docs/budget/*.md`, `docs/frontend/PRATICA-PERCORSO.md` si corregge in un commit `docs(ipotesi): riallineamento`.

- [ ] **Step 4: Chiusura**

Aggiornare la memoria del progetto (`percorso-ipotesi-budget-lotti.md`: stato del lotto, branch, cosa resta al proprietario: merge in `main`, `migrate_db.py` al rilascio, le due domande ancora aperte della spec §9). Riferire al proprietario: suite, banco, collaudo, i rilievi corretti e quelli lasciati fuori con il perche'.

---

## Numeri usati negli oracoli

Tutti i numeri attesi dei test dei Task 2-6 sono calcolati **a mano** dalle regole della spec sul kit `tests/e2e_kit.py` (`BASE_BS`/`BASE_CE`) o sui saldi che il test stesso scrive: chi esegue li ricontrolla prima di scrivere il codice e, se un numero non torna per un centesimo di arrotondamento (ROUND_HALF_UP al centesimo sul persistito), corregge l'atteso nel test **dichiarando nel commit** il numero misurato e perche' — mai il contrario. Un numero che non torna per piu' di un centesimo e' un difetto del motore o dell'oracolo, e si ferma a capire quale.
