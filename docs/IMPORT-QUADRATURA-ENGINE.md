# Sistema di importazione bilanci — routing, motore IV-CEE e quadratura

> Specifica e changelog delle modifiche (sessione 2026-06-15).
> Complementare a [`IMPORT-ROUTING-TAXONOMY.md`](IMPORT-ROUTING-TAXONOMY.md) (le 4 macro-aree)
> e alle note in `CLAUDE.md` (sezione *PDF Import*).
> Obiettivo: gestire la quadratura **per ogni bilancio**, in modo generale, non con patch per-file.

---


 342 (provvisorio parziale): il CE diverge dal gap SP (100k vs 168k) → la validazione lo respinge correttamente, importa col vecchio comportamento.
- 405/338 (slash gross interleaved): formato più ostico, lo split fisico delle colonne va riscritto — è un secondo intervento dedicato, te l'avevo segnalato come fuori dal "quick win" dei dotted.
- 330/376: layout non leggibili deterministicamente → per-design vanno al fallback LLM (CLAUDE.md). Forzarli nel parser C produrrebbe dati sbagliati.

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
- `normalize(text)` — lowercase, accenti rimossi, punteggiatura→spazio.
- `resolve(desc, side, statement)` — **classificatore condiviso** descrizione→nodo IV-CEE.
  Prudente: ritorna `None` se incerto (così la discesa gerarchica scende nei figli invece di
  misroutare). Match: alias esatto → alias più lungo contenuto.
- `classify_for_reclassify(desc)` — adattatore `(db_field, specific)` per `_be_reclassify`.
- `aggregate_flat(items)` — aggrega voci già a livello di legge (aree A/B/XBRL): somma le foglie,
  salta i nodi-totale (anti doppio-conteggio), applica la scadenza entro/oltre a crediti/debiti.
- `check_quadratura(bs, ce)` — il controllo unico (vedi §3).

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

`check_quadratura(bs, ce)` verifica:
1. **Attivo == Passivo** (±0,01) sui 18 aggregati SP.
2. **Utile CE == sp13** — cross-check che `validate_balance` NON faceva.
3. **Anti-masking**: legge `bs['_plug_residual']` (la massa NON classificata che il best-effort
   tampona in sp09/sp16). Se il plug supera **1% del totale** → `masked=True`: il bilancio "quadra"
   solo per costruzione, la composizione è inaffidabile.

Ritorna `Quadratura(totale_attivo, totale_passivo, sbilancio, quadra, utile_ce, sp13,
utile_match, plug_residual, masked, warnings)`.

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
| `SC_PLUG_REJECT_PCT` | `importers/pdf_importer.py` | `0.20` | sopra → rifiuta best-effort (LLM/onesto); sotto → import con flag Rettifiche |
| `_MASK_PCT` | `importers/iv_cee_hierarchy.py` | `0.01` | soglia diagnostica `masked` in `check_quadratura` |
