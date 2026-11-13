---
name: retrospettiva
description: Use when the owner asks for a retrospettiva, or asks how far a piece of work has really advanced, whether the project is going in circles, how much is rework, or what slowed it down — over the whole project or one area (the importer, the engine, the report). Measures from git, the SDD ledgers, the scoring runs and the session transcripts, never from memory, and writes one dated document in docs/superpowers/retrospettive/.
---

# Retrospettiva

Risponde a una domanda del proprietario sul **progresso effettivo** con numeri misurati e esempi
verificati, non con un'opinione. Produce **un solo documento**,
`docs/superpowers/retrospettive/AAAA-MM-GG-<tema>.md`, e lo committa da solo su un branch.

Modelli da leggere prima di scrivere, nell'ordine: `2026-10-18-ottobre.md` (la più completa: tre
risposte in cima, copertura nel tempo, Appendice A), `2026-09-26-rilavorazione-settembre.md`
(definizioni dei contatori, misurato vs inferito), `2026-10-15-debug-import-ottobre.md` (forma corta,
per una sessione sola).

## Perché è severa

Una riga di documentazione su otto era falsa a settembre (39 su 305). Una retrospettiva che ricopia
un conteggio da `CLAUDE.md`, da una pagina di revisione o dalla retro prima **eredita l'errore e lo
firma**. Ogni cifra si rimisura, e ha il comando che la produce nell'Appendice A.

## 0. Fissa la domanda, il periodo e l'ora

1. **La domanda** è quella del proprietario, citata tra virgolette in testa al documento. Se ha
   nominato un'area («l'importatore universale dei bilanci di verifica», «il motore»), la retro è su
   quell'area: il resto del repo entra solo come contesto e costo.
2. **Il periodo** parte dalla data della retrospettiva più recente
   (`ls docs/superpowers/retrospettive/`) e arriva a oggi, salvo che il proprietario dica altro. Se la
   domanda riguarda un progetto nato prima (es. le Fasi dell'importatore generico, dal 28/10), il
   **punto di partenza della misura di progresso** è la sua baseline, anche se precede il periodo git.
3. **L'ora della misura e lo sha di `main`** vanno nel documento: chi rimisura dopo trova di più.

Variabili usate sotto:

```bash
R=$(git rev-parse --show-toplevel)                    # repo principale
C=${BUDGET_CORPUS:-$R/../budget-corpus}               # dati locali fuori da git (LEGGIMI.md)
S=$R/.claude/skills/retrospettiva/strumenti
O=$C/superpowers/retrospettiva/<AAAA-MM-GG>           # output grezzi: fuori da git, si tengono
P=$C/corpus/_analisi-campione/punteggio               # giri di punteggio (IMPORT_PUNTEGGIO_DIR)
```

## 1. Le fonti (tutte in sola lettura)

| fonte | dove | che cosa dà |
|---|---|---|
| git, **tutti i ref** | `git log --all` | linea del tempo, churn, contatori, revert, rami in volo |
| registri SDD | `$C/superpowers/sdd/*/progress.md`, `task-*-report.md`, `final-review*.md` | giri di correzione, Ruling, decisioni del proprietario, task scartati |
| giri di punteggio | `$P/<etichetta>/punteggio.json` e `.md` | il progresso dell'import **contro le verità** |
| piani e spec | `docs/superpowers/plans/`, `specs/` | che cosa si era promesso, e con quale criterio di chiusura |
| pagina di revisione dell'importatore | l'artifact citato nei piani delle Fasi (Artifact `read`) | ciò che è stato raccontato al proprietario: **si verifica, non si ricopia** |
| materiale del proprietario | `$C/inbox/` | quando sono arrivate le richieste esterne |
| riallineamenti | `docs/superpowers/allineamento/` | quanto la documentazione ha tenuto |
| sessioni | `~/.claude/projects/<repo-codificato>/` | durata, USD, subagenti, comandi falliti |

Le sessioni di un altro PC **non si leggono da qui**: se il periodo ne contiene (il repo è passato da
`/home/peter` a `/home/claw03` il 10/11), dichiaralo e non contarle come zero.

## 2. Le misure

### 2.1 Linea del tempo
Una tabella `quando | che cosa | prove` (commit, merge, giro di punteggio, decisione). Una riga per
lotto o fase, con il commit di chiusura. I giorni a zero commit si scrivono.

### 2.2 Churn, sopravvivenza, contatori di rilavorazione
```bash
python3 $S/misure.py --da <inizio> --a <fine-esclusa> --out $O     # ~1-3 min col blame
```
Riporta la tabella delle aree (colonne `-w`), i file più riscritti, e la tabella dei contatori con
**le stesse righe della retro precedente**, così si confrontano: commit non-merge, merge, `fix*`,
parole di ritorno, revert veri, coppie sullo stesso file entro 3 giorni, commit ≥50 righe morti su
main, commit in volo (non raggiungibili da main), commit con «decisione del proprietario».
`misure.py` stampa anche gli id di documento più citati nei soggetti: sono i candidati per §2.5.

### 2.3 Il progresso dell'import — la misura che dice se si avanza
Dal 28/10 la misura principale è **il punteggio contro le verità**; la copertura dei lettori a regole
del 18/10 resta come seconda misura.

```bash
python3 $S/serie_punteggio.py $P --forme conti/colonne,contrapposte --json $O/serie.json
```
Stampa i giri sul campione **raggruppati per insieme di documenti** e i giri sul corpus intero.
Regole per leggerla:
- **Si confronta solo dentro un gruppo** (stessi id). Il campione è cresciuto 53 → 78 → 86.
- **Le verità cambiano anche a insieme fisso**: un giro con suffisso `-R3` (o simile) è lo stesso esito
  ripunteggiato con le verità nuove. Il salto va dichiarato con la decisione che lo ha causato.
- **La colonna `commit` è quella dello strumento al momento del punteggio**, non sempre il codice
  misurato: quello sta nell'etichetta del giro e nel registro.
- Un giro di misura (es. «classico spento») non è un rilascio: dillo.
- Per i bilanci di verifica guarda le forme `conti/colonne` (elenchi di conti) e `contrapposte`; la
  pagina di revisione le chiama account lists e contrapposte.
- I giri si **leggono**, non si lanciano: mandare documenti a gx10 o MinerU è un'uscita di dati dei
  clienti approvata solo come misura del lavoro, non per una retrospettiva. Se serve un punto nuovo,
  chiedi.

Seconda misura, offline e senza rete (nessun documento esce dal PC):
```bash
git -C $R worktree add --detach $O/wt/<sha> <sha>        # mai nel repo principale
RETRO_ROOT=$O/wt/<sha> RETRO_TEST=$C/corpus python3 $S/copertura/driver.py $O/copertura/<sha>.jsonl
RETRO_ROOT=$R          RETRO_TEST=$C/corpus python3 $S/copertura/driver.py $O/copertura/oggi.jsonl
```
Conta i PDF distinti letti dai lettori deterministici (`adottato: true`), con `rete 0` da verificare
nella riga finale. Il denominatore cresce con i lotti: scrivilo accanto a ogni punto. Le foglie del
lettore prima del modello hanno uno strumento proprio, `tests/corpus/foglie_campione.py`.

### 2.4 Rilavorazione e avanzamento
Usa la definizione di settembre (§2.3 di `2026-09-26`): un ritorno è rilavorazione solo se la causa è
la stessa o se la seconda correzione **disfa** la prima. Elenca: revert veri, esperimenti misurati e
scartati (con quanto codice), fix su fix sullo stesso file, rami mai arrivati in main.

### 2.5 I ritorni sullo stesso problema
Per l'import, i documenti (`budget_NNN`, id del campione) che tornano in più commit, registri o fasi:
per ciascuno la causa ogni volta, e se è **aperto da più fasi** (i «casi aperti» che passano di
pagina in pagina). Per il motore, le regole cambiate due volte.

### 2.6 Decisioni del proprietario dopo il codice
Ogni decisione datata (`git log --grep "decisione del proprietario"`, i Ruling nei registri) che ha
reso inutile codice già scritto, o l'ha ribaltato. Distinguile da quelle chieste **prima** del codice
(sono il comportamento giusto, e vanno contate come tali).

### 2.7 Le raccomandazioni della retrospettiva precedente
Tabella `# | raccomandazione | esito | prova`: sì, no, a metà, mutata. Ogni esito con la prova presa
dal periodo (un commit, un file, un conteggio). La retro precedente scrive anche la metrica: usala.

### 2.8 Sessioni e costo
```bash
python3 $R/scripts/analisi_sessioni.py --da <inizio> --a <fine-esclusa> \
  --projects ~/.claude/projects/$(echo $R | tr / -) --out $O/sessioni [--no-pi]
```
Il default di `--projects` è il percorso del PC vecchio: passalo sempre. Il `cost-state` è
**cumulativo sulla vita della sessione**: una sessione iniziata prima della finestra va sottratta
della parte già contata, e la sottrazione è inferita. I trailer `Co-Authored-By` dei commit non
misurano il modello.

## 3. La forma del documento

```
# Retrospettiva — <periodo o tema>: <la domanda in breve>
<puntata precedente linkata · domanda tra virgolette · periodo · ora della misura e sha · strumenti · fonti>
**Come leggere i numeri.** misurato vs inferito.
## 0. Le tre risposte, in cima
   1) <la domanda del proprietario>: sì / no / in parte, e dove.  2) I tre problemi tornati di più, e perché.
   3) Che cosa cambierebbe il ritmo (rimando a §6).
## 1. La linea del tempo
## 2. I numeri          (churn · file riscritti · contatori · progresso dell'import · sessioni · costo in una riga)
## 3. Le cause, con esempi verificati
## 4. Le raccomandazioni della retro precedente: applicate? (con la prova)
## 5. Ha funzionato / non ha funzionato (con numeri)
## 6. Raccomandazioni misurabili — ognuna con la metrica che la prossima retro conterà
## Appendice A — come rimisurare   (ogni comando, con il risultato atteso commentato, e le avvertenze)
## Appendice B — le sessioni del periodo
```

Su una domanda di area (es. l'importatore) aggiungi in §2 una tabella **«dove siamo rispetto
all'obiettivo»**: i pezzi del traguardo dichiarati nel piano o nella pagina di revisione, ciascuno con
lo stato misurato oggi e la prova.

## 4. Regole

- **Misurato vs inferito**, sempre distinti nel testo. Un'interpretazione non diventa un numero.
- **Rimisura, non ricopiare**: un conteggio di `CLAUDE.md`, di un piano, della pagina di revisione o
  della retro precedente si verifica con un comando; se non torna, il documento lo dice.
- **Le cifre dei clienti non vanno in git.** Il documento cita id di documento, percentuali e
  conteggi; mai importi o etichette dei bilanci reali (quelli restano in `$O` e nei rapporti in
  `$C`). Prima del commit: `git diff --cached | grep -nE '[0-9]{1,3}(\.[0-9]{3})+,[0-9]{2}'` deve
  uscire vuoto, o ogni riga trovata va motivata (un conteggio di righe non è un importo).
- **Un verdetto negativo vuole una prova**: «non applicata» è una ricerca andata a vuoto, scritta.
- Si scrive solo il nuovo documento: nessuna modifica a `CLAUDE.md`, alle altre retrospettive, al
  codice. Gli output grezzi vanno in `$O`, che non è in git.
- Nessuna chiamata a gx10, MinerU, Anthropic o altri servizi; la copertura offline blocca la rete.
- Test e script che toccano il DB solo su una copia (`DATABASE_PATH`); mai la suite intera.
- Mai `find /`; sul corpus `find -L`. Per aspettare un processo, il suo PID (`kill -0`), mai
  `pgrep -f` col pattern nello stesso comando.
- Git: branch `docs/retrospettiva-<AAAA-MM-GG>`, `git add` del solo documento, niente
  `git add -A`, niente `git stash`. Merge e push solo quando il proprietario lo chiede.
- Italiano; nelle conclusioni dai del tu al proprietario.

## 5. Consegna

Il commit sul branch, poi un messaggio breve al proprietario: le tre risposte, i numeri principali,
e **che cosa non si è potuto misurare** (sessioni di un altro PC, punti di copertura non
ricostruibili, verità cambiate a metà serie). Se il proprietario lo chiede, aggiorna anche la pagina
di revisione con le misure nuove.
