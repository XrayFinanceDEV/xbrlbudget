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

**La posizione tributaria al 31/12** (lotto 3A, Task 5, decisione 4 del proprietario) non è più «apertura + imposta
− acconti»: al 31/12 resta **solo il saldo dell'anno in corso**, `imposta(anno) − acconti(anno)`, positivo in
`sp16e` e negativo in `sp06e`. Gli acconti sono `tax_advances_paid` se **maggiore di zero**, altrimenti il 100% del
`ce20` dell'anno di riferimento; senza riferimento l'imposta su cui commisurarli non esiste, quindi **zero** —
tutta l'imposta dell'anno resta da versare al 31/12 (il lato prudente, mai un acconto inventato). La regola è
`projection_common.acconti_dovuti`, la stessa del motore budget, e la posizione la costruisce
`projection_common.posizione_tributaria_fine_anno`. Quanto era aperto al mese del parziale **esce di cassa entro
fine anno**:

```
uscita = (debito di apertura − credito di apertura) + imposta dei mesi residui − posizione netta di fine anno
```

Misurato sui test (`tests/test_intra_year_imposte.py`): apertura 1.150.949,04, imposta dell'anno 120.000, acconti
99.247,26 → `sp16e` **20.752,74** e un'uscita di cassa di **1.250.196,30**. Prima: `sp16e` 1.171.701,78 con cassa
immutata, e il budget nato dal promote ereditava quel debito. Nel motore la cassa resta il plug, quindi è il kernel
a dichiarare `cash_out` e il test end-to-end a verificarlo. `sp17e` (rate oltre l'anno) non si tocca, e la via
manuale (`sp06e_growth_pct` o `sp16e_growth_pct` valorizzati) continua a saltare la posizione automatica.

**La differenza fra `cash_out` e le righe è il conguaglio, e si posa sul lato che si è mosso.**
`sp16e` e `sp06e` non nascono dal kernel: nascono dalla **rotazione** del circolante (Task 1/2), che
porta via la percentuale di crescita del riferimento, e posano la massa non riconosciuta su
`sp16g`/`sp06g`. Quando la sostituzione fiscale li riscrive, dal `g` se ne va (o ci torna) la
**quota di rotazione `x`**, non il debito di apertura `P_d` che è quello che `cash_out` misura. La
riga da sola muove dunque cassa per `(chiusura − x)`, non per `cash_out`, e lo scarto era assorbito
dal plug senza che nessun flusso lo nominasse:

```
correzione = −cash_out − [(chiusura_debito − x_debito) − (chiusura_credito − x_credito)]
```

La contropartita la sceglie il **verso**, e una sola (ruling del coordinatore, 2026-09-12):
conguaglio **negativo** → `sp16g_altri_debiti_breve` **scende** (stiamo pagando un debito, non
incrementandolo); conguaglio **positivo** → `sp06g_crediti_altri_breve` scende, cioè si scarica
l'**attivo** (stiamo incassando). **Mai** un aumento di passività a fronte di un incasso: la prima
stesura di questa regola, che applicava il solo lato debito in entrambi i casi, su uno scenario reale
del database fabbricava **+144.188,46 di `sp16g`**, peggiorando la PFN senza alcun evento.
Nessun campo scende sotto zero: si applica la parte che ci sta e il residuo si dichiara con
`tax_settlement_reclass_below_zero` (campo nominato e importo), lasciando la cassa dov'è. Un secondo
bersaglio sarebbe il vecchio plug. Nel **testo** del messaggio non c'è alcun importo, solo il nome del
campo: la cifra che conta vive nel payload `amount`. Dire "trova solo X di capienza" avrebbe infatti
significato, sul lato debito, mostrare una capienza **negativa** (`applicato` è negativo per
costruzione), e una capienza esiste o non esiste (rilievo di revisione, 2026-09-12).

**Il residuo dichiarato è misurato *prima* degli `sp_overrides`, e può quindi sottostimare.** Se un
override insiste sullo stesso campo neutro (`sp16g` o `sp06g`), la parte che il conguaglio ha applicato
viene sovrascritta dall'override — un override vince sulla riga, per costruzione — la cassa non si muove
per nulla, e il warning riporta solo ciò che il motore non era riuscito a collocare: resta corto
dell'importo cancellato. Vale per qualunque anno e qualunque campo neutro, non è la particolarità di
uno scenario; chi legge quel warning deve sapere che può sottostimare, e perché.

I due rami non sono simmetrici, e non per disattenzione: sul **ramo col riferimento** il Task 2 ha
già portato `sp06e` al valore governato **prima** dei riassorbimenti, quindi il credito non lascia
alcun residuo implicito e la formula è **solo debito** (`x_credito = chiusura_credito` per
costruzione); sul **ramo annualizzato** (nessun anno pieno importato) la riga combinata
`sp06e, sp16e = ...` gira **dopo** i riassorbimenti e perde massa su entrambi i lati, quindi lì la
forma è **bidirezionale**. Non si è riordinato nulla: il change aggiunge solo il flusso dichiarato.

Misurato sugli 8 scenari infrannuali del database di riferimento (cinque producono una proiezione;
gli altri tre falliscono prima per dati mancanti, invariati prima e dopo):

| Scenario | Prima | Dopo |
|---|---|---|
| 4 | cassa 15.271,65, `sp16g` 26.093,20, foglio quadrato | cassa 0,00 (clamp), `sp16g` 8.964,79, sbilancio 1.856,76 dichiarato da `unfunded_financing_requirement` — un fabbisogno che prima non esisteva |
| 5 | `sp16g` 20.617,43, cassa invariata | persistito **identico**, ma con residuo dichiarato −30.712,76: la parte applicata (3.614,28) viene cancellata da `sp_overrides.sp16g` dell'utente — l'istanza della regola qui sopra |
| 8 | `sp16g` 0,00, cassa invariata | cassa **ferma** com'era, `sp16g` 0,00 (nessuna passività negativa), residuo dichiarato −14.306,93 |
| 12 (ramo annualizzato) | `sp16g` 134.484,00 | `sp16g` 123.086,00, cassa −11.398,00, nessun residuo |
| 18 (conguaglio positivo) | `sp06g` 33.131,63, cassa 1.468.473,63 | `sp06g` 0,00, cassa 1.501.605,26, `sp16g` **invariato**, residuo dichiarato +111.056,83 |

Su `tests/test_intra_year_crediti_commerciali.py` la stessa regola muove di 5.000,00 l'aggregato
`sp06`: il fixture porta 5.000,00 di credito tributario d'apertura, e da qui quel credito si incassa.
La massa non è persa, passa dall'attivo alla liquidità — le due asserzioni leggevano 200.000,00
perché prima di questo change non c'era alcun meccanismo che lo muovesse.

**Se la cassa del parziale non copre quell'uscita** (debito tributario di apertura maggiore della cassa
disponibile), il plug generale dell'infrannuale — §5 sotto, "Il fabbisogno scoperto è un diagnostico, non un
debito" — clampa `sp09` a zero e dichiara `unfunded_financing_requirement`: la proiezione esce comunque, ma **non
quadrata**, e il cancello del promote (`check_quadratura(...).semantic_valid`) la rifiuta finché l'utente non
aggiunge un finanziamento esplicito o una rettifica — decisione del proprietario, lotto 3A, 2026-09-11: si tiene
la regola, mai un plug al posto della diagnostica.

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
| **Crediti a breve** | **aggregato**: con riferimento, proporzionale ai ricavi proiettati (salvo rapporto degenere, sotto), poi meno la **svalutazione residua**; **composizione** (verso clienti/controllate/collegate/controllanti/altri): sempre dal parziale, mai dal riferimento — crediti tributari e imposte anticipate esclusi, governati altrove |
| **Crediti oltre, attività finanziarie, ratei, fondi rischi** | invariati dal parziale |
| **Capitale e riserve** | **presi dal parziale così come sono** |
| **Risultato** | = risultato del CE proiettato, per costruzione |
| **Fondo TFR** | parziale + accantonamento dei mesi residui |
| **Debiti a breve** | **debito finanziario (banche/altri finanziatori/obbligazioni)**: invariato dal parziale, come i debiti a lungo sotto; **residuo operativo** (fornitori/tributari/previdenziali/altri): con riferimento proporzionale ai costi operativi proiettati (salvo rapporto degenere, sotto), senza riferimento invariato |
| **Debiti a lungo** | **solo movimenti espliciti**: rimborsi e nuovi finanziamenti; la quota del prestito nuovo che scade l'anno dopo sta nei debiti a breve, e il debito bancario pregresso si riduce solo con le proprie rate |
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

**Eccezione di settore per le rimanenze (lotto 3A, Task 10).** Per Immobiliare (settore 5) ed
Edilizia (6) una giacenza oltre l'anno **è il mestiere** — immobili in rimanenza, lavori in corso
su ordinazione — e lì la soglia non si applica alle rimanenze: il rapporto dedotto (anche oltre 1)
scala sulla base proiettata, `None` invece di 1 come `max_ratio` di `_turnover_ratio`. La tabella
sta in un punto solo per entrambi i motori, `projection_common.soglia_giorni_magazzino`. Le altre
voci, in ogni settore, e un **denominatore nullo** in qualunque settore restano degeneri com'erano.
Quando il diagnostic scatta, dichiara la soglia applicata nel campo `soglia_giorni`: `"365"`, o
`null` dove di soglia non ce n'è — e nei settori senza soglia su `sp05_rimanenze` non scatta mai.

> **La formula è duplicata**: `calculateProjectedBS` (frontend, `app/pratica/page.tsx`) e
> `_project_balance_sheet` (backend). Devono restare d'accordo. Quando divergevano si otteneva
> il caso peggiore — il plug di cassa del frontend scaricava i 165 M eccedenti sui debiti a
> breve e mostrava a schermo un bilancio che "quadra", mentre il record persistito restava
> sbilanciato e il promote lo rifiutava, senza che nulla spiegasse la differenza. Dal
> 2026-09-02 il lato client non calcola più la proiezione — la legge dal forecast che il motore
> ha persistito — quindi la guardia esiste in un posto solo e non c'è nulla da tenere d'accordo.

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

**Il controllo si misura una volta sola, dopo gli `sp_overrides` (lotto 3A, Task 11; §11.1 del
lotto 2).** `generate_projection` applica gli `sp_overrides` **dopo** aver proiettato lo SP, e solo
allora normalizza e ricalcola la cassa dagli aggregati; un override che sposta il passivo o
l'attivo — anche uno che non sposta la cassa direttamente — cambia quel residuo, quindi il
fabbisogno va misurato sulla cifra **finale**, mai su quella calcolata prima dell'override. Ogni
diagnostico `unfunded_financing_requirement` che il roll-forward avesse già registrato (il plug
descritto sopra, calcolato prima degli override) viene tolto e sostituito da quello, unico, letto
sulla cassa ricalcolata: prima di questa correzione la cassa restava congelata al valore
pre-override — con l'override applicato ma senza ricalcolo — e il foglio persistito poteva restare
sbilanciato dell'importo dell'override senza che alcun diagnostico lo dichiarasse con la cifra
giusta, oppure, quando nessun errore precedeva l'override, la cassa ricalcolata **senza clamp**
usciva negativa e restava **persistita così** (`sp09` negativa in DB). Caso del test
(`tests/test_intra_year_override_cassa.py`): parziale a 9 mesi con `sp05_rimanenze` forzato a
5.000.000 dà un avviso `unfunded_financing_requirement` di severità `error` per 4.998.445,00, la
`sp09` persistita è 0,00 (mai negativa), e `promote_projection_to_financial_year` rifiuta la
proiezione perché il foglio non quadra — esattamente come ogni altro fabbisogno scoperto di questo
motore.

### Le sotto-voci si distribuiscono, mai si inventano
Vale per il **residuo operativo** di `sp16`/`sp17` (fornitori/tributari/previdenziali/altri): le
quote si distribuiscono **proporzionalmente** alla fonte (il riferimento nel regime 1, il parziale
nel regime 2). Se la fonte non ha alcuna ripartizione operativa, tutte le quote sono **zero** più
un diagnostico: *"La ripartizione del debito operativo a breve (fornitori/tributario/previdenziale/
altri) non è disponibile: nessuna categoria è stata inventata."*

Il **debito finanziario** (banche/altri finanziatori/obbligazioni, `sp16a-c`/`sp17a-c`) **non**
segue questa regola: si porta avanti dal parziale come blocco a sé, in ENTRAMBI i regimi — mai
dalla proporzione del riferimento — perché un mutuo non è trainato dal fatturato o dai costi
operativi (`indagine-1-debito-bancario.md`, 2026-09-11). Quando il riferimento non ha alcun
dettaglio finanziario (nessuna delle tre categorie popolata) e il parziale sì, il motore lo
dichiara con `reference_financial_debt_undetailed` (severità *warning*: non è un errore, è il
motivo per cui la ripartizione viene dal parziale invece che dal riferimento).

I **crediti a breve e a lungo** (`sp06`/`sp07`) seguono una regola diversa da entrambe le
precedenti: l'aggregato resta trainato dal fatturato (rotazione/DSO, sopra), ma la
**composizione** delle sotto-voci (verso clienti/controllate/collegate/controllanti/altri) viene
**sempre** dal parziale — mai dal riferimento, in nessuno dei due regimi — perché un riferimento
senza dettaglio reale (il 98% dei bilanci annuali completi, come per il debito) riclassificava in
silenzio il credito verso clienti in "altri crediti" (`indagine-2`, 2026-09-12). Il credito
tributario (`sp06e`) e le imposte anticipate (`sp06f`/`sp07f`, quando impostate esplicitamente)
sono **esclusi** dalla ripartizione prima che avvenga — il loro valore viene dalla posizione
tributaria di fine anno o dalle differite, mai da una quota proporzionale che verrebbe poi
scartata: prima di questa correzione quella quota scartata spariva silenziosamente in cassa (fino
a 39.781,69 su un caso reale). Quando il riferimento non ha alcun dettaglio reale sui crediti (solo
il secchio "altri") e il parziale sì, il motore lo dichiara con
`reference_receivables_undetailed` (severità *warning*, informativo: la ripartizione viene comunque
dal parziale, con o senza il segnale).

### La rata di rimborso
```
rata = debito finanziario a lungo dell'anno base / anni di piano
```
Il **debito finanziario** sono banche + obbligazioni + l'eventuale gap positivo di un abbreviato
(allocato alle banche). Esclude "altri finanziatori" — che ha un piano proprio — e i debiti a
lungo non finanziari (fornitori, tributari, previdenza), per non doppiare né sovra-rimborsare.

È **kernel condiviso** col budget: l'infrannuale la applica all'aggregato, il budget la ripartisce
sulle sotto-voci. Orchestrazione diversa, formula identica per costruzione.

**La rata di un prestito nuovo non consuma il debito bancario pregresso** (lotto 3A, Task 4). Il
pregresso conserva la propria ripartizione breve/lungo e si riduce solo con le proprie rate (prima
dal breve); il prestito nuovo si ammortizza per conto suo e mette a breve, in `sp16a`, la quota di
capitale che scade l'anno dopo. Misurato sul test kit: 12.345,67 di pregresso e un prestito di
120.000 / 4 anni / 5% erogato nell'anno danno `sp16a` 42.345,67 (12.345,67 + 30.000,00) e `sp17a`
60.000,00; prima davano `sp16a` 0,00 e `sp17a` 102.345,67. Il totale del debito, gli interessi in
`ce15` e la cassa non cambiano: la divisione è solo di scadenze. Un contratto **misto** (importo
nuovo e residuo pregresso sulla stessa riga) viene spezzato in due contratti dalle funzioni condivise
del kernel (`projection_common.contratti_da_riga_finanziamento`, `separa_prestiti_nuovi`,
`quota_breve_prestiti_nuovi`), e dà gli stessi numeri di due righe separate.

## 6. I gate: cosa blocca un infrannuale

### Gate semantico sulla fonte
Applicato **prima di ogni calcolo**, al parziale sempre e al riferimento se presente. Solleva
*"{label} {anno}/{mesi}M non è utilizzabile per la previsione: …"*.

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
