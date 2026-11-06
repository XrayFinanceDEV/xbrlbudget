# Fase 3 — Il lettore decide gli importi: prima quadrato, poi i dettagli — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un percorso nuovo d'import costruito sul lettore di righe (Fasi 1-2) che, su un PDF che quadra, produce
**per costruzione** uno SP e un CE quadrati, con le macro-voci ancorate ai totali stampati verificati e i dettagli
KPI distribuiti solo dentro la propria macro-voce; anno precedente compreso, con la sua durata.

**Architecture:** Il lettore dà le righe e le parentele verificate dalle somme stampate. Un modulo prende le
**foglie contate una volta** (mai mastro e figli insieme) e le **ancore** (totali stampati che corrispondono a una
voce di legge, più totale attivo/passivo e risultato). La classificazione è in due passi: (1) foglia → macro-voce
(sp01-sp18, ce01-ce20), prima deterministica dal percorso di legge stampato, poi Qwen con JSON guidato su un elenco
già ristretto dal lato e dalla sezione della foglia (la colonna decide il lato); (2) solo per le macro-voci KPI,
foglia → sotto-voce dentro quella macro. Un blocco ancorato che dopo il passo 1 non torna si richiede a Qwen solo
per le sue foglie, 3 volte, a maggioranza. La composizione somma le foglie per campo, ricava `sp13` dal CE, chiude
in automatico e dichiara uno scarto fino a 1 € nel secchio «altri» della macro-voce, e dichiara (non tappa) ciò che
resta oltre. Il percorso entra in `import_snello.importa` **dopo** i lettori deterministici e **prima** del modello
di oggi, con lo stesso cancello di adozione (`deterministico._esito`); se non quadra, il percorso di oggi prosegue
come prima.

**Tech Stack:** Python 3.12, `decimal.Decimal`, pytest; Qwen su gx10 via `llm_provider.chiama_gx10_json`
(temperatura 0, JSON guidato); nessuna dipendenza nuova.

**Spec:** la review «Generic Importer Gap Review» (https://claude.ai/artifact/ByQZE4SXdTd4TbeVVX6Yxy), «Phase 3 —
Two-step classification with votes» e «Rules for the new path»; le decisioni del proprietario in memoria
`prima-quadrato-poi-dettagli` (2026-11-06) e qui sotto; `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` §11 e
`docs/import/REGOLE-IMPORT-04-QUADRATURE.md` §13 (misura della Fase 2: in 9 dei 10 documenti salvati sbilanciati
il PDF quadra); la mappa del percorso snello `.superpowers/sdd/2026-11-06-fase3-mappa-snello.md` (ancore file:riga).

## Decisioni del proprietario

- **Prima quadrato, poi i dettagli** (2026-11-06): «our priority is to import balanced PDF than we search for extra
  details needed for correct classification, the details should not unbalance the imported sheet».
- **Fino a 1 € è arrotondamento** (2026-11-06): «1 eur difference is acceptable and we can auto fix it» — si chiude
  in automatico, dichiarato, senza avviso all'utente. Il tappo snello fino a 10 € resta com'è.
- **Profondità: macro-voci + dettagli KPI** (2026-11-06): `sp06a`, `sp16a`-`sp16d`, `sp17a`-`sp17c`, `ce08`
  (`ce08a`-`ce08d`), `ce09` (`ce09a`/`ce09b`). Il resto della massa di una macro-voce va nel suo secchio «altri».
- **3 voti solo sui blocchi che non tornano** (2026-11-06): un documento che quadra al primo passo non costa più di oggi.

## Global Constraints

- **Gli importi vengono solo dal testo** (o dalle celle MinerU) tramite il lettore; Qwen non scrive mai un importo,
  indica una classe per un id di riga.
- **Ogni foglia conta una volta.** Si sommano le foglie del lettore (righe non `totale`, con importo sulla colonna),
  mai un mastro e i suoi figli insieme (CLAUDE.md, «Mai dedurre la parentela»).
- **La colonna decide il lato** (CLAUDE.md): una foglia del lato attivo va solo su `sp01`-`sp10`, una del passivo
  solo su `sp11`-`sp18`; costi e ricavi come da sezione e colonna, mai per descrizione (`_resolve_ce_field`, non
  `iv_cee_hierarchy.resolve(side=…)`, CLAUDE.md).
- **Un dettaglio non attraversa mai la sua macro-voce**: il passo 2 sceglie solo fra le sotto-voci della macro
  assegnata al passo 1; la macro-voce resta la somma delle sue foglie.
- **Mai un plug** oltre 1 €: lo scarto oltre 1 € si dichiara (`_plug_residual` = solo la chiusura ≤ 1 €,
  `_unclassified_mass` = massa senza classe), e l'adozione decide `deterministico._esito` come per ogni lettore.
- **`TIER0_FIELDS` non sono mai un secchio di ripiego** (CLAUDE.md); i secchi «altri» sono quelli di
  `iv_cee_hierarchy.residual_bucket` (`sp06g`, `sp16g`, `ce06` fra i costi, `ce04` fra i ricavi, …).
- **I lettori deterministici di oggi restano davanti** e i loro risultati non cambiano: un documento che oggi adotta
  `xbrl_reso`, `schema_codici`, … ha gli stessi numeri (verificato col punteggio, Task 8).
- Interruttore `IMPORT_LETTORE` (default acceso sul branch per la misura; `0`/`off` lo spegne e il percorso di oggi
  è identico byte per byte, test in Task 7).
- Rimanenze per natura, netting dei fondi, risultato come cifra di chiusura: si riusano le regole condivise
  (`importers/rimanenze_ce.py`, `percorsi.e_fondo`, `calculate_ce_result`), nessuna seconda implementazione.
- Nomi privati dei moduli vecchi: solo tramite `importers/lettore/_ereditati.py` con test di deriva (regola della
  Fase 2, `test_nessun_privato_da_fuori`).
- Codice, test e commenti in italiano; importi `Decimal`; test con PDF sintetici in `tmp_path`, Qwen sostituito
  (`chiama_json=` iniettabile o `monkeypatch` di `llm_provider.chiama_gx10_json`), DB su copia (`DATABASE_PATH` e
  `BUDGET_REAL_DB`); mai `pytest tests` intero, mai `ANTHROPIC_CONSENTITO`.
- Lavoro sul branch `feat/fase3-importi` da `main` c57e232; merge e push su richiesta del proprietario.

## Review Focus

1. **Un mastro con figli verificati e anche i figli stampati**: la somma per campo conta solo le foglie; il
   mastro mai. Test in Task 2.
2. **Una foglia sul lato attivo che il modello manda su un campo del passivo**: si rifiuta la risposta e si
   riprova nella stessa chiamata di voto; senza classe valida la massa va nel secchio «altri» del lato, dichiarata.
   Test in Task 3.
3. **Contrapposte con il solo totale attività/passività** (nessuna ancora di macro-voce): il foglio quadra
   comunque perché ogni foglia sta sul suo lato; la macro-voce sbagliata resta un errore dentro il lato, che il
   punteggio misura. Test in Task 4.
4. **Colonna precedente di 9 mesi**: l'anno precedente si salva con `period_months` dalla colonna del lettore
   (`Colonna.mesi`), mai come anno pieno. Test in Task 6.
5. **Qwen non risponde o va in errore a metà**: il percorso del lettore esce `vuoto`/non adottato e il percorso di
   oggi prosegue come prima, senza eccezioni. Test in Task 7.

## Mappa dei file

| File | Responsabilità |
|---|---|
| `importers/lettore/tavola.py` (nuovo) | La tavola unica percorso di legge → campo → macro-voce → dettagli KPI → secchio «altri» |
| `importers/lettore/foglie.py` (nuovo) | Foglie contate una volta e ancore (totali stampati di voce di legge, attivo, passivo, risultato) per colonna |
| `importers/lettore/classifica.py` (nuovo) | Passo 1 (macro), voti sui blocchi, passo 2 (dettagli KPI); cache per documento |
| `importers/lettore/componi.py` (nuovo) | Somma per campo, `sp13`, chiusura ≤ 1 €, scarti contro le ancore, chiavi diagnostiche |
| `importers/lettore/percorso.py` (nuovo) | `importa_col_lettore`: corrente + precedente con durata, risultato nella forma `_det` |
| `importers/import_snello/__init__.py` (modifica) | Innesto dopo `deterministico.tentativo` (≈ righe 279-285), interruttore |
| `tests/lettore/test_tavola.py`, `test_foglie.py`, `test_classifica.py`, `test_componi.py`, `test_percorso.py`, `tests/test_snello_lettore.py` | Test |
| `tests/corpus/punteggio.py` (branch `feat/punteggio-fase0`) | Sezione «Percorso del lettore» |
| `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md`, `REGOLE-IMPORT-04-QUADRATURE.md` | Documentazione |

---

### Task 1: La tavola unica

**Files:**
- Create: `importers/lettore/tavola.py`, `tests/lettore/test_tavola.py`

**Interfaces:**
- Consumes: `importers.import_snello.percorsi.campo_da_percorso`, `percorsi.NOMI`, `percorsi.e_fondo`;
  `iv_cee_hierarchy.detail_fields`, `iv_cee_hierarchy.residual_bucket`, `_ATTIVO_FIELDS`/`_PASSIVO_FIELDS`
  (pubblici o via `_ereditati.py`).
- Produces:
  ```python
  MACRO_ATTIVO: tuple[str, ...]   # codici corti "sp01".."sp10"
  MACRO_PASSIVO: tuple[str, ...]  # "sp11".."sp18"
  MACRO_COSTI: tuple[str, ...]    # ce05..ce17, ce19, ce20 con segno di costo
  MACRO_RICAVI: tuple[str, ...]   # ce01..ce04, ce18 (e i proventi finanziari)
  DETTAGLI_KPI: dict[str, tuple[str, ...]]  # {"sp06": ("sp06a",), "sp16": ("sp16a","sp16b","sp16c","sp16d"),
                                            #  "sp17": ("sp17a","sp17b","sp17c"), "ce08": ("ce08a".."ce08d"),
                                            #  "ce09": ("ce09a","ce09b")}
  def campo_da_percorso_legale(percorso: str) -> str | None   # "SPA.C.II.1.E" -> "sp06a"; delega a percorsi
  def macro_di(campo: str) -> str                             # "sp06a" -> "sp06"; "sp06" -> "sp06"
  def altri_di(macro: str) -> str                             # "sp06" -> "sp06g"; "ce08" -> "ce08d"; "sp01" -> "sp01"
  def macro_ammesse(lato: str, sezione: str, verso: str | None) -> tuple[str, ...]
      # lato "L"/"U" attivo, "R" passivo su SP; su CE verso "costo"/"ricavo"/None
  def nome_pieno(codice: str) -> str                          # "sp06a" -> "sp06a_crediti_clienti_breve"
  ```
  Etichette brevi delle macro-voci per il prompt: `ETICHETTE_MACRO: dict[str, str]` (dai nomi delle colonne ORM).

**Ruling sul conflitto A.3/A.4** (mappa §2): la tavola segue le colonne del DB (`ce03` = A.3 variazione lavori in
corso su ordinazione, `ce03a` = A.4 incrementi per lavori interni, commenti in `database/models.py:759-760`),
come `percorsi.py`; `iv_cee_tree.json` e `schema_etichette_parser._VALORE_PRODUZIONE` restano come sono (Fase 4).
Le **rimanenze di un elenco di conti** vanno comunque per natura con `importers/rimanenze_ce.py` (Task 4).

- [ ] **Step 1: Scrivi i test** in `tests/lettore/test_tavola.py`:
  - `test_percorsi_noti` (parametrizzato: `"SPA.C.II.1.E"→"sp06a"`, `"SPP.D.4.E"→"sp16a"`, `"SPP.D.4.O"→"sp17a"`,
    `"CE.B.9.a"→"ce08a"`, `"CE.B.10.b"→"ce09b"`, `"CE.A.3"→"ce03"`, `"CE.A.4"→"ce03a"`; uguale a
    `percorsi.campo_da_percorso` su ognuno);
  - `test_macro_e_altri` (`macro_di("sp16b")=="sp16"`, `altri_di("sp16")=="sp16g"`, `altri_di("ce09")` uguale a
    `residual_bucket("ce09", Decimal(0))`);
  - `test_macro_ammesse_per_lato` (`"sp06" in macro_ammesse("L","SP",None)`, `"sp16" not in macro_ammesse("L","SP",None)`,
    `"sp16" in macro_ammesse("R","SP",None)`, `"ce05" in macro_ammesse("U","CE","costo")`,
    `"ce01" not in macro_ammesse("U","CE","costo")`);
  - `test_nessun_tier0_come_altri` (per ogni macro, `altri_di(macro)` non è in `TIER0_FIELDS` salvo che sia la
    macro stessa senza dettagli);
  - `test_dettagli_kpi_dentro_la_macro` (ogni dettaglio di `DETTAGLI_KPI[m]` ha `macro_di(d) == m`).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_tavola.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implementa** `tavola.py` delegando a `percorsi` e `iv_cee_hierarchy`: nessuna tabella copiata a mano.
- [ ] **Step 4: Lancia** tutta `tests/lettore`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(lettore): la tavola unica percorso → campo → macro → dettaglio KPI`.

### Task 2: Foglie e ancore

**Files:**
- Create: `importers/lettore/foglie.py`, `tests/lettore/test_foglie.py`

**Interfaces:**
- Consumes: `Documento.righe_del_prospetto()`, `Riga` (`id`, `lato`, `sezione`, `codice`, `etichetta`, `celle`,
  `totale`, `figli`, `padre`, `padre_verificato`, `verso`, `percorso`), `Documento.colonne`, `Profilo.tipo`,
  `valore_nel_totale`; `schema_etichette_parser.percorso(etichetta)` (pubblica) per il percorso di legge di una
  voce stampata; `tavola.campo_da_percorso_legale`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Foglia:
      id: str; etichetta: str; codice: str; lato: str; sezione: str
      importo: Decimal            # con il segno di valore_nel_totale sulla colonna (verso e D/A del lettore)
      percorso_legale: str | None # dal proprio codice/etichetta o dal primo antenato verificato che ne ha uno
      antenati: tuple[str, ...]   # etichette degli antenati verificati, per il prompt
  @dataclass(frozen=True)
  class Ancora:
      chiave: str                 # un campo macro ("sp06", "ce08"), oppure "attivo" | "passivo" | "utile"
      importo: Decimal; riga: str; foglie: tuple[str, ...]  # id delle foglie sotto l'ancora
  def foglie_contabili(doc: Documento, colonna: int) -> list[Foglia]
  def ancore(doc: Documento, colonna: int) -> list[Ancora]
  def colonne_utili(doc: Documento) -> tuple[int | None, int | None]  # (corrente, precedente) esercizio/saldo
  ```
  Una foglia è una riga di prospetto non `totale`, con importo non nullo sulla colonna, non intestazione; una riga
  coi figli verificati su quella colonna non è mai foglia. Le ancore di macro-voce nascono solo da un totale chiuso
  (`Riga.totale` vero su quella colonna) il cui percorso di legge si risolve a un campo macro; «attivo»/«passivo»/
  «utile» dai totali generali stampati (lessico C12 di `totali.py`, nessuna seconda regex).

- [ ] **Step 1: Scrivi i test** (PDF sintetici, `tests/lettore/pdf_sintetico.py`):
  - `test_mastro_e_figli_contano_una_volta` (mastro «Crediti v/clienti» 300 con figli 100+200 verificati → due
    foglie, nessuna col mastro);
  - `test_foglia_senza_figli_verificati_resta_foglia` (riga con importo e figli solo da intestazione → foglia);
  - `test_percorso_legale_dall_antenato` (schema con «C) II - Crediti» › «1) verso clienti esigibili entro» ›
    conto «Cliente Rossi» → `percorso_legale` risolto a `sp06a` attraverso `tavola`);
  - `test_ancora_di_macro_voce` (totale «Totale crediti» chiuso → `Ancora("sp06", …)` con le sue foglie);
  - `test_ancore_attivo_passivo_utile` (contrapposte con «Totale attività», «Totale passività», «Utile
    d'esercizio» → tre ancore);
  - `test_righe_della_nota_escluse` (tabella di nota integrativa → nessuna foglia);
  - `test_colonne_utili` (due colonne esercizio 31/12/2025 e 31/12/2024 → `(0, 1)`; una sola → `(0, None)`;
    differenza/percentuale mai scelte).
- [ ] **Step 2: Lancia** `test_foglie.py`. Expected: FAIL.
- [ ] **Step 3: Implementa** `foglie.py`.
- [ ] **Step 4: Lancia** tutta `tests/lettore`; poi `strumenti/foglie_campione.py` (nella cartella del piano, fuori
  da git) che sui 78 documenti del campione stampa, per la colonna corrente: numero di foglie, somma attivo e
  passivo delle foglie, ancore trovate, e se Σ foglie attivo = ancora «attivo» e Σ passivo = «passivo» entro 1 €.
  Riportare nel rapporto la quota di documenti in cui le foglie già quadrano contro le ancore generali (è il tetto
  di ciò che il percorso può adottare quadrato).
- [ ] **Step 5: Commit** `feat(lettore): foglie contate una volta e ancore stampate`.

### Task 3: La classificazione in due passi, con i voti

**Files:**
- Create: `importers/lettore/classifica.py`, `tests/lettore/test_classifica.py`

**Interfaces:**
- Consumes: `Foglia`, `Ancora` (Task 2); `tavola.macro_ammesse`, `ETICHETTE_MACRO`, `DETTAGLI_KPI`, `macro_di`;
  `llm_provider.chiama_gx10_json(system, messaggi, schema, *, max_tokens, timeout)`; `GX10_CONCORRENZA`.
- Produces:
  ```python
  @dataclass
  class Classe:
      macro: str | None          # "sp06"; None = senza classe
      dettaglio: str | None      # "sp06a" solo per le macro di DETTAGLI_KPI, altrimenti None
      fonte: str                 # "legale" | "modello" | "voto" | "nessuna"
      voti: tuple[str, ...] = () # le risposte dei voti, se ci sono stati
  def classifica_macro(foglie: list[Foglia], *, chiama_json=None, cache: dict | None = None) -> dict[str, Classe]
  def rivota(foglie: list[Foglia], classi: dict[str, Classe], *, voti: int = 3, chiama_json=None) -> dict[str, Classe]
  def classifica_dettagli(foglie: list[Foglia], classi: dict[str, Classe], *, chiama_json=None, cache=None) -> None
  PROMPT_MACRO: str; PROMPT_DETTAGLIO: str
  ```
  **Passo 1:** una foglia con `percorso_legale` prende la macro da `tavola` senza modello (`fonte="legale"`, e il
  dettaglio se il percorso lo dà). Le altre vanno a Qwen a blocchi di 60, JSON guidato: per ogni id un valore
  dell'enum delle macro ammesse **per quella foglia** (`macro_ammesse(lato, sezione, verso)`), più `"X"` (non è un
  conto). Una risposta fuori dall'enum della foglia è scartata; la foglia resta senza classe. Cache per documento
  su `(etichetta normalizzata, lato, sezione)`.
  **Voti:** `rivota` richiede le sole foglie date `voti` volte con il prompt del passo 1 e una nota «blocco che non
  torna contro il totale stampato»; vince la maggioranza assoluta; senza maggioranza la classe precedente resta e
  la foglia è segnata `fonte="voto"` con i `voti` registrati.
  **Passo 2:** solo per le foglie la cui macro è in `DETTAGLI_KPI` e senza dettaglio legale: enum = le sotto-voci
  di quella macro più `"altri"`; la macro non cambia mai.

- [ ] **Step 1: Scrivi i test** (Qwen finto, nessuna rete):
  - `test_percorso_legale_senza_modello` (tutte le foglie con percorso → `chiama_json` mai chiamato);
  - `test_enum_ristretto_al_lato` (lo schema passato per una foglia del lato «L» non contiene `sp16`; per una «R»
    non contiene `sp06`);
  - `test_risposta_fuori_lato_scartata` (il finto risponde `sp16` per una foglia dell'attivo → `macro is None`,
    `fonte == "nessuna"`);
  - `test_cache_una_domanda_per_etichetta` (due foglie uguali per etichetta, lato e sezione → una sola voce nella
    richiesta);
  - `test_voti_maggioranza` (risposte `sp06`, `sp06`, `sp07` → `sp06`, `fonte == "voto"`, tre voti registrati);
  - `test_voti_senza_maggioranza` (`sp06`, `sp07`, `sp05` → classe precedente, tre voti registrati);
  - `test_dettaglio_dentro_la_macro` (foglia in `sp16`, il finto risponde `sp16b` → `dettaglio == "sp16b"`,
    `macro == "sp16"`; risponde `sp17a` → scartato, `dettaglio is None`);
  - `test_macro_senza_dettagli_kpi_non_chiede` (foglia in `sp04` → nessuna chiamata al passo 2);
  - `test_errore_del_modello` (il finto solleva `LLMProviderError` → le foglie restano senza classe, nessuna
    eccezione).
- [ ] **Step 2: Lancia** `test_classifica.py`. Expected: FAIL.
- [ ] **Step 3: Implementa** `classifica.py` (concorrenza con `ThreadPoolExecutor(GX10_CONCORRENZA)` come in
  `import_snello/lettura.py`; `max_tokens` = 40 + 14·n).
- [ ] **Step 4: Lancia** tutta `tests/lettore`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(lettore): classificazione in due passi, voti sui blocchi`.

### Task 4: La composizione quadrata

**Files:**
- Create: `importers/lettore/componi.py`, `tests/lettore/test_componi.py`

**Interfaces:**
- Consumes: `Foglia`, `Ancora`, `Classe`; `tavola.altri_di`, `nome_pieno`, `macro_di`; `percorsi.completa`;
  `calculate_ce_result`; `importers.rimanenze_ce.e_conto_rimanenze`/`natura_rimanenze`; `percorsi.e_fondo`.
- Produces:
  ```python
  TOLLERANZA_ARROTONDAMENTO = Decimal("1.00")   # la stessa di importers.lettore.diagnosi, importata da lì
  @dataclass
  class Composizione:
      bs: dict[str, Decimal]; ce: dict[str, Decimal]   # nomi pieni, aggregati = somma dei dettagli (percorsi.completa)
      scarti: dict[str, Decimal]       # per ancora: stampato - composto
      blocchi: list[str]               # chiavi delle ancore con |scarto| > 1 €
      chiusure: list[dict]             # [{"campo", "importo", "motivo": "arrotondamento"}], solo ≤ 1 €
      senza_classe: Decimal            # massa delle foglie senza macro (finita in altri_di del lato, dichiarata)
  def componi(foglie: list[Foglia], classi: dict[str, Classe], ancore: list[Ancora]) -> Composizione
  ```
  Regole: ogni foglia somma sul suo dettaglio, o sul secchio «altri» della sua macro, o — senza macro — sul secchio
  «altri» del suo lato (`sp06g` sull'attivo, `sp16g` sul passivo, `ce06` sui costi, `ce04` sui ricavi), contata in
  `senza_classe`; rimanenze per natura (`ce02`/`ce10`); fondi nettati sul cespite; `sp13` = utile del CE; uno scarto
  attivo-passivo o utile-`sp13` con valore assoluto ≤ 1 € si chiude sul secchio «altri» del lato che manca e si
  registra in `chiusure`; oltre 1 € nulla si muove.

- [ ] **Step 1: Scrivi i test:**
  - `test_contrapposte_quadra_per_costruzione` (foglie attivo 1.000, passivo 900, CE utile 100, classi arbitrarie
    ma sul lato giusto → attivo = passivo, `blocchi == []`);
  - `test_dettaglio_non_sbilancia` (spostare una foglia da `sp16a` a `sp16b` non cambia `sp16` né il pareggio);
  - `test_senza_classe_nel_secchio_del_lato` (foglia dell'attivo senza macro → in `sp06g`, `senza_classe` = suo
    importo);
  - `test_arrotondamento_chiuso` (scarto 0,80 € → chiuso, una voce in `chiusure` con motivo «arrotondamento»);
  - `test_oltre_un_euro_dichiarato` (scarto 1,50 € → nulla chiuso, `chiusure == []`);
  - `test_ancora_che_non_torna_e_un_blocco` (ancora `sp06` 500, foglie classificate `sp06` per 400 → `"sp06" in blocchi`,
    `scarti["sp06"] == 100`);
  - `test_rimanenze_per_natura` (conto «Rimanenze finali prodotti finiti» → `ce02`, «Rimanenze materie prime» → `ce10`);
  - `test_risultato_cifra_di_chiusura` (la riga «Utile d'esercizio» stampata non entra come foglia: `sp13` viene dal CE).
- [ ] **Step 2: Lancia** `test_componi.py`. Expected: FAIL.
- [ ] **Step 3: Implementa** `componi.py`.
- [ ] **Step 4: Lancia** tutta `tests/lettore`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(lettore): composizione quadrata, arrotondamento fino a 1 € dichiarato`.

### Task 5: Il percorso del lettore, anno corrente

**Files:**
- Create: `importers/lettore/percorso.py`, `tests/lettore/test_percorso.py`

**Interfaces:**
- Consumes: `leggi_pdf`, `leggi_celle` (pagine MinerU da 0 → `+1`, come `diagnosi._leggi`); Task 2-4.
- Produces:
  ```python
  def importa_col_lettore(file_path: str, contesto_mineru=None, *, chiama_json=None) -> dict
  ```
  Restituisce il dict nella forma che `deterministico._esito`/`_risultato_deterministico` si aspettano:
  `{"bs", "ce", "prior_bs", "prior_ce", "anno_precedente", "prior_stato", "diagnostica"}` con
  `bs["_plug_residual"]` = somma delle `chiusure`, `bs["_unclassified_mass"]` = `senza_classe` (sempre presenti,
  anche a zero), e `diagnostica = {"foglie", "ancore", "blocchi", "voti", "chiamate", "classi_per_fonte",
  "secondi"}`. Sequenza: foglie e ancore della colonna corrente → passo 1 → `componi` → se `blocchi`, `rivota` sulle
  foglie di quei blocchi e `componi` di nuovo → passo 2 → `componi` finale. Mai un'eccezione verso il chiamante: un
  errore dà `{"bs": {}, "ce": {}, "diagnostica": {"errore": ...}}` (che `_esito` legge come vuoto).

- [ ] **Step 1: Scrivi i test** (PDF sintetici, Qwen finto):
  - `test_schema_di_legge_senza_modello` (schema con voci di legge → zero chiamate, SP quadrato);
  - `test_contrapposte_col_modello` (contrapposte di 10 conti, il finto classifica → SP quadrato, `chiamate >= 1`);
  - `test_blocco_rivotato` (il primo passo sbaglia un conto sotto un'ancora `sp06`, i voti lo correggono →
    `blocchi == []` nella composizione finale, `voti > 0`);
  - `test_chiavi_diagnostiche_a_zero` (documento che quadra → `_plug_residual == 0`, `_unclassified_mass == 0`);
  - `test_errore_non_solleva` (file inesistente → dict con `diagnostica["errore"]`, nessuna eccezione).
- [ ] **Step 2-4:** come nei task precedenti.
- [ ] **Step 5: Commit** `feat(lettore): il percorso del lettore costruisce SP e CE`.

### Task 6: L'anno precedente e la sua durata

**Files:**
- Modify: `importers/lettore/percorso.py`; Test: `tests/lettore/test_percorso.py`

**Interfaces:**
- Consumes: `colonne_utili`, `Colonna.mesi/fine`.
- Produces: in `importa_col_lettore`, `prior_bs`/`prior_ce` composti sulla colonna precedente con **le stesse
  classi** del corrente (nessuna chiamata in più: le foglie si accoppiano per id di riga; una foglia presente solo
  nel precedente si classifica nello stesso giro del passo 1), `anno_precedente` = anno di `Colonna.fine`,
  `diagnostica["mesi_precedente"]` = `Colonna.mesi` (None se ignoto); `prior_stato` = `"letto"` se la composizione
  precedente non ha blocchi oltre 1 €, altrimenti `"scartato"` (come `deterministico._con_precedente`).

- [ ] **Step 1: Scrivi i test:**
  - `test_due_anni_stesse_classi` (due colonne, il finto chiamato una volta per etichetta → precedente quadrato);
  - `test_precedente_di_nove_mesi` (intestazioni «30/09/2026» e «30/09/2025 (9 mesi)», o periodo dichiarato →
    `mesi_precedente == 9`);
  - `test_precedente_che_non_torna_scartato` (colonna precedente con un blocco oltre 1 € → `prior_stato == "scartato"`,
    il corrente resta adottabile — budget_1445);
  - `test_una_colonna_niente_precedente` (`prior_bs is None`, `prior_stato == "assente"`).
- [ ] **Step 2-4:** come sopra. In `pdf_importer`, verificare che `mesi_precedente` arrivi dove si decide
  `prior_mesi` (mappa §5: `durata_comparato.mesi_del_comparato`, ≈ riga 2774): il valore del lettore vince quando
  c'è, il testo di testa resta il ripiego. Test `test_mesi_dal_lettore_nel_salvataggio` in
  `tests/test_snello_lettore.py` (Task 7).
- [ ] **Step 5: Commit** `feat(lettore): anno precedente con le stesse classi e la sua durata`.

### Task 7: L'innesto nel percorso snello

**Files:**
- Modify: `importers/import_snello/__init__.py` (dopo `_det = deterministico.tentativo(...)`, prima di
  `_importa_modello`, ≈ righe 279-285), `importers/import_snello/deterministico.py` (`_MODO_DA_PARSER` con
  `"lettore": "conti"` o il modo del profilo), `importers/pdf_importer.py` (solo `mesi_precedente`, Task 6)
- Create: `tests/test_snello_lettore.py`

**Interfaces:**
- Consumes: `importa_col_lettore`; `deterministico._esito(nome, bs_raw, ce_raw, stampati)`;
  `_risultato_deterministico(_det, struttura_deterministica(file_path, modo=...), modo, t0)`.
- Produces: `report["fonte"] == "deterministico:lettore"` quando adottato, con `report["lettore_percorso"]` =
  la `diagnostica`; altrimenti il percorso di oggi prosegue come prima e `report["lettore_percorso"]` porta l'esito
  del tentativo (`"non_adottato"` + misura). Interruttore `IMPORT_LETTORE`.

- [ ] **Step 1: Scrivi i test** (sul modello di `tests/test_snello_importa.py` e `tests/test_snello_innesto.py`):
  - `test_lettori_noti_restano_davanti` (un PDF che `xbrl_reso`/`schema_codici` adotta → `importa_col_lettore` mai
    chiamata);
  - `test_lettore_adottato_quando_quadra` (contrapposte sintetica, Qwen finto → `fonte == "deterministico:lettore"`,
    esito `ok`);
  - `test_lettore_non_quadra_prosegue_il_modello` (composizione con un blocco oltre soglia → `_importa_modello`
    chiamato come oggi);
  - `test_interruttore_spento_identico` (`IMPORT_LETTORE=0` → risultato e report uguali a oggi campo per campo,
    escluso il tempo);
  - `test_qwen_in_errore_prosegue` (il finto solleva → nessuna eccezione, percorso di oggi);
  - `test_mesi_dal_lettore_nel_salvataggio` (Task 6).
- [ ] **Step 2: Lancia** con il DB su copia. Expected: FAIL.
- [ ] **Step 3: Implementa** l'innesto (una decina di righe, in un `try` proprio).
- [ ] **Step 4: Lancia** `tests/lettore`, `tests/test_snello_lettore.py`, `tests/test_snello_*.py`,
  `tests/test_lettore_nell_import.py`, `tests/test_durata_comparato.py`, `tests/test_standard_ivcee_parser.py` su DB
  copia, prima (sul BASE) e dopo: dopo = prima + i nuovi, nessun fallito nuovo.
- [ ] **Step 5: Commit** `feat(import): il percorso del lettore dopo i lettori noti, prima del modello`.

### Task 8: Misura e documentazione

**Files:**
- Modify: `tests/corpus/punteggio.py` (branch `feat/punteggio-fase0`, dopo un merge di `feat/fase3-importi`),
  `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` (§11, il percorso del lettore), `docs/import/REGOLE-IMPORT-04-QUADRATURE.md`
  (§13 «prima quadrato»), `CLAUDE.md` («Percorso snello»: una riga sul lettore fra i deterministici e il modello)

**Interfaces:**
- Consumes: `report["import_snello"]["fonte"]`, `report["import_snello"]["lettore_percorso"]` negli esiti.
- Produces: sezione «Percorso del lettore» del punteggio: documenti adottati dal lettore (per tipologia), chiamate
  e voti per documento, secondi (mediana, massimo), documenti salvati sbilanciati prima/dopo, chiusure ≤ 1 €.

- [ ] **Step 1:** estendi `punteggio.py` e i suoi test con esiti finti.
- [ ] **Step 2:** giro 78 × 3, `--paralleli 2`, etichetta `fase3-<sha>`, `--confronta fase2-93432bb`, lanciato dal
  coordinatore con `setsid nohup` (chiavi solo nell'ambiente del processo).
- [ ] **Step 3: Confronta** con `fase2-93432bb` (e `base-fase2-e3455d6`). Ogni documento che peggiora è un difetto
  da spiegare prima di chiudere.
- [ ] **Step 4: Documenta**.
- [ ] **Step 5: Commit** dei due branch.

## Quando la Fase 3 è fatta

- **Quadrato:** dei 9 documenti della Fase 2 il cui PDF quadra ma l'import no (161, 1426, 1440, 1432, 1523, 1531,
  1561, 1566, 1567), almeno 7 si salvano quadrati; i documenti salvati sbilanciati scendono da 14.
- **Non peggio:** macro-voci, KPI, dettagli e anno precedente ≥ `fase2-93432bb` sull'insieme, e su contrapposte e
  conti/colonne in particolare; nessun documento adottato da un lettore noto cambia numeri.
- **Anno precedente:** gli elenchi di conti a due colonne salvano l'anno precedente quando quadra, con la durata
  giusta (nessun esercizio con la durata sbagliata).
- **Stabilità:** documenti instabili fra i giri ≤ 15 (la Fase 2), e nessun instabile nuovo fra quelli adottati dal
  lettore.
- **Costo:** sui documenti adottati, mediana del percorso del lettore ≤ 30 s e massimo ≤ 120 s, voti compresi.

## Fuori da questa fase

La tavola unica per i lettori vecchi e il conflitto A.3/A.4 di `iv_cee_tree.json` (Fase 4); spegnere la pipeline
classica e congelare i 12 parser di layout (Fase 4); `legge` mode sul percorso del lettore (Fase 4); i limiti noti
della Fase 1 (OCR sporco 337/1410, confine per pagina 1429/1432/1410, colonne col ruolo sbagliato 1445/588/161/328,
righe a capo 208): dove impediscono le foglie, il percorso non adotta e il percorso di oggi prosegue.
