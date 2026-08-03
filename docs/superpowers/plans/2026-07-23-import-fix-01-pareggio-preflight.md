# Piano 01 — Verdetto sorgente pareggio-aware (declared totals)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** eliminare il falso "Il bilancio sorgente non quadra … Correggere il documento contabile
originale" quando lo scarto attivo−passivo è il risultato d'esercizio implicito di un trial balance.

**Architettura:** una nuova funzione pura `declared_source_verdict(dc, is_trial_balance, tol)` in
`importers/pdf_extractor_llm.py` incapsula l'identità di pareggio (§1.1 del quadro generale); il ramo
diagnostico di `pdf_importer.py` (righe ~1017-1079) la usa al posto del confronto nudo attivo vs passivo.
Si estendono i marker di `_declared_control_totals` con i sinonimi osservati nell'audit.

**Tech stack:** Python, pytest. Nessun LLM coinvolto (funzioni pure su testo).

## Vincoli globali
Ereditati dal quadro generale (file `…-00-quadro-generale.md` §7). In particolare: tolleranza 2 €,
Decimal, messaggi italiani, test committati solo con testo sintetico.

---

### Task 0: probe di produzione committata

**Files:**
- Create: `tests/_import_probe.py` (copia adattata della probe di sessione)

**Interfaces:**
- Produces: CLI `python tests/_import_probe.py <pdf> <standard|ocr> [fiscal_year]` → stampa un JSON con
  `ok`, `error`, `result.{extraction_method,warnings,validation_report}`, `stored[]`. Usata da TUTTI i
  piani come gate di regressione.

- [ ] **Step 1: creare il file** con questo contenuto (è la probe validata in audit, path-indipendente):

```python
"""Probe fedele alla produzione: import di UN pdf con UN metodo su DB in-memory.

Uso:  python tests/_import_probe.py <pdf_path> <standard|ocr> [fiscal_year]
Stampa un JSON; exit 0 sempre (l'esito sta in "ok"). Non tocca financial_analysis.db.
"""
import os, sys, json, asyncio, traceback, hashlib
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

ENV = os.path.join(ROOT, "backend", ".env")
if os.path.exists(ENV):
    for line in open(ENV, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _dec(x):
    try:
        return float(Decimal(str(x)))
    except Exception:
        return None


def _setup_memory_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from database.db import Base
    import database.models  # noqa
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    import importers.pdf_importer as pi
    pi.SessionLocal = TestSession
    return TestSession


def _summarize(result):
    keys = ["success", "extraction_method", "validation_status", "forecastable",
            "prior_year_imported", "macro_area", "macro_subcategory",
            "ocr_engine", "detail_level"]
    out = {k: result.get(k) for k in keys if k in result}
    out["warnings"] = result.get("warnings", [])
    vr = result.get("validation_report")
    if isinstance(vr, dict):
        out["validation_report"] = {k: vr.get(k) for k in
                                    ("semantic_valid", "sbilancio", "utile_ce",
                                     "sp13", "masked", "is_empty") if k in vr}
    return out


def _stored():
    import importers.pdf_importer as pi
    from database.models import FinancialYear
    db = pi.SessionLocal()
    out = []
    for fy in db.query(FinancialYear).order_by(FinancialYear.year).all():
        bs, ce = fy.balance_sheet, fy.income_statement
        out.append({
            "year": fy.year, "period_months": fy.period_months,
            "total_assets": _dec(bs.total_assets) if bs else None,
            "total_liabilities": _dec(bs.total_liabilities) if bs else None,
            "sp13": _dec(bs.sp13_utile_perdita) if bs else None,
            "bs": {c.name: _dec(getattr(bs, c.name)) for c in bs.__table__.columns
                   if c.name.startswith("sp") and getattr(bs, c.name)} if bs else {},
            "ce": {c.name: _dec(getattr(ce, c.name)) for c in ce.__table__.columns
                   if c.name.startswith("ce") and getattr(ce, c.name)} if ce else {},
        })
    db.close()
    return out


def main():
    path, method = sys.argv[1], sys.argv[2]
    fiscal_year = int(sys.argv[3]) if len(sys.argv) > 3 else 2024
    out = {"file": os.path.basename(path), "method": method, "ok": False}
    _setup_memory_db()
    try:
        from importers.pdf_importer import import_pdf_balance_sheet
        kwargs = dict(file_path=path, fiscal_year=fiscal_year, create_company=True,
                      sector=1,
                      company_name="PROBE_" + hashlib.sha1(path.encode()).hexdigest()[:8])
        if method == "ocr":
            from backend.app.services.mineru_client import MinerUClient
            from importers.mineru_adapter import build_extraction_context
            client = MinerUClient(base_url="http://127.0.0.1:8002",
                                  expected_version="3.2.0", language="latin",
                                  backend="pipeline", parse_method="ocr",
                                  timeout_seconds=600.0)
            content = open(path, "rb").read()

            async def _go():
                await client.health()
                return await client.parse_pdf(content=content,
                                              filename=os.path.basename(path))
            kwargs["extraction_context"] = build_extraction_context(asyncio.run(_go()))
        result = import_pdf_balance_sheet(**kwargs)
        out["ok"] = True
        out["result"] = _summarize(result)
        out["stored"] = _stored()
    except Exception as e:
        out["error_type"] = type(e).__name__
        out["error"] = str(e)[:2000]
        out["traceback"] = traceback.format_exc().splitlines()[-8:]
    print(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: verificare che giri** su un file pulito del corpus:

Run: `python tests/_import_probe.py "Test/successTerzo/success/budget_143_BILCC58E.pdf" standard`
Expected: JSON con `"ok": true` e `stored[0].total_assets` valorizzato.

- [ ] **Step 3: Commit**

```bash
git add tests/_import_probe.py
git commit -m "test: probe di produzione per import standard/ocr su DB in-memory"
```

---

### Task 1: `declared_source_verdict` (funzione pura + test)

**Files:**
- Modify: `importers/pdf_extractor_llm.py` (dopo `_declared_control_totals`, ~riga 3140)
- Test: `tests/test_declared_source_verdict.py` (nuovo)

**Interfaces:**
- Produces: `declared_source_verdict(dc: Dict[str, Optional[Decimal]], *, is_trial_balance: bool, tol: Decimal = Decimal('2')) -> str`
  con ritorno in `{"balanced", "unbalanced", "contradictory", "unknown"}`.
  Consumata dal Task 2 e dal Piano 02.

  > **RIVISTO 2026-07-27:** aggiunto il quarto esito **`contradictory`** — i controlli stampati esistono
  > ma non sono coerenti fra loro. Va trattato come `unknown` dal chiamante (**mai** come "documento da
  > correggere"): non è provato che sia il documento a sbagliare, può essere la nostra lettura dei marker.
  > Va però **loggato in modo distinto**, perché è il segnale che il Piano 05 spazio `marker` ha agganciato
  > il numero sbagliato — cioè esattamente il bug budget_337.
  > Aggiungere al Task un test per ogni combinazione: coerenti → `balanced`; pareggio che non combacia col
  > lato maggiore → `contradictory`; risultato che non spiega lo scarto → `contradictory`.

- [ ] **Step 1: scrivere il test che fallisce**

```python
# tests/test_declared_source_verdict.py
from decimal import Decimal as D
from importers.pdf_extractor_llm import declared_source_verdict


def dc(**kw):
    base = {"attivo": None, "passivo": None, "pareggio": None,
            "utile": None, "perdita": None}
    base.update({k: D(str(v)) for k, v in kw.items()})
    return base


# --- trial balance (risultato implicito) ---

def test_trial_scarto_uguale_utile_e_balanced():          # budget_229/238/610/243/246/395
    d = dc(attivo="1464996.42", passivo="1449982.45", utile="15013.97")
    assert declared_source_verdict(d, is_trial_balance=True) == "balanced"


def test_trial_perdita_su_lato_attivo_e_balanced():        # budget_623
    d = dc(attivo="2420397.40", passivo="2454987.65", perdita="34590.25",
           pareggio="2454987.65")
    assert declared_source_verdict(d, is_trial_balance=True) == "balanced"


def test_trial_pareggio_uguale_su_un_lato_e_balanced():    # AGO: pareggio == attivo
    d = dc(attivo="354443.14", passivo="338717.20", pareggio="354443.14",
           utile="15725.94")
    assert declared_source_verdict(d, is_trial_balance=True) == "balanced"


def test_trial_scarto_diverso_da_utile_e_unbalanced():     # sorgente rotta vera
    d = dc(attivo="1075486.51", passivo="1067475.73", utile="17428.62")
    assert declared_source_verdict(d, is_trial_balance=True) == "unbalanced"


def test_trial_senza_risultato_ne_pareggio_e_unknown_se_scarto_piccolo_ratio():
    # scarto 5% senza utile/perdita/pareggio: non possiamo provare nulla
    d = dc(attivo="1050000", passivo="1000000")
    assert declared_source_verdict(d, is_trial_balance=True) == "unknown"


# --- bilancio IV-CEE (passivo INCLUDE il risultato) ---

def test_ivcee_attivo_uguale_passivo_e_balanced():
    d = dc(attivo="1526020.43", passivo="1526020.43")
    assert declared_source_verdict(d, is_trial_balance=False) == "balanced"


def test_ivcee_scarto_e_unbalanced_anche_se_uguale_utile():
    # su un IV-CEE lo scarto NON è mai giustificato dall'utile (già dentro il PN)
    d = dc(attivo="4079635.72", passivo="4346574.29", utile="266938.57")
    assert declared_source_verdict(d, is_trial_balance=False) == "unbalanced"


def test_totali_mancanti_e_unknown():
    assert declared_source_verdict(dc(utile="100"), is_trial_balance=True) == "unknown"
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_declared_source_verdict.py -q`
Expected: `ImportError: cannot import name 'declared_source_verdict'`

- [ ] **Step 3: implementare** in `importers/pdf_extractor_llm.py`, subito dopo il corpo di
`_declared_control_totals` (l'helper geometrico incluso), a livello modulo:

```python
def declared_source_verdict(
    dc: Dict[str, Optional[Decimal]],
    *,
    is_trial_balance: bool,
    tol: Decimal = Decimal('2'),
) -> str:
    """Verdetto sui totali DICHIARATI dal documento: 'balanced' | 'unbalanced' | 'unknown'.

    Identità di pareggio (vedi piano 00 §1.1): su un bilancio IV-CEE il passivo stampato
    include il risultato, quindi vale il confronto diretto attivo==passivo. Su un TRIAL
    BALANCE il risultato è IMPLICITO: attivo − passivo == utile (o passivo − attivo ==
    perdita; o la perdita è già sommata al lato attivo e i due "totale a pareggio"
    coincidono). Dichiarare 'unbalanced' un trial balance il cui scarto è il risultato
    è il falso positivo che incolpa il documento del cliente (audit 2026-07-23).
    """
    att, pas = dc.get('attivo'), dc.get('passivo')
    utile, perdita = dc.get('utile'), dc.get('perdita')
    pareggio = dc.get('pareggio')
    if att is None or pas is None:
        # con un solo totale non si prova nulla; il pareggio da solo non basta
        return "unknown"
    diff = att - pas
    if abs(diff) <= tol:
        return "balanced"
    if not is_trial_balance:
        return "unbalanced"
    # --- trial balance: risultato implicito ---
    if utile is not None and abs(diff - utile) <= tol:
        return "balanced"                       # attivo = passivo + utile
    if perdita is not None and abs(-diff - perdita) <= tol:
        return "balanced"                       # passivo = attivo + perdita
    # ⚠️ RIVISTO 2026-07-27 — la versione precedente era TROPPO PERMISSIVA:
    #     if pareggio is not None and (|att-pareggio|<=tol or |pas-pareggio|<=tol): "balanced"
    # Bastava che UN lato coincidesse col pareggio stampato. Su un documento davvero
    # sbilanciato in cui un lato coincide per caso col pareggio, dichiarava "balanced" e
    # mascherava un difetto vero — l'errore opposto, e piu' pericoloso, di quello che il
    # piano vuole eliminare. Quando ci sono piu' controlli stampati devono essere COERENTI
    # FRA LORO, non basta che uno regga:
    #     utile:   att ~ pas + utile   e   pareggio ~ max(att, pas)
    #     perdita: pas ~ att + perdita e   pareggio ~ max(att, pas)
    if pareggio is not None:
        risultato = utile if utile is not None else (
            -perdita if perdita is not None else None)
        pareggio_ok = abs(max(att, pas) - pareggio) <= tol
        if risultato is None:
            # solo il pareggio: si accetta, ma solo se COMBACIA col lato maggiore
            return "balanced" if pareggio_ok else "contradictory"
        risultato_ok = abs((att - pas) - risultato) <= tol
        if pareggio_ok and risultato_ok:
            return "balanced"
        # i controlli stampati si contraddicono: NON e' un verdetto di quadratura.
        # Non e' nemmeno colpa dimostrata del documento (puo' essere la nostra lettura
        # dei marker): il chiamante deve trattarlo come "non decidibile", mai come
        # "sorgente da correggere".
        return "contradictory"
    if utile is None and perdita is None and pareggio is None:
        return "unknown"                        # niente per giudicare
    return "unbalanced"
```

- [ ] **Step 4: verificare che passi**

Run: `python -m pytest tests/test_declared_source_verdict.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add importers/pdf_extractor_llm.py tests/test_declared_source_verdict.py
git commit -m "feat(import): declared_source_verdict — identita' di pareggio sui totali dichiarati"
```

---

### Task 2: usare il verdetto nel ramo diagnostico di `pdf_importer`

**Files:**
- Modify: `importers/pdf_importer.py:1017-1079` (ramo `if not mapper.validate_balance(...)`)
- Test: `tests/test_source_verdict_messages.py` (nuovo)

**Interfaces:**
- Consumes: `declared_source_verdict` (Task 1); `_declared_control_totals` (esistente);
  `is_trial_balance` (variabile locale già presente nel flusso).
- Produces: nuova costante messaggio `MSG_EXTRACTION_INCOMPLETE` riusata dal Piano 02.

- [ ] **Step 1: test che fallisce** (si testa la logica estratta in una funzione, non l'intero import):
prima si rifattorizza la decisione in una funzione modulo-level testabile `_source_failure_error`.

```python
# tests/test_source_verdict_messages.py
from decimal import Decimal as D
from importers.pdf_importer import _source_failure_error


def test_trial_balance_quadrato_non_incolpa_la_sorgente():
    dc = {"attivo": D("1464996.42"), "passivo": D("1449982.45"),
          "utile": D("15013.97"), "perdita": None, "pareggio": D("1464996.42")}
    msg = _source_failure_error(dc, is_trial_balance=True, sample_text="")
    assert "Correggere il documento" not in msg
    assert "estra" in msg.lower()          # parla di estrazione, non di sorgente


def test_sorgente_realmente_sbilanciata_resta_denunciata():
    dc = {"attivo": D("1075486.51"), "passivo": D("1067475.73"),
          "utile": D("17428.62"), "perdita": None, "pareggio": None}
    msg = _source_failure_error(dc, is_trial_balance=True, sample_text="")
    assert "non quadra" in msg
    assert "8.010,78" in msg               # scarto reale, formattato IT


def test_totali_ignoti_messaggio_generico_onesto():
    dc = {"attivo": None, "passivo": None, "utile": None,
          "perdita": None, "pareggio": None}
    msg = _source_failure_error(dc, is_trial_balance=True, sample_text="")
    assert "Correggere il documento" not in msg
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_source_verdict_messages.py -q`
Expected: `ImportError: cannot import name '_source_failure_error'`

- [ ] **Step 3: implementare.** In `importers/pdf_importer.py` aggiungere a livello modulo (vicino a
`_is_aggregated_summary`):

```python
MSG_EXTRACTION_INCOMPLETE = (
    "Importazione non riuscita: il documento risulta CONTABILMENTE QUADRATO "
    "(pareggio dichiarato rispettato), ma l'estrazione automatica non e' riuscita a "
    "ricostruirne le voci IV-CEE. Il difetto e' del lettore, non del documento: "
    "riprovare l'import oppure segnalare il file all'assistenza."
)


def _it_amount(value: Decimal) -> str:
    return (f"{value:,.2f}".replace(',', '#').replace('.', ',').replace('#', '.'))


def _source_failure_error(dc, *, is_trial_balance: bool, sample_text: str) -> str:
    """Messaggio per il fallimento di validate_balance, basato sul VERDETTO dei
    totali dichiarati (identita' di pareggio) e mai su attivo-vs-passivo nudo."""
    from importers.pdf_extractor_llm import declared_source_verdict
    verdict = declared_source_verdict(dc, is_trial_balance=is_trial_balance)
    att, pas = dc.get('attivo'), dc.get('passivo')
    if verdict == "unbalanced" and att is not None and pas is not None:
        gap = abs(att - pas)
        utile = dc.get('utile') or dc.get('perdita')
        extra = ""
        if utile is not None:
            gap_vs_result = abs(gap - utile)
            extra = (f" Lo scarto NON coincide con il risultato dichiarato "
                     f"(€{_it_amount(utile)}): residuo €{_it_amount(gap_vs_result)}.")
        return (
            "Il bilancio sorgente non quadra prima dell'importazione: Totale Attivo "
            f"€{_it_amount(att)} != Totale Passivo €{_it_amount(pas)} "
            f"(scarto €{_it_amount(gap)}).{extra} "
            "Correggere il documento contabile originale."
        )
    if verdict == "balanced":
        return MSG_EXTRACTION_INCOMPLETE
    return (
        "Il bilancio non quadra oppure il documento non contiene dettaglio "
        "sufficiente per ricostruire Attivo, Passivo e Patrimonio netto. "
        "Verificare il file sorgente e caricare un prospetto completo."
    )
```

Poi nel ramo `if not mapper.validate_balance(balance_sheet_data):` sostituire il blocco
righe 1017-1079 (dal commento "Prefer an evidence-based source diagnosis…" fino al `raise` generico
di riga 1075-1079 INCLUSO, lasciando INTATTI il ramo `is_scanned or _ocr_source` e il ramo
`_is_aggregated_summary`) con:

```python
            try:
                from importers.pdf_extractor_llm import _declared_control_totals
                _dc_fail = _declared_control_totals(file_path, text=ocr_text)
            except Exception:
                _dc_fail = {}

            if not is_trial_balance and _is_aggregated_summary(sample_text):
                _contradiction = _summary_internal_contradiction(sample_text)
                if _contradiction:
                    raise PDFImportError(_contradiction)
                raise PDFImportError(
                    "Formato non supportato: il documento è un riepilogo aggregato per "
                    "macro-voci, non uno schema di bilancio IV-CEE (art. 2424/2425) "
                    "importabile. Carica il prospetto di Stato Patrimoniale e Conto "
                    "Economico completo."
                )

            raise PDFImportError(_source_failure_error(
                _dc_fail, is_trial_balance=is_trial_balance,
                sample_text=sample_text))
```

- [ ] **Step 4: verificare i test nuovi + regressione**

Run: `python -m pytest tests/test_source_verdict_messages.py tests/test_declared_source_verdict.py -q`
Expected: tutti PASS.

Run: `python tests/_import_probe.py "Test/errori/budget_229_MBS 2025.pdf" standard`
Expected: NIENTE "Correggere il documento contabile originale"; errore = `MSG_EXTRACTION_INCOMPLETE`
(finché il Piano 02/03 non sblocca l'estrazione) OPPURE import ok.

Run (invarianza sui rigetti giusti): `python tests/_import_probe.py "Test/errori/budget_152_BILAQ-001.pdf" standard`
Expected: ancora FAIL con denuncia dello sbilancio reale (scarto ≠ utile → 8.010,78).

- [ ] **Step 5: Commit**

```bash
git add importers/pdf_importer.py tests/test_source_verdict_messages.py
git commit -m "fix(import): il preflight sorgente applica l'identita' di pareggio — mai piu' falso 'correggere il documento' pari all'utile"
```

---

### ~~Task 3: sinonimi dei marker in `_declared_control_totals`~~ — ANNULLATO (2026-07-27)

> **NON ESEGUIRE.** Questo task è stato **assorbito dal Piano 05 Task 4**.
>
> Consisteva nell'aggiungere a mano altri 8 marker letterali (`"utile stato patrimoniale"`,
> `"utile esercizio"`, `"perdita conto economico"`, …) scelti enumerando i PDF dell'audit — i nomi dei suoi
> stessi test lo dichiarano (`# budget_229/238/243`, `# budget_703`, `# budget_176/182`). È esattamente la
> fragilità che il Quadro §1.4 dice di voler eliminare: al primo gestionale che stampa
> «Risultato del periodo» o «Utile netto d'esercizio» si torna al punto di partenza.
>
> Nel Piano 05 quelle grafie diventano lo **spazio `marker`** del dizionario semantico
> (`__tot_attivo`, `__tot_passivo`, `__pareggio`, `__utile`, `__perdita`, `__sez_sp_attivo`,
> `__col_scostamento`), con normalizzazione condivisa, cache e arbitro LLM: una grafia nuova si impara una
> volta e resta. Il Piano 05 T4 conserva lo scoping SP-vs-CE (che qui mancava per i marker nuovi: è il bug
> budget_337) e la regola sul testo garbled.
>
> **Attenzione a un effetto collaterale dei Task 1-2 non dichiarato nel piano originale:** riscrivere il
> blocco `pdf_importer.py:1017-1079` elimina il messaggio *"i totali Attivo e Passivo stampati coincidono,
> ma le componenti patrimoniali disponibili/estratte non li ricostruiscono"*, che oggi è quello che vedono
> budget_138/342/365/435. Sostituirlo con `MSG_EXTRACTION_INCOMPLETE` è corretto — ma va verificato che il
> nuovo testo resti altrettanto specifico, perché quel messaggio è **giusto**: dice la verità (la sorgente
> quadra, l'estrazione no).

<details>
<summary>Testo originale del Task 3 (archiviato, non eseguire)</summary>

### Task 3: sinonimi dei marker in `_declared_control_totals`

**Files:**
- Modify: `importers/pdf_extractor_llm.py:3105-3113` (liste marker utile/perdita) e `:3071-3079` (attivo/passivo)
- Test: `tests/test_declared_totals_markers.py` (nuovo)

**Interfaces:**
- Consumes/Produces: `_declared_control_totals(file_path, text=...)` (firma invariata).

- [ ] **Step 1: test che fallisce** (testo sintetico che replica i footer dell'audit):

```python
# tests/test_declared_totals_markers.py
from decimal import Decimal as D
from importers.pdf_extractor_llm import _declared_control_totals


def test_utile_stato_patrimoniale_e_sbilancio():          # budget_229/238/243 (Sistemi/DEPI)
    text = ("TOTALE ATTIVO 1.464.996,42\n"
            "TOTALE PASSIVO 1.449.982,45\n"
            "UTILE STATO PATRIMONIALE 15.013,97\n"
            "TOTALE A PAREGGIO 1.464.996,42\n"
            "SBILANCIO 0,00\n")
    dc = _declared_control_totals("/nonexistent.pdf", text=text)
    assert dc["attivo"] == D("1464996.42")
    assert dc["passivo"] == D("1449982.45")
    assert dc["utile"] == D("15013.97")
    assert dc["pareggio"] == D("1464996.42")


def test_utile_esercizio_senza_apostrofo():               # budget_703 "Utile Esercizio"
    text = "ATTIVITA' 2.303.519,78\nPASSIVITA' 2.248.113,53\nUtile Esercizio 55.406,25\n"
    dc = _declared_control_totals("/nonexistent.pdf", text=text)
    assert dc["utile"] == D("55406.25")


def test_stato_patrimoniale_attivo_stessa_riga():         # budget_176/182 (riclassificata)
    text = ("Stato patrimoniale attivo 1.116.259,44\n"
            "Stato patrimoniale passivo 1.116.259,44\n")
    dc = _declared_control_totals("/nonexistent.pdf", text=text)
    assert dc["attivo"] == D("1116259.44")
    assert dc["passivo"] == D("1116259.44")
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_declared_totals_markers.py -q`
Expected: FAIL sui casi 1 (utile None: "utile stato patrimoniale" non è nei marker), 2 e 3.

- [ ] **Step 3: implementare.** In `_declared_control_totals`:

(a) estendere i marker utile/perdita (righe 3105-3113):

```python
    out["utile"] = _largest_after([
        "utile d'esercizio", "utile dell'esercizio", "utile di esercizio",
        "utile del periodo", "utile in corso di formazione", "utile (perdita) dell'esercizio",
        "risultato d'esercizio", "risultato dell'esercizio",
        "utile stato patrimoniale", "utile conto economico",
        "utile esercizio", "utile dell esercizio",
    ])
    out["perdita"] = _largest_after([
        "perdita d'esercizio", "perdita dell'esercizio", "perdita di esercizio",
        "perdita del periodo", "perdita in corso di formazione",
        "perdita stato patrimoniale", "perdita conto economico",
        "perdita esercizio", "perdita dell esercizio",
    ])
```

(b) accettare la variante SAME-LINE di "stato patrimoniale attivo/passivo": dopo il blocco
`_section_heading_total` (righe 3101-3104) aggiungere:

```python
    def _section_heading_inline(side: str) -> Optional[Decimal]:
        """'Stato patrimoniale attivo 1.116.259,44' sulla STESSA riga (176/182)."""
        pattern = re.compile(
            rf"(?im)^\s*stato\s+patrimoniale\s+(?:-\s*)?{side}\s+({_DECL_NUM_RE.pattern})\s*$"
        )
        values = []
        for match in pattern.finditer(low):
            try:
                values.append(abs(Decimal(
                    match.group(1).replace(".", "").replace(",", "."))))
            except Exception:
                continue
        return max(values) if values else None

    if out["attivo"] is None:
        out["attivo"] = _section_heading_inline("attivo")
    if out["passivo"] is None:
        out["passivo"] = _section_heading_inline("passivo")
```

- [ ] **Step 4: verificare che passi + zero regressioni sui marker esistenti**

Run: `python -m pytest tests/test_declared_totals_markers.py -q`
Expected: `3 passed`

Run: `python Test/_quadratura_harness.py Test/june_sample`
Expected: risultato identico alla baseline (6/10) — i marker sono solo AGGIUNTI.

- [ ] **Step 5: Commit**

```bash
git add importers/pdf_extractor_llm.py tests/test_declared_totals_markers.py
git commit -m "fix(import): marker sinonimi per i totali dichiarati (utile SP, utile esercizio, stato patrimoniale attivo inline)"
```

---

## Accettazione del piano

```bash
python -m pytest tests/test_declared_source_verdict.py tests/test_source_verdict_messages.py \
                 tests/test_declared_totals_markers.py -q            # tutti PASS
python tests/_import_probe.py "Test/prova_tets/budget_610_2023 Bar e altri esercizi simili senza cucina.pdf" standard
python tests/_import_probe.py "Test/errori/budget_238_CARP 2025.pdf" standard
# → in entrambi: mai "Correggere il documento contabile originale"
python tests/_import_probe.py "Test/errori/budget_152_BILAQ-001.pdf" standard
# → ancora rifiutato come sorgente sbilanciata (scarto reale ≠ utile)
```

Più il gate di regressione standard del quadro generale (§6).

</details>

---

## Accettazione del piano — RIVISTA 2026-07-27

- Task 0: **gia fatto** (`tests/_import_probe.py` esiste ed e funzionante).
- Task 1 e 2: eseguibili cosi come scritti.
- Task 3: **annullato**, assorbito dal Piano 05 Task 4.
- I file 610/229/238/243/246/188/395 non devono piu ricevere un messaggio che incolpa il documento
  quando il pareggio dichiarato conferma che la sorgente quadra.
- Nessuna variazione dei totali salvati sul campione pulito (Quadro §6).
