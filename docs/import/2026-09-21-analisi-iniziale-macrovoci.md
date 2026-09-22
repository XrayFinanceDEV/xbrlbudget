# Analisi iniziale delle macro-voci IV CEE

> La regola di arresto su macrovoci incomplete è superata dalla
> [correzione con fallback e conti residuali](2026-09-21-fallback-macrovoci-ambienta.md).

Branch: `feat/import-analytical-details`.
Parser: `macro-analysis-v7-2026-09-21`.

## Contratto introdotto

Prima dell'arricchimento analitico serve una base SP/CE acquisita e riconciliata.
Nel percorso LLM dei **PDF IV CEE con testo nativo**, la lettura esaustiva delle
macro-voci sostituisce il precedente ciclo di estrazioni su finestre SP/CE,
estrazione comparativa e tentativi ripetuti. Non è una correzione specifica dei
numeri di FIMAP: il modello classifica celle della fonte, mentre il codice
ricostruisce gli importi e applica i controlli.

I percorsi deterministici con prova contabile indipendente mantengono la
precedenza. OCR, vision e bilanci di verifica conservano i percorsi esistenti:
questa modifica non dichiara di aver esteso a essi il nuovo protocollo LLM.

## Acquisizione e verifica

- Tutte le righe estratte, su tutte le pagine, sono assegnate a blocchi. Nessun
  limite fisso di sei pagine SP o quattro CE nel nuovo percorso.
- Per ciascuna macro-voce si distingue `observed`, `observed_zero`,
  `not_reported` e `unresolved`. Quest'ultimo stato blocca il passaggio.
- `not_reported` richiede dichiarazione esplicita di assenza in **ogni blocco**,
  oltre alla riconciliazione della sezione. Non è una prova visiva di assenza:
  è l'esito della lettura del testo estratto, dichiarato come tale nell'audit.
- Il modello restituisce riferimenti riga/cella e orientamento del segno, non
  importi arbitrari. Totali ripetuti sono alternativi, non additivi. Riferimenti
  fuori blocco, celle di periodo errato o scarto/percentuale, celle condivise tra
  macro-voci sorelle e totali contraddittori vengono respinti.
- La verifica confronta somma dell'attivo, somma del passivo/PN, totali stampati
  delle due sezioni, valore della produzione, costi della produzione, risultato
  CE stampato e risultato CE/SP. Nessun importo viene inventato per chiudere uno
  scarto. Tolleranza di un centesimo per fonti con decimali; due euro per fonti
  con soli importi interi.
- Crediti e debiti vengono inizialmente ripartiti usando solo scadenze esplicite;
  il non distinto resta breve. La regola gestionale dei finanziamenti resta
  responsabilità della fase successiva. Le riserve sono la partizione del
  **patrimonio netto stampato**, meno capitale e risultato, non una differenza
  tra attivo e passivo.
- Una base incompleta consente una sola rilettura correttiva, con errori
  espliciti. Budget di avvio delle richieste: 240 secondi; timeout per richiesta:
  60 secondi; nessun retry SDK. Errori API/credito fermano immediatamente il
  passaggio. Alla fine dei tentativi non si ripiega sul vecchio lettore incompleto:
  non si avviano dettagli e non si salva/sovrascrive il bilancio.
- Pagine prive di testo o chiaramente immagini con poco testo richiedono
  esplicitamente OCR/vision; non vengono dichiarate lette.
- La diagnosi è conservata in `validation_report.macro_analysis` e non viene
  cancellata dalle rettifiche manuali. Un comparativo non verificato non
  invalida il corrente: viene escluso e segnalato. Per il nuovo percorso gli
  infrannuali non richiedono il comparativo, evitando il salvataggio improprio
  di un confronto di cinque mesi come annuale.

## Colonne SAP

Le intestazioni `TotPerRep`, `TotPerCfr`, scarto assoluto e percentuale vengono
legate alle colonne fisiche. I codici a sinistra non sono celle monetarie.
Nel 524 il codice di posizione `92` non può più diventare un saldo; la cella
corrente della riga previdenziale è `-752474.43` nella convenzione della fonte.
Il lettore delle macro-voci normalizza il segno tramite riferimenti documentati.
Questo non costituisce ancora una verifica live della suddivisione analitica SAP.

SP/CE principale, note e conti non assegnati sono separati. I saldi correnti nei
conti non assegnati rimangono una segnalazione di revisione della fonte, anche
quando lo schema principale quadra: non vengono aggiunti alle macro-voci.

## Verifica effettuata

Test **offline**, API reali interdette, database SQLite in memoria.
Suite mirata finale: **276 test superati, 3 saltati** (fixture locali assenti).
Sul PDF 524 le risposte del lettore sono sostituite da una fixture che indica
etichette/riferimenti/segni; **gli importi sono letti dal PDF reale**.

- 20 pagine e 1.128 righe completate;
- attivo e passivo/PN: **55.117.048,16**;
- perdita CE e SP: **7.674.851,79**;
- immobilizzazioni immateriali: **615.829,08**;
- ammortamenti: **977.681,20**;
- variazione materie prime: **6.036.705,98**;
- test attraverso l'importatore e il salvataggio, non solo il riduttore;
- togliendo gli ammortamenti dalla risposta, la pipeline blocca dettagli e
  scritture; lo scarto comparativo 2025 di 809 euro non viene compensato;
- il caso resta da rivedere per i conti non assegnati: la previsione resta bloccata.

Questi test dimostrano il funzionamento del contratto e della riconciliazione,
**non la qualità della risposta dell'LLM reale al nuovo prompt**. Nessuna nuova
importazione a pagamento è stata lanciata. Resta necessaria una controprova live
autorizzata, seguita dalla verifica separata dei dettagli e delle scadenze SAP.
