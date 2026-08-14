# Riscatto vision per sezione (route C) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** quando la catena route C finisce con un foglio che non quadra, rileggere in vision le sole
pagine della sezione che non torna, ricostruirla da zero dai mastri letti, e tenerla solo se
riconcilia al totale stampato ed è strettamente migliore di prima.

**Architecture:** un terzo candidato prodotto **su richiesta** alla fine di
`pdf_importer.import_pdf_balance_sheet` (ramo route C), dopo `overlay_debt_typing`,
`net_contra_accounts` e `_reconcile_trial_to_declared`. Il nuovo modulo `importers/vision_rescue.py`
non conosce né DB né ORM: rende le pagine, chiama Haiku in vision, restituisce righe e totali letti,
e ospita il cancello di accettazione come funzioni pure. La classificazione descrizione→voce IV-CEE
riusa i classificatori già esistenti in `situazione_contabile_parser`, estratti da closure a funzioni
di modulo. `pdf_importer` fa solo da innesco e ri-esegue la catena sul candidato riscattato.

**Tech Stack:** Python 3, PyMuPDF (`fitz`), `anthropic` (Haiku vision, `config.PDF_LLM_MODEL`),
`pydantic` per lo schema tool, `pytest`.

**Spec:** `docs/superpowers/specs/2026-08-14-riscatto-vision-route-c-design.md` — leggerla prima di
iniziare. Precedenti obbligatori: `docs/FIXING-IMPORT.md` §1 (principi), §2 (geometria), §3
(recupero mastri orfani).

## Global Constraints

- **Mai un plug.** Il riscatto o riconcilia al totale stampato, o si butta via. Nessun valore
  inventato, nessun ripiego a metà. Se il riscatto non riesce, il foglio resta **identico** a com'è
  oggi, con i suoi `BILANCIO NON QUADRATO` / `QUADRATURA MASCHERATA`.
- **Nessun errore del riscatto è fatale.** Rendering, API irraggiungibile, risposta malformata,
  schema non validato, eccezione qualsiasi: si logga con `logger.warning` e si tiene il candidato
  precedente. Stessa filosofia del rollback atomico di `net_contra_accounts`.
- **La colonna è la verità sul lato.** Sinistra = attivo/costi, destra = passivo/ricavi
  (`FIXING-IMPORT.md` §1.3). La descrizione decide la voce, mai il lato.
- **Per il CE usare `situazione_contabile_parser._resolve_ce_field(desc, direction)`**, mai
  `iv_cee_hierarchy.resolve(side=…)`: su un nodo CE `side` non filtra nulla e una voce di costo può
  risolversi su un nodo di ricavo, spostando il risultato di 2×.
- **Tetto pagine:** `MAX_RESCUE_PAGES = 8` per sezione, costante nominata.
- **Un solo tentativo per sezione.** Nessun ritenta con prompt diverso o a risoluzione maggiore.
- **Il riscatto CE non tocca `sp13`** e il riscatto SP non tocca il conto economico. Le due sezioni
  sono indipendenti.
- **Tolleranza di riconciliazione:** `max(Decimal("50"), totale * Decimal("0.005"))` — la stessa di
  `_select_dedup` / `_reconcile_trial_to_declared`, non una nuova.
- **Fine riga:** `importers/situazione_contabile_parser.py` e `importers/pdf_extractor_llm.py` sono
  **CRLF**; `importers/pdf_importer.py` e i test sono **LF**. Gli strumenti di edit normalizzano e
  gonfiano il diff. Prima di ogni commit: `git diff --stat` e verificare che il numero di righe
  toccate sia quello atteso. Se il diff esplode, `git checkout` del file e rifare l'edit.
- **Test:** eseguirli dalla root del progetto con `python -m pytest tests/<file> -v`. Nessun test
  nuovo può fare una chiamata di rete: la risposta vision si passa sempre con un doppio.

---

## File Structure

| File | Responsabilità |
|---|---|
| `importers/vision_rescue.py` (nuovo) | Costanti, tipi (`VisionRow`, `VisionSection`), schema pydantic del tool, prompt CoGe-vision, rendering pagine, chiamata al modello, filtro al livello mastro, e il **cancello di accettazione** come funzioni pure. Non importa `pdf_importer`, non conosce il DB. |
| `importers/situazione_contabile_parser.py` (modificato) | `classify_page_section` + `section_pages` estratte dal ciclo pagine di `extract_contrapposte_best_effort`; i quattro classificatori `cl_att`/`cl_pas`/`cl_cos`/`cl_ric` promossi a funzioni di modulo; `build_sp_from_vision` / `build_ce_from_vision` che montano una sezione da righe piatte. |
| `importers/pdf_extractor_llm.py` (modificato) | `_declared_control_totals` guadagna le chiavi `costi` e `ricavi`. |
| `importers/pdf_importer.py` (modificato) | `_apply_vision_rescue`: innesco, ri-esecuzione della catena SP, provenienza nel `validation_report`. |
| `tests/test_vision_rescue.py` (nuovo) | Il cancello, il filtro mastri, il tetto pagine, la non-fatalità degli errori, e i due PDF veri (gated). |
| `tests/test_section_pages.py` (nuovo) | `classify_page_section` / `section_pages`. |

---

## Task 1: `section_pages` — quali pagine sono SP e quali CE

La regola esiste già dentro il ciclo pagine di `extract_contrapposte_best_effort`
(`importers/situazione_contabile_parser.py`, il `for page in doc:` che parte a `:4524` circa).
Va **estratta, non riscritta**: stessa logica, riusata da due chiamanti.

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (ciclo pagine di `extract_contrapposte_best_effort`)
- Test: `tests/test_section_pages.py` (create)

**Interfaces:**
- Produces:
  - `classify_page_section(page_text: str) -> Optional[Tuple[bool, bool]]` — `(is_sp, is_ce)`,
    oppure `None` quando la pagina va **saltata del tutto** (appendice fiscale di
    rideterminazione). Distinzione importante: `None` ≠ `(False, False)` — oggi la pagina saltata
    non entra affatto in `pages_data`, quella "né SP né CE" sì.
  - `section_pages(file_path: str) -> Dict[str, List[int]]` — chiavi `"sp"` e `"ce"`, indici
    pagina **0-based**, ordinati. Una pagina classificata come entrambe compare in entrambe le
    liste.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `tests/test_section_pages.py`:

```python
"""Tests per l'estrazione di section_pages dal ciclo pagine best-effort.

Spec: docs/superpowers/specs/2026-08-14-riscatto-vision-route-c-design.md §4
Run:  python -m pytest tests/test_section_pages.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.situazione_contabile_parser import (  # noqa: E402
    classify_page_section,
    section_pages,
)


def test_titolo_patrimoniale_da_solo():
    text = "STATO PATRIMONIALE\n01 CASSA 100,00\nTOTALE ATTIVITA' 100,00\n"
    assert classify_page_section(text) == (True, False)


def test_titolo_economico_da_solo():
    text = "CONTO ECONOMICO\n60 ACQUISTI 100,00\nTOTALE COSTI 100,00\n"
    assert classify_page_section(text) == (False, True)


def test_titolo_misto_vince_la_prima_riga_di_titolo():
    # Una sola pagina che nomina entrambe le sezioni: decide la riga di titolo che
    # viene PRIMA nel testo.
    text = "STATO PATRIMONIALE E CONTO ECONOMICO\nCOSTI 1,00\nRICAVI 2,00\n"
    is_sp, is_ce = classify_page_section(text)
    assert is_sp and is_ce


def test_appendice_di_rideterminazione_va_saltata():
    text = ("RIDETERMINAZIONE RISULTATO D'ESERCIZIO\n"
            "VARIAZIONI IN AUMENTO 10,00\nVARIAZIONI IN DIMINUZIONE 5,00\n")
    assert classify_page_section(text) is None


def test_senza_titolo_riconosce_attivita_e_passivita():
    text = "ATTIVITA'\n01 CASSA 100,00\nPASSIVITA'\n20 FORNITORI 100,00\n"
    assert classify_page_section(text) == (True, False)


def test_pagina_senza_marcatori_non_e_ne_sp_ne_ce():
    # Non è None: la pagina esiste ancora, semplicemente non appartiene a nessuna
    # sezione. Questa distinzione è ciò che il ciclo chiamante usa.
    assert classify_page_section("Pagina 3 di 7\n") == (False, False)


REAL_PDF = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "debug",
    "budget_624_2024 Commercio al dettaglio di ferramenta, vernici, vetro piano "
    "e materiale elettrico e termoidraulico .pdf",
)


@pytest.mark.skipif(not os.path.exists(REAL_PDF), reason="PDF di debug non presente")
def test_section_pages_su_pdf_reale():
    pages = section_pages(REAL_PDF)
    assert pages["sp"], "nessuna pagina di stato patrimoniale rilevata"
    assert pages["ce"], "nessuna pagina di conto economico rilevata"
    assert pages["sp"] == sorted(pages["sp"])
    assert pages["ce"] == sorted(pages["ce"])
    # Il CE di 624 sta in coda al documento: l'ultima pagina CE viene dopo la prima SP.
    assert max(pages["ce"]) > min(pages["sp"])
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_section_pages.py -v`
Expected: FAIL — `ImportError: cannot import name 'classify_page_section'`

- [ ] **Step 3: Estrarre le due funzioni**

In `importers/situazione_contabile_parser.py`, **subito prima** di
`def extract_contrapposte_best_effort(...)`, inserire:

```python
def classify_page_section(page_text: str) -> Optional[Tuple[bool, bool]]:
    """(is_sp, is_ce) per una pagina di contrapposte, o None se la pagina va saltata.

    Estratta verbatim dal ciclo pagine di extract_contrapposte_best_effort perché il
    riscatto vision ha bisogno della stessa classificazione senza ri-eseguire l'intera
    estrazione. `None` significa "salta la pagina" (appendice fiscale di
    rideterminazione), che NON e' la stessa cosa di (False, False) — quest'ultima e'
    una pagina reale che non appartiene a nessuna sezione.
    """
    up = page_text.upper()
    flat = up.replace(' ', '')
    # Classify the page by its FIRST section title line — a single page may
    # carry a subtitle naming both ("Stato Patrimoniale e Conto Economico"),
    # so the title line that comes first decides.
    title = ''
    for l in page_text.split('\n'):
        lu = l.strip().upper()
        if 'PATRIMONIAL' in lu or 'ECONOMIC' in lu:
            title = lu
            break
    # Fiscal-reconciliation appendices ("RIDETERMINAZIONE RISULTATO D'ESERCIZIO"
    # for II.DD./IRAP, with VARIAZIONI IN AUMENTO/DIMINUZIONE) re-list cost/revenue
    # accounts but are NOT the income statement — skip them so they don't pollute
    # the CE (they otherwise match the loose COSTI+RICAVI test below).
    if ('RIDETERMINAZIONE' in flat or 'REDDITOIMPONIBILE' in flat
            or ('VARIAZIONIINAUMENTO' in flat and 'VARIAZIONIINDIMINUZIONE' in flat)):
        return None
    if 'PATRIMONIAL' in title and 'ECONOMIC' not in title:
        return True, False
    if 'ECONOMIC' in title and 'PATRIMONIAL' not in title:
        return False, True
    is_sp = ('PATRIMONIALE' in flat) or ('ATTIVIT' in up and 'PASSIVIT' in up and 'CONTOECONOMICO' not in flat)
    is_ce = ('CONTOECONOMICO' in flat) or ('COSTI' in up and 'RICAVI' in up)
    return is_sp, is_ce


def section_pages(file_path: str) -> Dict[str, List[int]]:
    """Indici pagina (0-based) che portano lo Stato Patrimoniale e il Conto Economico.

    Una pagina classificata come entrambe compare in entrambe le liste; una pagina da
    saltare (classify_page_section -> None) in nessuna.
    """
    out: Dict[str, List[int]] = {"sp": [], "ce": []}
    with fitz.open(file_path) as doc:
        for idx, page in enumerate(doc):
            verdict = classify_page_section(page.get_text())
            if verdict is None:
                continue
            is_sp, is_ce = verdict
            if is_sp:
                out["sp"].append(idx)
            if is_ce:
                out["ce"].append(idx)
    return out
```

Poi, **dentro** il ciclo `for page in doc:` di `extract_contrapposte_best_effort`, sostituire il
blocco che va da `up = ptext.upper()` fino alla riga `is_ce = ('CONTOECONOMICO' in flat) or (...)`
con:

```python
        up = ptext.upper()
        verdict = classify_page_section(ptext)
        if verdict is None:
            continue
        is_sp, is_ce = verdict
```

`up` resta perché serve più sotto (`pages_data.append((words, is_sp, is_ce, up, page.rect.width))`).
`flat` e `title` erano usati solo dalla classificazione: verificare con `grep -n "flat\b" ` che non
siano più referenziati nel corpo del ciclo prima di rimuoverli.

- [ ] **Step 4: Eseguire i test nuovi e la regressione**

Run:
```bash
python -m pytest tests/test_section_pages.py -v
python -m pytest tests/test_contra_netting.py tests/test_dedup_partition.py -v
```
Expected: tutti PASS. Se una regressione fallisce, l'estrazione non è stata fedele: confrontare
riga per riga con `git diff`.

- [ ] **Step 5: Commit**

```bash
git diff --stat    # deve toccare SOLO situazione_contabile_parser.py (~40 righe) + il test nuovo
git add importers/situazione_contabile_parser.py tests/test_section_pages.py
git commit -m "refactor(import): la classificazione pagina->sezione diventa una funzione"
```

---

## Task 2: `_declared_control_totals` legge anche i totali del conto economico

Oggi restituisce solo `attivo/passivo/pareggio/utile/perdita`: il CE **non ha ancora** un'ancora
dichiarata contro cui misurare un riscatto.

**Files:**
- Modify: `importers/pdf_extractor_llm.py:3077-3095` (dict `out`) e la coda della funzione
- Test: `tests/test_vision_rescue.py` (create — il file nasce qui, gli altri test si aggiungono dopo)

**Interfaces:**
- Produces: `_declared_control_totals(...)` con due chiavi in più, `"costi"` e `"ricavi"`,
  `Optional[Decimal]`, `None` quando il documento non stampa quella riga.

- [ ] **Step 1: Scrivere i test che falliscono**

Creare `tests/test_vision_rescue.py`:

```python
"""Tests per il riscatto vision per sezione (route C).

Spec: docs/superpowers/specs/2026-08-14-riscatto-vision-route-c-design.md
Run:  python -m pytest tests/test_vision_rescue.py -v

Nessun test in questo file effettua una chiamata di rete: la risposta vision e'
sempre passata con un doppio.
"""
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.pdf_extractor_llm import _declared_control_totals  # noqa: E402

D = Decimal


# ------------------------------------------------- ancore dichiarate del CE

def test_declared_totals_legge_i_totali_del_conto_economico():
    text = (
        "CONTO ECONOMICO\n"
        "73020005 Amm.to immobilizzazioni materiali 4.656,95\n"
        "TOTALE COSTI 2.482.879,59\n"
        "TOTALE RICAVI 2.491.786,38\n"
        "UTILE D'ESERCIZIO 8.906,79\n"
    )
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] == D("2482879.59")
    assert out["ricavi"] == D("2491786.38")
    assert out["utile"] == D("8906.79")


def test_declared_totals_costi_ricavi_sono_none_se_non_stampati():
    text = "STATO PATRIMONIALE\nTOTALE ATTIVO 1.000,00\nTOTALE PASSIVO 1.000,00\n"
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] is None
    assert out["ricavi"] is None


def test_declared_totals_costi_ricavi_tollerano_le_intestazioni_spaziate():
    text = "T O T A L E   C O S T I 1.234,56\nT O T A L E   R I C A V I 2.345,67\n"
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] == D("1234.56")
    assert out["ricavi"] == D("2345.67")
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: FAIL — `KeyError: 'costi'`

- [ ] **Step 3: Aggiungere le due chiavi**

In `importers/pdf_extractor_llm.py`, nel dizionario iniziale di `_declared_control_totals`:

```python
    out: Dict[str, Optional[Decimal]] = {
        "attivo": None, "passivo": None, "pareggio": None, "utile": None, "perdita": None,
        "costi": None, "ricavi": None,
    }
```

E **subito dopo** l'assegnazione di `out["perdita"]` (prima del blocco di fallback geometrico che
inizia con `if out["utile"] is None or out["perdita"] is None:`):

```python
    # Ancore della sezione economica. Servono al riscatto vision, che misura un CE
    # ricostruito contro il totale che il documento stampa: senza queste il CE non ha
    # alcun controllo indipendente (lo SP ha pareggio/attivo/passivo, il CE nulla).
    out["costi"] = _largest_after([
        "totale costi", "totale dei costi", "totale costi e oneri",
        "totale a pareggio costi",
    ])
    out["ricavi"] = _largest_after([
        "totale ricavi", "totale dei ricavi", "totale ricavi e proventi",
        "totale a pareggio ricavi",
    ])
```

- [ ] **Step 4: Eseguire i test**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git diff --stat    # pdf_extractor_llm.py ~14 righe + il test nuovo
git add importers/pdf_extractor_llm.py tests/test_vision_rescue.py
git commit -m "feat(import): il conto economico ha le sue ancore dichiarate"
```

---

## Task 3: i classificatori diventano funzioni di modulo

`cl_att`, `cl_pas`, `cl_cos`, `cl_ric` sono oggi closure dentro
`extract_contrapposte_best_effort` (`:4716-4778`). Non chiudono su alcuna variabile locale — usano
solo helper di modulo — quindi la promozione è uno **spostamento puro**. Il riscatto vision ha
bisogno delle stesse regole senza ri-eseguire l'estrazione.

**Files:**
- Modify: `importers/situazione_contabile_parser.py:4716-4778`
- Test: `tests/test_vision_rescue.py` (append)

**Interfaces:**
- Produces (tutte `(field: str, specific: bool)`):
  - `classify_attivo(desc_upper: str) -> Tuple[str, bool]`
  - `classify_passivo(desc_upper: str) -> Tuple[str, bool]`
  - `classify_costi(desc_upper: str) -> Tuple[str, bool]`
  - `classify_ricavi(desc_upper: str) -> Tuple[str, bool]`

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere in coda a `tests/test_vision_rescue.py`:

```python
from importers.situazione_contabile_parser import (  # noqa: E402
    classify_attivo,
    classify_costi,
    classify_passivo,
    classify_ricavi,
)


# ------------------------------------------------- classificatori promossi

def test_classify_attivo_banche_e_cassa_sul_lato_attivo():
    # Nel layout contrapposte il LATO e' verita': BANCHE in colonna attivo e'
    # liquidita', non il fallback generico dei crediti.
    assert classify_attivo("BANCHE C/C") == ("sp09", True)


def test_classify_attivo_categoria_legale_esatta_ferma_la_discesa():
    assert classify_attivo("IMMOBILIZZAZIONI MATERIALI") == ("sp03", True)


def test_classify_passivo_fondo_ammortamento_e_un_contro_conto():
    field, _specific = classify_passivo("F.DO AMM.TO IMMOBILIZZAZIONI MATERIALI")
    assert field == "depr_sp03"


def test_classify_passivo_tipizza_i_debiti_per_creditore():
    assert classify_passivo("DEBITI VERSO FORNITORI")[0].startswith("sp16")


def test_classify_costi_e_ricavi_hanno_catch_all_distinti():
    assert classify_costi("VOCE SCONOSCIUTA XYZ") == ("ce12", False)
    assert classify_ricavi("VOCE SCONOSCIUTA XYZ") == ("ce04", False)
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: FAIL — `ImportError: cannot import name 'classify_attivo'`

- [ ] **Step 3: Promuovere le quattro closure**

Spostare i corpi di `cl_att`, `cl_pas`, `cl_cos`, `cl_ric` **fuori** da
`extract_contrapposte_best_effort`, subito prima di `def extract_contrapposte_best_effort(...)` e
dopo `classify_page_section`/`section_pages` del Task 1, rinominandoli
`classify_attivo`/`classify_passivo`/`classify_costi`/`classify_ricavi`. Il corpo va copiato
**verbatim** — l'unico cambiamento è il nome, il parametro (`d` → `desc_upper`, con `d = desc_upper`
come prima riga per non toccare il resto) e il commento di intestazione:

```python
# Classifiers map a mastro/subtotal DESCRIPTION to an IV-CEE field; the second
# element flags whether the match is specific enough to stop descending.
# Erano closure dentro extract_contrapposte_best_effort: promosse a funzioni di
# modulo perche' il riscatto vision (vision_rescue.py) classifica le stesse
# descrizioni senza ri-eseguire l'estrazione. Nessun cambiamento di regola.
def classify_attivo(desc_upper: str) -> Tuple[str, bool]:
    d = desc_upper
    ...   # corpo di cl_att, verbatim
```

Dentro `extract_contrapposte_best_effort`, sostituire le quattro definizioni con quattro alias, così
che il resto del corpo (che passa `cl_att` a `_be_reclassify`) non cambi di una riga:

```python
    cl_att, cl_pas = classify_attivo, classify_passivo
    cl_cos, cl_ric = classify_costi, classify_ricavi
```

- [ ] **Step 4: Eseguire i test e la regressione**

Run:
```bash
python -m pytest tests/test_vision_rescue.py tests/test_section_pages.py -v
python -m pytest tests/test_contra_netting.py tests/test_dedup_partition.py -v
```
Expected: tutti PASS.

- [ ] **Step 5: Commit**

```bash
git diff --stat    # situazione_contabile_parser.py: spostamento, non riscrittura
git add importers/situazione_contabile_parser.py tests/test_vision_rescue.py
git commit -m "refactor(import): i classificatori di contrapposte sono funzioni di modulo"
```

---

## Task 4: montare una sezione da righe piatte

Il riscatto legge **mastri**, non una gerarchia: la lista è piatta, quindi non serve
`_be_reclassify` (che serve a scegliere il livello). Serve invece la stessa gestione dei tag che il
best-effort applica dopo la classificazione: netting dei fondi, tipizzazione debiti, roll-up dei
sotto-campi CE.

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (aggiungere in coda a `extract_contrapposte_best_effort`)
- Test: `tests/test_vision_rescue.py` (append)

**Interfaces:**
- Consumes: `classify_attivo/passivo/costi/ricavi` (Task 3), `_resolve_ce_field`, `_DEBT_FIELD`,
  `_ATTIVO_KEYS`, `_PASSIVO_KEYS`, `fallback_field` — tutti già in questo modulo.
- Produces:
  - `build_sp_from_vision(rows: Sequence[Tuple[str, str, Decimal, str]], utile: Decimal) -> Dict[str, Decimal]`
    — `rows` è `(codice, descrizione, importo, colonna)` con `colonna ∈ {"left", "right"}`.
    Restituisce **chiavi corte** (`sp03`, `sp16a`, …) come il best-effort, più
    `totale_attivo`, `totale_passivo`, `sp13`, `_netted_contra`, `_plug_residual` (0: qui il
    residuo lo misura il cancello, non questa funzione).
  - `build_ce_from_vision(rows: Sequence[Tuple[str, str, Decimal, str]]) -> Dict[str, Decimal]`
    — chiavi corte `ce01`…`ce20` più i sotto-campi a nome pieno (`ce08b_salari_stipendi`, …).

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere in coda a `tests/test_vision_rescue.py`:

```python
from importers.situazione_contabile_parser import (  # noqa: E402
    build_ce_from_vision,
    build_sp_from_vision,
)


# ------------------------------------------------- montaggio di una sezione

def test_build_sp_netta_i_fondi_dall_attivo():
    rows = [
        ("01", "IMMOBILIZZAZIONI MATERIALI", D("1000.00"), "left"),
        ("02", "F.DO AMM.TO IMMOBILIZZAZIONI MATERIALI", D("400.00"), "right"),
        ("20", "DEBITI VERSO FORNITORI", D("600.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("0"))
    assert bs["sp03"] == D("600.00")          # 1000 lordo - 400 fondo
    assert bs["_netted_contra"] == D("400.00")
    assert bs["totale_attivo"] == D("600.00")
    assert bs["totale_passivo"] == D("600.00")


def test_build_sp_scrive_il_risultato_ricevuto_e_non_lo_inventa():
    rows = [
        ("01", "CASSA", D("150.00"), "left"),
        ("20", "DEBITI VERSO FORNITORI", D("100.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("50.00"))
    assert bs["sp13"] == D("50.00")
    assert bs["totale_passivo"] == D("150.00")   # 100 debiti + 50 utile


def test_build_sp_tipizza_i_debiti_per_creditore():
    rows = [
        ("01", "CASSA", D("300.00"), "left"),
        ("20", "DEBITI VERSO FORNITORI", D("200.00"), "right"),
        ("21", "BANCHE C/C PASSIVI", D("100.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("0"))
    assert bs["sp16"] == D("300.00")                       # aggregato invariato
    assert bs["debiti_fornitori_breve"] == D("200.00")
    assert bs["debiti_banche_breve"] == D("100.00")


def test_build_ce_usa_la_colonna_come_direzione():
    rows = [
        ("60", "ACQUISTI MATERIE PRIME", D("500.00"), "left"),
        ("70", "RICAVI DELLE VENDITE", D("800.00"), "right"),
    ]
    ce = build_ce_from_vision(rows)
    assert ce["ce05"] == D("500.00")
    assert ce["ce01"] == D("800.00")


def test_build_ce_non_manda_un_costo_su_una_voce_di_ricavo():
    # DIFFERENZE CAMBIO PASSIVE risolve su un nodo di GUADAGNO nell'albero
    # condiviso: sulla colonna dei costi deve cadere sul catch-all neutro, mai
    # su ce16 (che ALZEREBBE il risultato, spostandolo di 2x).
    rows = [("75", "DIFFERENZE CAMBIO PASSIVE", D("90.00"), "left")]
    ce = build_ce_from_vision(rows)
    assert ce.get("ce16", D("0")) == D("0")
    assert sum(v for k, v in ce.items() if k.startswith("ce")) >= D("90.00")


def test_build_ce_arrotola_i_sottocampi_sul_padre():
    rows = [("64", "SALARI E STIPENDI", D("300.00"), "left")]
    ce = build_ce_from_vision(rows)
    assert ce["ce08"] == D("300.00")
    assert ce["ce08b_salari_stipendi"] == D("300.00")
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_sp_from_vision'`

- [ ] **Step 3: Implementare le due funzioni**

Prima, **promuovere a costante di modulo** il dizionario `_CE_SUBFIELD_PARENT` che oggi è locale
dentro `extract_contrapposte_best_effort` (attorno a `:4830`, quello con `'ce08a_tfr':
('ce08a_tfr_accrual', 'ce08')` e i suoi otto elementi): spostarlo verbatim accanto a
`_CE_HIER_SUBPARENT`, in cima al modulo, e lasciare la funzione a leggerlo da lì. Deve esistere in
un posto solo — `build_ce_from_vision` legge lo stesso.

Poi, in `importers/situazione_contabile_parser.py`, **dopo** `extract_contrapposte_best_effort`:

```python
def build_sp_from_vision(rows, utile: Decimal) -> Dict[str, Decimal]:
    """Monta lo Stato Patrimoniale da righe MASTRO piatte lette in vision.

    `rows` = [(codice, descrizione, importo, colonna)], colonna in {'left','right'}.
    La colonna e' verita' sul lato (FIXING-IMPORT.md §1.3); la descrizione decide la
    voce. `utile` e' il risultato LETTO dal documento, non derivato qui: questa
    funzione non inventa il pareggio.

    Le righe sono gia' al livello mastro, quindi non passano da _be_reclassify (che
    serve a scegliere fra padre e figli in una gerarchia): ogni riga vale per se'.
    Chiavi corte come il best-effort — il chiamante applica _map_sc_keys.
    """
    Z = Decimal('0')
    bs: Dict[str, Decimal] = {}
    netted = Z

    def add(k, v):
        bs[k] = bs.get(k, Z) + v

    for _code, desc, amount, column in rows:
        d = (desc or '').upper()
        if column == 'left':
            field, _specific = classify_attivo(d)
            add({'gross_sp02': 'sp02', 'gross_sp03': 'sp03',
                 'gross_sp04': 'sp04'}.get(field, field), amount)
            continue
        tag, _specific = classify_passivo(d)
        if tag in ('depr_sp02', 'depr_sp03', 'depr_sp04'):
            add(tag.replace('depr_', ''), -amount)     # netta il fondo dall'attivo
            netted += amount
        elif tag == 'deduct_crediti':
            add('sp06', -amount)
            netted += amount
        elif tag in ('sp11', 'sp12', 'sp14', 'sp15', 'sp18'):
            add(tag, amount)
        elif len(tag) == 5 and tag.startswith('sp16') and tag[4] in 'abcdefg':
            add('sp16', amount)                        # aggregato: pareggio invariato
            add(_DEBT_FIELD['breve'][tag[4]], amount)  # tipizzato, nome pieno
        else:
            add('sp16', amount)

    # Un fondo non puo' mai superare il proprio cespite lordo: un'immobilizzazione
    # netta negativa e' sempre una misclassificazione. Il cancello vedra' il divario.
    for k in ('sp02', 'sp03', 'sp04'):
        if bs.get(k, Z) < Z:
            bs[k] = Z

    bs['sp13'] = utile
    bs['_netted_contra'] = netted
    bs['totale_attivo'] = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
    bs['totale_passivo'] = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
    bs['_plug_residual'] = Z
    return bs


def build_ce_from_vision(rows) -> Dict[str, Decimal]:
    """Monta il Conto Economico da righe MASTRO piatte lette in vision.

    La colonna decide la DIREZIONE (sinistra = costi, destra = ricavi) e la direzione
    vincola la risoluzione: _resolve_ce_field rifiuta una voce del segno opposto, cosi'
    un costo non puo' finire su un nodo di ricavo (che sposterebbe il risultato di 2x).
    Ordine: tabella a parole chiave -> albero IV-CEE vincolato -> catch-all neutro.
    """
    Z = Decimal('0')
    ce: Dict[str, Decimal] = {}

    def add(k, v):
        ce[k] = ce.get(k, Z) + v

    for _code, desc, amount, column in rows:
        d = (desc or '').upper()
        direction = 'costi' if column == 'left' else 'ricavi'
        if direction == 'costi':
            tag, specific = classify_costi(d)
        else:
            tag, specific = classify_ricavi(d)
        if not specific:
            # La tabella a parole chiave non conosce questa descrizione: prova
            # l'albero condiviso, VINCOLATO alla direzione. iv_cee_hierarchy.resolve
            # non filtra per segno sui nodi CE — _resolve_ce_field si'.
            resolved = _resolve_ce_field(d, direction)
            tag = resolved if resolved else fallback_field('ce')
        if tag == 'ce01_return':
            add('ce01', -amount)
        elif tag == 'ce10_close':
            add('ce10', -amount)
        elif tag == 'ce13_cost':
            add('ce15', amount)
        elif tag in _CE_SUBFIELD_PARENT:
            detail, parent = _CE_SUBFIELD_PARENT[tag]
            add(parent, amount)
            add(detail, amount)
        else:
            add(tag, amount)
    return ce
```

- [ ] **Step 4: Eseguire i test**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: tutti PASS. Se `test_build_sp_tipizza_i_debiti_per_creditore` fallisce sui nomi dei campi,
leggere `_DEBT_FIELD` in `situazione_contabile_parser.py` e correggere le **asserzioni del test** ai
nomi reali (sono nomi DB esistenti, non da inventare).

- [ ] **Step 5: Commit**

```bash
git diff --stat
git add importers/situazione_contabile_parser.py tests/test_vision_rescue.py
git commit -m "feat(import): montare una sezione da righe mastro piatte"
```

---

## Task 5: `vision_rescue.py` — leggere la sezione

**Files:**
- Create: `importers/vision_rescue.py`
- Test: `tests/test_vision_rescue.py` (append)

**Interfaces:**
- Produces:
  - `MAX_RESCUE_PAGES = 8`, `RESCUE_DPI = 200`
  - `@dataclass(frozen=True) VisionRow: code: str; description: str; amount: Decimal; column: str`
  - `@dataclass(frozen=True) VisionSection: section: str; rows: Tuple[VisionRow, ...]; totals: Dict[str, Optional[Decimal]]`
    — `section ∈ {"sp","ce"}`; `totals` ha chiavi `left`, `right`, `utile`, `perdita`.
  - `parse_amount(raw: str) -> Optional[Decimal]`
  - `mastro_level_rows(rows: Sequence[VisionRow]) -> Tuple[VisionRow, ...]`
  - `read_section(file_path: str, pages: Sequence[int], section: str, client=None) -> Optional[VisionSection]`
    — `None` su qualunque errore o quando `len(pages) > MAX_RESCUE_PAGES` o `pages` è vuoto.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere in coda a `tests/test_vision_rescue.py`:

```python
from importers import vision_rescue as vr  # noqa: E402


class _FakeBlock:
    type = "tool_use"

    def __init__(self, payload):
        self.input = payload


class _FakeResponse:
    def __init__(self, payload):
        self.content = [_FakeBlock(payload)]


class _FakeMessages:
    def __init__(self, payload_or_exc):
        self._p = payload_or_exc
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if isinstance(self._p, Exception):
            raise self._p
        return _FakeResponse(self._p)


class _FakeClient:
    """Doppio del client anthropic: nessuna chiamata di rete."""

    def __init__(self, payload_or_exc):
        self.messages = _FakeMessages(payload_or_exc)


_PAYLOAD_CE = {
    "mastri": [
        {"codice": "73020005", "descrizione": "Amm.to immobilizzazioni materiali",
         "importo": "4.656,95", "colonna": "left"},
        {"codice": "706440000", "descrizione": "amm.to fabbricati",
         "importo": "486,93", "colonna": "left"},
        {"codice": "70000005", "descrizione": "Ricavi delle vendite",
         "importo": "2.491.786,38", "colonna": "right"},
    ],
    "totale_sinistra": "2.482.879,59",
    "totale_destra": "2.491.786,38",
    "utile": "8.906,79",
    "perdita": None,
}


def test_parse_amount_formato_italiano():
    assert vr.parse_amount("1.426.002,20") == D("1426002.20")
    assert vr.parse_amount("4.656,95") == D("4656.95")
    assert vr.parse_amount("") is None
    assert vr.parse_amount("n.d.") is None


def test_mastro_level_rows_scarta_i_dettagli_piu_lunghi():
    # I dettagli a 9 cifre la vision li sbaglia (spec, sezione Evidenza) e non
    # servono: il mastro porta gia' l'intero importo della voce.
    rows = [
        vr.VisionRow("73020005", "Amm.to", D("4656.95"), "left"),
        vr.VisionRow("706440000", "amm.to fabbricati", D("486.93"), "left"),
    ]
    kept = vr.mastro_level_rows(rows)
    assert [r.code for r in kept] == ["73020005"]


def test_mastro_level_rows_ignora_le_righe_senza_codice():
    rows = [
        vr.VisionRow("73020005", "Amm.to", D("4656.95"), "left"),
        vr.VisionRow("", "TOTALE COSTI", D("2482879.59"), "left"),
    ]
    assert [r.code for r in vr.mastro_level_rows(rows)] == ["73020005"]


def test_read_section_monta_righe_e_totali():
    got = vr.read_section("ignorato.pdf", [0], "ce",
                          client=_FakeClient(_PAYLOAD_CE),
                          images=["ZmFrZQ=="])
    assert got is not None
    assert got.section == "ce"
    assert [r.code for r in got.rows] == ["73020005", "70000005"]
    assert got.totals["left"] == D("2482879.59")
    assert got.totals["right"] == D("2491786.38")
    assert got.totals["utile"] == D("8906.79")
    assert got.totals["perdita"] is None


def test_read_section_rifiuta_una_sezione_oltre_il_tetto_di_pagine():
    fake = _FakeClient(_PAYLOAD_CE)
    assert vr.read_section("ignorato.pdf", list(range(vr.MAX_RESCUE_PAGES + 1)), "ce",
                           client=fake, images=["ZmFrZQ=="]) is None
    assert fake.messages.calls == 0, "il tetto deve fermare PRIMA di spendere una chiamata"


def test_read_section_senza_pagine_non_chiama_il_modello():
    fake = _FakeClient(_PAYLOAD_CE)
    assert vr.read_section("ignorato.pdf", [], "ce", client=fake, images=[]) is None
    assert fake.messages.calls == 0


def test_read_section_restituisce_none_se_il_modello_esplode():
    fake = _FakeClient(RuntimeError("API irraggiungibile"))
    assert vr.read_section("ignorato.pdf", [0], "ce",
                           client=fake, images=["ZmFrZQ=="]) is None


def test_read_section_restituisce_none_su_risposta_malformata():
    fake = _FakeClient({"mastri": "non e' una lista"})
    assert vr.read_section("ignorato.pdf", [0], "ce",
                           client=fake, images=["ZmFrZQ=="]) is None


def test_read_section_fa_un_solo_tentativo():
    fake = _FakeClient(_PAYLOAD_CE)
    vr.read_section("ignorato.pdf", [0], "ce", client=fake, images=["ZmFrZQ=="])
    assert fake.messages.calls == 1
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'importers.vision_rescue'`

- [ ] **Step 3: Creare il modulo**

Creare `importers/vision_rescue.py`:

```python
"""Riscatto vision per sezione — route C (situazione contabile / sezioni contrapposte).

Quando la catena route C finisce con un foglio che non quadra, le pagine della sezione
che non torna vengono rese a immagine e rilette in vision: il numero giusto e' STAMPATO
sulla pagina, e' il text layer a non arrivarci (mastri disegnati come vettori, ordine di
stream rotto, importi corrotti).

Questo modulo non conosce il DB, non importa pdf_importer e non decide nulla da solo:
legge, misura, e restituisce. Il cancello di accettazione (accept_rescue) e' qui perche'
e' puro; l'innesco e la ri-esecuzione della catena stanno in pdf_importer.

Spec: docs/superpowers/specs/2026-08-14-riscatto-vision-route-c-design.md
"""
import base64
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Sequence, Tuple

import fitz
import pydantic

logger = logging.getLogger(__name__)

# Oltre questo numero di pagine il riscatto non parte: il costo cresce, la resa cala,
# e il file resta dichiarato non quadrato invece di spendere una chiamata enorme con
# poca speranza. Sui file noti la sezione ha 2 pagine.
MAX_RESCUE_PAGES = 8
RESCUE_DPI = 200

Z = Decimal("0")


@dataclass(frozen=True)
class VisionRow:
    code: str
    description: str
    amount: Decimal
    column: str          # 'left' | 'right'


@dataclass(frozen=True)
class VisionSection:
    section: str                              # 'sp' | 'ce'
    rows: Tuple[VisionRow, ...]
    totals: Dict[str, Optional[Decimal]]      # left / right / utile / perdita


class _VisionMastro(pydantic.BaseModel):
    codice: str = ""
    descrizione: str = ""
    importo: str = ""
    colonna: str = ""


class _VisionSectionModel(pydantic.BaseModel):
    mastri: List[_VisionMastro] = []
    totale_sinistra: Optional[str] = None
    totale_destra: Optional[str] = None
    utile: Optional[str] = None
    perdita: Optional[str] = None


_SP_SYSTEM_PROMPT = """Sei un perito contabile che TRASCRIVE una pagina di stato patrimoniale
a sezioni contrapposte di una situazione contabile italiana (piano dei conti CoGe).

REGOLE ASSOLUTE:
1. TRASCRIVI, non calcolare. Non sommare, non dedurre, non correggere nulla.
2. Riporta SOLO le righe di MASTRO — i conti il cui codice ha il MINOR numero di cifre
   nella pagina. Le righe di dettaglio (codice piu' lungo) vanno IGNORATE: il mastro
   porta gia' l'intero importo della voce.
3. La COLONNA e' decisiva: 'left' per la colonna di sinistra (ATTIVITA'), 'right' per
   quella di destra (PASSIVITA'). Se un conto compare su entrambe le colonne, riportalo
   due volte con i rispettivi importi.
4. Le righe di TOTALE non vanno in 'mastri': vanno nei campi totale_sinistra
   (TOTALE ATTIVITA'/ATTIVO), totale_destra (TOTALE PASSIVITA'/PASSIVO), utile e perdita.
5. Riporta gli importi ESATTAMENTE come stampati, formato italiano (1.234.567,89).
   Se un importo non e' leggibile, lascia la stringa vuota.
6. Se un campo di totale non e' stampato sulla pagina, lascialo assente."""

_CE_SYSTEM_PROMPT = """Sei un perito contabile che TRASCRIVE una pagina di conto economico
a sezioni contrapposte di una situazione contabile italiana (piano dei conti CoGe).

REGOLE ASSOLUTE:
1. TRASCRIVI, non calcolare. Non sommare, non dedurre, non correggere nulla.
2. Riporta SOLO le righe di MASTRO — i conti il cui codice ha il MINOR numero di cifre
   nella pagina. Le righe di dettaglio (codice piu' lungo) vanno IGNORATE: il mastro
   porta gia' l'intero importo della voce.
3. La COLONNA e' decisiva: 'left' per la colonna dei COSTI, 'right' per quella dei
   RICAVI.
4. Le righe di TOTALE non vanno in 'mastri': vanno nei campi totale_sinistra
   (TOTALE COSTI), totale_destra (TOTALE RICAVI), utile e perdita.
5. Riporta gli importi ESATTAMENTE come stampati, formato italiano (1.234.567,89).
   Se un importo non e' leggibile, lascia la stringa vuota.
6. Se un campo di totale non e' stampato sulla pagina, lascialo assente."""

_TOOL_NAME = "trascrivi_sezione"


def parse_amount(raw: Optional[str]) -> Optional[Decimal]:
    """Importo in formato italiano -> Decimal. None quando non e' un numero."""
    if raw is None:
        return None
    s = str(raw).strip().replace("\u00a0", " ")   # spazio unificatore
    if not s:
        return None
    negative = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        return None
    # Formato italiano: '.' migliaia, ',' decimali. Senza virgola il '.' resta
    # separatore di migliaia (un CoGe non stampa mai decimali col punto).
    s = s.replace(".", "").replace(",", ".") if "," in s else s.replace(".", "")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def mastro_level_rows(rows: Sequence[VisionRow]) -> Tuple[VisionRow, ...]:
    """Tiene solo le righe al livello MASTRO: quelle il cui codice ha il minor numero
    di cifre fra quelle lette.

    I dettagli (codice piu' lungo) la vision li sbaglia — sono le righe con gli importi
    corrotti nel testo sorgente — e non servono, perche' il mastro porta gia' l'intero
    importo della voce. Il filtro e' deterministico e non si fida della sola obbedienza
    del modello alla regola 2 del prompt. Le righe senza codice (totali intercettati per
    errore) sono scartate.
    """
    digits = {}
    for idx, row in enumerate(rows):
        only = re.sub(r"\D", "", row.code or "")
        if only:
            digits[idx] = len(only)
    if not digits:
        return ()
    level = min(digits.values())
    return tuple(r for idx, r in enumerate(rows) if digits.get(idx) == level)


def render_section_images(file_path: str, pages: Sequence[int],
                          dpi: int = RESCUE_DPI) -> List[str]:
    """Le pagine indicate rese in PNG base64. Solleva se il PDF non si apre."""
    images: List[str] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(file_path) as doc:
        for p in sorted(pages):
            if 0 <= p < len(doc):
                pix = doc[p].get_pixmap(matrix=matrix)
                images.append(base64.standard_b64encode(pix.tobytes("png")).decode("ascii"))
    return images


def _build_tool_schema() -> dict:
    return {
        "name": _TOOL_NAME,
        "description": "Registra i mastri e i totali trascritti dalla sezione.",
        "input_schema": _VisionSectionModel.model_json_schema(),
    }


def read_section(file_path: str, pages: Sequence[int], section: str,
                 client=None, images: Optional[List[str]] = None) -> Optional[VisionSection]:
    """Rilegge in vision le pagine di una sezione. None su QUALUNQUE problema.

    Un solo tentativo: un riscatto che fallisce non viene ritentato, ne' con un prompt
    diverso ne' a risoluzione maggiore. `client` e `images` sono iniettabili perche' i
    test non facciano rete ne' aprano un PDF.
    """
    pages = list(pages)
    if not pages:
        return None
    if len(pages) > MAX_RESCUE_PAGES:
        logger.info(f"Riscatto vision: sezione {section} di {len(pages)} pagine, oltre il "
                    f"tetto di {MAX_RESCUE_PAGES} — non tentato")
        return None
    try:
        from config import PDF_LLM_MODEL, PDF_LLM_MAX_TOKENS

        if images is None:
            images = render_section_images(file_path, pages)
        if not images:
            return None
        if client is None:
            import anthropic
            client = anthropic.Anthropic()

        content: List[dict] = [
            {"type": "image",
             "source": {"type": "base64", "media_type": "image/png", "data": img}}
            for img in images
        ]
        content.append({
            "type": "text",
            "text": (f"Trascrivi la sezione ({'stato patrimoniale' if section == 'sp' else 'conto economico'}) "
                     f"da queste pagine usando lo strumento {_TOOL_NAME}."),
        })

        response = client.messages.create(
            model=PDF_LLM_MODEL,
            max_tokens=PDF_LLM_MAX_TOKENS,
            system=_SP_SYSTEM_PROMPT if section == "sp" else _CE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            tools=[_build_tool_schema()],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )
        payload = next((b.input for b in response.content if b.type == "tool_use"), None)
        if payload is None:
            logger.warning("Riscatto vision: nessun blocco tool_use nella risposta")
            return None
        parsed = _VisionSectionModel.model_validate(payload)
    except Exception as err:
        logger.warning(f"Riscatto vision saltato ({type(err).__name__}: {err})")
        return None

    rows: List[VisionRow] = []
    for m in parsed.mastri:
        amount = parse_amount(m.importo)
        column = "left" if str(m.colonna).strip().lower().startswith("l") else "right"
        if amount is None or amount == Z:
            continue
        rows.append(VisionRow(code=(m.codice or "").strip(),
                              description=(m.descrizione or "").strip(),
                              amount=amount, column=column))
    return VisionSection(
        section=section,
        rows=mastro_level_rows(rows),
        totals={
            "left": parse_amount(parsed.totale_sinistra),
            "right": parse_amount(parsed.totale_destra),
            "utile": parse_amount(parsed.utile),
            "perdita": parse_amount(parsed.perdita),
        },
    )
```

- [ ] **Step 4: Eseguire i test**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: tutti PASS.

- [ ] **Step 5: Commit**

```bash
git diff --stat
git add importers/vision_rescue.py tests/test_vision_rescue.py
git commit -m "feat(import): rileggere in vision le pagine di una sezione"
```

---

## Task 6: il cancello di accettazione

Tre condizioni, **tutte** necessarie (spec §3). Se una qualsiasi cade, si scarta tutto e resta il
candidato di prima con i suoi warning.

**Files:**
- Modify: `importers/vision_rescue.py` (append)
- Test: `tests/test_vision_rescue.py` (append)

**Interfaces:**
- Consumes: `iv_cee_hierarchy.check_quadratura` (import locale dentro la funzione — `vision_rescue`
  resta senza dipendenze da DB/ORM).
- Produces:
  - `reconcile_tolerance(total: Decimal) -> Decimal`
  - `totals_are_coherent(sec: VisionSection) -> bool`
  - `section_anchor(sec: VisionSection, declared: Dict[str, Optional[Decimal]]) -> Optional[Decimal]`
  - `accept_rescue(section, rebuilt_total, sec, declared, before, after) -> Tuple[bool, str]`
    dove `before`/`after` sono i `Quadratura` di `check_quadratura` prima e dopo. Ritorna
    `(accettato, motivo)`; `motivo` è sempre popolato e va nel log.

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere in coda a `tests/test_vision_rescue.py`:

```python
from importers.iv_cee_hierarchy import check_quadratura  # noqa: E402


def _sezione(section, left, right, utile=None, perdita=None):
    return vr.VisionSection(section=section, rows=(),
                            totals={"left": left, "right": right,
                                    "utile": utile, "perdita": perdita})


# ------------------------------------------------- cancello: coerenza interna

def test_coerenza_sp_attivo_uguale_passivo_piu_utile():
    assert vr.totals_are_coherent(_sezione("sp", D("1000"), D("950"), utile=D("50")))


def test_coerenza_sp_attivo_piu_perdita_uguale_passivo():
    assert vr.totals_are_coherent(_sezione("sp", D("950"), D("1000"), perdita=D("50")))


def test_coerenza_ce_costi_piu_utile_uguale_ricavi():
    assert vr.totals_are_coherent(
        _sezione("ce", D("2482879.59"), D("2491786.38"), utile=D("8906.79")))


def test_incoerenza_quando_i_totali_non_tornano():
    assert not vr.totals_are_coherent(
        _sezione("ce", D("2482879.59"), D("2491786.38"), utile=D("1000")))


def test_incoerenza_quando_manca_un_totale():
    assert not vr.totals_are_coherent(_sezione("sp", D("1000"), None, utile=D("50")))


# ------------------------------------------------- cancello: scelta dell'ancora

def test_ancora_preferisce_i_totali_vision_quando_sono_coerenti():
    # budget_623: le ancore di TESTO si contraddicono (il passivo letto dal testo e'
    # 2.420.397,40 mentre il PDF stampa 2.454.987,65). La coerenza interna dei totali
    # vision e' cio' che autorizza a preferirli.
    sec = _sezione("sp", D("2420397.40"), D("2370397.40"), utile=D("50000"))
    declared = {"attivo": D("2420397.40"), "passivo": D("2454987.65"), "pareggio": None}
    assert vr.section_anchor(sec, declared) == D("2420397.40")


def test_ancora_ricade_sul_testo_quando_i_totali_vision_non_sono_coerenti():
    sec = _sezione("sp", D("999"), D("111"), utile=D("1"))
    declared = {"attivo": D("2000"), "passivo": None, "pareggio": None}
    assert vr.section_anchor(sec, declared) == D("2000")


def test_ancora_none_quando_nessun_insieme_e_utilizzabile():
    sec = _sezione("sp", None, None)
    assert vr.section_anchor(sec, {"attivo": None, "passivo": None, "pareggio": None}) is None


# ------------------------------------------------- cancello: verdetto

_BS_ROTTO = {"sp09_disponibilita_liquide": D("700"), "sp16_debiti_breve": D("1000"),
             "totale_attivo": D("700"), "totale_passivo": D("1000")}
_BS_SANO = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("1000"),
            "totale_attivo": D("1000"), "totale_passivo": D("1000")}


def test_accetta_un_riscatto_che_riconcilia_e_migliora():
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(_BS_ROTTO), after=check_quadratura(_BS_SANO))
    assert ok, motivo


def test_rifiuta_un_riscatto_che_non_riconcilia_al_totale_stampato():
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("600"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(_BS_ROTTO), after=check_quadratura(_BS_SANO))
    assert not ok
    assert "riconcilia" in motivo


def test_rifiuta_un_riscatto_che_peggiora_la_quadratura():
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(_BS_SANO), after=check_quadratura(_BS_ROTTO))
    assert not ok
    assert "peggiora" in motivo


def test_rifiuta_un_riscatto_vuoto():
    vuoto = {"totale_attivo": D("0"), "totale_passivo": D("0")}
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("0"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(_BS_ROTTO), after=check_quadratura(vuoto))
    assert not ok


def test_rifiuta_quando_non_c_e_nessuna_ancora():
    sec = _sezione("sp", None, None)
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": None, "passivo": None, "pareggio": None},
        before=check_quadratura(_BS_ROTTO), after=check_quadratura(_BS_SANO))
    assert not ok
    assert "ancora" in motivo
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: FAIL — `AttributeError: module 'importers.vision_rescue' has no attribute 'totals_are_coherent'`

- [ ] **Step 3: Implementare il cancello**

In coda a `importers/vision_rescue.py`:

```python
# --------------------------------------------------------------- il cancello

# La stessa tolleranza di _select_dedup / _reconcile_trial_to_declared: non una nuova.
_TOL_ABS = Decimal("50")
_TOL_PCT = Decimal("0.005")
# I totali stampati o tornano al centesimo o sono stati letti male: qui non si
# tollera nulla, e' un'identita' contabile, non una riconciliazione.
_COHERENCE_TOL = Decimal("0.05")


def reconcile_tolerance(total: Decimal) -> Decimal:
    return max(_TOL_ABS, abs(total) * _TOL_PCT)


def totals_are_coherent(sec: VisionSection) -> bool:
    """I totali LETTI dalla vision tornano fra loro?

    SP: attivo + perdita == passivo, oppure attivo == passivo + utile.
    CE: costi + utile == ricavi, oppure costi == ricavi + perdita.

    E' questa coerenza interna che autorizza a preferirli alle ancore di testo quando
    quelle si contraddicono (budget_623: il testo legge un passivo che il PDF non
    stampa). Senza entrambi i totali di colonna non c'e' identita' da verificare.
    """
    left, right = sec.totals.get("left"), sec.totals.get("right")
    if left is None or right is None:
        return False
    utile = sec.totals.get("utile") or Z
    perdita = sec.totals.get("perdita") or Z
    return (abs((left + perdita) - right) <= _COHERENCE_TOL
            or abs(left - (right + utile)) <= _COHERENCE_TOL)


def section_anchor(sec: VisionSection,
                   declared: Dict[str, Optional[Decimal]]) -> Optional[Decimal]:
    """Il totale stampato contro cui misurare la sezione ricostruita.

    Preferisce il totale letto in vision quando i totali vision sono coerenti fra loro;
    altrimenti ricade sulle ancore di testo. None quando nessuno dei due insiemi e'
    utilizzabile — e allora il riscatto si scarta, non si accetta al buio.
    """
    if totals_are_coherent(sec):
        left = sec.totals.get("left")
        if left:
            return left
    if sec.section == "sp":
        for key in ("attivo", "pareggio", "passivo"):
            value = (declared or {}).get(key)
            if value:
                return value
        return None
    value = (declared or {}).get("costi")
    return value or None


def accept_rescue(section: str, rebuilt_total: Decimal, sec: VisionSection,
                  declared: Dict[str, Optional[Decimal]],
                  before, after) -> Tuple[bool, str]:
    """Tre condizioni, tutte necessarie (spec §3). Ritorna (accettato, motivo).

    `rebuilt_total` e' il totale LORDO della sezione ricostruita — per lo SP la somma
    dell'attivo netto PIU' la massa dei fondi nettati, perche' il totale stampato su
    questi file e' lordo (stessa aritmetica del cancello 1 di _hier_reconstruct).
    `before`/`after` sono i Quadratura del foglio prima e dopo il riscatto.
    """
    anchor = section_anchor(sec, declared)
    if anchor is None or anchor <= 0:
        return False, "nessuna ancora utilizzabile (ne' i totali vision ne' quelli di testo)"

    delta = abs(anchor - rebuilt_total)
    tol = reconcile_tolerance(anchor)
    if delta > tol:
        return False, (f"non riconcilia al totale stampato: ricostruito {rebuilt_total:,.2f} "
                       f"contro {anchor:,.2f} (scarto {delta:,.2f} > {tol:,.2f})")

    if after.is_empty:
        return False, "il riscatto produce un'estrazione vuota"

    improved = (abs(after.sbilancio) < abs(before.sbilancio)
                or after.plug_residual < before.plug_residual
                or (not before.utile_match and after.utile_match))
    worsened = (abs(after.sbilancio) > abs(before.sbilancio)
                or after.plug_residual > before.plug_residual
                or (before.utile_match and not after.utile_match))
    if worsened or not improved:
        return False, (f"peggiora o non migliora la quadratura: sbilancio "
                       f"{before.sbilancio:,.2f} -> {after.sbilancio:,.2f}, residuo "
                       f"{before.plug_residual:,.2f} -> {after.plug_residual:,.2f}")

    return True, (f"riconcilia a {anchor:,.2f} (scarto {delta:,.2f}); sbilancio "
                  f"{before.sbilancio:,.2f} -> {after.sbilancio:,.2f}")
```

- [ ] **Step 4: Eseguire i test**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: tutti PASS.

- [ ] **Step 5: Commit**

```bash
git diff --stat
git add importers/vision_rescue.py tests/test_vision_rescue.py
git commit -m "feat(import): il cancello che decide se tenere un riscatto vision"
```

---

## Task 7: innesco in `pdf_importer` e ri-esecuzione della catena

**Files:**
- Modify: `importers/pdf_importer.py` — nuovo helper di modulo + ~15 righe di innesco fra il blocco
  `if not _authoritative:` e la riga `others = ", ".join(...)` (attorno a `:1100`)
- Test: `tests/test_vision_rescue.py` (append)

**Interfaces:**
- Produces: `_apply_vision_rescue(file_path, bs, ce, declared, donor_bs, ocr_text, reader=None) ->
  Tuple[Dict[str, Decimal], Dict[str, Decimal], List[str]]` — restituisce `(bs, ce, sezioni_riscattate)`.
  `sezioni_riscattate` è una lista di `"sp"`/`"ce"`, vuota quando nulla è stato accettato.
  `reader` è iniettabile per i test (default: `vision_rescue.read_section`).

- [ ] **Step 1: Scrivere i test che falliscono**

Aggiungere in coda a `tests/test_vision_rescue.py`:

```python
from importers.pdf_importer import _apply_vision_rescue  # noqa: E402


_BS_624 = {   # SP corretto: quadra. Il rotto e' il CE.
    "sp09_disponibilita_liquide": D("2181734.09"),
    "sp16_debiti_breve": D("2172827.30"),
    "sp13_utile_perdita": D("8906.79"),
    "totale_attivo": D("2181734.09"), "totale_passivo": D("2181734.09"),
}
_CE_624_ROTTO = {"ce01_ricavi_vendite": D("2491786.38"),
                 "ce05_costi_materie_prime": D("938766.79")}


def test_non_viene_invocato_su_un_foglio_che_gia_quadra():
    chiamate = []

    def _reader(*a, **kw):
        chiamate.append(a)
        return None

    ce_ok = {"ce01_ricavi_vendite": D("2491786.38"),
             "ce05_costi_materie_prime": D("2482879.59")}
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_624), dict(ce_ok),
        declared={}, donor_bs=None, ocr_text=None, reader=_reader)
    assert riscattate == []
    assert chiamate == [], "nessuna chiamata vision su un foglio sano"
    assert ce == ce_ok


def test_un_eccezione_nel_riscatto_lascia_il_foglio_intatto():
    def _reader(*a, **kw):
        raise RuntimeError("boom")

    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_624), dict(_CE_624_ROTTO),
        declared={}, donor_bs=None, ocr_text=None, reader=_reader)
    assert riscattate == []
    assert bs == _BS_624
    assert ce == _CE_624_ROTTO


def test_un_riscatto_ce_che_riconcilia_sostituisce_il_conto_economico(monkeypatch):
    # La sezione CE riletta chiude il divario misurato: costi 2.482.879,59 contro i
    # 938.766,79 letti dal testo, utile 8.906,79 = sp13.
    sec = vr.VisionSection(
        section="ce",
        rows=(vr.VisionRow("73", "ACQUISTI MATERIE PRIME", D("2482879.59"), "left"),
              vr.VisionRow("70", "RICAVI DELLE VENDITE", D("2491786.38"), "right")),
        totals={"left": D("2482879.59"), "right": D("2491786.38"),
                "utile": D("8906.79"), "perdita": None},
    )
    monkeypatch.setattr(
        "importers.situazione_contabile_parser.section_pages",
        lambda _p: {"sp": [0], "ce": [1]},
    )
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_624), dict(_CE_624_ROTTO),
        declared={"costi": D("2482879.59"), "ricavi": D("2491786.38")},
        donor_bs=None, ocr_text=None, reader=lambda *a, **kw: sec)
    assert riscattate == ["ce"]
    assert ce["ce05_costi_materie_prime"] == D("2482879.59")
    assert bs == _BS_624, "il riscatto del CE non tocca lo stato patrimoniale"


def test_un_riscatto_ce_che_non_riconcilia_viene_scartato(monkeypatch):
    sec = vr.VisionSection(
        section="ce",
        rows=(vr.VisionRow("73", "ACQUISTI MATERIE PRIME", D("100000.00"), "left"),
              vr.VisionRow("70", "RICAVI DELLE VENDITE", D("2491786.38"), "right")),
        totals={"left": D("2482879.59"), "right": D("2491786.38"),
                "utile": D("8906.79"), "perdita": None},
    )
    monkeypatch.setattr(
        "importers.situazione_contabile_parser.section_pages",
        lambda _p: {"sp": [0], "ce": [1]},
    )
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_624), dict(_CE_624_ROTTO),
        declared={"costi": D("2482879.59"), "ricavi": D("2491786.38")},
        donor_bs=None, ocr_text=None, reader=lambda *a, **kw: sec)
    assert riscattate == []
    assert ce == _CE_624_ROTTO
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python -m pytest tests/test_vision_rescue.py -v`
Expected: FAIL — `ImportError: cannot import name '_apply_vision_rescue'`

- [ ] **Step 3: Implementare l'helper**

In `importers/pdf_importer.py`, come funzione di modulo (accanto a `_map_sc_keys`):

```python
def _apply_vision_rescue(file_path: str,
                         balance_sheet_data: Dict[str, Decimal],
                         income_data: Dict[str, Decimal],
                         declared: Dict[str, Optional[Decimal]],
                         donor_bs: Optional[Dict[str, Decimal]],
                         ocr_text: Optional[str],
                         reader=None) -> Tuple[Dict[str, Decimal], Dict[str, Decimal], List[str]]:
    """Riscatto vision per sezione, in coda alla catena route C.

    Innesco: check_quadratura sul foglio FINITO. La posizione e' deliberata — innescare
    prima del netting farebbe scattare il riscatto su un attivo ancora lordo, un divario
    che il netting dei fondi chiude da solo. Le due sezioni si innescano in modo
    indipendente: un file puo' riscattare il CE e lasciare l'SP com'e'.

    Ogni errore e' NON fatale: si logga e si tiene il candidato precedente. Se il
    riscatto non riesce, il foglio resta esattamente com'e' oggi.
    """
    from importers import vision_rescue as vr
    from importers.iv_cee_hierarchy import check_quadratura
    from importers.situazione_contabile_parser import (
        build_ce_from_vision, build_sp_from_vision, section_pages,
    )

    read = reader or vr.read_section
    rescued: List[str] = []
    try:
        before = check_quadratura(balance_sheet_data, income_data)
    except Exception as err:
        logger.warning(f"Riscatto vision: quadratura iniziale non calcolabile ({err})")
        return balance_sheet_data, income_data, rescued

    sp_broken = before.is_empty or abs(before.sbilancio) > Decimal("0.01") or before.masked
    ce_broken = not before.utile_match
    if not sp_broken and not ce_broken:
        return balance_sheet_data, income_data, rescued

    try:
        pages = section_pages(file_path)
    except Exception as err:
        logger.warning(f"Riscatto vision: pagine per sezione non determinabili ({err})")
        return balance_sheet_data, income_data, rescued

    # --- Conto economico ---------------------------------------------------
    if ce_broken:
        try:
            sec = read(file_path, pages.get("ce", []), "ce")
            if sec is not None and sec.rows:
                new_ce = _map_sc_keys(build_ce_from_vision(
                    [(r.code, r.description, r.amount, r.column) for r in sec.rows]))
                rebuilt = sum((r.amount for r in sec.rows if r.column == "left"),
                              Decimal("0"))
                after = check_quadratura(balance_sheet_data, new_ce)
                ok, why = vr.accept_rescue("ce", rebuilt, sec, declared, before, after)
                logger.info(f"Riscatto vision CE: {'accettato' if ok else 'scartato'} — {why}")
                if ok:
                    income_data = new_ce
                    before = after
                    rescued.append("ce")
        except Exception as err:
            logger.warning(f"Riscatto vision CE fallito ({type(err).__name__}: {err})")

    # --- Stato patrimoniale ------------------------------------------------
    if sp_broken:
        try:
            sec = read(file_path, pages.get("sp", []), "sp")
            if sec is not None and sec.rows:
                utile = (sec.totals.get("utile")
                         or (-(sec.totals["perdita"]) if sec.totals.get("perdita") else Decimal("0")))
                new_bs = _map_sc_keys(build_sp_from_vision(
                    [(r.code, r.description, r.amount, r.column) for r in sec.rows],
                    utile=utile))
                netted = new_bs.get('_netted_contra', Decimal('0'))
                # Il totale stampato e' LORDO quando i fondi stanno sul passivo: si
                # misura il lordo contro il lordo (stesso cancello di _hier_reconstruct).
                rebuilt = new_bs.get('totale_attivo', Decimal('0')) + netted

                # Stessa post-elaborazione degli altri candidati.
                if donor_bs is not None:
                    from importers.situazione_contabile_parser import overlay_debt_typing
                    new_bs = overlay_debt_typing(new_bs, donor_bs)
                from importers.situazione_contabile_parser import net_contra_accounts
                new_bs, _contra = net_contra_accounts(
                    new_bs, file_path, text=ocr_text, declared=declared)
                from importers.pdf_extractor_llm import _reconcile_trial_to_declared
                _decl = dict(declared or {})
                _cut = _contra if _contra > 0 else netted
                if _cut > 0:
                    for _k in ('attivo', 'passivo', 'pareggio'):
                        if _decl.get(_k):
                            _decl[_k] = _decl[_k] - _cut
                new_bs = _reconcile_trial_to_declared(new_bs, _decl, "vision")

                after = check_quadratura(new_bs, income_data)
                ok, why = vr.accept_rescue("sp", rebuilt, sec, declared, before, after)
                logger.info(f"Riscatto vision SP: {'accettato' if ok else 'scartato'} — {why}")
                if ok:
                    balance_sheet_data = new_bs
                    rescued.append("sp")
        except Exception as err:
            logger.warning(f"Riscatto vision SP fallito ({type(err).__name__}: {err})")

    return balance_sheet_data, income_data, rescued
```

- [ ] **Step 4: Innescare dentro la catena route C**

In `importers/pdf_importer.py`, **subito dopo** il blocco `if not _authoritative:` (cioè dopo la
riga `logger.warning(f"Route C: declared-result reconcile skipped: {_rc_err}")`) e **prima** di
`others = ", ".join(...)`, inserire:

```python
                # Riscatto vision (spec 2026-08-14): il foglio FINITO non quadra ma il
                # numero giusto e' stampato sulla pagina — e' il text layer a non
                # arrivarci. Rilegge in vision le sole pagine della sezione che non
                # torna. La posizione in coda alla catena e' deliberata: prima del
                # netting il riscatto scatterebbe su un attivo ancora lordo.
                _rescued_sections = []
                try:
                    _donor = next((c[1] for c in candidates if c[3] == "deterministico"), None)
                    balance_sheet_data, income_data, _rescued_sections = _apply_vision_rescue(
                        file_path, balance_sheet_data, income_data,
                        declared=_dc0, donor_bs=_donor, ocr_text=ocr_text)
                    if _rescued_sections:
                        residual = balance_sheet_data.get('_plug_residual', residual)
                        source = f"{source}+vision({'+'.join(_rescued_sections)})"
                except Exception as _vr_err:
                    logger.warning(f"Route C: riscatto vision saltato: {_vr_err}")
```

E, nella costruzione del `validation_report` (funzione `_validation_report_payload`, chiamata a
`:1335`), registrare la provenienza. Il modo più economico e coerente con `+mineru-<ver>`: dopo
l'innesco, se `_rescued_sections` non è vuoto, aggiungere al `parser_version` persistito il suffisso
`+vision-<sezioni>`. Nel blocco che costruisce `_stored_parser_version` (`:1339-1375`), aggiungere:

```python
        if _rescued_sections:
            _stored_parser_version = (
                f"{_stored_parser_version}+vision-{'-'.join(_rescued_sections)}")
```

**Attenzione allo scope:** `_rescued_sections` è definita dentro `if candidates:`. Inizializzarla a
`[]` accanto alle altre variabili di route C (prima di `if is_trial_balance:`) così che il blocco
del `parser_version` la trovi sempre definita.

- [ ] **Step 5: Eseguire i test**

Run: `python -m pytest tests/test_vision_rescue.py tests/test_section_pages.py -v`
Expected: tutti PASS.

- [ ] **Step 6: Commit**

```bash
git diff --stat    # pdf_importer.py: ~110 righe. NON deve toccare i file CRLF.
git add importers/pdf_importer.py tests/test_vision_rescue.py
git commit -m "feat(import): innescare il riscatto vision quando il foglio finito non quadra"
```

---

## Task 8: i due PDF veri, e la misura che nient'altro si è mosso

Questa è la task che verifica gli obiettivi della spec. **L'obiettivo 2 (budget_623) è dichiarato
incerto dalla spec stessa** (§Rischi noti 2): l'evidenza copre solo la pagina 1 del patrimoniale.
Se non si chiude, non forzare nulla — riportarlo, e verificare che gli obiettivi 3 e 4 reggano.

**Files:**
- Test: `tests/test_vision_rescue.py` (append)

**Interfaces:**
- Consumes: tutto il precedente. Richiede `ANTHROPIC_API_KEY` e i PDF in `tests/debug/`; entrambi
  gated con `skipif`.

- [ ] **Step 1: Scrivere i test gated**

Aggiungere in coda a `tests/test_vision_rescue.py`:

```python
# ------------------------------------------------- i due PDF veri (gated)

_DEBUG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug")
_PDF_624 = os.path.join(_DEBUG, "budget_624_2024 Commercio al dettaglio di ferramenta, "
                                "vernici, vetro piano e materiale elettrico e termoidraulico .pdf")
_PDF_623 = os.path.join(_DEBUG, "budget_623_2025 Commercio al dettaglio di ferramenta, "
                                "vernici, vetro piano e materiale elettrico e termoidraulico  .pdf")

_needs_live = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="riscatto vision: serve ANTHROPIC_API_KEY (nessuna chiamata in CI)",
)


@_needs_live
@pytest.mark.skipif(not os.path.exists(_PDF_624), reason="PDF di debug non presente")
def test_budget_624_il_conto_economico_torna():
    # `probe` esegue il percorso di produzione completo (estrazione -> catena route C
    # -> reconcile -> validate) e non solleva mai: restituisce un record piatto.
    from tests._import_probe import probe
    rec = probe(_PDF_624)
    assert rec["error"] is None, rec.get("traceback", rec["error"])
    assert rec["utile_ce"] == pytest.approx(8906.79, abs=1.0)
    assert rec["sp13"] == pytest.approx(8906.79, abs=1.0)


@_needs_live
@pytest.mark.skipif(not os.path.exists(_PDF_623), reason="PDF di debug non presente")
def test_budget_623_il_patrimoniale_torna():
    from tests._import_probe import probe
    rec = probe(_PDF_623)
    assert rec["error"] is None, rec.get("traceback", rec["error"])
    assert rec["totale_attivo"] == pytest.approx(2420397.40, abs=100.0)
    assert abs(rec["sbilancio"]) <= 1.0
    assert not rec["masked"]
```

- [ ] **Step 2: Eseguirli e leggere il risultato**

Run:
```bash
python -m pytest tests/test_vision_rescue.py -v -k "624 or 623"
```

Se `624` passa: obiettivo 1 chiuso.
Se `623` fallisce: **non forzare**. Leggere il log (`--log-cli-level=INFO`) per capire quale
condizione del cancello ha respinto il riscatto, e registrarlo nel commit e nel report finale.
Il file deve comunque importarsi esattamente come prima — questo è l'obiettivo 4.

- [ ] **Step 3: Misurare che nient'altro si sia mosso**

Run:
```bash
python -m pytest tests/test_import_baseline.py -v
python -m pytest tests/test_contra_netting.py tests/test_dedup_partition.py tests/test_reliability.py -v
```
Expected: tutti PASS. Il riscatto parte **solo** su file già rotti, quindi la baseline non deve
muoversi di un carattere (obiettivo 3). Se un file della baseline cambia, il riscatto sta
innescando dove non doveva: **non aggiornare la baseline** — capire perché.

- [ ] **Step 4: Aggiornare la documentazione**

In `CLAUDE.md`, nella sezione "PDF Import (Claude LLM)", aggiungere una sottosezione dopo
"CoGe LLM extractor for trial balances":

```markdown
#### Riscatto vision per sezione (`importers/vision_rescue.py`)
Terzo candidato route C prodotto **solo su richiesta**, alla FINE della catena
(`overlay_debt_typing` → `net_contra_accounts` → `_reconcile_trial_to_declared`), quando
`check_quadratura` sul foglio finito dice `is_empty` / sbilancio / `masked` / utile CE ≠ sp13.
Le pagine della sola sezione che non torna (`situazione_contabile_parser.section_pages`) sono
rese a 200 dpi e rilette in vision: su questi file il numero giusto è STAMPATO ma il text layer
non ci arriva (mastri disegnati come vettori su budget_624; ordine di stream rotto su budget_623).
La sezione è **ricostruita da zero** dai mastri letti — mai sommata a quelli già estratti, che
richiederebbe di sapere cosa era già dentro e conta due volte un mastro (è l'errore che fece
revertare il tentativo del 14/07). Solo i **mastri**: i dettagli a codice più lungo la vision li
sbaglia e non servono (`mastro_level_rows`).
**Il cancello** (`accept_rescue`) tiene il riscatto solo se tutte e tre: riconcilia al totale
stampato entro `max(50 €; 0,5%)`; i totali letti dalla vision sono coerenti fra loro
(`attivo + perdita == passivo`, `costi + utile == ricavi`) — è questa coerenza che autorizza a
preferirli alle ancore di testo quando quelle si contraddicono, come su budget_623; e la
quadratura risultante è **strettamente migliore**. Se una cade si scarta tutto e resta il
candidato di prima con i suoi warning. **Un solo tentativo per sezione**, tetto `MAX_RESCUE_PAGES
= 8`, ogni errore non fatale. Le due sezioni si innescano indipendentemente; il riscatto del CE
non tocca `sp13` e quello dell'SP non tocca il conto economico. Un import riscattato è
riconoscibile a posteriori dal suffisso `+vision-<sezioni>` su `parser_version`.
Tests: `tests/test_vision_rescue.py`, `tests/test_section_pages.py`.
```

- [ ] **Step 5: Commit finale**

```bash
git diff --stat
git add tests/test_vision_rescue.py CLAUDE.md
git commit -m "test(import): i due PDF veri del riscatto vision, piu' la documentazione"
```

---

## Note di esecuzione

- **`uvicorn --reload` non ricarica i moduli condivisi.** Se si prova il riscatto dall'app,
  riavviare il backend a mano dopo ogni modifica a `importers/`, o la correzione "non funziona".
- **L'estrazione vision è non deterministica.** Una singola esecuzione dei test gated su PDF reale
  non è una prova di regressione: se un risultato sembra spostarsi, ripetere prima di concludere.
- **Non toccare `tests/fixtures/import_baseline.json`** in questo lavoro. Se si muove, è un bug del
  riscatto, non una baseline da rinfrescare.
