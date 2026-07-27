# Piano 03 — Netting completo dei fondi rettificativi (route C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** azzerare i residui "QUADRATURA MASCHERATA" su bilanci in realtà perfetti, estendendo il netting
deterministico route-C a: (a) **fondo svalutazione / rischi su CREDITI** → riduce sp06 (non è un debito);
(b) **fondo rischi e oneri** → passivo sp14 (non è contra-asset); (c) fondi ammortamento esposti come
conti singoli senza riga di sotto-totale.

**Architettura:** il netting route-C vive in `importers/situazione_contabile_parser.py`:
`_contra_rows` (scan del PDF) → `_contra_classify` (→ `ContraScan`) → `net_contra_accounts` (overlay sul
candidato scelto, chiamato da `pdf_importer.py:871`). Oggi `ContraScan` cattura solo fondi immobilizzazioni
+ IVA; la massa "fondo svalutazione crediti" e "fondo rischi e oneri" resta non classificata → plug →
rigetto. Si estende `ContraScan` con due nuovi aggregati e si aggancia il netting sp06 / la
riclassificazione sp14 dentro `net_contra_accounts`.

**Tech stack:** Python, pytest. Test unitari su `_contra_classify` / `net_contra_accounts` con righe
sintetiche (nessun PDF nel repo). Indipendente dagli altri piani (ma i suoi effetti si sommano al Piano
02: un candidato ben nettato passa i gates e viene scelto senza plug).

## Vincoli globali
Quadro generale §7. In più: il netting è DETERMINISTICO e auto-validante — ogni nuova compensazione deve
avere un gate che la rende no-op quando i dati non confermano (mai scrivere un netto sbagliato). Distinguere
SEMPRE per descrizione della SINGOLA riga (leaf), mai per etichetta aggregata (budget_646: aggregato
"F.DI RISCHI SU CREDITI" contiene in realtà un fondo rischi e oneri da 1,41M).

---

## Contesto contabile (perché tre trattamenti diversi)

| Voce sorgente (lato passivo, presentazione lorda) | Natura | Destinazione IV-CEE |
|---|---|---|
| F.do amm.to / F.do svalutaz. IMMOBILIZZAZIONI (fabbricati, impianti, marchi…) | contra-asset B.I/B.II | netta **sp02/sp03** (già gestito) |
| F.do svalutaz. / rischi su **CREDITI** (v/clienti, tributari, fiscali) | contra-asset C.II | netta **sp06** ← NUOVO |
| F.do **rischi e oneri** (cause, garanzie, controversie, generico) | vero passivo B | classifica **sp14** ← NUOVO |
| IVA erario (attivo/passivo) | posizione compensabile | offset (già gestito) |

Regola di disambiguazione (leaf-level): `SVALUT`/`RISCHI` **+** `CREDIT` → sp06. `RISCHI`/`ONERI` **senza**
`CREDIT` → sp14. `SVALUT`/`AMM` **+** immobilizzazione → sp02/sp03 (già). Vedi `_SVALUT_NON_IMMOB_KW`
esistente (riga 3358) che già elenca `CREDIT/RIMANENZ/MAGAZZIN/TITOL/PARTECIP` come "non immobilizzazioni".

---

### ~~Task 1: estendere `ContraScan` con crediti e rischi/oneri~~ — RIDOTTO (2026-07-27)

> **La parte "riconoscere l'etichetta" è assorbita dal Piano 05 Task 5. Resta solo la parte strutturale.**
>
> La **regola contabile** del task è giusta e va tenuta: contra-crediti → netta sp06; fondo rischi e oneri
> → sp14 e **non** si netta; disambiguazione leaf-level `SVALUT`/`RISCHI` **+** `CREDIT` → sp06,
> `RISCHI`/`ONERI` **senza** `CREDIT` → sp14; mai fidarsi dell'etichetta aggregata (budget_646: un
> aggregato «F.DI RISCHI SU CREDITI» contiene in realtà 1,41M di fondo rischi e oneri).
>
> Quello che **non** va scritto qui sono le due liste di substring (`_is_fondo_crediti`,
> `_is_fondo_rischi_oneri` con `RISCHI|ONERI|CONTROVERS|GARANZI|CAUSE`). Coprono solo l'osservato e
> lasciano fuori fondi rischi ordinarissimi — «F.do indennità suppletiva di clientela», «Fondo spese
> future», «Fondo manutenzioni cicliche», «Accantonamento quiescenza» — che continuerebbero a finire nei
> debiti. Inoltre `'F/' in d` come marcatore di "fondo" è un match di due caratteri che colpisce
> descrizioni innocue.
>
> **Da fare invece, in questo piano:**
> 1. aggiungere a `ContraScan` i due campi `sval_crediti` e `fondi_rischi_oneri` (parte strutturale, resta);
> 2. il loop di `_contra_classify` **legge il `role`** da `label_semantics.classify_label(desc,
>    space="conto", side=...)` (Piano 05 T5) invece di chiamare due nuovi predicati a keyword;
> 3. **aggiornare il SECONDO consumatore di `ContraScan`**, che il piano originale non menziona:
>    `pdf_importer.py:823-836` ricalcola indipendentemente la massa contra
>    (`_fondi = _scan.fondi_immat + _scan.fondi_mat + _scan.sval_immat + _scan.sval_mat`) per correggere
>    l'ancora `_decl_tot` usata nell'**ordinamento dei candidati route C**. Se si netta `sval_crediti` dal
>    `bs` ma non lo si toglie dall'ancora, `_completeness_gap` sbaglia di quella massa e la selezione del
>    candidato cambia. ⚠️ Sono le stesse righe che il Piano 02 Task 2 riscrive: coordinare o eseguire 03
>    prima di 02 (l'ordine rivisto del Quadro §4 lo prevede).

<details>
<summary>Testo originale del Task 1 (archiviato — usare solo per la regola contabile, non per le liste)</summary>

### Task 1: estendere `ContraScan` con crediti e rischi/oneri

**Files:**
- Modify: `importers/situazione_contabile_parser.py:3388-3401` (NamedTuple `ContraScan`)
- Modify: `importers/situazione_contabile_parser.py:3437-…` (`_contra_classify`, popolamento nuovi campi)
- Test: `tests/test_contra_classify_crediti.py` (nuovo)

**Interfaces:**
- Produces: `ContraScan` con due campi nuovi `sval_crediti: Decimal = Decimal('0')` e
  `fondi_rischi_oneri: Decimal = Decimal('0')`. Consumati dal Task 2.
- Helper nuovi modulo-level: `_is_fondo_crediti(desc_upper) -> bool`, `_is_fondo_rischi_oneri(desc_upper) -> bool`.

- [ ] **Step 1: test che fallisce**

```python
# tests/test_contra_classify_crediti.py
from decimal import Decimal as D
from importers.situazione_contabile_parser import (
    _contra_classify, _is_fondo_crediti, _is_fondo_rischi_oneri)


def test_riconosce_fondo_svalutazione_crediti():
    assert _is_fondo_crediti("F.DO SVAL.CREDITI V.CLIENTI")
    assert _is_fondo_crediti("F/DO RISCHI SU CREDITI V.CLIENTI")
    assert _is_fondo_crediti("F/DO SVALUTAZIONI CREDITI FISCALI")
    assert not _is_fondo_crediti("F.DO AMM.TO FABBRICATI")
    assert not _is_fondo_crediti("F/DO RISCHI E ONERI")           # niente CREDITI → non qui


def test_riconosce_fondo_rischi_oneri_passivo():
    assert _is_fondo_rischi_oneri("F/DO RISCHI E ONERI")
    assert _is_fondo_rischi_oneri("FONDO PER RISCHI E ONERI FUTURI")
    assert _is_fondo_rischi_oneri("FONDO CONTROVERSIE LEGALI")
    assert not _is_fondo_rischi_oneri("F/DO RISCHI SU CREDITI")   # è contra-crediti
    assert not _is_fondo_rischi_oneri("F.DO AMM.TO IMPIANTI")


def test_contra_classify_separa_crediti_e_rischi_oneri():
    # budget_646: aggregato fuorviante, leaf-level decide
    passivo = [
        ("160010", "F/DO SVALUTAZIONI CREDITI FISCALI", D("9520.00")),
        ("160010", "F/DO RISCHI E ONERI", D("1413685.61")),
        ("200765", "F.DO AMM. FABBRICATI STRUMENTALI", D("1968.13")),
    ]
    attivo = [("140000", "CREDITI V/CLIENTI", D("500000")),
              ("130850", "FABBRICATI", D("100000"))]
    scan = _contra_classify(attivo, passivo)
    assert scan.sval_crediti == D("9520.00")
    assert scan.fondi_rischi_oneri == D("1413685.61")
    assert scan.fondi_mat == D("1968.13")            # fabbricati resta contra-immobilizzi
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_contra_classify_crediti.py -q`
Expected: `ImportError` (helper e campi inesistenti).

- [ ] **Step 3: implementare.**

(a) Helper modulo-level, vicino a `_is_fondo_svalut_immob` (~riga 3361):

```python
def _is_fondo_crediti(desc_upper: str) -> bool:
    """Fondo svalutazione / rischi su CREDITI: contra-asset dei crediti (riduce sp06),
    non un debito. Richiede sia il marcatore fondo/svalutazione/rischi sia 'CREDIT'."""
    d = desc_upper
    if 'CREDIT' not in d:
        return False
    has_fund = ('FOND' in d or 'F.DO' in d or 'F/DO' in d or 'F/' in d)
    return has_fund and ('SVALUT' in d or 'SVAL' in d or 'RISCHI' in d)


def _is_fondo_rischi_oneri(desc_upper: str) -> bool:
    """Fondo rischi e oneri (art. 2424 B del passivo → sp14): vero passivo, NON contra.
    Esclude i fondi su crediti (quelli sono contra-asset, _is_fondo_crediti) e i fondi
    ammortamento/svalutazione immobilizzazioni."""
    d = desc_upper
    if 'CREDIT' in d:
        return False
    if _is_fondo_amm(d) or _is_fondo_svalut_immob(d):
        return False
    has_fund = ('FOND' in d or 'F.DO' in d or 'F/DO' in d or 'F/' in d)
    return has_fund and ('RISCHI' in d or 'ONERI' in d or 'CONTROVERS' in d
                         or 'GARANZI' in d or 'CAUSE' in d)
```

(b) In `ContraScan` (righe 3400-3401) aggiungere:

```python
    sval_crediti: Decimal = Decimal('0')       # fondo svalut./rischi su crediti (→ sp06)
    fondi_rischi_oneri: Decimal = Decimal('0')  # fondo rischi e oneri (→ sp14, vero passivo)
```

(c) In `_contra_classify`, nel loop che classifica le righe (dopo che vengono già sommati
`fondi_immat`/`fondi_mat`/IVA), aggiungere prima del fallback, per OGNI riga (usa `desc_upper` e
`amount` già disponibili nel loop — l'implementatore lo aggancia al loop esistente):

```python
        # contra sui crediti e fondo rischi/oneri (leaf-level, mai per aggregato)
        if _is_fondo_crediti(desc_upper):
            sval_crediti_acc += abs(amount)
            continue
        if _is_fondo_rischi_oneri(desc_upper):
            rischi_oneri_acc += abs(amount)
            continue
```

inizializzando `sval_crediti_acc = Z` e `rischi_oneri_acc = Z` a inizio funzione, e passandoli nella
costruzione finale del `ContraScan(...)`: `sval_crediti=sval_crediti_acc, fondi_rischi_oneri=rischi_oneri_acc`.

NB: l'ordine dei check conta — `_is_fondo_crediti` PRIMA di `_is_fondo_amm`/immob (un "F.DO SVAL CREDITI"
non deve finire nei fondi immobilizzazioni). Verificare che nel loop questi due `if` precedano i check
immobilizzazioni esistenti.

- [ ] **Step 4: verificare che passi**

Run: `python -m pytest tests/test_contra_classify_crediti.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add importers/situazione_contabile_parser.py tests/test_contra_classify_crediti.py
git commit -m "feat(netting): ContraScan riconosce fondo svalut./rischi crediti (→sp06) e fondo rischi e oneri (→sp14)"
```

</details>

---

### Task 2: nettare crediti e classificare rischi/oneri in `net_contra_accounts`

> **CORREZIONE 2026-07-27 — due difetti da sanare prima di scrivere il codice proposto.**
>
> 1. **`_apply_contra_to_bs` può sbilanciare il foglio.** Il codice proposto riduce `sp06` del fondo
>    crediti e toglie la stessa massa dai debiti **solo se** la trova lì
>    (`if bs.get('sp16g_altri_debiti_breve', Z) >= sc: …`). Se il candidato aveva classificato il fondo in
>    `sp17`, in `sp14`, o l'aveva già escluso, l'attivo scende e il passivo no: **sbilancio pari alla massa
>    del fondo**. Questo viola il vincolo globale che il piano stesso si dà («ogni nuova compensazione deve
>    avere un gate che la rende no-op quando i dati non confermano»). Il gate riusato è quello delle
>    immobilizzazioni (`scan.attivo_total` vs `decl_total`) e **non dice nulla sui crediti**.
>    → Serve un gate proprio: **applicare il netting crediti solo se la massa è effettivamente localizzata
>    nel passivo**, e altrimenti **no-op** (nessuna scrittura, un warning). Cercarla in tutti i bucket
>    plausibili (`sp16*`, `sp17*`, `sp14`), non solo in `sp16g`.
> 2. **`>=` non garantisce idempotenza.** Il piano afferma «il nuovo codice è idempotente perché i gate
>    `>=` non ri-sottraggono se sp06 non contiene più la massa»: falso — se `sp06` contiene *altri* crediti
>    per un importo ≥ del fondo, la sottrazione si riapplica. Usare un **flag esplicito sul `bs`**
>    (stesso pattern di `_skip_declared_reconcile`, già presente nel repo), non una disuguaglianza.
> 3. Il parametro `netted_immob` della firma proposta è **dichiarato e mai usato**: o serve al gate del
>    punto 1, o va tolto.

**Files:**
- Modify: `importers/situazione_contabile_parser.py:3697-…` (`net_contra_accounts`)
- Test: `tests/test_net_contra_crediti.py` (nuovo)

**Interfaces:**
- Consumes: `ContraScan.sval_crediti`, `ContraScan.fondi_rischi_oneri` (Task 1).
- Produces: `net_contra_accounts(winner_bs, file_path, text, declared)` con la stessa firma; ora riduce
  `sp06*` del fondo crediti, sposta il fondo rischi/oneri in `sp14`, e li sottrae dalla massa debiti.
  Il secondo valore di ritorno `netted_contra` include anche la massa crediti nettata.

- [ ] **Step 1: test che fallisce** — testa il ramo di netting in isolamento tramite un piccolo hook.
Poiché `net_contra_accounts` rilegge il PDF, si estrae la logica di applicazione in una funzione pura
`_apply_contra_to_bs(bs, scan, netted_immob) -> (bs, netted_total)` testabile senza file:

```python
# tests/test_net_contra_crediti.py
from decimal import Decimal as D
from importers.situazione_contabile_parser import _apply_contra_to_bs, ContraScan


def _scan(**kw):
    base = dict(gross_sp02=D("0"), gross_sp03=D("0"), attivo_total=D("0"),
                fondi_immat=D("0"), fondi_mat=D("0"), iva_credito=D("0"),
                iva_debito=D("0"), fondi_att=D("0"), anchor_sp02=None,
                anchor_sp03=None, has_aggregate=False, sval_immat=D("0"),
                sval_mat=D("0"), sval_crediti=D("0"), fondi_rischi_oneri=D("0"))
    base.update(kw)
    return ContraScan(**base)


def test_fondo_crediti_netta_sp06_e_esce_dai_debiti():
    bs = {"sp06_crediti_breve": D("500000"),
          "sp06a_crediti_clienti_breve": D("500000"),
          "sp16_debiti_breve": D("140039"),
          "sp16g_altri_debiti_breve": D("140039"),
          "totale_attivo": D("600000"), "totale_passivo": D("600000")}
    scan = _scan(sval_crediti=D("40039"))
    bs2, netted = _apply_contra_to_bs(bs, scan, D("0"))
    assert bs2["sp06_crediti_breve"] == D("459961")     # 500000 - 40039
    assert bs2["sp16_debiti_breve"] == D("100000")      # 140039 - 40039
    assert netted == D("40039")


def test_fondo_rischi_oneri_va_in_sp14_e_esce_dai_debiti():
    bs = {"sp14_fondi_rischi": D("0"),
          "sp16_debiti_breve": D("1413685.61"),
          "sp16g_altri_debiti_breve": D("1413685.61"),
          "totale_attivo": D("2000000"), "totale_passivo": D("2000000")}
    scan = _scan(fondi_rischi_oneri=D("1413685.61"))
    bs2, netted = _apply_contra_to_bs(bs, scan, D("0"))
    assert bs2["sp14_fondi_rischi"] == D("1413685.61")
    assert bs2["sp16_debiti_breve"] == D("0")
    # la riclassificazione passivo→passivo non cambia il totale: netted crediti = 0 qui
    assert netted == D("0")
```

- [ ] **Step 2: verificare che fallisca**

Run: `python -m pytest tests/test_net_contra_crediti.py -q`
Expected: `ImportError: cannot import name '_apply_contra_to_bs'`

- [ ] **Step 3: implementare** `_apply_contra_to_bs` (modulo-level) e chiamarla da `net_contra_accounts`.

```python
def _apply_contra_to_bs(bs: Dict[str, Decimal], scan, netted_immob: Decimal):
    """Applica al bilancio i contra su crediti e i fondi rischi/oneri già classificati
    in `scan`. netted_immob = massa già nettata su sp02/sp03 dal ramo immobilizzazioni.
    Ritorna (bs, netted_crediti): netted_crediti riduce anche l'ancora dichiarata (i
    crediti lordi erano contati a lordo nel TOTALE ATTIVO). La riclassificazione
    rischi/oneri (passivo→passivo) NON cambia i totali, quindi non entra in netted."""
    bs = dict(bs)
    Z = Decimal('0')
    # (a) fondo svalut./rischi crediti → riduce sp06 e sp06a, ed esce dai debiti
    sc = scan.sval_crediti
    if sc > Z and bs.get('sp06_crediti_breve', Z) >= sc:
        bs['sp06_crediti_breve'] = bs['sp06_crediti_breve'] - sc
        if bs.get('sp06a_crediti_clienti_breve', Z) >= sc:
            bs['sp06a_crediti_clienti_breve'] = bs['sp06a_crediti_clienti_breve'] - sc
        # rimuovi la stessa massa dai debiti dove era finita (altri debiti prima)
        for k_ag, k_de in (('sp16_debiti_breve', 'sp16g_altri_debiti_breve'),):
            if bs.get(k_de, Z) >= sc:
                bs[k_de] = bs[k_de] - sc
                bs[k_ag] = bs.get(k_ag, Z) - sc
            elif bs.get(k_ag, Z) >= sc:
                bs[k_ag] = bs[k_ag] - sc
        netted_crediti = sc
    else:
        netted_crediti = Z
    # (b) fondo rischi e oneri → sp14 (vero passivo), spostato via dai debiti
    ro = scan.fondi_rischi_oneri
    if ro > Z:
        bs['sp14_fondi_rischi'] = bs.get('sp14_fondi_rischi', Z) + ro
        if bs.get('sp16g_altri_debiti_breve', Z) >= ro:
            bs['sp16g_altri_debiti_breve'] = bs['sp16g_altri_debiti_breve'] - ro
            bs['sp16_debiti_breve'] = bs.get('sp16_debiti_breve', Z) - ro
        elif bs.get('sp16_debiti_breve', Z) >= ro:
            bs['sp16_debiti_breve'] = bs['sp16_debiti_breve'] - ro
    return bs, netted_crediti
```

In `net_contra_accounts`, DOPO l'applicazione del netting immobilizzazioni (dove `netted` fondi/IVA è già
calcolato e sp02/sp03 sovrascritti), aggiungere:

```python
        winner_bs, netted_crediti = _apply_contra_to_bs(winner_bs, scan, netted)
        netted = netted + netted_crediti
```

Aggiornare il gate di riconciliazione: la massa crediti nettata riduce il `decl_total` atteso allo stesso
modo dei fondi immobilizzazioni (i crediti lordi erano nel TOTALE ATTIVO). L'implementatore verifica che il
`decl_total` usato per il gate 2 tenga conto di `sval_crediti` (sottrarlo dall'ancora come già fatto per i
fondi), così il gate resta coerente.

- [ ] **Step 4: verificare + regressione mirata**

Run: `python -m pytest tests/test_net_contra_crediti.py -q` → PASS.

```bash
python tests/_import_probe.py "Test/errori/budget_169_spectra.pdf" standard
python tests/_import_probe.py "Test/errori/budget_338_Pandoro srl Bilancino 2025.pdf" standard
python tests/_import_probe.py "Test/prova_tets/budget_646_AIC SRL al 31.05.2026 - non completa.pdf" standard
```
Expected: 169 e 338 → `ok=true`, `masked=false`, sbilancio 0 (residuo 40.039,24 / 96.563,98 azzerato).
646 → residuo (12,8%) crolla drasticamente: se ≤ 20% importa flaggato (con Piano 02), altrimenti almeno
il residuo scende sotto 1% e importa pulito.

- [ ] **Step 5: regressione anti-doppio-netting** su file già corretti:

```bash
python tests/_import_probe.py "Test/errori/budget_309_BILANCIO.pdf" standard     # nettava già bene
python tests/_prod_route_c_runner.py "Test/sez-contrapposte/budget_343_Bilancio 2025 ver_definitiva 1-6-2026.pdf"
```
Expected: 309 total_assets INVARIATO (il fondo rischi crediti 6.480 era già nettato → il nuovo codice è
idempotente perché i gate `>=` non ri-sottraggono se sp06 non contiene più la massa); 343 `quadra=True`
invariato.

- [ ] **Step 6: Commit**

```bash
git add importers/situazione_contabile_parser.py tests/test_net_contra_crediti.py
git commit -m "fix(netting): netta il fondo svalut./rischi crediti su sp06 e classifica il fondo rischi e oneri su sp14 — via dai debiti"
```

---

### Task 3: fondi ammortamento come conti singoli senza sotto-totale (budget_281)

> **MISURATO 2026-07-27 — il task è confermato, ma la diagnosi va precisata.**
>
> Una revisione indipendente ha sostenuto che il problema di 281 sia a monte: «il parser assegna tutte le
> righe all'Attivo perché presuppone colonne Attivo/Passivo affiancate, mentre il documento usa sezioni
> sequenziali». **Metà vero.** Il layout **è** sequenziale — verificato: colonna unica, pagina 1
> `** A T T I V I T A'`, pagina 2 `** P A S S I V I T A'`, lato dato dalle colonne SALDO DARE (x≈280) /
> SALDO AVERE (x≈340), nessun affiancamento. Ma il parser **non** sbaglia il lato. Eseguito
> `python tests/_prod_route_c_runner.py "Test/errori/budget_281_MSIT-31 3 2026.pdf"`:
>
> ```
> totale_attivo = 1.816.100,59     (dichiarato 1.833.868,69  → gap 0,97%)
> sp13 result   = 48.207,96        (= "**** UTILE DI ESERCIZIO 48.207,96" stampato, esatto)
> contra netted = 0.00             ← IL DIFETTO
> plug residual = 17.768,10
> ```
>
> Le sezioni sono lette bene e il risultato è esatto. Quello che non scatta è il **contra-scan**:
> `net_contra_accounts` netta **zero**. Quindi il Task resta com'è formulato (far entrare nello scan i
> fondi ammortamento esposti come conti singoli senza riga di sotto-totale) e **non** serve riscrivere
> l'acquisizione.
>
> Due note per chi implementa:
> - il **gap dello 0,97%** e il `plug residual` di 17.768,10 sono un problema **diverso** dal netting e non
>   vanno confusi: sono conti non classificati (materia del Piano 05 spazio `conto`);
> - la misura sopra viene dalla **replica deterministica**. In produzione con la chiave gira prima la
>   CoGe-LLM e poi la selezione per completezza: **rifare la misura con `tests/_import_probe.py` quando i
>   crediti tornano**, perché il candidato scelto può essere un altro.
>
> ⚠️ Lo Step 2 del task originale allentava il gate anchor del netting («consentire il netting anche senza
> anchor quando i fondi leaf sono da text-layer»). Quel gate è documentato come protezione deliberata
> ("never write a wrong net immobilizzazioni"): allentarlo è una **scelta di rischio**, non un bugfix. Se
> serve, va motivata contabilmente e accompagnata da un'auto-validazione propria (il netto ricostruito
> riconcilia col totale dichiarato entro tolleranza), non solo dall'assenza di `from_ocr`.

**Files:**
- Modify: `importers/situazione_contabile_parser.py` — `_contra_rows` / `_dedup_parent_child` (riga 3413)
- Test: `tests/test_contra_single_accounts.py` (nuovo)

**Contesto:** budget_309 netta perché espone i sotto-totali `07/**/*** F/AMM IMMOB. MATERIALI`; budget_281
elenca i singoli conti `07/xx F/AMM ...` SENZA la riga aggregata → lo scan non li somma. `_contra_classify`
già somma i fondi da righe leaf, quindi la lacuna è a monte in `_contra_rows` (che raccoglie le righe) o
in `_dedup_parent_child` (che può scartare i leaf quando manca il parent). Verificare quale dei due perde
i conti singoli e correggere in modo che i fondi ammortamento leaf siano SEMPRE inclusi nello scan.

**Interfaces:**
- Consumes: output di `_contra_rows`. Produces: nessuna nuova firma; il fix è interno.

- [ ] **Step 1: test che fallisce** — su `_contra_classify` con leaf singoli senza parent:

```python
# tests/test_contra_single_accounts.py
from decimal import Decimal as D
from importers.situazione_contabile_parser import _contra_classify


def test_fondi_amm_leaf_singoli_senza_sottototale():
    # budget_281: F/AMM per singolo cespite, nessuna riga aggregata 07/**/***
    passivo = [
        ("070105", "F/AMM MACCHINARI", D("68541.79")),
        ("070110", "F/AMM ATTREZZATURE", D("12000.00")),
        ("070115", "F/AMM AUTOCARRI", D("44394.00")),
    ]
    attivo = [
        ("020105", "MACCHINARI", D("69255.80")),
        ("020110", "ATTREZZATURE", D("24761.82")),
        ("020115", "AUTOCARRI", D("92942.99")),
    ]
    scan = _contra_classify(attivo, passivo)
    assert scan.fondi_mat == D("124935.79")     # 68541.79 + 12000 + 44394
```

- [ ] **Step 2: verificare esito** (potrebbe già passare se `_contra_classify` somma i leaf):

Run: `python -m pytest tests/test_contra_single_accounts.py -q`
Se PASSA già: il difetto di 281 è a valle (il gate 2 di `net_contra_accounts` fallisce perché
`scan.attivo_total` non riconcilia, o manca l'anchor). In tal caso spostare il fix sul ramo ANCHORED di
`net_contra_accounts` (righe 3744-3781): consentire il netting anche senza anchor quando i fondi leaf sono
letti da TEXT-LAYER (`from_ocr=False`) e la loro somma sta sotto il gross attivo lato immobilizzazioni.
Se FALLISCE: procedere allo Step 3.

- [ ] **Step 3: correggere** il punto individuato (documentare nel commit QUALE era). Criterio: i fondi
ammortamento leaf singoli devono contribuire a `fondi_mat`/`fondi_immat` indipendentemente dalla presenza
della riga di sotto-totale, e `net_contra_accounts` deve poterli nettare quando la sorgente è text-layer
(capture affidabile) anche in assenza di anchor esplicito, purché `fondi_mat <= gross_sp03`.

- [ ] **Step 4: verificare**

```bash
python tests/_import_probe.py "Test/errori/budget_281_MSIT-31 3 2026.pdf" standard
```
Expected: `sp03_immob_materiali` NETTO (~72.905, non 194.896); `sp16_debiti_breve` ~714.000 (non gonfiato
di ~200k); residuo del fondo rischi crediti 17.768 nettato da sp06 (Task 2). `ok=true`, masked=false.

Regressione: budget_309 total_assets invariato (`python tests/_import_probe.py "Test/errori/budget_309_BILANCIO.pdf" standard`).

- [ ] **Step 5: Commit**

```bash
git add importers/situazione_contabile_parser.py tests/test_contra_single_accounts.py
git commit -m "fix(netting): fondi ammortamento come conti singoli senza sotto-totale ora nettati (budget_281)"
```

---

## Accettazione del piano

- 169, 338, 281: `ok=true`, `masked=false`, sbilancio 0, composizione patrimoniale NETTA corretta.
- 646: residuo crolla; importa (flaggato o pulito).
- 309, 343, 348, 337: totali INVARIATI (netting idempotente, nessun doppio netting).
- Campione pulito §6: invariato.

## Note per i file non risolti da questo piano
- **405** (dotted interlacciato lordo) e **703** (layout 1/10/005, header "Attività/Passività") hanno un
  problema di LETTURA del layout a monte del netting: il parser non estrae bene le righe. Il netting
  esteso li migliora ma la copertura piena dipende dal Piano 04 (riconoscimento layout) + Piano 05
  (etichette). Documentare il residuo che resta dopo questo piano.
- **623** (perdita sul lato attivo): il netting è coperto qui, ma la derivazione della PERDITA dal gap
  Attivo/Passivo è nel Piano 02 (`_force_balance_trial` usa `dc['perdita']`). Verificare che i due piani
  insieme lo importino.
