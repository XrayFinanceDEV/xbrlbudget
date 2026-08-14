# CLAUDE.md snellito — i dettagli in /docs

**Data:** 2026-08-14
**Stato:** Design approvato (in attesa di review della spec scritta)
**Area:** sola documentazione. Nessuna modifica a codice, test, DB o comportamento.
**Da conoscere prima di leggere:** il preambolo di `CLAUDE.md` stesso, e
`docs/import/REGOLE-IMPORT-00-INDICE.md` §1 (a chi serve quella serie e come si legge).

## Problema

`CLAUDE.md` è **1694 righe**. Due blocchi ne occupano il 68%:

| blocco | righe | quota |
|---|---|---|
| `### PDF Import (Claude LLM)` + 15 sottosezioni (305–965) | 661 | 39% |
| Rettifiche + Pratica + Layout SP/CE + tab (1028–1519) | 491 | 29% |

Ma la lunghezza è il sintomo, non la malattia. `docs/import/` contiene già **3.415 righe**
su 13 file, con un proprio indice e un proprio criterio dichiarato («questa serie descrive
regole e comportamenti, non implementazione»). Gran parte delle 661 righe di import in
`CLAUDE.md` non è materiale da *spostare*: è una **seconda copia**, che può divergere dalla
prima e che nessun meccanismo tiene allineata.

Questo repo è già stato morso da quella divergenza, e il preambolo di `CLAUDE.md` lo
registra: una sezione descriveva plug che il codice aveva smesso di applicare, e mandava chi
la leggeva a cercare un bug dentro un plug inesistente. In questa stessa sessione ne sono
emerse altre tre — la frase «The OCR button stays visible by design» dopo che il pulsante era
stato rimosso, i 289.788,03 di fondi attribuiti a budget_623 su un file dove
`net_contra_accounts` non può nemmeno partire, e una conseguenza su `base_bank_debt`
enunciata al contrario.

Il costo non è estetico. `CLAUDE.md` viene caricato **a ogni sessione**: ogni riga che non
serve compete per l'attenzione con una che serve, e ogni riga falsa viene creduta.

## Obiettivi

1. `CLAUDE.md` scende a **~450 righe** (obiettivo) e comunque **sotto 500** (soglia dura, è
   quella che si verifica), e contiene solo ciò che, se ignorato, produce un danno silenzioso.
2. Nessun fatto vero va perso: per ogni affermazione rimossa esiste una destinazione
   registrata e verificabile.
3. Le affermazioni **false** incontrate durante il lavoro vengono corrette o cancellate, non
   trasportate altrove.
4. Chi apre il repo domani capisce, dal solo `CLAUDE.md`, **dove andare e perché**.

## Non obiettivi

- Non si riscrive `docs/import/`: si verifica e, dove manca qualcosa, si integra.
- Non si tocca il codice, né i test, né il comportamento. È un lavoro di sola documentazione.
- Non si uniforma la lingua. `CLAUDE.md` è oggi misto inglese/italiano; resta com'è, salvo
  le sezioni che vengono riscritte da zero, che seguono la lingua della sezione vicina.
- Non si accorpano i file di `docs/import/`: la loro struttura è già decisa e funziona.

## Design

### 1. Il criterio: resta ciò che evita danni

Una riga resta in `CLAUDE.md` se vale almeno una di queste:

- **è un invariante**: violarlo corrompe un dato e nessun controllo se ne accorge
  (esempio: `sp16` e `sp17` stanno entrambi nel passivo, quindi appiattire la scadenza
  dei debiti lascia il foglio perfettamente quadrato);
- **è una trappola dell'ambiente**: fa fallire il lavoro in modi che non si spiegano da soli
  (`uvicorn --reload` non ricarica i moduli condivisi; i file CRLF misti);
- **è orientamento**: dove stanno le cose, come si avvia, come si chiama l'API.

Va in `/docs` tutto il resto: come funziona un meccanismo, perché è stato fatto così, la
storia di un file di prova, il dettaglio per gestionale.

Il confine si riconosce da una domanda: *«se questa riga non c'è, cosa succede?»* Se la
risposta è «una sessione futura rompe qualcosa senza accorgersene», resta. Se è «una sessione
futura deve aprire un altro file», va via.

### 2. La forma nuova

```
CLAUDE.md  (~450 righe)
  1 Project Overview             orientamento, ~15 righe
  2 Quick Reference              percorsi, comandi, workflow API
  3 Architecture                 moduli condivisi, sys.path, auth, DB
  4 Key Conventions              sp/ce, Decimal, OIC, settori
  5 Invarianti e trappole        ← NUOVA, ~120 righe
  6 Technical Constraints
  7 Development Workflow
  8 Mappa della documentazione   ← NUOVA, ~40 righe
  9 Common Tasks
```

**La sezione 5 è il cuore, e non esiste oggi.** Gli invarianti sono attualmente *sepolti
dentro* la prosa esplicativa: «la colonna è la verità sul lato» vive dentro una descrizione di
94 righe dei parser, «`side` non filtra nulla sui nodi CE» dentro la sezione del leveling
IV-CEE. Spostando la prosa, quegli invarianti uscirebbero con lei. Vanno **sollevati prima**.

Ogni voce è una o due righe: la regola, e cosa si rompe ignorandola. L'elenco iniziale — da
completare durante l'inventario, non prima:

- la **colonna** è la verità sul lato; la **descrizione** decide la voce. Mai il contrario
- **diagnose, never fabricate**: un divario si misura e si dichiara, non si tappa
- debiti senza scadenza → **a breve** (prudenziale). `sp16` e `sp17` stanno entrambi nel
  passivo: il pareggio non vede l'appiattimento, gli indici di liquidità sì
- CE: `situazione_contabile_parser._resolve_ce_field(desc, direction)`, **mai**
  `iv_cee_hierarchy.resolve(side=…)` — su un nodo CE `side` non filtra nulla, un costo può
  risolversi su un ricavo e il risultato si sposta di **2×**
- `period_months`: **NULL o 12** = anno intero. Ogni query «anno intero» accetta entrambi
- mai classificare per **prefisso di codice conto**: i prefissi sono specifici del gestionale
- il **risultato d'esercizio** è la figura di pareggio, non un dato indipendente
- chi chiama le assumptions bulk deve leggere **`forecast_generated`**, non l'HTTP 200
- `uvicorn --reload` **non** ricarica `calculations/` e `importers/`: riavvia
- gli strumenti di edit normalizzano CRLF/LF: `git diff --stat` prima di ogni commit
- Tailwind non genera una classe che i suoi `content` glob non scandiscono
- `useEffect` sull'oggetto restituito da `useRettificheYear`: il hook ne restituisce uno nuovo
  a ogni render, l'effetto si ri-innesca all'infinito. Dipendere dai singoli campi
- `TIER0_FIELDS` / `FALLBACK_FIELDS`: dove la massa non classificata può e non può finire

**La sezione 8 conta quanto la 5.** Un rimando che dice solo «vedi `docs/import/`» non viene
seguito. Ogni riga dice per *quale domanda* si va lì:

```
Stai cambiando come si riconosce un formato?   docs/import/REGOLE-IMPORT-01-ROUTING.md
Un bilancio non quadra e non capisci perché?   docs/import/REGOLE-IMPORT-04-QUADRATURE.md
Devi aggiungere una sotto-voce a SP o CE?      docs/frontend/LAYOUT-SP-CE.md
Il wizard della pratica si comporta male?      docs/frontend/PRATICA-PERCORSO.md
```

### 3. Le destinazioni

| Da `CLAUDE.md` | Righe | Va in |
|---|---|---|
| `### PDF Import` + 15 sottosezioni (305–965) | 661 | `docs/import/` — verifica contro i 13 file esistenti; ciò che manca si **integra lì**, non in un file nuovo |
| `### Rettifiche` (1028–1104) | 77 | `docs/frontend/RETTIFICHE.md` **(nuovo)** |
| `### Il percorso unico "Pratica"` (1105–1301) | 197 | `docs/frontend/PRATICA-PERCORSO.md` **(nuovo)** |
| `### Shared BS/IS Layout` (1302–1411) | 110 | `docs/frontend/LAYOUT-SP-CE.md` **(nuovo)** |
| Projection Tab · Indicatori charts · AI Comments (1412–1445) | 34 | accorpati nei tre file sopra, e in `docs/frontend/INDICATORI-E-STAMPA.md` che già esiste |
| Upload Tracking (1446–1459) | 14 | `docs/deployment/UPLOAD-TRACKING.md` **(nuovo)**; in `CLAUDE.md` restano 3 righe, perché `ADMIN_API_KEY` e il percorso di storage servono per orientarsi |
| Bulk Assumptions · Promote · CE Overrides (1460–1519, 982–998) | 75 | `docs/budget/` — esistono già `TEST_BUDGET_API.md` e `FORECASTING_GUIDE.md` |
| FGPMI · Forecasting Engine · Intra-Year (966–1027) | 62 | **restano**, compressi: 24% IRES, split variabile/fisso 60/40, cassa come plug sono convenzioni, non dettagli |

I tre file nuovi stanno tutti in `docs/frontend/`, accanto ai due che ci sono già.

### 4. L'inventario

Prima di cancellare, ogni affermazione del testo che esce entra in
`docs/superpowers/2026-08-14-inventario-claude-md.md`, con **una** di quattro destinazioni:

| destinazione | significato |
|---|---|
| `RESTA` | è un invariante o una trappola: torna nella sezione 5 di `CLAUDE.md` |
| `GIÀ IN <file> §<n>` | il fatto è già scritto in `/docs`: da `CLAUDE.md` si **cancella** |
| `SPOSTATA IN <file>` | il fatto esiste solo qui: si **trascrive** nella destinazione |
| `OBSOLETA — <perché>` | il codice non fa (più) quello che la riga dice: si cancella |

La quarta voce è la ragione per cui l'inventario vale il tempo che costa. Leggendo ~1.170
righe con questo criterio, **alcune risulteranno false**: tre sono già emerse in questa
sessione. Un inventario le intercetta; uno spostamento le trasporterebbe intatte nella nuova
casa, dove sarebbero più difficili da smentire perché circondate da testo vero.

L'inventario si committa. Chi rivede controlla **quello**, non deve rileggere ~1.170 righe di
diff.

### 5. Verifica

- **Meccanica:** ogni riga `GIÀ IN` / `SPOSTATA IN` trova riscontro nel file di destinazione;
  `git grep` di una frase chiave di quel fatto restituisce **un solo** posto (se ne
  restituisce due, la duplicazione non è stata rimossa — è stata creata).
- **Di forma:** `wc -l CLAUDE.md` ≤ 500; ogni link relativo in `CLAUDE.md` risolve a un file
  esistente; ogni `path/file.py` nominato esiste.
- **Di sostanza:** ogni voce `OBSOLETA` porta la prova nel proprio campo «perché» —
  il comportamento reale, letto nel codice, non un'impressione.

**Quello che questa verifica NON dimostra**, e va detto: che qualcuno *leggerà* il materiale
spostato. L'inventario prova che il testo è sopravvissuto, non che sarà trovato. L'unica
difesa su quel fronte è la qualità dei rimandi della sezione 8, e non è dimostrabile con un
test — è una scommessa sul fatto che un rimando che pone una domanda («un bilancio non quadra
e non capisci perché?») venga seguito più spesso di uno che nomina una cartella.

## Rischi noti

1. **Un invariante non riconosciuto come tale esce dal file sempre caricato.** È il rischio
   principale, e l'inventario lo riduce ma non lo annulla: la classificazione
   `RESTA` vs `SPOSTATA` è un giudizio. Mitigazione: in dubbio, **resta** — una riga di troppo
   nella sezione 5 costa attenzione, una di meno costa un dato corrotto.
2. **`docs/import/` potrebbe contraddire `CLAUDE.md` su un punto.** In quel caso non vince
   nessuno dei due per anzianità: si legge il **codice** e si corregge chi sbaglia,
   registrando la voce come `OBSOLETA`. È la regola che
   `REGOLE-IMPORT-00-INDICE.md` §5 già applica a sé stessa.
3. **Il lavoro è lungo e tutto in un commit sarebbe irrivedibile.** Va spezzato per blocco
   (import, rettifiche, pratica, layout, budget), ciascuno con il proprio pezzo di inventario,
   così ogni commit resta leggibile da solo.
