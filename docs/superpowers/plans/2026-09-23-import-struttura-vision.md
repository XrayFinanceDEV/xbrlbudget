# Import PDF in tre fasi (struttura vision → macroconti → dettagli) — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** prima di estrarre, l'import capisce la struttura del documento (dove stanno SP, CE e le tabelle di dettaglio di crediti e debiti, e di che famiglia è), sceglie la route **dopo** averla vista, e manda alla lettura dei macroconti e dei dettagli **solo le pagine utili** invece dell'intero documento.

**Architecture:** si porta in main la mappa di struttura già scritta e collaudata sul branch `feat/import-mappa-classificazione` (`importers/mappa_classificazione/mappa.py`: blocchi dal text layer, una chiamata Sonnet per blocco, zero chiamate sugli xbrl di legge) in un pacchetto nuovo `importers/struttura_documento/`, che produce un oggetto `Struttura` (pagine SP, pagine CE, pagine di dettaglio, route). `pdf_importer` lo usa dietro l'interruttore `IMPORT_STRUTTURA=vision`: la route della struttura vince su quella del classificatore (dichiarandolo), `analyze_pdf_macros` riceve solo le righe delle pagine SP+CE, `enrich_pdf_details` solo quelle delle pagine SP+dettaglio. Gli estrattori, i riduttori, le verifiche sui totali stampati e i ripieghi di oggi non cambiano.

**Tech Stack:** Python 3, PyMuPDF (`fitz`), Anthropic SDK (Sonnet 5 per la mappa), pytest. Il fornitore dei passi di lettura resta quello scelto da `importers/llm_provider.py` (`PDF_LLM_PROVIDER_IVCEE`, `PDF_LLM_PROVIDER_DETTAGLI`).

**Spec:** `docs/superpowers/specs/2026-09-22-import-mappa-classificazione-design.md` (sul branch `feat/import-mappa-classificazione`: `git show feat/import-mappa-classificazione:docs/superpowers/specs/2026-09-22-import-mappa-classificazione-design.md`), §3.1 «Mappa» e «Xbrl di legge», §6 «Pagine di dettaglio delle note». Decisioni del proprietario che la aggiornano (2026-09-23): «riciclare il più possibile da quella impostazione con 3 route diversi per tipo di pdf»; «vision con sonnet 5 per la struttura e qwen per analisi e recupero dettagli»; «la route è meglio sceglierla dopo la vision»; «risistemeremo l'importatore in modo più ottimizzato: analisi vision, raccolta macroconti, raccolta dettagli»; «lasciamo haiku per ora, poi useremo un modello più economico»; «non facciamo altri test con haiku, usiamo qwen». Motivo misurato: su route A/B ogni chiamata manda l'intero documento (748 righe, 43.000 caratteri su un file del corpus) e una lettura delle macro-voci su Qwen dura 60 s da sola.

## Global Constraints

- Branch `feat/import-struttura`, worktree `/home/peter/DEV/budget-struttura` (da `main` @ `264f1c9`). Nessuna operazione git in `/home/peter/DEV/budget`.
- Interruttore: `IMPORT_STRUTTURA=vision` accende la struttura; assente o qualunque altro valore → comportamento identico a `main`.
- Modello della mappa: `config.STRUTTURA_MODEL = os.environ.get("STRUTTURA_MODEL", "claude-sonnet-5")`. Pagine a 110 dpi, tool forzato, una chiamata per blocco, concorrenza 6 (valori del branch mappa).
- Xbrl di legge (piè di pagina «conforme alla tassonomia», «generato automaticamente», «itcc-ci-»): zero chiamate vision, mappa deterministica dai titoli.
- La struttura non decide nessun importo, colonna o lato: seleziona pagine e route. I numeri li leggono gli estrattori di oggi; la verifica sui totali stampati resta quella di oggi.
- Se la struttura fallisce (Sonnet non risponde, nessuna chiave Anthropic, eccezione) l'import prosegue esattamente come oggi e lo dichiara in `validation_report["struttura"]`. Un controllo mancante non blocca.
- PDF scansionato o testo da OCR (`is_scanned`, `_ocr_source`): la struttura non gira.
- Un insieme di pagine vuoto non restringe nulla (si passa `None`, cioè tutto il documento), mai zero righe.
- `config.py` e `importers/pdf_extractor_llm.py` sono CRLF (verificare gli altri con `file`): preservare, `git diff --stat` prima di ogni commit.
- `git add` per nome file, mai `-A` o `.`. Nessun push.
- Corpus `Test/`, `inbox/`, dati clienti mai committati; le fixture sono PDF sintetici generati con `fitz`. DB reale mai toccato.
- Nessuna chiamata di rete nei test: la mappa si sostituisce con `mappa_pagina_fn`.
- Python: `cd /home/peter/DEV/budget-struttura && /home/peter/DEV/budget/backend/venv/bin/python -m pytest ...`. Regressione: `... -m pytest tests/ -q -p no:cacheprovider -k "pdf or import or vision or trial or coge or ivcee or detail or ledger or macro or struttura"`. Fallimento preesistente accettato: `tests/test_vision_rescue.py::test_build_ce_non_manda_un_ricavo_sconosciuto_su_una_voce_di_costo`.

## Review Focus

1. **Vision non disponibile** (nessuna `ANTHROPIC_API_KEY`, Sonnet in errore): l'import deve completarsi come oggi, con `struttura.stato = "errore"` nel report — test nel Task 4.
2. **Pagina di continuazione mancata** dalla struttura (SP su due pagine, la seconda non riconosciuta): i macroconti non verificano e scatta il ripiego di oggi, dichiarato; mai un bilancio salvato come verificato su metà SP — il riduttore di `analyze_pdf_macros` già lo impedisce; test nel Task 4 che la restrizione non tolga righe di pagine prospetto riconosciute.
3. **Disaccordo di route** (struttura dice C, classificatore dice A/B o viceversa): vince la struttura e il report porta entrambe e `disaccordo: true` — test nel Task 4.
4. **Documento senza nota integrativa o senza tabelle di dettaglio riconosciute**: i dettagli ricevono le pagine SP (sottoconti) e basta, mai zero righe — test nel Task 3.
5. **PDF scansionato**: la struttura non gira e il report dice `stato: "non_applicabile"` — test nel Task 4.

---

### Task 1: portare la mappa di struttura in main

**Files:**
- Create: `importers/struttura_documento/__init__.py`, `importers/struttura_documento/mappa.py`
- Create: `tests/_struttura_fixtures.py`, `tests/test_struttura_mappa.py`
- Modify: `config.py` (CRLF)

**Interfaces:**
- Produces (in `importers/struttura_documento/mappa.py`, identiche al branch mappa): `blocchi(pdf) -> list[Blocco]`, `mappa_documento(pdf, mappa_pagina_fn=None, cache_dir=None, concorrenza=6) -> list[dict]` (una mappa per pagina, `mappe[0]["_chiamate"]` = chiamate fatte), `mappa_pagina(client, png) -> dict`, `e_xbrl_di_legge(pdf) -> bool`, `mappa_xbrl(pdf) -> list[dict]`, costanti `TIPI`, `SCHEMA`, `NOTA_INTEGRATIVA`, `MIN_IMPORTI`, funzioni `_testo_di_testa(page)`, `_importi_pagina(page)`.

- [ ] **Step 1: copia dal branch mappa.**

```bash
cd /home/peter/DEV/budget-struttura
mkdir -p importers/struttura_documento
git show feat/import-mappa-classificazione:importers/mappa_classificazione/mappa.py > importers/struttura_documento/mappa.py
git show feat/import-mappa-classificazione:tests/test_mappa_mappa.py > tests/test_struttura_mappa.py
git show feat/import-mappa-classificazione:tests/_mappa_fixtures.py > tests/_struttura_fixtures.py
```

- [ ] **Step 2: adattare gli import.**
  - In `mappa.py`: `from config import MAPPA_MODEL as MODELLO` → `from config import STRUTTURA_MODEL as MODELLO`; sostituire `from importers.mappa_classificazione.lettore import NUM_SEP` con la definizione locale, copiata verbatim da `lettore.py:17` del branch mappa:

```python
NUM_SEP = re.compile(r"^\(?-?\d{1,3}(\.\d{3})+(,\d{1,2})?\)?-?$|^\(?-?\d+,\d{1,2}\)?-?$")
```

  - In `tests/test_struttura_mappa.py`: `importers.mappa_classificazione.mappa` → `importers.struttura_documento.mappa`, `tests._mappa_fixtures` → `tests._struttura_fixtures`.
  - In `tests/_struttura_fixtures.py`: tenere **solo** le funzioni e costanti usate da `tests/test_struttura_mappa.py` (e dai Task 2-4, che useranno `pdf_xbrl_legge`, `pdf_xbrl_con_nota`, `pdf_contrapposte`, `pdf_colonna_unica`, `MAPPA_CONTRAPPOSTE`, `MAPPA_COLONNA_UNICA` — tenere anche queste), con gli helper privati da cui dipendono (`FONT`, `_riga`, …). Nessun import da `importers.mappa_classificazione`: se una fixture tenuta ne importa qualcosa, riportarlo o toglierla insieme ai test che la usano, annotandolo nel report.
  - `importers/struttura_documento/__init__.py`: docstring di una riga («Struttura del documento: dove stanno i prospetti e le tabelle di dettaglio, prima di estrarre.»).
- [ ] **Step 3:** in `config.py`, accanto a `GX10_MODEL` (preservando CRLF):

```python
STRUTTURA_MODEL = _os.environ.get("STRUTTURA_MODEL", "claude-sonnet-5")  # mappa della struttura (vision)
```

- [ ] **Step 4:** `pytest tests/test_struttura_mappa.py -q` → tutti verdi (sono i test del branch mappa: nessuno va cambiato nelle asserzioni; se uno fallisce per un motivo diverso dagli import, fermarsi e riportarlo).
- [ ] **Step 5: commit** `feat(import): mappa della struttura portata dal branch mappa in importers/struttura_documento`

---

### Task 2: `analizza_struttura` — pagine per fase e route dalla struttura

**Files:**
- Create: `importers/struttura_documento/analisi.py`
- Test: `tests/test_struttura_analisi.py`

**Interfaces:**
- Consumes: Task 1 (`mappa_documento`, `mappa_xbrl`, `e_xbrl_di_legge`, `NOTA_INTEGRATIVA`, `MIN_IMPORTI`, `_testo_di_testa`, `_importi_pagina`); `importers.bilancio_classifier.ROUTE_TRIAL`, `ROUTE_IVCEE`.
- Produces:
  - `@dataclass Struttura(fonte: str, route: str | None, pagine_sp: list[int], pagine_ce: list[int], pagine_dettaglio: list[int], chiamate_vision: int, secondi: float, mappe: list[dict])` con i metodi `pagine_macro() -> set[int] | None`, `pagine_dettagli() -> set[int] | None`, `report() -> dict`.
  - `route_da_mappe(mappe: list[dict]) -> str | None`
  - `pagine_tabelle_nota(pdf: str) -> list[int]`
  - `analizza_struttura(pdf: str, *, mappa_pagina_fn=None) -> Struttura`

- [ ] **Step 1: test che falliscono** in `tests/test_struttura_analisi.py`:

```python
from importers.bilancio_classifier import ROUTE_IVCEE, ROUTE_TRIAL
from importers.struttura_documento.analisi import (
    Struttura, analizza_struttura, pagine_tabelle_nota, route_da_mappe)
from tests._struttura_fixtures import (MAPPA_COLONNA_UNICA, MAPPA_CONTRAPPOSTE, pdf_contrapposte,
                                       pdf_xbrl_con_nota, pdf_xbrl_legge)


def _m(tipo, schema):
    return {"tipo_pagina": tipo, "schema": schema}


def test_route_da_mappe_conti_contro_legge():
    assert route_da_mappe([_m("prospetto_sp", "piano_dei_conti_gerarchico"),
                           _m("prospetto_ce", "piano_dei_conti_gerarchico")]) == ROUTE_TRIAL
    assert route_da_mappe([_m("prospetto_sp", "iv_cee_di_legge"),
                           _m("prospetto_ce", "riclassificato_con_codici_ivcee")]) == ROUTE_IVCEE
    assert route_da_mappe([_m("nota_o_testo", "elenco_piatto")]) is None       # nessun prospetto
    assert route_da_mappe([_m("prospetto_sp", "elenco_piatto"),
                           _m("prospetto_ce", "iv_cee_di_legge")]) is None     # pari: decide il classificatore


def test_xbrl_di_legge_zero_chiamate_e_pagine_dai_titoli(tmp_path):
    s = analizza_struttura(pdf_xbrl_legge(str(tmp_path / "x.pdf")),
                           mappa_pagina_fn=lambda c, png: (_ for _ in ()).throw(AssertionError("vision chiamata")))
    assert s.fonte == "xbrl_titoli" and s.chiamate_vision == 0
    assert s.route == ROUTE_IVCEE
    assert s.pagine_sp == [1] and s.pagine_ce == [2]


def test_contrapposte_una_chiamata_per_blocco_e_route_c(tmp_path):
    chiamate = []
    def finta(client, png):
        chiamate.append(png)
        return {**MAPPA_CONTRAPPOSTE, "schema": "piano_dei_conti_gerarchico"}
    s = analizza_struttura(pdf_contrapposte(str(tmp_path / "c.pdf")), mappa_pagina_fn=finta)
    assert s.fonte == "vision" and s.chiamate_vision == len(chiamate) >= 1
    assert s.route == ROUTE_TRIAL


def test_tabelle_nota_dai_titoli_standard(tmp_path):
    path = pdf_xbrl_con_nota(str(tmp_path / "n.pdf"))
    pagine = pagine_tabelle_nota(path)
    s = analizza_struttura(path, mappa_pagina_fn=lambda c, p: (_ for _ in ()).throw(AssertionError("vision chiamata")))
    assert s.pagine_dettaglio == pagine
    assert not set(pagine) & (set(s.pagine_sp) | set(s.pagine_ce))


def test_insiemi_vuoti_non_restringono():
    s = Struttura(fonte="vision", route=None, pagine_sp=[], pagine_ce=[], pagine_dettaglio=[],
                  chiamate_vision=1, secondi=0.1, mappe=[])
    assert s.pagine_macro() is None and s.pagine_dettagli() is None
    s2 = Struttura(fonte="vision", route=ROUTE_IVCEE, pagine_sp=[1, 2], pagine_ce=[3], pagine_dettaglio=[],
                   chiamate_vision=1, secondi=0.1, mappe=[])
    assert s2.pagine_macro() == {1, 2, 3}
    assert s2.pagine_dettagli() == {1, 2}           # senza tabelle di nota: le pagine SP (sottoconti)
    r = s2.report()
    assert r["stato"] == "ok" and r["route_struttura"] == ROUTE_IVCEE and r["pagine_sp"] == [1, 2]
    assert "mappe" not in r                          # il report persistito non porta le mappe intere
```

`pdf_xbrl_con_nota` è la fixture del branch mappa con prospetti e nota integrativa: leggere che cosa stampa. Se non contiene titoli di tabelle di crediti/debiti, aggiungere a `tests/_struttura_fixtures.py` una fixture `pdf_xbrl_con_tabelle_nota(path)` sullo stesso stile: pagina 1 SP, pagina 2 CE (con il piè «Generato automaticamente - Conforme alla tassonomia itcc-ci-2018-11-04» e le due date come `pdf_xbrl_legge`), pagina 3 «Nota integrativa» di sola prosa, pagina 4 con il titolo «Analisi delle variazioni e della scadenza dei debiti» e almeno 6 importi, pagina 5 di sola prosa; il test allora asserisce `pagine_tabelle_nota(path) == [4]` (la 5 non ha importi) e usa quella fixture.
- [ ] **Step 2:** i test falliscono (modulo mancante).
- [ ] **Step 3: implementazione** `importers/struttura_documento/analisi.py`:

```python
"""Struttura del documento per fase: quali pagine leggono i macroconti, quali i dettagli, e
quale route, decisa DOPO aver visto il documento (decisione del proprietario, 2026-09-23).

La struttura seleziona pagine e route; non decide importi, colonne o lati. Un insieme di
pagine vuoto non restringe nulla: meglio leggere tutto il documento che zero righe."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from importers.bilancio_classifier import ROUTE_IVCEE, ROUTE_TRIAL
from importers.struttura_documento.mappa import (MIN_IMPORTI, NOTA_INTEGRATIVA, _importi_pagina,
                                                 _testo_di_testa, e_xbrl_di_legge, mappa_documento,
                                                 mappa_xbrl)

SCHEMI_CONTI = {"piano_dei_conti_gerarchico", "elenco_piatto"}
SCHEMI_LEGGE = {"iv_cee_di_legge", "riclassificato_con_codici_ivcee"}
TIPI_SP = {"prospetto_sp", "prospetto_sp_e_ce"}
TIPI_CE = {"prospetto_ce", "prospetto_sp_e_ce"}

# Titoli fissi delle tabelle di nota integrativa (schema OIC / tassonomia itcc) che portano
# natura e scadenza di crediti e debiti e la composizione delle rimanenze.
TITOLI_TABELLE_NOTA = re.compile(
    r"variazioni e (?:della )?scadenza dei (?:crediti|debiti)"
    r"|crediti iscritti nell'?\s*attivo circolante"
    r"|suddivisione dei (?:crediti|debiti) per area geografica"
    r"|debiti assistiti da garanzie reali"
    r"|finanziamenti effettuati da soci"
    r"|analisi delle variazioni delle rimanenze", re.I)


@dataclass
class Struttura:
    fonte: str                      # "xbrl_titoli" | "vision"
    route: str | None
    pagine_sp: list[int]
    pagine_ce: list[int]
    pagine_dettaglio: list[int]
    chiamate_vision: int
    secondi: float
    mappe: list[dict] = field(default_factory=list)

    def pagine_macro(self) -> set[int] | None:
        pagine = set(self.pagine_sp) | set(self.pagine_ce)
        return pagine or None

    def pagine_dettagli(self) -> set[int] | None:
        pagine = set(self.pagine_sp) | set(self.pagine_dettaglio)
        return pagine or None

    def report(self) -> dict:
        return {"stato": "ok", "fonte": self.fonte, "route_struttura": self.route,
                "pagine_sp": self.pagine_sp, "pagine_ce": self.pagine_ce,
                "pagine_dettaglio": self.pagine_dettaglio,
                "chiamate_vision": self.chiamate_vision, "secondi": round(self.secondi, 1)}


def route_da_mappe(mappe: list[dict]) -> str | None:
    prospetti = [m for m in mappe if m.get("tipo_pagina") in TIPI_SP | TIPI_CE]
    conti = sum(1 for m in prospetti if m.get("schema") in SCHEMI_CONTI)
    legge = sum(1 for m in prospetti if m.get("schema") in SCHEMI_LEGGE)
    if conti > legge:
        return ROUTE_TRIAL
    if legge > conti:
        return ROUTE_IVCEE
    return None


def pagine_tabelle_nota(pdf: str) -> list[int]:
    """Pagine dopo «Nota integrativa» con un titolo di tabella di dettaglio e almeno
    MIN_IMPORTI importi, piu' la pagina seguente se ha importi (le tabelle continuano)."""
    import fitz
    out: set[int] = set()
    with fitz.open(pdf) as doc:
        pagine = list(doc)
        inizio = next((i for i, p in enumerate(pagine) if NOTA_INTEGRATIVA.search(_testo_di_testa(p))), None)
        if inizio is None:
            return []
        for i in range(inizio, len(pagine)):
            testo = " ".join(pagine[i].get_text().split())
            if TITOLI_TABELLE_NOTA.search(testo) and _importi_pagina(pagine[i]) >= MIN_IMPORTI:
                out.add(i + 1)
                if i + 1 < len(pagine) and _importi_pagina(pagine[i + 1]) >= MIN_IMPORTI:
                    out.add(i + 2)
    return sorted(out)


def analizza_struttura(pdf: str, *, mappa_pagina_fn=None) -> Struttura:
    inizio = time.monotonic()
    if e_xbrl_di_legge(pdf):
        mappe, fonte, chiamate = mappa_xbrl(pdf), "xbrl_titoli", 0
    else:
        mappe = mappa_documento(pdf, mappa_pagina_fn=mappa_pagina_fn)
        fonte, chiamate = "vision", int(mappe[0].get("_chiamate", 0)) if mappe else 0
    route = ROUTE_IVCEE if fonte == "xbrl_titoli" else route_da_mappe(mappe)
    pagine_sp = [m["pagina"] for m in mappe if m.get("tipo_pagina") in TIPI_SP]
    pagine_ce = [m["pagina"] for m in mappe if m.get("tipo_pagina") in TIPI_CE]
    prospetti = set(pagine_sp) | set(pagine_ce)
    dettaglio = {m["pagina"] for m in mappe if m.get("tipo_pagina") == "dettaglio_conti"}
    dettaglio |= set(pagine_tabelle_nota(pdf))
    return Struttura(fonte=fonte, route=route, pagine_sp=pagine_sp, pagine_ce=pagine_ce,
                     pagine_dettaglio=sorted(dettaglio - prospetti), chiamate_vision=chiamate,
                     secondi=time.monotonic() - inizio, mappe=mappe)
```

- [ ] **Step 4:** `pytest tests/test_struttura_analisi.py tests/test_struttura_mappa.py -q` verde.
- [ ] **Step 5: commit** `feat(import): struttura del documento per fase — pagine dei macroconti, dei dettagli e route dopo la vision`

---

### Task 3: macroconti e dettagli leggono solo le pagine indicate

**Files:**
- Modify: `importers/detail_enrichment.py` (`enrich_pdf_details`, ~820), `importers/struttura_documento/analisi.py` (aggiunge `righe_delle_pagine`)
- Test: `tests/test_detail_enrichment.py`, `tests/test_struttura_analisi.py`

**Interfaces:**
- Produces:
  - `righe_delle_pagine(file_path: str, pagine: set[int] | None) -> list[SourceRow] | None` in `analisi.py`: `None` se `pagine` è `None`; altrimenti le righe di `collect_source_rows(file_path)` con `row.page in pagine`.
  - `enrich_pdf_details(file_path, current, prior=None, *, fiscal_year=None, ocr_text=None, pagine: set[int] | None = None)`: se `pagine` non è `None`, dopo `collect_source_rows` tiene solo le righe con `row.page in pagine` e scrive `report["pagine"] = sorted(pagine)` e `report["source_rows_documento"] = <righe prima del filtro>`; `report['source_rows_total']` resta il numero di righe effettivamente usate.

- [ ] **Step 1: test che falliscono.**
  - In `tests/test_struttura_analisi.py`: su `pdf_xbrl_legge`, `righe_delle_pagine(path, {1})` restituisce solo righe con `page == 1` ed è non vuoto; `righe_delle_pagine(path, None) is None`.
  - In `tests/test_detail_enrichment.py` (riusare l'impianto già presente per `enrich_pdf_details` con `PDF_DETAIL_ENRICHMENT` e un lettore finto; leggerlo prima): con `pagine={1}` il lettore finto (o `search_details` sostituito) riceve solo righe di pagina 1, e il report ha `pagine == [1]`, `source_rows_documento >= source_rows_total`; con `pagine=None` il comportamento e il report sono quelli di oggi (nessuna chiave `pagine`).
- [ ] **Step 2:** falliscono.
- [ ] **Step 3:** implementare le due funzioni come da interfaccia. In `enrich_pdf_details` il filtro sta subito dopo `rows = collect_source_rows(file_path, ocr_text=ocr_text)` e prima di ogni uso di `rows`. Nessun altro cambiamento.
- [ ] **Step 4:** `pytest tests/test_detail_enrichment.py tests/test_detail_search.py tests/test_struttura_analisi.py -q` verde.
- [ ] **Step 5: commit** `feat(import): macroconti e dettagli possono leggere solo le pagine della struttura`

---

### Task 4: `pdf_importer` — struttura prima della route, dietro `IMPORT_STRUTTURA=vision`

**Files:**
- Modify: `importers/pdf_importer.py`
- Test: `tests/test_struttura_import.py` (nuovo)

**Interfaces:**
- Consumes: `analizza_struttura`, `Struttura.pagine_macro()`, `Struttura.pagine_dettagli()`, `Struttura.report()`, `righe_delle_pagine` (Tasks 2-3); `enrich_pdf_details(..., pagine=)` (Task 3); `analyze_pdf_macros(file_path, *, include_prior, rows=...)` (esiste già: con `rows` non raccoglie da sé).
- Produces: `validation_report["struttura"]` su ogni import PDF: con interruttore spento `{"stato": "spenta"}`; scansione/OCR `{"stato": "non_applicabile"}`; errore `{"stato": "errore", "errore": <nome della classe dell'eccezione>, "route_classificatore": ...}`; riuscita `Struttura.report()` più `route_classificatore`, `route_usata`, `disaccordo: bool`.

- [ ] **Step 1: test che falliscono** in `tests/test_struttura_import.py`, sullo stesso impianto di `tests/test_provenienza_llm.py` (DB in memoria, `import_pdf_balance_sheet`, fixture PDF sintetiche; leggerlo prima) con `analizza_struttura` sostituita in `importers.struttura_documento.analisi` da una finta:
  1. interruttore assente → `validation_report["struttura"] == {"stato": "spenta"}` e la finta non viene chiamata;
  2. `IMPORT_STRUTTURA=vision`, finta che restituisce una `Struttura` con `route=ROUTE_TRIAL` su un PDF che il classificatore manda in `ROUTE_IVCEE` → il report ha `route_classificatore == ROUTE_IVCEE`, `route_usata == ROUTE_TRIAL`, `disaccordo is True`, e l'import passa dal ramo di route C (verificarlo da `validation_report`/`extraction_method`, come fa `test_coge_provider.py`);
  3. finta che solleva `RuntimeError` → l'import si completa come con l'interruttore spento e il report ha `stato == "errore"`, `errore == "RuntimeError"`;
  4. finta con `pagine_sp=[1]`, `pagine_ce=[2]` su un PDF route A/B che arriva ad `analyze_pdf_macros` (sostituita da una finta che registra `rows`) → la finta riceve solo righe con `page in {1, 2}`; `enrich_pdf_details` riceve `pagine == {1} | set(pagine_dettaglio)`;
  5. PDF con `is_scanned` (riusare una fixture o un test esistente di scansione; se non ce n'è uno economico, sostituire `fitz` per far risultare il testo vuoto come fanno i test esistenti sulle scansioni) → `stato == "non_applicabile"`.
- [ ] **Step 2:** falliscono.
- [ ] **Step 3: implementazione.**
  - Subito dopo `classification = classify_bilancio(...)` e dopo i due `raise` per `ROUTE_XBRL`/`ROUTE_UNSUPPORTED`:

```python
        _struttura = None
        if os.environ.get("IMPORT_STRUTTURA") != "vision":
            _struttura_report = {"stato": "spenta"}
        elif is_scanned or _ocr_source:
            _struttura_report = {"stato": "non_applicabile"}
        else:
            from importers.struttura_documento import analisi as _analisi_struttura
            try:
                _struttura = _analisi_struttura.analizza_struttura(file_path)
                _struttura_report = _struttura.report()
            except Exception as exc:  # la struttura e' un'economia: senza, l'import di oggi
                logger.warning("Struttura del documento non disponibile (%s): import come oggi", type(exc).__name__)
                _struttura_report = {"stato": "errore", "errore": type(exc).__name__}
        _route = (_struttura.route if _struttura is not None and _struttura.route else classification.route)
        _struttura_report.update(route_classificatore=classification.route, route_usata=_route,
                                 disaccordo=_route != classification.route)
```

  (per `"spenta"` e `"non_applicabile"` l'`update` aggiunge le tre chiavi con `disaccordo=False`: va bene, e il test 1 va scritto di conseguenza — asserire `["stato"] == "spenta"` e `disaccordo is False`, non l'uguaglianza dell'intero dict.)
  - `is_trial_balance = (_route == ROUTE_TRIAL)` e, alla riga del preflight (`if classification.route == ROUTE_IVCEE and not is_scanned ...`), `_route` al posto di `classification.route`. Nessun'altra lettura di `classification.route` cambia (`macro_area`/`subcategory` nel risultato restano quelle del classificatore).
  - Alla chiamata di `analyze_pdf_macros` passare `rows=_analisi_struttura.righe_delle_pagine(file_path, _struttura.pagine_macro())` quando `_struttura is not None` (con `pagine_macro()` `None` la funzione restituisce `None` e `analyze_pdf_macros` raccoglie da sé come oggi); import locale del modulo come sopra.
  - Alla chiamata di `enrich_pdf_details` aggiungere `pagine=_struttura.pagine_dettagli() if _struttura is not None else None`.
  - Scrivere `_validation_payload["struttura"] = _struttura_report` accanto a `ivcee_provider`/`dettagli_provider` (stesso punto, prima della serializzazione, su ogni route) e lo stesso su `_prior_validation`.
- [ ] **Step 4:** `pytest tests/test_struttura_import.py tests/test_provenienza_llm.py tests/test_coge_provider.py -q` verde; poi la regressione dei Global Constraints.
- [ ] **Step 5: commit** `feat(import): struttura del documento prima della route, dietro IMPORT_STRUTTURA=vision`

---

### Task 5: sonda, confronto, documentazione

**Files:**
- Modify: `tests/_import_probe.py`, `scripts/confronta_probe.py`, `tests/test_confronta_probe.py`, `docs/deployment/PRODUCTION_CONFIG.md` (CRLF), `docs/import/REGOLE-IMPORT-01-ROUTING.md`, `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md`

- [ ] **Step 1: test che falliscono** in `tests/test_confronta_probe.py`: `confronta` restituisce anche `struttura` = tupla `((route_usata, chiamate_vision, secondi), (…))` e `righe` = tupla `((macro_rows, dettagli_rows), (…))`; `campi_diversi` invariato.
- [ ] **Step 2:** falliscono.
- [ ] **Step 3:** nella sonda: `rec["struttura"] = vr.get("struttura")`, `rec["macro_rows"] = (vr.get("macro_analysis") or {}).get("rows_total")`, `rec["dettagli_rows"] = (vr.get("detail_enrichment") or {}).get("source_rows_total")`. In `confronta` le due tuple nuove (valori `None` se assenti). Documentazione in italiano:
  - `PRODUCTION_CONFIG.md`: `IMPORT_STRUTTURA` (`vision` per accendere) e `STRUTTURA_MODEL`, con costo atteso (1-2 chiamate Sonnet a file, zero sugli xbrl di legge) e il fatto che le pagine intere vanno ad Anthropic;
  - `REGOLE-IMPORT-01-ROUTING.md`: con l'interruttore acceso la route viene dalla struttura, il classificatore resta ripiego e il disaccordo si dichiara;
  - `REGOLE-IMPORT-02-ESTRAZIONE.md`: macroconti sulle sole pagine SP+CE, dettagli sulle sole pagine SP+tabelle di nota, e il ripiego sull'intero documento quando la struttura non c'è.
- [ ] **Step 4:** test verdi + regressione.
- [ ] **Step 5: commit** `feat(import): la sonda registra struttura e righe lette; documentazione di IMPORT_STRUTTURA`

---

### Task 6 (controller): banco

- [ ] Elenchi: i 26 file A/B (`budget-intermedio/.superpowers/sdd/2026-09-22-import-mappa-classificazione/banco/route-ab/elenco.txt`) e i 22 di route C (`.../banco/route-c/elenco.txt`).
- [ ] Passate su Qwen (decisione del proprietario: niente passate Haiku): `IMPORT_STRUTTURA=vision`, `PDF_LLM_PROVIDER_COGE=gx10`, `PDF_LLM_PROVIDER_IVCEE=gx10`, `PDF_LLM_PROVIDER_DETTAGLI=gx10`, su snapshot del codice, **gx10 dedicato al banco** (nessuna sonda concorrente). Due passate per misurare il rumore.
- [ ] Misure per file: `secondi`, `struttura` (fonte, route, disaccordo, chiamate vision), `macro_rows` e `dettagli_rows` (contro le 748 righe intere del file misurato il 23/09), quadratura, `time_budget_exhausted` nei warning, e se `sp16a`/`sp17a` (banche) e `sp16d` (fornitori) escono valorizzati.
- [ ] Registrare nel ledger esiti e decisione (accendere `IMPORT_STRUTTURA` in produzione, tarare i budget, o prossimo passo).
