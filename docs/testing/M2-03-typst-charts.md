# M2-03 — componenti grafici nativi Typst

Implementazione diretta, review Terra high su autorizzazione dell’utente (Pi
impegnati). Dipendenze integrate: dossier v2 M2-00B, runtime M2-01 e base/piano
provvisorio M2-02A. Nessuna modifica a formule, assembler finanziario o API.

## Componenti e dimensioni

`charts.typ` consuma `chart_series`: sei grafici M1 e dieci approfondimenti v2.
Barre affiancate divergenti per risultati, cashflow, equilibri strutturali,
PFN e incidenze; linee con punti per margini, liquidità, redditività, coperture
e giorni. I tratti si interrompono sui null; un singolo anno resta un punto.
Le barre zero sono segni sulla baseline, non rettangoli di altezza inventata.
All-null: `n.d.` e motivo leggibile, senza una serie zero fittizia.

Dimensioni dichiarate nel file verificato `chart-layout.json`:

| Elemento | Larghezza | Altezza |
|---|---:|---:|
| Componente grafico | 178 mm | 94 mm |
| Plot, assi e categorie | 178 mm | 62 mm |
| Legenda e riferimenti | 178 mm | 32 mm |

La composizione usa stack senza spazi aggiuntivi. La misura Typst emessa nei
metadata conferma l’ingombro; la legenda che non entra fallisce senza essere
tagliata. Il contratto Python vincola anche le quattro misure ai valori esatti
di `native-charts-1`: una revisione firmata con altre dimensioni è rifiutata.
I test confrontano le misure reali con i letterali 178/94, oltre al file del bundle.
Quattro stili distinti coprono la cardinalità massima delle serie
materializzate, compreso cashflow: colori e, sulle linee, dash/simboli differenti.
Un numero maggiore di serie richiede un layout/stili esteso, non sovrapposizioni.

`ChartTemplateBundle` sceglie esclusivamente l’entrypoint interno fisso
`charts-preview.typ` tra i file allowlisted/hash-verificati del bundle comune,
senza duplicare font. Espone `ChartDimensions` con Decimal e versione
`native-charts-1` al successivo planner. Il renderer default della base resta
una composizione separata; i componenti sono pronti per il template completo.

La preview è un collaudo del modulo (copertina più un grafico per pagina), non
il dossier definitivo. Include tabelle, metodologia/convenzioni dei riferimenti
canonici e spazio commento. Piano finale/reflow/note seguono M2-02A/M2-00C.

## Fedeltà dei dati

Float solo per coordinate/assi, con scala esponenziale dichiarata quando serve;
non per testo finanziario. Prima si normalizzano estremi grandi e poi si sottrae,
evitando overflow sui segni opposti. Coordinate fuori range o underflow a falso
zero sono rifiutate. Nessuna formula finanziaria, riclassificazione o soglia
calcolata nel renderer.

`chart-format.typ` arrotonda le stringhe decimali con carry cifra per cifra,
senza passare da float o da un intero grande. Separatore italiano; euro,
percentuali e punti due decimali, giorni uno, rapporti tre. Il numero di decimali
è dichiarato. Le tabelle sono matrici quando i valori entrano; altrimenti usano
periodo/valore con più spazio. Importi che non entrano sono rifiutati, mai tagliati.
Metadata invisibili mantengono unità, categorie e stringhe wire complete.

Riferimenti grafici soltanto dalle `thresholds` degli indicatori effettivamente
referenziati, con label, valore e fonte originali. Nessuna linea DSCR 1 implicita.
Il proxy DSCR della pratica resta separato dalle coperture analitiche; la preview
mostra le rispettive metodologie/convenzioni. La palette della base è ora davvero
grigia su opzione: anche testo, regole e fondi, non soltanto le serie.

## Disponibilità canonica

I grafici v2 materializzati sono `structural_balance`, `practice_liquidity`,
`practice_profitability`, `practice_asset_coverage`, `practice_net_debt`,
`practice_net_debt_ebitda`, `practice_dscr_proxy`, `economic_incidence`,
`financial_charges`, `analytical_liquidity`. Consumo diretto delle serie validate
dal contratto e dei metadati del catalogo.

Audit Terra read-only: nel dossier v2 non sono materializzate serie di pareggio,
Altman/FGPMI/EM-Score, composizione completa impieghi/fonti o confronto collegato
osservato→rettificato→chiusura. I grafici attuali contengono solo anni previsionali.
Altri servizi hanno alcuni di questi risultati, ma non sono input canonici del
report v2: il renderer non li importa né li ricava dai prospetti. Nessun grafico
al 100% sulle sole tre incidenze economiche, che non formano un totale completo.
Questi approfondimenti richiedono l’estensione dell’assembler/contratto prima
di essere inclusi; assenza documentata, nessun dato/soglia/classe inventato.

## Verifica

```bash
PYTHONPATH=.:backend /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
  tests/test_typst_charts.py tests/test_typst_dossier_base.py \
  tests/test_typst_layout_probe.py tests/test_typst_base_plan.py \
  tests/test_typst_runtime.py tests/test_typst_toolchain.py \
  tests/test_m2_00_spike.py tests/test_m2_00_spike_fixtures.py \
  tests/test_final_report_v2.py -q
```

53 test del modulo: 36 combinazioni workflow/orizzonte/stato/colore e controlli
mirati su valori estraibili, font incorporati, vettori senza raster, margini,
footprint/metadata wire, null, negativi, zero, Decimal oltre 2^53/carry, soglie
autorevoli, quattro stili in grigio, overflow/underflow, dimensioni e bytes
riproducibili. Query di test isolata con espressione fissa/output privato, nessuna
diagnostica catturata. Fixture sintetiche, non previsioni di clienti.

Esito finale 2026-09-15: **205 passed, 147 warnings in 76.14s**, con 53 test
grafici e 152 regressioni di base, planner provvisorio, runtime, toolchain/spike
e dossier v2. Warning di deprecazione delle dipendenze già presenti.
Review indipendente Terra high approvata dopo il fix della geometria:
prima verifica 52 test grafici e 13 base; riesame mirato del fix 8 passed.
Audit separato Terra sul catalogo e sulle serie canoniche completato in lettura.

Preview locale BOZZA di 17 pagine (copertina e 16 grafici), dati sintetici della
fixture infrannuale, generata dal runtime isolato e ispezionata anche a schermo:
`inbox/artifacts/2026-09-15-report-finale/m2-03-grafici-typst.pdf`.
Non è un export definitivo né il collaudo del dossier completo.
