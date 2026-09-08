# Task 12 — `StepCosti`: slider della quota fissa e tabella a due gruppi

**Stato:** fatto. **Branch:** `worktree-agent-a25d66ab2b8080522`, partito da `d0d6d0a`.

## Che cosa esiste ora

| File | Nuovo? | Che cosa |
|---|---|---|
| `frontend/lib/budget-costi-step.ts` | nuovo | tutte le decisioni del passo, modulo puro |
| `frontend/lib/budget-costi-step.test.ts` | nuovo | 31 test, `environment: node` |
| `frontend/components/budget/wizard/steps/StepCosti.tsx` | nuovo | il componente, presentazionale |

**Nessun file preesistente è stato toccato**: `git diff --name-only d0d6d0a` non stampa nulla.

## Il vincolo che ha deciso la forma

«La logica che decide non vive dentro un componente» ha spostato in `lib/` sette funzioni che il
brief mostrava come codice inline dentro `StepCosti.tsx`:

- `fixedShareOf(assumptions, years, field)` → `{ value, uneven }`. Quota del **primo anno previsto**;
  un anno senza valore vale `FIXED_SHARE_DEFAULT = 40`, non zero — e uno zero esplicito **discorda**
  dal default dell'anno che non ce l'ha, quindi accende `uneven`. Con `years` vuoto: default, niente
  discordanza.
- `isSplitForced(assumptions, years, "ce05_override" | "ce06_override")` — basta un anno qualunque.
  Un override **a zero è un override** (`!= null`, non falsy).
- `costiBase(baseInc)` → le quattro voci dell'anno base; senza anno base sono `null`, non `0`.
- `splitBaseAmount(amount, share)` → `{ fixed, variable }`; `null` in ingresso resta `null` in uscita.
- `costiTableRows(base, mat, serv, forced)` → le righe del brief, con `off` e `baseLabel`.
- `alignVariablesToRevenue(assumptions, years)` → l'elenco delle scritture, non le scritture.
- `costiPreview(baseInc, fixedShare, data)` → `{ years, tableRows, fornitori, dpo, bars, weight }`.

`CostiTableRow` è dichiarato in `lib/` (non può importare `YearInputRow` da `components/`) in forma
strutturalmente compatibile con `YearInputRow | YearInputGroup`; l'assegnazione è verificata da
`tsc`, non da un cast.

## Un solo motore di proiezione

La ripartizione fisso/variabile degli **anni previsti** che finisce a schermo — le barre impilate
dell'anteprima, le righe «di cui fissi» / «di cui variabili», il peso dei fissi — viene da
`rowsCosti`, cioè dai `details` del motore (`ce05_fixed`, `ce05_variable`, `ce06_fixed`,
`ce06_variable`). Lo slider **non** entra in quell'aritmetica. Il test
*«le barre vengono dai details del motore, non dallo slider»* lo fissa: con `fixedShare` a 32,5/60 la
barra del 2027 vale `130+120+155+30` e `300+90`, i numeri del motore, non un ricalcolo della quota.

L'unico posto in cui la quota digitata moltiplica un importo è la **colonna dell'anno base** — che il
motore non calcola affatto, essendo storico. È l'illustrazione di come il taglio scelto divide
l'ultimo bilancio, ed è già così anche dentro `rowsCosti` (`bFixed`/`bVar`), scritto al task 8.

`costiPreview` usa **gli anni che il motore ha prodotto** (`data.forecast_years`), non
`p.forecastYears`: se il motore si è fermato a metà, la 200 porta gli anni validi e sono quelli che
si mostrano. Le colonne richieste non vengono riempite di vuoto.

## Zero e assente

- Anno base mancante → `baseLabel` «—» su tutte le righe, e lo slider mostra «—» al posto
  dell'importo; le due fasce colorate restano ma senza cifra.
- Ripartizione forzata da un override → `fissi`/`variabili` sono `null`, la barra non ha segmenti
  (`fixedFlex` e `variableFlex` a 0 sopra la traccia `bg-muted`), e `weight.last` è `null` → «—»,
  mai «0,0%».
- `preview.dpo === null` (nessun anno previsto) → l'occhiello perde la parentesi «(N GG)» invece di
  stampare «(0 GG)».
- `alignVariablesToRevenue` su un anno senza `revenue_growth_pct` scrive **0**, e lì lo zero è
  giusto: è il valore che il motore userebbe comunque.

## Scostamenti dal brief, e perché

1. **`baseAmount` di `SplitSlider` è `number | null`, non `number`.** Il brief lo tipizza `number` e
   chiama `formatCurrency(baseAmount)` secco. Con l'anno base assente avrebbe stampato «0 €» su una
   cosa che non si sa: violerebbe «zero e assente sono due cose diverse». Il resto del markup dello
   slider è verbatim (min/max/step, `accent-blue-500`, le soglie `> 12` / `< 88`, le classi delle due
   fasce con le loro `dark:`, il testo dell'avviso `uneven`).
2. **Il badge «forzato in CE Prev.» sta accanto all'etichetta dello slider** («Materie prime»,
   «Servizi») e non accanto alle righe della tabella. Il brief dice «accanto all'etichetta di
   Materie/Servizi»: nella tabella quelle etichette non esistono per intero (sono «Materie prime ·
   parte variabile» ecc.), mentre negli slider sì. Ed è il posto che informa davvero: l'override
   spegne l'effetto **dello slider**. Nella tabella lo stesso avviso compare come `sub` sulle due
   righe del gruppo colpito — `YearInputRow.label` è una `string`, non un `ReactNode`, quindi un
   `<Badge>` lì dentro avrebbe richiesto di modificare `YearInputTable.tsx`, che non è mio.
3. **Icona sul pulsante**: `AlignLeft` di lucide-react, non prevista dal brief ma coerente con la
   riga «niente emoji, icone lucide».

## I due dubbi che ti sottopongo

**1. La quota fissa per anno non è correggibile da questo passo.** È l'avvertimento che mi hai dato,
e il brief prescrive solo `updateAll` (§4.3, «tutti gli anni»). Ho seguito il brief. Conseguenza
concreta: `fixed_materials_percentage` e `fixed_services_percentage` sono in `STEP_FIELDS.costi`,
quindi il passo li *possiede*, ma l'unica via per differenziarli anno per anno resta il form
avanzato fuori dal wizard — e appena lo slider si muove, i valori differenziati vengono **appiattiti**
su tutti gli anni. Il modulo `lib/` è già pronto per l'altra metà: `fixedShareOf` dichiara `uneven`,
il componente lo rende come avviso ambrato («Valori diversi per anno: muovendo lo slider li
allinei»), e servirebbero solo due righe in più nella tabella (`fixed_materials_percentage`,
`fixed_services_percentage`, con `FIELD_RULES` già a min 0 / max 100 / step 1) per renderla
correggibile con `update`. Dimmi se le aggiungo: sono ~6 righe in `costiTableRows` più un test.

**2. Il pulsante «Allinea le variabili ai ricavi» non tocca le quote fisse, solo le crescite.**
Il brief è esplicito e l'ho seguito alla lettera. Vale la pena notare che il nome può leggersi in due
modi: «le percentuali di crescita delle parti variabili prendono la crescita dei ricavi» (quello
implementato) oppure «la parte variabile viene dimensionata sui ricavi». Se l'etichetta ti sembra
ambigua a schermo, il posto per cambiarla è solo il componente.

## Verifiche

```
cd frontend
npx vitest run lib/    →  30 file, 362 test, tutti verdi (31 nuovi in budget-costi-step.test.ts)
npx tsc --noEmit       →  nessun output
```

**Terminatori di riga:** nessun file preesistente toccato — `git diff --name-only d0d6d0a` è vuoto,
quindi il conteggio delle coppie `equal` con byte diversi è **0** per definizione, su zero file. I
tre file nuovi sono LF puro (`grep -c $'\r'` = 0 su ciascuno).

**Verifiche a mano coi dev server: saltate**, come da consegna. Non ho quindi visto con gli occhi
che lo slider a 0 e a 100 spenga le righe giuste (Step 4 del brief): quello che posso affermare è
che `costiTableRows` lo decide correttamente, provato dal test *«a quota 100 si spengono le
variabili, a quota 0 le fisse — e mai le altre»*, e che `YearInputTable` traduce `off` in
`opacity-40` + `disabled`. Il collaudo con browser reale è il Task 17.

Il componente non è ancora montato da nessuna parte: il wizard che sceglie il passo è il Task 15.
