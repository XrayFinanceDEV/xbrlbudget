# Retrospettiva — sessioni agentiche dal 24 agosto al 11 settembre 2026

Come ha lavorato un agente di piano su questo repo per 17 giorni di calendario: quanto è
costato, che cosa ha prodotto, dove ha sprecato, e che differenza c'è stata fra i due metodi
usati (issue-driven il 1-2 settembre, subagent-driven-development l'8-10).

Tutte le cifre sono **misurate** da `scripts/analisi_sessioni.py` sulle trascrizioni JSONL, sui
registri SDD, sul tracker e su `git log`. Dove una cifra non è misurata ma ragionata lo dico
esplicitamente (**inferito**), e dove un numero che ricordavo si è rivelato falso lo dico lo
stesso: è successo, vedi §4.1.

## 1. Che cosa è stato misurato

| Fonte | Copertura |
|---|---|
| Trascrizioni Claude (`~/.claude/projects/-home-peter-DEV-budget/*.jsonl`) | 12 sessioni avviate nel periodo, 93.827 righe lette, 2 scartate |
| Trascrizioni dei subagenti (`<sessione>/subagents/**/agent-*.jsonl`) | 170 classificati, 169 con trascrizione |
| `cost-state` (snapshot di fine sessione, include i subagenti) | USD 1.655,93 totali, per modello |
| Registri SDD (`.superpowers/sdd/*/progress.md`) | 11 registri, 4.059 righe; i due del periodo: 685 + 2.191 |
| GitHub (`XrayFinanceDEV/xbrlbudget`) | 47 issue (44 chiuse, 3 aperte), di cui 46 create il 1-2 settembre |
| `git log` su tutti i ref | 246 commit non-di-merge + 23 merge dal 24 agosto |
| Trascrizioni pi (`~/.pi/agent/sessions/`) | 13 run dello stesso modello locale |

Misurazione dell'11 settembre alle 09:21, e un limite grosso da sapere subito: **la sessione
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

## 2. I numeri

| | valore |
|---|---|
| Sessioni principali | 12 (di cui una, `b06623a4`, = il 73% del lavoro) |
| Tempo attivo (pause > 30 min escluse) | 44,7h su 461,0h di parete |
| Subagenti lanciati | 170 · ripresi con `SendMessage` 53 volte · 9 compattazioni del contesto · 5 interruzioni di processo |
| Costo (`cost-state`) | **USD 1.655,93** — opus 1.278,99 · sonnet 356,83 · fable 15,86 · haiku 4,24 |
| Messaggi del proprietario | 169 (9 erano solo `/compact`, 12 iniettati dal ponte di orchestrazione: non richieste umane) |
| Chiamate di strumento nei loop principali | 3.341, con 108 risultati d'errore e 101 `sleep` (43 min di attesa dichiarata) |
| Agenti per lavoro | 66 revisioni · 46 implementazioni · 20 fan-out di workflow · 17 ri-revisioni · 9 stesure di piani · 8 collaudi · 4 ricognizioni |
| Codice | 246 commit non-di-merge su tutti i ref, 23 merge, due rami-lotto da 58 e 84 commit |

La sessione `b06623a4` (8-11 settembre) è il coordinatore dei due lotti SDD: 28,0h attive —
metà di tutto il tempo attivo del periodo — USD 1.202,60, 130 agenti, 53 riprese, 80 messaggi del
proprietario. Per ripartirla per giorno non c'è
di meglio degli snapshot `cost-state` (che non portano un timestamp proprio: li ho agganciati alla
prima riga timestampata successiva): ≈ USD 362 fra l'8 e il 9, ≈ USD 685 il 10, il resto l'11. È
una ripartizione grezza, e il confine fra i due lotti non è netto: il lotto 1 chiude a metà del 9.

## 3. Che cosa ha funzionato

### 3.1 Il fan-out sulle issue: 16 commit in 14 minuti
Il 2 settembre la sessione `65f68717` ha lanciato due ondate di `workflow` in parallelo, 20
subagenti in tutto (primi alle 18:20:28, altri alle 21:33). Sono usciti **16 commit in 14 minuti
di orologio** — 8 fra le 18:24 e le 18:27, 8 fra le 21:37 e le 21:43 — e quindici di essi chiudevano
una issue diversa (`00513d7` ne unisce quattro: #22 #39 #40 #41). I due commit delle 18:12-18:13
sono lavoro del loop principale, appena prima del fan-out. Su tutto il 2 settembre i commit sono
22, sui giorni 1-2 sono 54.

Costo dell'intero ciclo issue: **USD 367,81 in sette sessioni in due giorni**, cioè 6,81 USD per
commit e 27,6 USD ogni 1000 righe di diff (13.327 righe). Il proprietario non è stato interrotto
una volta durante il fan-out: le issue erano state scritte bene il giorno prima.

### 3.2 Il metodo ha tenuto la contabilità delle decisioni, e si è visto
Il registro del lotto 2 porta **126 Ruling numerati** e 22 "decisione del proprietario" in 2.191
righe; quello del lotto 1, 43 occorrenze di "Ruling" in 685. È la differenza fra un lotto che ha
dovuto decidere il comportamento del motore (scoperto, saldo/acconto, pregresso, sweep) e uno che
ha applicato scelte già prese. La prova che serve: `.superpowers/sdd/2026-09-08-scadenziamento-pregresso/progress.md:1440`
(Ruling 41) dove una decisione del proprietario **cambia rotta in corsa** e nasce il task 16.

### 3.3 Una trappola documentata ha smesso di ripresentarsi
Il `churn` di terminatori CRLF/LF: **12 occorrenze** nel registro del lotto 1 (un giro di
correzione bruciato a riscrivere byte, e il coordinatore che decide di riparare lui —
`2026-09-08-percorso-ipotesi-budget/progress.md`, «il churn di terminatori lo correggo io sul
branch, non l'implementatore»), **0 occorrenze** nel registro del lotto 2, dove la stessa verifica
riappare come controllo esplicito («terminatori invariati», `...scadenziamento-pregresso/progress.md:1878`).
Meccanismo: la regola era stata spostata nel prompt dell'implementatore, non solo in quello del
revisore (`MEMORY.md`, voce `mixed-line-endings-hazard`).

### 3.4 Il messaggio di merge porta il verdetto, non solo il titolo
`git log --merges` nel periodo: 23 merge, e quelli del lotto 2 dicono **chi ha verificato e con
che risultato** — `7896b13` «revisione sonnet: 66 frasi vere su 68, 0 false», `1490476`
«revisione sonnet: accettabile, 0 importanti», `59bf9f4` «giro 1». È la tracciabilità che altrimenti
starebbe solo nei report gitignorati.

### 3.5 Un'interruzione di processo non ha cancellato nulla
Il 10 settembre il processo del coordinatore si è chiuso con **quattro agenti in volo**. Il
registro (`...scadenziamento-pregresso/progress.md:1015`) elenca cosa era stato salvato prima di
riprendere (due patch + un file di test copiati fuori dall'albero) e riprende gli agenti dal loro
transcript invece di ridispacciarli: «nessun lavoro perso». Stessa scena, in scala, alla riga 740.
Le 5 «interruzioni» misurate sulle 12 sessioni sono tutte qui o in `4aebaba4`.

### 3.6 Il ciclo di apprendimento funziona davvero
6 file di memoria toccati nel periodo, ciascuno **dopo** un guasto, non in astratto: il 1
settembre per il netting dei fondi (`979f70ad`), il 9 per `git add -A` (`34d3a489`), il 10 per la
scelta del modello, per pi e per lo stato dei lotti (tutti `b06623a4`). E la memoria giusta è
arrivata in tempo: la regola «mai `git add -A` con un agente vivo» è del 9, il giorno dopo
l'errore del coordinatore (`progress.md:239`).

## 4. Che cosa non ha funzionato

### 4.1 Il modello è scivolato verso opus, e la memoria lo raccontava peggio di com'è
La memoria `scelta-modello-subagenti` dice che nel lotto 2 «la scelta è scivolata: 15 opus su 18
dispacci». **Misurato sulle trascrizioni, nei due giorni del lotto 2: 13 implementazioni su 26 su
opus e 14 revisioni su 36 su opus** — circa la metà, non l'83%. Lo scivolamento c'è (la regola del
proprietario era «opus solo sul motore»), ma la cifra annotata in memoria era sbagliata: è il
genere di numero che, una volta scritto in un file, nessuno rimisura più.

Costo reale, sul periodo intero: opus **USD 1.278,99 dei 1.655,93 totali (77,2%) con 79 agenti**,
sonnet USD 356,83 con 84: a parità quasi perfetta di numero di agenti, opus è costato **3,6 volte
sonnet**. Nei soli due giorni del lotto 2 gli 86 agenti lanciati sono 29 opus, 55 sonnet e 2 haiku:
sulle implementazioni la metà è opus (13 su 26), sulle revisioni poco più di un terzo (14 su 36).

### 4.2 Venti agenti opus per chiudere issue da 150 righe
Il fan-out del 2 settembre (`65f68717`) ha lanciato 20 `workflow-subagent` **tutti su
claude-opus-5**, per fix da 110-170 righe (`git show --stat` su `8bfed52`: 4 file, 110 inserzioni).
Su quei due giorni il prezzo per 1000 righe è 27,6 USD; la stessa classe di lavoro, fatta inline
fan-out il 8 settembre (sessione `4aebaba4`: 0 subagenti, 254 Bash nel main loop, 34 chiusure),
è costata 1,64 USD a issue. Non è un confronto di qualità — è il costo marginale della
delega quando il compito è sotto la soglia in cui serve.

### 4.3 Il piano del lotto 2 è stato riscritto 14 volte; quello del lotto 1 zero
`git log --follow` sui due piani: `2026-09-08-scadenziamento-pregresso.md` ha 15 commit, di cui
**14 emendamenti** fra il 9 e il 10 settembre; `2026-09-08-percorso-ipotesi-budget.md` ne ha 1.
Il significato non è «il lotto 2 era scritto male»: è che **nel lotto 2 il piano è diventato il
quaderno delle scoperte**, e tre task su 17 (15, 16, 17) sono nati durante l'esecuzione. La
scoperta arriva dal collaudo o dalla revisione, viene decisa, e finisce in un commit `plan(...)`
invece che in un Ruling. Funziona — ogni emendamento è tracciabile — ma il piano smette di essere
il contratto: a metà lavoro nessuno può dire «che cosa resta» leggendolo, e infatti il proprietario
lo chiede 9 volte (§4.6).

### 4.4 Un'implementazione intera gettata via su una premessa falsa
Issue #24, creata il 1 settembre. Il 8 settembre: commit `e845f67` alle 15:34 (un file di test da
218 righe, +44 sulle ancore), **revert** `3eac1e3` alle 17:25 («non ha superato la prova»,
−318 righe), e commento all'issue alle 17:28: «**La premessa di questa issue è falsa** —
implementata, verificata sul corpus e revertita». **1h51 di lavoro distrutto**, dentro USD 55,78.
Il costo vero non sono le 1h51: è che un'issue nata da una premessa falsa ha attraversato il
triage che l'aveva creata, un'implementazione con 218 righe di test e un commit, **prima** della
prova sui file reali — l'unico momento in cui qualcuno poteva accorgersi che non stava in piedi. La rete che ha beccato l'errore è arrivata
per ultima, e solo perché quella mattina il proprietario aveva importato il corpus reale nella cartella
`Test/` (messaggio delle 12:16).

### 4.5 Un agente ha passato 4h27 e 33,5M token a leggere prima di scrivere
Il piano del lotto 3A, agente opus "Piano lotto 3A motori" di `b06623a4`, lanciato il 10
settembre alle 17:17:49. Misurato sul suo transcript: **126 turni e 83 chiamate di strumento (60
Bash, 23 Read, zero scritture) per 33,5M token di cache-lettura prima che il file del piano
comparisse**, 4h27 dopo la prima riga. Il proprietario ha chiesto conto prima che il file
arrivasse — «ha bruciato 643k token non sta girando in loop?» alle 21:40:44, cinque minuti prima
della scrittura. Su tutta la vita dell'agente: 169 turni, 63,1M cache-lettura, 4 riprese, picco
di contesto 778k. Gli altri 8 agenti di stesura piani del periodo stanno a 10,0M di cache-lettura
in media e 11 minuti di transcript. Il caso non è un loop: **la stesura del piano non aveva un
perimetro di ricognizione** — leggere tutto il motore per scrivere 14 task.

### 4.6 Il proprietario ha dovuto chiedere "quanti task mancano" 9 volte
Sugli 80 messaggi in `b06623a4`, nove sono richieste di stato o di parallelizzazione: «quindi ci
manca ancora tanto?» (09 08:35), «quanti task mancano?» (09 15:28, 10 10:23), «prossimi step?»
(09 16:17), «quindi il grosso è fatto?» (10 08:37), «non riusciamo a far partire altri task in
parallelo?» (10 08:05), «riusciamo a far partire altri step?» (10 12:35). Tre di queste cadono
**subito dopo una compattazione** (09 09:09 `/compact` → 09 09:14 «ok possiamo far partire lotto
2?»; 10 12:30 `/compact` → 10 12:35 «riusciamo a far partire altri step?»). Il coordinatore ha
lo `stato` completo nel proprio contesto; dopo una compattazione quel quadro è l'ultima cosa che
sopravvive, e nessuno lo ristampa.

### 4.7 I 43 minuti di `sleep` e i 108 comandi falliti
101 chiamate `sleep` nei loop principali (43 minuti di attesa dichiarata) e 108 `tool_result` con
`is_error`, cioè 3,2 ogni 100 chiamate di strumento. Non è un dramma di per sé: è l'impronta di
un'attesa fatta al buio, visto che lo strumento per non dormire esiste ed è stato usato **una
volta sola** in tutto il periodo (`Monitor` ×1, contro 53 `SendMessage` e 15 `ListAgents`).

### 4.8 Trentaquattro issue chiuse sei giorni dopo il fix
Mediana di chiusura 152,5 ore, max 170: ma il lavoro era finito il 2 settembre (16 commit in 14
minuti). Le 34 chiusure del 8 settembre sono quelle **del merge** (`ade2320`), non della
correzione. Il time-to-close, qui, misura la pigrizia del bookkeeping, non il ciclo di lavoro.
Tre issue sono ancora aperte (una dal 1 settembre: #24, quella della premessa falsa).

## 5. pi (Qwen locale) come esecutore: che cosa costa davvero

Tredici run nel periodo, di cui una è l'analisi che state leggendo. **Al netto di questa: 11 run,
15,6h di parete, 1.284 turni, 1.359 chiamate di strumento (1.015 Bash, 163 read, 160 edit, 20
write), USD 0 di fattura** (modello locale).

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
   (`progress.md:1879`): il worktree di pi era stato creato da una base che **non conteneva i
   commit di documentazione del lotto** — pi ha visto un `CLAUDE.md` con 7 citazioni invece di 15
   e un `API-PREVISIONALE` di 327 righe invece di 591. Ha dichiarato «queste chiavi non esistono
   più», vero nel suo albero, falso sul branch. La sua nota era esatta e inútile. Rimedio: un
   secondo task (A2) sulla stessa cosa.
3. **Il parallelismo è un falso guadagno.** Tre figli pi sullo stesso modello locale rallentavano
   tutti; la regola è diventata «teniamo max 2 agenti pi attivi», e a 17:34 il proprietario
   segnala che «dei 3 children pi solo uno è attivo, gli altri sono terminali vuoti» (worktree
   lasciati vivi dopo il release — `progress.md:2055`).

**Verdetto.** pi sull'esecuzione documentale è **conveniente**: costo marginale zero, esito
verificato, e Claude tiene la revisione. Diventa costoso quando (a) il task non è autosufficiente
— allora esplora per ore; (b) la base del worktree non è l'HEAD integrato — allora consegna
parziale; (c) si contano più di due istanze. Le tre condizioni sono tutte regole di dispaccio, non
di modello. La decisione del proprietario («pi implementa tutto, Claude rivede», 10/09 17:26) è
coerente coi dati **a condizione che il «tutto» resti dentro i binari che pi sa percorrere da
solo**.

## 6. I due metodi, messi uno accanto all'altro

| | issue-driven (1-2 settembre) | SDD a lotti (8-10 settembre) |
|---|---|---|
| Unità di lavoro | 46 issue (44 chiuse, 3 ancora aperte) | 34 task su 2 piani (17 + 17) |
| Sessioni / agenti | 7 sessioni di lavoro + 1 di setup, 40 subagenti | 1 sessione coordinatrice, 130 agenti |
| Costo | USD 367,81 (+55,78 per le 34 chiusure del 08-09) | USD 1.202,60 |
| Commit | 54 | 142 |
| **USD per commit** | **6,81** | **8,47** |
| **USD per 1000 righe di diff** | **27,6** | **33,0** |
| Righe di codice | 13.327 (+11.233/−2.094) | 36.454 (+32.733/−3.721) |
| Giri di revisione per unità | non tracciati: non c'era un registro | 30 fix round nel lotto 1 (22 di primo giro, 8 di secondo) · 10 ri-revisioni e 4 «giro» nel lotto 2 |
| Decisioni registrate | 12 AskUserQuestion in 9 sessioni | 126 Ruling + 22 decisioni del proprietario (lotto 2) |
| Piano corretto dopo la stesura | n/d (l'elenco delle issue *è* il piano) | 14 emendamenti (lotto 2), 0 (lotto 1) |
| Riprese di agenti / compattazioni | 0 / 1 | 53 / 8 |
| Chiusure in massa senza delega | — | 34 issue il 08-09 inline: 1,64 USD a issue, la cosa più economica del periodo |

**Il costo per unità prodotta è dello stesso ordine: 6,81 contro 8,47 USD a commit.** Il
secondo numero è però accusato a una sessione che, oltre ai due lotti, contiene i piani 3A/3B, il
riallineamento della documentazione e il dispaccio di questa analisi: la parte attribuibile ai soli
due lotti sta più vicina al primo. Quello che cambia è **che cosa compri** con quei dollari. Il
ciclo issue ha massimizzato il throughput su difetti indipendenti e piccoli: 15 issue chiuse in 14
minuti di fan-out, senza un intervento umano. Il lotto SDD ha massimizzato la qualità delle
decisioni condivise: 126 Ruling e 22 decisioni del proprietario non sono burocrazia, sono il
motivo per cui lo scoperto di c/c, il saldo/acconto e il pregresso oggi hanno una semantica scritta
e testata. A un costo per unità quasi uguale corrispondono due prodotti diversi: **non esiste un
metodo economicamente più conveniente, esiste il metodo giusto per la forma del lavoro**.

Dove i due metodi si sono scambiati di ruolo, è andata peggio: quando il ciclo issue ha delegato
a 20 opus dei fix da 110-170 righe (§4.2) ha pagato la delega senza comprarci niente; quando il
lavoro è rimasto nel main loop — il giorno delle 34 chiusure, 0 subagenti, 254 Bash — è venuto il
risultato più economico del periodo.

## 7. Raccomandazioni

1. **Prima della spec, la prova sul corpus.** Ogni issue che afferma "il file X importa male"
   va aperta con una riga di verifica su un file reale, non con una spec. §4.4: 1h51 e un
   ciclo completo (triage → implementazione → verifica → prova sul corpus → revert) per una
   premessa falsa. La verifica costa minuti: è l'ultima cosa che abbiamo fatto.
2. **Un perimetro di ricognizione scritto nel prompt del pianificatore.** «Leggi questi N file,
   poi scrivi.» §4.5: 33,5M token e 4h27 per un piano. Gli altri 8 agenti-piano del
   periodo stanno a 10,0M di cache-lettura in media e 11 minuti di transcript: non è un limite che
   toglie qualità, è quello che li distingue
   dai casi degenerati.
3. **Il modello si sceglie per compito a ogni dispaccio, e il conteggio si misura.** §4.1: 29
   agenti opus in due giorni, e metà delle implementazioni del lotto 2. Rimedio concreto: una riga «motore? prima revisione del
   motore? se no, sonnet» nel prompt, e un controllo a fine lotto sui `model_richiesto` del
   proprio `aggregato.json` — non sulla memoria, che diceva «15 su 18» quando sono 13 su 26.
4. **Lo stato del piano si ristampa da solo dopo ogni compattazione.** §4.6: 9 messaggi per
   sapere una cosa che il registro già dice. Una riga «mancano i task N, M; in volo X; prossimo gate Y»
   in testa a `progress.md` riscritta a ogni merge, e letta ad alta voce dopo ogni ripresa.
5. **Gli emendamenti del piano finiscono nei ruling, non nel piano.** §4.3: 14 commit di
   correzione al piano del lotto 2 contro 0 in quello del lotto 1, e la differenza non è
   pianificazione migliore. Se una scoperta merita un commit `plan(...)`, merita un Ruling con
   dentro il "costo se sbagliato"; il piano resta il contratto.
6. **Un figlio pi va dispacciato dall'HEAD integrato, con un task autosufficiente, e mai in
   tre.** §5: la base sbagliata (Ruling 55), le 433 chiamate senza conclusione, i terminali vuoti. Le tre condizioni sono verificabili in 30 secondi prima di lanciare; il rilascio del
   worktree va fatto subito dopo il merge.
7. **Si chiude un'issue il giorno che la si corregge.** §4.8: mediana di chiusura di 6 giorni
   quando il lavoro durava un giorno. Se serve il merge per poter chiudere, si commenti
   l'issue al commit: il numero di days-to-fix è l'unico che legge chi non c'era.

## Appendice A — come rimisurare

```bash
cd backend && source venv/bin/activate && cd ..
python3 scripts/analisi_sessioni.py --da 2026-08-24 --out .superpowers/retrospettiva
# schede: .superpowers/retrospettiva/schede/*.md · aggregati: aggregato.{json,md}
```

Lo script non scrive nel repo (l'output sta sotto `.superpowers/`, git-ignorato) e maskera
autonomamente: contenuti dei tool result mai copiati, secret e nomi di azienda sostituiti da
`[omesso]`/`[azienda]` (i nomi sono letti in sola lettura da `financial_analysis.db`, `--db`).

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
| `13ecc3c9` | 24-08 → 01-09 | 1h39 | 21,40 | 0 | 2 | push, triage del rapporto del tester, 3 spec, nascita del tracker |
| `1e96601e` | 01-09 | 1h50 | 72,02 | 1 | 14 | 33 issue create, primi `/implement` |
| `979f70ad` | 01-09 | 1h18 | 49,37 | 6 | 6 | issue 15-18 (estrattore IV-CEE) |
| `d6c5a308` | 01-09 | 2h52 | 43,62 | 4 | 5 | issue + prima "caccia ai bug" autonoma |
| `fec77d8b` | 01-09 | 0h38 | 24,58 | 2 | 3 | 0 messaggi del proprietario: notte, lavoro in corso |
| `fd9ae387` | 02-09 | 0h38 | 35,60 | 3 | 1 | review → issue da aprire, e fix del segnaposto «auto:» del DSO (#31) |
| `70d3b928` | 02-09 | 1h22 | 40,73 | 4 | 3 | auth JWT con token admin, poi un bug di `/forecast/income` da screenshot |
| `65f68717` | 02-09 → 08-09 | 2h12 | 101,89 | 20 | 4 | fan-out del workflow: 16 commit in 14 minuti, 21 issue |
| `4aebaba4` | 08-09 | 3h50 | 55,78 | 0 | 4 | 34 chiusure inline, #24 falsa → revert, discussione vision |
| `b06623a4` | 08-09 → 11-09 | 28h00 | 1.202,60 | 130 | 16 | coordinatore dei lotti 1 e 2, piani 3A/3B, pi |
| `7a984fbb` | 08-09 | 0h23 | 7,94 | 0 | 0 | segnalazione di un utente in produzione su 4 import |
| `90a1c2d7` | 10-09 | 0h00 | 0,42 | 0 | 0 | 14 secondi: svegliata da un messaggio di orchestrazione, non da una persona |

Le cifre "commit" sono quelle eseguite **dal loop principale** della sessione: i 246 commit del
periodo sono stati scritti per la maggior parte dai subagenti nei propri worktree.
