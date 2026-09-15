# M2-00 — confronto Typst e decisione tecnica

Data: 2026-09-15. Base: M2-00A `db8c97b`.
Spike implementato in directory dedicata; nessuna route o servizio PDF di
produzione modificato. La riproduzione locale è completata, la review
indipendente Pi-B prevista dal piano resta da svolgere.

## Scelta

Proposta tecnica: **primitive native Typst** per i sei grafici del report.
CeTZ-Plot è compatibile con tutti i casi provati, ma aggiunge tre pacchetti e
un asset WASM e richiede più tempo e memoria. Primaviz 0.10.0 non viene scelto:
le sue linee multi-serie non accettano null e il dominio delle barre negative
resta limitato a zero. Adeguarlo richiederebbe un adapter ulteriore non presente
nella versione confrontata; lo spike non altera il pacchetto né i dati.

## Ambiente e metodo

Linux WSL2 `6.6.87.2-microsoft-standard-WSL2`, x86_64, AMD Ryzen 7 7730U.
Typst `0.15.1 (9dfd3a08)`, verificato dal manifest M2-00A; `--jobs 1`.
Tutti i processi di confronto sono avviati con
`unshare --user --map-root-user --net`. Font di sistema esclusi;
Libertinus Serif incorporato nel compilatore. Snapshot sintetici M1 validati
con hash, senza modificare i JSON canonici.

36 compilazioni: tre candidati × annuale 1 anno / infrannuale 3 anni / startup
5 anni × finale / bozza × colore / grigi. Sei ripetizioni in nuovi processi.
Non viene svuotata la page cache del sistema: le misure sono prima esecuzione e
ripetizione con cache filesystem, non prove di cold boot del container.
`/usr/bin/time` misura RSS del compilatore; il tempo include avvio del namespace.

Campioni: denominazioni lunghe, sei grafici, null, negativi, zeri, 18 rettifiche,
tabelle con sei prestiti e otto differenze temporanee, matrice delle ipotesi
strutturate e chiusura infrannuale con segnali extra-contabili. Sono stress di
rendering; non esempi di coerenza contabile o di previsioni reali.

## Risultati locali

| Candidato | Report validi | Tempo osservato | Picco RSS massimo | Dimensione PDF | Pagine |
|---|---:|---:|---:|---:|---:|
| Native | 12/12 | 0,152–0,256 s | 44,12 MiB | 145.554–181.591 byte | 10 |
| CeTZ-Plot | 12/12 | 0,879–1,384 s | 104,57 MiB | 152.744–188.469 byte | 10 |
| Primaviz | 0/12 | interrotto sui null | 41,12 MiB prima del fallimento | — | — |

I tempi di Primaviz non vengono confrontati con compilazioni riuscite.
Misure grezze versionate in [`M2-00-results.json`](M2-00-results.json).
Sono misure di sviluppo, non limiti operativi concordati o benchmark di carico.

Otto probe isolati per candidato: i sei grafici startup, barre negative a un
anno e serie interamente null. Native e CeTZ: **8/8 compilano**.
Primaviz: **4/8 compilano** (risultati economici, cashflow, liquidità/debito,
barre negative); margini, giorni, coperture e all-null falliscono.
Il caso completo liquidità/debito fornisce anche una prova riuscita di linee
Primaviz, evitando di dedurne il comportamento dalle sole compilazioni fallite.

Il codice upstream Primaviz `src/charts/line.typ` passa gli elementi `none` a
`calc.min/calc.max`; il compilatore risponde `cannot compare float and none`.
`src/charts/bar.typ` calcola il dominio con minimo zero anche per valori negativi:
il campione compila ma mostra le barre negative sotto l'asse, nella zona delle
etichette, senza tacche negative. Gli SVG dei tre candidati sono inclusi nel
confronto HTML e sono estratti dai PDF realmente compilati.

## Verifica semantica e riproduzione

Tutti i 24 PDF riusciti hanno firma `%PDF-`, A4, font incorporati con mappature
Unicode, testo estraibile, vettori e **zero immagini raster**. Il controllo legge
il contenuto sia con Poppler sia con PyMuPDF per gestire la lettura delle celle
multilinea; normalizza solo whitespace, apostrofi e segni meno tipografici.
Verifica titoli del corpo (non solo indice), hash, valori dei grafici e rettifiche,
sezione infrannuale condizionale, assenza di pagine vuote e watermark BOZZA su
ogni pagina della bozza. Intestazioni tabella ripetute osservate nei campioni.

Riproduzione con directory output vuota e nuova cache estratta dagli archivi
ricontrollati: **36 esiti identici e 24 PDF validi identici byte per byte**.
È stata usata la stessa installazione verificata del compilatore; non è una
review indipendente su una seconda macchina. Il timestamp di creazione PDF è
fissato, non è quello dello scenario di un cliente.

Controllo negativo: un import non disponibile in entrambe le cache non può
essere scaricato nel namespace senza rete e la compilazione termina con errore
DNS. Nessun download viene effettuato durante le compilazioni riuscite.

Gate pytest mirato: **80 passed**, un warning preesistente `python_multipart`.
Il test semantico fallisce realmente quando viene rimosso il titolo di una
sezione dal corpo, anche se resta nell'indice, o quando viene richiesto un
valore assente. Test aggiuntivo: archivio pacchetto alterato rifiutato prima
dell'estrazione. HTML verificato con Chrome esclusivamente in sviluppo su
viewport 1440, 768 e 390 px: nessun overflow della pagina, sezioni condizionali,
sei SVG per percorso, stati bozza/grigi e tutti i 12 PDF incorporati validi.
Il confronto HTML mostra tre candidati per ognuno degli otto probe.

## Versioni, asset e licenze

| Asset | Versione | Licenza | Distribuzione dello spike |
|---|---|---|---|
| Typst | 0.15.1 | Apache-2.0 | binario pinato M2-00A, ignorato da git |
| Libertinus Serif | incorporato nel binario pinato | SIL OFL 1.1 | `--ignore-system-fonts`, nessun font esterno |
| CeTZ-Plot | 0.1.4 | LGPL-3.0-or-later | archivio registry con SHA-256 pinato |
| CeTZ | 0.5.2 | LGPL-3.0-or-later | archivio registry, include `cetz_core.wasm` |
| oxifmt | 1.0.0 | MIT OR Apache-2.0 | dipendenza transitiva di CeTZ |
| Primaviz | 0.10.0 | MIT | archivio registry con SHA-256 pinato |

Versioni/digest in `tools/typst/spike/packages.json`, licenze lette dai manifest
dei pacchetti. I digest sono misurati sugli archivi ufficiali, non firme
indipendenti del produttore. Gli archivi e il WASM non vengono committati.
La soluzione native non aggiunge pacchetti e usa esclusivamente primitive Typst.

Font: [licenza upstream Libertinus](https://github.com/alerque/libertinus/blob/master/OFL.txt).
Pacchetti: [CeTZ-Plot](https://typst.app/universe/package/cetz-plot/),
[Primaviz](https://typst.app/universe/package/primaviz/).
La finalizzazione del bundle asset/font resta M2-02/M2-06B.

## PDF/A e passi successivi

`--pdf-standard a-2u` compila il campione startup native e CeTZ e i PDF passano
gli stessi controlli semantici. **Non viene dichiarata conformità PDF/A**:
veraPDF non è installato e non è stata effettuata validazione formale.
Riferimento: [profili PDF supportati da Typst](https://typst.app/docs/reference/pdf/).

Lo spike fornisce evidenza favorevole all'adozione di Typst con primitive native.
Prima dell'integrazione di produzione servono review indipendente dello spike,
runtime/sandbox M2-01, template definitivo M2-02 e successivi gate. I controlli
del processo in questo harness non sostituiscono timeout, cleanup, concorrenza
e limiti input/output del renderer di produzione.

Riproduzione e generazione dei due HTML:
[`tools/typst/spike/README.md`](../../tools/typst/spike/README.md).
La pubblicazione Orca del link pubblico è stata rifiutata con
`artifact_sharing_disabled`; i due HTML autosufficienti sono consegnati localmente.
