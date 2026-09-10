# Lotto 3A — motori del previsionale e rendiconto

**Data:** 2026-09-10 · **Stato:** design approvato in chat dal proprietario, spec da rileggere
**Branch:** da staccare dal branch integrato del lotto 2 (`feat/scadenziamento-pregresso`) quando si implementa
**Lotto gemello:** [3B — robustezza del client](2026-09-10-lotto3b-robustezza-client-design.md), in parallelo, su file diversi
**Materiale:** `.superpowers/sdd/2026-09-08-scadenziamento-pregresso/lotto3-ricognizione.md` (nove voci misurate con
sonde su `288a8ca`) e `lotto3-codice.md` (mappa del codice su `f356907`). I numeri di riga lì citati sono indicativi:
il piano riparte dai simboli.

## 1. Perché

Il lotto 2 ha chiuso lo scadenziamento del pregresso, lo scoperto e la quota a breve dei prestiti. Alla chiusura
restavano difetti **che danno numeri sbagliati** su casi raggiungibili dal wizard, più tre contratti deboli (il bulk
che scavalca lo schema, i messaggi in inglese, il centesimo che attraversa la PFN). Ciascuno è misurato nella
ricognizione; qui si fissa il comportamento atteso.

**Fuori da questo lotto:** il tasso distinto per lo scoperto (voce 7 della ricognizione: è una funzione nuova, si fa
solo se il proprietario la chiede); la robustezza del client e lo stato d'errore delle pagine (lotto 3B).

## 2. Decisioni del proprietario (2026-09-10)

1. Lotto 3 diviso in due lotti paralleli: 3A motori e rendiconto, 3B robustezza del client. Tasso dello scoperto escluso.
2. **Bulk:** un input che le rotte tipizzate rifiutano si rifiuta **prima di salvare** (422, messaggio italiano per
   campo, nulla scritto), contiguità degli anni compresa.
3. **Cash sweep:** i finanziamenti con un piano **seguono solo il loro piano**. Sono piani: i contratti della griglia
   (nuovi e esistenti col residuo iniziale) **e** il rimborso aggregato del pregresso con «anni di rimborso»
   (`existing_debt_repayment_years`). Lo sweep rimborsa solo lo scoperto e il debito bancario pregresso **senza alcun
   piano**; la cassa eccedente resta cassa. (Superano due decisioni prese prima nella stessa giornata — «rata invariata,
   durata più corta» e «tasso più alto prima» — che non si applicano più.)
4. **Imposte dell'infrannuale:** al 31/12 resta **solo il saldo dell'anno in corso**; quanto era aperto al mese del
   parziale esce di cassa entro fine anno. Il budget che nasce dal promote scadenzia quel saldo come già fa. (Il
   proprietario usa l'infrannuale sempre come ponte: proiezione a fine anno → promote → anno base del budget.)
5. **Lingua:** i messaggi d'errore del motore e dei servizi del previsionale si scrivono **in italiano alla fonte**, in
   questo lotto.
6. **Dividendi** nel rendiconto: in agenda di questo lotto.

Decisioni precedenti che restano vincolanti: lo scoperto si rimborsa per primo, anche sotto `cash_sweep_min_cash`; un
debito pregresso scadenziato che il piano non rigenera si estingue; lo scoperto esiste solo se concesso
(`overdraft_allowed`).

## 3. Vincoli globali

- Soldi in `Decimal`; percentuali assolute. Un divario si misura e si dichiara, mai si tappa.
- **Dichiarato = persistito:** ogni valore che il motore dichiara in `details` è quello che finisce nel DB, al centesimo.
- **Il banco di parità è lo strumento di misura del lotto** (`scripts/parita_motore.py`, `--controllo-negativo`). Ogni
  task dichiara prima quali celle devono muoversi e in quali scenari; il merge verifica che si muovano solo quelle. Se
  nessun profilo del banco esercita il caso del task, il task aggiunge prima il profilo, in un commit separato che dà 0
  divergenze sul motore invariato.
- Una prova rossa vale solo se fallisce sulle **asserzioni**, non su un simbolo mancante.
- `CLAUDE.md` e `docs/budget/API-PREVISIONALE.md` si aggiornano **nello stesso commit** del comportamento che
  descrivono; ogni `file:riga` scritto si apre e si controlla.
- Terminatori CRLF da preservare: `frontend/types/api.ts`, `backend/app/services/analysis_service.py`,
  `backend/app/calculations/cashflow.py`, `backend/app/calculations/cashflow_detailed.py`,
  `docs/budget/FORECASTING_GUIDE.md`.
- Implementazione del motore e prima revisione del codice del motore su opus; il resto su sonnet.

## 4. Il design, voce per voce

### 4.1 Cash sweep e dichiarazione del debito bancario (voci 5 e 9)

**Oggi.** Lo sweep rimborsa prima `sp16a` e poi `sp17a` sull'aggregato, dopo che pregresso e prestiti nuovi sono già
fusi; gli interessi dei contratti seguono il piano teorico (`new_financing_schedule`, senza stato). Un prestito estinto
dallo sweep continua a maturare interessi (sonda: 7.200,00 in tre anni su debito a zero).

**Comportamento richiesto.**
- Il perimetro dello sweep è: (1) lo scoperto, come oggi; (2) il debito bancario pregresso **senza alcun piano**, cioè
  quando non ci sono contratti con residuo iniziale né `existing_debt_repayment_years`. Prima la quota a breve, poi la
  lunga. Nient'altro.
- I contratti della griglia e il pregresso con «anni di rimborso» non sono mai toccati dallo sweep: capitale e interessi
  sono quelli del loro piano, e quindi coerenti per costruzione.
- La cassa eccedente oltre `cash_sweep_min_cash` resta in `sp09`.
- Nuova chiave `details['debito_bancario']`, dichiarata **ogni anno anche vuota**, con le componenti del debito bancario
  a fine anno:
  ```
  {
    "pregresso_senza_piano":  {"apertura", "rimborso_sweep", "breve", "lungo"} | null,
    "pregresso_piano_anni":   {"apertura", "rimborso", "breve", "lungo"}       | null,
    "contratti": [ {"indice", "anno", "tasso", "erogato", "residuo_iniziale",
                    "rimborso", "interessi", "breve", "lungo"} ],
  }
  ```
  **Invariante:** somma dei `breve` + `scoperto_residuo` = `sp16a`; somma dei `lungo` = `sp17a`, al centesimo, ogni anno.
  Sostituisce `details['prestiti_nuovi_quota_breve']` (che oggi il motore rilegge da `prev_details`: il piano sposta
  quella lettura sulla chiave nuova).

**Celle attese sul banco.** Solo negli scenari con `cash_sweep_enabled` **e** almeno un piano: `sp09`, `sp16a`/`sp16`,
`sp17a`/`sp17` (la cassa resta, il debito segue il piano). **Zero celle di CE**: gli interessi dei contratti seguono
già il piano. In ogni scenario: la chiave `details` nuova appare e `prestiti_nuovi_quota_breve` sparisce. Tutto il
resto a zero.

**Test.** Il caso della sonda (prestito 80.000 / 5 anni / 5%, sweep a soglia zero, azienda molto profittevole):
`sp17a` segue il piano, `ce15` invariato, cassa più alta del rimborso non fatto. Sweep con pregresso senza piano:
rimborsato prima a breve poi a lungo, dopo lo scoperto. Sweep con «anni di rimborso»: il pregresso segue la sua rata.
Invariante di `details['debito_bancario']` su tutta la griglia del banco.

### 4.2 Infrannuale: debito bancario sul codice condiviso (voce 4)

**Oggi.** `intra_year_engine._apply_debt_repayment` fa `min(sp16_bank, repayment)` sul debito bancario non separato:
la prima rata di un prestito nuovo azzera il pregresso a breve (sonda: `sp16a` 12.345,67 → 0,00, `sp17a` 102.345,67).
`_financing_contracts` non divide il contratto misto. La separazione del task 16, la divisione del misto e la quota a
breve del task 17 vivono solo in `forecast_engine.py`.

**Comportamento richiesto.**
- Le tre regole passano in `calculations/projection_common.py` come funzioni pure e condivise: divisione del contratto
  misto in due; separazione pregresso / prestito nuovo **prima** di ogni piano di rimborso; quota a breve del prestito
  nuovo (la rata che scade l'anno dopo). `forecast_engine.py` le usa al posto delle copie locali.
- `intra_year_engine.py` usa le stesse funzioni. Il pregresso bancario dell'infrannuale conserva la propria
  ripartizione; il prestito nuovo si ammortizza per conto suo con la sua quota a breve.
- Il messaggio gemello sui residui iniziali («…must equal source bank debt») segue la regola di §4.6.

**Ordine interno obbligato.** Primo commit: il refactor del motore budget sulle funzioni condivise, che deve dare **0
divergenze** sul banco. Solo dopo, il cambio dell'infrannuale.

**Celle attese.** Budget: nessuna. Infrannuale (fuori dal banco, quindi test dedicati): `sp16a`/`sp17a` dell'anno
proiettato quando ci sono pregresso bancario e un prestito nuovo.

**Test.** Il caso della sonda: pregresso a breve 12.345,67 resta; prestito nuovo 120.000 / 4 anni / 5% erogato
nell'anno: 30.000,00 a breve e 60.000,00 a lungo per la sua parte. Contratto misto = due righe, zero differenze.
Invariante I1 esteso anche nell'infrannuale: la componente pregressa è identica con e senza il prestito nuovo.

### 4.3 Infrannuale: imposte al 31/12 (voce 3)

**Oggi.** `tax_closing_position` somma l'imposta al debito di apertura meno gli acconti e non paga mai nulla (sonda:
1.150.949,04 → 1.171.701,78; un secondo anno 1.251.701,78). Il budget che nasce dal promote eredita il debito gonfiato
e fallisce per fabbisogno.

**Comportamento richiesto** (decisione 4).
- Posizione netta a fine anno = imposta dell'anno − acconti versati nell'anno. Positiva → `sp16e`; negativa → credito
  `sp06e`.
- Acconti: `tax_advances_paid` se **maggiore di zero**, altrimenti il 100% dell'imposta dell'anno di riferimento (stessa
  regola del budget: zero vuol dire «non dichiarato»).
- Cassa: esce quanto serve a passare dalla posizione netta di apertura (al mese del parziale) alla posizione di fine
  anno, tenuto conto dell'imposta che matura nei mesi restanti:
  `uscita = posizione_netta_apertura + imposta_residua_dell'anno − posizione_netta_fine_anno`.
  Ciò che il parziale ha già versato è già nella posizione di apertura e non si ripaga.
- Le rate tributarie oltre l'anno (`sp17e`) restano a lungo, intatte.
- La funzione vive in `projection_common.py` accanto a `tax_settlement_saldo_acconto`, e i due motori condividono la
  regola sugli acconti.

**Test.** Con i numeri della sonda — apertura 1.150.949,04, imposta 120.000,00, acconti 99.247,26 — la posizione di
fine anno è 20.752,74 e l'uscita di cassa 1.250.196,30, **gli stessi numeri del kernel budget**. Acconti non dichiarati
→ 100% dell'imposta dell'anno di riferimento. Posizione negativa → credito. Catena promote → budget: il budget che parte
dalla proiezione non eredita il debito dell'anno prima.

### 4.4 Rendiconto: dividendi e scarto dichiarato

**Oggi.** In `backend/app/calculations/cashflow_detailed.py` `dividends_received` è fisso a zero («already in
profit»). Con proventi da partecipazioni (`ce13_proventi_partecipazioni`) il flusso operativo è sbagliato, e il residuo
dei mezzi di terzi (`debt_net`, calcolato per differenza) assorbe l'errore in silenzio. La variazione **misurata** del
debito finanziario è calcolata ma non esce da nessuna parte.

**Comportamento richiesto.**
- I dividendi incassati entrano nel flusso operativo (OIC 10). Il piano verifica come il primo blocco tratta `ce13`
  (se lo sottrae come elemento non monetario, `dividends_received = +ce13`) e lo fissa con un test.
- Nuovo campo nella riconciliazione (`CashReconciliation`, schema `backend/app/schemas/cashflow_detailed.py`, tipo in
  `frontend/types/api.ts`): lo scarto fra il netto dei mezzi di terzi calcolato per residuo e la variazione misurata
  del debito finanziario. Si **dichiara**, non si corregge.
- Stessa regola in `cashflow.py` (anni storici) se tratta i dividendi allo stesso modo.

**Test.** Scenario con `ce13` > 0: scarto = 0 e flusso operativo che contiene i dividendi. Scenario senza: niente cambia.
La variazione di cassa del rendiconto resta uguale a quella di `sp09` (controllo di sanità, non una prova).

### 4.5 Bulk tipizzato (voci 6 e 8)

**Oggi.** `PUT /assumptions` riceve `request: Any`: niente schema. Tetto di scoperto negativo → errore confuso ogni
anno; `tax_advances_paid` negativo → ignorato in silenzio; tasso 500% → applicato; righe 2027 e 2029 senza 2028 →
ricavi con un passo di crescita e prestito con due. Le ipotesi esistenti si cancellano **prima** di scoprire una riga
malformata.

**Comportamento richiesto** (decisione 2).
- Ogni riga passa lo schema tipizzato delle assumption (lo stesso vincolo di `BudgetAssumptionsCreate`: `ge=0`,
  `le=100`, `Literal` dei driver, …) **prima** di qualunque cancellazione o scrittura.
- Anni **consecutivi, senza lacune**, tutti successivi all'anno base (regola già esistente). Se oggi il servizio accetta
  un primo anno diverso da anno base + 1, il piano lo dichiara e non lo cambia senza chiedere.
- Un errore risponde **422** con un elenco `{forecast_year, campo, messaggio}` in italiano. I messaggi di Pydantic si
  traducono per tipo d'errore (maggiore o uguale, minore o uguale, valore non ammesso, campo mancante, tipo sbagliato);
  un tipo non mappato mostra comunque campo e valore ricevuto.
- **Nulla si salva**: né righe, né cancellazioni, né generazione.
- Il wizard (`BudgetWizard.tsx`) e la schermata Startup (`app/budget/page.tsx`) mostrano l'elenco dei messaggi invece
  del messaggio grezzo di un errore HTTP.
- Il comportamento documentato del bulk su un **previsionale** rifiutato (200, `forecast_generated: false`, ipotesi
  salvate) **non cambia**: vale per un input valido che il motore rifiuta, non per un input invalido.

**Celle attese.** Nessuna: il banco usa input validi.

**Test.** I quattro casi della sonda → 422 col messaggio italiano giusto, DB invariato (ipotesi preesistenti ancora lì).
Lacuna di anni → 422. Input valido → identico a oggi. Vitest sulla funzione che trasforma il 422 nei messaggi a schermo.

### 4.6 Messaggi in italiano alla fonte

**Perimetro:** i messaggi che arrivano all'utente dal motore budget, dal motore infrannuale e dai servizi del
previsionale e del promote. Elenco di partenza in `lotto3-codice.md` §G, più quelli di `validate_assumptions_list`
(«At least one assumption record is required», «Each assumption must have a forecast_year», «Forecast year … must be
greater than base year»). Fuori: `calculation_service.py` (indici, non previsionale).

**Regole.**
- Stesso contenuto informativo, stessi importi formattati come gli altri messaggi italiani del motore (per esempio
  «1.100.700,90»).
- I **codici** diagnostici (`unfunded_financing_requirement`, chiavi dei `details`) **non cambiano**: sono contratto
  per chi li legge.
- Test e documentazione che citano il testo si aggiornano nello stesso commit (`CLAUDE.md` cita
  «Unfunded financing requirement <importo>»).
- Il client smette di tradurre: `saveNotice` (`lib/budget-preview-notice.ts`) perde il riconoscimento dei prefissi
  inglesi. Il prefisso del servizio («Assumptions saved successfully, but forecast generation failed») nasce già
  italiano.

**Celle attese.** Nessuna; sul banco cambia solo il testo dei messaggi d'errore (il banco confronta anche quelli).

### 4.7 Centesimi su voci neutre (voci 1 e 2) — per ultima e da sola

**Oggi.** `_normalize_balance_sheet_cents` posa il residuo di arrotondamento di un gruppo sul campo di default, e se è
protetto sul primo campo libero **a ritroso nell'ordine del gruppo**. Per `sp16`/`sp17` l'ordine mescola conti
finanziari (a banche, b altri finanziatori, c obbligazioni) e operativi (d fornitori, e tributari, f previdenziali, g
altri). `_declared_sp_fields` protegge sempre tutti e quattro gli operativi, quindi il centesimo cade su `sp16c`
(sonda: 19 posature su 20), dentro la PFN. Nessun test lo vede: nessuno dichiara `sp16c`.

**Comportamento richiesto.**
- Per ogni gruppo si definisce l'insieme dei campi **neutri rispetto ai confini di KPI** su cui il residuo può
  posarsi; per i debiti: `g`, `f`, `e`, `d`, in quest'ordine, **mai** `a`, `b`, `c`. Il piano fa lo stesso esame per
  ogni altro gruppo normalizzato (crediti, immobilizzazioni, fondi…) e lo scrive in una tabella nel codice.
- `_declared_sp_fields` protegge solo i campi con un piano **attivo** in quello scenario.
- Se nessun campo neutro è libero, il residuo si posa sul default del gruppo e si **dichiara** in
  `details['residuo_quadratura']` con un'indicazione esplicita che ha toccato un campo dichiarato.
- Il test storico di `tests/test_forecast_dichiarato_vs_persistito.py`, il cui commento descrive un bersaglio superato
  (`sp16d`), si aggiorna.

**Celle attese.** Movimenti di ±0,01 fra campi dello stesso gruppo, **mai** da o verso `sp16a/b/c` e `sp17a/b/c`.
Aggregati, totali e CE a zero.

**Test.** Proprietà su tutta la griglia del banco: la somma dei campi finanziari di `sp16`/`sp17` è identica prima e
dopo la normalizzazione. Il caso della sonda (piano su tributari + previdenziali + altri, rate al mezzo centesimo): mai
`sp16c`.

## 5. Ordine e dipendenze

1. **4.1** sweep e `details['debito_bancario']` — il danno per anno più alto.
2. **4.2** infrannuale debito bancario — il refactor sul codice condiviso tocca le stesse funzioni della quota a breve
   che 4.1 dichiara: va dopo 4.1.
3. **4.3** infrannuale imposte — indipendente, ma sullo stesso motore di 4.2: in serie per non confliggere.
4. **4.4** rendiconto — indipendente dai motori; può andare in parallelo a 4.2-4.3 su un worktree suo.
5. **4.5** bulk tipizzato.
6. **4.6** messaggi italiani — tocca testi in tutti i file dei task precedenti: dopo di loro.
7. **4.7** centesimi — per ultima e da sola.

## 6. Verifica di fine lotto

- pytest intero, vitest, `tsc` puliti; banco con controllo negativo, con le divergenze attese da ogni task sommate e
  nient'altro.
- Collaudo a schermo: sweep con un prestito nuovo (cassa che resta, debito che segue il piano); infrannuale con
  pregresso bancario + prestito nuovo e con debito tributario d'apertura, poi promote → budget che genera; rendiconto
  con dividendi; bulk con input invalido dal wizard (422 leggibile, nulla salvato); un messaggio del motore in italiano.
- `/riallinea` sul diff del lotto.
