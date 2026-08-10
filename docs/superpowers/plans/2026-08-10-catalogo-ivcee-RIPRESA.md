# Ripresa — catalogo IV-CEE

Sviluppo **sospeso** il 2026-08-10 su richiesta dell'utente, a lavoro non finito.
Questo file serve a ripartire senza rileggere tutta la conversazione.

## Stato in una riga

Branch `refactor/catalogo-ivcee`, **6 commit**, niente pushato, niente mergiato.
Task 1 completo e approvato; Task 2 implementato e corretto ma **non ancora passato in
review**; Task 3-9 da fare. Albero pulito, `tsc` 0 errori, **77/77 test verdi**.

## Come ripartire

1. `git checkout refactor/catalogo-ivcee`
2. Leggi il ledger: `.superpowers/sdd/2026-08-10-catalogo-ivcee/progress.md`
   (git-ignored, ma **non cancellarlo**: contiene le diagnosi che in git non ci sono)
3. Invoca la skill `superpowers:subagent-driven-development` sul piano
   `docs/superpowers/plans/2026-08-10-catalogo-ivcee.md`
4. **Il prossimo passo è la review del Task 2**, non il Task 3. Il Task 2 è stato
   implementato (`28b484a`) e corretto in fix round 1 (`c354985`), ma la review di task
   non è mai stata eseguita.

Comando per il pacchetto di review del Task 2:
```bash
SK=/home/peter/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/subagent-driven-development
$SK/scripts/review-package docs/superpowers/plans/2026-08-10-catalogo-ivcee.md 270f32f c354985
```

## I commit del branch

| SHA | Cosa |
|---|---|
| `2eabb66` | spec |
| `02193b9` | piano (9 task) |
| `270f32f` | **Task 1** — l'invariante: 4 elenchi di codici fissati prima di toccare nulla |
| `28b484a` | **Task 2** — la tabella delle voci, 95 voci |
| `5724152` | correzione del piano: `COUNTERPART_PICKER_LABELS` ha 38 chiavi, non 14 |
| `c354985` | **Task 2 fix round 1** — la mappa vince per tutte e 38 |

`main` è a `e2860b1`, già pushato: contiene il refactoring precedente (`page.tsx` 6.019 →
1.810) e la correzione di `sp07_crediti_lungo` nel Totale Attivo. Questo branch parte da lì.

## Cosa fa il lavoro

Sei viste rendono prospetti IV-CEE e ciascuna si riscrive il proprio elenco di righe: 84
codici compaiono in almeno tre dei quattro file principali, e **38 codici su 87 portano
un'etichetta diversa fra Rettifiche e Confronto** — due schede consecutive della stessa
pratica. Il lavoro le unifica in `frontend/lib/ivcee-catalog.ts`.

Dettagli e misure: `docs/superpowers/specs/2026-08-10-catalogo-ivcee-design.md`.

## Decisioni già prese — non rimetterle in discussione

**Le etichette hanno un ruolo, non una forma canonica.** Ogni voce ha un'etichetta
*autonoma* (auto-esplicativa: giornale rettifiche, selettore contropartita, dialoghi, e
ogni riga di Rettifiche) e una *contestuale* (breve: righe di tabella sotto l'intestazione
del proprio aggregato). Non è disordine da sanare: `1) Verso clienti +5.000` in una riga di
giornale non dice se entro o oltre l'esercizio.

**Grafia vincente per il ruolo contestuale: quella del Confronto** (`I - Immobilizzazioni
immateriali`, non `B.I) Immobilizzazioni immateriali`). Era già in uso in cinque viste su
sei. *Ruling utente.*

**`COUNTERPART_PICKER_LABELS` vince come etichetta autonoma per tutte e 38 le sue chiavi**,
non solo i 14 sotto-conti dei debiti. Le altre 24 sono crediti (`sp06a-g`, `sp07a-g`),
immobilizzazioni finanziarie (`sp04a-e`) e rimanenze (`sp05a-e`): stessa natura, stessa
ambiguità fuori da un prospetto. *Ruling utente*, dopo che l'implementer del Task 2 ha
segnalato che il piano diceva 14.

**Rettifiche mostra il massimo dettaglio, le viste di lettura sintetizzano.** Le sotto-righe
restano tutte visibili anche a zero in Rettifiche — comportamento già esistente
(`RettificheTab.tsx` calcola `entroNonZero`/`oltreNonZero` e li scarta di proposito) — e le
viste di lettura filtrano gli zeri. *Ruling utente.*

**Fuori perimetro, con motivazione:** `app/budget/page.tsx` e
`components/budget/assumption-rows.ts` nominano *driver* ("Crescita ricavi %"), non *voci*:
vocabolario diverso, unificarlo sarebbe un errore. `/forecast/reclassified`, `/cashflow`,
`/report`, `/analysis` non contengono alcun codice IV-CEE.

## L'invariante — la cosa da non rompere

`frontend/lib/ivcee-catalog-parity.test.ts` fissa, per ciascuna vista osservabile,
**l'elenco dei codici resi e il loro ordine**. Lunghezze reali: 86 / 91 / 76 / 44.

**Gli elenchi `ATTESI_*` non vanno MAI aggiornati per far passare un test.** Se cambiano,
una vista ha perso o riordinato una riga, ed è quello il difetto. Nessun task del piano
rinomina un codice sintetico (`_hdr_attivo`, `_debt_banche`, i marcatori `computed:`): se
un implementer si trova costretto a farlo, deve fermarsi e segnalarlo.

## Cosa resta da fare

| Task | Cosa | Note |
|---|---|---|
| **2 — review** | review di task mai eseguita | il prossimo passo |
| 3 | proiezioni: `childrenOf`, `subtree`, `aggregate`, `sectionRows` | |
| 4 | adozione `forecast/balance` + `report-appendices` | assorbe e cancella `ivcee-balance-catalog.ts` |
| 5 | adozione `forecast/income` | estrae l'elenco CE inline a riga ~558 |
| 6 | adozione `report-composition` | **può concludersi con una rinuncia documentata**, vedi sotto |
| 7 | adozione `pratica-statement-rows` | Confronto, Proiezione, Stampa |
| 8 | adozione `RettificheTab` | **unico cambiamento visibile**: ~62 etichette |
| 9 | rimozione fonti morte + `CLAUDE.md` | |

Poi: review finale whole-branch, e la decisione su come integrare il branch.

## Trappole note, scritte per non ricascarci

**Il Task 6 può legittimamente non cambiare codice.** `report-composition` riceve dal server
gli *aggregati*, non i dettagli; ma `aggregate()` somma le foglie. Se le foglie sono a zero
restituirebbe zero dove oggi c'è un numero giusto. In quel caso il piano dice di non forzare
la sostituzione, documentare il perché e proseguire.

**Un `shortLabel` mancante non è un difetto.** Il fix round 1 del Task 2 ha prodotto 33
`shortLabel` su 38 codici coperti dal selettore: i 5 sotto-conti delle rimanenze
(`sp05a-e`) non hanno una voce `relabel` del Confronto da cui divergere, quindi restano
senza. È corretto — la contestuale esiste solo dove differisce dall'autonoma.

**Verificare i terminatori di riga prima di ogni commit.** `lib/pratica-*.ts`,
`lib/ivcee-catalog.ts`, `app/pratica/page.tsx` e `components/pratica/*` sono **CRLF**; i
`lib/*.test.ts` sono **LF**. `git diff --stat` che mostra un file riscritto per intero
significa che un tool ha normalizzato: va ripristinato, non committato.

**I server dev girano** su :3000 e :8000, avviati dall'utente. Non toccarli.

## Debito noto, non di questo lavoro

Misurato con un harness di mutazione durante il refactoring precedente: le tre suite di
caratterizzazione (`pratica-reconcile`, `pratica-indicators`, `pratica-statement-rows`)
hanno una copertura del **18% complessivo** e **3/29** sul modulo indicatori. Non vanno
considerate una protezione. La passata di fixture non-zero che le renderebbe vere è un
follow-up aperto, registrato in `CLAUDE.md`.
