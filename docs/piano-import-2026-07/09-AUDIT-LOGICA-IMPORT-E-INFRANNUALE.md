# 09 — Audit della logica di importazione, IV CEE e infrannuale

Data audit: 2026-07-15  
Stato: **sola analisi; nessuna correzione descritta in questo documento è stata applicata**.

Questo audit riesamina l'intera catena, non soltanto `budget_337_2023.pdf`:

```text
documento → scelta della route → estrazione fatti → classificazione contabile
→ netting contropartite → costruzione IV CEE → controlli/raccordi
→ mapping ORM/DB → infrannuale/previsione → promozione e cash flow
```

Il documento corregge una conclusione troppo ottimistica contenuta in
`08-AUDIT-QUADRATURE.md`: la presenza di un gate o di una riconciliazione non rende
la route «solida». Oggi alcune riconciliazioni modificano il contenuto economico per
ottenere il pareggio. Perciò **quadrato**, **corretto** e **fedele alla fonte** non
sono sinonimi.

## 1. Verdetto

Il difetto principale non è la grafica né il solo PDF 337. Nel corpus etichettato il
classificatore sceglie la route corretta in 77 casi su 77. Gli errori più gravi
nascono dopo l'estrazione:

1. formule diverse calcolano risultati d'esercizio diversi;
2. i dati mancanti vengono assorbiti in utile/perdita, cassa, debiti, riserve,
   altri ricavi o altri oneri;
3. il netto delle immobilizzazioni può mescolare fondo patrimoniale e quota di
   ammortamento del CE;
4. aggregati e sottovoci possono divergere senza impedire il salvataggio;
5. il mapping PDF → DB perde campi già estratti;
6. l'infrannuale può usare il periodo sbagliato, ammortizzare la classe sbagliata e
   costruire la quadratura tramite cassa/debito;
7. la provenienza, la confidenza e i plug non sopravvivono alla persistenza.

La conseguenza è strutturale: il sistema può produrre un bilancio aritmeticamente
bilanciato ma economicamente falso e poi usarlo come base del previsionale.

## 2. Evidenza sul corpus locale, senza nuove API

L'inventario deduplicato per hash contiene 205 documenti fisici e 128 contenuti
unici: 112 PDF, 15 XBRL e 1 CSV. La classificazione disponibile comprende 27
situazioni contabili/route C, 79 bilanci IV CEE/route A-B, 15 XBRL e 7 non
supportati. Le copie e i file di diagnostica spiegano la differenza fra documenti
fisici e contenuti unici.

Risultati riproducibili sui dati già presenti:

- route C di produzione: 17/27 quadrano senza masking; 10/27 richiedono un plug
  superiore all'1%;
- 22/27 route C hanno almeno un aggregato crediti/debiti diverso dalla somma dei
  sottotipi;
- 15 XBRL, 30 annualità: tutte risultano quadrate dopo l'allineamento automatico,
  ma 16/30 hanno breakdown crediti/debiti incoerente;
- 9 DB batch, 23 esercizi: almeno 14/23 hanno mismatch materiale fra aggregati e
  dettagli o componenti negative anomale;
- il CSV BILAQ del corpus non è leggibile dal parser corrente: encoding non UTF-8
  e schema a 13 colonne, mentre il parser presume TEBE a 5 colonne;
- la suite route C passa 7 test, ma il manifest copre soltanto 7 dei 27 file e non
  include il 337;
- la suite completa non è oggi una prova utilizzabile: la raccolta si interrompe
  in `tests/test_hierarchical_import.py` cercando la directory inesistente
  `tests/backend`.

Questi numeri non vanno interpretati come ground truth completa: molti DB e dump
sono prodotti da versioni precedenti. Sono però prove valide che gli invarianti
attuali permettono di persistere strutture semanticamente incoerenti.

## 3. Caso-spia 337: verità contabile e catena dell'errore

La lettura visuale e per coordinate della fonte dà i seguenti valori:

| Voce | Valore corretto |
|---|---:|
| Immobilizzazioni immateriali lorde e nette | 3.239,12 |
| Fondo ammortamento immateriali | 0,00 |
| Immobilizzazioni materiali lorde | 67.229,83 |
| Fondi ammortamento materiali | 62.045,10 |
| Immobilizzazioni materiali nette | 5.184,73 |
| Totale attività/passività lordo della situazione | 315.121,19 |
| Totale IV CEE dopo il netting dei fondi | 253.076,09 |
| Totale costi CE | 368.445,94 |
| Totale ricavi CE | 372.733,17 |
| Utile d'esercizio | **+4.287,23** |

Il valore `680,12` è la sottrazione errata:

```text
3.239,12 immateriali - 2.559,00 ammortamento dell'anno nel CE = 680,12
```

I 2.559 euro non sono un fondo patrimoniale. Il valore `-372.733` deriva invece dal
totale ricavi interpretato come perdita e usato come ancora di riconciliazione.

Il testo incorporato nel PDF è corrotto (`3.239 , 12`, lettere al posto di cifre e
separatori alterati), ma la pagina stampata è leggibile e le coordinate conservano
molta struttura. La route deterministica corrente non ricompone i token monetari
spezzati: `parse_entries` restituisce zero righe e il best-effort produce un attivo
di 36.568,27 con plug di 17.640,69, pari al 48,24%.

Ignorare i totali dichiarati quando il testo è corrotto evita che un totale falso
comandi l'import, ma non risolve l'estrazione. La diagnosi corretta non è «il file è
illeggibile»: è **il ricostruttore di righe e importi non è adeguato a quella mappa
font**. Serve una ricostruzione locale per coordinate, con normalizzazione controllata
dei glifi e validazione contabile; non un'eccezione hard-coded per il 337.

## 4. Cause P0: possono cambiare utile, perdita o stato patrimoniale

### 4.1 Non esiste una formula canonica del risultato CE

Sono presenti almeno quattro implementazioni divergenti:

- `database/models.py`: include `ce03a`, `ce11b` e somma `ce17`;
- `importers/iv_cee_hierarchy.py::_net_profit_from_ce`: omette `ce03a`;
- `importers/pdf_extractor_llm.py::_ce_risultato_ante`: omette `ce03a` e tratta
  `ce17` con segno diverso;
- `calculations/intra_year_engine.py::_net_profit_from_projection`: omette
  `ce11b`.

Con `ce03a > 0`, il controllo può dichiarare CE↔SP coerente usando l'algebra
sbagliata; una riconciliazione successiva può aggiungere lo stesso importo a `ce04`,
sovrastimando il risultato persistito. Con `ce11b > 0`, CE proiettato e `sp13`
previsionale possono divergere.

### 4.2 Le riconciliazioni modificano fatti economici

`enforce_ce_sp_identity` può correggere la differenza intervenendo su `sp13`,
riserve, `ce04_altri_ricavi` o `ce12_oneri_diversi`. Altri passaggi inseriscono lo
scarto in `sp09` o `sp16`, oppure calcolano `sp13` come residuo necessario al
pareggio.

Queste mutazioni sono contabilmente inammissibili senza una riga sorgente: una riga
non estratta può diventare utile, cassa o debito. Inoltre cambiare `ce04`/`ce12`
altera EBIT ed EBITDA, non soltanto una verifica finale.

Punti principali:

- `importers/iv_cee_hierarchy.py`: `reconcile_ivcee_balance` ed
  `enforce_ce_sp_identity`;
- `importers/pdf_extractor_llm.py`: riconciliazione ai totali dichiarati,
  ricostruzioni residuali e allineamento CE;
- `importers/situazione_contabile_parser.py`: best-effort e riduzione residui;
- route PDF, XBRL e CSV condividono parte della stessa logica mutante.

### 4.3 `check_quadratura` non è un gate semantico

`quadra` verifica soprattutto Attivo = Passivo. Non incorpora necessariamente
`utile_match` e non dimostra:

- aggregato = somma dettagli;
- gerarchia CE corretta;
- totale ricalcolato = totale dichiarato della fonte;
- segni e scadenze coerenti;
- assenza di plug economici;
- copertura delle righe sorgente.

La dicitura «OK» può quindi descrivere soltanto un'identità ottenuta dopo la
mutazione.

### 4.4 Netting delle immobilizzazioni non sufficientemente tipizzato

L'invariante corretto è:

```text
netto categoria = lordo categoria - fondo patrimoniale della stessa categoria
```

con `0 <= fondo <= lordo`. Non devono partecipare al netting le quote di
ammortamento del CE; un bilancio IV CEE già netto non deve essere nettato ancora; un
fondo materiale non può ridurre le immateriali. Il comportamento corrente può
clampare a zero un netto negativo, nascondendo una classificazione sbagliata, e può
ridurre altri debiti per assorbire il residuo.

### 4.5 La persistenza PDF perde dati

I costruttori manuali in `importers/pdf_importer.py` non trasferiscono tutti i campi
del modello. Fra i campi a rischio ci sono dettagli patrimoniali e `ce03a`, `ce17a`,
`ce17b`. Un'estrazione corretta può quindi diventare errata fra dizionario e DB.

## 5. Cause P1: classificazione, dettagli e formati

### 5.1 Default contabili troppo aggressivi

Le voci attive non riconosciute possono finire nei crediti, le passive nei debiti,
i costi in oneri diversi e i ricavi nei ricavi vendite. Questo conserva massa ma
perde significato. Una banca con saldo attivo, per esempio, non deve diventare un
credito soltanto perché nessuna regola più specifica ha fatto match.

Una voce non classificata deve restare esplicitamente non classificata, con fonte e
confidenza, e impedire il forecast oltre una soglia materiale.

### 5.2 Aggregati e dettagli non sono un unico oggetto coerente

Gli invarianti minimi sono:

```text
sp04 = Σ sp04a:e        sp05 = Σ sp05a:e
sp06 = Σ sp06a:g        sp07 = Σ sp07a:g
sp12 = Σ sp12a:h        sp14 = Σ sp14a:d
sp16 = Σ sp16a:g        sp17 = Σ sp17a:g
ce08 = Σ ce08a:d        ce09 = Σ ce09a:d
ce17 = ce17a - ce17b
```

Oggi XBRL può modificare un aggregato dopo avere formato i dettagli; PDF può scalare
proporzionalmente le categorie; altri percorsi ricostruiscono i dettagli dal
residuo. Il gap positivo può essere attribuito solo a un bucket esplicito
«non classificato/stimato» con provenienza. Se i dettagli superano l'aggregato non
devono essere scalati: è un conflitto che richiede blocco o revisione.

### 5.3 XBRL perde il contesto infrannuale

I facts sono raggruppati prevalentemente per anno e tag. Annuale, semestre, nove
mesi e facts dimensionali dello stesso anno possono sovrascriversi in base
all'ordine XML. La chiave deve includere entità, instant/duration, date, unità,
dimensioni/scenario e periodo. SP e CE devono provenire da contesti coerenti.

### 5.4 Il CSV supportato non coincide col CSV reale del corpus

Il parser usa UTF-8 fisso e posizioni TEBE a 5 colonne; il file BILAQ è in un altro
encoding e ha 13 colonne. Va introdotto un riconoscimento esplicito dello schema,
non un fallback posizionale.

## 6. Audit specifico dell'infrannuale

### 6.1 Selezione del periodo

`get_fy_partial` cerca per azienda e anno, non per i mesi esatti. Se manca un
parziale, il motore può usare il full-year e annualizzarlo come se fosse parziale.
Il fattore usa inoltre i mesi dello scenario, non necessariamente quelli del record
caricato. È presente nel DB anche uno scenario infrannuale con `period_months=12`.

Requisito: corrispondenza esatta `(company, year, period_months)`, mesi ammessi 1–11
e nessun fallback automatico annuale → parziale.

### 6.2 Roll-forward delle immobilizzazioni

Il motore distribuisce l'intero `ce09` fra `sp02`, `sp03` e perfino `sp04`. È
concettualmente errato:

- `ce09a` riduce solo `sp02`;
- `ce09b` riduce solo `sp03`;
- `ce09c` richiede la classe esplicitamente svalutata;
- `ce09d` riguarda crediti;
- `sp04` non è ammortizzata.

Il calcolo deve essere per classe e basarsi sul saldo parziale effettivo:

```text
netto finale = netto al periodo
             + investimenti residui della classe
             - ammortamenti residui della classe
             - dismissioni della classe
```

### 6.3 Stato patrimoniale parziale ignorato o sostituito

In presenza di un riferimento annuale, alcune voci patrimoniali vengono riprese dal
riferimento invece che dal saldo parziale corrente. Movimenti YTD di capitale,
riserve, TFR, debiti e crediti possono andare persi. L'utile precedente viene
implicitamente portato a riserva senza una delibera/movimento esplicito.

### 6.4 Cassa e debito usati come plug previsionali

La cassa chiude il bilancio; se diventa negativa, la differenza viene trasformata in
debito bancario. In assenza di breakdown il debito viene inventato con proporzione
40% finanziario / 60% operativo. Questo rende il forecast formalmente quadrato ma
altera indebitamento finanziario, DSO/DPO e cash sweep.

Un fabbisogno non coperto deve rimanere una voce diagnostica o richiedere una scelta
di finanziamento nello scenario; non può diventare automaticamente banca.

## 7. Stato corretto da rappresentare

Ogni import deve esporre separatamente almeno:

- `arithmetic_balanced`: Attivo = Passivo;
- `hierarchy_consistent`: aggregati = dettagli;
- `income_result_consistent`: risultato CE = risultato esplicito = `sp13`;
- `source_coverage`: percentuale/importo delle righe spiegate;
- `estimated`: presenza e ammontare di classificazioni stimate;
- `review_required`: conflitti o soglie materiali;
- `forecastable`: utilizzabile o meno dal motore infrannuale/previsionale.

Un solo booleano `quadra` non è sufficiente. Nessuna validazione deve modificare i
dati che sta validando.

## 8. Conclusione

Il 337 dimostra due famiglie di errore — ricostruzione dei token e compensazione
contabile — ma il corpus mostra che la seconda famiglia attraversa tutte le route.
La priorità non è aggiungere una regola speciale al 337: è separare fatti,
classificazione, costruzione, validazione e decisione di accettazione, usando una
sola algebra contabile e conservando la provenienza fino al DB.

Il piano di modifica è in `10-PIANO-CORREZIONI-PIPELINE-IV-CEE.md`; la strategia di
verifica senza nuove API è in `11-PIANO-VALIDAZIONE-CORPUS.md`.
