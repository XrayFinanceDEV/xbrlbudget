# 11 — Piano di validazione del corpus senza spreco di API

Data piano: 2026-07-15  
Stato: **eseguito offline il 2026-07-15; nessuna chiamata API effettuata**.

## 1. Scopo

Usare tutti i bilanci già presenti in `Test/`, i dump, le cache e i DB batch come
regressione ripetibile. Il corpus non deve limitarsi a dimostrare
`Attivo == Passivo`: deve verificare la fedeltà contabile lungo tutte le route e
l'idoneità all'infrannuale.

Inventario iniziale deduplicato per SHA-256:

| Tipo | Contenuti unici |
|---|---:|
| PDF | 112 |
| XBRL | 15 |
| CSV | 1 |
| **Totale** | **128** |

I file fisici sono 205 per la presenza di copie, cartelle di lavoro e fixture. Il
manifest deve usare l'hash come identità e conservare tutti i path alias.

## 2. Gerarchia delle fonti di verità

Non tutti gli output esistenti sono affidabili. L'ordine delle evidenze deve essere:

1. XBRL nativo ufficiale e fatti con contesto non ambiguo;
2. totali e righe leggibili direttamente nel documento sorgente;
3. coppie dello stesso bilancio in formati diversi;
4. fixture approvate manualmente con riferimento a pagina/riga;
5. cache di estrazioni precedenti come candidati da verificare;
6. DB batch e output LLM soltanto come evidenza di regressioni, mai come ground truth
   automatica.

Il pareggio ottenuto dal codice corrente non è una fonte di verità.

## 3. Schema del manifest

Un record per hash, con struttura concettuale:

```json
{
  "sha256": "...",
  "paths": ["Test/..."],
  "format": "pdf|xbrl|csv",
  "route_expected": "ivcee|trial_balance|xbrl|csv|unsupported",
  "subtype": "contrapposte|scanned|garbled|partial|full|...",
  "entity": "...",
  "year": 2023,
  "period_months": null,
  "source_controls": {
    "assets_gross": null,
    "contra_assets": null,
    "assets_net": null,
    "liabilities_net": null,
    "income_explicit": null,
    "income_recomputed": null
  },
  "fixed_assets": {
    "intangible_gross": null,
    "intangible_funds": null,
    "intangible_net": null,
    "tangible_gross": null,
    "tangible_funds": null,
    "tangible_net": null
  },
  "expected_fields": {},
  "allowed_negative_fields": [],
  "max_estimated_amount": 0,
  "status": "verified|open|unsupported",
  "evidence": [{"page": 1, "row": "...", "note": "..."}]
}
```

I campi non ancora verificati restano `null`; non vanno riempiti con l'output
corrente. Lo stato `open` permette di ampliare gradualmente la verità del corpus
senza fingere una copertura completa.

## 4. Livelli di test

### Livello A — classificazione e periodo

- formato e route attesi;
- scanned/test layer/garbled rilevati senza confonderli;
- esercizio e mesi dedotti dal documento;
- nessun `period_months=12` trattato come infrannuale;
- duplicati riconosciuti per hash.

### Livello B — ricostruzione dei fatti

- numero di righe e massa monetaria spiegata;
- importi spezzati ricomposti;
- Dare/Avere e segno;
- subtotali e totali conservati come controlli;
- coordinate/provenienza disponibili;
- nessun valore inventato per chiudere il bilancio.

### Livello C — classificazione e netting

- voce IV CEE attesa per i fatti verificati;
- lordo/fondo/netto per classe;
- nessun ammortamento CE trattato come fondo;
- nessun doppio netting su IV CEE già netto;
- classificazioni sconosciute esplicite.

### Livello D — invarianti del bilancio

- Attivo = Passivo;
- risultato esplicito = risultato CE ricalcolato = `sp13`;
- aggregati = dettagli;
- segni ammessi;
- totale netto = totale lordo - contropartite documentate;
- plug economico nullo per gli import accettati.

### Livello E — persistenza

- round-trip completo di ogni campo;
- validation report e provenance persistiti;
- hash e versione parser associati;
- `success` tecnico distinto da `forecastable`.

### Livello F — infrannuale e downstream

- selezione esatta dei mesi;
- CE YTD + mesi residui;
- roll-forward SP per classe;
- CE = `sp13` senza plug;
- fabbisogno finanziario esplicito;
- promote e cash flow rispettano lo stato di validazione.

## 5. Matrice minima di copertura

| Classe | Obiettivo iniziale |
|---|---|
| Route C leggibile | tutti i 27 file nel manifest |
| Contrapposte | tutti i file della cartella, compreso 337 |
| Garbled | almeno un truth set per ogni famiglia font/layout |
| Scansionati | fixture da cache locale, senza nuova API |
| IV CEE A/B | verifica tramite cache/DB e coppie XBRL; riestrazione soltanto dopo approvazione costi |
| XBRL | tutti i 15 file e tutte le annualità/periodi |
| CSV | il file BILAQ reale più fixture TEBE |
| Infrannuale | periodi 3, 6, 9 e 11 mesi, più mismatch e annuale rifiutato |
| Persistenza | almeno un caso per route e uno con tutti i dettagli non zero |

## 6. Regressioni bloccanti note

### 337

```text
sp02 immateriali nette: 3.239,12
sp03 materiali nette: 5.184,73
sp13 utile: +4.287,23
totale IV CEE netto: 253.076,09
fondo immateriali: 0
```

È vietato ottenere `680,12`, `-372.733`, un plug materiale o un pareggio derivato da
una compensazione.

### Route C con plug o breakdown materiali

Priorità di verifica manuale/cross-format:

- `budget_330`: plug 100%, debiti tipizzati mancanti;
- `budget_435`: plug 45,31%, gap crediti/debiti;
- `budget_367`: plug 12,39%;
- `budget_342`: plug 7,83% e sottotipo debiti negativo;
- `budget_249`, `188`, `338`, `BILANCIO-TEST`, `169`;
- 343, 348, 395 e 405: pareggio senza plug ma breakdown materialmente incoerente;
- 373, 374, 375, 229 e 243: grandi divergenze nei sottotipi.

I numeri servono a ordinare l'audit, non a essere copiati come verità.

### XBRL

Priorità:

- facts negativi inattesi in `04171640248-20251231.xbrl` e `budget_389`;
- grandi gap in `budget_414`, `budget_399` e `budget_407`;
- fixture sintetica con annuale e nove mesi nello stesso anno.

## 7. Runner e report richiesti

Un solo comando locale deve produrre almeno:

- conteggio per route e stato;
- confronto campo per campo con il manifest;
- scarto SP, scarto CE↔SP e scarto aggregati/dettagli;
- totale e percentuale di massa stimata/non classificata;
- valori negativi fuori whitelist;
- campi persi nel round-trip;
- periodo selezionato per ogni XBRL/infrannuale;
- elenco di differenze rispetto alla baseline precedente.

Il report deve distinguere:

```text
PASS_VERIFIED       verità sorgente rispettata
PASS_STRUCTURAL     invarianti rispettati, truth parziale
REVIEW_REQUIRED     import leggibile ma conflittuale/incompleto
REJECTED            non sicuro da persistere/usare
UNSUPPORTED         formato esplicitamente non supportato
```

`MASK` non deve essere contato come successo.

## 8. Politica API e costi

- nessuna API nei test automatici;
- riuso di dump/cache esistenti come input congelato;
- prima esecuzione sempre deterministica;
- eventuale OCR/LLM esterno soltanto per contenuti unici ancora `open`, dopo report
  di copertura e autorizzazione esplicita;
- cache obbligatoria per hash + versione prompt/modello;
- una risposta esterna non diventa ground truth senza verifica contabile;
- confronto di estrattori basato su verità della fonte e coverage, mai sul solo
  pareggio.

## 9. Criteri di completamento del corpus

Il lavoro di validazione è concluso quando:

1. tutti i 128 contenuti unici hanno un record manifest;
2. tutti i route C, XBRL e CSV hanno almeno route, periodo e controlli strutturali;
3. i casi critici hanno valori sorgente bloccanti documentati;
4. la suite completa viene raccolta ed eseguita;
5. ogni modifica produce un report differenziale ripetibile;
6. nessun import `PASS_VERIFIED` contiene plug, mismatch o negativi non ammessi;
7. i file `open` restano visibilmente aperti e non alimentano il forecast.

Questo piano permette di migliorare le regole su famiglie di documenti, misurando
ogni effetto sul corpus già pagato e impedendo che un fix per un caso sposti l'errore
su un altro.
