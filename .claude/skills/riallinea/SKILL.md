---
name: riallinea
description: Use when the user wants to check that documentation and memory still match the code — after a significant change, or as a periodic sweep. Finds claims the code contradicts, fixes only what is mechanically provable, reports the rest.
---

# Riallineamento documentazione ↔ codice

Trova le affermazioni di documentazione che il codice smentisce. **Corregge solo il
dimostrabile; segnala tutto il resto.** Non modifica mai un file di memoria.

Spec: `docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md`

## Perché è severo

Una correzione sbagliata è peggio del disallineamento: finisce in `CLAUDE.md`, che è
caricato a ogni sessione, firmata da un commit che dice di aver sistemato le cose, e
nessuno la rilegge. Nel dubbio si segnala.

## Procedura

1. **Raccogli, su un HEAD fermo.** `python3 scripts/riallinea.py --a <sha>` (aggiungi
   `--completo` se l'utente chiede lo sweep integrale; `--da <sha>` alla prima
   esecuzione). **Passa `--a` esplicito e verifica contro quello sha**, dichiarandolo nel
   rapporto: nel giro 2026-09-18 `main` si è mosso durante l'esecuzione, le prime letture
   erano su un albero vecchio e un rilievo è stato scritto e poi ritirato. Il JSON porta
   `sha_verificato`: è quello che va nel rapporto.
2. **Modo `diff` (default): parti dai `commits`, POI verifica tutte le citazioni.**
   - **I commit vengono prima, e non sono un extra.** Per ciascuno, il soggetto e il
     corpo dicono se ha cambiato una **regola**. Per ogni commit che ne cambia una,
     chiediti: *quali pagine enunciano quella regola?* — e cercale per **argomento**
     («aliquota», «TFR», «circolante»), non per nome di simbolo. È l'unico modo di
     arrivare a una pagina di prosa, e la misura dice quanto conta: sul giro 2026-09-18,
     **13 frasi false su 14 non nominavano alcun simbolo mosso**, quindi nessun join le
     avrebbe mai pescate. `docs/budget/FORECASTING_GUIDE.md` — la pagina più sbagliata
     di quel giro — non nomina né un simbolo mosso né un file di codice: era raggiungibile
     **solo** dal messaggio di `073927b`.
   - **Un buco della spina, quantificato (2026-09-19):** una citazione *nuova* scritta dentro
     la prosa di un commit che tocca solo `.md` non produce alcun candidato: il canale per
     simbolo salta le righe non-codice, e quello per file è invertito (cerca i documenti che
     nominano un file *toccato*, quindi una cita verso un file che l'intervallo non tocca —
     `aliquota-proposta.ts`, mai esistito — non la vede). Su 914 commit dall'1 giugno, 160
     toccano solo `.md` e 52 di questi aggiungevano un rimando a un file di codice: quella
     classe la copre `--puntatori` (o `--completo`), non la spina. È pinato in
     `tests/test_riallinea.py`.
   - **Poi verifica TUTTE le citazioni prodotte** (`citazioni`, per nome di simbolo, e
     `citazioni_file`, per percorso di file toccato). Se un diff enorme ne produce troppe
     per una verifica completa, applica la strategia dello sweep (sotto) e dichiaralo nel
     rapporto: è un'eccezione, non la norma.
3. **Modo `--completo`: applica la strategia a tre livelli** descritta sotto — non è
   negoziabile caso per caso.
4. **Per ciascuna citazione verificata**, apri il codice e stabilisci:
   - `OK` — il codice conferma. Nessuna azione.
   - `MORTO` — il simbolo nominato non esiste più.
   - `SMENTITO` — esiste, ma il codice fa altro.

   Più due classi che non nascono da una citazione, e vanno guardate comunque:
   - **`non_documentati` — una manopola nuova che nessun documento nomina.** Una colonna
     o una rotta aggiunta nell'intervallo con **zero** citazioni. Non è una frase
     sbagliata: è una funzionalità di cui nessuna pagina parla, e il silenzio non si
     distingue da «allineato». Verifica che sia davvero una manopola dell'utente e, se lo
     è, va in «Da decidere» con la proposta di dove documentarla. Misurato: nel giro
     2026-09-18 la lista avrebbe avuto **una riga sola**, `working_capital_mode` — una
     scelta di motore a tre valori, con dentro una ricerca per bisezione, zero occorrenze
     in tutta la documentazione. Era il buco più grosso del giro, e la raccolta lo
     scartava.
   - **`citazioni_file` — una pagina che nomina un file toccato.** Chiave debole (basta
     il basename) ma prende pagine che il nome di simbolo non tocca. Trattala come le
     altre citazioni: si apre il codice, si giudica.
5. **Correggi solo dentro la lista chiusa** (sotto). Tutto il resto va in «Da decidere».
6. **Verifica anche la memoria**, ma non modificarla: solo riferimenti morti a rapporto.
7. **Scrivi il rapporto**, sempre, anche a esito nullo.
7-bis. **Verifica gli sha che il rapporto cita**, prima di committarlo:
   `python3 scripts/riallinea.py --sha --data <AAAA-MM-GG>`. Tre esiti distinti perche' sono
   tre difetti diversi: `antenato` (ok), `orfano` (l'oggetto esiste a `cat-file -e` ma non e'
   raggiungibile da HEAD: il caso del commit emendato a meta' giro, che nessuno sguardo
   precedente vedeva), `inesistente`. Esce 1 con l'elenco e **non corregge nulla**: la
   correzione e' non citare sha irraggiungibili, riscrivendo la frase coi sostituti. Il numero
   e' 7-bis e non 8 per non rinumerare una procedura citata per numero altrove (qui al passo 9,
   e nel piano notturno).
8. **Committa in due volte**: prima le correzioni con il messaggio
   `docs(allineamento): correzioni dimostrabili`, poi il rapporto con
   `docs(allineamento): rapporto AAAA-MM-GG` (data del rapporto, non del giorno in cui
   giri lo skill se sono diversi). Letterali: non improvvisare un formato diverso, o i
   commit di riallineamento smettono di essere riconoscibili nel log.

   **Aggiungi solo i file toccati, nominandoli uno per uno** (`git add <percorso1>
   <percorso2> ...`). **`git add -A` e `git add .` sono vietati.** Nel repo convivono
   backup del database (`financial_analysis.db.bak-*`) e PDF di test non tracciati che
   non devono finire in un commit — e la convenzione qui è commit diretto su `main`,
   con Jenkins che builda a ogni push: un `git add` indiscriminato è l'unico modo in
   cui questo strumento può fare un danno vero.
9. **Registra l'esito, DOPO aver committato** — mai a mano, mai durante la raccolta
   (quella avviene prima di sapere com'è andata la verifica):
   ```bash
   python3 scripts/riallinea.py --registra <SHA verificato> --modo <diff|completo> \
       --data <AAAA-MM-GG del rapporto> \
       [--ripresa-l3 "<ultimo documento verificato PER INTERO al Livello 3>"]
   ```
   `--registra` è l'unico ramo della CLI autorizzato a scrivere `STATO.json`. Passa
   `--ripresa-l3` solo se hai girato il Livello 3, con l'ultimo documento verificato
   **per intero** — non quello su cui il tetto ti ha fermato a metà, se lì restavano
   citazioni non ancora guardate (vedi il Livello 3 sotto per il perché). Se lo ometti,
   la chiave esistente nello stato resta intatta: `salva_stato` scrive sopra solo le
   chiavi che conosce.

### `--puntatori`: il produttore di candidati che mancava alla lista chiusa §§1-2

`python3 scripts/riallinea.py --puntatori` elenca i percorsi citati in backtick il cui **basename
non esiste in nessun file del repo** — la classe di difetto che finora veniva fuori solo a mano,
giro dopo giro (`editorial_inventory.py` x13, `lib/aliquota-proposta.ts`,
`components/IntraYearAiComments.tsx`). **È un generatore di candidati, non un gate**: esce 0 sempre
e metà dell'elenco sono menzioni storiche corrette. Da qui le tre scelte che lo rendono leggibile:

- il predicato è il **basename**, non il percorso: `lib/pratica-codes.ts` non risolve dalla radice
  (vive in `frontend/lib/`, convenzione del progetto) e trattarlo da morto darebbe ~573 falsi
  positivi, seppellendo i ~41 veri;
- sono candidati anche i **nomi senza barra** (`CONTEXT-MAP.md`, il caso di `docs/agents/domain.md`)
  e il **codice**, perché le docstring dei servizi puntano al frontend: il caso di oggi era
  `aliquota_service.py:10`;
- i **verbali** (`docs/superpowers/plans|specs/`, `docs/piano-import-2026-07/`, `docs/outputs/`,
  `docs/archive/`) entrano marcati `[verbale]` e ordinati per ultimi: non si correggono mai, e in
  mezzo agli altri sono rumore (misurato: 176 su 247).

I fenced block del markdown sono saltati; il costo è perdere candidati dentro gli esempi, mai
inventarne. **Non è un passo del giro**: 247 candidati non sono una cosa da mettere in coda a una
notturna. È lo strumento di 1) e 2) quando si investigate.

## Strategia per lo sweep completo (`--completo`)

Un `--completo` sul repo reale produce **5857 simboli, 11366 citazioni, 143 nomi
generici e 40 manopole senza alcuna citazione** (rimisurato il 2026-09-19 dopo
l'allargamento di `RADICI_DOC` a `.claude/`; era 5822/11338/141/40 prima, e
2722/5722/50 il 2026-08-14 — il corpus raddoppia, e questi numeri invecchiano: rimisurali invece di
citarli). Nessun modello può leggere il codice dietro undicimila affermazioni in
un'unica esecuzione. Campionare in silenzio sarebbe
peggio di non verificare affatto: produrrebbe un rapporto che sembra esaustivo e non
lo è — il guasto stesso che questo strumento esiste per prevenire.

La regola è quindi: **verifica a fondo (apri il codice, giudica il comportamento)
solo un sottoinsieme dichiarato, in un ordine di priorità fisso, e dichiara in testa
al rapporto quante affermazioni erano candidate contro quante sono state
effettivamente verificate — mai una percentuale implicita.**

Tre livelli, in quest'ordine, senza eccezioni:

1. **Livello 1 — tutte le citazioni in `CLAUDE.md`.** È il file caricato a ogni
   sessione: un suo errore costa più di qualunque altro. Verifica integrale, sempre,
   qualunque sia il numero. **Non è "per costruzione limitato" — è un'affermazione
   falsa, misurata:** su uno sweep `--completo` reale `CLAUDE.md` da solo porta **332
   citazioni**, più dell'intero tetto di 300 del Livello 3. È l'unico livello senza un
   tetto dichiarato proprio per questo: essere un solo file non lo rende piccolo.
2. **Livello 2 — tutti i candidati `MORTO`, su tutto il repo.** Prima di leggere una
   sola citazione, fai passare **ogni simbolo** (non ogni citazione — molte citazioni
   condividono lo stesso simbolo, quindi il lavoro è sui ~5822 simboli, non sulle 11338
   righe) per un controllo meccanico di esistenza:
   ```bash
   git grep -n -w -- '<nome_simbolo>' -- '*.py' '*.ts' '*.tsx' '*.js' '*.jsx'
   ```
   Zero risultati nel codice attuale ⇒ candidato `MORTO`: tutte le sue citazioni
   passano al livello 2. Questo controllo è economico (un grep per simbolo) e ad alto
   valore (un nome morto è un errore inequivocabile), quindi non ha un tetto: si
   verificano **tutti** i candidati `MORTO` trovati, applicando comunque la lista
   chiusa e la regola del rename (`git log -M --follow`) prima di dichiarare `MORTO`
   invece di un rename mancato.
3. **Livello 3 — il resto, fino a un tetto dichiarato di 300 citazioni lette a
   fondo.** Filtrate le citazioni già coperte dai livelli 1 e 2, ordina i documenti
   rimanenti per percorso (ordine alfabetico, deterministico e riproducibile). **La
   ripresa è vera, non solo dichiarata:** leggi `ripresa_l3` da `STATO.json` (scritto
   al passo 9) e parti dal documento **successivo** a quello nell'ordinamento — non
   dalla testa alfabetica. Se `ripresa_l3` è assente (è il primo sweep, o `STATO.json`
   non l'ha ancora mai scritta), parti dall'inizio: dillo esplicitamente nel rapporto,
   così un'esecuzione successiva non trova un caso ambiguo. Verifica citazione per
   citazione, documento per documento, finché non raggiungi 300 verifiche di livello 3
   in questa esecuzione.

   **`ripresa_l3` registra l'ultimo documento verificato PER INTERO — mai un
   documento su cui il tetto ti ha fermato a metà.** Se le 300 verifiche si esauriscono
   mentre un documento ha ancora citazioni non guardate, quel documento **non** entra
   in `ripresa_l3`: lo sweep successivo riparte dal documento dopo l'ultimo
   completato — che è proprio quello interrotto — e ne riverifica le citazioni da
   capo. Costa qualche verifica ripetuta; l'alternativa (registrarlo comunque come
   "ultimo verificato") farebbe sparire per sempre le sue citazioni non ancora
   guardate, che è il buco che questa regola esiste per chiudere: un documento riletto
   costa poco, una citazione saltata non si recupera più.

   **Caso limite: il primo documento del giro è più lungo del tetto residuo.** Non
   completerà mai in una sola esecuzione, quindi `ripresa_l3` non avanzerebbe mai e il
   giro si bloccherebbe per sempre sullo stesso documento. Non inventare un
   meccanismo di ripresa parziale dentro un documento: **segnalalo nel rapporto**
   ("documento X non completabile entro il tetto: N citazioni, tetto residuo M") e
   registralo comunque come completo in `ripresa_l3`, per lasciare avanzare il giro
   invece di bloccarlo su un solo documento — è deliberatamente un'eccezione alla
   regola "mai a metà" appena scritta, e va dichiarata come tale nel rapporto, non
   applicata in silenzio.

   Se arrivi in fondo all'elenco dei documenti prima del tetto, **riavvolgi**
   all'inizio e continua da lì. 300 è scelto per stare comodamente dentro una sessione
   (in linea con le poche decine tipiche di un `diff`, moltiplicate per un fattore che
   lascia margine senza pretendere l'impossibile) — non è calibrato su una misura di
   tempo, è un tetto esplicito che chiunque legga lo skill può cambiare
   consapevolmente.

**Con un tetto di 300 su ~11338 citazioni candidate, uno sweep guarda meno del 3% del
corpo al Livello 3.** Servono all'incirca 38 sweep perché il giro dell'alfabeto si
chiuda e si ricominci da dove si era partiti la prima volta — la ripresa fa
avanzare la copertura sweep dopo sweep invece di rileggere sempre la stessa testa,
ma resta un giro lento: chi decide se e quando lanciare lo sweep completo deve saperlo
prima di lanciarlo, non dedurlo dal rapporto dopo.

**Cosa NON è stato guardato va dichiarato, non taciuto.** Il rapporto elenca i
documenti (percorso + numero di citazioni residue) che restavano fuori dal tetto di
livello 3 quando l'esecuzione si è fermata, così la prossima esecuzione — o una
persona — sa esattamente da dove riprendere. I 50 nomi generici (`generici` nel JSON,
citazioni ≥ `SOGLIA_GENERICO`) non entrano MAI nella verifica per nome: sono per
costruzione troppo comuni per essere affermazioni verificabili individualmente: si
riportano nel rapporto con il conteggio, non si aprono uno per uno.

**In testa a ogni rapporto di uno sweep completo:**
```
Candidate: <conteggio> · Verificate a fondo: <L1 + L2 + L3> (L1 CLAUDE.md: N · L2 MORTO: N · L3: N/300)
Livello 3 ripartito da: <ripresa_l3 dello stato, o «inizio (nessuna ripresa salvata)»>
Livello 3 arrivato a: <ultimo documento verificato PER INTERO — il nuovo ripresa_l3>
Non esaminate questa esecuzione: <conteggio> citazioni in <elenco documenti>
Manopole nuove senza citazioni: <conteggio> (anche zero)
Corrette da citazione: N · corrette da un commit: N
```

## Che cosa contiene il JSON della raccolta

| Chiave | Che cos'è | Che ci fai |
|---|---|---|
| `commits` | i commit dell'intervallo (sha, data, soggetto, corpo troncato, file di codice toccati; senza merge, solo codice) | **si legge per primo**: quali regole sono cambiate |
| `sha_verificato` | lo sha risolto di `--a` | va nel rapporto; verifica contro questo, non contro `HEAD` |
| `simboli` | i simboli mossi (definizioni aggiunte/rimosse) | materia prima dei due join |
| `citazioni` | righe di doc che nominano un simbolo mosso | si verificano tutte |
| `citazioni_file` | righe di doc che nominano un **file** toccato | chiave debole, si verificano come le altre |
| `non_documentati` | colonne e rotte nuove che **nessun** documento nomina | candidate funzionalità non documentate |
| `generici` / `generici_file` | i nomi troppo comuni per essere verificati per nome (≥ `SOGLIA_GENERICO`) | si riportano col conteggio, non si aprono |
| `esclusi_dal_corpus` | i percorsi non letti (i rapporti di allineamento) | si dichiara nel rapporto |
| `stato` | `STATO.json` come era prima del giro | `ultimo_sha`, `ultimo_completo`, `ripresa_l3` |

In `--completo` non esiste un intervallo: `commits` e `citazioni_file` sono **vuoti per
costruzione**, dichiarati e non omessi.

## La lista chiusa — ciò che puoi correggere da solo

1. Link relativo a un file inesistente → correggi **se** esiste un solo file con quel
   nome nel repo; altrimenti segnala.
2. Percorso di file nominato che non esiste → stessa regola.
3. Identificatore fra backtick sparito, **quando `git log -M --follow` mostra un
   rename inequivocabile** → sostituisci col nome nuovo. Rename ambiguo o simbolo
   rimosso → segnala.
4. Numero che contraddice una **costante nominata** nel codice, quando la frase cita
   sia la costante sia il valore → allinea il valore.

Non correggere mai: una descrizione di comportamento, un ordine di operazioni, una
motivazione, un numero non ancorato a una costante nominata, un esempio di codice.

### Piani e spec datati non si riscrivono

Un piano o una spec con una data nel nome (`docs/superpowers/plans/AAAA-MM-GG-*.md`,
`docs/superpowers/specs/AAAA-MM-GG-*.md`) è un **verbale**, non documentazione viva:
registra che cosa si era deciso in quel momento. Anche quando il codice ha smentito
quella decisione in modo dimostrabile (firma cambiata, valore di ritorno diverso, ecc.
— cose che altrove rientrerebbero nella lista chiusa) **non si riscrive la frase per
farla combaciare col codice**: la correzione va nel documento vivo (`CLAUDE.md`, le
pagine `REGOLE-IMPORT-*`). Sul verbale si annota il superamento — una riga in coda al
documento che dice cosa è cambiato dopo e dove guardare per lo stato attuale.
Riscriverlo cancellerebbe la traccia di quello che si era deciso in quel momento, che
è il suo unico valore.

## Il rapporto

`docs/superpowers/allineamento/AAAA-MM-GG.md`, con in testa il modo, l'intervallo, i
conteggi (nel caso `--completo`, i conteggi a tre livelli sopra), e **da quanto non si
lancia uno sweep completo** (`ultimo_completo` dello stato). Sezioni: «Regole cambiate (dai commit)» — i commit
dell'intervallo che cambiano un comportamento e, per ciascuno, le pagine che enunciano
quella regola e il loro esito — «Manopole nuove non documentate» (`non_documentati`, anche
a zero: una sezione assente si legge come «non guardato»), «Corretto automaticamente» (con
la regola che l'ha autorizzata), «Da decidere» (citazione, riga di codice, proposta NON
applicata), «Memoria — riferimenti morti», «Non verificabile».

## Limite da dichiarare in ogni rapporto

**La chiave di join è il nome di un simbolo, e la documentazione è prosa: è QUESTO il
limite, non l'intervallo.** Una frase che descrive una regola senza nominare un
identificatore non è raggiungibile da nessun join — né in `diff` né in `--completo`, che
usano la stessa chiave. La misura, sul giro 2026-09-18: delle 14 frasi false poi corrette,
**una sola** era raggiungibile dalle citazioni per simbolo; 13 no. Il join sul percorso
del file ne recupera una parte (prende `REGOLE-IMPORT-05` con 4 righe, dove il simbolo non
arrivava) ma non tocca una pagina scritta per l'utente: `FORECASTING_GUIDE.md`, **zero
righe** su entrambe le chiavi. Per quelle pagine esiste un solo strumento, e sono i
`commits`.

Dichiara quindi in ogni rapporto **quante delle affermazioni corrette venivano da una
citazione e quante da un commit**: è la sola misura che dice se questo strumento sta
funzionando.

Un controllo guidato dal diff trova la **deriva**, non l'errore di nascita: una frase
sbagliata fin dall'inizio non è mai stata «mossa» e nessun diff la segnala — e nemmeno
`--completo`, se quella frase non nomina un simbolo. Misurato:
`API-PREVISIONALE.md:249` puntava `_apply_sp_overrides` a una riga sbagliata **già** a
`1f09819`, e nessun giro l'aveva vista.

Il modo `--completo` è per costruzione **parziale nella verifica** — vedi la
strategia a tre livelli sopra, con il tetto esplicito e l'elenco di ciò che resta
fuori. Il modo `diff` verifica tutte le citazioni che produce, senza campionamento: è
esaustivo **sulle citazioni**, che non è affatto esaustivo **sulle affermazioni** — è
esattamente la frase che questo paragrafo esiste per correggere. Sono limiti
complementari, non intercambiabili: `diff` è completo sul proprio intervallo ma cieco a
ciò che non è cambiato di recente; `--completo` vede tutti i simboli ma non può leggerli
tutti in una sola esecuzione, e nessuno dei due vede la prosa.

**Cieco ai cambi di corpo, non solo all'errore di nascita.** `_REGOLE` aggancia solo
righe di *definizione* aggiunte o rimosse (una `def`, una `class`, un `Column(...)`,
una rotta). Un cambio nel *corpo* di una funzione — la deriva comportamentale più
comune — non produce alcun simbolo, quindi non innesca nessuna verifica: `accept_rescue`
è stato preso in un giro reale solo perché la sua firma è cambiata; la condizione sul
passivo aggiunta dal commit `9ffdb14` sarebbe stata invisibile a firma invariata.
«Trova la deriva, non l'errore di nascita» promette quindi più di quanto il meccanismo
dia: trova la deriva **delle interfacce**, non dei comportamenti.

**Il corpus si auto-inquinava fra un giro e il successivo, e ora non più.** Il rapporto di
uno sweep finisce esso stesso dentro `docs/`, quindi le sue citazioni entravano nel
conteggio del giro dopo: misurato, `create` passava da 38 a 45 citazioni — sopra
`SOGLIA_GENERICO` — solo perché il rapporto che ne parlava era stato aggiunto al corpus, e
sul giro 2026-09-18 erano 49 citazioni fantasma. Dal 2026-09-19
`docs/superpowers/allineamento/` è escluso dal corpus (`ESCLUSI_DAL_CORPUS`, con la sua
prova): il JSON lo dichiara in `esclusi_dal_corpus`. Restano fuori solo i rapporti, non i
verbali di piani e spec — quelli sono corpus a pieno titolo.

**Il corpus comprendeva solo `docs/` + `CLAUDE.md`, e non era bastante** (dal 2026-09-19). Le
istruzioni *agite* dagli agenti — `.claude/agents/`, `.claude/skills/` — erano
fuori da ogni giro, in `diff` come in `--completo`, con entrambe le chiavi: non una verifica
mancata, un file invisibile. Il costo è misurato, non un limite teorico: la regola dell'aliquota
rovesciata da `073927b` viveva in `.claude/agents/collaudatore.md` e nessun giro l'aveva mai vista.
L'allargamento costa **+28 citazioni su 11 366 (0,24%)**, di cui 9 dalla SKILL stessa:
auto-descrizioni (`SOGLIA_GENERICO`, `ESCLUSI_DAL_CORPUS`, `salva_stato`) che restano verificabili
e quindi *utili*, non fantasma. Se un giorno crescessero al punto da distorcere i conteggi dei
generici, la voce da escludere è `.claude/skills/` — e 0,24% è il parametro con cui deciderlo.
Corollario operativo, che prima non aveva motivo di esistere e ora ce l'ha: una riga di questa
pagina che descrive lo strumento **va mossa nello stesso commit** che muove lo strumento. Da quando
la SKILL è dentro il corpus, una riga rimasta indietro non è più una svista di redazione — è
un'affermazione falsa che il giro dopo il join troverà, e troverà come non verificata da nessuno.
