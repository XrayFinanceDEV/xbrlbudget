# 06 — Persistenza, round-trip e tracciabilità

> Torna all'[indice](REGOLE-IMPORT-00-INDICE.md).
> Motori: `importers/pdf_importer.py`, `database/models.py`.

## 1. Il round-trip lossless non è una promessa, è una proprietà strutturale

Il registro dei campi da salvare **non è scritto a mano**: è derivato dalle colonne del modello
dati stesso. Ogni colonna che inizia per `sp` finisce nello Stato Patrimoniale, ogni colonna che
inizia per `ce` nel Conto Economico.

La conseguenza è la ragione per cui la regola esiste:

> Un nuovo campo IV-CEE aggiunto al modello viene persistito **automaticamente**. Il registro
> non può divergere dallo schema, perché *è* lo schema.

Il costruttore precedente, scritto a mano, **perdeva silenziosamente intere famiglie di
dettaglio** — crediti verso soci, immateriali, materiali, rimanenze, fondi rischi. È il motivo
per cui i 23 esercizi nei database batch storici risultano tutti `review_required`: non per un
problema di quadratura, ma perché i dettagli erano stati persi all'epoca (`sp03` in 23 casi su
23, le riserve in 20, il personale in 18). Quei record **non sono stati riscritti
automaticamente**: una migrazione automatica inventerebbe proprio i dettagli che tutta questa
architettura vieta di inventare.

Ogni campo assente nell'estrazione vale **zero**, mai `NULL`.

### Il ponte di nomenclatura
I parser di route C usano chiavi corte (`sp03`), il database nomi pieni
(`sp03_immob_materiali`). La traduzione è esplicita, e le chiavi non mappate — i totali, i
metadati diagnostici con l'underscore iniziale — vengono **scartate**. Per questo `_plug_residual`
e simili non finiscono mai in una colonna.

## 2. I campi e la loro origine

Tutti gli importi sono `Numeric(15,2)`, default zero, non nullable (massimo circa ±10.000
miliardi).

### Attivo

| Campo | Voce | Note sull'origine |
|---|---|---|
| `sp01` | A) crediti verso soci | — |
| `sp02` / `sp03` | B.I / B.II immobilizzazioni | in route C sono il **netto** dopo il netting dei fondi |
| `sp04` | B.III finanziarie | i crediti immobilizzati **non** vanno nei crediti circolanti |
| `sp05` | C.I rimanenze | — |
| `sp06` / `sp07` | C.II crediti entro / oltre | — |
| `sp08` | C.III attività finanziarie | — |
| `sp09` | C.IV disponibilità liquide | — |
| `sp10` | D) ratei e risconti | — |

### Passivo e patrimonio netto

| Campo | Voce | Note |
|---|---|---|
| `sp11` | A.I capitale | — |
| `sp12` | riserve | **somma algebrica** dei dettagli: recupera le riserve **negative** (A.VIII utili portati a nuovo), che altrimenti gonfiano il patrimonio e si mascherano in cassa |
| `sp13` | A.IX risultato | **ancora autoritativa**: il CE viene confrontato con questo |
| `sp14` | B) fondi rischi | — |
| `sp15` | C) TFR | disambiguato dalla riga di CE "trattamento di fine rapporto" |
| `sp16` / `sp17` | D) debiti entro / oltre | **aggregati derivati**, riallineati ai dettagli in route A/B |
| `sp18` | E) ratei e risconti | — |

Le sotto-voci dei debiti tipizzano banche, altri finanziatori, obbligazioni, fornitori,
tributari, previdenza, altri.

### Conto economico
`ce01`–`ce20` secondo l'art. 2425. Da tenere presenti:

- `ce03a` (A.4 incrementi per lavori interni) e `ce11b` (B.13 altri accantonamenti) sono campi
  distinti dai rispettivi aggregati, e **non c'è deduplica automatica fra loro** (vedi pagina 04 §3);
- `ce04` (altri ricavi) e `ce12` (oneri diversi) sono le voci che *storicamente* venivano usate
  per allineare il CE allo SP — **non più**: l'allineamento è ora diagnostico;
- `ce20` (imposte): **le imposte estratte non vengono mai sovrascritte** per forzare un
  cross-check;
- `ce10` (variazione rimanenze materie): **il segno non viene mai capovolto** per forzare
  l'accordo.

### Metadati dell'anno

| Campo | Significato |
|---|---|
| `period_months` | `NULL` o `12` = anno pieno; `1`–`11` = infrannuale |
| `validation_status` | `verified` / `review_required` / `legacy` / `draft` |
| `validation_report` | JSON immutabile dei controlli contabili |
| `source_sha256` | **SHA-256 dei byte del file** |
| `parser_version` | `semantic-v2-2026-07-15` (PDF), `xbrl-context-period-v3` (XBRL) |
| `forecastable` | = `semantic_valid` |
| `original_bs_snapshot` / `original_is_snapshot` / `rettifiche_log` | stato pre-rettifiche e giornale (massimo 20 voci) |

Nel report di validazione ogni importo è serializzato **come stringa**: nessuna perdita di
precisione passando da decimale a virgola mobile.

## 3. Hash e versione: provenienza, non cache

Questo è il punto più frainteso dell'intero sottosistema, quindi vale enunciarlo chiaramente:

> **Non esiste alcuna cache di estrazione.** La coppia (hash del file, versione del parser) è
> **provenienza**, non memoization. L'import **non interroga mai** l'hash prima di estrarre.

Ricaricare lo stesso identico file **riesegue tutte le chiamate LLM** e riscrive il record. Le due
colonne servono a rispondere *a posteriori* a due domande:

- da quale file esatto vengono questi numeri?
- quale versione del parser li ha prodotti, e quindi quali righe vanno rivalidate quando la
  versione cambia?

L'anno corrente e l'anno precedente estratti dallo stesso PDF **condividono lo stesso hash**: è
l'impronta del documento sorgente, non della riga.

Il default `legacy` su `validation_status` chiude il cerchio: le righe scritte prima del
versionamento non sono dichiarate valide d'ufficio.

## 4. La cancellazione è omogenea

Un import **non** cancella "l'anno". Cancella solo i record **dello stesso tipo di periodo**:

- un import parziale rimuove solo i parziali;
- un import annuale rimuove solo gli annuali.

Parziale e annuale dello stesso anno **coesistono**, ed è voluto: un 5 mesi e il consuntivo dello
stesso esercizio sono due fatti diversi, entrambi legittimi.

## 5. Atomicità

Qualsiasi eccezione lungo la pipeline provoca il rollback completo della sessione. **Non
esistono scritture parziali.**

L'XBRL ha in più un blocco **atomico sulla quadratura**: se non quadra, rollback e HTTP 422 —
non arriva nemmeno al database. Il PDF invece salva anche un record `review_required`, perché un
bilancio di verifica leggibile ma incompleto ha comunque valore: l'utente lo corregge in
Rettifiche. La differenza è deliberata.

## 6. L'esito dell'import

Riporta il metodo di estrazione effettivamente usato — sorgente IV-CEE deterministica,
situazione contabile deterministica, CoGe-LLM, o LLM IV-CEE — la versione del parser, i warning
e un punteggio di confidenza derivato dalla confidence del router (alta 0,95 / media 0,70 / bassa
0,40).

Quel punteggio è **informativo**: nessuna decisione dipende da esso.
