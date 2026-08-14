# Riscatto vision per sezione — route C

**Data:** 2026-08-14
**Stato:** Design approvato (in attesa di review della spec scritta)
**Area:** import route C (situazione contabile / sezioni contrapposte). Nessuna modifica a DB,
motori di calcolo, endpoint o frontend.
**Precedenti da conoscere prima di leggere:** `docs/FIXING-IMPORT.md` §1 (principi), §2
(geometria), §3 (recupero mastri orfani), §6 (i due file di questo design);
`docs/piano-import-2026-07/01-NETTING-FONDI-AMMORTAMENTO.md` §N6 e
`docs/piano-import-2026-07/08-AUDIT-QUADRATURE.md` §3 — il **tentativo vision del 14/07,
revertato lo stesso giorno**.

## Problema

Due stampe AGO della stessa azienda, a un anno di distanza, si importano sbagliate per motivi
scorrelati. Entrambe sono route C, `C/contrapposte 8-digit`, e in entrambe **il numero giusto è
stampato sulla pagina**: è la lettura del text layer a non arrivarci.

**budget_624 (2024, AGO 06.07.00).** I mastri di costo dell'ultima pagina del conto economico
sono **disegnati come vettori**: non esistono in `page.get_text()`, nessun estrattore testuale
può leggerli. Sopravvivono solo i dettagli a 9 cifre, con importi interlacciati da `_` e alcuni
senza importo. Costi letti 938.766,79 sui 2.482.879,59 dichiarati → il CE chiude con un utile di
1.553.019,59 contro gli 8.906,79 stampati. Il patrimoniale invece è corretto (2.181.734,09 netto,
quadra), quindi il file **si importa** e l'errore è tutto nel conto economico.

**budget_623 (2025, AGO 10.08.00, pagine `/Rotate 90`).** Qui il conto economico è stato appena
sistemato (commit `cddfb7d`: il riordino per coordinate saldava la sottolineatura agli importi).
Resta corto il patrimoniale: attivo estratto 2.023.876,12 contro i 2.420.397,40 stampati, ~396k
(20%) di conti non classificati, e attivo ≠ passivo di 285.744,17. Il file si importa con
`BILANCIO NON QUADRATO` e `QUADRATURA MASCHERATA`.

In più, su questo file **le ancore dichiarate lette dal testo sono a loro volta sbagliate**:
`_declared_control_totals` restituisce `passivo = 2.420.397,40` mentre il PDF stampa
`TOTALE PASSIVITA' 2.454.987,65`, perché i due totali sono adiacenti nello stream rotto e la
finestra di ricerca prende il primo numero dopo il marcatore. E `pareggio = 2.323.033,59` è il
pareggio del CE, non quello dell'SP. Chi arbitra il riscatto non può fidarsi di quelle ancore.

## Evidenza raccolta prima del design

Esperimento diretto, pagine rese a 200 dpi e passate a `claude-haiku-4-5` in vision, con un prompt
che chiede la sola trascrizione (nessun calcolo).

**budget_624, pagina 4.** La vision legge i mastri che nel testo non esistono:

| mastro | vision |
|---|---|
| 73020005 Amm.to immobilizzazioni materiali | 4.656,95 |
| 73025005 Rim. iniziali materie/merci | 1.426.002,20 |
| 73040000 Oneri diversi di gestione | 14.127,60 |
| 75030015 Interessi e altri oneri fin. v/terzi | 99.326,05 |
| **somma** | **1.544.112,80** |

Il divario misurato sul CE era 1.544.112,80: **coincide alla virgola**. La vision legge anche i
totali stampati (`TOTALE COSTI 2.482.879,59`, `TOTALE RICAVI 2.491.786,38`,
`UTILE D'ESERCIZIO 8.906,79`), che sono l'ancora per autovalidare il recupero.

I **dettagli** a 9 cifre la vision li sbaglia (`706440 000 amm.to fabbricati` → 486,93 invece di
4.656,95): sono le righe con gli importi corrotti dagli `_`. Vanno ignorati — e non servono,
perché il mastro porta già l'intero importo della voce.

**budget_623, pagina 1.** La vision trascrive entrambe le colonne per intero, mastri e importi
corretti: 2.145.135,32 di soli mastri attivo su quella pagina, cioè **più di quanto l'estrazione
attuale abbia in tutto il documento** (2.023.876,12). Il resto dell'attivo sta a pagina 2.

## Perché questo non è il tentativo del 14/07

Il tentativo revertato sostituiva **la pagina** con la lettura vision e ne applicava i valori come
override. Fallì per due ragioni, entrambe registrate: su layout densi la vision perdeva blocchi
interi, e soprattutto l'override **alzava** l'attivo mentre il modello di netting lo **abbassava**,
senza nessun arbitro fra i due.

Qui la vision non sostituisce una pagina: chiude un **divario misurato** contro un **totale che il
documento stampa**, e il risultato passa dalla stessa post-elaborazione degli altri candidati prima
di essere accettato. Se non chiude il divario, si butta via. È il pattern §3 del playbook, quello
che ha funzionato su budget_615.

## Obiettivi

1. budget_624 importa con utile CE = sp13 = 8.906,79.
2. budget_623 importa con attivo = 2.420.397,40 e patrimoniale quadrato.
3. Un file che oggi si importa correttamente **non cambia di un carattere** e non paga nulla.
4. Quando il riscatto non riesce, il file resta esattamente com'è oggi: `BILANCIO NON QUADRATO`
   dichiarato all'utente, da correggere in Rettifiche. Mai un plug, mai un ripiego a metà.

## Non obiettivi

- Non è un nuovo estrattore generale né una quarta rotta. La vision non partecipa alla gara
  iniziale fra CoGe-LLM e deterministico.
- Non si tocca MinerU: quello è OCR per scansioni, dietro profilo compose e mai sul VPS. Qui si
  rende in immagine un PDF che il text layer c'è ma è incompleto.
- Non si recuperano i **dettagli** (sotto-conti a 9 cifre). Restano non letti come oggi: la
  precisione dentro l'aggregato è cosa da Rettifiche.

## Design

### 1. Innesco e posizione nella pipeline

Il riscatto è un **terzo candidato prodotto solo su richiesta**. La richiesta arriva alla **fine**
della catena route C in `pdf_importer.import_pdf_balance_sheet` — dopo `overlay_debt_typing`,
`net_contra_accounts` e `_reconcile_trial_to_declared` — quando `check_quadratura` sul foglio
finito dice comunque una di queste: `is_empty`, `sbilancio` oltre tolleranza, `masked`, oppure
utile CE ≠ sp13.

La posizione è deliberata e va rispettata. Innescare **prima** del netting farebbe scattare il
riscatto su budget_624, il cui attivo a quel punto è corto di ~370k rispetto al totale stampato —
un divario che il netting dei fondi ammortamento chiude da solo, perché il totale stampato su
quel file è **lordo**. Alla fine della catena, invece, 624 innesca il solo CE e 623 il solo SP.

Le due sezioni si innescano **indipendentemente**: un file può riscattare il CE e lasciare l'SP
com'è, o viceversa, o entrambe.

**Tetto di pagine.** Il riscatto non parte se la sezione supera le **8 pagine**. Su questi file la
sezione ne ha 2, ma una situazione contabile può arrivare a decine: oltre quel limite il costo
cresce e la resa cala, e il file resta dichiarato non quadrato invece di spendere una chiamata
enorme con poca speranza. Il limite è una costante nominata, non un numero sparso nel codice.

### 2. Cosa legge la vision

Le pagine della sezione che non torna, rese a 200 dpi (misurato: 185 KB base64/pagina su 624,
481 KB su 623). Un'unica chiamata per sezione, con le sue pagine come immagini multiple.

Legge e restituisce:
- i **mastri**: codice, descrizione, importo, colonna;
- i **totali stampati** di quella sezione.

Ignora i dettagli (vedi Evidenza). La **colonna** resta la verità sul lato — attivo/costi a
sinistra, passivo/ricavi a destra (`FIXING-IMPORT.md` §1.3) — e la **descrizione** decide la voce.
Per il CE la risoluzione passa da `situazione_contabile_parser._resolve_ce_field(desc, direction)`,
mai da `iv_cee_hierarchy.resolve(side=…)`: su un nodo CE `side` non filtra nulla e una voce di
costo può risolversi su un nodo di ricavo, spostando il risultato di 2×.

### 3. Il cancello di accettazione

Il riscatto **ricostruisce la sezione da zero** dai mastri letti in vision: non somma i conti
mancanti a quelli già estratti. Sommare richiederebbe di sapere quali conti erano già dentro — un
riconoscimento per codice o descrizione che, sbagliato, conta due volte un mastro e sbilancia il
foglio, ed è esattamente l'errore che ha fatto revertare il tentativo del 14/07. L'ancora è il
totale stampato, non un ragionamento su cosa mancava. Le voci dell'**altra** sezione restano
intoccate.

Il candidato riscattato attraversa **la stessa** post-elaborazione degli altri due (typing debiti →
netting contro-conti → riconciliazione al dichiarato) e si tiene **solo se tutte** queste valgono:

1. **Riconcilia al totale stampato** della sezione, tolleranza `max(50 €; 0,5%)` — la stessa di
   `_select_dedup`, non una nuova.
2. **I totali letti dalla vision sono coerenti fra loro**: `attivo + perdita = passivo` (oppure
   `attivo = passivo + utile`) per l'SP, `costi = ricavi + perdita` (oppure `costi + utile =
   ricavi`) per il CE. È questa coerenza interna che autorizza a preferirli alle ancore di testo
   quando quelle si contraddicono, come su budget_623. Se i totali vision non sono coerenti, si
   ricade sulle ancore di testo; se non lo è nessuno dei due insiemi, il riscatto si scarta.
3. **La quadratura risultante è strettamente migliore** di quella del candidato che sostituisce
   (sbilancio minore, o residuo non classificato minore, e mai `is_empty`).

Se una qualsiasi cade, si scarta tutto e resta il candidato di prima con i suoi warning. **Un solo
tentativo per sezione**: un riscatto rifiutato non viene ritentato, né con un prompt diverso né a
risoluzione maggiore. Niente cicli.

### 4. Moduli e confini

| Modulo | Ruolo | Dipendenze |
|---|---|---|
| `importers/vision_rescue.py` (nuovo) | Puro rispetto a DB e ORM: path + pagine + sezione → righe lette e totali letti. Qui vivono il prompt CoGe-vision e lo schema di risposta. | `fitz`, `anthropic`, `config.PDF_LLM_MODEL` |
| `situazione_contabile_parser.section_pages(file_path)` (estratto) | Quali pagine sono SP e quali CE. La regola **esiste già** dentro il ciclo pagine di `extract_contrapposte_best_effort` (`:4524`): va estratta, non riscritta, e diventa testabile da sola. | `fitz` |
| `pdf_extractor_llm._declared_control_totals` (esteso) | Aggiunge le chiavi `costi` e `ricavi`. Oggi restituisce solo `attivo/passivo/pareggio/utile/perdita`, quindi il CE **non ha ancora** un'ancora dichiarata da confrontare. | invariate |
| `importers/pdf_importer.py` | Il punto di innesco e la ri-esecuzione della catena sul candidato riscattato. ~30 righe. | le tre sopra |

`vision_rescue.py` non importa `pdf_importer` né conosce il DB: si testa con un doppio della
risposta del modello.

### 5. Errori, costi, tracciabilità

Parte solo su file già rotti: chi si importa bene oggi non paga nulla e non cambia. Sui rotti,
1–2 chiamate Haiku vision e qualche secondo sul percorso di import sincrono. Attivo sempre, senza
flag: con l'innesco misurato, l'alternativa per l'utente non è "più veloce", è "sbagliato".

Ogni errore del riscatto — rendering, API non raggiungibile, risposta malformata, schema non
validato — è **non fatale**: si logga e si tiene il candidato precedente. Stessa filosofia del
rollback atomico di `net_contra_accounts`.

Il `validation_report` persistito registra che il riscatto è avvenuto e su quale sezione, così un
import vision è distinguibile a posteriori da uno testuale — come già fa `parser_version` con
`+mineru-<ver>` per l'OCR.

### 6. Test

- **`tests/test_vision_rescue.py`**, con doppio della risposta vision (nessuna chiamata in CI):
  il cancello accetta un riscatto che riconcilia; rifiuta uno che non riconcilia; rifiuta uno che
  peggiora la quadratura; non viene nemmeno invocato su un foglio che già quadra; un'eccezione
  nel riscatto lascia il foglio precedente intatto.
- **`section_pages` estratta**: stessa classificazione pagina→sezione di prima sui casi noti,
  incluse le pagine senza intestazione.
- **`_declared_control_totals`**: le due chiavi nuove lette su un footer CE, `None` quando non
  stampate.
- **Sui due PDF veri**, gated su presenza in `tests/debug/` come da convenzione del repo
  (`skipif(not os.path.exists(...))`): 624 → utile CE 8.906,79 = sp13; 623 → attivo 2.420.397,40
  e patrimoniale quadrato.
- **`tests/test_import_baseline.py`** per misurare che nient'altro si è mosso.

## Rischi noti

1. **La vision è non deterministica.** Il cancello §3 è ciò che rende il rischio accettabile: una
   lettura sbagliata quasi mai riconcilia al totale stampato, e se non riconcilia viene scartata.
   Resta possibile una lettura sbagliata che riconcilia per caso — improbabile su somme a sei
   cifre con due decimali, ma non impossibile, e la difesa in quel caso è Rettifiche.
2. **Il caso 623 potrebbe non chiudersi.** L'evidenza copre pagina 1 (letta bene); pagina 2 non è
   stata provata in vision. Se il totale non riconcilia, il cancello scarta e il file resta come
   oggi — obiettivo 2 mancato, obiettivi 3 e 4 comunque rispettati. Va verificato in
   implementazione prima di dichiarare chiuso quel caso.
