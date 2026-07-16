# 01 — Riconoscimento della route

> Torna all'[indice](REGOLE-IMPORT-00-INDICE.md). Motore: `importers/bilancio_classifier.py`.

Il router è la prima decisione della pipeline e la più conseguente: sbagliare route significa
mandare un bilancio di verifica a un estrattore che cerca lo schema di legge, o viceversa. Il
router **non legge importi**: guarda solo la forma del documento.

## 1. Cosa produce

`classify_bilancio` restituisce sette informazioni (`bilancio_classifier.py:44-52`):

| Campo | Valori | Uso |
|---|---|---|
| `macro_area` | `A` / `B` / `C` / `OTHER` | classificazione concettuale |
| `subcategory` | descrittiva, es. `A2/abbreviato` | diagnostica |
| `route` | `IVCEE` / `TRIAL_BALANCE` / `XBRL_NATIVE` / `UNSUPPORTED` | **la decisione operativa** |
| `gestionale` | es. `TeamSystem` | diagnostica, best-effort |
| `confidence` | `high` / `med` / `low` | **puramente informativa**, nessuno la usa per decidere |
| `signals` | tutti i segnali calcolati | diagnostica |
| `reason` | frase in italiano | mostrata all'utente quando il file è rifiutato |

La finestra di lettura è di **14 pagine** (`:179-182`). Un documento la cui natura si rivela
solo a pagina 15 non è classificabile correttamente: è un limite noto e accettato.

## 2. Come viene letto il testo

Prima di ogni valutazione il testo è ridotto a due viste (`:57-66`):

- **minuscola** — la vista normale;
- **minuscola e senza alcuno spazio** — la vista compattata.

Un marcatore è considerato presente se compare in **almeno una** delle due. Il motivo è
concreto: questi PDF stampano spesso le intestazioni lettera-spaziate
(`S T A T O   P A T R I M O N I A L E`), che nella vista normale non corrispondono a nulla.

**Attenzione agli accenti.** I marcatori sono scritti senza accento (`passivita`,
`disponibilita liquide`), ma il testo **non è normalizzato per gli accenti**. Un documento che
stampa "Passività" con l'accento non attiva quel particolare marcatore; funziona lo stesso solo
perché i marcatori alternativi sono nove. È una fragilità latente, non un design.

## 3. L'albero decisionale

Le regole si valutano **in sequenza e la prima che scatta vince**. L'ordine *è* la gerarchia.

### Regola 0 — estensione (`:170-174`)
File `.xbrl` o `.xml` → `XBRL_NATIVE`. Precede tutto: il testo non viene nemmeno estratto.

### Regola 1 — solo Conto Economico (`:210-215`)
Se il documento ha un CE ma **nessun** marcatore patrimoniale → `UNSUPPORTED`, area `C`.

Questa regola sta prima di tutto il resto per una ragione precisa: un prospetto solo economico
può stampare un "TOTALE A PAREGGIO" che è il pareggio **del conto economico** (cioè il totale
ricavi), non dello stato patrimoniale. Senza questa precedenza quel falso amico lo manderebbe
in route C, che tenterebbe di costruirci uno stato patrimoniale (caso budget_376). Meglio un
rifiuto onesto.

È l'unico punto in cui `macro_area` e `route` divergono dalla mappatura dichiarata: il
documento *è* un prospetto contabile (area C), ma non è importabile.

### Regola 2 — facsimile di deposito XBRL (`:220-222`)
Marcatore `itcc` presente, meno di 5 codici conto, nessun "pareggio" né "bilancio di verifica"
→ **A1 / IVCEE**.

Sta prima del blocco B perché un facsimile di deposito può citare "bilancio riclassificato"
nella Nota Integrativa pur non avendo alcun elenco conti (`:217-219`).

### Blocco B — solo se non c'è "totale a pareggio" (`:226`)
Tutte richiedono `legal_skeleton` (vedi §4). Ordine interno:

| Priorità | Condizione aggiuntiva | Esito |
|---|---|---|
| 1 | marcatore AGO | **B3 / XBRL esteso AGO** |
| 2 | "riclassificat…" | **B1 / sit. riclassificata dettagliata** |
| 3 | ≥ 5 codici-PATH CEE (`B.II.1.a)`, `C.II.5 bis`) | **B1 / codici-PATH CEE** |
| 4 | marcatore "dettaglio …" **e** ≥ 5 codici conto | **B2 / dettaglio sottoconti** |

**Asimmetria da tenere a mente**: il blocco B è disabilitato solo da `pareggio`, non da
`verifica` né da `contrapposte`. Un file con "bilancio di verifica" + scheletro di legge +
marcatore AGO finisce in **B3**, non in C.

### Regole 4/5 — area C (`:241`)
Si entra in area C se c'è almeno uno fra: `pareggio`, `verifica`, `is_sc`, `contrapposte`.

**Deroga "B batte C"** (`:245-248`): se c'è lo scheletro di legge **e** almeno 2 subtotali di
voce, **e** l'unico marcatore C è `is_sc` (cioè niente pareggio, niente verifica, niente
contrapposte) → il file torna in **B / IVCEE**. Serve a proteggere i bilanci IV-CEE che
contengono sottoconti dentro lo schema di legge (budget_313/314) dal finire in un parser
trial-balance che non troverebbe nulla.

Altrimenti → **C / TRIAL_BALANCE**.

### Regola 6 — area A (`:254-271`)
Si entra se: scheletro di legge, **oppure** marcatore `itcc`, **oppure** ("stato patrimoniale"
e "totale attivo"). Sottocategoria per prima corrispondenza: `itcc` → A1; "abbreviat"/"2435-bis"
→ A2/abbreviato; "micro"/"2435-ter" → A2/micro; "riclassificat" → A3; altrimenti A/sintetico.

**Nota**: qui `abbreviat`/`micro` sono cercati nella sola vista **con** spazi. Un'intestazione
lettera-spaziata non corrisponde e il file ricade su "A/sintetico IV CEE".

### Regola 7 — fallback (`:274-275`)
`OTHER` / `UNSUPPORTED`.

## 4. I segnali che contano davvero

`legal_skeleton` è il perno: è semplicemente **"valore della produzione" E "immobilizzazioni"**
entrambi presenti (`:88`). È precondizione di tutto il blocco B e porta d'ingresso all'area A.

| Segnale | Cosa cerca | Perché conta |
|---|---|---|
| `pareggio` | "totale a pareggio" | marcatore C forte: **disabilita l'intero blocco B** |
| `verifica` | "bilancio di verifica" | marcatore C forte, ma non disabilita B |
| `itcc` | `itcc-ci-`, "conforme alla tassonomia", "generato automaticamente" | facsimile di deposito |
| `cee_path` | codici tipo `B.II.1.a)` | ≥5 → B1 |
| `contrapposte` | analisi **geometrica del file** | vedi §6 |
| `is_sc` | firma di situazione contabile | porta d'ingresso a C, ma da sola cede alla deroga B |

### Densità di codici
Sei famiglie di codici conto sono contate separatamente, e la loro somma (`coge_codes`) misura
"quanto questo documento è un elenco di conti":

| Famiglia | Forma | Gestionale tipico |
|---|---|---|
| `depi` | `03/05/005` | Sistemi/DEPI |
| `depi2` | `06/0015` | DEPI 2 parti |
| `teamsystem` | `01/0015/0002` | TeamSystem |
| `eight` | 8 cifre | AGO / contrapposte |
| `dotted` | `10.05.001` | FastReport |
| `mastro_sub` | `123.45678` | BILAGRA |
| `sixdigit_line` | 6 cifre a inizio riga | TeamSystem GIS |

`coge_codes` somma tutte **tranne** `depi2` e **tranne** `cee_path` — i codici-PATH CEE sono
struttura di legge, non un piano dei conti, e contarli come tali manderebbe in C i bilanci
dettagliati di area B.

### Segnali inerti
`sit_contabile` e `dare_avere` sono calcolati ed esposti, ma **nessuna regola li legge**.
`dare_avere` in particolare è strutturalmente inutilizzabile: cerca "dare" come sottostringa,
che compare in qualunque infinito italiano (an**dare**, ricor**dare**), quindi è quasi sempre
vero. Vanno considerati diagnostica storica, non discriminanti.

## 5. Scansione, testo corrotto, testo buono

Sono tre stati distinti e vanno tenuti separati, perché il rimedio è diverso.

**Scansione — il testo non c'è.** Meno di 50 caratteri sulle prime 14 pagine
(`pdf_importer.py:334`). Il router non vedrebbe nulla e rifiuterebbe per la regola 7, quindi a
monte si tenta un recupero, in quest'ordine:

1. **OCR locale deterministico** a coordinate (RapidOCR), gratuito. Se riesce, il file prosegue
   e — nota importante — non viene aggiunto alcun candidato LLM, perché le coordinate sono già
   state lette in modo affidabile.
2. Se fallisce e manca la chiave API → rifiuto esplicito.
3. Altrimenti **OCR via vision** su massimo 20 pagine. Restituisce testo libero, **non dati
   strutturati**: serve solo a far scattare i marcatori di routing. Le cifre vere le rilegge
   poi l'estrattore dalle immagini.
4. Se dopo l'OCR il testo è ancora sotto i 50 caratteri → "immagine illeggibile o documento non
   contabile".

Il testo OCR **sostituisce** il campione e viene dato allo stesso identico router.

**Testo corrotto (garbled) — il testo c'è ma è spazzatura.** La mappa font del PDF è rotta: i
glifi stampati sono giusti, ma l'estrazione spezza gli importi attorno alla virgola decimale
(`3.239 , 12`) e storpia le lettere (`roNDO AMM.TO`). Si misura contando gli importi spezzati:
garbled se sono **oltre il 30%** del totale, con un pavimento assoluto di **10** occorrenze
perché qualche riga strana su un file sano non deve far scattare la regola.

La soglia al 30% è calibrata sul corpus reale: budget_337 segna 60,7% di importi rotti, **ogni
altro file sta sotto il 5%**.

Conseguenza: il testo corrotto **non cambia la route** (il router ha già deciso sul testo
storpiato, e i marcatori grossi sopravvivono). Disattiva invece l'uso dei **totali dichiarati**,
che letti da lì sarebbero spazzatura. Il caso che ha originato la regola: una "perdita 372.733"
mal letta ribaltava una società in utile.

**Testo buono** — tutto il resto.

## 6. Il segnale `contrapposte` dipende dal file, non dal testo

È l'unico segnale che richiede il file su disco. Due vie (`situazione_contabile_parser.py:2685`):

1. **Testuale rapida**: sulle prime 3 pagine, se compare "SEZIONI CONTRAPPOSTE" o "BILANCIO DI
   VERIFICA" o "TOTALE A PAREGGIO" → vero.
2. **Geometrica**: servono *insieme* (a) token divisi in due bande con almeno 4 elementi per
   lato rispetto al gutter, e (b) intestazioni `ATTIV…`/`PASSIV…` **maiuscole** nel 35%
   superiore della pagina, sulla stessa riga e orizzontalmente separate.

Il vincolo maiuscolo è voluto: la prosa della Nota Integrativa usa "attività" minuscolo e
produrrebbe falsi positivi a raffica.

**Trappola nei test**: se il router è chiamato con il solo testo (come fanno i test sui dump),
`contrapposte` è **sempre falso**, e la deroga "B batte C" — che richiede la sua assenza — è
sempre soddisfatta. La stessa classificazione può quindi differire fra test offline e import
reale. In produzione il file è sempre passato, quindi il problema riguarda solo il testing.

## 7. Gestionali

Riconosciuti per prima corrispondenza (`:142-157`): AGO Infinity → TeamSystem (per nome) →
Genya → Cerved → itcc → Sistemi/DEPI (per densità di codici) → TeamSystem (per densità) →
sconosciuto.

Il campo è **best-effort e non influenza mai la route**: è diagnostica. BILAGRA, FastReport,
Dylog, Datev/Koinos sono citati nella tassonomia ma non rilevati qui.

## 8. Sotto-router dell'area C

Determina solo la sottocategoria (la route è già decisa). Prima corrispondenza:

| # | Condizione | Sottocategoria |
|---|---|---|
| 1 | ≥5 codici TeamSystem | `C/verifica TeamSystem` |
| 2 | ≥5 codici a 8 cifre **e nessun** codice DEPI | `C/contrapposte 8-digit` |
| 3 | ≥10 codici dotted | `C/contrapposte dotted` |
| 4 | ≥5 codici BILAGRA | `C/verifica BILAGRA` |
| 5 | segnale `contrapposte` | `C1/sezioni contrapposte fisiche` |
| 6 | ≥10 codici a 6 cifre **oppure** la parola "saldo" | `C2/colonna unica Saldo` |
| 7 | — | `C/verifica (generico)` |

La regola 6 è larga: "saldo" compare in qualunque bilancio di verifica. Essendo penultima il
rischio è contenuto, ma spiega perché `C2/colonna unica Saldo` può finire su file che non sono
affatto a colonna unica.

## 9. Tutte le soglie

| Soglia | Valore |
|---|---|
| Pagine lette | 14 |
| `coge_codes` per il facsimile itcc | < 5 |
| `coge_codes` per B2 | ≥ 5 |
| `cee_path` per B1 | ≥ 5 |
| Subtotali di voce per la deroga "B batte C" | ≥ 2 |
| `depi` / `depi2` per gestionale | ≥ 10 / ≥ 8 |
| `teamsystem` per gestionale e sottocategoria | ≥ 5 |
| `eight` per sottocategoria (con `depi` = 0) | ≥ 5 |
| `dotted` / `mastro_sub` / `sixdigit_line` per sottocategoria | ≥ 10 / ≥ 5 / ≥ 10 |
| Testo minimo "non è scansione" | 50 caratteri |
| Pagine OCR-izzate | 20 |
| Garbled | > 30% degli importi, minimo 10 in assoluto |
