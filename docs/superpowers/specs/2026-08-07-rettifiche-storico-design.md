# Rettifiche su due anni — "Storico" e "Bilancio di verifica"

Data: 2026-08-07 · Stato: approvato · Ambito: solo frontend

## Problema

Una situazione contabile infrannuale (es. bilancio di verifica al 30.06.2026) arriva quasi
sempre insieme al suo anno di riferimento (31.12.2025) — o perché il PDF ha due colonne e
l'importer crea entrambi gli anni, o perché l'utente carica un secondo PDF dal passo
Importazione. **Entrambi gli anni possono aver bisogno di rettifiche**, ma oggi il passo
Rettifiche ne espone uno solo: l'anno parziale. L'anno storico è visibile unicamente come
colonna di confronto in sola lettura.

Questo conta perché lo storico non è decorativo: il Confronto lo usa come base, la Proiezione
ci calcola sopra le percentuali di crescita e gli Indicatori ne derivano la colonna "Storico".
Un errore di classificazione non corretto sullo storico si propaga a tutto il resto.

## Vincoli già soddisfatti (nessuna modifica backend)

- `GET /companies/{id}/years/{year}/adjustable` e `PUT .../adjustments` accettano già
  `year` + `period_months` opzionale; `_find_fy` con `period_months=None` seleziona il record
  annuale (`financial_years.py:284-296`). Sono agnostici rispetto all'anno.
- L'importer persiste già l'anno precedente di un PDF a doppia colonna come `FinancialYear`
  con `period_months=None` (`pdf_importer.py:1375-1378`), incluso il percorso rotta C.
- Il passo Importazione garantisce già che l'anno di riferimento esista, sia importato con un
  secondo file (`handleImportRefYear`) o saltato esplicitamente (`handleSkipRefYear` →
  modalità annualizzazione pura).
- `RettificheTab` è già una funzione top-level guidata da props: `hasRef` nasconde la colonna
  di riferimento quando non c'è, e `periodEndDate` deriva la data da `(fiscalYear, periodMonths)`,
  quindi `(2025, 12)` produce già "31/12/2025". **Il componente non va modificato.**

## Progetto

### 1. Hook `useRettificheYear`

```ts
function useRettificheYear(
  companyId: number | null,
  year: number,
  periodMonths: number | undefined,   // undefined = anno intero
  onSaved: () => void,
): {
  data: AdjustableFinancialYear | null
  corrections: Record<string, number>; setCorrections: Dispatch<SetStateAction<…>>
  loading: boolean; saving: boolean; applied: boolean
  exists: boolean                     // false quando l'anno non ha un FinancialYear
  load: () => Promise<void>
  save: (corr?: Record<string, number>, log?: RettificaEntry[]) => Promise<void>
  reset: () => Promise<void>
}
```

`load`, `save` e `reset` sono `loadAdjustable` e i due handler inline di `page.tsx:4008-4065`
spostati invariati, con `year`/`periodMonths` presi dagli argomenti invece che dalla closure.
`load` mantiene il seeding di `corrections` dai valori SALVATI, `reconcileSubfields`, e il
calcolo di `applied` per confronto con `original_*`.

Unica differenza di comportamento: **un 404 imposta `exists = false` invece di emettere un
toast di errore** — è lo stato legittimo "anno storico assente". Ogni altro errore conserva i
messaggi attuali.

### 2. Due istanze, un solo componente

```ts
const storico  = useRettificheYear(companyId, fiscalYear - 1, undefined, invalidateDownstream)
const verifica = useRettificheYear(companyId, fiscalYear,
                                   periodMonths < 12 ? periodMonths : undefined,
                                   invalidateDownstream)
```

`referenceYearData` smette di essere una fetch e uno stato a sé e diventa **derivato da
`storico.data`** (merge BS+IS + `reconcileSubfields`, come oggi). È il punto che tiene insieme
la feature: correggendo lo storico su una scheda, la colonna "Storico" in sola lettura
dell'altra si aggiorna senza rifetch.

Dentro il passo Rettifiche del wizard, un `Tabs` shadcn con due schede:

| prop | Rettifiche Storico (default) | Rettifiche Bil. di verifica |
|---|---|---|
| `fiscalYear` | `fiscalYear - 1` | `fiscalYear` |
| `periodMonths` | `12` → intestazione 31/12/2025 | `periodMonths` → 30/06/2026 |
| `referenceYearData` | `null` (colonna nascosta da `hasRef`) | derivato da `storico.data` |
| `referenceYear` | irrilevante: la prop resta obbligatoria ma non è letta quando `hasRef` è falso | `fiscalYear - 1` |
| `onNext` | passa alla scheda Bil. di verifica | `setActiveTab("comparison")` |

Quando `storico.exists === false` il trigger è disabilitato e il pannello spiega che non è
stato caricato un bilancio storico e la proiezione gira in annualizzazione pura.

### 3. Invalidazione a valle

`invalidateDownstream()` esegue `setComparison(null)`, `setAnalysis(null)`,
`setProjectedBS(null)` e mostra un toast di avviso "ricalcola la proiezione" **solo quando una
proiezione esiste già** (`analysis || projectedBS`), così un utente al primo passaggio non
viene disturbato.

Si applica a **entrambi** gli anni, non solo allo storico: rettificare il bilancio di verifica
invalida la proiezione allo stesso modo, e oggi quel percorso azzera `comparison` ma lascia
`analysis` e `projectedBS` obsoleti. Nulla viene ricalcolato di nascosto: l'utente ripassa da
Confronto → Proiezione.

### 4. Casi limite

- Anno storico assente → `exists = false`, scheda disabilitata (non un errore).
- Il tetto di 20 rettifiche è per `FinancialYear` ed è imposto dal server, quindi ogni scheda
  ha il proprio budget di 20. Il toast client-side vive dentro `RettificheTab`, quindi funziona
  per istanza senza modifiche.
- Il controllo di quadratura server-side su `PUT /adjustments` si applica già per anno.
- `reset` tocca solo l'anno della propria scheda.

### 5. Verifica

Il frontend **non ha un test runner** (`package.json` ha solo dev/build/start/lint), quindi la
verifica è `tsc --noEmit`, `next build` e una prova manuale su `/infrannuale`:

1. storico presente, rettificato → la colonna Storico dell'altra scheda si muove;
2. storico assente → scheda disabilitata con spiegazione;
3. una rettifica su ciascun anno con proiezione esistente → avviso e invalidazione.

La suite backend resta verde perché non cambia nulla lato backend.

## Fuori ambito

Estrarre `RettificheTab` in un file proprio. Il componente dipende da ~15 costanti a livello di
modulo in `page.tsx` (`PROPOSAL_RULES`, `COUNTERPART_GROUPS`, `RETTIFICHE_BS_ATTIVO`,
`recalcAggregates`, `reconcileSubfields`, …) usate anche da Confronto e Proiezione: servirebbe
un modulo condiviso e toccherebbe codice estraneo a questa modifica. Da fare separatamente.
