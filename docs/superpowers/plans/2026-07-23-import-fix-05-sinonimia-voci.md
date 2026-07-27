# Piano 05 — Motore semantico delle etichette (sinonimia)

> **REVISIONE 2 — 2026-07-27.** Riscritto dopo una seconda analisi con misure sul corpus, poi **corretto
> in cinque punti** dopo una revisione indipendente (§0.6). Il piano è ora **diviso in due fasi**:
>
> | fase | task | dipende da crediti LLM? |
> |---|---|---|
> | **05A — motore deterministico** | 1, 2, 4, 5 (parte deterministica), 6 | **No — eseguibile oggi** |
> | **05B — arbitro Haiku + cache + telemetria** | 3, 5 (`use_llm=True`) | **Sì — bloccato** |
>
> Esegui 05A subito; 05B quando i crediti Anthropic sono di nuovo disponibili. Prerequisito di entrambe:
> **Piano 00A** (probe, baseline versionata, metriche per spazio) — senza quello non esiste un gate.

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development oppure
> superpowers:executing-plans. Steps con checkbox (`- [ ]`).

---

## 0. Perché questo piano viene prima di tutti

### 0.1 L'ipotesi dell'utente, misurata

> «le voci in alcuni bilanci sono scritte in maniera leggermente diversa ma sono la stessa, e l'API
> collegata non capisce che è la stessa, quindi non la mette o la sbaglia e il bilancio non quadra»

Misurato sul corpus (`tests/_label_coverage.py`, 72 PDF di `Test/successSecondo` + `Test/june_sample`,
righe ricostruite per coordinata):

```
righe con importo    : 7.823
righe NON risolte    : 4.557  (58,3%)
massa NON risolta    : 56,5% degli euro presenti nelle righe
dizionario alias     : 65 nodi, 246 alias, media 3,78 alias/nodo
```

Esempi verificati uno per uno con `resolve()` (`tests/_label_diag.py`):

| etichetta | `resolve()` oggi |
|---|---|
| `I. immateriali` (**l'esempio letterale dell'utente**) | `None` |
| `Immob. immateriali` | sp02 ✔ |
| `I - Immobilizzazioni immateriali` | sp02 ✔ |
| `Fornitori` | `None` |
| `Clienti` | `None` |
| `Fatture da ricevere` | `None` |
| `Totale a pareggio` | `None` |
| `Totale passività e netto` | `None` |
| `F.do amm.to impianti generici` | `None` |
| `B.II.1.a.1) (Fondi di ammortamento)` | `None` |
| `C.II.5 quater) Verso altri` | `None` |

**L'ipotesi è corretta.** La precisazione importante è *dove* si rompe: non è (solo) Haiku a non capire
il sinonimo — l'LLM sui documenti interi i sinonimi li capisce, è il motivo per cui è stato introdotto.
Si rompono i **gate deterministici che circondano l'LLM** e che decidono se accettarne il risultato:
ancoraggi di sezione, totali dichiarati, netting dei fondi, reclassificatore contrapposte. Quando uno di
questi non riconosce la grafia, un'estrazione corretta viene **rifiutata** — o una sbagliata viene accettata.

### 0.2 Non esiste una normalizzazione condivisa

Censite **sei** normalizzazioni incompatibili, e la più completa è quasi inutilizzata:

| normalizzatore | cosa fa | usato da |
|---|---|---|
| `iv_cee_hierarchy.normalize` (L41-50) | NFKD + accenti + punteggiatura + collapse | solo `iv_cee_hierarchy` e `mineru_adapter` |
| `standard_ivcee_parser._normalise` (L52-58) | casefold + accenti, **tiene la punteggiatura** | solo quel parser |
| `pdf_extractor_llm._normalize_for_search` (L751-762) | lower + de-spacing + `" - "`, **niente accenti** | solo `find_section_pages` |
| `_declared_control_totals` inline (L3029-3034) | lower + accenti + variante no-spaces, **niente punteggiatura** | solo quella funzione |
| `bilancio_classifier.has()` (L63-65) | lower + no-whitespace, **niente accenti** | tutto il router |
| `situazione_contabile_parser` | **solo `.upper()`** + 3 varianti flat ad hoc | ~200 regole keyword di route C |

Conseguenza già in produzione (verificata): `bilancio_classifier.py:96-97` cerca `"passivita"` e
`"disponibilita liquide"` con una funzione che **non toglie gli accenti** → su testo accentato non
matchano mai → se nessun altro marker regge, il file va a `ROUTE_UNSUPPORTED` e l'import **fallisce**.

E `iv_cee_hierarchy.classify_for_reclassify` — l'adattatore scritto apposta per collegare il resolver
alla route C — **non ha alcun chiamante**: è codice morto. Il "motore unico di classificazione"
descritto in CLAUDE.md oggi non è collegato alla route C.

### 0.3 Cosa era sbagliato nella versione precedente di questo piano

1. **Firma sbagliata.** `resolve()` restituisce un **`Node`**, non una stringa. I test del vecchio piano
   asserivano `resolve(desc) == "sp02_immob_immateriali"`: sarebbero falliti tutti.
2. **Un solo spazio di target.** `resolve()` mappa a una *foglia legale con `db_field`*. Ma i marker che
   rompono l'import non sono voci: `Totale a pareggio`, `Totale attivo`, `Utile d'esercizio`,
   `Stato patrimoniale attivo`, l'intestazione di colonna `Differenza`. Nel tree i nodi `is_total`
   hanno `db_field: null` e per i totali di controllo **non esiste alcun nodo**. Quindi il vecchio 05 non
   poteva assorbire nemmeno il Task 3 del Piano 01 — che è proprio una lista di marker scritta a mano.
3. **Divieto di alias di conto.** Il vecchio piano vietava esplicitamente gli alias di sotto-conto
   («solo grafie della STESSA voce legale»). Ma i file che falliscono sono trial balance il cui testo è
   fatto *solo* di nomi di conto (`Fornitori`, `Erario c/IVA`, `INPS c/contributi dipendenti`,
   `F.do amm.to automezzi`). Il divieto — motivato dal rischio di doppio conteggio in aggregazione flat
   A/B — va mantenuto **come separazione di spazi**, non come rinuncia: i conti vanno in uno spazio
   diverso, usato solo dalla route C.

### 0.4 Prova che è la causa vera, non una teoria

Diagnosi verificate durante l'analisi, ognuna riconducibile a una grafia non riconosciuta:

- **budget_176 / 182** (`Situazione contabile riclassificata dettagliata`). Il log dice
  `Filtered DIFFERENZA/SCOST. columns at x>=115.0 from source page 1`. Il cutoff è
  `min(x delle parole che iniziano per "differenza") − 2` (`pdf_extractor_llm.py:419`). A pagina 1
  esiste **`Differenza` a x=117**: non è l'intestazione della colonna analitica (quella è a x=460) — è la
  voce di legge del CE **«Differenza tra valore e costi di produzione (A−B)»** (art. 2425). Il filtro
  taglia quindi tutto a destra di x=115 e **cancella l'intera pagina**, importi e descrizioni. Questa è
  una collisione di etichette pura, e **non è la diagnosi che il Piano 04 aveva scritto** (vedi Piano 04
  rev. 2026-07-27).
- **budget_365 / 342 / 435 / 138**. Errore: *«i totali Attivo e Passivo stampati coincidono, ma le
  componenti patrimoniali estratte non li ricostruiscono»*. Sul 365 il log mostra: CoGe-LLM estrae
  590.071 su 1.119.894 dichiarati (`~529.823 di conti non classificati`), il best-effort deterministico
  lascia `residuo attivo=685.283`. Le etichette di quel documento sono `Fornitori`, `Clienti`,
  `Fatture da ricevere`, `Banche c/anticipi su fattura`, `Dipendenti c/retribuzioni`,
  `F.do amm.to <cespite>` — **tutte irrisolte da `resolve()`** (verificato).
- **`_is_fondo_amm`** (`situazione_contabile_parser.py:3274`) è una congiunzione di substring su testo
  solo-`upper()` che governa **l'intero netting dei fondi**, quindi il pareggio di tutta la route C.
  `F.di ammor.to`, `Fdo amm` non matchano → fondo non nettato → attivo lordo vs passivo gonfio → plug →
  `QUADRATURA MASCHERATA` → import rifiutato.

### 0.6 Correzioni dalla revisione indipendente (2026-07-27) — leggere prima di implementare

Cinque difetti di **questa** versione del piano, tutti confermati:

1. **La sola tokenizzazione non basta.** Il vecchio Task 2(e) diceva «match tokenizzato, così `cassa` non
   matcha `cassa previdenziale`». Falso: `cassa` e `titoli` **sono** token interi in «Cassa previdenziale»
   e «Debiti rappresentati da titoli». Serve un **punteggio di specificità** (§1.1), non un confronto
   booleano. È il problema simmetrico e altrettanto grave del mancato riconoscimento: la
   **corrispondenza falsa**, che non lascia residuo e quindi non fa scattare nessun gate.
2. **`Risultato del periodo` → `__utile` è sbagliato**: può essere una **perdita**. Il marker è
   `__risultato`; il segno lo decide il contesto (parola `perdita`, importo negativo, posizione rispetto
   al pareggio). Test corretto nel Task 2.
3. **Il path civilistico non va buttato.** `normalize_label` toglie la numerazione iniziale — giusto per
   il match — ma `B.II.1.a` / `C.II.5-quater` è **informazione**: va estratta in un `path_hint` separato e
   usata per disambiguare e per validare la gerarchia. Non si perde, si separa.
4. **La chiave di cache deve essere versionata.** `space|label` non basta: due documenti diversi possono
   dare significati diversi alla stessa grafia. Chiave minima:
   `space | statement(bs/ce) | side | label_normalizzata | versione_tassonomia | versione_prompt`.
   Senza `versione_prompt`, cambiare il prompt lascia in cache risposte prodotte da un prompt diverso.
5. **Il target `< 30%` non è una metrica valida** e va cancellato: la misura attuale (58,3%) mescola voci,
   conti, marcatori e prosa di nota integrativa in un unico denominatore. Il Piano 00A Task 4 la rifà per
   spazio; i target di questo piano si scrivono **dopo** quella misura, uno per spazio.

### 0.5 Conseguenza sull'ordine di esecuzione

I Piani 01 e 03 aggiungono **altre liste di stringhe letterali scritte a mano** (marker `utile …`,
keyword `RISCHI|ONERI|CONTROVERS|GARANZI|CAUSE`, …) per gli stessi casi. Eseguiti prima del 05, quelle
liste vanno scritte **due volte**: a mano ora e nel dizionario poi. **Il 05 va per primo**, e 01 T3 /
03 T1 diventano suoi consumatori. Vedi Piano 00 rev. 2026-07-27 §4.

---

## 1. Architettura bersaglio

Nuovo modulo unico **`importers/label_semantics.py`**. Un solo normalizzatore, **tre spazi di target**,
un dizionario che cresce, un arbitro LLM con cache persistente.

```
                       label_semantics.py
  ┌──────────────────────────────────────────────────────────────┐
  │ normalize_label(s)      ← UNICA forma canonica del sistema    │
  │                                                              │
  │ classify_label(label, space, side=None, use_llm=False)       │
  │        │                                                     │
  │        ├── space="voce"    → db_field  (sp01..18/ce01..20)   │  albero IV-CEE (esistente)
  │        ├── space="marker"  → __tot_attivo | __tot_passivo |  │  NUOVO
  │        │                     __pareggio | __utile |          │
  │        │                     __perdita  | __sez_sp_attivo |  │
  │        │                     __sez_sp_passivo | __sez_ce |   │
  │        │                     __fine_sp  | __col_scostamento  │
  │        └── space="conto"   → db_field + RUOLO contabile:     │  NUOVO (solo route C)
  │                              contra_immat | contra_mat |     │
  │                              contra_crediti | fondo_rischi | │
  │                              risultato | totale              │
  │                                                              │
  │ dizionario  →  cache JSON  →  arbitro Haiku (1 batch/doc)    │
  └──────────────────────────────────────────────────────────────┘
```

**Perché tre spazi e non uno.** Sono tre domande contabili diverse e hanno rischi diversi:
- *voce*: "che riga di legge è?" — deve restare **solo legale**, altrimenti l'aggregazione flat A/B
  doppio-conta (vincolo esistente del tree, corretto, si mantiene);
- *marker*: "questa riga è un totale di controllo / un'intestazione di sezione?" — non ha `db_field`,
  serve ai gate, ed è oggi la causa dei falsi rigetti;
- *conto*: "questo conto del piano dei conti dove va, e ha natura rettificativa?" — vale solo per la
  route C, dove il documento non contiene voci di legge. Il **ruolo** è la parte che oggi manca del
  tutto: `F.do amm.to automezzi` non è "un debito", è una **rettifica dell'attivo**, e sbagliarlo
  sbilancia il foglio.

**Regola d'oro (vincolo di sicurezza).** `classify_label` restituisce sempre una `LabelHit` con
`confidence` e `source` (`dizionario` | `cache` | `llm` | `nessuno`). **Nessun chiamante può usare un hit
`llm` per scrivere un importo senza che il gate contabile a valle lo confermi.** Il layer amplia la
COPERTURA del riconoscimento; non allenta nessun controllo di quadratura.

### 1.1 Specificità del match — il difetto simmetrico (corrispondenze FALSE)

Metà del problema è "non riconosce"; l'altra metà è **"riconosce la cosa sbagliata"**, ed è più pericolosa
perché **non lascia residuo**: la massa finisce nel campo sbagliato, il bilancio quadra lo stesso e nessun
gate se ne accorge. Difetti reali dell'indice attuale:

| etichetta | oggi risolve a | corretto |
|---|---|---|
| `Cassa previdenziale` | sp09 (alias `cassa`) | un debito previdenziale (sp16f) |
| `Debiti rappresentati da titoli` | C.III (alias `titoli`) | sp16c obbligazioni |
| `Fornitori c/anticipi` | sp16 (alias `fornitori c/`) | un **credito** (acconti a fornitori) |

Non si risolve tokenizzando (`cassa` è un token). Il match va **punteggiato**, e vince il punteggio più
alto solo se supera il secondo di un margine:

```
score = w_esatto      * (label == alias)                     # match esatto sulla forma canonica
      + w_copertura   * len(alias_token) / len(label_token)  # quanta parte dell'etichetta e' spiegata
      + w_path        * (path_hint compatibile col nodo)     # B.II.1.a -> deve cadere sotto B.II
      + w_lato        * (side coerente)                      # la COLONNA e' ground truth
      + w_parent      * (parent gia' risolto e compatibile)  # gerarchia della fonte
      - w_residuo     * (token dell'etichetta non spiegati)  # 'previdenziale' non spiegato da 'cassa'
```

Il termine **`- w_residuo`** è quello che salva i tre casi in tabella: `cassa` spiega 1 token su 2 di
`cassa previdenziale`, quindi il match perde contro un alias previdenziale e, in assenza di alternative,
scende sotto la soglia → `None` (che è un esito **onesto**: lascia residuo, il gate lo vede).

**Regola:** sotto soglia si restituisce `None`, mai il "meno peggio". Un irrisolto è misurabile; una
classificazione sbagliata no.

---

## 2. Vincoli globali

Quadro generale §7. In più:

- L'arbitro LLM è chiamato **al massimo una volta per documento** (batch di tutte le etichette irrisolte)
  e **solo** se `ANTHROPIC_API_KEY` è presente e valida. Senza chiave il sistema resta deterministico
  (normalizzazione + dizionario): **nessuna regressione in ambiente no-key**.
- **Il layer non tocca gli importi.** Sposta massa solo attraverso i chiamanti esistenti, che restano
  soggetti ai loro gate.
- Ogni Task che migra un chiamante deve dimostrare **zero variazioni** sui file che già importano
  puliti, non solo che i file bersaglio migliorano.
- **Nota ambientale 2026-07-27:** i crediti Anthropic dell'account sono esauriti (verificato:
  `Error code: 400 — Your credit balance is too low`). I Task 1, 2, 4, 5, 6 sono interamente
  deterministici e verificabili oggi. Il **Task 3 (arbitro LLM)** e ogni validazione end-to-end su
  route A/B **non sono eseguibili finché i crediti non vengono ricaricati**: implementarli con LLM
  mockato e marcare la verifica su corpus come pendente.

---

### Task 1: `normalize_label` — una sola forma canonica

**Files:**
- Create: `importers/label_semantics.py`
- Test: `tests/test_label_semantics_normalize.py`

**Interfaces:**
- Produces: `normalize_label(s: str) -> str` — minuscolo, senza accenti (NFKD), senza numerazione di
  voce iniziale (romani / lettere di sezione / arabi / path puntato `B.II.1.a`), senza spaziatura
  lettera-per-lettera (`S T A T O` → `stato`), abbreviazioni comuni espanse, punteggiatura → spazio,
  spazi collassati. È l'unica forma canonica del sistema; ogni altro normalizzatore verrà fatto
  delegare qui (Task 6).

- [ ] **Step 1: test che fallisce**

```python
# tests/test_label_semantics_normalize.py
from importers.label_semantics import normalize_label as N


def test_toglie_numerazione_di_voce_e_separatori():
    assert N("I - Immobilizzazioni immateriali") == "immobilizzazioni immateriali"
    assert N("B.I) Immob. immateriali") == "immobilizzazioni immateriali"
    assert N("C.II.5 quater) Verso altri") == "verso altri"
    assert N("B.II.1.a.1) (Fondi di ammortamento)") == "fondi di ammortamento"


def test_normalizzazione_non_inventa_parole():
    # 'I. immateriali' resta 'immateriali': l'espansione e' compito del DIZIONARIO (Task 2),
    # non della normalizzazione. Vedi test_alias in test_label_semantics_voce.py.
    assert N("I. immateriali") == "immateriali"


def test_espande_abbreviazioni_comuni():
    assert N("Crediti v/clienti") == "crediti verso clienti"
    assert N("F.do amm.to fabbricati") == "fondo ammortamento fabbricati"
    assert N("F.di ammor.to automezzi") == "fondo ammortamento automezzi"
    assert N("Erario c/IVA") == "erario conto iva"


def test_toglie_accenti_e_collassa_spazi():
    assert N("Totale   attività ") == "totale attivita"
    assert N("TOTALE A T T I V I T A'") == "totale attivita"
    assert N("TOTALE STATO PATRIMONIALE - PASSIVO") == "totale stato patrimoniale passivo"


def test_non_confonde_voci_diverse():
    assert N("immateriali") != N("materiali")
    assert N("Debiti verso fornitori") != N("Crediti verso clienti")
```

- [ ] **Step 2: verificare che fallisca** — `python -m pytest tests/test_label_semantics_normalize.py -q`
  → `ModuleNotFoundError: importers.label_semantics`.

- [ ] **Step 3: implementare.** Punti di attenzione, tutti già emersi da bug reali del repo:
  - **de-spacing lettera-per-lettera**: `TOTALE A T T I V I T A` esiste in 6 documenti del corpus
    (`Totale a t t i v i t á Totale p a s s i v i t á` su una sola riga). Riusare la logica di
    `pdf_extractor_llm._normalize_for_search` (L751-762), che è l'unica che lo fa.
  - **`" - "` collassato**: bug budget_585 (`TOTALE STATO PATRIMONIALE - PASSIVO`), già corretto in
    `_normalize_for_search`; deve valere qui per tutti.
  - **numerazione iniziale**: romani `I..X`, lettere `A..E`, arabi con `bis`/`ter`/`quater`, path puntato
    `B.II.1.a.1)`. Attenzione a NON mangiare parole che iniziano per `I`/`V`/`X` (`IVA`, `Immobili`):
    la numerazione richiede un separatore (`.`/`)`/`-`) **oppure** di essere seguita da spazio ed essere
    un romano valido isolato.
  - **abbreviazioni**: `immob`, `immobilizz` → `immobilizzazioni`; `f.do`/`f/do`/`f.di`/`fdo` → `fondo`;
    `amm.to`/`ammor.to`/`amm.nto`/`amm` → `ammortamento`; `v/` → `verso `; `c/` → `conto `;
    `sval` → `svalutazione`; `acc.to` → `accantonamento`.
  - **niente `/` residuo**: dopo l'espansione di `v/` e `c/`, la punteggiatura restante va a spazio.
  - Deve essere **idempotente**: `N(N(x)) == N(x)`. Aggiungere l'assert al test.

- [ ] **Step 4: verificare** — `python -m pytest tests/test_label_semantics_normalize.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add importers/label_semantics.py tests/test_label_semantics_normalize.py
git commit -m "feat(sinonimi): normalize_label - unica forma canonica delle etichette"
```

---

### Task 2: i tre spazi di target + dizionario

**Files:**
- Modify: `importers/label_semantics.py`
- Create: `data/label_dictionary.json`
- Modify: `data/iv_cee_tree.json` (arricchimento alias dello spazio *voce*)
- Test: `tests/test_label_semantics_spaces.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class LabelHit:
      target: str              # db_field, oppure "__tot_attivo" / "__risultato" / ...
      role: Optional[str]      # solo space="conto": contra_immat|contra_mat|contra_crediti|
                               #                     fondo_rischi|risultato|totale|None
      level: Optional[str]     # livello IV-CEE del nodo colpito (1=lettere .. 4=a/b/c)
      specificity: float       # punteggio §1.1 — quanta parte dell'etichetta e' spiegata
      confidence: str          # "alta" | "media" | "bassa"
      source: str              # "dizionario" | "cache" | "llm"
      reason: str              # perche' (alias colpito, path_hint usato, chi ha perso) — telemetria

  @dataclass(frozen=True)
  class ParsedLabel:
      canonical: str           # normalize_label(...)
      path_hint: Optional[str] # "B.II.1.a" / "C.II.5-quater" — ESTRATTO, non buttato via
      is_total: bool           # la riga si autodichiara totale/subtotale

  parse_label(label) -> ParsedLabel
  classify_label(label, space="voce", side=None, statement=None,
                 path_hint=None, parent=None, use_llm=False) -> Optional[LabelHit]
  ```
  `parent` è il `LabelHit` della riga-genitore già risolta (quando il chiamante la conosce): serve al
  termine `w_parent` del punteggio e a validare la gerarchia contro i subtotali della fonte.
  `space="voce"` delega all'albero esistente (`iv_cee_hierarchy.resolve`) e ne **converte il `Node` in
  `db_field`** — è questo che ripara il difetto §0.3 punto 1.

- [ ] **Step 1: test che fallisce**

```python
# tests/test_label_semantics_spaces.py
from importers.label_semantics import classify_label as C


def test_voce_grafie_diverse_stessa_voce():
    for desc in ["I. immateriali", "I - Immobilizzazioni immateriali", "Immob. immateriali",
                 "B.I IMMOBILIZZAZIONI IMMATERIALI", "Totale immobilizzazioni immateriali"]:
        hit = C(desc, space="voce", side="attivo")
        assert hit is not None and hit.target == "sp02_immob_immateriali", desc


def test_marker_totali_di_controllo():
    for desc, want in [
        ("Totale attivo", "__tot_attivo"),
        ("TOTALE ATTIVITA'", "__tot_attivo"),
        ("TOTALE STATO PATRIMONIALE - ATTIVO", "__tot_attivo"),
        ("Stato patrimoniale attivo", "__sez_sp_attivo"),
        ("Totale passività e netto", "__tot_passivo"),
        ("Totale a pareggio", "__pareggio"),
        ("Totale a quadratura", "__pareggio"),
        ("Utile d'esercizio", "__utile"),
        ("Utile Stato Patrimoniale", "__utile"),
        ("Perdita dell'esercizio", "__perdita"),
        ("Differenza", "__col_scostamento"),
        ("Scost.", "__col_scostamento"),
    ]:
        hit = C(desc, space="marker")
        assert hit is not None and hit.target == want, desc


def test_risultato_senza_segno_non_e_un_utile():
    """'Risultato del periodo' NON dice se e' utile o perdita: il marker e' neutro,
    il segno lo decide il chiamante (parola 'perdita', importo negativo, lato)."""
    for desc in ["Risultato del periodo", "Risultato d'esercizio",
                 "Risultato dell'esercizio"]:
        hit = C(desc, space="marker")
        assert hit is not None and hit.target == "__risultato", desc


def test_specificita_evita_le_corrispondenze_false():
    """Il difetto simmetrico: non 'non riconosce', ma 'riconosce la cosa sbagliata'.
    Una classificazione errata non lascia residuo e nessun gate la vede."""
    assert C("Cassa previdenziale", space="conto", side="passivo").target != \
        "sp09_disponibilita_liquide"
    assert C("Debiti rappresentati da titoli", space="conto", side="passivo").target != \
        "sp08_attivita_finanziarie"
    # acconti A fornitori sono un CREDITO, non un debito
    assert C("Fornitori c/anticipi", space="conto", side="attivo").target.startswith("sp06")


def test_sotto_soglia_ritorna_none_non_il_meno_peggio():
    assert C("Voce completamente estranea xyz", space="conto", side="attivo") is None


def test_path_hint_estratto_non_buttato():
    from importers.label_semantics import parse_label
    p = parse_label("C.II.5 quater) Verso altri")
    assert p.canonical == "verso altri" and p.path_hint == "C.II.5-quater"
    assert parse_label("B.II.1.a.1) (Fondi di ammortamento)").path_hint == "B.II.1.a.1"


def test_marker_non_confonde_la_voce_di_legge_con_l_intestazione_di_colonna():
    # budget_176: "Differenza tra valore e costi di produzione (A-B)" e' una VOCE del CE
    # (art. 2425), NON l'intestazione della colonna analitica "Differenza".
    hit = C("Differenza tra valore e costi di produzione (A-B)", space="marker")
    assert hit is None or hit.target != "__col_scostamento"
    voce = C("Differenza tra valore e costi di produzione (A-B)", space="voce")
    assert voce is not None


def test_conto_ruolo_contabile():
    for desc, target, role in [
        ("Fornitori", "sp16_debiti_breve", None),
        ("Fatture da ricevere", "sp16_debiti_breve", None),
        ("Clienti", "sp06_crediti_breve", None),
        ("Banche c/anticipi su fattura", "sp16_debiti_breve", None),
        ("Dipendenti c/retribuzioni", "sp16_debiti_breve", None),
        ("Erario c/IVA", "sp16_debiti_breve", None),
        ("F.do amm.to automezzi", "sp03_immob_materiali", "contra_mat"),
        ("F.do amm.to costi di impianto", "sp02_immob_immateriali", "contra_immat"),
        ("Fondo svalutazione crediti", "sp06_crediti_breve", "contra_crediti"),
        ("Fondo indennità suppletiva di clientela", "sp14_fondi_rischi", "fondo_rischi"),
        ("Fondo manutenzioni cicliche", "sp14_fondi_rischi", "fondo_rischi"),
    ]:
        hit = C(desc, space="conto", side="passivo" if "sp1" in target else None)
        assert hit is not None, desc
        assert hit.target == target and hit.role == role, desc


def test_fondo_rischi_su_crediti_e_contra_non_passivo():
    # regola contabile: SVALUT/RISCHI + CREDIT -> rettifica di C.II, non un fondo del passivo
    hit = C("Fondo rischi su crediti", space="conto", side="passivo")
    assert hit.target == "sp06_crediti_breve" and hit.role == "contra_crediti"


def test_spazi_separati_non_si_contaminano():
    # un conto NON deve essere risolvibile nello spazio 'voce' (doppio conteggio in A/B)
    assert C("F.do amm.to automezzi", space="voce") is None
    assert C("Erario c/IVA", space="voce") is None
```

- [ ] **Step 2: verificare che fallisca.**

- [ ] **Step 3: implementare.**

  (a) `data/label_dictionary.json` con due sezioni, `marker` e `conto`, ognuna
  `{ "<forma normalizzata>": {"target": "...", "role": null} }`. Popolarlo **dalle grafie realmente
  osservate nel corpus**, non a fantasia: la lista si ottiene con
  `python tests/_label_coverage.py Test/successSecondo Test/june_sample/success Test/june_sample/errori`,
  che stampa le etichette non risolte **ordinate per numero di documenti** in cui compaiono. Iniziare dalle
  prime 60 (quelle presenti in ≥2 documenti): sono grafie di gestionale, non casi singoli.

  (b) Lo spazio `voce` delega a `iv_cee_hierarchy.resolve` e restituisce `node.db_field`. Aggiungere al
  tree gli alias mancanti **di livello legale** emersi dalla misura: `"immateriali"`, `"materiali"`,
  `"finanziarie"` per B.I/B.II/B.III (grafia "schema secco" `I. immateriali`), `"verso altri"`,
  `"fatture da ricevere"` come alias di D.7 **solo** se il tree resta legale — se una grafia è di conto e
  non di voce, va nello spazio `conto`, non nel tree.

  (c) Lo spazio `conto` è **prefix-agnostico e side-aware**: la colonna resta ground truth per il lato
  (regola già consolidata nel repo: `resolve` non deve ribaltare il lato di una riga di trial balance).
  Il `role` è la novità:
  - `contra_immat` / `contra_mat`: fondo ammortamento o fondo svalutazione **di immobilizzazioni** →
    netta sp02/sp03;
  - `contra_crediti`: `SVALUT`/`RISCHI` **+** `CREDIT` → netta sp06 (C.II è netto per legge);
  - `fondo_rischi`: `RISCHI`/`ONERI`/`CONTROVERS`/`GARANZI`/`CAUSE`/`INDENNITA SUPPLETIVA`/
    `SPESE FUTURE`/`MANUTENZIONI CICLICHE`/`QUIESCENZA` **senza** `CREDIT` → sp14, **non** si netta;
  - `risultato`: utile/perdita d'esercizio (escluso `PORTAT`/`NUOVO`/`PRECEDENT`);
  - `totale`: riga di totale/subtotale → **da non sommare** (oggi `_be_reclassify` filtra con
    `'TOTALE' in d`, che manca `Tot.` e `T O T A L E`).

  (d) **Disambiguazione marker vs voce (obbligatoria, è il bug budget_176).** Un marker di *intestazione
  di colonna* matcha SOLO se l'etichetta normalizzata è **uguale** al marker o lo supera di ≤1 token
  ausiliario; mai per substring. `differenza tra valore e costi di produzione` **non** è
  `__col_scostamento`. Scrivere questa regola come funzione esplicita, non come ordine dei controlli.

  (e) Il match negli spazi `voce`/`conto` è **punteggiato** secondo §1.1 — non booleano e non solo
  tokenizzato. Sotto soglia: `None`. Il punteggio, l'alias colpito e chi ha perso finiscono in
  `LabelHit.reason` (telemetria).

- [ ] **Step 4: verificare** — `python -m pytest tests/test_label_semantics_spaces.py -q` → PASS.
  Poi ri-misurare la copertura **per spazio** (Piano 00A Task 4 deve essere già fatto):
  ```bash
  python tests/_label_coverage.py Test/successSecondo Test/june_sample/success Test/june_sample/errori
  ```
  **BASELINE MISURATA (2026-07-27, 72 documenti, resolver legacy)** — Piano 00A Task 4 eseguito:

  | spazio | righe | irrisolte | % righe | % massa |
  |---|---:|---:|---:|---:|
  | `marker` | 311 | 311 | **100,0%** | **100,0%** |
  | `account` | 5.914 | 3.725 | **63,0%** | 68,5% |
  | `legal` | 69 | 29 | **42,0%** | 44,5% |

  Il dato che conta è il primo: **il resolver non ha affatto lo spazio `marker`**, quindi non riconosce
  *nessuno* dei totali di controllo — `totale a pareggio` (7 doc), `utile d'esercizio` (6 doc),
  `totale a t t i v i t á` (6 doc), `differenza tra valore e costi di produzione` (7 doc). Sono
  esattamente le righe che pilotano il preflight, il netting e la selezione dei candidati: è **qui** che
  un'estrazione corretta viene rifiutata.
  *Nota sull'imprecisione nota:* le righe legali senza path in testa finiscono nell'insieme `account`
  (il campione `legal` è piccolo). Non importa per l'uso che se ne fa — la metrica serve a confrontare
  PRIMA e DOPO con lo stesso strumento, non a dare un valore assoluto.

  ⚠️ **Il vecchio target unico "< 30%" è cancellato**: la misura da cui derivava (58,3%) mescola voci
  civilistiche, conti, marcatori e prosa di nota integrativa in un denominatore solo, ed è quindi
  sovrastimata e non confrontabile. I target si fissano **dopo** la prima misura per spazio, così:
  - `marker`: **≥ 95%** risolto — sono poche decine di grafie e sono quelle che bloccano l'import;
  - `legal`: **≥ 90%** — il perimetro è chiuso dall'art. 2424/2425;
  - `account`: nessun target assoluto (il piano dei conti è aperto); si misura la **riduzione** rispetto
    alla baseline 00A e si guarda l'effetto contabile a valle (residuo non classificato per documento).

  Criterio di uscita che conta davvero, perché è contabile e non lessicale: **il residuo non classificato
  dei file bersaglio scende**, misurato con `tests/_prod_route_c_runner.py`. Le percentuali di copertura
  sono diagnostica, non accettazione.

- [ ] **Step 5: Commit**

```bash
git add importers/label_semantics.py data/label_dictionary.json data/iv_cee_tree.json \
        tests/test_label_semantics_spaces.py
git commit -m "feat(sinonimi): tre spazi di target (voce/marker/conto) + ruolo contabile dei conti"
```

---

### Task 3: arbitro Haiku con cache persistente

> **BLOCCATO sull'ambiente:** i crediti Anthropic sono esauriti. Implementare e testare con LLM
> **mockato** (nessuna chiamata reale nei test, come da vincolo CI); la verifica su corpus resta
> pendente e va annotata come tale nel commit.

**Files:**
- Modify: `importers/label_semantics.py`
- Create: `data/label_alias_cache.json` (inizialmente `{}`)
- Test: `tests/test_label_semantics_llm.py`

**Interfaces:**
- Produces: `resolve_labels_llm(labels: list[str], space: str, side=None) -> dict[str, Optional[dict]]`
  — mappa etichetta-normalizzata → `{"target": ..., "role": ...}` o `None`. Legge/scrive
  `data/label_alias_cache.json`. Chiama Haiku **una volta** per il batch delle sole etichette non in
  cache. Consumata da `classify_label(..., use_llm=True)`.

**Economia.** È il punto in cui l'intuizione dell'utente («l'LLM capisce che è la stessa voce») viene
messa a sistema **senza pagarla ogni volta**: la prima volta che il sistema incontra
`Immob.ni immateriali nette` chiede a Haiku, ottiene `sp02_immob_immateriali`, lo scrive in cache; da lì
in poi quella grafia è deterministica e gratuita. Costo marginale → 0; copertura → cresce da sola.

- [ ] **Step 1: consultare la skill `claude-api`** per la firma corrente di `client.messages.create` e i
pattern tool-use, **poi** scrivere i test (LLM iniettabile):

```python
# tests/test_label_semantics_llm.py
import json
from importers import label_semantics as LS


def test_cache_hit_non_chiama_llm(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({
        "conto|immobilizzazioni immateriali nette": {"target": "sp02_immob_immateriali", "role": None}
    }), encoding="utf-8")
    monkeypatch.setattr(LS, "_CACHE_PATH", str(cache))
    called = {"n": 0}
    monkeypatch.setattr(LS, "_llm_call", lambda labels, space, side: (called.__setitem__("n", called["n"] + 1) or {}))
    out = LS.resolve_labels_llm(["immobilizzazioni immateriali nette"], space="conto", side="attivo")
    assert out["immobilizzazioni immateriali nette"]["target"] == "sp02_immob_immateriali"
    assert called["n"] == 0


def test_chiama_llm_solo_per_le_mancanti_e_persiste(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"; cache.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(LS, "_CACHE_PATH", str(cache))

    def _fake(labels, space, side):
        assert labels == ["ratei e risconti attivi vari"]
        return {"ratei e risconti attivi vari": {"target": "sp10_ratei_risconti_attivi", "role": None}}

    monkeypatch.setattr(LS, "_llm_call", _fake)
    out = LS.resolve_labels_llm(["ratei e risconti attivi vari"], space="conto", side="attivo")
    assert out["ratei e risconti attivi vari"]["target"] == "sp10_ratei_risconti_attivi"
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["conto|ratei e risconti attivi vari"]["target"] == "sp10_ratei_risconti_attivi"


def test_target_non_valido_viene_scartato(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"; cache.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(LS, "_CACHE_PATH", str(cache))
    monkeypatch.setattr(LS, "_llm_call",
                        lambda l, s, side: {l[0]: {"target": "sp99_inventato", "role": None}})
    out = LS.resolve_labels_llm(["voce strana"], space="conto")
    assert out["voce strana"] is None                      # validato contro i target ammessi
    assert json.loads(cache.read_text(encoding="utf-8")) == {}   # e NON messo in cache


def test_no_key_ritorna_none_senza_errore(tmp_path, monkeypatch):
    cache = tmp_path / "cache.json"; cache.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(LS, "_CACHE_PATH", str(cache))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert LS.resolve_labels_llm(["voce ignota xyz"], space="conto")["voce ignota xyz"] is None
```

- [ ] **Step 2: verificare che fallisca.**

- [ ] **Step 3: implementare.** Requisiti non negoziabili:
  - **chiave di cache versionata**:
    `f"{space}|{statement}|{side}|{label_normalizzata}|{TAXONOMY_VERSION}|{PROMPT_VERSION}"`.
    `space|label` **non basta**: la stessa grafia ha significati diversi per prospetto e per lato, e senza
    `PROMPT_VERSION` una modifica al prompt lascerebbe in cache risposte prodotte da un prompt diverso —
    silenziosamente. `PROMPT_VERSION` è una costante del modulo da incrementare a ogni modifica del prompt;
  - **una sola chiamata per documento**, con **contesto**: al modello si manda, per ogni etichetta
    irrisolta, `{label, path_hint, sezione, lato, importo, etichetta_padre, vicini}` — non la sola stringa.
    Il contesto è ciò che distingue «Fornitori» (debito) da «Fornitori c/anticipi» (credito) e
    «Risultato del periodo» utile da perdita;
  - il modello **deve poter dire "non so"** (`null`): un'astensione è un esito valido e produce residuo
    misurabile; una risposta inventata produce massa nel campo sbagliato che nessun gate intercetta;
  - **telemetria**: log strutturato degli irrisolti e degli hit a `confidence="bassa"` (etichetta, spazio,
    documento, target scelto) — è la lista di lavoro per far crescere il dizionario deterministico e
    ridurre nel tempo le chiamate;
  - **validazione dell'output**: il `target` deve appartenire all'insieme ammesso per quello spazio
    (`db_field` legali dal tree per `voce`/`conto`; i `__marker` per `marker`); il `role` a un enum
    chiuso. Fuori insieme → `None`, **e non si scrive in cache**;
  - **solo i risolti vanno in cache**, mai i `None` (una grafia oggi ignota può diventare nota domani
    quando il dizionario cresce);
  - qualunque eccezione (rete, credito esaurito, 429) → `{}` e `logger.warning`: il chiamante degrada al
    deterministico. **Mai propagare l'errore all'import.**
  - scrittura della cache **atomica** (file temporaneo + `os.replace`): più import concorrenti non devono
    corromperla.

- [ ] **Step 4: verificare** — `python -m pytest tests/test_label_semantics_llm.py -q` → PASS (4).

- [ ] **Step 5: Commit**

```bash
git add importers/label_semantics.py data/label_alias_cache.json tests/test_label_semantics_llm.py
git commit -m "feat(sinonimi): arbitro Haiku con cache persistente e validazione dei target (costo marginale ->0)

Verifica su corpus PENDENTE: crediti Anthropic esauriti al 2026-07-27."
```

---

### Task 4: migrare `_declared_control_totals` allo spazio `marker`

> Questo Task **assorbe interamente il Task 3 del Piano 01** (che va quindi cancellato da quel piano).

**Files:**
- Modify: `importers/pdf_extractor_llm.py` (`_declared_control_totals`, `_section_heading_total`)
- Test: `tests/test_declared_totals_sinonimi.py`

- [ ] **Step 1: test che fallisce** — costruire testi **sintetici** (mai copiare PDF del corpus) con le
grafie osservate e verificare che `_declared_control_totals` legga attivo/passivo/pareggio/utile/perdita:
`TOTALE ATTIVITA'` / `TOTALE STATO PATRIMONIALE - ATTIVO` / `Totale passività e netto` /
`Totale a pareggio` / `UTILE STATO PATRIMONIALE` / `Utile Esercizio` (senza apostrofo) /
`Risultato del periodo` / `Stato patrimoniale attivo 1.116.259,44` sulla stessa riga.

- [ ] **Step 2: verificare che fallisca.**

- [ ] **Step 3: implementare.** Sostituire le liste letterali (L3068-3113) con: per ogni riga del testo,
`classify_label(riga_senza_importi, space="marker")`. Mantenere invariati:
  - lo **scoping SP vs CE** (`low.find("conto economico")`) — anzi renderlo un attributo del marker
    (`__utile` letto in sezione CE ≠ `__utile` letto in sezione SP), che è più robusto del `find` attuale;
  - `_largest_after` per la lettura del numero;
  - il comportamento su testo garbled (`_text_layer_is_garbled`): i totali dichiarati di un layer corrotto
    non devono pilotare nulla (regola già in produzione, non toccarla).

- [ ] **Step 4: verificare + regressione.**
```bash
python -m pytest tests/test_declared_totals_sinonimi.py -q
python tests/_prod_route_c_runner.py Test/sez-contrapposte      # nessun peggioramento
python tests/_import_probe.py "Test/june_sample/errori/budget_395_BILANCIO AGRIMIX SAS  31.12.2025 definitivo.pdf" standard
```
Attenzione al rischio: ampliare i marker può far agganciare a `_largest_after` il numero **sbagliato**
(è il bug budget_337, corretto a suo tempo con lo scoping). Il gate è: i file che oggi leggono
correttamente i totali devono leggere **gli stessi numeri**. Aggiungere al test un caso in cui il CE è
più grande dello SP.

- [ ] **Step 5: Commit**

```bash
git add importers/pdf_extractor_llm.py tests/test_declared_totals_sinonimi.py
git commit -m "fix(sinonimi): totali dichiarati letti dal layer semantico invece che da liste letterali"
```

---

### Task 5: migrare il netting fondi e il reclassificatore route C allo spazio `conto`

> Questo Task **assorbe il Task 1 del Piano 03** (le due liste di keyword `_is_fondo_crediti` /
> `_is_fondo_rischi_oneri`), che va quindi riscritto come consumatore. Il resto del Piano 03
> (l'aritmetica di `_apply_contra_to_bs` e il Task 3 su budget_281) resta suo.

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (`_is_fondo_amm`, `_contra_classify`,
  `_be_reclassify`, `cl_att`/`cl_pas`, `_strip_result`)
- Test: `tests/test_route_c_ruoli_conto.py`

- [ ] **Step 1: test che fallisce** — su descrizioni sintetiche, verificare che il ruolo sia corretto per:
`F.do amm.to automezzi`, `F.di ammor.to fabbricati`, `Fdo amm impianti`, `Fondo svalutazione crediti`,
`F.di rischi su crediti`, `Fondo indennità suppletiva di clientela`, `Fondo manutenzioni cicliche`,
`Tot. attività`, `T O T A L E   P A S S I V O`.

- [ ] **Step 2: verificare che fallisca** (oggi `_is_fondo_amm` manca `F.di ammor.to`/`Fdo amm`;
`_be_reclassify` manca `Tot.`).

- [ ] **Step 3: implementare.** `_is_fondo_amm` e le catene `_kw_match` diventano **wrapper** su
`classify_label(desc, space="conto", side=...)`:
  - `role in ("contra_immat", "contra_mat")` → netting immobilizzazioni (comportamento attuale);
  - `role == "contra_crediti"` → netta sp06 (nuovo — è la regola contabile del Piano 03);
  - `role == "fondo_rischi"` → sp14, **non** si netta;
  - `role == "totale"` → riga saltata;
  - `role == "risultato"` → `_strip_result`.
  Attivare `use_llm=True` **solo** in `_be_reclassify`, per le sole righe che il deterministico lascia
  irrisolte, **prima** di plug-are il residuo. Un batch per documento.
  **Vincolo:** il lato (attivo/passivo) resta quello della COLONNA, mai quello dedotto dalla descrizione
  (regola già consolidata: provata e ritirata in passato perché regrediva file puliti).

- [ ] **Step 4: verificare + regressione (il gate più importante del piano).**
```bash
python tests/_prod_route_c_runner.py Test/sez-contrapposte
python Test/_quadratura_harness.py Test/june_sample
python tests/_import_probe.py "Test/june_sample/success/budget_365_Bilancio di esercizio provvisorio al 31.12.2025.pdf" standard
python tests/_import_probe.py "Test/june_sample/errori/budget_405_all. A - PROGETTO DI BILANCIO.pdf" standard
```
Criteri: il residuo non classificato di 365 scende **sotto il 5%** del dichiarato (oggi: best-effort
685.283 su 1.119.894 = 61%); 405 esce da `QUADRATURA MASCHERATA` (oggi 182.545 = 2,3%); **nessun file
oggi pulito cambia `totale_attivo`**.

- [ ] **Step 5: Commit**

```bash
git add importers/situazione_contabile_parser.py tests/test_route_c_ruoli_conto.py
git commit -m "fix(sinonimi): route C classifica i conti dal layer semantico (ruolo contra/fondo/totale)"
```

---

### Task 6: un solo normalizzatore, e chiudere il codice morto

**Files:**
- Modify: `importers/iv_cee_hierarchy.py`, `importers/bilancio_classifier.py`,
  `importers/standard_ivcee_parser.py`, `importers/pdf_extractor_llm.py`
- Test: `tests/test_normalizzatore_unico.py`

- [ ] **Step 1: test che fallisce**

```python
# tests/test_normalizzatore_unico.py
def test_classifier_riconosce_i_marker_accentati():
    # bilancio_classifier.py:96-97 cerca "passivita"/"disponibilita liquide" con una
    # funzione che NON deaccenta -> su testo accentato non matchano MAI, e il file
    # finisce in ROUTE_UNSUPPORTED (import rifiutato).
    from importers.bilancio_classifier import compute_signals
    testo = ("Stato patrimoniale\nTotale passività 1.000,00\n"
             "Disponibilità liquide 500,00\nCapitale sociale 10.000,00\n")
    assert compute_signals(testo).sp_present is True


def test_un_solo_normalizzatore():
    from importers.label_semantics import normalize_label
    from importers.iv_cee_hierarchy import normalize
    for s in ["Totale attività", "TOTALE A T T I V I T A'", "F.do amm.to fabbricati",
              "TOTALE STATO PATRIMONIALE - PASSIVO"]:
        assert normalize(s) == normalize_label(s)
```

- [ ] **Step 2: verificare che fallisca.**

- [ ] **Step 3: implementare.**
  (a) `iv_cee_hierarchy.normalize` delega a `label_semantics.normalize_label` (attenzione all'import
  circolare: `label_semantics` non deve importare `iv_cee_hierarchy` a livello di modulo — import
  differito dentro la funzione dello spazio `voce`).
  (b) `bilancio_classifier.has()` usa `normalize_label` sul testo e sui marker. **Correggere il drift
  accenti** (`passivita` / `disponibilita liquide`).
  (c) `standard_ivcee_parser._normalise` e `_normalize_for_search`: delegare, verificando che il
  comportamento sulla punteggiatura resti compatibile con i loro `_find` (`"i. immateriali"` contiene un
  punto: se la normalizzazione lo toglie, quei `_find` vanno aggiornati **nella stessa commit**, con il
  test che lo dimostra).
  (d) **Cancellare il codice morto** individuato: `iv_cee_hierarchy.classify_for_reclassify` (nessun
  chiamante) e `pdf_mapper.extract_from_tables`/`extract_income_from_tables` (~60 literali, residuo
  Docling, nessun chiamante — verificare con un grep prima di cancellare, `validate_balance` nello
  stesso file **è in produzione** e va mantenuto).

- [ ] **Step 4: verificare.**
```bash
python -m pytest tests/ -q -k "normaliz or label or classifier or ivcee"
python Test/_quadratura_harness.py Test/june_sample
```

- [ ] **Step 5: Commit**

```bash
git add -A importers/ tests/test_normalizzatore_unico.py
git commit -m "refactor(sinonimi): un solo normalizzatore condiviso; fix drift accenti nel classifier; via il codice morto"
```

---

## 3. Accettazione del piano

- `classify_label` risolve **tutte** le grafie dei test dei Task 1, 2, 5.
- Copertura misurata su corpus: righe non risolte **da 58,3% a < 30%** (`tests/_label_coverage.py`).
- `resolve("I. immateriali")` — l'esempio dell'utente — restituisce `sp02_immob_immateriali`.
- budget_176/182 non vengono più amputati dal filtro colonne (vedi Piano 04 rev., che dipende da questo
  piano per la disambiguazione marker/voce).
- budget_365/342/435: residuo non classificato < 5% del totale dichiarato.
- `data/label_alias_cache.json` si popola al primo incontro di una grafia nuova e la rende deterministica.
- Ambiente no-key: comportamento invariato, **nessuna** regressione sul campione pulito (Quadro §6).
- Nessuna variazione di `totale_attivo` sui file che oggi importano puliti.

## 4. Cosa questo piano NON risolve (e va lasciato agli altri)

Per onestà di scope — non tutto quello che rompe l'import è sinonimia:

- **Geometria**: il taglio delle colonne (Piano 04), la ricostruzione delle due colonne contrapposte, la
  riga che contiene **sia** un conto dell'attivo **sia** uno del passivo (budget_365: `Impianti generici
  1.458,00 F.do amm.to impianti generici 583,20` su un'unica riga di testo — è la ragione per cui anche
  la CoGe-LLM perde metà dei conti, e non si ripara con un dizionario).
- **Aritmetica di netting** e assunzioni su dove l'estrattore aveva messo il fondo (Piano 03 T2).
- **Selezione dei candidati** e policy never-hard-block (Piano 02).
- **Sorgente del testo** nativo vs MinerU (Piano 06).
- **Identità CE↔SP** come policy contabile (Piano 04 T2).
