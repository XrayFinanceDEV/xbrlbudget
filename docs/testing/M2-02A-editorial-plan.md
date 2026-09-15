# M2-02A — piano misurato del dossier canonico completo

2026-09-15. Implementazione del coordinatore, inventario e audit fonti Terra,
review indipendente Terra high su autorizzazione dell’utente (nessun Pi).
Completa il piano provvisorio `scope=base, finalized=False` senza alterarlo.

## Perimetro e copertura

`editorial_inventory.py` proietta esclusivamente il dossier v2 autorizzato.
Dodici sezioni logiche, undici per bilancio/startup perché la chiusura
infrannuale è omessa. Conserva i sei blocchi narrativi, revisioni/qualità/fonti,
rettifiche e contropartite, tutti i valori di chiusura e alert, sette gruppi di
ipotesi e ogni campo delle strutture annidate, prospetti previsionali,
sedici grafici, tutti gli indicatori con metodi/convenzioni/fonti e diagnostica.
Gli Allegati contengono tutti i cataloghi CE/SP/CF ordinati, compresi i null
motivati e le voci non rappresentabili. Nessun subtotale o formula nel renderer.

Ogni riga annidata è un campo autonomo con la propria unità; nessuna stringa
composta viene interpretata come numero. Le ipotesi inattive e le provenienze
restano visibili. Valori scalari oltre gli anni assegnati sono esposti come
`Periodo non associato N`, senza scartarli o inventare anni. Codici previsionali
duplicati e periodi di indicatori con definizioni incompatibili sono rifiutati.
L’inventario mantiene stringhe Decimal esatte; l’arrotondamento solo di stampa
usa il componente M2-03. Le coperture analitiche non diventano il proxy DSCR.

Il confronto nel corpo usa i subtotali già canonici dei periodi disponibili;
gli Allegati mantengono tutte le righe e tutte le colonne. La nota di comparabilità
infrannuale dichiara che gli importi osservati/rettificati non sono annualizzati.
Il test aggiuntivo assembla storico, osservato a 9 mesi, rettificato a 9 mesi,
chiusura a 12 mesi e tre anni di budget attraverso `extend_dossier`: i valori
900/1020/1200 sono preservati, non moltiplicati per una durata stimata.

## Misura, congelamento e reflow

`DossierTemplateBundle` usa soltanto `editorial.typ`, entrypoint interno
allowlisted/hash-verificato. Condivide font IBM Plex, base e grafici M2-03.
`DossierLayoutProbe` riusa la query fissa e il processo Bubblewrap M2-01.
L’unico JSON aggiuntivo è derivato nel backend dal modello validato, con nome
costante, limite input/asset/file e nessun percorso o markup scelto dal client.

I marker sono confrontati nell’ordine esatto con l’inventario completo. Ogni
pagina fisica deve essere contigua, contenere dati noti, appartenere a una sola
sezione e avere una shell e un riquadro commento. I metadata dei grafici
verificano categorie, unità, serie, soglie e misure 178×94 mm: geometrie int/float
sono rifiutate, sono richieste stringhe finite. Le parti degli Allegati
referenziano ogni riga esattamente una volta nell’ordine del modello, con
namespace del prospetto e catena completa dei padri sulle continuazioni.
L’indice degli Allegati usa pagine reali risolte dai metadata Typst.

`build_editorial_plan` produce il contratto `EditorialPlan` verificato. ID pagina
e nota sono hash dell’ancora semantica iniziale, non del numero di pagina.
L’hash include font, layout/compilatore, asset, fonte e raggruppamento dei dati.
Include anche la definizione Python dell’inventario: una sua revisione invalida
il piano anche se le pagine non cambiano. La definizione viene catturata
all’import e ricontrollata prima dello staging; aggiornamenti del codice
richiedono un worker ricaricato. Il testo delle note non entra nel plan hash;
il model hash finale include i testi.

`prepare_editorial_report` restituisce uno snapshot con piano assegnato, senza
scritture o AI; rimane `pending` finché mancano i commenti. Conserva note e stato
quando il piano è identico, verificando nuovamente il loro ingombro. Se un piano
cambiato coinvolge note manuali, richiede una riassociazione esplicita, senza
sovrascriverle. L’input resta immutato.

`verify_editorial_layout` rimisura lo snapshot e confronta l’hash, prima di
riutilizzare le associazioni. Un drift è un errore, non una migrazione silenziosa
delle note. I riquadri hanno larghezza 178 mm, altezza utile 18 mm, font 9 pt e
quattro righe. Testo troppo alto o con parole che superano la larghezza fallisce
senza tagli. Anche importi/celle/prosa fuori spazio falliscono; le stringhe
tecniche possono andare a capo sui separatori conservando il testo.

## Verifica e limiti

```bash
PYTHONPATH=.:backend /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
  tests/test_editorial_inventory.py tests/test_typst_editorial_plan.py \
  tests/test_typst_charts.py tests/test_typst_dossier_base.py \
  tests/test_typst_layout_probe.py tests/test_typst_base_plan.py \
  tests/test_typst_runtime.py tests/test_typst_toolchain.py \
  tests/test_m2_00_spike.py tests/test_m2_00_spike_fixtures.py \
  tests/test_final_report_v2.py -q
```

Matrice reale dei tre workflow a 1/3/5 anni: inventario, pagine PDF vs misura,
titolo, A4 verticale, font/vettori, margini, indice, copertura degli Allegati e
cleanup. Note manuali su ogni pagina estratte dal PDF, rifiuto di overflow,
prosa che cambia il reflow, metadata ostili, font/asset e definizione inventario
modificati, limiti del JSON derivato. Fixture esclusivamente sintetiche.

Prima suite combinata: **235 passed, 147 warnings in 159.82s**.
I completamenti successivi aggiungono confronto a sette periodi, fingerprint
dell’inventario e limiti byte/file. Suite mirata finale sul codice aggiornato:
**34 passed, 2 warnings in 112.57s** (28 planner/composizione e 6 inventario).
Quattro test sono successivi alla prima suite combinata: **239 test distinti
passati** nelle due verifiche, con 205 regressioni di dossier/base/runtime/grafici.
Review indipendente Terra high approvata, compresi gli ultimi completamenti
dei fingerprint e dei cap prima dello staging. Checksum del bundle e diff check
verificati. I warning sono deprecazioni preesistenti.

Questa composizione congela il perimetro canonico attuale e le metriche per
M2-00C; non è il template editoriale definitivo M2-02 né un export finale.
Scoring, pareggio e composizioni complete hanno ancora bisogno di un blocco
canonico dedicato: l’audit delle fonti M2-03/M2-02A conferma che esistono alcuni
risultati nei servizi, ma non nel contratto v2. Un’estensione cambia le fonti e
richiede un nuovo piano prima del collaudo definitivo. Il renderer non importa
quei servizi per completare numeri mancanti. Segue M2-00C per note automatiche,
persistenza manuale/AI e client v2; poi template finale e gate di export.
Container e conformità PDF/A restano nei moduli di packaging/collaudo.
