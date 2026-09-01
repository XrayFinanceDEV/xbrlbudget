# Review tester — Lotto 3: contenuto analitico

**Data:** 2026-08-31
**Stato:** Design approvato
**Area:** frontend. `app/pratica/page.tsx`, `lib/pratica-indicators.ts`,
`components/pratica/IndicatoriCharts.tsx`, `app/report/page.tsx`,
`components/report/report-types.ts`. **Nessuna modifica a DB, motori o endpoint.**
**Origine:** `inbox/eccezioni1.md`.
**Serie:** 03 di 04. Da eseguire **dopo** la 02.

## Problema

Quattro richieste additive: il tester vuole più numeri in evidenza, più grafici, e il
prospetto previsionale non in fondo al report. Nessuna richiede logica nuova — tranne **un
indicatore che non abbiamo**.

### 3.1 Highlights del Confronto: quattro card su quattro possibili

`app/pratica/page.tsx:1518-1521` rende quattro card da quattro codici scritti a mano:
`ce01_ricavi_vendite`, `ce08_costi_personale`, `ce05_materie_prime`, `ce06_servizi`.

Il tester ne vuole altre quattro: **EBITDA, EBITDA margin, % materie/ricavi, % servizi/ricavi**.

L'EBITDA è già disponibile: `buildIncomeItemsWithEbitda` costruisce una riga sintetica
`_ebitda` con valore parziale, di riferimento e annualizzato
(`lib/pratica-statement-rows.ts:324`), ed è già passata alla tabella di confronto sottostante.
Le tre percentuali sono rapporti fra righe già presenti.

### 3.2 Indicatori: due grafici su quattordici indicatori calcolati

`components/pratica/IndicatoriCharts.tsx` rende due grafici — incidenza economica (EBITDA
margin, materie, servizi sui ricavi) ed equilibrio finanziario (MT, MS, PFN).

Il tester ne chiede altri sei: **CCN, DSCR, ROI, oneri finanziari su fatturato, PFN/EBITDA,
ROE**. Cinque su sei **esistono già** in `IndicatorSet` (`lib/pratica-indicators.ts:5-26`):
`ccn`, `dscr`, `roi`, `pfn_ebitda`, `roe`. Sono già calcolati, già tabellati, già scorati.

**Il sesto no.** «Oneri finanziari su fatturato» non esiste: abbiamo `of_mol`, che è oneri
finanziari **su MOL** (`:154`). Sono due domande diverse — quanto pesano gli oneri sul giro
d'affari, contro quanto pesano sulla capacità di generare cassa — e la seconda è quella che il
punteggio usa. Va **aggiunta** la prima, non sostituita la seconda.

### 3.3 Stampa infrannuale

Il tester chiede i grafici anche nell'output stampato. Non serve lavoro dedicato: la Stampa
rende **lo stesso componente** della tab (`components/pratica/StampaContent.tsx:659`), quindi
eredita quello che si aggiunge. È però quello che cambia l'impaginazione (§Trappole).

### 3.4 Report: il previsionale è in fondo

`app/report/page.tsx:252-258`: le appendici — SP e CE completi — sono gli ultimi blocchi prima
delle note metodologiche. Il tester le vuole a **pagina 2, 3 e 4**, con il rendiconto.
Parole sue: «è scomodo leggerli ora che sono in fondo».

## Decisioni prese

| # | Decisione | Perché |
|---|---|---|
| D1 | Highlights da 4 a **8**, su **due righe** da quattro | Una riga da otto rende ogni card illeggibile sotto i 1400px, e in stampa va fuori misura |
| D2 | Grafici da 2 a **6**, griglia **2×3**, e la Stampa li rende **tutti** | È lo stesso componente, e il senso della richiesta è proprio l'output stampato |
| D3 | Si **aggiunge** `of_revenue` (oneri finanziari / ricavi) e si **tiene** `of_mol` | Due domande diverse; `of_mol` è quella usata dal punteggio |
| D4 | Nel report CE, SP e Rendiconto salgono a pagina 2-3-4, **e il TOC segue** | Il sommario è generato dall'ordine: se non lo si sposta insieme, punta a pagine sbagliate |

## Interventi

### I1 — Otto highlights

`app/pratica/page.tsx:1517-1560`.

Le quattro card nuove non sono dello stesso tipo delle attuali, e **la differenza è
sostanziale**. Le card odierne confrontano `pct_of_reference` contro
`expectedPct = period_months / 12 × 100` (`:1523-1524`): il verde/rosso dice «questa voce sta
correndo più o meno di quanto ci si aspetti a questo punto dell'anno». Ha senso solo per una
**grandezza di flusso**.

Su un **rapporto** — EBITDA margin, % materie/ricavi, % servizi/ricavi — quel confronto è privo
di significato: un margine non matura pro-quota, e mostrarlo al 75% dopo 9 mesi direbbe il
falso. Le tre card percentuali vanno confrontate **direttamente col rapporto dell'anno di
riferimento** (margine parziale vs margine storico), non con la frazione d'anno.

Conseguenze:
- serve un secondo tipo di card, o un parametro che distingua **flusso** e **rapporto**;
- per le card di rapporto, il verde/rosso indica «migliore/peggiore del riferimento», e il segno
  va invertito sulle due di costo (materie e servizi più leggere sui ricavi sono un
  miglioramento, non un peggioramento);
- l'EBITDA in euro resta una card di flusso, come le quattro attuali.

Con `has_reference === false` (annualizzazione pura, nessun anno storico) le card di rapporto
non hanno termine di paragone: mostrano il valore senza freccia, come già fanno le altre
(`:1550-1553`).

Layout: `grid-cols-2 md:grid-cols-4` invariato — otto card riempiono due righe da sole.

### I2 — `of_revenue`

`lib/pratica-indicators.ts`. **Quattro punti, tutti obbligatori:**

1. il campo in `IndicatorSet` (`:5-26`);
2. il calcolo in `computeIndicators` (`:140-160`): `safeDivide(oneriFinanziari, revenue) * 100`,
   accanto a `of_mol` (`:154`);
3. **un `case` in `scoreIndicator`** — vedi Trappole: senza, il punteggio è 0,5 e nessuno se ne
   accorge;
4. la riga in `INDICATOR_DEFS` (`:219`), che alimenta sia la tabella
   (`components/pratica/IndicatoriTable.tsx:82-85`, `:175`) sia i punteggi.

Soglie proposte per il punteggio, coerenti con la pratica bancaria italiana già usata per
`of_mol`: `invertedScore(of_revenue, 1, 5)` — sotto l'1% dei ricavi è ottimo, sopra il 5%
critico. Da rivedere col proprietario se diverge dalle tabelle FGPMI.

### I3 — Sei grafici

`components/pratica/IndicatoriCharts.tsx`.

I due grafici attuali restano come sono. Se ne aggiungono quattro, ciascuno con la sua
`ChartConfig` e la sua unità:

| grafico | serie | unità |
|---|---|---|
| Redditività | ROI, ROE | % |
| Sostenibilità del debito | PFN/EBITDA, DSCR | volte |
| Peso degli oneri finanziari | OF/fatturato, OF/MOL | % |
| Capitale circolante | CCN | € |

Non mescolare unità dentro un grafico: CCN in euro accanto a un ROI in percentuale rende
illeggibili entrambi. È il motivo per cui i due grafici esistenti sono divisi esattamente così.

`buildIndicatorChartData` (`:263`) non va toccato: appiattisce già **tutto** l'`IndicatorSet`,
quindi i campi nuovi arrivano da soli. Va ricordata la regola che implementa: **una serie
assente viene scartata, non resa a zero** — una barra a zero sarebbe indistinguibile da
un'azienda con EBITDA nullo.

Griglia: `xl:grid-cols-2` per lo schermo. Per la stampa vedi Trappole.

### I4 — Ordine del report

Due file, **in un solo commit**:

1. `components/report/report-types.ts:9-21` — `REPORT_SECTIONS`, unica fonte del sommario
   (`components/report/report-toc.tsx` la itera).
2. `app/report/page.tsx:196-259` — l'ordine dei blocchi, oggi scritto a mano.

Nuovo ordine: copertina → **appendici SP** → **appendici CE** → **rendiconto** → dashboard →
composizione → margini → struttura → indici → scoring → break-even → note.

Da sistemare insieme:
- `print:break-before-page` sta oggi sul blocco appendici (`:252`) e sul blocco note (`:258`):
  vanno rimessi dove servono nel nuovo ordine, cioè sulla prima appendice e sulle note;
- `REPORT_SECTIONS` ha **un solo** id `appendices` mentre la pagina rende **due** blocchi
  (`section="bs"` e `section="is"`): con le appendici in testa la voce di sommario va sdoppiata,
  o l'ancora punta solo alla prima delle due;
- il commento AI complessivo resta attaccato alla copertina, non alle appendici.

## Trappole

- **`scoreIndicator` ha `default: return 0.5`** (`lib/pratica-indicators.ts:216`). Un indicatore
  aggiunto a `INDICATOR_DEFS` senza il proprio `case` prende **punteggio neutro su ogni
  azienda**, senza errore e senza test rosso: pallino giallo per tutti, per sempre. È la ragione
  per cui I2 elenca quattro punti e non tre.
- **`lib/pratica-indicators.test.ts:76-84` enumera tutte le chiavi dell'`IndicatorSet`.** È un
  elenco deliberato, non un residuo: `of_revenue` va aggiunto lì **nello stesso commit** che lo
  introduce. Vale la regola di CLAUDE.md sugli elenchi congelati — si aggiornano solo per una
  riga aggiunta di proposito, mai per far tornare verde la suite.
- **Sei grafici cambiano l'impaginazione della Stampa.** Oggi `print:grid-cols-2` e
  `print:h-[170px]` (`IndicatoriCharts.tsx:57`, `:66`) sono tarati su **due** grafici, con un
  commento che spiega perché: un A4 sta sotto il breakpoint `xl`, e senza quella regola i
  grafici si impilano spingendo la tabella degli indicatori a pagina nuova. Con sei grafici la
  taratura va rifatta, e **si verifica generando il PDF** — `emulateMedia` non impagina.
- **Non sostituire una somma scritta a mano con `aggregate()`** nei grafici o nei prospetti
  stampati: sul `BalanceSheet` che arriva da `/analysis` restituisce 0 su `sp04`, `sp06` e
  `sp07`, in silenzio (CLAUDE.md, «Frontend»).

## Verifica

| # | Che cosa | Come si prova |
|---|---|---|
| V1 | Le card di rapporto non mentono | Su un 9M con margine storico noto: la card EBITDA margin confronta margine con margine, **non** col 75% dell'anno. Le due card di costo mostrano verde quando l'incidenza **scende** |
| V2 | Senza anno di riferimento | `has_reference === false`: le otto card compaiono, quelle di rapporto senza freccia |
| V3 | `of_revenue` è scorato davvero | Il pallino cambia colore fra un'azienda con oneri all'1% dei ricavi e una al 6%. Un pallino sempre giallo = manca il `case` |
| V4 | I sei grafici a schermo | Griglia 2×3, unità non mescolate, serie assenti scartate e non a zero |
| V5 | I sei grafici in stampa | **PDF generato**: nessun grafico spezzato, la tabella indicatori non finisce da sola su una pagina |
| V6 | Il report è riordinato e il sommario lo segue | **PDF generato**: SP, CE e rendiconto sono le pagine 2-3-4; ogni voce del sommario porta alla propria sezione |
| V7 | Nessuna regressione | `cd frontend && npm test` verde, `lib/pratica-indicators.test.ts` compreso |

## Che cosa questo lotto NON fa

- Non tocca il calcolo degli indicatori esistenti: `of_mol` resta esattamente com'è.
- Non tocca le soglie FGPMI né `data/rating_tables.json`.
- Non rifà la home (spec 04) né le ipotesi budget (**outstanding**).
