# Prepara Report AI — un solo pulsante al posto di tre azioni su /report

Base `4eeeb9e`. Brief: `.superpowers/sdd/2026-09-17-dossier-v4/prepara-report-ai.md` (nel repo
principale, non versionato in questo worktree — vedi «Trovato fuori dal worktree» sotto). Solo
frontend, nessun endpoint né schema toccato.

## File creati/modificati

- `frontend/lib/prepare-report-ai.ts` (nuovo) — modulo puro, nessun import da `app/` o
  `components/` (regola CLAUDE.md «Frontend»): `decidePrepareReportAI` decide, senza chiamare
  nulla, se i sei blocchi narrativi vanno rigenerati e quali note di pagina sono candidate;
  `runPrepareReportAI` esegue la sequenza piano → narrativa → note, iniettando le tre chiamate
  reali e un `notify` opzionale per l'etichetta di stato a schermo.
- `frontend/lib/prepare-report-ai.test.ts` (nuovo) — 15 test sul modulo sopra.
- `frontend/app/report/page.tsx` — rimossi gli stati `preparing`/`generatingNarrative` e le
  funzioni `prepare`/`regenerateNarrative`; aggiunti `aiPrepMode`/`aiPrepStepLabel` e `runPrepareAI`
  che chiama il modulo puro. Due pulsanti nella `PageHeader` al posto dei tre precedenti («Prepara
  piano editoriale», «Rigenera commenti», e il trigger implicito di `generate(notes)`): **«Prepara
  Report AI»** e **«Rigenera tutto»** (`variant="secondary"`), entrambi disabilitati durante
  l'esecuzione dell'altro e durante un'azione PDF (`pdfRequestBusy`); i due pulsanti PDF sono ora a
  loro volta disabilitati mentre «Prepara Report AI» è in corso (esclusione simmetrica, §7 del
  brief). Il testo del banner «Piano editoriale da preparare» ora nomina il pulsante nuovo. La
  manciata di note manuali (`EditorialNotes`, il picker con le checkbox «Genera selezionati») resta
  intatta: non è la barra delle azioni, e il brief chiede di non ristrutturare `/report`.

## Come si decide «che cosa è da rigenerare»

- **Narrativa** (sei blocchi): un id assente dal modello conta sempre come da generare. Un blocco
  di provenienza `user` non si tocca mai, con o senza «Rigenera tutto». Senza `forceAll`: si
  rigenera se almeno un blocco non-utente è assente o non `fresh`. Con `forceAll`: si rigenera se
  esiste almeno un blocco non-utente (o mancante) — a prescindere dalla sua freschezza — perché
  `generateFinalReportNarrative` non prende una lista di id: rigenera sempre tutti e sei i blocchi
  in un'unica chiamata, e il server (non il client) è l'invariante che non tocca mai un blocco
  `user`. Se tutti e sei sono `user`, la chiamata si salta: non c'è nulla da rigenerare.
- **Note**: candidate = non `user` **e** senza bozza locale non salvata (stessa regola già in
  `generate()`), poi filtrate per freschezza (`freshness !== "fresh"`) — salvo `forceAll`, che
  rigenera tutte le candidate a prescindere dalla freschezza. Le note escluse per bozza o
  provenienza utente restano escluse anche con «Rigenera tutto»: non è un bypass di quella regola,
  solo della freschezza.
- **La decisione sulle note si prende DOPO il passo 1, non prima.** `POST .../prepare` può
  creare o riassociare pagine e note, e restituisce la sessione fresca (`revision`, `plan.plan_hash`,
  `report.source_hash`, `report.editorial_notes`). `runPrepareReportAI` è generico su `TSession`:
  riceve `preparePlan: () => Promise<TSession>`, e passa il risultato sia a `buildDecision`
  (`decidePrepareReportAI` applicata sulla sessione fresca) sia ai due passi successivi — che
  quindi generano/salvano con la `revision`/`plan_hash` corretti invece di un valore
  potenzialmente già superato dal prepare stesso. Verificato che la rigenerazione dei commenti
  narrativi non tocca `ReportEditorialState.revision` (`backend/app/services/editorial_notes_service.py`
  — la tabella che quella colonna presidia è scritta solo da `_cas_and_write`, mai dal percorso
  `ai_comments_service.generate_final_report_narrative`), quindi riusare la `revision` del prepare
  per la chiamata note successiva, anche dopo aver rigenerato la narrativa nel mezzo, è corretto.
- Un fallimento del passo 1 **ferma** narrativa e note (§5 del brief: senza piano non si generano
  note, e qui neanche la narrativa — decidere richiede comunque la sessione fresca). Un fallimento
  della narrativa **non ferma** le note: sono contenuti indipendenti nello schema (v1 vs v2), e ciò
  che riesce resta.
- Riepilogo (`summary`, un solo toast): conta piano/commenti/note fatti, saltati (già aggiornati) o
  falliti, nominando il passo che è fallito. Toast `error` solo se il piano fallisce; `warning` se
  narrativa o note falliscono ma il piano è riuscito; `success` altrimenti.

## Test

```
cd frontend
npx tsc --noEmit                              # verde, nessun errore
npx vitest run                                 # 84 file, 1002 test, tutti verdi
npx vitest run lib/prepare-report-ai.test.ts   # isolato: 15 test verdi
npx next lint                                  # nessun errore nuovo sui file toccati; i soli errori
                                                # (2, react/no-unescaped-entities) e warning pre-esistenti
                                                # sono in app/pratica/page.tsx, components/AppHeader.tsx,
                                                # BudgetWizard.tsx, StepPatrimonialePiano.tsx,
                                                # StampaContent.tsx, report-cover.tsx — nessuno di questi
                                                # toccato da questo lotto
```

I 15 test di `lib/prepare-report-ai.test.ts` coprono l'accettazione richiesta dal brief:
sequenza completa con l'ordine delle chiamate verificato (`invocationCallOrder`), salto dei passi
già aggiornati senza chiamare le rispettive API, interruzione al fallimento del piano (narrativa e
note mai tentate, `continued: false`, `decision: null`), errore parziale sulla narrativa che non
blocca le note (e viceversa) con il riepilogo che nomina il passo fallito, ed esclusione delle note
`user` e delle note con bozza locale non salvata dai target — sia in modalità normale sia con
`forceAll`. `decidePrepareReportAI` è testato separatamente dalla sequenza (`runPrepareReportAI`
nei test usa `TSession` fittizio, per isolare la logica di sequenziamento dalla logica di
decisione già coperta sopra).

`git diff --stat` su `frontend/app/report/page.tsx`: 48 inserzioni, 7 cancellazioni, nessuna riga
normalizzata (il file non è fra quelli CRLF/misti della regola comune).

## Scostamenti dal brief

- Il brief non specifica se il picker manuale delle note (`EditorialNotes`, «Genera selezionati»)
  vada rimosso quando si introduce «Prepara Report AI». Letto insieme al vincolo «non ristrutturare
  `/report`: solo la barra delle azioni e il codice che serve», l'ho lasciato intatto: resta un
  controllo più granulare per un caso d'uso diverso (rigenerare *una* nota specifica dopo averla
  ispezionata), non in conflitto con il pulsante nuovo.
- Il brief non specifica se i pulsanti PDF debbano essere disabilitati mentre «Prepara Report AI»
  è in corso (dice solo che i due pulsanti nuovi sono esclusi anche dalle azioni PDF). Ho reso
  l'esclusione simmetrica (anche i pulsanti PDF si disabilitano durante la preparazione) per
  coerenza: generare un PDF a metà di una rigenerazione dei contenuti editoriali produrrebbe un
  documento con contenuti in transizione.
- Colori/formato esatto del riepilogo (`summary`) e i due livelli di severità del toast
  (`warning` per un fallimento parziale, `error` solo per il fallimento del piano) sono una scelta
  di implementazione: il brief chiede «un solo toast di riepilogo» col conteggio, non la sua
  severità visiva.

## Rischi residui

- Non verificato contro un backend reale in esecuzione (nessun server avviato in questo lotto):
  la sequenza è verificata contro il contratto della sessione editoriale
  (`backend/app/schemas/editorial_notes.py`, `EditorialSession`) e contro il codice del servizio
  (`editorial_notes_service.py`) per la garanzia sulla `revision`, non con una chiamata end-to-end.
- Se in futuro `generateFinalReportNarrative` iniziasse a leggere o scrivere
  `ReportEditorialState.revision` (oggi non lo fa), l'assunzione documentata sopra — che riusare la
  `revision` del prepare dopo aver rigenerato la narrativa resti valido — andrebbe riverificata.
- `EditorialNotes.tsx` non è stato toccato: se un domani si volesse davvero rimuovere il picker
  manuale a favore del solo flusso automatico, è un cambiamento successivo e separato.

## Trovato fuori dal worktree

Il brief (`prepara-report-ai.md`) e le regole comuni (`regole-comuni.md`) vivono in
`.superpowers/sdd/2026-09-17-dossier-v4/` nel repo principale (`/home/peter/DEV/budget`), non in
questo worktree — `.superpowers/` qui non esiste affatto (non è tracciato da git in nessuno dei
due alberi). Questa ricevuta vive solo qui, in `docs/testing/PREPARA-REPORT-AI.md` (versionata);
la sua copia richiesta dal brief va nella cartella SDD del repo principale — l'unica eccezione
concessa al divieto di toccare `/home/peter/DEV/budget` — a
`.superpowers/sdd/2026-09-17-dossier-v4/receipts/prepara-report-ai.md`. Non ho copiato il brief
né le regole comuni nel worktree, e non ho toccato altro in `/home/peter/DEV/budget`.
