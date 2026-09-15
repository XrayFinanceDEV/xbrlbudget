# M2-02A — base A4 e planner misurato

Dipendenze integrate: M2-00B (`1b88195`) e M2-01 (`2972e19`), gate Typst
nativo approvato. Implementazione diretta e Terra su autorizzazione dell’utente.

## Composizione base

Il bundle interno `dossier-base-1` contiene copertina neutrale, font, stili,
spazio per commenti e i tre prospetti completi. È una base editoriale in sviluppo:
non è il report finale completo né un nuovo endpoint di esportazione.

Copertina A4 con fascia navy a tutta larghezza di 108 mm; titolo derivato
dall’orizzonte del modello (`Report Budget 2027 - 2029` o singolo anno).
Nome azienda preservato integralmente: Typst misura il testo e sceglie 17/14/11 pt
per restare nel riquadro; se non entra, fallisce senza troncarlo.
Corpo 9 pt, tabelle 8 pt, titoli 16 pt, margini laterali 16 mm.

Allegati: tutte le righe CE/SP/rendiconto del modello, compresi i dati non
disponibili con `n.d.`. Testi e importi restano stringhe JSON; nessun calcolo
finanziario e nessun `eval` del contenuto. In questa base gli importi sono euro,
come dichiarato nel prospetto; la formattazione finale segue M2-02.
La misura reale rifiuta importi troppo larghi per la colonna della base, senza
troncarli: formattazione in migliaia e gestione delle colonne estese sono M2-02.
Intestazioni ripetute; catena dei padri visibile nelle righe di dettaglio,
quindi preservata anche sulle continuazioni. Celle non divisibili tra pagine.
Il footer riserva 26 mm al commento con separatore e didascalia; testo commento
9 pt, capacità iniziale quattro righe. Il collaudo delle note reali segue M2-00C.
Spazio presente anche sulla copertina e su ogni continuazione.

## Font distribuiti

Quattro TTF ufficiali IBM Plex Sans, byte identici al riferimento CR: Regular,
Medium, SemiBold e Italic. Tag upstream v6.4.2, commit immutabile
`242c4cccd37e87985a5337815c99b960ef13c65c`, versione font incorporata 3.005.
OFL 1.1 completa, URL e checksum inclusi nel bundle e verificati dal renderer.

Typst legge i nomi legacy delle famiglie statiche: `IBM Plex Sans`,
`IBM Plex Sans Medm`, `IBM Plex Sans SmBld`. L’helper `plex` sceglie la famiglia
esplicitamente per i pesi 400/500/600, senza modificare i file upstream.
Verifica sul PDF dei font realmente incorporati, compresi Medium e SemiBold;
nessun fallback a font di sistema né immagini raster.

## Misura e piano provvisorio

`TypstLayoutProbe.measure_layout()` usa il compilatore pinato nell’isolamento
M2-01 con il bundle reale. Esegue solo l’espressione interna fissa
`query(metadata).map(x => x.value)` tramite `typst eval --in`: non riceve codice
o percorsi dall’utente. Il JSON va in un file output privato esclusivo 0600,
limitato da FSIZE, senza finire nei log.

Gli ID delle righe includono il prospetto (`row:<statement_id>:<row_id>`):
lo stesso ID locale è ammesso in prospetti diversi senza collisioni di pagina/note.
I marker invisibili risolvono le pagine fisiche della copertina, delle singole
righe e dei footer. Validazione: shell una volta per pagina, pagine positive,
contigue e nei limiti, nessuna pagina priva di contenuto, inventario noto,
righe una volta ciascuna nell’ordine completo del modello. La misura include
hash delle fonti/modello e dei byte effettivamente usati per font, template,
compilatore e asset. Una modifica al layout o ai font invalida il fingerprint.
La pagina misurata viene confrontata con il PDF realmente compilato.

Il planner della base raggruppa i contenuti e le parti dei prospetti secondo
queste pagine misurate, con ID ancorati al contenuto e ID dei commenti.
Il risultato è **provvisorio**, non viene assegnato a `editorial_plan` e non
autorizza note finali o readiness editoriale. M2-03 deve fissare le dimensioni
dei grafici; le sezioni complete e il reflow controllato precedono il
congelamento del piano definitivo e la generazione/persistenza note M2-00C.

## Collaudo

```bash
PYTHONPATH=.:backend /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
  tests/test_typst_dossier_base.py tests/test_typst_layout_probe.py \
  tests/test_typst_base_plan.py tests/test_typst_runtime.py -q
```

Verificati i tre workflow e orizzonti 1/3/5 anni, titoli neutri, nomi lunghi
integrali, font incorporati, intestazioni nelle continuazioni, footer/commenti,
assenza di testo fuori pagina, vettori, grigi e determinismo bytes.
Fixture sintetiche: non sono previsioni di clienti. Container/PDF-A restano M2-06B.

Verifica completa: **152 passed** in 41,67 s — 42 runtime, 13 base,
12 probe, 10 planner provvisorio, 42 toolchain/spike e 33 dossier v2.
Review base/probe/runtime: due Terra high indipendenti approvate (66 test).
Review finale planner: prima Terra high approvata (9 test). Seconda Terra high
ha rilevato una collisione di ID locali fra prospetti, corretta tramite namespace;
regressione reale v2 e riproduzione indipendente approvate (22 test probe/planner).
Gate finale della fase base/provvisoria superato.
