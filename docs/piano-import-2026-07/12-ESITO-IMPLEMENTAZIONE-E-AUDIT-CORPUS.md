# 12 — Esito implementazione e audit del corpus

Data: 2026-07-15  
Branch: `fix/import-netting-2026-07`  
Politica di esecuzione: **solo locale, zero chiamate OCR/vision/LLM**.

## 1. Risultato

La pipeline non considera più la quadratura aritmetica come prova sufficiente di
correttezza. Il risultato CE, lo stato patrimoniale, le gerarchie aggregato/dettaglio,
i residui e il periodo sono ora controlli distinti. Un numero dichiarato, un residuo
o un totale non possono più modificare automaticamente utile, cassa, debiti, riserve,
ricavi o costi.

Il caso 337 è bloccato come regressione sorgente:

```text
sp02 immateriali nette     3.239,12
sp03 materiali nette       5.184,73
sp13 utile                 4.287,23
totale IV CEE netto      253.076,09
plug                           0,00
```

Il 405 non è più un falso positivo: i valori netti delle immobilizzazioni restano
quelli documentati, ma il residuo non spiegato di 182.837,69 euro non viene cancellato
dopo il netting. Il file resta `review_required` e non può alimentare il forecast.

## 2. Correzioni implementate

### Algebra e validazione

- formula CE unica in `calculations/ce_result.py`, usata da ORM, import, quadratura,
  budget ordinario e infrannuale;
- inclusi A.4 (`ce03a`), B.13 (`ce11b`) e D.18/D.19 (`ce17a/b`) senza doppio conteggio;
- `check_quadratura` distingue SP, CE↔SP, estrazione vuota, residuo mascherato,
  gerarchie e validità semantica;
- riconciliazione e allineamento CE/SP sono diagnostici e non mutano più i dati.

### Route C, contrapposte e testo corrotto

- ricostruzione delle righe da coordinate, con ricomposizione degli importi spezzati;
- correzione generica dell'orientamento fisico costi/ricavi;
- netting immobilizzazioni per classe;
- eliminazione dei plug best-effort in `sp09` e `sp16`;
- eliminazione dell'azzeramento post-netting di `_plug_residual`;
- controlli dichiarati trattati come evidenza, non come destinazione di una differenza.

Sui nove PDF della cartella specifica, otto hanno estrazione locale non vuota: sette
restano quadrati con i valori sorgente verificati, mentre il 405 è correttamente
mascherato/revisionabile. `Bilancino 31-5-26.pdf` contiene solo immagini e resta
`UNSUPPORTED_LOCAL_OCR` perché non esiste una fixture OCR locale: non sono stati
inventati valori e non è stata usata un'API.

### XBRL e CSV

- identità del periodo XBRL basata su entità, date, durata e dimensioni;
- annuale e infrannuale dello stesso anno non si sovrascrivono;
- selezione deterministica di contesto e unità;
- aggiunte le tassonomie mancanti per B.13 altri accantonamenti, B.10.c, B.10.d e
  A.2 comprensivo dei lavori in corso su ordinazione;
- derivazione entro/oltre ammessa soltanto da totale pubblicato + altra scadenza
  pubblicata + dettagli corroboranti, e solo se migliora l'invariante SP;
- conflitti aggregato/dettaglio restano diagnostici;
- CSV BILAQ reale riconosciuto per intestazione ed encoding Windows, senza posizioni
  di colonna fisse.

Queste regole hanno ridotto gli XBRL nativi rifiutati da 9 a 6. I casi recuperati
non sono stati promossi artificialmente a verificati: restano `review_required`
quando mancano breakdown affidabili.

### Persistenza e infrannuale

- mapping PDF basato sulle colonne ORM e round-trip DB lossless;
- persistiti stato di validazione, report, hash, versione parser e `forecastable`;
- periodo parziale esatto da 1 a 11 mesi, senza fallback annuale;
- l'API consente più periodi dello stesso anno e normalizza 12 mesi a esercizio pieno;
- CE YTD e SP YTD separati correttamente; `ce09a→sp02`, `ce09b→sp03`, nessun
  ammortamento automatico su `sp04`;
- nessuna destinazione automatica dell'utile a riserve e nessuna ripartizione 40/60;
- fabbisogno non coperto esposto senza creare debito;
- budget ordinario bloccato su sorgente semanticamente insicura, investimento totale
  non più diviso 50/50 e differenze dei debiti non più attribuite alle banche;
- promozione di una proiezione consentita solo dopo validazione semantica completa.

## 3. Audit offline corrente

Il comando ripetibile è:

```powershell
python tests\corpus\audit_pipeline.py
```

Copertura: 205 file fisici, 128 contenuti unici (112 PDF, 15 XBRL, 1 CSV).

| Stato sorgenti uniche | Numero |
|---|---:|
| `PASS_VERIFIED` | 1 |
| `PASS_STRUCTURAL` | 15 |
| `REVIEW_REQUIRED` | 21 |
| `REJECTED` | 6 |
| `UNSUPPORTED` | 5 |
| `UNSUPPORTED_LOCAL_OCR` | 1 |
| `NOT_REEXECUTED_NO_API` | 79 |

Dettaglio delle route eseguite localmente:

| Route | Esito |
|---|---|
| Route C | 15 strutturali, 12 da revisionare |
| XBRL nativo | 9 da revisionare, 6 rifiutati |
| CSV nativo | 1 verificato e forecastable |
| PDF IV CEE A/B | 79 non rieseguiti per evitare nuove API |

I 23 esercizi presenti nei database batch già pagati sono stati riesaminati con il
validator corrente: tutti risultano `review_required`. La causa prevalente non è il
pareggio SP, ma la perdita storica dei dettagli durante la persistenza manuale
(`sp03` in 23/23, riserve in 20/23, personale in 18/23). Il nuovo mapping lossless
impedisce la regressione; i record storici non sono stati riscritti automaticamente.

Il report completo locale viene scritto in:

```text
Test/_analysis/current_logic_audit.json
Test/_analysis/current_logic_audit.md
```

## 4. Test

Risultato finale:

```text
109 passed, 3 skipped, 0 failed
```

Gli skip sono fixture sorgente non disponibili/diagnostiche; non ci sono chiamate API
nei test. Il corpus contrapposte e le route native vengono eseguiti realmente.

## 5. Limiti residui espliciti

1. I 79 PDF IV CEE A/B non sono stati riestratti: serve riusare una cache strutturata
   con tutti i campi oppure autorizzare una nuova estrazione per hash. I vecchi DB
   batch possono essere rivalidati, ma non equivalgono alla fonte a causa della
   persistenza lossless mancante all'epoca.
2. Sei XBRL hanno ancora conflitti sorgente/mapping su aggregati di crediti/debiti o
   sul confronto SP. Restano rifiutati; non è stato applicato un plug.
3. Dodici route C restano da revisionare per copertura o gerarchie insufficienti.
   I principali sono 330, 435, 342, 405, 188, 375, 373, 374, 338, 169 e 367.
4. Il PDF esclusivamente scansionato richiede una fixture OCR locale verificabile o
   un'autorizzazione separata; finché manca, il comportamento corretto è il rifiuto.
5. I record batch storici vanno reimportati o corretti esplicitamente; una migrazione
   automatica inventerebbe proprio i dettagli che questa modifica vieta.

Questi limiti sono parte del risultato: nessuno è contato come quadratura riuscita.
