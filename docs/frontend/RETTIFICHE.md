# Rettifiche — il giornale delle correzioni sul bilancio importato

> Le regole che, violate, corrompono un dato **senza che nessun controllo se ne accorga** stanno
> in `CLAUDE.md` § «Invarianti e trappole». Qui c'è come funziona.

Un bilancio importato da PDF è quasi sempre **leggibile ma imperfetto**: un conto finito nella
voce sbagliata, una scadenza non dichiarata, un aggregato che non si spacchetta. Il progetto ha
scelto di non rifiutare quei file — un import rifiutato è un file incorreggibile per sempre — ma
di salvarli e di dare all'utente il posto dove sistemarli. Quel posto sono le Rettifiche.

Sono lo step **DATI › Rettifiche** del percorso Pratica, fra Import e Confronto. Nulla a valle
(Confronto, Proiezione, Indicatori, Stampa) è raggiungibile finché non sono confermate.

## 1. Che cos'è una rettifica

Una riga del **giornale**: un campo di SP o CE cambia valore, e la variazione viene registrata
con la sua contropartita e la sua spiegazione. Il giornale è persistito insieme al bilancio, così
riaprendo la pratica si vede non solo il numero corretto ma **perché** è quello.

Due proprietà che vale la pena tenere a mente:

- Le Rettifiche lavorano su un `FinancialYear` **già persistito**. È il motivo per cui l'import
  salva anche ciò che non quadra: se rifiutasse, non ci sarebbe niente da rettificare.
- Il bilancio corrente riflette sempre lo stato **corretto**; l'originale non si perde, vive in
  uno snapshot immutabile (§4).

## 2. Due sotto-tab, una per anno

Un bilancio di verifica arriva quasi sempre col suo anno storico di riferimento (30.06.2026 +
31.12.2025), e **servono rettifiche su entrambi**: lo storico è la base su cui Confronto,
Proiezione e Indicatori calcolano la crescita, quindi una misclassificazione lasciata lì si
propaga ovunque, silenziosamente e con l'aria di essere un andamento.

Lo step contiene quindi un `Tabs` shadcn con *Rettifiche Storico {refYear}* (default) e
*Rettifiche Bil. di verifica {n}M {year}*.

**Non è servito alcun lavoro backend** per aggiungere il secondo anno: `GET
/companies/{id}/years/{year}/adjustable` e `PUT .../adjustments` prendevano già `year` più un
`period_months` opzionale (`_find_fy`), e l'importer persisteva già l'anno precedente di un PDF a
due colonne come `period_months=None`. Lo step di Importazione garantisce che l'anno di
riferimento esista (`handleImportRefYear`) o che sia stato esplicitamente saltato
(`handleSkipRefYear`).

Come è costruito:

- **`frontend/hooks/use-rettifiche-year.ts`** tiene load / save / reset / corrections per **UN**
  `FinancialYear`. La pagina lo istanzia **due volte**: `storico` (`fiscalYear - 1`,
  `periodMonths` **`undefined`** = anno intero) e `verifica` (`fiscalYear`, `periodMonths < 12 ?
  periodMonths : undefined`).
- **`RettificheTab` è immutato e reso due volte.** È prop-driven: `hasRef` nasconde la colonna di
  riferimento quando `referenceYearData` è `null`, e `periodEndDate` deriva 31/12/{refYear} da
  `(year, 12)`.
- **`referenceYearData`** — la colonna Storico in sola lettura dentro la tab Bil. di verifica — è
  un `useMemo` su `storico.data`, **non** una fetch propria. Per questo una correzione su una tab
  muove subito la colonna sull'altra.
- **Senza anno storico** (import saltato → modalità di pura annualizzazione): il trigger Storico è
  disabilitato con una card esplicativa e la sotto-tab parte da Bil. di verifica. Un 404 mette
  `exists = false` — è uno stato legittimo, non un errore.

Spec e piano: `docs/superpowers/specs/2026-08-07-rettifiche-storico-design.md`,
`docs/superpowers/plans/2026-08-07-rettifiche-storico.md`.

## 3. I tre modi di proposta

Scrivere un valore nuovo in un input aggiorna una mappa locale `pendingEdits`. Su blur / Invio si
apre il **dialogo di proposta**, che offre tre modi — non uno solo:

| Modo | Che cos'è | Contropartita |
|---|---|---|
| **Rettifica** (default) | partita doppia a cavallo dei lati: SP↔CE, oppure Attivo↔Passivo. Tocca il risultato | obbligatoria, filtrata alle categorie dell'altro lato |
| **Riclassifica** | partita doppia **dentro** lo stesso lato: SP→SP, CE→CE. Non tocca il risultato | obbligatoria, filtrata alla stessa categoria |
| **Correggi Import** | correzione a **partita singola**: il dato importato era semplicemente sbagliato | nessuna |

Il modo si sceglie nel dialogo (`ProposalMode = "rettifica" | "riclassifica" | "correggi_import"`,
`lib/pratica-rettifiche-rules.ts`); cambiarlo azzera la contropartita già scelta.

### La contropartita proposta

`PROPOSAL_RULES` associa a ogni campo modificabile una contropartita di default con la sua
direzione (`same` / `inverse`) e una spiegazione in italiano — e, quando serve, una **variante per
delta negativo** (`counterpartNeg`, `directionNeg`, `explanationNeg`): far *scendere* un credito
non è simmetrico a farlo salire, è una svalutazione, non un minor ricavo. Alcune regole offrono
anche uno `splitAlt`, una seconda destinazione fra cui ripartire l'importo.

### Come è filtrato il menu della contropartita

Per **categoria** (`ATTIVO`, `PASSIVO`, `CE_POS`, `CE_NEG`) e per **modo**. Non per segno:
`allowedCounterpartCategories(editedField, _delta, mode)` riceve il delta ma **non lo legge** — il
parametro è prefissato da underscore proprio per dirlo.

- **rettifica**: un campo `ATTIVO` offre `PASSIVO` + entrambe le categorie di CE; un `PASSIVO`
  offre `ATTIVO` + entrambe le categorie di CE; un campo di CE offre `ATTIVO` + `PASSIVO`.
- **riclassifica**: solo lo stesso lato — `ATTIVO`↔`ATTIVO`, `PASSIVO`↔`PASSIVO`, CE↔CE (fra
  ricavi e costi indifferentemente).

Il **segno** della contropartita non è una scelta dell'utente: lo calcola `computeCpDelta` dalla
regola contabile `A − L − C − R − Rev + Cost = 0` — stesso gruppo di coefficiente
(`{ATTIVO, CE_NEG}` contro `{PASSIVO, CE_POS}`) ⇒ delta opposto, gruppi diversi ⇒ delta uguale.
È deliberato: l'utente sceglie **dove**, il sistema garantisce che la scrittura resti bilanciata.

> ⚠️ Una versione precedente di `CLAUDE.md` diceva che il menu era filtrato «in base al campo
> modificato **e al segno**», con l'esempio «Debito↑ mostra solo Costi/Oneri + Attivo». È falso in
> entrambe le metà: il segno non filtra, e un campo di passivo offre **anche** i ricavi.

### Che cosa non può essere una contropartita

I campi **aggregati o calcolati** — `sp04`, `sp05`, `sp06`, `sp07`, `sp12`, `sp13`, `sp16`,
`sp17`, `ce08`, `ce09`, `ce17` — sono esclusi via `NON_POSTABLE_FIELDS`, perché `recalcAggregates`
li ricostruisce dai sotto-campi (e `sp13` dal CE) subito dopo: un delta scritto lì sparirebbe
**senza errore**. È un invariante, non una preferenza.

### «Correggi Import», e la trappola del gap

La correzione a partita singola si apre pre-compilata con lo **scarto esatto** di quadratura:
l'importo è un dato, non una scelta, e il dialogo lo mostra come testo. Le due destinazioni di
default sono `sp09_disponibilita_liquide` se eccede l'attivo, `sp16g_altri_debiti_breve` se eccede
il passivo — coerenti con la regola di progetto per cui la massa non attribuita va in un
sotto-campo esplicito, mai su un aggregato.

Il gap è calcolato sullo stato che esisterà **dopo** la conferma, non su quello reso a schermo.
Il motivo: `confirmActiveEdit` chiama sempre `recalcAggregates`, che sovrascrive
`sp13_utile_perdita` col valore derivato dal CE. Su un bilancio con CE e SP scollegati — proprio
quello che l'import oggi salva invece di rifiutare — il gap di rendering **non** è quello che
resterà, e correggerlo lascerebbe un residuo pari a `sp13_importato − sp13_CE`.

In giornale l'entrata resta riconoscibile: `counterpart_field = "_correzione_import"`, delta della
contropartita `0`.

## 4. Persistenza, tetto, riconciliazione, ripristino

**Snapshot.** `FinancialYear.original_bs_snapshot` + `original_is_snapshot` (JSON pre-rettifiche)
e `FinancialYear.rettifiche_log` (array JSON delle voci). Lo snapshot nasce alla **prima GET** su
`/adjustable` — e, se ancora mancasse, anche alla prima `PUT /adjustments`. Quindi `BalanceSheet`
e `IncomeStatement` riflettono sempre lo stato **corretto**, mentre `original_*_snapshot` resta
immutabile.

**Idratazione.** Al mount, `corrections` è seminata da `adjustableData.balance_sheet` /
`income_statement` (post-rettifiche) e `log` da `adjustableData.rettifiche_log`: riaprendo la tab
si rivede il giornale persistito.

**Tetto di 20 voci** (`RETTIFICHE_MAX`), applicato **su entrambi i lati**: client (toast e blocco
prima di salvare) e server (400 su `/adjustments`). Su entrambi i lati i marker di conferma
(`entry_type == "confirm"`) sono **esclusi dal conteggio** — sono contabilità interna, non
rettifiche.

**Il pannello del giornale** elenca ogni voce confermata con una cancellazione per riga, che
ripristina entrambi i delta, filtra il log e persiste. Il **dialogo Riepilogo Rettifiche** mostra
in più le righe **aggregate** toccate indirettamente da `recalcAggregates` — cioè i campi di
`NON_POSTABLE_FIELDS` — in grigio spento e corsivo, con un tooltip che spiega che sono totali
derivati: senza quel segnale l'utente le leggerebbe come scritture duplicate.

**Guardia anti-regressione del server.** `PUT /adjustments` fonde il payload sul record corrente e
misura tre grandezze prima e dopo: sbilancio Attivo−Passivo, scarto CE−`sp13`, scarto
aggregati−dettagli. Rifiuta con 400 solo ciò che **peggiora** una delle tre. È **relativa per
scelta**: un foglio già sbilanciato all'import deve restare lavorabile, ed è esattamente il file
per cui le Rettifiche esistono. Renderla assoluta lo renderebbe incorreggibile per sempre.

**Auto-riconciliazione al load** (`reconcileSubfields`, `lib/pratica-reconcile.ts`). Fa due cose
diverse, ed è importante non confonderle:

1. **Nove riconciliazioni aggregato → dettaglio**, `sp04`, `sp05`, `sp06`, `sp07`, `sp12`, `sp16`,
   `sp17`, `ce08`, `ce09`: se l'aggregato importato non è la somma dei suoi sotto-campi, il
   divario finisce nel secchio designato (`sp04a`, `sp05e`, `sp06g`, `sp07g`, `sp12e`, `sp16g`,
   `sp17g`, `ce08b`, `ce09c`). **Senza alcun tetto di importo**: serve a rendere lavorabile un
   bilancio abbreviato, che dichiara solo gli aggregati.
2. **Uno sbilancio Attivo/Passivo ≤ 5 €** da arrotondamento d'import, tappato in
   `sp09_disponibilita_liquide`. Questo sì è cappato, e una sola volta: le rettifiche successive
   sono in partita doppia, quindi il pareggio si conserva da sé.

**Ripristino** (`onReset`): rimanda lo snapshot come BS/IS più un log vuoto, cancellando
correzioni e giornale. Deve **riconciliare una copia** dello snapshot prima di inviarlo, per la
ragione spiegata nella sezione invarianti di `CLAUDE.md`.

## 5. Che cosa invalida a valle

Un salvataggio o un ripristino su **uno qualsiasi dei due anni** azzera `comparison`,
`projectedBS` e `analysis`. Nulla viene ricalcolato in silenzio: l'utente ripassa da Confronto →
Proiezione. Il toast *«Bilancio modificato — ricalcola la proiezione»* compare **solo** se una
proiezione esisteva davvero.

Quel test legge un **ref** (`projectedBSRef.current`), mai un updater di `setState`:
`reactStrictMode` invoca gli updater due volte in sviluppo, quindi un toast dentro un updater
sparerebbe doppio.

## 6. Etichette, rientro, intestazioni

Ogni riga rende `labelOf(field)` — la grafia **autonoma** del catalogo IV-CEE
(`lib/ivcee-catalog.ts`), non quella contestuale. Sulle sotto-righe dei debiti si legge quindi
`Debiti vs fornitori (entro)` e non `entro 12 mesi`: la forma breve funziona solo sotto
un'intestazione che la spieghi, e nel giornale delle rettifiche quell'intestazione non c'è.

Il **rientro** delle sotto-voci lo dichiara il catalogo (`isDettaglio`), non si deduce dalla
profondità del codice. Non è un dettaglio estetico: sulle 78 righe passate a `renderSection`,
`depthOf(code) > 0` ne selezionerebbe 42 contro le 32 corrette. Le 10 di scarto sono `sp12a..h` e
`ce17a/b` — hanno un padre nel catalogo ma portano già la propria lettera di schema (`A.II)`,
`18)`) e restano a filo. Il confronto è pinnato in `ivcee-catalog-parity.test.ts`.

Le **intestazioni di raggruppamento** dello schema art. 2424 (`B) Immobilizzazioni`, `C) Attivo
circolante`, `A) Patrimonio netto`) sono righe di **resa** dichiarate dentro `RettificheTab.tsx`,
non voci del catalogo: senza codice, non editabili, assenti da `VOCI`. Un'intestazione si stampa
sopra la prima riga **visibile** del proprio gruppo, così un gruppo interamente filtrato non lascia
un'intestazione orfana.

L'ordine di resa è dichiarato una volta sola in `RETTIFICHE_RENDER_SECTIONS` e
`RETTIFICHE_RENDER_ORDER` (`lib/pratica-rettifiche-rules.ts`), consumati dal componente **e** dai
test. Limite noto: questo fissa quali elenchi e in che ordine, non che il JSX li renda in
quell'ordine — il componente interfoglia intestazioni, totali e il blocco debiti fra le chiamate,
quindi una riga persa o aggiunta non sfugge, una sezione spostata nel JSX sì.

## 7. File chiave

| File | Che cosa contiene |
|---|---|
| `frontend/hooks/use-rettifiche-year.ts` | load / save / reset / confirm per UN anno; un'istanza per tab |
| `frontend/components/pratica/RettificheTab.tsx` | il componente, `recalcAggregates`, `openSbilancioCorrection`, il blocco a due tab |
| `frontend/lib/pratica-rettifiche-rules.ts` | la **politica**: `PROPOSAL_RULES`, `NON_POSTABLE_FIELDS`, `fieldCategory`, `computeCpDelta`, `COUNTERPART_GROUPS`, `DEBT_GROUPS`, gli elenchi di righe, `RETTIFICHE_MAX` |
| `frontend/lib/ivcee-catalog.ts` | la **tassonomia**: `labelOf`, `isDettaglio`, `COUNTERPART_OPTIONS` |
| `frontend/lib/pratica-reconcile.ts` | `reconcileSubfields` |
| `frontend/lib/pratica-codes.ts` | `DETAIL_PARENTS` — l'unica costante davvero condivisa con Confronto e Proiezione |
| `backend/app/api/v1/financial_years.py` | `RETTIFICHE_LOG_MAX = 20`, `_countable_log_entries`, GET `/adjustable`, PUT `/adjustments` e la guardia anti-regressione |
| `backend/app/schemas/adjustments.py` | `RettificaEntry`, `AdjustableFinancialYear`, `AdjustmentsUpdate` |
| `database/models.py` | `FinancialYear.rettifiche_log`, `original_bs_snapshot`, `original_is_snapshot` |

**Sulla struttura (2026-08-10).** Una nota precedente parlava di ~15 costanti condivise fra
Rettifiche, Confronto e Proiezione. Verificate una per una, l'unica davvero condivisa era
`DETAIL_PARENTS`, ora in `lib/pratica-codes.ts` e usata da tutti e tre per decidere quando mostrare
una riga di dettaglio. Non è servito alcun modulo ponte.
