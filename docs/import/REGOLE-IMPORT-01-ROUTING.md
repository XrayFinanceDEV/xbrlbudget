# 01 — Riconoscimento della route

> Torna all'[indice](REGOLE-IMPORT-00-INDICE.md). Motore: `importers/bilancio_classifier.py`.

Il router è la prima decisione della pipeline e la più conseguente: sbagliare route significa
mandare un bilancio di verifica a un estrattore che cerca lo schema di legge, o viceversa. Il
router **non legge importi**: guarda solo la forma del documento.

## 1. Cosa produce

`classify_bilancio` restituisce sette informazioni (`Classification`):

> I rimandi al codice di questa pagina sono per **simbolo**, non per numero di riga: ogni commit sul
> classificatore spostava i numeri, e il 2026-11-20 ne restavano giusti uno su diciassette. I rami di
> `classify_bilancio` si trovano dai loro commenti (`# ----- C: …`, `# ----- A: …`).

| Campo | Valori | Uso |
|---|---|---|
| `macro_area` | `A` / `B` / `C` / `OTHER` | classificazione concettuale |
| `subcategory` | descrittiva, es. `A2/abbreviato` | diagnostica |
| `route` | `IVCEE` / `TRIAL_BALANCE` / `XBRL_NATIVE` / `UNSUPPORTED` | **la decisione operativa** |
| `gestionale` | es. `TeamSystem` | diagnostica, best-effort |
| `confidence` | `high` / `med` / `low` | **puramente informativa**, nessuno la usa per decidere |
| `signals` | tutti i segnali calcolati | diagnostica |
| `reason` | frase in italiano | mostrata all'utente quando il file è rifiutato |

La finestra di lettura è di **14 pagine** (`doc[:14]` in `classify_bilancio`). Un documento la cui natura si rivela
solo a pagina 15 non è classificabile correttamente: è un limite noto e accettato.

A valle, `pdf_importer` non conserva la route come tale: ne deriva il solo booleano
`is_trial_balance = (route == TRIAL_BALANCE)` (`import_pdf_balance_sheet` in `pdf_importer.py`). `macro_area` e
`subcategory` viaggiano però fino all'esito dell'import e ai log, ed è deliberato: un formato
mai visto si presenta come **un'area con una sottocategoria**, non come un'eccezione.

## 2. Come viene letto il testo

Prima di ogni valutazione il testo è ridotto a due viste (`low` e `nos`, in testa a `compute_signals`):

- **minuscola** — la vista normale;
- **minuscola e senza alcuno spazio** — la vista compattata.

Un marcatore è considerato presente se compare in **almeno una** delle due. Il motivo è
concreto: questi PDF stampano spesso le intestazioni lettera-spaziate
(`S T A T O   P A T R I M O N I A L E`), che nella vista normale non corrispondono a nulla.

**Gli accenti sono normalizzati via** (aggiornato 2026-08-14). I marcatori sono scritti senza
accento (`passivita`, `disponibilita liquide`), e **il testo viene deaccentato** prima di
costruire le due viste: decomposizione NFKD e rimozione dei segni combinanti, la stessa regola
del normalizzatore unico `importers/label_semantics.py`. Anche il marcatore cercato passa dalla
stessa riduzione, quindi una grafia accentata trova quella senza accento e viceversa
(`compute_signals` e la sua funzione interna `has`).

Prima di questa correzione il difetto era vivo e non latente: su un documento che stampava
"Passività" nessun marcatore patrimoniale scattava, `sp_present` restava falso e il file veniva
**rifiutato come "solo Conto Economico"** (regola 1) pur avendo lo Stato Patrimoniale.
Test: `tests/test_classifier_accenti.py`.

## 3. L'albero decisionale

Le regole si valutano **in sequenza e la prima che scatta vince**. L'ordine *è* la gerarchia.

### Regola 0 — estensione (commento `# 0) file XBRL nativo`)
File `.xbrl` o `.xml` → `XBRL_NATIVE`. Precede tutto: il testo non viene nemmeno estratto.

### Regola 1 — solo Conto Economico (`# ----- Caso speciale: SOLO conto economico`)
Se il documento ha un CE ma **nessun** marcatore patrimoniale → `UNSUPPORTED`, area `C`.

**Una voce di CE non è un marcatore patrimoniale** (2026-11-19, budget_1667). Alcune voci dell'art.
2425 contengono una parola patrimoniale: B.10 «svalutazioni delle immobilizzazioni», A.4
«incrementi … iscritti nelle immobilizzazioni», D «rettifiche di valore di attività e passività
finanziarie». Prima di cercare i marcatori di `sp_present` si tolgono dal testo
(`_VOCI_CE_CON_PAROLE_PATRIMONIALI`). Senza, un CE riclassificato da solo accendeva `sp_present`,
finiva sulla rotta IV-CEE e veniva rifiutato dopo una decina di minuti di letture del modello
(«Stato Patrimoniale vuoto»), invece che subito come «solo conto economico».

Questa regola sta prima di tutto il resto per una ragione precisa: un prospetto solo economico
può stampare un "TOTALE A PAREGGIO" che è il pareggio **del conto economico** (cioè il totale
ricavi), non dello stato patrimoniale. Senza questa precedenza quel falso amico lo manderebbe
in route C, che tenterebbe di costruirci uno stato patrimoniale (caso budget_376). Meglio un
rifiuto onesto.

È l'unico punto in cui `macro_area` e `route` divergono dalla mappatura dichiarata: il
documento *è* un prospetto contabile (area C), ma non è importabile.

### Regola 1-bis — movimenti senza saldo finale (`# ----- Saldo iniziale e movimenti dare/avere`)
Una testata «saldo iniziale · dare · avere» non seguita da un saldo (`_MOVIMENTI_SENZA_SALDO`) → `OTHER` /
`UNSUPPORTED`, sottocategoria `movimenti senza saldo finale` (decisione del proprietario, 2026-11-21, budget_1776:
«deve essere importato un bilancio, non tabelle a caso»). La stampa elenca i movimenti del periodo; in 1776 la
colonna del saldo finale era scivolata su pagine separate, e il lettore leggeva i movimenti in dare come valori
(un attivo di tre volte quello vero, importato con lo sbilancio sotto la metà). Il saldo **non** si ricostruisce
da iniziale + dare − avere: si rifiuta, e il suggerimento (`movimenti_senza_saldo` in `importers/rifiuti_import.py`)
chiede la stampa col saldo finale accanto a ogni conto. Il saldo finale sulla stessa testata («… dare avere saldo
finale») resta un bilancio di verifica. Sul corpus di 284 PDF la regola scatta solo su 1776.

### Regola 2 — facsimile di deposito XBRL (`# ----- Facsimile XBRL itcc senza elenco conti`)
Marcatore `itcc` presente, meno di 5 codici conto, nessun "pareggio" né "bilancio di verifica"
→ **A1 / IVCEE**.

Sta prima del blocco B perché un facsimile di deposito può citare "bilancio riclassificato"
nella Nota Integrativa pur non avendo alcun elenco conti (commento sullo stesso ramo).

### Blocco B — solo se non c'è "totale a pareggio" (`# ----- B prima di C`)
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

### Regole 4/5 — area C (`# ----- C: bilancio di verifica / situazione contabile`)
Si entra in area C se c'è almeno uno fra: `pareggio`, `verifica`, `is_sc`, `contrapposte`,
`verifica_per_conti`.

**`verifica_per_conti`** (2026-11-19, budget_1776, 1562; 1776 dal 2026-11-21 si ferma alla regola 1-bis): colonne dare/avere (`dare_avere`),
almeno 30 codici conto (`_MIN_CONTI_VERIFICA`), meno di 5 codici-PATH CEE, né «riclassificata» né
«dettaglio». È l'elenco di conti che il rilevatore dei layout (`is_sc`) non riconosce: codici
puntati alfanumerici («10.05.3K»), conti a 8 cifre col partitario sotto. Prima finiva fra gli
schemi di legge, letto dal modello come uno schema (budget_1776 importato con milioni di
sbilancio), o fra i non riconosciuti e rifiutato (budget_1562). Sui 327 PDF del corpus di allora
il segnale cambiava la rotta di tre documenti.

**Deroga "B batte C"**: se c'è lo scheletro di legge **e** almeno 2 subtotali di voce, **e**
mancano i tre marcatori C forti (niente pareggio, niente verifica, niente contrapposte: entra cioè
per `is_sc` o per `verifica_per_conti`) → il file torna in **B / IVCEE**. Serve a proteggere i
bilanci IV-CEE che contengono sottoconti dentro lo schema di legge (budget_313/314) dal finire in
un parser trial-balance che non troverebbe nulla.

Altrimenti → **C / TRIAL_BALANCE**.

### Regola 6 — area A (`# ----- A: scheletro di legge senza conti CoGe`)
Si entra se: scheletro di legge, **oppure** marcatore `itcc`, **oppure** ("stato patrimoniale"
e "totale attivo"). Sottocategoria per prima corrispondenza: `itcc` → A1; "abbreviat"/"2435-bis"
→ A2/abbreviato; "micro"/"2435-ter" → A2/micro; "riclassificat" → A3; altrimenti A/sintetico.

**Nota**: qui `abbreviat`/`micro` sono cercati nella sola vista **con** spazi. Un'intestazione
lettera-spaziata non corrisponde e il file ricade su "A/sintetico IV CEE".

### Regola 6-bis — contabilità semplificata (`# ----- Contabilità semplificata`)
«utile fiscale» e «riepilogo dei ricavi» (o «dei costi»), senza «patrimonio netto» → `OTHER` /
`UNSUPPORTED`, sottocategoria `contabilità semplificata` (2026-11-19, budget_1710). È il
riepilogo fiscale di una semplificata: ricavi, costi e qualche cespite, senza cassa, crediti, debiti
né patrimonio netto. Il rifiuto c'era già, nel fallback; cambia il motivo, che prima diceva «né
elenco conti» (falso: l'elenco c'è) e ora dice che manca lo stato patrimoniale completo.

### Regola 7 — fallback (`# ----- fallback`)
`OTHER` / `UNSUPPORTED`.

## 4. I segnali che contano davvero

`legal_skeleton` è il perno: è semplicemente **"valore della produzione" E "immobilizzazioni"**
entrambi presenti (`s["legal_skeleton"]` in `compute_signals`). È precondizione di tutto il blocco B e porta d'ingresso all'area A.

| Segnale | Cosa cerca | Perché conta |
|---|---|---|
| `pareggio` | "totale a pareggio" | marcatore C forte: **disabilita l'intero blocco B** |
| `verifica` | "bilancio di verifica" | marcatore C forte, ma non disabilita B |
| `itcc` | `itcc-ci-`, "conforme alla tassonomia", "generato automaticamente" | facsimile di deposito |
| `cee_path` | codici tipo `B.II.1.a)` | ≥5 → B1 |
| `contrapposte` | analisi **geometrica del file** | vedi §6 |
| `is_sc` | firma di situazione contabile | porta d'ingresso a C, ma da sola cede alla deroga B |
| `verifica_per_conti` | dare/avere + ≥ 30 codici conto, niente struttura di legge | porta d'ingresso a C, cede alla deroga B come `is_sc` |

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

### Segnali inerti, e uno che non lo è più
`sit_contabile` è calcolato ed esposto, ma **nessuna regola lo legge**: è diagnostica storica.

`dare_avere` era inerte fino al 2026-11-19 e ora lo legge `verifica_per_conti`. Da solo resta un
segnale debole: cerca "dare" come sottostringa, che compare in qualunque infinito italiano
(an**dare**, ricor**dare**), quindi è quasi sempre vero. Per questo `verifica_per_conti` lo vuole
insieme ad almeno 30 codici conto e senza struttura di legge: è la densità di codici a decidere,
non la parola.

## 5. Scansione, testo corrotto, testo buono

Sono tre stati distinti e vanno tenuti separati, perché il rimedio è diverso.

**Scansione — il testo non c'è.** Meno di 50 caratteri sulle prime 14 pagine
(`is_scanned` in `import_pdf_balance_sheet`, `pdf_importer.py`). Per MinerU (passo 0) è scansione anche un PDF in cui **ogni pagina è
un'immagine a pagina intera con sopra il testo di un OCR** (copertura ≥ 90%, al più due font:
NAPS2, Unicarton 31/08/2026): quel testo esiste ma è sbagliato («18.978,72» per 18.378,72, «50 +
874 # 40») e sul percorso di testo lasciava 240 mila di sbilancio; da MinerU lo stesso file esce
verificato. Un PDF nativo con uno sfondo grafico ha i font del gestionale e resta testo
(`_e_una_scansione`, `backend/app/api/v1/imports.py`). Il router non vedrebbe nulla e rifiuterebbe per la regola 7, quindi a
monte si tenta un recupero, in quest'ordine:

0. **MinerU** (dal 2026-10-14, decisione del proprietario), quando `MINERU_OCR_ENABLED`: lo chiama
   l'endpoint `/import/pdf` prima dell'importatore (`_contesto_mineru_per_scansione` in
   `backend/app/api/v1/imports.py`), con la stessa soglia dei 50 caratteri, e passa il contesto
   come fa `/import/pdf-ocr`. Il testo di MinerU diventa campione e `ocr_text`, e i passi sotto non
   girano. Un MinerU che non risponde o non restituisce testo **non blocca**: si prosegue dal passo
   1 e la risposta porta l'avviso `OCR MINERU NON DISPONIBILE` / `OCR MINERU SENZA TESTO`.
   Quando le tabelle di MinerU hanno la forma di una situazione a sezioni contrapposte,
   `mineru_contrapposte.pdf_da_tabelle` ne stampa un PDF sintetico (un PDF di testo con la
   geometria pulita, righe spezzate da MinerU ricomposte) e l'**importatore legge quello**
   come ogni altro PDF di testo (`validation_report.import_snello.fonte_testo = "tabelle_mineru"`,
   metodo `mineru+import_snello`); se l'importatore non adotta, la route C riusa lo stesso PDF.
   Senza quella forma (schemi di legge scansionati, es. ERREGI) l'importatore non si tenta.
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

**Testo cifrato — il testo c'è ma ogni lettera è spostata di una costante.** Un PDF ripassato
da PDF24/Ghostscript può perdere la `ToUnicode` del font Type0/Identity-H: «Unicarton Srl» esce
«8QLFDUWRQ 6UO» (spostamento 29). Non è una scansione (il testo supera i 50 caratteri) e non è
garbled nel senso sopra: nessuna parola di bilancio si riconosce, e il router rifiuta. Prima di
tutto il resto `importers/testo_cifrato.py` misura lo spostamento che fa comparire le parole di
un bilancio, scrive una copia del PDF col testo decodificato e l'import legge quella, dichiarandolo
(avviso + `validation_report.testo_cifrato`).

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

Riconosciuti per prima corrispondenza (`_gestionale`): AGO Infinity → TeamSystem (per nome) →
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
| `coge_codes` per `verifica_per_conti` (`_MIN_CONTI_VERIFICA`) | ≥ 30 |
| `cee_path` sotto il quale vale `verifica_per_conti` | < 5 |
| Subtotali di voce per la deroga "B batte C" | ≥ 2 |
| `depi` / `depi2` per gestionale | ≥ 10 / ≥ 8 |
| `teamsystem` per gestionale e sottocategoria | ≥ 5 |
| `eight` per sottocategoria (con `depi` = 0) | ≥ 5 |
| `dotted` / `mastro_sub` / `sixdigit_line` per sottocategoria | ≥ 10 / ≥ 5 / ≥ 10 |
| Testo minimo "non è scansione" | 50 caratteri |
| Pagine OCR-izzate | 20 |
| Garbled | > 30% degli importi, minimo 10 in assoluto |
