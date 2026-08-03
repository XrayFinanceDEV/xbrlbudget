# Piano di adeguamento e collaudo end-to-end del bilancio

Data di esecuzione: 20 luglio 2026

## Obiettivo

Impedire che anomalie di importazione o di calcolo arrivino all'utente durante il
percorso operativo:

`PDF -> bilancio importato -> rettifiche -> ipotesi -> previsione -> promozione`

La verifica non si limita al messaggio di successo delle API: ogni passaggio deve
produrre dati persistiti contabilmente coerenti e utilizzabili dal passaggio
successivo.

## Matrice automatica implementata

Il test parametrico
`test_pdf_to_adjustments_to_assumptions_full_workflow_matrix` genera PDF IV-CEE
reali, li importa in un database isolato ed esegue tutto il percorso applicativo.

| Caso | Periodo | Variante verificata | Esito atteso |
|---|---:|---|---|
| Annuale ordinario | 12 mesi | patrimonio positivo, riserve voce VI, interesse stampato positivo | import e budget 2027-2028 |
| Annuale abbreviato | 12 mesi | patrimonio negativo, riserve voce VII | import e budget 2027-2028 |
| Infrannuale senza storico | 6 mesi | nessuna colonna precedente | annualizzazione e promozione 2026 |
| Infrannuale con parentesi | 9 mesi | negativi tra parentesi, riserve voce VI | annualizzazione e promozione 2026 |
| Infrannuale con meno finale | 3 mesi | formato `442.263,65-`, patrimonio negativo | annualizzazione finanziata e promozione 2026 |
| Sorgente contraddittoria | 6 mesi | Totale Passivo maggiore di 100 euro | rifiuto contabile prima di qualsiasi fallback AI |

Per ogni caso valido il test esegue e controlla:

1. importazione deterministica senza `ANTHROPIC_API_KEY`;
2. assenza di un esercizio precedente inventato;
3. stato `verified` e flag `forecastable`;
4. creazione dello snapshot originale delle rettifiche;
5. rettifica in partita doppia di cassa e debiti bancari;
6. conservazione dello snapshot e del registro rettifiche;
7. creazione dello scenario annuale o infrannuale;
8. salvataggio in blocco di ipotesi su ricavi, personale, investimenti,
   finanziamento, imposte differite e override SP/CE;
9. generazione automatica della previsione;
10. quadratura esatta Attivo = Passivo dopo il salvataggio a centesimi;
11. coerenza CE-SP e coerenza aggregati-dettagli IV-CEE;
12. per gli infrannuali, copia campo per campo e promozione a esercizio completo.

## Difetti trovati e logica corretta

### 1. PDF infrannuale monocolonna senza anno precedente

Il parser ora accetta una singola colonna quando SP e CE si validano sulla sorgente.
Il fallback LLM usa il prompt a un anno e non crea un esercizio comparativo che il
PDF non contiene.

### 2. Dettaglio delle immobilizzazioni perso nelle previsioni

I motori annuale e infrannuale calcolavano gli aggregati `sp02` e `sp03`, ma non
sempre propagavano le sottovoci. La previsione appariva quadrata, mentre il controllo
semantico della promozione la rifiutava.

La nuova logica conserva proporzionalmente la composizione della sorgente. Se il
documento abbreviato non espone dettagli, assegna il totale alla voce generica
prevista, senza perdere massa contabile.

### 3. Falso errore sul dettaglio dei debiti

Il controllo confrontava il totale debiti dell'anno precedente con sottovoci già
ricalcolate usando DPO, imposte e crescita dell'anno futuro. Qualunque variazione
poteva quindi apparire come dettaglio mancante.

Il controllo ora confronta esclusivamente valori omogenei dell'anno precedente;
solo dopo vengono applicate ipotesi, rimborso e nuovi finanziamenti.

### 4. Scarto di un centesimo nei budget pluriennali

I calcoli usano precisione estesa, mentre il database salva `Numeric(15,2)`.
Arrotondare ogni campo separatamente poteva produrre un centesimo di differenza dal
secondo anno in poi.

Prima del salvataggio vengono ora:

- arrotondate le voci CE a due decimali;
- riallineati i dettagli CE ai relativi aggregati;
- arrotondate le voci SP;
- assorbiti soltanto i residui di arrotondamento nelle voci generiche di dettaglio;
- ricalcolata la cassa sui valori aggregati già arrotondati.

In questo modo quadratura e gerarchie restano esatte anche sui valori realmente
letti dal database.

### 5. Documento sbilanciato segnalato come chiave AI mancante

I totali dichiarati Attivo e Passivo vengono controllati prima di scegliere il
motore di estrazione. Se la sorgente è contraddittoria, l'import restituisce lo
scarto esatto e chiede di correggere il documento originale; non propone più
`ANTHROPIC_API_KEY` come falsa soluzione.

## Criteri permanenti di accettazione

Una modifica al percorso bilancio è accettabile solo se:

- non inventa anni, saldi o classificazioni non sostenute dalla sorgente;
- una sorgente incoerente fallisce con diagnosi esplicita;
- le rettifiche non peggiorano quadratura, CE-SP o gerarchie;
- una previsione salvata è semanticamente valida, non solo aritmeticamente quadrata;
- una promozione infrannuale è una copia esatta campo per campo;
- l'intera suite `pytest -q tests` resta verde.

## Esito del collaudo

- Matrice PDF e percorso completo: **13 test superati** nel modulo dedicato.
- Suite contabili mirate: **63 superati, 1 saltato**.
- Suite completa del repository: **195 superati, 3 saltati**.
- PDF reale `Bilancio_CEE_30giu2026 PDF.pdf`: import deterministico senza storico,
  rettifica verificata, previsione semanticamente valida e promozione esatta.
- Build di produzione frontend: **compilazione e controllo TypeScript superati**.
- Verifica visiva: controllati il PDF annuale standard e il PDF con segno meno
  finale; layout e valori risultano leggibili e coerenti.

I test saltati dipendono dalla disponibilita del corpus locale prevista dai test e
non rappresentano fallimenti. Gli avvisi correnti sono deprecazioni gia presenti e
non errori funzionali.

## Esecuzione periodica

Da `C:\DEV\xbrlbudget-main\xbrlbudget`:

```powershell
$env:PYTHONPATH=(Get-Location).Path
pytest -q tests
```

Ogni nuovo formato problematico deve diventare una fixture o un caso parametrico
prima della correzione. La correzione e considerata conclusa soltanto quando il
nuovo caso esegue l'intero percorso, non quando supera la sola importazione.

---

# Round 2 - Suite "generi diversi" (21 luglio 2026)

Aggiunta di 5 famiglie di test DELIBERATAMENTE ORTOGONALI alla matrice PDF del
Round 1 (che copriva "PDF sintetici -> percorso completo"). Obiettivo: far
emergere dai test - non dai clienti - i difetti che vivono negli angoli che la
matrice non tocca: le proprieta contabili dei motori, la superficie HTTP reale
con autenticazione, le ripetizioni del ciclo, le rotte XBRL/CSV, e la scala
numerica. Tutti girano su SQLite in-memory, senza `ANTHROPIC_API_KEY`.

Ogni test e stato scritto e poi verificato da una revisione indipendente
(conformita alle specifiche + qualita), con particolare severita sul principio
"un test che fallisce e un difetto reale: si corregge il motore o si asserisce
il contratto onesto, MAI si indebolisce l'assert".

## Le 5 famiglie

| File | Test | Cosa verifica (non negoziabile) | Esito |
|---|---:|---|---|
| `tests/test_engine_accounting_invariants.py` | 5 | Identita contabili valide per QUALUNQUE input: riserve_t = riserve_{t-1} + utile_{t-1}; TFR_t = TFR_{t-1} + accant.; crescita 0% = CE operativo invariato; 2 generazioni identiche; cassa mai < 0; imposte = 24% del PBT | 5/5 |
| `tests/test_http_full_cycle.py` | 4 | Ciclo intero via ASGI reale (JSON/Decimal, auth, status): import->rettifica->scenario->ipotesi->analysis; cross-user 404; senza token 401; 21a rettifica 400; DELETE 204 + zero orfani | 4/4 |
| `tests/test_lifecycle_repeat.py` | 4 | Ripetizioni: re-import = 1 solo esercizio; override sopravvive al salvataggio idratato e muore solo col clear; reset = valori originali al centesimo; catena promote->budget quadra; ri-promozione = 1 solo esercizio pieno | 4/4 |
| `tests/test_xbrl_csv_full_cycle.py` | 2 | Rotte XBRL e CSV a ciclo completo (mai coperte prima): contratto onesto sulle fixture reali + happy-path su fixture sintetiche bilanciate che passano davvero dai parser | 2/2 |
| `tests/test_numeric_stress_cycle.py` | 7 | Budget 5 anni sotto stress: micro-importi coi centesimi, miliardi, +900%, -5% (quadra), -50% (rifiuto onesto), holding a ricavi zero | 7/7 |

Suite completa del repository dopo il Round 2: **217 passati, 3 saltati** (i 3
saltati dipendono da corpus PDF locale opzionale).

## Cosa hanno trovato (esiti confermati dalle revisioni)

Nessun difetto di CALCOLO nascosto e emerso: niente scarto di un centesimo al 4o/5o
anno, niente overflow oltre `Numeric(15,2)` alla scala dei miliardi, nessuna
divisione per zero sulla holding a ricavi zero. I punti sotto sono CONTRATTI del
sistema, resi ora espliciti e verificati - non regressioni.

1. **Fabbisogno finanziario scoperto sotto contrazione forte (design-corretto).**
   Con i costi tenuti piatti (default 0% di crescita costi) e i ricavi a -50%/anno,
   il conto economico va in perdita reale (es. -230.000 sul primo anno) e la cassa
   diventa negativa: il motore RIFIUTA di generare con "Unfunded financing
   requirement" invece di fabbricare debito a breve per mascherare la scelta
   mancante. Diagnostica dal vivo: la contrazione LIBERA cassa dal capitale
   circolante (crediti/rimanenze scendono) - il fabbisogno viene dalla perdita
   operativa, non da un errore di segno sul working capital. Aggiunto un caso
   `-5%` che invece genera e quadra a 5 anni, cosi la quadratura-sotto-declino
   resta coperta da un caso che riesce.

2. **Multi-tenancy applicata davvero.** Il test di isolamento passa per il motivo
   giusto (non per un bypass dev-mode): senza token si ottiene 401, non 200 - prova
   che l'autenticazione e effettivamente attiva - e il 404 di un secondo utente e un
   vero diniego di ownership (`validate_company_owned_by_user`), non l'artefatto di
   un DB vuoto (le chiamate riuscite del primo utente provano che il DB e vivo).

3. **Override CE: la sopravvivenza al salvataggio e responsabilita del frontend.**
   `bulk_upsert_assumptions` cancella e ricrea le righe dal payload; gli override
   sopravvivono al "Salva e Calcola" perche il frontend re-invia sempre le righe
   idratate (documentato in CLAUDE.md e nel commento esplicito in
   `frontend/app/budget/page.tsx`). Solo il clear esplicito li azzera. Il test
   modella il flusso reale, non una preservazione lato-backend inesistente.

## Gap di PRODOTTO scoperti e RISOLTI (21 luglio 2026)

Emersi dalla copertura delle rotte alternative e poi corretti in modo generale:

- **XBRL e CSV — dettaglio assente ⇒ non forecastable (RISOLTO).** Il bilancio
  abbreviato XBRL e il formato TEBE CSV pubblicano solo gli AGGREGATI di legge
  (`sp04/sp05/sp06/sp07/sp12/sp14/sp16/sp17`, `ce08/ce09`) senza le sotto-voci
  tipizzate. Il gate del motore previsionale (`_validate_forecast_source`) esige che
  ogni famiglia quadri col proprio dettaglio, quindi un'azienda XBRL con immob.
  finanziarie o fondi rischi — o un'azienda CSV con magazzino/crediti/debiti/
  ammortamenti — importava e quadrava ma **non era proiettabile**. **Fix:** nuovo
  helper condiviso `importers/iv_cee_hierarchy.reconcile_source_detail`, chiamato dai
  due importer, che al momento dell'import contabilizza il residuo
  `aggregato − Σdettaglio` nel bucket "altri" di ogni famiglia (aggregato e pareggio
  INTATTI, `ce09` ripartito immateriali/materiali in proporzione alla base cespiti
  `sp02`/`sp03`). È la stessa convenzione onesta "composizione ignota → bucket altri"
  già usata dal frontend (`reconcileSubfields`) e dalla riconciliazione di output del
  motore. Ora il fixture reale `ISTANZA02353550391.xbrl` e un TEBE con working
  capital reale completano il ciclo budget. Test:
  `tests/test_source_detail_reconcile.py` (8 unit) +
  `tests/test_xbrl_csv_full_cycle.py` (2 integrazione). Suite completa: **225
  passati, 3 saltati**.
- **Fixture d'esempio storiche (comportamento onesto, invariato):**
  `legacy/sample_data/sample_data.csv` (e il gemello `.xbrl`) sono sbilanciate alla
  fonte di 30.000 (Attivo 615.000 vs Passivo 645.000) e vengono correttamente
  rifiutate dall'import. Non e un bug: e il comportamento onesto, gia coperto anche
  da `test_csv_schema_detection`.

## Esecuzione

Identica al Round 1: da `C:\DEV\xbrlbudget-main\xbrlbudget`,
`$env:PYTHONPATH=(Get-Location).Path; pytest -q tests`. Le nuove famiglie non
richiedono ne PDF locali ne chiave API. Suite completa dopo Round 2 + fix
forecastability: **225 passati, 3 saltati**.

---

## Appendice — dettaglio dei nuovi test (cosa verifica ciascuno)

### `tests/e2e_kit.py` (kit condiviso, nessun test)
Fornisce l'infrastruttura riusata da 3 famiglie: `memory_sessions()` (SQLite
in-memory con `StaticPool`, connessione condivisa fra sessioni), `seed_base_year()`
(semina via ORM un anno base **verificato e forecastable** con dettagli IV-CEE
coerenti — `scale=` per lo stress, `holding=True` per la holding), e
`read_forecast_maps()` che rilegge i `ForecastYear` persistiti e ricalcola
`total_assets`/`total_liabilities` dalle colonne ORM (controllo indipendente, non
un numero in cache).

### `tests/test_engine_accounting_invariants.py` (5) — invarianti del motore
Proprietà che devono valere per QUALUNQUE input:
1. **Roll-forward PN/TFR** — `riserve_t = riserve_{t-1} + utile_{t-1}`; `TFR_t = TFR_{t-1} + ce08a`.
2. **Punto fisso** — crescita 0% e zero investimenti ⇒ CE operativo identico all'anno base.
3. **Determinismo** — due generazioni con le stesse ipotesi producono righe byte-identiche.
4. **Cassa-plug non negativa** — la cassa non va mai sotto zero.
5. **Imposte** — con aliquota esplicita e PBT>0, `ce20 = 24% del PBT`.
> Scoperta: il caso #4 ha confermato che il motore, davanti a cassa negativa,
> **solleva "Unfunded financing requirement"** invece di fabbricare debito a breve
> (scelta di design deliberata). Il test asserisce questo contratto onesto.

### `tests/test_http_full_cycle.py` (4) — superficie HTTP reale + multi-tenancy
Esercita l'app ASGI vera (TestClient) con JWT HS256, non le funzioni dei router:
1. **Ciclo intero via JSON** — import PDF → rettifica → scenario → ipotesi → analysis, tutto 200, quadratura sui float serializzati.
2. **Isolamento cross-user** — un secondo utente (JWT diverso) ottiene **404** su azienda/scenari/adjustable; **senza token 401** (prova che l'auth è attiva, non un bypass dev-mode).
3. **Cap rettifiche** — la 21ª rettifica ⇒ **400**.
4. **Cascade delete** — DELETE azienda ⇒ **204** e zero righe orfane in Company/FinancialYear/BalanceSheet/IncomeStatement/BudgetScenario.
> Scoperta: il doppio `sys.path` del backend (`app.*` vs `backend.app.*`) crea DUE
> oggetti `settings`/`get_db` distinti; la fixture deve patchare i moduli `app.*`
> che le route leggono davvero, altrimenti l'auth non è applicata e il test 404
> passerebbe per il motivo sbagliato. Verificato in vivo dalla review.

### `tests/test_lifecycle_repeat.py` (4) — cicli di vita ripetuti
Quello che l'utente reale ripete ogni giorno:
1. **Re-import stesso anno** ⇒ 1 solo `FinancialYear` + 1 `BalanceSheet` (sostituisce, non duplica).
2. **Override CE** — sopravvive al "Salva e Calcola" idratato, muore SOLO col `clear_overrides=True`.
3. **Rettifica → reset** — riporta ai valori originali al centesimo; lo snapshot originale è immutabile fra le PUT.
4. **Catena promote → budget** — infrannuale→promozione→budget sull'anno promosso quadra; ri-promozione ⇒ 1 solo esercizio pieno.
> Scoperta/riconciliazione confermata onesta dalla review: la sopravvivenza degli
> override è **responsabilità del frontend** (re-invia le righe idratate;
> `bulk_upsert_assumptions` cancella e ricrea) — documentato in `budget/page.tsx`.

### `tests/test_numeric_stress_cycle.py` (7) — stress numerico budget 5 anni
Scala e segno estremi lungo tutto il ciclo (il massimo orizzonte):
- micro-importi coi centesimi (scala 0.0037), scala miliardi, +900%, **−5% (genera e quadra)**, **−50% (rifiuto onesto)**, e una **holding a ricavi zero** (nessuna divisione per zero nella derivazione DSO/DPO).
- Ogni anno generato: quadratura ESATTA sui Decimal, `sp09 >= 0`, nessun campo fuori da `Numeric(15,2)`.
> Scoperta: i due casi −50% asseriscono il **rifiuto** del motore (fabbisogno
> scoperto), diagnosticato dal vivo come **design-corretto** (costi piatti +
> ricavi dimezzati = perdita reale, non errore di segno sul working capital); il
> caso −5% è stato aggiunto per coprire la quadratura-sotto-contrazione con una
> generazione che riesce.

### `tests/test_xbrl_csv_full_cycle.py` (2) — rotte XBRL e CSV a ciclo completo
Le rotte mai coperte end-to-end prima:
1. **XBRL** — il fixture reale depositato `ISTANZA02353550391.xbrl` importa, quadra e ora **completa il ciclo budget** (dopo il fix, vedi sotto); più un XBRL sintetico minimale.
2. **CSV** — il `sample_data.csv` sbilanciato di 30.000 alla fonte è **correttamente rifiutato**; un TEBE sintetico con working capital + ammortamenti reali ora **importa e proietta** (il reconcile popola i bucket "altri" e splitta `ce09`).

### `tests/test_source_detail_reconcile.py` (8) — unit del fix forecastability
Il nuovo helper `reconcile_source_detail`:
- plugga il residuo `aggregato − Σdettaglio` nel bucket "altri" **senza toccare l'aggregato**;
- solo il residuo non spiegato si sposta se c'è dettaglio parziale;
- è **idempotente** e **no-op** su fonti già coerenti;
- splitta `ce09` immateriali/materiali in proporzione a `sp02`/`sp03` (nessun centesimo perso);
- una fonte solo-aggregati diventa `hierarchy_consistent`;
- **un residuo NEGATIVO (over-extraction) NON viene inghiottito** — resta incoerente così il gate lo cattura (rilievo Important della review, corretto col guard solo-positivo).
