# Piano 07 — Geometria: relazione etichetta↔importo, totali nudi, sezioni sequenziali

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans oppure
> superpowers:subagent-driven-development. Steps con checkbox (`- [ ]`).
> **Nuovo piano (2026-07-27).** Copre la classe di difetti che il Piano 05 dichiara esplicitamente di
> NON poter risolvere (§4 di quel piano): quando la relazione fra un'etichetta e il suo importo è persa
> **geometricamente**, nessun dizionario semantico la recupera.

**Goal:** far leggere correttamente i layout in cui etichetta e importo non stanno sulla stessa riga
logica, i totali sono stampati "nudi", e le sezioni Attivo/Passivo sono sequenziali invece che affiancate.
Bersagli: **188, 703, 405** e la famiglia dei contrapposte a riga interlacciata (365, 342, 435).

**Perché è un piano a sé.** Il Piano 05 risponde a *«che cos'è questa etichetta?»*. Qui la domanda è
diversa: *«quale importo appartiene a questa etichetta, e a quale sezione appartiene questa riga?»*. Sono
due assi ortogonali, e confonderli è ciò che ha prodotto le diagnosi sbagliate dei piani precedenti
(budget_176 sembrava un problema di colonne anno, era una collisione di etichette; budget_281 sembra un
problema di sezioni, è un problema di contra-scan).

**Tech stack:** Python, PyMuPDF (`get_text("words")` con coordinate), pytest. **Nessun LLM** — è tutto
deterministico e quindi **eseguibile senza crediti**.

## Vincoli globali
Quadro §7. In più, due regole di sicurezza specifiche di questo piano:
- **Danno asimmetrico:** una ricostruzione geometrica sbagliata sposta massa fra voci senza lasciare
  residuo (nessun gate se ne accorge); una ricostruzione mancata lascia residuo (il gate lo vede).
  Quindi: **nel dubbio non ricostruire**.
- Ogni nuova euristica deve essere **auto-validante** contro un controllo stampato (subtotale o totale di
  sezione) e diventare no-op quando il controllo non conferma.

---

## 1. Casistica (dal corpus, verificata)

### 1.1 Riga interlacciata: due conti di lati opposti sulla stessa riga di testo
budget_365, testo nativo:
```
Impianti generici        1.458,00 F.do amm.to impianti generici       583,20
Clienti                622.446,98 Fornitori                       200.053,84
```
Una sola riga contiene un conto dell'**attivo** con il suo importo **e** un conto del **passivo** con il
suo. Un lettore riga-per-riga (compreso l'LLM, che riceve testo) associa i numeri all'etichetta sbagliata
o ne perde metà: sul 365 la CoGe-LLM estrae 590.071 su 1.119.894 dichiarati.
→ **Serve lo split per coordinata prima** di dare il testo a chiunque, LLM incluso.

### 1.2 Sezioni sequenziali, non affiancate
budget_281: colonna unica; il lato è dato da un marcatore di sezione (`** A T T I V I T A'` a pag. 1,
`** P A S S I V I T A'` a pag. 2) e dalla colonna d'importo (SALDO DARE x≈280 / SALDO AVERE x≈340).
Un parser che cerca un "gutter" fra due colonne di conti qui non trova nulla di sensato.
→ **Il lato si eredita dal marcatore di sezione corrente**, che va tracciato attraverso le pagine.
(Nota: il parser DEPI oggi lo fa già correttamente su 281 — vedi Piano 03 Task 3. L'obiettivo qui è
renderlo una capacità **condivisa**, non di un solo sub-parser.)

### 1.3 Importo sulla riga precedente/successiva rispetto all'etichetta
budget_176, riga reale ricostruita per coordinata:
```
B.II.4.b.2) Macchine d'ufficio elettromeccaniche, elettroniche e
442  1.884,43  1.884,43  0,00
calcolatori
```
La descrizione va a capo e l'importo finisce su una riga **diversa** da quella dell'etichetta.
→ **Serve la ricomposizione della riga logica** (etichetta multi-riga + importi), non della riga fisica.

### 1.4 Totali "nudi"
budget_188/703: righe di totale senza etichetta, o con l'etichetta su una riga e i due importi su
un'altra; codici gerarchici tipo `1 / 10 / 005` in cui il livello si deduce dal **numero di segmenti**, non
da un separatore costante.
→ **Un totale va riconosciuto per posizione e per aritmetica** (è la somma dei figli), non solo per
la parola «TOTALE».

---

### Task 1: ricomposizione della riga logica (`logical_rows`)

**Files:**
- Create: `importers/page_geometry.py`
- Test: `tests/test_page_geometry_rows.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Cell:
      text: str; x0: float; x1: float

  @dataclass(frozen=True)
  class LogicalRow:
      label: str                 # etichetta ricomposta (anche se andava a capo)
      amounts: list              # [(valore_str, x)] in ordine di colonna
      y: float
      page: int
      section: Optional[str]     # "attivo" | "passivo" | "ce" — dal Task 2
      code: Optional[str]        # codice conto in testa, se presente

  logical_rows(page_or_doc, ytol=2.5) -> list[LogicalRow]
  ```
- Consumata da: Task 3 (split contrapposte), Piano 03 (contra-scan), Piano 05 Task 5 (che riceve
  `label` già pulita e `code`/`path_hint` separati).

- [ ] **Step 1: test che fallisce** — con `words` sintetiche che riproducono §1.3: etichetta su due righe
fisiche, importi sulla seconda. Attesa: **una** `LogicalRow` con label completa e 3 importi.
Più un test §1.1: riga con due gruppi `descrizione+importo` a x molto distanti → la ricomposizione **non**
deve fonderli in un'unica label (li lascia separati per il Task 3).

- [ ] **Step 2: verificare che fallisca.**

- [ ] **Step 3: implementare.** Raggruppamento per y (come già fanno `tests/_label_coverage.py` e
`_filter_difference_columns`), poi:
  - una riga **senza importi** la cui x di inizio è compatibile con la colonna descrizione e che è
    adiacente (|Δy| ≤ 1,5 × altezza riga) a una riga **con importi ma con label corta o assente** si
    **fonde** con essa;
  - la fusione è **vietata** se la riga senza importi inizia con un codice di conto o con un path
    civilistico (è una voce a sé, non una continuazione);
  - il codice conto in testa (`\d{2}/\d{2}/\d{3}`, 8-digit, dotted, `NNN.NNNNN`) viene **estratto** in
    `code`, non lasciato nella label.

- [ ] **Step 4: verificare** — `python -m pytest tests/test_page_geometry_rows.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(geometria): ricomposizione della riga logica (etichetta multi-riga, codice estratto)"`

---

### Task 2: sezione corrente ereditata (`section_tracker`)

**Files:**
- Modify: `importers/page_geometry.py`
- Test: `tests/test_page_geometry_sections.py`

**Interfaces:**
- Produces: `assign_sections(rows) -> list[LogicalRow]` — attraversa le righe in ordine di documento e
  assegna `section` in base all'ultimo marcatore incontrato, **attraverso le pagine**.

- [ ] **Step 1: test che fallisce** — righe: `** A T T I V I T A'` (pag. 1) + 3 conti, poi
`** P A S S I V I T A'` (pag. 2) + 3 conti. Attesa: le prime 3 `section="attivo"`, le altre `"passivo"`.
Includere la grafia **lettera-spaziata**, che è quella reale di budget_281.

- [ ] **Step 2: verificare che fallisca.**

- [ ] **Step 3: implementare.** Il marcatore si riconosce con `label_semantics.classify_label(..., space="marker")`
(Piano 05: `__sez_sp_attivo` / `__sez_sp_passivo` / `__sez_ce`) — **non** con una lista di stringhe locale.
Il de-spacing lettera-per-lettera è già in `normalize_label` (Piano 05 Task 1).
**Regola di sicurezza:** se non si incontra alcun marcatore, `section` resta `None` e i chiamanti
mantengono il comportamento attuale — nessuna inferenza.

- [ ] **Step 4: verificare + regressione** su un file dove il lato è dato dalla colonna e non dalla
sezione: la sezione **non deve** ribaltare il lato dedotto dalla colonna (regola consolidata del repo: la
colonna è ground truth). `python tests/_prod_route_c_runner.py Test/sez-contrapposte`

- [ ] **Step 5: Commit** — `git commit -m "feat(geometria): sezione corrente ereditata attraverso le pagine (layout sequenziali)"`

---

### Task 3: split delle righe interlacciate prima dell'estrattore

**Files:**
- Modify: `importers/page_geometry.py` (`split_interleaved`), `importers/pdf_extractor_llm.py`
  (testo passato alla CoGe-LLM per la route C)
- Test: `tests/test_page_geometry_interleaved.py`

**Interfaces:**
- Produces: `split_interleaved(rows, gutter_x) -> tuple[list[LogicalRow], list[LogicalRow]]` (sinistra,
  destra) e `render_two_column_text(rows) -> str` che serializza **prima tutta la colonna sinistra, poi
  tutta la destra**, così l'LLM riceve due elenchi ordinati invece di righe miste.

**Perché tocca anche l'LLM.** È il punto che il Piano 05 non copre e che spiega perché la CoGe-LLM perde
metà dei conti sul 365: non è un problema di sinonimi, è che il testo che riceve è **strutturalmente
ambiguo**. Ricomporlo prima è il fix più economico e vale per qualunque modello.

- [ ] **Step 1: test che fallisce** — righe §1.1; attesa: sinistra = [`Impianti generici` 1.458,00;
`Clienti` 622.446,98], destra = [`F.do amm.to impianti generici` 583,20; `Fornitori` 200.053,84].
Più un test che su un layout **monocolonna** `split_interleaved` restituisce tutto a sinistra e destra
vuota (nessun falso split).

- [ ] **Step 2: verificare che fallisca.**

- [ ] **Step 3: implementare.** Il `gutter_x` si sceglie come già fa `_be_split` (la x che **bilancia** le
righe con descrizione sui due lati), ma con due gate nuovi:
  - lo split si applica **solo** se entrambi i lati risultanti hanno ≥ 3 righe con importo;
  - e se la somma degli importi per lato è dello stesso ordine di grandezza dei totali dichiarati di
    quella sezione (auto-validazione). Altrimenti: **nessuno split**.

- [ ] **Step 4: verificare + effetto contabile.**
```bash
python -m pytest tests/test_page_geometry_interleaved.py -q
python tests/_prod_route_c_runner.py "Test/june_sample/success/budget_365_Bilancio di esercizio provvisorio al 31.12.2025.pdf"
```
Atteso: il residuo non classificato di 365 **scende nettamente** (oggi: best-effort 685.283 su 1.119.894).
⚠️ L'effetto sulla CoGe-LLM è verificabile **solo con i crediti**: annotare come pendente.

- [ ] **Step 5: Commit** — `git commit -m "feat(geometria): split delle righe interlacciate prima dell'estrazione (contrapposte a riga unica)"`

---

### Task 4: totali riconosciuti per aritmetica, non solo per etichetta

**Files:**
- Modify: `importers/page_geometry.py` (`mark_totals`)
- Test: `tests/test_page_geometry_totals.py`

**Interfaces:**
- Produces: `mark_totals(rows) -> list[LogicalRow]` — imposta `is_total` quando la riga **è la somma dei
  suoi fratelli** entro tolleranza, anche se non contiene la parola «TOTALE».

**Perché.** Oggi `_be_reclassify` filtra i totali con `if 'TOTALE' in d or 'PAREGGIO' in d`. Non intercetta
`Tot.`, `T O T A L E`, né i **totali nudi** di 188/703. Un totale non filtrato viene **sommato insieme ai
figli**: doppio conteggio, e il bilancio non quadra per una ragione che non ha nulla a che vedere con la
semantica.

- [ ] **Step 1: test che fallisce** — 3 righe figlie + una riga senza etichetta il cui importo è la loro
somma → `is_total=True`. E: una riga il cui importo **non** è la somma → `is_total=False` (non si marca
per posizione da sola).

- [ ] **Step 2: verificare che fallisca.**

- [ ] **Step 3: implementare.** Combinare tre segnali, tutti necessari perché uno solo non basta:
marcatore semantico (`space="marker"`, Piano 05), **gerarchia del codice** (un codice con meno segmenti dei
successivi è un padre: è la regola già usata da `_hier_reconstruct` per la famiglia dotted), e
**verifica aritmetica** sui fratelli. Marcare solo quando l'aritmetica conferma.

- [ ] **Step 4: verificare + regressione**
```bash
python -m pytest tests/test_page_geometry_totals.py -q
python tests/_prod_route_c_runner.py Test/sez-contrapposte
python Test/_quadratura_harness.py Test/june_sample
```

- [ ] **Step 5: Commit** — `git commit -m "feat(geometria): totali riconosciuti per aritmetica e gerarchia dei codici (totali nudi 188/703)"`

---

## Accettazione del piano

- 365: residuo non classificato in netto calo rispetto alla baseline 00A (percorso deterministico).
- 188/703: i totali nudi non vengono più sommati insieme ai figli (nessun doppio conteggio).
- 281: invariato — il suo difetto è il contra-scan (Piano 03 T3), non la geometria.
- Nessun file che oggi importa pulito cambia un solo campo (baseline 00A, non solo i totali).
- Ogni euristica introdotta è **no-op** quando il controllo stampato non la conferma.
