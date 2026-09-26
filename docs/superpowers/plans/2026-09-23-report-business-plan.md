# Report Business plan — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un secondo report PDF, «Business plan», che riproduca il layout di `BUSINESS PLAN RIVISITATO.pdf` con i numeri del motore, per le pratiche infrannuale, bilancio e startup, scaricabile da `/report` accanto al dossier.

**Architecture:** `FinalReportModelV2` → `data.from_report` → `BusinessPlanData` (numeri già allineati alle colonne) → sezioni ReportLab (`sections_*.py`) + grafici matplotlib (`charts.py`) + testi a regole (`narrative.py`) → `document.render_business_plan` → rotta `POST …/business-plan/pdf`. Il renderer non vede mai il modello v2: legge solo `BusinessPlanData`. Per questo il banco di prova può dargli in pasto i numeri del PDF del committente e confrontare le pagine.

**Tech Stack:** Python 3.12, ReportLab 4.2.5, matplotlib 3.9.3 (solo API `Figure`, mai `pyplot`), PyMuPDF (solo nei test), FastAPI, Next.js 15 + Vitest.

**Spec:** `docs/superpowers/specs/2026-09-23-report-business-plan-design.md`

**Prova a secco (2026-09-23):** il codice dei moduli di questo piano è stato estratto ed eseguito in una scratchpad
contro una copia del DB locale. Risultati: AMBIENTA (575/18) 19 pagine come il riferimento, AIC SRL (21/16) 18,
STARTUP SRL (628/24) 18, circa 3 secondi ciascuno. Banco strutturale verde sulle pagine 4, 6 e 7, con scarto massimo
di 4,4 pt su `y0`. `test_bp_fmt` e `test_bp_narrative` sono verdi sul codice del piano. Le correzioni emerse dalla
prova sono già dentro il piano: colori in `layout._ps`, righe di gruppo degli allegati, spaziatura delle tabelle
(`pad`), ordine dei grafici della sezione 6, colore delle etichette degli assi. La prova non sostituisce i test dei
task: li precede.

## Global Constraints

- Worktree: `/home/peter/DEV/budget-report-bp`, branch `feat/report-business-plan`. Mai lavorare nell'albero principale `/home/peter/DEV/budget`, che ha lavoro non committato su `presentation-fix`.
- Python: `PY=/home/peter/DEV/budget/backend/venv/bin/python`; i test si lanciano da `backend/`: `cd /home/peter/DEV/budget-report-bp/backend && $PY -m pytest ../tests/<file> -q`.
- Money is `Decimal`, never `float`, fino al disegno: la conversione a `float` avviene solo dentro `charts.py`.
- Percentuali assolute (5 = 5%), come nel resto del repo e nel modello v2.
- Nessuna scrittura sul DB, nessuna chiamata AI dal PDF.
- Valore assente ⇒ `n.d.` in tabella, nessuna barra nel grafico, nessuna frase nel testo. Mai zero inventato.
- UI e testi in italiano; niente emoji.
- Palette (misurata sul riferimento): navy `#1f3a5f`, teal `#2a9d8f`, arancio `#e9a23b`, arancio scuro `#9a6512`, grigio `#9aa5b1`, rosso `#c8553d`, azzurro `#a9c4e2`, griglia `#e6e8ec`, assi `#3e4c59`, inchiostro `#1f2933`, attenuato `#616e7c`, filetto `#d9dee4`, riquadro KPI `#e8f1f8`, riga evidenziata `#e6f4f1`, pannello `#f2f5f8`, debolezza `#fbedea`, sottotitolo copertina `#c9d6e3`.
- Pagina A4, margine laterale 48,2 pt, fascia d'intestazione 31,2 pt, filetto del piè di pagina a 807,9 pt dall'alto.
- Grafici: larghezza 7,2″, altezza in decimi di pollice, 220 dpi, sfondo trasparente, font Lato.
- Ogni commit termina con la riga `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Prima di ogni commit: `git diff --stat`, per il rischio di fine riga misti (memoria del progetto).

## Review Focus

1. **Pratica con valori assenti o a zero** (startup con ricavi nulli, indicatori `None`, rendiconto base assente): il PDF esce lo stesso, con `n.d.` e grafici senza la barra, senza `ZeroDivisionError`. Test in Task 2 (`test_from_report_startup`), Task 3 (`test_grafici_con_valori_assenti`), Task 6 (`test_narrativa_senza_dati`) e Task 10 (render reale sul fixture minimo della rotta).
2. **Piano a 5 anni** (6 colonne di valori): le tabelle stanno nella larghezza della pagina e i grafici hanno 6 categorie. Test in Task 4 (`test_tabella_sei_colonne_sta_in_pagina`).
3. **Valori negativi** (EBITDA, flussi, cassa, margine di sicurezza): l'asse include lo zero, le etichette vanno sotto la barra e il segno è `−` (U+2212) in tabella. Test in Task 1 (`fmt`) e Task 3.
4. **Nome azienda lungo o fuori Latin-1**: la copertina va a capo, il nome file ha una versione ASCII. Test in Task 10 (`test_nome_file_ascii`).
5. **Render concorrenti** (FastAPI esegue le rotte sync in un threadpool): nessuno stato globale di `pyplot`, nessuna modifica di `rcParams` dopo l'import. Test in Task 3 (`test_render_concorrente`).

---

## File Structure

```
backend/app/renderers/business_plan/
  __init__.py            re-export: render_business_plan, from_report, BusinessPlanData
  theme.py               palette, misure di pagina, registrazione font ReportLab
  fmt.py                 formati italiani: euro, %, ×, gg, compatti (€ 4,11 mln)
  data.py                BusinessPlanData + from_report(report) + JSON del banco
  charts.py              8 grafici matplotlib → PNG bytes
  layout.py              stili, intestazione e piè, riquadri, tabelle, pannelli
  narrative.py           testi a regole e soglie
  sections_sintesi.py    copertina, sezione 1 (sintesi, forza/debolezza/azioni)
  sections_economia.py   sezioni 2–5
  sections_finanza.py    sezioni 6–8
  sections_partenza.py   sezioni 9–10
  sections_allegati.py   Allegati A–E
  document.py            catalogo delle sezioni, due passate per l'indice, render
  fonts/Lato-Regular.ttf, fonts/Lato-Bold.ttf, fonts/OFL.txt
backend/app/schemas/business_plan.py          BusinessPlanPdfRequest
backend/app/services/business_plan_pdf_service.py
backend/app/api/v1/reports.py                  + rotta POST …/business-plan/pdf
tests/test_bp_fmt.py, test_bp_data.py, test_bp_charts.py, test_bp_layout.py,
tests/test_bp_banco.py, test_bp_narrative.py, test_bp_document.py, test_bp_endpoint.py
tests/fixtures/business_plan/banco_ambienta.json
tests/.banco-business-plan/  (gitignored: riferimento.pdf, PNG di confronto)
tools/business_plan/confronta.py              PNG affiancati per la verifica vision
frontend/lib/api.ts, lib/final-report-download.ts, hooks/use-final-report-download.ts, app/report/page.tsx
docs/budget/BUSINESS-PLAN-PDF.md, CLAUDE.md
```

---

### Task 1: Fondamenta — font, tema, formati, banco

**Files:**
- Create: `backend/app/renderers/business_plan/__init__.py`, `theme.py`, `fmt.py`, `fonts/Lato-Regular.ttf`, `fonts/Lato-Bold.ttf`, `fonts/OFL.txt`
- Modify: `.gitignore`
- Test: `tests/test_bp_fmt.py`

**Interfaces:**
- Produces: `theme.register_fonts() -> None`, constants `theme.NAVY … theme.COVER_SUB`, `theme.PAGE_W, PAGE_H, LM, CW, HEADER_H, FOOTER_RULE_Y, FONT_DIR, REGULAR, BOLD`; `fmt.eur(v) -> str`, `fmt.pct(v, dec=2)`, `fmt.ratio(v, dec=2)`, `fmt.days(v, dec=1)`, `fmt.value(v, unit)`, `fmt.compact_eur(v)`, `fmt.compact_range(a, b)`, `fmt.pct_short(v)`, `fmt.chart_num(v, dec=0) -> str`, `fmt.prep(word, value_str) -> str`, costante `fmt.ND = "n.d."`, `fmt.MINUS = "−"`.

- [ ] **Step 1: Prepara il banco e i font**

```bash
cd /home/peter/DEV/budget-report-bp
mkdir -p tests/.banco-business-plan backend/app/renderers/business_plan/fonts tests/fixtures/business_plan tools/business_plan
cp "/home/peter/DEV/budget/inbox/BUSINESS PLAN RIVISITATO.pdf" tests/.banco-business-plan/riferimento.pdf
S=/tmp/claude-1000/-home-peter-DEV-budget/c84cb587-b7a2-4376-a794-7618627d4d71/scratchpad
cp $S/fonts/Lato-Regular.ttf $S/fonts/Lato-Bold.ttf backend/app/renderers/business_plan/fonts/ 2>/dev/null || \
  for f in Lato-Regular Lato-Bold; do curl -sfL -o backend/app/renderers/business_plan/fonts/$f.ttf https://github.com/google/fonts/raw/main/ofl/lato/$f.ttf; done
curl -sfL -o backend/app/renderers/business_plan/fonts/OFL.txt https://github.com/google/fonts/raw/main/ofl/lato/OFL.txt
printf '\n# Banco del report Business plan: PDF del committente e PNG di confronto, mai in git\ntests/.banco-business-plan/\n' >> .gitignore
file backend/app/renderers/business_plan/fonts/*.ttf
```
Expected: due righe `TrueType Font data`.

- [ ] **Step 2: Scrivi il test dei formati**

`tests/test_bp_fmt.py`:
```python
"""Formati italiani del Business plan: i valori attesi sono letti dal PDF del committente."""
from decimal import Decimal as D

from app.renderers.business_plan import fmt


def test_euro_e_segno():
    assert fmt.eur(D("4109510")) == "4.109.510"
    assert fmt.eur(D("-45192.4")) == "−45.192"
    assert fmt.eur(D("0")) == "0"
    assert fmt.eur(None) == "n.d."


def test_percentuali_rapporti_giorni():
    assert fmt.pct(D("4.035447")) == "4,04%"
    assert fmt.pct(D("-4.31")) == "−4,31%"
    assert fmt.ratio(D("5.7941"), 3) == "5,794×"
    assert fmt.ratio(D("2.94")) == "2,94×"
    assert fmt.days(D("119")) == "119,0 gg"
    assert fmt.value(D("12.5"), "percent") == "12,50%"
    assert fmt.value(D("1000"), "eur") == "1.000"
    assert fmt.value(None, "ratio") == "n.d."


def test_compatti():
    assert fmt.compact_eur(D("4109510")) == "€ 4,11 mln"
    assert fmt.compact_eur(D("4001471")) == "€ 4,00 mln"
    assert fmt.compact_eur(D("402197")) == "€ 402,2 mila"
    assert fmt.compact_eur(D("150000")) == "€ 150 mila"
    assert fmt.compact_eur(D("-150000")) == "−€ 150 mila"
    assert fmt.compact_eur(D("55")) == "€ 55"
    assert fmt.compact_range(D("960883"), D("73185")) == "€ 961 → 73 mila"
    assert fmt.compact_range(D("4109510"), D("4673885")) == "€ 4,11 → 4,67 mln"


def test_crescite_e_preposizioni():
    assert fmt.pct_short(D("5.000000")) == "5%"
    assert fmt.pct_short(D("5.5")) == "5,5%"
    assert fmt.prep("del", "5%") == "del 5%"
    assert fmt.prep("del", "1%") == "dell'1%"
    assert fmt.prep("dal", "8,61%") == "dall'8,61%"
    assert fmt.prep("al", "11%") == "all'11%"
    assert fmt.prep("al", "14,39%") == "al 14,39%"
    assert fmt.prep("dal", "180%") == "dal 180%"
    assert fmt.prep("del", "18%") == "dell'18%"


def test_numeri_dei_grafici_usano_il_trattino_ascii():
    assert fmt.chart_num(-225.5) == "-226"
    assert fmt.chart_num(4109.51) == "4.110"
    assert fmt.chart_num(8.614, 2) == "8,61"
```

- [ ] **Step 3: Verifica che fallisca**

Run: `cd backend && $PY -m pytest ../tests/test_bp_fmt.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.renderers.business_plan'`

- [ ] **Step 4: Scrivi `theme.py`, `fmt.py`, `__init__.py`**

`backend/app/renderers/business_plan/theme.py`:
```python
"""Palette, misure di pagina e font del Business plan, misurati sul PDF del committente."""
from __future__ import annotations

from pathlib import Path
from threading import Lock

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).parent / "fonts"
REGULAR, BOLD = "Lato-Regular", "Lato-Bold"

NAVY, TEAL, ORANGE, ORANGE_DARK = "#1f3a5f", "#2a9d8f", "#e9a23b", "#9a6512"
GREY, RED, LIGHTBLUE = "#9aa5b1", "#c8553d", "#a9c4e2"
GRID, AXIS, INK, MUTED, RULE = "#e6e8ec", "#3e4c59", "#1f2933", "#616e7c", "#d9dee4"
TILE, HL, PANEL, WEAK, COVER_SUB = "#e8f1f8", "#e6f4f1", "#f2f5f8", "#fbedea", "#c9d6e3"

PAGE_W, PAGE_H = A4
LM = 48.2
CW = PAGE_W - 2 * LM
HEADER_H = 31.2
FOOTER_RULE_Y = 807.9  # dall'alto, come lo misura PyMuPDF

_lock = Lock()
_registered = False


def register_fonts() -> None:
    """Registra Lato in ReportLab una volta sola, anche con render concorrenti."""
    global _registered
    with _lock:
        if _registered:
            return
        for name in (REGULAR, BOLD):
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / f"{name}.ttf")))
        _registered = True
```

`backend/app/renderers/business_plan/fmt.py`:
```python
"""Formati italiani del Business plan. Il segno meno delle tabelle è U+2212, quello dei grafici è ASCII."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

ND = "n.d."
MINUS = "−"
Num = Optional[Decimal]


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _q(v, dec: int) -> Decimal:
    return _dec(v).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)


def _group(v, dec: int) -> str:
    s = format(abs(_q(v, dec)), f",.{dec}f")
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _signed(v, dec: int, suffix: str = "") -> str:
    if v is None:
        return ND
    sign = MINUS if _q(v, dec) < 0 else ""
    return f"{sign}{_group(v, dec)}{suffix}"


def eur(v: Num) -> str:
    return _signed(v, 0)


def pct(v: Num, dec: int = 2) -> str:
    return _signed(v, dec, "%")


def ratio(v: Num, dec: int = 2) -> str:
    return _signed(v, dec, "×")


def days(v: Num, dec: int = 1) -> str:
    return _signed(v, dec, " gg")


def value(v: Num, unit: str) -> str:
    """Formato per unità del modello v2: eur | percent | ratio | days | score."""
    if unit == "eur":
        return eur(v)
    if unit == "percent":
        return pct(v)
    if unit == "days":
        return days(v)
    return ratio(v) if unit == "ratio" else _signed(v, 2)


def _trim(s: str) -> str:
    return s[:-2] if s.endswith(",0") else s


def compact_eur(v: Num) -> str:
    """€ 4,11 mln · € 402,2 mila · € 150 mila · € 55 (sempre due decimali sui milioni)."""
    if v is None:
        return ND
    v = _dec(v)
    sign = MINUS if v < 0 else ""
    a = abs(v)
    if a >= 1_000_000:
        body = f"{_group(a / 1_000_000, 2)} mln"
    elif a >= 1_000:
        body = f"{_trim(_group(a / 1_000, 1))} mila"
    else:
        body = _group(a, 0)
    return f"{sign}€ {body}"


def compact_range(a: Num, b: Num) -> str:
    """€ 4,11 → 4,67 mln · € 961 → 73 mila: una sola unità, scelta sul valore più grande."""
    if a is None or b is None:
        return ND
    a, b = _dec(a), _dec(b)
    top = max(abs(a), abs(b))
    if top >= 1_000_000:
        div, dec, unit = Decimal(1_000_000), 2, " mln"
    elif top >= 1_000:
        div, dec, unit = Decimal(1_000), 0, " mila"
    else:
        div, dec, unit = Decimal(1), 0, ""
    return f"€ {_signed(a / div, dec)} → {_signed(b / div, dec)}{unit}"


def pct_short(v: Num) -> str:
    """5% · 5,5% · 0%: per le liste di crescita («5% / 6% / 1%»)."""
    if v is None:
        return ND
    q = _q(v, 2)
    if q == q.to_integral_value():
        return _signed(q, 0, "%")
    return _trim_pct(q)


def _trim_pct(q: Decimal) -> str:
    s = _signed(q, 2, "")
    s = s.rstrip("0").rstrip(",")
    return s + "%"


def chart_num(v: float, dec: int = 0) -> str:
    """Etichetta di grafico: separatori italiani, segno meno ASCII come nel riferimento."""
    s = format(round(float(v), dec) + 0.0, f",.{dec}f")
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def prep(word: str, value_str: str) -> str:
    """«del 5%», «dell'1%», «dall'8,61%»: elisione davanti ai numeri che si leggono con vocale."""
    bare = value_str.lstrip(MINUS)
    integer = bare.split(",")[0].rstrip("%").replace(".", "")
    elide = integer.startswith("8") or integer in ("1", "11", "18")
    if not elide:
        return f"{word} {value_str}"
    return {"del": "dell'", "dal": "dall'", "al": "all'"}[word] + value_str
```

`backend/app/renderers/business_plan/__init__.py`:
```python
"""Report Business plan: ReportLab + matplotlib, accanto al dossier Typst."""
```

- [ ] **Step 5: Verifica che passi**

Run: `cd backend && $PY -m pytest ../tests/test_bp_fmt.py -q`
Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add .gitignore backend/app/renderers/business_plan tests/test_bp_fmt.py
git diff --cached --stat
git commit -m "feat(report-bp): fondamenta del Business plan — Lato, palette, formati italiani

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `BusinessPlanData` e `from_report`

**Files:**
- Create: `backend/app/renderers/business_plan/data.py`
- Test: `tests/test_bp_data.py`

**Interfaces:**
- Consumes: `app.schemas.final_report_v2.FinalReportModelV2`; `fmt.eur` (per gli esiti dei controlli).
- Produces:
  - `Column(period_id: str, year: int, label: str, is_base: bool)`
  - `AnnexRow(label: str, level: int, kind: str, values: tuple)`
  - `IndicatorRow(label: str, unit: str, values: tuple)`
  - `AssumptionRow(label: str, unit: str, values: tuple)`
  - `TableBlock(title: str, headers: tuple[str, ...], rows: tuple[tuple[str, tuple, str], ...], note: str = "")`
  - `StartingPoint(kind, title, intro, tiles: tuple[tuple[str,str,str],...], tables: tuple[TableBlock,...], indicator_headers: tuple[str,...], indicators: tuple[IndicatorRow,...], checks: tuple[tuple[str,str],...], note: str)`
  - `BusinessPlanData` (campi sotto), con i metodi `v(key) -> tuple`, le proprietà `plan_idx: list[int]`, `plan_columns`, `first`, `last`, `plan_years`, e la funzione `legend(data) -> str`
  - `VALUE_KEYS: tuple[str, ...]`, `UNITS: dict[str, str]`
  - `from_report(report, *, draft: bool) -> BusinessPlanData`
  - `load_json(path) -> BusinessPlanData`, `dump_json(data) -> dict`

- [ ] **Step 1: Scrivi il test**

`tests/test_bp_data.py`:
```python
"""from_report sui bilanci veri del DB locale (regola del proprietario: niente bilanci inventati).

Il DB viene COPIATO in una cartella temporanea; senza DB i test si saltano, come in test_intermedio_report.
"""
import os
import shutil
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.renderers.business_plan.data import VALUE_KEYS, BusinessPlanData, dump_json, from_report, load_json

ROOT = Path(__file__).resolve().parents[1]
_DB = Path(os.environ.get("BUDGET_REAL_DB", "/home/peter/DEV/budget/financial_analysis.db"))
CASI = {"infrannuale": (575, 18), "bilancio": (21, 16), "startup": (628, 24)}


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    if not _DB.is_file():
        pytest.skip(f"DB locale assente ({_DB})")
    copia = tmp_path_factory.mktemp("bp") / "db.sqlite"
    shutil.copyfile(_DB, copia)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{copia}")
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _data(db, caso) -> BusinessPlanData:
    from app.services.final_report_service import assemble_final_report
    company, scenario = CASI[caso]
    try:
        report = assemble_final_report(db, company, scenario, schema_version=2)
    except Exception as error:  # scenario assente in questa copia del DB
        pytest.skip(f"{caso}: {error}")
    return from_report(report, draft=True)


def test_from_report_infrannuale_ambienta(db):
    data = _data(db, "infrannuale")
    assert [c.label for c in data.columns] == ["2026 F", "2027 P", "2028 P", "2029 P"]
    assert data.columns[0].is_base and not any(c.is_base for c in data.columns[1:])
    assert data.v("ricavi")[0] == D("4109510")
    # costi operativi = costi della produzione − ammortamenti, ed EBITDA = VP − costi operativi
    for i in range(4):
        assert data.v("valore_produzione")[i] - data.v("costi_operativi")[i] == data.v("ebitda")[i]
    # debiti finanziari coerenti con la PFN per costruzione
    for i in range(4):
        assert data.v("debiti_finanziari")[i] - data.v("liquidita")[i] == data.v("pfn")[i]
    assert all(v >= 0 for v in data.v("cf_rimborsi"))
    assert data.partial_label == "6M 2026 R"
    assert data.starting_point.kind == "infrannuale"
    assert data.starting_point.tables[0].headers == ("Prima", "Rettifiche", "Dopo")
    assert data.residual_revenue == data.v("ricavi")[0] - D("2104755")
    assert data.base_description.startswith("Base: bilancio infrannuale al 30.06.2026 (6 mesi)")
    assert set(VALUE_KEYS) <= set(data.values)
    assert [r.label for r in data.assumptions][:1] == ["Crescita ricavi"]
    assert data.growth["revenue_growth_pct"] == (D("5.000000"), D("6.000000"), D("1.000000"))
    assert data.annex["income_statement"] and data.annex["balance_sheet"] and data.annex["cashflow"]
    assert len(data.indicators_practice) == 15
    assert data.indicators_practice_headers[0] == "6M 2026 R"
    assert not {r.label for r in data.indicators_analytical} & {"ROE", "ROI", "ROS", "EBITDA Margin"}


def test_from_report_bilancio(db):
    data = _data(db, "bilancio")
    assert data.workflow == "bilancio"
    assert data.columns[0].label.endswith(" C") and data.columns[0].is_base
    assert data.starting_point.kind == "bilancio"
    assert data.partial_label is None


def test_from_report_startup(db):
    data = _data(db, "startup")
    assert data.workflow == "startup"
    assert not any(c.is_base for c in data.columns)
    assert data.starting_point.kind == "startup"
    assert data.base_description.startswith("Startup")


def test_json_del_banco_andata_e_ritorno(tmp_path, db):
    data = _data(db, "infrannuale")
    path = tmp_path / "banco.json"
    import json
    path.write_text(json.dumps(dump_json(data)), encoding="utf-8")
    back = load_json(path)
    assert back.columns == data.columns
    assert back.v("ebitda") == data.v("ebitda")
    assert back.growth == data.growth
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && $PY -m pytest ../tests/test_bp_data.py -q`
Expected: FAIL, `ImportError: cannot import name 'VALUE_KEYS'`

- [ ] **Step 3: Scrivi `data.py`**

```python
"""Il modello del Business plan: numeri del motore allineati alle colonne del report.

Fonte unica: FinalReportModelV2. Qui si sommano e si sottraggono righe già presenti; nessun indicatore
viene ricalcolato (spec §4). Un valore assente resta None fino alla stampa, dove diventa «n.d.».
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal, Optional

from . import fmt

Num = Optional[Decimal]
Workflow = Literal["infrannuale", "bilancio", "startup"]

DIFF_ROW = ("balance_sheet:total_assets+sp11_capitale+sp12_riserve+sp13_utile_perdita+sp16_debiti_breve"
            "+sp17_debiti_lungo+sp14_fondi_rischi+sp15_tfr+sp18_ratei_risconti_passivi")


@dataclass(frozen=True)
class Column:
    period_id: str
    year: int
    label: str
    is_base: bool


@dataclass(frozen=True)
class AnnexRow:
    label: str
    level: int
    kind: str
    values: tuple


@dataclass(frozen=True)
class IndicatorRow:
    label: str
    unit: str
    values: tuple


@dataclass(frozen=True)
class AssumptionRow:
    label: str
    unit: str
    values: tuple  # uno per anno di piano


@dataclass(frozen=True)
class TableBlock:
    title: str
    headers: tuple
    rows: tuple  # (etichetta, valori, stile) con stile in "", "bold", "hl"
    note: str = ""


@dataclass(frozen=True)
class StartingPoint:
    kind: Workflow
    title: str
    intro: str
    tiles: tuple
    tables: tuple
    indicator_headers: tuple
    indicators: tuple
    checks: tuple
    note: str


@dataclass(frozen=True)
class BusinessPlanData:
    company_name: str
    workflow: Workflow
    columns: tuple
    base_description: str
    values: dict
    growth: dict = field(default_factory=dict)
    assumptions: tuple = ()
    partial_label: Optional[str] = None
    partial_dscr: Num = None
    residual_revenue: Num = None
    starting_point: Optional[StartingPoint] = None
    annex: dict = field(default_factory=dict)
    annex_zero_labels: dict = field(default_factory=dict)
    indicators_practice_headers: tuple = ()
    indicators_practice: tuple = ()
    indicators_analytical: tuple = ()
    draft: bool = False

    def v(self, key: str) -> tuple:
        return self.values.get(key) or (None,) * len(self.columns)

    @property
    def plan_idx(self) -> list:
        return [i for i, c in enumerate(self.columns) if not c.is_base]

    @property
    def plan_columns(self) -> list:
        return [self.columns[i] for i in self.plan_idx]

    @property
    def plan_years(self) -> list:
        return [c.year for c in self.plan_columns]

    @property
    def first(self) -> Column:
        return self.columns[0]

    @property
    def last(self) -> Column:
        return self.columns[-1]


def legend(data: BusinessPlanData) -> str:
    return {"infrannuale": "F = forecast · P = previsione di piano",
            "bilancio": "C = consuntivo · P = previsione di piano",
            "startup": "P = previsione di piano"}[data.workflow]


# ------------------------------------------------------------------ mappa chiave → righe del modello
_CE = {
    "ricavi": ("ce01_ricavi_vendite",),
    "var_produzione": ("ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce03a_incrementi_immobilizzazioni"),
    "altri_ricavi": ("ce04_altri_ricavi",),
    "valore_produzione": ("production_value",),
    "materie": ("ce05_materie_prime",),
    "servizi": ("ce06_servizi",),
    "godimento": ("ce07_godimento_beni",),
    "personale": ("ce08_costi_personale",),
    "var_rim_materie": ("ce10_var_rimanenze_mat_prime",),
    "accantonamenti": ("ce11_accantonamenti", "ce11b_altri_accantonamenti"),
    "oneri_diversi": ("ce12_oneri_diversi",),
    "costi_produzione": ("production_cost",),
    "ammortamenti": ("ce09_ammortamenti",),
    "ebitda": ("ebitda",),
    "ebit": ("ebit",),
    "proventi_fin": ("ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari"),
    "oneri_fin": ("ce15_oneri_finanziari",),
    "altre_componenti": ("ce16_utili_perdite_cambi", "ce17_rettifiche_attivita_fin", "extraordinary_result"),
    "ante_imposte": ("profit_before_tax",),
    "imposte": ("ce20_imposte",),
    "utile": ("net_profit",),
}
_SP = {
    "immobilizzazioni": ("fixed_assets",),
    "rimanenze": ("sp05_rimanenze",),
    "crediti_comm": ("sp06a_crediti_clienti_breve", "sp07a_crediti_clienti_lungo"),
    "liquidita": ("sp09_disponibilita_liquide",),
    "totale_attivo": ("total_assets",),
    "capitale": ("sp11_capitale",),
    "patrimonio_netto": ("sp11_capitale+sp12_riserve+sp13_utile_perdita",),
    "tfr": ("sp15_tfr",),
    "banche": ("sp16a_debiti_banche_breve+sp17a_debiti_banche_lungo",),
    "banche_breve": ("sp16a_debiti_banche_breve",),
    "banche_lungo": ("sp17a_debiti_banche_lungo",),
    "altri_finanziatori": ("sp16b_debiti_altri_finanz_breve+sp17b_debiti_altri_finanz_lungo",),
    "obbligazioni": ("sp16c_debiti_obbligazioni_breve+sp17c_debiti_obbligazioni_lungo",),
    "debiti_comm": ("sp16d_debiti_fornitori_breve+sp17d_debiti_fornitori_lungo",),
}
_CF = {
    "cf_ebit": ("operating.start.profit_before_adjustments",),
    "cf_non_monetarie": ("operating.non_cash_adjustments.total",),
    "cf_ante_ccn": ("operating.cashflow_before_wc",),
    "cf_var_ccn": ("operating.working_capital_changes.total",),
    "cf_altre": ("operating.cash_adjustments.total",),
    "cf_operativo": ("operating.total_operating_cashflow",),
    "cf_investimenti": ("investing.total_investing_cashflow",),
    "cf_finanziamento": ("financing.total_financing_cashflow",),
    "cf_nuovo_debito": ("financing.third_party_funds.increases",),
    "cf_rimborsi": ("financing.third_party_funds.decreases",),
    "cf_variazione": ("cash_reconciliation.total_cashflow",),
    "cassa_inizio": ("cash_reconciliation.cash_beginning",),
    "cassa_fine": ("cash_reconciliation.cash_ending",),
}
_IND = {
    "ebitda_margin": "practice.ebitda_margin", "dscr": "practice.dscr", "pfn": "practice.pfn",
    "pfn_ebitda": "practice.pfn_ebitda", "of_mol": "practice.of_mol", "of_ricavi": "practice.of_revenue",
    "ccn": "practice.ccn", "margine_tesoreria": "practice.mt", "margine_struttura": "practice.ms",
    "liquidita_corrente": "practice.current_ratio", "liquidita_immediata": "practice.quick_ratio",
    "indipendenza": "practice.indipendenza", "copertura_immob": "practice.copertura_immob",
    "roi": "practice.roi", "roe": "practice.roe", "ros": "practice.ros", "opex_ricavi": "practice.opex_revenue",
    "rod": "analytical.profitability.rod", "spread": "analytical.extended_profitability.spread",
    "dso": "analytical.activity.receivables_turnover_days", "dio": "analytical.activity.inventory_turnover_days",
    "dpo": "analytical.activity.payables_turnover_days", "ciclo": "analytical.activity.cash_conversion_cycle",
}
_BE = {"costi_fissi": "fixed_costs", "costi_variabili": "variable_costs",
       "margine_contribuzione": "contribution_margin", "bep": "break_even_revenue",
       "margine_sicurezza": "safety_margin_pct"}


def _add(*xs: Num) -> Num:
    return None if any(x is None for x in xs) else sum(xs, Decimal(0))


def _sub(a: Num, b: Num) -> Num:
    return None if a is None or b is None else a - b


def _share(a: Num, b: Num) -> Num:
    return None if a is None or b is None or b == 0 else a / b * 100


_DERIVED: dict = {
    "costi_operativi": lambda g: _sub(g("costi_produzione"), g("ammortamenti")),
    "debiti_finanziari": lambda g: _add(g("pfn"), g("liquidita")),
    "cc_comm": lambda g: _sub(_add(g("crediti_comm"), g("rimanenze")), g("debiti_comm")),
    "altre_attivita": lambda g: _sub(g("totale_attivo"),
                                     _add(g("immobilizzazioni"), g("rimanenze"), g("crediti_comm"), g("liquidita"))),
    "altre_passivita": lambda g: _sub(g("totale_attivo"), _add(g("patrimonio_netto"), g("debiti_finanziari"))),
    **{f"inc_{k}": (lambda k: lambda g: _share(g(k), g("ricavi")))(k)
       for k in ("materie", "servizi", "godimento", "personale", "oneri_diversi", "costi_operativi", "oneri_fin")},
}

VALUE_KEYS = tuple(_CE) + tuple(_SP) + tuple(_CF) + tuple(_IND) + tuple(_BE) + tuple(_DERIVED)

UNITS = {"ebitda_margin": "percent", "dscr": "ratio", "pfn": "eur", "pfn_ebitda": "ratio", "of_mol": "percent",
         "of_ricavi": "percent", "ccn": "eur", "margine_tesoreria": "eur", "margine_struttura": "eur",
         "liquidita_corrente": "ratio", "liquidita_immediata": "ratio", "indipendenza": "percent",
         "copertura_immob": "percent", "roi": "percent", "roe": "percent", "ros": "percent",
         "opex_ricavi": "percent", "rod": "percent", "spread": "percent", "dso": "days", "dio": "days",
         "dpo": "days", "ciclo": "days", "margine_sicurezza": "percent"}


class _Lookup:
    """Valori del modello v2 per (chiave, periodo)."""

    def __init__(self, report):
        self.rows: dict = {}
        for st in report.detailed_statements:
            pids = [p.id for p in st.periods]
            for r in st.rows:
                self.rows[r.id] = dict(zip(pids, r.values))
        self.ind = {i.id: dict(zip([p.id for p in i.periods], i.values)) for i in report.indicator_catalog}
        self.series: dict = {}
        for g in report.structure_series:
            pids = [p.id for p in g.periods]
            for s in g.series:
                self.series[(g.id, s.id)] = dict(zip(pids, s.values))

    def _rows(self, prefix: str, ids: tuple, pid: str) -> Num:
        vals = [self.rows.get(f"{prefix}:{i}", {}).get(pid) for i in ids]
        return _add(*vals)

    def get(self, key: str, pid: str) -> Num:
        if key in _CE:
            return self._rows("income_statement", _CE[key], pid)
        if key in _SP:
            return self._rows("balance_sheet", _SP[key], pid)
        if key in _CF:
            value = self._rows("cashflow", _CF[key], pid)
            return abs(value) if key == "cf_rimborsi" and value is not None else value
        if key in _IND:
            return self.ind.get(_IND[key], {}).get(pid)
        if key in _BE:
            return self.series.get(("break_even", _BE[key]), {}).get(pid)
        if key in _DERIVED:
            return _DERIVED[key](lambda k: self.get(k, pid))
        raise KeyError(key)


# ------------------------------------------------------------------ ipotesi
_ASSUMPTIONS = (
    ("revenue_growth_pct", "Crescita ricavi", "percent"),
    ("other_revenue_growth_pct", "Crescita altri ricavi", "percent"),
    ("variable_materials_growth_pct", "Crescita materie (variabile)", "percent"),
    ("variable_services_growth_pct", "Crescita servizi (variabile)", "percent"),
    ("personnel_growth_pct", "Crescita personale", "percent"),
    ("rent_growth_pct", "Crescita godimento beni di terzi", "percent"),
    ("other_costs_growth_pct", "Crescita oneri diversi", "percent"),
    ("dso_days", "DSO (giorni incasso)", "days"),
    ("dio_days", "DIO (giorni magazzino)", "days"),
    ("dpo_days", "DPO (giorni pagamento)", "days"),
    ("tangible_investments", "Investimenti materiali", "eur"),
    ("intangible_investments", "Investimenti immateriali", "eur"),
    ("depreciation_rate", "Aliquota ammortamenti materiali", "percent"),
    ("depreciation_rate_intangible", "Aliquota ammortamenti immateriali", "percent"),
    ("tax_rate", "Aliquota fiscale", "percent"),
    ("inflation_pct", "Inflazione", "percent"),
)


def _numeric(v) -> Num:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    return None


def _assumptions(report, plan_n: int) -> tuple:
    by_field = {a.field: a for s in report.assumption_sections for a in s.assumptions}
    growth, rows = {}, []
    for fld, label, unit in _ASSUMPTIONS:
        a = by_field.get(fld)
        if a is None or not a.active:
            continue
        vals = tuple(_numeric(x) for x in list(a.values)[:plan_n])
        vals = vals + (None,) * (plan_n - len(vals))
        if all(x is None for x in vals):
            continue
        growth[fld] = vals
        rows.append(AssumptionRow(label, unit, vals))
    return growth, rows


# ------------------------------------------------------------------ allegati e indicatori
_DUPLICATI_E = {"analytical.profitability.roe", "analytical.profitability.roi", "analytical.profitability.ros",
                "analytical.profitability.ebitda_margin"}


def _annex(statement, cols) -> tuple:
    pids = [p.id for p in statement.periods]
    rows, zero = [], []
    for r in statement.rows:
        vals = tuple(r.values[pids.index(c.period_id)] if c.period_id in pids else None for c in cols)
        if r.kind == "detail" and all(v is None or v == 0 for v in vals):
            zero.append(r.label.strip())
            continue
        rows.append(AnnexRow(r.label.strip(), r.level, r.kind, vals))
    return tuple(rows), tuple(zero)


# I 15 indicatori della pratica (contracts/final_report_dossier_catalog.json › practice_indicators), in quell'ordine.
# Il catalogo v2 aggiunge altri `practice.*` (incidenze, aliquota, margine EBIT, liquidità immediata) che l'Allegato D
# del riferimento non stampa.
_PRACTICE_D = tuple("practice." + k for k in ("dscr", "ebitda_margin", "mt", "ccn", "current_ratio", "ms",
                                              "copertura_immob", "indipendenza", "pfn", "pfn_ebitda", "roi", "roe",
                                              "ros", "of_mol", "of_revenue"))


def _indicators(report, ids, pids: list) -> tuple:
    by_id = {ind.id: ind for ind in report.indicator_catalog}
    out = []
    for identifier in ids:
        ind = by_id.get(identifier)
        if ind is None:
            continue
        by = dict(zip([p.id for p in ind.periods], ind.values))
        out.append(IndicatorRow(ind.label, ind.unit, tuple(by.get(pid) for pid in pids)))
    return tuple(out)


# ------------------------------------------------------------------ punto di partenza
_CE_LINES = (("Ricavi", "ricavi", ""), ("Costi operativi", "costi_operativi", ""), ("EBITDA", "ebitda", "bold"),
             ("Ammortamenti", "ammortamenti", ""), ("EBIT", "ebit", "bold"), ("Oneri finanziari", "oneri_fin", ""),
             ("Risultato ante imposte", "ante_imposte", ""), ("Imposte", "imposte", ""),
             ("Risultato netto", "utile", "hl"))
_START_IND = (("EBITDA margin", "ebitda_margin"), ("ROS", "ros"), ("ROI", "roi"), ("ROE", "roe"),
              ("Margine di tesoreria", "margine_tesoreria"), ("CCN", "ccn"),
              ("Liquidità corrente", "liquidita_corrente"), ("Margine di struttura", "margine_struttura"),
              ("Copertura immobilizzazioni", "copertura_immob"), ("Indipendenza finanziaria", "indipendenza"),
              ("PFN", "pfn"), ("PFN / EBITDA", "pfn_ebitda"))
_PIANO = {1: "annuale", 2: "biennale", 3: "triennale", 4: "quadriennale", 5: "quinquennale"}


def _checks(lk: _Lookup, cols, report) -> tuple:
    out = []
    diffs = [(c.label, lk.rows.get(DIFF_ROW, {}).get(c.period_id)) for c in cols]
    known = [(label, d) for label, d in diffs if d is not None]
    bad = [(label, d) for label, d in known if abs(d) > Decimal("0.01")]
    if not known:
        out.append(("Attivo = passivo e patrimonio netto", "Controllo non disponibile."))
    elif bad:
        worst = max(abs(d) for _, d in bad)
        out.append(("Attivo = passivo e patrimonio netto",
                    f"Non quadra in {', '.join(label for label, _ in bad)}: differenza massima € {fmt.eur(worst)}."))
    else:
        out.append(("Attivo = passivo e patrimonio netto", f"Quadra su {len(known)} periodi rappresentati."))
    cash, cash_bad = [], []
    for c in cols:
        b, t, e = (lk.get(k, c.period_id) for k in ("cassa_inizio", "cf_variazione", "cassa_fine"))
        if None in (b, t, e):
            continue
        cash.append(c.label)
        if abs(b + t - e) > Decimal("0.01"):
            cash_bad.append(c.label)
    if not cash:
        out.append(("Cassa iniziale + flussi = cassa finale", "Rendiconto non disponibile."))
    elif cash_bad:
        out.append(("Cassa iniziale + flussi = cassa finale", f"Non verificato in {', '.join(cash_bad)}."))
    else:
        out.append(("Cassa iniziale + flussi = cassa finale", f"Verificato su {len(cash)} periodi."))
    if report.practice.workflow_type == "infrannuale":
        n = len(report.adjustments.entries)
        out.append(("Rettifiche", f"{n} rettifiche confermate." if report.adjustments.confirmed
                    else f"{n} rettifiche, non confermate."))
    return tuple(out)


def _starting_infrannuale(report, lk, cols, periods) -> StartingPoint:
    obs = next(p for p in periods if p.basis == "observed")
    adj = next(p for p in periods if p.basis == "adjusted")
    clo = next(p for p in periods if p.basis == "closing")
    m, y = adj.period_months, adj.year
    g = lambda k, p: lk.get(k, p.id)  # noqa: E731
    prima_dopo = tuple((label, (g(k, obs), _sub(g(k, adj), g(k, obs)), g(k, adj)), style)
                       for label, k, style in _CE_LINES)
    ponte = tuple((label, (g(k, adj), _sub(g(k, clo), g(k, adj)), g(k, clo)), style)
                  for label, k, style in _CE_LINES)
    n_rett = len(report.adjustments.entries)
    e_eff = _sub(g("utile", adj), g("utile", obs))
    tiles = (
        (fmt.compact_eur(g("ricavi", adj)), f"Ricavi {m}M {y}", f"periodo osservato: {m} mesi"),
        (fmt.compact_eur(g("ebitda", adj)), f"EBITDA {m}M rettificato",
         f"{fmt.compact_eur(g('ebitda', obs))} prima delle rettifiche"),
        (fmt.compact_eur(g("utile", adj)), f"Utile {m}M rettificato", f"effetto rettifiche: {fmt.compact_eur(e_eff)}"),
        (fmt.compact_eur(g("ebitda", clo)), f"EBITDA forecast {y}",
         f"EBITDA margin {fmt.pct(g('ebitda_margin', clo))}"),
    )
    end = report.infrannual_closing.period_end if report.infrannual_closing else None
    end_txt = end.strftime("%d.%m.%Y") if end else f"{m} mesi"
    return StartingPoint(
        kind="infrannuale",
        title=f"Punto di partenza: infrannuale, rettifiche e forecast {y}",
        intro=(f"La base del piano è il forecast {y}, ottenuto dal bilancio infrannuale al {end_txt} "
               f"({m} mesi) rettificato più la stima del periodo residuo."),
        tiles=tiles,
        tables=(
            TableBlock("Bilancio infrannuale: prima e dopo le rettifiche", ("Prima", "Rettifiche", "Dopo"), prima_dopo,
                       f"{n_rett} rettifiche. Il progressivo di {m} mesi non è direttamente comparabile "
                       "con un esercizio completo."),
            TableBlock(f"Dal progressivo rettificato al forecast {y}",
                       (f"{m}M rettificato", "Stimato residuo", f"Forecast {y}"), ponte),
        ),
        indicator_headers=(f"{m}M {y} rettificato", f"Forecast {y}"),
        indicators=tuple(IndicatorRow(label, UNITS.get(k, "eur"), (g(k, adj), g(k, clo))) for label, k in _START_IND),
        checks=_checks(lk, cols, report),
        note=f"Periodi di durata diversa ({m} mesi e 12 mesi): gli indicatori reddituali vanno letti tenendo conto "
             "di questa differenza.",
    )


def _starting_bilancio(report, lk, cols, periods) -> StartingPoint:
    hist = [p for p in periods if p.basis == "historical"]
    base = hist[-1]
    prev = hist[-2] if len(hist) > 1 else None
    g = lambda k, p: lk.get(k, p.id)  # noqa: E731
    if prev:
        headers = (f"{prev.year} C", f"{base.year} C", "Variazione")
        rows = tuple((label, (g(k, prev), g(k, base), _sub(g(k, base), g(k, prev))), style)
                     for label, k, style in _CE_LINES)
        ind_headers, ind_pids = (f"{prev.year} C", f"{base.year} C"), (prev, base)
    else:
        headers = (f"{base.year} C",)
        rows = tuple((label, (g(k, base),), style) for label, k, style in _CE_LINES)
        ind_headers, ind_pids = (f"{base.year} C",), (base,)
    da = f"da {fmt.compact_eur(g('ricavi', prev))} nel {prev.year}" if prev else "ultimo esercizio depositato"
    tiles = (
        (fmt.compact_eur(g("ricavi", base)), f"Ricavi {base.year}", da),
        (fmt.compact_eur(g("ebitda", base)), f"EBITDA {base.year}", f"EBITDA margin {fmt.pct(g('ebitda_margin', base))}"),
        (fmt.compact_eur(g("utile", base)), f"Utile {base.year}", "risultato d'esercizio"),
        (fmt.compact_eur(g("pfn", base)), f"PFN {base.year}", "debiti finanziari − liquidità"),
    )
    return StartingPoint(
        kind="bilancio", title=f"Punto di partenza: bilancio {base.year}",
        intro=f"La base del piano è il bilancio d'esercizio {base.year}, confrontato con l'esercizio precedente.",
        tiles=tiles,
        tables=(TableBlock(f"Conto economico di partenza", headers, rows),),
        indicator_headers=ind_headers,
        indicators=tuple(IndicatorRow(label, UNITS.get(k, "eur"), tuple(g(k, p) for p in ind_pids))
                         for label, k in _START_IND),
        checks=_checks(lk, cols, report), note="",
    )


def _starting_startup(report, lk, cols, periods) -> StartingPoint:
    hist = [p for p in periods if p.basis == "historical"]
    first = next(p for p in periods if p.basis == "forecast")
    g = lambda k, p: lk.get(k, p.id)  # noqa: E731
    tables = ()
    if hist:
        o = hist[-1]
        tables = (TableBlock(f"Bilancio d'apertura {o.year}", (f"Apertura {o.year}",),
                             (("Capitale sociale", (g("capitale", o),), ""),
                              ("Disponibilità liquide", (g("liquidita", o),), ""),
                              ("Totale attivo", (g("totale_attivo", o),), "hl"))),)
    n = len([p for p in periods if p.basis == "forecast"])
    tiles = (
        (fmt.compact_eur(g("capitale", hist[-1]) if hist else None), "Capitale sociale", "all'apertura"),
        (fmt.compact_eur(g("liquidita", hist[-1]) if hist else None), "Liquidità iniziale", "all'apertura"),
        (fmt.compact_eur(g("ricavi", first)), f"Ricavi {first.year}", "primo anno di piano"),
        (str(n), "Anni di piano", f"dal {first.year}"),
    )
    return StartingPoint(kind="startup", title="Punto di partenza: apertura della startup",
                         intro="La startup parte dal bilancio d'apertura: non esiste un esercizio precedente.",
                         tiles=tiles, tables=tables, indicator_headers=(), indicators=(),
                         checks=_checks(lk, cols, report), note="")


# ------------------------------------------------------------------ ingresso
def from_report(report, *, draft: bool) -> BusinessPlanData:
    wf = report.practice.workflow_type
    periods = report.detailed_statements[0].periods
    plan = [p for p in periods if p.basis == "forecast"]
    if wf == "infrannuale":
        base = next((p for p in periods if p.basis == "closing"), None)
    elif wf == "bilancio":
        base = ([p for p in periods if p.basis == "historical"] or [None])[-1]
    else:
        base = None
    cols = ([Column(base.id, base.year, f"{base.year} {'F' if base.basis == 'closing' else 'C'}", True)]
            if base else []) + [Column(p.id, p.year, f"{p.year} P", False) for p in plan]
    cols = tuple(cols)
    lk = _Lookup(report)
    values = {k: tuple(lk.get(k, c.period_id) for c in cols) for k in VALUE_KEYS}
    growth, rows = _assumptions(report, len(plan))
    plan_pids = [p.id for p in plan]
    rows.append(AssumptionRow("Costi operativi / ricavi", "percent",
                              tuple(lk.get("opex_ricavi", pid) for pid in plan_pids)))
    rows.append(AssumptionRow("Ammortamenti", "eur", tuple(lk.get("ammortamenti", pid) for pid in plan_pids)))
    rows.append(AssumptionRow("Rimborso debito", "eur", tuple(lk.get("cf_rimborsi", pid) for pid in plan_pids)))

    n_word = _PIANO.get(len(plan), f"di {len(plan)} anni")
    partial_label = partial_dscr = residual = None
    adj = next((p for p in periods if p.basis == "adjusted"), None)
    if wf == "infrannuale" and adj is not None and base is not None:
        partial_label = f"{adj.period_months}M {adj.year} R"
        partial_dscr = lk.get("dscr", adj.id)
        residual = _sub(lk.get("ricavi", base.id), lk.get("ricavi", adj.id))
        end = report.infrannual_closing.period_end if report.infrannual_closing else None
        end_txt = f"al {end.strftime('%d.%m.%Y')} " if end else ""
        base_description = (f"Base: bilancio infrannuale {end_txt}({adj.period_months} mesi) · forecast {base.year} "
                            f"· piano {n_word}")
        starting = _starting_infrannuale(report, lk, cols, periods)
    elif wf == "bilancio" and base is not None:
        base_description = f"Base: bilancio d'esercizio {base.year} · piano {n_word}"
        starting = _starting_bilancio(report, lk, cols, periods)
    else:
        base_description = f"Startup · piano {n_word} dal {plan[0].year}"
        starting = _starting_startup(report, lk, cols, periods)

    ce, sp, cf = report.detailed_statements
    annex, zero = {}, {}
    for st in (ce, sp, cf):
        annex[st.id], zero[st.id] = _annex(st, cols)
    d_pids = [c.period_id for c in cols]
    d_headers = tuple(c.label for c in cols)
    if partial_label and len(cols) + 1 <= 6:
        d_pids, d_headers = [adj.id] + d_pids, (partial_label,) + d_headers
    return BusinessPlanData(
        company_name=report.company.name, workflow=wf, columns=cols, base_description=base_description,
        values=values, growth=growth, assumptions=tuple(rows), partial_label=partial_label,
        partial_dscr=partial_dscr, residual_revenue=residual, starting_point=starting,
        annex=annex, annex_zero_labels=zero,
        indicators_practice_headers=d_headers,
        indicators_practice=_indicators(report, _PRACTICE_D, d_pids),
        indicators_analytical=_indicators(
            report, [i.id for i in report.indicator_catalog
                     if i.id.startswith("analytical.") and i.id not in _DUPLICATI_E],
            [c.period_id for c in cols]),
        draft=draft,
    )


# ------------------------------------------------------------------ JSON del banco
def _enc(v):
    return None if v is None else str(v)


def _dec(v):
    return None if v is None else Decimal(v)


def dump_json(data: BusinessPlanData) -> dict:
    """Solo i campi che le sezioni economiche leggono: il banco non serializza allegati e punto di partenza."""
    return {
        "company_name": data.company_name, "workflow": data.workflow,
        "columns": [c.__dict__ for c in data.columns], "base_description": data.base_description,
        "values": {k: [_enc(x) for x in v] for k, v in data.values.items()},
        "growth": {k: [_enc(x) for x in v] for k, v in data.growth.items()},
        "partial_label": data.partial_label, "partial_dscr": _enc(data.partial_dscr),
        "residual_revenue": _enc(data.residual_revenue), "draft": data.draft,
    }


def load_json(path) -> BusinessPlanData:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return BusinessPlanData(
        company_name=raw["company_name"], workflow=raw["workflow"],
        columns=tuple(Column(**c) for c in raw["columns"]), base_description=raw["base_description"],
        values={k: tuple(_dec(x) for x in v) for k, v in raw["values"].items()},
        growth={k: tuple(_dec(x) for x in v) for k, v in raw.get("growth", {}).items()},
        partial_label=raw.get("partial_label"), partial_dscr=_dec(raw.get("partial_dscr")),
        residual_revenue=_dec(raw.get("residual_revenue")), draft=raw.get("draft", False),
    )
```

- [ ] **Step 4: Verifica che passi**

Run: `cd backend && $PY -m pytest ../tests/test_bp_data.py -q`
Expected: `4 passed`. Se `test_from_report_infrannuale_ambienta` fallisce su `residual_revenue` o `D("4109510")`, AMBIENTA nel DB locale è cambiata: rileggi i valori con `assemble_final_report(db, 575, 18, schema_version=2)`, aggiorna le due costanti e scrivi il valore nuovo nel messaggio di commit. Non allentare le uguaglianze strutturali (EBITDA, PFN).

- [ ] **Step 5: Commit**

```bash
git add backend/app/renderers/business_plan/data.py tests/test_bp_data.py
git diff --cached --stat
git commit -m "feat(report-bp): BusinessPlanData dal modello v2, tre workflow, JSON del banco

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: I grafici

**Files:**
- Create: `backend/app/renderers/business_plan/charts.py`
- Test: `tests/test_bp_charts.py`

**Interfaces:**
- Consumes: `theme` (colori, `FONT_DIR`), `fmt.chart_num`.
- Produces: `HEIGHTS: dict[str, float]` e funzioni che restituiscono `bytes` PNG:
  `ricavi_margine(labels, ricavi, margine)`, `risultati(labels, ebitda, ebit, utile)`,
  `pareggio(labels, ricavi, variabili, fissi, bep)`, `sicurezza(labels, margine)`,
  `flussi(labels, operativo, investimenti, finanziamento, cassa)`,
  `debito(labels, debiti_fin, liquidita, patrimonio, pfn)`, `dscr_pfn(labels, dscr, pfn_ebitda)`,
  `circolante(labels, dso, dio, dpo, cc_comm)`. Gli importi arrivano in euro (`Decimal | None`) e vengono divisi per 1000 qui dentro.

- [ ] **Step 1: Scrivi il test**

`tests/test_bp_charts.py`:
```python
"""Grafici: misure del riferimento (1584 px di larghezza, altezza = decimi di pollice × 220), assenze, thread."""
import io
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D

from PIL import Image

from app.renderers.business_plan import charts

L = ["2026 F", "2027 P", "2028 P", "2029 P"]
R = [D("4109510"), D("4314986"), D("4573885"), D("4673885")]


def _size(png):
    return Image.open(io.BytesIO(png)).size


def test_misure_come_il_riferimento():
    assert _size(charts.ricavi_margine(L, R, [D("4.04"), D("4.36"), D("8.64"), D("8.61")])) == (1584, 682)
    assert _size(charts.sicurezza(L, [D("-4.31"), D("5.02"), D("14.3"), D("14.39")])) == (1584, 528)
    assert charts.HEIGHTS == {"ricavi_margine": 3.1, "risultati": 2.8, "pareggio": 3.2, "sicurezza": 2.4,
                              "flussi": 3.1, "debito": 2.9, "dscr_pfn": 2.7, "circolante": 2.8}


def test_sfondo_trasparente_e_png_deterministico():
    a = charts.flussi(L, [D("-225519"), D("399355"), D("262189"), D("406154")],
                      [D("61790"), D("-150000"), D("0"), D("0")], [D("134517"), D("96591"), D("-105000"), D("-105000")],
                      [D("55"), D("346000"), D("503190"), D("804344")])
    b = charts.flussi(L, [D("-225519"), D("399355"), D("262189"), D("406154")],
                      [D("61790"), D("-150000"), D("0"), D("0")], [D("134517"), D("96591"), D("-105000"), D("-105000")],
                      [D("55"), D("346000"), D("503190"), D("804344")])
    assert a == b
    assert Image.open(io.BytesIO(a)).mode == "RGBA"


def test_grafici_con_valori_assenti():
    none4 = [None] * 4
    for png in (charts.ricavi_margine(L, none4, none4), charts.risultati(L, none4, none4, none4),
                charts.pareggio(L, none4, none4, none4, none4), charts.sicurezza(L, none4),
                charts.flussi(L, none4, none4, none4, none4), charts.debito(L, none4, none4, none4, none4),
                charts.dscr_pfn(L, none4, none4), charts.circolante(L, none4, none4, none4, none4)):
        assert png.startswith(b"\x89PNG")


def test_sei_categorie_e_valori_negativi():
    L6 = ["2025 C"] + [f"{y} P" for y in range(2026, 2031)]
    neg = [D("-50000"), D("-20000"), D("10000"), D("30000"), D("60000"), D("90000")]
    assert _size(charts.risultati(L6, neg, neg, neg))[0] == 1584


def test_render_concorrente():
    def job(_):
        return charts.ricavi_margine(L, R, [D("4"), D("5"), D("6"), D("7")])
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(job, range(12)))
    assert len(set(results)) == 1
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && $PY -m pytest ../tests/test_bp_charts.py -q`
Expected: FAIL, `ImportError: cannot import name 'charts'`

- [ ] **Step 3: Scrivi `charts.py`**

Lo stile viene dallo spike approvato (`spike_bp.py`, nella scratchpad della sessione): dimensioni del font del riferimento × 0,8064, linee da 2,2, marker 6. Qui però niente `pyplot` e niente `rcParams`: ogni grafico ha la sua `Figure`, e i font si passano esplicitamente.

```python
"""Grafici del Business plan. matplotlib con API Figure (thread-safe, mai pyplot), PNG 7,2″ × h a 220 dpi."""
from __future__ import annotations

import io
import math
from decimal import Decimal
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from . import theme  # noqa: E402
from .fmt import chart_num  # noqa: E402

DPI = 220
WIDTH_IN = 7.2
HEIGHTS = {"ricavi_margine": 3.1, "risultati": 2.8, "pareggio": 3.2, "sicurezza": 2.4,
           "flussi": 3.1, "debito": 2.9, "dscr_pfn": 2.7, "circolante": 2.8}
TICK, LEGEND, LABEL, SMALL = 9.3, 9.3, 8.9, 8.1
for _f in ("Lato-Regular.ttf", "Lato-Bold.ttf"):
    font_manager.fontManager.addfont(str(theme.FONT_DIR / _f))
FAMILY = "Lato"

Values = Sequence[Optional[Decimal]]


def _k(vals: Values) -> list:
    """Euro → migliaia di euro in float; None → nan (barra non disegnata)."""
    return [math.nan if v is None else float(v) / 1000 for v in vals]


def _f(vals: Values) -> list:
    return [math.nan if v is None else float(v) for v in vals]


def _finite(*series) -> list:
    return [x for s in series for x in s if not math.isnan(x)]


def _fig(key: str, ncols: int = 1):
    fig = Figure(figsize=(WIDTH_IN, HEIGHTS[key]), dpi=DPI)
    FigureCanvasAgg(fig)
    axes = fig.subplots(1, ncols)
    for ax in (axes if ncols > 1 else [axes]):
        _style(ax)
    return fig, axes


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme.GREY)
    ax.grid(True, color=theme.GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=theme.GREY, length=4)  # `colors` imposta anche le etichette: si sovrascrivono dopo
    ax.tick_params(labelcolor=theme.AXIS, labelsize=TICK, labelfontfamily=FAMILY)


def _legend(ax, handles, labels, **kw) -> None:
    ax.legend(handles, labels, frameon=False, prop=FontProperties(family=FAMILY, size=LEGEND), **kw)


def _text(ax, x, y, s, **kw) -> None:
    ax.text(x, y, s, fontfamily=FAMILY, **kw)


def _thousands(ax) -> None:
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: chart_num(v)))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))


def _ylabel(ax, text: str) -> None:
    ax.set_ylabel(text, fontfamily=FAMILY, fontsize=TICK, color=theme.AXIS)


def _limits(ax, values: list, top_room: float = 1.2, bottom_room: float = 1.25) -> None:
    lo = min([0.0] + values)
    hi = max([0.0] + values)
    span = (hi - lo) or 1.0
    ax.set_ylim(lo * bottom_room - (0.04 * span if lo < 0 else 0), hi * top_room + 0.02 * span)


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, transparent=True, metadata={"Software": None})
    return buf.getvalue()


def _xticks(ax, labels) -> None:
    ax.set_xticks(list(range(len(labels))), labels)


def ricavi_margine(labels, ricavi: Values, margine: Values) -> bytes:
    fig, ax = _fig("ricavi_margine")
    fig.subplots_adjust(left=0.075, right=0.93, top=0.96, bottom=0.12)
    x = list(range(len(labels)))
    k = _k(ricavi)
    bars = ax.bar(x, k, width=0.55, color=theme.NAVY, label="Ricavi delle vendite (€ migliaia)", zorder=2)
    _limits(ax, _finite(k), top_room=1.2)
    _thousands(ax)
    _xticks(ax, labels)
    top = ax.get_ylim()[1]
    for b, v in zip(bars, k):
        if math.isnan(v):
            continue
        inside = v > 0.12 * top
        _text(ax, b.get_x() + b.get_width() / 2, v - 0.02 * top if inside else v + 0.01 * top, chart_num(v),
              ha="center", va="top" if inside else "bottom", color="white" if inside else theme.NAVY,
              fontweight="bold", fontsize=LABEL)
    ax2 = ax.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color(theme.GREY)
    ax2.tick_params(colors=theme.GREY, length=4)
    ax2.tick_params(labelcolor=theme.AXIS, labelsize=TICK, labelfontfamily=FAMILY)
    m = _f(margine)
    line, = ax2.plot(x, m, color=theme.ORANGE, linewidth=2.2, marker="o", markersize=6, zorder=3)
    fm = _finite(m)
    ax2.set_ylim(min([0.0] + fm) * 1.5, max([1.0] + fm) * 1.5)
    ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{chart_num(v)}%"))
    span2 = ax2.get_ylim()[1] - ax2.get_ylim()[0]
    for xi, v in zip(x, m):
        if not math.isnan(v):
            _text(ax2, xi, v + 0.045 * span2, f"{chart_num(v, 2)}%", ha="center", va="bottom",
                  color=theme.ORANGE_DARK, fontweight="bold", fontsize=LABEL)
    _legend(ax, [bars, line], ["Ricavi delle vendite (€ migliaia)", "EBITDA margin %"], loc="upper left",
            ncol=2, handlelength=2.2, columnspacing=2.2, bbox_to_anchor=(0.0, 1.0))
    return _png(fig)


def _grouped(ax, labels, series, width) -> list:
    """series: [(valori_k, colore, etichetta)] → barre raggruppate con etichetta sopra/sotto."""
    x = list(range(len(labels)))
    n = len(series)
    handles = []
    allv = _finite(*[s[0] for s in series])
    span = (max([0.0] + allv) - min([0.0] + allv)) or 1.0
    for j, (vals, color, label) in enumerate(series):
        off = (j - (n - 1) / 2) * width
        h = ax.bar([i + off for i in x], vals, width, color=color, label=label, zorder=2)
        handles.append(h)
        for i, v in enumerate(vals):
            if math.isnan(v) or round(v) == 0:
                continue
            _text(ax, i + off, v + (0.01 * span if v > 0 else -0.01 * span), chart_num(v), ha="center",
                  va="bottom" if v > 0 else "top", color="black", fontsize=SMALL)
    return handles


def risultati(labels, ebitda: Values, ebit: Values, utile: Values) -> bytes:
    fig, ax = _fig("risultati")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.96, bottom=0.12)
    series = [(_k(ebitda), theme.NAVY, "EBITDA"), (_k(ebit), theme.TEAL, "EBIT"), (_k(utile), theme.ORANGE, "Utile netto")]
    handles = _grouped(ax, labels, series, 0.26)
    _limits(ax, _finite(*[s[0] for s in series]), top_room=1.25)
    ax.axhline(0, color=theme.AXIS, linewidth=1.2, zorder=3)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    _legend(ax, handles, [s[2] for s in series], loc="upper left", ncol=3, columnspacing=2.2)
    return _png(fig)


def pareggio(labels, ricavi: Values, variabili: Values, fissi: Values, bep: Values) -> bytes:
    fig, ax = _fig("pareggio")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.96, bottom=0.11)
    x = list(range(len(labels)))
    w = 0.32
    fk, vk, rk, bk = _k(fissi), _k(variabili), _k(ricavi), _k(bep)
    xl = [i - w / 2 - 0.01 for i in x]
    xr = [i + w / 2 + 0.01 for i in x]
    h_f = ax.bar(xl, fk, w, color=theme.NAVY, zorder=2)
    h_v = ax.bar(xl, vk, w, bottom=[0 if math.isnan(a) else a for a in fk], color=theme.LIGHTBLUE, zorder=2)
    h_r = ax.bar(xr, rk, w, color=theme.TEAL, zorder=2)
    h_b = ax.scatter(xr, bk, marker="D", s=60, color=theme.RED, zorder=4)
    for i in x:
        if not math.isnan(fk[i]):
            _text(ax, xl[i], fk[i] / 2, chart_num(fk[i]), ha="center", va="center", color="white", fontsize=8.5)
        if not (math.isnan(fk[i]) or math.isnan(vk[i])):
            _text(ax, xl[i], fk[i] + vk[i] / 2, chart_num(vk[i]), ha="center", va="center", color=theme.NAVY,
                  fontsize=8.5)
        if not math.isnan(rk[i]):
            _text(ax, xr[i], rk[i] / 2, chart_num(rk[i]), ha="center", va="center", color="white",
                  fontweight="bold", fontsize=8.5)
        if not math.isnan(bk[i]):
            _text(ax, xr[i] + 0.25, bk[i], chart_num(bk[i]), ha="left", va="center", color=theme.RED, fontsize=8.5)
    stacks = [a + b for a, b in zip(fk, vk)]
    _limits(ax, _finite(stacks, rk, bk), top_room=1.3)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    ax.set_xlim(-0.55, len(labels) - 0.25)
    _legend(ax, [h_b, h_f, h_v, h_r], ["Break even point", "Costi fissi", "Costi variabili", "Ricavi"],
            loc="upper left", ncol=4, columnspacing=2.2, bbox_to_anchor=(0.01, 1.0))
    return _png(fig)


def sicurezza(labels, margine: Values) -> bytes:
    fig, ax = _fig("sicurezza")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.96, bottom=0.15)
    x = list(range(len(labels)))
    m = _f(margine)
    colors = [theme.RED if (not math.isnan(v) and v < 0) else theme.TEAL for v in m]
    ax.bar(x, m, width=0.5, color=colors, zorder=2)
    fm = _finite(m)
    lo, hi = min([0.0] + fm), max([0.0] + fm)
    span = (hi - lo) or 1.0
    ax.set_ylim(lo - 0.25 * span if lo < 0 else -0.08 * span, hi + 0.25 * span)
    for i, v in enumerate(m):
        if not math.isnan(v):
            _text(ax, i, v + (0.04 * span if v >= 0 else -0.04 * span), f"{chart_num(v, 2)}%", ha="center",
                  va="bottom" if v >= 0 else "top", color=colors[i], fontweight="bold", fontsize=LABEL)
    ax.axhline(0, color=theme.AXIS, linewidth=1.2, zorder=3)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{chart_num(v)}%"))
    _ylabel(ax, "Margine di sicurezza")
    _xticks(ax, labels)
    return _png(fig)


def flussi(labels, operativo: Values, investimenti: Values, finanziamento: Values, cassa: Values) -> bytes:
    fig, ax = _fig("flussi")
    fig.subplots_adjust(left=0.095, right=0.985, top=0.96, bottom=0.12)
    series = [(_k(operativo), theme.NAVY, "Flusso operativo"), (_k(investimenti), theme.ORANGE, "Flusso di investimento"),
              (_k(finanziamento), theme.GREY, "Flusso finanziario")]
    handles = _grouped(ax, labels, series, 0.26)
    ck = _k(cassa)
    line, = ax.plot(list(range(len(labels))), ck, color=theme.TEAL, linewidth=2.2, marker="o", markersize=6, zorder=4)
    allv = _finite(*[s[0] for s in series], ck)
    _limits(ax, allv, top_room=1.3)
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    for i, v in enumerate(ck):
        if i > 0 and not math.isnan(v):
            _text(ax, i + 0.05, v + 0.012 * span, chart_num(v), ha="left", va="bottom", color=theme.TEAL,
                  fontweight="bold", fontsize=LABEL)
    ax.axhline(0, color=theme.AXIS, linewidth=1.2, zorder=3)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    _legend(ax, [line] + handles, ["Cassa finale"] + [s[2] for s in series], loc="upper left", ncol=4,
            columnspacing=2.2, handlelength=2.2, bbox_to_anchor=(0.0, 1.0))
    return _png(fig)


def debito(labels, debiti_fin: Values, liquidita: Values, patrimonio: Values, pfn: Values) -> bytes:
    fig, ax = _fig("debito")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.96, bottom=0.12)
    series = [(_k(debiti_fin), theme.GREY, "Debiti finanziari"), (_k(liquidita), theme.TEAL, "Disponibilità liquide"),
              (_k(patrimonio), theme.ORANGE, "Patrimonio netto")]
    x = list(range(len(labels)))
    handles = []
    for j, (vals, color, label) in enumerate(series):
        handles.append(ax.bar([i + (j - 1) * 0.26 for i in x], vals, 0.26, color=color, zorder=2))
    pk = _k(pfn)
    line, = ax.plot(x, pk, color=theme.NAVY, linewidth=2.2, marker="o", markersize=6, zorder=4)
    _limits(ax, _finite(*[s[0] for s in series], pk), top_room=1.3)
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    for i, v in enumerate(pk):
        if not math.isnan(v):
            _text(ax, i + 0.12, v + 0.015 * span, chart_num(v), ha="left", va="bottom", color=theme.NAVY,
                  fontweight="bold", fontsize=LABEL)
    ax.axhline(0, color=theme.AXIS, linewidth=1.0, zorder=3)
    _thousands(ax)
    _ylabel(ax, "€ migliaia")
    _xticks(ax, labels)
    _legend(ax, [line, handles[0], handles[1], handles[2]],
            ["PFN", "Debiti finanziari", "Disponibilità liquide", "Patrimonio netto"], loc="upper right", ncol=2)
    return _png(fig)


def _panel_title(ax, text: str) -> None:
    ax.set_title(text, loc="left", fontfamily=FAMILY, fontsize=10.5, color=theme.NAVY)


def dscr_pfn(labels, dscr: Values, pfn_ebitda: Values) -> bytes:
    fig, (a1, a2) = _fig("dscr_pfn", ncols=2)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.88, bottom=0.12, wspace=0.12)
    for ax, vals, color, title in ((a1, _f(dscr), theme.NAVY, "DSCR (proxy)"),
                                   (a2, _f(pfn_ebitda), theme.TEAL, "PFN / EBITDA")):
        x = list(range(len(labels)))
        ax.bar(x, vals, 0.55, color=color, zorder=2)
        fv = _finite(vals)
        _limits(ax, fv, top_room=1.18)
        span = ax.get_ylim()[1] - ax.get_ylim()[0]
        for i, v in enumerate(vals):
            if not math.isnan(v):
                _text(ax, i, v + (0.01 * span if v >= 0 else -0.01 * span), f"{chart_num(v, 2)}×",
                      ha="center", va="bottom" if v >= 0 else "top", color="black", fontweight="bold", fontsize=LABEL)
        _xticks(ax, labels)
        ax.tick_params(labelsize=SMALL)
        _panel_title(ax, title)
    a1.axhline(1.0, color=theme.RED, linestyle="--", linewidth=1.2, zorder=3)
    _text(a1, -0.45, 1.05, "soglia 1,0×", color=theme.RED, fontsize=7, va="bottom")
    return _png(fig)


def circolante(labels, dso: Values, dio: Values, dpo: Values, cc_comm: Values) -> bytes:
    fig, (a1, a2) = _fig("circolante", ncols=2)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.88, bottom=0.10, wspace=0.14)
    x = list(range(len(labels)))
    lines = []
    for vals, color, label, below in ((_f(dso), theme.NAVY, "DSO – giorni credito", True),
                                      (_f(dio), theme.ORANGE, "DIO – giorni magazzino", False),
                                      (_f(dpo), theme.TEAL, "DPO – giorni debito", False)):
        ln, = a1.plot(x, vals, color=color, linewidth=2.2, marker="o", markersize=6, zorder=3)
        lines.append((ln, label))
        for i, v in enumerate(vals):
            if not math.isnan(v):
                _text(a1, i, v + (-4 if below else 3), chart_num(v), ha="center", va="top" if below else "bottom",
                      color=color, fontsize=SMALL)
    alld = _finite(_f(dso), _f(dio), _f(dpo))
    a1.set_ylim(min([0.0] + alld), max([10.0] + alld) * 1.15)
    _xticks(a1, labels)
    a1.tick_params(labelsize=SMALL)
    _panel_title(a1, "Giorni del circolante")
    a1.legend([h for h, _ in lines], [lab for _, lab in lines], loc="center right", frameon=False,
              prop=FontProperties(family=FAMILY, size=SMALL))
    ck = _k(cc_comm)
    a2.bar(x, ck, 0.55, color=theme.NAVY, zorder=2)
    _limits(a2, _finite(ck), top_room=1.15)
    span = a2.get_ylim()[1] - a2.get_ylim()[0]
    for i, v in enumerate(ck):
        if not math.isnan(v):
            _text(a2, i, v + (0.01 * span if v >= 0 else -0.01 * span), chart_num(v), ha="center",
                  va="bottom" if v >= 0 else "top", color="black", fontweight="bold", fontsize=LABEL)
    _thousands(a2)
    _xticks(a2, labels)
    a2.tick_params(labelsize=SMALL)
    _panel_title(a2, "Capitale circolante commerciale (€ k)")
    return _png(fig)
```

- [ ] **Step 4: Verifica che passi**

Run: `cd backend && $PY -m pytest ../tests/test_bp_charts.py -q`
Expected: `5 passed`. Se `test_misure_come_il_riferimento` dà 1584×681 o simili, il problema è l'arrotondamento dei pixel di `savefig`: non usare `bbox_inches` (cambierebbe la misura) e verifica che `figsize × DPI` sia intero (7,2 × 220 = 1584; 3,1 × 220 = 682).

- [ ] **Step 5: Commit**

```bash
git add backend/app/renderers/business_plan/charts.py tests/test_bp_charts.py
git diff --cached --stat
git commit -m "feat(report-bp): otto grafici matplotlib thread-safe, misure del riferimento

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Primitivi di impaginazione e documento

**Files:**
- Create: `backend/app/renderers/business_plan/layout.py`, `backend/app/renderers/business_plan/document.py`
- Test: `tests/test_bp_layout.py`

**Interfaces:**
- Consumes: `theme`, `fmt`, `data.BusinessPlanData`, `data.legend`.
- Produces (`layout.py`):
  - `ST: dict[str, ParagraphStyle]`, con chiavi `eyebrow, title, sub, h2, note, kv, kl, ks, cell, cellb, body, bullet, cardtitle, cardhead`
  - `section_head(eyebrow: str, title: str, sub: str) -> list`
  - `tiles(items: list[tuple[str,str,str]]) -> Table`
  - `fin_table(headers: list[str], rows: list[tuple[str, list[str], str]], first: str = "Voce (euro)", label_width: float | None = None, value_size: float | None = None) -> Table`, con stile di riga in `"" | "bold" | "hl" | "group"`
  - `note(text) -> Paragraph`, `h2(text) -> list`
  - `panel(title, bullets: list[tuple[str, str]]) -> Table`
  - `chart(png: bytes, height_in: float, width_pt: float = CW) -> Image`
  - `SectionStart(key: str, registry: dict)` (Flowable che registra la pagina)
- Produces (`document.py`):
  - `SectionSpec(key: str, index_title: str | None, build: Callable[[BusinessPlanData, dict], list])`
  - `SECTIONS: list[SectionSpec]` (li riempiono i Task 5, 7, 8, 9)
  - `render_business_plan(data, *, only: tuple[str, ...] | None = None) -> bytes`

- [ ] **Step 1: Scrivi il test**

`tests/test_bp_layout.py`:
```python
"""Impaginazione: intestazione, piè di pagina, tabella a sei colonne e indice calcolato su due passate."""
from decimal import Decimal as D

import fitz

from app.renderers.business_plan import document, layout, theme
from app.renderers.business_plan.data import BusinessPlanData, Column


def _data(n_plan=3, draft=False):
    cols = (Column("closing:2026", 2026, "2026 F", True),) + tuple(
        Column(f"forecast:{y}", y, f"{y} P", False) for y in range(2027, 2027 + n_plan))
    return BusinessPlanData(company_name="AZIENDA PROVA", workflow="infrannuale", columns=cols,
                            base_description="Base: prova", values={}, draft=draft)


def _two_sections(monkeypatch):
    def a(data, pages):
        return layout.section_head("SEZIONE 1", "Prima", "sotto") + [layout.note("x")]

    def b(data, pages):
        return layout.section_head("SEZIONE 2", "Seconda", "sotto") + [layout.note(f"pagina prima: {pages.get('a')}")]
    monkeypatch.setattr(document, "SECTIONS", [document.SectionSpec("a", "Prima", a),
                                               document.SectionSpec("b", "Seconda", b)])


def test_intestazione_e_piede(monkeypatch):
    _two_sections(monkeypatch)
    pdf = fitz.open(stream=document.render_business_plan(_data()), filetype="pdf")
    assert pdf.page_count == 2
    p = pdf[0]
    band = [d for d in p.get_drawings() if d.get("fill") and abs(d["rect"].height - theme.HEADER_H) < 0.5]
    assert band and band[0]["rect"].y0 < 0.5
    text = p.get_text()
    assert "AZIENDA PROVA" in text and "Piano economico-finanziario 2027 – 2029" in text
    assert "F = forecast · P = previsione di piano" in text
    assert "pagina prima: 1" in pdf[1].get_text()  # seconda passata: la pagina è nota


def test_bozza_nell_intestazione(monkeypatch):
    _two_sections(monkeypatch)
    pdf = fitz.open(stream=document.render_business_plan(_data(draft=True)), filetype="pdf")
    assert "BOZZA" in pdf[0].get_text()


def test_tabella_sei_colonne_sta_in_pagina():
    headers = ["2025 C"] + [f"{y} P" for y in range(2026, 2031)]
    table = layout.fin_table(headers, [("Ricavi delle vendite e delle prestazioni", ["4.109.510"] * 6, "")])
    w, _ = table.wrap(theme.CW, 800)
    assert w <= theme.CW + 0.5
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && $PY -m pytest ../tests/test_bp_layout.py -q`
Expected: FAIL, `ImportError: cannot import name 'document'`

- [ ] **Step 3: Scrivi `layout.py`**

```python
"""Primitivi ReportLab del Business plan: misure prese dal PDF del committente (spike approvato)."""
from __future__ import annotations

import io

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Image, Paragraph, Spacer, Table, TableStyle

from . import theme
from .theme import BOLD, CW, REGULAR

C = HexColor


def _ps(name, font=REGULAR, size=8.6, leading=None, color=theme.INK, **kw):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading or size * 1.2,
                          textColor=C(color), **kw)


ST = {
    "eyebrow": _ps("eyebrow", BOLD, 8.5, 11, theme.TEAL),
    "title": _ps("title", BOLD, 19, 23, theme.NAVY),
    "sub": _ps("sub", REGULAR, 10, 13, theme.MUTED),
    "h2": _ps("h2", BOLD, 12.2, 15, theme.NAVY),
    "note": _ps("note", REGULAR, 8.3, 10.4, theme.MUTED),
    "kv": _ps("kv", BOLD, 14.5, 17, theme.NAVY),
    "kl": _ps("kl", BOLD, 8.4, 10, theme.INK),
    "ks": _ps("ks", REGULAR, 7.8, 9.4, theme.MUTED),
    "cell": _ps("cell", REGULAR, 8.6, 10),
    "cellb": _ps("cellb", BOLD, 8.6, 10),
    "body": _ps("body", REGULAR, 9.3, 12.2),
    "bullet": _ps("bullet", REGULAR, 9.3, 12.2, leftIndent=10, bulletIndent=0),
    "cardtitle": _ps("cardtitle", BOLD, 11, 14, theme.TEAL),
    "cardhead": _ps("cardhead", BOLD, 9.3, 11.5),
    "paneltitle": _ps("paneltitle", BOLD, 10, 13, theme.NAVY),
}
ST["value"] = _ps("value", REGULAR, 9.2, 10.5, alignment=TA_RIGHT)
ST["valueh"] = _ps("valueh", BOLD, 9.2, 10.5, "#ffffff", alignment=TA_RIGHT)
ST["cellh"] = _ps("cellh", BOLD, 8.6, 10, "#ffffff")


def section_head(eyebrow: str, title: str, sub: str) -> list:
    out = [Paragraph(eyebrow, ST["eyebrow"]), Spacer(0, 3), Paragraph(title, ST["title"])]
    if sub:
        out += [Spacer(0, 1), Paragraph(sub, ST["sub"])]
    return out + [Spacer(0, 9)]


def h2(text: str, after: float = 2) -> list:
    return [Paragraph(text, ST["h2"]), Spacer(0, after)]


def note(text: str) -> Paragraph:
    return Paragraph(text, ST["note"])


def tiles(items: list) -> Table:
    """Quattro riquadri KPI: valore, etichetta, riga di confronto; filetto navy in alto."""
    gap = 8.5
    w = (CW - 3 * gap) / 4
    cells = [[Paragraph(v, ST["kv"]), Spacer(0, 2), Paragraph(lab, ST["kl"]), Spacer(0, 1.5), Paragraph(s, ST["ks"])]
             for v, lab, s in items]
    while len(cells) < 4:
        cells.append("")
    data = [[cells[0], "", cells[1], "", cells[2], "", cells[3]]]
    t = Table(data, colWidths=[w, gap, w, gap, w, gap, w])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 8.8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
    for c in range(0, 2 * len(items), 2):
        style += [("BACKGROUND", (c, 0), (c, 0), C(theme.TILE)), ("LINEABOVE", (c, 0), (c, 0), 2.2, C(theme.NAVY))]
    t.setStyle(TableStyle(style))
    return t


def _value_width(n: int) -> float:
    return {1: 90, 2: 90, 3: 80, 4: 72, 5: 64, 6: 58}.get(n, 52)


def fin_table(headers: list, rows: list, first: str = "Voce (euro)", label_width: float | None = None,
              value_size: float | None = None, pad: float = 4.6, label_size: float | None = None) -> Table:
    """Tabella finanziaria del riferimento: intestazione navy, filetti sottili, subtotali e righe evidenziate.

    `pad` è la spaziatura verticale di cella: 4,6 pt dà le righe da 19,6 pt delle pagine di lettura, 3,8 quelle da
    18,4 della sezione 8, 2,2 quelle degli allegati (tutte misurate sul riferimento).
    """
    n = len(headers)
    vw = _value_width(n)
    lw = label_width if label_width is not None else CW - n * vw
    vs = ST["value"] if value_size is None else _ps("v2", REGULAR, value_size, value_size * 1.15, alignment=TA_RIGHT)
    cell, cellb = ST["cell"], ST["cellb"]
    if label_size is not None:
        cell = _ps("cs", REGULAR, label_size, label_size * 1.15)
        cellb = _ps("csb", BOLD, label_size, label_size * 1.15)
    data = [[Paragraph(first, ST["cellh"])] + [Paragraph(h, ST["valueh"]) for h in headers]]
    style = [("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
             ("TOPPADDING", (0, 0), (-1, 0), 4.6), ("BOTTOMPADDING", (0, 0), (-1, 0), 4.6),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, C(theme.RULE))]
    for r, (label, cells, kind) in enumerate(rows, start=1):
        bold = kind in ("bold", "hl", "group")
        data.append([Paragraph(label, cellb if bold else cell)] +
                    [Paragraph(x, vs) for x in (cells if kind != "group" else [""] * n)])
        if kind == "bold":
            style.append(("LINEABOVE", (0, r), (-1, r), 0.8, C(theme.MUTED)))
        elif kind == "hl":
            style += [("BACKGROUND", (0, r), (-1, r), C(theme.HL)), ("LINEABOVE", (0, r), (-1, r), 0.8, C(theme.TEAL))]
        elif kind == "group":
            style += [("BACKGROUND", (0, r), (-1, r), C(theme.PANEL)),
                      ("TOPPADDING", (0, r), (-1, r), min(pad, 3.4)), ("BOTTOMPADDING", (0, r), (-1, r), min(pad, 3.4))]
    t = Table(data, colWidths=[lw] + [vw] * n, repeatRows=1)
    t.setStyle(TableStyle(style))
    return t


def panel(title: str, bullets: list) -> Table:
    """Pannello grigio con filetto teal a sinistra: «Punti chiave», «Lettura». bullets = [(attacco, testo)]."""
    content = [Paragraph(title, ST["paneltitle"]), Spacer(0, 3)]
    for lead, text in bullets:
        lead_html = f"<b>{lead}</b> " if lead else ""
        content.append(Paragraph(f"<font color='{theme.TEAL}'>•</font>&nbsp;&nbsp;{lead_html}{text}", ST["body"]))
        content.append(Spacer(0, 3))
    t = Table([[content]], colWidths=[CW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(theme.PANEL)),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, C(theme.TEAL)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def chart(png: bytes, height_in: float, width_pt: float = CW) -> Image:
    img = Image(io.BytesIO(png), width=width_pt, height=width_pt * height_in / 7.2)
    img.hAlign = "CENTER"
    return img


class SectionStart(Flowable):
    """Segnaposto a dimensione zero: registra la pagina in cui comincia una sezione (per l'indice)."""

    def __init__(self, key: str, registry: dict):
        super().__init__()
        self.key, self.registry = key, registry

    def wrap(self, *args):
        return 0, 0

    def draw(self):
        self.registry.setdefault(self.key, self.canv.getPageNumber())
```

- [ ] **Step 4: Scrivi `document.py`**

```python
"""Assemblaggio del Business plan: catalogo fisso delle sezioni e due passate per l'indice."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Callable, Optional

from reportlab.lib.colors import HexColor, white
from reportlab.platypus import BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate

from . import theme
from .data import BusinessPlanData, legend
from .layout import SectionStart
from .theme import BOLD, LM, PAGE_H, PAGE_W, REGULAR

C = HexColor


@dataclass(frozen=True)
class SectionSpec:
    key: str
    index_title: Optional[str]
    build: Callable[[BusinessPlanData, dict], list]
    cover: bool = False


SECTIONS: list = []  # riempito da _register() in fondo al modulo


def header_title(data: BusinessPlanData) -> str:
    years = data.plan_years
    span = f"{years[0]} – {years[-1]}" if len(years) > 1 else f"{years[0]}"
    return f"Piano economico-finanziario {span}"


def _body_page(data: BusinessPlanData):
    right = header_title(data) + (" · BOZZA" if data.draft else "")
    foot = f"Riservato e confidenziale · {legend(data)}"

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C(theme.NAVY))
        canvas.rect(0, PAGE_H - theme.HEADER_H, PAGE_W, theme.HEADER_H, stroke=0, fill=1)
        canvas.setFillColor(white)
        canvas.setFont(BOLD, 9)
        canvas.drawString(LM, PAGE_H - 20.5, data.company_name)
        canvas.setFont(REGULAR, 9)
        canvas.drawRightString(PAGE_W - LM, PAGE_H - 20.5, right)
        canvas.setStrokeColor(C(theme.RULE))
        canvas.setLineWidth(0.5)
        canvas.line(LM, PAGE_H - theme.FOOTER_RULE_Y, PAGE_W - LM, PAGE_H - theme.FOOTER_RULE_Y)
        canvas.setFillColor(C(theme.MUTED))
        canvas.setFont(REGULAR, 7.8)
        canvas.drawString(LM, PAGE_H - 820, foot)
        canvas.drawRightString(PAGE_W - LM, PAGE_H - 820, str(canvas.getPageNumber()))
        canvas.restoreState()
    return on_page


def _cover_page(data: BusinessPlanData):
    from .sections_sintesi import draw_cover_band  # import locale: esiste solo dal Task 7
    return lambda canvas, doc: draw_cover_band(canvas, data)


def _build(data: BusinessPlanData, specs: list, pages: dict) -> tuple:
    theme.register_fonts()
    buf = io.BytesIO()
    registry: dict = {}
    doc = BaseDocTemplate(buf, pagesize=(PAGE_W, PAGE_H), leftMargin=LM, rightMargin=LM, topMargin=55,
                          bottomMargin=40, title=f"{data.company_name} – {header_title(data)}",
                          author="", subject="Business plan", creator="XBRL Budget")
    body = PageTemplate(id="body", frames=[Frame(LM, 40, theme.CW, PAGE_H - 95, id="b", leftPadding=0,
                                                 rightPadding=0, topPadding=0, bottomPadding=0)],
                        onPage=_body_page(data))
    cover = PageTemplate(id="cover", frames=[Frame(LM, 40, theme.CW, PAGE_H - 300 - 40, id="c", leftPadding=0,
                                                   rightPadding=0, topPadding=0, bottomPadding=0)],
                         onPage=_cover_page(data))
    has_cover = any(s.cover for s in specs)
    doc.addPageTemplates([cover, body] if has_cover else [body])
    story: list = []
    for n, spec in enumerate(specs):
        if n > 0:
            story.append(PageBreak())
        story.append(SectionStart(spec.key, registry))
        story.extend(spec.build(data, pages))
        if spec.cover:
            story.append(NextPageTemplate("body"))
    doc.build(story)
    return buf.getvalue(), registry


def render_business_plan(data: BusinessPlanData, *, only: Optional[tuple] = None) -> bytes:
    """Due passate: la prima misura in che pagina comincia ogni sezione, la seconda stampa l'indice giusto."""
    specs = [s for s in SECTIONS if only is None or s.key in only]
    _, pages = _build(data, specs, {})
    pdf, second = _build(data, specs, pages)
    assert second == pages, "l'indice ha spostato le pagine: la copertina deve avere altezza fissa"
    return pdf
```

In fondo a `document.py` non registrare ancora nulla: `SECTIONS` resta vuota finché i Task 5, 7, 8 e 9 non aggiungono le loro sezioni con `SECTIONS.extend(...)` dentro `_register()`. La forma finale di `_register()` è nel Task 9, Step 4.

Nota: l'`import` locale di `sections_sintesi` in `_cover_page` si risolve solo quando esiste una sezione con `cover=True`, cioè dal Task 7 in poi. I test di questo task non ne hanno.

- [ ] **Step 5: Verifica che passi**

Run: `cd backend && $PY -m pytest ../tests/test_bp_layout.py -q`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/renderers/business_plan/layout.py backend/app/renderers/business_plan/document.py tests/test_bp_layout.py
git diff --cached --stat
git commit -m "feat(report-bp): primitivi ReportLab, intestazione, indice a due passate

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Sezioni 2–5 e banco di prova strutturale

Questo è il cancello del lavoro: le tre pagine dello spike, rese dal codice di produzione con i numeri del committente, devono sovrapporsi al riferimento.

**Files:**
- Create: `backend/app/renderers/business_plan/sections_economia.py`, `tests/fixtures/business_plan/banco_ambienta.json`, `tests/test_bp_banco.py`
- Modify: `backend/app/renderers/business_plan/document.py` (registrazione)

**Interfaces:**
- Consumes: `layout.*`, `charts.*`, `fmt.*`, `BusinessPlanData`, `narrative.subtitle_flussi` e `narrative.lettura_costi`, che però arrivano nel Task 6. In questo task definisci `sections_economia._subtitle_flussi` e `_lettura_costi` come fallback locali: il Task 6 li sostituisce con le funzioni di `narrative`.
- Produces: `sections_economia.economia(data, pages)`, `costi(data, pages)`, `pareggio(data, pages)`, `flussi(data, pages)`, più gli helper condivisi `row(data, label, key, style="", unit="eur", sign=1) -> tuple`, `ref_phrase(data) -> str`, `tile_from(data, key, label, fmt_fn) -> tuple`.

- [ ] **Step 1: Scrivi il fixture del banco**

`tests/fixtures/business_plan/banco_ambienta.json` contiene i numeri stampati nel PDF del committente alle pagine 4, 6 e 7. Sono gli stessi dello spike.
```json
{
  "company_name": "AMBIENTA",
  "workflow": "infrannuale",
  "columns": [
    {"period_id": "closing:2026", "year": 2026, "label": "2026 F", "is_base": true},
    {"period_id": "forecast:2027", "year": 2027, "label": "2027 P", "is_base": false},
    {"period_id": "forecast:2028", "year": 2028, "label": "2028 P", "is_base": false},
    {"period_id": "forecast:2029", "year": 2029, "label": "2029 P", "is_base": false}
  ],
  "base_description": "Base: bilancio infrannuale al 30.06.2026 (6 mesi) · forecast 2026 · piano triennale",
  "values": {
    "ricavi": ["4109510", "4314986", "4573885", "4673885"],
    "var_produzione": ["93000", "93000", "93000", "93000"],
    "altri_ricavi": ["140706", "0", "0", "0"],
    "valore_produzione": ["4343216", "4407986", "4666885", "4766885"],
    "costi_operativi": ["4177379", "4219656", "4271852", "4364688"],
    "ebitda": ["165837", "188329", "395033", "402197"],
    "ebitda_margin": ["4.04", "4.36", "8.64", "8.61"],
    "ammortamenti": ["75264", "105264", "105264", "105264"],
    "ebit": ["90573", "83065", "289769", "296933"],
    "proventi_fin": ["11750", "11750", "11750", "11750"],
    "oneri_fin": ["45192", "57688", "51701", "47651"],
    "altre_componenti": ["0", "0", "0", "0"],
    "ante_imposte": ["57131", "37128", "249818", "261031"],
    "imposte": ["33000", "10359", "69699", "72828"],
    "utile": ["24131", "26769", "180119", "188204"],
    "costi_variabili": ["2507158", "2440004", "2470175", "2533150"],
    "margine_contribuzione": ["1602352", "1874981", "2103710", "2140735"],
    "costi_fissi": ["1671438", "1780869", "1802894", "1832755"],
    "bep": ["4286693", "4098401", "3919851", "4001471"],
    "margine_sicurezza": ["-4.31", "5.02", "14.30", "14.39"],
    "cf_ebit": ["90573", "83065", "289769", "296933"],
    "cf_non_monetarie": ["156279", "224632", "224632", "224632"],
    "cf_ante_ccn": ["246852", "307697", "514401", "521564"],
    "cf_var_ccn": ["-316510", "147954", "-92561", "-6681"],
    "cf_altre": ["-155861", "-56296", "-159650", "-108729"],
    "cf_operativo": ["-225519", "399355", "262189", "406154"],
    "cf_investimenti": ["61790", "-150000", "0", "0"],
    "cf_finanziamento": ["134517", "96591", "-105000", "-105000"],
    "cf_nuovo_debito": ["134930", "96591", "0", "0"],
    "cf_rimborsi": ["0", "0", "105000", "105000"],
    "cf_variazione": ["-29212", "345946", "157189", "301154"],
    "cassa_inizio": ["29267", "55", "346000", "503190"],
    "cassa_fine": ["55", "346000", "503190", "804344"]
  },
  "growth": {"revenue_growth_pct": ["5", "6", "1"], "personnel_growth_pct": ["0", "0", "0"]},
  "partial_label": "6M 2026 R",
  "partial_dscr": null,
  "residual_revenue": "2004755",
  "draft": false
}
```

- [ ] **Step 2: Scrivi il test del banco**

`tests/test_bp_banco.py`:
```python
"""Banco di prova: le sezioni 2, 4 e 5 rese con i numeri del committente contro le pagine 4, 6 e 7 del suo PDF.

Si confrontano i riquadri pieni (per colore), le immagini dei grafici e la fascia d'intestazione. Tolleranze della
spec §6: 8 pt su y0, 3 pt sull'altezza, 2 pt su x0/x1. Il PDF del committente non è in git: senza, il test si salta.
"""
import os
from pathlib import Path

import fitz
import pytest

from app.renderers.business_plan.data import load_json
from app.renderers.business_plan.document import render_business_plan

ROOT = Path(__file__).resolve().parents[1]
REF = Path(os.environ.get("BP_RIFERIMENTO_PDF", ROOT / "tests/.banco-business-plan/riferimento.pdf"))
FIXTURE = ROOT / "tests/fixtures/business_plan/banco_ambienta.json"
PAGINE = {"economia": 4, "pareggio": 6, "flussi": 7}


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(x * 255 + 0.5) for x in c)


def boxes(page) -> list:
    out = [(f"fill{_hex(d['fill'])}", d["rect"]) for d in page.get_drawings()
           if d.get("fill") and d["rect"].height > 3]
    out += [("img", fitz.Rect(i["bbox"])) for i in page.get_image_info()]
    return out


def confronta(ref_page, new_page) -> list:
    """Restituisce le discrepanze; lista vuota = pagina conforme."""
    a, b = boxes(ref_page), boxes(new_page)
    errors = []
    if sorted(k for k, _ in a) != sorted(k for k, _ in b):
        errors.append(f"riquadri diversi: riferimento {sorted(k for k, _ in a)} contro {sorted(k for k, _ in b)}")
        return errors
    used = set()
    for kind, r in a:
        cands = [(j, rr) for j, (kk, rr) in enumerate(b) if kk == kind and j not in used]
        j, best = min(cands, key=lambda c: abs(c[1].y0 - r.y0) + abs(c[1].x0 - r.x0))
        used.add(j)
        dy, dh = best.y0 - r.y0, best.height - r.height
        dx0, dx1 = best.x0 - r.x0, best.x1 - r.x1
        if abs(dy) > 8 or abs(dh) > 3 or abs(dx0) > 2 or abs(dx1) > 2:
            errors.append(f"{kind} a y={r.y0:.1f}: dy={dy:.1f} dh={dh:.1f} dx0={dx0:.1f} dx1={dx1:.1f}")
    return errors


@pytest.mark.skipif(not REF.is_file(), reason="PDF del committente assente: il banco gira solo in locale")
def test_banco_strutturale_pagine_4_6_7():
    pdf = render_business_plan(load_json(FIXTURE), only=tuple(PAGINE))
    new = fitz.open(stream=pdf, filetype="pdf")
    ref = fitz.open(REF)
    assert new.page_count == 3
    problemi = {sec: confronta(ref[p - 1], new[i]) for i, (sec, p) in enumerate(PAGINE.items())}
    assert not any(problemi.values()), problemi


@pytest.mark.skipif(not REF.is_file(), reason="PDF del committente assente")
def test_banco_testi_chiave():
    new = fitz.open(stream=render_business_plan(load_json(FIXTURE), only=tuple(PAGINE)), filetype="pdf")
    t4, t6, t7 = (new[i].get_text() for i in range(3))
    for s in ("SEZIONE 2", "Evoluzione economica dell'impresa", "€ 4,67 mln", "Conto economico di sintesi",
              "4.109.510", "−45.192", "EBITDA (MOL)"):
        assert s in t4, s
    for s in ("SEZIONE 4", "€ 1,83 mln", "14,39%", "Margine di contribuzione", "4.286.693"):
        assert s in t6, s
    for s in ("SEZIONE 5", "€ 1,07 mln", "−€ 150 mila", "−€ 210 mila", "€ 804,3 mila", "Flusso di cassa operativo (A)"):
        assert s in t7, s
```

- [ ] **Step 3: Verifica che fallisca**

Run: `cd backend && $PY -m pytest ../tests/test_bp_banco.py -q`
Expected: FAIL, `AssertionError: assert 0 == 3`: nessuna sezione è registrata, quindi il PDF è vuoto o `doc.build` solleva su una story vuota.

- [ ] **Step 4: Scrivi `sections_economia.py`**

```python
"""Sezioni 2–5: evoluzione economica, costi, break even, flussi di cassa."""
from __future__ import annotations

from decimal import Decimal

from reportlab.platypus import Spacer

from . import charts, fmt, layout
from .data import BusinessPlanData
from .theme import CW


def row(data: BusinessPlanData, label: str, key: str, style: str = "", unit: str = "eur", sign: int = 1) -> tuple:
    vals = data.v(key)
    return (label, [fmt.value(None if v is None else v * sign, unit) for v in vals], style)


def headers(data: BusinessPlanData) -> list:
    return [c.label for c in data.columns]


def labels(data: BusinessPlanData) -> list:
    return [c.label for c in data.columns]


def ref_phrase(data: BusinessPlanData) -> str:
    plan = data.plan_years
    span = f"{plan[0]}–{plan[-1]}" if len(plan) > 1 else str(plan[0])
    base = next((c for c in data.columns if c.is_base), None)
    if base is None:
        return f"anni di piano {span} (P)"
    word = "forecast" if data.workflow == "infrannuale" else "consuntivo"
    letter = "F" if data.workflow == "infrannuale" else "C"
    return f"{word} {base.year} ({letter}) e anni di piano {span} (P)"


def tile_from(data: BusinessPlanData, key: str, label: str, fmt_fn) -> tuple:
    vals = data.v(key)
    return (fmt_fn(vals[-1]), f"{label} {data.last.year}", f"da {fmt_fn(vals[0])} nel {data.first.label}")


def _sum_plan(data: BusinessPlanData, key: str) -> Decimal | None:
    vals = [data.v(key)[i] for i in data.plan_idx]
    return None if any(v is None for v in vals) else sum(vals, Decimal(0))


def _plan_span(data: BusinessPlanData) -> str:
    y = data.plan_years
    return f"{y[0]}–{y[-1]}" if len(y) > 1 else str(y[0])


def _years_phrase(years: list) -> str:
    if not years:
        return "nessun anno"
    return years[0] if len(years) == 1 else ", ".join(years[:-1]) + " e " + years[-1]


# ---------------------------------------------------------------- sezione 2
def economia(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 2", "Evoluzione economica dell'impresa",
                            f"Gli anni sono confrontati sulla medesima base annuale: {ref_phrase(data)}.")
    s += [layout.tiles([tile_from(data, "ricavi", "Ricavi delle vendite", fmt.compact_eur),
                        tile_from(data, "ebitda", "EBITDA", fmt.compact_eur),
                        tile_from(data, "ebitda_margin", "EBITDA margin", fmt.pct),
                        tile_from(data, "utile", "Utile netto", fmt.compact_eur)]), Spacer(0, 16)]
    s += layout.h2("Ricavi delle vendite ed EBITDA margin")
    s += [layout.chart(charts.ricavi_margine(labels(data), data.v("ricavi"), data.v("ebitda_margin")),
                       charts.HEIGHTS["ricavi_margine"]), Spacer(0, 8)]
    s += layout.h2("Conto economico di sintesi", after=2)
    rows = [row(data, "Ricavi delle vendite e delle prestazioni", "ricavi"),
            row(data, "Variazioni di rimanenze, lavori in corso e incrementi", "var_produzione"),
            row(data, "Altri ricavi e proventi", "altri_ricavi"),
            row(data, "Valore della produzione", "valore_produzione", "bold"),
            row(data, "Costi della produzione (esclusi ammortamenti e svalutazioni)", "costi_operativi"),
            row(data, "EBITDA (MOL)", "ebitda", "hl"),
            row(data, "EBITDA margin", "ebitda_margin", unit="percent"),
            row(data, "Ammortamenti e svalutazioni", "ammortamenti"),
            row(data, "EBIT (risultato operativo)", "ebit", "bold"),
            row(data, "Altri proventi finanziari", "proventi_fin"),
            row(data, "Interessi e altri oneri finanziari", "oneri_fin", sign=-1)]
    if any(v not in (None, 0) for v in data.v("altre_componenti")):
        rows.append(row(data, "Cambi, rettifiche di valore e componenti straordinarie", "altre_componenti"))
    rows += [row(data, "Risultato prima delle imposte", "ante_imposte", "bold"),
             row(data, "Imposte sul reddito", "imposte", sign=-1),
             row(data, "Utile netto dell'esercizio", "utile", "hl")]
    s += [layout.fin_table(headers(data), rows), Spacer(0, 5),
          layout.note("Dettaglio completo nell'Allegato A. Il valore della produzione include le variazioni di "
                      "rimanenze e lavori in corso e gli altri ricavi.")]
    return s


# ---------------------------------------------------------------- sezione 3
def costi(data: BusinessPlanData, pages: dict) -> list:
    from .narrative import lettura_costi
    s = layout.section_head("SEZIONE 3", "EBITDA margin e struttura dei costi",
                            "Composizione dei costi della produzione per natura e loro incidenza sui ricavi.")
    s += layout.h2("EBITDA, EBIT e utile netto")
    s += [layout.chart(charts.risultati(labels(data), data.v("ebitda"), data.v("ebit"), data.v("utile")),
                       charts.HEIGHTS["risultati"], width_pt=349.3), Spacer(0, 8)]
    s += layout.h2("Costi della produzione per natura", after=6)
    rows = [row(data, "Materie prime, sussidiarie, di consumo e merci", "materie"),
            row(data, "Servizi", "servizi"), row(data, "Godimento di beni di terzi", "godimento"),
            row(data, "Personale", "personale"),
            row(data, "Variazione rimanenze materie prime", "var_rim_materie")]
    if any(v not in (None, 0) for v in data.v("accantonamenti")):
        rows.append(row(data, "Accantonamenti", "accantonamenti"))
    rows += [row(data, "Oneri diversi di gestione", "oneri_diversi"),
             row(data, "Costi operativi (prima di ammortamenti)", "costi_operativi", "bold"),
             row(data, "Ammortamenti e svalutazioni", "ammortamenti"),
             row(data, "Totale costi della produzione", "costi_produzione", "bold"),
             row(data, "EBITDA margin", "ebitda_margin", "hl", unit="percent")]
    s += [layout.fin_table(headers(data), rows), Spacer(0, 10)]
    s += layout.h2("Incidenza dei costi sui ricavi delle vendite", after=6)
    inc = [row(data, "Materie prime", "inc_materie", unit="percent"),
           row(data, "Servizi", "inc_servizi", unit="percent"),
           row(data, "Godimento di beni di terzi", "inc_godimento", unit="percent"),
           row(data, "Personale", "inc_personale", unit="percent"),
           row(data, "Oneri diversi di gestione", "inc_oneri_diversi", unit="percent"),
           row(data, "Costi operativi (prima di ammortamenti)", "inc_costi_operativi", "hl", unit="percent"),
           row(data, "Oneri finanziari", "inc_oneri_fin", unit="percent")]
    s += [layout.fin_table(headers(data), inc, first="Incidenza su ricavi delle vendite"), Spacer(0, 10),
          layout.panel("Lettura", [("", t) for t in lettura_costi(data)])]
    return s


# ---------------------------------------------------------------- sezione 4
def pareggio(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 4", "Costi fissi e variabili · break even point",
                            "Il margine di sicurezza misura di quanto i ricavi possono ridursi prima di raggiungere "
                            "il break even point; è negativo quando i ricavi sono sotto il break even point.")
    s += [layout.tiles([tile_from(data, "costi_fissi", "Costi fissi", fmt.compact_eur),
                        tile_from(data, "margine_contribuzione", "Margine di contribuzione", fmt.compact_eur),
                        tile_from(data, "bep", "Break even point", fmt.compact_eur),
                        tile_from(data, "margine_sicurezza", "Margine di sicurezza", fmt.pct)]), Spacer(0, 16)]
    s += layout.h2("Costi fissi, costi variabili, ricavi e break even point (€ migliaia)")
    s += [layout.chart(charts.pareggio(labels(data), data.v("ricavi"), data.v("costi_variabili"),
                                       data.v("costi_fissi"), data.v("bep")), charts.HEIGHTS["pareggio"])]
    s += [layout.fin_table(headers(data), [
        row(data, "Ricavi delle vendite", "ricavi"), row(data, "Costi variabili", "costi_variabili"),
        row(data, "Margine di contribuzione", "margine_contribuzione", "bold"),
        row(data, "Costi fissi", "costi_fissi"), row(data, "Break even point", "bep", "hl"),
        row(data, "Margine di sicurezza", "margine_sicurezza", "hl", unit="percent")]), Spacer(0, 4),
        layout.chart(charts.sicurezza(labels(data), data.v("margine_sicurezza")), charts.HEIGHTS["sicurezza"])]
    return s


# ---------------------------------------------------------------- sezione 5
def _financing_note(data: BusinessPlanData) -> str:
    parts = []
    for i, c in enumerate(data.columns):
        new, rep = data.v("cf_nuovo_debito")[i], data.v("cf_rimborsi")[i]
        bits = []
        if new not in (None, 0):
            bits.append(f"nuovi finanziamenti € {fmt.eur(new)}")
        if rep not in (None, 0):
            bits.append(f"rimborsi € {fmt.eur(rep)}")
        if bits:
            parts.append(f"{c.label}: " + ", ".join(bits))
    body = "; ".join(parts) if parts else "nessun nuovo finanziamento né rimborso"
    return f"Flusso di finanziamento — {body}. Dettaglio nell'Allegato C."


def flussi(data: BusinessPlanData, pages: dict) -> list:
    from .narrative import subtitle_flussi
    s = layout.section_head("SEZIONE 5", "Flussi di cassa", subtitle_flussi(data))
    op, inv, rimb = _sum_plan(data, "cf_operativo"), _sum_plan(data, "cf_investimenti"), _sum_plan(data, "cf_rimborsi")
    rimb_years = [str(data.columns[i].year) for i in data.plan_idx if data.v("cf_rimborsi")[i] not in (None, 0)]
    cassa_last = data.v("cassa_fine")[-1]
    first_plan = data.plan_idx[0]
    start = data.v("cassa_inizio")[first_plan]
    delta = None if cassa_last is None or start is None else cassa_last - start
    s += [layout.tiles([
        (fmt.compact_eur(op), "Flussi operativi", f"cumulati {_plan_span(data)}"),
        (fmt.compact_eur(inv), "Investimenti", f"cumulati {_plan_span(data)}"),
        (fmt.compact_eur(None if rimb is None else -rimb), "Rimborsi di debito", _years_phrase(rimb_years)),
        (fmt.compact_eur(cassa_last), f"Cassa a fine {data.last.year}",
         f"variazione {_plan_span(data)}: {fmt.compact_eur(delta)}")]), Spacer(0, 16)]
    s += layout.h2("Composizione dei flussi e cassa di fine anno (€ migliaia)")
    s += [layout.chart(charts.flussi(labels(data), data.v("cf_operativo"), data.v("cf_investimenti"),
                                     data.v("cf_finanziamento"), data.v("cassa_fine")), charts.HEIGHTS["flussi"])]
    s += [layout.fin_table(headers(data), [
        row(data, "Utile prima di imposte, interessi e plusvalenze", "cf_ebit"),
        row(data, "Rettifiche non monetarie (ammortamenti, accantonamenti, svalutazioni)", "cf_non_monetarie"),
        row(data, "Flusso prima delle variazioni del circolante", "cf_ante_ccn", "bold"),
        row(data, "Variazioni del capitale circolante netto", "cf_var_ccn"),
        row(data, "Interessi, imposte pagate e utilizzo fondi", "cf_altre"),
        row(data, "Flusso di cassa operativo (A)", "cf_operativo", "hl"),
        row(data, "Flusso dell'attività di investimento (B)", "cf_investimenti"),
        row(data, "Flusso dell'attività di finanziamento (C)", "cf_finanziamento"),
        row(data, "Variazione delle disponibilità liquide (A+B+C)", "cf_variazione", "bold"),
        row(data, "Disponibilità liquide a inizio esercizio", "cassa_inizio"),
        row(data, "Disponibilità liquide a fine esercizio", "cassa_fine", "hl")]), Spacer(0, 5),
        layout.note(_financing_note(data))]
    return s
```

Nel Task 5 `narrative` non esiste ancora. Crea quindi uno scheletro minimo `backend/app/renderers/business_plan/narrative.py` con le due funzioni, che il Task 6 riscrive per intero:
```python
"""Testi a regole del Business plan (versione completa nel Task 6)."""
from decimal import Decimal


def subtitle_flussi(data) -> str:
    return "Rendiconto finanziario di sintesi (metodo indiretto)."


def lettura_costi(data) -> list:
    return ["Lettura in preparazione."]
```

- [ ] **Step 5: Registra le sezioni in `document.py`**

Aggiungi in fondo a `document.py`:
```python
def _register() -> None:
    from . import sections_economia as eco
    SECTIONS.clear()
    SECTIONS.extend([
        SectionSpec("economia", "Evoluzione economica dell'impresa", eco.economia),
        SectionSpec("costi", "EBITDA margin e struttura dei costi", eco.costi),
        SectionSpec("pareggio", "Costi fissi e variabili · break even point", eco.pareggio),
        SectionSpec("flussi", "Flussi di cassa", eco.flussi),
    ])


_register()
```

- [ ] **Step 6: Esegui il banco e tara gli spazi**

Run: `cd backend && $PY -m pytest ../tests/test_bp_banco.py -q`
Expected: `2 passed`. Se il banco strutturale fallisce, il messaggio elenca per ogni riquadro `dy`, `dh`, `dx0` e `dx1`. Correggi **solo** gli `Spacer` e gli `after` di `h2` nelle sezioni (lo spike aveva la tabella della pagina 4 a +6,1 pt: portare lo spazio fra grafico e titolo a 8 e fra titolo e tabella a 2). Mai allargare le tolleranze del test.

Poi guarda la resa con i tuoi occhi:
```bash
cd /home/peter/DEV/budget-report-bp && $PY - <<'EOF'
import sys; sys.path[:0] = [".", "backend"]
import fitz
from PIL import Image
from app.renderers.business_plan.data import load_json
from app.renderers.business_plan.document import render_business_plan
pdf = fitz.open(stream=render_business_plan(load_json("tests/fixtures/business_plan/banco_ambienta.json"),
                only=("economia", "pareggio", "flussi")), filetype="pdf")
ref = fitz.open("tests/.banco-business-plan/riferimento.pdf")
for i, p in enumerate((4, 6, 7)):
    a = Image.frombytes("RGB", *(lambda px: ((px.width, px.height), px.samples))(ref[p - 1].get_pixmap(dpi=100)))
    b = Image.frombytes("RGB", *(lambda px: ((px.width, px.height), px.samples))(pdf[i].get_pixmap(dpi=100)))
    m = Image.new("RGB", (a.width * 2 + 16, a.height), "#888"); m.paste(a, (0, 0)); m.paste(b, (a.width + 16, 0))
    m.save(f"tests/.banco-business-plan/banco-p{p}.png")
EOF
```
Apri i tre PNG con il tool Read e confrontali con quelli dello spike. Differenze attese: i testi dinamici della sezione 5 e le etichette «Variazioni di rimanenze…».

- [ ] **Step 7: Commit**

```bash
git add backend/app/renderers/business_plan/sections_economia.py backend/app/renderers/business_plan/narrative.py \
  backend/app/renderers/business_plan/document.py tests/fixtures/business_plan/banco_ambienta.json tests/test_bp_banco.py
git diff --cached --stat
git commit -m "feat(report-bp): sezioni 2-5 e banco strutturale sulle pagine 4, 6, 7 del committente

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Testi deterministici

**Files:**
- Modify: `backend/app/renderers/business_plan/narrative.py` (riscrittura completa)
- Test: `tests/test_bp_narrative.py`

**Interfaces:**
- Consumes: `BusinessPlanData`, `fmt`.
- Produces: `SOGLIE: dict[str, Decimal]`; `key_points(data) -> list[tuple[str, str]]`; `strengths_weaknesses(data) -> tuple[list[Finding], list[Finding]]`, con `Finding(id: str, title: str, text: str)`; `actions(data, weaknesses) -> list[tuple[str, str, str]]`; `lettura_costi(data) -> list[str]`; `lettura_circolante(data) -> list[str]`; `subtitle_flussi(data) -> str`; `growth_list(data, field) -> str | None`.

- [ ] **Step 1: Scrivi il test**

`tests/test_bp_narrative.py`:
```python
"""Le regole dei testi: stessa pratica, stesso testo; ogni frase nasce da una soglia dichiarata."""
from decimal import Decimal as D

from app.renderers.business_plan import narrative
from app.renderers.business_plan.data import BusinessPlanData, Column

COLS = (Column("closing:2026", 2026, "2026 F", True),) + tuple(
    Column(f"forecast:{y}", y, f"{y} P", False) for y in (2027, 2028, 2029))


def make(values: dict, growth: dict | None = None, workflow="infrannuale", residual=D("2004755")):
    vals = {k: tuple(None if x is None else D(str(x)) for x in v) for k, v in values.items()}
    g = {k: tuple(D(str(x)) for x in v) for k, v in (growth or {}).items()}
    return BusinessPlanData(company_name="X", workflow=workflow, columns=COLS, base_description="",
                            values=vals, growth=g, residual_revenue=residual)


AMBIENTA = {
    "ricavi": [4109510, 4314986, 4573885, 4673885], "ebitda": [165837, 188329, 395033, 402197],
    "ebitda_margin": [4.04, 4.36, 8.64, 8.61], "inc_personale": [57.06, 54.34, 51.26, 50.17],
    "personale": [2344742] * 4, "dscr": [2.939, 3.085, 6.293, 6.912], "of_mol": [27.25, 30.63, 13.09, 11.85],
    "cf_operativo": [-225519, 399355, 262189, 406154], "cf_investimenti": [61790, -150000, 0, 0],
    "cf_rimborsi": [0, 0, 105000, 105000], "pfn": [960883, 721528, 469339, 73185],
    "pfn_ebitda": [5.794, 3.831, 1.188, 0.182], "margine_sicurezza": [-4.31, 5.02, 14.30, 14.39],
    "dso": [119, 101, 99, 93], "dpo": [126, 126, 125, 120], "ciclo": [18, 0, 2, 3],
    "patrimonio_netto": [203616, 230385, 410503, 598707], "margine_struttura": [-253424, -281391, -6008, 277460],
    "indipendenza": [8.79, 8.89, 14.81, 20.15], "cassa_fine": [55, 346000, 503190, 804344],
    "banche": [960937, 1067528, 972528, 877528], "banche_breve": [493409, 495000, 495000, 450000],
    "costi_fissi": [1671438, 1780869, 1802894, 1832755], "cf_variazione": [-29212, 345946, 157189, 301154],
    "cc_comm": [852261, 888269, 979298, 983378], "inc_costi_operativi": [101.65, 97.79, 93.40, 93.38],
    "inc_servizi": [34.86, 34.03, 33.06, 32.52], "inc_materie": [3.15, 3.15, 3.15, 3.51],
    "inc_godimento": [5.71, 5.44, 5.13, 5.86], "inc_oneri_diversi": [0.91, 0.87, 0.82, 1.36],
}
GROWTH = {"revenue_growth_pct": [5, 6, 1], "personnel_growth_pct": [0, 0, 0], "dso_days": [96, 95, 90]}


def test_punti_chiave_ambienta():
    kp = narrative.key_points(make(AMBIENTA, GROWTH))
    leads = [lead for lead, _ in kp]
    assert leads == ["Crescita dei ricavi.", "Redditività in miglioramento.", "Servizio del debito coperto.",
                     "Generazione di cassa e deleveraging.", "Sopra il break even point.",
                     "Circolante più efficiente."]
    assert "del 5% nel 2027, del 6% nel 2028 e dell'1% nel 2029" in kp[0][1]
    assert "dal 4,04% all'8,61%" in kp[1][1]


def test_forza_debolezza_e_azioni_ambienta():
    forza, debolezza = narrative.strengths_weaknesses(make(AMBIENTA, GROWTH))
    assert [f.id for f in forza] == ["margini", "cassa", "deleveraging", "incassi", "patrimonio"]
    assert [f.id for f in debolezza] == ["sotto_bep", "costi_rigidi", "tensione_liquidita", "sottocapitalizzazione",
                                         "debito_breve"]
    azioni = narrative.actions(make(AMBIENTA, GROWTH), debolezza)
    assert [a[0] for a in azioni] == ["Consolidare il forecast 2026", "Superare stabilmente il break even point",
                                      "Presidiare i costi fissi", "Accelerare gli incassi",
                                      "Riequilibrare la struttura finanziaria"]
    assert "€ 2.004.755" in azioni[0][1]


def test_regole_di_segno_opposto():
    peggio = dict(AMBIENTA, ebitda_margin=[8, 7, 6, 5], cf_operativo=[10, -5, -3, 2], margine_sicurezza=[5, 3, 1, -2],
                  ciclo=[10, 20, 30, 40], pfn=[100, 200, 300, 400], pfn_ebitda=[1, 2, 3, 4], dscr=[3, 0.8, 1.1, 1.2])
    kp = dict(narrative.key_points(make(peggio, GROWTH)))
    assert "Redditività in calo." in kp and "Sotto il break even point." in kp
    assert "Servizio del debito non coperto." in kp and "Circolante in assorbimento." in kp
    forza, debolezza = narrative.strengths_weaknesses(make(peggio, GROWTH))
    assert {"margini_calo", "flussi_negativi", "indebitamento"} <= {f.id for f in debolezza}


def test_narrativa_senza_dati():
    vuota = make({})
    assert narrative.key_points(vuota) == []
    forza, debolezza = narrative.strengths_weaknesses(vuota)
    assert forza == [] and debolezza == []
    assert narrative.actions(make({}, workflow="startup"), []) == [
        ("Monitorare il piano", "Confrontare trimestralmente consuntivo e piano su ricavi, EBITDA e cassa.",
         "Ricavi, EBITDA, cassa")]
    assert narrative.lettura_costi(vuota) == []
    assert narrative.subtitle_flussi(vuota).startswith("Rendiconto finanziario di sintesi")


def test_testo_deterministico():
    a = make(AMBIENTA, GROWTH)
    assert narrative.key_points(a) == narrative.key_points(make(AMBIENTA, GROWTH))
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && $PY -m pytest ../tests/test_bp_narrative.py -q`
Expected: FAIL, `AttributeError: module ... has no attribute 'key_points'`

- [ ] **Step 3: Riscrivi `narrative.py`**

```python
"""Testi del Business plan, a regole deterministiche (spec D3): ogni frase nasce da una soglia in SOGLIE.

Un dato assente toglie la frase, non la inventa. Nessun LLM: stessa pratica, stesso testo.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from . import fmt
from .data import BusinessPlanData

D = Decimal
SOGLIE = {
    "margine_variazione_pp": D("1"),     # punti di EBITDA margin per dire «in espansione» o «in contrazione»
    "margine_stabile_pp": D("0.5"),
    "dscr_coperto": D("1.25"),
    "dscr_limite": D("1"),
    "dscr_ampio": D("2"),
    "pfn_ebitda_alto": D("3"),
    "dso_variazione_gg": D("5"),
    "indipendenza_bassa": D("15"),
    "personale_alto": D("50"),
    "banche_breve_quota": D("40"),
    "cassa_minima_ricavi_pct": D("1"),
    "dso_da_accelerare": D("90"),
}


@dataclass(frozen=True)
class Finding:
    id: str
    title: str
    text: str


def _v(data: BusinessPlanData, key: str) -> list:
    return list(data.v(key))


def _ends(data: BusinessPlanData, key: str) -> tuple:
    vals = _v(data, key)
    return (vals[0], vals[-1]) if vals else (None, None)


def _plan(data: BusinessPlanData, key: str) -> list:
    return [(data.columns[i], data.v(key)[i]) for i in data.plan_idx]


def _plan_values(data: BusinessPlanData, key: str) -> list:
    return [v for _, v in _plan(data, key)]


def _all(*xs) -> bool:
    return all(x is not None for x in xs)


def _join(items: list) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


def growth_list(data: BusinessPlanData, field: str) -> Optional[str]:
    vals = data.growth.get(field)
    if not vals or any(v is None for v in vals):
        return None
    return " / ".join(fmt.pct_short(v) for v in vals)


def _growth_phrase(data: BusinessPlanData) -> Optional[str]:
    vals = data.growth.get("revenue_growth_pct")
    if not vals or any(v is None for v in vals):
        return None
    parts = [f"{fmt.prep('del', fmt.pct_short(v))} nel {y}" for v, y in zip(vals, data.plan_years)]
    return _join(parts)


def _span(data: BusinessPlanData) -> str:
    y = data.plan_years
    return f"{y[0]}–{y[-1]}" if len(y) > 1 else str(y[0])


# ---------------------------------------------------------------- punti chiave (sezione 1)
def key_points(data: BusinessPlanData) -> list:
    out = []
    c0, cn = data.first.label, data.last.label
    r0, rn = _ends(data, "ricavi")
    if _all(r0, rn):
        lead = "Crescita dei ricavi." if rn > r0 else ("Ricavi stabili." if rn == r0 else "Ricavi in calo.")
        text = f"I ricavi delle vendite passano da € {fmt.eur(r0)} ({c0}) a € {fmt.eur(rn)} ({cn})"
        g = _growth_phrase(data)
        out.append((lead, text + (f", con ipotesi di crescita {g}." if g else ".")))
    m0, mn = _ends(data, "ebitda_margin")
    e0, en = _ends(data, "ebitda")
    if _all(m0, mn, e0, en):
        delta = mn - m0
        lead = ("Redditività in miglioramento." if delta > SOGLIE["margine_stabile_pp"] else
                "Redditività in calo." if delta < -SOGLIE["margine_stabile_pp"] else "Redditività stabile.")
        text = (f"L'EBITDA passa da € {fmt.eur(e0)} a € {fmt.eur(en)} e l'EBITDA margin "
                f"{fmt.prep('dal', fmt.pct(m0))} {fmt.prep('al', fmt.pct(mn))}.")
        p0, pn = _ends(data, "inc_personale")
        if _all(p0, pn):
            text += (f" L'incidenza del costo del personale sui ricavi passa "
                     f"{fmt.prep('dal', fmt.pct(p0))} {fmt.prep('al', fmt.pct(pn))}.")
        out.append((lead, text))
    dscr = [(c, v) for c, v in _plan(data, "dscr") if v is not None]
    of = [(c, v) for c, v in _plan(data, "of_mol") if v is not None]
    if dscr:
        mn_d = min(v for _, v in dscr)
        lead = ("Servizio del debito coperto." if mn_d >= SOGLIE["dscr_coperto"] else
                "Servizio del debito al limite." if mn_d >= SOGLIE["dscr_limite"] else
                "Servizio del debito non coperto.")
        (c1, d1), (cl, dl) = dscr[0], dscr[-1]
        text = f"Il DSCR (proxy) è pari a {fmt.ratio(d1)} nel {c1.year} e a {fmt.ratio(dl)} nel {cl.year}"
        if len(of) >= 2:
            text += (f"; gli oneri finanziari passano {fmt.prep('dal', fmt.pct(of[0][1]))} "
                     f"{fmt.prep('al', fmt.pct(of[-1][1]))} del MOL")
        out.append((lead, text + "."))
    op = _plan_values(data, "cf_operativo")
    inv = _plan_values(data, "cf_investimenti")
    rimb = _plan_values(data, "cf_rimborsi")
    f0, fn = _ends(data, "pfn")
    pe0, pen = _ends(data, "pfn_ebitda")
    if op and _all(*op, *inv, *rimb, f0, fn, pe0, pen):
        s_op, s_inv, s_r = sum(op, D(0)), sum(inv, D(0)), sum(rimb, D(0))
        lead = ("Generazione di cassa e deleveraging." if s_op > 0 and fn < f0 else
                "Generazione di cassa." if s_op > 0 else "Assorbimento di cassa.")
        out.append((lead, f"I flussi operativi cumulati {_span(data)} sono pari a {fmt.compact_eur(s_op)}, a fronte "
                          f"di investimenti per {fmt.compact_eur(abs(s_inv))} e rimborsi per {fmt.compact_eur(s_r)}. "
                          f"La PFN passa da € {fmt.eur(f0)} a € {fmt.eur(fn)} e il rapporto PFN/EBITDA da "
                          f"{fmt.ratio(pe0)} a {fmt.ratio(pen)}."))
    ms0, msn = _ends(data, "margine_sicurezza")
    if _all(ms0, msn):
        lead = "Sopra il break even point." if msn >= 0 else "Sotto il break even point."
        turn = next(((c, v) for c, v in _plan(data, "margine_sicurezza") if v is not None and v >= 0), None)
        if ms0 < 0 <= msn and turn:
            text = (f"Il margine di sicurezza, negativo nel {c0} ({fmt.pct(ms0)}), diventa positivo dal "
                    f"{turn[0].year} ({fmt.pct(turn[1])}) e raggiunge il {fmt.pct(msn)} nel {data.last.year}.")
        else:
            text = (f"Il margine di sicurezza passa {fmt.prep('dal', fmt.pct(ms0))} ({c0}) "
                    f"{fmt.prep('al', fmt.pct(msn))} ({cn}).")
        out.append((lead, text))
    d0, dn = _ends(data, "dso")
    k0, kn = _ends(data, "ciclo")
    if _all(d0, dn, k0, kn):
        lead = ("Circolante più efficiente." if kn < k0 else
                "Circolante stabile." if kn == k0 else "Circolante in assorbimento.")
        out.append((lead, f"I giorni di incasso (DSO) passano da {fmt.eur(d0)} a {fmt.eur(dn)}, il ciclo di "
                          f"conversione del denaro da {fmt.eur(k0)} a {fmt.eur(kn)} giorni."))
    return out


# ---------------------------------------------------------------- forza e debolezza (sezione 1 · segue)
def strengths_weaknesses(data: BusinessPlanData) -> tuple:
    forza, debolezza = [], []
    c0 = data.first.label
    m0, mn = _ends(data, "ebitda_margin")
    if _all(m0, mn):
        if mn - m0 >= SOGLIE["margine_variazione_pp"]:
            forza.append(Finding("margini", "Margini in espansione",
                                 f"EBITDA margin {fmt.prep('dal', fmt.pct(m0))} ({c0}) {fmt.prep('al', fmt.pct(mn))} "
                                 f"({data.last.label})."))
        elif m0 - mn >= SOGLIE["margine_variazione_pp"]:
            debolezza.append(Finding("margini_calo", "Margini in contrazione",
                                     f"EBITDA margin {fmt.prep('dal', fmt.pct(m0))} {fmt.prep('al', fmt.pct(mn))}."))
    op = _plan(data, "cf_operativo")
    if op and all(v is not None for _, v in op):
        neg = [str(c.year) for c, v in op if v < 0]
        if not neg:
            forza.append(Finding("cassa", "Generazione di cassa",
                                 f"Flussi operativi positivi in ogni anno di piano, "
                                 f"{fmt.compact_eur(sum((v for _, v in op), D(0)))} cumulati; liquidità a fine "
                                 f"{data.last.year} pari a € {fmt.eur(data.v('cassa_fine')[-1])}."))
        else:
            debolezza.append(Finding("flussi_negativi", f"Flussi operativi negativi nel {_join(neg)}",
                                     "La gestione operativa assorbe cassa in almeno un anno di piano."))
    f0, fn = _ends(data, "pfn")
    pe0, pen = _ends(data, "pfn_ebitda")
    dscr_plan = [v for v in _plan_values(data, "dscr") if v is not None]
    if _all(f0, fn, pe0, pen):
        if fn < f0 and pen < pe0:
            txt = f"PFN da € {fmt.eur(f0)} a € {fmt.eur(fn)} e PFN/EBITDA da {fmt.ratio(pe0)} a {fmt.ratio(pen)}."
            if dscr_plan:
                txt += f" DSCR (proxy) mai inferiore a {fmt.ratio(min(dscr_plan), 1)}."
            forza.append(Finding("deleveraging", "Rapido deleveraging", txt))
        if pen > SOGLIE["pfn_ebitda_alto"]:
            debolezza.append(Finding("indebitamento", "Indebitamento elevato",
                                     f"PFN/EBITDA pari a {fmt.ratio(pen)} nel {data.last.year}."))
    if dscr_plan and min(dscr_plan) < SOGLIE["dscr_limite"]:
        debolezza.append(Finding("dscr_basso", "Servizio del debito non coperto",
                                 f"DSCR (proxy) minimo pari a {fmt.ratio(min(dscr_plan))}."))
    d0, dn = _ends(data, "dso")
    k0, kn = _ends(data, "ciclo")
    if _all(d0, dn):
        if d0 - dn >= SOGLIE["dso_variazione_gg"]:
            txt = f"DSO da {fmt.eur(d0)} a {fmt.eur(dn)} giorni"
            if _all(k0, kn):
                txt += f"; ciclo di conversione del denaro da {fmt.eur(k0)} a {fmt.eur(kn)} giorni"
            forza.append(Finding("incassi", "Incassi più rapidi", txt + "."))
        elif dn - d0 >= SOGLIE["dso_variazione_gg"]:
            debolezza.append(Finding("incassi_lenti", "Incassi più lenti",
                                     f"DSO da {fmt.eur(d0)} a {fmt.eur(dn)} giorni."))
    p0, pn = _ends(data, "patrimonio_netto")
    msn = data.v("margine_struttura")[-1]
    if _all(p0, pn, msn) and pn > p0 and msn > 0:
        forza.append(Finding("patrimonio", "Rafforzamento patrimoniale",
                             f"Patrimonio netto da € {fmt.eur(p0)} a € {fmt.eur(pn)}; margine di struttura positivo "
                             f"nel {data.last.year} (€ {fmt.eur(msn)})."))
    ms0 = data.v("margine_sicurezza")[0]
    base = data.columns[0].is_base
    if base and ms0 is not None and ms0 < 0:
        debolezza.append(Finding("sotto_bep", "Punto di partenza sotto il break even point",
                                 f"Nel {c0} il margine di sicurezza è {fmt.pct(ms0)}."))
    pers0 = data.v("inc_personale")[0]
    fissi0, r0 = data.v("costi_fissi")[0], data.v("ricavi")[0]
    if pers0 is not None and pers0 > SOGLIE["personale_alto"]:
        txt = f"Il personale assorbe il {fmt.pct(pers0)} dei ricavi"
        if _all(fissi0):
            txt = f"Costi fissi pari a {fmt.compact_eur(fissi0)} nel {c0}; " + txt[0].lower() + txt[1:]
        debolezza.append(Finding("costi_rigidi", "Struttura dei costi rigida",
                                 txt + ". Una crescita dei ricavi inferiore al piano incide direttamente sul margine."))
    cassa0, op0 = data.v("cassa_fine")[0], data.v("cf_operativo")[0]
    if base and _all(cassa0, r0) and r0 > 0 and (
            cassa0 / r0 * 100 < SOGLIE["cassa_minima_ricavi_pct"] or (op0 is not None and op0 < 0)):
        debolezza.append(Finding("tensione_liquidita", f"Tensione di liquidità nel {data.first.year}",
                                 f"Flusso operativo {c0} pari a € {fmt.eur(op0)} e disponibilità liquide a fine "
                                 f"{data.first.year} pari a € {fmt.eur(cassa0)}."))
    ind0 = data.v("indipendenza")[0]
    if ind0 is not None and ind0 < SOGLIE["indipendenza_bassa"]:
        debolezza.append(Finding("sottocapitalizzazione", "Sottocapitalizzazione iniziale",
                                 f"Indipendenza finanziaria al {fmt.pct(ind0)} nel {c0}."))
    b0, bb0 = data.v("banche")[0], data.v("banche_breve")[0]
    if _all(b0, bb0) and b0 > 0 and bb0 / b0 * 100 > SOGLIE["banche_breve_quota"]:
        debolezza.append(Finding("debito_breve", "Debito bancario a breve",
                                 f"Debiti verso banche entro 12 mesi pari a € {fmt.eur(bb0)} nel {c0}, "
                                 f"il {fmt.pct(bb0 / b0 * 100, 0)} dell'esposizione bancaria."))
    return forza[:5], debolezza[:5]


# ---------------------------------------------------------------- azioni prioritarie
_AZIONI = {
    "sotto_bep": ("Superare stabilmente il break even point", None, "Margine di sicurezza, ricavi vs break even point"),
    "costi_rigidi": ("Presidiare i costi fissi", None, "Incidenza personale e costi fissi sui ricavi"),
    "margini_calo": ("Recuperare marginalità", "Verificare prezzi, mix e costi variabili che riducono l'EBITDA margin.",
                     "EBITDA margin"),
    "flussi_negativi": ("Coprire il fabbisogno operativo",
                        "Pianificare le fonti che coprono gli anni con flusso operativo negativo.",
                        "Flusso operativo, cassa"),
    "dscr_basso": ("Rinegoziare il servizio del debito",
                   "Allineare il piano di rimborso ai flussi che la gestione genera.", "DSCR"),
    "tensione_liquidita": ("Presidiare la liquidità", None, "Saldo di cassa, flusso operativo"),
}
_STRUTTURA = {"sottocapitalizzazione", "debito_breve", "indebitamento"}


def actions(data: BusinessPlanData, weaknesses: list) -> list:
    out = []
    if data.workflow == "infrannuale" and data.residual_revenue is not None:
        out.append((f"Consolidare il forecast {data.first.year}",
                    f"Verificare con i dati contabili più recenti il raggiungimento dei ricavi stimati per il periodo "
                    f"residuo (€ {fmt.eur(data.residual_revenue)}) e presidiare la liquidità di fine anno.",
                    "Ricavi e EBITDA mensili, saldo di cassa"))
    ids = [w.id for w in weaknesses]
    for wid in ids:
        if wid not in _AZIONI:
            continue
        if wid == "tensione_liquidita" and data.workflow == "infrannuale":
            continue  # già coperta da «Consolidare il forecast», che chiede di presidiare la liquidità di fine anno
        title, text, kpi = _AZIONI[wid]
        if wid == "sotto_bep":
            g = growth_list(data, "revenue_growth_pct")
            text = ("Sostenere la crescita dei ricavi" + (f" ({g})" if g else "") +
                    " con portafoglio ordini, contratti in essere e capacità operativa.")
        elif wid == "costi_rigidi":
            text = (f"Mantenere il costo del personale sul livello di piano (€ {fmt.eur(data.v('personale')[-1])}) "
                    "e monitorare servizi e godimento beni di terzi.")
        elif wid == "tensione_liquidita":
            text = f"Pianificare incassi e pagamenti del {data.first.year} per evitare tensioni di cassa."
        out.append((title, text, kpi))
    dso0 = data.v("dso")[0]
    target = growth_list(data, "dso_days")
    if target and dso0 is not None and dso0 > SOGLIE["dso_da_accelerare"]:
        out.append(("Accelerare gli incassi",
                    f"Portare i tempi di incasso ai giorni ipotizzati ({target.replace('%', '')}) con azioni su "
                    "scaduto e condizioni commerciali.", "DSO, scaduto clienti, ciclo monetario"))
    if _STRUTTURA & set(ids):
        out.append(("Riequilibrare la struttura finanziaria",
                    "Allineare la quota di debito a breve ai flussi del piano e mantenere gli utili a riserva per "
                    "rafforzare il patrimonio netto.", "PFN/EBITDA, DSCR, indipendenza finanziaria"))
    if not out:
        out.append(("Monitorare il piano", "Confrontare trimestralmente consuntivo e piano su ricavi, EBITDA e cassa.",
                    "Ricavi, EBITDA, cassa"))
    return out[:5]


# ---------------------------------------------------------------- letture e sottotitoli
_VOCI = (("inc_materie", "le materie prime"), ("inc_servizi", "i servizi"), ("inc_godimento", "il godimento di beni di terzi"),
         ("inc_personale", "il personale"), ("inc_oneri_diversi", "gli oneri diversi di gestione"))


def lettura_costi(data: BusinessPlanData) -> list:
    out = []
    p0, pn = _ends(data, "inc_personale")
    m0, mn = _ends(data, "ebitda_margin")
    pers_growth = data.growth.get("personnel_growth_pct")
    if _all(p0, pn, m0, mn) and pers_growth and all(v == 0 for v in pers_growth) and mn > m0 and pn < p0:
        out.append("Il miglioramento del margine deriva principalmente dalla stabilità del costo del personale "
                   "(crescita ipotizzata 0%) a fronte della crescita dei ricavi: l'incidenza del personale scende di "
                   f"{fmt.pct(p0 - pn, 1).replace('%', '')} punti.")
    else:
        o0, on = _ends(data, "inc_costi_operativi")
        if _all(o0, on):
            out.append(f"L'incidenza dei costi operativi sui ricavi passa {fmt.prep('dal', fmt.pct(o0))} "
                       f"{fmt.prep('al', fmt.pct(on))}.")
    last = [(label, data.v(k)[-1]) for k, label in _VOCI if data.v(k)[-1] is not None]
    if last:
        label, v = max(last, key=lambda x: x[1])
        out.append(f"Nel {data.last.year} la voce di costo con l'incidenza maggiore è {label} ({fmt.pct(v)} dei ricavi).")
    return out


def lettura_circolante(data: BusinessPlanData) -> list:
    out = []
    c0, cn = _ends(data, "cc_comm")
    r0, rn = _ends(data, "ricavi")
    d0, dn = _ends(data, "dso")
    p0, pn = _ends(data, "dpo")
    if _all(c0, cn, r0, rn) and c0 and r0:
        gc, gr = (cn / c0 - 1) * 100, (rn / r0 - 1) * 100
        verso = "meno" if gc < gr else "più"
        txt = (f"Il circolante commerciale cresce {verso} che proporzionalmente ai ricavi ({fmt.pct(gc, 1)} contro "
               f"{fmt.pct(gr, 1)})")
        if _all(d0, dn, p0, pn):
            txt += (f"; i giorni di incasso passano da {fmt.eur(d0)} a {fmt.eur(dn)} e quelli di pagamento da "
                    f"{fmt.eur(p0)} a {fmt.eur(pn)}")
        out.append(txt + ".")
    k0, kn = _ends(data, "ciclo")
    if _all(k0, kn):
        out.append(f"Il ciclo di conversione del denaro passa da {fmt.eur(k0)} giorni ({data.first.label}) a "
                   f"{fmt.eur(kn)} giorni ({data.last.label}).")
    return out


def subtitle_flussi(data: BusinessPlanData) -> str:
    base = "Rendiconto finanziario di sintesi (metodo indiretto)."
    plan = _plan(data, "cf_variazione")
    if not plan or any(v is None for _, v in plan):
        return base
    neg = [str(c.year) for c, v in plan if v < 0]
    if not neg:
        return base + " Il piano genera cassa in ogni anno, sufficiente a finanziare investimenti e rimborsi."
    return base + f" La cassa diminuisce nel {_join(neg)}."
```

Controllo dei due test di AMBIENTA: `debito_breve` scatta perché 493.409 / 960.937 = 51% > 40%, e `tensione_liquidita` perché la cassa 2026 F (55 €) è sotto l'1% dei ricavi. Le azioni sono: forecast (infrannuale), `sotto_bep`, `costi_rigidi`, «Accelerare gli incassi» (DSO base 119 > 90 con i giorni ipotizzati) e «Riequilibrare la struttura» (sottocapitalizzazione / debito breve). Sono cinque. Sull'infrannuale `tensione_liquidita` non genera un'azione sua, perché la copre già «Consolidare il forecast». Se l'ordine prodotto differisce da quello del test, **l'ordine del test è la specifica**: le azioni seguono l'ordine delle debolezze, poi gli incassi, poi la struttura. Aggiusta il codice, non il test.

- [ ] **Step 4: Verifica che passi, banco compreso**

Run: `cd backend && $PY -m pytest ../tests/test_bp_narrative.py ../tests/test_bp_banco.py -q`
Expected: `7 passed`. Il banco deve restare verde: il sottotitolo della sezione 5 è cambiato, ma non la sua altezza.

- [ ] **Step 5: Commit**

```bash
git add backend/app/renderers/business_plan/narrative.py tests/test_bp_narrative.py
git diff --cached --stat
git commit -m "feat(report-bp): testi deterministici — punti chiave, forza/debolezza, azioni, letture

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Copertina, sezione 1 e sezioni 6–8

**Files:**
- Create: `backend/app/renderers/business_plan/sections_sintesi.py`, `backend/app/renderers/business_plan/sections_finanza.py`
- Modify: `backend/app/renderers/business_plan/document.py` (`_register`)
- Test: `tests/test_bp_document.py`

**Interfaces:**
- Consumes: `narrative.key_points`, `strengths_weaknesses`, `actions`, `lettura_circolante`; `sections_economia.row`, `headers`, `labels`, `tile_from`, `_sum_plan`, `_plan_span`; `charts.debito`, `dscr_pfn`, `circolante`.
- Produces: `sections_sintesi.draw_cover_band(canvas, data)`, `copertina(data, pages)`, `sintesi(data, pages)`, `forza(data, pages)`, `INDEX: list[tuple[str, str, str]]`; `sections_finanza.debito(data, pages)`, `circolante(data, pages)`, `solidita(data, pages)`.

- [ ] **Step 1: Scrivi il test**

`tests/test_bp_document.py`:
```python
"""Documento completo sui bilanci veri (DB locale copiato): tre workflow, indice coerente, nessuna eccezione."""
import fitz
import pytest

from app.renderers.business_plan.document import render_business_plan
from tests.test_bp_data import _data, db  # noqa: F401  (fixture condivisa)


@pytest.mark.parametrize("caso", ["infrannuale", "bilancio", "startup"])
def test_documento_completo(db, caso):  # noqa: F811
    data = _data(db, caso)
    pdf = fitz.open(stream=render_business_plan(data), filetype="pdf")
    assert pdf.page_count >= 12
    cover = pdf[0].get_text()
    assert data.company_name in cover and "I numeri chiave del piano" in cover and "Indice" in cover
    # l'indice punta alla pagina dove il titolo compare davvero
    for title, page in _index_entries(pdf[0]):
        assert title.split(" · ")[0][:25] in pdf[page - 1].get_text(), (title, page)


def _index_entries(page):
    """Righe «N  Titolo … pagina» dell'indice in copertina."""
    words = page.get_text("words")
    lines = {}
    for x0, y0, x1, y1, w, *_ in words:
        if y0 > 500:
            lines.setdefault(round(y0), []).append((x0, w))
    out = []
    for _, ws in sorted(lines.items()):
        ws.sort()
        if len(ws) >= 3 and ws[-1][1].isdigit() and ws[0][1].isdigit():
            out.append((" ".join(w for _, w in ws[1:-1]), int(ws[-1][1])))
    return out


def test_sezione_uno_ambienta(db):  # noqa: F811
    pdf = fitz.open(stream=render_business_plan(_data(db, "infrannuale")), filetype="pdf")
    testi = [p.get_text() for p in pdf]
    # la sintesi sta in una pagina, come nel riferimento; forza/debolezza/azioni nella successiva
    i = next(n for n, t in enumerate(testi) if "Punti chiave del piano" in t)
    assert "Cruscotto degli indicatori" in testi[i]
    assert all(s in testi[i + 1] for s in ("Punti di forza", "Punti di debolezza", "Azioni prioritarie"))
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && $PY -m pytest ../tests/test_bp_document.py -q`
Expected: FAIL. Mancano la copertina e le sezioni: `page_count` è minore di 12, o `"I numeri chiave del piano"` non compare.

- [ ] **Step 3: Scrivi `sections_sintesi.py`**

```python
"""Copertina e sezione 1: numeri chiave, indice, sintesi, forza/debolezza e azioni."""
from __future__ import annotations

from decimal import Decimal

from reportlab.lib.colors import HexColor, white
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from . import fmt, layout, narrative, theme
from .data import BusinessPlanData
from .sections_economia import _plan_span, _sum_plan, headers, row
from .theme import BOLD, CW, LM, PAGE_H, PAGE_W, REGULAR

C = HexColor

INDEX = [  # (numero, titolo dell'indice, chiave di sezione)
    ("1", "Sintesi del piano · punti di forza, di debolezza e azioni prioritarie", "sintesi"),
    ("2", "Evoluzione economica dell'impresa", "economia"),
    ("3", "EBITDA margin e struttura dei costi", "costi"),
    ("4", "Costi fissi e variabili · break even point", "pareggio"),
    ("5", "Flussi di cassa", "flussi"),
    ("6", "Sostenibilità del debito · DSCR e PFN", "debito"),
    ("7", "Capitale circolante commerciale", "circolante"),
    ("8", "Solidità patrimoniale, liquidità e redditività", "solidita"),
    ("9", None, "partenza"),  # titolo dal punto di partenza del workflow
    ("10", "Assunzioni del piano", "ipotesi"),
    ("", "Allegati A–E · prospetti completi e indicatori", "allegato_a"),
]


def _years(data: BusinessPlanData) -> str:
    y = data.plan_years
    return f"{y[0]} – {y[-1]}" if len(y) > 1 else str(y[0])


def draw_cover_band(canvas, data: BusinessPlanData) -> None:
    """Fascia navy della copertina (0–283,5 pt dall'alto) con filetto teal, come nel riferimento."""
    theme.register_fonts()
    canvas.saveState()
    canvas.setFillColor(C(theme.NAVY))
    canvas.rect(0, PAGE_H - 283.5, PAGE_W, 283.5, stroke=0, fill=1)
    canvas.setFillColor(C(theme.TEAL))
    canvas.rect(0, PAGE_H - 289.1, PAGE_W, 5.6, stroke=0, fill=1)
    canvas.setFillColor(white)
    canvas.setFont(BOLD, 10)
    canvas.drawString(LM, PAGE_H - 64, f"REPORT DI BUDGET {_years(data)}" + (" · BOZZA" if data.draft else ""))
    name = data.company_name
    size = 40 if canvas.stringWidth(name, BOLD, 40) <= CW else max(20, 40 * CW / canvas.stringWidth(name, BOLD, 40))
    canvas.setFont(BOLD, size)
    canvas.drawString(LM, PAGE_H - 122, name)
    canvas.setFont(REGULAR, 21)
    canvas.drawString(LM, PAGE_H - 160, f"Piano economico-finanziario {_years(data)}")
    canvas.setFillColor(C(theme.COVER_SUB))
    canvas.setFont(REGULAR, 11)
    canvas.drawString(LM, PAGE_H - 200, data.base_description)
    canvas.drawString(LM, PAGE_H - 220, "Andamento economico, flussi di cassa, sostenibilità del debito e circolante")
    canvas.setFillColor(C(theme.MUTED))
    canvas.setFont(REGULAR, 7.8)
    canvas.drawString(LM, PAGE_H - 820, "Riservato e confidenziale")
    canvas.restoreState()


def _chip_tiles(items: list) -> Table:
    """Riquadri di copertina: chip teal con il periodo, valore, etichetta, nota."""
    gap = 8.5
    w = (CW - 3 * gap) / 4
    chip = layout._ps("chip", BOLD, 8.6, 10, "#ffffff")
    val = layout._ps("cv", BOLD, 12.5, 15, theme.NAVY)
    cells = []
    for period, value, label, sub in items:
        c = Table([[Paragraph(period, chip)]], colWidths=[w - 11])
        c.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(theme.TEAL)), ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)]))
        cells.append([c, Spacer(0, 3), Paragraph(value, val), Paragraph(label, layout.ST["kl"]), Spacer(0, 1),
                      Paragraph(sub, layout.ST["ks"])])
    rows = [cells[:4], cells[4:8]]
    data = [[r[0], "", r[1], "", r[2], "", r[3]] for r in rows]
    t = Table(data, colWidths=[w, gap, w, gap, w, gap, w])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5.5),
             ("RIGHTPADDING", (0, 0), (-1, -1), 5.5), ("TOPPADDING", (0, 0), (-1, -1), 6),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
    for r in range(2):
        for c in (0, 2, 4, 6):
            style += [("BACKGROUND", (c, r), (c, r), C(theme.TILE)), ("LINEABOVE", (c, r), (c, r), 2.2, C(theme.NAVY))]
    t.setStyle(TableStyle(style))
    return t


def _cover_kpis(data: BusinessPlanData) -> list:
    span = f"{data.first.label} → {data.last.label}"
    g = narrative.growth_list(data, "revenue_growth_pct")
    dscr_plan = [v for v in (data.v("dscr")[i] for i in data.plan_idx) if v is not None]
    op = _sum_plan(data, "cf_operativo")
    n = len(data.plan_idx)
    periodo = {2: "biennio", 3: "triennio"}.get(n, "piano")
    e0, en = data.v("ebitda")[0], data.v("ebitda")[-1]
    last = data.last.label
    return [
        (span, fmt.compact_range(data.v("ricavi")[0], data.v("ricavi")[-1]), "Ricavi delle vendite",
         f"crescita {g} nel piano" if g else "crescita da ipotesi di piano"),
        (span, f"{fmt.pct(data.v('ebitda_margin')[0])} → {fmt.pct(data.v('ebitda_margin')[-1])}", "EBITDA margin",
         f"EBITDA {fmt.compact_eur(e0)} → {fmt.compact_eur(en)}"),
        (span, f"{fmt.ratio(data.v('dscr')[0])} → {fmt.ratio(data.v('dscr')[-1])}", "DSCR (proxy)",
         f"sempre superiore a {fmt.ratio(min(dscr_plan), 1)}" if dscr_plan else "n.d."),
        (f"{data.plan_columns[0].label} – {last}", fmt.compact_eur(op), "Flussi di cassa operativi",
         f"cumulati sul {periodo} di piano"),
        (span, fmt.compact_range(data.v("pfn")[0], data.v("pfn")[-1]), "Posizione finanziaria netta",
         "debiti finanziari − liquidità"),
        (span, f"{fmt.ratio(data.v('pfn_ebitda')[0])} → {fmt.ratio(data.v('pfn_ebitda')[-1])}", "PFN / EBITDA",
         "rapporto di indebitamento"),
        (last, fmt.compact_eur(data.v("bep")[-1]), "Break even point",
         f"margine di sicurezza {fmt.pct(data.v('margine_sicurezza')[-1])}"),
        (last, fmt.compact_eur(data.v("cc_comm")[-1]), "Capitale circolante commerciale",
         f"DSO {fmt.eur(data.v('dso')[-1])} gg · DIO {fmt.eur(data.v('dio')[-1])} gg · "
         f"DPO {fmt.eur(data.v('dpo')[-1])} gg"),
    ]


def _index_table(data: BusinessPlanData, pages: dict) -> Table:
    num = layout._ps("in", BOLD, 9.8, 12, theme.TEAL)
    tit = layout._ps("it", REGULAR, 9.8, 12, theme.INK)
    pg = layout._ps("ip", REGULAR, 9.8, 12, theme.MUTED, alignment=2)
    rows = []
    for n, title, key in INDEX:
        if key == "partenza":
            title = data.starting_point.title if data.starting_point else "Punto di partenza"
        rows.append([Paragraph(n, num), Paragraph(title, tit), Paragraph(str(pages.get(key, "")), pg)])
    t = Table(rows, colWidths=[22, CW - 22 - 40, 40], rowHeights=19.2)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, C(theme.RULE)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    return t


def copertina(data: BusinessPlanData, pages: dict) -> list:
    return layout.h2("I numeri chiave del piano", after=6) + [_chip_tiles(_cover_kpis(data)), Spacer(0, 14)] + \
        layout.h2("Indice", after=4) + [_index_table(data, pages)]


def _cruscotto(data: BusinessPlanData) -> Table:
    g = lambda label: (label, [], "group")  # noqa: E731
    rows = [g("Conto economico"), row(data, "Ricavi delle vendite", "ricavi"),
            row(data, "Valore della produzione", "valore_produzione"), row(data, "EBITDA", "ebitda"),
            row(data, "EBITDA margin", "ebitda_margin", "hl", "percent"), row(data, "Risultato netto", "utile"),
            g("Cassa e debito"), row(data, "Flusso di cassa operativo", "cf_operativo"),
            row(data, "Disponibilità liquide a fine anno", "cassa_fine"),
            row(data, "Posizione finanziaria netta (PFN)", "pfn"),
            row(data, "PFN / EBITDA", "pfn_ebitda", unit="ratio"), row(data, "DSCR — proxy", "dscr", "hl", "ratio"),
            g("Break-even e circolante"), row(data, "Break even point", "bep"),
            row(data, "Margine di sicurezza", "margine_sicurezza", "hl", "percent"),
            row(data, "Capitale circolante commerciale ¹", "cc_comm", "hl"),
            row(data, "Ciclo di conversione del denaro (gg)", "ciclo", unit="days"),
            g("Patrimonio"), row(data, "Patrimonio netto", "patrimonio_netto"),
            row(data, "Indipendenza finanziaria", "indipendenza", unit="percent")]
    return layout.fin_table(headers(data), rows, first="Indicatore")


def sintesi(data: BusinessPlanData, pages: dict) -> list:
    base = data.first.label
    s = layout.section_head("SEZIONE 1", "Sintesi del piano",
                            f"Il quadro economico, finanziario e patrimoniale del piano in una pagina. "
                            f"{data.base_description}.")
    s += [layout.panel("Punti chiave del piano", narrative.key_points(data)), Spacer(0, 12)]
    s += layout.h2("Cruscotto degli indicatori", after=6) + [_cruscotto(data), Spacer(0, 5),
          layout.note(f"¹ Crediti commerciali + rimanenze − debiti commerciali, calcolato sui saldi dello stato "
                      f"patrimoniale (Sezione 7). Colonna {base}: {data.base_description.lower()}.")]
    return s


def _card(title: str, color: str, fill: str, items: list, width: float) -> Table:
    head = layout._ps("ch", BOLD, 11, 14, color)
    content = [Paragraph(title, head), Spacer(0, 5)]
    if not items:
        content.append(Paragraph("Nessun elemento supera le soglie di valutazione.", layout.ST["cell"]))
    for f in items:
        content += [Paragraph(f.title, layout.ST["cardhead"]), Paragraph(f.text, layout.ST["cell"]), Spacer(0, 5)]
    t = Table([[content]], colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(fill)), ("LINEABOVE", (0, 0), (-1, 0), 2.5, C(color)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def forza(data: BusinessPlanData, pages: dict) -> list:
    plan = data.plan_years
    s = layout.section_head("SEZIONE 1 · SEGUE", "Punti di forza, di debolezza e azioni prioritarie",
                            f"Valutazione di sintesi basata sui dati di {data.first.label} e degli anni di piano "
                            f"{plan[0]}–{plan[-1]}.")
    strengths, weaknesses = narrative.strengths_weaknesses(data)
    w = (CW - 11.4) / 2
    pair = Table([[_card("Punti di forza", theme.TEAL, theme.HL, strengths, w),
                   _card("Punti di debolezza", theme.RED, theme.WEAK, weaknesses, w)]], colWidths=[w, w])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    pair.hAlign = "CENTER"
    s += [pair, Spacer(0, 12)] + layout.h2("Azioni prioritarie", after=6)
    num = layout._ps("an", BOLD, 11, 13, theme.TEAL)
    rows = [[Paragraph("#", layout.ST["cellh"]), Paragraph("Azione", layout.ST["cellh"]),
             Paragraph("Contenuto", layout.ST["cellh"]), Paragraph("Indicatori da monitorare", layout.ST["cellh"])]]
    for i, (title, text, kpi) in enumerate(narrative.actions(data, weaknesses), start=1):
        rows.append([Paragraph(str(i), num), Paragraph(title, layout.ST["cellb"]), Paragraph(text, layout.ST["cell"]),
                     Paragraph(kpi, layout.ST["cell"])])
    t = Table(rows, colWidths=[24, 110, CW - 24 - 110 - 120, 120], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C("#ffffff"), C(theme.PANEL)]),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return s + [t]
```

- [ ] **Step 4: Scrivi `sections_finanza.py`**

```python
"""Sezioni 6–8: sostenibilità del debito, circolante commerciale, solidità e redditività."""
from __future__ import annotations

from reportlab.platypus import Spacer

from . import charts, fmt, layout, narrative
from .data import BusinessPlanData
from .sections_economia import headers, labels, row, tile_from


def _others(data: BusinessPlanData, key: str) -> str:
    y = [f"{fmt.ratio(data.v(key)[i])} nel {data.columns[i].year}" for i in data.plan_idx[:-1]]
    return " · ".join(y) if y else ""


def debito(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 6", "Sostenibilità del debito · DSCR e PFN",
                            "PFN = debiti finanziari meno disponibilità liquide. Il DSCR è calcolato come proxy: "
                            "(EBITDA − imposte) / oneri finanziari, senza la quota capitale.")
    last = data.last.year
    s += [layout.tiles([(fmt.ratio(data.v("dscr")[-1]), f"DSCR {last} (proxy)", _others(data, "dscr")),
                        tile_from(data, "pfn_ebitda", "PFN / EBITDA", fmt.ratio),
                        tile_from(data, "pfn", "PFN", fmt.compact_eur),
                        tile_from(data, "of_mol", "Oneri finanziari / MOL", fmt.pct)]), Spacer(0, 2)]
    # ordine e larghezze del riferimento (pagina 8): prima DSCR e PFN/EBITDA a 429 pt, poi il debito a 399 pt
    s += [layout.chart(charts.dscr_pfn(labels(data), data.v("dscr"), data.v("pfn_ebitda")),
                       charts.HEIGHTS["dscr_pfn"], 429.1), Spacer(0, 4)]
    s += layout.h2("Debiti finanziari, liquidità, PFN e patrimonio netto (€ migliaia)")
    s += [layout.chart(charts.debito(labels(data), data.v("debiti_finanziari"), data.v("liquidita"),
                                     data.v("patrimonio_netto"), data.v("pfn")), charts.HEIGHTS["debito"], 399.1),
          Spacer(0, 6)]
    rows = [row(data, "Debiti verso banche", "banche"), row(data, "di cui entro 12 mesi", "banche_breve"),
            row(data, "di cui oltre 12 mesi", "banche_lungo"),
            row(data, "Debiti finanziari (convenzione PFN)", "debiti_finanziari", "bold"),
            row(data, "Disponibilità liquide", "liquidita"), row(data, "Posizione finanziaria netta (PFN)", "pfn", "hl"),
            row(data, "PFN / EBITDA", "pfn_ebitda", unit="ratio"), row(data, "DSCR — proxy", "dscr", "hl", "ratio"),
            row(data, "Oneri finanziari / MOL", "of_mol", unit="percent"),
            row(data, "Oneri finanziari / ricavi", "of_ricavi", unit="percent"),
            row(data, "ROD (costo del denaro)", "rod", unit="percent")]
    notes = []
    if data.partial_label and data.partial_dscr is not None:
        notes.append(f"DSCR proxy nel progressivo rettificato {data.partial_label}: {fmt.ratio(data.partial_dscr)}.")
    other = data.v("altri_finanziatori")
    if any(v not in (None, 0) for v in other):
        notes.append(f"Debiti verso altri finanziatori: € {fmt.eur(other[-1])} nel {last}, fuori dalla PFN per la "
                     "convenzione del motore degli indici.")
    s += [layout.fin_table(headers(data), rows, first="Indicatore", pad=3.8)]
    if notes:
        s += [Spacer(0, 5), layout.note(" ".join(notes))]
    return s


def circolante(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 7", "Capitale circolante commerciale",
                            "Crediti commerciali, rimanenze e debiti commerciali. I giorni vengono dal motore degli "
                            "indici, su base 360 e sull'intero circolante.")
    s += [layout.tiles([tile_from(data, "cc_comm", "Circolante commerciale", fmt.compact_eur),
                        tile_from(data, "dso", "Giorni di credito (DSO)", lambda v: f"{fmt.eur(v)} gg"),
                        tile_from(data, "dio", "Giorni di magazzino (DIO)", lambda v: f"{fmt.eur(v)} gg"),
                        tile_from(data, "dpo", "Giorni di debito (DPO)", lambda v: f"{fmt.eur(v)} gg")]),
          Spacer(0, 6),
          layout.chart(charts.circolante(labels(data), data.v("dso"), data.v("dio"), data.v("dpo"), data.v("cc_comm")),
                       charts.HEIGHTS["circolante"]), Spacer(0, 6)]
    s += [layout.fin_table(headers(data), [
        row(data, "Crediti commerciali (clienti entro e oltre 12 mesi)", "crediti_comm"),
        row(data, "Rimanenze", "rimanenze"), row(data, "Debiti commerciali (fornitori)", "debiti_comm", sign=-1),
        row(data, "Capitale circolante commerciale", "cc_comm", "hl"),
        row(data, "Giorni di credito · DSO", "dso", unit="days"),
        row(data, "Giorni di magazzino · DIO", "dio", unit="days"),
        row(data, "Giorni di debito · DPO", "dpo", unit="days"),
        row(data, "Ciclo di conversione del denaro", "ciclo", "hl", "days")]), Spacer(0, 8)]
    lettura = narrative.lettura_circolante(data)
    if lettura:
        s.append(layout.panel("Lettura", [("", t) for t in lettura]))
    return s


def solidita(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 8", "Solidità patrimoniale, liquidità e redditività",
                            "Saldi di fine esercizio.")
    s += [layout.tiles([tile_from(data, "patrimonio_netto", "Patrimonio netto", fmt.compact_eur),
                        tile_from(data, "indipendenza", "Indipendenza finanziaria", fmt.pct),
                        tile_from(data, "liquidita_corrente", "Liquidità corrente", fmt.ratio),
                        tile_from(data, "margine_struttura", "Margine di struttura", fmt.compact_eur)]), Spacer(0, 10)]
    s += layout.h2("Stato patrimoniale di sintesi", after=4)
    s += [layout.fin_table(headers(data), [
        row(data, "Immobilizzazioni nette", "immobilizzazioni"), row(data, "Rimanenze", "rimanenze"),
        row(data, "Crediti commerciali", "crediti_comm"), row(data, "Disponibilità liquide", "liquidita"),
        row(data, "Altre attività", "altre_attivita"), row(data, "Totale attivo", "totale_attivo", "hl"),
        row(data, "Patrimonio netto", "patrimonio_netto"),
        row(data, "Debiti finanziari (convenzione PFN)", "debiti_finanziari"),
        row(data, "Altre passività", "altre_passivita"), row(data, "di cui debiti commerciali", "debiti_comm"),
        row(data, "Totale passivo e patrimonio netto", "totale_attivo", "hl")], pad=3.8), Spacer(0, 4),
        layout.note("Le altre passività comprendono debiti commerciali, TFR, debiti tributari e previdenziali, altri "
                    "debiti, debiti verso altri finanziatori e ratei e risconti passivi. Dettaglio nell'Allegato B."),
        Spacer(0, 10)]
    s += layout.h2("Margini strutturali e liquidità", after=6)
    s += [layout.fin_table(headers(data), [
        row(data, "Capitale circolante netto (CCN)", "ccn"), row(data, "Margine di tesoreria", "margine_tesoreria"),
        row(data, "Margine di struttura", "margine_struttura"),
        row(data, "Liquidità corrente", "liquidita_corrente", unit="ratio"),
        row(data, "Liquidità immediata", "liquidita_immediata", unit="ratio"),
        row(data, "Indipendenza finanziaria", "indipendenza", unit="percent"),
        row(data, "Copertura immobilizzazioni", "copertura_immob", unit="percent")], first="Indicatore", pad=3.8), Spacer(0, 10)]
    s += layout.h2("Redditività", after=6)
    s += [layout.fin_table(headers(data), [
        row(data, "ROI", "roi", unit="percent"), row(data, "ROE", "roe", unit="percent"),
        row(data, "ROS (EBIT / ricavi)", "ros", unit="percent"),
        row(data, "EBITDA margin", "ebitda_margin", unit="percent"),
        row(data, "Spread (ROI − ROD)", "spread", "hl", "percent")], first="Indicatore", pad=3.8)]
    return s
```

- [ ] **Step 5: Aggiorna `_register()`**

```python
def _register() -> None:
    from . import sections_economia as eco
    from . import sections_finanza as fin
    from . import sections_sintesi as sin
    SECTIONS.clear()
    SECTIONS.extend([
        SectionSpec("copertina", None, sin.copertina, cover=True),
        SectionSpec("sintesi", "Sintesi del piano", sin.sintesi),
        SectionSpec("forza", None, sin.forza),
        SectionSpec("economia", "Evoluzione economica dell'impresa", eco.economia),
        SectionSpec("costi", "EBITDA margin e struttura dei costi", eco.costi),
        SectionSpec("pareggio", "Costi fissi e variabili · break even point", eco.pareggio),
        SectionSpec("flussi", "Flussi di cassa", eco.flussi),
        SectionSpec("debito", "Sostenibilità del debito · DSCR e PFN", fin.debito),
        SectionSpec("circolante", "Capitale circolante commerciale", fin.circolante),
        SectionSpec("solidita", "Solidità patrimoniale, liquidità e redditività", fin.solidita),
    ])
```

`test_documento_completo` chiede almeno 12 pagine, e dopo questo task il documento ne ha circa 11. Nello Step 6 lancia solo `test_sezione_uno_ambienta`; il test completo diventa verde nel Task 9.

- [ ] **Step 6: Verifica**

Run: `cd backend && $PY -m pytest ../tests/test_bp_document.py::test_sezione_uno_ambienta ../tests/test_bp_banco.py -q`
Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/renderers/business_plan/sections_sintesi.py backend/app/renderers/business_plan/sections_finanza.py \
  backend/app/renderers/business_plan/document.py tests/test_bp_document.py
git diff --cached --stat
git commit -m "feat(report-bp): copertina con indice, sintesi, forza/debolezza, debito, circolante, solidità

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Sezioni 9–10 (punto di partenza, ipotesi)

**Files:**
- Create: `backend/app/renderers/business_plan/sections_partenza.py`
- Modify: `backend/app/renderers/business_plan/document.py` (`_register`)

**Interfaces:**
- Consumes: `StartingPoint`, `TableBlock`, `IndicatorRow`, `AssumptionRow` (Task 2); `narrative.growth_list`.
- Produces: `partenza(data, pages)`, `ipotesi(data, pages)`.

- [ ] **Step 1: Scrivi `sections_partenza.py`**

```python
"""Sezione 9 (punto di partenza, per workflow) e sezione 10 (ipotesi del piano)."""
from __future__ import annotations

from decimal import Decimal

from reportlab.lib.colors import HexColor
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from . import fmt, layout, narrative, theme
from .data import BusinessPlanData
from .theme import CW

C = HexColor


def partenza(data: BusinessPlanData, pages: dict) -> list:
    sp = data.starting_point
    if sp is None:
        return layout.section_head("SEZIONE 9", "Punto di partenza", "Dati di partenza non disponibili.")
    s = layout.section_head("SEZIONE 9", sp.title, sp.intro)
    s += [layout.tiles(list(sp.tiles)), Spacer(0, 12)]
    for block in sp.tables:
        s += layout.h2(block.title, after=6)
        s += [layout.fin_table(list(block.headers), [(label, [fmt.eur(v) for v in vals], style)
                                                     for label, vals, style in block.rows])]
        if block.note:
            s += [Spacer(0, 4), layout.note(block.note)]
        s += [Spacer(0, 10)]
    if sp.indicators:
        s += layout.h2("Indicatori di partenza", after=4)
        if sp.note:
            s += [layout.note(sp.note), Spacer(0, 4)]
        s += [layout.fin_table(list(sp.indicator_headers),
                               [(r.label, [fmt.value(v, r.unit) for v in r.values], "") for r in sp.indicators],
                               first="Indicatore"), Spacer(0, 10)]
    s += layout.h2("Controlli di quadratura", after=4)
    rows = [[Paragraph("Controllo", layout.ST["cellh"]), Paragraph("Esito", layout.ST["cellh"])]] + \
        [[Paragraph(a, layout.ST["cellb"]), Paragraph(b, layout.ST["cell"])] for a, b in sp.checks]
    t = Table(rows, colWidths=[180, CW - 180])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, C(theme.RULE)),
                           ("TOPPADDING", (0, 0), (-1, -1), 4.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.6)]))
    return s + [t]


_AREE = (("Scenario", "Inflazione e ipotesi di scenario generale."),
         ("Fatturato", "Crescita dei ricavi delle vendite e degli altri ricavi."),
         ("Costi", "Incidenza dei costi operativi e ripartizione fissi/variabili."),
         ("Capitale circolante", "Giorni di incasso, giacenza e pagamento del circolante."),
         ("Patrimoniale pregresso", "Debito pregresso, fidi e piano di rimborso già in essere."),
         ("Patrimoniale piano", "Investimenti, nuovo finanziamento, ammortamenti e cassa."),
         ("Imposte", "Aliquota fiscale e acconti."))


def _uniform(vals) -> bool:
    return bool(vals) and all(v is not None and v == vals[0] for v in vals)


def ipotesi(data: BusinessPlanData, pages: dict) -> list:
    years = data.plan_years
    s = layout.section_head("SEZIONE 10", "Assunzioni del piano", "Driver dichiarati per ciascun anno di piano.")
    g = data.growth
    rev = narrative.growth_list(data, "revenue_growth_pct")
    pers = g.get("personnel_growth_pct")
    inv = [sum((x or Decimal(0)) for x in pair) for pair in
           zip(g.get("tangible_investments", (None,) * len(years)), g.get("intangible_investments", (None,) * len(years)))]
    inv_years = [str(y) for y, v in zip(years, inv) if v]
    tax = g.get("tax_rate")
    s += [layout.tiles([
        (rev or fmt.ND, "Crescita ricavi", " / ".join(str(y) for y in years)),
        (fmt.pct_short(pers[0]) if pers and _uniform(pers) else (narrative.growth_list(data, "personnel_growth_pct") or fmt.ND),
         "Crescita costo del personale", "tutti gli anni di piano" if pers and _uniform(pers) else "per anno"),
        (fmt.compact_eur(sum(inv, Decimal(0))), "Investimenti",
         f"nel {' e '.join(inv_years)}" if inv_years else "nessun investimento"),
        (fmt.pct(tax[0]) if tax and _uniform(tax) else fmt.ND, "Aliquota fiscale",
         "tutti gli anni di piano" if tax and _uniform(tax) else "per anno")]), Spacer(0, 12)]
    s += layout.h2("Driver economici e finanziari", after=6)
    s += [layout.fin_table([f"{y} P" for y in years],
                           [(r.label, [fmt.value(v, r.unit) for v in r.values], "") for r in data.assumptions],
                           first="Driver"), Spacer(0, 10)]
    s += layout.h2("Aree del piano", after=6)
    rows = [[Paragraph("Area", layout.ST["cellh"]), Paragraph("Contenuto delle ipotesi", layout.ST["cellh"])]] + \
        [[Paragraph(a, layout.ST["cellb"]), Paragraph(b, layout.ST["cell"])] for a, b in _AREE]
    t = Table(rows, colWidths=[150, CW - 150])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, C(theme.RULE)),
                           ("TOPPADDING", (0, 0), (-1, -1), 4.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.6)]))
    return s + [t]
```

- [ ] **Step 2: Aggiungi a `_register()` dopo `solidita`**

```python
    from . import sections_partenza as par
    SECTIONS.extend([
        SectionSpec("partenza", "Punto di partenza", par.partenza),
        SectionSpec("ipotesi", "Assunzioni del piano", par.ipotesi),
    ])
```
(dentro `_register()`, dopo l'`extend` già esistente).

- [ ] **Step 3: Verifica sui tre workflow**

Run:
```bash
cd /home/peter/DEV/budget-report-bp/backend && $PY - <<'EOF'
import sys, shutil, tempfile; sys.path[:0] = ["..", "."]
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import fitz
tmp = Path(tempfile.mkdtemp()) / "db.sqlite"; shutil.copyfile("/home/peter/DEV/budget/financial_analysis.db", tmp)
db = sessionmaker(bind=create_engine(f"sqlite:///{tmp}"))()
from app.services.final_report_service import assemble_final_report
from app.renderers.business_plan.data import from_report
from app.renderers.business_plan.document import render_business_plan
for c, s in ((575, 18), (21, 16), (628, 24)):
    d = from_report(assemble_final_report(db, c, s, schema_version=2), draft=True)
    pdf = fitz.open(stream=render_business_plan(d), filetype="pdf")
    print(c, s, d.workflow, pdf.page_count)
EOF
```
Expected: tre righe, nessuna eccezione, `page_count` compreso fra 12 e 16.

- [ ] **Step 4: Commit**

```bash
git add backend/app/renderers/business_plan/sections_partenza.py backend/app/renderers/business_plan/document.py
git diff --cached --stat
git commit -m "feat(report-bp): punto di partenza per workflow e assunzioni del piano

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Allegati A–E e documento completo

**Files:**
- Create: `backend/app/renderers/business_plan/sections_allegati.py`
- Modify: `backend/app/renderers/business_plan/document.py` (`_register`, forma finale)

**Interfaces:**
- Consumes: `data.annex`, `data.annex_zero_labels`, `data.indicators_practice(_headers)`, `data.indicators_analytical`.
- Produces: `allegato_a`, `allegato_b`, `allegato_c`, `allegato_d`, `allegato_e`, tutti `(data, pages) -> list`.

- [ ] **Step 1: Scrivi `sections_allegati.py`**

```python
"""Allegati A–E: prospetti completi e indicatori, colonne del report (base + piano)."""
from __future__ import annotations

from reportlab.platypus import PageBreak, Spacer

from . import fmt, layout
from .data import BusinessPlanData
from .sections_economia import headers

_KIND = {"section": "group", "group": "bold", "subtotal": "bold", "total": "hl", "detail": ""}


def _rows(annex_rows) -> list:
    out = []
    for r in annex_rows:
        indent = "&nbsp;" * 3 * max(r.level - 1, 0)
        kind = _KIND.get(r.kind, "")
        if all(v is None for v in r.values):
            kind = "group"  # intestazione di gruppo del prospetto («Rettifiche per elementi non monetari:»)
        cells = [] if kind == "group" else [fmt.eur(v) for v in r.values]
        out.append((indent + r.label, cells, kind))
    return out


def _zero_note(data: BusinessPlanData, key: str) -> list:
    labels = data.annex_zero_labels.get(key, ())
    if not labels:
        return []
    uniq = list(dict.fromkeys(labels))
    return [Spacer(0, 4), layout.note("Voci pari a zero in tutti gli anni: " + "; ".join(uniq).lower() + ".")]


def _statement(data, key, eyebrow, title, sub):
    rows = data.annex.get(key, ())
    s = layout.section_head(eyebrow, title, sub)
    return s + [layout.fin_table(headers(data), _rows(rows), value_size=8.2, pad=2.2, label_size=8)] + _zero_note(data, key)


def allegato_a(data: BusinessPlanData, pages: dict) -> list:
    return _statement(data, "income_statement", "ALLEGATO A", "Conto economico completo",
                      "Valori in euro · schema civilistico · voci a zero in tutti gli anni raggruppate in nota.")


def allegato_b(data: BusinessPlanData, pages: dict) -> list:
    rows = list(data.annex.get("balance_sheet", ()))
    split = next((i for i, r in enumerate(rows) if r.label.upper().startswith("PASSIVO")), len(rows))
    s = layout.section_head("ALLEGATO B", "Stato patrimoniale completo",
                            "Valori in euro · saldi di fine esercizio · voci a zero in tutti gli anni raggruppate.")
    s += [layout.fin_table(headers(data), _rows(rows[:split]), value_size=8.2, pad=2.2, label_size=8)]
    if split < len(rows):
        s += [PageBreak()] + layout.section_head("ALLEGATO B", "Stato patrimoniale completo (segue)",
                                                 "Passivo e patrimonio netto · valori in euro.")
        s += [layout.fin_table(headers(data), _rows(rows[split:]), value_size=8.2, pad=2.2, label_size=8)]
    return s + _zero_note(data, "balance_sheet")


def allegato_c(data: BusinessPlanData, pages: dict) -> list:
    return _statement(data, "cashflow", "ALLEGATO C", "Rendiconto finanziario completo — metodo indiretto",
                      "Valori in euro.")


def allegato_d(data: BusinessPlanData, pages: dict) -> list:
    sub = f"R = progressivo rettificato {data.partial_label[:-2]}." if data.partial_label else "Indicatori della pratica."
    s = layout.section_head("ALLEGATO D", "Indicatori di sintesi", sub)
    rows = [(r.label, [fmt.value(v, r.unit) for v in r.values], "") for r in data.indicators_practice]
    return s + [layout.fin_table(list(data.indicators_practice_headers), rows, first="Indicatore")]


def allegato_e(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("ALLEGATO E", "Indici analitici",
                            "Quadro completo degli indici. ROE, ROI, ROS ed EBITDA margin sono nell'Allegato D.")
    rows = [(r.label, [fmt.value(v, r.unit) for v in r.values], "") for r in data.indicators_analytical]
    return s + [layout.fin_table(headers(data), rows, first="Indicatore"), Spacer(0, 5),
                layout.note("Lo Z-Score di Altman, il rating FGPMI e l'EMScore sono disponibili per ogni anno di piano "
                            "nel modello previsionale e non sono riportati in questo prospetto.")]
```

- [ ] **Step 2: Forma finale di `_register()`**

```python
def _register() -> None:
    from . import sections_allegati as ann
    from . import sections_economia as eco
    from . import sections_finanza as fin
    from . import sections_partenza as par
    from . import sections_sintesi as sin
    SECTIONS.clear()
    SECTIONS.extend([
        SectionSpec("copertina", None, sin.copertina, cover=True),
        SectionSpec("sintesi", "Sintesi del piano", sin.sintesi),
        SectionSpec("forza", None, sin.forza),
        SectionSpec("economia", "Evoluzione economica dell'impresa", eco.economia),
        SectionSpec("costi", "EBITDA margin e struttura dei costi", eco.costi),
        SectionSpec("pareggio", "Costi fissi e variabili · break even point", eco.pareggio),
        SectionSpec("flussi", "Flussi di cassa", eco.flussi),
        SectionSpec("debito", "Sostenibilità del debito · DSCR e PFN", fin.debito),
        SectionSpec("circolante", "Capitale circolante commerciale", fin.circolante),
        SectionSpec("solidita", "Solidità patrimoniale, liquidità e redditività", fin.solidita),
        SectionSpec("partenza", "Punto di partenza", par.partenza),
        SectionSpec("ipotesi", "Assunzioni del piano", par.ipotesi),
        SectionSpec("allegato_a", "Allegati A–E", ann.allegato_a),
        SectionSpec("allegato_b", None, ann.allegato_b),
        SectionSpec("allegato_c", None, ann.allegato_c),
        SectionSpec("allegato_d", None, ann.allegato_d),
        SectionSpec("allegato_e", None, ann.allegato_e),
    ])


_register()
```

- [ ] **Step 3: Aggiungi all'`__init__.py` gli export**

```python
"""Report Business plan: ReportLab + matplotlib, accanto al dossier Typst."""
from .data import BusinessPlanData, from_report  # noqa: F401
from .document import render_business_plan  # noqa: F401
```

- [ ] **Step 4: Verifica la suite del renderer**

Run: `cd backend && $PY -m pytest ../tests/test_bp_fmt.py ../tests/test_bp_data.py ../tests/test_bp_charts.py ../tests/test_bp_layout.py ../tests/test_bp_banco.py ../tests/test_bp_narrative.py ../tests/test_bp_document.py -q`
Expected: tutto verde. Su AMBIENTA le pagine sono 17–19. Se `test_documento_completo` fallisce sull'indice («titolo non nella pagina»), la causa è quasi sempre un `SectionStart` registrato prima di un `PageBreak` che si è spostato: controlla che in `_build` il `SectionStart` segua il `PageBreak`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/renderers/business_plan tests
git diff --cached --stat
git commit -m "feat(report-bp): Allegati A-E e documento completo su tre workflow

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Servizio e rotta `POST …/business-plan/pdf`

**Files:**
- Create: `backend/app/schemas/business_plan.py`, `backend/app/services/business_plan_pdf_service.py`
- Modify: `backend/app/api/v1/reports.py`
- Test: `tests/test_bp_endpoint.py`

**Interfaces:**
- Consumes: `assemble_final_report`, `FinalNotReady` (da `final_report_pdf_service`), `from_report`, `render_business_plan`.
- Produces: `BusinessPlanPdfRequest(document_state: Literal["draft","final"] = "draft")`; `business_plan_pdf_service.render(db, company_id, scenario_id, *, document_state) -> BusinessPlanPdf(data: bytes, filename: str, ascii_filename: str, etag: str)`; `filenames(company_name, years) -> tuple[str, str]`; la rotta `POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/business-plan/pdf`.

- [ ] **Step 1: Scrivi il test**

`tests/test_bp_endpoint.py`:
```python
"""Rotta del Business plan: ownership, final solo se ready, render reale sul fixture minimo, nessuna AI."""
from types import SimpleNamespace

import pytest

from app.services import business_plan_pdf_service as bp_service
from tests.test_final_report_endpoint import client, _url  # noqa: F401  fixture condivisa


def _bp(client, scenario=None):  # noqa: F811
    sid = scenario if scenario is not None else client.ids["scenario"]
    return f"/api/v1/companies/{client.ids['company']}/scenarios/{sid}/business-plan/pdf"


def test_render_reale_sul_fixture_minimo(client, monkeypatch):  # noqa: F811
    from app.services import ai_comments_service

    monkeypatch.setattr(ai_comments_service, "generate_final_report_narrative",
                        lambda *a, **k: pytest.fail("il Business plan non chiama l'AI"))
    response = client.post(_bp(client), json={"document_state": "draft"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "attachment;" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"


def test_scenario_altrui_404(client):  # noqa: F811
    assert client.post(_bp(client, client.ids["foreign"]), json={}).status_code == 404


def test_final_richiede_ready(client, monkeypatch):  # noqa: F811
    report = SimpleNamespace(readiness=SimpleNamespace(status="draft"))
    monkeypatch.setattr(bp_service, "assemble_final_report", lambda *a, **k: report)
    response = client.post(_bp(client), json={"document_state": "final"})
    assert response.status_code == 409


def test_contratto_richiesta_stretto(client):  # noqa: F811
    assert client.post(_bp(client), json={"document_state": "final", "grayscale": True}).status_code == 422


def test_nome_file_ascii():
    full, ascii_name = bp_service.filenames("Società Ünicode Ltd — ČR", [2027, 2029])
    assert full == "Business plan Società Ünicode Ltd — ČR 2027-2029.pdf"
    assert ascii_name.isascii() and ascii_name.endswith(".pdf")
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd backend && $PY -m pytest ../tests/test_bp_endpoint.py -q`
Expected: FAIL, `ImportError: cannot import name 'business_plan_pdf_service'`

- [ ] **Step 3: Scrivi schema e servizio**

`backend/app/schemas/business_plan.py`:
```python
"""Corpo di richiesta del PDF Business plan: bozza marcata o documento finale, nient'altro."""
from typing import Literal

from app.schemas.final_report import ContractModel


class BusinessPlanPdfRequest(ContractModel):
    document_state: Literal["draft", "final"] = "draft"
```

`backend/app/services/business_plan_pdf_service.py`:
```python
"""Business plan PDF: assemble → gate → from_report → render. Solo letture: niente AI, niente DB writes."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from app.renderers.business_plan import from_report, render_business_plan
from app.services.final_report_pdf_service import FinalNotReady
from app.services.final_report_service import assemble_final_report


@dataclass(frozen=True)
class BusinessPlanPdf:
    data: bytes
    filename: str
    ascii_filename: str
    etag: str


def filenames(company_name: str, years: list) -> tuple:
    span = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])
    full = f"Business plan {company_name} {span}.pdf"
    ascii_name = unicodedata.normalize("NFKD", full).encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9 ._-]+", "", ascii_name)
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip() or "Business plan.pdf"
    return full, ascii_name


def render(db, company_id: int, scenario_id: int, *, document_state: str = "draft") -> BusinessPlanPdf:
    report = assemble_final_report(db, company_id, scenario_id, schema_version=2)
    if document_state == "final" and report.readiness.status != "ready":
        raise FinalNotReady("Il documento finale richiede una pratica pronta: scarica la bozza.")
    data = from_report(report, draft=document_state != "final")
    pdf = render_business_plan(data)
    full, ascii_name = filenames(data.company_name, data.plan_years)
    return BusinessPlanPdf(pdf, full, ascii_name, hashlib.sha256(pdf).hexdigest()[:32])
```

Controlla che `FinalNotReady(...)` accetti un messaggio. Leggi `class FinalNotReady(ValueError)` in `final_report_pdf_service.py`: se ha un `__init__` suo con altri argomenti, adeguati alla sua firma.

- [ ] **Step 4: Aggiungi la rotta in `reports.py`**

In cima, accanto agli altri import:
```python
from app.schemas.business_plan import BusinessPlanPdfRequest
from app.services import business_plan_pdf_service
```
Dopo `download_final_report_pdf`:
```python
@router.post(
    "/companies/{company_id}/scenarios/{scenario_id}/business-plan/pdf",
    response_class=Response,
    summary="Download the Business plan report as PDF",
    responses={
        404: {"description": "Azienda o scenario non di questo utente"},
        409: {"description": "«final» su una pratica non pronta, o catena infrannuale incoerente"},
    },
)
def download_business_plan_pdf(
    company_id: int,
    scenario_id: int,
    request: BusinessPlanPdfRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> Response:
    """Il Business plan (ReportLab): nessuna AI, nessun forecast, nessuna scrittura."""
    validate_scenario_belongs_to_company(scenario_id, company_id, user_id, db)
    try:
        result = business_plan_pdf_service.render(db, company_id, scenario_id, document_state=request.document_state)
    except FinalReportNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from None
    except (FinalReportChainConflict, FinalReportPeriodUnavailable, FinalNotReady) as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from None
    headers = {
        "Content-Disposition": (f'attachment; filename="{result.ascii_filename}"; '
                                f"filename*=UTF-8''{quote(result.filename, safe='', encoding='utf-8')}"),
        "ETag": f'"{result.etag}"',
        "Cache-Control": "no-store",
    }
    return Response(content=result.data, media_type="application/pdf", headers=headers)
```

- [ ] **Step 5: Verifica che passi, e che il dossier non si sia rotto**

Run: `cd backend && $PY -m pytest ../tests/test_bp_endpoint.py ../tests/test_final_report_pdf_endpoint.py -q`
Expected: `test_bp_endpoint` 5 passed; `test_final_report_pdf_endpoint` invariato rispetto a prima (31 passed, 1 skipped).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/business_plan.py backend/app/services/business_plan_pdf_service.py \
  backend/app/api/v1/reports.py tests/test_bp_endpoint.py
git diff --cached --stat
git commit -m "feat(report-bp): rotta POST business-plan/pdf, final solo su pratica pronta

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Selettore su `/report`

**Files:**
- Modify: `frontend/lib/final-report-download.ts`, `frontend/lib/api.ts`, `frontend/hooks/use-final-report-download.ts`, `frontend/app/report/page.tsx`
- Test: `frontend/lib/api.test.ts`, `frontend/lib/final-report-download.test.ts` (crealo se non esiste)

**Interfaces:**
- Produces: `export type ReportModel = "dossier" | "business_plan"`, `export const REPORT_MODELS: { value: ReportModel; label: string }[]`, `export function reportPdfPath(model: ReportModel): string` in `lib/final-report-download.ts`; `downloadFinalReportPdf(companyId, scenarioId, { documentState, grayscale?, model? })`; gli hook `download`, `preview` e `loadInline` accettano un quarto parametro `model: ReportModel = "dossier"`.

- [ ] **Step 1: Installa le dipendenze del worktree, se mancano**

Run: `cd /home/peter/DEV/budget-report-bp/frontend && [ -d node_modules ] || npm ci`

- [ ] **Step 2: Scrivi i test**

In `frontend/lib/api.test.ts`, nel `describe` di `downloadFinalReportPdf`, aggiungi:
```ts
  it("con model business_plan chiama la rotta del Business plan e manda solo document_state", async () => {
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    fetchMock.mockResolvedValue({ ok: true, status: 200, headers: { get: () => null }, blob: async () => blob, json: async () => ({}) });
    await downloadFinalReportPdf(1, 2, { documentState: "draft", model: "business_plan" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/companies/1/scenarios/2/business-plan/pdf");
    expect(JSON.parse(init.body)).toEqual({ document_state: "draft" });
  });
```
In `frontend/lib/final-report-download.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { REPORT_MODELS, reportPdfPath } from "./final-report-download";

describe("modelli di report", () => {
  it("il Business plan è il primo, ed è il default", () => {
    expect(REPORT_MODELS.map((m) => m.value)).toEqual(["business_plan", "dossier"]);
  });
  it("ogni modello ha la sua rotta", () => {
    expect(reportPdfPath("dossier")).toBe("final-report/pdf");
    expect(reportPdfPath("business_plan")).toBe("business-plan/pdf");
  });
});
```

- [ ] **Step 3: Verifica che falliscano**

Run: `cd frontend && npx vitest run lib/api.test.ts lib/final-report-download.test.ts`
Expected: FAIL, `reportPdfPath is not a function` e l'URL che contiene ancora `final-report/pdf`.

- [ ] **Step 4: Implementa**

`frontend/lib/final-report-download.ts`, in fondo:
```ts
/** Quale PDF si stampa da /report: il Business plan (ReportLab) o il dossier (Typst). */
export type ReportModel = "dossier" | "business_plan";

export const REPORT_MODELS: { value: ReportModel; label: string }[] = [
  { value: "business_plan", label: "Business plan" },
  { value: "dossier", label: "Dossier" },
];

export function reportPdfPath(model: ReportModel): string {
  return model === "business_plan" ? "business-plan/pdf" : "final-report/pdf";
}
```
`frontend/lib/api.ts`: importa `reportPdfPath` e `type ReportModel` da `@/lib/final-report-download` (un modulo `lib/` può importare da `lib/`), poi in `downloadFinalReportPdf`:
```ts
  options: { documentState: FinalReportDocumentState; grayscale?: boolean; model?: ReportModel },
): Promise<DownloadFinalReportPdfResult> => {
  const model = options.model ?? "dossier";
  const body = model === "business_plan"
    ? { document_state: options.documentState }
    : { document_state: options.documentState, grayscale: options.grayscale ?? false };
  const response = await fetch(
    `${API_BASE_URL}/companies/${companyId}/scenarios/${scenarioId}/${reportPdfPath(model)}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(_authToken ? { Authorization: `Bearer ${_authToken}` } : {}),
      },
      body: JSON.stringify(body),
    },
  );
```
Se `lib/final-report-download.ts` importa già da `lib/api.ts` (e si creerebbe un ciclo), sposta `ReportModel`, `REPORT_MODELS` e `reportPdfPath` in un modulo nuovo `frontend/lib/report-model.ts` e importali da lì in entrambi. Il test del passo 2 va allora su `./report-model`.

`frontend/hooks/use-final-report-download.ts`: nelle tre callback aggiungi un quarto parametro `model: ReportModel = "dossier"` e passalo: `downloadFinalReportPdf(companyId, scenarioId, { documentState, model })`. Nel `Riprova` del toast inoltra anche `model`.

`frontend/app/report/page.tsx`:
- stato: `const [reportModel, setReportModel] = useState<ReportModel>("business_plan");`
- un `select` con `id="report-model"` accanto a quello dello scenario, con le opzioni `REPORT_MODELS`;
- i due bottoni «Prepara Report AI» e «Rigenera tutto» si rendono solo quando `reportModel === "dossier"`;
- `previewKey` diventa:
```ts
  const previewKey = selectedCompanyId && scenarioId && (reportModel === "business_plan" ? model : plan)
    ? `${reportModel}:${selectedCompanyId}:${scenarioId}:${reportModel === "business_plan" ? model?.model_hash : plan?.plan_hash}:${pdfState}`
    : null;
```
- l'effetto passa `reportModel` a `loadInlinePreview(selectedCompanyId, scenarioId, pdfState, reportModel)` e lo aggiunge alle dipendenze;
- `downloadPdf`, `previewPdf` e «Aggiorna anteprima» passano `reportModel`;
- l'indice laterale `pdfOutline` si mostra solo per il dossier (il piano editoriale descrive le pagine del dossier, non quelle del Business plan): `const pdfOutline = useMemo(() => reportModel === "dossier" ? buildPdfOutline(plan?.pages ?? []) : [], [plan, reportModel]);`
- nel `PageHeader`, `title={reportModel === "business_plan" ? "Business plan" : "Dossier finale"}`.

- [ ] **Step 5: Verifica**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: tutto verde, nessun errore di tipo.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib frontend/hooks/use-final-report-download.ts frontend/app/report/page.tsx
git diff --cached --stat
git commit -m "feat(report-bp): selettore Business plan | Dossier su /report, Business plan di default

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Banco visivo su AMBIENTA, documentazione, verifica finale

**Files:**
- Create: `tools/business_plan/confronta.py`, `docs/budget/BUSINESS-PLAN-PDF.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Scrivi lo strumento di confronto**

`tools/business_plan/confronta.py`:
```python
"""PNG affiancati riferimento | Business plan di AMBIENTA dal DB locale, per la verifica con la vision.

Uso: python tools/business_plan/confronta.py [--db PATH] [--company 575 --scenario 18]
Scrive in tests/.banco-business-plan/confronto/ (gitignored). Legge una COPIA del DB.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

import fitz  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def _png(page, dpi=90) -> Image.Image:
    px = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (px.width, px.height), px.samples)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/home/peter/DEV/budget/financial_analysis.db")
    ap.add_argument("--company", type=int, default=575)
    ap.add_argument("--scenario", type=int, default=18)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp()) / "db.sqlite"
    shutil.copyfile(args.db, tmp)
    db = sessionmaker(bind=create_engine(f"sqlite:///{tmp}"))()
    from app.renderers.business_plan import from_report, render_business_plan
    from app.services.final_report_service import assemble_final_report
    data = from_report(assemble_final_report(db, args.company, args.scenario, schema_version=2), draft=False)
    pdf_bytes = render_business_plan(data)
    out = ROOT / "tests/.banco-business-plan/confronto"
    out.mkdir(parents=True, exist_ok=True)
    (out / "business-plan.pdf").write_bytes(pdf_bytes)
    new = fitz.open(stream=pdf_bytes, filetype="pdf")
    ref_path = ROOT / "tests/.banco-business-plan/riferimento.pdf"
    ref = fitz.open(ref_path) if ref_path.is_file() else None
    for i in range(new.page_count):
        b = _png(new[i])
        if ref is not None and i < ref.page_count:
            a = _png(ref[i])
            m = Image.new("RGB", (a.width + b.width + 16, max(a.height, b.height)), "#888")
            m.paste(a, (0, 0))
            m.paste(b, (a.width + 16, 0))
        else:
            m = b
        m.save(out / f"p{i + 1:02d}.png")
    print(f"{new.page_count} pagine in {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Genera e guarda le pagine**

Run: `cd /home/peter/DEV/budget-report-bp && $PY tools/business_plan/confronta.py`
Expected: `N pagine in …/confronto` con N fra 17 e 19.

Apri con il tool Read **tutte** le pagine `p01.png … pNN.png`, una alla volta. Per ciascuna verifica, rispetto al riferimento a sinistra:
- stessa gerarchia (occhiello, titolo, sottotitolo, riquadri, grafico, tabella);
- nessun testo tagliato o sovrapposto, nessuna tabella che esce dal margine;
- grafici leggibili, con etichette che non si toccano;
- nessun `n.d.` dove AMBIENTA ha il dato. Se c'è, è un difetto di mappa in `data.py`, non di stampa.

Correggi ciò che vedi, rigenera e ricontrolla solo le pagine toccate. I numeri **devono** differire dal riferimento: su AMBIENTA il DB dà ricavi 2029 di 4.619.623, non 4.673.885. Una differenza di numeri non è un difetto; una differenza di layout sì.

- [ ] **Step 3: Scrivi la documentazione**

`docs/budget/BUSINESS-PLAN-PDF.md`:
```markdown
# Report Business plan (PDF)

Secondo report PDF della pratica, accanto al dossier Typst. Riproduce il layout del business plan preparato dal
committente (`BUSINESS PLAN RIVISITATO.pdf`, fuori da git) con i numeri del motore.

**Dove sta:** `backend/app/renderers/business_plan/` (ReportLab + matplotlib), servizio
`services/business_plan_pdf_service.py`, rotta `POST /companies/{id}/scenarios/{sid}/business-plan/pdf`
(`{"document_state": "draft"|"final"}`), selettore «Modello» su `/report`.

**Da dove vengono i numeri:** solo da `FinalReportModelV2`, via `data.from_report`. Il report somma e sottrae righe
già presenti (costi operativi = costi della produzione − ammortamenti; debiti finanziari = PFN + liquidità) e non
ricalcola indicatori. DSCR proxy = (EBITDA − imposte) / oneri finanziari.

**Testi:** `narrative.py`, regole deterministiche con soglie in `SOGLIE`. Nessun LLM. Per cambiare una frase si
cambia una regola o una soglia, e il test `tests/test_bp_narrative.py` ne fissa il comportamento su AMBIENTA.

**Banco di prova:**
- `tests/test_bp_banco.py` confronta riquadro per riquadro le sezioni 2, 4 e 5 (numeri del committente, in
  `tests/fixtures/business_plan/banco_ambienta.json`) con le pagine 4, 6 e 7 del suo PDF. Tolleranze: 8 pt su y0,
  3 pt sull'altezza, 2 pt su x. Si allarga uno spazio, mai una tolleranza.
- `tools/business_plan/confronta.py` affianca tutte le pagine di AMBIENTA al riferimento, per la verifica con la vision.
- Il PDF del committente va copiato in `tests/.banco-business-plan/riferimento.pdf` (gitignored); senza, il banco si salta.

**Trappole:**
- matplotlib solo con `Figure` e `FigureCanvasAgg`, mai `pyplot`, e nessuna modifica di `rcParams`: FastAPI esegue la
  rotta in un threadpool.
- L'indice della copertina nasce da due passate di `doc.build`: la copertina deve avere altezza fissa, o la seconda
  passata sposta le pagine (lo verifica un `assert` in `render_business_plan`).
- Un valore assente è `None` fino alla stampa (`n.d.`), mai zero.
```

In `CLAUDE.md`, sezione «Frontend pages», sostituisci la voce di `/report` con:
```
`/report` (selettore «Modello»: **Business plan** — ReportLab, default — oppure il dossier Typst; → [docs/budget/BUSINESS-PLAN-PDF.md](docs/budget/BUSINESS-PLAN-PDF.md))
```
e nella «Mappa della documentazione» aggiungi la riga:
```
| Il PDF Business plan esce diverso dal riferimento del committente, o un testo non torna? | [docs/budget/BUSINESS-PLAN-PDF.md](docs/budget/BUSINESS-PLAN-PDF.md) |
```

- [ ] **Step 4: Verifica finale**

Run:
```bash
cd /home/peter/DEV/budget-report-bp/backend && $PY -m pytest ../tests/test_bp_*.py ../tests/test_final_report_pdf_endpoint.py ../tests/test_final_report_endpoint.py -q
cd ../frontend && npx vitest run && npx tsc --noEmit
```
Expected: tutto verde. Riporta i numeri esatti (passed/skipped) nel messaggio di consegna.

- [ ] **Step 5: Commit**

```bash
git add tools/business_plan docs/budget/BUSINESS-PLAN-PDF.md CLAUDE.md backend/app/renderers/business_plan
git diff --cached --stat
git commit -m "docs(report-bp): banco visivo su AMBIENTA e documentazione del Business plan

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
