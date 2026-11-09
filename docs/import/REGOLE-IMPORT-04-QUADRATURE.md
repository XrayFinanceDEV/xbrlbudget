# 04 — Quadrature, gate e rifiuti

> Torna all'[indice](REGOLE-IMPORT-00-INDICE.md).
> Motori: `importers/iv_cee_hierarchy.py` (`check_quadratura`), `importers/pdf_mapper.py`
> (`validate_balance`), `calculations/ce_result.py` (formula del risultato).

## 1. Perché i controlli sono separati

La tentazione è avere un solo controllo: attivo = passivo. È insufficiente, e il sistema ha
imparato perché.

- Un'estrazione **vuota** ha attivo = passivo = 0, cioè sbilancio zero: quadrerebbe.
- Un bilancio **tamponato** quadra perché la differenza è stata spinta in una voce.
- Un bilancio con il **CE scollegato** dallo SP quadra sul patrimoniale ed è incoerente.
- Un bilancio con **aggregati che non tornano coi dettagli** quadra e ha una composizione falsa.

Perciò i controlli sono cinque, indipendenti, e ne servono di più per dire "questo dato è
utilizzabile" che per dire "questo dato è aritmeticamente coerente".

## 2. I cinque controlli

Basi di calcolo: **totale attivo** = somma di `sp01…sp10`; **totale passivo** = somma di
`sp11…sp18`, **risultato d'esercizio incluso**.

| # | Controllo | Verifica | Tolleranza | Effetto |
|---|---|---|---|---|
| 1 | **Estrazione vuota** | attivo e passivo entrambi ≈ 0 | la tolleranza corrente | forza "non quadra" ed **esclude** il controllo 2 |
| 2 | **Pareggio** | attivo = passivo | €0,01 di default, **€2** dal PDF | non quadra |
| 3 | **Mascheramento** | residuo non classificato oltre l'**1% del totale attivo** | 1%, con pavimento alla tolleranza | non quadra |
| 4 | **Identità CE↔SP** | risultato ricalcolato dal CE = `sp13` | **`max(€2; 0,1% del totale attivo)`** | non quadra |
| 5 | **Gerarchia** | ogni aggregato = somma dei suoi dettagli | la tolleranza corrente | **non** tocca la quadratura; abbassa solo la validità semantica |

Da cui i due verdetti:

```
quadra          = pareggio  E  identità CE↔SP  E  non mascherato  E  non vuoto
semantic_valid  = quadra    E  gerarchia coerente  E  residuo sotto tolleranza
```

**La distinzione fra i due è la cosa più importante di questa pagina.** `quadra` è il gate
contabile duro: sotto di esso l'import non viene salvato. `semantic_valid` è il gate a valle:
decide se il dato può alimentare il previsionale. Un bilancio abbreviato che omette
legittimamente i dettagli **quadra ma non è semanticamente valido** — si importa, si vede, e non
si può proiettare.

### Perché l'identità CE↔SP ha una tolleranza più larga
Il risultato del CE è **ricostruito** sommando una venticinquina di voci lette da un pass
indipendente. Qualche euro di scarto è rumore di composizione, non un errore contabile. Il
pareggio invece confronta due somme dello stesso pass, e resta stretto.

### Perché un aggregato senza dettagli viene segnalato
Può essere perfettamente legale in un bilancio abbreviato. Ma i calcoli a valle hanno bisogno
della ripartizione, e **non è lecito inventarla**. Quindi si segnala — e a farne le spese è
`semantic_valid`, non `quadra`.

## 3. La formula del risultato

Unica per import, ORM, quadratura, budget e infrannuale (`calculations/ce_result.py`). Valori
mancanti valgono zero.

```
Valore della produzione = ce01 + ce02 + ce03 + ce03a + ce04
Costi della produzione  = ce05 + ce06 + ce07 + ce08 + ce09 + ce10 + ce11 + ce11b + ce12
EBIT                    = Valore della produzione − Costi della produzione
EBITDA                  = EBIT + ce09
Gestione finanziaria    = ce13 + ce14 − ce15 + ce16
Rettifiche (sezione D)  = vedi sotto
Straordinari            = ce18 − ce19
Risultato ante imposte  = EBIT + finanziaria + rettifiche + straordinari
Utile netto             = Risultato ante imposte − ce20
```

`ce15` è l'unica voce sottratta nella gestione finanziaria: i costi sono estratti in positivo.

**Anti doppio conteggio sulla sezione D** — l'unico meccanismo esplicito: se *almeno uno* fra
`ce17a` (rivalutazioni) e `ce17b` (svalutazioni) è diverso da zero, si usa `ce17a − ce17b` e
**l'aggregato `ce17` viene ignorato**. Mai la somma di aggregato e dettaglio.

**Attenzione**: `ce03` e `ce03a` sono entrambi sommati, così come `ce11` e `ce11b`. Sono voci
distinte (A.3 e A.4; B.12 e B.13) e **non c'è deduplica fra loro**: se un estrattore mette lo
stesso importo in tutte e due, il risultato è doppiato e nessun controllo se ne accorge.

## 4. Il gate strutturale

Precede la quadratura. Tolleranza **€1**. Quattro test, tutti bloccanti:

1. totale attivo pari a zero → fallisce (estrazione vuota);
2. attivo ≠ passivo oltre €1 → fallisce;
3. la somma degli aggregati dell'attivo deve **ricostruire** il totale attivo dichiarato;
4. idem per il passivo.

I test 3 e 4 sono la difesa anti-masking più diretta: un tampone che avesse forzato
`totale_passivo = totale_attivo` non nasconde più uno sbilancio reale, perché le componenti
devono comunque ricostruire i totali.

Si sommano **solo gli aggregati**, mai i sotto-campi: un bilancio abbreviato che popola
legittimamente i soli aggregati non deve fallire.

Questo gate **non** controlla il CE: quel pezzo lo aggiunge la quadratura subito dopo.

## 5. I messaggi di avviso e di rifiuto, in ordine di precedenza

Quando il gate strutturale fallisce, si sceglie **la diagnosi più utile**, non la prima
disponibile. L'ordine è studiato: l'evidenza stampata dal documento batte la diagnosi di
formato.

**Task 17 (decisione del proprietario, 2026-09-27): «se il bilancio non è quadrato deve essere
comunque importato con avviso, l'utente lo correggerà nella tab rettifiche».** Le righe #2 e #3
erano rifiuti duri (`PDFImportError`) fino a questa decisione: un documento che contraddice i
propri stessi totali stampati non si scarta più, si importa con lo stesso testo diagnostico come
avviso. Solo #1 (scansione/OCR inaffidabile) e #4 (riepilogo davvero troppo aggregato, senza uno
schema IV-CEE da cui ripartire) restano errori duri: non c'è nulla che l'utente possa correggere
in Rettifiche su un file che non ha uno stato patrimoniale leggibile.

| # | Condizione | Messaggio | Duro o avviso |
|---|---|---|---|
| 1 | il documento è una scansione | "*Il documento è una scansione contabile, ma l'OCR non ha ricostruito in modo affidabile colonne, gerarchie e totali…*" — il file **non** viene dichiarato sbilanciato. **Eccezione** (2026-10-14): uno schema di legge le cui cifre ha letto la vision sulle immagini, non un testo OCR, si importa con l'avviso "*BILANCIO SBILANCIATO: le cifre sono lette dalle immagini della scansione…*" — è un errore di lettura correggibile in Rettifiche (ERREGI 30/09/2026: la stessa scansione una volta su tre usciva con 1.000 in meno sull'attivo) ; e qualunque scansione letta dall'OCR (MinerU o locale) con uno scarto entro il **5%** del totale (`_SCANSIONE_SBILANCIO_AMMESSO`, lo scarto peggiore fra aggregati e totali dichiarati) si importa con l'avviso "*…scansione letta dall'OCR, lo Stato Patrimoniale non quadra di…*" (decisione del proprietario, 2026-10-14: si blocca il previsionale, mai il salvataggio) | duro oltre il 5% (avviso se cifre da vision o scarto entro il 5%) |
| 2 | i due totali **stampati** differiscono oltre €2 | "***BILANCIO SBILANCIATO: il bilancio sorgente non quadra prima dell'importazione**: Totale Attivo … != Totale Passivo … (scarto …). Il bilancio è stato importato così com'è: correggilo in Rettifiche prima di calcolare la proiezione.*" | avviso — rilevato **prima** di scegliere un estrattore (`_declared_totals_contradiction` in `pdf_importer.py`, chiamato prima ancora del ramo IV-CEE/route C), ma l'estrazione prosegue comunque e l'avviso resta in testa a `warnings` qualunque cosa dica poi `mapper.validate_balance` sul foglio ricostruito |
| 3 | riepilogo aggregato **che contraddice se stesso** | "***BILANCIO SBILANCIATO: il documento sorgente è internamente incoerente**: le componenti del Conto Economico non ricostruiscono il risultato netto dichiarato (scarto …) e le componenti dell'Attivo non coincidono con il totale stampato (scarto …). Il bilancio è stato importato così com'è: correggilo in Rettifiche prima di calcolare la proiezione.*" | avviso — da `_classify_balance_failure`, dopo che `mapper.validate_balance` è già fallito |
| 4 | riepilogo aggregato la cui stampa è coerente (`_is_aggregated_summary`: nessun sotto-item in numero romano, nessun "esigibili entro/oltre", nessun codice conto) | "***Formato non supportato**: il documento è un riepilogo aggregato per macro-voci, non uno schema di bilancio IV-CEE (art. 2424/2425) importabile…*" | duro |
| 5 | totali stampati coincidenti, ma componenti che non li ricostruiscono | "*Documento non importabile automaticamente: i totali Attivo e Passivo stampati coincidono, ma le componenti… non li ricostruiscono.*" | avviso |
| 6 | nessuna delle precedenti | messaggio generico | avviso |

Sono tutte **regole generiche**, non legate a file specifici: la #2 colpisce indifferentemente
il LUGS di prova e un Greco Servizi reale, perché legge i totali che ciascun documento stampa.

### Perché la #3 viene prima della #4
Un riepilogo che pareggia **solo perché una cifra è stata gonfiata** non è "troppo aggregato":
è **auto-contraddittorio**, e questo è il difetto che l'avviso deve nominare per primo.

Il caso che ha originato la regola (2026-07-16, budget_137) è istruttivo. Lo stesso documento
esiste in tre versioni:

| Versione | Debiti | Effetto |
|---|---|---|
| budget_133 / 135 | 2.688.470,08 | attivo ≠ passivo → riceve la diagnosi #2 |
| budget_137 "definitivo" | **3.995.536,14** | i due lati pareggiano → sfuggiva alla #2 |

Il pareggio del 137 è cosmetico: i Debiti sono stati gonfiati di 1,3 milioni perché i totali
tornassero, e la nota tecnica del file si vanta di *"garantire la perfetta quadratura tra attivo
e passivo"*. Ma le sue componenti lo smentiscono: l'Attivo somma 4.168.990,10 contro un totale
stampato di 4.079.635,72 (scarto **89.354,38**), e il CE ricostruisce −205.587,68 contro un
risultato stampato di −266.938,57 (scarto **61.350,89**).

La diagnosi #3 legge **solo gli importi che il documento stampa**, riporta i due scarti, e **non
pubblica mai un totale "corretto"** che il documento non contiene. Tace quando la stampa è
coerente o troppo scarna per giudicare: il silenzio è la risposta sicura, e da Task 17 il file
si importa comunque con quel silenzio (nessun avviso di questo tipo) o con l'avviso dichiarato,
mai più rifiutato per queste sue ragioni — #4 resta l'unico rifiuto duro di questo gruppo, e solo
perché lì non c'è nemmeno uno schema da cui ripartire.

Il controllo del CE viene **saltato del tutto se il documento stampa una riga imposte**: fra la
differenza A−B e il risultato netto ci starebbero le imposte, e non sarebbe ricostruibile.

Gli importi dentro questi messaggi — e quelli delle diagnostiche di quadratura più a valle
(`check_quadratura` in `importers/iv_cee_hierarchy.py`: ESTRAZIONE VUOTA, BILANCIO NON QUADRATO,
QUADRATURA MASCHERATA, GERARCHIA INCOERENTE; `enforce_ce_sp_identity`, stesso file: CE↔SP
incoerente — entrambe misurano e dichiarano soltanto, non modificano una voce contabile; il 400
della guardia Rettifiche in
`backend/app/api/v1/financial_years.py`; gli avvisi di route C in `importers/pdf_importer.py`) —
si scrivono in formato italiano (`eur_it`/l'helper locale `_it_amount`), mai `{x:,.2f}` alla
americana: un messaggio in italiano con "1,470,357.32" invece di "1.470.357,32" è stato un
difetto reale, corretto in un'ondata successiva al lotto 3A
(`.superpowers/sdd/2026-09-11-indagine-difetti-collaudo-3a/indagine-2-promote.md`, 2026-09-11 —
spazio di lavoro **fuori dal repo**, non è mai stato in git).

## 5-bis. Lo sbilancio chiuso dal risultato stampato

Prima del gate, su ogni rotta (`importers/risultato_stampato.py`, chiamato da `pdf_importer`):
si misura `attivo − passivo` e lo si cerca **al centesimo** nel testo del documento, su una riga
che porta una didascalia di risultato (utile, perdita, risultato, eccedenza, avanzo, disavanzo),
dal lato in cui il gestionale la stampa. Due esiti soli:

- lo sbilancio è la differenza fra l'utile del CE e `sp13`, e quell'utile è stampato → `sp13`
  diventa l'utile del CE (`risultato_del_periodo`);
- lo sbilancio stesso è stampato come risultato → è l'anno prima non destinato, va in `sp12` e
  `sp12g` (`risultato_anno_prima`).

Non è un plug: etichetta un importo stampato, solo al centesimo, e se l'importo non c'è non
succede nulla. Si dichiara sempre (avviso e `validation_report["risultato_stampato"]`). Uno
sbilancio pari all'utile del periodo che `sp13` porta già non si tocca: è un risultato contato
due volte o una massa mancante altrove, non un anno prima.

**Costi disegnati come grafica** (situazioni AGO a sezioni contrapposte 8-digit, budget_618/619,
decisione del proprietario 2026-10-14). Alcuni importi del PDF sono tracciati, non testo: un
mastro di costi manca alla lettura e l'utile del CE esce più alto. `_c8_risultato_stampato`
(`situazione_contabile_parser.py`) mette in `sp13` l'«UTILE/PERDITA D'ESERCIZIO» stampato solo
se chiude lo SP al centesimo **e** la differenza col CE è esattamente TOTALE COSTI stampato meno
costi letti (ricavi letti = TOTALE RICAVI stampato). Il CE non si tocca: la massa mancante si
dichiara (`_ce_massa_non_letta`), il bilancio resta sbilanciato CE/SP con un avviso che cita i
due totali, e l'utente inserisce i costi in Rettifiche. Nel percorso snello quella lettura resta
in gara col modello (Task 28) anche oltre la soglia. Sullo stesso formato la firma 8-digit
(sottoconti `NNNNNN NNN`) vince su quella AGO a blocchi quando «BILANCIO DI VERIFICA» è testo.

**Verifica che non pareggia da sola** (verifica a colonna unica IE/E, budget_680, decisione del
proprietario 2026-10-06). `parse_entries_verifica_ie` legge il saldo finale di ogni conto (il segno
D/A decide il lato dello SP) e si verifica sui quattro totali di sezione e sull'utile stampati:
se una sezione non torna, la lettura è vuota. Quando il dare stampato (attività + costi) differisce
dall'avere (passività + ricavi), di solito per un risultato dell'anno prima non destinato, il
parser lo dichiara (`_verifica_dare`/`_verifica_avere`) e il percorso snello adotta la lettura
**squadrata** (`causa: documento_sbilanciato`, tipo `verifica`) senza chiamare il modello, se il suo
scarto Attivo/Passivo è esattamente quella differenza e il CE torna.

**Risultato dell'anno prima non riaperto** (verifica progressiva, decisione del proprietario
2026-10-15, che rivede quella del 2026-10-06 su budget_680). Il saldo finale è apertura + dare −
avere: se la colonna d'apertura stampata («Saldo al 31/12» dell'anno prima) ha solo stato
patrimoniale, non pareggia, e lo sbilancio dare/avere del saldo finale è **la stessa cifra al
centesimo**, i movimenti dell'anno pareggiano e lo sbilancio è il risultato dell'anno prima che le
scritture d'apertura non hanno riaperto. `_ie_risultato_in_apertura` lo mette negli utili (perdite)
portati a nuovo (`sp12`/`sp12g`, segno dell'apertura) e l'import lo dichiara con un avviso che cita
le due colonne. Se le due cifre non coincidono non si tocca nulla: resta il documento sbilanciato.
680: perdita 2025 −348.287,23, verificato.

## 6. Dopo il gate strutturale: la quadratura

Se `check_quadratura` dice che non quadra → **"Importazione non salvata: il bilancio estratto non
supera i controlli contabili (…)"**. I warning di gerarchia sono **esclusi** da questo messaggio:
non sono ciò che blocca.

Scelta di progetto esplicita: un disaccordo CE/SP o un tampone materiale **non sono
warning-only**, bloccano il salvataggio. La copertura dei dettagli resta invece visibile a parte
tramite `semantic_valid`, perché gli abbreviati possono legittimamente ometterla.

## 7. "TESTO PDF CORROTTO" è un flag, non un rifiuto

L'import **prosegue**, con warning: *"TESTO PDF CORROTTO (mappa font danneggiata): l'estrazione è
inaffidabile — verificare TUTTI i valori in Rettifiche"*. Ma i totali dichiarati vengono
disattivati in tre punti: selezione dei candidati, ancoraggio del risultato, arbitraggio CE↔SP.

## 8. Tutte le tolleranze

| Soglia | Valore | Dove |
|---|---|---|
| Pareggio, default | €0,01 | CSV, XBRL |
| Pareggio, PDF | **€2** | i campi LLM e i totali stampati sono arrotondati all'euro; il mapper concede €1 per lato, quindi i due lati possono divergere di €2 pur concordando con lo stesso dichiarato (budget_305: €1,82) |
| Mascheramento | 1% del totale attivo | — |
| Identità CE↔SP | `max(€2; 0,1% del totale attivo)` | — |
| Identità CE↔SP nell'arbitro | `max(€2; 0,1% di \|sp13\|)` | ancorata al risultato, non al totale |
| Gate strutturale | €1 per ciascuno dei test | — |
| Avviso "sorgente non quadra" (dal Task 17 non è più un rifiuto) | scarto stampato > €2 | — |
| Incoerenza interna (dal Task 17 non è più un rifiuto) | scarto CE > €2; scarto Attivo > €2 | — |
| Gap di completezza route C | ignorato sotto il 2% | — |
| Severità warning route C | 20% → "prevalentemente stimata" | **non rifiuta**, vedi indice §5 D2 |
| Emissione del warning residuo | > €1 | — |
| Rettifiche | €5 | — |
| Cross-check finale | > €1 → warning | non blocca |
| `arithmetic_balanced` nel report | **€0,01 fisso** | indipendente dalla tolleranza di runtime: un import passato con tolleranza €2 può risultare `false` qui |

## 9. Gli stati

### Persistiti sul database

| Stato | Criterio |
|---|---|
| `verified` + forecastable | `semantic_valid` |
| `review_required` + non forecastable | import salvato ma non semanticamente valido |
| `legacy` + non forecastable | **default di colonna**: i record importati prima del versionamento non sono dichiarati validi d'ufficio |
| `draft` | anno creato a mano |

`forecastable` **non** è più uguale a `semantic_valid` (aggiornato 2026-08-14). Sul percorso PDF è
`semantic_valid` **e** il verdetto sui conti critici (§9-bis): `pdf_importer.py:1534`. Resta vero
che un bilancio non semanticamente valido non alimenta mai il previsionale — è solo che ora non
basta. L'anno **precedente** fa eccezione e usa il solo `semantic_valid`. L'XBRL rafforza il
criterio da un'altra parte, aggiungendo l'assenza di conflitti aggregato/dettaglio e di breakdown
mancanti.

### Dell'audit di corpus (diagnostici, non persistiti)

| Stato | Criterio |
|---|---|
| `PASS_VERIFIED` | `semantic_valid` |
| `PASS_STRUCTURAL` | quadra ma non semanticamente valido |
| `REVIEW_REQUIRED` | leggibile ma non quadra |
| `REJECTED` | estrazione vuota o eccezione |
| `UNSUPPORTED` / `UNSUPPORTED_LOCAL_OCR` | formato non supportato / scansione senza OCR locale |
| `NOT_REEXECUTED_NO_API` | route LLM senza chiave |

`MASK` **non è uno stato**: è un flag, e per policy **non va mai contato come successo**.

## 9-bis. L'affidabilità dei conti che decidono i KPI

> Motore: `importers/reliability.py` — modulo **puro**, senza I/O, PDF o DB, così anche gli
> importer XBRL e CSV possono usarlo.

Trasforma l'evidenza che la pipeline ha già calcolato in un verdetto **per conto**, su tre gruppi
scelti perché decidono ogni indicatore:

| Gruppo | Evidenza letta |
|---|---|
| **Immobilizzazioni** | i marcatori `_contra_*`: massa di contro-conti *rilevata ma non applicata* significa attivo lordo con i fondi fra i debiti |
| **Patrimonio netto** | `sp11 + sp12 + sp13` ricostruito contro un totale di controllo stampato |
| **Debiti verso banche** | lo scarto aggregato/dettaglio, calcolato **come lo calcola `base_bank_debt`**, così il verdetto descrive ciò che il motore previsionale farà davvero |

Tre stati: `VERIFIED` (corroborato da evidenza indipendente), `DERIVED` (dedotto ma internamente
coerente), `UNRELIABLE` (l'evidenza dice che il numero è probabilmente sbagliato).

> **`UNRELIABLE` richiede una contraddizione POSITIVA, mai un controllo assente.** Un controllo che
> manca dà `DERIVED`. Senza questa regola ogni file di route A/B verrebbe segnalato solo perché su
> quelle route non gira nessuna scansione dei contro-conti.

Il report finisce nel `validation_report` persistito sotto `critical_accounts`, e
`PUT /adjustments` lo conserva e lo riapplica: una rettifica a vuoto non può ripulire il flag.

**Il verdetto gate il previsionale, mai il salvataggio.** Le Rettifiche operano su un
`FinancialYear` già persistito: rifiutare il salvataggio di un file inaffidabile lo renderebbe
incorreggibile per sempre. Qualunque errore nel calcolo del verdetto vale "non lo so", e "non lo
so" non blocca.

**Due limiti dichiarati.** Nessun percorso di previsionale legge oggi `fy.forecastable`:
l'infrannuale ri-deriva il proprio gate dai valori correnti (pagina 05 §6, e lì è **necessario**,
perché le Rettifiche cambiano il record dopo l'import), il budget non ne ha uno, e la promozione
scrive `True` fisso. Ed è per costruzione che `patrimonio_netto` risulta **sempre** `DERIVED`: la
lettura dei totali dichiarati non produce (ancora) una chiave `patrimonio_netto`, quindi il
controllo manca — e un controllo che manca non condanna.

Test: `tests/test_reliability.py`, `tests/test_reliability_gating.py`.

## 10. Le Rettifiche: la regola di monotonia

Una rettifica manuale viene rifiutata (HTTP 400) **solo se peggiora oltre €5** una fra: attivo −
passivo, CE − `sp13`, aggregati − dettagli.

La sfumatura importante: **uno squilibrio preesistente è ammesso**. Un record importato già
sbilanciato resta modificabile, purché il gap non aumenti — altrimenti sarebbe impossibile
correggerlo a mano, che è esattamente lo scopo delle Rettifiche. Dopo la modifica lo stato di
validazione è **ricalcolato**.

## 11. La promozione di una proiezione

Richiede `semantic_valid` **sulla proiezione**. Non è una soglia in euro (vedi indice §5 D5).

## 12. Il percorso snello: tappo di 10 € dichiarato

> Motore: `importers/import_snello/verifica.py`. Solo sotto `IMPORT_MOTORE=snello` — vedi
> [REGOLE-IMPORT-02-ESTRAZIONE.md §10](REGOLE-IMPORT-02-ESTRAZIONE.md).

Il percorso snello non usa le tolleranze fisse di questa pagina. Il tappo e il confronto con i
totali stampati dal documento tollerano **al massimo 10 €** per controllo (`verifica.limite_tappo`,
decisione del proprietario, 2026-10-03 — prima `max(100 €, 0,1% dell'attivo)`: su tre casi
controllati il tappo grande copriva una riga non letta o un importo inesistente; manopola
`IMPORT_SNELLO_TAPPO_MAX`). La soglia relativa `soglia()` =
`max(IMPORT_SNELLO_SOGLIA_MIN, IMPORT_SNELLO_SOGLIA_PCT% del totale attivo)` non decide più un
tappo, ma resta dove serve una tolleranza relativa:
- il cancello sulla massa non classificata dei candidati deterministici;
- la finestra della lettura di riserva (REGOLE-IMPORT-02 §10, «La lettura più vicina»);
- la coerenza dei totali stampati letti dal testo (`verifica.totali_stampati`: se attivo e
  passivo letti sono troppo distanti, si riprova sul testo ordinato per posizione);
- nel modo `"conti"`, il verdetto sul risultato d'esercizio ambiguo (`conti.py`: un'assegnazione
  corrente/precedente si accetta solo se lo scarto sta entro soglia).

**Entro 10 €, un tappo dichiarato — l'unica eccezione al divieto di plug di questa pagina**,
decisione del proprietario (2026-09-26, limite del 2026-10-03): lo scarto si chiude, non solo si dichiara, su un campo
esplicito — `sp06g_crediti_altri_breve` o `sp16g_altri_debiti_breve` sullo SP, `ce06_servizi` fra
CE e SP — mai su un campo `TIER0`. Un tappo che porterebbe `ce06_servizi` sotto zero **non si
applica**: l'esito diventa "oltre soglia" invece di un tappo negativo.

**Oltre i 10 €, si salva con lo sbilancio dichiarato — decisione del proprietario (Task 17,
2026-09-27): «se il bilancio non è quadrato deve essere comunque importato con avviso, l'utente
lo correggerà nella tab rettifiche».** Nessun tappo si applica in questo caso (lo SP/CE restano
quelli letti, invariati): l'esito diventato `"squadrato"` porta comunque `misura` con lo scarto
misurato, e `pdf_importer.py` ne deriva un `unbalanced_reason` esplicito
(`_snello_squadrato_reason`) quando nessun altro avviso lo ha già dichiarato — necessario perché
uno scarto sui soli totali **stampati** dal documento (`scarto_stampati`) può lasciare lo SP
ricostruito internamente quadrato, e `mapper.validate_balance` da solo non lo vedrebbe. Ne segue
un `validation_status` `"unbalanced"` (mai `"verified"`) e un previsionale bloccato dal verdetto
**esistente** di `check_quadratura` sul foglio persistito, non da un cancello nuovo.

**Dove si legge.** Nel `validation_report["import_snello"]` del foglio: `misura` porta lo scarto
SP/CE misurato prima del tappo (per esercizio: `corrente` e, in modo `"legge"`, `precedente`),
`tappo` il campo/importo scelto (`None` su `"squadrato"`). Gli esiti realmente emessi sono
**`"ok"` / `"tappo"` / `"squadrato"` / `"ripiego"` / `"non_applicabile"`** — la tabella completa,
con le chiavi proprie di ciascuno, è in
[REGOLE-IMPORT-02-ESTRAZIONE.md §10](REGOLE-IMPORT-02-ESTRAZIONE.md). Le chiavi diagnostiche
generali restano quelle di sempre, sul `BalanceSheet` finale: `_plug_residual` = l'importo del
tappo sullo SP (0 se nessun tappo, quindi anche su `"squadrato"`), `_unclassified_mass` = la massa
in `diag["lato_irrisolti"]`, per un conto sul lato sbagliato senza contropartita — mai zero per
omissione, sempre dichiarate.

**Una rilettura mirata (solo in modo `"legge"`); il ripiego resta solo per `"vuoto"` e per gli
insuccessi a monte.** Il ripiego è l'importatore attuale, intero e invariato: da lì in avanti
valgono **tutte** le regole di questa pagina, comprese quelle che qui sopra il percorso snello
supera (nessun plug, chiusura solo diagnostica). Si ripiega solo quando l'esito resta `"vuoto"`
dopo la rilettura (un'estrazione vuota non ha nulla di sensato da salvare), quando la struttura
del documento non si riconosce, o su un'eccezione imprevista — mai più su `"oltre_soglia"`, che
diventa `"squadrato"` (sopra). Anche in quei tre casi non si ripiega se un candidato
deterministico, scartato solo perché oltre i 10 €, aveva letto davvero: si salva quella lettura,
`"squadrato"`, con `ripiego_evitato` nel report (Task 28). Il ripiego si dichiara con
`validation_report["import_snello"]["esito"] = "ripiego"` (`fase`/`errore` accanto). Un documento
scansionato o letto da OCR non tenta nemmeno il percorso snello: `"non_applicabile"`, con
`motivo`, deciso prima di leggere una sola riga.

**La chiusura al centesimo resta la regola dell'importatore attuale.** Il limite di 10 € e il
tappo governano solo il **percorso snello** (F3, prima del punto di convergenza): non toccano
`arithmetic_balanced` (§8, **€0,01 fisso**, indipendente da qualunque tolleranza di runtime) né
il gate contabile duro di questa pagina (§2, `quadra`), che restano quelli di sempre e continuano
a girare sul foglio consegnato — un tappo entro 10 € non è una licenza a saltare la quadratura
al centesimo che l'importatore attuale misura dopo.

## 13. Blocchi che non chiudono (Fase 2)

> Codice: `importers/lettore/blocchi.py` (che cosa è un blocco), `importers/lettore/diagnosi.py` (diagnosi e
> frasi), `_lettore_diagnosi_import` in `importers/pdf_importer.py` (il collegamento). Il lettore di righe è
> descritto in [REGOLE-IMPORT-02-ESTRAZIONE.md §11](REGOLE-IMPORT-02-ESTRAZIONE.md).

Dalla Fase 2 il lettore di righe gira su ogni PDF importato, **solo per diagnosticare**: nomina i totali
stampati i cui figli non sommano, così l'utente sa dove guardare in Rettifiche. Non legge, non classifica e non
corregge nulla: **nessun importo dell'import dipende da questo modulo** (SP, CE, esito e anni sono quelli di
prima). Se qualcosa va storto nel lettore, l'import non se ne accorge.

### Che cosa è un blocco

Un blocco è un **totale stampato dal documento** il cui importo, su una colonna di esercizio o di saldo, non
è la somma dei figli candidati oltre la tolleranza della cella (la C6 del lettore: un euro se il totale è
stampato all'unità, altrimenti il centesimo). Una voce che ha solo figli dichiarati dall'intestazione, senza
un totale stampato, **non è un blocco**: una parentela da intestazione è un'ipotesi, e «non chiude» su
un'ipotesi inventerebbe un difetto. Un totale senza figli con un importo non è un blocco. Colonne di
differenza, percentuale e i parziali delle coppie non contano.

Due origini, e la differenza si porta in `cercato`:

- **`cercato: false` — figli noti.** Il totale è stato chiuso su un'altra colonna (stessi figli, colonna
  per colonna): su questa colonna gli stessi figli non sommano. I figli sono quelli veri, lo scarto è un
  fatto del documento.
- **`cercato: true` — riga di controllo mai chiusa.** Nessuna colonna chiude; i figli sono un tratto di righe
  **scelto dal lettore per minimo scarto** fra i tagli possibili sopra la riga. È una stima di dove sta il
  buco, non un fatto.

I blocchi `cercato` si producono **solo su un profilo da schema di legge** (`schema`, `schema-dettaglio`). Su
contrapposte, bilanci di verifica e profilo ignoto ci sono solo blocchi da figli noti: sugli elenchi di conti
il tratto indovinato inventa divari da milioni, e un divario falso vale peggio di nessun avviso. Se il
criterio è troppo stretto, si nominano meno blocchi sulle contrapposte, mai uno falso.

L'ordine è dal più grande scarto in valore assoluto. Il tratto è dato da prima e ultima riga (totale
compreso), pagina del totale ed etichette dei figli (al massimo 12).

### Che cosa vede l'utente, e quando

Le frasi stanno fra gli avvisi dell'import, subito dopo il motivo di sbilancio (se c'è), **solo quando
l'import stesso dichiara che qualcosa non torna**: SP sbilanciato oltre 2 € (`_TOL_QUADRATURA`, la tolleranza dei gate dell'import: sotto non c'è avviso e quindi nemmeno
frasi; sezione SP), utile del CE
diverso da `sp13` (sezione CE), esito snello `squadrato` o `tappo` (SP); se c'è un motivo di sbilancio ma
nessuna di queste, entrambe le sezioni. Si mostrano soltanto i blocchi di quelle sezioni, la colonna corrente prima dell'anno precedente, e mai un blocco
con scarto fino a 1,00 € (`TOLLERANZA_ARROTONDAMENTO`, decisione del proprietario: è arrotondamento; resta in
`validation_report`). Una colonna corrente senza data stampata non viene scartata dal filtro per anno.
Su un import che quadra l'utente non vede nulla: un blocco «aperto» in un documento che torna è quasi sempre
un limite del lettore, non un difetto del bilancio, e avvisarne l'utente sarebbe rumore. Il dato resta in
`validation_report`.

Forma: un'intestazione fissa seguita da **al massimo 5** frasi (prima i blocchi a figli noti, poi i
cercati, ciascun gruppo dallo scarto maggiore), solo della **colonna corrente** (o dell'anno precedente):

> BLOCCHI CHE NON CHIUDONO NEL PDF: i totali stampati qui sotto non sono la somma delle righe che li
> precedono; verificarli in Rettifiche.
> B) II - Crediti (2025, p. 3, righe 12-27): stampato 1.234,56, i conti sommano 1.200,00, scarto 34,56

(esempio sintetico). Se il tratto attraversa una pagina la frase dice «pp. 3-4». Le frasi dei blocchi
`cercato` terminano con « (righe individuate dal lettore: da verificare)»: l'utente deve sapere che il tratto
è una stima. Una diagnosi malformata non produce frasi.

### `validation_report["lettore"]`

La diagnosi intera, sempre (anche su un import che quadra), una volta per import:

| Campo | Contenuto |
|---|---|
| `esito` | `ok`, `errore`, `tempo`, `non_applicabile` (nessun testo né tabella) |
| `motivo` | perché, se non `ok` |
| `ingresso` | `pdf` (text layer) o `mineru` (tabelle OCR) |
| `tipo`, `contrapposto` | il profilo letto dal lettore |
| `colonne` | indice, ruolo, fine, mesi, corrente |
| `blocchi_aperti` | al massimo 20, solo colonne dell'anno corrente e del precedente; voce, codice, sezione, lato, colonna, fine, mesi, corrente, stampato, somma, scarto, pagina, righe, etichette, `cercato` (importi come stringhe) |
| `avvisi` | quelli del lettore (`Documento.tutti_gli_avvisi`) |
| `secondi` | durata |

Se il lettore fallisce fuori dal suo tetto, la chiave porta `{esito: "errore", motivo}`.

**Interruttore e tetto.** `LETTORE_DIAGNOSI=0|false|no|off` spegne tutto: nessuna chiave, nessuna frase.
`LETTORE_TETTO_SECONDI` (default 20; un valore non numerico o non positivo torna al default) è il tempo
massimo della lettura: scaduto, esito `tempo` e l'import prosegue. La diagnosi **non solleva mai**, né dentro
il lettore né nel collegamento; il thread scaduto non si attende.

### Limiti noti, ereditati dalla Fase 1

Vedi [REGOLE-IMPORT-02 §11](REGOLE-IMPORT-02-ESTRAZIONE.md). In pratica un blocco può mancare o essere
sbagliato per: text layer OCR sporchi; confine fra i due lati deciso per pagina; colonne col ruolo letto
male; righe di etichetta spezzate su più righe fisiche; e, per i blocchi `cercato`, il tratto scelto per
minimo scarto che può non essere quello vero (per questo «da verificare»). Un documento sbilanciato senza
blocco nominato non vuol dire che il bilancio sia a posto.

**Misura sul campione** (78 documenti × 3 giri, 2026-11-06, contro la base `base-fase2-e3455d6`):

- nessun import fallito per colpa del lettore; la chiave `lettore` c'è su ogni giro importato;
- esito `ok` su tutti i documenti con testo salvo un giro su 234 andato in `tempo` (1540, 20,5 s), dopo la correzione della numerazione delle pagine di MinerU (da 0,
  il lettore conta da 1: prima della correzione i sei documenti arrivati da MinerU uscivano in `errore`); una
  scansione senza tabelle utili esce `non_applicabile`;
- tempo: mediana 0,39 s, media 0,92 s;
- numeri invariati su 60 dei 64 documenti stabili della base; i quattro che cambiano cambiano anche a lettore
  spento (`LETTORE_DIAGNOSI=0`, verificato su due di essi): la causa è fuori dal lettore (variabilità del modello);
- documenti salvati sbilanciati: 14; un blocco nominato su 4, e su uno lo scarto spiega lo sbilancio al
  centesimo. Sui 10 senza blocco, in 9 il PDF quadra (ogni totale stampato chiude, attivo = passivo): lo
  sbilancio nasce dalla classificazione o dalla scelta di colonna dell'import, che la diagnosi non vede per
  costruzione; il decimo è una scansione. Il criterio del piano («almeno metà degli sbilanciati con un blocco»)
  presupponeva sbilanci nati dal PDF: sul campione non lo sono.

Da qui la regola della Fase 3 (decisione del proprietario, 2026-11-06): un PDF che quadra si importa quadrato,
con gli aggregati ancorati ai totali stampati verificati dal lettore; i dettagli si distribuiscono dentro
l'aggregato e non possono sbilanciare il foglio.

## 14. Prima quadrato, poi i dettagli (Fase 3)

> Codice: `importers/lettore/componi.py`, `importers/lettore/percorso.py`. Il percorso è descritto in
> [REGOLE-IMPORT-02 §11](REGOLE-IMPORT-02-ESTRAZIONE.md).

**La regola del proprietario (2026-11-06):** la priorità è importare PDF quadrati; la ricerca dei dettagli per la
classificazione corretta viene dopo, e **i dettagli non devono sbilanciare il foglio importato**. Un dettaglio sbagliato
è un errore dentro un aggregato (l'utente lo rifinisce in Rettifiche); un foglio sbilanciato è un numero su cui non si
può decidere.

**Perché un PDF che quadra esce quadrato per costruzione.**

- **Ogni foglia conta una volta**, mai un mastro coi suoi figli.
- **La colonna decide il lato**: attivo solo su `sp01`-`sp10`, passivo su `sp11`-`sp18`, costi e ricavi per
  sezione e colonna, mai per descrizione. Anche con la macro-voce sbagliata la foglia resta sul suo lato, quindi il
  pareggio non si muove.
- **Una rettifica stampata nella colonna opposta** (un fondo ammortamento fra le passività, perdite portate a nuovo
  fra le attività) si netta sul bene o sul netto: sparisce da un lato e scende dall'altro della stessa massa, quindi
  il pareggio resta. È l'unico conto che attraversa il lato, e solo se il modello lo nomina come rettifica
  (`tavola.RETTIFICHE`). Un fondo oltre il proprio cespite si azzera e l'eccedenza resta sbilancio dichiarato, come
  in `conti.py`. I totali stampati sono lordi: il cancello li confronta al netto di `_netted_contra` e al lordo di `spostati` (i saldi negativi passati all'altro lato,
  `percorso._stampati`). Un fondo si
  netta sulla macro del cespite della sua famiglia (F3-16), così la massa non passa fra `sp02` e `sp03`.
- **I dettagli stanno dentro la loro macro-voce**: il secondo passo sceglie solo fra le sotto-voci della macro
  assegnata; l'aggregato resta la somma delle sue foglie. Dal 2026-11-09 il dettaglio è il più fine possibile (ogni
  macro che ne ha, e quello del percorso di legge si tiene), «altri» solo se ignoto: più dettagli non muovono il
  pareggio, perché nessuno esce dalla sua macro.
- **`sp13` è la cifra di chiusura**: l'utile del CE se il documento ha un CE; il risultato stampato se c'è solo lo
  SP (una cifra letta, non inventata, `sp13_da: "stampato"`); altrimenti assente. Mai una foglia (la riga del
  risultato e le classi `sp13`/`ce21` non si sommano).
- Una foglia **senza classe** cade nel secchio «altri» del suo lato (`sp06g`/`sp16g`, `ce06` fra i costi, `ce04` fra
  i ricavi), mai su un aggregato né su `TIER0_FIELDS`; se anche il lato è ignoto non entra da nessuna parte.

**Chiusura fino a 1 € per controllo, dichiarata** (le chiusure possibili sono due, utile/CE e attivo/passivo: al più 2 € in totale). Decisione del proprietario: fino a 1 € è arrotondamento, si chiude da sé, senza
avviso all'utente. Utile stampato contro utile del CE: lo scarto va su `ce04` (utile stampato più alto) o `ce06`;
attivo contro passivo: su `sp16g` (manca passivo) o `sp06g` (manca attivo). Ogni chiusura è registrata
(`diagnostica["chiusure"]`) e la loro somma è `_plug_residual`. Il tappo snello fino a 10 € di §12 resta com'è e
non è questo. **Oltre 1 €** nulla si muove: lo scarto si misura, le ancore che non tornano restano in
`blocchi` e il cancello comune (`deterministico.esito`) decide l'adozione.

**La massa non classificata si dichiara**, non si copre: `_unclassified_mass` è il valore assoluto delle foglie
senza macro, sempre presente anche a zero (a valle una chiave assente vale zero). Il cancello respinge un
documento con troppa massa non classificata.

**Mai un plug.** Un divario oltre 1 € non si tappa: o il documento non è adottato e prosegue il percorso di §10,
o si salva con lo sbilancio dichiarato come per ogni lettore. *Se si ignora:* un plug attribuisce a un conto vero un
importo che nessuno ha letto, e il foglio quadra lo stesso: è il guasto che questa regola esiste per evitare.

Misura sul campione (78 documenti × 3 giri, `tests/corpus/punteggio.py`, giro `fase3-4de18b6`, 2026-11-09, contro `fase3-502f078` del primo innesto): dei 9 documenti il cui PDF quadra ma l'import no alla Fase 2, **7 escono quadrati in tutti i giri** (contro 2); i due fuori sono attesi (massa non classificabile; foglie davvero non in pari, attivo e passivo affiancati). Documenti salvati sbilanciati 12 → 7, nessuno nuovo. 11 documenti adottati dal lettore, nessuno instabile nell'adozione. Macro-voci esatte 78,7% → 80,6%, dettagli KPI 76,4% → 80,3%, altri dettagli 75,5% → 78,7%. Costo per import adottato: mediana 6 chiamate al modello (max 9, tetto 40 mai toccato), 66 s di lettore (max 153 s).
