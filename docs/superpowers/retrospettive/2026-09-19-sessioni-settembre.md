# Retrospettiva — sessioni agentiche dall'11 al 19 settembre 2026

Seconda puntata. Misura la settimana dopo il [rapporto del 10 settembre](2026-09-10-sessioni-agosto-settembre.md)
e risponde prima di tutto a una domanda: **le sue sette raccomandazioni sono state applicate?**
Poi rifà la stessa analisi sul periodo nuovo, aggiungendo una fonte che allora non esisteva: le
**sessioni pi** (Qwen 3.8 su provider locale `gx10`), che dal 11/09 diventano il grosso
dell'esecuzione.

- Periodo misurato: `2026-09-11 00:00 → 2026-09-19 00:00` (Europa/Rome, fine esclusiva).
- Strumento: `scripts/analisi_sessioni.py`, esteso in questo branch (commit `4554e42`) con
  `--pi`, la lettura delle sessioni pi e la colonna **esecutore** nell'aggregato.
- Output: `/home/peter/DEV/budget/.superpowers/retrospettiva/2026-09-19/` — 78 schede pi,
  4 schede Claude, `aggregato.{json,md}`.

**Come leggere i numeri.** Gli identificatori di sessione sono scritti spezzati (`b066…23a4`)
perché il controllo sha non li scambi per commit: le prime quattro e le ultime quattro cifre
dell'id a otto. Ogni cifra è **misurata** (conteggio dello script o del registro) o
**inferita** (l'interpretazione che ne traiamo), e le due cose sono sempre distinte. Il `cost-state`
delle sessioni Claude è cumulativo **sull'intera vita della sessione**, non sul periodo: quando una
sessione è iniziata prima dell'11/09 il suo USD non è scindibile, e la cosa è dichiarata dove conta.
I token degli eventi del 19/09 (giorno fuori finestra) non passano dallo script: sono misurati
direttamente sui transcript, e detto ogni volta.

---

## 1. Linea del tempo

Otto giorni, due motori che si scambiano i ruoli: la settimana comincia con l'ultimo merge del lotto
3A e finisce con un tool di riallineamento scritto da un pi nell'albero principale mentre un altro
agente ci committava sopra.

| quando | che cosa | prove |
|---|---|---|
| **11/09** | Chiusura del lotto 3A (motori del previsionale e rendiconto): 13 merge in `feat/scadenziamento-pregresso`, il netto alle 18:05. Decisione del proprietario sul modello: opus non è più il default nemmeno per il motore. | `git log --merges --since=2026-09-10` (9 merge con «lotto 3A» nel subject); `memory/scelta-modello-subagenti.md`, «Aggiornamento 2026-09-11» |
| **11/09** | Il collaudo 3A produce quattro difetti → **18 run pi quel giorno** (chiusura 3A, le quattro indagini, il giro finale del lotto 2: 23,1h di parete) e le issue #51-#58 | `aggregato.md` (sweep giornaliero); `.superpowers/sdd/2026-09-11-indagine-difetti-collaudo-3a/`; `gh issue list` |
| **12/09** | **Ondata finale di correzioni**, 8 task: due slot pi (motore, client), revisione finale opus. 3 task su 8 al giro 2. Merge `d7bd09f` | `.superpowers/sdd/2026-09-12-ondata-finale-correzioni/progress.md:3-4` («Esecuzione: pi (worker Orca), max 2 attivi»), `:663-668` |
| **13/09** | Nasce il **piano del report finale** (M1 web + M2 PDF Typst): `1f66cdf`. È il piano che verrà corretto di più: 10 commit `--follow`, 6 heading di task aggiunti in corsa | `git log --follow docs/superpowers/plans/2026-09-13-report-finale-e-pdf-typst.md` |
| **14/09** | M1: **29 run pi in un giorno** (34 sui worktree `m1-00`…`m1-09`, 5 il 13/09), gate, review, preflight, adversarial. La sessione `dfec…81cc` apre il coordinatore del filone report | `aggregato.md`, tabella «Sessioni pi» — righe con worktree `m1-*` |
| **14-15/09** | **Giro di rilievi del percorso ipotesi**: 16 task, base `d5ef65a`, pi + sonnet in parallelo (2 pi + 2 sonnet, decisione del proprietario). 17 merge il 15/09, tutto in main con `7c258a8` | `.superpowers/sdd/2026-09-15-percorso-ipotesi-rilievi/progress.md:7-9` |
| **16/09** | Ricreazione dello scenario budget cancellato (`feat/budget-recovery`, merge `1f09819`); rapporto di riallineamento (1598 citazioni candidate, strategia a tre livelli «escalata») | `docs/superpowers/allineamento/2026-09-16.md:1,10` |
| **17/09** | **Errore del coordinatore**: due worktree creati da `main` mentre il branch di lavoro era 31 commit avanti; un pi legge un piano vecchio e si ferma. Il M2-02 partorisce 54 pagine: il proprietario ferma tutto («non è quello che ho chiesto») e nasce il dossier v4 | `memory/worktree-agenti-partono-da-main.md`; `sdd/2026-09-17-dossier-v4/m2-02d.md:3` |
| **18/09** | Dossier v4: cinque merge di gruppo (M2-02D «fondazione/dati/piano/indicatori/allegati», `4eeeb9e`…`df5ec17`), contratto estratto dalla v4 (`f853889`). **Imposte secondo il commercialista**: merge `073927b` | `git log --merges --since=2026-09-18`; `memory/artifact-e-la-specifica.md` |
| **18-19/09** | M2-02G fase 2: tracce A/B (`31c5c4f`, `7375006`). Rapporti di riallineamento del 18 e del 19: lo strumento si specializza (`--puntatori`, `--sha`, `2318e18`/`84b2b88`) | `git log --merges --since=2026-09-19`; `docs/superpowers/allineamento/2026-09-19.md` |
| **19/09** | Un pi che lavora **nell'albero principale** dichiara quattro errori propri, tutti nel racconto e nessuno nei commit; due agenti committano sullo stesso repo nello stesso minuto | transcript `~/.pi/agent/sessions/--home-peter-DEV-budget--/2026-09-19T05-07-07-535Z_01a0b80f-*.jsonl`, `2026-09-19T06:00:38Z` e `09:30:01Z`; §5.5 qui sotto |

---

## 2. Numeri

**Sulle sessioni iniziate nel periodo, Claude costa 715 USD di API — ma non è il costo del periodo,
e nemmeno un confronto con i 1.656 della settimana scorsa: esclude la sessione più cara del periodo,
`b066…23a4` (223 agenti, 11-13/09), il cui `cost-state` è cumulativo e non scindibile.** Il periodo
non è costato meno: è in parte inscomponibile. Con un esecutore nuovo che di API non pesa nulla:
Claude resta il revisore, pi diventa l'implementatore.

| | settimana precedente | questo periodo |
|---|---|---|
| sessioni principali Claude | 12 | **4** (+1, la `4db3…4d3d` del 19/09, fuori finestra) |
| trascrizioni di subagente Claude | ~145 | **256 lette, 133 classificate** |
| run pi | 12 | **78** |
| USD (cost-state, **sole sessioni iniziate nel periodo; esclusa la `b066…23a4`, non scindibile — non è un confronto con i 1.656 della colonna a sinistra**) | 1.655,93 | **715,36** |
| commit nell'albero (`--all`, finestra `--until=2026-09-19T00:00`) | 262 | **357** (297 non-merge, 60 merge) |
| righe JSONL lette / scartate | n/d | **175.405 / 1** |

Le quattro sessioni principali Claude del periodo (più una quinta, tutta del 19/09 e quindi fuori
finestra), con il loro `cost-state` (cumulativo a fine sessione):

| sessione | quando (nel periodo) | attivo | USD | agenti | commit | merge | compatt. |
|---|---|---|---|---|---|---|---|
| `b066…23a4` | 11/09 → 13/09 | 22,9h | 1.709,45 *(vita intera, iniziata l'8/09 — non scindibile)* | 223 | 5 | 51 | 6 |
| `dfec…81cc` | 14/09 → 18/09 | 29,5h | 637,90 | 33 | 55 | 52 | 6 |
| `6020…fd96` | 18/09 | 2,3h | 72,65 | 0 | 2 | 1 | 0 |
| `f64f…9350` | 14/09 | 0,9h | 4,81 | 0 | 0 | 0 | 0 |
| `4db3…4d3d` | 19/09 (fuori finestra) | — | 31,65 | 0 | 0 | 0 | 0 |

**Per esecutore** (`aggregato.json` → `per_esecutore`, contati nel periodo):

| esecutore | unità | turni | strumenti | durata attiva | input | output | cache letto |
|---|---|---|---|---|---|---|---|
| Claude principale | 4 sessioni | — | 3.848 | 55,7h | 8,01M (in+out, main loop) | — | — |
| subagente Claude (sonnet) | 129 agenti | — | 8.344 | 38,3h | 30,1k | 6,46M | 2.768,02M |
| subagente Claude (opus) | 4 agenti | — | 294 | 1,5h | 10,0k | 181,6k | 98,15M |
| pi | 78 run | 6.716 | 7.371 | 69,4h | 710,20M | 4,69M | 0 |

Le due lezioni del tavolo: il **cache-lettura di sonnet (2,77 miliardi)** è il numero che paga la
factura, ed è dove Claude è molto più efficiente di pi; pi non ha cache (`cacheRead: 0` sempre,
`aggregato.json` → `sessioni_pi[*].token_cache_lettura`) e ri-paga l'intero contesto a ogni turno —
710M di input contro 4,7M di output, un rapporto di **151 input per 1 output** (inferito dai due
conteggi).

**Distribuzione del lavoro Claude** (133 agenti classificati): revisione 43, implementazione 33,
scrittura di piani 18, ri-revisione 8, ricognizione 7, collaudo 4, altro 20.

**Giri di correzione e rilievi per task**, dal conteggio dei marker nei quattro registri SDD del
periodo (`grep -o 'giro [0-9]` sulle cartelle):

| registro | task | «giro 1» | «giro 2» | «giro 3» | oltre |
|---|---|---|---|---|---|
| `2026-09-10-lotto3a-motori-rendiconto` | 13 | 36 | 2 | 3 | 1 (giro 4), 1 (giro 5) |
| `2026-09-11-indagine-difetti-collaudo-3a` | 5 + 3 indagini | 1 | 0 | 0 | 0 |
| `2026-09-12-ondata-finale-correzioni` | 8 | 8 | 3 | 0 | 0 |
| `2026-09-15-percorso-ipotesi-rilievi` | 16 | 4 | 0 | 1 | 0 |
| `2026-09-17-dossier-v4` | ~20 ricevute | — | — | — | marker «giro» assenti: il registro è a ricezioni, non a giri |

**Claude contro pi, sulla stessa classe di lavoro.** I task documentali del filone report: 16 agenti
Claude con «report|dossier|typst|pdf» nella descrizione consumano 624,89M di token-notifica e 6,1h
aggregate; le 11 run pi dei worktree `m2-*` consumano 135,11M di input, 0,87M di output e 12,7h di
parete a costo API zero. Il pi è più lento e più caro in tempo (più del doppio) e non costa in
dollari; Claude costa in dollari e finisce prima.

---

## 3. Le sette raccomandazioni del 10/09

Una riga per ciascuna: applicata / parziale / no, con la prova. È la sezione più importante: una
raccomandazione non applicata costa due volte, la prima per il difetto e la seconda per averla
letta e ignorata.

| # | Raccomandazione | Esito | La prova |
|---|---|---|---|
| 1 | **Prima della spec, la prova sul corpus.** | **parziale** | Dove c'era un file vero, la prova è arrivata prima della spec: le quattro indagini dell'11/09 partono da scenari reali e chiudono in un giorno, e i due difetti del 17/09 (54 pagine, «molto diverso da quello richiesto») nascono da una constatazione a schermo, non da una spec. Dove il corpus serviva **al renderer del PDF** non è stata fatta: M2-02 genera 54 pagine con 229 test verdi sopra, e la verifica «su dati veri» arriva solo il 19/09 — «la fixture sintetica non aveva né chiusura né storico e ha nascosto tavole a 4 colonne invece di 5, due grafici e una pagina intera, sotto 229 test verdi» (`memory/artifact-e-la-specifica.md`). Un giorno di refactoring. |
| 2 | **Un perimetro di ricognizione scritto nel prompt del pianificatore.** | **no** | La regola non è da nessuna parte: `regole-comuni.md` del dossier v4 (36 file, il registro più curato del periodo) non contiene mai la parola «perimetro» nel senso della raccomandazione — compare solo come «Worker attivi e loro perimetro, da NON toccare». Sui 18 agenti «scrittura di piani» del periodo il cache-lettura mediano è 8,83M con un max di 71,59M (`aggregato.json` → `agenti`): nessuno scivolone da 33,5M come quello della scorsa retrospettiva, ma è un dato di fatto, non un perimetro dichiarato. |
| 3 | **Il modello si sceglie per compito a ogni dispaccio, e il conteggio si misura.** | **applicata** | È la raccomandazione che ha funzionato meglio. Il conteggio ora esiste: la colonna `esecutore` e il blocco `per_esecutore` di `aggregato.json` (aggiunta in commit `4554e42`). Misurato: **4 agenti opus su 133 (3%)**, tutti e quattro «revisione» (`agenti[*].famiglia_modello == "opus"`). La regola dell'11/09 è rispettata: vedi §5.3. |
| 4 | **Lo stato del piano si ristampa da solo dopo ogni compattazione.** | **parziale** | Il sintomo è migliorato: «quanti task mancano / a che punto siamo» chiesto **2 volte in 8 giorni** contro 9 della settimana scorsa (§5.4). Ma il meccanismo non c'è: non una riga in testa a nessun `progress.md` del periodo, nessun `stato.md` in testa ai 3 registri nuovi. Il miglioramento viene dal canale sostitutivo — il proprietario usa `check`/`worker-read` di Orca, non il registro. |
| 5 | **Gli emendamenti del piano finiscono nei ruling, non nel piano.** | **no** | La prova che avevo raccolto dice il contrario dell'«applicata», e la correggo: i **6 heading di task aggiunti in corsa** stanno nel **piano**, non nei ruling (§5.1), e nel dossier v4 i Ruling sono **zero** — le due deviazioni più costose del periodo (il fermo del 17/09, il contratto estratto il 18/09) vivono in file di memoria, non in righe di registro. Se mai è parziale per un verso: la direzione del rimprovero si è invertita, e i 28 Ruling numerati dell'ondata del 12/09 e i 33 del registro 3A mostrano che *quando il registro viene usato* lì finiscono le decisioni — ma il periodo in cui il piano è stato emendato di più (§5.1, §5.2) è esattamente quello in cui i ruling non sono stati scritti. |
| 6 | **Un figlio pi va dispacciato dall'HEAD integrato, con un task autosufficiente, e mai in tre.** | **parziale** | La terza parte è quella violata: **4 run pi nello stesso istante alle 11:45 dell'11/09** (sweep sugli intervalli, `aggregato.json` → `sessioni_pi`), e il 14/09 è un giorno di 29 run. Il task autosufficiente regge nei fatti (le ricezioni del dossier: «BASE `997068b`», «base `884718d` (verificato con `git log --oneline -1` prima di iniziare — invariato)»). L'HEAD integrato è quello che è mancato davvero — vedi §5.2, che è la voce più costosa del periodo. |
| 7 | **Si scrive `Closes #NN` nel commit, il giorno che si corregge.** | **no** | Misurato: **1 commit su 357** porta `Closes #NN` nel corpo nel periodo (`git log --all --since=2026-09-10T22:00 --until=2026-09-19T00:00 --pretty=%b \| grep -c 'Closes #'` → `4dc1296`, `Closes #51 / Refs #52`). Le 8 issue create e chiuse nel periodo sono state chiuse a mano: la mediana di **1,16 giorni** tra creazione e chiusura è il tempo di un ciclo di lavoro, non il segno di un collegamento automatico. La colpa non è la svista: nessuno ha scritto la regola in un posto che l'implementatore legge (`regole-comuni.md` del dossier non la cita, e nei 4 registri «Closes» non compare mai). |

**Totale: 1 applicata, 3 parziali, 3 no.** Il pattern regge, ma si è assottigliato: l'unica
applicata (la 3) è precisamente quella che ha partorito un **artefatto verificabile** — un campo in
`aggregato.json`; le tre non applicate sono quelle che richiedevano una **nuova abitudine di
scrittura** in un file che nessuno ha toccato (il perimetro nel prompt, `Closes #NN` nel commit, gli
emendamenti nei ruling). Le tre parziali dicono la stessa cosa da un'altra riva: il meccanismo non è
stato scritto mai, e il sintomo è migliorato per vie sostitutive. Una raccomandazione che non diventa
un campo, una riga di codice o un test non si applica da sola.

---

## 4. Che cosa ha funzionato

**4.1 Il fan-out pi sui task autosufficienti è diventato il modo normale di chiudere un lotto.**
Il 14/09, 29 run pi (34 complessive sui worktree `m1-*`, 5 il 13/09) chiudono il filone M1 del report (gate,
review, preflight, adversarial, coding) con 0,82M di token output e 10,9h di parete. Prova: `aggregato.md`, tabella «Sessioni pi», worktree
`m1-*`, e il merge M1 in `7c258a8` («e report finale M1 fino a `12ecfb7`»).

**4.2 Il passaggio del testimone Claude→pi ha retto sulla qualità, non solo sul costo.**
I Ruling numerati del periodo stanno dove servivano: 28 nell'ondata finale del 12/09 (base, slot,
conflitti pre-flight) e 33 nel registro 3A chiuso l'11/09, con dentro
sempre il costo se sbagliato. Prova: `.superpowers/sdd/2026-09-12-ondata-finale-correzioni/progress.md:34-44`
(Ruling 1-3, «Costo se sbagliato: un merge in più del previsto») e il `Registro dei task` dello
stesso file: «Ruling 21 — si corregge» (`:637`). Nel dossier v4, zero: è §5.2.

**4.3 Il metodo della prova sul corpus ha smesso di essere una raccomandazione ed è diventato
procedura, dove il corpus esisteva.** Le quattro indagini dell'11/09 partono da scenari reali e
producono 8 issue nel giro di un giorno, con mediana di chiusura di 1,16 giorni (8 create e chiuse
nel periodo, `gh issue list`). È l'esatto contrario del 2026-08-24→09-11, dove 44 issue sono state
chiuse 6 giorni dopo il fix.

**4.4 Il centesimo e il Decimal sono diventati un vincolo di dispaccio, non una correzione a valle.**
Il registro del 15/09 documenta il ciclo completo: una deviazione «respinta» perché il motore
convertiva il pareggio in float per far tornare un atteso float del piano, la regola «details
annidati in Decimal» aggiunta a `regole-comuni.md` **e al piano**, il worker avvisato con
`terminal send` prima che finisse. Prova:
`.superpowers/sdd/2026-09-15-percorso-ipotesi-rilievi/progress.md:29-38`.

**4.5 La stampa ha smesso di essere un'emergenza.** Dopo il 17/09 il PDF ha un contratto generato
(`contracts/dossier_page_contract.json`, `--check` che fallisce se diverge dalla v4) e test di
conformità parametrizzati per pagina, con le non conformità come `xfail` dichiarati: l'elenco
**è** la lista di lavoro. Prova: `docs/agents/riprodurre-un-artifact.md` §5,
`sdd/2026-09-17-dossier-v4/m2-02g-contratto-pagine.md:14-40`.

**4.6 La memoria del progetto ha smesso di raccontare e ha iniziato a misurare.**
`scelta-modello-subagenti.md` (aggiornata l'11/09) non dice più «15 opus su 18 dispacci» ma porta la
misura giusta («opus USD 1.278,99 su 1.655,93 = 77%») e nomina il rapporto che l'ha prodotta; e
chiude con la correzione che la retrospettiva stessa aveva chiesto. Prova: il file, blocco
«Aggiornamento 2026-09-11».

---

## 5. Che cosa non ha funzionato

### 5.1 Il piano del report finale è stato riscritto 9 volte, e i task aggiunti in corsa sono 6

**Che cosa è successo.** Il piano del filone report (`2026-09-13-report-finale-e-pdf-typst.md`) è
l'unico del periodo con emendamenti a catena: 10 commit di cui 9 dopo la stesura, e 6 heading di
task che non c'erano al primo `git add`.

**Quanto è costato.** Misurato dal `--follow`: i 6 task in più si distribuiscono su 3 giorni
(`02983d9` il 15, `9d0ce08` il 17-18) e ciascuno trascina un ciclo proprio di dispaccio, ricezione e
merge: le ricezioni del dossier sono ~20, contro i 23 heading di task della stesura originale.
La riscrittura non è
stata gratis nemmeno in token: i 18 agenti «scrittura di piani» del periodo sommano 1,75h di durata
con un massimo di 44 minuti su un singolo draft (`aggregato.json` → `agenti`, `tipo_lavoro ==
"scrittura di piani"`).

**La prova.** `git log --oneline --follow docs/superpowers/plans/2026-09-13-report-finale-e-pdf-typst.md`
→ 10 righe; il confronto heading-per-heading fra una versione e l'altra produce
`M2-00B/M2-00C/M2-02A` (in `02983d9`) e `M2-02B/M2-02C/M2-08` (in `9d0ce08`).

**La causa.** Il piano è stato scritto prima di sapere quale fosse il risultato accettabile: la forma
del PDF non era nel contratto, e quando è arrivata la prova visiva il piano è diventato il posto dove
correggere — invece che i ruling. Vale al contrario della raccomandazione 5: quella dice che gli
emendamenti vanno nei ruling, qui l'emendamento *è* il lavoro. Ma la raccomandazione regge lo stesso
per una parte: dei 10 commit di `docs(piano)`, nessuno è un Ruling e nessuno dice il costo se
sbagliato.

### 5.2 Il dossier PDF: due giorni di lavoro orchestrato e uno per rifarne la forma

**Che cosa è successo.** Il proprietario consegna un artifact di riferimento, l'anteprima v4 (33
pagine), e chiede di riprodurlo. Il 16/09 M2-02 produce 54 pagine che rispettano «griglia, font,
testatina, footer e riquadro commento» e non la composizione: «il PDF è coerente con ciò che era
scritto e **diverso dall'anteprima v4** che il proprietario vuole». Il 17/09 il proprietario ferma
tutto; il 18/09 nasce M2-02G, che rinuncia a descrivere la forma a parole e la **estrae** dal
generatore della v4; il 19/09 la verifica accetta su dati veri.

**Le tre ipotesi che il repo avanza, verificate una per una sui transcript e sui registri.**

1. *«Il brief descriveva il contenuto, mai la forma» → confermata, ed è la causa prima.*
   Prova diretta nel registro: «Il piano e le specifiche descrivevano l'estetica a parole; i criteri
   di accettazione misuravano altro» (`sdd/2026-09-17-dossier-v4/m2-02g-contratto-pagine.md:3-7`).
   La forma a parole era nel brief: «KPI + grafico margini + tabella CE 9 righe»
   (`docs/agents/riprodurre-un-artifact.md` §1), che è una descrizione di contenuto.
2. *«Spec e piano hanno dichiarato l'artifact non vincolante» → confermata, tempi compresi.*
   La frase nasce nella nota V3 dell'artifact, 15/09 **16:19**
   (`inbox/artifacts/2026-09-15-report-finale/ANTEPRIMA-V3.md:3-5`, «Il numero di pagine è proprio
   del campione, non un limite o un obiettivo per i report effettivi»; le note hanno l'ora sul
   disco: V3 16:19, V4 16:25, V5 16:36), ed entra nella spec (`2026-09-15-report-budget-dossier-design.md:62`,
   «le sue 33 pagine non sono un vincolo») e nel piano (`2026-09-13-report-finale-e-pdf-typst.md:909`,
   con il richiamo alla v4 a `:923`) con lo stesso commit, `02983d9` del 15/09 **16:39**:
   `git log -S "non dalle 33 pagine del campione" -- <piano>`. La memoria diceva «venti minuti dopo
   che l'artifact era nato»: **venti minuti, esatto**. Una precedente stesura di questo rapporto
   giudicava il claim «non verificabile» e attribuiva la clausola a `1f66cdf`: falso su tutti e due
   i punti — le note di rilascio stanno su disco con la loro ora, e il piano non ha «un solo commit
   nel giorno» (§5.1 ne conta 10, tutti entro la finestra). La clausola è poi rimasta in vigore
   quattro giorni, fino al 18/09.
3. *«Si è distribuito il ventaglio prima del pilota» → confermata, e costa più delle altre due.*
   M2-02D è «Quattro agenti in parallelo, un gruppo ciascuno» (`m2-02d-fase2.md:4`): cinque merge di
   gruppo nello stesso giorno (`4eeeb9e`…`df5ec17`) su un contratto che nessuno aveva validato su una
   pagina sola.

**Quanto è costato.** Misurato: **45 run pi sui worktree `m1-*`/`m2-*`** (34 + 11,
`aggregato.json` → `sessioni_pi` raggruppate per worktree) — 220,18M di token input, 1,68M di output
e **23,6h di parete**; più i 16 agenti Claude del filone (624,89M di token-notifica, 6,1h). La
sola famiglia `m2-*` vale 11 run, 12,7h e 23 commit. **I tre file di `mappatura` del registro
`2026-09-17-dossier-v4` (brief + pagine 1-11 + pagine 12-33, 615 righe) sono la traduzione a mano
dell'artifact**, e su quella traduzione un check indipendente trova «**tre righe di questa tabella
erano sbagliate**» (`riscontro-grafici-v4.md:36`): 3 su 21 righe di grafici, come dice la memoria.
Il lavoro rifatto è misurabile anche come merge: 13 merge di dossier in due giorni (5 il 17,
8 il 18).

**La causa.** Tre, in ordine di costo. (a) L'artifact è stato trattato come esempio di *contenuto*
e non di *layout*, e nessun documento diceva quale delle due fosse la consegna — finché non è stato
scritto, il 19/09: `docs/agents/riprodurre-un-artifact.md` §1. (b) Il contratto è stato **trascritto
a occhio** invece che **estratto**: da lì i 3/21 sbagliati, e un brief sbagliato si moltiplica per il
numero di agenti che lo leggono (ibid. §4). (c) La verifica era sul modello dati (229 test verdi) e
non sulla pagina: nessuna rete guardava il PDF, e le fixture sintetiche non avevano né chiusura né
storico (§1, `memory/artifact-e-la-specifica.md`).

**Che cosa i dati smentiscono dell'ipotesi della memoria.** La memoria attribuisce la colpa anche al
piano e alla spec come testi; i dati dicono che il problema non era la qualità della prosa — il
piano del 13/09 era scritto bene e misurava le cose giuste — era che **nessuno dei tre documenti
conteneva la forma**, e la forma non era descrivibile a parole in modo verificabile. È una
distinzione che cambia il rimedio: non «scrivere spec migliori» ma «estrarre il contratto dal
sorgente dell'artifact». Che è esattamente ciò che M2-02G ha poi fatto, e ha funzionato al primo giro
(3 tracce, 3 merge, nessuna ri-revisione nei 4 giorni di registro del dossier).

### 5.3 I worker pi: costo zero, e un giorno a testa per pagarlo

**Che cosa è successo.** Il passaggio a pi come implementatore principale è stato deciso l'11/09
dopo la retrospettiva. Nel periodo pi fa **78 run, 6.716 turni, 7.371 chiamate di strumento, 68
commit**, con **243 comandi falliti (3,3% delle chiamate)** e 16 compattazioni.

**Quanto è costato.** In API: zero, dichiarato dal formato (`cost.total = 0` su tutti i 6.716 messaggi assistant del
periodo; nessun `cost-state` da leggere). In tempo di parete: **69,4 ore** cumulate, con una media
di 53 minuti a run. In rework: misurabile dal rapporto input/output — 710,20M contro 4,69M, **151
token letti per ogni token scritto** — perché pi non ha cache e ri-paga il contesto a ogni turno; e
dai 4 casi di *abort* (`stopReason: "aborted"`, 4 su 6.716 turni).

**Consegne accettate al primo giro.** Il marker nei registri non distingue l'esecutore, quindi lo si
legge dove il registro nomina chi lavora: l'ondata del 12/09 (tutto pi) chiude **5 task su 8 al primo
giro** e 3 al secondo (`grep -o 'giro [0-9]' progress.md` → 8×«giro 1», 3×«giro 2»), con i tre giri 2
che sono correzioni di dettagli (conguaglio al centesimo, codice campo come etichetta) e mai di
premise. Il lotto del 15/09 (pi + sonnet) documenta deviazioni accettate/respinte task per task, e
non un solo rework completo.

**Il caso del 19/09: un andamento o un episodio?** L'ipotesi della consegna era che un pi, il 19/09,
avesse dichiarato quattro errori propri tutti nel racconto e nessuno nei commit. **Misurato, è vero,
ed è una cosa più specifica di un errore di modello.** I quattro sono nominati in due messaggi della
stessa run (`01a0…b80f`, `/home/peter/DEV/budget`, 19/09 05:07→15:44, 280 turni, 22 commit):

1. 06:00:38 — un falso positivo sua: «correzione mechanically-authorized … **era un falso mio**», una
   riga dentro un fence ` ```markdown `, quindi un modello e non un rimando. Annullata in `ad86cc4`
   dopo aver committato `0ac033d`.
2. 06:00:38 — una scansione manuale che «ha prodotto 2 candidati, **entrambi falsi**, entrambi per
   recinti non saltati».
3. 06:50:41 — «il mio controllo di esistenza era `git cat-file -e`, e **rispondeva verde su commit
   scossati**»: due sha citate nel rapporto esistono come oggetti ma non sono raggiungibili da
   HEAD, e `git gc` li cancellerà.
4. 09:30:01 — «I earlier narrated having *rewritten* the skill's collection section into commit-first.
   **Never happened** … Fourth self-error today, same shape: plausible, not read.»

**Verdetto: un andamento del modo di lavorare, non un errore del modello.** Tre dei quattro hanno la
stessa forma: un'affermazione scritta **senza leggere**, e la quarta è il racconto di una cosa fatta
da un altro (la sessione concorrente, §5.5). Il punto diagnosticamente importante è l'asimmetria:
i 22 commit di quella run reggono tutti al controllo incrociato (ogni sha citata che ho verificato
con `git merge-base --is-ancestor` è raggiungibile, e le due che non lo sono il pi le ha trovate da
sé). È il racconto che mente, non il codice. Che il problema non sia pi-specifico lo prova il fatto
che il rimedio inventato quel giorno è uno strumento, e serve a entrambi gli esecutori: `--sha` di
`scripts/riallinea.py` (`2318e18`) verifica la **raggiungibilità**, non l'esistenza, con i tre verdetti
distinti `antenato/orfano/inesistente` — ed è lo stesso difetto che la prima retrospettiva aveva
incontrato su un greppatore ingenuo. La regola da tener ferma è quella che il pi stesso formula alle
15:44: «un numero non contato non si scrive».

**Che cosa è andato bene, per onestà.** 68 commit a costo API nullo su 78 run; e sul filone report
il modello della settimana scorsa è diventato prassi: 45 run pi su `m1-*`/`m2-*` producono 31 commit
in cinque giorni di lavoro, con gli agenti Claude del filone (16, per lo più gate e review) a fare da
rete; e i giri 2 sono sempre e solo di finitura.

### 5.4 I comandi falliti e le attese

**Che cosa è successo.** 243 comandi falliti pi (3,3%) e 56 Claude nel periodo; `sleep` per 75
chiamate / 2.030 secondi (34 minuti) sulle sessioni Claude e 41 chiamate / 1.646 secondi (27 minuti)
sulle run pi. Il singolo picco è il giro finale del lotto 2: 19 falliti su 433 chiamate, e 108 invochi
dello stesso comando bash (`aggregato.json` → `sessioni_pi`, worktree `lotto2-giro-finale`, run
`01a0…8d83`, 3h28m di parete).

**Quanto è costato.** ~61 minuti di `sleep` cumulati su otto giorni (Claude 75 chiamate / 2.030s,
pi 41 / 1.646s), e il giorno 11/09 — 18 run pi, 23,1h — è anche quello con la run da 108 invochi
dello stesso comando.

**La prova.** `aggregato.json` → `per_sessione[*].sleep_s`, `n_sleep` e `bash_top_ripetuti`.

**La causa.** Il polling del coordinatore: attendere un worker leggendo il terminale a intervalli
fissi, che è il comportamento che la prima retrospettiva aveva già contato (44 minuti di `sleep`) e
che non è stato sostituito da nulla — `check --wait`/`ask` esistono e sono l'alternativa, ma nessuno
li ha messi nelle `regole-comuni`.

### 5.5 Gli errori del coordinatore: la base sbagliata, e due agenti che committano sullo stesso albero

**Il worktree su base sbagliata (17/09).** `orca-ide orchestration worker-start --worktree new-child`
**senza** `--base-branch`, e l'Agent tool con `isolation: "worktree"`, creano il worktree da `main`
anche se il branch corrente ne è 31 commit avanti: un pi ha letto un piano vecchio di 31 commit e si
è fermato; un agente Claude, istruito a controllare, si è fermato senza toccare nulla e il suo
worktree è stato rimosso. Prova: `memory/worktree-agenti-partono-da-main.md` (misurato il 17/09, con
gli SHA), e la linea difensiva ora nel prompt: ogni ricezione del dossier inizia con «base `884718d`
(verificato con `git log --oneline -1` prima di iniziare — invariato)».

**I commit concorrenti nell'albero principale (19/09).** Due agenti hanno scritto sullo stesso
`/home/peter/DEV/budget`: il pi `01a0…b80f` e un altro che committava a distanza di minuti.
**Misurato, e non è una sensazione**: `cc14811` e `6e12c37` portano lo **stesso timestamp al secondo**
(07:53:20, due commit `docs(allineamento)` diversi dello stesso giro), e `6e12c37` conteneva
**la correzione di un errore del pi**, committata per prima da qualcun altro. Il pi se n'è accorto e
l'ha dichiarato: «Una sessione concorrente sta committendo su questo repo» (06:00:38). Costa: un
rapporto di riallineamento che è «opera di entrambe», e nessun agente sapeva quale fosse la versione
buona finché non è stato confrontato con git.

**Il polling.** §5.4: 61 minuti di `sleep`, e la domanda «quanti task mancano» chiesta due volte
perché il registro non la ristampa.

**La causa, unica per tutti e tre.** Il coordinatore usa il meccanismo giusto (worktree, `check`,
registro) ma con un default non verificato: il default del worktree è `main`, il default del
coordinatore in attesa è `sleep`, e il default di un albero condiviso è che qualcuno ci scriva. Ogni
volta che il default era esplicitato nel prompt, il difetto non è apparso (le ricezioni del dossier
non hanno un caso di base sbagliata).

### 5.6 Il rapporto di riallineamento si scrive da sé, ma l'ultima migrazione resta manuale

**Che cosa è successo.** Cinque rapporti nel periodo (11, 13, 16, 18 e 19/09). Quello dell'11 è
esaustivo sul suo intervallo (98 citazioni verificate, modo `diff`), e dal 16 la strategia diventa a
tre livelli («escalata», 1.598 candidate). Ma il rapporto del 19/09 contiene una frase che vale come
un mezzo fallimento: «il rilievo 5 **non è effetto di una regola di questo strumento**: è fuori dalla
lista chiusa (è una descrizione di comportamento) e l'autorizzazione è venuta dal proprietario».

**Quanto è costato.** Il corpus dello strumento è cresciuto tre volte in otto giorni (1.598
citazioni candidate il 16/09, 642 il 18, 34 affermazioni il 19 quando passa ai commit), e i
falsi positivi sono il prezzo: «ritirata la correzione del link — falso positivo» (`ad86cc4`),
e i candidati del check «2/2 falsi» (§5.3 caso 2).

**La prova.** `docs/superpowers/allineamento/2026-09-11.md:10` (98 citazioni),
`2026-09-16.md:1,10` (1.598, «escalata»), `2026-09-19.md:10`.

**La causa.** Lo strumento verifica ciò che ha una forma meccanica (percorsi, simboli, sha) e il
problema che resta — l'affermazione falsa su un comportamento — non ne ha una. È il confine onesto di
una campagna di riallineamento, non un difetto: ma va detto, perché è la ragione per cui il rapporto
del 19/09 dice «lo trova soltanto chi legge».

---

## 6. Claude e pi come esecutori, uno accanto all'altro

| | Claude principale | subagente Claude | pi |
|---|---|---|---|
| costo API nel periodo | USD 715 (sessioni iniziate nel periodo) | incluso nel `cost-state` del principale: sonnet 815,87 / opus 1.570,02 di vita intera | **USD 0** |
| token | 8,01M in+out sul main loop | sonnet 2,77 miliardi di cache-lettura | 710,20M input, 4,69M output, **zero cache** |
| unità prodotte | 4 sessioni, 62 commit, 104 merge | 133 agenti classificati (43 revisione, 33 implementazione, 18 piani) | 78 run, 68 commit, 6.716 turni |
| durata attiva | 55,7h | 39,8h (sonnet + opus) | 69,4h |
| falliti | 56 comandi | 0 errori API | 243 comandi (3,3%) + 4 abort |
| tempo medio per unità | — | ~18 min/agente | ~53 min/run |

**Costo per consegna accettata, per come si può misurare.** Se la consegna è un commit: Claude
(principale + subagenti) ha prodotto 62+ commit a 715 USD, pi 68 commit a 0 USD e 69,4h di macchina
locale. Se la consegna è un task accettato al primo giro, il confronto va fatto dove i due hanno
lavorato sulla stessa cosa: **sul filone report**, Claude ha speso 624,89M di token-notifica e 6,1h
per 16 agenti, pi 220,18M di input e 23,6h per 45 run, con 5 task su 8 accettati al primo giro
sull'ondata del 12/09 (esecuzione interamente pi) e nessun rework completo nei 16 task del 15/09.
**Conviene l'uno quando la consegna è un giudizio, l'altro quando è
un lavoro meccanico su un contratto scritto bene.** Il periodo conferma la regola data il 10/09
(«pi implementa tutto, Claude rivede») con una precisazione che i dati impongono: regge finché il
contratto c'è — dove il contratto andava **scoperto** (il layout del PDF, §5.2), pi ha iterato per
giorni senza che nessuno gli dicesse che era fuori strada, perché nessun messaggio d'errore
esiste per una pagina brutta.

**Quando conviene l'uno o l'altro, in tre righe.** Pi: task autosufficiente, base verificata,
contratto esplicito, accettazione meccanica (test, hash, `--check`), ≤2 istanze. Claude:
ricognizione, piani, revisione, qualunque cosa dove il criterio di accettazione vive nella testa di
chi legge. E la regola che il periodo ha imparato a caro prezzo — **la forma di un output visivo non
è specificabile in prosa**: si estrae, e poi la si verifica con gli occhi su un pilota da 5 pagine.

---

## 7. Raccomandazioni

Ordinate per impatto stimato. Le prime quattro sono nuove, le ultime tre chiudono il conto delle
sette vecchie.

1. **La consegna di un artifact visivo è il layout, e il contratto si estrae: pilota da 5 pagine,
   un solo agente, poi il ventaglio.** §5.2. Impatto: un giorno di rework su otto, e la cosa era già
   costata mezzo agosto al grafico malato. Prova che funziona: M2-02G, tre tracce e tre merge senza
   una ri-revisione. Da scrivere come regola, non come memoria: `regole-comuni.md` deve contenere la
   riga «il brief di una pagina nomina blocchi, ordine, `kind` del grafico, serie, colonne — estratti,
   non trascritti»; `docs/agents/riprodurre-un-artifact.md` §1-4 lo dice già a chi lo legge, non a chi
   dispaccia.
2. **Il default di ogni meccanismo di dispaccio va verificato o reso esplicito nel prompt.**
   §5.5. Impatto: un pi al lavoro su 31 commit di codice vecchio, e un rapporto di riallineamento
   scritto da due agenti che non lo sapevano. Costo se sbagliato: lavoro fantasma, e una blame che non
   dice chi. Rimedio già pronto: `--base-branch` sempre, `git log --oneline -1` in ogni brief (le
   ricezioni del dossier lo fanno già, e infatti lì il difetto non compare), e mai due agenti
   committanti sullo stesso albero — con l'eccezione dichiarata del riallineamento notturno, che
   nell'albero principale ci deve stare.
3. **Un'affermazione che non ha una misura non si scrive, e uno sha si cita solo se è raggiungibile.**
   §5.3. Impatto: quattro errori di racconto in una run da 22 commit perfetti — il costo non sono i
   minuti annullati (`0ac033d` → `ad86cc4`), è che il coordinatore ha dovuto fare da fact-checker di
   un testo, il lavoro più caro che c'è. Rimedio: `scripts/riallinea.py --sha` è nato ieri (`2318e18`)
   con i tre verdetti `antenato/orfano/inesistente`, e va richiamato **dopo** il commit che pubblica
   il documento — prima, le sha del documento stesso non sono raggiungibili (è capitato a questo
   rapporto, in fase di collaudo); e la sua assenza dalla lista chiusa del riallineamento è
   il rilievo 5 di `2026-09-19.md`.
4. **Il polling si sostituisce, non si scoraggia: `check --wait`/`ask` nelle `regole-comuni`, e mai
   `sleep` in un loop.** §5.4. Impatto: 61 minuti di `sleep` e una domanda di stato in più.
   È la raccomandazione 4 della settimana scorsa non applicata per mancanza di meccanismo: la riga
   «mancano i task N, M; in volo X; prossimo gate Y» non l'ha scritta nessuno, e la domanda del
   proprietario è rientrata da 9 a 2 soltanto perché Orca offre `check`.
5. **(vecchia 7, da cambiare) Il collegamento fra issue e commit non è una buona pratica: è un campo
   del template.** §3.7. Impatto stimato: la mediana di 1,16 giorni è già buona, quindi l'impatto non
   è il ritardo — è che `days-to-fix` resta cieco e la prossima retrospettiva dovrà chiedere di nuovo
   «chi ha chiuso cosa». La raccomandazione com'era scritta non funziona: ha chiesto un'abitudine a
   357 commit e ne ha ottenuta una. Va sostituita da un meccanismo: o `Closes #NN` nel template di
   `regole-comuni.md` (dove l'implementatore lo legge davvero), o un check a fine lotto che elenca le
   issue chiuse a mano — **non** un richiamo nel prompt, che è il livello a 1/357 di adesione.
6. **(vecchia 2 e 4, da tenere con un'altra forma) Le raccomandazioni che chiedono una nuova abitudine
   di scrittura vanno convertite in un artefatto o muoiono.** §3.2, §3.4, §3.5. La prova si è
   assottigliata con la correzione della riga 5 di §3 — dalle «due applicate» ne resta **una**, ed
   è precisamente quella che ha partorito un campo in un JSON (`esecutore`, `per_esecutore`); le tre
   non applicate chiedevano tutte una riga in un file (il perimetro nel prompt del pianificatore, la
   riga di testa di `progress.md` era una via, `Closes #NN` nel commit un'altra, gli emendamenti nei
   ruling la terza) che nessuno ha scritto. Le eccezioni
   confermano: la regola «details annidati in Decimal» il coordinatore l'ha scritta dentro
   `regole-comuni.md` il giorno stesso, e infatti il float non è più riapparso. Questa voce vale come
   meta-regola: quando una
   raccomandazione non ha un posto dove vive, non è una raccomandazione, è un augurio.
7. **(vecchia 6, da restringere) «Mai in tre» sui pi non regge al confronto con i dati: lo si
   espliciti come limite di throughput, non di qualità.** §3.6, §5.3. Impatto misurato: il 14/09
   sono 29 run pi in un giorno e M1 si chiude in un giorno; le due settimane in cui i pi erano 2 sono
   quelle in cui il proprietario segnalava i terminali vuoti. Il limite di due è nato da un
   rallentamento del modello locale su 3 istanze — va rimisurato su gx10 (se il collo di bottiglia è
   l'LLM, il numero giusto dipende da quanto parallelismo regge; se è il disco o il contesto, non lo
   sa nessuno dei due registri). Nel frattempo: la base verificata e il task autosufficiente restano
   regole, e sono quelle che hanno tenuto.

---

## Appendice A — come rimisurare

```bash
python3 scripts/analisi_sessioni.py --da 2026-09-11 --a 2026-09-19 \
    --out /home/peter/DEV/budget/.superpowers/retrospettiva/2026-09-19
# 4 sessioni Claude (+1 fuori finestra), 256 trascrizioni di subagente (133 classificate), 78 run pi
# righe lette 175.405, scartate 1 · schede in schede/*.md, aggregati in aggregato.{json,md}
```

Lo script ora legge anche le sessioni pi: una run per file, worktree, modello, provider, durata
attiva, chiamate per strumento, comandi falliti (`isError`), `git commit` eseguiti (sola parte di
comando prima di un eventuale heredoc, come sul percorso Claude) e token per messaggio. Il formato
pi **riporta i token** (`usage.input/output/cacheRead/cacheWrite/reasoning/totalTokens/cost`) e
**non riporta cache** (sempre 0): per questo le colonne dei due esecutori non sono confrontabili a
parità di cifra, e la riga «Nota» in testa alla tabella `Per esecutore` lo dice.

Tre avvertenze per chi rimisura:

- **Il `cost-state` Claude è cumulativo sulla vita della sessione, non sul periodo.** `b066…23a4`
  riporta USD 1.709,45 per una sessione iniziata l'8/09; nel periodo la sua parte non è scindibile.
  Per un numero onesto: 435,28 USD dalle sessioni **iniziate** nel periodo, più il residuo di
  `b066…23a4`.
- **La riga con un solo `type` in testa al file non è un messaggio.** Le sessioni pi iniziano con
  `session`, `model_change`, `thinking_level_change`; i contatori (turni, token, strumenti) guardano
  solo `message/assistant`, e il filtro `da <= ts < fine` è applicato **prima** di contare, non dopo.
- **Le due misure di token non vanno mai sommate.** Vale come la settimana scorsa:
  la notifica è per-dispaccio, la somma degli `usage` è per-vita, e l'input pi non è cache.

## Appendice B — le sessioni del periodo

Claude (4 principali nel periodo, più la sessione del 19/09 fuori finestra; attive e USD dal
`cost-state`, che include i subagenti):

| sessione | quando | attive | USD | agenti | commit | merge | cosa era |
|---|---|---|---|---|---|---|---|
| `b066…23a4` | 11/09 → 13/09 | 22,9h | (1.709,45 vita) | 223 | 5 | 51 | chiusura lotto 3A, quattro indagini, ondata finale, revisione finale opus |
| `f64f…9350` | 14/09 | 0,9h | 4,81 | 0 | 0 | 0 | apertura M1, il portafoglio dei task report |
| `dfec…81cc` | 14/09 → 18/09 | 29,5h | 637,90 | 33 | 55 | 52 | coordinatore del filone report: M1, M2-02, il fermo del 17/09, il dossier v4, M2-02G |
| `6020…fd96` | 18/09 | 2,3h | 72,65 | 0 | 2 | 1 | imposte secondo il commercialista |

pi (78 run, raggruppate per famiglia di worktree; intere in `aggregato.md` → «Sessioni pi»):

| campagna (worktree) | run | turni | attive | commit | falliti | output | input |
|---|---|---|---|---|---|---|---|
| lotto 2 — giro finale (11/09) `lotto2-*` | 6 | 963 | 10,0h | 8 | 32 | 0,70M | 130M |
| lotto 3A (11/09) `lotto3a-*` | 11 | 855 | 9,0h | 6 | 26 | 0,57M | 77M |
| ondata finale (12/09) `ondata-*` | 3 | 662 | 8,3h | 5 | 24 | 0,50M | 76M |
| analisi retrospettiva #1 (10-11/09) `retrospettiva-sessioni` | 1 | 325 | 4,2h | 1 | 14 | 0,24M | 43M |
| M1 report (14/09) `m1-*` | 34 | 1.286 | 10,9h | 8 | 42 | 0,82M | 85M |
| percorso ipotesi rilievi (15/09) `rilievi-*` | 9 | 812 | 9,0h | 12 | 34 | 0,64M | 89M |
| M2 dossier (17-18/09) `m2-*` | 11 | 1.146 | 12,7h | 23 | 46 | 0,87M | 135M |
| altro (documentazione, main tree) | 3 | 667 | 5,3h | 5 | 25 | 0,35M | 74M |

> Le cifre «falliti» sono chiamate di strumento con `isError: true`; i 4 abort e le 16 compattazioni
> sono nel blocco `sessioni_pi[*]` di `aggregato.json`.
