# Piano 06 — OCR/MinerU: ricongiunzione col percorso standard

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** far sì che `/import/pdf-ocr` NON degradi i PDF a testo nativo e riesca sulle scansioni. Oggi
MinerU **sostituisce ciecamente** il testo (anche quando il PDF ha un testo nativo perfetto), perdendo la
geometria a due colonne dei trial balance → i 4 fallimenti solo-OCR dell'audit (Bilancino, 131, 132, 158).
La richiesta dell'utente: "i due percorsi si potrebbero ricongiungere dopo l'import" — cioè MinerU deve
essere un **provider di testo/tabelle alternativo**, non una pipeline parallela. A valle (classificatore →
estrattori → gates) i due percorsi sono già identici; questo piano elimina l'unica vera divergenza.

**Architettura:** in `importers/pdf_importer.py:333-362`, quando arriva un `extraction_context` MinerU, il
codice fa `sample_text = ocr_text = _mineru_full_text; is_scanned=False; _ocr_source=True`, sostituendo il
testo per SEMPRE. Il fix: **decidere la fonte del testo** in base alla qualità del testo NATIVO:
- testo nativo assente/corrotto (vera scansione) → usa MinerU (comportamento attuale) **e** consenti il
  candidato vision del percorso standard;
- testo nativo presente e non corrotto → usa il testo NATIVO per estrazione (route + estrattori standard),
  e usa il candidato MinerU (tabelle) SOLO come candidato aggiuntivo nella selezione route-C.

**Tech stack:** Python, PyMuPDF, MinerU 3.2.0 (Docker :8002), pytest + probe. Beneficia di TUTTI i piani
precedenti (il candidato MinerU passa negli stessi gates migliorati). Da eseguire PER ULTIMO.

## Vincoli globali
Quadro generale §7. In più: il contratto dell'endpoint `/import/pdf-ocr` NON cambia; cambia solo la logica
interna di scelta della fonte testo. Nessun fallback silenzioso a `/import/pdf` (resta l'errore 503 se
MinerU è spento — comportamento voluto).

---

### Task 1: scelta della fonte-testo in base alla qualità del nativo

> **RIVISTO 2026-07-27 — due correzioni prima di implementare.**
>
> **(a) La soglia "≥ 50 caratteri e non garbled" è troppo debole.** `len(native) >= 50` replica sì una
> soglia già in produzione (`is_scanned`), ma lì serve solo a dire "c'è del testo"; qui deve decidere
> **quale delle due fonti è migliore**, che è un'altra domanda. Un PDF con layer nativo **parziale ma non
> garbled** (es. solo le intestazioni vettoriali su pagine scansionate: centinaia di caratteri puliti e
> zero importi) oggi è salvato da MinerU e con questa regola verrebbe **degradato** al nativo povero. E il
> gate proposto non lo intercetterebbe, perché i 10 file-campione sono stati scelti fra quelli che
> importano bene **in standard**.
>
> Sostituire il booleano con un **punteggio di qualità** confrontabile fra le due fonti, calcolato allo
> stesso modo su entrambe:
> - **copertura pagine**: frazione di pagine con testo non banale;
> - **densità di importi**: quanti token-importo per pagina (un bilancio senza numeri non è un bilancio);
> - **controlli contabili presenti**: quanti marker `__tot_attivo` / `__tot_passivo` / `__pareggio` /
>   `__risultato` si riconoscono (Piano 05 spazio `marker`) — è il segnale più informativo, perché sono
>   proprio i numeri che i gate a valle useranno;
> - **righe legali/contabili riconosciute**: quante righe risolvono negli spazi `legal`/`account`;
> - **geometria disponibile**: il nativo ha coordinate reali (parola per parola), MinerU no — vantaggio
>   strutturale del nativo, da pesare esplicitamente perché abilita il Piano 07;
> - **caratteri corrotti**: `_text_layer_is_garbled` resta, come penalità, non come unico criterio;
> - **coerenza totali↔dettagli**: i totali riconosciuti riconciliano con la somma dei dettagli?
>
> Regola: si sceglie il nativo **a parità o vantaggio di punteggio** (perché porta la geometria);
> si sceglie MinerU solo quando **vince nettamente**. In caso di punteggi vicini e nativo non garbled:
> nativo. Il punteggio va **loggato** per entrambe le fonti — senza quello, una scelta sbagliata è
> indiagnosticabile.
>
> **(b) L'arrivo di MinerU non deve spegnere l'OCR locale a coordinate.** Verificato: nel blocco che
> installa il contesto MinerU (`importers/pdf_importer.py:~350-360`) vengono impostati
> `is_scanned = False` **e** `local_coordinate_ocr = False`; quel secondo flag è letto più avanti
> (`:744`) e disattiva il percorso RapidOCR a coordinate — che è **l'unico** in grado di alimentare il
> parser "verifica per segno" con bounding box esatte, ed è quello che oggi fa riuscire il Bilancino in
> standard mentre l'OCR fallisce. Il Task deve **disaccoppiare** le due cose: la presenza di testo MinerU
> dice "ho una fonte testuale alternativa", **non** "non serve l'OCR a coordinate". I due candidati
> devono poter coesistere ed essere confrontati con il punteggio del punto (a).

**Files:**
- Modify: `importers/pdf_importer.py:333-362` (blocco `_mineru_full_text`)
- Test: `tests/test_ocr_text_source.py` (nuovo)

**Interfaces:**
- Produces: `_choose_text_source(native_text, mineru_text, is_native_garbled) -> tuple[str, bool]`
  che ritorna `(text_to_use, use_mineru_as_primary)`. Consumata dal blocco import.

- [ ] **Step 1: test che fallisce**

```python
# tests/test_ocr_text_source.py
from importers.pdf_importer import _choose_text_source


def test_nativo_buono_vince_su_mineru():
    native = "TOTALE ATTIVO 1.000.000\n" * 50    # testo nativo ricco
    mineru = "roba ocr rumorosa"
    text, use_mineru = _choose_text_source(native, mineru, is_native_garbled=False)
    assert text == native and use_mineru is False


def test_nativo_assente_usa_mineru():
    text, use_mineru = _choose_text_source("", "TESTO MINERU RICCO " * 20,
                                           is_native_garbled=False)
    assert use_mineru is True and text.startswith("TESTO MINERU")


def test_nativo_corrotto_usa_mineru():
    text, use_mineru = _choose_text_source("_1_4_._4_7_2,9_2_ garbled",
                                           "TESTO MINERU " * 20, is_native_garbled=True)
    assert use_mineru is True
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_ocr_text_source.py -q`
Expected: ImportError.

- [ ] **Step 3: implementare** `_choose_text_source` (modulo-level) e cablarla:

```python
def _choose_text_source(native_text: str, mineru_text: str, is_native_garbled: bool):
    """Decide se estrarre dal testo NATIVO (preferito quando presente e sano) o dal
    testo MinerU (vere scansioni / nativo corrotto). MinerU degrada i trial balance a
    testo nativo (perde le due colonne), quindi non deve mai soppiantare un nativo buono
    (audit: Bilancino/131/132/158)."""
    native = (native_text or "").strip()
    mineru = (mineru_text or "").strip()
    native_ok = len(native) >= 50 and not is_native_garbled
    if native_ok:
        return native_text, False           # nativo primario; MinerU resta candidato (Task 2)
    if mineru:
        return mineru_text, True             # scansione / nativo rotto → MinerU primario
    return native_text, False                # niente MinerU → nativo (foss'anche povero)
```

Nel blocco `if _mineru_full_text and _mineru_full_text.strip():` (righe ~349-362) sostituire la
sostituzione incondizionata con:

```python
        _mineru_full_text = getattr(extraction_context, "full_text", "") if extraction_context is not None else ""
        if _mineru_full_text and _mineru_full_text.strip():
            _native_sample = sample_text            # testo nativo già estratto sopra
            _native_garbled = False
            try:
                from importers.pdf_extractor_llm import _text_layer_is_garbled
                _native_garbled = _text_layer_is_garbled(_native_sample)
            except Exception:
                pass
            _text_to_use, _use_mineru = _choose_text_source(
                _native_sample, _mineru_full_text, _native_garbled)
            if _use_mineru:
                sample_text = _text_to_use
                ocr_text = _text_to_use
                is_scanned = False
                local_coordinate_ocr = False
                _ocr_source = True
                logger.info("OCR: MinerU primario (nativo assente/corrotto), text_len=%d",
                            len(sample_text))
            else:
                # nativo buono: NON soppiantarlo. MinerU resta disponibile come
                # candidato aggiuntivo route-C (Task 2). L'import procede come standard.
                logger.info("OCR: testo nativo valido, MinerU usato solo come candidato")
```

- [ ] **Step 4: verificare + import reali**

Run: `python -m pytest tests/test_ocr_text_source.py -q` → PASS.

```bash
python tests/_import_probe.py "Test/successTerzo/success/budget_131_Oprandi Fabrizio - 30.04.2026 (provvisoria).pdf" ocr
python tests/_import_probe.py "Test/successTerzo/success/budget_132_Oprandi Fabrizio - 30.04.2026.pdf" ocr
python tests/_import_probe.py "Test/errori/budget_158_BILANCIO CONA.pdf" ocr
```
Expected: `ok=true` (ora l'OCR usa il testo nativo e passa per la route C standard, come l'import standard
che già riesce su questi file). `stored.total_assets` uguale al metodo standard.

- [ ] **Step 5: Commit**

```bash
git add importers/pdf_importer.py tests/test_ocr_text_source.py
git commit -m "fix(ocr): MinerU non soppianta piu' il testo nativo valido — /import/pdf-ocr delega al percorso standard sui PDF a testo nativo"
```

---

### Task 2: MinerU come candidato route-C aggiuntivo (ricongiunzione)

**Files:**
- Modify: `importers/pdf_importer.py` (blocco route C, costruzione `candidates`)
- Test: copertura via probe (integrazione)

**Contesto.** Quando il testo nativo è primario (Task 1) ma il file è route C, le tabelle MinerU possono
comunque aiutare (es. una scansione parziale con testo misto). Aggiungere un candidato route-C costruito
dalle tabelle MinerU, che compete nella STESSA selezione-per-completezza degli altri candidati (CoGe-LLM,
deterministico). È la "ricongiunzione dopo l'import" richiesta: un'unica selezione, tre provider.

**Interfaces:**
- Consumes: `extraction_context.tables`; `check_quadratura` (per il residuo); la selezione candidati
  esistente (Piano 02 Task 2).

- [ ] **Step 1** (deciso a valle dei piani 02–05): verificare se, dopo il Task 1, i file OCR route-C
già importano correttamente per delega al nativo. **Se sì**, questo Task è YAGNI su questo corpus →
documentarlo e chiuderlo senza codice (non aggiungere un candidato che non serve). **Se no** (esiste una
scansione route-C in cui né il testo MinerU come primario né il nativo bastano, ma le TABELLE MinerU sì),
allora implementare il candidato:

```python
# dentro il blocco route C, accanto agli altri candidati:
if extraction_context is not None and getattr(extraction_context, "tables", None):
    try:
        from importers.mineru_adapter import build_trial_candidate_from_tables
        mineru_bs, mineru_ce = build_trial_candidate_from_tables(extraction_context)
        r = _residual_of(mineru_bs, mineru_ce)
        if r is not None:
            candidates.append((r, mineru_bs, mineru_ce, "MinerU-tables"))
    except Exception as exc:
        logger.warning(f"Route C: candidato MinerU-tables saltato: {exc}")
```

(`build_trial_candidate_from_tables` andrebbe aggiunto a `importers/mineru_adapter.py` — mappa le righe
tabellari MinerU a sp/ce riusando `resolve` del Piano 05; specificarne il test se e solo se il ramo serve.)

- [ ] **Step 2: verificare** con la probe OCR sui file route-C scansionati che restano problematici dopo il
Task 1. Se non ce ne sono, chiudere il Task con nota "non necessario sul corpus 2026-07-23".

- [ ] **Step 3: Commit** (solo se implementato)

```bash
git add importers/pdf_importer.py importers/mineru_adapter.py
git commit -m "feat(ocr): candidato route-C dalle tabelle MinerU nella selezione unificata (ricongiunzione provider)"
```

---

### Task 3: scansioni vere — consentire il candidato vision anche via OCR

**Files:**
- Modify: `importers/pdf_importer.py` (guardia `is_scanned` quando `_ocr_source` e MinerU è inaffidabile)
- Test: probe su Bilancino (integrazione)

**Contesto.** Bilancino è una **vera scansione**: l'import standard riesce tramite il candidato vision
(`_extract_with_llm_vision`), che scatta quando `is_scanned=True`. Via OCR, oggi `_ocr_source=True` forza
`is_scanned=False` → il candidato vision è saltato → se il testo MinerU è inaffidabile, l'import fallisce
mentre lo standard riesce. Fix: quando la fonte è MinerU (`_use_mineru`) MA il risultato route-C non
quadra, consentire il fallback al candidato vision come nel percorso standard.

- [ ] **Step 1: individuare** nel blocco route C il punto in cui, con `api_key and not local_coordinate_ocr`,
si aggiunge il candidato CoGe-LLM. Verificare se il candidato vision (`_extract_with_llm_vision`) è
raggiungibile quando `_ocr_source=True`. Documentare il flusso reale prima di modificarlo.

- [ ] **Step 2: implementare** la guardia minima: se `_ocr_source` e nessun candidato route-C passa i gates
(dopo il retry del Piano 02), e il PDF è fisicamente una scansione (nessun testo nativo selezionabile),
tentare il candidato vision sulle immagini di pagina (lo stesso usato dal percorso standard scanned),
aggiungendolo ai `candidates`. Riusare `_extract_with_llm_vision` — non duplicarlo.

- [ ] **Step 3: verificare**

```bash
python tests/_import_probe.py "Test/sez-contrapposte/Bilancino 31-5-26.pdf" ocr
```
Expected: `ok=true`, stessi numeri del metodo standard (total_assets NET 1.913.698,44, sp13 17.872,66).

- [ ] **Step 4: Commit**

```bash
git add importers/pdf_importer.py
git commit -m "fix(ocr): scansioni vere via /import/pdf-ocr usano il candidato vision come lo standard (Bilancino)"
```

---

## Accettazione del piano

- 131, 132, 158 via OCR: `ok=true`, numeri identici al metodo standard.
- Bilancino via OCR: `ok=true`, numeri identici al metodo standard.
- 594, 597, 599, 636, 638 via OCR (route A/B a testo nativo): invariati/ok (delega al nativo, nessuna
  regressione da sostituzione MinerU).
- Nessun file che oggi importa via OCR regredisce (probe `ocr` sul campione pulito §6, metodo `ocr`).

## Nota di chiusura (richiesta utente)
Con questo piano i due percorsi convergono davvero: `/import/pdf` e `/import/pdf-ocr` condividono
classificatore, estrattori, selezione candidati e gates; MinerU è un provider di testo/tabelle che
interviene SOLO quando serve (scansioni / nativo corrotto) e altrimenti si fa da parte. È la
"ricongiunzione dopo l'import" descritta dall'utente.
