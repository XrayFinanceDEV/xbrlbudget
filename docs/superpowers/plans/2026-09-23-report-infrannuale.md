# Report infrannuale (ReportLab) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (scelto dal proprietario: esecuzione
> inline in questa sessione, revisione indipendente dell'intero branch alla fine). Steps use checkbox (`- [ ]`) syntax.

**Goal:** un PDF infrannuale che riproduca `INFRANNUALE RIVISITATO.pdf` (13 pagine) con i numeri del motore, e che
la tab Stampa scarichi al posto del report intermedio Typst.

**Architecture:** `IntermediateReportModel` (`assemble_intermedio`) → `infrannuale/data.from_intermedio` →
`InfrannualeData` (valori già allineati alle colonne C, 6M, Ann., F) → sezioni ReportLab + grafici matplotlib + testi a
regole → `infrannuale/document.render_infrannuale` → rotta `POST …/infrannuale/pdf`. Il renderer non vede il modello:
legge solo `InfrannualeData`, quindi il banco gli può dare i numeri del committente.

**Tech Stack:** Python 3.12, ReportLab 4.2.5, matplotlib 3.9.3 (solo `Figure`), PyMuPDF (test), FastAPI, Next.js 15.

**Spec:** `docs/superpowers/specs/2026-09-23-report-infrannuale-design.md`

**Spike che fa da banco:** `tools/infrannuale/spike_inf.py` (committato nel Task 1 come riferimento di resa). Le
pagine 4, 6 e 9 stanno a 0,2 pt dal riferimento con queste misure:
- grafici larghi 459 pt, centrati; la crisi a 439,1 pt;
- riquadri KPI col bollino teal alto 13,5 pt: padding 6 in alto, 4,9 in basso, 5,5 ai lati;
- tabelle con `pad=3.55`, intestazione a 4,0 pt, valori a 9,8 pt ed etichette a 8,0 pt;
- 5 pt fra riquadri e grafico, 0 fra grafico e tabella, 5 fra tabella e nota, 4,6 fra nota e pannello.

## Global Constraints

- Worktree `/home/peter/DEV/budget-report-inf`, branch `feat/report-infrannuale`. Mai lavorare nell'albero
  principale `/home/peter/DEV/budget`.
- `PY=/home/peter/DEV/budget/backend/venv/bin/python`; test da `backend/`: `$PY -m pytest ../tests/<file> -q`.
- I test che leggono il DB lo copiano (`/home/peter/DEV/budget/financial_analysis.db`) in una cartella temporanea e si
  saltano se non c'è. Nessuna scrittura sul DB, nessuna chiamata AI dal PDF.
- `Decimal` fino al disegno; percentuali assolute (5 = 5%).
- Il pacchetto `business_plan` si **estende**, non si modifica: dopo ogni task che lo tocca,
  `test_bp_*.py` deve restare verde (banco del Business plan compreso).
- Valore assente ⇒ `n.d.`; mai zero inventato; nessuna barra per un valore assente.
- Ogni commit termina con `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`; prima di ogni
  commit `git diff --cached --stat` (fine riga misti in `reports.py`/`api.ts`: modifiche solo additive).

## Review Focus

1. **Pratica senza proiezione** (AIC scenario 3): niente colonne F, nessuna eccezione, la copertina lo dichiara.
   Test in Task 2 e Task 6.
2. **Periodo di 12 mesi o di 3 mesi**: niente colonna Ann. a 12 mesi; «3M» nelle etichette e nella legenda. Test in
   Task 2 (fixture sintetica).
3. **Indicatori assenti o infiniti** (`crisi` senza proiezione, oneri zero ⇒ DSCR non calcolabile): `n.d.` e nessun
   esito colorato. Test in Task 2 e Task 3.
4. **Valori negativi** (fornitori nel grafico del circolante, margini negativi): asse con lo zero, etichette sotto la
   barra, segno `−` in tabella. Test in Task 3.
5. **Render concorrenti**: nessuno stato globale. Il test di concorrenza sta nel Task 3.

---

## File Structure

```
backend/app/renderers/business_plan/layout.py     + tiles_chip() (primitiva nuova, accanto a tiles)
backend/app/renderers/infrannuale/
  __init__.py        re-export: render_infrannuale, from_intermedio, InfrannualeData
  data.py            InfrannualeData, Col, from_intermedio(model), load_json/dump_json del banco
  charts.py          ricavi_periodi, risultati, stato_patrimoniale, circolante, debito, crisi
  narrative.py       ESITO/soglie, classe_colore, key_points, strengths_weaknesses, actions, letture
  sections.py        sezioni 2–8 (economia, costi, patrimonio, circolante, debito, crisi, segnali)
  sections_sintesi.py copertina con indice, sintesi, forza/debolezza/azioni
  sections_allegati.py Allegati A–B
  document.py        catalogo delle sezioni, due passate per l'indice, intestazione e piè
backend/app/schemas/infrannuale_pdf.py             InfrannualePdfRequest (vuoto, extra=forbid)
backend/app/services/infrannuale_pdf_service.py    render(db, scenario) -> InfrannualePdf
backend/app/api/v1/intermedio_report.py            + rotta POST …/infrannuale/pdf
tests/test_inf_data.py, test_inf_charts.py, test_inf_narrative.py, test_inf_banco.py, test_inf_document.py,
tests/test_inf_endpoint.py, tests/fixtures/infrannuale/banco_ambienta.json
tools/infrannuale/spike_inf.py, tools/infrannuale/confronta.py
frontend/lib/api.ts (downloadInfrannualePdf), hooks/use-intermedio-download.ts, components/pratica/StampaContent.tsx
docs/budget/REPORT-INFRANNUALE-PDF.md, CLAUDE.md
```

---

### Task 1: Primitiva `tiles_chip` e spike di riferimento

**Files:** Modify `backend/app/renderers/business_plan/layout.py`; Create `tools/infrannuale/spike_inf.py` (copia dello
spike); Test `tests/test_inf_primitives.py`.

**Interfaces — Produces:** `layout.tiles_chip(items: list[tuple[str, str, str, str]], value_style: str = "kv") -> Table`
(chip, valore, etichetta, confronto); `layout.ST["chip"]`, `layout.ST["kv13"]`.

- [ ] Step 1: test
```python
from reportlab.platypus import SimpleDocTemplate
import io, fitz
from app.renderers.business_plan import layout, theme


def test_tiles_chip_misure_del_riferimento():
    theme.register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, leftMargin=theme.LM, rightMargin=theme.LM, topMargin=128, bottomMargin=40)
    doc.build([layout.tiles_chip([("6M 2026", "€ 2,10 mln", "Ricavi del semestre", "EBITDA € 82,2 mila")] * 4)])
    p = fitz.open(stream=buf.getvalue(), filetype="pdf")[0]
    fills = sorted((d["rect"] for d in p.get_drawings() if d.get("fill")), key=lambda r: (r.y0, r.x0))
    tiles = [r for r in fills if abs(r.width - 118.3) < 1]
    chips = [r for r in fills if abs(r.height - 13.5) < 0.3]
    assert len(tiles) == 4 and len(chips) == 4
    assert abs(tiles[0].height - 65.8) < 0.6          # 128,0–193,8 nel riferimento
    assert abs(chips[0].y0 - tiles[0].y0 - 6.0) < 0.5  # bollino a 6 pt dal bordo
```
- [ ] Step 2: FAIL (`AttributeError: tiles_chip`). Step 3: implementa copiando `tiles_chip` dallo spike. Step 4: PASS,
  più `test_bp_*.py` verdi. Step 5: commit `feat(report-inf): riquadro KPI col bollino e spike di riferimento`.

---

### Task 2: `InfrannualeData` e `from_intermedio`

**Files:** Create `backend/app/renderers/infrannuale/__init__.py`, `data.py`; Test `tests/test_inf_data.py`.

**Interfaces — Produces:**
- `Col(key: str, label: str, kind: Literal["C","6M","Ann","F"])`.
- `InfrannualeData`, con i campi:
  - `company_name`, `period_months`, `reference_year`, `partial_year`, `period_end: str` («30.06.2026»);
  - `ce_cols: tuple[Col]` (C, 6M, Ann?, F?) e `sp_cols: tuple[Col]` (C, 6M, F?);
  - `values: dict[str, dict[str, Decimal|None]]`, chiave → colonna → valore;
  - `crisi: dict[str, CrisiCol]` per colonna, con `CrisiCol(codice, etichetta, oltre, segnali, indicatori: dict,
    punteggi: dict)`;
  - `definizioni: tuple[(chiave, etichetta, formato, nel_punteggio)]`, `segnali: tuple[(chiave, etichetta, attivo)]`;
  - `annex_ce`, `annex_sp: tuple[AnnexRow]`, con `AnnexRow(label, level, kind, values: tuple)`;
  - `has_forecast: bool`, `has_annualized: bool`.
- Metodi: `v(key, col) -> Decimal|None`, `var(key, col, base="storico") -> Decimal|None` (percentuale).
  Proprietà: `legend: str`, `header_title: str`.
- `from_intermedio(model) -> InfrannualeData`; `load_json(path)`, `dump_json(data) -> dict`.

**Mappa delle chiavi** (`values`), tutte dal modello, nessun indicatore ricalcolato:

| chiave | fonte |
|---|---|
| ricavi, valore_produzione, costi_operativi, ebitda, ammortamenti, ebit, risultato_ante_imposte, risultato_netto | `CeAggregati` omonimi |
| oneri_finanziari | − `CeAggregati.oneri_finanziari` (in tabella col segno, come il riferimento) |
| imposte | − `CeAggregati.imposte` |
| ebitda_margin | `crisi[col].indicatori["ebitda_margin"]`; per `annualizzato` = quello dell'`infrannuale` |
| altri_proventi_fin | prospetto CE `ce14_altri_proventi_finanziari` |
| materie, servizi, godimento, personale, var_rim_materie, oneri_diversi | `ce05_materie_prime`, `ce06_servizi`, `ce07_godimento_beni`, `ce08_costi_personale`, `ce10_var_rimanenze_mat_prime`, `ce12_oneri_diversi` |
| totale_costi_produzione | `production_cost` |
| immobilizzazioni, attivo_circolante, totale_attivo, patrimonio_netto, debiti_finanziari, debiti_operativi, liquidita, ccn_sp | `SpAggregati` (`cassa` → liquidita, `ccn` → ccn_sp) |
| ratei_attivi | `sp10_ratei_risconti_attivi` |
| crediti_clienti | `sp06a_crediti_clienti_breve` + `sp07a_crediti_clienti_lungo`; `crediti_clienti_breve`, `crediti_clienti_lungo` separati |
| rimanenze | `sp05_rimanenze` |
| fornitori | `sp16d_debiti_fornitori_breve+sp17d_debiti_fornitori_lungo` |
| cc_comm | crediti_clienti + rimanenze − fornitori |
| banche, banche_breve, banche_lungo, altri_finanziatori | `sp16a…+sp17a…`, `sp16a_debiti_banche_breve`, `sp17a_debiti_banche_lungo`, `sp16b…+sp17b…` |
| debiti_previdenziali, debiti_tributari | righe «Debiti previdenziali», «Debiti tributari» (codici `sp16f…+sp17f…`, `sp16e…+sp17e…`) |
| immob_finanziarie | `sp04_immob_finanziarie` |
| dscr, mt, ccn, current_ratio, ms, copertura_immob, indipendenza, pfn, pfn_ebitda, roi, roe, ros, of_mol, of_revenue | `crisi[col].indicatori` (solo C, 6M, F) |

- [ ] Step 1: test (copia del DB, skip se assente)
```python
"""from_intermedio sui bilanci veri: AMBIENTA (575/17) stampa le cifre del committente."""
import shutil, tempfile
from decimal import Decimal as D
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SRC = Path("/home/peter/DEV/budget/financial_analysis.db")


@pytest.fixture(scope="module")
def db():
    if not SRC.is_file():
        pytest.skip("DB locale assente")
    tmp = Path(tempfile.mkdtemp()) / "db.sqlite"
    shutil.copyfile(SRC, tmp)
    s = sessionmaker(bind=create_engine(f"sqlite:///{tmp}"))()
    yield s
    s.close()


def _data(db, scenario_id):
    from database.models import BudgetScenario
    from app.services.intermedio_report_service import assemble_intermedio
    from app.renderers.infrannuale.data import from_intermedio
    return from_intermedio(assemble_intermedio(db, db.get(BudgetScenario, scenario_id)))


def test_ambienta_coincide_col_riferimento(db):
    d = _data(db, 17)
    assert [c.label for c in d.ce_cols] == ["2025 C", "6M 2026", "Ann. 2026", "2026 F"]
    assert [c.label for c in d.sp_cols] == ["2025 C", "6M 2026", "2026 F"]
    assert round(d.v("ricavi", "proiezione")) == 4109510
    assert round(d.v("oneri_finanziari", "storico")) == -40744
    assert round(d.v("cc_comm", "storico")) == 371906 and round(d.v("cc_comm", "proiezione")) == 852261
    assert round(d.v("crediti_clienti", "infrannuale")) == 1198959
    assert round(d.v("dscr", "storico"), 3) == D("3.026")
    assert round(d.var("ricavi", "proiezione"), 2) == D("9.26")
    assert d.crisi["infrannuale"].codice == "C2" and d.crisi["proiezione"].oltre == 8
    assert d.period_end == "30.06.2026"
    assert d.legend.startswith("C = consuntivo · 6M = infrannuale al 30.06.2026")


def test_senza_proiezione(db):
    d = _data(db, 3)  # AIC, nessun ForecastYear
    assert not d.has_forecast and [c.kind for c in d.sp_cols] == ["C", "6M"]
    assert "F = forecast" not in d.legend


def test_json_del_banco(db, tmp_path):
    from app.renderers.infrannuale.data import dump_json, load_json
    import json
    d = _data(db, 17)
    p = tmp_path / "b.json"
    p.write_text(json.dumps(dump_json(d)))
    assert load_json(p).values == d.values
```
- [ ] Step 2: FAIL (modulo assente). Step 3: implementa. Step 4: PASS. Step 5: commit
  `feat(report-inf): InfrannualeData dal modello dell'intermedio`.

---

### Task 3: Grafici

**Files:** Create `backend/app/renderers/infrannuale/charts.py`; Test `tests/test_inf_charts.py`.

**Interfaces — Produces:** `HEIGHTS` e sei funzioni che restituiscono PNG `bytes`:
- `ricavi_periodi(labels, ricavi, margine, kinds)`, alto 3,0;
- `risultati(labels, ebitda, ebit, utile)`, alto 2,6, sulle colonne C, Ann. e F;
- `stato_patrimoniale(labels, attivo, deb_fin, deb_op, pn)`, alto 2,8;
- `circolante(labels, crediti, rimanenze, fornitori_negativi, cc_comm)`, alto 2,7;
- `debito(labels, dscr, pfn_ebitda)`, alto 2,6: due pannelli e la soglia DSCR 1,0 tratteggiata;
- `crisi(labels, oltre, totale, classi)`, alto 2,4.

Riusano `business_plan.charts` (`_fig`, `_k`, `_f`, `_legend`, `_text`, …) senza toccarlo: le altezze nuove stanno in
un dizionario locale e si passano a una `_fig` locale che chiama `Figure(figsize=(7.2, h))`.

- [ ] Step 1: test
```python
import math, threading
from decimal import Decimal as D
from PIL import Image
import io
from app.renderers.infrannuale import charts

L3 = ["2025 C", "6M 2026", "2026 F"]


def _size(png):
    return Image.open(io.BytesIO(png)).size


def test_misure_come_il_riferimento():
    assert _size(charts.ricavi_periodi(["a", "b", "c", "d"], [D(1)] * 4, [D(1)] * 4, ["C", "6M", "Ann", "F"])) == (1584, 660)
    assert _size(charts.stato_patrimoniale(L3, *([[D(1)] * 3] * 4))) == (1584, 616)
    assert _size(charts.crisi(L3, [9, 7, 8], 14, ["D · Crisi", "C2 · Rischio grave", "D · Crisi"])) == (1584, 528)


def test_valori_assenti_e_negativi():
    charts.circolante(L3, [D(1), None, D(3)], [None] * 3, [D(-5), D(-6), None], [D(-1), D(2), None])
    charts.debito(L3, [None, D("2.9"), None], [None] * 3)
    charts.crisi(L3, [None, 7, 8], 14, ["A3 · Nessun rischio", "B1 · Rischio lieve", "D · Crisi"])


def test_render_concorrente():
    out = []
    ts = [threading.Thread(target=lambda: out.append(charts.crisi(L3, [9, 7, 8], 14, ["D · Crisi"] * 3))) for _ in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(set(out)) == 1
```
- [ ] Step 2: FAIL. Step 3: implementa. I tre grafici dello spike si copiano; gli altri tre si misurano sul riferimento:
  - p5: `risultati` a barre raggruppate, EBITDA navy, EBIT teal, utile arancio;
  - p7: `circolante` a 4 serie, fornitori in negativo;
  - p8: `debito`, due pannelli, DSCR navy e PFN/EBITDA rosso.

  Step 4: PASS. Step 5: commit `feat(report-inf): sei grafici del report infrannuale`.

---

### Task 4: Documento e sezioni 2, 4, 7 — banco strutturale (cancello)

**Files:** Create `infrannuale/document.py`, `infrannuale/sections.py` (economia, patrimonio, crisi),
`tests/fixtures/infrannuale/banco_ambienta.json` (`dump_json` di AMBIENTA 17: i numeri coincidono col riferimento),
`tests/test_inf_banco.py`.

**Interfaces — Produces:**
- `SectionSpec(key, index_title, build, cover=False)`, `SECTIONS`.
- `render_infrannuale(data, *, only=None) -> bytes`: due passate, con intestazione e piè di pagina dello spike.
- `sections.economia`, `sections.patrimonio`, `sections.crisi`: `(data, pages) -> list`.

- [ ] Step 1: test del banco. È il test del Business plan con le pagine (4, 6, 9) e le sezioni
  ("economia", "patrimonio", "crisi"), stesse tolleranze (8 / 3 / 2 pt), skip se manca `riferimento.pdf`. In più:
```python
def test_cifre_della_crisi_come_il_riferimento():
    pdf = fitz.open(stream=render_infrannuale(load_json(FIXTURE), only=("crisi",)), filetype="pdf")
    t = pdf[0].get_text()
    for s in ("3,026×", "−67.803", "20,85%", "attenzione", "C2 · Rischio grave", "8 su 14 oltre soglia"):
        assert s in t, s
```
- [ ] Step 2: FAIL. Step 3: implementa, con le misure dello spike. Step 4: `2 passed`, scarto ≤ 1 pt. Step 5: commit.

---

### Task 5: Testi a regole

**Files:** Create `infrannuale/narrative.py`; Test `tests/test_inf_narrative.py`.

**Interfaces — Produces:**
- `esito(punteggio) -> Literal["oltre soglia", "attenzione", "in soglia"] | None`: sotto 0,33, sotto 0,66, altrimenti;
  `None` se il punteggio manca.
- `ESITO_COLORE`, `classe_colore(codice)`: A teal, B e C arancio, D rosso.
- `key_points(d) -> list[(attacco, testo)]`, con 6 punti:
  - ricavi, marginalità, utile, indebitamento, circolante e cassa, classe di rischio;
  - ogni punto cade se i suoi dati mancano.
- `strengths_weaknesses(d) -> (forza, debolezza)`, con i titoli del riferimento:
  - forza: «Crescita dei ricavi», «Risultati in miglioramento», «Servizio del debito coperto», «Liquidità corrente in
    miglioramento», «Nessun segnale extracontabile»;
  - debolezza: «Classe di rischio …», «Leva finanziaria elevata», «Redditività contenuta», «Sottocapitalizzazione»,
    «Circolante e cassa», «Debiti previdenziali in aumento»;
  - ciascuno scatta sulla regola scritta nel codice, accanto al titolo.
- `actions(d, weaknesses) -> list[(azione, contenuto, indicatori)]`, massimo 6.
- `lettura_costi(d)`, `lettura_patrimonio(d)`, `lettura_circolante(d) -> list[str]`.

- [ ] Step 1: il test su AMBIENTA (fixture del banco) fissa i sei attacchi e questi titoli: forza «Crescita dei
  ricavi», «Servizio del debito coperto», «Nessun segnale extracontabile»; debolezza «Classe di rischio D · Crisi»,
  «Leva finanziaria elevata», «Sottocapitalizzazione». Inoltre:
  - `esito(0.557) == "attenzione"`, `esito(0.691) == "in soglia"`, `esito(0.2) == "oltre soglia"`;
  - una fixture svuotata (tutti `None`) non solleva e restituisce liste vuote.

  Step 2–5 come sopra.

---

### Task 6: Copertina, sintesi, sezioni 3, 5, 6, 8, Allegati — documento completo

**Files:** Create `sections_sintesi.py`, `sections_allegati.py`; Modify `sections.py`, `document.py`; Test
`tests/test_inf_document.py`.

- [ ] Step 1: test
  - AMBIENTA (DB): 13 pagine; l'indice punta alle pagine vere; la copertina contiene «I numeri chiave» e «D · Crisi».
  - Le pagine 2, 4, 6 e 9 contengono le cifre del riferimento: «4.109.510», «852.261», «5,794×», «997.441»,
    «−22.596».
  - Tutti gli scenari infrannuali del DB (1, 3, 4, 5, 17, 19, 21, 23) si rendono senza eccezioni.
  - Lo scenario 3 (senza proiezione) ha in copertina «Forecast non ancora generato».
- [ ] Step 2–5: implementa sezione per sezione, misurando ogni pagina sul riferimento (occhiello, titolo, riquadri,
  grafico, tabelle, pannelli). Commit `feat(report-inf): documento completo di 13 pagine`.

---

### Task 7: Servizio e rotta

**Files:** Create `schemas/infrannuale_pdf.py`, `services/infrannuale_pdf_service.py`; Modify
`api/v1/intermedio_report.py`; Test `tests/test_inf_endpoint.py`.

- [ ] Test:
  - 404 su scenario altrui; 400 su scenario budget; 422 su un campo in più nel corpo;
  - 200 con `application/pdf`, `Content-Disposition` RFC 5987 più la variante ASCII, `Cache-Control: no-store`;
  - nessuna chiamata AI: il test fa fallire `get_infrannuale_comments` o qualunque client Anthropic, se chiamati;
  - la rotta Typst esistente continua a rispondere come prima (i suoi test non cambiano).
- [ ] Commit `feat(report-inf): rotta POST …/infrannuale/pdf`.

---

### Task 8: Stampa

**Files:** `frontend/lib/api.ts` (+ `downloadInfrannualePdf`), `hooks/use-intermedio-download.ts`,
`components/pratica/StampaContent.tsx`; Test `frontend/lib/api.test.ts`.

- [ ] Test Vitest: `downloadInfrannualePdf(1, 2)` chiama `…/companies/1/scenarios/2/infrannuale/pdf` con corpo `{}`.
- [ ] L'hook chiama la nuova funzione, e «Scarica PDF» resta dov'è. Il testo della Stampa non promette più che i
  commenti AI finiscano nel PDF. `npx vitest run` e `npx tsc --noEmit` verdi. Commit.

---

### Task 9: Banco visivo, documentazione, verifica finale

- [ ] `tools/infrannuale/confronta.py`: affianca le 13 pagine di AMBIENTA al riferimento, in
  `tests/.banco-infrannuale/confronto/`.
- [ ] Revisione con la vision di tutte le pagine; si corregge ciò che differisce nel layout.
- [ ] `docs/budget/REPORT-INFRANNUALE-PDF.md`.
- [ ] `CLAUDE.md`: nella sezione «Tab Proiezione, tab Stampa», «Scarica PDF» ora produce il report infrannuale
  ReportLab; il Typst resta nel codice. Aggiungere una riga alla mappa della documentazione.
- [ ] Suite completa: `test_inf_*`, `test_bp_*`, i test dell'intermedio, `vitest`, `tsc`. Commit.
