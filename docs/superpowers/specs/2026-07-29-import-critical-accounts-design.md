# Design — Conti critici, netting corretto e affidabilità dell'import

**Data:** 2026-07-29 · **Stato:** approvato in brainstorming, da implementare
**Audit di riferimento:** `docs/piano-import-2026-07/14-AUDIT-CLASSIFICAZIONE-E-NETTING-2026-07-27.md`
**Schema concettuale:** `docs/import/SCHEMA-RICONOSCIMENTO-CLASSIFICAZIONE-NETTING.md`

---

## 1. Problema

Un import può **quadrare ed essere falso**. Il caso misurato è `613_2024`: 2,25 M di fondi
ammortamento restano iscritti fra i debiti, l'attivo resta lordo (4,98 M invece di 3,13 M), il
file passa tutti i gate, viene salvato come `verified` e alimenta il previsionale. Nessun
warning raggiunge l'utente.

Tre cause distinte, tutte verificate sperimentalmente:

1. **Il netting non avviene** perché la deduplicazione padre/figlio usa i prefissi di codice
   (`c.startswith(code)`), mentre AGO usa due famiglie disgiunte — mastri a 8 cifre
   (`13095000`) e dettagli a 9 cifre (`101080000`). Mastro e dettaglio vengono sommati
   entrambi: l'attivo scansionato sfora dello 0,836 %, il gate di riconciliazione cade, la
   modalità *anchored* non è disponibile (nessun subtotale immobilizzazioni stampato) e
   `net_contra_accounts` restituisce `netted = 0`.
2. **La classificazione ha due sistemi paralleli** che si ignorano a vicenda:
   `resolve()` conosce `AMMORTAMENTI → ce09` ma non `COSTI PERSONALE DIPENDENTE`;
   `_classify_ce_costi` il contrario. Il rescue gerarchico usa solo il secondo, quindi su
   budget_342 perde 36.500,17 di ammortamenti dentro `ce12` e sbaglia l'EBITDA.
3. **Un errore su un conto critico non ha conseguenze visibili.** `forecastable` dipende solo
   da `semantic_valid`, che non sa nulla di contro-conti non applicati.

## 2. Obiettivo e non-obiettivi

**Obiettivo.** Un import "decente": corretto sui conti che decidono i KPI, approssimativo dove
non conta, e **onesto su quale delle due cose è successa**. Metrica: l'utente deve poter portare
un file a `semantic_valid` con **≤ 10 rettifiche** (il limite tecnico è
`RETTIFICHE_LOG_MAX = 20`).

**Non-obiettivi di questa spec:**
- interfaccia utente (pannelli KPI "non affidabile", rettifiche pre-compilate) → spec successiva;
- assegnazione anno/colonna su route B e sezione C-vs-D → **spec 2**, fixture
  `tests/debug/Bilancio_Riclassificato DEF.pdf`;
- metrica di "decenza" sul corpus;
- modifiche allo schema del database.

## 3. Il modello del raggio d'impatto

La classificazione va valutata per **conseguenze**, non per precisione.

| Classe | Effetto | Esempio | Ammessa? |
|---|---|---|---|
| **1 — cambia un TOTALE** | gonfia due lati insieme | fondo ammortamento fra i debiti | **mai** |
| **2 — attraversa un confine di KPI** | totale giusto, indicatore sbagliato | `AMMORTAMENTI → ce12` (EBITDA) | solo sotto `M` |
| **3 — dentro lo stesso aggregato** | nessun effetto sui KPI | `ce06` invece di `ce12` | **sì** |

I confini reali, da `calculations/ce_result.py`:

```
Costi della produzione = ce05+ce06+ce07+ce08+ce09+ce10+ce11+ce11b+ce12
EBIT                   = Valore della produzione − Costi della produzione
EBITDA                 = EBIT + ce09        ← unico confine dentro i costi operativi
Gestione finanziaria   = ce13+ce14−ce15+ce16
```

### 3.1 Tier di criticità

| Tier | Conti | Fallback |
|---|---|---|
| **0 — critici** | `sp02`/`sp03`/`sp04` netti · `sp11` + `sp12*` (+`sp13`) · `sp16a`/`sp17a` banche | **vietato** |
| **1 — confine KPI** | `ce09`, `ce15`, split entro/oltre (`sp16` vs `sp17`) | solo ≤ `M` |
| **2 — libero** | `ce05/06/07/08/11/12`, `sp16d…g`, `sp06a…g` | sì |

**Soglia di materialità:** `M = max(1.000 €; 0,1 % del totale attivo)`.

### 3.2 Plug contro fallback

| Operazione | Ammessa |
|---|---|
| Creare massa inesistente per far quadrare | **no** — falsifica i totali |
| Etichettare massa **letta ma non riconosciuta** in un bucket generico | **sì** |
| Assorbire uno scarto ≤ `M` per far combaciare utile CE e `sp13` | **sì**, con flag |
| Assorbire uno scarto > `M` allo stesso modo | **no** — è massa mancante |

Un plug **inventa** massa; un fallback **etichetta** massa che c'è già. La documentazione
attuale le tratta come la stessa cosa, ed è per questo che oggi il sistema preferisce fallire
piuttosto che etichettare.

## 4. Architettura

```
route C:  net_contra_accounts ─┐
debt typing / base_bank_debt ──┼─→ metadati `_contra_*`, `_bank_*`, `_pn_*` nel dict bs
totali dichiarati + controlli ─┘
                                        │
                    reliability.assess(bs, ce, declared) → ReliabilityReport
                                        │
        ┌───────────────────────────────┴──────────────────────────┐
   forecastable = semantic_valid AND report.all_critical_ok    validation_report
   validation_status idem                                      ["critical_accounts"]
```

| Componente | Responsabilità |
|---|---|
| **`importers/reliability.py`** (nuovo) | `assess()`, `ReliabilityReport`, `AccountStatus`. Funzione pura: dict in, verdetto out. Nessun I/O |
| `situazione_contabile_parser` (modificato) | dedup senza prefissi; `net_contra_accounts` registra *perché* ha fatto no-op |
| `_classify_*` (modificato) | catena di fallback verso `resolve()` |
| **`fallback_bucket()`** (nuovo) | unico punto in cui si applica la politica del §3 |
| `pdf_importer` (modificato) | chiama `assess()`, piega il risultato in `forecastable`, lo espone in `validation_report` |
| `iv_cee_hierarchy.check_quadratura` | **invariato** |

**Convenzione metadati:** chiavi con underscore nel dict `bs` (`_contra_detected`,
`_contra_applied`, `_contra_reason`), come le esistenti `_plug_residual`, `_netted_contra`,
`_ce_sp_difference` — già sopravvivono a `_map_sc_keys` e sono già rimosse prima della scrittura ORM.

**Non si toccano:** `validate_balance`, la decisione salva/rifiuta, lo schema DB.

## 5. Componenti in dettaglio

### 5.1 Dedup senza prefissi di codice

Il totale dichiarato diventa l'autorità; le strategie di dedup sono solo **partizioni candidate**.

```
candidati = [
  tutte_le_righe,                      # comportamento attuale
  scarta_padri_per_importo,            # stesso importo + descrizione compatibile, stesso lato
  scarta_padri_per_profondita_codice,  # codice più corto = livello; i figli sommano al padre ±max(2€,1%)
  combinato,
]
vince il candidato la cui somma attivo riconcilia al TOTALE ATTIVO dichiarato
  entro max(50 €; 0,5 %);  a parità → quello che scarta meno righe
nessuno riconcilia → si tiene `tutte_le_righe` E si marca immobilizzazioni UNRELIABLE
```

La profondità del codice è usata **solo** come indizio di gerarchia, mai per la semantica, ed è
comunque sovrascritta dal gate sul dichiarato: il divieto "mai classificare per prefisso di
codice" resta intatto.

L'ultima riga è la parte importante: quando nessuna partizione riconcilia, il fallimento diventa
**visibile** invece che un no-op silenzioso.

### 5.2 Catena di classificazione

```python
field = _classify_ce_costi(desc) or _resolve_field(desc, side) or fallback_bucket(...)
```

dove `_resolve_field(desc, side)` è un adattatore sottile — nuovo, in
`situazione_contabile_parser` — che chiama `iv_cee_hierarchy.resolve(desc, side)` e ne
restituisce `node.db_field` tradotto nella **chiave corta** usata dai parser di route C
(`ce09`, `sp16`, …), oppure `None`. Serve perché `resolve()` ragiona in nomi di colonna DB
mentre route C lavora in chiavi corte fino a `_map_sc_keys`.

Puramente additiva: interviene solo dove oggi il risultato è `None`.

### 5.3 `fallback_bucket()`

```python
fallback_bucket(desc, side, statement, amount, total) -> (field, severity)
    target di tier 0  -> solleva ValueError (i chiamanti non devono arrivarci)
    amount <= M       -> (campo generico, 'silent')
    amount >  M       -> (campo generico, 'recorded')   # accodato a _unclassified
```

Campi generici: `ce06` costi per servizi · `ce12` oneri diversi · `sp16g` altri debiti ·
`sp06g` altri crediti.

**Sempre un sotto-campo esplicito, mai un residuo di aggregato**: `projection_common.base_bank_debt`
assegna **alle banche** qualunque scarto fra `sp16_debiti_breve` e la somma dei suoi sotto-campi,
quindi un fallback lasciato nell'aggregato diventerebbe debito bancario fantasma — una
corruzione di tier 0 dalla porta di servizio.

### 5.4 `reliability.assess()`

```python
class AccountStatus(Enum):
    VERIFIED    # corroborato da evidenza indipendente della fonte
    DERIVED     # calcolato/inferito ma internamente coerente
    UNRELIABLE  # l'evidenza dice che il valore è probabilmente sbagliato

@dataclass(frozen=True)
class ReliabilityReport:
    immobilizzazioni: AccountStatus;  immobilizzazioni_reason: str
    patrimonio_netto: AccountStatus;  patrimonio_netto_reason: str
    debiti_banche:    AccountStatus;  debiti_banche_reason:    str
    unclassified_mass: Decimal
    @property
    def all_critical_ok(self) -> bool   # nessun conto è UNRELIABLE
```

| Conto | VERIFIED | DERIVED | UNRELIABLE |
|---|---|---|---|
| Immobilizzazioni | scan contro riconciliato **e applicato** | nessuna massa contro trovata (documento già netto) | **massa contro rilevata e non applicata** ← 613 |
| Patrimonio netto | `sp11+Σsp12*+sp13` riconcilia col "Totale patrimonio netto" stampato | nessun controllo stampato, internamente coerente | controllo stampato presente e in disaccordo > `M` |
| Debiti banche | letti da righe sorgente `sp16a`/`sp17a` esplicite | debito bancario nullo e nessuno scarto | dedotti da uno scarto aggregato/dettaglio > `M` |

`DERIVED` **non blocca**: altrimenti ogni bilancio abbreviato resterebbe fuori.

**Assenza di evidenza ≠ evidenza di errore.** `UNRELIABLE` richiede un segnale **positivo** di
contraddizione, mai la semplice mancanza di un controllo. In particolare:

- un file di **route A/B non esegue alcuno scan contro-conti**: `immobilizzazioni` è `DERIVED`
  (lo schema di legge espone già i valori netti), **mai** `UNRELIABLE`;
- un documento senza "Totale patrimonio netto" stampato dà `patrimonio_netto = DERIVED`;
- `debiti_banche = DERIVED` quando non c'è né esposizione bancaria né scarto.

Senza questa regola l'intera route B verrebbe bloccata da una diagnostica pensata per la route C.

### 5.5 Gating

```python
forecastable      = _qd.semantic_valid and reliability.all_critical_ok
validation_status = "verified" if (semantic_valid and all_critical_ok) else "review_required"
validation_report["critical_accounts"] = {...}   # status + reason per conto
```

`quadra` e la decisione salva/rifiuta restano invariati: **un file inaffidabile si salva
comunque**, altrimenti le Rettifiche non potrebbero raggiungerlo (operano su un
`FinancialYear` già persistito).

## 6. Gestione degli errori

- `assess()` è pura e totale: non fa I/O, quindi non cattura nulla.
- Il **call site** la avvolge: qualunque eccezione → log + trattata come "sconosciuto, non
  bloccante". La valutazione di affidabilità non deve mai trasformare un import funzionante in
  un fallimento. Stessa postura difensiva del `try/except → no-op` già presente in
  `net_contra_accounts`.

## 7. Compatibilità

- **Nessuna migrazione DB**: `validation_report` è una colonna JSON esistente.
- **I record esistenti non vengono rivalutati.** Il loro `forecastable` resta com'è; la nuova
  regola vale solo su import/re-import. Ribaltare in silenzio anni già salvati romperebbe i
  budget costruiti su di essi.
- Chi legge tratta una chiave `critical_accounts` **assente** come "sconosciuto, non bloccante".
- **Atteso un calo reale di `verified` sui re-import.** File come 613, che oggi passano,
  diventeranno `review_required`. È l'effetto voluto, ma va **quantificato sul corpus prima e
  dopo**, non subìto.

## 8. Test

| Livello | Test | Accettazione |
|---|---|---|
| Dedup | `test_contra_netting.py::test_contra_rows_on_613_finds_the_fondi_mass` (correggere lo spacchettamento 2→3) | fondi **1.853.799,20**; `scan.attivo_total` **4.979.885,27** |
| Netting e2e | `test_contra_netting.py::test_613_production_path_with_stubbed_gross_llm` | `netted > 1.800.000`; `sp03 ≈ 3,08 M`; debiti < 400 k; `totale_attivo ≈ 3,13 M` |
| Classificazione | nuovo, budget_342 | `ce09 = 36.500,17`; `ce12 ≈ 7.036,26`; EBITDA corretto |
| Politica | nuovo, `fallback_bucket` | rifiuta i target di tier 0; `silent` ≤ `M`, `recorded` > `M` |
| Affidabilità | nuovo, `assess()` | forma 613 → UNRELIABLE; già netto → DERIVED; banche esplicite → VERIFIED |
| Non regressione | `tests/_prod_route_c_runner.py` sul corpus, diff prima/dopo | nessun file regredisce; 615 e 342 restano `quadra` |
| Preliminare | `tests/test_csv_schema_detection.py` | aggiungere `skipif` sul CSV di corpus assente (oggi la suite è rossa e maschererebbe una regressione) |

I due test su 613 **contengono già i numeri giusti**: sono la specifica, non qualcosa da riscrivere.

## 9. Fixture di accettazione finale

`tests/debug/Bilancio_Riclassificato DEF.pdf` — bilancio riclassificato comparativo, route B.

**Verità dal layer di testo** (documento internamente coerente, verificato a entrambi gli anni):

| | 2025 (corrente) | 2024 (precedente) |
|---|---|---|
| TOTALE ATTIVO = PASSIVO | 1.758.609 | 1.836.998 |
| Totale patrimonio netto | 160.307 | 288.301 |
| Utile (perdita) | **−127.995** | 17.305 |
| EBIT / EBITDA | −81.422 / −48.438 | 61.025 / 98.875 |
| Totale debiti | 1.506.575 | 1.472.021 |

**Baseline 2026-07-29: il file NON importa.**

```
PDFImportError: Importazione non salvata: il bilancio estratto non supera i
controlli contabili (Utile CE 45.082 != sp13 17.305, diff 27.777)
```

Difetti osservati, **tutti fuori dallo scope di questa spec**:

1. **Anni invertiti** — l'estrattore mette il 2024 come corrente (`sp13 = 17.305`) e il 2025
   come precedente (`−127.995`);
2. **Sezione C letta come D** — 27.777 di *proventi e oneri finanziari (C)* finiscono in
   `ce17_rettifiche_attivita_fin` invece che in `ce15`. È l'errore di classe 2 che rompe
   l'identità CE↔SP e provoca il rifiuto;
3. **Aggregati e sotto-campi da colonne diverse** — `sp06_crediti_breve` differisce dai dettagli
   di 1.308.629, cioè il valore *2024*.

→ **Spec 2** (assegnazione anno/colonna su route B + sezione C vs D). Questo file va usato come
**test end-to-end finale di entrambe le spec**: dopo la spec 1 deve restare rifiutato in modo
onesto e senza regressioni; dopo la spec 2 deve importare con i valori della tabella qui sopra.

Nota positiva: il sistema si sta comportando correttamente — **rifiuta invece di importare un
dato falso**. Questo non è un caso di fallimento silenzioso, è un caso di accuratezza di
estrazione.

## 10. Ordine di implementazione

| # | Passo | Rischio |
|---|---|---|
| 0 | `skipif` sui due test CSV (suite verde prima di iniziare) | nullo |
| 1 | Dedup auto-validante (§5.1) — rianima i due test 613 | basso: gate sul dichiarato |
| 2 | Catena di classificazione (§5.2) — EBITDA sui "4 sezioni" | molto basso: solo dove oggi è `None` |
| 3 | `fallback_bucket()` (§5.3) — politica centralizzata | medio |
| 4 | `reliability.assess()` (§5.4) — modulo puro, testabile isolatamente | basso |
| 5 | Gating in `pdf_importer` (§5.5) + diff corpus prima/dopo | medio: cambia `forecastable` |

I passi 1 e 2 hanno criteri di accettazione già scritti nei test esistenti e si possono fare in
TDD senza il corpus completo.
