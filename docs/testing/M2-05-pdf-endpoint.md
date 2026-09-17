# M2-05 — Endpoint PDF del dossier

2026-09-17, worker M2-05 (task `task_759a78b1f3cb`), branch dal worktree
`m2-05-endpoint-pdf` su `0e1e7f5`. Nessuna modifica a renderer, template,
inventario, piano (perimetro M2-02B) né al contratto v2.

## Che cosa è stato fatto

- **Nuova rotta** `POST /api/v1/companies/{id}/scenarios/{id}/final-report/pdf`
  con corpo chiuso `{document_state: "draft"|"final", grayscale: bool}`
  (`backend/app/schemas/final_report_pdf.py`, in `backend/app/api/v1/reports.py`).
- **Nuovo servizio** `backend/app/services/final_report_pdf_service.py`:
  assembla il modello v2 esattamente come `GET final-report?schema_version=2`
  (quindi con piano editoriale e note già persistiti, proiezione inclusa),
  vara il cancello e rende con il `DossierLayoutProbe` condiviso del servizio
  editoriale — un'istanza sola per processo, semaforo interno già esistente.
  Nessuna AI, nessuna rigenerazione del previsionale, nessuna scrittura su DB.
- **Mappa errori** condivisa: `_NON_ENTRA` si è spostata da
  `api/v1/editorial_notes.py` a `core/render_panics.py` (`NON_ENTRA`), importata
  da entrambe le rotte senza duplicazione.
  404 proprietà (via `validate_scenario_belongs_to_company`, come tutte le rotte);
  409 piano mancante/non attuale («premere «Prepara piano editoriale»»), 409
  `final` su readiness ≠ `ready`; 503 `RendererBusy`/`RendererUnavailable`;
  504 `RendererTimeout`; 422 `RendererCompileError` con panic noto; 500
  `RendererInvalidPdf`, panic sconosciuto e resto. Messaggi solo in italiano,
  senza percorsi né dati.
- **Risposta** `application/pdf` con `Content-Disposition: attachment;
  filename="Report Budget 2027 - 2029 - <azienda>.pdf"` (sanificato dai
  caratteri vietati, più `filename*=UTF-8''…`), `ETag` = hash canonical
  modello+piano, `X-Report-Model-Hash`, `X-Report-Template-Version`,
  `X-Report-Compiler-Version`, `Cache-Control: no-store`. Nessuna tabella nuova.

## Commit

| SHA | Messaggio |
|---|---|
| `aa89bc3` | refactor(report): M2-05 la mappa dei panic non-entra diventa condivisa |
| `49f6c3e` | feat(report): M2-05 endpoint PDF del dossier con cancello e mappa errori |
| `cf8a402` | test(report): M2-05 suite endpoint PDF con cancello, header, errori e flusso nativo |

File: `backend/app/core/render_panics.py` (nuovo),
`backend/app/schemas/final_report_pdf.py` (nuovo),
`backend/app/services/final_report_pdf_service.py` (nuovo),
`backend/app/api/v1/reports.py`, `backend/app/api/v1/editorial_notes.py`,
`tests/test_final_report_pdf_endpoint.py` (nuovo).

## Test eseguiti (venv del repo principale, `PYTHONPATH=backend`,
`TYPST_TEST_BINARY=tools/typst/bin/typst`)

| Suite | Esito | Durata |
|---|---|---|
| `tests/test_final_report_pdf_endpoint.py` — 27 mock (409 piano mancante, 404 altro utente, bozza sempre 200, final solo su ready, 422 contratto, 503/503/504/422/500×4 mappati con renderer in monkeypatch, nessuna chiamata AI, nessun scrittura DB, header e nome file, `artifact_filename` pura) | 27 passati | 3,0 s |
| `tests/test_final_report_pdf_endpoint.py::test_native_pdf_matches_get_v2_and_watermarks` — preparazione piano reale, bozza 72… (fixture) con BOZZA su ogni pagina, 409 final non-ready, narrativa → ready → ripreparazione → final senza watermark, ETag = hash(modello+piano) della `GET v2` | 1 passato | 17,8 s |
| Regressione: `test_final_report_endpoint.py` + `test_editorial_notes_endpoint.py` + `test_http_full_cycle.py` + `test_final_report_v2.py` | 79 passati | 27,3 s |
| Regressione: `test_cors_on_500.py` + `test_final_report_contract.py` + `test_editorial_notes_service.py` | 44 passati | 2,6 s |
| Regressione Typst: `test_typst_editorial_plan.py` (12 funzioni, 29 parametri) | 29 passati | 119,6 s |

## Prova reale su AMBIENTA (azienda 575, scenario 18)

Contro **copia** del DB reale (`DATABASE_PATH`, originale mai toccato), con
piano preparato sulla copia (1 riga in `report_editorial_states`, 0 note: le
neutral restano proiezione). Server `uvicorn` dev-mode, `ANTHROPIC_API_KEY`
vuota. Piano pre-esistente sulla copia: `pending` (firma renderer cambiata da
`0e1e7f5`) → `POST …/editorial/prepare` **200 in 7,0 s**, 72 pagine, readiness
`ready` ovunque.

| Chiamata PDF | Esito | Durata | Bytes |
|---|---|---|---|
| `draft` | 200, 72 pagine, `%PDF`, titolo `Report Budget 2027 - 2029`, BOZZA su 72/72 pagine | 4,70 s | 1.112.014 |
| `final` | 200, 72 pagine, BOZZA su 0 pagine | 4,47 s | 1.107.699 |
| `final` grayscale | 200 | 4,41 s | 1.102.767 |

Header osservati: `Content-Disposition: attachment;
filename="Report Budget 2027 - 2029 - AMBIENTA.pdf"; filename*=UTF-8''…`,
`ETag: "e6d353…"`, `X-Report-Model-Hash: 69156c…`,
`X-Report-Template-Version: dossier-final-1+native-charts-1+editorial-2`,
`X-Report-Compiler-Version: 0.15.1`, `Cache-Control: no-store`. Snapshot
`count(*), max(rowid)` di 12 tabelle: **identico prima e dopo le tre chiamate**
(nessuna scrittura). Artefatti:
`/home/peter/DEV/budget/inbox/artifacts/2026-09-17-m2-05/report-budget-ambienta-{draft,final,final-grayscale}.pdf`
(sha256 nel report del worker).

## Scostamenti dal piano e rischi residui

- L'`ETag` è, alla lettera del task, hash di modello+piano: **non distingue
  draft da final né grayscale**. Le tre chiamate sulla stessa copia hanno lo
  stesso ETag con PDF diversi. È voluto, come da specifica; se il download
  dovesse mai passare da una cache HTTP, servirebbe estenderlo alle opzioni.
- `RendererCompileError` con panic sconosciuto → 500 (mappa PDF) mentre la via
  editoriale risponde 503: le due superfici divergono di proposito perché il
  task lo chiede; la mappa dei panic è invece unica.
- Il cancello `final` guarda `readiness.status` del report (diagnostica
  economica), non `editorial_readiness`: un piano valido senza readiness `ready`
  stampa la bozza, non il finale. Il caso «piano valido ma report blocked» è
  testato (`409`).
- La parità con la `GET` è verificata in nativo sull'hash (stesso modello renderizzato),
  non sul JSON del PDF: due render dello stesso modello differiscono solo per
  il timestamp di creazione (`--creation-timestamp` congelato su `generated_at`).
- Rischio noto: `render()` condivide il semaforo con le due sonde editoriali
  (`max_concurrent=2` per processo) — un download durante un `prepare` può
  uscire 503 «occupata» senza coda. Coerente con le scelte del runtime M2-01.
