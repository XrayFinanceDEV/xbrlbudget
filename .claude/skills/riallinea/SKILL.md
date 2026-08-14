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
8. **Committa in due volte**: prima le correzioni, poi il rapporto.
9. **Aggiorna** `STATO.json`.

## Strategia per lo sweep completo (`--completo`)

Un `--completo` sul repo reale produce circa 2722 simboli, 5714 citazioni, 49 nomi
generici, in circa 45 secondi di sola raccolta. Nessun modello può leggere il codice
dietro 5714 affermazioni in un'unica esecuzione. Campionare in silenzio sarebbe
peggio di non verificare affatto: produrrebbe un rapporto che sembra esaustivo e non
lo è — il guasto stesso che questo strumento esiste per prevenire.

La regola è quindi: **verifica a fondo (apri il codice, giudica il comportamento)
solo un sottoinsieme dichiarato, in un ordine di priorità fisso, e dichiara in testa
al rapporto quante affermazioni erano candidate contro quante sono state
effettivamente verificate — mai una percentuale implicita.**

Tre livelli, in quest'ordine, senza eccezioni:

1. **Livello 1 — tutte le citazioni in `CLAUDE.md`.** È il file caricato a ogni
   sessione: un suo errore costa più di qualunque altro. Verifica integrale, sempre,
   qualunque sia il numero (è un solo file, quindi per costruzione limitato).
2. **Livello 2 — tutti i candidati `MORTO`, su tutto il repo.** Prima di leggere una
   sola citazione, fai passare **ogni simbolo** (non ogni citazione — molte citazioni
   condividono lo stesso simbolo, quindi il lavoro è sui ~2722 simboli, non sulle 5714
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
   rimanenti per percorso (ordine alfabetico, deterministico e riproducibile) e
   verifica citazione per citazione finché non raggiungi 300 verifiche di livello 3 in
   questa esecuzione. 300 è scelto per stare comodamente dentro una sessione (in linea
   con le poche decine tipiche di un `diff`, moltiplicate per un fattore che lascia
   margine senza pretendere l'impossibile) — non è calibrato su una misura di tempo,
   è un tetto esplicito che chiunque legga lo skill può cambiare consapevolmente.

**Cosa NON è stato guardato va dichiarato, non taciuto.** Il rapporto elenca i
documenti (percorso + numero di citazioni residue) che restavano fuori dal tetto di
livello 3 quando l'esecuzione si è fermata, così la prossima esecuzione — o una
persona — sa esattamente da dove riprendere. I 49 nomi generici (`generici` nel JSON,
citazioni ≥ `SOGLIA_GENERICO`) non entrano MAI nella verifica per nome: sono per
costruzione troppo comuni per essere affermazioni verificabili individualmente: si
riportano nel rapporto con il conteggio, non si aprono uno per uno.

**In testa a ogni rapporto di uno sweep completo:**
```
Candidate: 5714 · Verificate a fondo: <L1 + L2 + L3> (L1 CLAUDE.md: N · L2 MORTO: N · L3: N/300)
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
