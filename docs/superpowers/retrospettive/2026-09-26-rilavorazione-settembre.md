# Retrospettiva — settembre 2026: quanta parte del lavoro rifacciamo

Terza puntata, dopo le [sessioni del 24/08-11/09](2026-09-10-sessioni-agosto-settembre.md) e le
[sessioni dell'11-19/09](2026-09-19-sessioni-settembre.md). Le prime due misurano le sessioni;
questa aggiunge la misura che mancava — **la rilavorazione nel codice**, letta dai diff git su
tutti i ref — e rifà l'analisi delle sessioni sulla parte nuova, `2026-09-19 → 2026-09-27`.
La domanda di partenza, posta dal proprietario: *quanto siamo efficienti su un progetto che
continuiamo a rifare e riaggiornare?*

- Periodo git: `2026-09-01 00:00 → 2026-09-27 00:00` (Europa/Rome), **tutti i ref** (`git log --all`),
  repo `/home/peter/DEV/budget` + i worktree collegati (`git worktree list`: 15 worktree alla misura).
- Periodo sessioni: `2026-09-19 → 2026-09-27` (la parte nuova rispetto al rapporto del 19).
- Strumenti: `scripts/analisi_sessioni.py` (invariato dall'ultima puntata; le sessioni pi le legge
  di default, `--no-pi` per escluderle), più tre script di misura
  scritti per questa analisi (`churn.py`, `survival.py`, `churn730.py`, output in
  `.superpowers/retrospettiva/2026-09-26/` — comandi in Appendice A).
- Fonti aggiuntive: i 17 registri SDD di settembre (nei worktree oltre che nell'albero principale),
  `inbox/` (i fogli e i PDF del consulente), `docs/superpowers/allineamento/` (i giri 19, 25, 26/09).

**Come leggere i numeri.** Gli id di sessione sono spezzati (`4db3…4d3d`: prime e ultime quattro
cifre del primo gruppo). Ogni cifra è **misurata** (conteggio da git, dallo script, da un registro)
o **inferita** (l'interpretazione che ne traiamo), e le due cose sono sempre distinte. Il
`cost-state` Claude è cumulativo sulla vita della sessione; qui tutte e quattro le sessioni del
periodo sono iniziate **dentro** la finestra, quindi il totale è pulito — con un'eccezione
dichiarata in §2.5. La sopravvivenza del codice è misurata con `git blame` **a cavallo di tutti i
ref attivi** (max per file), non solo `main`: quello che sta su un branch non mergiato è vivo sul
branch, e dirlo morto sarebbe sbagliato.

**L'ora della misura.** Ogni numero git di questo rapporto è contato il **26/09 alle 14:30**, e le
righe che dicono «alla misura» dicono esattamente questo. Dopo quell'ora `main` ha ricevuto i tre
lotti dei fix AMBIENTA (merge `78e8278` e `4167b65`, poi `bbf5a6f` sui test), e i contatori che
dipendono dai ref raggiungibili si sono mossi di poche unità: chi rimisura la sera trova gli in volo
a 72 invece di 131, e due ref (`fix/rilievi-ambienta`, `fix/rilievi-l2`) non esistono più. Dove una
verifica successiva dà un numero diverso per questo motivo, il rapporto **non** si aggiorna: la
finestra è quella delle 14:30.

---

## 1. La linea del tempo di settembre

| quando | che cosa (fatto / rifatto / buttato) | prove |
|---|---|---|
| 01-02/09 | Ciclo a issue: 54 commit, ~46 issue; il motore di proiezione TypeScript duplicato viene **ucciso** (`00513d7` «un motore solo, e sta in Python») | `git log --all`, §3.6 |
| 08-11/09 | Lotti SDD 1, 2, 3A, 3B: 259 commit (tutti i ref, merge comprese), e l'08/09 `3eac1e3` ritira la generalizzazione della «cella vuota» che non passa la prova sul corpus: è il primo dei **due revert veri del mese** (§2.3). Il motore del previsionale è riscritto a più riprese (`forecast_engine.py`: **76 commit a settembre**, +5.156/−1.430) | churn misurato, §2.2 |
| 11-12/09 | Collaudo 3A → quattro indagini → ondata finale: i difetti escono dal browser, non dalle revisioni. 3 task su 8 al giro 2 | `sdd/2026-09-11-indagine-difetti-collaudo-3a/`, `2026-09-12-ondata-finale-correzioni/` |
| 13-18/09 | Filone report: il **piano più riscritto del mese** (`2026-09-13-report-finale-e-pdf-typst.md`: 10 commit, 6 task aggiunti in corsa), il fermo del 17/09, il contratto estratto dalla v4 | `git log --follow`, retro 19/09 §5.1-5.2 |
| **19/09** | Chiudono le due retrospettive (`4b5f80a`, merge `c8585f4`-series); un pi nell'albero principale dichiara quattro errori di racconto (§5.3 della retro del 19); riallinea Notturno si difende da sé (`a5d9876`) | `git log`, retro 19/09 |
| 20/09 | **Zero commit.** Il tester lavora: `inbox/riptova/` aggiornato lo stesso giorno | `git log --all`, date su disco |
| 21/09 | Il report intermedio Typst dell'infrannuale entra in main (`cea80ec`), con gli indicatori di crisi calcolati dal server (`e401987`); l'import analitico IV-CEE (`ccab5f8`) | merge, `9de3e22` |
| 22/09 | Nasce il **motore mappa** (mappa vision + classificazione locale): spec e piano in un giorno (`2960da5`…`f4d3483`), pilota «usa-e-getta» (`613958b`) poi promosso a motore e riassorbito in `importers/`, ~34 commit di fix (fitti quelli sul lettore geometrico senza oracolo — due proprio «fix(import): il lettore…») in due giorni. **Il branch non è in main alla misura: 70 commit in attesa** | `f4d3483`…`6d611d8`, `git log feat/import-mappa-classificazione --not main` |
| 23/09 | Tre giorni di PDF in un giorno: **Business plan ReportLab** (merge `2a6ce25`), route A/B e C su **Qwen** (`4726093`, memory `banchi-solo-qwen`: «non facciamo altri test con haiku»), il reference del committente arriva in `inbox/` alle 15:28 e alle 21:02. 69 commit | merge list, `inbox/` date su disco |
| 24/09 | Report infrannuale (`2e8e992`), **Word** (`8c57b3d`), e il **dossier Typst staccato dall'interfaccia** (`6d2c447`: «REPORT_MODELS ha il solo Business plan») — 8.529 righe di renderer Typst scritte dal 13/09 restano nel codice ma non producono più nulla. Fix dei piani multipli cancellati (`fc4e8c2`) | merge, `git log --since=2026-09-13 -- backend/app/renderers/typst` |
| 25/09 | Arriva il foglio del consulente (`inbox/Verifica_piano_Ambienta_problemi.xlsx`, 14:49) → **banco di triage**: 21 rilievi, verdetto con xfail strict su base AMBIENTA reale; la revisione finale scopre che il tool **invertiva i verdetti** con gli xfail e che un test A01 era un falso positivo | `ffdb32d`…`8eaffab`, `sdd/2026-09-25-triage-rilievi-ambienta/final-findings.md` |
| 26/09 | **Tre lotti di fix in un giorno** (motore, report, wizard): ~61 commit dal 25/09 sera (52 datati 26/09 entro la misura), quasi tutti ancora su branch non mergiati alla misura, 4 piani/spec scritti la mattina stessa, revisioni finali opus | `80048d3`…`c46a051`, §2.3, §3.1 |
| 26/09 | Il riallineamento del 25/09 dichiara che **7 dei 9 rilievi documentali non erano raggiungibili dalle citazioni** — «terza volta di fila»; quello del 26/09 verifica che 8 delle 9 correzioni della vigilia sono vere | `allineamento/2026-09-25.md`, `2026-09-26.md` |

Il mese in una riga: si costruisce tanto (215.434 righe aggiunte), si butta poco **(9 righe su 10
dell'aggiunto vive ancora**, §2.1), e si **ripara in proporzione molto più di quanto si butti**:
un commit su tre è `fix:`, e la metà dei giri di correzione nasce tardi, fuori dal ciclo di
sviluppo — da un browser, da un PDF stampato, da un foglio di un consulente.

---

## 2. I numeri

### 2.1 Churn per area: che cosa si rimescola davvero

Misurata con `git log --all --numstat` **filtrando per data autore** su una traversata aperta dal
24/08 (9/1→9/27, ogni commit contato una volta). Il motivo è un dettaglio che sposta i totali:
la finestra secca `--since=2026-09-01` **pota la traversata** — git interrompe la discesa quando
trova un genitore più vecchio della soglia, e così non vede 22 commit del **1° settembre** che sono
appendici di un albero d'agosto (731 invece di 743, −2,5% di righe). I contatori di §2.3 vengono
dalla traversata aperta; i conteggi *per area* della tabella qui sotto vengono invece da `churn.py`,
che gira sulla finestra potata: sono ~2,5% più bassi del valore corretto. «Morte ≤7g» = righe
aggiunte e poi rimosse entro 7 giorni dallo **stesso file**
(approssimazione LIFO: una cancellazione consuma prima le righe più recenti — **inferita** nel
meccanismo, misurata nei conteggi).

| area | +righe | −righe | vive (max sui ref) | morte ≤7g | morte ≤30g |
|---|---|---|---|---|---|
| tests/ | 66.552 | 3.034 | ~96% | 4% | 4% |
| docs/ | 51.222 | 2.193 | ~98% | 3% | 3% |
| frontend/ | 41.514 | 14.218 | ~86% | **21%** | 24% |
| backend/app/renderers/ | 13.844 | 2.630 | ~88% | 19% | 19% |
| calculations/ | 8.879 | 2.867 | ~84% | **26%** | 27% |
| importers/ | 7.334 | 844 | ~94% | 10% | 10% |
| backend/app/ (altro) | 9.176 | 1.526 | ~92% | 11% | 11% |
| **CLAUDE.md** | 934 | **275** | — | **29%** | 29% |
| tutto il repo | **215.434** | **28.222** | **93%** | **9%** | **10%** |

Le 12 aree di `churn.json` sommano 215.434 e 28.222; le quattro non elencate sopra (altro 10.564 /−426,
`scripts/` 5.213 /−147, `database/` 201 /−62, `pdf_service/` 1 /−0) entrano solo nel totale.

La colonna che conta è l'ultima: **il 90% di ciò che è stato aggiunto a settembre è stato scritto
una volta sola** (≤30 giorni). Le percentuali «vive» per area sono attribuzioni proporzionali
delle righe blame del commit (**inferite**); le «morte» sono il numero diretto, e non cambiano
il quadro: la rilavorazione non è cancellare codice, è **ripararlo dove è già vivo** — e si
concentra in due aree (calculations, frontend) più la documentazione di servizio (CLAUDE.md: 82
commit nel mese, riga nuova su quattro ricancellata entro una settimana).

Periodo nuovo 19→27: 52.651 righe aggiunte, morte ≤7g il 5%, vive il 96% — **la finestra migliore
del mese** (§5.1). Attenzione ai denominatori, che qui non sono lo stesso numero: il 96% viene da
`survival.py` (binari esclusi, 52.651 righe), il 5% da `churn730.py` (binari inclusi, 53.786): ~2%
di differenza, la lettura non cambia.

### 2.2 I file più riscritti

| file | commit | righe toccate | lettura |
|---|---|---|---|
| `calculations/forecast_engine.py` | **76** | +5.156/−1.430 | il cuore: ogni lotto, ogni rilievo, ogni decisione del proprietario passa di qui |
| `CLAUDE.md` | 82 | +934/−275 | documentazione di servizio: riscritta a ogni merge di lotto |
| `frontend/app/pratica/page.tsx` | 26 | +3.042/−2.748 | mezzo file riscritto: le tre campagne di UI (percorso, ipotesi, stampa) |
| `frontend/app/budget/page.tsx` | 25 | +630/−891 | più tolte che aggiunte: smantellato a favore dei moduli puri |
| `docs/budget/API-PREVISIONALE.md` | 54 | +1.228/−274 | la documentazione che insegue il motore |
| `backend/app/renderers/typst/editorial_inventory.py` | 10 | +1.314/−1.342 | **generazione bruciata**: metà riscritta, poi staccata (§3.6) |
| `calculations/intra_year_engine.py` | 28 | +2.275/−1.261 | come sopra, sull'infrannuale |
| `tests/fixtures/final_report/v2/*.json` | 6-7 | +22.677/−140 | le fixture rigenerate a ogni change del contratto — churn **meccanico**, non decisionale |

Una prudenza sulla colonna «commit»: **non ha un numero unico**. Dipende dalla potatura della
traversata e dai ref montati nell'istante della misura, e si muove di ±3 (la riga di
`pratica/page.tsx`, aperta dal 24/08 e filtrata per data autore, conta 29 commit, non 26). I
valori qui sono quelli di `churn.out` alle 14:30.

### 2.3 I contatori della rilavorazione git (tutti misurati)

| cosa | mese | 19→27 |
|---|---|---|
| commit non-merge (tutti i ref) | 743 | 241 |
| merge | 94 | 13 |
| commit `fix*` | 288 (39%) | 87 (36%) |
| commit con «fix round/wave, correzioni, revert, rilievi, ripristina» nel soggetto | 73 (revert veri: 2) | 32 |
| coppie di commit sullo stesso file entro 3 giorni (≥20 righe) | 851 | 227 |
| commit ≥50 righe la cui totalità è morta su ogni ref | 8 (1.294 righe) | 1 (141) |
| commit 19→27 non raggiungibili da `main` alla misura | 131 (16.801 righe) | — |

I due revert nominati: `3eac1e3` (08/09, generalizzazione non provata sul corpus) e `66c7f95`
(23/09, che **annulla** `d978001` «un totale si verifica su un livello solo» e due commit dopo
viene sostituita dalla versione corretta `b776b73` «riprova la ricerca un livello alla volta» —
è la correzione della correzione in forma pura).
Due note sui contatori della tabella. La riga «parole nel soggetto» è il filtro di `churn.py`
(`fix round|fix wave|correzion|revert|riliev|ripristin|regression|secondo giro|giro 2` sul solo
soggetto, traversata potata): il 73 è ciò che stampa `churn.out`, e la colonna periodo usa lo
stesso filtro sullo stesso tipo di passeggiata; allargare il filtro al corpo dei commit lo porta a
230, perché i corpi dei registri SDD nominano i fix round a ogni riga. E le righe «commit non-merge»
e `fix*` sono contate per data autore sulla traversata aperta, mentre «coppie ≤3gg» e la riga delle
keyword vengono da `churn.py` sulla finestra potata: ~2-5% di scarto fra le due famiglie, tenuto
dentro la stessa tabella — chi rimisura dica quale delle due ha usato.
La riga più lunga è l'ultima: al momento della misura metà del lavoro del periodo nuovo vive su
branch non mergiati (il motore mappa: 70 commit; i fix AMBIENTA: ~61 sugli altri rami, più qualche
cherry-pick). Non è lavoro perso, ma è **rilavorazione rinviata**: ogni branch in attesa è un rebase
e un re-test futuro. Alla sera dello stesso giorno, con i lotti mergiati, gli in volo sono **72**.

### 2.4 I giri di correzione, dai registri SDD

Marker contati con `grep -c "fix round\|fix wave"` e `grep -c Ruling` su ogni `progress.md`
(misurati; i 17 registri di settembre, nei worktree inclusi). **Un marker non è un giro**: ogni giro
di correzione produce almeno due righe (una di dispaccio, una di chiusura), quindi la colonna «fix
round» va letta come densità di scrittura, non come numero di ondate — contando i giri distinti
(`grep -oE 'Task [0-9]+: fix( round| wave) [0-9]+' | sort -u`) dai 53 marker escono **15 giri** nel
periodo, e 17 nel registro del 08/09. Righe = lotti del periodo nuovo, «task» = i titoli `Task N`
del piano:

| registro (data) | task | marker fix round | Ruling | revisione finale |
|---|---|---|---|---|
| import mappa (22/09) | 12 + 7b (il registro poi arriva a **Task 28**: «reader robustness A-F», un secondo giro di lotto) | **22** | 26 | Yes — 3 Important (sonnet) |
| route C su qwen (23/09) | 6 | 8 | 9 | «With fixes (doc only)» |
| route A/B qwen (23/09) | 6 | 0 | 7 | With fixes (1 Critical: cancelli API key) |
| report Business plan (23/09) | 12 | 0 | 6 | With fixes — 0 C, 3 I, 11 minor |
| report infrannuale (23/09) | 9 | 0 | 16 | With fixes — 0 C, 4 I, 5 minor |
| report docx (24/09) | 5 | 0 | 11 | With fixes — 1 C, 2 I, 8 minor |
| triage rilievi AMBIENTA (25/09) | 6 | 2 | 9 | With fixes — **verdetti sbagliati su 4 ID (A01, A04, A05, E05) + 2 fuorvianti (B04, A06)** |
| fix rilievi lotto 1 motore (26/09) | 8 | 7 | 9 | With fixes — 1 bloccante |
| fix rilievi lotto 2 report (26/09) | 8 | 10 | 14 | **No — with fixes** (4 bloccanti/importanti + 2 decisioni rinviate al proprietario) |
| fix rilievi lotto 3 wizard (26/09) | 2 | 4 | 3 | With fixes — 1 Important |

Due letture. (a) Il record di **53 marker di fix round (≈15 giri distinti) su 74 task del piano —
90 i task passati dai registri** — sta tutto nel 22→26, ma è asimmetrico:
i lotti report del 23-24 chiudono con **zero** marker per task (banco + contratto, §5.1), i
lotti di fix del 26 ne accumulano 21 su 18 task perché stanno correggendo codice nato mesi fa
sotto un osservatore nuovo (il consulente). (b) La prima metà di settembre aveva gli stessi
marker a densità più alta: `percorso-ipotesi-budget` **32 marker su 17 task (1,9/task)**, 45
Ruling — contro 0,7 marker/task del periodo nuovo (53 su 74). **Il giro di correzione per task sta
calando.**

### 2.5 Le sessioni della parte nuova (19→27)

`scripts/analisi_sessioni.py --da 2026-09-19 --a 2026-09-27` — dettagli in Appendice B.

| | Claude principale | subagente Claude | pi |
|---|---|---|---|
| unità | **4 sessioni** (2 coordinatori veri) | **158 agenti** con trascrizione (tutti classificati) | **7 run** (2 sono questa analisi e il notturno) |
| durata attiva | 41,4h | 57,8h | 8,0h |
| USD | **443,64** (opus 293,86 · sonnet 121,73 · fable 26,09 · haiku 1,95) | nel `cost-state` del principale | 0 (gx10 locale) |
| mix lavoro | — | implementazione 64 · revisione 61 · **ri-revisione 23** · ricognizione 6 | — |
| comandi falliti / sleep | 43 / 52 chiamate, 13 min | — | 46 / non misurato in questo giro |

Tre fatti nuovi, misurati:

1. **Claude ha ripreso il posto di pi come implementatore, senza una decisione scritta.**
   I pi del periodo sono 7 (84 fuori periodo nelle stesse cartelle), e i registri SDD del 22→26
   dicono «implementer sonnet» riga per riga. Nessuna memoria registra il sorpasso: l'ultima è
   «opus non è più il default nemmeno per il motore» (11/09); il 26/09 ne arriva una nuova,
   «opus per le revisioni finali» (memory `scelta-modello-subagenti`, modificata 26/09 09:26), che
   è coerente con gli 11 opus del periodo, 8 dei quali chiamate «Final review».
2. **Il costo della settimana nuova è 443,64 USD per 241 commit** (inferita la divisione: i commit
   dei subagenti non sono attribuibili): **1,84 contro 2,41 USD/commit non-merge** (241 e 297).
   La precedente retrospettiva divideva 715,36 per 357 commit *compresi i 60 merge*: con lo stesso
   criterio da entrambe le parti fa **1,75 contro 2,00**. La tendenza calante continua, e il confronto
   onesto è il primo; il salto vero è che ora spende in sonnet
   (implementazione + revisione) e non più in cache-letture opus.
3. **Il polling è quasi finito**: 13 minuti di `sleep` di Claude contro i **34** del periodo
   precedente (`per_sessione[*].sleep_s`: 785s su 3 sessioni con `sleep_s > 0`). Il «61 minuti»
   della retro del 19/09 era Claude **più** pi (2.030s + 1.646s), e non è confrontabile: in questo
   giro la chiave `sleep_s` delle 7 run pi esce a zero per tutte, perché lo script non la popola su
   questo percorso. La raccomandazione 4 del 19/09 ha funzionato
   per surclassa (`check --wait`, orchestrazione Orca) più che per regola.

Una nota di onestà sul punto 2: il `cost-state` delle due sessioni coordinatori è cumulato sulla
vita intera, e `4db3…4d3d` è iniziata **il 19/09 alle 06:35, cioè il primo giorno del periodo**:
tutta dentro, per fortuna. Non ci sono sessioni iniziate prima della finestra: il numero è pulito.

### 2.6 Che cosa costa la rilavorazione, in una riga

**Inferita**, con i pezzi misurati sopra: ~87 `fix` commit su 241 nel periodo nuovo; 53 marker di fix round
nei 10 registri SDD del periodo; revisioni finali tutte con-findings (10/10, §3.4). Se si assumesse
che un giro di correzione costi metà di un task, la parte di periodo nuova *spesa a correggere
lavoro del proprio stesso mese* è **~25-30%** (~110-130 dei 443 USD, ripartizione inferita).
Se si guardano solo i rilievi che riaprivano difetti già dichiarati chiusi (triage 25/09: ~6 ID su
21 fra «già risolto il 24/09», «comportamento voluto», «falso positivo di un test»), il costo puro
di **rilavorazione vera** è la parte A/B/E dei fix del 26/09, ~25-30 commit su ~60: **~12% del
periodo**. La differenza fra le due cifre è la definizione: *correggere ciò che è nuovo* (sano)
contro *riaprire ciò che era stato dichiarato finito* (la malattia).

---

## 3. Le cause della rilavorazione, con esempi verificati

### 3.1 La revisione esterna riapre ciò che avevamo «già corretto» — ed è la causa n.1

Il 25/09 arriva `inbox/Verifica_piano_Ambienta_problemi.xlsx`: 21 rilievi. Il triage (banco
meccanico su due commit + letture a mano, `tools/triage_rilievi.py`) produce il verdetto:

- **15 confermati**, di cui **10 «n/a su `62bfed1`»** (i nove C01-C09 e A02) — non erano difetti
  regressivi: i C sono difetti **di prima passata** del report nato due giorni prima, che nessuna
  delle 26 revisioni di task né le tre revisioni finali del lotto report aveva visto (li ha visti il
  foglio del consulente, §5.2);
- **3 non riprodotti** (A03, B04, A06 in parte): il sintomo del consulente si spiegava
  con A01-bis (il previsionale vecchio stampato dopo un salvataggio respinto — il difetto che
  `forecast_stale` documenta dal lotto 3B), non con la formula contestata;
- **1 comportamento voluto che produce sintomo vero** (A05: `beb33c5` «passare a Manuale da
  «ricavi» congela la crescita — decisione del proprietario», e il consulente lo ha letto come bug);
- **1 falso positivo nostro** (A01: il test Vitest era scritto sul percorso sbagliato,
  `final-findings.md` punto 1);
- **1 riprodotto come caratteristica voluta, in attesa di scelta** (E05: aliquota piena al primo anno
  e straordinari ripetuti ogni anno — «scelta ⚖»; i due test di caratterizzazione sono verdi oggi e
  diventeranno rossi quando la decisione sarà implementata).

(21 rilievi contati così: i 22 ID del banco meno **E04**, che è «Senza test» e fuori perimetro per
la spec §6).

Che cosa è rifatto qui, di già pagato: i ~60 commit dei tre lotti fix del 25-26/09
(`80048d3`…`c46a051`, due coordinatori e una trentina di subagenti) **esistono perché la verifica
è arrivata da fuori il ciclo**. E la riapertura era cominciata prima del foglio: A04 «risolto il
2026-09-24» (lettura nel rapporto di triage) e il mix del consulente riaperto lo stesso.

### 3.2 Definizioni duplicate: lo stesso indice scritto tre volte

C02-C07 **del triage** e F6/F7 **della revisione finale opus di lotto 2** sono tutti la stessa
cosa: **la formula di un indice vive in
`calculations/ratios.py`, in `backend/app/renderers/*/` (dossier, business_plan, infrannuale) e
in una riga di frontend** — e le copie divergono. Prova nel registro lotto 2: «due formule del
margine di tesoreria (ratios.py `sp06+sp07+sp09−passività`; report_indicators
`sp06+sp08+sp09+sp10−sp16`)»; e `c641f30` «C05 **un solo** current ratio», `65b2aa5` «C02…C07
**una definizione per indice**». È la stessa causa che la decisione del proprietario del 02/09
aveva chiuso nella proiezione (memoria `un-solo-motore-di-proiezione`, e CLAUDE.md: «tre bilanci
diversi della stessa azienda»; nella retro del 10/09 quel racconto non c'è): il
rimedio di allora — un motore solo, letto da tutti — non è stato esteso agli indici, e il conto
è arrivato 15 giorni dopo in un fix wave da 6 commit.

### 3.3 Le decisioni del proprietario arrivano dopo il codice (e il codice pagato va rifatto)

Tre esempi verificati, tutti nel periodo nuovo: **F2/F5** (26/09): la revisione finale di lotto 2
*blocca* il merge su due domande che non erano nel contratto — «DSCR conta scoperto e sweep?» e
«colonna base BEP 60/40 o quote del piano?» — decise al momento, con due fix commit
(`b01755c`, e BEP `d01db34`+2 round). **A05**: la decisione c'era (`beb33c5`), ma visse solo come
comportamento del motore, e il consulente l'ha pagata come bug. **23/09 «non facciamo altri test
con haiku, usiamo qwen»** (memory `banchi-solo-qwen`): ferma una passata di banco a 5/26 file.
Non è colpa delle decisioni: è che un **ruling senza riga di registro non esiste** — e i Ruling del
periodo stanno nei `progress.md` solo dove qualcuno li ha scritti (26 nel motore mappa, **0** nel
registro del 15/09 dove il `grep` non trova marker).

### 3.4 I difetti che escono solo dalla revisione finale — e le reti sbagliate

**Tutte e 10 le revisioni finali del periodo riportano almeno un rilievo Important**, e in **6**
di esse il giro dopo la revisione finale è un dispaccio separato, scritto nel registro come
«Final fix wave: dispatched» (mappa, route C, triage, lotti 1-2-3); negli altri 4 i fix
dell'ultima revisione entrano riga per riga senza un dispaccio proprio («Final: fixed …»). Il caso
di scuola è nel registro lotto 1: «nel lotto 1
del motore la revisione finale opus ha trovato **l'unico difetto che bloccava il merge** (pool degli
ammortamenti non riallineati a un `sp_overrides`), **passato a otto revisioni sonnet per task**»
(memory, 26/09). Sull'altro lato, la rete *giusta* ha funzionato: sul Business plan la revisione
finale ha promosso a fix «per effetto sul lettore» 4 dei suoi 11 minor, e i cancelli di banco del
23/09 hanno fermato `ModuleNotFoundError` e la pagina 7 fuori di 13 pt **prima** del merge. Il
costo non è fare la revisione: è farla tardi.

### 3.5 Documentazione falsa, e rilievi che la doc non può raggiungere

Il riallineamento del 25/09 mette a verbale una misura che vale da sola tutta questa sezione:
**«dei nove rilievi sotto, sette non erano raggiungibili né da citazioni né da citazioni_file:
tre pagine nominano il comportamento con parole proprie, e il comportamento si era mosso senza
che si muovesse nessuna delle loro firme. È la terza volta di fila»**
(`allineamento/2026-09-25.md`). E quello del 26/09: simboli mossi **0**, tutto il lavoro è stato
**ricontrollare le nove affermazioni** scritte il giorno prima — «otto delle nove voci sono
risultate vere», la nona applicata male. Un esempio che viene dal prodotto, non dalle firme: la
frase falsa «altri finanziatori fuori dalla PFN» era **nata il 23/09** col Business plan, e a
scoprirla falsa è stata la **revisione finale opus di lotto 2 il 26/09** (rilievo F4); `5bbde9b`
l'ha tolta in giornata. Nei registri del 23/09 quella frase non è mai nominata come difetto: ha
camminato tre giorni stampata. La memoria del progetto lo dice già («una riga di documentazione
su otto è falsa»): qui è misurato
come **1 correzione su 9 del giro di riallineamento sbagliata al primo colpo**, e come 26 commit
`docs(allineamento)` / +2.372 righe aggiunte da quei commit a settembre (misurato, `--all`
non-merge).

### 3.6 Che cosa è stato buttato per davvero

- **Il renderer Typst del dossier**: 8.529 righe aggiunte dal 13/09 (52 commit), **staccato
  dall'interfaccia il 24/09** (`6d2c447`) — il codice resta (scelta dichiarata: «rotte e codice
  restano, pronto a tornare come prodotto più avanzato»), ma a HEAD di main non produce più
  output: è il pezzo più grosso di settembre a lavorare a zero. Confronto onesto: il Word
  (`renderers/docx_export.py`) **ricicla gli stessi flowable** del ReportLab, quindi il costo del
  distacco è la traduzione, non il ri-facimento.
- **Il pilota «usa-e-getta» del motore mappa** (`613958b`, +882 righe): di quelle righe si butta
  davvero il solo telaio di pilotaggio (`pilota.py`, 114 righe, rimosso con `6d611d8`); il resto
  **diventa** il motore, coi rename `tools/pilota_import/* → importers/mappa_classificazione/*`
  (`237c8c7` lettore, `289c134` verifica, `a4a0d67` riconcilia, `e972996` classifica, `2a603af`
  mappa). Poco è dunque perso **per costruzione**: il costo vero del pilota sono i 22 marker di fix
  round che quella transizione ha chiesto (§2.4).
- **Commit ≥50 righe con zero sopravvissuti su ogni ref: 8 in tutto il mese (1.294 righe)**.
  Il numero piccolo è la scoperta: a settembre **non si è lavorato per niente invano** quasi mai;
  quasi tutto è passato da «vivo» a «vivo-corretto», non da «vivo» a «morto».
- **I rami di lavoro fantasma** del periodo vecchio (cherry-pick doppi `f234894`/`de84645`,
  `worktree-agent-ab1d87377f683bd5a`) non producono più morti: zero nel periodo nuovo.

### 3.7 I piani: si riscrivevano a mano a mano, ora si scrive tutto la mattina

Misurato con `git log --all --follow` sulle aggiunte di piano/spec di settembre (39 file, contati
una volta per file, branch dei worktree inclusi): i piani della prima metà del mese portano
10-19 commit di riscrittura ciascuno
(`scadenziamento-pregresso` 19, `report-finale-typst` 10, `percorso-ipotesi-rilievi-design` 6);
nel periodo nuovo se ne aggiungono 18, e **16 sono committati una volta sola** — le due eccezioni
sono design-spec riscritte *in stesura* (3 commit ciascuna, `import-llm-gx10` e
`import-mappa-classificazione`), nessuna riscritta a esecuzione iniziata. I tre lotti del 26/09
hanno scritto i piani la mattina (80048d3, 3737f29, 8147896, 4a4aeaf) e spediti il giorno stesso,
dopo il triage. La raccomandazione del 19/09 («gli emendamenti finiscono nei ruling») è stata
superata dai fatti: quando la spec arriva **dopo** la prova, il piano non ha bisogno di
emendamenti.

---

## 4. Le sette raccomandazioni del 19/09: applicate, con la prova

| # | Raccomandazione | Esito | Prova (periodo nuovo) |
|---|---|---|---|
| 1 | Artifact visivo: pilota + contratto **estratto**, poi il ventaglio | **applicata** | I tre lotti report del 23-24/09 chiudono con **0 marker di fix round per task**; il banco di pagina confronta con `BUSINESS PLAN RIVISITATO.pdf` (arrivato il 23/09 alle 15:28) e i Ruling «banco p7 di 13 pt» / «AIC 18→19 pagine» correggono **prima** del merge. Il caso contrario (§3.1) è quando il contratto non c'era: i C01-C09. |
| 2 | Il default di ogni meccanismo verificato nel prompt (base, worktree) | **applicata** | Ogni dispaccio che i registri scrivono come `dispatched` su lavoro nuovo nomina la BASE (`BASE 14b5755`, `BASE 3b96892`; i senza-BASE sono giri di correzione sullo stesso ramo); gli altri otto registri nominano la base con l'intervallo di commit («complete (commits X..Y)») o con l'intestazione del worktree («Worktree: … da 3737f29»), e uno (infrannuale) non la nomina mai. Nessun caso di worktree su base sbagliata nei log. Il difetto del 17/09 non è riapparso. |
| 3 | Un'affermazione non misurata non si scrive; sha solo se raggiungibile | **applicata, con un buco** | I rapporti di riallineamento dichiarano `sha_verificato` esplicito e «mai HEAD in corso d'opera» (25/09); MA la stessa misura del 26/09 trova che una delle nove «correzioni dimostrabili» del giorno prima era stata applicata male — l'abitudine è vera, la rete sul *comportamento* (non sulle sha) resta manuale. |
| 4 | Sostituire il polling, non scoraggiarlo | **applicata** | 13 minuti di `sleep` di Claude nel periodo (vs 34 sullo stesso perimetro; il «61» della volta scorsa includeva anche pi): le attese passano da `check`/`wait` di Orca. Nessun registro nuovo nomina sleep-loop. |
| 5 | `Closes #NN` come campo, non abitudine | **no (peggio)** | 0 commit con `Closes #` su 241 (periodo nuovo), **1 su 357** nel periodo prec. (retro 19/09 §7, `4dc1296` «Closes #51 / Refs #52»). **E il canale issue è stato abbandonato del tutto: 0 issue create dopo il 16/09** (l'ultima è #60, creata quel giorno); due aperte in tutto, #53 (11/09) e #60. Il tracciamento è migrato su `inbox/` + registri + branch — posto dove nessuna retrospettiva futura grep-pa. |
| 6 | Le raccomandazioni diventano artefatti o muoiono | **applicata per metà** | Dove sono diventate codice hanno funzionato: `tools/triage_rilievi.py` (banco con verdetti e `LETTURE`), `engine_version_stale`/`forecast_stale` come campi, il contratto delle pagine come JSON, `--sha` in riallinea. Dove sono rimaste abitudini di scrittura mancano ancora tutte (`Closes #NN`, il «perimetro» nel prompt). La meta-regola del 19/09 regge: è il campione che si è allargato. |
| 7 | Limite di parallelismo pi da rimisurare | **caduta** (surclassata) | Non rimisurata: pi esce di scena come implementatore (7 run nel periodo, di cui 2 questa analisi e il notturno) senza che **nessuna** decisione scritta lo dica. La raccomandazione era «se il collo è gx10, il numero dipende». Il collo si è spostato altrove. |

**Totale: 4 applicate, 1 a metà, 1 no, 1 caduta.** Capovolto il bilancio del 19/09 (1/3/3): le
raccomandazioni che sono diventate codice o un campo nei registri si applicano da sole; quelle
rimaste abitudini di scrittura (`Closes #NN`, il perimetro nel prompt) mancano ancora, e quella
che presupponeva un esecutore (pi) è evaporata con l'esecutore.

---

## 5. Che cosa ha funzionato / che cosa no

### 5.1 Ha funzionato (con numeri)

- **Contratto + banco, quando c'è, azzera i giri di correzione.** Il Business plan ha il banco di
  pagina che confronta con `BUSINESS PLAN RIVISITATO.pdf` (arrivato il 23/09 alle 15:28) e i Ruling
  «banco p7 di 13 pt» / «AIC 18→19 pagine» correggono **prima** del merge; l'infrannuale porta il
  proprio, il Word i test sul contratto di pagina. Risultato: 26 task nei tre lotti report,
  **0 marker di fix round per task**, 25 commit sui renderer nei giorni 22-24/09 (misurato:
  `git log --all --no-merges --since=2026-09-22 --until=2026-09-25 -- backend/app/renderers`). Il
  contrasto è con il motore mappa della stessa settimana: **22 marker su 13 task** (12 del piano più
  il 7b; il registro poi arriva a Task 28), perché lì il contratto del lettore geometrico lo si
  scopriva a mano, un PDF alla volta.
- **Il triage come artefatto, non come discussione.** 21 rilievi → verdetto per ID in **un giorno**,
  con xfail strict che **non lasciano dichiarare chiuso ciò che non passa** — e che alla revisione
  finale hanno fatto ammettere al tool di invertire i verdetti. Il giorno dopo, i piani di fix
  nascevano già collaudati.
- **I piani nati la mattina.** §3.7: 18 piani/spec nel periodo, 16 committati una volta sola.
  La rata di riscrittura del piano (la metrica della retro del 19/09) è a zero nel periodo.
- **Le decisioni che cambiano il modello escono prima del codice, nei ruling**: il periodo nuovo
  conta **110 Ruling numerati** nei 10 registri — **81 recano la clausola «costo se sbagliato»**
  parola per parola e **92 nominano un costo in qualche forma** (le altre 18 la omettono o dicono
  «nessuno» / «costano poco»): la clausola è la norma, non un'universalità. Il float che la
  regola Decimal del 15/09 aveva cacciato non è riapparso.

### 5.2 Non ha funzionato

- **L'ultima linea di verifica è esterna e arriva a ciclo chiuso.** I rilievi del consulente
  (25/09) e i PDF «rivisitati» (23/09) sono gli unici momenti in cui qualcuno guarda il prodotto
  come un lettore. Finché l'osservatore esterno è l'ultimo gate, ogni suo passaggio produce un
  lotto di fix: **a settembre ne sono serviti quattro cicli** (3A/3B, ondata finale, rilievi
  ipotesi, AMBIENTA) per la stessa classe di difetti.
- **Nove definizioni di indice nel prodotto, e la UI che le mostrava diverse.** §3.2: l'invariante
  che per la proiezione esiste come regola scritta e verificata («Un solo motore di proiezione, e
  sta in Python», CLAUDE.md, e la memoria `un-solo-motore-di-proiezione`) per gli indici non è mai
  diventata una regola del genere, e nessun test di parità la verifica.
  `ivcee-catalog-parity.test.ts` congela le righe: non esiste un test
  analogo per le **formule**.
- **Le issue sono morte e niente le ha sostituite.** 0 create dal 16/09, e il `--jq` di una
  futura retrospettiva su `gh issue list` darà un mese vuoto mentre il lavoro (tanto) era da
  un'altra parte. La raccomandazione 5 è, di fatto, diventata «decidi dove vive il tracciamento»
  — e non è stata decisa.
- **Il branch non mergiato come norma.** §2.3: 131 commit e 16.801 righe del periodo sopra branch
  aperti alla misura (mappa 70, il resto sono fix e test AMBIENTA ~61, vari cherry-pick). Il merge
  in main il giorno stesso (regola del periodo vecchio) è diventato «merge quando la revisione
  finale dice sì», e quando la revisione finale dice «No — with fixes» il branch invecchia un
  altro giro.

---

## 6. Raccomandazioni (misurabili)

Ognuna con la metrica con cui la prossima retrospettiva la controllerà — così com'era stato
promesso in chiusura della volta scorsa: una raccomandazione senza metrica è un augurio.

1. **Un test di parità delle formule, come `ivcee-catalog-parity` ma per i numeri.** Una suite che
   per ogni indice/chiave KPI confronta `ratios.py`, ogni renderer e il frontend, e fallisce se due
   definizioni divergono. → *Metrica: diff `fix(indici)` causati da definizioni divergenti nel
   prossimo mese: 0.* (Settembre: 9 rilievi C01-C09 + F6/F7, ~8 commit.)
2. **Porta l'osservatore esterno dentro il ciclo, non alla fine.** Ogni lotto che tocca un output
   consegnato (PDF, Word, /report) include un giro «banco cieco» con un agente che legge il PDF
   come il consulente, **prima** del merge, con la griglia dei rilievi tipizzati (A/B/C/E del
   triage AMBIENTA) come checklist. → *Metrica: quota dei rilievi esterni confermati su lavoro
   «finito» sul totale dei rilievi: 15/21 a settembre; sotto 6/21 a ottobre.*
3. **Scegli dove vive il tracciamento, e scrivilo in una riga di CLAUDE.md.** O le issue tornano
   (`Closes #NN` nel template dei registri, non nei prompt), o il canale ufficiale diventa
   `triage/` + `final-findings.md` e questa retrospettiva smette di grep-parle. → *Metrica:
   issue create nel mese: 0 a settembre (16/09 poi); ≥15 a ottobre se il canale è scelto, oppure
   0 con la riga scritta.*
4. **Niente branch oltre 48 ore senza merge o rebase dichiarata.** Misura i giorni di vita dei ref
   non in `main` alla data di misura. → *Metrica: commit non raggiungibili da main alla prossima
   misura: 131 oggi (72 alla sera dello stesso giorno, coi lotti mergiati); ≤30.* (Ogni giorno in più è il costo del merge, che il blame «vivo» non vede.)
5. **Ogni decisione che cambia un output si scrive come Ruling nel registro del lotto, lo stesso
   giorno.** A05/BEP/DSCR insegnano: una decisione del proprietario vale quanto un bug, e il
   costo se sbagliato è identico. → *Metrica: Ruling nei registri: 110 nel periodo nuovo (bene);
   rilievi di triage la cui causa è una decisione non scritta: 1/21 — sotto 1 il prossimo mese,
   e ogni «comportamento voluto» del triage deve puntare a una riga di registro.*
6. **La documentazione di comportamento si ri-verifica coi piedi nel prodotto: il giro di
   riallineamento legge anche i verbali, non solo le firme.** Il 25/09 ha misurato che 7 rilievi
   su 9 erano fuori dalla portata del join simbolico; il rimedio meccanico non c'è ancora. →
   *Metrica: nel rapporto di riallineamento di ottobre, la riga «raggiungibili dalle citazioni»
   sui rilievi confermati del mese: ora 2/9, obiettivo ≥5/9 (con l'elenco dei non raggiungibili
   migrato in regole a forma meccanica — tabella campi, `STEP_FIELDS`, rotte).*
7. **Dichiara l'esecutore corrente nei registri come campo, non come prosa.** pi senza una
   decisione scritta, opus promosso «a posteriori» (26/09): la prossima retrospettiva non deve
   dedurre chi implementa da un grep su «implementer sonnet». → *Metrica: ogni `progress.md` di
   ottobre ha una riga `esecutori:`; l'aggregato `per_esecutore` torna a leggere quel campo.*

---

## Appendice A — come rimisurare

```bash
# Sessioni (identico alle precedenti; le run pi si leggono di default, --no-pi per escluderle):
python3 scripts/analisi_sessioni.py --da 2026-09-19 --a 2026-09-27 \
    --out .superpowers/retrospettiva/2026-09-26
# 4 sessioni Claude (75.242 righe lette), 158 subagenti classificati, 7 run pi, 443,64 USD.

# Churn + sopravvivenza (script di questa analisi, in .superpowers/retrospettiva/2026-09-26/;
# girano tutti e tre sulla finestra potata --since=2026-09-01, ~2,5% sotto la traversata aperta):
python3 churn.py        # numstat per area/file + keyword fix (soggetto) + coppie ≤3gg → churn.out
python3 survival.py     # sopravvivenza max sui ref attivi — ATTENZIONE: mai blame su binari:
                        # un .ttf vale ~10.000 «righe» e falsava tutto al primo giro (0→105%)
python3 churn730.py     # righe aggiunte poi rimosse entro 7/30gg, per area (LIFO per file)

# Contatori git a mano — LA finestra va percorsa aperta e filtrata per data autore: la forma
# secca --since=2026-09-01 interrompe la discesa al primo genitore d'agosto e perde 22 commit
# del 1° settembre (731 invece di 743).
B=/home/peter/DEV/budget
git -C $B log --all --no-merges --since=2026-08-24 --date=iso-strict --pretty='%ad' \
  | awk '$1>="2026-09-01" && $1<"2026-09-26T14:30"' | wc -l                                # 743 (742 alla replica)
git -C $B log --all --no-merges --since=2026-08-24 --date=iso-strict --pretty='%ad' \
  | awk '$1>="2026-09-19" && $1<"2026-09-26T14:30"' | wc -l                                # 241 (240 alla replica)
git -C $B log --all --no-merges --since=2026-08-24 --format='%ad%x09%s' --date=iso-strict \
  | awk -F'\t' '$1>="2026-09-19" && $1<"2026-09-26T14:30"{print $2}' | grep -cE '^fix'   # 87 alla misura, 86-90 oggi
# Qui il `Closes #` non si filtra per data autore: un corpo multiriga, passato in awk, lascia
# passare le righe che iniziano per lettera (esce 4 invece di 0). Si chiudono le due estremita'.
git -C $B log --all --no-merges --since=2026-09-19 --until=2026-09-26T14:30 --format='%b' \
  | grep -c 'Closes #'                                                                  # 0
git -C $B log --all --no-merges --since=2026-08-24 --numstat --format='%x01%ad' --date=iso-strict \
  | awk '/^\x01/{d=substr($0,2,16); next} $1!="-" && d>="2026-09-01" && d<"2026-09-26T14:30" {a+=$1} END{print a}'
                                                                                        # ~218.200 (215.434 con la finestra potata)
git -C $B log --all --no-merges --since=2026-09-01 --until=2026-09-27 --format='%s' \
  | grep -ciE 'fix round|fix wave|correzion|revert|riliev|ripristin|regression|secondo giro|giro 2'   # 73 in churn.out (71-73 oggi)

# Ref in volo alla misura. La forma `--not $(git for-each-ref … | grep -v retrospettiva)` non
# funziona: si esclude da sé tutto ciò che `--all` include, e restituisce 1. `fe2a79b` è la punta
# di main all'istante della misura.
git -C $B log --all --no-merges --since=2026-09-19 --until=2026-09-26T14:30 --not fe2a79b \
  --oneline | wc -l                                                                     # 131 (130 oggi)
git -C $B log --all --no-merges --since=2026-09-19 --until=2026-09-26T14:30 --not fe2a79b \
  --numstat --format= | awk '$1!="-"{a+=$1} END{print a}'                               # 16.801 (16.715 oggi)
git -C $B log fe2a79b..3737f29 --no-merges --oneline | wc -l                             # 36: lotto 1, fix AMBIENTA
git -C $B log feat/import-mappa-classificazione --not main --no-merges --oneline | wc -l   # 70: il motore mappa
# (i nomi `fix/rilievi-ambienta` e `fix/rilievi-l2` non esistono più: mergiati alle 15:34 con
#  `78e8278` e `4167b65`; contro la main di stasera gli in volo sono 72)

# Giri di correzione per registro (i registri stanno nei worktree, non solo nell'albero):
for f in /home/peter/DEV/budget{,-*}/.superpowers/sdd/2026-09-*/progress.md; do [ -f "$f" ] &&
  echo "$(grep -c 'fix round\|fix wave' $f) $(grep -c Ruling $f) $f"; done | sort -u
# 17 registri; la prima colonna sono MARKER di riga, non giri: per i giri distinti
#   grep -oE 'Task [0-9]+: fix( round| wave) [0-9]+' progress.md | sort -u | wc -l   → 15 nel periodo, 17 nel 08/09

# Piani/spec riscritti (39 file a settembre, non 43: §3.7):
git -C $B log --all --diff-filter=A --format= --name-only \
    --since=2026-09-01 --until=2026-09-27 -- 'docs/superpowers/plans/*' 'docs/superpowers/specs/*' | sort -u
# poi per ognuno: git log --all --follow --oneline --since=2026-09-01 -- <file>

# Verdetto triage AMBIENTA (il `sed '/## Verdetto per ID/,/^```/p'` si ferma alla fence che APRE
# il blocco e stampa solo il titolo — servono due fence):
awk '/^## Verdetto per ID/{f=1} f{print} f&&/^```$/{c++; if(c==2) exit}' \
  /home/peter/DEV/budget/docs/superpowers/allineamento/2026-09-25-triage-rilievi-ambienta.md
```

Cinque avvertenze per chi rimisura:

- **Il blame sui binari mente.** `git blame` su un `.ttf` conta ~10k righe e attribuisce; il filtro
  (solo file con `+` numerico nel numstat, esclusioni per estensione) è dentro `survival.py`: non
  toglierlo. Il primo giro di questa analisi ha prodotto un «105% di sopravvivenza» con quel bug.
- **La LIFO di `churn730.py` è un'approssimazione**: una cancellazione consuma le aggiunte più
  recenti dello stesso file. Con `--all` i cherry-pick doppi contano due volte (pochi casi: i
  rami `worktree-agent-*`, dups `f23489`/`de84645`). È il motivo per cui le percentuali vanno
  lette come ordine di grandezza, **inferite** nel meccanismo.
- **I ref non mergiati cambiano il segno delle cifre tra due misurazioni dello stesso giorno.**
  «Vive 93%» è *max sui ref alla misura del 26/09 alle 14:30*: il 27 i fix AMBIENTA saranno in
  main e il numero si muoverà di un paio di punti. Il timestamp della misura è d'obbligo.
- **Il blame sui commit conta ±3 per file.** La colonna «commit» di §2.2 dipende dalla potatura e
  dai ref montati: la stessa riga di `pratica/page.tsx`, aperta dal 24/08 e filtrata per data
  autore, dà 29 commit, non 26. Chi rimisura dica quale traversata ha usato.
- **`survival.py` si mangia il proprio osservatore.** Esclude i ref `retrospettiva*` dalla
  raggiungibilità, quindi il commit di *questo rapporto* (07d12ad), che non vive su nessun altro
  ref, entra fra i «morti ≥50 righe»: alla misura 8 commit / 1.294 righe, alla replica serale
  9 / 1.774. Non è una regressione, è la finestra che ha mangiato chi la guarda.

## Appendice B — le sessioni del periodo nuovo

Claude (tutte iniziate nella finestra; attive ed USD dal `cost-state`):

| sessione | quando | attive | USD | agenti | commit | merge | cosa era |
|---|---|---|---|---|---|---|---|
| `4db3…4d3d` | 19→23/09 | 22,4h | 334,83 | 80 | 12 | 15 | coordinatore: chiusura retro, report intermedio, gx10/qwen, pilota mappa |
| `b187…1d76` | 21/09 | 0,6h | 4,75 | 0 | 1 | 0 | parentesi |
| `c84c…b587` | 23→26/09 | 18,3h | 104,05 | 78 | 37 | 15 | coordinatore: BP/infrannuale/docx/solo-bp, triage AMBIENTA, i tre lotti di fix |
| `facb…af1b` | 23/09 | 7s | 0 | 0 | 0 | 0 | svegliata da orchestrazione, come `90a1c2d7` della retro del 10/09 |

> 158 subagenti: sonnet 139 (implementazione 61, revisione 52, ri-revisione 19), **opus 11 — 8
> «Final review»** (la decisione del 26/09), haiku 8. Cache-lettura sonnet 2,24 miliardi: il
> numero che paga, come la volta scorsa. 25 riprese, 0 errori API.

pi:

| run | worktree | quando | attive | turni | commit |
|---|---|---|---|---|---|
| `01a0…b538` | `budget` | 19/09 | 0,3h | 49 | 3 |
| `01a0…b80f` | `budget` | 19/09 | 2,8h | 280 | 16 |
| `01a0…ba46` | `retrospettiva-settembre` | 19/09 | 1,5h | 192 | 6 |
| `01a0…d89b` | `budget` | 25/09 | 2,8h | 357 | 3 |
| `01a0…dbf8` | `budget` | 26/09 | 0,6h | 125 | 2 |
| `01a0…dd64` | `budget` | 26/09 | 0,0h | 3 | 0 |
| `01a0…ddab` | `retrospettiva-2026-09-26` | 26/09 | 0,0h | 9 | 0 *(è questa analisi)* |

---

*Il resto delle cifre vive in `.superpowers/retrospettiva/2026-09-26/` (aggregato.{json,md},
churn.{json,out}, survival.json, churn730.out, schede/). I worktree con lavoro in volo sono stati
usati in sola lettura; nessun repository toccato fuori da questo.*
