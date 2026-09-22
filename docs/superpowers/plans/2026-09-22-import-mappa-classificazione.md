# Import PDF con mappa, lettura verificata e classificazione locale — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portare il pilota `tools/pilota_import/` dentro `importers/mappa_classificazione/` come motore di import selezionabile per configurazione (`IMPORT_ENGINE=mappa`), con test, diagnostica persistita e un banco di prova sul corpus.

**Architecture:** Cinque stadi in un pacchetto: mappa della struttura (Sonnet 5, una chiamata per prospetto; deterministica sugli xbrl di legge), lettore geometrico del text layer, verifica sui totali stampati (prefisso più corto che somma al centesimo), classificazione righe → codici (Qwen su gx10 con grammatica a sequenza fissa; tabella `iv_cee_hierarchy` sugli xbrl), riconciliazione in Python. Il motore restituisce i due dizionari `bs`/`ce` con le colonne del DB e un rapporto di diagnostica; `pdf_importer` lo invoca prima delle route esistenti e, se non è acceso o fallisce, prosegue come oggi.

**Tech Stack:** Python 3.11, PyMuPDF (`fitz`), `anthropic` SDK (mappa), `httpx` (gx10, `/v1/chat/completions` con `structured_outputs.regex`), pydantic (già in uso), pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-import-mappa-classificazione-design.md`

## Global Constraints

- Ramo del codice: `feat/import-mappa-classificazione` (worktree `/home/peter/DEV/budget-intermedio`, già creato da `main`). Docs e config vanno su `main` a fine lotto; il codice sul ramo.
- `git add` sempre per nome di file, mai `-A` o `.`; nessun push (Jenkins su staging) senza richiesta esplicita.
- Nessun dato cliente nel repo: i PDF di `inbox/` e `Test/` restano fuori da git; i test usano PDF sintetici generati con `fitz`.
- La chiave gx10 arriva SOLO dalla variabile d'ambiente `GX10_API_KEY` e viaggia SOLO nell'header `Authorization: Bearer`; mai in argv, nei log, nelle eccezioni, nei rapporti persistiti.
- Il DB reale `financial_analysis.db` non si tocca: i test di integrazione usano `tests/_import_probe.py` (SQLite in memoria).
- Nessun plug: un divario si misura e si dichiara (`_mappa_*` nel `validation_report`), mai si tappa. Un totale che non torna è un avviso da Rettifiche, non un blocco al salvataggio.
- I file `frontend/lib/api.ts`, `types/api.ts` e `backend/app/main.py` hanno terminatori misti o CRLF: questo piano non li tocca. Prima di ogni commit: `git diff --stat` e nessun file con migliaia di righe cambiate.
- Nomi in italiano per moduli, funzioni e messaggi (convenzione del pacchetto, come nel pilota); docstring che dicono *perché*.
- Fuori da questo piano (piano 2): le tabelle di dettaglio delle note negli xbrl di legge (scadenze e sotto-campi di crediti e debiti) e le scansioni (OCR MinerU prima della mappa).

---

## Struttura dei file

| File | Responsabilità |
|---|---|
| `importers/mappa_classificazione/__init__.py` | espone `estrai`, `Estrazione`, `MappaError` |
| `importers/mappa_classificazione/lettore.py` | `Riga`, `numero()`, `leggi_pagina()`, `leggi_documento()` — text layer → righe con colonne |
| `importers/mappa_classificazione/verifica.py` | `individua_totali()`, `somme_per_lato()` — totali verificati, foglie |
| `importers/mappa_classificazione/riconcilia.py` | `riconcilia()` — foglie classificate → campi, netting, lato, diagnostica |
| `importers/mappa_classificazione/llm_gx10.py` | `ClientGx10.completa_vincolato()` — una chiamata vincolata da regex a gx10 |
| `importers/mappa_classificazione/classifica.py` | `legenda()`, `classifica()` — righe → codici via Qwen |
| `importers/mappa_classificazione/legge.py` | `classifica_legge()` — righe dello schema di legge → codici via `iv_cee_hierarchy`, senza modello |
| `importers/mappa_classificazione/mappa.py` | schema della mappa, `mappa_pagina()` (Sonnet), `blocchi()` (filtro, confine SP/CE, riuso), `mappa_documento()`, `mappa_xbrl()` |
| `importers/mappa_classificazione/engine.py` | `estrai()` — orchestrazione, dizionari con le colonne del DB, rapporto |
| `config.py` | `IMPORT_ENGINE`, `GX10_BASE_URL`, `GX10_MODEL`, `MAPPA_MODEL` |
| `importers/pdf_importer.py` | ramo `IMPORT_ENGINE == "mappa"` prima delle route, salto dell'arricchimento Haiku, rapporto nel `validation_report`, `_PDF_PARSER_VERSION` |
| `scripts/bench_mappa.py` | banco di prova su una cartella, confronto con `original_*_snapshot` o con `import_baseline.json` |
| `tests/_mappa_fixtures.py` | PDF sintetici (`fitz`) per contrapposte, colonna unica, xbrl di legge |
| `tests/test_mappa_*.py` | una suite per modulo |

Il pilota in `tools/pilota_import/` viene spostato con `git mv` (storia conservata) e cancellato alla fine: `tools/pilota_import/pilota.py` diventa `scripts/bench_mappa.py`.

---

### Task 1: PDF sintetici per i test

**Files:**
- Create: `tests/_mappa_fixtures.py`
- Test: `tests/test_mappa_fixtures.py`

**Interfaces:**
- Produces: `pdf_contrapposte(path) -> str`, `pdf_colonna_unica(path) -> str`, `pdf_xbrl_legge(path) -> str`, `MAPPA_CONTRAPPOSTE: dict`, `MAPPA_COLONNA_UNICA: dict` (mappe attese, nel formato di Task 7).

- [ ] **Step 1: Scrivere il test che apre i tre PDF e conta pagine e importi**

```python
# tests/test_mappa_fixtures.py
import fitz

from tests._mappa_fixtures import pdf_contrapposte, pdf_colonna_unica, pdf_xbrl_legge


def test_i_pdf_sintetici_hanno_text_layer_e_importi(tmp_path):
    for costruttore, pagine, importi_min in ((pdf_contrapposte, 1, 12), (pdf_colonna_unica, 2, 10), (pdf_xbrl_legge, 3, 12)):
        path = costruttore(str(tmp_path / f"{costruttore.__name__}.pdf"))
        with fitz.open(path) as doc:
            assert doc.page_count == pagine
            parole = [w[4] for p in doc for w in p.get_text("words")]
        assert sum(1 for w in parole if "," in w and w.replace(".", "").replace(",", "").isdigit()) >= importi_min
```

- [ ] **Step 2: Eseguire il test e vederlo fallire**

Run: `cd /home/peter/DEV/budget-intermedio && source /home/peter/DEV/budget/backend/venv/bin/activate && pytest tests/test_mappa_fixtures.py -v`
Expected: FAIL, `ModuleNotFoundError: tests._mappa_fixtures`

- [ ] **Step 3: Scrivere i costruttori**

```python
# tests/_mappa_fixtures.py
"""PDF sintetici con text layer, nelle tre famiglie della spec. Niente dati reali."""
import fitz

FONT = "helv"


def _riga(page, y, colonne):
    """colonne: [(x, testo, allinea_destra)] — i numeri sono allineati a destra sull'ancora."""
    for x, testo, destra in colonne:
        if not testo:
            continue
        if destra:
            larghezza = fitz.get_text_length(testo, fontname=FONT, fontsize=8)
            page.insert_text((x - larghezza, y), testo, fontname=FONT, fontsize=8)
        else:
            page.insert_text((x, y), testo, fontname=FONT, fontsize=8)


def pdf_contrapposte(path: str) -> str:
    """Una pagina, ATTIVITA' a sinistra e PASSIVITA' a destra, piano dei conti a 3 livelli,
    colonne 'Saldo non rettificato | Rettifiche | Saldo finale' per lato."""
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.insert_text((300, 40), "STATO PATRIMONIALE", fontname=FONT, fontsize=10)
    page.insert_text((30, 60), "ATTIVITA'", fontname=FONT, fontsize=9)
    page.insert_text((450, 60), "PASSIVITA'", fontname=FONT, fontsize=9)
    for x0 in (30, 450):
        page.insert_text((x0, 80), "Conto", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 60, 80), "Descrizione", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 230, 76), "Saldo non", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 230, 86), "rettificato", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 290, 80), "Rettifiche", fontname=FONT, fontsize=8)
        page.insert_text((x0 + 345, 80), "Saldo finale", fontname=FONT, fontsize=8)
    sinistra = [("05", "IMMOBILIZZAZIONI MATERIALI", "1.500,00", "", "1.500,00"),
                ("05.01", "IMPIANTI", "1.000,00", "", "1.000,00"),
                ("05.01.01", "Impianti generici", "1.000,00", "", "1.000,00"),
                ("05.03", "ATTREZZATURE", "500,00", "", "500,00"),
                ("05.03.01", "Attrezzatura varia", "500,00", "", "500,00"),
                ("11", "CREDITI COMMERCIALI", "800,00", "", "800,00"),
                ("11.01", "Clienti Italia", "800,00", "", "800,00"),
                ("19", "DISPONIBILITA' LIQUIDE", "200,00", "50,00", "250,00"),
                ("19.01", "Banca c/c", "200,00", "50,00", "250,00")]
    destra = [("23", "CAPITALE E RISERVE", "1.000,00", "", "1.000,00"),
              ("23.01", "Capitale sociale", "1.000,00", "", "1.000,00"),
              ("33", "DEBITI COMMERCIALI", "900,00", "", "900,00"),
              ("33.01", "Fornitori Italia", "900,00", "", "900,00"),
              ("41", "FONDI AMMORTAMENTO", "400,00", "", "400,00"),
              ("41.01", "F.do amm. impianti", "400,00", "", "400,00"),
              ("", "Utile del periodo", "250,00", "", "250,00"),
              ("", "Totale a pareggio", "2.550,00", "", "2.550,00")]
    for x0, righe in ((30, sinistra), (450, destra)):
        y = 100
        for codice, testo, a, b, c in righe:
            _riga(page, y, [(x0, codice, False), (x0 + 60, testo, False),
                            (x0 + 280, a, True), (x0 + 335, b, True), (x0 + 395, c, True)])
            y += 12
    doc.save(path)
    return path


def pdf_colonna_unica(path: str) -> str:
    """Due pagine, riclassificato in colonna unica con codici IV CEE + conto, colonne
    'Importo corrente | Importo comparato', fondi come righe negative nell'attivo.
    La seconda pagina continua la prima senza ristampare il titolo di sezione."""
    doc = fitz.open()
    intestazioni = [(400, "Importo corrente", True), (500, "Importo comparato", True)]
    righe_p1 = [(20, "", "STATO PATRIMONIALE ATTIVO", "1.700,00", "1.600,00"),
                (26, "", "B) Immobilizzazioni", "900,00", "950,00"),
                (30, "", "II. Immobilizzazioni Materiali", "900,00", "950,00"),
                (34, "", "2) Impianti e macchinario", "900,00", "950,00"),
                (38, "", "Costo storico", "1.000,00", "1.000,00"),
                (44, "BII2 104.00011", "IMPIANTI GENERICI", "1.000,00", "1.000,00"),
                (38, "", "Fondo ammortamento", "-100,00", "-50,00"),
                (44, "BII2A 114.00011", "F.AMM. IMPIANTI GENERICI", "-100,00", "-50,00"),
                (26, "", "C) Attivo circolante", "800,00", "650,00"),
                (30, "", "II. Crediti", "800,00", "650,00"),
                (34, "", "1) verso clienti", "800,00", "650,00"),
                (38, "", "- entro esercizio successivo", "800,00", "650,00")]
    righe_p2 = [(44, "CII1A 208.00001", "CLIENTI ITALIA", "800,00", "650,00"),
                (20, "", "STATO PATRIMONIALE PASSIVO", "1.700,00", "1.600,00"),
                (26, "", "A) Patrimonio netto", "1.000,00", "1.000,00"),
                (30, "", "I) Capitale", "1.000,00", "1.000,00"),
                (44, "AI 301.00001", "CAPITALE SOCIALE", "1.000,00", "1.000,00"),
                (26, "", "D) Debiti", "700,00", "600,00"),
                (30, "", "7) Debiti verso fornitori", "700,00", "600,00"),
                (44, "D7 401.00001", "FORNITORI ITALIA", "700,00", "600,00")]
    for righe in (righe_p1, righe_p2):
        page = doc.new_page(width=595, height=842)
        page.insert_text((20, 30), "BILANCIO RICLASSIFICATO UE", fontname=FONT, fontsize=9)
        _riga(page, 50, [(20, "Descrizione", False)] + intestazioni)
        y = 70
        for x, codice, testo, a, b in righe:
            _riga(page, y, [(x, (codice + " " + testo).strip(), False), (400, a, True), (500, b, True)])
            y += 12
        page.insert_text((20, 820), "Continua..", fontname=FONT, fontsize=7)
    doc.save(path)
    return path


def pdf_xbrl_legge(path: str) -> str:
    """Tre pagine: SP e CE nello schema civilistico con due date, più una pagina di nota
    con prosa e nessun importo. Piè di pagina della tassonomia."""
    doc = fitz.open()
    intest = [(380, "31-12-2025", True), (480, "31-12-2024", True)]
    sp = [(30, "Stato patrimoniale", "", ""), (34, "Attivo", "", ""),
          (38, "B) Immobilizzazioni", "", ""),
          (42, "I - Immobilizzazioni immateriali", "100", "90"),
          (42, "II - Immobilizzazioni materiali", "900", "950"),
          (42, "Totale immobilizzazioni (B)", "1.000", "1.040"),
          (38, "C) Attivo circolante", "", ""),
          (42, "II - Crediti", "", ""),
          (46, "esigibili entro l'esercizio successivo", "600", "500"),
          (46, "esigibili oltre l'esercizio successivo", "100", "80"),
          (46, "Totale crediti", "700", "580"),
          (42, "IV - Disponibilita' liquide", "300", "200"),
          (42, "Totale attivo circolante (C)", "1.000", "780"),
          (38, "Totale attivo", "2.000", "1.820"),
          (34, "Passivo", "", ""),
          (38, "A) Patrimonio netto", "", ""),
          (42, "I - Capitale", "1.000", "1.000"),
          (42, "IX - Utile (perdita) dell'esercizio", "200", "(20)"),
          (42, "Totale patrimonio netto", "1.200", "980"),
          (38, "D) Debiti", "", ""),
          (42, "esigibili entro l'esercizio successivo", "800", "840"),
          (42, "Totale debiti", "800", "840"),
          (38, "Totale passivo", "2.000", "1.820")]
    ce = [(30, "Conto economico", "", ""), (34, "A) Valore della produzione", "", ""),
          (38, "1) ricavi delle vendite e delle prestazioni", "3.000", "2.500"),
          (38, "Totale valore della produzione", "3.000", "2.500"),
          (34, "B) Costi della produzione", "", ""),
          (38, "7) per servizi", "2.000", "1.900"),
          (38, "9) per il personale", "", ""),
          (42, "a) salari e stipendi", "500", "450"),
          (42, "Totale costi per il personale", "500", "450"),
          (38, "Totale costi della produzione", "2.500", "2.350"),
          (34, "Differenza tra valore e costi della produzione (A - B)", "500", "150"),
          (34, "20) Imposte sul reddito dell'esercizio", "300", "170"),
          (34, "21) Utile (perdita) dell'esercizio", "200", "(20)")]
    for righe in (sp, ce):
        page = doc.new_page(width=595, height=842)
        _riga(page, 50, intest)
        y = 70
        for x, testo, a, b in righe:
            _riga(page, y, [(x, testo, False), (380, a, True), (480, b, True)])
            y += 12
        page.insert_text((20, 820), "Bilancio di esercizio al 31-12-2025  Generato automaticamente - Conforme alla tassonomia itcc-ci-2018-11-04",
                         fontname=FONT, fontsize=6)
    nota = doc.new_page(width=595, height=842)
    nota.insert_text((30, 60), "Nota integrativa", fontname=FONT, fontsize=10)
    for i in range(20):
        nota.insert_text((30, 90 + i * 14), "I criteri di valutazione adottati sono conformi alle disposizioni del codice civile.",
                         fontname=FONT, fontsize=8)
    doc.save(path)
    return path


MAPPA_CONTRAPPOSTE = {
    "tipo_pagina": "prospetto_sp", "disposizione": "sezioni_contrapposte", "schema": "piano_dei_conti_gerarchico",
    "sezioni": [
        {"posizione": "sinistra", "contenuto": "attivo", "colonne": [
            {"ruolo": "saldo_non_rettificato", "intestazione": "Saldo non rettificato"},
            {"ruolo": "rettifiche", "intestazione": "Rettifiche"},
            {"ruolo": "saldo_finale", "intestazione": "Saldo finale"}]},
        {"posizione": "destra", "contenuto": "passivo", "colonne": [
            {"ruolo": "saldo_non_rettificato", "intestazione": "Saldo non rettificato"},
            {"ruolo": "rettifiche", "intestazione": "Rettifiche"},
            {"ruolo": "saldo_finale", "intestazione": "Saldo finale"}]}],
    "continuazione": False, "codici_conto": True, "totali_stampati": True, "anno_precedente": False,
    "negativi": "segno_meno", "fondi_ammortamento": "nel_passivo", "note": "", "pagina": 1,
}

MAPPA_COLONNA_UNICA = {
    "tipo_pagina": "prospetto_sp", "disposizione": "colonna_unica", "schema": "riclassificato_con_codici_ivcee",
    "sezioni": [{"posizione": "unica", "contenuto": "misto", "colonne": [
        {"ruolo": "saldo_corrente", "intestazione": "Importo corrente"},
        {"ruolo": "saldo_precedente", "intestazione": "Importo comparato"}]}],
    "continuazione": False, "codici_conto": True, "totali_stampati": True, "anno_precedente": True,
    "negativi": "segno_meno", "fondi_ammortamento": "righe_negative_nell_attivo", "note": "", "pagina": 1,
}
```

- [ ] **Step 4: Eseguire il test e vederlo passare**

Run: `pytest tests/test_mappa_fixtures.py -v`
Expected: PASS (3 costruttori)

- [ ] **Step 5: Commit**

```bash
git add tests/_mappa_fixtures.py tests/test_mappa_fixtures.py
git commit -m "test(import): PDF sintetici per le tre famiglie del motore mappa"
```

---

### Task 2: Lettore geometrico nel pacchetto

**Files:**
- Create: `importers/mappa_classificazione/__init__.py` (vuoto per ora)
- Move: `tools/pilota_import/lettore.py` → `importers/mappa_classificazione/lettore.py`
- Test: `tests/test_mappa_lettore.py`

**Interfaces:**
- Produces: `numero(tok: str) -> Decimal | None`; `Riga` (campi: `id, pagina, posizione, lato, codice, testo, importi: dict[str, Decimal], valore: Decimal | None, profondita_codice: int, profondita_rientro: int, y: float, x0: float, intestazione: bool, statement: str`); `leggi_pagina(page, mappa: dict, stato: dict | None = None) -> list[Riga]`; `leggi_documento(pdf: str, mappe: list[dict]) -> list[Riga]`.

- [ ] **Step 1: Scrivere i test**

```python
# tests/test_mappa_lettore.py
from decimal import Decimal

import fitz
import pytest

from importers.mappa_classificazione.lettore import leggi_documento, leggi_pagina, numero
from tests._mappa_fixtures import MAPPA_COLONNA_UNICA, MAPPA_CONTRAPPOSTE, pdf_colonna_unica, pdf_contrapposte


@pytest.mark.parametrize("tok,atteso", [
    ("1.234,56", Decimal("1234.56")), ("(1.499)", Decimal("-1499")), ("-12.986,93", Decimal("-12986.93")),
    ("406", Decimal("406")), ("1.234,56-", Decimal("-1234.56")), ("abc", None), ("12.3.4", None),
])
def test_numero_italiano(tok, atteso):
    assert numero(tok) == atteso


def test_contrapposte_taglio_colonne_e_lato(tmp_path):
    with fitz.open(pdf_contrapposte(str(tmp_path / "c.pdf"))) as doc:
        righe = leggi_pagina(doc[0], MAPPA_CONTRAPPOSTE)
    sinistra = [r for r in righe if r.posizione == "sinistra" and r.valore is not None]
    destra = [r for r in righe if r.posizione == "destra" and r.valore is not None]
    assert [r.codice for r in sinistra][:3] == ["05", "05.01", "05.01.01"]
    assert all(r.lato == "attivo" for r in sinistra) and all(r.lato == "passivo" for r in destra)
    banca = next(r for r in sinistra if r.testo == "Banca c/c")
    assert banca.importi == {"saldo_non_rettificato": Decimal("200.00"), "rettifiche": Decimal("50.00"),
                             "saldo_finale": Decimal("250.00")}
    assert banca.valore == Decimal("250.00")           # saldo_finale vince
    assert banca.profondita_codice == 2
    pareggio = next(r for r in destra if r.testo == "Totale a pareggio")
    assert pareggio.valore == Decimal("2550.00") and pareggio.codice == ""
    # nessuna parola della sezione destra finisce a sinistra
    assert not any("CAPITALE" in r.testo for r in sinistra)


def test_colonna_unica_lato_dalle_intestazioni_e_continuazione(tmp_path):
    path = pdf_colonna_unica(str(tmp_path / "u.pdf"))
    mappe = [MAPPA_COLONNA_UNICA, {**MAPPA_COLONNA_UNICA, "pagina": 2, "continuazione": True}]
    righe = leggi_documento(path, mappe)
    clienti = next(r for r in righe if r.testo == "CLIENTI ITALIA")
    assert clienti.pagina == 2 and clienti.lato == "attivo" and clienti.codice == "CII1A 208.00001"
    fornitori = next(r for r in righe if r.testo == "FORNITORI ITALIA")
    assert fornitori.lato == "passivo" and fornitori.valore == Decimal("700.00")
    fondo = next(r for r in righe if r.testo == "F.AMM. IMPIANTI GENERICI")
    assert fondo.valore == Decimal("-100.00")
    # il rientro e' quello della descrizione, non del codice
    costo = next(r for r in righe if r.testo == "Costo storico")
    assert clienti.x0 > costo.x0


def test_pagine_non_prospetto_non_si_leggono(tmp_path):
    path = pdf_colonna_unica(str(tmp_path / "u.pdf"))
    righe = leggi_documento(path, [MAPPA_COLONNA_UNICA, {**MAPPA_COLONNA_UNICA, "pagina": 2,
                                                          "tipo_pagina": "nota_o_testo", "continuazione": False}])
    assert {r.pagina for r in righe} == {1}
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_lettore.py -v`
Expected: FAIL, `ModuleNotFoundError: importers.mappa_classificazione`

- [ ] **Step 3: Spostare il lettore e creare il pacchetto**

```bash
mkdir -p importers/mappa_classificazione
git mv tools/pilota_import/lettore.py importers/mappa_classificazione/lettore.py
printf '"""Motore di import PDF: mappa della struttura, lettura verificata, classificazione locale.\n\nSpec: docs/superpowers/specs/2026-09-22-import-mappa-classificazione-design.md\n"""\n' > importers/mappa_classificazione/__init__.py
```

Nel file spostato non serve cambiare gli import (non importa altri moduli del pilota). Se un test fallisce sul taglio, la costante da guardare è `larghezza * 0.25` in `_taglio_da_intestazione` e la tolleranza `larghezza * 0.035` in `leggi_pagina`; non toccare la logica dei centri delle parole.

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `pytest tests/test_mappa_lettore.py -v`
Expected: PASS (4 test, 7 casi di `numero`)

- [ ] **Step 5: Commit**

```bash
git add importers/mappa_classificazione/__init__.py importers/mappa_classificazione/lettore.py tests/test_mappa_lettore.py
git commit -m "feat(import): lettore geometrico guidato dalla mappa in importers/mappa_classificazione"
```

---

### Task 3: Verifica sui totali stampati

**Files:**
- Move: `tools/pilota_import/verifica.py` → `importers/mappa_classificazione/verifica.py`
- Test: `tests/test_mappa_verifica.py`

**Interfaces:**
- Consumes: `Riga` (Task 2).
- Produces: `individua_totali(righe: list[Riga]) -> dict` con chiavi `totali: dict[str, list[str]]`, `non_verificati: list[tuple[str, Decimal, Decimal | None]]`, `foglie: list[str]`, `genitore: dict[str, str]`; `somme_per_lato(righe, foglie: set[str]) -> dict[str, Decimal]`.

- [ ] **Step 1: Scrivere i test con righe costruite a mano**

```python
# tests/test_mappa_verifica.py
from decimal import Decimal as D

from importers.mappa_classificazione.lettore import Riga
from importers.mappa_classificazione.verifica import individua_totali, somme_per_lato


def riga(i, testo, valore, *, codice="", x0=30.0, lato="attivo", statement="sp", pc=0):
    return Riga(id=f"r{i}", pagina=1, posizione="unica", lato=lato, codice=codice, testo=testo,
                importi={}, valore=D(valore) if valore is not None else None, profondita_codice=pc,
                profondita_rientro=1, y=float(i), x0=x0, intestazione=valore is None, statement=statement)


def test_mastro_prima_dei_figli_con_codici():
    righe = [riga(1, "IMMOBILIZZAZIONI", "1500", codice="05", pc=1),
             riga(2, "IMPIANTI", "1000", codice="05.01", pc=2),
             riga(3, "Impianti generici", "1000", codice="05.01.01", pc=3),
             riga(4, "ATTREZZATURE", "500", codice="05.03", pc=2),
             riga(5, "Attrezzatura varia", "500", codice="05.03.01", pc=3)]
    v = individua_totali(righe)
    assert v["totali"] == {"r1": ["r2", "r4"], "r2": ["r3"], "r4": ["r5"]}
    assert v["foglie"] == ["r3", "r5"] and v["genitore"]["r3"] == "r2"
    assert somme_per_lato(righe, set(v["foglie"])) == {"sp:attivo": D("1500")}


def test_totale_dopo_i_figli_prefisso_piu_corto():
    # IV CEE: «Totale crediti» sta al livello della propria intestazione, i figli piu' rientrati
    righe = [riga(1, "I - Rimanenze", "79", x0=42), riga(2, "II - Crediti", None, x0=42),
             riga(3, "esigibili entro", "574", x0=46), riga(4, "esigibili oltre", "95", x0=46),
             riga(5, "imposte anticipate", "5", x0=46), riga(6, "Totale crediti", "674", x0=42),
             riga(7, "IV - Disponibilita'", "28", x0=42), riga(8, "Totale attivo circolante (C)", "781", x0=42)]
    v = individua_totali(righe)
    assert v["totali"]["r6"] == ["r5", "r4", "r3"]
    assert v["totali"]["r8"] == ["r7", "r6", "r1"]      # il totale verificato conta come un figlio solo
    assert v["non_verificati"] == [] and set(v["foglie"]) == {"r1", "r3", "r4", "r5", "r7"}


def test_mastri_asterisco_dopo_i_figli_e_rientro_che_deriva():
    righe = [riga(1, "COSTI DI IMPIANTO", "3763.44", codice="03/05/005", pc=3),
             riga(2, "COSTI DI IMPIANTO E AMPL.", "3763.44", codice="03/05/***", pc=2),
             riga(3, "SOFTWARE", "282.03", codice="03/15/010", pc=3),
             riga(4, "LICENZE", "11881.14", codice="03/15/015", pc=3),
             riga(5, "DIRITTI DI BREV.", "12163.17", codice="03/15/***", pc=2),
             riga(6, "IMMOB. IMMATERIALI", "15926.61", codice="03/**/***", pc=1)]
    v = individua_totali(righe)
    assert v["totali"]["r2"] == ["r1"] and v["totali"]["r5"] == ["r4", "r3"] and v["totali"]["r6"] == ["r5", "r2"]
    assert set(v["foglie"]) == {"r1", "r3", "r4"}
    # colonna unica: «II.» spostato di 1,5 pt rispetto a «I.» non rompe la struttura
    righe = [riga(1, "I. Immateriali", "100", x0=23.7), riga(2, "1) Costi", "100", x0=26.8),
             riga(3, "Costo storico", "100", x0=30.0), riga(4, "BI1 CONTO", "100", x0=35.2),
             riga(5, "II. Materiali", "50", x0=25.2), riga(6, "2) Impianti", "50", x0=28.4),
             riga(7, "Costo storico", "50", x0=31.6), riga(8, "BII2 CONTO", "50", x0=35.2)]
    v = individua_totali(righe)
    assert set(v["foglie"]) == {"r4", "r8"} and v["totali"]["r1"] == ["r2"] and v["totali"]["r5"] == ["r6"]


def test_totale_nominato_che_non_torna_e_dichiarato_e_non_e_foglia():
    righe = [riga(1, "a", "10"), riga(2, "b", "20"), riga(3, "Totale sezione", "35")]
    v = individua_totali(righe)
    assert v["non_verificati"] == [("r3", D("35"), D("30"))]
    assert set(v["foglie"]) == {"r1", "r2"}


def test_un_totale_nominato_che_segue_non_e_mai_figlio_di_una_foglia():
    # «altri 55.310» seguito da «Totale interessi 55.310»: la foglia resta foglia
    righe = [riga(1, "altri", "55310", x0=46, statement="ce", lato=None),
             riga(2, "Totale interessi e altri oneri finanziari", "55310", x0=42, statement="ce", lato=None)]
    v = individua_totali(righe)
    assert v["foglie"] == ["r1"] and v["totali"] == {"r2": ["r1"]}


def test_gruppi_separati_per_prospetto_e_lato():
    righe = [riga(1, "Clienti", "100", lato="attivo"), riga(2, "Fornitori", "100", lato="passivo"),
             riga(3, "Servizi", "100", lato="costi", statement="ce")]
    v = individua_totali(righe)
    assert v["totali"] == {} and set(v["foglie"]) == {"r1", "r2", "r3"}
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_verifica.py -v`
Expected: FAIL, `ModuleNotFoundError: importers.mappa_classificazione.verifica`

- [ ] **Step 3: Spostare il modulo e correggere l'import**

```bash
git mv tools/pilota_import/verifica.py importers/mappa_classificazione/verifica.py
```

In `importers/mappa_classificazione/verifica.py` sostituire `from lettore import Riga` con
`from importers.mappa_classificazione.lettore import Riga`.

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `pytest tests/test_mappa_verifica.py -v`
Expected: PASS (6 test). Se `test_totale_dopo_i_figli_prefisso_piu_corto` fallisce sull'ordine dei figli, l'asserzione va confrontata come insieme: l'ordine all'indietro è quello di lettura invertita e non è un contratto.

- [ ] **Step 5: Commit**

```bash
git add importers/mappa_classificazione/verifica.py tests/test_mappa_verifica.py
git commit -m "feat(import): verifica sui totali stampati, prefisso piu' corto che somma al centesimo"
```

---

### Task 4: Riconciliazione

**Files:**
- Move: `tools/pilota_import/riconcilia.py` → `importers/mappa_classificazione/riconcilia.py`
- Test: `tests/test_mappa_riconcilia.py`

**Interfaces:**
- Consumes: `Riga`; `genitore` di Task 3.
- Produces: `riconcilia(righe, foglie: set[str], codici: dict[str, str], genitore: dict[str, str] | None = None) -> dict` con `campi: dict[str, Decimal]` (codici brevi: `sp03b`, `ce06`), `aggregati: dict[str, Decimal]` (radici `sp03`, `ce06`), `per_riga: dict[str, tuple[str, Decimal]]`, `diagnostica: dict` (`totale_attivo, totale_passivo, sbilancio_sp, ricavi, costi, risultato_ce, sp13_letto, risultato_ce_stampato, sp13_da_ce?, non_classificate, avvisi`).

- [ ] **Step 1: Scrivere i test**

```python
# tests/test_mappa_riconcilia.py
from decimal import Decimal as D

from importers.mappa_classificazione.lettore import Riga
from importers.mappa_classificazione.riconcilia import riconcilia


def riga(i, testo, valore, lato, statement="sp"):
    return Riga(id=f"r{i}", pagina=1, posizione="unica", lato=lato, codice="", testo=testo, importi={},
                valore=D(valore), profondita_codice=0, profondita_rientro=1, y=float(i), x0=30.0,
                statement=statement)


def test_fondi_in_detrazione_qualunque_sia_il_segno():
    righe = [riga(1, "Impianti", "1000", "attivo"), riga(2, "F.do amm. impianti", "400", "passivo"),
             riga(3, "F.amm. licenze", "-100", "attivo"), riga(4, "Licenze", "300", "attivo")]
    r = riconcilia(righe, {"r1", "r2", "r3", "r4"}, {"r1": "sp03b", "r2": "fa03", "r3": "fa02", "r4": "sp02d"})
    assert r["campi"]["sp03b"] == D("1000") and r["campi"]["sp03"] == D("-400")
    assert r["aggregati"]["sp03"] == D("600") and r["aggregati"]["sp02"] == D("200")


def test_lato_dalla_colonna_con_classe_del_mastro_o_secchio():
    righe = [riga(1, "MUTUI", "500", "passivo"), riga(2, "Soci c/finanziamento", "500", "passivo"),
             riga(3, "Fornitori c/anticipi", "20", "attivo")]
    r = riconcilia(righe, {"r2", "r3"}, {"r1": "sp16a", "r2": "sp01a", "r3": "sp16d"}, genitore={"r2": "r1"})
    assert r["campi"] == {"sp16a": D("500"), "sp06g": D("20")}
    assert len(r["diagnostica"]["avvisi"]) == 2 and "dal mastro" in r["diagnostica"]["avvisi"][0]


def test_risultato_nel_ce_e_riga_di_pareggio_non_un_costo():
    righe = [riga(1, "Servizi", "700", "costi", "ce"), riga(2, "Utile del periodo", "300", "costi", "ce"),
             riga(3, "Ricavi", "1000", "ricavi", "ce"), riga(4, "Utile", "300", "passivo")]
    r = riconcilia(righe, {"r1", "r2", "r3", "r4"}, {"r1": "ce06", "r2": "sp13", "r3": "ce01", "r4": "sp13"})
    d = r["diagnostica"]
    assert d["costi"] == D("700") and d["risultato_ce"] == D("300") and d["risultato_ce_stampato"] == D("300")
    assert d["sp13_letto"] == D("300")


def test_na_con_importo_e_dichiarato_e_non_sommato():
    righe = [riga(1, "Totale attivo", "2000", "attivo"), riga(2, "Cassa", "10", "attivo")]
    r = riconcilia(righe, {"r1", "r2"}, {"r1": "na", "r2": "sp09"})
    assert r["aggregati"] == {"sp09": D("10")}
    assert r["diagnostica"]["non_classificate"] == [("r1", "attivo", "Totale attivo", D("2000"))]


def test_sp13_da_ce_quando_lo_sbilancio_coincide_col_risultato():
    righe = [riga(1, "Cassa", "1300", "attivo"), riga(2, "Capitale", "1000", "passivo"),
             riga(3, "Ricavi", "500", "ricavi", "ce"), riga(4, "Servizi", "200", "costi", "ce")]
    r = riconcilia(righe, {"r1", "r2", "r3", "r4"}, {"r1": "sp09", "r2": "sp11", "r3": "ce01", "r4": "ce06"})
    assert r["diagnostica"]["sbilancio_sp"] == D("300") and r["diagnostica"]["sp13_da_ce"] == D("300")
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_riconcilia.py -v`
Expected: FAIL, modulo mancante

- [ ] **Step 3: Spostare il modulo**

```bash
git mv tools/pilota_import/riconcilia.py importers/mappa_classificazione/riconcilia.py
```

Il modulo non importa altro. Verificare che `SECCHIO`, `FALLBACK_CE`, `CONTRA_DI`, `_lato_del_codice` e il ramo `codice == "sp13" and r.statement == "ce"` siano presenti (sono nel pilota dal commit 6e6035e).

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `pytest tests/test_mappa_riconcilia.py -v`
Expected: PASS (5 test)

- [ ] **Step 5: Commit**

```bash
git add importers/mappa_classificazione/riconcilia.py tests/test_mappa_riconcilia.py
git commit -m "feat(import): riconciliazione delle foglie classificate con netting e lato dalla colonna"
```

---

### Task 5: Client gx10 vincolato da regex

**Files:**
- Create: `importers/mappa_classificazione/llm_gx10.py`
- Modify: `config.py` (dopo la riga 214 `PDF_LLM_MAX_TOKENS = 8192`)
- Test: `tests/test_mappa_llm_gx10.py`

**Interfaces:**
- Produces: `ClientGx10(base_url: str | None = None, modello: str | None = None, chiave: str | None = None, timeout: float = 900.0, transport=None)`; `ClientGx10.completa_vincolato(prompt: str, regex: str, max_tokens: int) -> Risposta` con `Risposta(testo: str, token_in: int | None, token_out: int | None, secondi: float, finish: str | None)`; eccezione `Gx10Error(RuntimeError)`.

- [ ] **Step 1: Scrivere i test con `httpx.MockTransport`**

```python
# tests/test_mappa_llm_gx10.py
import json

import httpx
import pytest

from importers.mappa_classificazione.llm_gx10 import ClientGx10, Gx10Error


def _transport(catturato, status=200, contenuto="r1 sp09\n", finish="stop"):
    def handler(request):
        catturato["url"] = str(request.url)
        catturato["auth"] = request.headers.get("authorization")
        catturato["body"] = json.loads(request.content)
        if status != 200:
            return httpx.Response(status, text="errore")
        return httpx.Response(200, json={"choices": [{"message": {"content": contenuto}, "finish_reason": finish}],
                                         "usage": {"prompt_tokens": 12, "completion_tokens": 4}})
    return httpx.MockTransport(handler)


def test_invia_bearer_regex_e_thinking_spento(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", "segreta")
    c = {}
    client = ClientGx10(base_url="http://gx10:18300", modello="qwen", transport=_transport(c))
    r = client.completa_vincolato("prompt", r"r1 (sp09|na)\n", max_tokens=50)
    assert r.testo == "r1 sp09\n" and r.token_in == 12 and r.token_out == 4 and r.finish == "stop"
    assert c["url"] == "http://gx10:18300/v1/chat/completions" and c["auth"] == "Bearer segreta"
    b = c["body"]
    assert b["structured_outputs"] == {"regex": r"r1 (sp09|na)\n"} and b["temperature"] == 0
    assert b["chat_template_kwargs"] == {"enable_thinking": False} and b["max_tokens"] == 50
    assert b["messages"] == [{"role": "user", "content": "prompt"}] and b["model"] == "qwen"


def test_senza_chiave_solleva_senza_chiamare(monkeypatch):
    monkeypatch.delenv("GX10_API_KEY", raising=False)
    with pytest.raises(Gx10Error, match="GX10_API_KEY"):
        ClientGx10(base_url="http://gx10:18300", modello="qwen", transport=_transport({}))


def test_errore_http_non_espone_la_chiave(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", "segreta")
    client = ClientGx10(base_url="http://gx10:18300", modello="qwen", transport=_transport({}, status=500))
    with pytest.raises(Gx10Error) as exc:
        client.completa_vincolato("p", r"x\n", 10)
    assert "segreta" not in str(exc.value) and "500" in str(exc.value)


def test_risposta_troncata_e_un_errore(monkeypatch):
    monkeypatch.setenv("GX10_API_KEY", "segreta")
    client = ClientGx10(base_url="http://gx10:18300", modello="qwen", transport=_transport({}, finish="length"))
    with pytest.raises(Gx10Error, match="troncata"):
        client.completa_vincolato("p", r"x\n", 10)
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_llm_gx10.py -v`
Expected: FAIL, modulo mancante

- [ ] **Step 3: Aggiungere la configurazione e scrivere il client**

In `config.py`, dopo `PDF_LLM_MAX_TOKENS = 8192`:

```python
# Motore di import PDF «mappa» (spec 2026-09-22). "classico" = route attuali.
import os as _os
IMPORT_ENGINE = _os.environ.get("IMPORT_ENGINE", "classico")          # classico | mappa
MAPPA_MODEL = _os.environ.get("MAPPA_MODEL", "claude-sonnet-5")       # mappa della struttura
GX10_BASE_URL = _os.environ.get("GX10_BASE_URL", "http://100.65.63.12:18300")
GX10_MODEL = _os.environ.get("GX10_MODEL", "qwen3.8-flash-next")
# La chiave gx10 NON sta qui: GX10_API_KEY si legge al momento della chiamata (llm_gx10.py).
```

```python
# importers/mappa_classificazione/llm_gx10.py
"""Una chiamata a gx10 (vLLM, OpenAI-compatibile) con output vincolato da regex.

Su vLLM il tool forzato per nome non e' affidabile e /v1/messages non impone il
tool: la decodifica vincolata (structured_outputs) si'. Thinking spento e
temperatura 0: la classificazione non ha bisogno di ragionare, e senza
grammatica a sequenza fissa il modello senza thinking ripete l'ultima riga.
La chiave viaggia solo nell'header Bearer e non compare mai in errori o log.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

from config import GX10_BASE_URL, GX10_MODEL


class Gx10Error(RuntimeError):
    pass


@dataclass
class Risposta:
    testo: str
    token_in: int | None
    token_out: int | None
    secondi: float
    finish: str | None


class ClientGx10:
    def __init__(self, base_url: str | None = None, modello: str | None = None, chiave: str | None = None,
                 timeout: float = 900.0, transport=None):
        self.base_url = (base_url or GX10_BASE_URL).rstrip("/")
        self.modello = modello or GX10_MODEL
        self._chiave = chiave or os.environ.get("GX10_API_KEY", "")
        if not self._chiave:
            raise Gx10Error("GX10_API_KEY non impostata: il motore mappa richiede gx10")
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def completa_vincolato(self, prompt: str, regex: str, max_tokens: int) -> Risposta:
        body = {"model": self.modello, "temperature": 0, "max_tokens": max_tokens,
                "chat_template_kwargs": {"enable_thinking": False},
                "structured_outputs": {"regex": regex},
                "messages": [{"role": "user", "content": prompt}]}
        t0 = time.monotonic()
        try:
            r = self._client.post(f"{self.base_url}/v1/chat/completions",
                                  headers={"Authorization": "Bearer " + self._chiave}, json=body)
        except httpx.HTTPError as exc:
            raise Gx10Error(f"gx10 non raggiungibile: {type(exc).__name__}") from None
        if r.status_code != 200:
            raise Gx10Error(f"gx10 ha risposto {r.status_code}") from None
        d = r.json()
        scelta = d["choices"][0]
        finish = scelta.get("finish_reason")
        if finish == "length":
            raise Gx10Error("risposta gx10 troncata: max_tokens insufficiente")
        uso = d.get("usage") or {}
        return Risposta(testo=scelta["message"].get("content") or "", token_in=uso.get("prompt_tokens"),
                        token_out=uso.get("completion_tokens"), secondi=round(time.monotonic() - t0, 1),
                        finish=finish)
```

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `pytest tests/test_mappa_llm_gx10.py -v`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add config.py importers/mappa_classificazione/llm_gx10.py tests/test_mappa_llm_gx10.py
git commit -m "feat(import): client gx10 con output vincolato da regex, chiave solo da GX10_API_KEY"
```

---

### Task 6: Classificazione righe → codici

**Files:**
- Move: `tools/pilota_import/classifica.py` → `importers/mappa_classificazione/classifica.py`
- Test: `tests/test_mappa_classifica.py`

**Interfaces:**
- Consumes: `ClientGx10.completa_vincolato` (Task 5), `Riga` (Task 2).
- Produces: `legenda() -> list[tuple[str, str]]`; `classifica(righe: list[Riga], client=None, blocco: int = 110, concorrenza: int = 2) -> dict` con `codici: dict[str, str]`, `chiamate: list[dict]` (`blocco, righe, secondi, in, out, finish`), `righe_classificate: int`; costante `CONTRA: dict[str, str]`.

- [ ] **Step 1: Scrivere i test con un client finto**

```python
# tests/test_mappa_classifica.py
import re
from decimal import Decimal as D

from importers.mappa_classificazione.classifica import CONTRA, classifica, legenda
from importers.mappa_classificazione.lettore import Riga
from importers.mappa_classificazione.llm_gx10 import Risposta


def riga(i, testo, valore, lato="attivo", codice=""):
    return Riga(id=f"p1Ur{i}", pagina=1, posizione="unica", lato=lato, codice=codice, testo=testo, importi={},
                valore=D(valore) if valore is not None else None, profondita_codice=0, profondita_rientro=1,
                y=float(i), x0=30.0, intestazione=valore is None)


class ClientFinto:
    def __init__(self):
        self.chiamate = []

    def completa_vincolato(self, prompt, regex, max_tokens):
        self.chiamate.append((prompt, regex, max_tokens))
        ids = re.findall(r"^(p1Ur\d+) ", prompt, flags=re.M)
        return Risposta(testo="".join(f"{i} sp09\n" for i in ids), token_in=1, token_out=1, secondi=0.1, finish="stop")


def test_legenda_ha_i_codici_del_db_i_fondi_e_na():
    codici = dict(legenda())
    assert {"sp01", "sp02a", "sp16g", "ce01", "ce20", "na"} <= set(codici) and set(CONTRA) <= set(codici)
    assert codici["sp03b"] == "impianti macchinari"


def test_solo_le_righe_con_importo_con_intestazioni_come_contesto_e_regex_a_sequenza_fissa():
    righe = [riga(1, "B) Immobilizzazioni", None), riga(2, "Impianti", "10"), riga(3, "Cassa", "5")]
    client = ClientFinto()
    out = classifica(righe, client=client)
    assert out["codici"] == {"p1Ur2": "sp09", "p1Ur3": "sp09"} and out["righe_classificate"] == 2
    prompt, regex, max_tokens = client.chiamate[0]
    assert "# B) Immobilizzazioni\np1Ur2 [sp:attivo] Impianti" in prompt
    assert regex.startswith("p1Ur2 (") and regex.endswith("\\n") and regex.count("\\n") == 2
    assert "(...)+" not in regex and max_tokens == 40 * 2 + 200
    assert len(out["chiamate"]) == 1 and out["chiamate"][0]["righe"] == 2


def test_blocchi_di_110_righe_e_due_chiamate_in_parallelo():
    righe = [riga(i, f"Conto {i}", "1") for i in range(1, 251)]
    client = ClientFinto()
    out = classifica(righe, client=client, blocco=110)
    assert len(client.chiamate) == 3 and len(out["codici"]) == 250
    assert [c["blocco"] for c in out["chiamate"]] == [0, 1, 2]
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_classifica.py -v`
Expected: FAIL, modulo mancante

- [ ] **Step 3: Spostare il modulo e passare dal client**

```bash
git mv tools/pilota_import/classifica.py importers/mappa_classificazione/classifica.py
```

Poi, in `importers/mappa_classificazione/classifica.py`:

1. togliere `BASE`, `MODEL`, `_chiave()`, `LATO_CODICE`, `ATTIVO` e l'import di `subprocess`;
2. aggiungere `from importers.mappa_classificazione.llm_gx10 import ClientGx10`;
3. cambiare la firma in `def classifica(righe, client=None, blocco=110, concorrenza=2) -> dict:` e, come prima riga del corpo, `client = client or ClientGx10()`;
4. sostituire il corpo di `chiama` con:

```python
    def chiama(indice, rows):
        regex = "".join(f"{re.escape(r.id)} ({codici_ammessi})\\n" for r in rows)
        risposta = client.completa_vincolato(_prompt(voci, rows, contesto), regex, 40 * len(rows) + 200)
        chiamate.append({"blocco": indice, "righe": len(rows), "secondi": risposta.secondi,
                         "in": risposta.token_in, "out": risposta.token_out, "finish": risposta.finish})
        out = {}
        for line in risposta.testo.splitlines():
            parti = line.split()
            if len(parti) == 2:
                out[parti[0]] = parti[1]
        return out
```

5. togliere `import httpx` e `import time` dentro `classifica`.

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `pytest tests/test_mappa_classifica.py -v`
Expected: PASS (3 test)

- [ ] **Step 5: Commit**

```bash
git add importers/mappa_classificazione/classifica.py tests/test_mappa_classifica.py
git commit -m "feat(import): classificazione righe -> codici via gx10 con grammatica a sequenza fissa"
```

---

### Task 7: Mappa: schema, una chiamata per prospetto, riuso per intestazioni uguali

**Files:**
- Move: `tools/pilota_import/mappa.py` → `importers/mappa_classificazione/mappa.py`
- Test: `tests/test_mappa_mappa.py`

**Interfaces:**
- Consumes: `numero()` (Task 2) per contare gli importi di una pagina.
- Produces: `SCHEMA`, `PROMPT`, `mappa_pagina(client, png: bytes) -> dict`; `blocchi(pdf: str) -> list[Blocco]` con `Blocco(pagine: list[int], titolo: str | None, intestazione: str)`; `mappa_documento(pdf: str, mappa_pagina_fn=None, cache_dir: str | None = None) -> list[dict]` (una mappa per pagina, `pagina` 1-based, `continuazione` True sulle pagine riusate, `tipo_pagina = "nota_o_testo"` sulle pagine filtrate, `chiamate: int` in `mappe[0]["_chiamate"]`).

- [ ] **Step 1: Scrivere i test (Sonnet sostituito da una funzione finta)**

```python
# tests/test_mappa_mappa.py
from importers.mappa_classificazione.mappa import blocchi, mappa_documento
from tests._mappa_fixtures import MAPPA_COLONNA_UNICA, MAPPA_CONTRAPPOSTE, pdf_colonna_unica, pdf_contrapposte, pdf_xbrl_legge


def test_blocchi_filtro_prosa_e_confine_sp_ce(tmp_path):
    b = blocchi(pdf_xbrl_legge(str(tmp_path / "x.pdf")))
    assert [x.pagine for x in b] == [[1], [2]]                  # la pagina 3 (prosa) non entra
    assert b[0].titolo == "stato patrimoniale" and b[1].titolo == "conto economico"


def test_continuazione_riusa_la_mappa_senza_chiamare(tmp_path):
    path = pdf_colonna_unica(str(tmp_path / "u.pdf"))
    chiamate = []

    def finta(client, png):
        chiamate.append(png)
        return dict(MAPPA_COLONNA_UNICA)

    mappe = mappa_documento(path, mappa_pagina_fn=finta)
    assert len(chiamate) == 1 and [m["pagina"] for m in mappe] == [1, 2]
    assert mappe[1]["continuazione"] is True and mappe[1]["sezioni"] == MAPPA_COLONNA_UNICA["sezioni"]
    assert mappe[0]["_chiamate"] == 1


def test_una_chiamata_per_blocco_e_cache(tmp_path):
    path = pdf_contrapposte(str(tmp_path / "c.pdf"))
    n = {"v": 0}

    def finta(client, png):
        n["v"] += 1
        return dict(MAPPA_CONTRAPPOSTE)

    prima = mappa_documento(path, mappa_pagina_fn=finta, cache_dir=str(tmp_path / "cache"))
    seconda = mappa_documento(path, mappa_pagina_fn=finta, cache_dir=str(tmp_path / "cache"))
    assert n["v"] == 1 and prima == seconda and prima[0]["disposizione"] == "sezioni_contrapposte"


def test_mappa_pagina_produce_lo_schema(monkeypatch):
    from importers.mappa_classificazione import mappa as m

    class Blocco:
        type = "tool_use"
        input = {**MAPPA_CONTRAPPOSTE}

    class Uso:
        input_tokens, output_tokens = 3000, 500

    class Client:
        class messages:
            @staticmethod
            def create(**kw):
                assert kw["tool_choice"] == {"type": "tool", "name": "struttura"}
                assert kw["messages"][0]["content"][0]["type"] == "image"
                return type("R", (), {"content": [Blocco()], "usage": Uso()})()

    out = m.mappa_pagina(Client(), b"png")
    assert out["disposizione"] == "sezioni_contrapposte" and out["_token"] == {"in": 3000, "out": 500}
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_mappa.py -v`
Expected: FAIL, modulo mancante

- [ ] **Step 3: Spostare il modulo e aggiungere blocchi e riuso**

```bash
git mv tools/pilota_import/mappa.py importers/mappa_classificazione/mappa.py
```

In `importers/mappa_classificazione/mappa.py`: sostituire `MODELLO = os.environ.get("MAPPA_MODEL", "claude-sonnet-5")` con `from config import MAPPA_MODEL as MODELLO`; sostituire `mappa_documento` con il codice seguente e aggiungere `blocchi`, `_intestazione_pagina`, `_importi_pagina`:

```python
import re
from dataclasses import dataclass

from importers.mappa_classificazione.lettore import NUM_SEP

TITOLI_SP = re.compile(r"stato patrimoniale|attivit[aà]'?\s|passivit[aà]|situazione patrimoniale", re.I)
TITOLI_CE = re.compile(r"conto economico|situazione economica|costi\b.*\bricavi|a\) valore della produzione", re.I)
MIN_IMPORTI = 5


@dataclass
class Blocco:
    pagine: list
    titolo: str | None       # "stato patrimoniale" | "conto economico" | None
    intestazione: str        # riga delle intestazioni di colonna, normalizzata


def _importi_pagina(page) -> int:
    return sum(1 for w in page.get_text("words") if NUM_SEP.match(w[4]))


def _titolo_pagina(page) -> str | None:
    testo = page.get_text()[:1500]
    if TITOLI_CE.search(testo):
        return "conto economico"
    if TITOLI_SP.search(testo):
        return "stato patrimoniale"
    return None


def _intestazione_pagina(page) -> str:
    """La prima riga di testo che contiene almeno due parole di intestazione tipiche, normalizzata;
    vuota se la pagina non ristampa le intestazioni (continuazione)."""
    chiavi = ("saldo", "importo", "descrizione", "conto", "dare", "avere", "rettifiche", "corrente", "precedente",
              "esercizio", "31-12", "31/12", "30-06", "30/06")
    righe = {}
    for w in page.get_text("words"):
        righe.setdefault(round(w[1] / 4), []).append(w[4].lower())
    for y in sorted(righe):
        parole = righe[y]
        if sum(1 for p in parole if any(k in p for k in chiavi)) >= 2:
            return " ".join(parole)
    return ""


def blocchi(pdf: str) -> list[Blocco]:
    """Pagine con importi, divise ai titoli di prospetto e alle intestazioni di colonna diverse."""
    import fitz
    out: list[Blocco] = []
    with fitz.open(pdf) as doc:
        for page in doc:
            if _importi_pagina(page) < MIN_IMPORTI:
                continue
            titolo, intestazione = _titolo_pagina(page), _intestazione_pagina(page)
            precedente = out[-1] if out else None
            stesso = (precedente is not None
                      and (titolo is None or titolo == precedente.titolo)
                      and (intestazione == "" or intestazione == precedente.intestazione))
            if stesso:
                precedente.pagine.append(page.number + 1)
            else:
                out.append(Blocco([page.number + 1], titolo or (precedente.titolo if precedente else None), intestazione))
    return out


def mappa_documento(pdf: str, mappa_pagina_fn=None, cache_dir: str | None = None, concorrenza: int = 6) -> list[dict]:
    """Una mappa per pagina, con UNA chiamata al modello per blocco: le pagine seguenti del
    blocco riusano la mappa con continuazione=True; le pagine senza importi sono nota_o_testo."""
    cache = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache = os.path.join(cache_dir, os.path.basename(pdf) + ".mappa.json")
        if os.path.exists(cache):
            with open(cache, encoding="utf-8") as fh:
                return json.load(fh)
    import fitz
    fn = mappa_pagina_fn or mappa_pagina
    gruppi = blocchi(pdf)
    client = None if mappa_pagina_fn else _client()
    with fitz.open(pdf) as doc:
        n_pagine = doc.page_count
        prime = [doc[b.pagine[0] - 1].get_pixmap(dpi=110).tobytes("png") for b in gruppi]
    with ThreadPoolExecutor(max_workers=concorrenza) as pool:
        mappe_blocco = list(pool.map(lambda png: fn(client, png), prime))
    mappe = [{"pagina": i + 1, "tipo_pagina": "nota_o_testo", "disposizione": "colonna_unica",
              "schema": "elenco_piatto", "sezioni": [], "continuazione": False, "codici_conto": False,
              "totali_stampati": False, "anno_precedente": False, "negativi": "non_visibile",
              "fondi_ammortamento": "assenti", "note": "filtrata: nessun importo"} for i in range(n_pagine)]
    for blocco, mappa in zip(gruppi, mappe_blocco):
        for k, pagina in enumerate(blocco.pagine):
            mappe[pagina - 1] = {**mappa, "pagina": pagina, "continuazione": k > 0}
    mappe[0]["_chiamate"] = len(gruppi)
    if cache:
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(mappe, fh, ensure_ascii=False, indent=1)
    return mappe
```

`render_pagine` non serve più: cancellarla. `mappa_pagina(client, png)` resta com'è nel pilota.

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `pytest tests/test_mappa_mappa.py -v`
Expected: PASS (4 test). Se `test_blocchi_filtro_prosa_e_confine_sp_ce` trova un solo blocco, il titolo del CE sintetico non è stato riconosciuto: il `_titolo_pagina` legge i primi 1500 caratteri e la pagina del CE inizia con «Conto economico»; verificare con `page.get_text()[:200]`.

- [ ] **Step 5: Commit**

```bash
git add importers/mappa_classificazione/mappa.py tests/test_mappa_mappa.py
git commit -m "feat(import): mappa della struttura con una chiamata per prospetto e riuso per intestazioni uguali"
```

---

### Task 8: Xbrl di legge senza modello: mappa e classificazione deterministiche

**Files:**
- Modify: `importers/mappa_classificazione/mappa.py` (aggiungere `e_xbrl_di_legge`, `mappa_xbrl`)
- Create: `importers/mappa_classificazione/legge.py`
- Test: `tests/test_mappa_legge.py`

**Interfaces:**
- Consumes: `blocchi()` (Task 7), `iv_cee_hierarchy.resolve(desc, side, statement) -> Node | None` (esistente, `Node.db_field`, `Node.scadenza`, `Node.is_total`, `Node.is_result`), `iv_cee_hierarchy._apply_scadenza(field, scad)`.
- Produces: `e_xbrl_di_legge(pdf: str) -> bool`; `mappa_xbrl(pdf: str) -> list[dict]` (mappe con `tipo_pagina` prospetto_sp/prospetto_ce, `schema = "iv_cee_di_legge"`, colonne = le due date in ordine, `contenuto = "misto"`); `classifica_legge(righe: list[Riga]) -> dict` con `codici: dict[str, str]` (codici brevi; `na` per totali di sezione; una riga non risolta manca dal dizionario), `non_risolte: list[str]`.

- [ ] **Step 1: Scrivere i test**

```python
# tests/test_mappa_legge.py
from decimal import Decimal as D

from importers.mappa_classificazione.legge import classifica_legge
from importers.mappa_classificazione.lettore import Riga, leggi_documento
from importers.mappa_classificazione.mappa import e_xbrl_di_legge, mappa_xbrl
from tests._mappa_fixtures import pdf_contrapposte, pdf_xbrl_legge


def test_riconosce_il_pie_di_pagina_della_tassonomia(tmp_path):
    assert e_xbrl_di_legge(pdf_xbrl_legge(str(tmp_path / "x.pdf"))) is True
    assert e_xbrl_di_legge(pdf_contrapposte(str(tmp_path / "c.pdf"))) is False


def test_mappa_xbrl_senza_modello(tmp_path):
    mappe = mappa_xbrl(pdf_xbrl_legge(str(tmp_path / "x.pdf")))
    assert [m["tipo_pagina"] for m in mappe] == ["prospetto_sp", "prospetto_ce", "nota_o_testo"]
    assert mappe[0]["schema"] == "iv_cee_di_legge" and mappe[0]["codici_conto"] is False
    assert [c["intestazione"] for c in mappe[0]["sezioni"][0]["colonne"]] == ["31-12-2025", "31-12-2024"]
    assert [c["ruolo"] for c in mappe[0]["sezioni"][0]["colonne"]] == ["saldo_corrente", "saldo_precedente"]
    assert mappe[0]["negativi"] == "parentesi"


def test_classifica_legge_per_tabella(tmp_path):
    path = pdf_xbrl_legge(str(tmp_path / "x.pdf"))
    righe = leggi_documento(path, mappa_xbrl(path))
    out = classifica_legge(righe)
    per_testo = {r.testo: out["codici"].get(r.id) for r in righe if r.valore is not None}
    assert per_testo["I - Immobilizzazioni immateriali"] == "sp02"
    assert per_testo["II - Immobilizzazioni materiali"] == "sp03"
    assert per_testo["IV - Disponibilita' liquide"] == "sp09"
    assert per_testo["I - Capitale"] == "sp11" and per_testo["IX - Utile (perdita) dell'esercizio"] == "sp13"
    assert per_testo["1) ricavi delle vendite e delle prestazioni"] == "ce01"
    assert per_testo["7) per servizi"] == "ce06" and per_testo["a) salari e stipendi"] == "ce08b"
    assert per_testo["20) Imposte sul reddito dell'esercizio"] == "ce20"
    assert per_testo["Totale attivo"] == "na" and per_testo["Totale crediti"] == "na"
    # «esigibili entro» prende il lato e la scadenza dal contesto: crediti nell'attivo, debiti nel passivo
    entro = [r for r in righe if r.testo == "esigibili entro l'esercizio successivo"]
    assert out["codici"][entro[0].id] == "sp06" and out["codici"][entro[1].id] == "sp16"
    oltre = next(r for r in righe if r.testo == "esigibili oltre l'esercizio successivo")
    assert out["codici"][oltre.id] == "sp07"
    assert out["non_risolte"] == []
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_legge.py -v`
Expected: FAIL, `ImportError: e_xbrl_di_legge`

- [ ] **Step 3: Scrivere `mappa_xbrl` e `classifica_legge`**

In `importers/mappa_classificazione/mappa.py`:

```python
PIE_TASSONOMIA = re.compile(r"conforme alla tassonomia|generato automaticamente|itcc-ci-", re.I)
DATA = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}$")


def e_xbrl_di_legge(pdf: str) -> bool:
    import fitz
    with fitz.open(pdf) as doc:
        return any(PIE_TASSONOMIA.search(doc[i].get_text()) for i in range(min(3, doc.page_count)))


def mappa_xbrl(pdf: str) -> list[dict]:
    """Mappa deterministica per i PDF generati dalla tassonomia: prospetti dai titoli,
    colonne dalle due date stampate in testa. Le pagine di nota restano nota_o_testo."""
    import fitz
    mappe = []
    with fitz.open(pdf) as doc:
        for page in doc:
            base = {"pagina": page.number + 1, "tipo_pagina": "nota_o_testo", "disposizione": "colonna_unica",
                    "schema": "iv_cee_di_legge", "sezioni": [], "continuazione": False, "codici_conto": False,
                    "totali_stampati": True, "anno_precedente": False, "negativi": "parentesi",
                    "fondi_ammortamento": "assenti", "note": "xbrl di legge, mappa deterministica"}
            titolo = _titolo_pagina(page)
            date = [w[4] for w in sorted(page.get_text("words"), key=lambda w: (w[1], w[0])) if DATA.match(w[4])]
            if titolo and _importi_pagina(page) >= MIN_IMPORTI and date:
                colonne = [{"ruolo": "saldo_corrente", "intestazione": date[0]}]
                if len(date) > 1 and date[1] != date[0]:
                    colonne.append({"ruolo": "saldo_precedente", "intestazione": date[1]})
                base.update(tipo_pagina="prospetto_sp" if titolo == "stato patrimoniale" else "prospetto_ce",
                            sezioni=[{"posizione": "unica", "contenuto": "misto", "colonne": colonne}],
                            anno_precedente=len(colonne) > 1)
            mappe.append(base)
    return mappe
```

```python
# importers/mappa_classificazione/legge.py
"""Classificazione per tabella delle voci dello schema di legge (art. 2424/2425).

Le etichette sono standard e `iv_cee_hierarchy` le risolve gia': qui non serve un
modello. Una riga che la tabella non riconosce resta fuori dal dizionario, e il
motore la manda a Qwen con le altre. I totali di sezione sono `na`: la verifica
(verifica.py) li ha gia' riconosciuti come totali e non entrano nelle foglie.
"""
from __future__ import annotations

import re

from importers.iv_cee_hierarchy import _apply_scadenza, resolve

TOTALE = re.compile(r"^\W*totale\b|^differenza tra valore|^risultato prima delle imposte", re.I)
ENTRO = re.compile(r"esigibili entro", re.I)
OLTRE = re.compile(r"esigibili oltre", re.I)


def _breve(db_field: str) -> str:
    return db_field.split("_", 1)[0]


def classifica_legge(righe) -> dict:
    codici, non_risolte = {}, []
    ultimo_padre = None          # l'ultima intestazione o voce di livello superiore letta (per «esigibili entro/oltre»)
    for r in sorted(righe, key=lambda r: (r.pagina, r.y)):
        if r.valore is None:
            nodo = resolve(r.testo, side=r.lato, statement="bs" if r.statement == "sp" else "ce")
            if nodo is not None and nodo.db_field:
                ultimo_padre = nodo
            continue
        if TOTALE.match(r.testo):
            codici[r.id] = "na"
            continue
        if ENTRO.search(r.testo) or OLTRE.search(r.testo):
            if ultimo_padre is None or not ultimo_padre.db_field:
                non_risolte.append(r.id)
                continue
            campo = _apply_scadenza(ultimo_padre.db_field, "oltre" if OLTRE.search(r.testo) else "entro")
            codici[r.id] = _breve(campo)
            continue
        nodo = resolve(r.testo, side=r.lato, statement="bs" if r.statement == "sp" else "ce")
        if nodo is None or not nodo.db_field:
            non_risolte.append(r.id)
            continue
        codici[r.id] = _breve(nodo.db_field)
        if not nodo.is_legal_leaf:
            ultimo_padre = nodo
    return {"codici": codici, "non_risolte": non_risolte}
```

Se `_apply_scadenza("sp06_crediti_breve", "oltre")` non restituisce `sp07_crediti_lungo`, leggere `importers/iv_cee_hierarchy.py:225` e adattare la chiamata alla firma reale: il contratto di questo task è il codice breve restituito, non il nome dell'helper.

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `pytest tests/test_mappa_legge.py -v`
Expected: PASS (3 test). Se una voce risulta `non_risolta`, l'alias manca in `data/iv_cee_tree.json`. Le etichette dello schema di legge (es. «IV - Disponibilita' liquide», «20) Imposte sul reddito dell'esercizio», «21) Utile (perdita) dell'esercizio») SONO di livello legale: aggiungerle come alias del nodo giusto è lecito e va fatto qui, perché in Task 9 una foglia non risolta andrebbe a Qwen e il test dell'xbrl senza modelli fallirebbe. **Mai** alias di sotto-conto (CLAUDE.md: il tree resta di livello legale, o l'aggregazione piatta delle route A/B raddoppia gli importi).

- [ ] **Step 5: Commit**

```bash
git add importers/mappa_classificazione/mappa.py importers/mappa_classificazione/legge.py tests/test_mappa_legge.py
git commit -m "feat(import): xbrl di legge per titoli e tabella delle voci, senza modello"
```

---

### Task 9: Motore `estrai()`

**Files:**
- Create: `importers/mappa_classificazione/engine.py`
- Modify: `importers/mappa_classificazione/__init__.py`
- Test: `tests/test_mappa_engine.py`

**Interfaces:**
- Consumes: tutto quanto sopra.
- Produces: `estrai(file_path: str, *, period_months: int | None = None, mappa_fn=None, classifica_fn=None, cache_dir: str | None = None) -> Estrazione`; `Estrazione(bs: dict[str, Decimal], ce: dict[str, Decimal], prior_bs: dict | None, prior_ce: dict | None, rapporto: dict)`; `MappaError(RuntimeError)`; `CAMPO_DA_CODICE: dict[str, str]` (`"sp03b" -> "sp03b_impianti_macchinari"`).

I dizionari `bs`/`ce` usano le colonne del DB e portano le chiavi diagnostiche `_mappa_totali_verificati`, `_mappa_totali_non_verificati`, `_mappa_sbilancio_sp`, `_mappa_righe_na_con_importo` (Decimal, anche a zero: «un estrattore dichiara sempre le proprie chiavi diagnostiche»). `prior_*` sono `None` in questo piano (l'anno precedente è letto dalla colonna ma non riconciliato: piano 2).

- [ ] **Step 1: Scrivere i test (mappa e classificatore finti; xbrl senza finti)**

```python
# tests/test_mappa_engine.py
from decimal import Decimal as D

import pytest

from importers.mappa_classificazione import Estrazione, MappaError, estrai
from importers.mappa_classificazione.engine import CAMPO_DA_CODICE
from tests._mappa_fixtures import MAPPA_CONTRAPPOSTE, pdf_contrapposte, pdf_xbrl_legge

CLASSI_CONTRAPPOSTE = {"IMMOBILIZZAZIONI MATERIALI": "sp03", "IMPIANTI": "sp03b", "Impianti generici": "sp03b",
                       "ATTREZZATURE": "sp03c", "Attrezzatura varia": "sp03c", "CREDITI COMMERCIALI": "sp06",
                       "Clienti Italia": "sp06a", "DISPONIBILITA' LIQUIDE": "sp09", "Banca c/c": "sp09",
                       "CAPITALE E RISERVE": "sp11", "Capitale sociale": "sp11", "DEBITI COMMERCIALI": "sp16",
                       "Fornitori Italia": "sp16d", "FONDI AMMORTAMENTO": "fa03", "F.do amm. impianti": "fa03",
                       "Utile del periodo": "sp13", "Totale a pareggio": "na"}


def classificatore_finto(righe, **kw):
    return {"codici": {r.id: CLASSI_CONTRAPPOSTE[r.testo] for r in righe if r.valore is not None},
            "chiamate": [{"blocco": 0, "righe": 17, "secondi": 0.1, "in": 1, "out": 1, "finish": "stop"}],
            "righe_classificate": 17}


def test_contrapposte_quadra_e_dichiara(tmp_path):
    path = pdf_contrapposte(str(tmp_path / "c.pdf"))
    e = estrai(path, mappa_fn=lambda pdf, **kw: [MAPPA_CONTRAPPOSTE], classifica_fn=classificatore_finto)
    assert isinstance(e, Estrazione) and e.prior_bs is None
    assert e.bs["sp03b_impianti_macchinari"] == D("1000") and e.bs["sp03c_attrezzature"] == D("500")
    assert e.bs["sp03_immob_materiali"] == D("1100")             # 1.500 lordi meno 400 di fondo
    assert e.bs["sp06_crediti_breve"] == D("800") and e.bs["sp06a_crediti_clienti_breve"] == D("800")
    assert e.bs["sp09_disponibilita_liquide"] == D("250") and e.bs["sp13_utile_perdita"] == D("250")
    assert e.bs["sp16_debiti_breve"] == D("900") and e.bs["sp16d_debiti_fornitori_breve"] == D("900")
    assert e.bs["_mappa_sbilancio_sp"] == D("0") and e.bs["_mappa_totali_non_verificati"] == D("0")
    # 05, 05.01, 05.03, 11, 19, 23, 33, 41 e «Totale a pareggio» (= utile + 41 + 33 + 23)
    assert e.rapporto["metodo"] == "mappa_classificazione" and e.rapporto["totali_verificati"] == 9
    assert e.rapporto["chiamate_mappa"] == 0 and e.rapporto["pagine_lette"] == [1]


def test_xbrl_di_legge_senza_alcun_modello(tmp_path):
    path = pdf_xbrl_legge(str(tmp_path / "x.pdf"))
    e = estrai(path, classifica_fn=lambda righe, **kw: pytest.fail("Qwen non deve essere chiamato"),
               mappa_fn=lambda pdf, **kw: pytest.fail("Sonnet non deve essere chiamato"))
    assert e.bs["sp02_immob_immateriali"] == D("100") and e.bs["sp03_immob_materiali"] == D("900")
    assert e.bs["sp06_crediti_breve"] == D("600") and e.bs["sp07_crediti_lungo"] == D("100")
    assert e.bs["sp09_disponibilita_liquide"] == D("300") and e.bs["sp16_debiti_breve"] == D("800")
    assert e.bs["sp11_capitale"] == D("1000") and e.bs["sp13_utile_perdita"] == D("200")
    assert e.ce["ce01_ricavi_vendite"] == D("3000") and e.ce["ce06_servizi"] == D("2000")
    assert e.ce["ce08b_salari_stipendi"] == D("500") and e.ce["ce20_imposte"] == D("300")
    assert e.bs["_mappa_sbilancio_sp"] == D("0") and e.rapporto["classificazione"] == "tabella_di_legge"


def test_senza_pagine_leggibili_solleva(tmp_path):
    import fitz
    doc = fitz.open(); doc.new_page(); doc.save(str(tmp_path / "vuoto.pdf"))
    with pytest.raises(MappaError, match="nessuna pagina"):
        estrai(str(tmp_path / "vuoto.pdf"), mappa_fn=lambda pdf, **kw: [], classifica_fn=classificatore_finto)


def test_campo_da_codice_copre_tutte_le_colonne():
    assert CAMPO_DA_CODICE["sp03b"] == "sp03b_impianti_macchinari" and CAMPO_DA_CODICE["ce20"] == "ce20_imposte"
    assert len(CAMPO_DA_CODICE) == 114
```

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_engine.py -v`
Expected: FAIL, `ImportError: cannot import name 'estrai'`

- [ ] **Step 3: Scrivere il motore**

```python
# importers/mappa_classificazione/engine.py
"""Orchestrazione: mappa -> lettura -> verifica -> classificazione -> riconciliazione.

Restituisce i dizionari con le colonne del DB e un rapporto. Non scrive nulla,
non inventa nulla: i divari sono chiavi diagnostiche e avvisi.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from decimal import Decimal

from importers.mappa_classificazione.classifica import classifica
from importers.mappa_classificazione.legge import classifica_legge
from importers.mappa_classificazione.lettore import leggi_documento
from importers.mappa_classificazione.mappa import e_xbrl_di_legge, mappa_documento, mappa_xbrl
from importers.mappa_classificazione.riconcilia import riconcilia
from importers.mappa_classificazione.verifica import individua_totali


class MappaError(RuntimeError):
    pass


@dataclass
class Estrazione:
    bs: dict
    ce: dict
    prior_bs: dict | None
    prior_ce: dict | None
    rapporto: dict = field(default_factory=dict)


def _campi_db() -> dict[str, str]:
    from database.models import BalanceSheet, IncomeStatement
    out = {}
    for tabella in (BalanceSheet, IncomeStatement):
        for c in tabella.__table__.columns:
            if re.match(r"^(sp|ce)\d\d", c.name):
                out[c.name.split("_", 1)[0]] = c.name
    return out


CAMPO_DA_CODICE = _campi_db()
TIPI_PROSPETTO = ("prospetto_sp", "prospetto_ce", "prospetto_sp_e_ce")


def estrai(file_path: str, *, period_months=None, mappa_fn=None, classifica_fn=None, cache_dir=None) -> Estrazione:
    tempi, t = {}, time.monotonic()
    xbrl = e_xbrl_di_legge(file_path)
    if xbrl:
        mappe = mappa_xbrl(file_path)
    else:
        mappe = (mappa_fn or mappa_documento)(file_path, cache_dir=cache_dir)
    tempi["mappa"] = round(time.monotonic() - t, 1)
    if not any(m.get("tipo_pagina") in TIPI_PROSPETTO for m in mappe):
        raise MappaError("nessuna pagina di prospetto riconosciuta")
    t = time.monotonic()
    righe = leggi_documento(file_path, mappe)
    if not any(r.valore is not None for r in righe):
        raise MappaError("nessuna pagina con importi leggibili")
    ver = individua_totali(righe)
    foglie = set(ver["foglie"])
    tempi["lettura_verifica"] = round(time.monotonic() - t, 1)

    t = time.monotonic()
    codici, chiamate, metodo_cls = {}, [], "tabella_di_legge"
    if xbrl:
        tabella = classifica_legge(righe)
        codici = tabella["codici"]
        residue = [r for r in righe if r.id in foglie and r.id not in codici]
    else:
        residue = [r for r in righe if r.valore is not None]
    if residue:
        metodo_cls = "tabella_di_legge+qwen" if xbrl else "qwen"
        esito = (classifica_fn or classifica)(righe if not xbrl else residue)
        codici.update(esito["codici"])
        chiamate = esito["chiamate"]
    tempi["classificazione"] = round(time.monotonic() - t, 1)

    ric = riconcilia(righe, foglie, codici, ver["genitore"])
    d = ric["diagnostica"]
    bs, ce = {}, {}
    for codice, valore in ric["campi"].items():
        campo = CAMPO_DA_CODICE.get(codice)
        if campo is None:
            continue
        (bs if campo.startswith("sp") else ce)[campo] = valore
    for radice, valore in ric["aggregati"].items():
        campo = CAMPO_DA_CODICE.get(radice)
        if campo:
            (bs if campo.startswith("sp") else ce)[campo] = valore
    if "sp13_utile_perdita" not in bs and "sp13_da_ce" in d:
        bs["sp13_utile_perdita"] = d["sp13_da_ce"]
    bs["_mappa_totali_verificati"] = Decimal(len(ver["totali"]))
    bs["_mappa_totali_non_verificati"] = Decimal(len(ver["non_verificati"]))
    # un risultato non stampato nello SP ma spiegato dal CE non e' uno sbilancio
    bs["_mappa_sbilancio_sp"] = d["sbilancio_sp"] - (d["sp13_da_ce"] if "sp13" not in ric["aggregati"] and "sp13_da_ce" in d else Decimal(0))
    bs["_mappa_righe_na_con_importo"] = Decimal(len(d["non_classificate"]))
    rapporto = {
        "metodo": "mappa_classificazione", "xbrl_di_legge": xbrl, "classificazione": metodo_cls,
        "pagine_lette": sorted({r.pagina for r in righe}),
        "chiamate_mappa": 0 if xbrl else (mappe[0].get("_chiamate", 0) if mappe else 0),
        "chiamate_classificazione": chiamate, "tempi": tempi,
        "totali_verificati": len(ver["totali"]),
        "totali_non_verificati": [(rid, str(v), None if s is None else str(s)) for rid, v, s in ver["non_verificati"]],
        "somme": {k: str(v) for k, v in d.items() if isinstance(v, Decimal)},
        "avvisi": list(d["avvisi"]),
        "righe_na_con_importo": [(rid, lato, testo, str(v)) for rid, lato, testo, v in d["non_classificate"]],
        "warnings": [],
    }
    for rid, v, s in ver["non_verificati"]:
        r = next(x for x in righe if x.id == rid)
        rapporto["warnings"].append(f"TOTALE NON VERIFICATO «{r.testo[:50]}» pag. {r.pagina}: stampato {v}, somma delle righe {s}")
    if bs["_mappa_sbilancio_sp"] != 0:
        rapporto["warnings"].append(f"SBILANCIO SP dopo la riconciliazione: {bs['_mappa_sbilancio_sp']}")
    return Estrazione(bs=bs, ce=ce, prior_bs=None, prior_ce=None, rapporto=rapporto)
```

`importers/mappa_classificazione/__init__.py`:

```python
"""Motore di import PDF: mappa della struttura, lettura verificata, classificazione locale.

Spec: docs/superpowers/specs/2026-09-22-import-mappa-classificazione-design.md
"""
from importers.mappa_classificazione.engine import Estrazione, MappaError, estrai

__all__ = ["Estrazione", "MappaError", "estrai"]
```

- [ ] **Step 4: Eseguire i test e vederli passare**

Run: `pytest tests/test_mappa_engine.py -v`
Expected: PASS (4 test). Se `test_contrapposte_quadra_e_dichiara` dà `sp03_immob_materiali == 1500`: il fondo del passivo (`fa03`) non è arrivato come foglia; controllare che «FONDI AMMORTAMENTO» (mastro) sia stato verificato come totale di «F.do amm. impianti» e che la foglia sia la seconda.

- [ ] **Step 5: Commit**

```bash
git add importers/mappa_classificazione/engine.py importers/mappa_classificazione/__init__.py tests/test_mappa_engine.py
git commit -m "feat(import): motore estrai() con dizionari del DB, chiavi diagnostiche e rapporto"
```

---

### Task 10: Integrazione in `pdf_importer` dietro `IMPORT_ENGINE=mappa`

**Files:**
- Modify: `importers/pdf_importer.py` (righe 23, 1216-1232, 1502, 1566-1571, 1788-1792)
- Test: `tests/test_mappa_import_integration.py`

**Interfaces:**
- Consumes: `estrai`, `MappaError` (Task 9), `config.IMPORT_ENGINE`.
- Produces: `validation_report["mappa_classificazione"]` (il `rapporto` del motore) e i suoi `warnings` nel report; `_PDF_PARSER_VERSION = "mappa-classificazione-v1-2026-09-22"` quando il motore ha prodotto i numeri, altrimenti il valore attuale.

- [ ] **Step 1: Scrivere il test di integrazione sul DB in memoria**

```python
# tests/test_mappa_import_integration.py
"""Il motore mappa dentro import_pdf_balance_sheet, sul DB in memoria di _import_probe."""
from decimal import Decimal as D

import pytest

from tests import _import_probe
from tests._mappa_fixtures import MAPPA_CONTRAPPOSTE, pdf_contrapposte
from tests.test_mappa_engine import classificatore_finto


@pytest.fixture(autouse=True)
def niente_rete(monkeypatch):
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: pytest.fail("chiamata Anthropic inattesa"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "finta")


def test_motore_mappa_salva_i_numeri_e_il_rapporto(tmp_path, monkeypatch):
    import config
    from importers import pdf_importer
    from importers.mappa_classificazione import engine
    monkeypatch.setattr(config, "IMPORT_ENGINE", "mappa")
    monkeypatch.setattr(pdf_importer, "IMPORT_ENGINE", "mappa", raising=False)
    monkeypatch.setattr(engine, "mappa_documento", lambda pdf, **kw: [MAPPA_CONTRAPPOSTE])
    monkeypatch.setattr(engine, "classifica", classificatore_finto)
    path = pdf_contrapposte(str(tmp_path / "c.pdf"))
    rec = _import_probe.probe(path, "standard", fiscal_year=2026, period_months=6)
    assert rec["ok"], rec.get("error")
    assert D(rec["fields"]["sp03_immob_materiali"]) == D("1100") and D(rec["fields"]["sp16d_debiti_fornitori_breve"]) == D("900")
    assert rec["validation_report"]["mappa_classificazione"]["metodo"] == "mappa_classificazione"
    assert rec["parser_version"] == "mappa-classificazione-v1-2026-09-22"


def test_motore_spento_non_cambia_nulla(tmp_path, monkeypatch):
    monkeypatch.setattr("importers.mappa_classificazione.estrai", lambda *a, **k: pytest.fail("il motore mappa non deve girare"))
    path = pdf_contrapposte(str(tmp_path / "c.pdf"))
    rec = _import_probe.probe(path, "standard", fiscal_year=2026, period_months=6)
    assert "mappa_classificazione" not in (rec.get("validation_report") or {})


def test_errore_del_motore_e_dichiarato_e_si_prosegue(tmp_path, monkeypatch):
    import config
    from importers import pdf_importer
    from importers.mappa_classificazione import engine
    monkeypatch.setattr(config, "IMPORT_ENGINE", "mappa")
    monkeypatch.setattr(pdf_importer, "IMPORT_ENGINE", "mappa", raising=False)
    monkeypatch.setattr(engine, "mappa_documento", lambda pdf, **kw: [])
    path = pdf_contrapposte(str(tmp_path / "c.pdf"))
    rec = _import_probe.probe(path, "standard", fiscal_year=2026, period_months=6)
    warnings = (rec.get("validation_report") or {}).get("warnings", []) + (rec.get("warnings") or [])
    assert any("MOTORE MAPPA" in w for w in warnings)
```

Prima di scrivere il test leggere `tests/_import_probe.py` (funzione `probe`) per i nomi esatti delle chiavi restituite (`fields`, `validation_report`, `parser_version`): se `parser_version` non è nel record, aggiungerla al probe leggendo `FinancialYear.pdf_parser_version` (o il nome reale della colonna, `grep -n parser_version database/models.py`).

- [ ] **Step 2: Eseguire i test e vederli fallire**

Run: `pytest tests/test_mappa_import_integration.py -v`
Expected: FAIL: il primo test trova i numeri della route classica (che per un PDF sintetico senza Haiku fallisce o dà altro), il terzo non trova l'avviso.

- [ ] **Step 3: Cablare il motore in `import_pdf_balance_sheet`**

1. In testa a `importers/pdf_importer.py`, dopo `from config import Sector` (riga 19): `from config import IMPORT_ENGINE`.
2. Riga 23: lasciare `_PDF_PARSER_VERSION = "macro-fallback-v8-2026-09-21"` e aggiungere `_PDF_PARSER_VERSION_MAPPA = "mappa-classificazione-v1-2026-09-22"`.
3. Subito prima del blocco `_source_candidates = []` (riga 1220), inserire:

```python
        # Motore «mappa» (spec 2026-09-22): acceso per configurazione, solo su PDF nativi.
        # Se produce i numeri, le route sotto non girano; se fallisce, lo dichiara e si prosegue.
        _mappa_estrazione = None
        _mappa_report = {}
        if IMPORT_ENGINE == "mappa" and not is_scanned and not _ocr_source:
            from importers.mappa_classificazione import estrai as _mappa_estrai, MappaError
            try:
                _mappa_estrazione = _mappa_estrai(file_path, period_months=period_months)
                _mappa_report = _mappa_estrazione.rapporto
            except MappaError as exc:
                warning = f"MOTORE MAPPA non applicabile ({exc}): importazione proseguita con le route esistenti"
                sc_quadratura_warnings.append(warning)
                _mappa_report = {"metodo": "mappa_classificazione", "fallito": str(exc), "warnings": [warning]}
                logger.warning(warning)
```

4. Il blocco `_source_candidates` (riga 1223, `if not is_scanned and not _ocr_source:`) diventa `if _mappa_estrazione is None and not is_scanned and not _ocr_source:`.
5. La riga 1500 `if not is_trial_balance and not _source_complete:` diventa `if _mappa_estrazione is None and not is_trial_balance and not _source_complete:`; il ramo route C sopra (`if is_trial_balance:` o equivalente, verificarlo con `grep -n "is_trial_balance" importers/pdf_importer.py`) va reso `if _mappa_estrazione is None and is_trial_balance:`. Subito prima di questi rami:

```python
        if _mappa_estrazione is not None:
            balance_sheet_data, income_data = dict(_mappa_estrazione.bs), dict(_mappa_estrazione.ce)
            prior_bs_data, prior_ce_data = _mappa_estrazione.prior_bs, _mappa_estrazione.prior_ce
            sc_quadratura_warnings.extend(_mappa_report.get("warnings", []))
```

6. L'arricchimento Haiku (riga 1566-1571, `enrich_pdf_details`) va saltato quando il motore ha prodotto i numeri:

```python
        if _mappa_estrazione is None:
            from importers.detail_enrichment import enrich_pdf_details
            balance_sheet_data, prior_bs_data, _detail_report = enrich_pdf_details(
                file_path, balance_sheet_data, prior_bs_data, fiscal_year=fiscal_year,
                ocr_text=ocr_text,
            )
            sc_quadratura_warnings.extend(_detail_report.get('warnings', []))
        else:
            _detail_report = {"status": "skipped", "method": "mappa_classificazione", "warnings": []}
```

Se più avanti la funzione chiama `_apply_vision_rescue` o `prepare_ledger` in base a condizioni sui dati (`grep -n "_apply_vision_rescue(\|prepare_ledger(" importers/pdf_importer.py`), aggiungere la stessa guardia `_mappa_estrazione is None`: il motore mappa non usa Haiku né vision.

7. Dopo la riga 1792 (`_validation_payload['warnings'].extend(_macro_report.get('warnings', []))`):

```python
        if _mappa_report:
            _validation_payload["mappa_classificazione"] = _mappa_report
```

8. Riga 1801 `_stored_parser_version = _PDF_PARSER_VERSION` diventa
`_stored_parser_version = _PDF_PARSER_VERSION_MAPPA if _mappa_estrazione is not None else _PDF_PARSER_VERSION`.

- [ ] **Step 4: Eseguire i test e vederli passare, poi tutta la suite import**

Run: `pytest tests/test_mappa_import_integration.py -v`
Expected: PASS (3 test)

Run: `pytest tests/test_macro_analysis.py tests/test_residual_finalization.py tests/test_import_semantic_validation.py tests/test_import_baseline.py -q`
Expected: invariati rispetto a prima del task (il motore è spento per default: `IMPORT_ENGINE` non impostata).

- [ ] **Step 5: Commit**

```bash
git diff --stat   # nessun file CRLF gonfiato
git add importers/pdf_importer.py tests/test_mappa_import_integration.py
git commit -m "feat(import): motore mappa dietro IMPORT_ENGINE=mappa, rapporto nel validation_report"
```

---

### Task 11: Banco di prova e pulizia del pilota

**Files:**
- Move: `tools/pilota_import/pilota.py` → `scripts/bench_mappa.py`
- Delete: `tools/pilota_import/` (resta vuota dopo gli spostamenti)
- Test: `tests/test_bench_mappa.py`

**Interfaces:**
- Produces: `scripts/bench_mappa.py <pdf>... [--fy ID ...] [--db PATH] [--cache DIR] [--out JSONL]` che stampa per file tempi, totali verificati, somme per lato, differenze dal DB; funzione pura `confronta(aggregati: dict[str, Decimal], riferimento: dict[str, Decimal]) -> list[tuple[str, Decimal | None, Decimal | None]]`.

- [ ] **Step 1: Scrivere il test della funzione di confronto**

```python
# tests/test_bench_mappa.py
from decimal import Decimal as D

from scripts.bench_mappa import confronta


def test_confronta_elenca_solo_le_differenze_oltre_il_centesimo():
    diff = confronta({"sp03": D("100.00"), "sp06": D("50.004")}, {"sp03": D("100.00"), "sp06": D("50.00"), "sp09": D("1")})
    assert diff == [("sp09", D("1"), None)]
```

- [ ] **Step 2: Eseguire il test e vederlo fallire**

Run: `pytest tests/test_bench_mappa.py -v`
Expected: FAIL, `ModuleNotFoundError: scripts.bench_mappa` (se `scripts/` non è un pacchetto, creare `scripts/__init__.py` vuoto)

- [ ] **Step 3: Spostare e adattare il banco di prova**

```bash
git mv tools/pilota_import/pilota.py scripts/bench_mappa.py
git rm -r tools/pilota_import   # dopo gli spostamenti restano solo __pycache__/file vuoti
```

In `scripts/bench_mappa.py`: gli import diventano `from importers.mappa_classificazione import estrai`; la funzione `main` chiama `estrai(pdf, cache_dir=a.cache)` e legge `e.rapporto` al posto delle chiamate ai singoli stadi; `snapshot_db` e `fmt` restano; aggiungere:

```python
def confronta(aggregati, riferimento, tolleranza=Decimal("0.01")):
    chiavi = sorted(set(aggregati) | set(riferimento))
    return [(k, riferimento.get(k), aggregati.get(k)) for k in chiavi
            if abs((aggregati.get(k) or 0) - (riferimento.get(k) or 0)) > tolleranza]
```

e usarla per la stampa delle differenze (aggregati = radici a 4 caratteri, dettagli = il resto). `--out` scrive una riga JSON per file con `file, tempi, rapporto, aggregati, differenze`.

- [ ] **Step 4: Eseguire il test e il banco sui 5 PDF nativi**

Run: `pytest tests/test_bench_mappa.py -v`
Expected: PASS

Run (richiede `GX10_API_KEY`, `ANTHROPIC_API_KEY` in `backend/.env`, DB in sola lettura):
```bash
cd /home/peter/DEV/budget-intermedio && source /home/peter/DEV/budget/backend/venv/bin/activate
python scripts/bench_mappa.py "/home/peter/DEV/budget/inbox/import-test/TM-BUSINESS_589_bilancio 2026.pdf" --fy 470 \
  --db /home/peter/DEV/budget/financial_analysis.db --cache /tmp/mappe --out /tmp/bench.jsonl
```
Expected: attivo = passivo al centesimo, `totali_non_verificati` vuoto, tempi sotto i 90 s. Ripetere per 471 (TM 590), 477 (FORMETAL-TEST), 478 (FORMETAL 701, 0 chiamate a Sonnet), 443 (AMB): gli esiti attesi sono la tabella in §4 della spec.

- [ ] **Step 5: Commit**

```bash
git add scripts/bench_mappa.py scripts/__init__.py tests/test_bench_mappa.py
git add -u tools/pilota_import
git commit -m "chore(import): banco di prova del motore mappa, pilota rimosso"
```

---

### Task 12: Documentazione su main

**Files:**
- Modify: `CLAUDE.md` (sezione «Import PDF (Claude LLM)», dopo il paragrafo introduttivo)
- Modify: `docs/import/REGOLE-IMPORT-00-INDICE.md` (una riga nell'indice)
- Modify: `backend/.env.example` se esiste (`grep -l GX10 backend/.env* || true`), altrimenti `docs/deployment/PRODUCTION_CONFIG.md`

Questo task si esegue su `main` nell'albero principale, dopo il merge del ramo (o come commit di docs separato, con il riferimento al ramo).

- [ ] **Step 1: Aggiungere il paragrafo a CLAUDE.md**

Dopo «Gli invarianti che governano tutte e tre le rotte stanno in «Invarianti e trappole», sopra.»:

```markdown
**Motore «mappa» (2026-09-22, `IMPORT_ENGINE=mappa`, spento per default).** In
`importers/mappa_classificazione/`: Sonnet 5 dichiara la struttura della prima pagina di ogni
prospetto (colonne per intestazione stampata, sezioni affiancate), un lettore geometrico assegna
i numeri alle colonne, la verifica riconosce un totale solo se un insieme contiguo di righe somma
al centesimo, Qwen su gx10 classifica le righe con una grammatica a sequenza fissa (thinking
spento; chiave solo da `GX10_API_KEY`), Python somma le foglie e netta i fondi. Gli xbrl di legge
vanno per titoli e tabella, senza modelli. Nessun plug: `_mappa_*` e
`validation_report.mappa_classificazione` dichiarano totali non verificati e sbilanci. Le tabelle
di dettaglio delle note e le scansioni restano alle route esistenti. →
`docs/superpowers/specs/2026-09-22-import-mappa-classificazione-design.md`
```

- [ ] **Step 2: Una riga nell'indice delle regole di import e le variabili d'ambiente**

In `docs/import/REGOLE-IMPORT-00-INDICE.md`, nella tabella o elenco delle pagine, aggiungere:
`| Il motore «mappa» (IMPORT_ENGINE=mappa): struttura dichiarata, totali verificati, classificazione locale | spec 2026-09-22-import-mappa-classificazione-design.md |`

Nel file di configurazione scelto, aggiungere le quattro variabili con una riga di commento ciascuna:
`IMPORT_ENGINE=classico` · `MAPPA_MODEL=claude-sonnet-5` · `GX10_BASE_URL=http://100.65.63.12:18300` · `GX10_MODEL=qwen3.8-flash-next` · `GX10_API_KEY=` (mai nel repo).

- [ ] **Step 3: Verificare che i test di documentazione passino**

Run: `pytest tests -q -k "claude_md or docs or indice" || true` e `git diff --stat`
Expected: nessun test rotto; solo i tre file cambiati.

- [ ] **Step 4: Commit su main**

```bash
git add CLAUDE.md docs/import/REGOLE-IMPORT-00-INDICE.md <file di configurazione>
git commit -m "docs(import): motore mappa dietro IMPORT_ENGINE, variabili gx10"
```

---

## Verifica finale del lotto (prima del merge)

- [ ] `pytest tests/test_mappa_*.py tests/test_bench_mappa.py -q` verde.
- [ ] `pytest tests/test_macro_analysis.py tests/test_residual_finalization.py tests/test_import_semantic_validation.py tests/test_import_baseline.py -q` invariato con `IMPORT_ENGINE` non impostata.
- [ ] Banco sui 5 PDF nativi con gli esiti della spec §4; poi sugli 87 con baseline (`Test/`, non tracciata): tempo per file, totali verificati, differenze per aggregato, ogni differenza giudicata sul PDF. Esiti in `docs/import/2026-09-XX-banco-motore-mappa.md`.
- [ ] `git diff --stat main...feat/import-mappa-classificazione`: nessun file con terminatori cambiati, nessun PDF, nessun `.jsonl` di esiti.
- [ ] Merge in `main` senza push; il push lo chiede il proprietario.
