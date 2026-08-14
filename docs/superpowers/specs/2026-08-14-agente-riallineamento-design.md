# Agente di riallineamento documentazione ↔ codice

**Data:** 2026-08-14
**Stato:** Design approvato (in attesa di review della spec scritta)
**Area:** strumenti di progetto. Nessuna modifica a codice applicativo, DB, API o frontend.
**Da conoscere prima di leggere:** il preambolo di `CLAUDE.md` (perché una documentazione
falsa è peggio di una assente), e `docs/superpowers/specs/2026-08-14-claude-md-snellito-design.md`
(lo snellimento in corso, che è il lavoro *una tantum* di cui questo agente è la manutenzione).

## Problema

Dopo mesi di modifiche, documentazione e memoria non descrivono più il codice. Non è
un'impressione: in una sola giornata di lavoro sono emerse **otto** affermazioni false, tutte
scritte in buona fede da chi conosceva il codice **al momento in cui scriveva**.

| Affermazione | Realtà |
|---|---|
| «The OCR button stays visible by design» | il pulsante era stato rimosso poche ore prima |
| «CoGe LLM primario, deterministico *fallback*» (×2) | il codice lancia **entrambi** e sceglie il più completo — e `CLAUDE.md` conteneva anche la versione giusta 200 righe più sotto: si contraddiceva da solo |
| gate di promote «tolleranza €5» | è `check_quadratura(...).semantic_valid`, nessuna soglia in euro |
| «77 documenti unici analizzati» | sono 137 |
| «289.788,03 di fondi su budget_623» | su quel file `net_contra_accounts` non parte nemmeno |
| conseguenza su `base_bank_debt` | enunciata **al contrario** di quello che il codice fa |
| il router non normalizza gli accenti (`docs/import/01 §2`) | li normalizza |

Il danno non è l'imprecisione. `CLAUDE.md` viene caricato **a ogni sessione**: un'affermazione
falsa lì dentro viene creduta e agita. Il preambolo del file lo registra già come guasto
storico — una sezione descriveva plug che il codice aveva smesso di applicare, e mandava chi
la leggeva a cercare un bug dentro un plug inesistente.

La deriva è **continua** e il rilevamento è **occasionale**: viene alla luce solo quando
qualcuno inciampa nella frase sbagliata mentre lavora ad altro. Serve un controllo periodico
che non dipenda dall'inciampo.

## Obiettivi

1. Un disallineamento fra codice e documentazione viene trovato **entro una settimana** dal
   commit che lo ha introdotto, senza che nessuno debba accorgersene.
2. Ciò che una macchina può **provare** viene corretto da sola; ciò che richiede
   interpretazione viene **segnalato con la prova**, e decide una persona.
3. L'agente non introduce mai un'affermazione falsa. In caso di dubbio segnala, non scrive.
4. Il costo di un'esecuzione è proporzionale a **quanto è cambiato**, non alle 35.208 righe di
   documentazione.

## Non obiettivi

- Non riscrive i file di **memoria** (`~/.claude/projects/-home-peter-DEV-budget/memory/`): li
  legge e ne verifica i riferimenti, ma una memoria è il racconto del *perché* di una scelta e
  una correzione meccanica ne perde il senso.
- Non giudica la **qualità** della documentazione (chiarezza, struttura, ridondanza). Verifica
  solo la corrispondenza col codice.
- Non tocca codice, test, DB, API o frontend. Se una correzione richiederebbe di cambiare il
  codice, è una segnalazione, non una correzione.
- Non sostituisce la revisione umana: il rapporto è fatto per essere letto.

## Design

### 1. Le tre fasi

**A — Cosa il codice ha mosso.** Da `git diff <ultimo-sha-verificato>..HEAD` sui file di
codice si estraggono i **simboli mossi**: funzioni, classi, costanti di modulo, colonne del DB,
variabili d'ambiente, rotte API — aggiunti, rinominati o rimossi. Non serve un parser del
linguaggio: `git diff -U0` più un riconoscimento per riga (`def `, `class `,
`export function`, `export const`, `NOME_COSTANTE =`, `Column(`) copre il caso normale. I
falsi positivi costano una verifica in più, i falsi negativi costano un disallineamento non
visto: quindi in dubbio il simbolo si include.

**B — Chi ne parla.** Per ogni simbolo mosso, `git grep -l` sui `.md` del repo più i file di
memoria. **Solo i documenti che lo nominano entrano in verifica.** È questa fase che rende il
costo proporzionale al cambiamento: dodici file di codice toccati diventano tipicamente sei o
sette affermazioni da controllare, non un corpus da rileggere.

**C — Verdetto.** Per ogni affermazione trovata, uno di tre esiti:

| esito | significato | azione |
|---|---|---|
| `OK` | il codice conferma | nessuna |
| `MORTO` | il simbolo nominato non esiste più | correzione automatica **se** rientra nella lista chiusa (§2), altrimenti segnalazione |
| `SMENTITO` | il simbolo esiste ma il codice fa altro | **sempre** segnalazione, mai correzione |

La separazione fra `MORTO` e `SMENTITO` è la stessa linea che divide il dimostrabile
dall'interpretabile: che un nome non esista si prova con un `grep`; che una frase descriva male
un comportamento richiede di leggere il codice e capirlo.

### 2. Cosa può correggere da solo — lista chiusa

Il perimetro è **enumerato e non estendibile a runtime**. Un agente che decide caso per caso
cosa sia «ovvio» è esattamente il rischio che questo design evita.

1. Un **link relativo** a un file che non esiste → si corregge se esiste un solo file con quel
   nome altrove nel repo; altrimenti segnalazione.
2. Un **percorso di file** nominato (`importers/foo.py`) che non esiste → stessa regola.
3. Un **identificatore fra backtick** sparito, **quando `git log --follow`/`-M` mostra un
   rename inequivocabile** → si sostituisce col nome nuovo. Se il rename è ambiguo, o il
   simbolo è stato rimosso e non rinominato → segnalazione.
4. Un **numero che contraddice una costante nominata** nel codice (`RETTIFICHE_MAX`,
   `MAX_RESCUE_PAGES`, `SC_PLUG_REJECT_PCT`, `MAX_COMPANIES_PER_USER`…), quando la frase cita
   la costante **e** il valore → si allinea il valore.

Tutto il resto è segnalazione. In particolare **non** si corregge mai: una descrizione di
comportamento, un ordine di operazioni, una motivazione, un numero non ancorato a una costante
nominata, un esempio di codice.

### 3. La memoria

Trattamento separato e più prudente, perché i file di memoria stanno **fuori dal repo**
(`~/.claude/projects/-home-peter-DEV-budget/memory/`, 19 file): non sono in git, quindi non c'è
un diff da cui partire né uno da rivedere dopo.

L'agente fa **una sola cosa**: per ogni file, funzione, flag o percorso nominato, verifica che
esista ancora nel codice. Ciò che non esiste finisce nel rapporto, in una sezione propria.
**Nessun file di memoria viene modificato.**

Il rapporto distingue due casi, perché richiedono decisioni diverse: un riferimento morto in
una memoria di tipo `reference`/`project` di solito va aggiornato; in una di tipo `feedback` è
spesso il racconto di *perché* si lavora in un certo modo, e il nome vecchio può restare
legittimamente come contesto storico.

### 4. Stato fra un'esecuzione e l'altra

`docs/superpowers/allineamento/STATO.json`, versionato:

```json
{"ultimo_sha": "ea6461c", "data": "2026-08-14", "modo": "diff", "ultimo_completo": null}
```

L'agente lo legge all'avvio e lo aggiorna in coda. Versionato di proposito: così è visibile da
dove riparte, e un `git log` di quel file racconta la storia delle esecuzioni. Alla prima
esecuzione lo sha di partenza si indica a mano.

Uno sweep completo aggiorna `ultimo_sha` a `HEAD` esattamente come il modo `diff` — ha appena
verificato tutto, quindi il punto di ripartenza è lo stesso — e in più scrive
`"ultimo_completo": "AAAA-MM-GG"`. È quel campo che ogni rapporto legge per dire in testa da
quanto non si lancia uno sweep integrale.

### 5. Output

`docs/superpowers/allineamento/AAAA-MM-GG.md`, scritto **sempre**, anche a esito nullo. Un
rapporto che dice «zero disallineamenti su 40 simboli mossi» è un'informazione; un rapporto
assente è ambiguo — non si distingue «non ha trovato nulla» da «non è girato».

Struttura:

```markdown
# Riallineamento 2026-08-21

Modo: diff · Intervallo: ea6461c..a1b2c3d · 12 file di codice, 40 simboli mossi
Documenti entrati in verifica: 6 · Affermazioni controllate: 23

> Un controllo guidato dal diff trova la DERIVA, non l'errore di nascita.
> Per quello serve `/riallinea --completo`, che va lanciato a mano ogni tanto.
> Ultimo sweep completo: <data, oppure «mai»>.

## Corretto automaticamente (N)
| documento:riga | era | è | regola |

## Da decidere (N)
### <documento>:<riga>
**Dice:** «<citazione>»
**Il codice:** `<file>:<riga>` — <cosa fa davvero>
**Proposta:** <riscrittura, NON applicata>

## Memoria — riferimenti morti (N)
| file | riferimento | tipo | nota |

## Non verificabile (N)
```

Due commit distinti: `docs(allineamento): correzioni dimostrabili` (solo le correzioni della
lista chiusa) e `docs(allineamento): rapporto AAAA-MM-GG`. Separati perché il primo deve
restare leggibile in un `git show`.

### 6. Come si lancia

Uno **skill di progetto** in `.claude/skills/riallinea/`, invocabile come `/riallinea` e
`/riallinea --completo`. Lo skill è la cosa vera; la cadenza è solo un innesco, così puoi
lanciarlo a mano dopo una modifica importante senza aspettare il lunedì.

Per la cadenza automatica, una routine schedulata settimanale che invoca lo stesso skill. Va
configurata separatamente e **non** fa parte di questa implementazione: prima si verifica che
lo skill funzioni lanciandolo a mano.

## Rischi noti

1. **Il diff trova la deriva, non l'errore di nascita.** Le tre affermazioni sbagliate trovate
   il 2026-08-14 in `docs/import/` non erano deriva: erano nate sbagliate, e nessun `git diff`
   le avrebbe mai segnalate. Mitigazione: lo sweep completo, e il fatto che ogni rapporto
   ricordi in testa da quanto non lo si lancia.
2. **Una correzione automatica sbagliata è peggio del disallineamento**, perché arriva firmata
   da un commit che dice di aver sistemato le cose. Mitigazione: la lista chiusa del §2, e il
   fatto che ogni correzione automatica compaia nel rapporto con la regola che l'ha
   autorizzata — così è verificabile a campione senza rileggere il diff.
3. **Il riconoscimento dei simboli per riga produce falsi positivi e falsi negativi.** I primi
   costano una verifica inutile, i secondi un disallineamento non visto. La regola è quindi
   asimmetrica: in dubbio si include. Il rapporto dichiara quanti simboli sono stati estratti,
   così un numero implausibile si nota.
4. **Un simbolo che nessun documento nomina non viene mai controllato.** Se una funzione
   cambia comportamento senza cambiare nome, e la documentazione la descrive senza citarla per
   nome, la fase B non la pesca. È un limite strutturale del filtro per nome; lo sweep completo
   lo attenua ma non lo elimina.
