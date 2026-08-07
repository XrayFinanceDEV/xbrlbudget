# Import sbilanciato + chiusura dello sbilancio in Rettifiche — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un bilancio PDF che non quadra viene importato con un avviso e corretto in Rettifiche, invece di essere rifiutato del tutto.

**Architecture:** Nel gate di `importers/pdf_importer.py` restano errori duri solo le condizioni per cui non c'è nulla da rettificare (estrazione vuota, formato non IV-CEE, OCR inaffidabile); lo sbilancio diventa un warning con `validation_status="unbalanced"` e `forecastable=False`. Lo stesso vale per l'anno di raffronto, oggi scartato in silenzio. Lato frontend il banner quadratura di Rettifiche guadagna un bottone che pre-compila la modalità "Correggi Import" **già esistente** con l'importo esatto dello scarto.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / pytest (backend, venv in `backend/venv`); Next.js 15 / React 19 / TypeScript / shadcn-ui (frontend).

## Global Constraints

- Spec di riferimento: `docs/superpowers/specs/2026-08-07-import-sbilanciato-design.md`.
- Tutti i valori monetari sono `Decimal`, mai `float` (`CLAUDE.md` → Financial Calculations).
- Testi UI in italiano. Niente emoji: usare icone `lucide-react`.
- Solo componenti shadcn/ui, niente HTML grezzo per tabelle/bottoni.
- Il principio del progetto è **diagnose, never fabricate**: nessun valore contabile va inventato o "pluggato" in silenzio. Uno scarto si misura e si mostra.
- `forecastable` resta il gate della PROIEZIONE, mai del SALVATAGGIO.
- Commit direttamente su `main` (nessun feature branch) — vedi memoria `commit-directly-to-main`.
- Backend: attivare sempre il venv prima di eseguire test — `source backend/venv/bin/activate` dalla root del progetto.

## File Structure

| File | Responsabilità | Azione |
|---|---|---|
| `importers/pdf_importer.py` | classificazione fallimento import (duro vs avviso), stato di validazione, anno precedente | Modifica |
| `backend/app/api/v1/financial_years.py` | `validation_status` a tre vie dopo una rettifica | Modifica |
| `frontend/app/infrannuale/page.tsx` | bottone "Chiudi sbilancio" nel banner quadratura; toast su import sbilanciato | Modifica |
| `frontend/lib/api.ts` | dichiara `validation_status` su `PDFImportResult` | Modifica |
| `frontend/components/import/ImportPanel.tsx` | toast su import sbilanciato (la UI reale dietro `/import`) | Modifica |
| `tests/test_unbalanced_import.py` | test del nuovo comportamento del gate | Crea |

---

### Task 1: Il gate `validate_balance` classifica il fallimento invece di rifiutare sempre

**Files:**
- Modify: `importers/pdf_importer.py:1030-1107`
- Test: `tests/test_unbalanced_import.py` (crea)

**Interfaces:**
- Produces: `_UNBALANCED_WARNING_PREFIX: str = "BILANCIO SBILANCIATO"` (costante a livello di modulo, usata anche dai Task 2 e 3) e la variabile locale `unbalanced_reason: Optional[str]` dentro `import_pdf_balance_sheet`, che il Task 2 legge per calcolare `validation_status`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `tests/test_unbalanced_import.py`. Il test non usa PDF reali: chiama direttamente il classificatore estratto dal gate, così è veloce e deterministico (l'estrazione LLM non lo è).

```python
"""Il gate di import distingue cio' che si puo' rettificare da cio' che non si puo'.

Uno sbilancio e' correggibile in Rettifiche, quindi si importa con un avviso.
Un'estrazione vuota o un documento che non e' uno schema IV-CEE non lo sono,
quindi restano errori duri: non c'e' nulla su cui l'utente possa intervenire.
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from importers.pdf_importer import (
    _UNBALANCED_WARNING_PREFIX,
    _classify_balance_failure,
)


def _sheet(**overrides):
    """Uno stato patrimoniale minimo che quadra, salvo gli override."""
    data = {
        "totale_attivo": Decimal("1000"),
        "totale_passivo": Decimal("1000"),
        "sp09_disponibilita_liquide": Decimal("1000"),
        "sp16_debiti_breve": Decimal("1000"),
    }
    data.update(overrides)
    return data


def test_estrazione_vuota_resta_errore_duro():
    verdict = _classify_balance_failure(
        _sheet(totale_attivo=Decimal("0"), totale_passivo=Decimal("0"),
               sp09_disponibilita_liquide=Decimal("0"),
               sp16_debiti_breve=Decimal("0")),
        is_scanned=False, ocr_source=False,
        is_trial_balance=False, sample_text="B) II 1) Terreni 100",
        file_path="x.pdf", ocr_text=None,
    )
    assert verdict.hard_error is not None
    assert "nessun dato" in verdict.hard_error.lower()


def test_ocr_resta_errore_duro():
    verdict = _classify_balance_failure(
        _sheet(totale_passivo=Decimal("960")),
        is_scanned=True, ocr_source=False,
        is_trial_balance=False, sample_text="B) II 1) Terreni 100",
        file_path="x.pdf", ocr_text=None,
    )
    assert verdict.hard_error is not None
    assert "OCR" in verdict.hard_error


def test_sbilancio_e_importabile_con_avviso():
    verdict = _classify_balance_failure(
        _sheet(totale_passivo=Decimal("960")),
        is_scanned=False, ocr_source=False,
        is_trial_balance=False, sample_text="B) II 1) Terreni 100",
        file_path="x.pdf", ocr_text=None,
    )
    assert verdict.hard_error is None
    assert verdict.warning.startswith(_UNBALANCED_WARNING_PREFIX)
    assert "Rettifiche" in verdict.warning
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -m pytest tests/test_unbalanced_import.py -v
```

Atteso: FAIL in raccolta — `ImportError: cannot import name '_classify_balance_failure'`.

- [ ] **Step 3: Estrarre il classificatore**

In `importers/pdf_importer.py`, subito dopo `class PDFImportError` (riga 53), aggiungere:

```python
_UNBALANCED_WARNING_PREFIX = "BILANCIO SBILANCIATO"
_UNBALANCED_WARNING_SUFFIX = (
    "Il bilancio è stato importato così com'è: correggilo in Rettifiche "
    "prima di calcolare la proiezione."
)


class BalanceFailureVerdict(NamedTuple):
    """Esito della diagnosi su un bilancio che non supera ``validate_balance``.

    Esattamente uno dei due campi e' valorizzato. ``hard_error`` significa che
    non c'e' nulla che l'utente possa correggere in Rettifiche (estrazione
    vuota, documento che non e' uno schema IV-CEE, totali letti dall'OCR e
    quindi inaffidabili di per se'). ``warning`` significa che il bilancio e'
    leggibile ma non quadra: si importa e si corregge a mano.
    """
    hard_error: Optional[str]
    warning: Optional[str]


def _it_amount(value: Decimal) -> str:
    """Formattazione italiana: 1.234.567,89."""
    return f"{value:,.2f}".replace(',', '#').replace('.', ',').replace('#', '.')


def _classify_balance_failure(
    balance_sheet_data: Dict[str, Decimal],
    *,
    is_scanned: bool,
    ocr_source: bool,
    is_trial_balance: bool,
    sample_text: str,
    file_path: str,
    ocr_text: Optional[str],
) -> BalanceFailureVerdict:
    """Decide se un fallimento di ``validate_balance`` blocca o solo avvisa.

    L'ordine conta: le diagnosi irrecuperabili girano per prime, cosi' un
    documento che non e' importabile non viene salvato come "sbilanciato".
    """
    # 1. Testo OCR: i totali stessi possono essere letti male, quindi non si puo'
    #    dichiarare sbilanciato il documento sorgente.
    if is_scanned or ocr_source:
        return BalanceFailureVerdict(
            "Il documento è una scansione contabile, ma l'OCR non ha "
            "ricostruito in modo affidabile colonne, gerarchie e totali. "
            "Il file sorgente non viene dichiarato sbilanciato: serve una "
            "lettura OCR strutturata oppure un PDF con testo selezionabile.",
            None,
        )

    # 2. Estrazione vuota: non c'e' niente da rettificare.
    if balance_sheet_data.get('totale_attivo', Decimal('0')) == Decimal('0'):
        return BalanceFailureVerdict(
            "Nessun dato estratto dal documento: lo Stato Patrimoniale "
            "risulta vuoto (Totale Attivo pari a zero). Verificare che il "
            "file contenga un prospetto leggibile.",
            None,
        )

    # 3. Riepilogo aggregato: manca lo schema IV-CEE, non la quadratura.
    if not is_trial_balance and _is_aggregated_summary(sample_text):
        contradiction = _summary_internal_contradiction(sample_text)
        if contradiction:
            return BalanceFailureVerdict(contradiction, None)
        return BalanceFailureVerdict(
            "Formato non supportato: il documento è un riepilogo aggregato per "
            "macro-voci, non uno schema di bilancio IV-CEE (art. 2424/2425) "
            "importabile. Carica il prospetto di Stato Patrimoniale e Conto "
            "Economico completo.",
            None,
        )

    # 4. Tutto il resto e' uno sbilancio correggibile. Il messaggio d'errore
    #    che prima bloccava e' la migliore diagnosi disponibile: diventa il
    #    testo dell'avviso, cosi' l'utente sa cosa cercare in Rettifiche.
    try:
        from importers.pdf_extractor_llm import _declared_control_totals
        controls = _declared_control_totals(file_path, text=ocr_text)
        source_attivo = controls.get('attivo')
        source_passivo = controls.get('passivo')
    except Exception:
        source_attivo = source_passivo = None

    if source_attivo is not None and source_passivo is not None:
        difference = abs(source_attivo - source_passivo)
        if difference > Decimal('2'):
            detail = (
                "il bilancio sorgente non quadra già nel documento: Totale "
                f"Attivo €{_it_amount(source_attivo)} != Totale Passivo "
                f"€{_it_amount(source_passivo)} (scarto €{_it_amount(difference)})"
            )
        else:
            detail = (
                "i totali Attivo e Passivo stampati coincidono, ma le "
                "componenti patrimoniali estratte non li ricostruiscono"
            )
    else:
        detail = (
            "il bilancio non quadra oppure il documento non contiene "
            "dettaglio sufficiente per ricostruire Attivo, Passivo e "
            "Patrimonio netto"
        )

    return BalanceFailureVerdict(
        None,
        f"{_UNBALANCED_WARNING_PREFIX}: {detail}. {_UNBALANCED_WARNING_SUFFIX}",
    )
```

Modificare la riga 12 del file da:

```python
from typing import Dict, Any, Optional
```

a:

```python
from typing import Dict, Any, NamedTuple, Optional
```

- [ ] **Step 4: Eseguire il test e verificare che passi**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -m pytest tests/test_unbalanced_import.py -v
```

Atteso: 3 passed.

- [ ] **Step 5: Sostituire il vecchio blocco con il classificatore**

In `import_pdf_balance_sheet`, sostituire **integralmente** il blocco `if not mapper.validate_balance(balance_sheet_data):` (righe 1032-1107, cioè fino alla `raise PDFImportError("Il bilancio non quadra oppure ...")` compresa) con:

```python
        # Step 2: Validate balance sheet (both paths)
        logger.info("Validating balance sheet...")
        unbalanced_reason: Optional[str] = None
        if not mapper.validate_balance(balance_sheet_data):
            _verdict = _classify_balance_failure(
                balance_sheet_data,
                is_scanned=is_scanned,
                ocr_source=bool(_ocr_source),
                is_trial_balance=is_trial_balance,
                sample_text=sample_text,
                file_path=file_path,
                ocr_text=ocr_text,
            )
            if _verdict.hard_error:
                raise PDFImportError(_verdict.hard_error)
            # Sbilancio: si importa e si corregge in Rettifiche. forecastable
            # restera' False da solo (semantic_valid include la quadratura),
            # e _validate_forecast_source blocca comunque la proiezione.
            unbalanced_reason = _verdict.warning
            logger.warning(unbalanced_reason)
```

- [ ] **Step 6: Verificare che il file compili e che i test esistenti non si rompano**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -c "import importers.pdf_importer"
python -m pytest tests/test_unbalanced_import.py tests/test_intra_year_semantics.py tests/test_reliability.py -q
```

Atteso: nessun errore di import; tutti i test passati.

- [ ] **Step 7: Commit**

```bash
cd /home/peter/DEV/budget
git add importers/pdf_importer.py tests/test_unbalanced_import.py
git commit -m "$(cat <<'EOF'
feat(import): uno sbilancio non blocca piu' il salvataggio del bilancio

validate_balance rifiutava l'intero import per qualunque scarto oltre 1,00 EUR.
Su rotta B l'estrazione e' LLM e quindi non deterministica: budget_664 falliva
in modo intermittente (scarti di 40 / 224,98 / 727 / 107.000 EUR tra i retry)
pur essendo leggibile e correggibile.

_classify_balance_failure separa cio' che l'utente puo' correggere in Rettifiche
da cio' che non puo': estrazione vuota, riepilogo aggregato e testo OCR restano
errori duri; lo sbilancio diventa un avviso e il bilancio si importa.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `check_quadratura` avvisa invece di bloccare, e `validation_status` distingue lo sbilancio

**Files:**
- Modify: `importers/pdf_importer.py:1135-1150` (blocco `if not _qd.quadra`)
- Modify: `importers/pdf_importer.py:1275-1284` (costruzione `FinancialYear`)
- Modify: `backend/app/api/v1/financial_years.py:506-514`
- Test: `tests/test_unbalanced_import.py`

**Interfaces:**
- Consumes: `_UNBALANCED_WARNING_PREFIX`, `_UNBALANCED_WARNING_SUFFIX`, `unbalanced_reason` dal Task 1.
- Produces: `_resolve_validation_status(arithmetic_balanced: bool, forecastable: bool) -> str`, che ritorna `"unbalanced" | "verified" | "review_required"`. Il Task 3 la riusa per l'anno precedente.

- [ ] **Step 1: Scrivere il test che fallisce**

Aggiungere in coda a `tests/test_unbalanced_import.py`:

```python
from importers.pdf_importer import _resolve_validation_status


def test_status_unbalanced_ha_precedenza_su_review_required():
    assert _resolve_validation_status(False, False) == "unbalanced"


def test_status_unbalanced_anche_se_forecastable_fosse_vero():
    # Difensivo: un bilancio che non quadra non e' mai "verified".
    assert _resolve_validation_status(False, True) == "unbalanced"


def test_status_verified_solo_se_quadra_ed_e_forecastable():
    assert _resolve_validation_status(True, True) == "verified"


def test_status_review_required_se_quadra_ma_non_forecastable():
    assert _resolve_validation_status(True, False) == "review_required"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -m pytest tests/test_unbalanced_import.py -v
```

Atteso: FAIL — `ImportError: cannot import name '_resolve_validation_status'`.

- [ ] **Step 3: Implementare `_resolve_validation_status`**

In `importers/pdf_importer.py`, subito dopo `_classify_balance_failure`:

```python
def _resolve_validation_status(arithmetic_balanced: bool, forecastable: bool) -> str:
    """Stato di validazione a tre vie.

    ``unbalanced`` ha la precedenza: un bilancio che non quadra non e' mai
    "verified", e la UI deve poterlo distinguere da un bilancio che quadra ma
    ha dettagli da rivedere, senza fare string-matching sui warning.
    """
    if not arithmetic_balanced:
        return "unbalanced"
    return "verified" if forecastable else "review_required"
```

- [ ] **Step 4: Eseguire il test e verificare che passi**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -m pytest tests/test_unbalanced_import.py -v
```

Atteso: 7 passed.

- [ ] **Step 5: Rendere non bloccante `check_quadratura` tranne che per l'estrazione vuota**

Sostituire il blocco `if not _qd.quadra:` (righe 1135-1150) con:

```python
            if not _qd.quadra:
                _blocking_warnings = [
                    warning for warning in _qd.warnings
                    if not warning.startswith("GERARCHIA INCOERENTE:")
                ]
                reason = "; ".join(_blocking_warnings) or (
                    f"attivo {_qd.totale_attivo} / passivo {_qd.totale_passivo}"
                )
                if _qd.is_empty:
                    # Un'estrazione vuota non e' rettificabile: non c'e' alcuna
                    # voce su cui l'utente possa intervenire.
                    raise PDFImportError(
                        "Importazione non salvata: nessun dato contabile "
                        f"estratto dal documento ({reason})"
                    )
                # Sbilancio, mismatch CE/SP o plug mascherato: importabile e
                # correggibile in Rettifiche. Allinea finalmente il codice a
                # quanto CLAUDE.md gia' afferma per la rotta C ("Trial-balance
                # import is never hard-blocked"), che oggi non e' vero perche'
                # ``quadra`` richiede ``not masked``.
                if unbalanced_reason is None:
                    unbalanced_reason = (
                        f"{_UNBALANCED_WARNING_PREFIX}: {reason}. "
                        f"{_UNBALANCED_WARNING_SUFFIX}"
                    )
                logger.warning(unbalanced_reason)
```

- [ ] **Step 6: Portare l'avviso nei warning e nello stato**

Subito dopo `warnings.extend(sc_quadratura_warnings)` (riga ~1167), inserire l'avviso **in testa** all'elenco perché sia il primo che l'utente legge:

```python
        if unbalanced_reason:
            warnings.insert(0, unbalanced_reason)
```

Poi, nella costruzione di `FinancialYear` (righe 1275-1284), sostituire la riga `validation_status=` con:

```python
            validation_status=_resolve_validation_status(
                bool(_validation_payload["arithmetic_balanced"]), _forecastable
            ),
```

- [ ] **Step 7: Allineare `PUT /adjustments`**

In `backend/app/api/v1/financial_years.py`, sostituire la riga 511
(`fy.validation_status = "verified" if _forecastable else "review_required"`) con:

```python
    # Stato a tre vie identico a quello dell'import: senza questo, la PRIMA
    # rettifica salvata degraderebbe "unbalanced" a "review_required" pur
    # restando il bilancio sbilanciato, perdendo il segnale per la UI.
    from importers.pdf_importer import _resolve_validation_status
    fy.validation_status = _resolve_validation_status(
        abs(new_q.sbilancio) <= Decimal("0.01"), _forecastable
    )
```

- [ ] **Step 8: Verificare**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -c "import importers.pdf_importer, backend.app.api.v1.financial_years"
python -m pytest tests/test_unbalanced_import.py tests/test_intra_year_semantics.py -q
```

Atteso: nessun errore di import; tutti i test passati.

- [ ] **Step 9: Verifica end-to-end sul file che ha originato il problema**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python tests/_import_probe.py "docs/examples/budget_664_31-05-26 facchinetti.pdf"
```

Atteso: riga finale `OK [B] budget_664...`. (L'estrazione e' LLM: se il run e' fortunato il bilancio quadra e non compare alcun avviso di sbilancio — va bene lo stesso, il punto e' che non fallisce mai.)

- [ ] **Step 10: Commit**

```bash
cd /home/peter/DEV/budget
git add importers/pdf_importer.py backend/app/api/v1/financial_years.py tests/test_unbalanced_import.py
git commit -m "$(cat <<'EOF'
feat(import): validation_status "unbalanced" e quadratura non bloccante

check_quadratura rifiutava l'import per sbilancio, mismatch CE/SP o plug
mascherato. Ora blocca solo l'estrazione vuota: il resto e' correggibile in
Rettifiche. Questo allinea il codice a cio' che CLAUDE.md gia' afferma per la
rotta C ("Trial-balance import is never hard-blocked").

_resolve_validation_status introduce il terzo stato "unbalanced" cosi' la UI
distingue "dettagli da rivedere" da "non quadra" senza string-matching sui
warning. Replicato in PUT /adjustments, altrimenti la prima rettifica salvata
degradava lo stato pur restando il bilancio sbilanciato.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: L'anno di raffronto sbilanciato viene importato invece che scartato

**Files:**
- Modify: `importers/pdf_importer.py:1332-1345` e `1375-1386`
- Test: `tests/test_unbalanced_import.py`

**Interfaces:**
- Consumes: `_resolve_validation_status` dal Task 2.
- Produces: `_should_import_prior(fresh_balances: bool, is_empty: bool, has_existing: bool) -> bool`.

Contesto: `fresh_prior_balances = mapper.validate_balance(prior_bs_data) and _prior_q.quadra` (riga 1325) scarta l'anno precedente ogni volta che non quadra. È il motivo per cui `POST /import/pdf` su `budget_664` risponde `prior_year_imported: false` con uno scarto di soli 40,00 € sul 2025, e per cui il wizard infrannuale pretende poi un caricamento separato dello storico.

- [ ] **Step 1: Scrivere il test che fallisce**

Aggiungere in coda a `tests/test_unbalanced_import.py`:

```python
from importers.pdf_importer import _should_import_prior


def test_prior_che_quadra_si_importa_sempre():
    assert _should_import_prior(True, False, has_existing=False) is True
    assert _should_import_prior(True, False, has_existing=True) is True


def test_prior_sbilanciato_si_importa_se_non_ce_n_e_gia_uno():
    # Meglio uno storico sbilanciato da correggere che nessuno storico:
    # senza anno di raffronto il wizard infrannuale non parte affatto.
    assert _should_import_prior(False, False, has_existing=False) is True


def test_prior_sbilanciato_non_sovrascrive_un_record_esistente():
    assert _should_import_prior(False, False, has_existing=True) is False


def test_prior_vuoto_non_si_importa_mai():
    assert _should_import_prior(False, True, has_existing=False) is False
    assert _should_import_prior(False, True, has_existing=True) is False
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -m pytest tests/test_unbalanced_import.py -v
```

Atteso: FAIL — `ImportError: cannot import name '_should_import_prior'`.

- [ ] **Step 3: Implementare `_should_import_prior`**

In `importers/pdf_importer.py`, subito dopo `_resolve_validation_status`:

```python
def _should_import_prior(
    fresh_balances: bool, is_empty: bool, *, has_existing: bool
) -> bool:
    """Se salvare l'anno di raffronto appena estratto.

    Un anno vuoto non si importa mai: non c'e' nulla da rettificare. Un anno
    sbilanciato si importa SOLO se non ne esiste gia' uno: meglio uno storico
    da correggere che nessuno storico (senza anno di raffronto il wizard
    infrannuale non parte), ma mai al prezzo di degradare un record buono.
    """
    if is_empty:
        return False
    if fresh_balances:
        return True
    return not has_existing
```

- [ ] **Step 4: Eseguire il test e verificare che passi**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -m pytest tests/test_unbalanced_import.py -v
```

Atteso: 12 passed.

- [ ] **Step 5: Usare la funzione nel percorso dell'anno precedente**

Sostituire il blocco `if not fresh_prior_balances:` (righe 1332-1345) con:

```python
                _prior_ok = _should_import_prior(
                    fresh_prior_balances, _prior_q.is_empty,
                    has_existing=existing_prior is not None,
                )
                if not _prior_ok:
                    logger.info(
                        f"Prior year {prior_fiscal_year} extraction is not accounting-valid — "
                        f"{'keeping existing record' if existing_prior else 'not importing it'}"
                    )
                    prior_year_imported = existing_prior is not None
                    warnings.append(
                        f"ANNO PRECEDENTE NON IMPORTATO [{prior_fiscal_year}]: "
                        + "; ".join(_prior_q.warnings)
                    )
                else:
                    if not fresh_prior_balances:
                        warnings.append(
                            f"{_UNBALANCED_WARNING_PREFIX} [ANNO PRECEDENTE "
                            f"{prior_fiscal_year}]: " + "; ".join(_prior_q.warnings)
                            + f". {_UNBALANCED_WARNING_SUFFIX}"
                        )
```

Il ramo `else:` esistente (righe 1346 in poi, che inizia con il commento `# Import (or, on re-import, REPLACE) the prior year.`) va **fuso** in questo nuovo `else:`: rimuovere la riga `else:` originale e reindentare il suo corpo di un livello meno, in modo che segua le due righe di warning appena aggiunte.

Attenzione al ramo di sostituzione: `if existing_prior:` cancella il record esistente. Con la nuova regola quel ramo è raggiungibile **solo** quando `fresh_prior_balances` è vero (se fosse falso, `_should_import_prior` avrebbe restituito `False`), quindi il commento *"replacing a stale record with a freshly extracted one that BALANCES"* resta corretto. Lasciarlo invariato.

- [ ] **Step 6: Aggiornare lo stato dell'anno precedente**

Nella costruzione di `prior_fy` (righe 1375-1386), sostituire le righe `validation_status=` e `forecastable=` con:

```python
                        validation_status=_resolve_validation_status(
                            bool(_prior_validation["arithmetic_balanced"]),
                            _prior_q.semantic_valid,
                        ),
                        validation_report=json.dumps(_prior_validation, ensure_ascii=False),
                        source_sha256=_source_sha256,
                        parser_version=_stored_parser_version,
                        forecastable=_prior_q.semantic_valid,
```

- [ ] **Step 7: Verificare**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -c "import importers.pdf_importer"
python -m pytest tests/test_unbalanced_import.py -q
python tests/_import_probe.py "docs/examples/budget_664_31-05-26 facchinetti.pdf"
```

Atteso: 12 passed; probe `OK`.

- [ ] **Step 8: Commit**

```bash
cd /home/peter/DEV/budget
git add importers/pdf_importer.py tests/test_unbalanced_import.py
git commit -m "$(cat <<'EOF'
feat(import): l'anno di raffronto sbilanciato si importa invece di sparire

Un anno precedente che non quadrava veniva scartato in silenzio: budget_664
rispondeva prior_year_imported=false per uno scarto di 40 EUR sul 2025, e il
wizard infrannuale pretendeva poi un caricamento separato dello storico.

_should_import_prior lo salva quando non ne esiste gia' uno — meglio uno
storico da correggere in Rettifiche che nessuno storico — ma non sovrascrive
mai un record esistente con uno sbilanciato, e continua a scartare il vuoto.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Bottone "Chiudi sbilancio" nel banner quadratura di Rettifiche

**Files:**
- Modify: `frontend/app/infrannuale/page.tsx:1936-1952` (banner), più una funzione nuova accanto a `confirmActiveEdit`

**Interfaces:**
- Consumes: il tipo `DoubleEntryProposal`, lo stato `activeProposal` / `setActiveProposal`, e la modalità `correggi_import` — **tutti già esistenti** (`ProposalMode` alla riga 1485, `confirmActiveEdit` alle righe 1729-1755).
- Produces: nessuna interfaccia nuova per altri task.

Contesto essenziale: la registrazione a partita singola **esiste già**. `confirmActiveEdit` in modalità `correggi_import` applica un solo delta senza contropartita, usando il sentinella `counterpart_field: "_correzione_import"` con `counterpart_delta: 0`; il pannello journal la rende già in forma dedicata (riga 2288) e `deleteLogEntry` la inverte correttamente. Questo task **non** introduce un nuovo tipo di voce: aggiunge solo il punto d'ingresso che oggi manca, perché per chiudere uno scarto l'utente deve indovinare il percorso (scegliere una riga, digitarci un valore, aprire il dialog, accorgersi del terzo pulsante di modalità e calcolarsi da sé l'importo).

- [ ] **Step 1: Aggiungere la funzione che costruisce la proposta**

In `frontend/app/infrannuale/page.tsx`, subito **prima** di `const confirmActiveEdit = () => {` (riga 1725), inserire:

```tsx
  // Campi "altri" che reconcileSubfields usa gia' come bucket di plug: imputarci
  // lo scarto lascia coerenti gli aggregati padre dopo recalcAggregates.
  // `side` e' esplicito perche' decide il SEGNO del delta (vedi sotto): dedurlo
  // dal prefisso del codice funzionerebbe oggi ma si romperebbe al primo campo
  // aggiunto fuori schema.
  const SBILANCIO_TARGETS: { field: string; label: string; side: "attivo" | "passivo" }[] = [
    { field: "sp09_disponibilita_liquide", label: "IV) Disponibilità liquide", side: "attivo" },
    { field: "sp06g_crediti_altri_breve", label: "II) Crediti - altri (entro)", side: "attivo" },
    { field: "sp05e_acconti", label: "I) Rimanenze - acconti", side: "attivo" },
    { field: "sp16g_altri_debiti_breve", label: "D) Altri debiti (entro)", side: "passivo" },
    { field: "sp17g_altri_debiti_lungo", label: "D) Altri debiti (oltre)", side: "passivo" },
    { field: "sp12e_altre_riserve", label: "A) VI - Altre riserve", side: "passivo" },
  ];

  // Apre la modalita' "Correggi Import" (partita singola) pre-compilata con lo
  // scarto esatto. L'importo e' un dato, non una scelta: il dialog lo mostra
  // come testo, non come input.
  //
  // SEGNO. gap = attivo - passivo.
  //   gap > 0 (l'attivo eccede)  -> ridurre un campo dell'attivo di gap,
  //                                 oppure aumentare un campo del passivo di gap.
  //   gap < 0 (il passivo eccede) -> aumentare un campo dell'attivo di |gap|,
  //                                 oppure ridurre un campo del passivo di |gap|.
  // In entrambi i casi: delta = -gap su un campo dell'attivo, delta = +gap su un
  // campo del passivo.
  const openSbilancioCorrection = () => {
    const gap = Math.round((totalAttivo - totalPassivo) * 100) / 100;
    if (Math.abs(gap) < 0.01) return;
    // Default: l'attivo eccede -> si toglie dalla cassa; il passivo eccede ->
    // si tolgono altri debiti.
    const target = gap > 0 ? SBILANCIO_TARGETS[0] : SBILANCIO_TARGETS[3];
    const delta = target.side === "attivo" ? -gap : gap;
    setActiveProposal({
      id: Date.now(),
      mode: "correggi_import",
      editedField: target.field,
      editedLabel: target.label,
      delta,
      counterpartField: "",
      counterpartLabel: "",
      proposedDelta: 0,
      accepted: true,
      explanation:
        `Correzione di quadratura: scarto di importazione ${formatEuro(Math.abs(gap))} ` +
        `imputato a ${target.label}`,
    });
  };
```

`totalAttivo` e `totalPassivo` sono già calcolati alle righe 1836-1841, nello stesso scope. Il test dello Step 4 punto 3 verifica il segno: se dopo la conferma il banner passa da `40,00` a `80,00` invece che a `0,00`, il segno è invertito.

- [ ] **Step 2: Aggiungere il bottone al banner**

Sostituire il ramo `else` del banner (righe 1947-1951) con:

```tsx
            {isBalanced ? (
              <Check className="h-4 w-4 text-green-600 dark:text-green-400" />
            ) : (
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-xs font-medium">SBILANCIATO</span>
                <Button size="sm" variant="outline" onClick={openSbilancioCorrection}>
                  Chiudi sbilancio
                </Button>
              </div>
            )}
```

- [ ] **Step 3: Nessuna modifica al dialog**

Il dialog rende il delta come testo (righe 2425-2433), non come input, quindi l'importo è già non editabile; il testo di aiuto della modalità `correggi_import` (righe 2437-2439, *"Correzione singola per errore di importazione. Non richiede contropartita."*) resta corretto anche per questo punto d'ingresso, e il bottone di conferma è già abilitato senza contropartita (riga 2532). Questo step è una verifica di lettura: nessuna riga da cambiare.

- [ ] **Step 4: Verificare a mano nell'app**

Avviare backend e frontend, importare un bilancio sbilanciato, aprire `/infrannuale` → Rettifiche.

```bash
# Terminale 1
cd /home/peter/DEV/budget/backend && source venv/bin/activate
DEV_USER_ID=dev-user-001 uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# Terminale 2
cd /home/peter/DEV/budget/frontend && npm run dev
```

Verificare, nell'ordine:
1. il banner rosso mostra `SBILANCIATO` e il bottone **Chiudi sbilancio**;
2. il click apre il dialog in modalità **Correggi Import** con l'importo dello scarto;
3. **Applica correzione** porta il banner a verde con `Verifica quadratura` e la spunta;
4. la voce compare nel journal e il suo cestino riporta il banner a rosso con lo scarto identico a prima.

Il punto 3 è il test del segno dello Step 1: se il banner passa da `40,00` a `80,00` invece che a `0,00`, il segno è invertito.

- [ ] **Step 5: Controllo dei tipi**

```bash
cd /home/peter/DEV/budget/frontend && npx tsc --noEmit
```

Atteso: nessun errore nuovo in `app/infrannuale/page.tsx`.

- [ ] **Step 6: Commit**

```bash
cd /home/peter/DEV/budget
git add frontend/app/infrannuale/page.tsx
git commit -m "$(cat <<'EOF'
feat(rettifiche): bottone "Chiudi sbilancio" nel banner quadratura

La registrazione a partita singola esisteva gia' (modalita' "Correggi Import"),
ma per arrivarci l'utente doveva indovinare il percorso: scegliere una riga,
digitarci un valore, aprire il dialog, accorgersi del terzo pulsante di
modalita' e calcolarsi da se' l'importo dello scarto. Il banner che gli diceva
SBILANCIATO non offriva alcuna azione.

Ora il banner apre la proposta gia' compilata con lo scarto esatto e un campo
di imputazione di default. Nessun nuovo tipo di voce di journal.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Rendere visibile all'utente che il bilancio importato non quadra

**Files:**
- Modify: `frontend/lib/api.ts:327-349` (interfaccia `PDFImportResult`)
- Modify: `frontend/app/infrannuale/page.tsx:2992-3097` (`handleImport`)
- Modify: `frontend/components/import/ImportPanel.tsx:136-145`

**Interfaces:**
- Consumes: `PDFImportResult.warnings: string[]` (già presente) e `PDFImportResult.validation_status` (**da aggiungere allo Step 1** — l'API lo restituisce già ma il tipo TypeScript non lo dichiara).

Contesto e delimitazione dello scope:
- `handleImport` in `/infrannuale` ignora oggi `result.warnings` e `result.validation_status` e mostra un `toast.success` liscio (riga 2987). Dopo i Task 1-3 un bilancio può arrivare in DB sbilanciato: se l'utente non lo sa, prosegue verso Confronto e Proiezione e sbatte contro un rifiuto della proiezione senza capire perché.
- `components/import/ImportPanel.tsx` (la UI reale dietro `/import`; `app/import/page.tsx` è solo un wrapper) **rende già** `pdfResult.warnings` come elenco puntato alle righe 348-350. Il Task 2 Step 6 inserisce l'avviso in **posizione 0**, quindi lì comparirà per primo senza altro lavoro. Serve solo il toast, perché un elenco sotto la scheda è facile da non vedere.
- **Solo il percorso PDF.** Le modifiche di backend dei Task 1-3 sono in `pdf_importer.py`: l'import XBRL non produce `validation_status="unbalanced"` e non va toccato.

- [ ] **Step 1: Dichiarare il campo nel tipo**

In `frontend/lib/api.ts`, dentro `interface PDFImportResult`, aggiungere dopo la riga `warnings: string[];`:

```tsx
  // "verified" | "review_required" | "unbalanced" — l'API lo restituisce da sempre,
  // ma il tipo non lo dichiarava. "unbalanced" significa che il bilancio e' stato
  // importato pur non quadrando, e va corretto in Rettifiche.
  validation_status?: string;
```

- [ ] **Step 2: Catturare lo stato e mostrare il toast nell'infrannuale**

In `handleImport`, dichiarare la variabile accanto a `let companyId` / `let companyName` in cima alla funzione:

```tsx
      let unbalancedWarning: string | null = null;
```

Nel ramo PDF (righe 3029-3050), subito dopo `companyName = result.company_name;`:

```tsx
        if (result.validation_status === "unbalanced") {
          unbalancedWarning =
            (result.warnings ?? []).find((w) => w.startsWith("BILANCIO SBILANCIATO"))
            ?? "Il bilancio importato non quadra: correggilo in Rettifiche.";
        }
```

Poi mostrare il toast:

`createScenarioAndAdvance` emette `toast.success(...)` alla riga 2987. Per non contraddirlo, emettere l'avviso **dopo**, con durata più lunga perché è un'azione richiesta e non una notifica di passaggio. Inserire subito prima di `await createScenarioAndAdvance(companyId, companyName, ocrMetadata);` (riga 3079):

```tsx
      if (unbalancedWarning) {
        toast.warning(unbalancedWarning, { duration: 12000 });
      }
```

E anche nel ramo di uscita anticipata, subito prima del `return;` alla riga 3076 (dove manca l'anno di raffronto):

```tsx
        if (unbalancedWarning) {
          toast.warning(unbalancedWarning, { duration: 12000 });
        }
        return;
```

- [ ] **Step 3: Stesso toast in `ImportPanel`**

In `frontend/components/import/ImportPanel.tsx`, subito dopo `toast.success("Estrazione PDF completata!");` (riga 144):

```tsx
      if (result.validation_status === "unbalanced") {
        toast.warning(
          (result.warnings ?? []).find((w) => w.startsWith("BILANCIO SBILANCIATO"))
          ?? "Il bilancio importato non quadra: correggilo in Rettifiche.",
          { duration: 12000 }
        );
      }
```

L'elenco dei warning alle righe 348-350 continua a mostrare lo stesso avviso in prima posizione: il toast è il richiamo, l'elenco è il dettaglio consultabile.

- [ ] **Step 4: Controllo dei tipi**

```bash
cd /home/peter/DEV/budget/frontend && npx tsc --noEmit
```

Atteso: nessun errore nuovo.

- [ ] **Step 5: Verifica a mano**

Con backend e frontend avviati, importare un bilancio sbilanciato da `/infrannuale`. Atteso: dopo il toast verde di importazione compare un toast arancione con la ragione dello sbilancio e il rimando a Rettifiche. Ripetere da `/import`: stesso toast, più l'avviso in cima all'elenco dei warning.

- [ ] **Step 6: Commit**

```bash
cd /home/peter/DEV/budget
git add frontend/lib/api.ts frontend/app/infrannuale/page.tsx frontend/components/import/ImportPanel.tsx
git commit -m "$(cat <<'EOF'
feat(import): avvisa l'utente quando il bilancio importato non quadra

handleImport ignorava validation_status e warnings e mostrava un toast di
successo liscio. Con l'import sbilanciato ora possibile, senza avviso l'utente
prosegue verso Confronto e Proiezione e sbatte contro il rifiuto della
proiezione senza sapere perche'.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Aggiornare CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Correggere la sezione sul blocco degli import**

Nella sezione *"IV-CEE leveling + quadratura engine"*, il punto **"Trial-balance import is never hard-blocked"** descriveva un comportamento che il codice non aveva (`quadra` richiede `not masked`, quindi un file mascherato veniva rifiutato alla riga 1147). Ora è vero, e vale per tutte le rotte. Sostituire quel punto elenco con:

```markdown
- **Nessun bilancio leggibile viene hard-bloccato per quadratura** (`pdf_importer`): dopo
  `validate_balance` e `check_quadratura`, `_classify_balance_failure` distingue cio' che
  l'utente puo' correggere in **Rettifiche** da cio' che non puo'. Restano errori duri solo:
  estrazione vuota (`totale_attivo == 0` / `q.is_empty`), riepilogo aggregato senza schema
  IV-CEE ("Formato non supportato"), e testo OCR (i totali stessi possono essere misletti).
  Sbilancio Attivo/Passivo, mismatch CE/SP e plug mascherato diventano un warning con
  prefisso `BILANCIO SBILANCIATO:` e `validation_status="unbalanced"`.
  `_resolve_validation_status` e' la sola definizione dei tre stati ed e' usata sia
  dall'import sia da `PUT /adjustments`. **`forecastable` resta il gate della PROIEZIONE,
  mai del SALVATAGGIO** — `intra_year_engine._validate_forecast_source` blocca comunque su
  `abs(sbilancio) > 0.01`, quindi un bilancio sbilanciato si salva e si corregge ma non
  proietta. L'anno di raffronto segue `_should_import_prior`: si importa anche sbilanciato
  se non ne esiste gia' uno (senza storico il wizard infrannuale non parte), non sovrascrive
  mai un record esistente con uno sbilanciato, e il vuoto non si importa mai.
  Test: `tests/test_unbalanced_import.py`.
```

- [ ] **Step 2: Documentare il punto d'ingresso in Rettifiche**

Nella sezione *"Rettifiche (BS/IS Adjustments Journal)"*, aggiungere dopo il punto **Counterpart picker**:

```markdown
- **Chiusura dello sbilancio:** una rettifica in partita doppia NON puo' chiudere uno scarto
  Attivo≠Passivo — sposta i due lati della stessa quantita', per costruzione — e
  `reconcileSubfields` si ferma a 5 €. Per questo il dialog ha una terza modalita',
  **"Correggi Import"** (`ProposalMode`), che applica un solo delta senza contropartita,
  registrata nel journal con il sentinella `counterpart_field: "_correzione_import"` e
  `counterpart_delta: 0`. Il banner quadratura la offre direttamente col bottone **"Chiudi
  sbilancio"**, gia' compilato con lo scarto esatto e un campo di imputazione di default
  (`sp09` se l'attivo eccede, `sp16g` se eccede il passivo — entrambi bucket di plug di
  `reconcileSubfields`, cosi' gli aggregati padre restano coerenti dopo `recalcAggregates`).
```

- [ ] **Step 3: Commit**

```bash
cd /home/peter/DEV/budget
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: allinea CLAUDE.md all'import sbilanciato e alla chiusura in Rettifiche

Il punto "Trial-balance import is never hard-blocked" descriveva un
comportamento che il codice non aveva. Ora e' vero e vale per tutte le rotte.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Verifica finale

- [ ] **Suite completa**

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
python -m pytest tests/ -q -x --ignore=tests/debug
```

Atteso: nessun fallimento nuovo rispetto alla baseline pre-modifica. Registrare l'output.

- [ ] **Baseline di regressione degli import**

`tests/fixtures/import_baseline.json` contiene 19 entry, tutte in errore, e **11 registrano un bug del probe già corretto** (`AttributeError: 'str' object has no attribute 'close'`): la fixture è stale a prescindere da questa modifica. Delle rimanenti, **4 passano da errore a import-con-avviso** per effetto di questo lavoro: `budget_365`, `budget_342` (*"Documento non importabile automaticamente..."*) e `budget_405`, `budget_367` (*"Importazione non salvata: il bilancio estratto non supera i controlli contabili"*).

Il corpus `Test/` non è presente in locale e `tests/test_import_baseline.py` skippa i file assenti, quindi la suite non si romperà. Se il corpus è disponibile, rigenerare:

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
IMPORT_CORPUS_ROOT=<percorso-corpus> python scripts/refresh_import_baseline.py
```

Se il corpus **non** è disponibile, dirlo esplicitamente nel resoconto finale invece di dichiarare la baseline verificata.

- [ ] **Verifica end-to-end sul file d'origine, ripetuta**

L'estrazione di rotta B è LLM e non deterministica: un singolo run riuscito non dimostra nulla. Eseguire 5 volte e verificare che **nessuna** fallisca:

```bash
cd /home/peter/DEV/budget && source backend/venv/bin/activate
for i in 1 2 3 4 5; do
  python tests/_import_probe.py "docs/examples/budget_664_31-05-26 facchinetti.pdf" 2>/dev/null | grep -E "^(OK|FAIL)"
done
```

Atteso: 5 righe, tutte `OK`.

## Cosa questo lavoro NON risolve

Non rende deterministico l'import di `budget_664`. La causa vera resta la varianza di Claude Haiku sulla rotta B. Con queste modifiche il tentativo sfortunato non fallisce più, ma consegna all'utente un bilancio con un buco da chiudere a mano — 40 € nel caso benigno, 107.000 € nel caso peggiore osservato tra i retry. Ridurre la varianza a monte è un lavoro separato, da non confondere con questo.
