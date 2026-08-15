# Indicatori: i due grafici, condivisi fra la tab e la Stampa

## Cosa rende chi

Due grafici a barre riassumono la sezione Indicatori:

| Grafico | Serie | Asse |
|---|---|---|
| **Incidenza economica sui ricavi** | `ebitda_margin`, `materials_revenue`, `services_revenue` | percentuale |
| **Equilibrio finanziario e strutturale** | `mt` (margine di tesoreria), `ms` (margine di struttura), `pfn` | euro, notazione compatta |

Li rendono **due viste**: la tab *Indicatori* di `/pratica` e la tab *Stampa* (che è il PDF).
In Stampa stanno fra le card di rating e la tabella dei 14 indicatori: prima il quadro
d'insieme, poi il dettaglio riga per riga.

## Un componente, non una copia

`components/pratica/IndicatoriCharts.tsx` contiene i due `<Card>`, le due `ChartConfig` e la
griglia. Lo rendono entrambe le viste, e sono i due soli consumatori:
`components/pratica/IndicatoriTable.tsx:154` e `components/pratica/StampaContent.tsx:659`.

Le configurazioni dei grafici sono lo stesso oggetto per le due viste: duplicarle avrebbe
creato una seconda definizione della stessa cosa, cioè il difetto che il catalogo IV-CEE ha
appena finito di eliminare per le etichette (vedi `frontend/lib/ivcee-catalog.ts`).

Le **etichette delle serie** restano invece di chi chiama, perché divergono davvero:

| Vista | Etichetta della colonna infrannuale |
|---|---|
| tab Indicatori | `Infrann. 9M` |
| Stampa | `Infrann. 9M 2026` |

Il componente riceve le serie già nominate:

```ts
const serieGrafici: SerieIndicatori[] = [
  { periodo: `Storico ${refYear}`, indicatori: storicoInd },
  { periodo: `Infrann. ${periodMonths}M ${partialYear}`, indicatori: infraInd },
  { periodo: `Proiezione ${partialYear}`,
    indicatori: periodMonths === 12 ? null : proiezioneInd },
];
```

## `buildIndicatorChartData`

Vive in `lib/pratica-indicators.ts`, non dentro il componente, perché è **l'unica parte
verificabile dai test**: la suite di questo progetto gira con `environment: "node"` e non ha
DOM (`frontend/vitest.config.ts`), quindi il componente si verifica nel browser e la logica
qui (`lib/pratica-chart-series.test.ts`).

Regola non ovvia: **una serie assente viene scartata, non resa a zero.** Una barra a zero
sarebbe indistinguibile da un'azienda con EBITDA nullo. `indicatori: null` significa "questo
periodo non esiste" — bilancio già annuale (`periodMonths === 12`), o previsionale non ancora
generato.

## La stampa

Un A4 è ~794px, **sotto** il breakpoint `xl` (1280px). Senza regole di stampa i due grafici
si impilerebbero e spingerebbero la tabella degli indicatori a pagina nuova. Sono utilità
Tailwind sul componente, non regole in `globals.css`:

```
grid-cols-1 xl:grid-cols-2 print:grid-cols-2 print:gap-2
h-[260px] w-full print:h-[170px]
```

Misurato a viewport 794px:

| | colonne | altezza |
|---|---|---|
| schermo | `731px` (una sola) | 260px |
| stampa | `369px 369px` | 170px |

### `print:break-inside-avoid` sulle Card

`globals.css` ha già `.recharts-wrapper { break-inside: avoid }`, che protegge **il grafico**
ma non la `Card` che lo contiene. Senza il `print:break-inside-avoid` sulle card, il titolo
resta orfano in fondo a una pagina e il grafico apre la successiva — difetto trovato
generando il PDF, invisibile a ogni controllo sul DOM.

> Verificare una resa di stampa richiede di **produrre il PDF**. L'emulazione
> `emulateMedia({ media: "print" })` dà le misure giuste ma non impagina, quindi non mostra
> mai un salto di pagina sbagliato.

## Limite noto: il denominatore dei rapporti percentuali

`computeIndicators` usa `revenue = ce01_ricavi_vendite` **da solo** come denominatore di
`ebitda_margin`, `materials_revenue`, `services_revenue` e `ros`.

Un'azienda che fattura su `ce04_altri_ricavi` porta un `ce01` prossimo a zero e produce
percentuali prive di senso: su AIC SRL (2025: `ce01` = 100,92 €) l'`EBITDA %` risulta
80.395,7% e l'asse del grafico arriva a 600.000%, schiacciando le altre due colonne a
scaglie invisibili. Il grafico resta corretto rispetto ai dati; sono i dati a essere
inutilizzabili.

È lo **stesso difetto** corretto in `intra_year_engine` per i rapporti di rotazione (vedi
`docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5). Qui **non** è stato corretto: cambiare il
denominatore sposta i valori degli indicatori, quindi i punteggi, quindi il rating di crisi,
per **ogni** azienda — una decisione più grande dell'aggiunta di un grafico.
