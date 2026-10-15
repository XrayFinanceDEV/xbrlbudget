# Retrospettiva — debug dell'import, 14-15 ottobre 2026

Una sessione sola, dal giro sui bilanci sbilanciati di ottobre alla pulizia dello staging.
Il lavoro dichiarato era: **verificare i bilanci sbilanciati uno per uno, correggerli in modo
deterministico, unire a main e provarli su staging dall'API interna.**

Fonti: `git log` su main (`2ec8c72..0539766`), il registro SDD
`.superpowers/sdd/2026-10-14-debug-import-10-2026/` (fuori da git, per scelta), le riletture su
staging. Ogni numero qui sotto è misurato da quelle fonti, salvo dove dice «inferito».

## 1. Che cosa è successo

| quando | che cosa | esito misurato |
|---|---|---|
| 14/10 | Lettori deterministici per formati nuovi (verifica IE/E, AGO a 8 cifre con importi grafici), scansioni contrapposte da MinerU senza modello, testo cifrato PDF24, mastri dalla somma | 15 commit non-merge, 13 `fix` |
| 15/10 mattina | Santini (XBRL infragruppo, verifica «Mastri»), 1343 (Totale Sub / Mastro), 1331 (percorso come codice di riga) | 3 `feat`, ognuno con la propria famiglia di test |
| 15/10 | Primo giro di staging: 3 bilanci a campione, poi altri 7 con almeno una scansione | restano non quadrati 435, 689, 1322, 1319 |
| 15/10 | 435 (contrapposte di soli conti) e 689 (scansione con partitario) | chiusi al centesimo su staging |
| 15/10 | Fondi con la categoria abbreviata (1325, 1330, 1343) | chiusi |
| 15/10 sera | Cancellate le 34 aziende create oggi su staging | 34 × 204, restano le 6 dei giorni prima |

Totale dell'intervallo: **46 commit di codice, 5.056 righe aggiunte / 159 tolte in 68 file**
(tra codice e test), di cui 2.188 / 83 in `importers/`. Test finale della fetta rilevante:
926 passati e uno rosso già prima (`test_final_report_pdf_endpoint`).

## 2. Che cosa ha funzionato

- **Il corpus come rete.** Dopo ogni modifica al lettore ho rigirato `corpus/dump.py` e
  confrontato con `cmp.py` contro tre baseline. Nessun file è peggiorato in nessun giro. È
  l'unica ragione per cui si sono potute fare modifiche al divisore delle colonne
  (`_be_split_codeless`) senza paura.
- **Misurare prima di cambiare il centro.** Tre tentativi di spostare il varco centrale
  (ordinare per righe, per parole attraversate, per punto medio) sono falliti sul corpus o sul
  test sintetico. Il quarto, «prima gli spazi veri, poi la griglia», ha funzionato perché è
  partito da un fatto del documento (la zona vuota è larga un punto) e non da una statistica.
- **PDF sintetico al posto del file del cliente.** Per 435 e 689 ho costruito un documento con
  la stessa geometria e nessun dato vero (`test_contrapposte_soli_conti.py`, regressione 689 nei
  test MinerU). Il file reale non è mai entrato in git, e il test resta leggibile.
- **Il confine dei vincoli di sicurezza.** Nessuna prova dall'esterno, solo Qwen su Tailscale e
  MinerU in LAN, l'immagine della scansione mai inviata ad Anthropic, le chiavi mai stampate. Il
  lavoro è stato rallentato dal non poter guardare la scansione, e va bene così.
- **Le regole di foglia come ultima risorsa.** Le parole dei conti foglia
  (`_classify_ce_costi_foglia`) sono entrate solo dopo mastro e gerarchia. La prima versione
  stava dentro `_classify_ce_costi` e ha rotto 680; la regressione l'ha vista il corpus, non un
  test unitario.

## 3. Che cosa ha richiesto rilavorazione

Misurato dai miei stessi tentativi nel corso della sessione (non dai diff, che non conservano i
rami provati e scartati):

1. **Il varco centrale di 435: 4 tentativi, 3 scartati.** Ogni tentativo aveva un'ipotesi sul
   «giusto» centro, e il test sintetico non esisteva ancora. Il test è arrivato dopo il secondo
   fallimento. **Inferito:** scrivere il sintetico *prima* avrebbe risparmiato due giri.
2. **Mappature di foglia sbagliate, scoperte una per una.** «PREMIO DI PRODUZIONE», «CANONI DI
   ASSISTENZA», «ACCAN.TFR», «CONTRIBUTI ASSISTENZA SANITARIA», «PREMI E ALTRI ELEMENTI»: tutte e
   cinque erano finite nella voce sbagliata perché una parola generica scavalcava la specifica.
   La causa è una sola: un elenco di parole-chiave ordinato per intuito. **Inferito:** il test
   giusto è un elenco di coppie descrizione → campo da confrontare con l'intero corpus, non un
   caso alla volta.
3. **689: la correzione ha scoperto un secondo difetto.** Normalizzare gli importi OCR ha fatto
   uscire la pagina dal percorso «garbled», e lì è emerso il partitario (il «4» diventato padre
   di 41/43/45). Due difetti nascosti l'uno dietro l'altro, il secondo visibile solo dopo il
   primo. Il corpus senza MinerU non poteva vederlo: serviva la cache MinerU.
4. **Jenkins: tre rilanci chiesti all'utente.** Ogni correzione ha richiesto un deploy prima di
   poter rileggere su staging, e in due casi ho ricaricato prima di aver verificato che il deploy
   fosse arrivato. **Il costo non è il tempo del build, ma la domanda «devo rilanciare ancora?»
   che l'utente ha dovuto farmi.** Regola per la prossima volta: dopo un push, dire subito «da
   rilanciare», e verificare il deploy da un campo del risultato prima di leggere il numero.
5. **Cache MinerU persa per Unicarton.** Il pickle non c'era più; rigenerata dalla LAN. La
   cache sta nella cartella SDD, non nello scratchpad, proprio per questo (memoria
   `banco-import-snello`), ma Unicarton era stato fatto prima di quella regola.

## 4. Che cosa non si è chiuso

- **1322 e 1319, scansioni.** Si importano sbilanciate con avviso (regola del 5% e della vision).
  Tracciate in #64. Il tempo di risposta di staging è stato di 174 e 260 secondi: non è un
  difetto di lettura ma resta una fragilità se gx10 rallenta.
- **Conferma su staging** di 680, 238, MBS, CONA, 188, 281: verificati in locale sul corpus, mai
  riletti in produzione di prova.
- **Robustezza a gx10 lento:** nessuna misura, nessun timeout dichiarato lato lettore.

## 5. La misura che manca

La sessione non ha un contatore del *tempo per bilancio chiuso*. Dalla cronologia: tra il primo
campione di staging e la chiusura di 689 sono passati circa un giorno di lavoro, con 4 file
chiusi da correzioni nuove e 6 che erano già a posto. **Inferito**, non misurato: la quota di
file che un lettore nuovo chiude è molto più alta nei formati *mai visti* (Santini, 1343, 1331:
tre su tre) che nei formati *già visti con una variante* (435, 689: due giorni di lavoro per due
file). I formati nuovi si pagano una volta; le varianti si pagano a ogni giro.

## 6. Tre cose da portare avanti

1. **Documentare i sei formati nuovi** in `IMPORT-ROUTING-TAXONOMY.md`. Il riallineamento di
   oggi li segnala come silenzio; senza pagina, il prossimo import che non quadra riparte da zero.
2. **Un test di tabella per le regole di foglia**, non un test per voce. La stessa classe di
   difetto (§3.2) tornerà ogni volta che un cliente scrive una voce nuova.
3. **Dire «da rilanciare» a ogni push e verificare il deploy** prima di rileggere (§3.4).
