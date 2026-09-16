# Typst toolchain (sviluppo) — M2-00A

Installatore **riproducibile** del compilatore Typst per lo spike M2-00.
Nessun binario finisce in git: `bin/` (binario installato, `.install-state`
di provenienza, LICENSE/NOTICE dell'asset) e `download/` (scratch
dell'installer: l'archivio scaricato vive solo in una `run.*` temporanea,
cancellata all'uscita) sono ignorati (`.gitignore`). Il packaging definitivo
nel container backend **non** è qui:
quello è il task **M2-06B**. Questo strumento serve solo a sviluppo/CI locale
e allo spike, così che runtime, template e grafici non vengano scritti contro
un `typst` preso a caso dal sistema.

## Che cosa è fissato

`manifest.json` è l'unica fonte di verità, versionata:

| Campo | Valore |
|---|---|
| versione | `0.15.1` (canale stable, release ufficiale typst/typst) |
| asset | `typst-x86_64-unknown-linux-musl.tar.xz` (Linux x86_64, statico musl) |
| URL | `https://github.com/typst/typst/releases/download/v0.15.1/typst-x86_64-unknown-linux-musl.tar.xz` |
| SHA-256 | `a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c` (dal digest della release ufficiale GitHub) |
| licenza | Apache-2.0 (Typst) |

Cambiare versione = modificare `manifest.json` in un commit revisionato
(con il nuovo digest), mai con flag degli script.

## Installare (serve rete)

```bash
bash tools/typst/install.sh          # download + verifica + installazione
bash tools/typst/verify.sh           # controlla ciò che è installato
tools/typst/bin/typst --version      # il binario installato
```

L'installer, in ordine: gate di piattaforma (Linux x86_64), download in un
file temporaneo dentro `tools/typst/download/` (ignorato), **verifica SHA-256
prima di estrarre**, **scansione dei membri dell'archivio prima
dell'estrazione** (percorsi assoluti, `..`, symlink/hardlink e file speciali
vengono rifiutati), estrazione in directory temporanea (`--no-same-owner`),
controllo di `typst --version` contro la versione fissata, installazione
atomica in `tools/typst/bin/typst` con registrazione di provenienza in
`bin/.install-state`. È **rieseguibile** e stampa sempre versione e checksum
(attesi e reali). Non esiste alcun percorso curl-pipe-shell: l'archivio viene
scaricato, misurato, poi estratto.

Dipendenze: `tar`, `xz`, `python3`, `curl` o `wget`, `sha256sum` (o `shasum`).
Macchine non Linux/x86_64 escono con un errore esplicito: per quelle servirà
un asset diverso, deciso in M2-06B, mai un binario "del sistema".

## Verifica offline (cosa fa Pi-B)

Dopo un'installazione riuscita, `verify.sh` non tocca la rete. L'ordine dei
controlli è un contratto: **il binario viene eseguito solo dopo che è stato
provato che è ancora byte per byte quello misurato dall'installer**.

1. manifesto leggibile (versione, asset, sha256 fissati);
2. `bin/typst` esiste ed è eseguibile;
3. `bin/.install-state` esiste, è ben formato (righe `key=value`) e contiene
   **tutte** le chiavi richieste (`typst_version`, `asset`, `asset_sha256`,
   `binary_sha256`, `source_url`) — provenienza mancante o malformata è un
   errore, **non un avviso**: un binario che nessuno può certificare è un
   binario non verificato;
4. la provenienza coincide col manifesto pinato (versione → uscita 4; asset e
   digest d'archivio e URL sorgente → uscita 1); chiavi duplicate o sconosciute
   nella provenienza sono rifiutate prima di eseguire il binario;
5. la SHA-256 del binario coincide con `binary_sha256` registrato (uscita 1) —
   un binario manomesso si ferma **qui**, prima di ogni esecuzione;
6. solo ora si esegue `typst --version`, che deve riportare esattamente la
   versione pinata (uscita 4).

Per verificare un archivio scaricato a mano, senza script:

```bash
sha256sum typst-x86_64-unknown-linux-musl.tar.xz
# deve stampare a6d077d0a95eed5a2eba715b2dae06be954f624ccbf85758a03f389ded33118c
```

Il digest si confronta anche con la pagina della release
(`https://github.com/typst/typst/releases/tag/v0.15.1`). Un artefatto alterato
fa uscire l'installer con codice 3 **prima** di estrarre qualsiasi cosa; un
archivio che passa il checksum ma contiene membri pericolosi (percorsi
assoluti, `..`, link, file speciali) viene rifiutato **prima**
dell'estrazione.

## Codici di uscita

| Codice | install.sh | verify.sh |
|---|---|---|
| 1 | uso/manifesto/dipendenza/rete/estrazione/membri non sicuri | manifesto/strumenti/binario mancante · provenienza assente, malformata o in contrasto col manifesto (asset, digest d'archivio) · binario modificato dopo l'installazione |
| 2 | piattaforma non supportata | — |
| 3 | checksum non corrispondente | — |
| 4 | binario che riporta un'altra versione | versione in contrasto nella provenienza (senza eseguire il binario) o riportata dal binario già verificato |

## Test

`tests/test_typst_toolchain.py` (pytest, **senza rete**): installa/verifica
contro artefatti finti in directory temporanee, usando gli override
`TYPST_TOOL_MANIFEST` / `TYPST_TOOL_ROOT` / `TYPST_TOOL_TEST_OS|ARCH`. Gli
override cambiano *da dove* arrivano i dati, mai *se* vengono controllati: la
verifica del checksum e della versione non è disattivabile, e i default di
produzione (manifesto pinato + URL ufficiale) sono assertati da un test
dedicato. Il binario finto scrive anche un **marker di side-effect**
(`TYPST_RUN_MARKER`): i test provano così che un binario manomesso o senza
provenienza **non viene mai eseguito**, e che un archivio malevolo (traversal,
percorso assoluto, symlink, hardlink/fifo) viene rifiutato prima
dell'estrazione e prima di ogni scrittura fuori dalla root.

```bash
python3 -m pytest tests/test_typst_toolchain.py -q
```

## Confini

- Nessuna modifica a `pdf_service/`, alle route, al renderer, agli output
  dello spike M2-00.
- `Dockerfile.backend` non viene toccato: portare Typst nell'immagine
  (multi-stage, versione/checksum identici a questo manifesto, health check
  del compilatore) è **M2-06B**.
- Pacchetti/font Typst per lo spike: non di sistema, pinned e verificati —
  ma la loro fissatura appartiene ai task dello spike, non a questo.
