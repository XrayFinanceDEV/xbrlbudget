# M2-01 — runtime isolato Typst

Implementazione diretta, review indipendenti Terra high su istruzione dell’utente
(agenti Pi impegnati). Dipendenza M2-00 approvata dalla riproduzione indipendente.

## Confine del package

`TypstRenderer.render(FinalReportModelV2, document_state, grayscale)` congela e
rivalida il JSON con hash. Riceve dati già assemblati: non legge il database,
non effettua calcoli finanziari e non invoca AI. Restituisce bytes PDF, digest,
hash del modello/fonti, versione schema/template/compilatore, pagine e durata.

Il template `runtime-smoke-1` serve esclusivamente a collaudare il processo.
Non è il dossier finale né un endpoint di esportazione. Il chiamante futuro
M2-05 deve verificare readiness economica/editoriale prima di richiedere final.
La base/font/planner segue in M2-02A; grafici M2-03, note M2-00C, template M2-02.

## Isolamento e limiti

- Solo Linux x86_64 e compilatore statico ufficiale pinato nel manifest unico.
  SHA dell’archivio già verificato dall’installer, SHA del binario verificato
  prima di ogni esecuzione. Nessun programma fornito dal modello viene eseguito.
- Bundle interno con entrypoint e allowlist SHA-256: rifiutati symlink, traversal,
  asset alterati o nomi riservati; staging dei soli file dichiarati.
- Bubblewrap senza rete, namespace nuovi, capability rimosse e ambiente vuoto.
  Root contiene solo `/report`, montato in sola lettura, e output scrivibile.
  Font di sistema ignorati e cache/pacchetti vuoti; nessun fallback senza sandbox.
- Input 8 MiB; asset totali 16 MiB/64 file; output 32 MiB/200 pagine;
  memoria virtuale 512 MiB; CPU 25 s; descriptor 128; core dump disabilitati.
- Deadline totale 30 s dall’inizio richiesta, condivisa da probe e compile;
  timeout termina il gruppo di processi e attende la terminazione. Limiti OS
  applicati da un processo Python nuovo, senza `preexec_fn` nei thread.
- Due richieste contemporanee per istanza: riusare una sola istanza per worker.
  Il deployment deve limitare anche worker e memoria complessivi. Saturazione
  immediata con categoria `renderer_busy`; slot rilasciati anche sugli errori.
- Directory temporanea privata eliminata su successi, errori e timeout.
  stdout/stderr scartati: errori pubblici italiani senza contenuto, diagnostica,
  percorsi o dati cliente. Log: sole categorie o schema/pagine/bytes/durata.

Validazione prima della restituzione: dimensione e firma/EOF PDF, parser non
riparato, assenza di cifratura/allegati incorporati, pagine A4, titolo metadata,
testo non vuoto e BOZZA su ogni pagina draft. Testo JSON rimane letterale.
Font, vettori e valori/sezioni del dossier saranno verificati dal harness M2-04.
Conformità PDF/A e cold boot del container non sono dichiarati: M2-06B.

## Riproduzione

```bash
bash tools/typst/install.sh
PYTHONPATH=.:backend /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
  tests/test_typst_runtime.py tests/test_typst_toolchain.py \
  tests/test_m2_00_spike.py tests/test_m2_00_spike_fixtures.py \
  tests/test_final_report_v2.py -q
```

Il test integration richiede il binario pinato installato; `TYPST_TEST_BINARY`
consente una posizione alternativa con lo stesso hash. I test reali comprendono
tre workflow × bozza/finale × colore/grigi, determinismo bytes, injection di
markup come testo, accessi esterni/import offline negati, compiler/asset alterati,
limiti input/output, timeout con pulizia, terminazione del discendente e
saturazione concorrente. Docker Desktop non è integrato nella distro WSL locale:
il collaudo qui riguarda processi Linux isolati, non un container distribuito.

Verifica locale completa: **117 passed**, inclusi **42 test runtime**,
42 toolchain/spike e 33 dossier v2. Warning delle dipendenze già presenti.
Prima review Terra high approvata (42 runtime test, 11,98 s).
Seconda review indipendente Terra high obbligatoria approvata (42/42, 9,45 s):
nessun blocco; verificato anche rifiuto FIFO senza attesa. Gate M2-01 superato.
