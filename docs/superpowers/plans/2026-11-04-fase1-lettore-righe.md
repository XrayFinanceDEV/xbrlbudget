# Fase 1 — Lettore di righe unico — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un solo lettore che trasforma un PDF (text layer) o le celle di MinerU in righe con etichetta,
codice, importi per colonna, ruolo e periodo di ogni colonna, lato, sezione SP/CE e righe di totale con la
loro parentela, per i tre formati (schema di legge, schema con dettaglio conti, sezioni contrapposte e
bilanci di verifica).

**Architecture:** Un pacchetto nuovo, `importers/lettore/`, scritto **accanto** al percorso attuale e
**non collegato** all'import degli utenti: nessun file esistente di `importers/` cambia comportamento in
questa fase. Le regole vengono dall'inventario, riusate o fuse, mai riscritte da capo; la geometria (bordi
destri, distanze) decide, le parole d'intestazione confermano. La misura è un'ispezione nuova sul campione di
78 documenti: i totali stampati che le due letture indipendenti hanno annotato devono ritrovarsi come righe di
totale i cui figli sommano, colonna per colonna, e ogni colonna deve avere il periodo giusto.

**Tech Stack:** Python 3.12, PyMuPDF (`fitz`), `decimal.Decimal`, pytest. Nessuna dipendenza nuova, nessuna
chiamata a modelli.

**Spec:** la review «Generic Importer Gap Review» (https://claude.ai/artifact/ByQZE4SXdTd4TbeVVX6Yxy, Fase 1)
e l'inventario `.superpowers/sdd/2026-10-30-importatore-generico-fase1/inventario-lettura.md` (fuori da git:
i riferimenti `§` e `C1`…`C12` qui sotto sono a quel file). Leggere entrambi prima di cominciare.

## Global Constraints

- Nessuna modifica di comportamento al percorso di import esistente: `importers/*.py` fuori da
  `importers/lettore/` non si tocca. Il collegamento all'import è la Fase 2-4.
- Importi sempre `Decimal`, mai `float` (CLAUDE.md, «Money is Decimal»).
- La colonna (il lato stampato) è la verità sul lato; il lettore restituisce il lato fisico, mai riscritto.
- Mai dedurre la parentela dal prefisso o dalla lunghezza del codice: decide il totale stampato (CLAUDE.md,
  «Estrazione e classificazione»).
- Il lettore non classifica in campi sp/ce, non netta, non tappa: legge e dichiara. Una cosa che non sa
  decidere la dice (`Documento.avvisi`), non la indovina.
- Le regole di un solo gestionale (inventario §4) restano fuori dal pacchetto.
- I test usano PDF sintetici generati in `tmp_path` con `fitz`; nessun PDF di `Test/` in git e nessun test
  della suite che dipenda da `Test/` (la misura sul corpus è uno script, non un test).
- Ogni test che importa da `importers/` gira con il DB su una copia (`DATABASE_PATH`), come il resto della
  suite.
- Tutto il lavoro sul branch `feat/lettore-righe`; merge su richiesta.

## Review Focus

1. **Una cella vuota in mezzo alla riga** (`corrente | <vuoto> | differenza`): l'importo resta nella sua
   colonna, non scivola sulla vicina (C9). Test in Task 5.
2. **Pagina ruotata** (stampe orizzontali girate di 90°): righe e colonne nel riferimento visualizzato (C8).
   Test in Task 2.
3. **Un conto la cui colonna precedente non torna** (budget_1445): i totali si riconoscono colonna per
   colonna e la colonna che non chiude si dichiara, senza buttare la corrente (C6). Test in Task 6.
4. **Testo con una data o un importo dentro la descrizione** («capitale sociale euro 22.000.000,00» in
   intestazione, una scadenza «12 mesi»): resta etichetta, non diventa una cella. Test in Task 5.
5. **Documento senza text layer** (scansione): il lettore restituisce un `Documento` vuoto con un avviso,
   mai un'eccezione. Test in Task 5.

---

## File Structure

| File | Responsabilità |
|---|---|
| `importers/lettore/__init__.py` | Esporta `leggi_pdf`, `leggi_celle`, `Documento`, `Riga`, `Colonna`, `Importo` |
| `importers/lettore/importi.py` | Il parser unico degli importi (token → `Importo`) |
| `importers/lettore/geometria.py` | Parole nel riferimento visualizzato e raggruppamento in righe fisiche |
| `importers/lettore/colonne.py` | Colonne di importi dai bordi destri, ruolo e periodo di ogni colonna |
| `importers/lettore/lati.py` | Se il documento è a sezioni contrapposte e dove passa il confine fra i lati |
| `importers/lettore/righe.py` | Assemblaggio: celle per colonna, a capo, importi orfani, margini, sezioni SP/CE |
| `importers/lettore/totali.py` | Righe di totale e parentela, colonna per colonna |
| `importers/lettore/celle.py` | Ingresso dalle tabelle MinerU verso lo stesso `Documento` |
| `tests/lettore/pdf_sintetico.py` | Costruttore di PDF sintetici per i test |
| `tests/lettore/test_*.py` | Un file di test per modulo |
| `tests/corpus/righe_campione.py` | Misura sul campione: totali ritrovati e chiusi, periodi delle colonne |
| `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` | Una sezione nuova «Lettore di righe unico (Fase 1)» |

---

### Task 1: Parser unico degli importi

**Files:**
- Create: `importers/lettore/__init__.py`, `importers/lettore/importi.py`
- Create: `tests/lettore/__init__.py`, `tests/lettore/test_importi.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Importo:
      valore: Decimal
      forma: str          # "importo" | "percentuale" | "zero" (cella "-")
      testo: str          # il token come stampato
  def leggi_importo(token: str) -> Importo | None
  ```

Fonde le righe di §1.1 dell'inventario. Base: `import_snello/righe.py:_dec`/`importi`; le altre si
allineano a questa. Risolve C1 e C2.

- [ ] **Step 1: Scrivi i test** in `tests/lettore/test_importi.py`, uno per riga della tabella:

  | token | atteso |
  |---|---|
  | `1.234,56` | `Decimal("1234.56")`, forma `importo` |
  | `1.234` | `Decimal("1234")` (migliaia senza centesimi) |
  | `-1.234,56`, `1.234,56-`, `(1.234,56)` | `Decimal("-1234.56")` (C1: il meno in coda mai zero) |
  | `(5.367,37` | `Decimal("5367.37")` positivo: parentesi aperta non chiusa non è un segno (budget_1450, C2) |
  | `1.234,56 A` / `1.234,56 D` | negativo / positivo (marcatore di sezione) |
  | `1.234,56_` | `Decimal("1234.56")` (sottolineatura come glifo) |
  | `46.078 (1)`, `46.078*` | `Decimal("46078")` (rimando di nota) |
  | `€ 1.234,56` | `Decimal("1234.56")` |
  | `-` | `Decimal("0")`, forma `zero` (cella vuota Infocamere) |
  | `12,345` (3 decimali) | forma `percentuale` |
  | `2025`, `104`, `31/12/2025`, `12` mesi | `None` (non è un importo: un intero senza separatori o una data, C9) |
  | `1.712.097,143` | forma `percentuale` (3 decimali; SEZBIL resta fuori, §4) |
  | `********` | `None` |

- [ ] **Step 2: Lancia i test e verifica che falliscano**
  Run: `backend/venv/bin/python -m pytest tests/lettore/test_importi.py -q`
  Expected: FAIL (modulo inesistente)

- [ ] **Step 3: Implementa `leggi_importo`** in `importers/lettore/importi.py`. Una sola regex di forma
  (migliaia a gruppi di 3, virgola e 1-3 decimali), poi segno: `-` in testa o in coda, parentesi **chiuse**,
  marcatore `D`/`A` separato da spazio. Il token si pulisce prima da `_`, simboli di valuta, rimandi di nota.

- [ ] **Step 4: Lancia i test e verifica che passino** (stesso comando). Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add importers/lettore tests/lettore
  git commit -m "feat(lettore): parser unico degli importi"
  ```

### Task 2: Parole e righe fisiche

**Files:**
- Create: `importers/lettore/geometria.py`, `tests/lettore/pdf_sintetico.py`, `tests/lettore/test_geometria.py`

**Interfaces:**
- Consumes: niente
- Produces:
  ```python
  @dataclass(frozen=True)
  class Parola:
      x0: float; y0: float; x1: float; y1: float; testo: str
  @dataclass
  class RigaFisica:
      pagina: int          # 1-based
      y: float             # centro verticale
      parole: list[Parola] # ordinate per x0
  def parole_pagina(pagina: "fitz.Page") -> list[Parola]       # già nel riferimento visualizzato
  def righe_fisiche(parole: list[Parola], pagina: int) -> list[RigaFisica]
  # tests/lettore/pdf_sintetico.py
  def scrivi_pdf(path, pagine: list[list[tuple[float, float, str]]], *, a_destra: bool = True,
                 rotazione: int = 0, larghezza: float = 595, altezza: float = 842) -> None
  ```
  `scrivi_pdf` scrive ogni testo `(x, y, testo)` con `fitz`; con `a_destra=True` la x è il **bordo destro**
  per i token che sono importi (come stampano i gestionali), il bordo sinistro per gli altri.

Regola unica: quella di `situazione_contabile_parser._be_cluster_physical_rows` (centri entro 3,6 pt
**oppure** sovrapposizione verticale >= 55% dell'altezza minore, solo le ultime 4 righe candidate). Le
rotazioni come `detail_enrichment.collect_source_rows` 205-207. Sostituisce le 10 regole di C7.

- [ ] **Step 1: Scrivi i test**: `test_jitter_di_tre_punti_resta_una_riga` (codice a y=100, importo a
  y=102,8 → 1 riga); `test_due_righe_a_otto_punti_sono_due` (y=100 e y=108 → 2); `test_bordo_del_bucket_non_spezza`
  (y=99,9 e y=100,4 → 1 riga, contro la regola `round(centro)` di C7); `test_pagina_ruotata_di_90_gradi`
  (`rotazione=90`: le parole di una riga visualizzata restano una riga, ordinate da sinistra a destra).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_geometria.py -q`. Expected: FAIL
- [ ] **Step 3: Implementa** `parole_pagina` (`page.get_text("words")`, coordinate moltiplicate per
  `page.rotation_matrix` quando `page.rotation`) e `righe_fisiche`.
- [ ] **Step 4: Lancia** lo stesso comando. Expected: PASS
- [ ] **Step 5: Commit** `git commit -m "feat(lettore): parole nel riferimento visualizzato e righe fisiche"`

### Task 3: Colonne, ruoli e periodi

**Files:**
- Create: `importers/lettore/colonne.py`, `tests/lettore/test_colonne.py`

**Interfaces:**
- Consumes: `RigaFisica`, `Parola` (Task 2), `leggi_importo` (Task 1)
- Produces:
  ```python
  @dataclass
  class Colonna:
      indice: int                  # 0.. nell'ordine x
      x_destra: float              # bordo destro mediano
      lato: str                    # "U" (unico) | "L" | "R" (Task 4 lo raffina)
      ruolo: str                   # "esercizio" | "mastro" | "differenza" | "percentuale" | "dare" | "avere" | "saldo" | "ignoto"
      fine: date | None            # data di chiusura stampata sopra la colonna
      inizio: date | None
      mesi: int | None             # da inizio..fine, o da gennaio se l'inizio non è stampato
      corrente: bool               # la colonna-esercizio più recente
  def colonne_documento(righe: list[RigaFisica]) -> list[Colonna]
  def colonna_di(x_destra: float, colonne: list[Colonna]) -> Colonna | None   # None = fuori colonna
  ```

Base: `schema_legge_generico._bordi`/`_colonne_pagina` (bordi destri allineati entro 14 pt su >= 4 righe,
x0 > 150) e `_e_differenza`/maggioranza a 3 decimali per i ruoli «dai dati»; le intestazioni confermano:
parole di analisi con **una lista sola** (`differenza, diff., scostamento, scost., variazione, %`, C10),
`dare`/`avere`/`saldo`. Anni e date come `_anni_intestazione` (anno nudo `2025`, `31/12/2025`, `31/12/25`,
`31.12.2025`, `30-09-2025`; data lontana dalle colonne = frase), con «dal … al …» per l'inizio. Corrente =
colonna-esercizio **più recente**, ovunque stia (C4); due colonne-esercizio con lo stesso anno e mesi
diversi si tengono entrambe. Risolve C3, C4, C5, C10.

- [ ] **Step 1: Scrivi i test** con `scrivi_pdf`:
  - `test_due_esercizi_con_date` («31/12/2025 | 31/12/2024» sopra 6 righe di importi → 2 colonne
    `esercizio`, `fine` 2025-12-31 e 2024-12-31, `mesi` 12, la prima `corrente`);
  - `test_anni_nudi_sotto_esercizio` («ESERCIZIO ESERCIZIO DIFFERENZA SCOST.» con «2025 2024» sotto, come
    budget_313 → 4 colonne: esercizio 2025, esercizio 2024, differenza, percentuale);
  - `test_differenza_riconosciuta_dai_numeri_senza_intestazione` (terza colonna = prima − seconda su 5 righe →
    `differenza`);
  - `test_infrannuale_con_confronto_parziale` («Periodo fino al 30/06/2026 | infrannuale al 30/06/2025» → `mesi`
    6 e 6, come budget_1445);
  - `test_infrannuale_con_anno_intero` («dal 01/01/2026 al 31/05/2026 | dal 01/01/2025 al 31/12/2025» → 5 e 12);
  - `test_corrente_a_destra` («2024 | 2025» → `corrente` è la seconda);
  - `test_mastri_e_conti_su_colonne_diverse` (importi dei mastri allineati a un bordo, dei conti a un altro,
    una sola data in testa → due colonne dello stesso periodo, la prima `mastro`, la seconda `esercizio`;
    il ruolo `mastro` si riconosce perché ogni suo importo è la somma dei conti che lo seguono nell'altra
    colonna, non dalla posizione);
  - `test_colonna_di_fuori_tolleranza` (un importo 40 pt a sinistra di ogni bordo → `None`).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_colonne.py -q`. Expected: FAIL
- [ ] **Step 3: Implementa** `colonne_documento` e `colonna_di` (tolleranza 14 pt sul bordo destro).
- [ ] **Step 4: Lancia** lo stesso comando. Expected: PASS
- [ ] **Step 5: Commit** `git commit -m "feat(lettore): colonne dai bordi destri, con ruolo e periodo"`

### Task 4: Lati delle sezioni contrapposte

**Files:**
- Create: `importers/lettore/lati.py`, `tests/lettore/test_lati.py`

**Interfaces:**
- Consumes: `RigaFisica`, `Colonna`
- Produces:
  ```python
  def confine_dei_lati(righe: list[RigaFisica], colonne: list[Colonna]) -> float | None
  # x del confine fra lato sinistro (attivo/costi) e destro (passivo/ricavi); None = una sola sezione
  def assegna_lati(colonne: list[Colonna], confine: float | None) -> list[Colonna]   # lato "L"/"R"/"U"
  ```

Un solo rilevatore al posto dei 6 separatori e dei 4 «è contrapposto» (C11). Principio da
`_be_split`/`_be_split_codeless`: il confine è un varco verticale fra due gruppi di colonne-saldo, ciascuno
con le proprie descrizioni, su più righe; le parole `ATTIVITÀ/PASSIVITÀ`, `COSTI/RICAVI` in qualunque
maiuscolo lo confermano, non lo decidono. Uno schema di legge a due colonne-esercizio **non** è contrapposto:
la colonna di sinistra non ha descrizioni proprie a sinistra di sé.

- [ ] **Step 1: Scrivi i test**: `test_contrapposte_con_codici` (codice + descrizione + importo a sinistra,
  codice + descrizione + importo a destra, 8 righe → confine fra i due blocchi); `test_contrapposte_senza_codici`;
  `test_schema_a_due_esercizi_non_e_contrapposto` (descrizione + due importi → `None`);
  `test_intestazione_minuscola_attivita_passivita` («Attività … Passività» in minuscolo → confine trovato).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_lati.py -q`. Expected: FAIL
- [ ] **Step 3: Implementa** `confine_dei_lati` e `assegna_lati`.
- [ ] **Step 4: Lancia** lo stesso comando. Expected: PASS
- [ ] **Step 5: Commit** `git commit -m "feat(lettore): confine dei lati delle sezioni contrapposte"`

### Task 5: Assemblaggio delle righe

**Files:**
- Create: `importers/lettore/righe.py`, `tests/lettore/test_righe.py`
- Modify: `importers/lettore/__init__.py` (esporta `leggi_pdf`, `Documento`, `Riga`)

**Interfaces:**
- Consumes: Task 1-4
- Produces:
  ```python
  @dataclass
  class Riga:
      id: str                      # "p{pagina}r{n}{lato}", stabile fra due letture dello stesso file
      pagina: int
      y: float
      lato: str                    # "U" | "L" | "R"
      sezione: str                 # "SP" | "CE" | ""
      codice: str                  # "" se assente
      etichetta: str
      celle: dict[int, Importo]    # indice di Colonna -> importo; una colonna assente = cella vuota
      totale: bool = False         # Task 6
      figli: dict[int, tuple[str, ...]] = field(default_factory=dict)   # per colonna, id dei figli (Task 6)
      intestazione: bool = False   # riga-titolo senza importi (mastro o gruppo stampato come titolo)
      padre: str | None = None     # id della riga madre (Task 6)
      padre_verificato: bool = False   # True se i figli del padre sommano al suo totale stampato
      percorso: tuple[str, ...] = ()   # etichette degli antenati, dalla sezione al padre (Task 6)
  @dataclass
  class Documento:
      righe: list[Riga]
      colonne: list[Colonna]
      contrapposto: bool
      avvisi: list[str]
  def leggi_pdf(file_path: str) -> Documento
  ```

Regole riusate (inventario §1.2, §1.6, §1.8): importo legato alla colonna dal bordo destro (fuori colonna =
torna nell'etichetta, `righe._importo_in_descrizione` diventa questo); parentesi aperta staccata ricucita;
importo orfano a pochi punti dalla didascalia riattaccato (`_riattacca_importi`); didascalia a capo per
interlinea (`_grezze_pdf` 0,7 × interlinea mediana) e per frase aperta / sillaba / minuscola
(`_unisci_a_capo`), anche nelle righe-conto (lacuna di `collect_source_rows`); righe di margine ripetute e
piedi «Pagina N di M», «Pag. N», numero di pagina nudo, «Utente:» tolti (`_ripetute`, `_PIEDE`); riporti
«A RIPORTO», «SEGUE»; indirizzo/C.F./P.IVA/REA non sono righe; codice conto in testa separato dall'etichetta
(predicato unico «riga conto», `standard_ivcee.riga_conto`); sezione SP/CE dalle righe-titolo e dalla
continuazione di pagina (`collect_source_rows` 240-267, `_sezione_della_chiusura`). Un PDF senza text layer
→ `Documento` vuoto con avviso «nessun testo: serve l'OCR».

- [ ] **Step 1: Scrivi i test**:
  - `test_cella_vuota_non_sposta_la_riga` (3 colonne, riga con corrente e differenza, precedente vuota →
    `celle == {0: …, 2: …}`, Review Focus 1);
  - `test_capitale_sociale_in_intestazione_resta_etichetta` («CAP. SOC. E 22.000.000,00» lontano dalla colonna
    → nessuna cella, Review Focus 4);
  - `test_scadenza_in_didascalia_non_e_cella` («esigibili oltre 12 mesi 1.000,00» → una cella 1000);
  - `test_didascalia_a_capo_diventa_una_riga` («C) TRATTAMENTO DI FINE RAPPORTO DI LAVORO 387.507,50» +
    «SUBORDINATO» → una riga, budget_1445);
  - `test_importo_orfano_si_riattacca` (importo 4 pt sotto la didascalia senza importi → una riga);
  - `test_piede_ripetuto_non_e_una_riga` (stessa riga «Pagina 1 di 3» in fondo a 3 pagine → assente);
  - `test_sezione_dai_titoli_e_continuazione` («STATO PATRIMONIALE» p1, nessun titolo p2, «CONTO ECONOMICO» p3
    → sezioni SP, SP, CE);
  - `test_codice_conto_separato` («102355 151 - banche c/ricevute all'incasso (113.340,54)» → codice
    `102355 151`, importo −113340,54);
  - `test_scansione_senza_testo` (PDF di sola immagine → `righe == []`, un avviso, nessuna eccezione,
    Review Focus 5).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_righe.py -q`. Expected: FAIL
- [ ] **Step 3: Implementa** `leggi_pdf` componendo `parole_pagina` → `righe_fisiche` → `colonne_documento`
  → `confine_dei_lati`/`assegna_lati` → righe con celle.
- [ ] **Step 4: Lancia** lo stesso comando. Expected: PASS
- [ ] **Step 5: Commit** `git commit -m "feat(lettore): righe con celle per colonna, a capo, margini e sezioni"`

### Task 6: Righe di totale e parentela, colonna per colonna

**Files:**
- Create: `importers/lettore/totali.py`, `tests/lettore/test_totali.py`
- Modify: `importers/lettore/righe.py` (`leggi_pdf` chiama `marca_totali` e poi `assegna_padri` in fondo)

**Interfaces:**
- Consumes: `Documento`, `Riga`
- Produces:
  ```python
  def marca_totali(doc: Documento) -> None
  # imposta Riga.totale e Riga.figli[indice_colonna]; aggiunge a doc.avvisi le voci che chiudono su una
  # colonna e non sull'altra
  def assegna_padri(doc: Documento) -> None
  # imposta Riga.padre, Riga.padre_verificato e Riga.percorso per ogni riga
  ```

**Mastri e percorso dei conti.** Un conto si classifica dal suo contesto: «Altri», «c/anticipi», «diversi»
non dicono nulla da soli. `assegna_padri` dà a ogni riga il padre e il percorso delle etichette dei suoi
antenati, in quest'ordine di prova:
1. **dalla somma** (verificato): il padre è il totale (mastro, sotto-totale, voce di legge) i cui `figli`
   contengono la riga su almeno una colonna; `padre_verificato = True`;
2. **dall'intestazione** (non verificato): senza un totale che la contenga, il padre è l'ultima riga
   `intestazione` sopra di lei nello stesso lato e sezione, alla stessa profondità di rientro o meno rientrata;
   `padre_verificato = False`. Un mastro stampato solo come titolo («10 IMMOBILIZZAZIONI» senza importo) resta
   così nel percorso dei suoi conti;
3. mai dal codice conto: né prefisso né lunghezza (CLAUDE.md). Il codice resta un dato della riga.
Le due fonti non si mescolano in silenzio: se l'intestazione sopra un conto è diversa dal totale che lo
contiene, vince il totale e la differenza va in `doc.avvisi`.

Algoritmo: quello di `import_snello/righe.py:marca_totali` (somma al centesimo di righe adiacenti dello
stesso lato e sezione, k >= 2, poi k = 1 solo se il documento ha mostrato un gruppo vero; scelta della
direzione con le due passate forzate; il totale risolto resta addendo del livello sopra; seconda passata a
direzione opposta per righe senza descrizione o «Totale …»; tetto 80 membri) applicato **a una colonna per
volta**, per ogni colonna-esercizio e saldo. Tolleranza unica (C6): 0,01 €, oppure 1 € quando le voci della
colonna sono stampate tutte all'unità. Lessico delle righe di controllo unico (C12): `TOTALE`, `TOTALI`,
`PAREGGIO`, `SALDO FINALE`, `SALDO GENERALE`, `ECCEDENZA`, risultato d'esercizio. Il totale stampato decide
la parentela, mai il codice. Una voce i cui figli tornano su una colonna e non sull'altra resta totale sulla
colonna che torna, e la differenza sull'altra va in `doc.avvisi` col nome della voce e lo scarto.

- [ ] **Step 1: Scrivi i test**:
  - `test_totale_e_figli_su_una_colonna` (tre conti + «Totale» → `totale`, `figli[0]` i tre id);
  - `test_totale_che_precede_i_figli` (voce con importo e poi i conti, schema con dettaglio);
  - `test_colonna_precedente_che_non_torna` (budget_1445: TFR 387.507,50 = 161.654,36 + 97.660,80 + 128.192,34
    sulla corrente; precedente 401.361,79 contro 333.227,76 → `figli[0]` pieno, `figli[1]` vuoto, un avviso con
    `68.134,03`; Review Focus 3);
  - `test_mastro_e_foglie_non_si_sommano_due_volte` (mastro 100 + foglie 60 e 40 + totale 100 → il totale ha
    per figlio il mastro, non le foglie);
  - `test_prefisso_del_codice_non_decide` (codici `10000001`/`100000010` come AGO, nessuno prefisso dell'altro:
    la parentela viene dalla somma);
  - `test_stampa_all_unita_tollera_un_euro` (voci intere, scarto di 1 → totale);
  - `test_stessa_descrizione_in_due_mastri` (mastro «FORNITORI» con «Altri» 100 e mastro «CLIENTI» con «Altri» 50,
    ciascuno col suo totale → i due «Altri» hanno `percorso` che finisce rispettivamente in FORNITORI e CLIENTI,
    `padre_verificato` vero);
  - `test_mastro_solo_intestazione` («10 IMMOBILIZZAZIONI» senza importo, poi tre conti senza totale → padre è
    l'intestazione, `padre_verificato` falso);
  - `test_percorso_fino_alla_sezione` (SP › DEBITI › FORNITORI › c/anticipi: tre livelli di totali annidati);
  - `test_totale_vince_sull_intestazione` (intestazione «CREDITI» sopra un conto che somma nel totale
    «DEBITI DIVERSI» → padre DEBITI DIVERSI, un avviso).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_totali.py -q`. Expected: FAIL
- [ ] **Step 3: Implementa** `marca_totali`; dove possibile **importa** gli helper puri di
  `import_snello/righe.py` (`_trova_totali`, `_cerca_membri`) invece di copiarli; se la loro firma lega a
  `Riga` vecchia, adattali dentro `totali.py` e scrivi nel commit perché.
- [ ] **Step 4: Lancia** lo stesso comando e tutta `tests/lettore/`. Expected: PASS
- [ ] **Step 5: Commit** `git commit -m "feat(lettore): totali e parentela colonna per colonna"`

### Task 7: Ingresso dalle celle MinerU

**Files:**
- Create: `importers/lettore/celle.py`, `tests/lettore/test_celle.py`
- Modify: `importers/lettore/__init__.py` (esporta `leggi_celle`)

**Interfaces:**
- Consumes: `leggi_importo`, `Colonna`, `Riga`, `Documento`, `marca_totali`
- Produces:
  ```python
  def leggi_celle(tabelle: list[str], pagine: list[int]) -> Documento
  # tabelle: HTML delle tabelle MinerU (come mineru_adapter._parse_table_html le riceve), pagine: pagina di ciascuna
  ```

Riusa `mineru_adapter._parse_table_html` per l'HTML; colonne dall'intestazione della tabella (date e anni come
Task 3; tabella senza intestazione eredita quella prima; tabella con intestazione non di date = nota, saltata,
come `schema_legge_generico._grezze_mineru`); etichetta = prima cella con lettere; **la colonna di ogni importo
è la posizione della sua cella**, mai «gli ultimi due» (C4, `_row_label_and_values`); normalizzazione OCR
(`94.086.46`, `11 396,02`, virgola staccata) dentro `leggi_importo` o in un pre-passo di `celle.py`.

- [ ] **Step 1: Scrivi i test**: `test_quattro_colonne_con_differenza` (`corrente | precedente | differenza | %` →
  corrente e precedente giuste, contro C4); `test_tabella_senza_intestazione_eredita`;
  `test_grafie_ocr` (`94.086.46` → 94086,46; `11 396,02` → 11396,02).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_celle.py -q`. Expected: FAIL
- [ ] **Step 3: Implementa** `leggi_celle`.
- [ ] **Step 4: Lancia** lo stesso comando. Expected: PASS
- [ ] **Step 5: Commit** `git commit -m "feat(lettore): ingresso dalle tabelle MinerU"`

### Task 8: Misura sul campione e documentazione

**Files:**
- Create: `tests/corpus/righe_campione.py`
- Modify: `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` (sezione nuova in fondo)

**Interfaces:**
- Consumes: `leggi_pdf`, `Documento`; il campione `tests/corpus/campione.json` (78 documenti, sul branch
  `feat/punteggio-fase0`: portalo su questo branch con `git checkout feat/punteggio-fase0 -- tests/corpus/campione.json`);
  le letture `Test/_analisi-campione/<id>.json` e `opus/<id>.json` (campo `totali_stampati`:
  `{voce, colonna, valore, pagina, testo}`, la `colonna` è la numerazione del lettore e non va usata) e la verità
  `Test/_analisi-campione/verita/<id>.json` (`periodi[].fine`, `periodi[].periodo`).
- Produces: `Test/_analisi-campione/righe/<etichetta>/righe.json` e `righe.md`

Per ogni documento con text layer (le scansioni si contano a parte, vanno per `leggi_celle` solo con MinerU
acceso, fuori da questa misura):
- **totali ritrovati**: un totale stampato (unione delle due letture, valore diverso da zero, deduplicato per
  `(pagina, valore)`) è ritrovato se una riga di quella pagina ha una cella con quel valore entro 0,01 €
  (1 € se il documento stampa all'unità);
- **totali chiusi**: fra i ritrovati, quelli marcati `totale` con `figli` non vuoti sulla stessa colonna;
- **periodi giusti**: per ogni periodo della verità, esiste una colonna-esercizio con la stessa `fine`
  (anno e mese) e gli stessi `mesi`; per un documento a una colonna basta la `fine`;
- **mastri giusti**: per i documenti con l'elenco `conti` nella prima lettura (campi `codice`, `descrizione`,
  `importo`, `pagina`, `padre`), ogni conto non totale ritrovato (stessa pagina e importo) ha come padre una
  riga la cui etichetta o il cui codice coincide col `padre` annotato; quota di conti con padre giusto, e quota
  con padre verificato dalla somma.
Il rapporto dà le tre percentuali in totale e per tipologia, e per documento l'elenco dei totali non ritrovati
o non chiusi (pagina, valore, voce).

- [ ] **Step 1: Scrivi lo script** con opzioni `--etichetta`, `--solo` (id separati da virgola) e un
  riepilogo a terminale, sul modello di `tests/corpus/punteggio.py`. Nessun import, nessuna rete.
- [ ] **Step 2: Lancialo sul campione**
  Run: `IMPORT_CORPUS_ROOT=$PWD/Test backend/venv/bin/python tests/corpus/righe_campione.py --etichetta fase1`
  Expected: un rapporto per 78 documenti (meno le scansioni), senza eccezioni.
- [ ] **Step 3: Leggi i documenti peggiori e correggi nel modulo che ne è responsabile** (colonne, a capo,
  totali…), con un test sintetico nuovo per ogni regola aggiunta, mai una regola legata a un `budget_ID`.
  Ripeti finché i criteri di «fatto» qui sotto non sono raggiunti o finché un caso non chiede una decisione del
  proprietario: in quel caso fermati e riportalo.
- [ ] **Step 4: Documenta** in `REGOLE-IMPORT-02-ESTRAZIONE.md` una sezione «Lettore di righe unico (Fase 1)»:
  che cosa legge, le regole riusate e da dove (rimando all'inventario), che non è ancora collegato all'import,
  come si lancia la misura.
- [ ] **Step 5: Lancia tutta la suite del lettore e la suite dell'import**
  Run: `DATABASE_PATH=<copia> backend/venv/bin/python -m pytest tests/lettore tests/test_standard_ivcee_parser.py tests/test_durata_comparato.py -q`
  Expected: PASS
- [ ] **Step 6: Commit** `git commit -m "feat(lettore): misura sul campione e documentazione"`

## Quando la Fase 1 è fatta

- Sui documenti del campione con text layer, **>= 95% dei totali stampati ritrovati** e **>= 90% chiusi**,
  in totale e in ogni tipologia con almeno 4 documenti; i documenti sotto soglia elencati con il motivo.
- **>= 95% dei conti con il mastro giusto** sui documenti con elenco dei conti, e i casi sbagliati elencati.
- **Periodi giusti su tutti** i documenti a due colonne (1470 settembre su settembre, 1540 giugno su giugno,
  1548 settembre sull'anno, 638 maggio sull'anno, 313 ad anni nudi).
- Le contraddizioni C1-C12 dell'inventario hanno ciascuna un test che fissa la scelta del lettore nuovo.
- Il percorso di import esistente non è cambiato: la suite di prima passa come prima (gli stessi 9 test che
  falliscono già su `main` restano gli unici).

## Fuori da questa fase

Collegare il lettore all'import (Fase 2-4), la classificazione dei conti, il netting, il plug, le regole per
gestionale dell'inventario §4, la riparazione dei glifi di font danneggiati (resta nel percorso attuale finché
la Fase 4 non lo congela).
