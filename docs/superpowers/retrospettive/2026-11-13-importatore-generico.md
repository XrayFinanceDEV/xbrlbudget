# Retrospettiva — 19 ottobre-13 novembre 2026: l'importatore universale dei bilanci di verifica

Quinta puntata, dopo la [retrospettiva di ottobre](2026-10-18-ottobre.md). La domanda del proprietario:
*«facciamo la retrospettiva per capire quanto stiamo avanzando nello sviluppo dell'importatore universale
dei bilanci di verifica»*. Quindi: di quanto è migliorato l'import sulle due forme che sono bilanci di
verifica (sezioni contrapposte ed elenchi di conti), che cosa resta e quanto è costato.

- **Periodo git:** dal `2026-10-19 00:00` al `2026-11-14` escluso, **tutti i ref**, traversata aperta dal
  16/10 e filtrata per data autore. **Misura del 13/11/2026 alle 17:49 (Europa/Roma), `main` = `352620f`.**
- **Punto di partenza della misura di progresso:** la baseline della Fase 0 del 28/10 (`046ab43`), che sta
  dentro il periodo.
- **Strumenti:** lo skill `/retrospettiva` (`.claude/skills/retrospettiva/`), rifatto il 13/11 sui metodi
  delle retrospettive precedenti: `misure.py` (churn, sopravvivenza, contatori), `serie_punteggio.py` (la
  serie dei giri di punteggio), il driver offline della copertura. Output grezzi in
  `budget-corpus/superpowers/retrospettiva/2026-11-13/`, fuori da git.
- **Fonti:** i giri di punteggio in `budget-corpus/corpus/_analisi-campione/punteggio/`, i registri SDD
  delle Fasi 1-4 (`budget-corpus/superpowers/sdd/2026-11-0*/progress.md`), i piani
  `docs/superpowers/plans/2026-11-0*` e `2026-11-11-*`, la pagina di revisione dell'importatore generico
  (artifact privato del proprietario, versione dell'11/11), `git ls-remote`, le sessioni di Claude Code.
- **Nessun documento è stato mandato a un servizio** per questa retrospettiva: ogni cifra viene da giri già
  fatti o dal driver offline con la rete bloccata.

**Come leggere i numeri.** Ogni cifra è **misurata** (git, uno script, un registro, un `punteggio.json`) o
**inferita** (l'interpretazione), e lo dice. Le percentuali di punteggio sono «esatte entro 1 €» sui campi
indicati, medie su tre esecuzioni per documento. **Si confrontano solo giri sullo stesso insieme di
documenti** (53, 78 o 86) e con le stesse verità: dove la serie salta, lo dichiaro.

---

## 0. Le tre risposte, in cima

**1) Stiamo avanzando? Sì, ma su una forma sola.** Il 28/10 l'import ha smesso di essere corretto un file
alla volta ed è stato misurato contro verità controllate. Da lì le **sezioni contrapposte** (24 documenti
del campione su 86) sono passate da 60,6% a 70,6% di macro-voci esatte, da 51,0% a 77,5% di KPI e da 40,7%
a 72,3% di altri dettagli. Gli **elenchi di conti** (9 documenti) sono andati da 50,6% a circa 59% di
macro-voci e da 46,9% a 54-59% di KPI: sono ancora la forma peggiore e non hanno mai avuto una fase
propria. Sul campione intero l'ago si muove poco: sugli stessi 78 documenti, dalla Fase 2 alla Fase 4, le
macro-voci vanno da 79,3% a 80,6%. Si muove di più il resto: sbilanciati da 14 a 5, esito giusto da 97,0%
a 99,6%, documenti adottati dal nuovo lettore da 0 a 25 (§2.3).

**2) I tre problemi tornati di più.** (a) **Una regressione entrata in main senza che nessuno la
nominasse**: 1405, letto dalle regole dal 19/10, non lo è più da `29eefdb` (Fase 4, 9/11). È la stessa forma
di 1337 a ottobre: il punteggio non poteva vederla perché 1405 non è nel campione (§2.4). (b) **Quattro
casi difficili attraverso tre fasi**: 161, 1426, 1445, 1533 sono sbilanciati alla fine della Fase 3, della 4
e della 5, e nessuno ha deciso che cosa farne (§3.2). (c) **Il metro che cambia durante la serie**: il
campione è cresciuto due volte (53 → 78 → 86) e le verità sono cambiate due volte (regole R3 dell'11/11;
1562 e 1565 diventati rifiuti attesi), quindi nessuna linea sola va dal 28/10 a oggi (§3.4).

**3) Che cosa cambierebbe il ritmo** (§6): misurare il **corpus**, non solo il campione, prima di ogni
merge dell'import; una **fase per gli elenchi di conti** con un obiettivo numerico; un **tetto** a
instabilità e tempo; una **decisione** sui quattro casi difficili.

---

## 1. La linea del tempo

| quando | che cosa | prove |
|---|---|---|
| 19/10 | Lettore del prospetto sintetico (1405), verifica «Mastri» a 3/5 cifre (1401), ammortamenti su `ce09a`/`ce09b`, rimanenze per natura, riallineamento della documentazione | `e94764c`, `ab3b405`, `6fa2330`, `25600ec` |
| 20/10 | Il personale lo ripartisce il modello sui conti, il codice decide; MinerU senza didascalia | `a6e14e2`, merge `814aecc` |
| 21-25/10 | **Zero commit** | `git log --all` |
| 26/10 | MinerU sull'API 4 di gx10; schemi di legge e contrapposte AGO scansionati letti dalle celle MinerU | `80ac6bf`, `d2f49c2`, `f777859` |
| 28/10 | Lotto week-43 (1410, 1432, 1450), poi la **Fase 0**: campione di 53 documenti con due letture cieche riconciliate, script di punteggio, baseline su `046ab43` | `9589449`, `1a55bd2`, `b315133` |
| 29/10-3/11 | **Zero commit.** Il 30/10 l'inventario della lettura per la Fase 1 (fuori da git) | `sdd/2026-10-30-importatore-generico-fase1/` |
| 4-5/11 | **Fase 1**, un solo lettore di righe (`importers/lettore/`), non collegato all'import | merge `e3455d6` (5/11 06:55) |
| 5-6/11 | **Fase 2**, il lettore nell'import come diagnosi, i blocchi che non chiudono nominati; campione a 78 | giro `fase2-93432bb` 11:08 → merge `c57e232` 11:56 |
| 6-9/11 | **Fase 3**, il lettore decide gli importi, Qwen nomina solo la classe | giro `fase3-4de18b6` 16:56 → merge `5817f8b` 18:25 |
| 9-10/11 | **Fase 4**, il percorso generico diventa quello normale, 12 parser di layout congelati, A.4 in `ce03a` ovunque (`ENGINE_VERSION` 5), ripiego classico misurato e tenuto | giro `fase4-ad2b581` (9/11 23:24) → merge `49b6080` (10/11 08:08) |
| 10/11 | Il repo passa al PC nuovo; `punteggio.py --corpus`, PyMuPDF fissato a 1.28.2, giro su tutti i 211 PDF × 3 | merge `616a0c0`, giro `corpus-a2c4394-pm1` |
| 11/11 | Campione a 86 (8 dal giro sul corpus) con le regole R3 del proprietario; esperimento `IMPORT_LETTORE_PRIMA`; **Fase 5** (contrapposte) e le due decisioni di accenderla per default; schema di legge coi conti all'unità; piano della Fase 6 | merge `2b8a418`, `63efdf1`, `45e7863` (16:20, dopo `fase5-regole-e4be5f1` 15:40), `94c2eb3` |
| 12/11 | Home: il 400 della creazione azienda dice il motivo | merge `352620f` |
| 13/11 | Nessun commit; questa retrospettiva | — |

Fra il 19 e il 28/10: 39 commit, 21 `fix`, quasi tutti col nome di un file. Fra il 4 e il 12/11: 182
commit, 85 `fix`. **Misurato** (Appendice A).

---

## 2. I numeri

### 2.1 Churn per area

`misure.py --da 2026-10-19 --a 2026-11-14`. Le righe sono già senza spazi (`-w`): in questo periodo i due
conteggi differiscono di poco (+40.722/−11.817 con gli spazi, +40.536/−11.631 senza), e **nessun commit**
ha il numstat cinque volte sopra il diff `-w`: il flip dei fine-riga di ottobre non si è ripetuto.

| area | +righe | −righe | commit |
|---|---|---|---|
| `tests/` (fuori da `tests/corpus/`) | 16.301 | 398 | 174 |
| `importers/lettore/` | **11.027** | 2.406 | **123** |
| `tests/corpus/` (punteggio, campione, manifesto) | 6.340 | 581 | 29 |
| `docs/` | 3.489 | 7.691 | 62 |
| `importers/` (il resto) | 2.641 | 315 | 41 |
| `frontend/` | 423 | 77 | 8 |
| `backend/app/` | 222 | 134 | 5 |
| `CLAUDE.md` | 43 | 9 | 10 |
| `calculations/` | 12 | 10 | 2 |
| **tutto il repo** | **40.536** | **11.631** | **221** |

Le colonne «commit» non sommano a 221, perché un commit tocca più aree. `importers/lettore/` **non esisteva
il 18/10** (`git ls-tree 83eeb06 importers/lettore` vuoto): un terzo delle righe di codice del periodo è un
pacchetto nuovo. Le 7.691 righe tolte da `docs/` sono quasi tutte le copie fotografate dell'handoff del 16/10
(`e193cd4`). **Sopravvivenza:** l'89,0% delle righe aggiunte è ancora vivo su `main` (`git blame -w`), e la
LIFO stima al 9,8% le righe morte entro 7 giorni (a ottobre 90,9% e 21%).

### 2.2 I file più riscritti

| file | commit | righe (+/−) | lettura |
|---|---|---|---|
| `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` | **39** | +711/−70 | ogni fase ha scritto qui la sua misura e le sue regole |
| `importers/lettore/classifica.py` | 26 | +641/−118 | la domanda a Qwen: macro, poi dettaglio, poi le regole del proprietario |
| `importers/lettore/totali.py` | 24 | +1.530/−197 | parziali → totali decisi dai totali stampati |
| `importers/lettore/foglie.py` | 24 | +1.283/−160 | le foglie che quadrano per lato |
| `importers/lettore/profilo.py` | 23 | +1.487/−258 | il profilo del documento prima delle righe |
| `importers/lettore/righe.py` | 22 | +1.248/−520 | righe e colonne: il rapporto righe tolte/aggiunte più alto del pacchetto |
| `importers/lettore/componi.py`, `percorso.py` | 17 + 17 | +473/−52, +356/−70 | il percorso del lettore dentro l'import |

Nei soggetti dei commit gli id di documento ricorrono poco (1432 e 1450 due volte, gli altri una): da
novembre i commit nominano la **regola**, non il file. **Misurato**; che questo sia un buon segno è
**inferito**.

### 2.3 Il progresso dell'import, contro le verità

`serie_punteggio.py` sui `punteggio.json`. Ogni riga è un giro di tre esecuzioni per documento sul percorso
di produzione (gx10 per il modello, MinerU per le scansioni).

**Campione intero**

| giro | insieme | esito | macro | KPI | dettagli | anno prec. | instabili | sbilanciati | adottati dal lettore |
|---|---|---|---|---|---|---|---|---|---|
| `baseline-046ab43-x3` (28/10) | 53 | 98,7% | 79,3% | 76,9% | 78,7% | 75,4% | 5 | — | — |
| `base-fase2-e3455d6` (5/11) | 78 | 97,0% | 79,3% | 77,8% | 76,8% | 74,8% | 14 | — | — |
| `fase2-93432bb` (6/11) | 78 | 96,6% | 78,7% | 77,4% | 76,9% | 72,4% | 15 | 14 | — |
| `fase3-4de18b6` (9/11) | 78 | 97,0% | 80,6% | 80,3% | 78,7% | 71,6% | 11 | 7 | 11 |
| `fase4-senza-classico-c337ed7` (misura, non rilascio) | 78 | 91,5% | 79,4% | 79,3% | 78,2% | 71,8% | 11 | 6 | 10 |
| `fase4-ad2b581` (9/11) | 78 | **99,6%** | **80,6%** | **80,3%** | **79,5%** | 72,7% | **9** | **5** | 14 |
| `fase4-ad2b581-R3` (stesso esito, verità R3) | 78 | 99,6% | 80,3% | 80,0% | 79,3% | 72,7% | 9 | 5 | 14 |
| `base5-86` (11/11, verità R3) | 86 | 97,3% | 79,2% | 79,1% | 78,7% | 70,5% | 12 | 10 | 14 |
| `fase5-ee2a506` (11/11) | 86 | 97,7% | **81,7%** | **83,2%** | **82,8%** | 70,5% | **23** | 11 | **25** |

**Le due forme dei bilanci di verifica** (macro / KPI / altri dettagli)

| giro | insieme | contrapposte | elenchi di conti |
|---|---|---|---|
| `baseline-046ab43-x3` | 53 | 60,6 / 51,0 / 40,7 | 50,6 / 46,9 / 47,4 |
| `base-fase2-e3455d6` | 78 | 60,6 / 51,6 / 45,9 | 55,0 / 57,8 / 45,0 |
| `fase3-4de18b6` | 78 | 65,6 / 61,1 / 49,6 | 56,8 / 60,7 / 55,7 |
| `fase4-ad2b581` | 78 | 65,5 / 61,9 / 49,9 | 56,8 / 62,2 / 56,8 |
| `base5-86` (verità R3) | 86 | 64,5 / 62,6 / 53,2 | 56,8 / 58,7 / 55,7 |
| `fase5-ee2a506` | 86 | **70,6 / 77,5 / 72,3** | 59,4 / **54,4** / 57,9 |
| `fase5-regole-e4be5f1` (regole riviste, i 39 toccati) | 39 | 71,6 / 76,6 / 72,2 | 59,1 / 58,7 / 57,6 |

Sugli 86 documenti del campione ci sono 24 contrapposte e 9 elenchi di conti (`tests/corpus/campione.json`).
Fra le contrapposte quasi tutto il guadagno arriva **in un passo solo**, la Fase 5, e viene dal lettore che
prova per primo: da `base5-86` a `fase5-soloprima-d33f5e5` (stessi documenti di contrapposte) +5,6 macro,
+11,3 KPI, +17,4 dettagli. Sugli elenchi di conti la prima versione delle regole nel prompt ha abbassato i
KPI da 58,7 a 54,4, e la versione rivista li ha riportati a 58,7. **Misurato.**

**Il giro sul corpus intero** (`corpus-a2c4394-pm1`, 10/11, 211 PDF distinti × 3, senza verità): 199
importati in ogni giro, nessun documento che cambia esito fra i giri, 10 rifiuti attesi, 2 rifiuti da
guardare (355 e 1444; poi entrati nel campione, 355 si importa, 1444 è un rifiuto atteso), 183 quadrati in
ogni giro, 16 sbilanciati in almeno un giro, 21 instabili, mediana 2,1 s. Salvati da: lettori a regole 158,
percorso del lettore 18, MinerU + lettore 3, Qwen 20; rifiutati 12. **Misurato.**

### 2.4 La copertura dei lettori a regole: la linea di ottobre, continuata

Stesso metodo del 18/10: worktree detached, chiavi tolte, `socket.connect` bloccato, un processo per PDF.
Il corpus è cresciuto: **211 PDF distinti** (esclusi `july_budget`, `_analysis` e `_analisi*`), contro i 176
del 18/10.

| punto | PDF letti a regole / 211 |
|---|---|
| `83eeb06` (18/10, il punto finale di ottobre: 144/176) | **146** |
| `352620f` (13/11) | **155**: 9 guadagnati, **0 persi** |

0 crash e 0 chiamate di rete a entrambi i punti. Oggi i lettori sono: reso XBRL 46, situazione contabile 43,
schema di legge generico 32, etichette 20, fonti di legge 6, IV-CEE standard 3, schema con dettaglio 2,
fonti AGO 2, codici 1. Su 31 documenti letti a entrambi i punti cambia qualche cifra: soprattutto ammortamenti
(`ce09a`/`ce09b`, 17 e 13 documenti) e variazioni delle rimanenze (`ce02`/`ce10`, 13 e 12), cioè le due
regole del 19/10 (**inferito** dal tipo di campo). 6 documenti muovono anche capitale e riserve, e non ne ho
cercato la causa.

**1327 è recuperato.** Il 18/10 nessun lettore lo leggeva; oggi il parser della situazione contabile lo legge
quadrato, offline e nel giro sul corpus. Nessun commit del periodo lo nomina (`git log --all | grep -c 1327` = 0):
lo ha recuperato una correzione generale.

**1405 è una regressione entrata in main.** Il driver lo dà «letto a regole» su `e94764c` (19/10), su
`046ab43` (28/10) e su ogni merge di `main` fino a `4f73905` (il piano della Fase 4); da `49b6080` in poi no.
Dentro la Fase 4 il primo commit che lo spegne è **`29eefdb`** («fix(schema_etichette): A.3 in ce03 e A.4 in
ce03a, dalla tavola unica»): il lettore del prospetto sintetico risponde `non_applicabile`. Il giro sul corpus
del 10/11 lo ha salvato sbilanciato attraverso Qwen in tutti e tre i giri e lo ha messo fra i «da guardare»;
il punteggio della Fase 4 era verde perché 1405 non sta nel campione. **Misurato** (Appendice A).

### 2.5 I contatori della rilavorazione

| cosa | 19/10-13/11 | ottobre (27/09-18/10) |
|---|---|---|
| commit non-merge (tutti i ref) | **221** | 248 |
| merge | 29 | 44 |
| commit `fix*` | **106 (48%)** | 147 (59%) |
| commit con parole di ritorno nel soggetto | 15 | 30 |
| **revert veri** | **3**, un solo esperimento | 2 |
| coppie di commit sullo stesso file entro 3 giorni (≥20 righe) | 225 | 229 |
| commit ≥50 righe la cui totalità è morta su main | 0 | 5 |
| commit del periodo non raggiungibili da main | **0** | 6 |
| commit con «decisione del proprietario» nel messaggio | 14 | 10 |
| flip dei fine-riga | 0 | 2 |

I tre revert sono la Task 4 della Fase 4: indizi a parole chiave dati al modello, misurati in calo su quattro
documenti due volte (macro + KPI da 117/115 a 109/109) e tolti **prima del merge**. Le 225 coppie entro tre
giorni sono quasi tutte dentro `importers/lettore/` e nei suoi test, nella forma «task → giro di correzione
della revisione». **Misurato** il conteggio, **inferita** la forma.

### 2.6 Le sessioni e il costo

`analisi_sessioni.py --da 2026-11-10 --a 2026-11-14 --projects ~/.claude/projects/-home-claw03-workspace-DEV-budget`:
4 sessioni, 15 subagenti con trascrizione (11 opus, 4 sonnet), **136,46 USD** di `cost-state`. La sessione
`bb1f7251` (10-12/11, 120,21 USD) ha portato il merge della Fase 4, il giro sul corpus, il campione a 86 e la
Fase 5. **Le sessioni dal 19/10 al 9/11, Fasi 0-3 comprese, sono sul PC precedente e da qui non si leggono:
non sono contate, e non valgono zero.**

### 2.7 Che cosa costa la rilavorazione, in una riga

**Inferita**, coi pezzi misurati: la rilavorazione vera del periodo è una task tolta prima del merge (tre
revert) e una regressione entrata in main (1405). Le 225 coppie entro tre giorni sono il ciclo
task-revisione-correzione dentro un pacchetto nuovo, non il ritorno su lavoro dichiarato chiuso. Il motore
non è stato riaperto (2 commit su `calculations/`, entrambi per A.4 in `ce03a`). Il resto è **progresso che
resta**: l'89% delle righe vive, un pacchetto nuovo in produzione, +27 punti di KPI sulle contrapposte.

---

## 3. Le cause, con esempi verificati

### 3.1 Il cambio di metodo del 28/10

Fino al 28/10 l'unica misura di «si avanza» era quanti PDF leggono i lettori a regole: una misura di
**adozione**, non di correttezza. La Fase 0 ha aggiunto la seconda: verità scritte con due letture cieche
riconciliate e 17 decisioni del proprietario, e un comando che dà un punteggio a ogni import. Da quel giorno
le Fasi 2-5 si chiudono su un giro di punteggio fatto fra 30 minuti e 9 ore prima del merge (§1), che è la
raccomandazione 2 di ottobre messa in pratica sul campione. La Fase 1 si chiude sulla propria misura delle
righe, perché non era ancora collegata all'import.

### 3.2 I casi che attraversano le fasi

161 (si contraddice da solo), 1426 (gerarchia senza totali stampati, due tabelle affiancate), 1445 (CE a
blocchi), 1533 (un'eco di 1,30 €: allargare la tolleranza sarebbe un plug) sono sbilanciati alla fine della
Fase 3, della 4 e della 5, e tutti e quattro compaiono fra i «da guardare» del giro sul corpus. Su 1562 e
1565 il proprietario ha deciso «rifiutati, e la verità si aspetta un rifiuto», e da allora non sono più
tornati. Su questi quattro una decisione non c'è. **Misurato.**

### 3.3 Le fasi chiuse sotto il proprio piano, ma dichiarate

Tre fasi su cinque si sono chiuse sotto il proprio criterio. La Fase 1 sul 76-82% di righe che chiudono,
contro il 90/95 del piano. La Fase 4 con 4 documenti ancora letti dal modello in modo `legge`, dove il piano
ne voleva 3. Nella Fase 5 la strada «il parser legge, il modello classifica» si è fermata dopo la
ricognizione, perché avrebbe voluto dire un tredicesimo parser. Ogni mancanza è scritta nel registro o nella
pagina di revisione: non è nascosta. **Misurato.**

### 3.4 Il metro che cambia

Il campione è passato da 53 a 78 documenti il 5/11 e a 86 l'11/11. Le verità sono cambiate con le 21
decisioni R3 dell'11/11: lo stesso esito della Fase 4, ripunteggiato, scende da 80,6% a 80,3% di macro-voci
e da 62,2% a 58,7% di KPI sugli elenchi di conti. I giri `-R3` lo rendono visibile, ed è per questo che
`serie_punteggio.py` raggruppa i giri per insieme di documenti.

**Una tabella non riproducibile.** La pagina di revisione dà, per i 39 documenti della Fase 5, 66,3% →
69,3% → 70,0% → 70,7% di macro-voci; `punteggio.json` di `fase5-soloprima-d33f5e5` e di
`fase5-regole-e4be5f1` dice 71,9% e 73,5%. Le differenze fra un giro e l'altro coincidono, i livelli no, e la
Fase 5 non ha un registro da cui ricostruire il calcolo. **Misurato** lo scarto; la causa non è nota.

### 3.5 Il prezzo della Fase 5

Sugli 86 documenti gli instabili, cioè quelli le cui cifre cambiano fra le tre esecuzioni, passano da 12 a
23 con la Fase 5; sui 78 erano scesi da 15 a 9 durante le Fasi 2-4. Dove il lettore prova prima del parser
un import dura circa 70 s invece di circa 1 s, perché il lettore chiede a Qwen di classificare le foglie. Le
due manopole (`IMPORT_LETTORE_PRIMA`, `IMPORT_REGOLE_NEL_PROMPT`) sono accese per decisione del proprietario
dell'11/11: è uno scambio misurato, non un incidente, ma nessuno gli ha messo un tetto.

### 3.6 Le regole del proprietario arrivate dopo il codice

Due. Il debito senza scadenza stampata va a breve, mutui compresi (9/11): toglie ovunque la vecchia regola
gestionale «finanziamenti a lungo». Le regole R3 (11/11) riscrivono le verità. Le scelte grandi sono state
invece misurate prima e decise dopo: il ripiego classico è stato spento per misura e poi tenuto, il lettore
che prova per primo è stato provato su un branch d'esperimento prima di diventare default, A.4 in `ce03a` è
stata decisa prima di toccare tutti gli importatori. Su `ce03` la metrica di ottobre è al limite: azzerata
negli anni di piano il 9/10, separata in A.3/A.4 il 9/11.

---

## 4. Le sette raccomandazioni del 18/10: applicate? (con la prova)

| # | Raccomandazione | Esito | Prova |
|---|---|---|---|
| 1 | Banco di accettazione del motore sui tre scenari reali | **no** (non messa alla prova) | Non costruito. Nel periodo nessun foglio del consulente e solo 2 commit su `calculations/`, entrambi per A.4. |
| 2 | Il confronto sul corpus come cancello pre-merge dell'import | **a metà** | Ogni fase dalla 2 alla 5 si unisce dopo un punteggio su tre giri; la Fase 5 aggiunge `tests/corpus/foglie_campione.py`. 1327 ha il suo verdetto (recuperato). Ma il cancello copre gli 86 del campione, non il corpus: 1405 è passato. Metrica «regressioni entrate in main su file già letti»: ottobre 2, novembre **1**. |
| 3 | «In attesa del proprietario» prima della regola | **a metà** | Scelte grandi misurate prima, decise dopo (§3.6); 14 commit citano la decisione con la data. Due regole arrivate dopo il codice. |
| 4 | `.gitattributes` con `* text=auto` | **a metà** | Il file ha ancora una riga sola (la licenza Typst). La metrica è rispettata lo stesso: 0 flip. |
| 5 | Il registro SDD torna, o si dichiara chiuso | **sì** | `progress.md` per le Fasi 1-4 (170, 71, 124, 74 righe; 82 Ruling; 38 righe con decisioni del proprietario). La Fase 5 (25 commit in un giorno) non ne ha. |
| 6 | Decidere dove vive la suite di test dell'import | **no** | `tests/conftest.py` imposta ancora `IMPORT_MOTORE=classico` e `ANTHROPIC_CONSENTITO=1`; la produzione non usa nessuno dei due. |
| 7 | Chiudere i rami fantasma | **sì** | `git ls-remote origin`: solo `main`, nessun tag. Ogni branch locale è unito, 0 commit in volo. La «tag di archivio» del ramo della mappa citata a ottobre non è su `origin`. |

**Totale: 2 sì, 3 a metà, 2 no.** A ottobre le raccomandazioni tenevano quando diventavano meccanica git. A
novembre tengono anche due cambi di processo (il registro, il punteggio prima del merge), perché sono
diventati uno strumento (`punteggio.py`) e un file per fase.

---

## 5. Ha funzionato / non ha funzionato

### 5.1 Ha funzionato

- **Le verità come metro.** Tutte le cifre di §2.3 si rimisurano con un comando, e un salto di metro si vede
  (`-R3`). È la prima volta che il progetto risponde «di quanto è migliorato?» e non solo «quanti file legge?».
- **Le fasi corte con il giro prima del merge.** Cinque fasi in otto giorni lavorativi, ognuna con piano,
  registro (tranne la 5) e una riga sulla pagina di revisione.
- **L'esperimento tolto in tempo.** La Task 4 della Fase 4 è stata misurata, ha peggiorato, è stata tolta
  prima del merge, e la lezione è diventata una regola del proprietario nella Fase 5.
- **I lettori a regole non arretrano offline**: 146 → 155 su 211, 0 persi, 0 chiamate di rete.

### 5.2 Non ha funzionato

- **Il cancello guarda il campione, non il corpus**, e 1405 è passato (§2.4).
- **Gli elenchi di conti sono rimasti indietro**: 9 documenti, circa 59% di macro-voci, nessuna fase propria.
  La Fase 6 pianificata riguarda la struttura dal modello, non loro.
- **La Fase 5 non ha registro**, ed è l'unica i cui numeri sulla pagina di revisione non si ricostruiscono.
- **Instabilità e tempo raddoppiati** senza un tetto (§3.5).

---

## 6. Raccomandazioni (misurabili: la prossima retrospettiva le conta così)

1. **Misurare il corpus, non solo il campione, prima di ogni merge dell'import.** Il driver offline
   (`.claude/skills/retrospettiva/strumenti/copertura/`) gira in pochi minuti senza far uscire documenti: va
   confrontato file per file con il giro precedente. → *Metrica: file che smettono di essere letti a regole
   senza un commit che li nomini; novembre 1 (1405), obiettivo 0. E 1405 corretto o dichiarato.*
2. **Una fase per gli elenchi di conti.** → *Metrica: macro-voci sugli elenchi di conti ≥ 70% alla prossima
   retrospettiva, o una decisione scritta che restano sul parser di prima.*
3. **Un tetto a instabilità e tempo.** → *Metrica: instabili sugli 86 ≤ 12 (la base della Fase 5), o ognuno
   in più nominato con la sua causa; secondi mediani per import stampati in ogni rapporto di punteggio
   accanto ai punteggi.*
4. **Un verdetto sui quattro casi difficili** (161, 1426, 1445, 1533): corretti, o dichiarati nella verità
   come «importato con avviso», come 1562/1565 sono stati dichiarati rifiuti. → *Metrica: nessun caso aperto
   per più di due fasi.*
5. **Un registro per ogni fase, anche di un giorno, e ogni riga della pagina di revisione dichiara giro e
   versione delle verità.** → *Metrica: un `progress.md` per ogni fase unita; nessuna cifra della pagina
   senza il giro da cui viene.*
6. **Portate avanti da ottobre:** il regime della suite di test e `.gitattributes`. → *Metrica come a
   ottobre.*

---

## Appendice A: come rimisurare

```bash
R=/home/claw03/workspace/DEV/budget
C=/home/claw03/workspace/DEV/budget-corpus
S=$R/.claude/skills/retrospettiva/strumenti
O=$C/superpowers/retrospettiva/2026-11-13
P=$C/corpus/_analisi-campione/punteggio

# --- churn, sopravvivenza, contatori (traversata aperta dal 16/10, filtro per data autore) ---
python3 $S/misure.py --da 2026-10-19 --a 2026-11-14 --out $O     # ~1 min col blame
# 221 commit, 29 merge, +40536/-11631 (-w), fix 106, revert 3, vive 89.0%, morte 7g 9.8%,
# coppie 3gg 225, in volo 0, flip 0, decisione del proprietario 14; importers/lettore/ 123 commit

# --- sotto-periodi ---
git -C $R log --all --no-merges --since=2026-10-16 --format='%ad|%s' --date=short \
  | awk -F'|' '$1>="2026-10-19" && $1<="2026-10-28"' | wc -l             # 39 (21 fix)
git -C $R log --all --no-merges --since=2026-10-16 --format='%ad|%s' --date=short \
  | awk -F'|' '$1>="2026-11-04"' | wc -l                                   # 182 (85 fix)

# --- serie dei punteggi ---
python3 $S/serie_punteggio.py $P --forme conti/colonne,contrapposte --json $O/serie.json
# tabelle di §2.3; per forma i valori sono in sintesi.per_tipologia di ogni punteggio.json

# --- copertura offline (rete bloccata, worktree fuori dal repo) ---
git -C $R worktree add --detach $O/wt/83eeb06 83eeb06
RETRO_ROOT=$O/wt/83eeb06 RETRO_TEST=$C/corpus python3 $S/copertura/driver.py $O/copertura/p_83eeb06.jsonl  # 146/211
RETRO_ROOT=$R            RETRO_TEST=$C/corpus python3 $S/copertura/driver.py $O/copertura/p_oggi.jsonl     # 155/211
# persi 0, guadagnati 9, 31 documenti con cifre diverse

# --- 1405: su quale commit si spegne ---
f=$(find -L $C/corpus -name 'budget_1405*' -not -path '*july_budget*' | head -1)
for sha in $(git -C $R rev-list --first-parent --reverse 046ab43..49b6080) \
           $(git -C $R rev-list --reverse --no-merges 4f73905..49b6080 -- importers/); do
  git -C $R worktree add --detach -q $O/wt/$sha $sha
  RETRO_ROOT=$O/wt/$sha $R/backend/venv/bin/python -I $S/copertura/worker.py "$f" | grep '^@@JSON@@'
done                         # adottato fino a c6d2441, non_applicabile da 29eefdb in poi
git -C $R worktree prune     # dopo aver tolto i worktree

# --- casi e rami ---
git -C $R log --all --since=2026-10-18 --oneline | grep -c 1327         # 0
git -C $R ls-remote --heads --tags origin                                # solo refs/heads/main
git -C $R ls-tree 83eeb06 importers/lettore | wc -l                     # 0
grep -n 'IMPORT_MOTORE\|ANTHROPIC_CONSENTITO' $R/tests/conftest.py       # classico, 1
for f in $C/superpowers/sdd/2026-11-0*/progress.md; do wc -l < $f; grep -ci ruling $f; done  # 170/28 71/18 124/25 74/11

# --- sessioni ---
python3 $R/scripts/analisi_sessioni.py --da 2026-11-10 --a 2026-11-14 \
  --projects ~/.claude/projects/-home-claw03-workspace-DEV-budget --no-pi --out $O/sessioni
# 4 sessioni, 15 subagenti, 136,46 USD; prima del 10/11 sul PC precedente
```

Avvertenze per chi rimisura:

- **I denominatori cambiano.** Il campione è di 53, 78 e 86 documenti a seconda del giro; il corpus è di 211
  PDF distinti oggi, contro 176 il 18/10. Confronta solo dentro lo stesso insieme.
- **La colonna `commit` di `serie_punteggio.py` è il commit dello strumento quando il giro è stato
  punteggiato**, non sempre il codice misurato: i giri `-R3` portano `dc3950f` anche quando l'esito è della
  Fase 4.
- **Il driver offline misura i soli lettori a regole**: il percorso del lettore chiede a Qwen la classe di
  ogni foglia, quindi a rete bloccata non adotta. È la misura di ottobre, non quella di produzione.
- **Le sessioni prima del 10/11** sono sul PC precedente (`/home/peter`): per contarle serve leggerle lì.

## Appendice B: le sessioni leggibili del periodo

| sessione | inizio | attive | USD (`cost-state`) | agenti | commit | merge | che cosa |
|---|---|---|---|---|---|---|---|
| `bb1f7251` | 10/11 10:19 | 8h53m | 120,21 | 15 | 23 | 7 | merge della Fase 4, giro sul corpus, campione a 86, Fase 5 |
| `86c5a117` | 12/11 10:16 | 2h31m | 16,25 | 0 | 0 | 0 | creazione azienda, il 400 che dice il motivo |
| `da1c901a` | 13/11 11:24 | in corso | — | 0 | 0 | 0 | questa retrospettiva, lo skill rifatto |
| `04b97dae` | 13/11 09:21 | 0 | 0 | 0 | 0 | 0 | sessione vuota |

I commit delle Fasi 0-3 (28/10-9/11) vengono da sessioni del PC precedente: qui non compaiono.
