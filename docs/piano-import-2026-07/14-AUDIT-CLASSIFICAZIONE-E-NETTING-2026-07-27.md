# 14 — Audit logica di riconoscimento, classificazione e rettifica (2026-07-27)

> Metodo: lettura della serie `docs/import/REGOLE-IMPORT-*` e dei documenti di piano, poi
> **verifica sperimentale** di ogni affermazione contro il codice e contro i PDF disponibili
> (`tests/debug/`, `docs/examples/`). Ogni numero qui sotto è stato misurato, non dedotto.
>
> Il corpus completo (137 file) **non è in questo checkout**: le misure valgono sui 17 PDF
> presenti. Dove un difetto è strutturale lo dico; dove la conferma è su un solo file, lo dico.

## 0. Sintesi

| # | Area | Gravità | Stato |
|---|---|---|---|
| N1 | Dedup padre/figlio per **prefisso di codice** — fallisce sulle famiglie di codici disgiunte AGO | **alta** | RISOLTO 2026-07-29 (piano import-critical-accounts) |
| N2 | Il netting di 613 è un **no-op**: 2,25 M di fondi restano nei debiti | **alta** | RISOLTO 2026-07-29 (piano import-critical-accounts) |
| N3 | Il netting **non ha copertura di regressione viva**: i due test su 613 sono rotti | **alta** | RISOLTO 2026-07-29 (piano import-critical-accounts) |
| C1 | **Due classificatori paralleli** che si contraddicono e si mancano a vicenda | **alta** | RISOLTO 2026-07-29 (piano import-critical-accounts) |
| C2 | Il catch-all `ce12` è **silenzioso**: nessuna diagnostica sulla massa non classificata | media | PARZIALE 2026-07-29 — lato CE risolto (`_unclassified_mass` + `fallback_bucket`); resta da cablare il catch-all del PASSIVO, che scrive ancora l'aggregato `sp16` |
| D1 | `CLAUDE.md` descrive plug e riallineamenti **che il codice non fa più** | media | RISOLTO 2026-07-29 (§6 riscritta in `CLAUDE.md`: `enforce_ce_sp_identity`, `reconcile_ivcee_balance` e il residuo best-effort ora documentati come misurati, non tamponati) |
| T1 | 2 test CSV falliscono per file di corpus assente (manca lo `skipif`) | bassa | RISOLTO 2026-07-29 (`skipif` allineato agli altri test dipendenti dal corpus) |

---

## 1. NETTING — N1: la deduplicazione padre/figlio è basata sui prefissi di codice

### La regola dichiarata

`REGOLE-IMPORT-03` §3, "Il problema del doppio conteggio padre/figlio":

> **Si sommano i mastri oppure le foglie, mai entrambi.** Un mastro viene scartato quando i suoi
> figli **diretti** sommano al suo importo entro `max(€2; 1%)`.

E `REGOLE-IMPORT-03` §8, divieto n° 7: *"Mai sommare mastri e foglie insieme"*.

### Come è implementata

`situazione_contabile_parser._dedup_parent_child` (`:3458`) stabilisce la parentela con
`c.startswith(code)` — cioè **per prefisso del codice conto**.

### Perché non funziona

Il formato AGO usa **due famiglie di codici disgiunte**: i mastri a 8 cifre (`13095000`) e i
sotto-conti di dettaglio a 9 cifre (`101080000`). Il dettaglio **non è un prefisso** del mastro:

```
'101080000'.startswith('13095000')  -> False
'101220000'.startswith('13105000')  -> False
'101280000'.startswith('13110000')  -> False
'201385000'.startswith('13115005')  -> False
```

Nessuna coppia viene deduplicata, e **mastro + dettaglio vengono sommati entrambi** — esattamente
il divieto n° 7.

Questo è lo stesso principio già registrato in `docs/FIXING-IMPORT.md` e nella memoria di
progetto ("mai per prefisso di codice; riconoscere per descrizione"): qui è rimasto un residuo.

### Misura su `613_2024` (`docs/examples/`)

Righe lette dallo scan contro-conti, separate per lunghezza del codice:

| | somma | riferimento indipendente |
|---|---|---|
| ATTIVO — **solo mastri** (8 cifre, 12 righe) | **4.979.885,27** | = TOTALE ATTIVO dichiarato, **alla virgola** |
| ATTIVO — dettagli (9 cifre, 5 righe) | 41.613,46 | massa duplicata |
| ATTIVO — somma attuale del codice | 5.021.498,73 | +0,836 % sul dichiarato |
| FONDI — **solo mastri** (7 righe) | **1.853.799,20** | = valore atteso dal test |
| FONDI — dettagli (2 righe) | 393.916,50 | massa duplicata |
| FONDI — somma attuale del codice | 2.247.715,70 | +21 % |

Le coppie duplicate sono visibili a occhio nudo, stesso importo:

```
13095000 ATTREZZATURE INDUSTRIALI E COMMERCIALI   18.218,86
101080000 ATTREZZATURA VARIA E MINUTA             18.218,86   <- lo stesso importo
13105000 MOBILI E ARREDI                           7.610,00
101220000 MOBILI E ARREDI                          7.610,00   <- idem
13110000 MACCHINE D'UFFICIO                        1.694,90
101280000 MACCHINE UFFICIO ELETTRONICHE            1.694,90   <- idem
```

Idem sul passivo: `31010000 RISERVE DI RIVALUTAZIONI 2.598.287,91` e
`203887000 RISERVA DI RIVALUTAZIONE D.L. 104 2.598.287,91`; `37015000 DEBITI VERSO BANCHE (EE)
7.161,98` e `103435000 INTESA SANPAOLO 7.161,98`.

**Che la somma dei soli mastri riproduca il TOTALE ATTIVO dichiarato alla virgola è la prova
che i mastri sono la partizione corretta e i dettagli sono puro doppione.**

## 2. NETTING — N2: conseguenza, su 613 il netting non avviene

Con i dettagli sommati, i gate di `net_contra_accounts` (`:3742`) cadono così:

| Gate | Esito | Valore |
|---|---|---|
| 1 — massa contro > 1 % del dichiarato | **PASS** | 2.247.715,70 > 49.798,85 |
| 2 — lordo scansionato riconcilia entro 0,5 % | **FAIL** | scarto 41.613,46 = **0,836 %** |
| modalità *anchored* — servono i subtotali immobilizzazioni stampati | **FAIL** | `anchor_sp02 = anchor_sp03 = None` |

→ `return winner_bs, Z` — **no-op, `netted = 0`**.

Effetto sul bilancio importato: 2,25 M di fondi ammortamento **restano iscritti fra i debiti**,
l'attivo resta **lordo**, e l'ancora dichiarata non viene ridotta. Il documento non viene
corrotto (il no-op è conservativo e conforme al divieto n° 11), ma il risultato è un bilancio
sostanzialmente sbagliato che l'utente deve rifare a mano in Rettifiche.

**Correggendo N1 il gate 2 passerebbe con scarto 0,00** e la modalità anchored non servirebbe
affatto.

## 3. NETTING — N3: nessuna copertura di regressione viva

`REGOLE-IMPORT-03` §9 indica `tests/test_contra_netting.py` (668 righe) come *"il file di
riferimento"* del netting. **Due dei suoi test non girano**:

| Test | Errore | Natura |
|---|---|---|
| `test_contra_rows_on_613_finds_the_fondi_mass` | `ValueError: too many values to unpack (expected 2)` | debito di test: `_contra_rows` restituisce 3 valori, il test ne spacchetta 2 |
| `test_613_production_path_with_stubbed_gross_llm` | `assert Decimal('0') > Decimal('1800000')` | **difetto reale di prodotto** (N1/N2) |

**Il documento `13-DIAGNOSI-budget_615` §8 attribuisce entrambi allo stesso `ValueError` di
spacchettamento.** È esatto per il primo e **sbagliato per il secondo**: quel test fallisce
sull'asserzione `netted > 1.800.000`, cioè sta segnalando correttamente che il netting non
avviene. Il difetto è stato quindi archiviato come rumore di test.

I due test codificano i valori giusti (1.853.799,20; sp03 netto ~3,08 M; debiti < 400 k):
**vanno usati come specifica della correzione, non riscritti.**

## 4. CLASSIFICAZIONE — C1: due classificatori paralleli che si contraddicono

Esistono **due sistemi indipendenti** che mappano una descrizione su una voce IV-CEE:

| | Motore | Dati | Usato da |
|---|---|---|---|
| A | `iv_cee_hierarchy.resolve(desc, side)` | `data/iv_cee_tree.json` | `_be_reclassify` (best-effort) |
| B | `situazione_contabile_parser._classify_ce_costi` / `_ricavi` / `_sp_attivo` / `_sp_passivo` | tabelle di keyword inline | `_hier_reconstruct`, parser strutturati |

Non condividono nulla, e **ciascuno conosce ciò che l'altro ignora**:

| Descrizione | A — `resolve()` | B — `_classify_ce_costi` |
|---|---|---|
| `AMMORTAMENTI` | **`ce09_ammortamenti`** | **`None`** |
| `COSTI PERSONALE DIPENDENTE` | **`None`** | **`ce08`** |
| `ONERI FINANZIARI` | `ce15` | `ce15` |
| `ACQUISTI DI BENI` | `None` | `None` |

Il rescue gerarchico usa **solo B**, quindi su un file "4 sezioni" perde `AMMORTAMENTI` — che il
classificatore condiviso saprebbe risolvere.

### Effetto misurato su budget_342

`_classify_ce_costi` non riconosce 5 mastri di costo, che finiscono tutti nel catch-all
`ce12_oneri_diversi` (`f = _classify_ce_costi(d) or 'ce12'`):

```
ACQUISTI DI BENI                   58.604,70   -> dovrebbe essere ce05
AMMORTAMENTI                       36.500,17   -> dovrebbe essere ce09
PRESTAZIONI DI LAVORO NON DIPEND   23.172,80   -> ce06
GESTIONE VEICOLI AZIENDALI          8.773,07   -> ce06/ce07
SPESE AMMIN.,COMM. E DI RAPPRESE    6.831,68   -> ce06
```

`ce12_oneri_diversi` risulta 140.918,68 invece di ~7.036,26.

**Il pareggio e il risultato d'esercizio restano corretti** (la somma dei costi non cambia), per
cui **nessun gate se ne accorge**. Ma:

- **EBITDA è sbagliato**: 36.500,17 di ammortamenti sono dentro un costo operativo;
- `ce05` (materie prime) è a zero su un'impresa che compra beni;
- di conseguenza MOL, ROS, PFN/EBITDA, OF/MOL e il rating FGPMI/Altman sono falsati.

È esattamente il caso descritto in `REGOLE-IMPORT-00` §2: *"una quadratura perfetta non è una
prova di correttezza"*. Qui il file **quadra ed è classificato male**.

### Copertura sui PDF disponibili

Sonda su tutti i mastri di livello 1 dei 17 PDF presenti:

| Classificatore | Mastri non riconosciuti |
|---|---|
| `_classify_ce_costi` | **5** (elencati sopra) |
| `_classify_ce_ricavi` | 0 |
| `_classify_sp_attivo` | 0 |
| `_classify_sp_passivo` | 0 |

Il problema è concentrato sui **costi**. Attivo e passivo sono coperti su questo corpus.

## 5. CLASSIFICAZIONE — C2: il catch-all è silenzioso

`f = _classify_ce_costi(d) or 'ce12'` non lascia traccia. Una voce finita in `ce12` per default
è **indistinguibile** da un vero "oneri diversi di gestione".

Il sistema è per il resto molto attento a non mascherare (`_plug_residual`, `masked`, `is_empty`,
`_ce_sp_difference`, `_declared_assets_difference`). Qui manca l'equivalente: **non esiste un
`_unclassified_cost_mass`**. Una diagnostica analoga renderebbe visibile in Rettifiche una
classificazione da rivedere, senza cambiare un solo numero.

## 6. DOCUMENTAZIONE — D1: `CLAUDE.md` descrive comportamenti rimossi

`REGOLE-IMPORT-00` §5 registra i disallineamenti D1/D3/D4 e chiude con *"Resta da ripulire
`CLAUDE.md`, che descrive ancora il plug"*. **Non è stato fatto.** Verificato eseguendo il codice:

| `CLAUDE.md` afferma | Comportamento reale (misurato) |
|---|---|
| `enforce_ce_sp_identity` "forza `utile_CE == sp13`", con plug in `ce12`/`ce04`, spostamento in riserve con cap 10 % | **Non muta nulla.** Restituisce il CE invariato + `_ce_sp_difference`; logga *"nessuna voce CE/SP è stata modificata"* |
| "any residual ... is plugged into sp09/sp16 with a `BILANCIO NON QUADRATO` warning" | **Nessun plug.** Il residuo è solo misurato (`_plug_residual`); i log dicono *"nessun plug applicato"* |
| `reconcile_ivcee_balance` tampona la differenza (`cap_frac=0.05`) | Restituisce il BS invariato + `_declared_assets_difference` |

Il rischio non è teorico: `CLAUDE.md` è il file caricato per primo in ogni sessione. Chi legge
lì che esiste un plug **cerca un bug nel plug che non esiste**, o peggio, si fida di una
riconciliazione che non avviene.

## 7. TEST — T1: due test CSV falliscono per file assente

`tests/test_csv_schema_detection.py` (2 test) non è protetto da `skipif`: senza
`Test/june_sample/errori/budget_370_BILAQ-001.csv` sollevano `CSVImportError: File not found`
invece di essere saltati, come fanno tutti gli altri test dipendenti dal corpus. Igiene, non
prodotto — ma tiene la suite rossa e nasconde le regressioni vere.

## 8. Ciò che ho verificato e ho trovato corretto

Per non lasciare l'impressione che tutto sia rotto:

- **Il router** classifica correttamente i 17 PDF disponibili (aree A/B/C coerenti col
  contenuto). L'unico `UNSUPPORTED` (`Bilancino 31-5-26.pdf`) è una **scansione** (0 caratteri di
  testo): in produzione passa dal ramo OCR *prima* del router, quindi non è un errore di
  classificazione — chiamare `classify_bilancio` direttamente salta quel ramo.
- **Il principio "diagnosticare, mai fabbricare"** è realmente implementato: nessuna delle
  funzioni che la vecchia documentazione descrive come plug muta più alcun valore.
- **I gate auto-validanti funzionano**: su budget_613 il netting si è fermato invece di scrivere
  un valore sbagliato; su budget_342 il rescue gerarchico si è rifiutato di applicarsi finché il
  cross-check CE non tornava.
- **`_hier_lvl1`** (mastro = codice senza separatore i cui figli puntati lo seguono) regge
  correttamente sui file dotted disponibili.

## 9. Ordine di correzione consigliato

1. **N1** — parentela mastro/dettaglio non per prefisso. Sblocca N2 e N3 insieme; i valori
   attesi sono già scritti nei due test di 613.
2. **C1** — far consultare a route C anche `resolve()` quando la tabella keyword non risolve
   (o unificare i due classificatori). Sblocca `AMMORTAMENTI` → `ce09` e l'EBITDA.
3. **C2** — esporre la massa di costo non classificata come diagnostica.
4. **D1** — allineare `CLAUDE.md` a `REGOLE-IMPORT-00` §5.
5. **T1** — `skipif` sui due test CSV.
