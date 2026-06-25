# Sistema di importazione bilanci — motore IV-CEE e quadratura

> Specifica del motore condiviso e della quadratura (sessioni 2026-06-15 → 2026-06-25).
> Complementare a [`IMPORT-ROUTING-TAXONOMY.md`](IMPORT-ROUTING-TAXONOMY.md) (il routing nelle 4 rotte)
> e a [`IMPORT-BALANCING-SCHEME.md`](IMPORT-BALANCING-SCHEME.md) (lo schema di quadratura L0→L5).
> Note granulari per-parser nel `CLAUDE.md` (sezione *PDF Import*).
> Obiettivo: gestire la quadratura **per ogni bilancio**, in modo generale, non con patch per-file.

---

## 1. Principio architetturale

```
              ┌─────────────────────── ROUTER (bilancio_classifier) ───────────────────────┐
  file  ─────▶│  A sintetico IV-CEE   B dettaglio IV-CEE   C contrapposte   OTHER (XBRL/…)  │
              └───────┬──────────────────────┬───────────────────┬───────────────┬─────────┘
                      │ LLM IV-CEE           │ LLM IV-CEE         │ deterministico│ parser XBRL
                      ▼                      ▼                    ▼ (situazione    ▼ nativo
                   bs/ce                  bs/ce               contabile)
                      └──────────────┬──────────────────────────┘
                                     ▼
                ┌──────── MOTORE IV-CEE (iv_cee_hierarchy) — STADIO CONDIVISO ────────┐
                │  leveling per livello di legge  +  check_quadratura  +  anti-masking │
                └──────────────────────────────────────────────────────────────────────┘
```

**Le 4 macro-aree restano SEPARATE** (ognuna col suo estrattore). Il motore IV-CEE **non è un
router**: è lo **stadio condiviso a valle** dove ogni route, dopo aver estratto le voci *a modo
suo*, le fa passare per la **stessa** classificazione di legge e lo **stesso** controllo di
quadratura. Una sola tassonomia, una sola quadratura, quattro estrattori distinti.

---

## 2. Componenti nuovi

### 2.1 Albero canonico IV-CEE — `data/iv_cee_tree.json`
Struttura di legge (art. 2424 / 2425 c.c.) come albero. Ogni nodo:

| campo | significato |
|---|---|
| `path` | percorso di legge (`B.II`, `C.II.1`, `PD.7`, `A.1`…) |
| `level` | 1 = lettere A/B/C/D · 2 = romani I/II/III · 3 = arabi 1..n · 4 = lettere a/b/c (+bis/ter) |
| `side` | `attivo`/`passivo` (solo SP; disambigua A/B/C/D che sui due lati significano cose diverse) |
| `db_field` | foglia legale → campo DB (`sp01`–`sp18`, `ce01`–`ce20`) |
| `is_legal_leaf` | la voce mappa a un campo DB (è qui che si quadra) |
| `is_total` | nodo-totale di sezione (per riconciliazione, NON sommato per evitare doppi conteggi) |
| `netting` | fondi amm.to/sval. → si nettano dall'attivo lordo |
| `aliases` | sinonimi normalizzati per il match descrizione |

Copre **tutti** i 18 SP + 20 CE. È **volutamente solo livello di legge**: NON contiene alias di
sotto-conti (es. "TERRENI E FABBRICATI"), perché in modalità *flat* (A/B) ciò causerebbe doppio
conteggio. I sotto-conti li gestisce la discesa gerarchica nel ramo C.

### 2.2 Motore — `importers/iv_cee_hierarchy.py`
- `load_tree()` — carica `data/iv_cee_tree.json` e costruisce l'indice degli alias.
- `normalize(text)` — unicode-normalize, lowercase, accenti rimossi, punteggiatura→spazio.
- `resolve(desc, side=None, statement=None) -> Optional[Node]` — **classificatore condiviso**
  descrizione→nodo IV-CEE. Prudente: ritorna `None` se incerto (così la discesa gerarchica scende
  nei figli invece di misroutare). Match: alias esatto → alias più lungo contenuto.
  **NON** usarlo per ribaltare il LATO attivo/passivo di una riga di verifica: la **colonna è verità**
  (provato e revertito, vedi §5).
- `classify_for_reclassify(desc, side=None) -> (Optional[str], bool)` — adattatore `(db_field, specific)`
  per `situazione_contabile_parser._be_reclassify`.
- `aggregate_flat(items) -> AggResult` — aggrega voci già a livello di legge (aree A/B/XBRL): somma le
  foglie, salta i nodi-totale (anti doppio-conteggio), applica la scadenza entro/oltre a crediti/debiti.
- `check_quadratura(bs, ce=None, tol=Decimal("0.01")) -> Quadratura` — il controllo unico (vedi §3).
- `reconcile_ivcee_balance(bs, declared=None, label="", cap_frac=Decimal("0.05")) -> bs` — **route A/B**:
  ancora al `TOTALE ATTIVO` dichiarato e tampona il piccolo lato corto (sp09 se attivo corto, sp16 se
  passivo corto). Se il gap supera `cap_frac` (5%) → lascia intatto e fallisce onestamente (errore
  strutturale, non si maschera). Espone `_plug_residual`.
- `enforce_ce_sp_identity(bs, ce, label="", tol=None, prefer="sp13", declared=None) -> bs` — **tutte le
  rotte**: forza `utile_CE == sp13` (vedi `IMPORT-BALANCING-SCHEME.md` L2-bis per la logica dell'arbitro).

### 2.3 Harness di misura — `Test/_quadratura_harness.py`
Misura il **tasso di quadratura** sul corpus. Scansione **ricorsiva** + **dedup per hash** di
contenuto. Per default solo route deterministiche (gratis); `--llm` include le aree A/B.
```
python Test/_quadratura_harness.py Test          # tutto il corpus, deterministiche
python Test/_quadratura_harness.py Test --llm     # include A/B (chiamate LLM)
python Test/_quadratura_harness.py Test/june_sample
```
Colonne: `area | route | mode | quadra(SI/NO/MASK) | plug | note`.

---

## 3. Quadratura e anti-masking (il cuore)

`check_quadratura(bs, ce=None, tol=Decimal("0.01"))` verifica:
1. **Attivo == Passivo** (±`tol`) sui 18 aggregati SP.
2. **Utile CE == sp13** — cross-check che `validate_balance` NON faceva.
3. **Anti-masking**: legge `bs['_plug_residual']` (la massa NON classificata che il best-effort
   tampona in sp09/sp16). Se il plug supera `_MASK_PCT` = **1% del totale** → `masked=True`: il
   bilancio "quadra" solo per costruzione, la composizione è inaffidabile.
4. **Vuoto**: `totale_attivo ~ 0` → `is_empty=True`. Un'estrazione vuota è un **FALLIMENTO**, non un
   pass (senza questo, att==pas==0 darebbe sbilancio 0 → falso "quadra", che nascondeva le estrazioni
   vuote dei contrapposte misroutati).

`quadra` richiede `not is_empty and not masked` (oltre ad attivo==passivo). Ritorna la NamedTuple:

```python
class Quadratura(NamedTuple):
    totale_attivo: Decimal
    totale_passivo: Decimal
    sbilancio: Decimal          # attivo - passivo
    quadra: bool
    utile_ce: Optional[Decimal]
    sp13: Decimal
    utile_match: bool
    plug_residual: Decimal      # massa non classificata tamponata in sp09/sp16
    masked: bool                # quadra solo grazie al plug (composizione errata)
    is_empty: bool              # totale attivo ~ 0 → NON quadra
    warnings: List[str]
```

**Perché serviva**: il parser best-effort contrapposte impone `totale_attivo == totale_passivo`
per costruzione e assorbe il residuo in sp09/sp16. Quindi sia `validate_balance` sia un controllo
ingenuo "attivo==passivo" venivano **ingannati**. Esporre `_plug_residual` rende la quadratura
**onesta per tutti i file area-C in un colpo**, non file per file.

---

## 4. Modifiche ai file esistenti

| File | Modifica | Perché |
|---|---|---|
| `importers/situazione_contabile_parser.py` | `extract_contrapposte_best_effort` espone `bs['_plug_residual']` (sopravvive a `_map_sc_keys`, ignorato dal BS builder) | rendere visibile il tampone |
| `importers/situazione_contabile_parser.py` | **`_be_split`** sceglie il gutter che **bilancia le righe con descrizione su entrambi i lati** (centro come spareggio), non il gap più largo | il gap più largo tagliava la colonna passivo → masking (343/348/405) |
| `importers/pdf_importer.py` | **gate anti-masking** `SC_PLUG_REJECT_PCT = 0.20`: best-effort con plug > 20% del totale → rifiuta e fallback LLM/onesto; sotto → import con flag `BILANCIO NON QUADRATO` per Rettifiche | rifiutare la spazzatura, preservare il workflow Rettifiche |
| `importers/pdf_importer.py` | `check_quadratura` come **diagnostica unificata** dopo `validate_balance` (tutte le route): aggiunge il cross-check utile==sp13 + masking, loggato (non-bloccante) | un solo giudice di quadratura per tutte le route |
| `importers/pdf_extractor_llm.py` | `SP_END_KEYWORDS` riconosce le varianti di "Totale passivo" ("totale stato patrimoniale passivo", "…e patrimonio netto", …) | il passivo veniva escluso dalla finestra LLM (es. 352) |
| `importers/pdf_extractor_llm.py` | guardia **sezione iniziale azzerata** non-mascherante: rilloca la finestra SP/CE solo se esiste una **vera seconda copia con header** IV-CEE; i blocchi di soli numeri (es. 355) falliscono onestamente | provvisori con copia template a zero in testa |

---

## 5. Learnings (decisioni prese e scartate)

- **TENUTI** i fix di categoria in `pdf_extractor_llm.py` (varianti "Totale passivo", guardia
  sezione-azzerata): sono generali, non patch su singolo file.
- **352/355 come casi singoli: lasciati stare** (richiesta utente). 352 migliora molto col fix
  SP_END (pareggia in single-year); 355 ha i valori reali in colonne di soli numeri (richiede
  estrazione per-coordinate dedicata) → resta fallimento onesto.
- **PROVATO E REVERTITO — tree-classify in `_be_reclassify` per togliere il default "sconosciuto
  → sp16"**: concettualmente **sbagliato**. La **COLONNA** (attivo/passivo) è la verità sul lato;
  far sovrascrivere la colonna dalla descrizione dell'albero rompe i conti **ambigui**
  (`ERARIO C/`, `DEPOSITI BANCARI` = scoperto di c/c, `FORNITORI C/ANTICIPI`, `INAIL C/`,
  `FONDI AMM.TO`), che cambiano lato in base alla colonna, non alla descrizione → ha regredito un
  file pulito (375 SI→MASK). **Non ritentare.** Il default-sp16 fa danno solo quando la colonna è
  già sbagliata (bug `_be_split`), che è la vera causa radice.

---

## 6. Risultati misurati (baseline onesta)

**Deterministiche, tutto il corpus `Test/` (127 file unici):** quadrano 14/26 testate; i restanti
sono mascherati (best-effort plug, ora **visibili** e non più silenziosi) o falliscono onestamente.

I file mascherati avevano **plug enormi** (22–72% del totale): 405 = 57%, 343 = 62%, 342 = 72%,
395 = 22%, BILANCIO-TEST = 34%. Non erano "quadrati": importavano col tampone. Il gate al 20% ora
li rifiuta (→ LLM/onesto) o, per plug minori, li importa con flag Rettifiche.

> Il run completo con `--llm` (aree A/B) misura il resto del corpus; i numeri vanno aggiornati qui
> quando disponibili. `python Test/_quadratura_harness.py Test --llm`.

> **CAVEAT — l'harness è PESSIMISTA, non confonderlo con "importa?".** L'harness esegue
> `extract → check_quadratura` ma NON le due fasi di produzione che `pdf_importer` esegue subito dopo:
> `reconcile_ivcee_balance` (ancora al Totale attivo dichiarato, tampona il piccolo arrotondamento →
> flag Rettifiche) e `enforce_ce_sp_identity`. Quindi un "NO" dell'harness NON è "non importa": molti
> file A/B segnati NO **importano** in app (es. budget_152/254/289/336). L'harness è autorevole solo
> per il **masking** (plug > 1% su route C). Inoltre l'estrazione A/B è **non deterministica** (rumore
> LLM): SI/NO può oscillare tra run sullo stesso file. Per rispondere a "questo PDF importa?" gira il
> percorso completo di produzione (`extract → reconcile_ivcee_balance → enforce_ce_sp_identity →
> validate_balance`), non un singolo run dell'harness.

---

## 7. Aperto / da fare

- **Layout-fix profondi** per i mascherati residui: 405 (gross/fondi *interleaved*, non un semplice
  2-colonne), 395 (DEPI contrapposte → parser dedicato invece del best-effort generico),
  343/348 (residuo dopo il fix `_be_split`).
- **355-class** (schema IV-CEE azzerato + valori reali in colonne di soli numeri) → estrazione
  per-coordinate dedicata.
- Estendere la baseline ad A/B (`--llm`) e consolidare i numeri in §6.
- Valutare se gli **XBRL nativi** vanno inclusi nell'harness (oggi rotta deterministica a parte).

---

## 8. Parametri configurabili

| Parametro | File | Default | Effetto |
|---|---|---|---|
| `SC_PLUG_REJECT_PCT` | `importers/pdf_importer.py` | `Decimal("0.20")` | scala la severità del warning `BILANCIO NON QUADRATO`: sopra il 20% → "prevalentemente stimata", sotto → "parziale" |
| `_MASK_PCT` | `importers/iv_cee_hierarchy.py` | `Decimal("0.01")` | soglia diagnostica `masked` in `check_quadratura` (1% del totale attivo) |
| `_COGE_SP_MAX_ATTEMPTS` | `importers/pdf_extractor_llm.py` | `3` | ritentativi del pass SP CoGe per completezza (tiene il `_plug_residual` minore) |
| `_COGE_SP_CLEAN_PCT` | `importers/pdf_extractor_llm.py` | `Decimal("0.02")` | residuo < 2% del totale → "abbastanza pulito", stop anticipato dei ritentativi |
| `cap_frac` (`reconcile_ivcee_balance`) | `importers/iv_cee_hierarchy.py` | `Decimal("0.05")` | gap > 5% del totale → non si tampona, errore onesto |

> **Nota import vs harness:** `validate_balance` (`pdf_mapper`) è il gate hard prima della scrittura DB;
> controlla (1) `totale_attivo != 0`, (2) `|attivo − passivo| ≤ €1`, (3) gli aggregati sp01–10 e
> sp11–18 ricostruiscono i totali dichiarati (±€1). `check_quadratura` è invece la **diagnostica
> unificata** (non bloccante) loggata per tutte le rotte. Una "NO" dell'harness NON significa "non
> importa": vedi il CAVEAT in §6 e in `IMPORT-BALANCING-SCHEME.md`.
