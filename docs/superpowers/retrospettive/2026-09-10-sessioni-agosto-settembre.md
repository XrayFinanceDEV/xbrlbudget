# Retrospettiva — sessioni agentiche dal 24 agosto al 11 settembre 2026

Come ha lavorato un agente di piano su questo repo per 17 giorni di calendario: quanto è
costato, che cosa ha prodotto, dove ha sprecato, e che differenza c'è stata fra i due metodi
usati (issue-driven il 1°-2 settembre, subagent-driven-development l'8-10).

**La finestra è dal 24 agosto all'11 settembre 2026, misurata alle 11:03 dell'11.** Il nome del
file e il messaggio del primo commit dicono «10 settembre»: è l'ultimo giorno di lavoro intero, e
nell'11 settembre entrano solo le prime ore del lotto 3B e questa stessa analisi.

Tutte le cifre sono **misurate** da `scripts/analisi_sessioni.py` sulle trascrizioni JSONL, sui
registri SDD, sul tracker e su `git log`. Dove una cifra non è misurata ma ragionata lo dico
esplicitamente (**inferito**), e dove un numero che ricordavo si è rivelato falso lo dico lo
stesso: è successo, vedi §5.1.

## 1. Linea del tempo

Diciassette giorni di calendario, otto giorni di lavoro. Le date sono l'author date dei commit
(`git log --all --no-merges --pretty=%ad --date=short`, filtrate dal 24 agosto: 32+22+53+68+57+30 =
**262 commit**), i merge sono
`git log --merges --since=2026-08-24 --date=short --pretty='%h|%ad|%s'` — **23** sul ramo
controllato, 24 aggiungendo `--all` — il ramo del lotto 2 non è ancora in `main`.

| quando | che cosa è successo | prova |
|---|---|---|
| 24-25 agosto | `13ecc3c9` apre il tracker: triage del rapporto del tester, tre spec, primi push. Pochissimo codice | scheda `13ecc3c9` |
| 26-31 agosto | **fermo su questo repo**: il 24 ha 2 messaggi del proprietario, il 31 ne ha 7 e nessun agente; le sessioni di quei giorni stanno sotto altri progetti | §3 |
| 1 settembre | comincia il ciclo a issue: **32 commit**, 33 issue create, 10 chiuse lo stesso giorno da `gh issue close` dentro `1e96601e`, primi `/implement` | `git log`, `gh api` |
| 2 settembre | **22 commit**, altre 13 issue create; due ondate di fan-out (`65f68717`, 20 `workflow-subagent`) che producono 16 commit in 14 minuti; cinque branch di fix uniti in `integrazione-lotto` (`a59b0c0`, `5019aaf`, `b38614a`, `e5d0b6a`, `4a57bb6`) | §4.1 |
| 3-7 settembre | **fermo**: nessuna riga su questo repo | §3 |
| 8 settembre | **53 commit**. Merge `ade2320` (11:22); trentaquattro issue chiuse fra le 11:35 e le 11:36 da una chiamata API senza `commit_id` (§5.10); `4aebaba4` (11:50) porta il corpus reale in `Test/`, implementa la guardia della #24 e la reverta (§5.6); apre il **lotto 1 SDD** | §5.6, §5.10 |
| 9 settembre | **68 commit**. Il lotto 1 si chiude a ore 10:45 con il merge `40f0332` («percorso guidato delle ipotesi di budget in sette passi», 58 commit, 27 dei quali il giorno prima); il lotto 2 comincia e in giornata mette a segno 28 dei suoi commit | `git log -1 40f0332`, §5.3 |
| 10 settembre | **57 commit**, 56 dei quali del lotto 2: merge per task sul proprio ramo (`288a8ca`, `5ad6112`, `e9fa4cf`, `59bf9f4`, `0334e7e`, `64f58ed`, `2571623`) e i due merge di documentazione di pi (`f356907`, `7896b13`). Revisione finale del branch alle 15:06Z (17:06 locali), poi il giro finale; il processo del coordinatore si chiude in giornata con quattro agenti in volo (`progress.md:1015`) | §5.4, §4.5 |
| 11 settembre | **30 commit**: cominciano i piani 3A/3B, e il 3B si chiude in giornata con il merge `4aa283f` (revisione finale sonnet: 2 importanti corretti). Il lotto 2 non è ancora in `main`: 92 commit sul ramo `feat/scadenziamento-pregresso`, dei quali 16 di follow-up entrati con `1490476` | `git log --merges --since=2026-09-11` |

Le issue aperte alla misurazione sono **5 su 49** (33 create il 1°, 13 il 2, una l'8, due l'11);
44 chiuse, tutte il 1° o l'8 settembre.

## 2. Che cosa è stato misurato

| Fonte | Copertura |
|---|---|
| Trascrizioni Claude (`~/.claude/projects/-home-peter-DEV-budget/*.jsonl`) | 12 sessioni avviate nel periodo, 99.744 righe lette, 2 scartate |
| Trascrizioni dei subagenti (`<sessione>/subagents/**/agent-*.jsonl`) | 183 classificati, 182 con trascrizione |
| `cost-state` (snapshot di fine sessione, include i subagenti) | USD 1.655,93 totali, per modello |
| Registri SDD (`.superpowers/sdd/*/progress.md`) | 11 registri, 4.087 righe; i due del periodo: 685 + 2.219 |
| GitHub (`XrayFinanceDEV/xbrlbudget`) | 49 issue non-PR (44 chiuse, 5 aperte), 46 create il 1°-2 settembre |
| `git log` su tutti i ref | 262 commit non-di-merge + 23 merge dal 24 agosto (24 con `--all`) |
| Trascrizioni pi (`~/.pi/agent/sessions/`) | 14 run dello stesso modello locale, di cui 2 sono questa analisi |

Misurazione dell'11 settembre alle 11:03, e un limite grosso da sapere subito: **la sessione
coordinatrice `b06623a4` era ancora viva mentre leggevo**. Le sue cifre sono quelle di uno
snapshot, e il report che state leggendo è essa stessa uno dei lavori che quella sessione ha
dispacciato.

Altri due limiti:

- **Le giornate lavorative sono 8, non 17.** Il 24 e il 31 agosto hanno 2 e 7 messaggi del
  proprietario e zero agenti; poi 01-02, 08-09-10-11 settembre. Fra il 25 e il 30 agosto e fra il
  3 e il 7 settembre non c'è **nessuna** riga su questo repo: le sessioni di quei giorni stanno
  sotto altri progetti (`-home-peter-DEV-Artifacts`, 14 file; `-home-peter-DEV-formulafinance`,
  11). "Tre settimane" è quindi una finestra di calendario, non di lavoro.
- **Il costo è cumulativo, non per unità di lavoro.** Il campo `cost-state` di una sessione dà il
  totale di quella sessione, subagenti compresi; non esiste una misura di quanto è costato il
  singolo task. Le cifre per-task che seguono sono ripartizioni, non letture dirette.

## 3. I numeri

| | valore |
|---|---|
| Sessioni principali | 12 (di cui una, `b06623a4`, = il 72,6% del costo e il 64% del tempo attivo) |
| Tempo attivo (pause > 30 min escluse) | 46,4h su 462,7h di parete |
| Subagenti lanciati | 183 · ripresi con `SendMessage` 56 volte · 10 compattazioni del contesto · 5 interruzioni di processo |
| Costo (`cost-state`) | **USD 1.655,93** — opus 1.278,99 · sonnet 356,83 · fable 15,86 · haiku 4,24 |
| Messaggi del proprietario | 178 (10 erano solo `/compact`, 13 iniettati dal ponte di orchestrazione: non richieste umane) |
| Chiamate di strumento nei loop principali | 3.525, con 109 risultati d'errore e 102 `sleep` (44 min di attesa dichiarata) |
| Agenti per lavoro | 70 revisioni · 49 implementazioni · 20 fan-out di workflow · 19 ri-revisioni · 10 stesure di piani · 10 collaudi · 5 ricognizioni |
| Codice | 262 commit non-di-merge su tutti i ref (author date ≥ 24 agosto), 23 merge dal ramo controllato, due rami-lotto da 58 e 92 commit |
| Tracker | 49 issue (44 chiuse, 5 aperte), 46 create il 1°-2 settembre |

La sessione `b06623a4` (8-11 settembre) è il coordinatore dei due lotti SDD: 29,6h attive — due
terzi di tutto il tempo attivo del periodo — USD 1.202,60, 143 agenti, 56 riprese, 89 messaggi del
proprietario. Per ripartirla per giorno non c'è di meglio degli snapshot `cost-state` (che non
portano un timestamp proprio: li ho agganciati alla prima riga timestampata successiva): ≈ USD 362
fra l'8 e il 9, ≈ USD 685 il 10, il resto l'11. È una ripartizione grezza, e il confine fra i due
lotti non è netto: il lotto 1 chiude a metà del 9.

## 4. Che cosa ha funzionato

### 4.1 Il fan-out sulle issue: 16 commit in 14 minuti
Il 2 settembre la sessione `65f68717` ha lanciato due ondate di `workflow` in parallelo, 20
subagenti in tutto (primi alle 18:20:28, altri alle 21:33). Sono usciti **16 commit in 14 minuti
di orologio** — 8 fra le 18:24 e le 18:27, 8 fra le 21:37 e le 21:43 — e quindici di essi nominavano
una issue diversa in oggetto (`00513d7` ne unisce quattro: #22 #39 #40 #41). La forma è `— #NN`, non
`Closes #NN`: GitHub non la interpreta, e infatti nessuna di quelle issue si è chiusa da sola
(§5.10). I due commit delle 18:12-18:13
sono lavoro del loop principale, appena prima del fan-out. Su tutto il 2 settembre i commit sono
22, sui giorni 1-2 sono 54.

Costo dell'intero ciclo issue: **USD 367,81 in sette sessioni in due giorni** (più 21,40 nella
sessione di setup `13ecc3c9`), cioè 6,81 USD per commit e 29,7 USD ogni 1000 righe di diff — 12.397
righe su 54 commit (`git log --all --since=2026-09-01 --until=2026-09-03 --no-merges --numstat`). Il proprietario non è stato interrotto
una volta durante il fan-out: le issue erano state scritte bene il giorno prima.

### 4.2 Il metodo ha tenuto la contabilità delle decisioni, e si è visto
Contato coi comandi, sui due registri (`grep -oE "Ruling [0-9]+" | sort -u | wc -l`,
`grep -c "decisione del proprietario"`, `wc -l`):

| | lotto 1 | lotto 2 |
|---|---|---|
| righe di registro | 685 | 2.219 |
| «Ruling» numerati distinti | **0** | **63** (fino a Ruling 63) |
| occorrenze testuali di «Ruling» | 52, tutti in forma libera («Ruling: esecuzione parallela…») | 129 |
| occorrenze di «decisione del proprietario» | 3 | 9 |

È la differenza fra un lotto che ha dovuto decidere il comportamento del motore (scoperto,
saldo/acconto, pregresso, sweep) e uno che ha applicato scelte già prese. La prova che serve è il
Ruling 41 (`2026-09-08-scadenziamento-pregresso/progress.md:1440`): una decisione del proprietario
**cambia rotta in corsa** e nasce il task 16.

### 4.3 Una trappola documentata ha smesso di ripresentarsi
La parola `churn` compare **19 volte** nel registro del lotto 1 (`grep -c churn`) e **zero** in
quello del lotto 2: lì è un giro di correzione bruciato a riscrivere byte, con il coordinatore che
decide di riparare lui — «il churn di terminatori lo correggo io sul branch, non l'implementatore»
(`2026-09-08-percorso-ipotesi-budget/progress.md:70`). Nel lotto 2 il tema non scompare —
`CRLF` vi compare 17 volte — ma diventa una decisione misurata (**Ruling 14, «il rumore CRLF si
accetta, non si corregge», `progress.md:308`**) e una voce di verifica nelle revisioni
(«terminatori invariati», `:1878`). Meccanismo: la regola era stata spostata nel prompt
dell'implementatore, non solo in quello del revisore (`MEMORY.md`, voce
`mixed-line-endings-hazard`).

### 4.4 Il messaggio di merge porta il verdetto, non solo il titolo
`git log --merges --since=2026-08-24` dal ramo controllato: **23 merge** (24 con `--all`). Quelli
del lotto 2 stanno ancora sul ramo, che non è in `main`. E quelli del lotto 2 dicono **chi ha verificato e con che
risultato**: `7896b13` «revisione sonnet: 66 frasi vere su 68, 0 false», `1490476` «revisione
sonnet: accettabile, 0 importanti», `59bf9f4` «giro 1», `64f58ed` «trova due difetti del client e un
override rifiutato che restava salvato (task 10, giri 1-3)». È la tracciabilità che altrimenti
starebbe solo nei report gitignorati.

### 4.5 Un'interruzione di processo non ha cancellato nulla
Il 10 settembre il processo del coordinatore si è chiuso con **quattro agenti in volo**. Il
registro (`...scadenziamento-pregresso/progress.md:1015`) elenca cosa era stato salvato prima di
riprendere (due patch + un file di test copiati fuori dall'albero) e riprende gli agenti dal loro
transcript invece di ridispacciarli: «nessun lavoro perso». Stessa scena, in scala, alla riga 740.
Le 5 «interruzioni» misurate sulle 12 sessioni sono tutte qui o in `4aebaba4`.

### 4.6 Il ciclo di apprendimento funziona davvero
6 file di memoria toccati nel periodo (frontmatter `modified` fra il 1° e il 11 settembre), ciascuno
**dopo** un guasto, non in astratto: il 1° settembre per il netting dei fondi (`979f70ad`) e il
netting dei fondi immobilizzati, il 9 per `git add -A` (`34d3a489`) e per i timer globali in
`environment: node` — la lezione del Critical trovato col browser (§5.4) — e il 10-11 per la scelta
del modello, per pi e per lo stato dei lotti (tutti `b06623a4`). E la memoria giusta è
arrivata in tempo: la regola «mai `git add -A` con un agente vivo» è del 9, il giorno dopo
l'errore del coordinatore (`progress.md:239`).

## 5. Che cosa non ha funzionato

### 5.1 Il modello è scivolato verso opus, e la memoria lo raccontava peggio di com'è
La memoria `scelta-modello-subagenti` (frontmatter `modified: 2026-09-10T20:56:09Z`) dice che nel
lotto 2 «la scelta è scivolata: **15 opus su 18 dispacci**». Misurando i dispacci di `b06623a4`
(modello richiesto dal `.meta.json` dell'agente), il numeratore è esatto e il denominatore no:

| finestra (agenti di `b06623a4`, ora di Roma) | dispacci | ripartizione |
|---|---|---|
| solo 10 settembre | **49** | **opus 15** · sonnet 34 (6 senza modello dichiarato, risolti dal transcript) |
| tutti e due i giorni del lotto 2 | 86 | opus 29 · sonnet 55 · haiku 2 |
| 10 settembre, solo implementazioni | 13 | opus 6 · sonnet 7 |
| 10 settembre, solo revisioni | 23 | opus 8 · sonnet 15 |

Nessuna finestra dà 18 dispacci con 15 opus: il «15» è il conteggio giusto degli opus di quel
giorno, il «18» è un denominatore perduto. Lo scivolamento c'è — la regola del proprietario era «opus
solo sul motore», e 15 dispatch opus in un giorno sono troppi — ma valeva il 31%, non l'83%. È il
genere di numero che, una volta scritto in un file di memoria, nessuno rimisura più: questo è il
primo conteggio che lo fa.

Costo reale, sul periodo intero: **USD 1.278,99 di opus su 1.655,93 (77,2%) con 80 agenti**, contro
USD 356,83 di sonnet con 96. A parità quasi perfetta di numero di agenti — 80 contro 96 — un agente
opus è costato **3,9 volte** un agente sonnet.

### 5.2 Venti agenti opus per fix da 150 righe
Il fan-out del 2 settembre (`65f68717`) ha lanciato 20 `workflow-subagent` **tutti su
claude-opus-5** (risolto dai `.meta.json`: 20 su 20), per fix da 110-170 righe (`git show --stat` su
`8bfed52`: 4 file, 110 inserzioni). Quei venti agenti sono 124,9M token di cache-lettura e
USD 101,89 della sessione: **opus dappertutto dove il compito era una modifica locale già
descritta nell'issue**. Due giorni e sette sessioni più tardi, nel lotto 2, la stessa
categoria di lavoro viene ripartita 29 opus e 55 sonnet su 86 dispacci: la scelta per compito era
diventata una regola, e ha retto (§5.1). Che qui fosse un errore lo dice il compito, non il
conto finale: è il costo marginale della delega quando la modifica è sotto la soglia in cui serve
una seconda opinione.

### 5.3 Il piano del lotto 2 è stato riscritto 14 volte; quello del lotto 1 zero
`git log --follow` sui due piani: `2026-09-08-scadenziamento-pregresso.md` ha 15 commit, di cui
**14 emendamenti** fra il 9 e il 10 settembre; `2026-09-08-percorso-ipotesi-budget.md` ne ha 1.
Il significato non è «il lotto 2 era scritto male»: è che **nel lotto 2 il piano è diventato il
quaderno delle scoperte**, e due task su 17 sono nati durante l'esecuzione: il 16 da una decisione
del proprietario a metà lotto (`progress.md:1442`, Ruling 41) e il 17 da un'altra (`:1608`). La
scoperta arriva dal collaudo o dalla revisione, viene decisa, e finisce in un commit `plan(...)`
invece che in un Ruling. Funziona — ogni emendamento è tracciabile — ma il piano smette di essere
il contratto: a metà lavoro nessuno può dire «che cosa resta» leggendolo, e infatti il proprietario
lo chiede 9 volte (§5.8).

### 5.4 Rilievi emersi solo alla revisione finale o al collaudo
Sono i più cari, perché arrivano quando il task è già stato rivisto e mergeato. Quattro casi, tutti
nei registri:

- **lotto 1, 9 settembre — un Critical trovato col browser, invisibile a 467 test**
  (`2026-09-08-percorso-ipotesi-budget/progress.md:289`): `TypeError: Illegal invocation`. Il difetto
  era **del Task 10**, ed è emerso solo quando il cablaggio del Task 15 ha reso l'anteprima
  raggiungibile: «l'anteprima non ha **mai** funzionato: sei passi su sette morti». La revisione del
  Task 10 non l'aveva visto, e nessun test poteva vederlo (`environment: node`, ricevitore non
  controllato). Il coordinatore l'ha corretto da sé invece di aprire un round 2 (`72ae705`).
- **lotto 1 — un rilievo del proprietario, non di un revisore** (`progress.md:433`): i giorni
  medi automatici erano degeneri (DSO proiettato 3.692.922,45 giorni). Trovato eseguendo
  `compute_forecast` e leggendo i `details`, dopo il merge dei task interessati.
- **lotto 1, collaudo pre-merge** (`progress.md:585-631`): R1 (media) e R2 (alta) — i giorni
  dell'anteprima stampati come float grezzo, e l'atterraggio su **un altro scenario** dopo il
  salvataggio. Entrambi dentro un giro di correzione dedicato (`96bebdb`).
- **lotto 2, 10 settembre — revisione finale del branch** (opus, 320k token, `progress.md:2020`):
  tre Important, di cui **I1 è esplicitamente «regressione del Task 6»** e I3 una regressione di
  parità rispetto alla base `40f0332` («smentisce «al centesimo» di `CLAUDE.md:514`»). Il Ruling 56
  li ammette così: «sono regressioni del lotto su scenari che il lotto prometteva identici».

**Quanto è costato.** Le due correzioni di I1 e I3 sono finite nel **giro finale** del lotto 2:
una sola dispatch, a pi. Sul transcript, il worktree `lotto2-giro-finale` porta quattro run — 12,6h
di parete, 890 turni, 911 chiamate di strumento — di cui una singola da 5h08 con 431 turni e 433
chiamate. Poi due ri-revisioni opus dedicate (I1 alle 21:37Z, I3 alle 22:28Z) e una sonnet sui
rilievi minori (21:53Z, `progress.md:2047`). A questo si aggiunge il primo giro di collaudo della
parte 1: 227k token, **bloccato dall'ambiente** — database mai migrato, 0 verifiche OK su 15
(`progress.md:1686`) — e in cambio tre difetti preesistenti trovati per caso, diventati il lotto 3B
(Ruling 48).

**Causa.** Le revisioni di task giudicavano il task contro il suo brief; nessuno giudicava il
prodotto contro la promessa fatta all'utente («l'anteprima funziona», «identico al centesimo»). La
prova sul corpus e il browser erano piazzati in fondo al lotto, per scelta, e infatti è da lì che
escono i difetti veri.

### 5.5 Giri di correzione oltre il primo
Un giro in più è un costo pieno: un implementatore ripreso, un revisore rilanciato, un merge
riaperto. Che cosa si può contare e che cosa no, dai registri:

- **lotto 1 — contato dai marcatori `Task N: fix round K/5`** (32 occorrenze nel registro):
  **12 task su 17 hanno richiesto almeno un giro, 17 giri in tutto, e 5 task (1, 9, 10, 12, 15)
  sono arrivati al secondo giro** — il 70% dei task ha pagato un giro, il 30% due. Quattro verdetti
  «Needs work» all'andata: task 4, 8, 9, 10.
- **lotto 2 — il registro numera i giri in modo diverso**: 16 titoli dichiarano un giro numerato,
  su 10 task; solo due task vanno oltre il primo — **task 10, tre giri** (15 titoli che lo nominano,
  fra ri-revisioni e collaudi) e **task 5, due**. Il che rende il conteggio dei giri
  del lotto 2 **non confrontabile** con i `fix round K/5` del lotto 1: lì è un marcatore, qui è una
  convenzione dei titoli.
- **la misura indipendente, dalle trascrizioni: 19 ri-revisioni** nel periodo — 16 sonnet, 2 opus,
  1 haiku, 1,7h di tempo-agente e 114,6M token di cache-lettura. Sono il numero più pulito di «seconde passate» che questo repo
  possa dare: le prime diciassette stanno fra l'08-09 21:09 e il 10-09 16:41, le altre due sono
  già nel lotto 3B.

Il giro in più, quando serve, costa una ripresa e una seconda revisione: i due giri del task 15
sono costati una ri-revisione opus (10 min) e una sonnet (4 min). Il giro 3 del task 10 ha
richiesto due rapporti di collaudo separati, parte 2A e parte 2B (`progress.md:1905`, `:1984`, 330k
e 332k token l'uno).

### 5.6 Un'implementazione intera gettata via su una premessa falsa
Issue #24, creata il 1° settembre. L'8 settembre: commit `e845f67` alle 15:34 (un file di test da
218 righe, +44 sulle ancore), **revert** `3eac1e3` alle 17:25 («non ha superato la prova»,
−318 righe), e commento all'issue alle 17:28: «**La premessa di questa issue è falsa** —
implementata, verificata sul corpus e revertita». **1h51 di lavoro distrutto**, dentro USD 55,78.
Il costo vero non sono le 1h51: è che un'issue nata da una premessa falsa ha attraversato il
triage che l'aveva creata, un'implementazione con 218 righe di test e un commit, **prima** della
prova sui file reali — l'unico momento in cui qualcuno poteva accorgersi che non stava in piedi. La
rete che ha beccato l'errore è arrivata per ultima, e solo perché quella mattina il proprietario
aveva importato il corpus reale nella cartella `Test/` (messaggio delle 12:16).

### 5.7 Un agente ha passato 4h27 e 33,5M token a leggere prima di scrivere
Il piano del lotto 3A, agente opus "Piano lotto 3A motori" di `b06623a4`, lanciato il 10
settembre alle 17:17:49. Misurato sul suo transcript: **126 turni e 83 chiamate di strumento (60
Bash, 23 Read, zero scritture) per 33,5M token di cache-lettura prima che il file del piano
comparisse**, 4h27 dopo la prima riga. Il proprietario ha chiesto conto prima che il file
arrivasse — «ha bruciato 643k token non sta girando in loop?» alle 21:40:44, cinque minuti prima
della scrittura. Su tutta la vita dell'agente: 169 turni, 63,1M cache-lettura, 4 riprese, picco di
contesto 778k. Gli altri 9 agenti di stesura piani del periodo stanno a 10,8M di
cache-lettura in media e 11 minuti di transcript. Il caso non è un loop: **la stesura del piano non
aveva un perimetro di ricognizione** — leggere tutto il motore per scrivere 14 task.

### 5.8 Il proprietario ha dovuto chiedere "quanti task mancano" 9 volte
Sugli 89 messaggi in `b06623a4`, nove sono richieste di stato o di parallelizzazione: «quindi ci
manca ancora tanto?» (09 08:35), «quanti task mancano?» (09 15:28, 10 10:23), «prossimi step?»
(09 16:17), «quindi il grosso è fatto?» (10 08:37), «non riusciamo a far partire altri task in
parallelo?» (10 08:05), «riusciamo a far partire altri step?» (10 12:35). Tre di queste cadono
**subito dopo una compattazione** (09 09:09 `/compact` → 09 09:14 «ok possiamo far partire lotto
2?»; 10 12:30 `/compact` → 10 12:35 «riusciamo a far partire altri step?»). Il coordinatore ha
lo `stato` completo nel proprio contesto; dopo una compattazione quel quadro è l'ultima cosa che
sopravvive, e nessuno lo ristampa.

### 5.9 I 44 minuti di `sleep` e i 109 comandi falliti
102 chiamate `sleep` nei loop principali (44 minuti di attesa dichiarata) e 109 `tool_result` con
`is_error`, cioè 3,1 ogni 100 chiamate di strumento (3.525). Non è un dramma di per sé: è l'impronta di
un'attesa fatta al buio, visto che lo strumento per non dormire esiste ed è stato usato **tre
volte** in tutto il periodo (`Monitor` ×3, contro 56 `SendMessage`, 15 `ListAgents` e 8 `TaskStop`).

### 5.10 Trentaquattro issue chiuse sei giorni dopo il fix
Mediana di chiusura 152,5 ore, max 170: ma il lavoro era finito il 2 settembre (16 commit in 14
minuti). Le 44 chiusure si dividono in due modi diversi, e questa è la parte che una versione
precedente di questo documento raccontava male:

- **10 issue il 1° settembre**, chiuse a comando dentro la sessione `1e96601e` (10 occorrenze di
  `gh issue close` nel suo transcript, tutte in giornata).
- **34 issue l'8 settembre, fra le 11:35 e le 11:36 di Roma**: un'issue al secondo, `commit_id` **null**
  su tutti gli eventi `closed` (`gh api repos/…/issues/{49,42,35,20}/events`), quindi chiuse da una
  chiamata API e non da un commit sulla default branch. **Nessuna trascrizione di questo repo le
  chiude**: i fix erano stati committati il 2 settembre, e la sessione `4aebaba4` — la candidata
  naturale, quello stesso giorno — è cominciata alle 11:50, quattordici minuti *dopo*. Le ha chiuse
  l'account del proprietario, non un agente.

Due conseguenze. La prima: la causa non è la pigrizia del bookkeeping, è che **i commit citavano le
issue con `— #NN` invece di `Closes #NN`** — il collegamento automatico non poteva esistere, e la
chiusura di 44 issue è diventata un lavoro manuale una settimana dopo. La seconda: il time-to-close
di 152,5 ore non misura il ciclo di lavoro, e non va mai citato come tale.

Le cinque issue aperte alla misurazione sono #50 (ramo infrannuale comparato, dall'8 settembre),
#48 (route C, dal 2 settembre), #24 (quella della premessa falsa, dal 1° settembre) e #51 #52, create
l'11 settembre.

## 6. pi (Qwen locale) come esecutore: che cosa costa davvero

Dodici run nel periodo, più le due di questa analisi (13,4h di parete, 377 turni, 396 chiamate).
**Al netto delle nostre: 12 run, 16,8h di parete, 1.395 turni, 1.480 chiamate di strumento (1.108
Bash, 175 edit, 171 read, 25 write), 1,05M token in uscita, USD 0 di fattura** — modello locale, e
non c'è `cost-state` da leggere: qui il conto lo paga il tempo, non la fattura.

**Che cosa ha prodotto di buono (misurato).** Due lavori di documentazione portati a casa con
verifica indipendente, entrambi citati nei merge:
- riallineamento delle citazioni `file:riga`: 41 citazioni esaminate, 28 corrette, diff di sole
  cifre, terminatori invariati — `progress.md:1874`;
- riscrittura della guida al previsionale: 68 frasi controllate una per una dal revisore sonnet,
  **66 vere, 0 false**, 2 non riverificate, due refusi corretti (`progress.md:2015`).

Per la classe "lettura di molto codice, scrittura di testo" pi ha un vantaggio di struttura, non
di qualità: costa zero, e gira in un worktree mentre Claude tiene il motore.

**Dove è costato.** Tre cose, tutte con prova:

1. **Il tempo di parete non è trascurabile.** Un figlio di pi tenuto acceso 5h08 con 431 turni e
   433 chiamate di strumento, senza un loop: **tutte le 338 chiamate Bash di quella run hanno un
   comando distinto dalle altre** (verificato). Non gira in tondo: esplorare non finisce. Il
   proprietario se ne accorge prima del coordinatore — «pi con il lotto 2 sembra in difficoltà,
   continua a ragionare e fare test … ma non conclude» (10 settembre, 22:36). Confronto sulla stessa
   classe di lavoro: l'equivalente Claude del riallineamento ha fatto 79 chiamate in 16 minuti
   (24,3M cache-lettura, dentro `b06623a4`), pi 94 in 28 minuti.
2. **La consegna era corretta ma parziale, per colpa del coordinatore.** Ruling 55
   (`progress.md:1880`): il worktree di pi era stato creato da una base che **non conteneva i
   commit di documentazione del lotto** — pi ha visto un `CLAUDE.md` con 7 citazioni invece di 15
   e un `API-PREVISIONALE` di 327 righe invece di 591. Ha dichiarato «queste chiavi non esistono
   più», vero nel suo albero, falso sul branch. La sua nota era esatta e inutile. Rimedio: un
   secondo task (A2) sulla stessa cosa.
3. **Il parallelismo è un falso guadagno.** Tre figli pi sullo stesso modello locale rallentavano
   tutti; la regola è diventata «teniamo max 2 agenti pi attivi», e a 17:34 il proprietario
   segnala che «dei 3 children pi solo uno è attivo, gli altri sono terminali vuoti» (worktree
   lasciati vivi dopo il release — `progress.md:2055`).

**Verdetto.** pi sull'esecuzione documentale è **conveniente**: costo marginale zero, esito
verificato, e Claude tiene la revisione. Diventa costoso quando (a) il task non è autosufficiente
— allora esplora per ore; (b) la base del worktree non è l'HEAD integrato — allora consegna
parziale; (c) si contano più di due istanze. Le tre condizioni sono tutte regole di dispaccio, non
di modello. La decisione del proprietario («pi implementa tutto, Claude rivede», 10 settembre 17:26) è
coerente coi dati **a condizione che il «tutto» resti dentro i binari che pi sa percorrere da
solo**.

## 7. I due metodi, messi uno accanto all'altro

| | issue-driven (1-2 settembre) | SDD a lotti (8-10 settembre) |
|---|---|---|
| Unità di lavoro | 46 issue create in due giorni; 44 chiuse, e nessuna da un commit (§5.10) | 34 task su 2 piani (17 + 17), tracker non usato come unità |
| Sessioni / agenti | 7 sessioni di lavoro + 1 di setup, 40 subagenti | 1 sessione coordinatrice, 143 agenti |
| Costo | USD 367,81 in sette sessioni di lavoro (+21,40 nella sessione di setup `13ecc3c9`) | USD 1.202,60 |
| Commit | 54 | 150 (58 + 92 sui due rami) |
| **USD per commit** | **6,81** | **8,02** |
| **USD per 1000 righe di diff** | **29,7** | **32,0** |
| Righe di codice | 12.397 (+10.305/−2.092) | 37.530 (+33.655/−3.875) |
| Giri di revisione per unità | non tracciati: non c'era un registro | lotto 1: 17 giri su 12 task, 5 task al secondo giro · lotto 2: task 10 al giro 3 · 19 ri-revisioni misurate nel periodo (§5.5) |
| Decisioni registrate | 12 AskUserQuestion in 9 sessioni | 63 Ruling numerati, di cui 9 «decisione del proprietario» nel solo lotto 2 |
| Piano corretto dopo la stesura | n/d (l'elenco delle issue *è* il piano) | 14 emendamenti (lotto 2), 0 (lotto 1) |
| Riprese di agenti / compattazioni | 0 / 1 | 56 / 10 |

**Il costo per unità prodotta è dello stesso ordine: 6,81 contro 8,02 USD a commit.** Il
secondo numero è però accusato a una sessione che, oltre ai due lotti, contiene i piani 3A/3B, il
riallineamento della documentazione e il dispaccio di questa analisi: la parte attribuibile ai soli
due lotti sta più vicina al primo. Quello che cambia è **che cosa compri** con quei dollari. Il
ciclo issue ha massimizzato il throughput su difetti indipendenti e piccoli: 16 commit di fix in 14
minuti di fan-out, senza un intervento umano. Il lotto SDD ha massimizzato la qualità delle
decisioni condivise: 63 Ruling numerati e nove «decisione del proprietario» nel registro
non sono burocrazia, sono il
motivo per cui lo scoperto di c/c, il saldo/acconto e il pregresso oggi hanno una semantica scritta
e testata. A un costo per unità quasi uguale corrispondono due prodotti diversi: **non esiste un
metodo economicamente più conveniente, esiste il metodo giusto per la forma del lavoro**.

Dove i due metodi si sono scambiati di ruolo è andata peggio: il ciclo issue ha delegato a 20 opus
dei fix da 110-170 righe (§5.2) pagando la delega senza comprarci niente, e il lotto SDD ha fatto
uscire dalla revisione finale tre regressioni che le revisioni dei singoli task avrebbero dovuto
vedere (§5.4).

## 8. Raccomandazioni

1. **Prima della spec, la prova sul corpus.** Ogni issue che afferma "il file X importa male"
   va aperta con una riga di verifica su un file reale, non con una spec. §5.6: 1h51 e un
   ciclo completo (triage → implementazione → verifica → prova sul corpus → revert) per una
   premessa falsa. §5.4 dice che vale anche dentro un lotto: i difetti veri sono usciti dal browser
   e dalla prova sul corpus, in fondo, mai dalle revisioni di task. La verifica costa minuti: è
   l'ultima cosa che abbiamo fatto.
2. **Un perimetro di ricognizione scritto nel prompt del pianificatore.** «Leggi questi N file,
   poi scrivi.» §5.7: 33,5M token e 4h27 per un piano. Gli altri 9 agenti-piano del periodo stanno a
   10,8M di cache-lettura in media e 11 minuti di transcript: non è un limite che toglie qualità, è
   quello che distingue i casi normali da quello degenrato.
3. **Il modello si sceglie per compito a ogni dispaccio, e il conteggio si misura.** §5.1: 15
   agenti opus in un giorno, 29 nei due giorni del lotto 2. Rimedio concreto: una riga «motore? prima
   revisione del motore? se no, sonnet» nel prompt, e un controllo a fine lotto sui
   `model_richiesto` del proprio `aggregato.json`. Non sulla memoria, che diceva «15 opus su 18
   dispacci»: il numeratore era giusto, il denominatore no, e il rapporto così com'è scritto
   raddoppia la colpa (15/49 = 31%, non 83%).
4. **Lo stato del piano si ristampa da solo dopo ogni compattazione.** §5.8: 9 messaggi per
   sapere una cosa che il registro già dice. Una riga «mancano i task N, M; in volo X; prossimo gate Y»
   in testa a `progress.md` riscritta a ogni merge, e letta ad alta voce dopo ogni ripresa.
5. **Gli emendamenti del piano finiscono nei ruling, non nel piano.** §5.3: 14 commit di
   correzione al piano del lotto 2 contro 0 in quello del lotto 1, e la differenza non è
   pianificazione migliore. Se una scoperta merita un commit `plan(...)`, merita un Ruling con
   dentro il "costo se sbagliato"; il piano resta il contratto.
6. **Un figlio pi va dispacciato dall'HEAD integrato, con un task autosufficiente, e mai in
   tre.** §6: la base sbagliata (Ruling 55), le 433 chiamate senza conclusione, i terminali vuoti. Le tre condizioni sono verificabili in 30 secondi prima di lanciare; il rilascio del
   worktree va fatto subito dopo il merge.
7. **Si scrive `Closes #NN` nel commit, il giorno che si corregge.** §5.10: la mediana di chiusura
   è di 6 giorni mentre il lavoro durava un giorno, e la causa non è la pigrizia del bookkeeping:
   gli oggetti dei commit citavano le issue con `— #NN`, che GitHub non interpreta, quindi 34 issue
   sono rimaste aperte finché qualcuno non le ha chiuse a mano con una chiamata API. Il numero che
   legge chi non c'era è days-to-fix, e time-to-close non lo sostituisce.

## Appendice A — come rimisurare

```bash
cd backend && source venv/bin/activate && cd ..
python3 scripts/analisi_sessioni.py --da 2026-08-24 --out .superpowers/retrospettiva
# schede: .superpowers/retrospettiva/schede/*.md · aggregati: aggregato.{json,md}
```

Lo script non scrive nel repo (l'output sta sotto `.superpowers/`, git-ignorato) e maschera
autonomamente: contenuti dei tool result mai copiati, secret e nomi di azienda sostituiti da
`[omesso]`/`[azienda]`. I nomi vengono da due posti: la tabella `companies` letta in sola lettura
(`--db`) **e** tre forme contestuali in maiuscole — `record <anno> di X`, `testing X`, `>> X` —
perché un'azienda di prova citata nei transcript non era nel database di sviluppo, e il solo elenco
dal DB l'avrebbe lasciata in chiaro.

Due avvertenze per chi rimisura:

- **Le due misure di token non vanno mai sommate insieme.** `subagent_tokens` nella notifica di
  completamento è una misura *per dispaccio* (e sull'ultimo segmento, negli agenti ripresi); la
  somma dei campi `usage` nel transcript è una misura *per vita dell'agente*. Sull'implementatore
  del task 9 del lotto 1: 145.771 token nella notifica, 84M di cache-lettura nel transcript.
  `aggregato.json` tiene la provenienza in `token_fonte` per ogni agente.
- **Un grep di ricerca segreti su tutto il repo trova il masker.** Quattro righe di
  `scripts/analisi_sessioni.py` contengono i pattern letterali con cui i secret si nascondono:
  sono il codice del filtro, non secret. Il report che state leggendo invece non ne contiene
  nessuno.

## Appendice B — le sessioni del periodo

| sessione | quando | attive | USD | agenti | commit | cosa era |
|---|---|---|---|---|---|---|
| `13ecc3c9` | 08/24 → 09/01 | 1h39m | 21,40 | 0 | 2 | setup: triage del rapporto del tester, tre spec, nascita del tracker |
| `1e96601e` | 09/01 | 1h50m | 72,02 | 1 | 14 | 33 issue create, primi `/implement` |
| `979f70ad` | 09/01 | 1h19m | 49,37 | 6 | 6 | issue 15-18 (estrattore IV-CEE) |
| `d6c5a308` | 09/01 | 2h53m | 43,62 | 4 | 5 | issue + prima "caccia ai bug" autonoma |
| `fec77d8b` | 09/01 | 0h39m | 24,58 | 2 | 3 | 0 messaggi del proprietario: notte, lavoro in corso |
| `fd9ae387` | 09/02 | 0h38m | 35,60 | 3 | 1 | review → issue da aprire, fix del segnaposto «auto:» del DSO (#31) |
| `70d3b928` | 09/02 | 1h22m | 40,73 | 4 | 3 | auth JWT con token admin, poi un bug di `/forecast/income` da screenshot |
| `65f68717` | 09/02 → 09/08 | 2h12m | 101,89 | 20 | 4 | fan-out del workflow: 16 commit in 14 minuti, 20 opus (§5.2) |
| `4aebaba4` | 09/08 → 09/10 | 3h51m | 55,78 | 0 | 4 | #50, corpus reale in `Test/`, guardia della #24 → revert, poi debugging di pi |
| `b06623a4` | 09/08 → 09/11 | 29h24m | 1.202,60 | 143 | 16 | coordinatore dei lotti 1 e 2, piani 3A/3B, pi |
| `7a984fbb` | 09/08 | 0h24m | 7,94 | 0 | 0 | segnalazione di un utente in produzione su 4 import |
| `90a1c2d7` | 09/10 | 0h00m | 0,42 | 0 | 0 | 14 secondi: svegliata da un messaggio di orchestrazione, non da una persona |

Le cifre «commit» sono quelle eseguite **dal loop principale** della sessione: i 262 commit del
periodo sono stati scritti per la maggior parte dai subagenti nei propri worktree; i merge sono 23
(`git log --merges --since=2026-08-24 --date=short --pretty='%h|%ad|%s'`, 24 con `--all`).
