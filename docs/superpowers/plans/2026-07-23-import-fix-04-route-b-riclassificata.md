# Piano 04 — Route B: "situazione riclassificata dettagliata" e riallineamento CE↔SP

> **REVISIONE 2026-07-27.** Il Task 1 è stato riscritto: la diagnosi precedente era **sbagliata** ed è
> stata sostituita dalla causa reale, verificata sul file (§Task 1 "Contesto tecnico"). Il Task 2 è stato
> riscritto perché partiva da una **premessa falsa** sullo stato attuale del codice.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** importare correttamente i bilanci "situazione contabile riclassificata dettagliata" (route B →
IV-CEE LLM) che oggi falliscono con attivo vuoto (176, 182) e decidere onestamente il caso in cui il
risultato dichiarato conferma sp13 ma l'utile CE estratto differisce di pochi euro (319).

**Architettura:** due difetti distinti, due task indipendenti.
(1) `_filter_difference_columns` (`importers/pdf_extractor_llm.py:397`) confonde una **voce di legge del
CE** con l'**intestazione della colonna analitica** e cancella l'intera pagina.
(2) `enforce_ce_sp_identity` (`importers/iv_cee_hierarchy.py`) è oggi **diagnostica pura** per scelta di
progetto; il caso 319 richiede una decisione di policy, non un bugfix.

**Tech stack:** Python, PyMuPDF (geometria parole), pytest.
**Dipende dal Piano 05** (spazio `marker` del layer semantico, per distinguere l'intestazione di colonna
dalla voce di legge). Non dipende dal Piano 01.

## Vincoli globali
Quadro generale §7. La correzione del filtro colonne deve restare **geometrica e conservativa**: nel
dubbio **non tagliare nulla** (`return None`), perché un taglio sbagliato distrugge la pagina mentre un
mancato taglio produce solo una colonna in più nel testo passato all'LLM — danno asimmetrico.

---

### Task 1: filtro DIFFERENZA/SCOST che preserva le colonne importo

**Files:**
- Modify: `importers/pdf_extractor_llm.py:397-441` (`_filter_difference_columns`)
- Test: `tests/test_filter_difference_columns.py` (nuovo)

**Contesto tecnico — CAUSA REALE, verificata sul file (2026-07-27).**

La diagnosi precedente ("gli header anno cadono a x elevata, il cutoff cade a sinistra della colonna
31/12/2025") **era sbagliata**, e il fix che ne derivava non avrebbe funzionato. Ecco i dati.

Geometria reale di budget_176 pagina 1 (`page.get_text('words')`, righe ricostruite per coordinata y):

```
Cod.@31   Descrizione@157   31/12/2025@319   31/12/2024@389   Differenza@460   Scost.@525   %@552
2@38  Stato patrimoniale attivo   1.116.259,44@332  1.119.879,38@402  -3.619,94@483  -0,323@548
```

Le colonne importo dell'esercizio stanno a **x≈332** e **x≈402**; l'intestazione `Differenza` sta a
**x=460**. Un cutoff a `460 − 2 = 458` sarebbe **corretto** e preserverebbe entrambe le colonne.

Ma il log di produzione dice:

```
Filtered DIFFERENZA/SCOST. columns at x>=115.0 from source page 1
```

Il cutoff calcolato è **115**, non 458. Motivo (`pdf_extractor_llm.py:407-419`):

```python
difference_headers = [w for w in words if str(w[4]).strip().casefold().startswith('differenza')]
cutoff_x = min(float(w[0]) for w in difference_headers) - 2
```

Il `min` è su **tutte** le parole della pagina che iniziano per "differenza". Sulla pagina 1 di 176 ce ne
sono **due** (verificato con uno scan delle words): `Differenza@460` — l'intestazione di colonna — e
**`Differenza@117`**, che è la prima parola della voce di legge del Conto Economico
**«Differenza tra valore e costi di produzione (A−B)»** (art. 2425). Vince il minimo, 117 → cutoff 115 →
`kept = [w for w in words if w[0] < 115]` → **sopravvivono solo `Cod.` e le prime lettere delle
descrizioni**. Tutti gli importi di entrambi gli anni, su tutta la pagina, vengono buttati. L'LLM riceve
un elenco di descrizioni senza numeri, l'attivo risulta vuoto e l'import fallisce.

Questa è una **collisione fra due significati della stessa parola**: intestazione di colonna analitica vs
voce civilistica del CE. È lo stesso difetto strutturale del Piano 05 (§0.4) — ed è il motivo per cui
questo piano ora dipende dal 05 e non dal 01.

**Fix, in tre parti (tutte necessarie):**
1. l'header di colonna si riconosce **come marker**, non per prefisso di stringa: usare
   `classify_label(parola/riga, space="marker")` e accettare solo `__col_scostamento`. La voce
   «Differenza tra valore e costi di produzione» **non** è un marker di colonna (test dedicato nel Piano
   05 Task 2);
2. i candidati header vanno cercati **solo nella banda verticale dell'intestazione** (le parole che
   condividono la riga y di `Scost.`/`%`/degli header anno), non su tutta la pagina;
3. il cutoff deve essere **validato**: se a destra del cutoff non resta almeno una colonna di importi, o
   se a sinistra del cutoff non ne restano almeno due, il calcolo è sbagliato → `return None`
   (nessun taglio). È la regola asimmetrica dei vincoli globali.

**Interfaces:**
- Consumes/Produces: `_filter_difference_columns(page) -> Optional[str]` (firma invariata).

- [ ] **Step 1: test che fallisce.** Poiché serve una `fitz.Page`, si estrae la logica geometrica in una
funzione pura testabile `_difference_cutoff_x(words) -> Optional[float]` dove `words` è la lista
`(x0,y0,x1,y1,text,...)` di PyMuPDF.

```python
# tests/test_filter_difference_columns.py
from importers.pdf_extractor_llm import _difference_cutoff_x


def W(x0, text, y0=0.0):
    return (x0, y0, x0 + 10, y0 + 8.0, text, 0, 0, 0)


HEADER_Y = 0.0
ROW_Y = 40.0


def test_cutoff_a_destra_delle_colonne_importo():
    words = [
        W(31, "Cod.", HEADER_Y), W(157, "Descrizione", HEADER_Y),
        W(319, "31/12/2025", HEADER_Y), W(389, "31/12/2024", HEADER_Y),
        W(460, "Differenza", HEADER_Y), W(525, "Scost.", HEADER_Y),
        W(38, "2", ROW_Y), W(57, "Immobilizzazioni", ROW_Y),
        W(332, "1.116.259,44", ROW_Y), W(402, "1.119.879,38", ROW_Y),
        W(483, "-3.619,94", ROW_Y), W(548, "-0,323", ROW_Y),
    ]
    cut = _difference_cutoff_x(words)
    assert cut is not None and 402 < cut <= 460


def test_la_voce_di_legge_del_ce_non_e_un_header_di_colonna():
    """budget_176: 'Differenza tra valore e costi di produzione (A-B)' e' una VOCE
    dell'art. 2425 a x=117, NON l'intestazione della colonna analitica a x=460.
    Il vecchio min(x) prendeva 117 -> cutoff 115 -> pagina distrutta."""
    words = [
        W(31, "Cod.", HEADER_Y), W(319, "31/12/2025", HEADER_Y),
        W(389, "31/12/2024", HEADER_Y),
        W(460, "Differenza", HEADER_Y), W(525, "Scost.", HEADER_Y),
        W(117, "Differenza", 300.0), W(160, "tra", 300.0), W(180, "valore", 300.0),
        W(210, "e", 300.0), W(220, "costi", 300.0), W(250, "di", 300.0),
        W(262, "produzione", 300.0),
        W(332, "45.000,00", 300.0), W(402, "41.000,00", 300.0),
    ]
    cut = _difference_cutoff_x(words)
    assert cut is not None and cut > 402, f"cutoff {cut} amputa le colonne importo"


def test_nel_dubbio_non_taglia():
    # nessun header anno affidabile a sinistra di Differenza -> meglio non tagliare
    words = [W(10, "10"), W(40, "Cassa"), W(130, "2025"), W(180, "Saldo")]
    assert _difference_cutoff_x(words) is None


def test_nessun_taglio_senza_scostamento():
    words = [W(31, "Cod."), W(319, "2025"), W(389, "2024"), W(460, "Differenza")]
    assert _difference_cutoff_x(words) is None
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_filter_difference_columns.py -q`
Expected: `ImportError: cannot import name '_difference_cutoff_x'`. Dopo l'estrazione della sola
funzione (senza correggerla), `test_la_voce_di_legge_del_ce_non_e_un_header_di_colonna` deve fallire con
`cutoff 115.0 amputa le colonne importo` — **è la riproduzione esatta del bug**; non procedere finché non
si è vista quella riga.

- [ ] **Step 3: implementare.**

```python
def _difference_cutoff_x(words) -> Optional[float]:
    """x oltre il quale tagliare le colonne DIFFERENZA/SCOST.

    Il vecchio calcolo era `min(x di ogni parola che inizia per 'differenza') - 2`.
    Su budget_176 la voce di legge del CE «Differenza tra valore e costi di
    produzione (A-B)» sta a x=117 e vinceva sul vero header di colonna a x=460:
    cutoff 115 -> l'intera pagina (importi compresi) veniva buttata.

    Ora: l'header si cerca SOLO nella banda verticale dell'intestazione, e' un
    MARKER di colonna (non un prefisso di stringa), e il cutoff e' valido solo se
    lascia a sinistra almeno due colonne di importi. Nel dubbio: None (nessun taglio).
    """
    from importers.label_semantics import classify_label       # Piano 05

    def _is_col_marker(w) -> bool:
        hit = classify_label(str(w[4]), space="marker")
        return hit is not None and hit.target == "__col_scostamento"

    markers = [w for w in words if _is_col_marker(w)]
    if not markers:
        return None

    # 1) banda dell'intestazione = riga y del marker piu' ALTO nella pagina
    header_y = min(float(w[1]) for w in markers)
    band = [w for w in words if abs(float(w[1]) - header_y) <= 3.0]
    band_markers = [w for w in band if _is_col_marker(w)]
    if len(band_markers) < 2:          # servono sia 'Differenza' sia 'Scost.'
        return None
    diff_x = min(float(w[0]) for w in band_markers)

    # 2) il cutoff deve lasciare a sinistra almeno DUE colonne di importi
    amounts_left = {round(float(w[0]) / 5) for w in words
                    if _AMOUNT_TOKEN_RE.fullmatch(str(w[4]).strip())
                    and float(w[0]) < diff_x}
    if len(amounts_left) < 2:
        return None
    return diff_x - 2
```

`_AMOUNT_TOKEN_RE` è una regex di importo italiano (`-?\(?\d{1,3}(?:[.\s]\d{3})*,\d{2}\)?`), da definire
a livello di modulo se non esiste già. Il raggruppamento `round(x/5)` conta le **colonne** distinte, non i
singoli numeri.

E in `_filter_difference_columns` sostituire il calcolo di `cutoff_x` con:

```python
    cutoff_x = _difference_cutoff_x(words)
    if cutoff_x is None:
        return None
```

(rimuovendo le righe che ricomputano `difference_headers`/`has_deviation`/`years`/`cutoff_x` — ora dentro
l'helper). **Nota:** sparisce anche il requisito `len(years) >= 2` basato su
`re.fullmatch(r"20\d{2}")`, che su questi file non matcha mai perché l'header è una parola sola
(`31/12/2025`); il suo ruolo (non tagliare un layout monocolonna) è ora svolto dal controllo "almeno due
colonne di importi a sinistra", che è più diretto e non dipende dalla grafia della data.

- [ ] **Step 4: verificare che passi + import reale**

Run: `python -m pytest tests/test_filter_difference_columns.py -q` → `2 passed`

```bash
python tests/_import_probe.py "Test/successTerzo/success/budget_176_2R IMMOBILIARE.pdf" standard
python tests/_import_probe.py "Test/successTerzo/success/budget_182_2R IMMOBILIARE1.pdf" standard
```
Expected: l'attivo NON è più vuoto (sp02/sp03/sp06/sp09 valorizzati); `stored.total_assets` = 1.116.259,44;
sbilancio 0. (Se l'attivo compare ma resta uno scarto per il netting dei fondi materiali esposti come
righe positive separate, quello è coperto dal Piano 03 — verificare la combinazione.)

- [ ] **Step 5: regressione** — budget_314 era il file per cui il filtro DIFFERENZA fu introdotto:

```bash
python tests/_import_probe.py "Test/successTerzo/success/budget_314_2024.pdf" standard
```
Expected: `ok=true`, totali invariati (il filtro continua a togliere Differenza/Scost.).

- [ ] **Step 6: Commit**

```bash
git add importers/pdf_extractor_llm.py tests/test_filter_difference_columns.py
git commit -m "fix(route-B): il filtro DIFFERENZA/SCOST preserva le colonne ESERCIZIO (budget_176/182 attivo non piu' vuoto)"
```

---

### Task 2: riallineamento CE↔SP quando il risultato dichiarato conferma sp13

**Files:**
- Modify: `importers/iv_cee_hierarchy.py` (`enforce_ce_sp_identity`)
- Test: `tests/test_enforce_ce_sp_small_gap.py` (nuovo)

**Contesto — CORREZIONE 2026-07-27.** La versione precedente di questo Task diceva di «rimuovere o
allargare la condizione che oggi salta il plug». **Quella condizione non esiste.** Stato attuale
verificato (`iv_cee_hierarchy.py:627-660`):

```python
def enforce_ce_sp_identity(bs, ce, label="", tol=None, prefer="sp13", declared=None):
    """Diagnose the CE/SP identity without altering either statement.

    ``prefer`` and ``declared`` remain accepted so existing callers do not break,
    but an arbiter may only select/reject a candidate.  It must never create a
    balancing amount in reserves, other income or other costs.
    """
```

La funzione è **diagnostica pura per scelta di progetto**: emette `_ce_sp_difference` e un warning, e non
tocca nulla. Il plug descritto in CLAUDE.md (§"CE↔SP identity enforcement") **è documentazione obsoleta**,
non codice. Quindi questo Task non è un bugfix: è la **proposta di reintrodurre un plug che il codice
attuale vieta esplicitamente**. Va trattato come tale.

Il caso: 319, sp13 = −71.563,96 (ancorato al pareggio), utile CE estratto = −68.518,00, scarto 3.045,96;
il risultato dichiarato dal documento (A.IX) **conferma sp13**. Oggi `check_quadratura` blocca l'import.

**Decisione da prendere prima di scrivere codice** (non è una scelta tecnica, è di prodotto — portarla
all'utente, non deciderla da soli):

**DECISA — 2026-07-27: nessun plug. Retry + revisione.** L'opzione "spalmare lo scarto su `ce12`/`ce04`"
è **scartata**: contraddice le invarianti già documentate in `docs/import/REGOLE-IMPORT-00-INDICE.md`
(**D3**: `enforce_ce_sp_identity` è puramente diagnostico; **D1**: nessun plug; **D4**:
`reconcile_ivcee_balance` ritorna una copia invariata) e ricrea la "quadratura finta" che
`check_quadratura` esiste per smascherare. Il repo ha già fatto consapevolmente il percorso opposto
(commit `4a2e80f` "diagnosi oneste al posto dei plug").

**Procedura in tre passi, in quest'ordine:**

1. **Ri-estrazione mirata del solo Conto Economico.** I 3.045,96 mancanti sono costi che l'estrazione ha
   perso, non un'incoerenza del documento: la risposta giusta è **rileggerli**, non fabbricarli. Un retry
   LLM sulla sola finestra CE (la stessa tecnica già prevista per la colonna prior nel Quadro §5), con il
   risultato dichiarato passato come vincolo nel prompt.
2. **Arbitraggio a tre**: confrontare `risultato dichiarato` / `sp13` / `utile CE ricalcolato`. Se dopo il
   retry due su tre coincidono entro tolleranza, si tiene quello e si prosegue normalmente.
3. **Se lo scarto resta**: importare **i valori così come sono estratti**, senza modificarne nessuno, con
   `validation_status = "review_required"` e `forecastable = False` (un CE che non ricostruisce il
   risultato non deve alimentare un forecast), warning esplicito e rimando a Rettifiche.

`enforce_ce_sp_identity` **non si tocca**: resta diagnostica. Va invece corretta la documentazione
(CLAUDE.md descrive un plug che il codice non ha — vedi drift D3).

**Interfaces:**
- Consumes/Produces: `enforce_ce_sp_identity(bs, ce, source, prefer=..., declared=...)` (firma invariata).

- [ ] **Step 1: implementare il retry mirato del CE** (passo 1 della procedura). Nessuna modifica a
`enforce_ce_sp_identity`.

- [ ] **Step 2: test che fallisce** — CE il cui utile differisce di poco da sp13, risultato dichiarato =
sp13:

```python
# tests/test_enforce_ce_sp_small_gap.py
from decimal import Decimal as D
from importers.iv_cee_hierarchy import enforce_ce_sp_identity


def test_riallinea_ce_a_sp13_quando_dichiarato_conferma_sp13():
    # utile CE -68518, sp13 -71563.96, dichiarato -71563.96 → allinea il CE
    bs = {"sp13_utile_perdita": D("-71563.96"),
          "totale_attivo": D("510159.11"), "totale_passivo": D("510159.11")}
    ce = {"ce01_ricavi_vendite": D("129500.03"),
          "ce12_oneri_diversi": D("5000.00"),
          # utile CE implicito = -68518.00 (costruito dai valori del test)
          "ce20_imposte": D("0")}
    out = enforce_ce_sp_identity(bs, ce, "import", prefer="sp13",
                                 declared={"utile": None, "perdita": D("71563.96")})
    from importers.iv_cee_hierarchy import _net_profit_from_ce
    assert abs(_net_profit_from_ce(out) - D("-71563.96")) <= D("2")


def test_no_op_quando_gia_coincidono():
    bs = {"sp13_utile_perdita": D("-71563.96")}
    ce = {"ce01_ricavi_vendite": D("100000"), "ce12_oneri_diversi": D("171563.96")}
    out = enforce_ce_sp_identity(bs, ce, "import", prefer="sp13", declared={})
    # nessuna modifica sostanziale (già -71563.96)
    from importers.iv_cee_hierarchy import _net_profit_from_ce
    assert abs(_net_profit_from_ce(out) - D("-71563.96")) <= D("2")
```

NB per l'implementatore: adeguare i valori del primo test in modo che
`_net_profit_from_ce(ce)` iniziale valga esattamente −68.518,00 (costruire i costi/ricavi coerenti),
così lo scarto verso sp13 sia 3.045,96 come nel file reale.

- [ ] **Step 3: verificare che fallisca**

Run: `python -m pytest tests/test_enforce_ce_sp_small_gap.py -q`
Expected: FAIL sul primo test (il CE non viene allineato).

- [ ] **Step 4: implementare i passi 2 e 3** (arbitraggio + `review_required`).

  Nel gate `check_quadratura` di `pdf_importer` (righe ~1107-1122): quando **solo** `utile_match` è falso
  (il pareggio Attivo=Passivo regge) e il retry del CE non ha chiuso lo scarto, **non sollevare**: salvare
  i valori come estratti con `validation_status="review_required"`, `forecastable=False` e il warning
  `Utile CE … != sp13 …` visibile all'utente. **Il pareggio Attivo=Passivo resta bloccante** — non si
  allenta nulla lì.

  ⚠️ Leggere il campo **strutturato** `Quadratura.utile_match`, non il testo del warning. Il Piano 02
  Task 3 (ora annullato) faceva `w.startswith("Utile CE")`: legare un gate bloccante al prefisso di un
  messaggio significa che riformularlo lo disattiva **in silenzio**.

- [ ] **Step 5: verificare + import reale**

Run: `python -m pytest tests/test_enforce_ce_sp_small_gap.py -q` → PASS.

```bash
python tests/_import_probe.py "Test/successTerzo/success/budget_319_detail_riclass - 2026-05-27T125618.533.pdf" standard
```
Expected: `ok=true`, sp13 = −71.563,96, utile CE allineato, sbilancio 0. (L'OCR di 319 resta un limite di
classificazione MinerU → Piano 06.)

- [ ] **Step 6: regressione CE↔SP** su file dove il risultato dichiarato conferma il CE (non sp13) — la
direzione opposta non deve cambiare:

```bash
python tests/_import_probe.py "Test/successTerzo/success/budget_302_Bilancio CEE al 31.12.2025 con dettaglio sottoconti.pdf" standard
python tests/_import_probe.py "Test/successTerzo/success/budget_320_nicee.pdf" standard
```
Expected: `ok=true`, totali invariati (stessa famiglia B1 di 319, già ok).

- [ ] **Step 7: Commit**

```bash
git add importers/iv_cee_hierarchy.py tests/test_enforce_ce_sp_small_gap.py
git commit -m "fix(CE-SP): riallinea il CE a sp13 quando il risultato dichiarato lo conferma e lo scarto e' piccolo (budget_319)"
```

---

## Accettazione del piano

- 176, 182: attivo valorizzato, total_assets 1.116.259,44, sbilancio 0.
- 319: import ok, sp13 −71.563,96.
- 314 (filtro DIFFERENZA), 302, 320 (famiglia B1): totali invariati.
- Campione pulito §6: invariato.
