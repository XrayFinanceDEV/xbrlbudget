# Piano fix import PDF (standard + OCR) — Quadro generale

> **REVISIONE 2026-07-27 — leggere §8 PRIMA di eseguire qualunque piano.** Una seconda analisi con
> misure sul corpus ha cambiato **l'ordine di esecuzione** (il Piano 05 va per primo), ha **eliminato**
> il Task 3 del Piano 01 e il Task 1 del Piano 03 (assorbiti dal 05), e ha **corretto due diagnosi
> sbagliate** nel Piano 04.

> **For agentic workers:** questo file è il QUADRO: contesto economico-contabile, architettura, inventario
> difetti→piani, ordine di esecuzione, protocollo di regressione. I task eseguibili stanno nei piani
> 01–06 (stessa cartella, prefisso `2026-07-23-import-fix-`). REQUIRED SUB-SKILL per eseguirli:
> superpowers:subagent-driven-development oppure superpowers:executing-plans.

**Goal:** portare a import corretto i 18 file "problema software" dell'audit 2026-07-23 (più i 4 solo-OCR)
senza regredire i ~55 file che già importano puliti, e unificare il percorso OCR su quello standard.

**Architettura (stato attuale):** `import_pdf_balance_sheet` (importers/pdf_importer.py) instrada via
`bilancio_classifier` su route A/B (IV-CEE → LLM Haiku), route C (trial balance → CoGe-LLM + parser
deterministico, selezione per completezza), OTHER. A valle, gates condivisi: `net_contra_accounts`,
`_reconcile_trial_to_declared`, `enforce_ce_sp_identity`, `validate_balance`, `check_quadratura`.
Il percorso OCR (`/import/pdf-ocr`) inietta un `extraction_context` MinerU che SOSTITUISCE il testo.

**Tech stack:** Python 3, PyMuPDF (fitz), Anthropic Haiku (`claude-haiku-4-5-20251001`), MinerU 3.2.0
(Docker, porta 8002), SQLite/SQLAlchemy. Test: corpus reale in `Test/` (gitignored), harness
`Test/_quadratura_harness.py`, replica produzione `tests/_prod_route_c_runner.py`, probe
`import_probe.py` (vedi §Protocollo di regressione).

---

## 1. Fondamento economico-contabile (perché questi bug sono bug)

Chi implementa deve interiorizzare QUATTRO identità contabili; ogni fix discende da una di esse.

### 1.1 Identità di pareggio e risultato implicito
Un bilancio IV-CEE (art. 2424) stampa `Totale attivo = Totale passivo` dove il passivo INCLUDE il
patrimonio netto (e quindi l'utile/perdita d'esercizio, voce A.IX).
Un **bilancio di verifica / situazione contabile** (trial balance, route C) NO: stampa i saldi dei conti,
e il risultato d'esercizio **non è un conto** — non esiste ancora come scrittura. Perciò:

```
TOTALE ATTIVITA'  −  TOTALE PASSIVITA'  =  UTILE  (se positivo)
TOTALE PASSIVITA' −  TOTALE ATTIVITA'   =  PERDITA (se negativo)
TOTALE A PAREGGIO = max(lato attivo, lato passivo) identico sui due lati
```

Molti gestionali lo dichiarano esplicitamente ("UTILE STATO PATRIMONIALE", "TOTALE A PAREGGIO",
"SBILANCIO 0,00"). Alcuni (AGO, budget_623) stampano la PERDITA sul lato ATTIVO per far tornare il
pareggio. **Confrontare attivo vs passivo "nudi" su un trial balance produce sempre un falso sbilancio
pari esattamente al risultato d'esercizio.** → Piano 01.

### 1.2 Presentazione lorda vs netta; fondi rettificativi vs fondi rischi
- **Fondo ammortamento / fondo svalutazione immobilizzazioni** = posta RETTIFICATIVA dell'attivo
  (contra-asset). In IV-CEE non esiste come passivo: va NETTATA da sp02/sp03 (`B.I`/`B.II` sono netti
  per legge).
- **Fondo svalutazione / rischi su crediti** = contra-asset dei CREDITI: netta sp06 (C.II è "al netto
  del fondo"), NON è un debito né un fondo rischi.
- **Fondo rischi e oneri** (cause, garanzie, controversie) = vero PASSIVO: voce B del passivo → sp14.
  NON si netta.
I trial balance in **presentazione lorda** espongono i fondi sul lato passivo; l'import deve nettarli
(sp02/sp03/sp06) o classificarli (sp14) — altrimenti restano "massa non spiegata" → plug → rigetto per
QUADRATURA MASCHERATA su bilanci in realtà perfetti (169, 338, 281, 646, 623, 405, 703). → Piano 03.

### 1.3 Identità CE↔SP
Il risultato è UN numero: ultima riga del CE **e** sp13 nello SP. Se l'estrazione li fa divergere,
l'errore è dell'estrazione, non del documento; quando il risultato DICHIARATO dal documento conferma
sp13, il CE va riallineato (plug in ce12/ce04), non rigettato (319, 330-CE). → Piani 02 e 04.

### 1.4 Sinonimia delle voci (il punto sollevato dall'utente)
Le voci civilistiche hanno UN significato ma N grafie per gestionale: `I. immateriali` (schema secco),
`I - Immobilizzazioni immateriali` (Passepartout), `B.I IMMOBILIZZAZIONI IMMATERIALI` (riclassificate),
`Totale attivo` / `TOTALE ATTIVITA'` / `Stato patrimoniale attivo` / `TOTALE STATO PATRIMONIALE - ATTIVO`.
Il matching per stringa fissa fallisce su ogni variante nuova; è ESATTAMENTE il motivo per cui è stato
introdotto l'LLM. Strategia a 3 livelli: (a) normalizzazione aggressiva deterministica,
(b) dizionario alias centralizzato che CRESCE, (c) arbitro Haiku SOLO per le etichette irrisolte, con
cache persistente → ogni sinonimo costa una chiamata LLM UNA VOLTA nella vita del sistema. → Piano 05.

### 1.5 Economics del sistema
- **Costo LLM**: Haiku ≈ 1$/MTok input; un import route A/B ≈ 2 chiamate (~30-60k token) ≈ 3-6 centesimi.
  L'arbitro alias (Piano 05) è 1 micro-chiamata batch per documento SOLO su etichette mai viste, con cache
  → costo marginale → 0 nel tempo.
- **Costo MinerU**: container GPU; ha senso SOLO per scansioni. Oggi viene pagato anche su PDF a testo
  nativo dove DEGRADA il risultato (audit: 4 fail solo-OCR su testo nativo + Bilancino scansione dove
  vince la vision del percorso standard). → Piano 06 (delega al nativo quando esiste).
- **Costo utente**: ogni falso "Correggere il documento contabile originale" è un ticket cliente e una
  perdita di fiducia (18 lamentele storiche in backlog). Il valore dei fix è prima di tutto lì.

---

## 2. Inventario difetti → piani (dall'audit `Test/_import_audit_2026-07-23/`)

| # | Difetto | File colpiti | Piano |
|---|---------|-------------|-------|
| P1 | Preflight "declared-total": attivo vs passivo senza utile implicito → falso "sorgente non quadra… Correggere il documento" | 610, 229, 238, 243, 246, 395 (+ messaggio generico su 188, 703, 176, 182, 623, 330) | **01** |
| P2 | Route C: candidato CoGe-LLM scelto/fallito senza retry sul deterministico che quadra; fallimenti intermittenti; hard-fail su trial balance leggibili (violazione policy "never hard-blocked") | 243, 246, 395, 330, 623 | **02** |
| P3 | Netting incompleto: f.do sval./rischi crediti non nettato; f.do rischi e oneri non → sp14; fondi amm. senza riga subtotale; perdita su lato attivo; layout 1/10/005 e dotted interlacciato | 169, 338, 281, 646, 623, 405, 703, 188 | **03** |
| P4 | Route B "riclassificata dettagliata": filtro DIFFERENZA/SCOST amputa le colonne importi; totali "Stato patrimoniale attivo" non ancorati; CE↔SP non riallineato su risultato negativo | 176, 182, 319 | **04** |
| P5 | Sinonimia etichette: matching a stringa fissa su totali/voci/sezioni | trasversale (188, 703, 176, 182 + futuri) | **05** |
| P6 | OCR: MinerU sostituisce testo nativo buono e perde la geometria a 2 colonne; niente candidato vision; nessuna delega al percorso standard | Bilancino, 131, 132, 158, 243-ocr, 281-ocr, 319-ocr + tutti i route C via OCR | **06** |
| P7 | (backlog, non bloccante) Colonna anno precedente persa per drift LLM — anno corrente sempre corretto | 254, 255, 597, 599 | §5 |

NON toccare (comportamenti corretti dell'audit): rigetto di 133/135/137/138/152/161/289 (sorgenti
genuinamente sbilanciate), 150/196/335 (non-bilanci), il netting corretto di 309/337/343/348.

---

## 3. Architettura bersaglio ("ricongiunzione" standard/OCR)

```
                    ┌────────────────────────────────────────────────────┐
 /import/pdf ──────►│                                                    │
                    │  testo nativo? ──sì──► testo+geometria PyMuPDF     │
 /import/pdf-ocr ──►│       │no/garbled                                  │
   (MinerU parse)   │       ├──► candidato MinerU (testo+tabelle+bbox)   │
                    │       └──► candidato vision/rapidocr (esistente)   │
                    └───────────────┬────────────────────────────────────┘
                                    ▼
                    classificatore route (A/B/C/other) — INVARIATO
                                    ▼
                    estrattori per route — INVARIATI ma:
                      • route C: selezione candidati CON retry (Piano 02)
                      • etichette → layer alias semantici (Piano 05)
                                    ▼
                    gates contabili condivisi — INVARIATI ma:
                      • verdetto sorgente pareggio-aware (Piano 01)
                      • netting fondi completo (Piano 03)
```

Punto chiave (richiesta utente): **MinerU diventa un PROVIDER di testo/tabelle alternativo, non una
pipeline parallela**. A valle dell'estrazione i due percorsi sono già oggi la stessa pipeline; il Piano
06 elimina l'unica vera divergenza (la sostituzione cieca del testo) e aggiunge il candidato vision.

---

## 4. Ordine di esecuzione e razionale — **RIVISTO 2 — 2026-07-27**

| # | piano | perché qui | crediti LLM? |
|---|---|---|---|
| 1 | **00A** — probe, baseline versionata, metriche per spazio | senza baseline nessun piano ha un gate: `Test/` è gitignorato e le route A/B non sono deterministiche (§8.4) | no |
| 2 | **05A** — motore semantico deterministico (Task 1, 2, 4, 5-det, 6) | causa dominante; i Piani 01 e 03 aggiungevano a mano le liste che qui diventano dizionario (§8.1-8.2) | no |
| 3 | **07** — geometria: riga logica, sezioni, split interlacciato, totali nudi | ortogonale al 05 e altrettanto bloccante; il 05 dichiara di non poterlo risolvere | no |
| 4 | **01** — verdetto sorgente pareggio-aware (T1, T2; **T3 annullato**) | consuma i marker del 05A | no |
| 5 | **03** — netting (T2 auto-validante, T3; **T1 assorbito dal 05A**) | consuma i ruoli `conto` del 05A | no |
| 6 | **04** — route B (T1 con la causa reale; T2 = retry + `review_required`, **niente plug**) | consuma i marker del 05A | T1 no / T2 sì |
| 7 | **02** — retry candidati (**solo T1 e T2; T3 annullato**) | il suo `_passes` anticipa i gate: va dopo 03 e 04 | parziale |
| 8 | **05B** — arbitro Haiku batch + cache versionata + telemetria | serve il dizionario del 05A già popolato, così l'LLM viene chiamato solo sul residuo vero | **sì** |
| 9 | **06** — orchestrazione OCR per punteggio di qualità | beneficia di tutti i precedenti | sì (MinerU) |

Ogni piano resta auto-consistente: produce software funzionante e testabile da solo.

**Ordini precedenti (`01→03→02→04→05→06` e `05→01→03→04→02→06`): non usarli.**

### 4.1 Tre task ANNULLATI (non eseguire)

| task | perché |
|---|---|
| **01 T3** — marker letterali | assorbito dal 05A Task 4 (spazio `marker`) |
| **02 T3** — `_force_balance_trial` | **inventava importi** in `sp09`/`sp16g` per forzare lo zero; viola le invarianti D1/D3/D4 di `docs/import/REGOLE-IMPORT-00-INDICE.md` e ribalta il commit `4a2e80f` "diagnosi oneste al posto dei plug". Sostituito da: retry → import invariato con `validation_status="review_required"` + `forecastable=False` |
| **03 T1** — liste keyword fondi | assorbito dal 05A Task 5 (ruolo `conto`); resta la regola contabile e la parte strutturale di `ContraScan` |

**Principio che li unisce:** nessun fix può creare un importo per far quadrare un bilancio. Se non quadra,
lo si dice — con i valori come sono stati estratti.

---

## 5. Backlog P7 — anno precedente (approccio, non pianificato)

Colonna prior persa per micro-drift LLM (254: 2.725; 255: riserva legale 11.419; 597/599: ~1-1,5M).
Approccio quando si affronterà: (a) leggere i totali dichiarati della colonna prior
(`_declared_control_totals` è già dual-capable sul testo pieno); (b) se il prior estratto non riconcilia
entro 2€, UN retry LLM mirato alla sola colonna prior; (c) se ancora no → import current-only (odierno).
Non bloccante: l'anno corrente è sempre corretto.

---

## 6. Protocollo di regressione (VALE PER OGNI PIANO)

Strumenti (già esistenti, non ricrearli):
- **Probe fedele alla produzione**: `tests/_import_probe.py` — **già scritto e funzionante** (2026-07-27;
  il Task 0 del Piano 01 è quindi da considerarsi fatto). Chiama la vera `import_pdf_balance_sheet` su DB
  SQLite in-memory (mai il DB reale), legge indietro i valori **salvati** e li giudica con
  `check_quadratura`. Uso:
  `python tests/_import_probe.py --dir <cartella> standard --json out.jsonl`.
- **Diagnostica sinonimia**: `tests/_label_diag.py <file.pdf>` — rotta scelta, totali dichiarati
  effettivamente letti, elenco delle etichette che il resolver **non** risolve.
- **Copertura del resolver**: `tests/_label_coverage.py <cartelle…>` — % di righe e di massa non risolte
  su un corpus, più le etichette non risolte ordinate per numero di documenti. È la metrica di
  accettazione del Piano 05.
- **Harness quadratura**: `python Test/_quadratura_harness.py Test/june_sample` (route deterministiche).
- **Replica route C**: `python tests/_prod_route_c_runner.py <cartella|pdf>`.

Gate di regressione, da eseguire DOPO ogni piano:

```bash
# 1. I file bersaglio del piano importano (o falliscono col NUOVO messaggio atteso)
python tests/_import_probe.py "<file bersaglio>" standard

# 2. ZERO regressioni sui file puliti — campione fisso di 10:
for f in budget_143 budget_147 budget_162 budget_209 budget_215 budget_247 \
         budget_256 budget_275 budget_287 budget_328; do
  python tests/_import_probe.py "Test/successTerzo/success/<match $f>" standard
done
# Criterio: ok=true, stored.total_assets IDENTICO al valore pre-fix (annotato nell'audit),
# validation_report.masked=false, sbilancio=0.

# 3. Baseline harness non peggiora:
python Test/_quadratura_harness.py Test/june_sample     # oggi: 6/10
python tests/_prod_route_c_runner.py Test/sez-contrapposte
```

Criteri di accettazione finali (dopo tutti i piani):
- dei 18 file "problema software": ≥ 14 importano con sbilancio 0 e `masked=false`; i restanti
  falliscono con messaggi onesti che NON incolpano la sorgente;
- dei 4 solo-OCR: tutti e 4 importano via `/import/pdf-ocr` (per delega al nativo o candidato vision);
- nessuna variazione dei totali salvati sui ~55 file puliti;
- nessun falso "Correggere il documento contabile originale" su documenti con pareggio dichiarato.

---

## 7. Vincoli globali (validi per tutti i piani)

- NON modificare lo schema DB (nessuna migrazione).
- NON cambiare il contratto degli endpoint (`/import/pdf`, `/import/pdf-ocr`) né i payload di risposta,
  salvo aggiunta di chiavi opzionali.
- Decimal ovunque per gli importi; mai float.
- Messaggi utente in italiano; niente messaggi che attribuiscono al documento difetti non provati.
- Tolleranza contabile: 2 € (coerente con `check_quadratura(tol=Decimal('2'))`).
- Commit frequenti, uno per task; branch `fix/import-audit-2026-07`; niente push senza richiesta.
- I file del corpus `Test/` sono dati sensibili gitignorati: i test committati usano SOLO frammenti di
  testo sintetico ricostruito nei test stessi (mai copiare interi PDF nel repo).

---

## 8. Seconda analisi (2026-07-27) — cosa cambia e perché

Rifatta da zero con misure sul corpus e verifica del codice riga per riga, su richiesta dell'utente
(«secondo me il problema è che le voci sono scritte leggermente diverse ma sono la stessa, e l'LLM non
capisce che è la stessa»). L'ipotesi è **confermata**, con una precisazione sul meccanismo.

### 8.1 La sinonimia è la causa dominante, ma si rompe nei GATE, non nell'LLM

L'LLM sui documenti interi (route A/B) i sinonimi li capisce. Si rompono i **controlli deterministici che
decidono se accettarne il risultato**: ancoraggi di sezione, totali dichiarati, netting dei fondi,
reclassificatore contrapposte. Misure (dettaglio e riproduzione nel Piano 05 §0):

| misura | valore |
|---|---|
| righe con importo la cui etichetta il resolver NON risolve (72 PDF) | **58,3%** |
| massa in euro corrispondente | **56,5%** |
| dizionario alias | 65 nodi, 246 alias (**3,78 per nodo**) |
| `resolve("I. immateriali")` — l'esempio letterale dell'utente | **`None`** |
| `resolve("Fornitori")` / `("Clienti")` / `("Totale a pareggio")` | **`None`** |
| normalizzatori di stringa incompatibili nel codice | **6** |
| `iv_cee_hierarchy.classify_for_reclassify` (adattatore per la route C) | **codice morto, 0 chiamanti** |

Due diagnosi puntuali, entrambe verificate e **diverse da quelle scritte nei piani**:
- **budget_176/182**: il filtro colonne taglia a `x≥115` perché scambia la voce di legge
  «**Differenza** tra valore e costi di produzione (A−B)» (x=117) per l'intestazione della colonna
  analitica «Differenza» (x=460), e **cancella l'intera pagina**. Piano 04 T1, riscritto.
- **budget_365/342/435/138**: errore *"i totali stampati coincidono ma le componenti estratte non li
  ricostruiscono"*. Su 365 il CoGe-LLM estrae 590.071 su 1.119.894 dichiarati e il best-effort lascia
  685.283 di residuo; le etichette del documento (`Fornitori`, `Clienti`, `Fatture da ricevere`,
  `F.do amm.to <cespite>`) sono **tutte irrisolte**.

### 8.2 Correttivo di metodo: i piani stavano curando i sintomi con le stesse liste

I Piani 01 T3 e 03 T1 aggiungevano nuove liste di stringhe letterali (`"utile stato patrimoniale"`,
`"utile esercizio"`, `RISCHI|ONERI|CONTROVERS|GARANZI|CAUSE`) scelte enumerando i file dell'audit — cioè
**esattamente la fragilità che §1.4 dichiara di voler eliminare**. Sono stati assorbiti nel Piano 05
(Task 4 e Task 5), che li trasforma in dizionario + cache + arbitro. Questo risponde al sospetto
dell'utente che «i fix vengano fatti specifici per caso e non generali»: era fondato per 01 T3, 03 T1,
02 T3 (soglie 5%/20% tarate su 188 e 246) e 04 T1 (diagnosi non verificata).

### 8.3 Difetti dei piani da correggere prima di eseguirli

- **03 T2** (`_apply_contra_to_bs`): riduce sp06 del fondo crediti solo se trova la stessa massa nei
  debiti (`>=`), altrimenti riduce l'attivo **senza** ridurre il passivo → sbilancia. Serve un gate
  auto-validante (il piano stesso lo impone come vincolo, poi non lo applica) e un flag di idempotenza
  sul `bs` (`>=` **non** garantisce idempotenza). Il parametro `netted_immob` è dichiarato e mai usato.
- **03 → 02**: il Piano 03 aggiunge `sval_crediti` a `ContraScan` ma non aggiorna il **secondo**
  consumatore (`pdf_importer.py:823-836`, che ricalcola la massa contra per correggere l'ancora della
  selezione candidati): l'ancora resterebbe lorda dei crediti mentre il `bs` è netto → l'ordinamento dei
  candidati route C cambia. Conflitto di merge certo con 02 T2, che riscrive le stesse righe.
- **02 T3**: il codice proposto contiene una riga morta immediatamente riassegnata, chiede
  all'implementatore di *verificare empiricamente* la propria premessa contabile, e il warning emesso
  contraddice la policy a tre scaglioni descritta due paragrafi sopra. Inoltre lega un gate bloccante al
  **testo** di un warning (`w.startswith("Utile CE")`): va letto un campo strutturato di `Quadratura`.
- **04 T2**: partiva dal presupposto che `enforce_ce_sp_identity` avesse un plug da "allargare". Non ce
  l'ha: è diagnostica pura **per scelta di progetto documentata nel docstring**. CLAUDE.md su quel punto
  è obsoleto. Serve una decisione di prodotto, non un bugfix (Piano 04 T2 Step 0).
- **06 T1**: `_choose_text_source` usa `_text_layer_is_garbled` come unico indicatore di qualità. Un PDF
  con layer nativo **parziale ma non garbled** (>50 caratteri) oggi è salvato da MinerU e verrebbe
  degradato. Il gate proposto non intercetta questo caso.

### 8.4 Il gate anti-regressione non è un gate

`Test/` è gitignorato (`.gitignore:111`). Quindi corpus, harness e — soprattutto — **i valori pre-fix**
non sono versionati; i test committati sono unit test su testo sintetico; le route A/B sono
LLM-non-deterministiche e solo il Piano 02 impone 3 run, sui soli file bersaglio. Il "gate" è una
checklist manuale per chi ha il corpus in locale: non è riproducibile da un secondo sviluppatore, non gira
in CI, e non distingue una regressione dal rumore LLM. **Se i piani vengono eseguiti da agenti in sessioni
separate — come i piani stessi prescrivono — questo è il rischio numero uno dell'operazione.**

Rimedio minimo, da fare **prima** di eseguire i piani: committare una **baseline versionata** in
`tests/fixtures/import_baseline.json` con, per ogni file del corpus, `sha256` + `totale_attivo` +
`sbilancio` + `masked` attesi (generata da `tests/_import_probe.py --json`), e un test che la confronta
saltando i file assenti in locale. I numeri non sono dati sensibili; i PDF restano fuori dal repo.

### 8.5 Stato dell'ambiente (2026-07-27)

- **Crediti Anthropic esauriti** (`Error code: 400 — Your credit balance is too low`). La misura sul
  corpus si è interrotta a metà: risultati validi 42 file su 72 (25 OK / 17 FAIL); i restanti hanno
  fallito per assenza di credito, **non** per un difetto di import. Tutto ciò che passa da route A/B,
  dalla CoGe-LLM o dall'arbitro del Piano 05 **non è verificabile finché non si ricarica**.
- **Docker/MinerU non attivo** (`npipe:////./pipe/dockerDesktopLinuxEngine` non raggiungibile) → il metodo
  `ocr` non è stato eseguito. Il Piano 06 non è validabile in questo stato.
