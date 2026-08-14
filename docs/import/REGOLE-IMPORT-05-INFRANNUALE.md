# 05 — Bilancio infrannuale

> Torna all'[indice](REGOLE-IMPORT-00-INDICE.md).
> Motori: `calculations/intra_year_engine.py`, `calculations/projection_common.py`,
> `database/queries.py`, `backend/app/api/v1/budget_scenarios.py`.

L'infrannuale prende un bilancio di periodo (per esempio i primi 5 mesi) e ne proietta l'anno
intero. Tutto ciò che segue discende da una domanda: **quali numeri si possono annualizzare, e
quali no.**

## 1. La convenzione del periodo

> `NULL` **oppure** `12` = anno pieno. `1`–`11` = periodo parziale genuino.

Il `12` esiste solo per compatibilità storica: alcuni importer lo scrivevano. Ogni query "anno
pieno" accetta entrambi. **In scrittura, 12 mesi non è mai un parziale su disco**: XBRL, PDF e
creazione manuale normalizzano tutti a `NULL`.

### Il periodo si deduce dal documento, non dall'utente
Nell'XBRL i mesi si calcolano dai *contesti*: dalla data di inizio e fine di ogni durata,
accettata solo se compresa fra 1 e 12. Un contesto istantaneo non ha durata.

**Il parametro manuale non può declassare un periodo annuale.** Un `period_months` passato
dall'utente vale **solo** come fallback, **solo** per il periodo più recente, e **solo** se il
documento non dichiara una durata propria. Un bilancio che dichiara 12 mesi non diventa un
nove-mesi perché l'utente ha scritto 9.

### Più periodi nello stesso anno coesistono
Un import a 6 mesi non deve mai sovrascrivere un 9 mesi dello stesso anno. La cancellazione
avviene **per corrispondenza esatta**: un import parziale tocca solo i parziali, un annuale solo
gli annuali.

### Nessun fallback nella selezione
La ricerca di un periodo parziale restituisce **esattamente** quel record, e rifiuta valori fuori
da 1–11. **Gli anni pieni non sono un fallback.** Il motivo è dichiarato: scegliere un parziale
arbitrario renderebbe il fattore di annualizzazione scollegato dai dati che si stanno
proiettando.

Se manca: *"Dati anno {Y} ({M} mesi) non trovati o incompleti… Importare esattamente quel
periodo"*.

### Il fattore appartiene al record, non allo scenario
`factor = 12 / period_months`, e i mesi si leggono **dal record contabile selezionato, non dai
metadati mutabili dello scenario**. Un record annuale dà fattore 1: un infrannuale a 12 mesi è
legittimo e produce l'identità.

## 2. I due regimi

L'anno di riferimento (per esempio il 2024, quando si proietta il 2025 da 5 mesi) è
**opzionale**. Se manca — o è incompleto, cioè privo di SP o CE — il motore passa a **pura
annualizzazione**.

Nell'interfaccia questo è il pannello giallo "Serve il bilancio storico {anno}", con due strade:
caricare il PDF annuale, oppure **"Prosegui senza l'anno precedente (solo annualizzazione)"**.

### Regime 1 — con riferimento: crescita sul riferimento

| Voce | Regola |
|---|---|
| Ricavi, altri ricavi, godimento beni, personale, oneri diversi | `riferimento × (1 + crescita%)` |
| **Materie e servizi** | split variabile/fisso: `rif × (1−f) × (1+g_var) + rif × f × (1+g_fix)` |

### Regime 2 — senza riferimento: tutto × 12/mesi
Le percentuali di crescita non si applicano, perché non hanno una base su cui applicarsi.
Restano attivi gli override finanziari, l'ammortamento dei nuovi investimenti, i finanziamenti e
il ricalcolo delle imposte.

## 3. Cosa non cresce mai

Alcune voci **non seguono mai una percentuale di crescita**, in nessun regime: si annualizzano e
basta. Sono `ce02`, `ce03`, `ce03a`, `ce10`, `ce11`, `ce11b`, `ce13`, `ce16`, `ce18`, `ce19`.

`ce03a` (incrementi di immobilizzazioni per lavori interni) è incluso **espressamente**: senza,
il risultato del CE non riconcilia con lo SP e si produce un falso sbilancio.

## 4. Le regole per voce

### Ammortamenti: mai per crescita
`ce09` e tutte le sue quote si annualizzano sempre — l'ammortamento è un accrual lineare, non
una grandezza che "cresce col fatturato".

### Ammortamento dei nuovi investimenti: sui mesi residui
```
nuovo ammortamento = investimento × aliquota × (12 − mesi) / 12
```
Separatamente per immateriali e materiali. Un investimento fatto in un periodo di 12 mesi ha
residuo zero e non genera ammortamento aggiuntivo.

### Investimenti aggregati: vietati
Un investimento senza lo split immateriale/materiale **solleva errore**. Nessuno split 50/50
inventato. La regola gemella esiste nel budget.

### TFR: quota statutaria
```
quota annua = base retributiva / 13,5
```
dove la base sono i salari e stipendi se disponibili, altrimenti **il 70% del costo del
personale totale** — fallback per quando l'import non ha lo spacchettamento della voce B.9.

Il **fondo** cresce dell'accantonamento dei **mesi residui**, non dell'intera quota annua.

### Coerenza delle sotto-voci del personale
Le quattro sotto-voci non superano mai il totale: la quota TFR è cappata al residuo disponibile,
e l'ultima voce assorbe ciò che avanza.

### Imposte
```
ce20 = max(0, risultato ante imposte proiettato × aliquota)
```
Mai negative: nessun credito d'imposta inventato.

> **Divergenza da conoscere**: l'**aliquota effettiva** derivata dall'anno base (con cap al 60% e
> fallback) esiste **solo nel budget**, non nell'infrannuale, che usa direttamente l'aliquota
> dell'assunzione. Nell'interfaccia infrannuale l'override del risultato è tradotto dal frontend
> in un'aliquota effettiva.

### Rimanenze
Con riferimento: si applica l'**indice di rotazione del magazzino** del riferimento al costo
materie proiettato. Senza riferimento: la giacenza parziale è portata a fine anno **invariata**.
Le *variazioni* a CE si annualizzano sempre. Vale comunque la guardia sui rapporti degeneri
(§5), che qui può far ricadere le rimanenze sul comportamento "senza riferimento".

## 5. Il roll-forward dello Stato Patrimoniale

> **Le voci patrimoniali sono stock puntuali: non si annualizzano.** Nel confronto, il "valore
> annualizzato" di una voce di SP è il valore parziale stesso.

| Voce | Regola |
|---|---|
| **Immobilizzazioni immateriali / materiali** | parziale − **ammortamento residuo della propria classe**, clampato a zero, + nuovi investimenti della classe |
| **Immobilizzazioni finanziarie** | invariate: **mai ammortizzate** |
| **Crediti a breve** | con riferimento: proporzionali ai ricavi proiettati (salvo rapporto degenere, sotto); poi meno la **svalutazione residua** |
| **Crediti oltre, attività finanziarie, ratei, fondi rischi** | invariati dal parziale |
| **Capitale e riserve** | **presi dal parziale così come sono** |
| **Risultato** | = risultato del CE proiettato, per costruzione |
| **Fondo TFR** | parziale + accantonamento dei mesi residui |
| **Debiti a breve** | con riferimento: proporzionali ai costi operativi proiettati (salvo rapporto degenere, sotto); senza: invariati |
| **Debiti a lungo** | **solo movimenti espliciti**: rimborsi e nuovi finanziamenti |
| **Cassa** | plug di chiusura, ma **solo verso l'alto** (vedi sotto) |

Ogni classe usa **il proprio** ammortamento: gli immateriali con la quota immateriali, i
materiali con la quota materiali. Mai incrociati.

### Rapporti di rotazione degeneri: si riporta, non si moltiplica

Le tre voci "proporzionali" della tabella — rimanenze, crediti a breve, debiti a breve — si
scalano su un rapporto letto dall'anno di riferimento (`giacenza / base economica`). Quel
rapporto è valido solo se la base **può spiegare** la giacenza.

> **Un rapporto oltre un anno di giacenza è DEGENERE: non descrive l'azienda, descrive il
> proprio denominatore.** `_turnover_ratio` restituisce `None` e il chiamante riporta la
> **giacenza infrannuale osservata**, esattamente come nel regime senza riferimento.

`_safe_divide` protegge dal denominatore **zero**, non da quello **trascurabile**, e qui la
differenza è tutta. Il caso reale (AIC SRL, riferimento 2025):

| | |
|---|---|
| `ce01_ricavi_vendite` di riferimento | **100,92 €** (il giro d'affari sta su `ce04_altri_ricavi`, 1.252.849,27) |
| `sp06_crediti_breve` di riferimento | 1.035.249,26 € |
| rapporto | **10.258×**, cioè 3,7 milioni di giorni di credito |
| crediti proiettati | **166.684.157,69 €** su un attivo reale di 1,5 M |

Lo SP persistito non quadrava (attivo 167.054.466,63 contro passivo 1.572.757,71) e il
promote a budget lo rifiutava — correttamente. Il ripiego emette un diagnostico
`degenerate_turnover_ratio` di severità *warning*: la voce non è stata proiettata e va
verificata in **Rettifiche**. È la stessa regola dell'import — *misurare, mai fabbricare*.

Le aziende sane non si muovono: sotto la soglia il calcolo resta quello di prima.

> **La formula è duplicata**: `calculateProjectedBS` (frontend, `app/pratica/page.tsx`) e
> `_project_balance_sheet` (backend). Devono restare d'accordo. Quando divergevano si otteneva
> il caso peggiore — il plug di cassa del frontend scaricava i 165 M eccedenti sui debiti a
> breve e mostrava a schermo un bilancio che "quadra", mentre il record persistito restava
> sbilanciato e il promote lo rifiutava, senza che nulla spiegasse la differenza. La guardia
> è implementata su entrambi i lati (`lib/pratica-turnover.ts` per il frontend).

### Nessuna destinazione implicita dell'utile
Capitale e riserve si prendono dal parziale invariati. Il commento nel codice è netto: *il
risultato dell'anno precedente non viene mai spostato a riserva implicitamente, perché richiede
una delibera dei soci*. Questo preserva i movimenti di patrimonio già avvenuti nell'anno.

### CE = risultato, senza plug
Il risultato dello SP **è** il risultato del CE, calcolato con la stessa formula canonica usata
da import e ORM. Non c'è riconciliazione perché non può essercene bisogno.

### Il fabbisogno scoperto è un diagnostico, non un debito
Se il plug di cassa risulta **negativo**, la cassa va a zero e si emette un diagnostico di
severità *error*: *"Add an explicit financing assumption; no debt was created automatically"*.

> **Nessun aumento automatico del debito a breve.** È una divergenza esplicita e voluta dal
> motore di budget, che storicamente aumentava il debito a breve per assorbire la cassa
> negativa. Qui il fabbisogno si **mostra**; non si finge di averlo coperto.

### Le sotto-voci si distribuiscono, mai si inventano
Le quote si distribuiscono **proporzionalmente** alla fonte (il riferimento nel regime 1, il
parziale nel regime 2). Se la fonte non ha alcuna ripartizione, tutte le quote sono **zero** più
un diagnostico: *"Short-term debt breakdown is unavailable; no categories were invented"* —
esplicitamente **non** uno split 40/60 fra finanziario e operativo.

### La rata di rimborso
```
rata = debito finanziario a lungo dell'anno base / anni di piano
```
Il **debito finanziario** sono banche + obbligazioni + l'eventuale gap positivo di un abbreviato
(allocato alle banche). Esclude "altri finanziatori" — che ha un piano proprio — e i debiti a
lungo non finanziari (fornitori, tributari, previdenza), per non doppiare né sovra-rimborsare.

È **kernel condiviso** col budget: l'infrannuale la applica all'aggregato, il budget la ripartisce
sulle sotto-voci. Orchestrazione diversa, formula identica per costruzione.

## 6. I gate: cosa blocca un infrannuale

### Gate semantico sulla fonte
Applicato **prima di ogni calcolo**, al parziale sempre e al riferimento se presente. Solleva
*"{label} {anno}/{mesi}M is not forecastable: …"*.

| # | Causa | Soglia |
|---|---|---|
| G1 | bilancio vuoto | — |
| G2 | attivo ≠ passivo | > €0,01 |
| G3 | risultato CE ≠ `sp13` | qualsiasi |
| G4 | tampone residuo persistito nella fonte | > €0,01 |
| G5 | aggregato ≠ somma dettagli su una voce **usata dal motore** | qualsiasi |
| G6 | diagnostiche dello snapshot illeggibili | — |

**G5 opera su un insieme chiuso**: immobilizzazioni finanziarie, crediti a breve, riserve, debiti
a breve, debiti a lungo, ammortamenti. Solo su queste il disallineamento blocca, perché sono le
voci che il motore **scala o riporta**: procedere fabbricherebbe una composizione. L'elenco dei
dettagli di ciascun aggregato non è riscritto qui: il gate legge `detail_fields()` di
`iv_cee_hierarchy`, la stessa mappa che usa `check_quadratura`.

> **Una ripartizione ASSENTE non è un disallineamento** (dal 2026-08-07). Un bilancio abbreviato
> dichiara solo l'aggregato, e i distributori lo sanno già fare: restituiscono zeri e riportano
> l'aggregato invariato, senza inventare nulla. A bloccare è solo una ripartizione **dichiarata**
> che non somma al proprio aggregato — cioè una contraddizione: una delle due cifre è sbagliata.
> È la stessa regola di `importers/reliability.py` (pagina 04 §9-bis), dove anche `UNRELIABLE`
> vuole una contraddizione e non l'assenza di un controllo.

**`sp16`/`sp17` sono l'eccezione e bloccano comunque**, dichiarati o no: lì
`projection_common.base_bank_debt` assegna alle banche l'intero scarto aggregato/dettaglio, quindi
una ripartizione assente diventa davvero debito bancario fantasma e gonfia la PFN. È una falla
nota, non una scelta.

**Come si manifestava il rifiuto, prima di quella correzione — e perché era invisibile.** Una
verifica di route C con `sp04`/`sp05` solo aggregati veniva respinta, ma
`bulk_upsert_assumptions` **cattura** l'errore e risponde **HTTP 200** con
`forecast_generated: false` e la ragione in `message`: nessun `ForecastYear` scritto,
`analysis.forecast_years` vuoto, e la colonna Proiezione della tab Indicatori vuota **sotto un
toast di successo**.

> **Chi chiama l'endpoint bulk delle assumptions deve leggere `forecast_generated`, non lo stato
> HTTP.** Oggi lo fanno `/budget` ed entrambi i punti di chiamata del wizard della pratica.

Test: `tests/test_intra_year_semantics.py` (`test_forecast_gate_*`).

**G4 è anti-elusione, ed è sottile.** Le diagnostiche di import non sono colonne del database:
vengono ripescate dallo snapshot originale e reiniettate prima della validazione, *"so a
historical cash/debt plug cannot pass the forecast gate merely because it was persisted as an
ordinary amount"*. Cioè: un tampone storico non diventa lecito solo perché è stato salvato come
un importo qualsiasi.

Nota architetturale: il motore **non legge il flag `forecastable`** — riesegue i controlli sui
valori correnti. È necessario perché le Rettifiche modificano il record dopo l'import. Il flag è
la superficie API/interfaccia, non la fonte di verità.

### Gate di ammissibilità
Scenario non infrannuale; `period_months` assente o fuori da 1–12; periodo parziale esatto
inesistente; anno pieno inesistente quando i mesi sono 12; nessuna assunzione. Un cambio di anno
base, tipo scenario o mesi **riscatena la rivalidazione**.

## 7. Infrannuale contro budget: le divergenze

| Aspetto | Infrannuale | Budget |
|---|---|---|
| Selezione anno fonte | **esatta**, nessun fallback | preferisce l'anno pieno, con fallback |
| Gate semantico | — | **lo stesso**, riusato dall'infrannuale |
| Aliquota imposte | quella dell'assunzione | **effettiva**, derivata dall'anno base, cap 60% |
| Cassa negativa | cassa a zero + diagnostico, **nessun debito creato** | aumenta il debito a breve |
| Rimborso debito | rata sull'aggregato | stessa rata, ripartita sulle sotto-voci |
| Nuovi finanziamenti | importo singolo | scadenzario multi-prestito |
| Guardia ricavi negativi | **assente** | presente |
| Output | 1 anno, promuovibile | N anni |

**Kernel realmente condiviso**: rata di rimborso, rata altri finanziatori, quota TFR, scadenzario
dei nuovi finanziamenti, formula del risultato, validatore di quadratura. Il principio dichiarato
è buono e vale la pena citarlo:

> Gli *orchestratori* possono divergere — come si arriva all'anno da proiettare è una scelta.
> Le *regole per riga* no: sono fatti sul mondo. **Una rata fissa non cambia se guardi l'azienda
> su 3 mesi o su 5 anni.**

Attenzione a una differenza operativa: l'infrannuale usa **una sola** assunzione (la prima),
mentre il budget le ordina tutte per anno.

## 8. Il confronto

Per ogni voce di CE: valore parziale, valore di riferimento, valore dell'anno prima, percentuale
sul riferimento, e valore annualizzato. Per ogni voce di SP: gli stessi campi, ma **il valore
annualizzato è il valore parziale** — punto nel tempo, nessuna annualizzazione.

Il payload espone `has_reference`, che l'interfaccia usa per nascondere le colonne di confronto
quando si è in pura annualizzazione.
