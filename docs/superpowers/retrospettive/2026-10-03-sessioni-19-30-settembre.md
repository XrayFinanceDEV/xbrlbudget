# Retrospettiva — sessioni agentiche dal 19 al 30 settembre 2026

Terza puntata **sulle sessioni**, dopo le [sessioni del 24/08-11/09](2026-09-10-sessioni-agosto-settembre.md)
e le [sessioni dell'11-19/09](2026-09-19-sessioni-settembre.md). Misura gli ultimi dodici giorni di
settembre e chiude il conto delle **sette raccomandazioni del 19/09**.

Una precisazione d'ordine, perché i numeri si incrociano: il [rapporto del 26/09
sulla rilavorazione](2026-09-26-rilavorazione-settembre.md) misura settembre **dai diff git**
(churn, sopravvivenza, giri di correzione) e su quello non torna nulla: dove serve lo si cita.
Questa puntata rifà invece l'analisi delle **sessioni** sulla finestra che il rapporto del 19/09
non copriva, `2026-09-19 00:00 → 2026-10-01 00:00` (Europa/Rome, fine esclusiva).

- Strumento: `scripts/analisi_sessioni.py`, invariato.
- Output: `.superpowers/retrospettiva/2026-10-03-periodo/` — 4 schede Claude, 10 run pi,
  `aggregato.{json,md}` (misure fatte il 03/10).
- Repo: `/home/peter/DEV/budget` e i worktree collegati; registri SDD letti nell'albero principale
  e in `budget-intermedio` + `archivio-worktree`.

**Come leggere i numeri.** Gli id di sessione sono spezzati (`c84c…b587`): prime e ultime quattro
cifre del primo gruppo. Ogni cifra è **misurata** (conteggio dello script, di git, di un registro)
o **inferita** (l'interpretazione che ne traiamo), e le due cose sono sempre distinte.

**L'avvertenza che conta, sul costo.** Tutte e quattro le sessioni principali sono iniziate **dentro**
la finestra, ma `c84c…b587` era **ancora aperta all'ora della misura** (03/10): il suo `cost-state`
(1.118,94 USD) copre la vita intera dal 23/09 e include quindi i giorni 01-03/10 (Task 24-28 del
percorso snello), che sono fuori periodo. **Il costo del periodo non è ripartibile e qui non viene
stimato**: si dichiara. Le altre tre sessioni (339,58 USD) sono chiuse e pulite. Anche il conteggio
dei subagenti cresce fra due letture della stessa finestra: il rapporto del 26/09 leggeva 158
trascrizioni su 19→27; qui, leggendo il 03/10 sulla finestra fino al 30/09, sono **242**.

---

## 1. Linea del tempo

Dodici giorni, due metà quasi opposte: la prima costruisce (quattro prodotti nuovi: report
intermedio, motore mappa, Business plan/infrannuale/Word), la seconda **corregge** (i tre lotti
AMBIENTA e il percorso snello, e due terzi dei suoi commit sono `fix:`).

| quando | che cosa | prove |
|---|---|---|
| 19/09 | Chiudono in main le due retrospettive delle sessioni; un pi nell'albero principale (rialineamento) dichiara quattro errori di racconto — già messi a verbale dal rapporto del 19. Nasce il tool `riallinea --sha`. | merge `c8585f4`; `2318e18`, `84b2b88`; retro 19/09 §5.3 |
| 20/09 | **Zero commit.** Il tester lavora. | `git log --all` (giorno vuoto); retro 26/09 §1 |
| 21/09 | Report intermedio Typst dell'infrannuale in main + indicatori di crisi dal server + import analitico IV-CEE. | merge `cea80ec`, `ccab5f8` |
| 22/09 | Nasce il **motore mappa** (spec e piano in giornata, pilota usa-e-getta poi promosso a motore); 53 commit nel giorno, il branch resta fuori main alla misura del 26/09 (70 commit in volo). | `f4d3483`…`6d611d8`; retro 26/09 §1, §3.6 |
| 23/09 | Tre giorni di PDF in un giorno: **Business plan** ReportLab, route A/B e C su **Qwen** («basta haiku ai banchi»), il reference del committente in `inbox/` alle 15:28. 69 commit. Si spegne la sessione `4db3…4d3d`. | merge `2a6ce25`, `62bfed1`; memory `banchi-solo-qwen`; `inbox/` date su disco |
| 24/09 | Report infrannuale, **Word**, e il dossier Typst **staccato** (`6d2c447`); fix dei piani multipli. | merge `2e8e992`, `8c57b3d`, `6d2c447`, `fc4e8c2` |
| 25/09 | Il foglio del consulente (`Verifica_piano_Ambienta_problemi.xlsx`, 14:49) → **banco di triage**: 21 rilievi, verdetti con xfail strict. Run pi notturna di riallineamento (357 turni, 2,8h). | `ffdb32d`…`8eaffab`; run `01a0d89b` |
| 26/09 | **85 commit, il giorno più denso del mese**: tre lotti di fix AMBIENTA + il **percorso snello** che parte all'alba (Task 1-8 in un giorno, ondate parallele di sonnet) + il rapporto del 26/09 mergiato. **Il proprietario decide per iscritto: «agenti sonnet al posto di pi».** | merge `78e8278`, `4167b65`, `bf6b87a`, `1bf0fa0`…`9651a99`; ledger `2026-09-26-import-pdf-snello/progress.md:4` e Ruling «implementatori sonnet al posto di pi» |
| 27-28/09 | Snello Task 9-23: banco dei 50 file in passate successive, diagnosi dei ripieghi, due lotti di correzioni dal banco, merge a punto (t12, t15, t17). | merge `6fec515`…`f2eeb1a`, `5da76ab`; ledger (44 marker di fix round) |
| 29/09 | **Merge in main di `feat/import-struttura`** (`854a6a1`), dietro `IMPORT_MOTORE=snello`. Zero commit di codice: la revisione finale opus del branch «non ancora fatta» al momento del merge. | ledger, riga «Proprietario 2026-09-29» |
| 30/09 | **Zero commit.** Il mese si chiude fermo; il lavoro riparte il 2/10 con Task 24-28, fuori finestra. | `git log --all` (giorno vuoto) |

Il mese in una riga, debitamente citato dal rapporto del 26/09: si costruisce molto e si butta poco
(9 righe su 10 dell'aggiunto vive), e la malattia non è il codice morto — è il `fix:` che attraversa
un confine di KPI dopo che il prodotto è dichiarato finito.

---

## 2. Numeri

### 2.1 Le due metà del periodo

| | 19→26/09 (costruzione) | 26→30/09 (correzione) | periodo |
|---|---|---|---|
| commit non-merge (tutti i ref, data autore) | 189 | 145 | **334** |
| merge | 13 | 29 | **42** |
| commit `fix*` | 55 (29%) | **95 (66%)** | 150 (45%) |
| righe aggiunte / rimosse | +45.804 / −3.987 | +22.466 / −2.904 | **+68.270 / −6.891** |
| commit con `Closes #NN` nel corpo | 0 | 0 | **0** |

Per giorno (non-merge): 19→4, 20→**0**, 21→8, 22→53, 23→69, 24→22, 25→14, 26→**85**, 27→47,
28→13, 29→0 (solo il merge), 30→**0**. Il 45% del mese in `fix:` non è un giudizio sul codice: è
l'osservatore esterno (il consulente, il banco dei 50 file) che incassa le rate di costruzione della
prima metà — lettura già sviluppata nel rapporto del 26/09 §3.1.

### 2.2 Le sessioni

| | Claude principale | subagente Claude | pi |
|---|---|---|---|
| unità | **4 sessioni** (2 coordinatori veri: `4db3…4d3d` 19→23, `c84c…b587` 23→03/10; `b187…1d76` parentesi; `facb…af1b` svegliata da orchestrazione) | **242 con trascrizione, tutti classificati**: sonnet 223 · opus 11 · haiku 8 | **10 run**: 4 sono la retrospettiva del 26/09 che si autopsia, 3 rialineamento/notturno, 2 manutenzione, 1 il worktree della retro del 19 |
| durata attiva | 60,6h (4db3 22,4 · c84c 37,6) | 111,4h (implementazione 80,6) | 12,7h |
| USD | sessioni chiuse 339,58; `c84c…b587` 1.118,94 **non ripartibile** (nota in testa) | nel `cost-state` del principale (sonnet 956,47 · opus 473,52 · fable 26,09 · haiku 2,44) | **0** (gx10 locale) |
| produzione | 66 commit, 66 merge, 57 riprese, 14 compattazioni | cache-lettura 5,08 **miliardi** (il numero che paga la fattura) | 1.718 turni, 31 commit, 88 comandi falliti (5,1%), 6 compatt., **0 abort** |
| token | 6,81M in+out main loop | sonnet output 1,46M | 204,80M input / 1,09M output — rapporto **188:1** (inferito), niente cache |
| `sleep` | 74 chiamate / 1.208s = **20 min** | — | 10 chiamate / 880s = **15 min** |

**Il sorpasso Claude→pi dell'estate si è rovesciato di nuovo, e questa volta per iscritto.** Le run
pi del periodo sono 10 contro le 78 del periodo precedente, e nessuna lavora sul percorso snello:
il ledger nomina l'esecutore a ogni ondata («Ondata 2 avviata da 1bf0fa0: Task 2 e Task 4,
implementatori sonnet»), e la decisione del proprietario è la quarta riga del file: «parti con la
prima ondata agenti sonnet al posto di pi» (26/09). Il mix Claude misura 93 agenti di
**implementazione** (80,6h) accanto a 86 di revisione e 36 di **ri-revisione** — 36 contro gli 8
 del periodo precedente: il rigiro è diventato un passo del flusso, non un'emergenza (e
 l'implementazione, che lì era 33 agenti, qui è 93).

**Distribuzione del lavoro** (242 agenti): implementazione 93 · revisione 86 · ri-revisione 36 ·
altro 18 · ricognizione 9. Gli 11 opus (4,5% del totale) sono le revisioni finali — la regola del
26/09 («opus per le revisioni finali») tiene come rapporto, non come numero assoluto: 11 contro 8
della misura del 26/09, perché la finestra si è allungata di quattro giorni.

### 2.3 I giri di correzione, dai registri SDD

I registri aperti o attivi nel periodo sono 11 (dieci chiusi prima del 26 + il snello). Marker
`fix round|fix wave` e righe `Ruling` contati con grep su ogni `progress.md`:

| registro | task | fix round | Ruling | esito revisione finale |
|---|---|---|---|---|
| import mappa (22/09) | 12 → 28 | **22** | 26 | Yes — 3 Important |
| route C qwen (23/09) | 6 | 8 | 9 | With fixes (doc only) |
| route A/B qwen (23/09) | 6 | 0 | 7 | With fixes — 1 Critical |
| report BP / infrannuale / docx (23-24/09) | 12 / 9 / 5 | **0 / 0 / 0** | 6 / 16 / 11 | tutte With fixes, 0 Critical sul prodotto |
| triage AMBIENTA (25/09) | 6 | 2 | 9 | With fixes — verdetti sbagliati su 4 ID, corretti lo stesso giorno |
| fix AMBIENTA lotti 1-3 (26/09) | 8 / 8 / 2 | 7 / 10 / 4 | 9 / 14 / 3 | lotto 2: **No — with fixes**, e il branch invecchia un giro |
| **percorso snello (26/09 →)** | 23 nel periodo | **44** | **58** | il merge del 29/09 **prima** della revisione finale opus del branch |

Il snello è il registro più denso del mese (307 righe alla misura — registro vivo, quindi con
anche ottobre; 28 task nominati, 43 riferimenti a `review`), e ha una forma nuova: **ogni giro di
correzione è chiuso da un "controllore" che verifica il fix round sul diff o sui numeri** («round 2
verificato dal controllore sui numeri 22 file: cambiano solo 158 e 337»). I 44 marker non sono 44
ondate: la forma canonica `Task N: fix round K` distinta ne conta **8**, e molti giri sono registrati
in prosa («fix round inviato al T24», «Fix round 2: N1-N4 risolti»); il più costoso è il caso di
scuola — i tre round del Task 22 sul segno dei costi, nati dal banco (passata3: «D2M ok →
squadrato»).

### 2.4 Il costo del periodo, in tre righe oneste

- Le sessioni **chiuse** nel periodo costano 339,58 USD (misura diretta dal `cost-state`).
- La sessione aperta (`c84c…b587`) riporta 1.118,94 USD di vita intera dal 23/09, **comprensivi
  dei giorni 01-03/10**: non ripartibile, non stimato.
- Confronto con le altre finestre: la puntata precedente dichiarava 715,36 USD «iniziate nel
  periodo, esclusa la sessione non scindibile»; qui la parte scindibile è **minore** e quella
  inscomponibile è la maggioranza del conto. È il prezzo di fare coordinare dodici giorni di due
  campagne a una sessione sola (v. §5.4).

---

## 3. Le sette raccomandazioni del 19/09

| # | Raccomandazione | Esito | La prova |
|---|---|---|---|
| 1 | Artifact visivo: pilota + contratto **estratto**, poi il ventaglio | **applicata (già misurata dal 26/09 §4)** | Il pilota del motore mappa nasce «usa-e-getta» il 22/09 e viene promosso a motore (`613958b` → rename in `importers/mappa_classificazione/*`); il Business plan si confronta con il PDF del committente arrivato il 23/09 15:28 e i Ruling «banco p7 di 13 pt» correggono **prima** del merge. Dove il contratto non c'era (i C01-C09 del triage) è il rapporto del 26/09 §3.1 che lo racconta. |
| 2 | Il default di ogni meccanismo di dispaccio verificato o esplicitato nel prompt | **applicata, con un'eccezione** | Ogni ondata snello nomina worktree, branch e base («worktree budget-snello-t2, branch snello/t2», «da 1982e04»); il Ruling del 26/09 separa i task paralleli in worktree propri **proprio perché** «lo stesso worktree con due agenti che fanno commit insieme rischia l'indice git» — è la risposta diretta a §5.5 della scorsa puntata, e nei registri letti non compare alcun caso di commit concorrenti. L'eccezione è il 29/09: il merge in main avviene **prima** della revisione finale del branch, dichiarata «non ancora fatta» nel registro stesso. |
| 3 | Un'affermazione senza misura non si scrive; uno sha solo se raggiungibile | **applicata** | Il giro «Costo: il proprietario segnala ~10 USD» viene riscritto misurando dai JSONL («403 chiamate vision, 1,24M token in»); il report di Task dice «compromesso accettato dal proprietario» e il controllore lo dichiara **falso** («il proprietario vuole import veloci») e lo lascia nel registro come difetto. I riallineamenti del 25 e 26/09 portano `sha_verificato` esplicito e «mai HEAD in corso d'opera» (25/09 §1). La regola del 19/09 — «un numero non contato non si scrive» — gira. |
| 4 | Il polling si sostituisce, non si scoraggia | **applicata (misurata)** | 20 min di `sleep` Claude (74 chiamate) + 15 min pi (10 chiamate, e 4 run sono la retrospettiva che aspetta i propri dati) = **35 min su dodici giorni**, contro i 61 dell'11→19/09. Nessuno sleep-loop nei registri: le attese passano dai `check`/`wait` di Orca e dal controllore che rilancia i banchi. |
| 5 | `Closes #NN` come campo del template, non come abitudine | **no — e il canale è morto** | **0 commit su 334** con `Closes #`; **0 issue create dal 16/09** (l'ultima è #60). Il tracciamento è emigrato **davvero** nei registri: le sezioni «Parcheggiati (Minor)» del ledger snello sono issue con tutto tranne che un numero. La meta-regola della raccomandazione 6 si conferma al rovescio: il campo nei registri c'è, il collegamento verso git no. |
| 6 | Le raccomandazioni diventano artefatti o muoiono | **applicata** | Il periodo ha partorito strumenti, non abitudini: `tools/triage_rilievi.py` con i verdetti, lo schema **contratto→banco→diagnosi** che apre ogni fase del snello (banchi passata1→4 sul corpus dei 50 file, con l'harness e la cache vision), il `--sha`/`--puntatori` di riallinea, e — nuovo — **il ruolo del controllore**: una seconda lettura che verifica il fix round sul diff, scritta nel registro come passo e non come speranza. È il meccanismo che la puntata precedente chiedeva come «campo o riga di registro»: qui è un attore del flusso. |
| 7 | Mai in tre su pi: lo si dichiari come limite di throughput | **caduta, per surclassa scritta** | Non c'è più un «figlio pi» da dispacciare: 10 run (di cui 4 = la retrospettiva del 26/09 che si autopsia, 3 = rialineamento/notturno, 3 = manutenzione e worktree della puntata precedente) e **zero** sul percorso snello, per decisione del proprietario **scritta nel ledger** il 26/09 («implementatori sonnet al posto di pi; revisori sonnet; revisione finale opus»). Il rapporto del 26/09 rimproverava al sorpasso di non avere «nessuna memoria che lo registri»: la decisione ora c'è, nel registro, riga 4. |

**Totale: 5 applicate (di cui una con eccezione), 1 no, 1 caduta.** Contro l'1/3/3 della
puntata precedente: il periodo in cui le
raccomandazioni sono diventate **ruoli e strumenti** (controllore, banco, contratto) è quello in cui
si applicano; le due che restano scoperte (collegamento issue↔commit, e il merge «prima» della
revisione finale) sono le due che non hanno ancora un artefatto che le ricordi alla macchina.

---

## 4. Che cosa ha funzionato

**4.1 Il banco sul corpus prima del modello: il percorso snello è la campagna meglio misurata del
progetto.** Quattro passate da 50 file (10.118s → 2.513s totali, mediana 91s → 27s) e ogni decisione
di codice nasce da una misura: la pre-classificazione deterministica dei conti **non si costruisce**
perché la misura dice «risparmio piccolo, e un conto classificato male in silenzio non passa più da
nessun controllo» (`misura-preclassificazione.md` + Ruling). È l'invariante di CLAUDE.md
(«diagnose, never fabricate») diventata criterio di dispaccio.

**4.2 Il controllore, cioè la ri-revisione come ruolo.** 36 agenti di ri-revisione (8, nella
puntata precedente) e un flusso scritto: consegna → review sonnet → Ruling → fix round →
«verificato dal controllore sul diff / sui numeri». Il caso di scuola è il Task 21: il controllore
scopre che l'ancoraggio introdotto dal Task non aveva **mai funzionato** sui file TM («a baa6b21
restituiva None/None: l'ok era assenza di controllo») — un verdetto positivo che era un buco, preso
da una lettura indipendente e non dal test dell'implementatore.

**4.3 Le decisioni escono come Ruling lo stesso giorno.** Nel solo ledger snello 58 righe
portano la parola (contate con grep, non sono le numerazioni dei registri precedenti: i 110 Ruling
numerati del rapporto del 26/09 stavano negli altri dieci registri), e quasi ogni Ruling ha il suo
«costo se sbagliato»; e
quando la revisione contesta un ruling, il ruling **cambia** («il mio ruling F4 "voto a conteggio"
era sbagliato; sostituito da… — costo se sbagliato: riserve stampate in avere restano negative»).
Nessun A05-bis: quando il proprietario decide, la riga finisce nel registro (es. il tappo a 10 € e
i riepiloghi rifiutati, scritti come Task 27 la mattina stessa).

**4.4 Il modello si sceglie per compito, e la scelta è nel registro.** sonnet implementa e revisiona,
opus chiude le revisioni finali (11 agenti), Qwen gx10 legge i documenti e basta — con una
clausola nuova, di onestà operativa: «si parallelizza con agenti sonnet **perché non occupano il
contesto di gx10, che serve libero al banco**» (Ruling 26/09). Il limite di concorrenza (4→6
richieste gx10) torna una decisione del proprietario verbalizzata, non una scoperta.

**4.5 La povertà di pi come esecutore non è stata una perdita.** Le 10 run del periodo hanno
prodotto 31 commit quasi tutti il 19/09 (rialineamento) e 0 abort; il lavoro pesante è passato su
sonnet con cache-lettura da 5,1 miliardi — il canale a cache dove il conto lo paga il riuso del
contesto, l'opposto del canale pi, che nel periodo ha letto 204,8M di token per produrne 1,09
(188:1, §2.2: ogni turno ri-paga il contesto intero).

---

## 5. Che cosa non ha funzionato

### 5.1 Due terzi dei commit del 26→30 sono `fix:`

**Che cosa è successo.** 95 fix su 145 commit nella seconda metà, contro 55 su 189 nella prima.
**Quanto è costato.** In righe, poco: la prima metà aggiunge 45.804 righe e ne toglie 3.987, la
seconda 22.466 e 2.904 — metà della costruzione, un terzo delle rimozioni, ma il 66% dei commit:
il costo non è in righe, è in **giri** (44 marker nel solo snello, §2.3).
**La causa.** Non è la stessa del 26/09 §3.1 (l'osservatore esterno), è gemella: qui l'osservatore
nuovo era **il corpus** (i 50 file del banco) puntato contro un codice — il parser snello — che
ereditava regole da tre anni di importatori. Vale la diagnosi già fatta dal rapporto del 26/09
(«si ripara in proporzione molto più di quanto si butti»); la novità del periodo è che la riparazione
è stata **preceduta** dalla misura (banco prima, fix dopo), e i due giorni di `fix:` sono l'ultima
rata, non una scoperta tardiva.

### 5.2 Il merge del 29/09 davanti alla revisione finale

Il registro lo dice con le sue parole: «Proprietario 2026-09-29: merge in main… **Revisione finale
opus del branch non ancora fatta.**» È l'unica violazione di flusso del periodo, e regge il
rovesciamento della regola del 26/09 («merge quando la revisione finale dice sì»): la causa non è
l'impazienza, è che la revisione finale di un branch da 23 task **non è un evento pianificato nel
piano** — i tre lotti del 26/09 l'avevano, il snello l'ha rincorsa task per task (43 review) e
nessuno l'ha chiusa come rito. Costo: lo dichiarerà il registro nei giorni successivi (fuori
finestra: Task 24-28, dove un **Critical del fix 3 del Task 26** — la situazione contabile che
adotta 238/338 con voci sbagliate — emerge solo in revisione, a branch già in marcia, e viene
revertito).

### 5.3 L'infrastruttura di misura vive fuori dal repo, e viene cancellata due volte

Il 30/09 e di nuovo il 2/10 il ledger annota: «Scratchpad cancellato: **persi harness, JSONL di
passata1-4, cache vision**». L'harness del banco viene ricostruito a mano (banco.sh + banco.py +
elenco.txt), la cache vision ripagata rilanciando 76-106 chiamate. Il costo è **inferito**: mezza
giornata di riavvio del banco a ricostruzione; ed è misurato l'effetto, che le passate 1-4 restano
verificabili solo **per cifra nel registro** — l'esatto contrario di ciò che la raccomandazione 6 del
19/09 predica. Che un tool di produzione-dipendente (il banco) non stia in git è un difetto con
nome: i `scripts/` ci stanno, il banco no.

### 5.4 Due campagne in una sessione sola, per dieci giorni e mezzo

`c84c…b587`: iniziata il 23/09, **46 riprese, 8 compattazioni, 145h di estensione**, ancora aperta
il 3/10. È il coordinatore del report, del triage e del percorso snello insieme; il suo `cost-state`
non è scindibile e la sua memoria di contesto è, per costruzione, l'ultima versione letta. Nessun
incidente attribuibile alla compattazione è nei registri, ma il pattern è quello che la prima
retrospettiva chiamava «il piano si perde dopo la compattazione»: la mitigazione di fatto sono i
ledger (307 righe di registro coprono ciò che la sessione non ricorda), non un meccanismo.

### 5.5 Il blocco di credito come singolo punto di fallimento

Il 26/09 il registro si ferma con «**BLOCCO: credito Anthropic esaurito durante la diagnosi**. Il
banco successivo non può girare finché non si ricarica». Due giorni dopo, la sessione ancora aperta
sulla stessa fattura è la prova che la campagna è partita con il contatore che fa da gate. Costo
reale: un'attesa nel giorno più denso del mese. Rimedio a forma di artefatto (sempre ric. 6): una
soglia di credito residuo dichiarata prima di lanciare un banco, o la cache vision già dentro
l'harness — che però esiste **solo** nell'harness ricostruito, cioè fuori dal repo: §5.3.

---

## 6. Raccomandazioni

Ognuna con la metrica con cui la prossima puntata la controllerà.

1. **La revisione finale di un branch multi-task è un passo del piano, con il proprio task.** §5.2.
   Impatto se salta: un merge che impegna main davanti all'ultimo sguardo (29/09). → *Metrica: ogni
   branch con ≥10 task mergiato con una riga «Final review: …» nel registro **prima** del merge
   commit; a settembre: 22/23 task del snello revisionati, il branch no.*
2. **Il banco va in git come i `scripts/`: harness, elenco file, cache opzionale, output in
   `.superpowers/`.** §5.3. Impatto: due ricostruzioni a memoria in cinque giorni, e quattro passate
   di 50 file verificabili solo «per cifra nel registro». → *Metrica: `git log` su
   `tools/banco/` (o `scripts/banco*`) al prossimo mese: ≥1 commit; JSONL di passata nel registro
   stesso, non nello scratchpad.*
3. **Il collegamento tracciamento↔commit si decide, una volta per tutte.** §3.5. Le issue sono
   morte il 16/09 senza verdetto e i `Parcheggiati` le sostituiscono senza numeri. → *Metrica: o il
   canale torna (≥10 issue create a ottobre, con `Closes #NN` ≥30% dei fix commit), o CLAUDE.md
   dice in una riga che il tracciamento è il registro; la prossima retrospettiva grep-pa la riga
   scelta e non entrambe.*
4. **Una sessione coordinatrice non passa le 100 ore di vita; il registro è il suo stato.** §5.4.
   Impatto: il costo non scindibile di §2.4 e un contesto che è ciò che l'ultima compattazione
   ha lasciato. → *Metrica: alla prossima misura, nessuna sessione con `estensione_s > 100h` che
   copra più di una campagna; e ogni `progress.md` con una riga di stato in testa (la vecchia ric.
   4 del 19/09, mai nata, ri-askata qui come conseguenza della 6).*
5. **Il gate di credito prima dei banchi: una riga di preflight, non un incident report.** §5.5.
   → *Metrica: registri di ottobre: 0 «BLOCCO: credito»; se uno compare, la riga di preflight
   esiste già in `regole-comuni.md` del banco (v. ric. 2).*
6. **I `Parcheggiati` dei registri si riversano da qualche parte con un numero.** §5.1: una quota
   dei fix nasce da difetti già nominati e parcheggiati (es. il Task 25 parcheggia «dettagli dalla
   nota integrativa non letti: prossimo task», e il task arriva). Oggi la catena la tiene a mente
   chi coordina. → *Metrica: alla prossima misura, ogni «Parcheggiato» che diventa lavoro ha un
   rimando incrociato nel registro che lo raccoglie; 0 parcheggiati che riappaiono come fix senza
   che nessuno li avesse nominati prima.*

---

## Appendice A — come rimisurare

```bash
python3 scripts/analisi_sessioni.py --da 2026-09-19 --a 2026-10-01 \
    --out .superpowers/retrospettiva/2026-10-03-periodo
# 4 sessioni Claude (1 ancora aperta alla misura), 242 trascrizioni di subagente,
# 10 run pi, 126.588 righe lette, 1 scartata.

B=/home/peter/DEV/budget
# commit del periodo (traversata aperta dal 18/09, filtrata per data autore):
git -C $B log --all --no-merges --since=2026-09-18 --date=iso-strict --pretty='%ad' \
  | awk '$1>="2026-09-19" && $1<"2026-10-01"' | wc -l                       # 334
git -C $B log --all --no-merges --since=2026-09-18 --date=iso-strict --format='%ad%x09%s' \
  | awk -F'\t' '$1>="2026-09-19" && $1<"2026-10-01"{print $2}' | grep -cE '^fix'   # 150
git -C $B log --all --no-merges --since=2026-09-19 --until=2026-10-01 --format='%b' \
  | grep -c 'Closes #'                                                      # 0

# registri SDD del periodo (i marker non sono giri; i giri distinti:
#   grep -oE 'Task [0-9]+[a-z]?: fix( round| wave) [0-9]+' progress.md | sort -u | wc -l)
grep -c 'fix round\|fix wave' $B/.superpowers/sdd/2026-09-26-import-pdf-snello/progress.md   # 44
grep -c Ruling                $B/.superpowers/sdd/2026-09-26-import-pdf-snello/progress.md   # 58
for f in $B/.superpowers/archivio-worktree/*/sdd/2026-09-2*/progress.md \
         /home/peter/DEV/budget-intermedio/.superpowers/sdd/*/progress.md; do
  [ -f "$f" ] && echo "$(grep -c 'fix round\|fix wave' $f) $(grep -c Ruling $f) $f"; done

# il canale issue: vuota dal 16/09
gh issue list --repo XrayFinanceDEV/xbrlbudget --state all --search "created:>2026-09-18"
```

Tre avvertenze, specifiche di questa finestra:

- **Il `cost-state` si legge alla data della misura, non alla fine del periodo.** `c84c…b587` era
  aperta il 3/10: il suo USD include i giorni 1-3/10. Non ripartibile, non stimato: se ne dia la
  dichiarazione, non la cifra «del periodo».
- **Due letture della stessa finestra non coincidono.** Il rapporto del 26/09 leggeva 158 subagenti
  e 443,64 USD su 19→27; la stessa finestra letta il 3/10 dà 242 trascrizioni e un conto molto più
  grosso, perché le sessioni sono continuate. Le cifre del 26/09 restano valide **alla sua ora**;
  chi confronta due puntate confronti i timestamp di misura, non le finestre.
- **Le run pi contano per ciò che sono.** 4 delle 10 del periodo sono la retrospettiva del 26/09
  che si autopsiava, 1 il worktree della retro del 19, 5 fra rialineamento, notturno e manutenzione:
  il lavoro pi *di prodotto* del periodo sono i commit del 19/09.

## Appendice B — le sessioni del periodo

Claude (tutte iniziate nella finestra; attive ed USD dal `cost-state` letto il 03/10):

| sessione | quando | attive | estensione | USD | agenti | riprese | compatt. | commit | merge | cosa era |
|---|---|---|---|---|---|---|---|---|---|---|
| `4db3…4d3d` | 19→23/09 | 22,4h | 104h | 334,83 | 80 | 11 | 6 | 12 | 15 | chiusura retro, report intermedio, gx10/qwen, pilota mappa |
| `b187…1d76` | 21/09 | 0,6h | 1h | 4,75 | 0 | 0 | 0 | 1 | 0 | parentesi |
| `c84c…b587` | 23/09 → **aperta al 3/10** | 37,6h | 145h | **1.118,94 (non ripartibile)** | 162 | 46 | 8 | 53 | 51 | coordinatore: BP/infrannuale/docx, triage AMBIENTA, tre lotti fix, percorso snello T1-T23 (+24-28 a ottobre) |
| `facb…af1b` | 23/09 | 0h | 7s | 0 | 0 | 0 | 0 | 0 | 0 | svegliata da orchestrazione |

pi (10 run; `aggregato.md` → «Sessioni pi»):

| famiglia | run | turni | attive | commit | falliti | note |
|---|---|---|---|---|---|---|
| rialineamento/notturno + manutenzione, `budget` | 6 | 1.006 | 8,0h | 30 | 46 | fra il 19 e il 26/09, albero principale |
| retrospettiva 26/09 (autopsia) | 4 | 712 | 4,4h | 1 | 42 | worktree `retrospettiva-2026-09-26` |
| worktree `retrospettiva-settembre` (retro 19/09) | 1 | 192 | 1,5h | 6 | 14 | la puntata precedente che si chiudeva |

> I 31 commit pi del periodo sono 30 + 1: quasi tutto il 19/09, e tutto senza costo API.

---

*Il resto delle cifre vive in `.superpowers/retrospettiva/2026-10-03-periodo/`
(aggregato.{json,md}, schede/). Fonti git: `/home/peter/DEV/budget` + worktree, tutti usati in sola
lettura. Per i numeri «dai diff» — churn, sopravvivenza, i 110 Ruling dei lotti AMBIENTA — il
riferimento è il [rapporto del 26/09](2026-09-26-rilavorazione-settembre.md), che non viene rifatto.*
