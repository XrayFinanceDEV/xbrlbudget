# Regole di importazione del bilancio — indice generale

> **Data:** 2026-07-16 · **Branch:** `fix/import-netting-2026-07`
> **Fonte:** il codice, letto riga per riga. Dove un documento preesistente contraddice il
> codice, vince il codice e la contraddizione è registrata al §5 di questa pagina.
>
> Questa serie descrive **regole e comportamenti**, non implementazione. Non contiene codice
> Python: i riferimenti `file:riga` servono a ritrovare la regola, non a leggerla.

## 1. A chi serve e come si legge

Il lettore atteso è tecnico ma non necessariamente programmatore: un commercialista che deve
capire perché un bilancio è stato rifiutato, un analista che deve fidarsi di un numero
importato, uno sviluppatore che deve cambiare una regola senza romperne altre tre.

Ogni pagina è autonoma. L'ordine sotto è quello in cui i fatti accadono a un file caricato.

| # | Pagina | Copre |
|---|---|---|
| 01 | [Riconoscimento route](REGOLE-IMPORT-01-ROUTING.md) | Come si decide *che cosa è* un documento e a quale estrattore va |
| 02 | [Estrazione e scelta dell'estrattore](REGOLE-IMPORT-02-ESTRAZIONE.md) | Ordine di lettura del testo, deterministico vs LLM, riscatto vision, OCR, XBRL, CSV, come si sceglie il candidato |
| 03 | [Spacchettature e netting](REGOLE-IMPORT-03-SPACCHETTATURE-NETTING.md) | Ricostruzione righe, fondi ammortamento, grafie, tipizzazione debiti, entro/oltre, dove può finire la massa non classificata |
| 04 | [Quadrature, gate e rifiuti](REGOLE-IMPORT-04-QUADRATURE.md) | I controlli contabili, le tolleranze, i messaggi di errore e il loro ordine, l'affidabilità dei conti critici |
| 05 | [Bilancio infrannuale](REGOLE-IMPORT-05-INFRANNUALE.md) | Periodi parziali, annualizzazione, roll-forward, i gate del previsionale |
| 06 | [Persistenza e round-trip](REGOLE-IMPORT-06-PERSISTENZA.md) | Cosa finisce sul DB, stati di validazione, hash, versioni, provenienza, baseline di regressione |

Documenti preesistenti nella stessa cartella ([IMPORT-OVERVIEW](IMPORT-OVERVIEW.md),
[IMPORT-ROUTING-TAXONOMY](IMPORT-ROUTING-TAXONOMY.md),
[IMPORT-QUADRATURA-ENGINE](IMPORT-QUADRATURA-ENGINE.md),
[IMPORT-BALANCING-SCHEME](IMPORT-BALANCING-SCHEME.md),
[TRIAL-BALANCE-IMPORT](TRIAL-BALANCE-IMPORT.md)) restano validi come contesto storico e di
progetto, ma **non** come specifica: vedi §5.

## 2. Il principio che governa tutto: diagnosticare, mai fabbricare

Ogni regola di questa serie discende da un'unica scelta di fondo, e conviene enunciarla prima
di tutto perché spiega decisioni che altrimenti sembrano ostili all'utente:

> **L'import non aggiusta il bilancio sorgente. Se i numeri stampati non tornano, l'import lo
> dice e si ferma. Non esiste una correzione automatica che renda vero un documento falso.**

Concretamente, il codice non ha più il permesso di:

- creare un importo di cassa o di debito per far quadrare l'attivo col passivo;
- spostare massa nelle riserve, negli altri ricavi o negli oneri diversi per far coincidere il
  Conto Economico con lo Stato Patrimoniale;
- ricostruire uno Stato Patrimoniale da un documento che contiene solo il Conto Economico;
- inventare la ripartizione di un aggregato di cui non conosce i dettagli;
- capovolgere il segno di una voce perché "così torna".

Il corollario, meno ovvio ma più importante: **una quadratura perfetta non è una prova di
correttezza**. Un estrattore che perde metà dei conti e poi forza il pareggio produce un
bilancio che quadra ed è sbagliato. Il caso di riferimento è budget_395: quadra con residuo
zero, e ha `sp02`/`sp03` entrambi errati. Per questo la validazione ha controlli separati per
il pareggio, per l'identità CE↔SP, per la coerenza aggregati/dettagli e per la massa non
classificata — e per questo la scelta fra due estrattori non guarda il residuo per primo.

## 3. Le quattro strade di un file

| Route | Che documento è | Estrattore |
|---|---|---|
| `XBRL_NATIVE` | istanza XBRL (`.xbrl`/`.xml`) | parser XBRL nativo |
| `IVCEE` (aree A/B) | prospetto redatto secondo lo schema di legge art. 2424/2425 | deterministico se quadra, altrimenti LLM |
| `TRIAL_BALANCE` (area C) | bilancio di verifica / situazione contabile / sezioni contrapposte | famiglia di parser deterministici, LLM come concorrente |
| `UNSUPPORTED` | non è un prospetto importabile | rifiuto motivato |

Il CSV ha un percorso proprio, parallelo (vedi pagina 02).

## 4. Le costanti che decidono di più

Raccolte qui perché sono i numeri che più spesso spiegano un comportamento. Il dettaglio e la
motivazione stanno nelle pagine relative.

| Soglia | Valore | Cosa decide |
|---|---|---|
| Testo minimo per "non è una scansione" | 50 caratteri sulle prime 14 pagine | attiva o no il ramo OCR |
| Testo corrotto (garbled) | oltre il 30% degli importi spezzati, con almeno 10 in assoluto | esclude i totali dichiarati da ogni decisione |
| Tolleranza di pareggio (PDF) | €2 | attivo = passivo |
| Tolleranza di pareggio (CSV/XBRL) | €0,01 | attivo = passivo |
| Tolleranza identità CE↔SP | `max(€2; 0,1% del totale attivo)` | utile CE = `sp13` |
| Quadratura mascherata | residuo oltre l'1% del totale attivo | declassa a non quadrato |
| Gap di completezza (route C) | ignorato sotto il 2% del totale dichiarato | quale estrattore vince |
| Gate del netting fondi | massa nettata oltre l'1% del dichiarato, e lordo che riconcilia entro lo 0,5% | se nettare o lasciare stare |
| Tolleranza Rettifiche | €5 | una modifica può non peggiorare oltre questo |

## 5. Disallineamenti noti fra documentazione e codice

Rilevati il 2026-07-16 confrontando il codice con i documenti esistenti. **Il codice è la
fonte autorevole**; queste voci sono da correggere nei documenti citati.

| # | Il documento dice | Il codice fa | Dove |
|---|---|---|---|
| D1 | Il residuo viene "tamponato in sp09/sp16" | **Nessun plug viene applicato.** Il residuo è solo *misurato* e dichiarato | `CLAUDE.md`. **I messaggi utente sono stati corretti il 2026-07-16**: ora dicono "non classificato", vedi sotto |
| D2 | `SC_PLUG_REJECT_PCT` (20%) è una soglia di rifiuto | Non rifiuta nulla: scala solo la severità del testo del warning fra "parziale" e "prevalentemente stimata" | `pdf_importer.py:194`, `:788-797` |
| D3 | `enforce_ce_sp_identity` riallinea il CE (plug in `ce04`/`ce12`, spostamento in riserve con cap 10%) | È **puramente diagnostico**: espone `_ce_sp_difference` e non muta né CE né SP | `iv_cee_hierarchy.py:520-553` |
| D4 | `reconcile_ivcee_balance` tampona la differenza (`cap_frac=0.05`) | Ritorna una copia invariata e riporta la differenza. `cap_frac` è tenuto solo per compatibilità di firma | `iv_cee_hierarchy.py:493-517` |
| D5 | Il gate di promozione è "€5" | È il gate `semantic_valid` completo, non una soglia in euro | `promote_service.py:46-57` |
| D6 | La tassonomia copre 124 file / 77 unici | Il corpus è a **214 file fisici / 137 contenuti unici** | `IMPORT-ROUTING-TAXONOMY.md:2-4`; manifest corrente |
| D7 | Il blocco B richiede `legal_skeleton AND coge_codes>=5` | La soglia `coge_codes>=5` la richiede **solo B2**; B1 e B3 no | `IMPORT-ROUTING-TAXONOMY.md:142` vs `bilancio_classifier.py:227-238` |
| D8 | I segnali `sit_contabile` e `dare_avere` sono elencati fra i discriminanti | Sono **calcolati e mai letti** da nessuna regola: puramente diagnostici | `bilancio_classifier.py:73`, `:117` |
| D9 | La tassonomia elenca A4/Cerved, A5/riepiloghi AI, B4, C1b, C5 | Il router **non produce mai** queste sottocategorie | `IMPORT-ROUTING-TAXONOMY.md:59-88` |

**D1 era l'unico disallineamento che raggiungeva l'utente finale**, ed è stato corretto il
2026-07-16. I due messaggi dicevano "tamponato in liquidità/debiti" e "tamponato in sp09/sp16",
descrivendo un'operazione che non avviene più. Ora dicono **"non classificato in alcuna voce"**
e **"non classificato"**: il residuo misura massa che non è stata attribuita a nessuna voce
IV-CEE, e il bilancio resta esattamente come è stato letto. Le etichette `BILANCIO NON QUADRATO`
e `QUADRATURA MASCHERATA` sono invariate — restano vere e sono citate in tutta la documentazione.

**`CLAUDE.md` è stato ripulito** (2026-08-14): il blocco di 661 righe sull'import è stato sostituito
da una sezione breve che rimanda a questa serie, e le affermazioni superate sono registrate una per
una in `docs/superpowers/2026-08-14-inventario-claude-md.md`. Da lì in avanti, **questa cartella è
la sede dell'import**: una regola nuova si scrive qui, non là.

## 6. Codice dichiarato morto

Da non documentare come funzionalità:

- `is_contrapposte_depi` / `parse_entries_contrapposte_depi`
  (`situazione_contabile_parser.py:1652`, `:1690`) — i DEPI a sezioni contrapposte sono
  esplicitamente **rifiutati** da `is_situazione_contabile` (`:76-77`) e deferiti all'LLM. Il
  codice si autodichiara inutilizzato (`:1655-1658`).
- `xbrl_parser.py` (legacy) — riduce ogni contesto al solo anno, quindi collassa annuale e
  infrannuale dello stesso anno. Il parser di produzione è `xbrl_parser_enhanced.py`.
- `tests/test_hierarchical_import.py` — il nome inganna: è un diagnostico manuale **XBRL**,
  interamente skippato (`pytestmark = pytest.mark.skip`). Non copre la gerarchia dotted. Il
  riferimento corretto è `tests/test_prod_route_c.py`.
