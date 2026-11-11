# Fase 6 — la struttura dal modello, verificata dalle somme — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** che un bilancio di un gestionale mai visto si importi bene al primo colpo, senza una regola nuova nel lettore
per ogni layout. Oggi la **struttura** del documento (quali colonne sono periodi, quali righe sono titoli, totali,
conti, dove cominciano SP e CE) la decide il codice con regole sulla geometria; il modello entra solo dopo, per la
voce di ogni conto. Ogni gestionale nuovo rompe una di quelle regole (lotto di novembre: colonna dei totali presa
per l'anno precedente, titoli a lettere spaziate, CE senza titolo, conti d'ordine, interi col meno in coda, scadenza
«a) Entro 12 mesi»). La Fase 6 fa proporre la struttura a Qwen **quando le regole non bastano**, e la accetta solo se
le somme stampate la confermano.

**Il principio, invariato:** il modello non decide mai un importo. Propone ruoli (di colonne e di righe) e sezioni;
gli importi restano quelli letti dal testo (o dalle celle MinerU); la parentela la decidono i totali stampati
(`totali.marca_totali`); l'adozione passa dallo stesso cancello `deterministico.esito`. Una struttura che non fa
tornare le somme si scarta e si dichiara.

**Architecture:** il punto d'innesto è il `Profilo` (`importers/lettore/profilo.py`): è già l'oggetto con le decisioni
che il lettore di righe consuma senza rifarle (colonne con ruolo e periodo, coppie parziali/totali, confine dei lati,
sezione e parte di ogni riga fisica, righe scartate). La Fase 6 aggiunge una seconda fonte del profilo:

```
PDF -> profilo dalle regole -> righe -> foglie -> guardia -> classi -> cancello
                     \ se la guardia rinuncia o il cancello rifiuta per un motivo di lettura:
                      -> vista compatta del documento -> Qwen: profilo proposto (JSON guidato)
                      -> profilo corretto -> righe -> foglie -> guardia -> classi -> stesso cancello
```

**Tech Stack:** `importers/lettore/*`, `importers/import_snello/*`, Qwen su gx10 (`llm_provider.chiama_gx10_json`, JSON
guidato), pytest con Qwen finto, `tests/corpus/foglie_campione.py`, `tests/corpus/punteggio.py`.

## Global Constraints

- **Mai un importo dal modello**; il modello non vede altro che il testo delle righe e la posizione delle celle
  (colonna), e risponde con ruoli e sezioni per id.
- **Le somme decidono**: il profilo proposto si accetta solo se dopo la rilettura la guardia passa (foglie in pari) e il
  cancello adotta; altrimenti resta l'esito di oggi, e il report dichiara il tentativo.
- **Solo dove le regole falliscono**: un documento che oggi il lettore adotta non chiama mai il profilo dal modello.
  «Numeri invariati» sugli adottati e sui lettori deterministici.
- **Interruttore** `IMPORT_STRUTTURA_MODELLO` (spento per default fino alla misura); tetto di chiamate dichiarato.
- Dati dei clienti mai in git (test con PDF sintetici, numeri inventati); gx10 solo per le misure, un giro alla volta;
  PyMuPDF < 2; regole di sempre (CRLF, parser congelati, niente `git add -A`).

## Review Focus

1. Un profilo del modello che fa quadrare un documento che si contraddice da solo (1410, 289, 138, 152, 161): il
   cancello lo deve ancora vedere (totali stampati contro composti).
2. Un profilo che cambia un documento già adottato: non deve succedere (il percorso non lo chiama).
3. Variabilità: la stessa domanda due volte dà due profili; un peggioramento si conferma su 3 giri.

---

### Task 0: la misura che conta — lotti nuovi, primo colpo

- [ ] Un lotto «mai visto» con le verità: i bilanci che arrivano in `budget-corpus/inbox/` (novembre 2026 e i
      successivi), letti due volte alla cieca e riconciliati come il campione (`lotto: "inbox-<mese>"`).
- [ ] Nel rapporto di `punteggio.py`: la quota di documenti di un lotto nuovo importati quadrati e con le macro giuste
      **al primo giro sul codice di quel giorno**, prima di ogni correzione. È il numero che dice se ci stiamo
      avvicinando a un importatore generico; il campione resta la rete contro le regressioni.
- [ ] Base: il lotto di novembre sul codice di `main` prima della Fase 6.

### Task 1: la vista compatta del documento

**Files:** Create `importers/lettore/vista.py`; Test `tests/lettore/test_vista.py`.

- [ ] Dal `Documento` letto con le regole: per pagina, le righe con id, testo (codice + etichetta, troncato), e per ogni
      colonna di valori un segno «c» se la riga ha una cella lì (mai l'importo). Le colonne con x, ruolo e periodo
      proposti dalle regole e le testate stampate sopra.
- [ ] Dimensione: un documento di 9 pagine sta in un blocco; oltre, a blocchi di pagine con le testate ripetute.

### Task 2: lo schema del profilo proposto

**Files:** Create `importers/lettore/profilo_modello.py`; Test `tests/lettore/test_profilo_modello.py`.

- [ ] JSON guidato: per colonna `ruolo` ∈ {corrente, precedente, totali_della (indice), differenza, percentuale,
      ignora}; per riga `tipo` ∈ {titolo_SP, titolo_CE, titolo_attivo, titolo_passivo, titolo_costi, titolo_ricavi,
      voce, conto, totale, risultato, fuori} («fuori» = nota, conti d'ordine, anagrafica, testata); per pagina la
      sezione. Il prompt spiega le forme (coppie parziali/totali, contrapposte, verifica) senza nomi di gestionali.
- [ ] Validazione: enum per id, colonne esistenti, una sola corrente; risposta fuori schema = nessun profilo.

### Task 3: il profilo corretto applicato al documento

**Files:** Modify `importers/lettore/righe.py` (`leggi_pdf`), `profilo.py`; Test `tests/lettore/test_profilo_modello.py`.

- [ ] `leggi_pdf(path, correzioni=...)`: il profilo dalle regole, poi le correzioni del modello sovrascrivono ruolo e
      periodo delle colonne, coppie, sezione e parte delle righe, righe scartate; le righe si rileggono su quel profilo
      e `marca_totali` rifà la parentela dalle somme. Nessun importo cambia.
- [ ] Test sintetici: un documento con la colonna dei totali senza segni distintivi (le regole la prendono per un
      periodo) e un CE senza titolo; col profilo corretto le foglie tornano in pari.

### Task 4: l'innesto nel percorso del lettore

**Files:** Modify `importers/lettore/percorso.py`; Test `tests/lettore/test_percorso.py`.

- [ ] Quando la guardia rinuncia (`foglie_non_in_pari`, `senza_foglie_sp`) o le foglie restano con sezione, lato o
      verso ignoti in quantità, o il cancello rifiuta per `massa_non_classificata` / `oltre_soglia`: una chiamata per il
      profilo proposto, rilettura, stesso percorso fino al cancello. Al più un tentativo (più uno con la nota «le somme
      non tornano» se il primo non porta la guardia in pari).
- [ ] Report: `struttura_modello` con esito, chiamate, campi cambiati (conteggi, mai etichette o importi).
- [ ] Interruttore `IMPORT_STRUTTURA_MODELLO`; spento = percorso identico (test).

### Task 5: misura

- [ ] Offline: strumento delle foglie con Qwen finto che restituisce il profilo delle regole (nessun cambiamento).
- [ ] gx10, su approvazione: campione 86 × 3 (nessun adottato cambia; rinunce del lettore recuperate), corpus (quanti
      dei documenti oggi letti da Qwen in `legge` o salvati squadrati passano al lettore), lotto nuovo (primo colpo).
- [ ] Decisione del proprietario sul default; documentazione (`REGOLE-IMPORT-02` §11, CLAUDE.md, pagina di revisione).

## Fuori da questa fase

- Le regole di lettura esistenti restano: sono la via veloce e gratuita, e il modello entra solo dove falliscono.
- Gli schemi di legge letti dai lettori deterministici (reso XBRL, schema con codici/etichette): non cambiano.
- Le scansioni: il profilo dal modello vale anche sulle celle MinerU, ma la misura si fa dopo, a parte.

## Stima

Sul lotto di novembre i sette difetti trovati erano tutti di struttura (colonne, titoli, sezioni, righe da escludere,
scadenza come sottovoce): un profilo proposto e verificato li avrebbe coperti senza codice nuovo, tranne l'intero col
meno in coda (lettura dell'importo, resta al codice). Costo atteso: 1-2 chiamate e 20-60 s, solo sui documenti dove le
regole falliscono.
