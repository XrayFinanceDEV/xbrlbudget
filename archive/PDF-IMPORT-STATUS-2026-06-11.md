# Stato Import PDF Bilanci — 2026-06-11

Riepilogo del lavoro svolto sull'import PDF dei bilanci (modulo `importers/`), lo stato
attuale del programma e i file ancora da sistemare nel batch `Test/successTerzo/`.

> **NB IMPORTANTE — i fix agiscono in fase di import.** Tutte le correzioni qui sotto
> operano durante l'estrazione/import del PDF. I record **già presenti in DB non cambiano**:
> per beneficiarne occorre **ri-caricare il PDF** dalla UI.

---

## 1. Lavoro svolto oggi

### 1.1 Bug segno/valore `ce10` (variazioni rimanenze materie prime) — squadratura CE
Sintomo utente: nel Conto Economico l'item **11) Variazioni rimanenze materie prime** non
quadrava (es. alma `/infrannuale`: CE off di 15.662). `ce10` è una **variazione**, non un
costo puro: costo quando le rimanenze calano (positivo nel modello), **credito** quando salgono
(negativo). Il modello somma i costi positivi (`COPRO = Σcosti`, `utile = VdP − COPRO`).

Tre cause distinte, tutte risolte in `importers/pdf_extractor_llm.py`:

1. **Convenzione "costi in parentesi"** (`_normalize_ce_signs`, Pass 2): nei PDF dove i costi
   sono stampati negativi, `ce10` va **negato** (stessa trasformazione delle altre righe costo),
   non `abs()`. Credito `+X → −X`, costo reale `−X → +X`. (caso **alma/271**: +7.831 → −7.831)

2. **Backstop BS-ancorato** `_validate_ce10_against_bs` (chiamato su single+dual **prima** del
   cross-check imposte; gated su BS quadrato così `sp13` è affidabile):
   - **FLIP** se l'unica cosa che riconcilia CE↔SP è invertire il segno (gap `== −2·ce10`).
   - **ZERO** se è azzerarlo (gap `== −ce10`): l'LLM ha pescato un valore spurio da una colonna
     anno-precedente disallineata. (caso **Elle Erre 144/328**: PDF stampa item 11 `(300.567)`,
     ma i totali del PDF e l'utile contabilizzato tornano solo con `ce10 = 0`).
   - Entrambi sono detector **exact-match** (tol €2), mutuamente esclusivi: non scattano su
     un `ce10` legittimo (es. GHEDA `−33.286` lasciato intatto).

### 1.2 Imposte mancanti (`ce20`) — `_validate_ce_imposte` "Case 0"
L'LLM a volte perde il valore della riga **20) Imposte** (`ce20 ≈ 0`) pur essendo presente nel
PDF → utile CE sovrastimato. Nuovo ramo: se `ce20 ≈ 0` e l'ancora BS implica un'imposta positiva
plausibile (`PBT > 0`, `0 < PBT − sp13 < PBT`), riempie `ce20 = PBT − sp13`.
Guardato a `ce20 ≈ 0` (non sovrascrive imposte reali, es. GHEDA 117.892) e `expected < PBT`
(un gap > PBT è un altro errore, es. `ce10` fabbricato di 328 → lasciato stare).
(caso **336**: `ce20` 0 → 302.178, utile → 618.847 = `sp13`).

### 1.3 Fallback deterministico→LLM inefficace — `force_llm`
Un bilancio mis-rilevato come "situazione contabile" dava estrazione vuota. Il fallback in
`pdf_importer` chiamava `extract_pdf_with_llm`, ma **quella funzione ri-controllava
`is_situazione_contabile` e rimbalzava di nuovo sul parser deterministico vuoto**. Aggiunto
`extract_pdf_with_llm(file_path, force_llm=True)` che salta il re-routing; `pdf_importer._llm_extract`
ora lo usa. (caso **313**: estrazione vuota → ora ATT=PAS=265.810, CE quadra).
Aggiornato anche `Test/_harness.py` per rispecchiare il fallback.

### 1.4 Frontend — Toaster (sonner)
`components/ui/sonner.tsx` era il wrapper shadcn vecchio (sonner v1) mentre è installato
**sonner v2.0.7**. Allineato alla versione canonica v2 (CSS-var `--normal-bg/text/border`,
mappate ai token `--background/--foreground/--border` con `hsl()` per Tailwind v3), preservando
l'aspetto. Build + type-check OK; nessun errore riproducibile lato SSR (errore originale = cache
`.next` stantia / edge di hydration React 19).

### File corretti oggi
`271` (alma), `144` + `328` (Elle Erre), `336`, `313` — più il fix Toaster frontend.

---

## 2. Stato del programma (import PDF)

Architettura di estrazione invariata, ora più robusta:

- **Situazione contabile / trial balance** → parser deterministico
  (`situazione_contabile_parser.py`): DEPI, AGO 8-cifre, single-column 6-cifre, TeamSystem,
  contrapposte 8-cifre, generico contrapposte best-effort.
- **IV-CEE / bilancio** → LLM (PyMuPDF + Claude Haiku), single-year + dual-year.
- **Fallback**: parser deterministico vuoto (`totale_attivo == 0`) → LLM forzato (`force_llm`).
- **Validatori post-estrazione (LLM)** ancorati al BS bilanciato:
  `_normalize_ce_signs` → `_validate_ce10_against_bs` → `_validate_ce_imposte`,
  più crediti/debiti/equity. Helper condiviso `_ce_risultato_ante`.
- **Anti-masking**: niente plug negativi/oversize silenziosi; `BILANCIO NON QUADRATO` quando
  il pareggio non è ricostruibile (da correggere in Rettifiche).

**Esito batch `successTerzo` (59 PDF): ~40 CLEAN**, BS quadrato e cross-check CE↔SP a 0.

---

## 3. File analizzati — dettaglio batch `Test/successTerzo/success/`

### ✅ CLEAN (~40)
`143, 162, 164, 171, 173, 176, 182, 201, 202, 207, 208, 209, 221, 227, 241, 255, 256, 257,
269, 272, 275, 283, 287, 288, 298, 319, 320, 329, 330, 315, 324` + i corretti oggi
`144, 271, 313, 328, 336`.

### 🟡 Rounding benigno (≤ 2 €, di fatto clean)
`147` (1.51), `265` (1), `280` (0.38), `302` (2/0.30), `324` (0.74), `340` (0.18), `341` (1).

### 🔧 Corretti oggi (vedi §1)
| File | Problema | Fix |
|------|----------|-----|
| `271` alma | ce10 segno (CE off 15.662) | normalize negate + flip BS-ancorato |
| `144`/`328` Elle Erre | ce10 spurio `(300.567)` (CE off 300.567) | ce10 zero BS-ancorato |
| `336` | imposte mancanti (CE off 302.178) | ce20 fill da ancora BS |
| `313` | estrazione vuota (mis-detect trial balance) | fallback `force_llm` |

---

## 4. Cosa manca da sistemare

### 4.1 Honest-fail — comportamento CORRETTO, non bug
Il parser rifiuta/segnala invece di inventare dati. Richiedono un sorgente migliore o sono
intrinsecamente non elaborabili:

| File | Motivo |
|------|--------|
| `137` | Lato attivo sotto-estratto (~4M) → `validate_balance = False` |
| `150` | PDF minuscolo/garbage (imposte misparse) → `validate_balance = False` |
| `196`, `335` | Documento **solo economico**, nessuno Stato Patrimoniale → `ValueError` |
| `314` | Colonna anno corrente (2025) **tutta a zero** nel sorgente (comparativo "2024") |
| `337` | Scansione **OCR corrotta** ("Perdlta d'esercizio") |

### 4.2 Varianza LLM — non deterministicamente correggibile
BS quadra, ma la CE ha letture errate del modello, diverse a ogni run. Nessun campo singolo
spiega esattamente il gap (quindi i corrector BS-ancorati non scattano):

| File | Gap CE↔SP | Ipotesi |
|------|-----------|---------|
| `138` | −61.350 | riga CE persa |
| `161` | 168.877 | CE sotto-estrae ricavi (sp13=321.232 è **corretto**) |
| `254` | 667.731 | accantonamento/provento non bilanciato |
| `282` | 131.561 | misread cifre (296→279k) su infrannuale 2-decimali |
| `331` | −1.520 (BS) | riga crediti persa in estrazione |

### 4.3 Trial-balance CE rebuild best-effort — ✅ RISOLTO (2026-06-12)
Tutti i 6 file ora a `diff vs CE = 0.00`, `validate_balance=True`. Triage via 5 agenti
diagnostici (fan-out) → 5 cause-radice distinte, riconciliate al centesimo.

| File | Gap prima | Causa-radice | Fix |
|------|-----------|--------------|-----|
| `211`,`215` | −216.776 / −222.176 | sub-voci `ce08b/ce09a/ce09b` (328.177) tenute separate, formula utile legge solo aggregati | `ce_add` somma sub-voci in `ce08`/`ce09` |
| `131`,`132` | −21.067 | route DEPI `default_ce=False` → mastri costo non riconosciuti scartati | DEPI `default_ce=True` |
| `210` | −320.370 | header "TOTALE A T T I V I T" letter-spaced → regex totali fallisce → sp13=0 | `_find_total` fallback whitespace-stripped |
| `246` | −1.469.999 | `_be_split` taglia pagine costi-only a colonna singola in mezzo alla riga + `_be_reclassify` perde scarto mastri con figli incompleti | guard amounts-one-sided in `_be_split` + booking residuo padre−Σfigli |

Tutto in `importers/situazione_contabile_parser.py` (path deterministico; l'LLM lo bypassa →
zero rischio sui ~40 IV-CEE puliti). Non-regressione verificata: `158/159/249/213` restano 0.00;
l'edit residuo isolato SOLO migliora (`338` da 1,35M → 160k), mai peggiora.

**Restano honest-fail** (BS quadra con plug grande, `BILANCIO NON QUADRATO` per le Rettifiche, mai
cross-check 0): `169` (573k), `309` (852k), `338` (160k). `330` = CE vuota (sezione P&L non
parsata, sp13 −2.505) pre-esistente e fuori da questo cluster.

> **NB:** fix in fase di import → **ri-caricare i PDF** dalla UI + **restart backend** (uvicorn
> `--reload` non ricarica i moduli condivisi).

---

## 5. File toccati (codice)

- `importers/pdf_extractor_llm.py` — `_normalize_ce_signs`, `_ce_risultato_ante` (nuovo),
  `_validate_ce10_against_bs` (ex `_validate_ce10_sign`, generalizzato), `_validate_ce_imposte`
  (Case 0 fill), `extract_pdf_with_llm(force_llm=)`.
- `importers/pdf_importer.py` — `_llm_extract` usa `force_llm=True`.
- `Test/_harness.py` — fallback deterministico→LLM rispecchiato.
- `frontend/components/ui/sonner.tsx` — allineato a sonner v2.
