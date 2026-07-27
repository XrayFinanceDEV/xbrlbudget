# Piano 02 — Route C: retry sui candidati e "trial balance mai hard-blocked"

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** eliminare i fallimenti INTERMITTENTI del route C (243, 246, 395) facendo ripiegare
automaticamente sul candidato successivo quando quello scelto non supera i gates contabili, e ripristinare
la policy documentata "un trial balance leggibile importa SEMPRE" (330, 623) con plug flaggato in
Rettifiche invece di hard-fail.

**Architettura:** oggi `pdf_importer.py` (blocco `if is_trial_balance:` righe ~714-937) ordina i candidati
(CoGe-LLM, deterministico) per completezza e prende `candidates[0]`; se quel candidato fallisce più a valle
(`validate_balance` riga 1004 o `check_quadratura` riga 1107) l'import muore senza mai provare l'altro
candidato — che spesso quadra (dimostrato da `tests/_prod_route_c_runner.py` su 243/246/395). Si estrae la
post-elaborazione del candidato in una funzione, si valuta OGNI candidato in ordine e si tiene il primo che
passa; se nessuno passa e il documento dichiara il proprio pareggio, si importa il migliore con plug +
warning severo (mai il messaggio che incolpa la sorgente — Piano 01).

**Tech stack:** Python, pytest. Dipende dal Piano 01 (usa `declared_source_verdict` e
`MSG_EXTRACTION_INCOMPLETE`).

## Vincoli globali
Ereditati dal quadro generale §7. In più: la selezione NON deve cambiare esito sui file dove il candidato
scelto oggi già passa (usare i 10 file-campione del protocollo §6 come invarianti).

---

### Task 1: helper puro di selezione con retry

**Files:**
- Modify: `importers/pdf_importer.py` (nuova funzione modulo-level, prima di `import_pdf_balance_sheet`)
- Test: `tests/test_route_c_candidate_retry.py` (nuovo)

**Interfaces:**
- Produces: `_pick_first_passing_candidate(ordered_candidates, finalize, passes) -> tuple[Any, bool]`
  dove `ordered_candidates` è la lista già ordinata per completezza, `finalize(cand)` applica la
  post-elaborazione e ritorna il risultato finalizzato, `passes(finalized)` è il gate booleano.
  Ritorna `(finalized, True)` per il primo che passa, altrimenti `(finalized_del_primo, False)`.
  Consumata dal Task 2.

- [ ] **Step 1: test che fallisce**

```python
# tests/test_route_c_candidate_retry.py
from importers.pdf_importer import _pick_first_passing_candidate


def test_primo_candidato_che_passa_vince():
    calls = []
    cands = ["llm", "det"]
    fin = lambda c: (calls.append(c) or f"fin-{c}")
    ok, passed = _pick_first_passing_candidate(cands, fin, lambda f: f == "fin-det")
    assert (ok, passed) == ("fin-det", True)
    assert calls == ["llm", "det"]          # il retry ha valutato entrambi


def test_se_il_primo_passa_non_si_valuta_il_secondo():
    calls = []
    cands = ["llm", "det"]
    fin = lambda c: (calls.append(c) or f"fin-{c}")
    ok, passed = _pick_first_passing_candidate(cands, fin, lambda f: True)
    assert (ok, passed) == ("fin-llm", True)
    assert calls == ["llm"]                 # nessun costo extra sul percorso felice


def test_nessuno_passa_si_tiene_il_primo():
    ok, passed = _pick_first_passing_candidate(["a", "b"], lambda c: c, lambda f: False)
    assert (ok, passed) == ("a", False)


def test_finalize_che_solleva_scarta_il_candidato():
    def fin(c):
        if c == "rotto":
            raise ValueError("estrazione esplosa")
        return c
    ok, passed = _pick_first_passing_candidate(["rotto", "sano"], fin, lambda f: True)
    assert (ok, passed) == ("sano", True)
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_route_c_candidate_retry.py -q`
Expected: `ImportError: cannot import name '_pick_first_passing_candidate'`

- [ ] **Step 3: implementare** in `importers/pdf_importer.py` (modulo-level):

```python
def _pick_first_passing_candidate(ordered_candidates, finalize, passes):
    """Valuta i candidati route-C in ordine di completezza e ritorna il PRIMO il cui
    risultato finalizzato supera i gates contabili. L'estrattore CoGe-LLM e' stocastico:
    quando sotto-estrae, il deterministico e' spesso perfetto (audit 2026-07-23:
    budget_243/246/395) — prima di questo retry l'import moriva senza provarlo.
    Se nessun candidato passa, ritorna il finalizzato del primo (per il percorso
    plug-and-flag / diagnosi onesta a valle) con passed=False. Un finalize che solleva
    scarta il candidato."""
    first_finalized = None
    for cand in ordered_candidates:
        try:
            finalized = finalize(cand)
        except Exception as exc:
            logger.warning(f"Route C: candidato scartato in finalizzazione "
                           f"({type(exc).__name__}: {exc})")
            continue
        if first_finalized is None:
            first_finalized = finalized
        if passes(finalized):
            return finalized, True
    if first_finalized is None:
        raise PDFImportError(
            "Route C: nessun candidato di estrazione utilizzabile")
    return first_finalized, False
```

- [ ] **Step 4: verificare che passi**

Run: `python -m pytest tests/test_route_c_candidate_retry.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add importers/pdf_importer.py tests/test_route_c_candidate_retry.py
git commit -m "feat(route-C): helper di selezione candidati con retry sui gates contabili"
```

---

### Task 2: cablare il retry nel blocco route C

**Files:**
- Modify: `importers/pdf_importer.py:795-937` (blocco `if candidates:`)

**Interfaces:**
- Consumes: `_pick_first_passing_candidate` (Task 1); le funzioni esistenti `overlay_debt_typing`,
  `net_contra_accounts`, `_reconcile_trial_to_declared`, `check_quadratura`, `mapper.validate_balance`,
  `enforce_ce_sp_identity`.
- Produces: variabili `balance_sheet_data`, `income_data`, `residual`, `source`, `_contra` con la stessa
  semantica di oggi (il codice a valle non cambia).

- [ ] **Step 1: rifattorizzare.** Il corpo attuale righe 849-920 (dal
`residual, balance_sheet_data, income_data, source = candidates[0]` fino al blocco
`_reconcile_trial_to_declared` incluso) diventa una closure `_finalize(cand)` DENTRO il blocco
`if candidates:` — testo INVARIATO salvo lavorare su copie e ritornare un dict:

```python
            if candidates:
                # (il calcolo di _decl_tot / _dc0 / _completeness_gap resta INVARIATO qui sopra)
                candidates.sort(key=lambda c: (_completeness_gap(c[1]), c[0]))

                def _finalize(cand):
                    residual, bs, ce, source = cand
                    bs = dict(bs)          # mai mutare il candidato: serve al retry
                    ce = dict(ce)
                    if source != "deterministico":
                        _det = next((c for c in candidates if c[3] == "deterministico"), None)
                        if _det is not None:
                            from importers.situazione_contabile_parser import overlay_debt_typing
                            bs = overlay_debt_typing(bs, _det[1])
                    _contra = Decimal('0')
                    try:
                        from importers.situazione_contabile_parser import net_contra_accounts
                        bs, _contra = net_contra_accounts(
                            bs, file_path, text=ocr_text, declared=_dc0)
                        if _contra > 0:
                            logger.info(f"Route C: contra-netting applicato "
                                        f"({_contra:,.0f} fondi ammortamento/IVA)")
                    except Exception as _cn_err:
                        logger.warning(f"Route C: contra-netting saltato: {_cn_err}")
                    _authoritative = bs.pop('_skip_declared_reconcile', False)
                    if not _authoritative:
                        try:
                            from importers.pdf_extractor_llm import _reconcile_trial_to_declared
                            from importers.iv_cee_hierarchy import _net_profit_from_ce
                            _decl = dict(_dc0)
                            _anchor_cut = _contra if _contra > 0 else bs.get(
                                '_netted_contra', Decimal('0'))
                            if _anchor_cut > 0:
                                for _k in ('attivo', 'passivo', 'pareggio'):
                                    if _decl.get(_k):
                                        _decl[_k] = _decl[_k] - _anchor_cut
                            try:
                                _ce_res = _net_profit_from_ce(ce)
                            except Exception:
                                _ce_res = None
                            bs = _reconcile_trial_to_declared(
                                bs, _decl, source, ce_result=_ce_res)
                            residual = bs.get('_plug_residual', residual)
                        except Exception as _rc_err:
                            logger.warning(f"Route C: declared-result reconcile skipped: {_rc_err}")
                    return {"bs": bs, "ce": ce, "residual": residual,
                            "source": source, "contra": _contra}

                def _passes(f):
                    """Gates contabili anticipati: gli stessi che a valle bloccherebbero
                    (validate_balance + quadratura non mascherata)."""
                    try:
                        if not mapper.validate_balance(f["bs"]):
                            return False
                        q = check_quadratura(f["bs"], f["ce"], tol=Decimal('2'))
                        return q.quadra
                    except Exception:
                        return False

                chosen, _cand_passed = _pick_first_passing_candidate(
                    candidates, _finalize, _passes)
                balance_sheet_data = chosen["bs"]
                income_data = chosen["ce"]
                residual = chosen["residual"]
                source = chosen["source"]
                _contra = chosen["contra"]
                _coge_ok = True
                others = ", ".join(f"{s}={r:,.0f}" for r, _b, _c, s in candidates)
                logger.info(f"Route C: scelto estrattore '{source}' "
                            f"(passed={_cand_passed}); candidati: {others}")
```

Il blocco successivo (warning `BILANCIO NON QUADRATO` righe 924-937) resta INVARIATO.
NOTA: `check_quadratura` è già importato in testa al blocco route C (riga 725).

- [ ] **Step 2: regressione sui file bersaglio (intermittenti) — 3 run ciascuno**

```bash
for i in 1 2 3; do
  python tests/_import_probe.py "Test/errori/budget_243_MBS 2025.pdf" standard
  python tests/_import_probe.py "Test/successTerzo/success/budget_246_SAMAC APPALTI SRL - BILANCIO AL 31.12.2025.pdf" standard
  python tests/_import_probe.py "Test/sez-contrapposte/budget_395_BILANCIO AGRIMIX SAS  31.12.2025 definitivo.pdf" standard
done
```
Expected: `ok=true` in TUTTE e 9 le run (il deterministico passa sempre i gates su questi file:
243 → sp13 4.395,97; 246 → sp13 56.999,12, attivo netto 5.331.402,16; 395 → sp13 125.447,80,
attivo netto 10.337.913,78).

- [ ] **Step 3: regressione sul campione pulito** (protocollo §6 del quadro): totali IDENTICI a prima.

- [ ] **Step 4: Commit**

```bash
git add importers/pdf_importer.py
git commit -m "fix(route-C): retry automatico sul candidato successivo quando i gates contabili bocciano il primo — addio fallimenti intermittenti"
```

---

### ~~Task 3: "trial balance mai hard-blocked" — plug-and-flag~~ — ANNULLATO (2026-07-27)

> **NON ESEGUIRE. `_force_balance_trial` non va scritto.**
>
> Il task proponeva di **aggiungere importi a `sp09` (cassa) e `sp16g` (altri debiti)** per portare a zero
> lo sbilancio di un trial balance che non quadra. È un fix del sintomo che **inventa dati contabili**, e
> contraddice tre invarianti già documentate in `docs/import/REGOLE-IMPORT-00-INDICE.md` (tabella dei
> drift, §5):
>
> | | il documento diceva | il codice fa (verificato) |
> |---|---|---|
> | **D1** | il residuo viene "tamponato in sp09/sp16" | **nessun plug viene applicato**: il residuo è solo *misurato* e dichiarato |
> | **D3** | `enforce_ce_sp_identity` riallinea il CE | è **puramente diagnostico**, non muta né CE né SP |
> | **D4** | `reconcile_ivcee_balance` tampona con `cap_frac=0.05` | ritorna una **copia invariata** e riporta la differenza |
>
> Il repo ha già fatto, consapevolmente, il percorso opposto: dai plug alle diagnosi oneste
> (commit `4a2e80f` "import: diagnosi oneste al posto dei plug"). Reintrodurli qui significherebbe
> tornare indietro e, peggio, farlo in silenzio: un bilancio con `sbilancio = 0` ottenuto per plug è
> **indistinguibile** da uno corretto per qualunque gate a valle.
>
> Difetti tecnici aggiuntivi del codice proposto, per memoria: conteneva una riga morta immediatamente
> riassegnata; chiedeva all'implementatore di *verificare empiricamente* la propria premessa contabile
> («verificare su un candidato reale se `totale_passivo` include già sp13»); emetteva sempre il warning
> "prevalentemente stimata" contraddicendo la policy a tre scaglioni descritta due paragrafi sopra; e le
> soglie 5%/20% erano tarate enumerando i file (188 al 4,1%, il run degenerato di 246 al 21%).
>
> **Sostituzione — policy "leggibile ⇒ importabile, ma dichiarato".** L'obiettivo del task (un trial
> balance leggibile non deve morire con un errore) resta valido; cambia il mezzo. Quando **nessun**
> candidato supera i gate:
>
> 1. **ri-tentare** l'estrazione/classificazione (retry del Task 1 + `use_llm=True` del Piano 05 sulle
>    sole righe irrisolte) — è l'unico intervento che può far quadrare *davvero*;
> 2. se ancora no, **importare i valori COSÌ COME SONO ESTRATTI**, senza toccare un solo importo,
>    marcando il record `validation_status = "review_required"` (la colonna esiste già:
>    **nessuna migrazione**), con il residuo e lo sbilancio esposti nel `validation_report` e un warning
>    esplicito che rimanda a Rettifiche;
> 3. **`forecastable = False`** su quel record: un bilancio non quadrato non deve poter alimentare un
>    forecast;
> 4. **mai** modificare un valore contabile per ottenere zero.
>
> Chi implementa la sostituzione: il gate `if not _qd.quadra` (`pdf_importer.py:~1107-1122`) smette di
> sollevare `PDFImportError` per la route C e passa per il ramo `review_required`; **il pareggio resta
> bloccante per le route A/B**, dove il documento è un bilancio di legge che deve quadrare per costruzione.
> Test: un trial balance sbilanciato importa con `validation_status="review_required"`,
> `forecastable=False`, **e i valori identici a quelli estratti** (nessun campo modificato).

<details>
<summary>Testo originale del Task 3 (archiviato, NON eseguire)</summary>

### Task 3: "trial balance mai hard-blocked" — plug-and-flag come ultima risorsa

**Files:**
- Modify: `importers/pdf_importer.py` — ramo `if not mapper.validate_balance(...)` (post Piano 01) e
  ramo `if not _qd.quadra` (righe ~1107-1122)
- Test: `tests/test_trial_never_hard_blocked.py` (nuovo)

**Interfaces:**
- Consumes: `declared_source_verdict` (Piano 01), `SC_PLUG_REJECT_PCT` (costante esistente, = 0.20).
- Produces: `_force_balance_trial(bs, ce, dc) -> tuple[dict, dict, list[str]]` modulo-level.

**Decisione di policy (dal quadro §1.2 e dalla policy documentata in CLAUDE.md):** un route C con
sorgente che dichiara il proprio pareggio NON viene mai rigettato. Soglie:
- residuo ≤ 5% del totale → import con warning "BILANCIO NON QUADRATO (parziale)" (oggi: rigetto >1%);
- 5% < residuo ≤ `SC_PLUG_REJECT_PCT` (20%) → import con warning "prevalentemente stimata";
- residuo > 20% → rigetto (estrazione inutilizzabile), col messaggio del Piano 01 che NON incolpa la
  sorgente. I casi audit: 169 (2,3%), 338 (2,7%), 188 (4,1%) rientrano nel primo scaglione — e con il
  Piano 03 il loro residuo scende comunque ~a 0; 646 (12,8%) nel secondo; il run degenerato di 246 (21%)
  resta rigettato finché il retry (Task 2) non lo evita a monte.

- [ ] **Step 1: test che fallisce**

```python
# tests/test_trial_never_hard_blocked.py
from decimal import Decimal as D
from importers.pdf_importer import _force_balance_trial


def test_gap_attivo_va_in_cassa_e_sp13_dal_dichiarato():
    # componenti sotto-estratte: attivo 300k vs passivo 340k, utile dichiarato 10k
    bs = {"totale_attivo": D("300000"), "totale_passivo": D("340000"),
          "sp09_disponibilita_liquide": D("5000"), "sp13_utile_perdita": D("0")}
    ce = {}
    dc = {"attivo": D("360000"), "passivo": D("350000"), "utile": D("10000"),
          "perdita": None, "pareggio": D("360000")}
    bs2, ce2, warns = _force_balance_trial(bs, ce, dc)
    assert bs2["sp13_utile_perdita"] == D("10000")
    assert bs2["totale_attivo"] == bs2["totale_passivo"]
    assert any("BILANCIO NON QUADRATO" in w for w in warns)


def test_gap_passivo_va_in_altri_debiti():
    bs = {"totale_attivo": D("360000"), "totale_passivo": D("300000"),
          "sp16_debiti_breve": D("0"), "sp13_utile_perdita": D("10000")}
    bs2, _ce, _w = _force_balance_trial(bs, {}, {"attivo": D("360000"),
                    "passivo": D("350000"), "utile": D("10000"),
                    "perdita": None, "pareggio": None})
    assert bs2["totale_attivo"] == bs2["totale_passivo"]
    assert bs2["sp16_debiti_breve"] > 0
    assert bs2.get("sp16g_altri_debiti_breve", D("0")) == bs2["sp16_debiti_breve"]
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_trial_never_hard_blocked.py -q`
Expected: ImportError.

- [ ] **Step 3: implementare** `_force_balance_trial` (modulo-level in `pdf_importer.py`):

```python
def _force_balance_trial(bs, ce, dc):
    """Ultima risorsa route C su sorgente che DICHIARA il proprio pareggio: forza il
    bilancio estratto a quadrare, marcando tutto per Rettifiche. Mai chiamata quando
    un candidato ha gia' passato i gates. Ritorna (bs, ce, warnings)."""
    bs = dict(bs)
    warns = []
    utile = dc.get('utile')
    perdita = dc.get('perdita')
    if utile is not None and not bs.get('sp13_utile_perdita'):
        bs['sp13_utile_perdita'] = utile
    elif perdita is not None and not bs.get('sp13_utile_perdita'):
        bs['sp13_utile_perdita'] = -perdita
    att = bs.get('totale_attivo', Decimal('0'))
    pas = (bs.get('totale_passivo', Decimal('0'))
           + (bs['sp13_utile_perdita'] if 'sp13_utile_perdita' in bs else Decimal('0'))
           - (bs.get('sp13_utile_perdita') or Decimal('0')))  # sp13 gia' dentro totale? no: vedi sotto
    # totale_passivo dei candidati route C NON include mai sp13 non riconciliato:
    pas = bs.get('totale_passivo', Decimal('0'))
    gap = pas + (bs.get('sp13_utile_perdita') or Decimal('0')) - att
    if gap > 0:            # manca attivo → plug in cassa
        bs['sp09_disponibilita_liquide'] = (
            bs.get('sp09_disponibilita_liquide', Decimal('0')) + gap)
        bs['totale_attivo'] = att + gap
        bs['totale_passivo'] = pas + (bs.get('sp13_utile_perdita') or Decimal('0'))
    elif gap < 0:          # manca passivo → plug in altri debiti breve
        bs['sp16_debiti_breve'] = bs.get('sp16_debiti_breve', Decimal('0')) - gap
        bs['sp16g_altri_debiti_breve'] = (
            bs.get('sp16g_altri_debiti_breve', Decimal('0')) - gap)
        bs['totale_passivo'] = pas - gap + (bs.get('sp13_utile_perdita') or Decimal('0'))
        bs['totale_attivo'] = att
    else:
        bs['totale_passivo'] = pas + (bs.get('sp13_utile_perdita') or Decimal('0'))
    plug = abs(gap)
    tot = bs.get('totale_attivo') or Decimal('1')
    warns.append(
        f"BILANCIO NON QUADRATO (prevalentemente stimata): differenza {plug:,.0f} "
        f"({100 * plug / tot:.0f}% del totale) forzata a pareggio per consentire la "
        f"correzione in Rettifiche — la composizione NON e' affidabile")
    bs['_plug_residual'] = plug
    return bs, ce, warns
```

NB per l'implementatore: PRIMA di fidarsi delle due righe su `totale_passivo`, verificare su un
candidato reale (probe su budget_330) se `totale_passivo` del candidato route C include già sp13;
allineare il calcolo del `gap` di conseguenza. Il test del Step 1 fissa il contratto atteso.

- [ ] **Step 4: cablarla.** Nel ramo di fallimento di `validate_balance` (dopo le modifiche del Piano
01, PRIMA del `raise _source_failure_error(...)`):

```python
            from importers.pdf_extractor_llm import declared_source_verdict
            _verdict = declared_source_verdict(_dc_fail, is_trial_balance=is_trial_balance)
            if (is_trial_balance and _verdict == "balanced"
                    and balance_sheet_data.get('totale_attivo', Decimal('0')) > 0):
                balance_sheet_data, income_data, _fb_warns = _force_balance_trial(
                    balance_sheet_data, income_data, _dc_fail)
                sc_quadratura_warnings.extend(_fb_warns)
                logger.warning("Route C: import forzato a pareggio (never-hard-blocked); "
                               "residuo in Rettifiche")
            else:
                raise PDFImportError(_source_failure_error(
                    _dc_fail, is_trial_balance=is_trial_balance,
                    sample_text=sample_text))
```

E nel ramo `if not _qd.quadra:` (righe ~1107-1122) esentare il route C sotto soglia:

```python
            if not _qd.quadra:
                _tot_q = balance_sheet_data.get('totale_attivo', Decimal('0')) or Decimal('1')
                _plug_q = balance_sheet_data.get('_plug_residual', Decimal('0'))
                _route_c_tolerable = (
                    is_trial_balance
                    and not _qd.is_empty
                    and _plug_q <= SC_PLUG_REJECT_PCT * _tot_q
                    and not any(w.startswith("Utile CE") for w in _qd.warnings)
                )
                if _route_c_tolerable:
                    for _w in _qd.warnings:
                        if _w not in sc_quadratura_warnings:
                            sc_quadratura_warnings.append(_w)
                    logger.warning("Route C: quadratura imperfetta importata con flag "
                                   f"(plug {_plug_q:,.0f} ≤ {SC_PLUG_REJECT_PCT:.0%})")
                else:
                    _blocking_warnings = [
                        warning for warning in _qd.warnings
                        if not warning.startswith("GERARCHIA INCOERENTE:")
                    ]
                    reason = "; ".join(_blocking_warnings) or (
                        f"attivo {_qd.totale_attivo} / passivo {_qd.totale_passivo}")
                    raise PDFImportError(
                        "Importazione non salvata: il bilancio estratto non supera i "
                        f"controlli contabili ({reason})")
```

(la condizione `not any(w.startswith("Utile CE") ...)` mantiene BLOCCANTE la violazione CE↔SP:
quella non è tollerabile perché corrompe il risultato d'esercizio).

- [ ] **Step 5: verificare**

Run: `python -m pytest tests/test_trial_never_hard_blocked.py -q` → PASS.

```bash
python tests/_import_probe.py "Test/successTerzo/success/budget_330_KG Project Srl situazione contabile al 31-12-2025.pdf" standard
python tests/_import_probe.py "Test/prova_tets/budget_623_2025 Commercio al dettaglio di ferramenta, vernici, vetro piano e materiale elettrico e termoidraulico  .pdf" standard
```
Expected: `ok=true` con warning "BILANCIO NON QUADRATO" nei warnings (330: sp13=-2.505,51 dal dichiarato).

Regressione: i file 133/135/152 (sorgenti rotte, route A/B o verdict unbalanced) devono restare FAIL.

- [ ] **Step 6: Commit**

```bash
git add importers/pdf_importer.py tests/test_trial_never_hard_blocked.py
git commit -m "fix(route-C): trial balance mai hard-blocked — plug a pareggio con flag Rettifiche quando la sorgente dichiara il pareggio"
```

---

</details>

---

## Accettazione del piano

- 243/246/395: `ok=true` su 3 run consecutive ciascuno (niente intermittenza).
- 330/623: importano flaggati.
- Campione pulito §6: totali identici. Harness `Test/june_sample`: ≥ 6/10 (nessuna regressione).
- 133/135/137/152/161/289: ancora rifiutati.

> **Rettifica 2026-07-27:** i criteri qui sopra che presuppongono `_force_balance_trial` non valgono
> piu. Il Task 3 e annullato: un trial balance che non quadra importa **con i valori estratti**,
> `validation_status="review_required"` e `forecastable=False` — mai con un plug. Verificare inoltre che
> NESSUN campo differisca da quello estratto (test dedicato), oltre ai criteri dei Task 1-2.
