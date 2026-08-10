# Catalogo IV-CEE unico per i prospetti SP/CE

Data: 2026-08-10
Branch: `refactor/catalogo-ivcee` (deroga voluta alla convenzione "commit su main":
Jenkins builda da `main`, quindi un branch separato tiene lo staging fuori dal lavoro
finché non è pronto)
Stato: design approvato dall'utente

## Il problema

Sei viste rendono prospetti IV-CEE e ciascuna si riscrive il proprio elenco di righe.
Misurato: **84 codici compaiono in almeno tre dei quattro file principali**
(`lib/pratica-rettifiche-rules.ts` 95 codici, `lib/pratica-statement-rows.ts` 90,
`app/forecast/balance/page.tsx` 62, `app/forecast/income/page.tsx` 64).

`CLAUDE.md` documenta già la conseguenza come procedura obbligata: *"When adding a new
BS/IS sub-field, add rows in all of: [quattro file]"*. Il modo in cui questo fallisce è
silenzioso — chi dimentica un posto non rompe niente, semplicemente quella riga non
compare in una vista.

### La conseguenza peggiore: le etichette divergono

**38 dei 87 codici etichettati sia in Rettifiche sia in Confronto portano un testo
diverso.** Sono due schede consecutive della stessa pratica:

| Codice | Rettifiche | Confronto |
|---|---|---|
| `sp02_immob_immateriali` | `B.I) Immobilizzazioni immateriali` | `I - Immobilizzazioni immateriali` |
| `sp01_crediti_soci` | `A) Crediti verso soci` | `A) Crediti verso soci per versamenti ancora dovuti` |
| `sp08_attivita_finanziarie` | `C.III) Attività finanziarie` | `III - Attività finanziarie che non costituiscono immobilizzazioni` |
| `ce09a_ammort_immateriali` | `a) Ammort. delle immobilizzazioni immateriali` | `a) Ammortamento immobilizzazioni immateriali` |

Non è disordine estetico: è la stessa riga chiamata in due modi nello stesso percorso.

### Un catalogo esiste già, ed è adottato a metà

`lib/ivcee-balance-catalog.ts` (178 righe) definisce `BALANCE_HIERARCHY_GROUPS` e
`BALANCE_STATEMENT_ROWS`, ma copre **solo lo stato patrimoniale** e lo importano **due**
consumatori su sei: `app/forecast/balance/page.tsx` e `components/report/report-appendices.tsx`.

Il conto economico non ha catalogo — però l'elenco righe in
`app/forecast/income/page.tsx:558` è **già scritto nella forma esatta del catalogo**
(`{label, field, isTotal, isSubtotal, indent}`): gli manca solo di essere estratto.

## La scoperta che ha riscritto il design: le etichette hanno un ruolo

Delle 38 divergenze, 14 sono i sotto-conti dei debiti. Rettifiche li chiama
`"D) Debiti vs banche (entro)"`, Confronto `"entro 12 mesi"`.

Sembrava che una delle due dovesse vincere. Non è così: **le due grafie servono contesti
diversi e sono entrambe necessarie.**

`RETTIFICHE_LABELS` è letta in tre posti dove la riga **non ha alcuna intestazione sopra
di sé** che la spieghi:
- `components/pratica/RettificheTab.tsx:249,252` — `editedLabel` e `counterpartLabel` di
  ogni riga del **giornale rettifiche**;
- `lib/pratica-rettifiche-rules.ts:328-335` — il **selettore della contropartita**;
- `components/pratica/RettificheTab.tsx:312-313` — il dialogo di correzione dello sbilancio.

In una tabella, sotto l'intestazione `7) Debiti verso fornitori`, *"entro 12 mesi"* basta.
In una riga di giornale, *"entro 12 mesi +5.000"* non dice quale debito.

La prova che il problema è già stato incontrato: **`COUNTERPART_PICKER_LABELS` esiste solo
per rendere quei 14 codici auto-esplicativi nel selettore.** È una toppa a questo esatto
problema, applicata a un solo consumatore.

Quindi il modello "una etichetta canonica per codice" è **sbagliato**. Ci sono due ruoli:

| Ruolo | Dove serve | `sp16d` |
|---|---|---|
| **autonomo** | giornale, selettore, dialoghi, e ogni riga di Rettifiche | `Debiti vs fornitori (entro)` |
| **contestuale** | riga di tabella sotto un'intestazione che la spiega | `entro 12 mesi` |

## Decisioni prese

**Un catalogo solo, con il massimo dettaglio.** `lib/ivcee-catalog.ts` sostituisce
`lib/ivcee-balance-catalog.ts` e copre SP e CE. Contiene ogni foglia esistente, perché è
il livello che serve a Rettifiche.

**Il catalogo è un albero, e le viste lo proiettano.** Una vista dichiara a che profondità
fermarsi e quali gruppi espandere; il catalogo espone la funzione che, dato un livello,
restituisce le righe con i totali già aggregati. Le viste sintetiche restano sintetiche
esattamente come oggi — la sintesi si ottiene **proiettando** l'albero, non riscrivendo
l'elenco.

La forma esatta di quell'API non va inventata qui: va **ricavata** in fase di piano da ciò
che le sei viste chiedono davvero oggi, prendendo il minimo comune denominatore. Inventarla
in anticipo produrrebbe parametri che nessuno usa — e i due warts trascinati dal
refactoring precedente (`periodMonths` di `buildIncomeItemsWithEbitda`, morto; le locali
`partialRevenue`/`refRevenue`, morte) sono esattamente cosa succede quando si aggiunge un
parametro "che servirà".

**Grafia vincente: quella del Confronto**, per le 24 divergenze non-debito. È già la
grafia del catalogo esistente, delle pagine previsionali, della Stampa e del report:
cambia una vista su sei invece di cinque.

**Per le 14 dei debiti**, il testo del Confronto diventa l'etichetta *contestuale* e quella
auto-esplicativa resta l'*autonoma*. Il giornale non si muove.

**In Rettifiche le sotto-righe dei debiti passano a mostrare l'etichetta autonoma**
(`Debiti vs fornitori (entro)` invece dell'attuale `entro 12 mesi`, oggi stringa fissa in
`RettificheTab.tsx:743,745`). Chi registra deve leggere cosa sta toccando.

## Perimetro

**Dentro** — le sei viste che rendono prospetti IV-CEE:

| Consumatore | Oggi |
|---|---|
| `lib/pratica-rettifiche-rules.ts` → `RettificheTab` | array piatti di codici + `RETTIFICHE_LABELS` (93 voci) |
| `lib/pratica-statement-rows.ts` → Confronto/Proiezione/Stampa | due mappe `relabel` (89 voci) |
| `app/forecast/balance/page.tsx` | usa già `BALANCE_STATEMENT_ROWS` |
| `app/forecast/income/page.tsx` | elenco CE inline a riga 558 |
| `components/report/report-appendices.tsx` | usa già `BALANCE_STATEMENT_ROWS` |
| `components/report/report-composition.tsx` | aggregazioni scritte a mano (`immob = sp02+sp03+sp04+sp01`) |

**Fuori**, con la ragione:

- `app/budget/page.tsx` e `components/budget/assumption-rows.ts` — i loro 56 codici sono
  campi di **ipotesi** (`sp01_growth_pct`, `ce01_override`), non righe di prospetto, e le
  etichette nominano *driver* ("Crescita ricavi %"), non *voci* ("1) Ricavi delle
  vendite"). Vocabolario diverso: unificarlo sarebbe un errore.
- `/forecast/reclassified`, `/cashflow`, `/report`, `/analysis` — **zero** codici IV-CEE:
  consumano dati già riclassificati dal backend.
- Il backend, il modello dati e gli importatori. Nessuna colonna nuova, nessuna migrazione.

## Cosa tiene il catalogo, e cosa no

**Tiene:** codice, padre (l'aggregato in cui rientra), sezione IV-CEE, ordine fra pari,
etichetta autonoma, etichetta contestuale dove serve.

**Non tiene:** formattazione, regole di visibilità, editabilità, colori, totali calcolati.
Il catalogo dice *cosa esiste e come si chiama*; ogni vista decide *come appare*.

Questo confine è ciò che rende il lavoro sicuro: le regole di resa che oggi divergono
legittimamente fra le viste — Rettifiche mostra sempre le sotto-righe anche a zero
(`RettificheTab.tsx:738`, dove `entroNonZero`/`oltreNonZero` sono calcolati e scartati di
proposito), Confronto e le previsionali le nascondono — restano dove sono e non vengono
toccate.

## Cosa sparisce

- `RETTIFICHE_LABELS` (93 voci)
- le due mappe `relabel` di `lib/pratica-statement-rows.ts` (89 voci)
- l'elenco CE inline di `app/forecast/income/page.tsx`
- `COUNTERPART_PICKER_LABELS` — esisteva solo come toppa al problema dei ruoli, e diventa
  superflua quando i ruoli sono espliciti
- le aggregazioni a mano di `components/report/report-composition.tsx`
- la catena di ternari in `ivcee-balance-catalog.ts:161-168`, che ricostruisce i nomi dei
  campi da un suffisso quando `BALANCE_HIERARCHY_GROUPS[6]`/`[7]` già li contengono

## Verifica

**Il criterio di accettazione è meccanico: per ciascuna delle sei viste, l'elenco dei
codici resi e il loro ordine devono essere identici prima e dopo.** Catturato come test,
**una vista per volta** — l'adozione procede in sei passi indipendenti, ciascuno con il
proprio confronto prima/dopo, così una riga persa si manifesta nel passo che l'ha persa.

Sul catalogo, essendo dati puri, si scrivono test **veri**, non di caratterizzazione:

- ogni codice presente in `BalanceSheet`/`IncomeStatement` ha una voce nel catalogo;
- nessun `parent` punta a un codice inesistente;
- l'ordine è totale (nessun pari con lo stesso indice sotto lo stesso padre);
- ogni codice usato dalle sei viste esiste nel catalogo;
- ogni voce ha un'etichetta autonoma non vuota;
- l'etichetta contestuale, dove presente, è diversa dall'autonoma (altrimenti è rumore).

Più il livello di verifica del lavoro precedente: `npx tsc --noEmit`, `npm test`,
`npm run build`.

**Nota onesta sulla rete esistente:** le tre suite di caratterizzazione scritte nel
refactoring del 2026-08-10 hanno una mutation coverage misurata del 18% complessivo e
3/29 sul modulo indicatori (vedi `CLAUDE.md`). Non vanno considerate una protezione per
questo lavoro. La protezione qui è il confronto prima/dopo degli elenchi di codici, che è
diretto e non deducibile.

## Rischi

**Perdere una riga in una vista durante il passaggio.** È il rischio dominante e la
ragione dell'adozione una-vista-per-volta con confronto prima/dopo. Un'adozione in blocco
renderebbe impossibile attribuire una riga mancante al passo che l'ha causata.

**Applicare l'etichetta contestuale dove serve quella autonoma.** Produrrebbe un giornale
rettifiche illeggibile — righe "entro 12 mesi" senza indicazione del debito. Mitigazione:
l'etichetta contestuale è **opzionale** nel tipo, e il chiamante deve chiederla
esplicitamente; il default è l'autonoma.

**Il catalogo diventa un file grande e centrale.** Mitigazione: contiene solo dati, è
coperto da test propri, e la separazione fra tabella delle voci e liste di righe derivate
tiene le due responsabilità distinte dentro lo stesso modulo.
