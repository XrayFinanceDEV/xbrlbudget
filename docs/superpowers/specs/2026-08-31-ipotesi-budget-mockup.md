# Riprogettazione delle ipotesi budget — i tre mockup

**Data:** 2026-08-31 · **Stato:** **outstanding**, nessun design approvato
**Origine:** review del tester del 31/08. Stavano in `inbox/`, che è gitignorata;
spostati qui il 2026-09-01 su richiesta del proprietario perché sopravvivessero a una
pulizia della cartella.

> Questo file **non è una spec**. È l'indice di tre immagini, più ciò che si vede
> guardandole. Le decisioni non sono state prese: le quattro spec della review
> (`2026-08-31-review-tester-0*`) dichiarano tutte, in fondo, «Non tocca le ipotesi del
> budget: **outstanding** per decisione del 31/08».

## I tre mockup

| File | Che cosa mostra |
|---|---|
| [01 — divisione costi](2026-08-31-ipotesi-budget-mockup-01-divisione-costi.png) | La tab «Variabili economiche» del percorso **da bilancio** |
| [02 — startup, testa](2026-08-31-ipotesi-budget-mockup-02-startup-testa.png) | La stessa tab nel percorso **startup**, dall'alto |
| [03 — startup, variazioni](2026-08-31-ipotesi-budget-mockup-03-startup-variazioni.png) | Il seguito della 02: la tabella delle variazioni |

## Che cosa si vede

**Tre tab al posto di una lista sola:** «Informazioni scenario» · «Variabili economiche»
· «Variabili patrimoniali». Oggi le ipotesi sono un elenco unico con un accordion
«Avanzate» (`ESSENTIAL_ROWS` / `ADVANCED_GROUPS` in
`frontend/components/budget/assumption-rows.ts`).

**Passo «Composizione dei costi al {anno base}»**, con la domanda scritta per esteso —
*«Quanta parte di queste due voci resta costante al variare del fatturato?»*. Per
materie prime e costi per servizi: uno **slider** con la percentuale fissa, e sotto una
barra che mostra i due importi in euro aggiornati (`Fissa · 97.129 €` /
`Variabile · 64.753 €`). Nel mockup 02 lo slider a 0% lascia la sola barra variabile.

**Passo «Variazioni % rispetto al {anno base}»**: una tabella per anno, con le righe
raggruppate in **Ricavi · Costi variabili · Costi fissi**, e la quota fissa e quella
variabile di ogni voce di costo come **righe separate**, ciascuna con la propria
percentuale per anno. Legenda a due colori, `quota fissa · quota variabile`. Nel
mockup 03 la riga «Materie prime — parte fissa» è **spenta** perché lo slider ha messo
la quota fissa a 0%.

**Solo nel percorso startup** (mockup 02), un passo «Dati di base» in testa: capitale
sociale, numero dipendenti, e l'orizzonte come scelta a due bottoni (3 anni / 5 anni).

## Quello che il codice già regge

I campi per la divisione costi **esistono già**, quindi i mockup riorganizzano come si
chiedono le stesse cose, non introducono un modello nuovo:

- `fixed_materials_percentage` e `fixed_services_percentage`
  (`backend/app/schemas/budget.py:151-152`, default **40**) — sono lo slider;
- `variable_materials_growth_pct` / `fixed_materials_growth_pct` e i due gemelli per i
  servizi (`:107-109`) — sono le righe separate della tabella;
- in UI oggi sono quattro righe percentuali piatte dentro l'accordion
  (`assumption-rows.ts:71-80`), senza importi in euro accanto e senza raggruppamento.

**Da verificare quando il lavoro verrà preso**, perché dalle immagini non si deduce: la
divisione in «Variabili economiche / patrimoniali», dove finiscono le righe che oggi
stanno in `ADVANCED_GROUPS`, e se «numero dipendenti» esista già nel form startup o sia
un campo nuovo.

## Prima di partire

Serve un `/brainstorming` e una spec vera. Tre immagini non dicono che cosa succede a
uno scenario già salvato con i valori di oggi, né se lo slider scriva un `_override` o
una percentuale — e la regola di CLAUDE.md sugli override («un override vince sulla
percentuale di crescita e sopravvive al salvataggio») è esattamente il punto su cui una
UI nuova può mentire senza dare errore.
