# M2-02 — impaginazione editoriale definitiva

Dipendenze integrate: dossier canonico v2 e piano misurato M2-02A, sedici grafici
nativi M2-03 e commenti per pagina M2-00C. Il modulo modifica soltanto template,
identità degli asset e fixture di rendering; non introduce formule, indicatori,
soglie, commenti AI o scritture contabili.

## Sistema editoriale

Il bundle `dossier-final-1` adotta il riferimento approvato: A4 verticale, fascia
navy di copertina alta 108 mm, margini laterali di 16 mm, IBM Plex Sans incorporato,
corpo 8,8 pt, titoli navy e regole azzurro-grigie. Il titolo arriva sempre dal
contratto ed è neutrale (`Report Budget 2027 - 2029`, oppure l'orizzonte reale).
La copertina mostra azienda, percorso, periodo di piano, anno base, scenario di
origine e i contenuti del dossier. Non contiene claim finanziari calcolati dal
template né diciture di sviluppo.

Dalla seconda pagina la testatina riporta azienda e titolo del report. Il piè di
pagina contiene la dicitura di riservatezza e la numerazione corrente/totale. Il
riquadro `Lettura del consulente` mantiene la capacità misurata di 178 × 18 mm,
9 pt e quattro righe su ogni pagina, copertina e continuazioni comprese. Le bozze
mantengono il watermark su tutte le pagine; il documento finale lo rimuove.

## Contenuto e Allegati

Le dodici sezioni logiche del workflow infrannuale, undici per bilancio e startup,
restano determinate dall'inventario canonico. I sedici grafici vettoriali espongono
risultati, margini, indebitamento, liquidità, coperture, circolante e indicatori
materializzati dal modello, con la tabella valori nello stesso foglio. Nessun KPI
viene selezionato in copertina in base all'ordine del catalogo: manca un riferimento
canonico che autorizzi quella selezione.

I prospetti con più periodi usano una matrice comune: voce a sinistra, valori
allineati a destra e metadati tecnici in corpo ridotto. Storico, osservato,
rettificato, chiusura e budget restano distinti e non annualizzati. Celle e righe
non vengono troncate; un token o un importo che non entra causa un errore esplicito.
Le intestazioni delle tabelle ripetono sezione, titolo e periodi su ogni pagina di
continuazione. Gli Allegati conservano una volta sola tutte le righe CE, SP e
rendiconto, il contesto padre, il catalogo e le ragioni di indisponibilità.

La revisione del layout aggiorna la versione editoriale a `editorial-2`. Hash di
bundle, font, template e inventario invalidano intenzionalmente piani e associazioni
precedenti: le note manuali richiedono la riassociazione già protetta da M2-00C.

## Verifica

La matrice reale copre infrannuale, bilancio e startup con orizzonti di uno, tre e
cinque anni. Per ciascun caso verifica inventario e righe esatti, nota distinta su
ogni pagina, watermark di bozza, titolo e metadati della copertina, testatina,
riservatezza, numerazione pagina/totale, intestazione di ogni continuazione,
font incorporati, assenza di raster e bounding box interamente nel foglio.

Le suite della base e dei grafici coprono inoltre stato finale, determinismo e
scala di grigi: palette monocromatica anche per vettori, testi, fondi e regole.
La fixture infrannuale a sette periodi verifica separatamente valori osservati e
rettificati di nove mesi, chiusura di dodici mesi e tre esercizi previsionali.

Comando di collaudo:

```bash
PYTHONPATH=backend TYPST_TEST_BINARY=tools/typst/bin/typst \
  /home/peter/DEV/budget/backend/venv/bin/pytest -q \
  tests/test_typst_editorial_plan.py tests/test_typst_dossier_base.py \
  tests/test_typst_layout_probe.py tests/test_typst_charts.py \
  tests/test_typst_base_plan.py tests/test_typst_runtime.py
```

Artifact di verifica, costruito con dati sintetici e note per tutte le pagine:
`inbox/artifacts/2026-09-16-m2-02-final-layout/report-budget-2027-2029.pdf`.
È una fixture locale del template, non un export di una pratica cliente.

Esito finale 2026-09-16: **158 passed, 2 warning preesistenti in 150,52 s**.
Regressioni di inventario, API note, concorrenza, persistenza e contratto v2: **71 passed**; totale mirato eseguito in chiusura: **229 test superati**.
