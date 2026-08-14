# Inventario dello snellimento di CLAUDE.md

**Data:** 2026-08-14 · **Spec:** [design](specs/2026-08-14-claude-md-snellito-design.md)

Ogni affermazione rimossa da `CLAUDE.md` è registrata qui con la sua destinazione.
Chi rivede controlla questa tabella, non 1.170 righe di diff.

| destinazione | significato |
|---|---|
| `RESTA` | invariante o trappola: confluisce nella sezione «Invarianti e trappole» di `CLAUDE.md` (Task 6) |
| `GIÀ IN <file> §<n>` | il fatto è già scritto in `/docs`: da `CLAUDE.md` si cancella |
| `SPOSTATA IN <file>` | il fatto esiste solo qui: si trascrive nella destinazione |
| `OBSOLETA — <perché>` | il codice non fa quello che la riga dice: si cancella |

Una voce `RESTA` porta il **testo** dell'invariante, non solo il suo titolo: è questo file
a trasportarlo mentre la prosa che lo conteneva viene cancellata.

I percorsi `<file>` senza cartella si intendono relativi a `docs/import/`.

## Blocco import (`CLAUDE.md:305-964`)

### Intestazione `### PDF Import (Claude LLM)` (305-332)

| # | affermazione | destinazione |
|---|---|---|
| 1 | Routing-first: ogni PDF è classificato da `bilancio_classifier.classify_bilancio` PRIMA di scegliere un estrattore | `RESTA` (nella nuova sezione «Import PDF» di `CLAUDE.md`, scritta in questo task) — dettaglio `GIÀ IN REGOLE-IMPORT-01 §3` |
| 2 | «Il classificatore sostituisce il vecchio check binario `is_trial_balance`» | `OBSOLETA` — descrive una migrazione conclusa. Nel codice non esiste più alcun check binario: `is_trial_balance = (classification.route == ROUTE_TRIAL)` (`pdf_importer.py:742`) è un alias derivato dalla route |
| 3 | Estrazione testo PyMuPDF + Claude Haiku 4.5 per le route IV-CEE | `GIÀ IN IMPORT-OVERVIEW §5` e `REGOLE-IMPORT-02 §5` (modello, token, tool-use forzato, retry) |
| 4 | Ordine di lettura (`reading_order_text` / `_stream_order_is_scrambled`): stream ≠ ordine visivo, i due danni, la soglia 25% su min 6 blocchi, i 212/249 file invariati, la posizione dopo i filtri a coordinate | `GIÀ IN REGOLE-IMPORT-02 §2` (intero, compresi gli importi dei due casi reali) |
| 5 | «Solo il secondo difetto è visibile; **quello dell'anno sbagliato quadra perfettamente**, per questo si corregge a monte e non ai gate» | `RESTA` — testo: *Un bilancio letto dall'anno sbagliato è internamente coerente: quadra, e nessun gate lo vede. I difetti che quadrano si correggono a monte, non aggiungendo un controllo a valle.* |
| 6 | Tempo di elaborazione 3-10 s per PDF | `SPOSTATA IN REGOLE-IMPORT-02 §5` |
| 7 | Supporta Bilancio Micro / Abbreviato / Ordinario (IV CEE) | `GIÀ IN REGOLE-IMPORT-01 §3` (regola 6) e `IMPORT-ROUTING-TAXONOMY §3` |
| 8 | Supporta il formato «Stampa dettaglio voci» (report ERP con conti di dettaglio) | `GIÀ IN REGOLE-IMPORT-01 §3` (blocco B, B2 «dettaglio sottoconti») |
| 9 | «Supporta Situazione Contabile (estrattore CoGe LLM primario, parser deterministico *fallback*)» | `OBSOLETA` — sulla route C i due estrattori girano **entrambi** e si sceglie il candidato migliore; il deterministico gira **sempre**, anche con la chiave API (`pdf_importer.py:1057-1198`). Non è un fallback, è un concorrente |
| 10 | Pre-filtri: Zucchetti, Datev/Koinos, «Stampa dettaglio voci», rumore dei separatori Dylog | `SPOSTATA IN REGOLE-IMPORT-02 §2` |
| 11 | Validatori post-estrazione: crediti, split debiti, coerenza del patrimonio netto, cross-check `ce20_imposte` | `GIÀ IN IMPORT-OVERVIEW §5` (elenco del post-processing) |
| 12 | Mappa le tabelle estratte su sp01-sp18 / ce01-ce20 | `GIÀ IN REGOLE-IMPORT-06 §2` |
| 13 | Modalità di estrazione a singolo anno e a due anni | `GIÀ IN REGOLE-IMPORT-02 §5` («I due anni») |

### `#### Macro-area router` (334-370)

| # | affermazione | destinazione |
|---|---|---|
| 14 | Gira per primo, sul testo delle prime ~14 pagine, e decide la **route** | `GIÀ IN REGOLE-IMPORT-01 §1` |
| 15 | «Tassonomia completa in `IMPORT-ROUTING-TAXONOMY.md` (77 documenti unici; le 3 macro-aree coprono il 96% dei casi reali)» | `OBSOLETA` (il numero) — il corpus è a 214 file fisici / 137 contenuti unici, già registrato in `REGOLE-IMPORT-00 §5 D6`. Il **rimando** al file `RESTA` nella tabella dei rimandi |
| 16 | `classify_bilancio` restituisce `Classification(macro_area, subcategory, route, gestionale, confidence, signals, reason)` | `GIÀ IN REGOLE-IMPORT-01 §1` (con l'annotazione, assente qui, che `confidence` non decide nulla) |
| 17 | Le tre macro-aree A / B / C più OTHER e la route di ciascuna | `RESTA` (nuova sezione «Import PDF», tre frasi) — dettaglio `GIÀ IN REGOLE-IMPORT-01 §3` |
| 18 | I segnali: marcatori testuali, densità di codici conto (DEPI, 8 cifre, TeamSystem, dotted, BILAGRA, 6 cifre), codici-PATH CEE, `is_contrapposte_file`, variante senza spazi | `GIÀ IN REGOLE-IMPORT-01 §4` e `§6` |
| 19 | Deroga «B batte C» (budget_313/314), purché manchino i marcatori C forti | `GIÀ IN REGOLE-IMPORT-01 §3` |
| 20 | «Route C LLM-first con fallback deterministico» | `OBSOLETA` — stesso errore della riga 9, qui in forma estesa (vedi `pdf_importer.py:1080-1131`: il candidato CoGe è saltato quando l'OCR locale a coordinate ha già letto il file, e il deterministico è aggiunto comunque) |
| 21 | `SC_PLUG_REJECT_PCT` (20%) scala solo la severità del warning `BILANCIO NON QUADRATO` | `GIÀ IN REGOLE-IMPORT-00 §5 D2` e `REGOLE-IMPORT-04 §8` |
| 22 | `is_trial_balance` è derivato dalla route; il risultato porta `macro_area` + `macro_subcategory`, così un formato nuovo emerge come area e non come crash | `SPOSTATA IN REGOLE-IMPORT-01 §1` |

### `#### CoGe LLM extractor for trial balances` (372-390)

| # | affermazione | destinazione |
|---|---|---|
| 23 | `extract_trial_balance_with_llm` manda il testo COMPLETO senza windowing SP/CE, perché una verifica non ha header IV-CEE su cui ancorarsi | `GIÀ IN IMPORT-OVERVIEW §5` («Perché C ha bisogno di un LLM CoGe dedicato») |
| 24 | I due prompt CoGe: convenzione Dare/Avere, netting dei contro-conti, mapping descrizione→sp01-18, risultato implicito; costi tutti positivi nel CE | `GIÀ IN IMPORT-OVERVIEW §5` e `IMPORT-ROUTING-TAXONOMY §6` |
| 25 | Post-processing (`_normalize_ce_signs`, `_validate_crediti`/`_validate_debiti`, `_validate_ce10_against_bs`, `_validate_ce_imposte`) e `_balance_trial_via_result`; scansionati via vision; solo single-year | `GIÀ IN IMPORT-OVERVIEW §5` |

### `#### Riscatto vision per sezione` (392-533)

| # | affermazione | destinazione |
|---|---|---|
| 26 | Terzo candidato di route C, prodotto solo su richiesta e alla FINE della catena (dopo `overlay_debt_typing` → `net_contra_accounts` → `_reconcile_trial_to_declared`); innescarlo prima farebbe scattare il riscatto su un attivo ancora lordo | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 27 | Innesco gated su `api_key`: senza chiave non si parte nemmeno, perché `render_section_images` gira PRIMA che `read_section` istanzi il client | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 28 | Si rendono a 200 dpi le sole pagine della sezione che non torna (`section_pages`); su questi file il numero giusto è STAMPATO ma il text layer non ci arriva (su budget_624 i mastri di costo sono disegnati come vettori) | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 29 | La sezione è **ricostruita da zero**, mai sommata a quella già estratta: sommare conterebbe due volte un mastro | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 30 | Solo i **mastri**: i dettagli a codice più lungo la vision li sbaglia e non servono | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 31 | `mastro_level_rows` sceglie il livello per RICONCILIAZIONE al totale stampato, non per profondità del codice (il minimo di cifre scartava due mastri buoni per 46.110,67) | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis`; l'invariante generale è la riga 91 |
| 32 | Il cancello `accept_rescue`: colonna sinistra riconcilia entro `max(50 €; 0,5%)`; colonna destra idem quando misurabile; estrazione non vuota; non spegne un'identità CE=sp13 che reggeva; quadratura strettamente migliore misurata come `|sbilancio| + |residuo|` | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 33 | La bandiera `residual_measured`: un residuo ASSERITO a zero non è una misura, e un controllo che manca non è un controllo superato | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` — l'invariante generale è la riga 116 |
| 34 | «La coerenza dei totali vision NON è una condizione del cancello»: serve solo a scegliere l'ancora (`section_anchor`), con ricaduta sulle ancore di testo | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 35 | Sul percorso SP la coerenza è necessaria di fatto ma altrove: `pdf_importer` rinuncia se `vision_result(sec)` è `None` | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 36 | L'ancora sul passivo ricostruito (`rebuilt_passivo` = `totale_passivo − utile + _netted_contra`), e il motivo: una sovra-lettura del passivo verrebbe ASSORBITA da `net_contra_accounts` cancellando debiti fino alla massa dei fondi, senza un solo avviso | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 37 | «Su budget_623 questo non può accadere: `_contra_rows` non trova nulla da leggere e `net_contra_accounts` no-oppa» | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` (verificata: è la correzione del 2026-08-14 della precedente attribuzione errata di 289.788,03 di fondi a quel file) |
| 38 | `vision_result` prende il SEGNO dall'identità che ha validato i totali, non dall'ordine delle chiavi: un documento stampa spesso sia «utile» sia «perdita» | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 39 | Scadenza non determinata → debiti **a breve**, per prudenza; l'utente li sposta in Rettifiche. Non è un ripiego dell'estrattore vision: è la regola del progetto, seguita anche dal best-effort di route C | `RESTA` — testo: *Un debito di cui la fonte non dichiara la scadenza va **a breve**, per prudenza: anticipare una scadenza peggiora gli indici di liquidità, non li abbellisce, e l'utente lo sposta in Rettifiche. Vale per ogni estrattore. Attenzione: `sp16` e `sp17` stanno entrambi nel passivo, quindi il pareggio non vede l'appiattimento — lo vedono CCN, current ratio e il capitale circolante di Altman.* |
| 40 | `_source_maturity_unspecified` → avviso `SCADENZA DEBITI NON DISTINTA`; è una stringa di avviso, non un verdetto: nessun cancello la legge e non deve leggerla | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 41 | Su budget_623 significa che 873.205,40 di debito bancario finiscono a breve finché l'utente non li riclassifica | `SPOSTATA IN docs/FIXING-IMPORT.md §6` |
| 42 | Il clamp sulle immobilizzazioni negative in `build_sp_from_vision`: azzera, logga a warning, e somma l'eccedenza a `_unclassified_mass` | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` (il divieto generale è la riga 108) |
| 43 | `build_sp_from_vision` dichiara **sempre** `_unclassified_mass`, anche a zero: `reliability.assess` legge quella chiave e una chiave assente vale zero | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 44 | Un solo tentativo per sezione, tetto `MAX_RESCUE_PAGES = 8`, ogni errore non fatale; le due sezioni si innescano indipendentemente | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 45 | Provenienza: suffisso `+vision-<sezioni>` su `parser_version` e chiave `vision_rescue` nel `validation_report` (una sezione SCARTATA non lascia traccia nel suffisso) | `SPOSTATA IN REGOLE-IMPORT-06 §2` |
| 46 | Costo misurato: ~4.500 token in / 1.000-2.000 out e 8-16 s per sezione | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |
| 47 | Esito su budget_624 (CE riscattato, utile 8.906,79, `verified`) e su budget_623 (attivo riconciliato a 2.130.609,37 netti, mascheratura sparita, sbilancio non deterministico; dopo l'ancora sul passivo il riscatto viene SCARTATO quando alla vision sfugge un mastro) | `SPOSTATA IN docs/FIXING-IMPORT.md §6` (che oggi dichiara entrambi i file «open») |
| 48 | «Una sola esecuzione live dopo la correzione (1/1, non 6/6): un campione da uno non è una frequenza» | `SPOSTATA IN docs/FIXING-IMPORT.md §6` |
| 49 | Il ripiego del CE va scelto per DIREZIONE: `ce06` su una riga della colonna RICAVI è un COSTO e sposta il risultato di 2× (a destra si tiene `ce04`) | `RESTA` — testo: *Un secchio di ripiego è neutro solo dentro il proprio insieme: `ce06` è neutro fra i costi della produzione, ma su una riga letta nella colonna RICAVI è un costo, e sposta il risultato di **2×** il proprio importo. Il ripiego si sceglie per direzione (a destra `ce04`).* |
| 50 | Test: `tests/test_vision_rescue.py`, `tests/test_section_pages.py` | `SPOSTATA IN REGOLE-IMPORT-02 §4-bis` |

### `#### Trial-balance / Situazione Contabile parsers` (535-628)

| # | affermazione | destinazione |
|---|---|---|
| 51 | L'elenco dei sub-parser di route C e le loro condizioni di attivazione (DEPI, AGO 8 cifre, colonna unica, TeamSystem, contrapposte 8 cifre, verifica-per-segno, best-effort, DEPI flat) | `GIÀ IN REGOLE-IMPORT-03 §1` (con l'ordine di prova, che qui manca) |
| 52 | Il parser «verifica contrapposte PER SEGNO»: split per coordinata, mastri classificati per NATURA mai per colonna, netting fondi, scoperto vs cassa, split debiti, conto risultato a PN, `sp13` dal CE, auto-validazione con `ValueError`, `_skip_declared_reconcile` | `GIÀ IN IMPORT-ROUTING-TAXONOMY §6` e `REGOLE-IMPORT-03 §1/§5/§6` |
| 53 | Best-effort contrapposte: split colonne al cluster dei codici, riclassificazione mastri/subtotali per descrizione, fondi nettati, risultato dal gap del pareggio | `GIÀ IN REGOLE-IMPORT-03 §2/§3/§5` |
| 54 | Il residuo è **misurato, non tappato** (`_plug_residual`, log «nessun plug applicato», `masked` oltre l'1%) | `GIÀ IN REGOLE-IMPORT-00 §2 e §5 D1`, `REGOLE-IMPORT-04 §2` — l'invariante generale è la riga 79 |
| 55 | Typed debiti split (`_debt_type`), sotto-campi sp16a..g emessi accanto all'aggregato; Σ tipi = sp16, i sotto-campi sono display-only | `GIÀ IN REGOLE-IMPORT-03 §4` |
| 56 | Gross/net anchoring (`netted_contra`): l'ancora dichiarata è LORDA sulle presentazioni lorde e va ridotta della massa nettata | `GIÀ IN REGOLE-IMPORT-02 §4` («la correzione lordo→netto dell'ancora») e `REGOLE-IMPORT-03 §3` |
| 57 | Code-collision aggregation: due conti che normalizzano alla stessa stringa di cifre si SOMMANO, non si sovrascrivono | `GIÀ IN REGOLE-IMPORT-03 §3` |
| 58 | Secondo passaggio senza codice (`_be_collect_side(codeless=True)`): righe `descrizione importo` senza codice conto (budget_367), ritentato solo se il passaggio normale non ha trovato nulla, codici sintetici non prefissanti, gutter per split più bilanciato, colonna troncata al primo `TOTALE` di sezione | `SPOSTATA IN REGOLE-IMPORT-03 §2` |
| 59 | Rete di sicurezza «vuoto → best-effort» su file fisicamente a due colonne | `GIÀ IN REGOLE-IMPORT-03 §1` |
| 60 | Rescue dotted-hierarchical «BILANCIO 4 SEZIONI»: mastri livello-1 in ordine di documento, foglie troncate rigettate, fondi nettati a qualsiasi profondità, due cancelli di auto-validazione | `GIÀ IN REGOLE-IMPORT-03 §7` |
| 61 | Risultato dell'anno precedente non consolidato: riga tipicamente **senza codice** nel footer dell'SP («Utile esercizio precedente 68.228,65»), scartata da `_hier_collect` → il gap SP sovrastimava il risultato di quell'importo e il rescue veniva rigettato (budget_342). Ora finisce in `sp12`; solo righe code-less (una coduta sta già dentro un mastro e raddoppierebbe); il risultato CORRENTE non è mai agganciato | `SPOSTATA IN REGOLE-IMPORT-03 §7` |

### `#### Balance hardening (anti-masking)` (630-651)

| # | affermazione | destinazione |
|---|---|---|
| 62 | `validate_balance` fallisce su `totale_attivo == 0` e quando gli aggregati non ricostruiscono i totali dichiarati | `GIÀ IN REGOLE-IMPORT-04 §4` e `IMPORT-OVERVIEW §9` |
| 63 | I correttori LLM cappano la correzione, non portano un campo sotto zero, ed emettono `BILANCIO NON QUADRATO` | `GIÀ IN IMPORT-OVERVIEW §9` |
| 64 | Dual-year: si scarta un anno precedente fabbricato quando il PDF ha una sola colonna importi | `GIÀ IN REGOLE-IMPORT-02 §5` e `IMPORT-OVERVIEW §9` |
| 65 | `ce03_lavori_interni` incluso nel Valore della Produzione; le imposte estratte non vengono sovrascritte | `GIÀ IN REGOLE-IMPORT-04 §3`, `REGOLE-IMPORT-06 §2`, `IMPORT-OVERVIEW §9` |
| 66 | `_coerce_year_blob`: una colonna serializzata da Haiku come stringa JSON-ish con numeri italiani non fa più fallire l'import | `GIÀ IN IMPORT-OVERVIEW §9` |
| 67 | `SP_END_KEYWORDS`: la finestra SP chiude su qualsiasi variante «Totale … passivo/passività» | `GIÀ IN IMPORT-OVERVIEW §9` |
| 68 | Guardia sulla sezione di testa azzerata (`find_section_pages`): le finestre scivolano a una seconda copia con header e importi veri; non si rilocalizza su un blocco di soli numeri | `GIÀ IN IMPORT-OVERVIEW §9` |

### `#### IV-CEE detail-line reconciler` (653-688)

| # | affermazione | destinazione |
|---|---|---|
| 69 | `_reconcile_pn_detail` (A.II-A.X → sp12a..h, somma ALGEBRICA, gated sul «Totale patrimonio netto» stampato) e il caso LIO 2025 (cassa 106.156 → 150.156) | `GIÀ IN IMPORT-ROUTING-TAXONOMY §6` e `IMPORT-BALANCING-SCHEME L5-bis` |
| 70 | `_reconcile_personale_detail` (B.9 a/b/c/e → ce08a/b/c/d) e il lookahead `(?!\s+di\s+lavoro)` che distingue la riga CE dal fondo TFR di SP | `GIÀ IN IMPORT-ROUTING-TAXONOMY §6` e `IMPORT-BALANCING-SCHEME L5-bis` |
| 71 | Copertura dei formati gestionali (prefisso `A.` opzionale, separatore o solo spazio, `_values_for_label` salta un `Totale <voce>` interposto); FLUIVER, Zucchetti, BERTELLI | `GIÀ IN IMPORT-ROUTING-TAXONOMY §6` |
| 72 | Correzione monocolonna: `extract_pdf_both_years_with_llm` non esce più presto, svuota il precedente e lascia girare validatori e reconciler sulla colonna corrente | `GIÀ IN IMPORT-ROUTING-TAXONOMY §6` |
| 73 | Scoping crediti: sp06/sp07 ristretti a C.II, esclusi i B.III.2 crediti immobilizzati (che sono sp04) | `GIÀ IN IMPORT-ROUTING-TAXONOMY §6` e `REGOLE-IMPORT-06 §2` |
| 74 | Colonna corrente azzerata (Step 4c): la precedente viene promossa a corrente | `GIÀ IN REGOLE-IMPORT-02 §5` e `IMPORT-ROUTING-TAXONOMY §6` |

### `#### CE↔SP identity enforcement` (690-714)

| # | affermazione | destinazione |
|---|---|---|
| 75 | Il risultato dell'esercizio è UN numero: `sp13` nello SP e ultima riga del CE; SP e CE sono estratti separatamente e possono divergere | `GIÀ IN REGOLE-IMPORT-04 §2` (controllo 4) |
| 76 | `enforce_ce_sp_identity` gira dopo il blocco di ogni route e prima di `validate_balance`, XBRL nativo compreso (budget_361/404) | `GIÀ IN REGOLE-IMPORT-02 §1` (fase 5) e `IMPORT-BALANCING-SCHEME` («Pipeline per route») |
| 77 | **Non muta più nulla**: espone `_ce_sp_difference` e logga «nessuna voce CE/SP è stata modificata»; `prefer=`/`declared=` restano per compatibilità di firma | `GIÀ IN REGOLE-IMPORT-00 §5 D3` e `docs/FIXING-IMPORT.md §0` |
| 78 | Idem per `reconcile_ivcee_balance` (`cap_frac` vestigiale) e per il best-effort (`_plug_residual` misurato) | `GIÀ IN REGOLE-IMPORT-00 §5 D1/D4` |
| 79 | «Per molto tempo `CLAUDE.md` ha descritto plug che il codice aveva smesso di applicare, e mandava a cercare un bug dentro un plug inesistente» | `RESTA` — testo: ***Diagnose, never fabricate.** Un divario si misura e si dichiara; non si tappa. `enforce_ce_sp_identity`, `reconcile_ivcee_balance` e il parser best-effort non modificano nulla: espongono `_ce_sp_difference`, `_declared_assets_difference`, `_plug_residual`, e la correzione la fa l'utente in Rettifiche. Non cercare un bug dentro un plug che non esiste.* |

### `#### IV-CEE leveling + quadratura engine` (716-818)

| # | affermazione | destinazione |
|---|---|---|
| 80 | `iv_cee_hierarchy` è uno stadio condiviso a VALLE delle quattro route, non un router | `GIÀ IN IMPORT-QUADRATURA-ENGINE §1` e `IMPORT-OVERVIEW §7` |
| 81 | `data/iv_cee_tree.json`: struttura dei nodi, foglie legali che coprono sp01-18 + ce01-20, deliberatamente solo di livello LEGALE (nessun alias di piano dei conti: raddoppierebbe nell'aggregazione piatta di A/B) | `GIÀ IN IMPORT-QUADRATURA-ENGINE §2.1` e `IMPORT-OVERVIEW §7` |
| 82 | `resolve(desc, side)` è conservativo (`None` quando non è sicuro, così `_be_reclassify` scende invece di sbagliare) | `GIÀ IN IMPORT-OVERVIEW §7` e `REGOLE-IMPORT-03 §3` |
| 83 | **Non** usarlo per ribaltare il LATO attivo/passivo di una riga di trial balance: la COLONNA è la verità; i conti ambigui cambiano lato per colonna, non per descrizione (tentato e revertito) | `RESTA` — testo: *La **colonna** è la verità sul lato attivo/passivo; la **descrizione** decide la voce. Mai il contrario: `ERARIO C/`, `DEPOSITI BANCARI`, `FORNITORI C/ANTICIPI` cambiano lato per colonna. È stato tentato e revertito, ha regredito file puliti.* (dettaglio `GIÀ IN REGOLE-IMPORT-03 §2` e `IMPORT-OVERVIEW §9`) |
| 84 | `side` non filtra NULLA sui nodi CE (`Node.side` è popolato solo per lo SP): un costo può risolversi su un ricavo — `DIFFERENZE CAMBIO PASSIVE` → `ce16` sposta l'importo di 2× nella gestione finanziaria. Il ripiego di route C deve passare da `_resolve_ce_field`, vincolato agli allowlist `_CE_COST_FIELDS`/`_CE_REVENUE_FIELDS`, disgiunti e di unione esatta le 21 foglie CE | `RESTA` — testo: *Per classificare una voce di CE usare `situazione_contabile_parser._resolve_ce_field(desc, direction)`, **mai** `iv_cee_hierarchy.resolve(side=…)`: su un nodo CE `side` non filtra nulla, un costo può risolversi su un ricavo e il risultato si sposta di **2×** il suo importo.* (parziale `GIÀ IN docs/FIXING-IMPORT.md §1`) |
| 85 | `check_quadratura`: pareggio + identità CE↔SP + anti-masking (`_plug_residual` oltre l'1%) + `is_empty`; `quadra` richiede `not is_empty and not masked` | `GIÀ IN REGOLE-IMPORT-04 §2` |
| 86 | «Un'estrazione vuota dà att == pas == 0, cioè sbilancio zero: senza `is_empty` quadrerebbe» | `RESTA` — testo: *Attivo = Passivo = 0 non è una quadratura. Un'estrazione vuota ha sbilancio zero: senza il controllo `is_empty` risulterebbe il bilancio più pulito del corpus.* (dettaglio `GIÀ IN REGOLE-IMPORT-04 §1/§2`) |
| 87 | Selezione dell'estrattore di route C per completezza: gap dal totale dichiarato per primo, `_plug_residual` solo come spareggio; il residuo è cieco alla sotto-estrazione (AITEC: CoGe 9,92 M contro 12,65 M dichiarati); gap ignorato sotto il 2% | `GIÀ IN REGOLE-IMPORT-02 §4` (con la motivazione per esteso) |
| 88 | Contra-netting overlay: rilettura delle pagine SP, sovrascrittura di sp02/sp03 col netto, rimozione dai debiti dell'eccesso cappato ai fondi, i due cancelli (1% e 0,5%), ancora ridotta della massa nettata, idempotenza | `GIÀ IN REGOLE-IMPORT-03 §3` e `SCHEMA-RICONOSCIMENTO §I.4` |
| 89 | La fase di applicazione del netting è **atomica**: snapshot prima della prima scrittura e rollback completo se qualcosa solleva, poi `detected>0 / applied==0`. Senza, un fallimento a metà lasciava un foglio MEZZO nettato senza i marcatori `_contra_*`, che il motore di affidabilità legge come «su questa route non gira nessuna scansione» | `SPOSTATA IN REGOLE-IMPORT-03 §3` |
| 90 | Partizione per riconciliazione e non per prefisso di codice: `c.startswith(code)` no-oppa in silenzio su piani con codici disgiunti (AGO: mastri 8 cifre, figli 9 cifre); su `613_2024` l'attivo era sovra-letto di 41.613,46 (0,836%) e 2,25 M di fondi restavano fra i debiti **su un foglio che quadrava** | `GIÀ IN SCHEMA-RICONOSCIMENTO §I.4` e `REGOLE-IMPORT-03 §3` — l'invariante generale è la riga 91 |
| 91 | La profondità del codice è solo un generatore di ipotesi; il totale che il DOCUMENTO stampa è il giudice. Senza totale dichiarato si torna al comportamento storico con `reconciled=False`, così il chiamante sa che la scansione non è verificata | `RESTA` — testo: *Mai dedurre la parentela fra conti dal **prefisso** o dalla **lunghezza** del codice: i piani dei conti sono specifici del gestionale (AGO stampa mastri a 8 cifre con figli a 9, nessuno prefisso dell'altro). La profondità genera ipotesi; il **totale stampato dal documento** decide. Nessun totale ⇒ scansione dichiarata non verificata, mai data per buona.* |
| 92 | `_select_dedup` restituisce la **regola** vincente, non un'etichetta: un'etichetta verrebbe risolta di nuovo sulle righe che le vengono passate e potrebbe ricadere in silenzio sul dedup per prefisso sul lato passivo | `SPOSTATA IN REGOLE-IMPORT-03 §3` |
| 93 | Entrambi i consumatori di route C la usano: `net_contra_accounts` e l'ancora della selezione (`contra_declared_total`/`contra_scan_mass`), che decide CoGe-LLM contro deterministico | `SPOSTATA IN REGOLE-IMPORT-03 §3` |
| 94 | «Si sommano i mastri OPPURE le foglie, mai entrambi» | `GIÀ IN REGOLE-IMPORT-03 §3` — l'invariante generale è la riga 91 |
| 95 | Un bilancio di verifica leggibile non viene MAI bloccato: si importa con flag non bloccante, per la correzione in Rettifiche | `GIÀ IN REGOLE-IMPORT-03 §8` (divieto 12) e `REGOLE-IMPORT-06 §5` |
| 96 | L'LLM **IV-CEE** è l'estrattore sbagliato per una verifica, ed è l'ultima risorsa solo quando il deterministico esce davvero VUOTO | `GIÀ IN IMPORT-OVERVIEW §5` (tabella) e `REGOLE-IMPORT-03 §1` |
| 97 | `Test/_quadratura_harness.py` misura il tasso di quadratura sul corpus (deterministico di default, `--llm` per A/B) | `SPOSTATA IN REGOLE-IMPORT-03 §9` — con l'avvertenza che `Test/` è in `.gitignore` (riga 111 di `.gitignore`) e **non esiste in un clone**: è uno strumento locale, non una parte del repo |
| 98 | CAVEAT: l'harness fa `extract → check_quadratura` ma non le due fasi di produzione successive, quindi un «NO» dell'harness non è «non importa» (budget_152/254/289/336); è autorevole solo sulla mascheratura | `GIÀ IN docs/FIXING-IMPORT.md §0` |
| 99 | L'estrazione LLM di route A/B è **non deterministica**: SI/NO possono ribaltarsi fra esecuzioni sullo stesso file — è rumore, non una regressione | `RESTA` — testo: *L'estrazione LLM (route A/B, e il pass CoGe) **non è deterministica**: lo stesso file può dare due esiti diversi a otto minuti di distanza. Un sospetto di regressione si conferma sul percorso di produzione e su più esecuzioni, mai su una sola.* (casi `GIÀ IN IMPORT-OVERVIEW §5/§11`) |
| 100 | Messaggio «Formato non supportato» (`_is_aggregated_summary`), emesso al punto di fallimento di `validate_balance` per i riepiloghi senza sottostruttura IV-CEE | `GIÀ IN REGOLE-IMPORT-04 §5` (con l'ordine di precedenza completo dei sei messaggi) |
| 101 | `_be_split` sceglie il gutter che BILANCIA le righe con descrizione, non il gap più largo | `GIÀ IN REGOLE-IMPORT-03 §2` e `IMPORT-OVERVIEW §9` |

### `#### Label semantics` (820-841)

| # | affermazione | destinazione |
|---|---|---|
| 102 | Una voce di legge ha UN significato e N grafie per gestionale; l'LLM le regge, a rompersi sono i **cancelli deterministici** che decidono se accettarne l'output — quando uno non riconosce una grafia, un'estrazione CORRETTA viene rifiutata | `SPOSTATA IN REGOLE-IMPORT-03 §3-bis` |
| 103 | Sei forme normali incompatibili coesistevano; una era un bug vivo: `bilancio_classifier` cercava `passivita`/`disponibilita liquide` **senza deaccentare**, e su testo accentato il file cadeva in `ROUTE_UNSUPPORTED` | `SPOSTATA IN REGOLE-IMPORT-01 §2` — e **corregge** quel paragrafo, che oggi dichiara il difetto ancora aperto («è una fragilità latente»): `compute_signals` deaccenta entrambe le viste e il marcatore cercato (`bilancio_classifier.py:57-79`) |
| 104 | `normalize_label` è la forma canonica unica, idempotente, e **non inventa parole**; il path civilistico non è rumore, viene estratto in `path_hint` | `SPOSTATA IN REGOLE-IMPORT-03 §3-bis` |
| 105 | Tre spazi target (voce / marcatore / conto) in `data/label_dictionary.json`, misurati su 72 documenti: marcatori 100% irrisolti prima, conti 63%, legale 42% | `SPOSTATA IN REGOLE-IMPORT-03 §3-bis` |
| 106 | Consumato da `_is_fondo_amm`, che riconosce `F.di ammor.to` / `Fdo amm` / `Fondo amm.` via la forma contigua `fondo ammortamento`. Quella funzione governa tutto il netting di route C: un fondo non riconosciuto lascia l'attivo lordo. I costi di CE restano esclusi | `SPOSTATA IN REGOLE-IMPORT-03 §3-bis` (il divieto di nettare le quote di CE è già in `REGOLE-IMPORT-03 §3`) |

### `#### Fallback + materiality policy` (843-865)

| # | affermazione | destinazione |
|---|---|---|
| 107 | «Un plug INVENTA massa ed è vietato; un fallback ETICHETTA massa che è stata davvero letta ed è ammesso» | `RESTA` — testo: *Un **plug** inventa massa ed è vietato; un **fallback** etichetta massa che è stata davvero letta ed è ammesso. Non sono la stessa cosa e la differenza è tutta qui.* (motivazione `GIÀ IN SCHEMA-RICONOSCIMENTO §III.3`) |
| 108 | `TIER0_FIELDS` = sp02/sp03/sp04, sp11/sp12/sp13, sp16a/sp17a, ce09 — un fallback non può scriverli mai; un errore lì cambia un TOTALE e rompe PFN, ROI, indipendenza finanziaria e i due modelli di rating in un colpo | `RESTA` — testo: *`TIER0_FIELDS` (immobilizzazioni nette, patrimonio netto, debiti verso banche, `ce09`) non è mai una destinazione di ripiego: `ce09` è l'unico confine di KPI dentro i costi operativi (`EBITDA = EBIT + ce09`), gli altri spostano un totale.* |
| 109 | `FALLBACK_FIELDS = {'ce': 'ce06', 'bs': 'sp16g'}` — destinazioni KPI-neutre, e **sempre un SOTTO-campo**: `projection_common.base_bank_debt` assegna alle BANCHE ogni scarto aggregato/dettaglio, quindi massa lasciata sull'aggregato diventa debito bancario fantasma | `RESTA` — testo: *La massa non riconosciuta va in un **sotto-campo** esplicito (`ce06`, `sp16g`), mai su un aggregato: `projection_common.base_bank_debt` assegna alle BANCHE qualunque scarto fra `sp16`/`sp17` e la somma dei loro dettagli, e il residuo diventa debito bancario fantasma con tanto di piano di rimborso.* (parziale `GIÀ IN SCHEMA-RICONOSCIMENTO §II.1`) |
| 110 | `materiality_threshold(total) = max(1.000 €; 0,1% dell'attivo)`, definizione canonica in `importers/reliability.py`, ri-esportata dal parser perché la regola sia una sola | `SPOSTATA IN REGOLE-IMPORT-03 §8-bis` (oggi in `/docs` esiste solo come *proposta*, `SCHEMA-RICONOSCIMENTO §III.1`) |
| 111 | `fallback_field(statement)` dà la destinazione dentro un ciclo di classificazione; `fallback_bucket(...)` aggiunge il verdetto di materialità quando il totale è noto e rifiuta un `target` di tier 0; la massa materiale si accumula in `_unclassified_mass` invece di sparire | `SPOSTATA IN REGOLE-IMPORT-03 §8-bis` |
| 112 | Ordine di classificazione in `_hier_reconstruct`: tabella di keyword → albero IV-CEE condiviso (`_resolve_ce_field`, vincolato per direzione) → catch-all. Puramente additivo. È ciò che ha smesso di seppellire 36.500,17 di ammortamenti nel catch-all `ce12` di budget_342: totali e `sp13` restavano corretti, nessun cancello scattava, ed EBITDA era sbagliato | `SPOSTATA IN REGOLE-IMPORT-03 §8-bis` (in `/docs` è l'«opzione 2a» proposta in `SCHEMA-RICONOSCIMENTO §IV`) |
| 113 | «L'imprecisione DENTRO un aggregato è accettata per progetto (l'utente rifinisce in Rettifiche); ciò che non è accettato è massa che attraversa un aggregato o un confine di KPI» | `RESTA` — testo: *Un errore **dentro** un aggregato è accettato: l'utente lo rifinisce in Rettifiche. Un errore che **attraversa** un aggregato o un confine di KPI no — cambia un numero su cui si decide.* |

### `#### Critical-account reliability + il gate forecastable` (867-890)

| # | affermazione | destinazione |
|---|---|---|
| 114 | `reliability.py` è puro e senza dipendenze (niente I/O, PDF, DB), riusabile dagli importer XBRL/CSV | `SPOSTATA IN REGOLE-IMPORT-04 §9` |
| 115 | `AccountStatus` = VERIFIED / DERIVED / UNRELIABLE e i tre gruppi valutati (immobilizzazioni dai marcatori `_contra_*`, patrimonio netto contro un totale stampato, debiti banche con lo stesso calcolo di `base_bank_debt`) | `SPOSTATA IN REGOLE-IMPORT-04 §9` |
| 116 | **`UNRELIABLE` richiede una contraddizione POSITIVA, mai un controllo assente**: un controllo che manca dà `DERIVED`. Senza questa regola ogni file di route A/B sarebbe segnalato solo perché su quelle route non gira nessuna scansione dei contro-conti | `RESTA` — testo: *Un verdetto negativo vuole una **contraddizione**, non un controllo assente. Vale in `reliability.assess`, nel cancello del riscatto vision (`residual_measured`) e nel gate infrannuale: un controllo che manca è «non lo so», e «non lo so» non blocca.* |
| 117 | `to_dict()` finisce nel `validation_report` sotto `critical_accounts`; `forecastable = semantic_valid and all_critical_ok` | `SPOSTATA IN REGOLE-IMPORT-04 §9` — e **corregge** `REGOLE-IMPORT-04 §9` e `REGOLE-IMPORT-06 §2`, che dicono «`forecastable` è sempre uguale a `semantic_valid`»: dal 2026-07 è `_qd.semantic_valid and _critical_ok` (`pdf_importer.py:1534`) |
| 118 | **Il verdetto gate il FORECAST, mai il SAVE**: le Rettifiche operano su un `FinancialYear` persistito, quindi rifiutare il salvataggio renderebbe il file incorreggibile per sempre. Un errore nel calcolo del verdetto vale «non lo so», e «non lo so» non blocca. `PUT /adjustments` conserva `critical_accounts` e lo riapplica, così una rettifica a vuoto non può ripulire il flag | `RESTA` — testo: *Un verdetto di inaffidabilità blocca il **previsionale**, mai il **salvataggio**: le Rettifiche lavorano su un `FinancialYear` già persistito, e un file non salvato sarebbe incorreggibile per sempre.* |
| 119 | Limite noto: nessun percorso di previsionale legge `fy.forecastable` (l'infrannuale ri-deriva il proprio gate, il budget non ne ha, `promote_service` scrive `True` fisso); `patrimonio_netto` resta sempre `DERIVED` perché `_declared_control_totals` non produce una chiave `patrimonio_netto` | `SPOSTATA IN REGOLE-IMPORT-04 §9` (parziale `GIÀ IN REGOLE-IMPORT-05 §6`, che spiega perché il motore ri-deriva) |

### `#### The intra-year forecast gate` (892-917)

| # | affermazione | destinazione |
|---|---|---|
| 120 | Il gate blocca: bilancio vuoto, sbilancio SP, disaccordo CE/SP, plug persistito nella fonte, mismatch aggregato/dettaglio sulle voci che il motore scala o riporta | `GIÀ IN REGOLE-IMPORT-05 §6` (G1-G6, con le soglie) |
| 121 | **Una ripartizione ASSENTE non è un mismatch**: un abbreviato dichiara solo l'aggregato e i distributori lo riportano invariato senza inventare nulla. Blocca solo una ripartizione DICHIARATA che non somma al suo aggregato | `SPOSTATA IN REGOLE-IMPORT-05 §6` — `§6` oggi descrive G5 come se bloccasse anche l'assenza |
| 122 | `sp16`/`sp17` sono l'eccezione e bloccano comunque, perché lì `base_bank_debt` trasforma davvero l'assenza in debito bancario fantasma (finding C2 aperto) | `SPOSTATA IN REGOLE-IMPORT-05 §6` |
| 123 | `detail_fields()` in `iv_cee_hierarchy` è l'accessore pubblico sulla mappa che usa `check_quadratura`, così il gate non la riscrive | `SPOSTATA IN REGOLE-IMPORT-05 §6` |
| 124 | Il fallimento era INVISIBILE: `bulk_upsert_assumptions` cattura l'errore e restituisce **HTTP 200** con `forecast_generated: false`, nessun `ForecastYear` scritto, `forecast_years: []`, e la colonna Proiezione vuota sotto un toast di successo | `RESTA` — testo: *Chi chiama l'endpoint bulk delle assumptions deve leggere **`forecast_generated`**, non l'HTTP 200: un previsionale rifiutato torna comunque 200, con la ragione in `message`. Ignorarlo dipinge una colonna Proiezione vuota sotto un toast verde.* |

### `#### MinerU OCR` (919-956)

| # | affermazione | destinazione |
|---|---|---|
| 125 | Backend OCR opzionale per PDF scansionati, configurato in `backend/app/core/config.py` | `SPOSTATA IN REGOLE-IMPORT-02 §5-bis` |
| 126 | **Solo macchina di sviluppo: MinerU non va MAI sul VPS.** L'immagine è `FROM vllm/vllm-openai`; il servizio sta dietro un compose profile che lo esclude da *ogni* comando compose, `build` compreso — e il `Jenkinsfile` fa `docker compose build --no-cache --parallel` sul VPS di staging. `MINERU_OCR_ENABLED` è `false` di default nell'env del backend per la stessa ragione | `RESTA` — testo: *MinerU non va **mai** sul VPS: la sua immagine è `FROM vllm/vllm-openai` (gigabyte, orientata GPU). Sta dietro il compose profile `mineru`, che lo esclude da ogni comando compose — `build` compreso — perché il `Jenkinsfile` esegue `docker compose build --no-cache --parallel` sullo staging. Toglierlo dal profile trascina vLLM sul server.* |
| 127 | Come si avvia in locale (`MINERU_OCR_ENABLED=true docker compose --profile mineru up -d`, variante NVIDIA) | `SPOSTATA IN REGOLE-IMPORT-02 §5-bis` |
| 128 | Con OCR spento il backend è indifferente: import dentro l'endpoint (mai a caricamento modulo), `ocr_available: false`, 503 `MINERU_DISABLED` reso come «Il servizio OCR non è disponibile» | `SPOSTATA IN REGOLE-IMPORT-02 §5-bis` |
| 129 | Il pulsante OCR **non è reso** (2026-08-14): rimozione semplice, non un controllo di capability; `getImportCapabilities` esiste e resta non cablato, il percorso client (`importOCR`, `handleImport("pdf_ocr")`) è intatto | `SPOSTATA IN REGOLE-IMPORT-02 §5-bis` — verificata: `frontend/app/pratica/page.tsx:1377-1381` (commento) e nessun render del pulsante; la formulazione precedente («the OCR button stays visible by design») era falsa ed è già stata corretta |
| 130 | Provenienza OCR: `validation_report["ocr"]` (engine, versione, pagine, tabelle, `accounting_method`, `source_detail_fields`, `detail_level`) e suffisso `+mineru-<ver>` su `parser_version` | `SPOSTATA IN REGOLE-IMPORT-06 §2` |
| 131 | Test (`tests/test_mineru_*.py`, `tests/test_pdf_ocr_endpoint.py`) e piano (`docs/piano-import-2026-07/14-PIANO-INTEGRAZIONE-MINERU-OCR.md`) | `SPOSTATA IN REGOLE-IMPORT-02 §5-bis` |

### `#### Import regression baseline` (958-964)

| # | affermazione | destinazione |
|---|---|---|
| 132 | `tests/fixtures/import_baseline.json`: registro versionato, indicizzato per hash del contenuto, di che cosa importa ogni file del corpus; `tests/_import_probe.py` esegue fedelmente il percorso di produzione, `scripts/refresh_import_baseline.py` rigenera, `tests/test_import_baseline.py` verifica campo per campo | `SPOSTATA IN REGOLE-IMPORT-06 §7` |
| 133 | Ogni voce dichiara se i valori sono `verified` (confrontati col documento) o solo `observed`; è questo — non una singola esecuzione dell'harness — a rispondere a «la mia modifica ha spostato qualcosa?» | `SPOSTATA IN REGOLE-IMPORT-06 §7` |

### Fuori dal blocco import, incontrata durante la verifica

| # | affermazione | destinazione |
|---|---|---|
| 134 | (sezione «Intra-Year Engine», `CLAUDE.md:388`) «Quadratura gate: rifiuta di promuovere una proiezione il cui SP è sbilanciato (attivo−passivo > €5)» | `OBSOLETA` — **corretta sul posto** in questo task, perché una soglia in euro inesistente manda a cercare il posto sbagliato: il cancello è `check_quadratura(...).semantic_valid` (`backend/app/services/promote_service.py:46-57`), cioè pareggio **e** identità CE↔SP **e** non mascherato **e** coerenza aggregati/dettagli. Già registrato come D5 in `REGOLE-IMPORT-00-INDICE §5` |
