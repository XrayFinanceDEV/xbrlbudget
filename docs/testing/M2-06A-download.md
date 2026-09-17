# M2-06A — download del PDF finale dalla pagina /report

Lavora sul **contratto** dell'endpoint `POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/final-report/pdf`
(M2-05, branch `XrayFinanceDEV/m2-05-endpoint-pdf`, non unito in questo worktree): nessun test
end-to-end contro un backend vero, solo contro il contratto documentato nel brief. Nessun file
backend, template o test Python toccato.

## File creati/modificati

- `frontend/lib/final-report-download.ts` (nuovo) — modulo puro, nessun import da `app/` o
  `components/` (regola CLAUDE.md «Frontend»): nome file da `Content-Disposition`, mappa dei
  messaggi d'errore per stato HTTP, `FinalReportDownloadError`, sink DOM iniettabile
  (`saveBlobAsFile`) e guardia anti-doppio-click (`withDownloadGuard`).
- `frontend/lib/final-report-download.test.ts` (nuovo) — 18 test sul modulo sopra.
- `frontend/lib/api.ts` — `downloadFinalReportPdf(companyId, scenarioId, { documentState, grayscale })`:
  usa `fetch` diretto (non l'istanza axios condivisa, perché la risposta 200 è binaria e il nome
  file vive negli header, non nel corpo JSON che il resto del client si aspetta), stesso Bearer
  (`_authToken` impostato da `setAuthToken`) delle altre chiamate.
- `frontend/lib/api.test.ts` — 4 test aggiunti su `downloadFinalReportPdf` (body inviato, header
  `Authorization` presente/assente, filename dagli header, `FinalReportDownloadError` su un
  errore JSON e su un corpo non-JSON).
- `frontend/hooks/use-final-report-download.ts` (nuovo) — hook React, innesto sottile: usa il
  sink DOM vero (`URL.createObjectURL`/`<a download>`/`URL.revokeObjectURL`) e la guardia del
  modulo puro; su errore mostra un toast col messaggio risolto, con azione «Riprova» solo su
  503/504. Non testato con Vitest: nessun hook di questo repo lo è (vedi `vitest.config.mts`,
  `include` limitato a `lib/**` e `components/final-report/**`), e testarlo servirebbe un harness
  di rendering hook che qui non esiste — tutta la logica non banale (guardia, parsing, mappa
  errori) è già coperta nel modulo puro sottostante.
- `frontend/app/report/page.tsx` — un pulsante nella toolbar della `PageHeader`, accanto ad
  «Anteprima stampa»: «Scarica PDF finale» quando `model.readiness.status === "ready"`, altrimenti
  «Scarica bozza» (con `document_state` coerente); spinner + «Preparazione PDF…» mentre
  `finalReportDownload.downloading` è vero; disabilitato senza modello/azienda/scenario o mentre
  scarica.

## Comportamento verificato contro il brief

- **Nome file**: `filename*` (RFC 5987, `UTF-8''<percent-encoded>`) preferito su `filename`
  ASCII; percent-encoding non valido ricade sul token ASCII; nessuno dei due token, o header
  assente/vuoto → `Report Budget.pdf`.
- **Mappa errori**: 404/409/422/503/504/500 mappati; il `detail` del server (già in italiano per
  contratto) vince sempre quando presente e non vuoto; un corpo di errore non-JSON ricade sulla
  mappa per stato invece di far esplodere il parsing.
- **Doppio click**: `withDownloadGuard` lascia passare una sola chiamata quando due richieste
  condividono lo stesso guard mentre la prima è ancora in volo (test con una promise controllata a
  mano); la seconda risolve `null` senza toccare `task` una seconda volta. Il guard si libera
  anche se il task lancia, e una chiamata successiva (non sovrapposta) riparte normalmente.
- **503/504 → «Riprova»**: `isRetryableDownloadStatus` è vero solo per questi due stati; l'hook
  aggiunge l'azione del toast solo in quel caso.
- **409 sul piano editoriale**: nessuna logica client deve indovinare *quale* 409 sia (piano
  mancante/superato vs. `final` su report non pronto) — il messaggio arriva già corretto nel
  `detail` del server per contratto, e viene mostrato tale e quale via toast. Il fallback per
  stato (usato solo quando manca il `detail`) resta un messaggio generico sul piano editoriale.
- **Pulsante finale vs. bozza**: legato a `model.readiness.status` (`Readiness` da
  `types/final-report.ts`, lo stesso tipo che guida `ReadinessBanner`), non a
  `editorial_readiness` (che governa un'altra cosa: i commenti editoriali).
- **Nessun `window.print()`, nessuna scrittura di dati, nessuna invalidazione di query** nel
  percorso di download: `downloadPdf` non chiama `queryClient.invalidateQueries` né tocca lo stato
  delle altre azioni della pagina.

## Comandi eseguiti

```
cd frontend
npx tsc --noEmit                 # verde, nessun errore
npx vitest run                   # 83 file, 980 test, tutti verdi
npx next lint                    # nessun errore; warning pre-esistenti in altri file, non toccati qui
```

`npx vitest run lib/final-report-download.test.ts lib/api.test.ts` isolato: 27 test verdi (18 +
9, di cui 4 nuovi in `api.test.ts`).

## Scostamenti dal brief

- Il brief lascia all'implementazione la scelta di dove mettere la guardia anti-doppio-click e il
  sink DOM: qui vivono nel modulo puro (`lib/final-report-download.ts`) proprio per poterli
  testare in `environment: node`, con l'hook come solo innesto — nessuna deviazione di
  comportamento, solo di collocazione del codice testabile.
- Nessun endpoint `GET /import/capabilities`-style di introspezione della readiness lato client:
  il pulsante legge `model.readiness.status` già presente nel modello v2 restituito da
  `/final-report`, come da contratto — non è stata aggiunta nessuna chiamata di rete ulteriore.

## Rischi residui

- **Non testato end-to-end contro il backend reale**: l'endpoint M2-05 non è unito in questo
  worktree. Se l'header `Content-Disposition` reale del backend si discostasse dal formato RFC
  5987 assunto qui (es. `filename*` senza `UTF-8''`, o con virgolette diverse), il fallback
  ASCII/di default assorbirebbe la differenza silenziosamente — non è un errore bloccante, ma il
  nome del file scaricato potrebbe non essere quello atteso finché non si integra contro
  l'endpoint vero.
- Il messaggio di errore per un 409 «`final` su report non pronto» è per contratto lo stesso path
  di codice del 409 «piano editoriale mancante»: se in futuro il backend smettesse di mandare un
  `detail` per uno dei due casi, il fallback generico del modulo (`FINAL_REPORT_DOWNLOAD_ERROR_MESSAGES[409]`)
  nomina solo il piano editoriale, non entrambi i casi — da rivedere quando l'endpoint reale sarà
  disponibile per l'integrazione.
