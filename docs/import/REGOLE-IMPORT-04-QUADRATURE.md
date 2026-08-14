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

## 5. I messaggi di rifiuto, in ordine di precedenza

Quando il gate strutturale fallisce, si sceglie **la diagnosi più utile**, non la prima
disponibile. L'ordine è studiato: l'evidenza stampata dal documento batte la diagnosi di
formato.

| # | Condizione | Messaggio |
|---|---|---|
| 1 | il documento è una scansione | "*Il documento è una scansione contabile, ma l'OCR non ha ricostruito in modo affidabile colonne, gerarchie e totali…*" — il file **non** viene dichiarato sbilanciato |
| 2 | i due totali **stampati** differiscono oltre €2 | "***Il bilancio sorgente non quadra prima dell'importazione**: Totale Attivo … != Totale Passivo … (scarto …). Correggere il documento contabile originale.*" |
| 3 | riepilogo aggregato **che contraddice se stesso** | "***Il documento sorgente è internamente incoerente**: le componenti del Conto Economico non ricostruiscono il risultato netto dichiarato (scarto …) e le componenti dell'Attivo non coincidono con il totale stampato (scarto …). Correggere il documento contabile originale.*" |
| 4 | riepilogo aggregato la cui stampa è coerente (`_is_aggregated_summary`: nessun sotto-item in numero romano, nessun "esigibili entro/oltre", nessun codice conto) | "***Formato non supportato**: il documento è un riepilogo aggregato per macro-voci, non uno schema di bilancio IV-CEE (art. 2424/2425) importabile…*" |
| 5 | totali stampati coincidenti, ma componenti che non li ricostruiscono | "*Documento non importabile automaticamente: i totali Attivo e Passivo stampati coincidono, ma le componenti… non li ricostruiscono.*" |
| 6 | nessuna delle precedenti | messaggio generico |

Sono tutte **regole generiche**, non legate a file specifici: la #2 colpisce indifferentemente
il LUGS di prova e un Greco Servizi reale, perché legge i totali che ciascun documento stampa.

### Perché la #3 sta prima della #4
Un riepilogo che pareggia **solo perché una cifra è stata gonfiata** non è "troppo aggregato":
è **auto-contraddittorio**, e questo è il difetto che il mittente deve correggere.

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
coerente o troppo scarna per giudicare: il silenzio è la risposta sicura, il file viene comunque
rifiutato per le sue ragioni.

Il controllo del CE viene **saltato del tutto se il documento stampa una riga imposte**: fra la
differenza A−B e il risultato netto ci starebbero le imposte, e non sarebbe ricostruibile.

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
| Rifiuto "sorgente non quadra" | scarto stampato > €2 | — |
| Incoerenza interna | scarto CE > €2; scarto Attivo > €2 | — |
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
