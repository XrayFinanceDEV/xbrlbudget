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

1. **Raccogli.** `python3 scripts/riallinea.py` (aggiungi `--completo` se l'utente
   chiede lo sweep integrale; `--da <sha>` alla prima esecuzione).
2. **Modo `diff` (default): verifica TUTTE le citazioni prodotte.** L'intervallo è
   guidato dal diff, quindi tipicamente poche decine di affermazioni — è pensato per
   essere esaustivo (vedi «Limite da dichiarare» sotto). Se un giorno un diff enorme
   produce troppe citazioni per una verifica completa, applica comunque la strategia
   dello sweep (sotto) e dichiaralo nel rapporto: è un'eccezione, non la norma.
3. **Modo `--completo`: applica la strategia a tre livelli** descritta sotto — non è
   negoziabile caso per caso.
4. **Per ciascuna citazione verificata**, apri il codice e stabilisci:
   - `OK` — il codice conferma. Nessuna azione.
   - `MORTO` — il simbolo nominato non esiste più.
   - `SMENTITO` — esiste, ma il codice fa altro.
5. **Correggi solo dentro la lista chiusa** (sotto). Tutto il resto va in «Da decidere».
6. **Verifica anche la memoria**, ma non modificarla: solo riferimenti morti a rapporto.
7. **Scrivi il rapporto**, sempre, anche a esito nullo.
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

## Strategia per lo sweep completo (`--completo`)

Un `--completo` sul repo reale produce circa 2722 simboli, 5722 citazioni, 50 nomi
generici, in circa 45 secondi di sola raccolta. Nessun modello può leggere il codice
dietro 5722 affermazioni in un'unica esecuzione. Campionare in silenzio sarebbe
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
   condividono lo stesso simbolo, quindi il lavoro è sui ~2722 simboli, non sulle 5722
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

**Con un tetto di 300 su ~5722 citazioni candidate, uno sweep guarda circa il 5% del
corpo al Livello 3.** Servono all'incirca 19 sweep perché il giro dell'alfabeto si
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
Candidate: 5722 · Verificate a fondo: <L1 + L2 + L3> (L1 CLAUDE.md: N · L2 MORTO: N · L3: N/300)
Livello 3 ripartito da: <ripresa_l3 dello stato, o «inizio (nessuna ripresa salvata)»>
Livello 3 arrivato a: <ultimo documento verificato PER INTERO — il nuovo ripresa_l3>
Non esaminate questa esecuzione: <conteggio> citazioni in <elenco documenti>
```

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
lancia uno sweep completo** (`ultimo_completo` dello stato). Sezioni: «Corretto
automaticamente» (con la regola che l'ha autorizzata), «Da decidere» (citazione, riga
di codice, proposta NON applicata), «Memoria — riferimenti morti», «Non verificabile».

## Limite da dichiarare in ogni rapporto

Un controllo guidato dal diff trova la **deriva**, non l'errore di nascita: una frase
sbagliata fin dall'inizio non è mai stata «mossa» e nessun diff la segnala. Solo
`--completo` la prende.

Il modo `--completo` è per costruzione **parziale nella verifica** — vedi la
strategia a tre livelli sopra, con il tetto esplicito e l'elenco di ciò che resta
fuori. Il modo `diff` è invece **esaustivo sul proprio intervallo**: verifica tutte le
citazioni che produce, senza campionamento. Sono limiti complementari, non
intercambiabili: `diff` è completo ma cieco a ciò che non è cambiato di recente;
`--completo` vede tutto ma non può leggerlo tutto in una sola esecuzione.

**Cieco ai cambi di corpo, non solo all'errore di nascita.** `_REGOLE` aggancia solo
righe di *definizione* aggiunte o rimosse (una `def`, una `class`, un `Column(...)`,
una rotta). Un cambio nel *corpo* di una funzione — la deriva comportamentale più
comune — non produce alcun simbolo, quindi non innesca nessuna verifica: `accept_rescue`
è stato preso in un giro reale solo perché la sua firma è cambiata; la condizione sul
passivo aggiunta dal commit `9ffdb14` sarebbe stata invisibile a firma invariata.
«Trova la deriva, non l'errore di nascita» promette quindi più di quanto il meccanismo
dia: trova la deriva **delle interfacce**, non dei comportamenti.

**Il corpus si auto-inquina fra un giro e il successivo.** Il rapporto di uno sweep
finisce esso stesso dentro `docs/`, quindi le sue citazioni entrano nel conteggio del
giro successivo: misurato su questo repo, `create` passa da 38 a 45 citazioni — sopra
`SOGLIA_GENERICO` — solo perché il rapporto che ne parla è stato aggiunto al corpus.
Non c'è (ancora) un'esclusione per i rapporti di riallineamento stessi: se un simbolo
generico compare per la prima volta a causa di un rapporto precedente, dichiaralo.
