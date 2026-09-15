# Percorso ipotesi budget — giro di rilievi del 14/09: sette passi rifatti

**Data:** 2026-09-15 · **Stato:** decisioni prese dal proprietario il 14/09/2026 sull'artifact «Percorso
Ipotesi Budget» (versione 6, approvata il 15/09: «ora va bene»); prototipo accanto,
`2026-09-15-percorso-ipotesi-rilievi-prototipo.html` (stesso file dell'artifact).
**Origine:** i rilievi del proprietario sul wizard a sette passi già unito (lotti 1, 2, 3A, 3B): «il
risultato non soddisfa e bisogna apporre alcune modifiche per rendere il workflow più ordinato».
**Sostituisce:** i passi 3-6 del percorso della spec `2026-09-08-percorso-ipotesi-budget-design.md`
(§4.3-§4.6) e, nel motore, il modo in cui il debito bancario pregresso, gli altri finanziatori e il
fondo TFR si muovono nel piano. Il passo 7 «Imposte» **non cambia**: il proprietario attende i
dettagli del commercialista.

---

## 1. Il problema

Il wizard unito fa quello che la spec di settembre chiedeva, ma il proprietario, provandolo su
aziende vere, ha trovato sei cose fuori posto:

1. **Le percentuali sulla parte variabile dei costi sono di troppo.** I costi variabili seguono già
   la crescita del fatturato: chiedere all'utente di scriverle è una complicazione, e nella pratica
   si scrive due volte lo stesso numero.
2. **La parte fissa parte da valori medi poco chiari** (il seme dalla tendenza storica) invece che
   dall'inflazione dichiarata al primo passo. Personale e godimento partono da una media invece che
   da 0, che è la parte che l'utente deve ipotizzare.
3. **«Altre voci CE» è un passo inutile fatto così**: una riga sola (oneri diversi) e tre righe in
   sola lettura.
4. **Il passo «Pregresso e nuovo» è troppo stretto** per ciò che deve contenere. Il debito bancario
   esistente va spacchettato dall'utente **finanziamento per finanziamento**, col capitale rimborsato
   **anno per anno** (2027, 2028, 2029 …), non con una durata; gli altri finanziatori (di solito
   finanziamenti soci, rimborsati molto in là) allo stesso modo. Le voci oltre 12 mesi vanno
   scadenziate a mano e possono restare aperte a fine piano.
5. **Manca il punto di pareggio.**
6. **Su PROVA AMBIENTA i debiti verso fornitori del piano sono zero** senza alcun avviso. Diagnosi
   fatta durante il giro: `intra_year_engine._distribute_sp16_operativo` (riga 2148) ripartisce il
   residuo del debito operativo con le proporzioni dell'anno di riferimento, e i 652.885,44 di
   fornitori del parziale sono finiti in «altri debiti» nell'anno promosso. **Decisione 8 del
   proprietario:** è un problema di riclassifica, non del percorso; si segnala soltanto.

Più tre cose emerse discutendo il prototipo: il fondo TFR deve poter essere **scaricato** con
liquidazioni per anno (pensionamenti, licenziamenti), i **nuovi finanziamenti** devono essere più
d'uno e con un nome («Nuovo finanziamento BPM 500.000»: la banca con cui si sta trattando), e la
**cassa in eccesso** deve abbattere le linee autoliquidanti, non i mutui.

## 2. Obiettivo

Lo stesso wizard, con lo stesso motore Python dietro l'anteprima, riordinato in sette passi che
seguono come un analista ragiona sul patrimoniale: **prima ciò che c'è già e come si chiude, poi
ciò che il piano genera**. Le due cose non si mescolano né a schermo né nel calcolo.

| # | Passo | Gruppo | Che cosa cambia |
|---|---|---|---|
| 1 | Scenario | Impostazione | l'inflazione si **salva** e precompila la parte fissa dei costi; nessun seme dalla tendenza |
| 2 | Fatturato | Conto economico | ricavi e altri ricavi partono da 0; la tendenza storica è solo un riferimento |
| 3 | Costi | Conto economico | assorbe «Altre voci CE»; parte variabile senza caselle; parte fissa dall'inflazione; pareggio sul MOL |
| 4 | Capitale circolante | Stato patrimoniale | invariato (giorni medi); avviso fornitori a zero; le voci minori passano al 6 |
| 5 | Patrimoniale pregresso | Stato patrimoniale | **nuovo**: a breve si chiude nel primo anno; oltre 12 mesi a mano; banche per contratto con capitale per anno; fidi separati; altri finanziatori per anno |
| 6 | Patrimoniale piano | Stato patrimoniale | **nuovo**: voci minori, fondo TFR con liquidazioni, investimenti, nuovi finanziamenti multipli, cassa e scoperto |
| 7 | Imposte | Stato patrimoniale | **invariato** |

Criteri di successo:

- uno scenario salvato **prima** di questo lotto si riapre, e alla prima apertura ricalcola ciò che
  si può (decisione 1) dichiarando a schermo che cosa ha ricalcolato e che cosa manca;
- uno scenario salvato prima e **non toccato** (nessun salvataggio) produce lo stesso `ForecastYear`
  di prima al centesimo: il banco di parità (`scripts/parita_motore.py`) dà 0 divergenze su ogni
  profilo esistente, perché ogni intervento sul motore è additivo e spento senza i campi nuovi;
- nessun secondo motore in TypeScript: ogni numero derivato dell'anteprima — pareggio compreso —
  viene dai `details` del motore;
- i messaggi di rifiuto del motore nominano i passi con i nomi nuovi.

## 3. Non obiettivi

- Il passo 7 «Imposte» e il kernel a saldo + acconto: **fermi**. Anche i debiti tributari
  rateizzati restano scadenziati al passo 7, dove sono oggi; il passo 5 li elenca in sola lettura
  con il rimando. Il prototipo li mostrava al passo 5: decisione **presa qui** per non spostarli due
  volte, prima e dopo il commercialista (assunzione da confermare col proprietario).
- Il riutilizzo dei fidi quando la cassa **manca** (tirare di nuovo sulla linea invece di aprire lo
  scoperto): non modellato, non chiesto. Il fabbisogno resta governato dallo scoperto di c/c.
- La riclassifica dell'infrannuale che azzera i fornitori (PROVA AMBIENTA): fuori lotto. Qui solo
  l'avviso.
- Il percorso Startup, gli scenari infrannuali, il Report finale: come prima. Il catalogo delle
  sezioni del report segue la nuova lista dei passi (è lo stesso file JSON), senza cambiare la resa.

## 4. Il percorso, passo per passo

### 4.1 Scenario

Come oggi, con due differenze. **L'inflazione attesa si salva** (`inflation_pct`, stesso valore su
ogni riga di ipotesi, scritta con `updateAll`): «Precompila la crescita della parte fissa di materie
prime e servizi (passo 3), dove puoi correggerla anno per anno». **Il seme dalla tendenza storica
sparisce** (decisione 3): niente `shouldSeedTrend`, niente pulsante «Riparti dalla tendenza». La
tabella della tendenza resta a destra come riferimento in sola lettura.

### 4.2 Fatturato

Come oggi. La nota sotto la tabella dice la tendenza storica dei ricavi («Per riferimento: tendenza
storica 2024-2026 dei ricavi +6,0% annuo. Non viene applicata.») quando ci sono almeno due anni
storici. **Ogni scrittura su `revenue_growth_pct` scrive anche `variable_materials_growth_pct` e
`variable_services_growth_pct` dello stesso anno** (write-through nell'hook): il motore non cambia,
la parte variabile segue i ricavi per costruzione.

### 4.3 Costi

Sottotitolo: «Quanto è fisso, e il resto segue da solo: la parte variabile cresce con i ricavi, la
parte fissa con l'inflazione. A mano restano solo personale, godimento beni di terzi e oneri
diversi.»

- **Quanto è fisso**: i due slider di oggi (invariati), con la legenda «la parte variabile segue il
  fatturato in proporzione: nessuna ipotesi da inserire · la parte fissa parte dall'inflazione,
  correggibile qui sotto».
- **Come si muovono i costi**, tabella in due gruppi:
  - *Parte fissa* («precompilata con l'inflazione del passo 1 · correggi se serve, anche a 0»):
    `fixed_materials_growth_pct`, `fixed_services_growth_pct`. Una casella **azzurra** segue
    l'inflazione (`fixed_materials_growth_auto = true`): cambia se si cambia l'inflazione al passo 1.
    Una casella scritta dall'utente resta sua (`auto = false`); svuotarla la riporta all'inflazione.
    Il pulsante «Riallinea all'inflazione» rimette tutte le caselle in automatico.
  - *Ipotesi manuali* («partono da 0 · variazione % sull'anno precedente»): personale, godimento
    beni di terzi, oneri diversi di gestione (`other_costs_growth_pct`, spostata qui da «Altre voci
    CE»).
  - Le righe «quota fissa anno per anno» e le due righe della parte variabile di oggi **spariscono**
    dalla tabella (la quota per anno resta modificabile solo dallo slider: non è mai stata usata).
- **Calcolate in altri passi** (card piatta): ammortamenti → passo 6, oneri finanziari → passi 5 e 6,
  imposte → passo 7; nota sugli override di CE Prev.
- Anteprime, tutte lette dal motore: **Costi e margine** (ricavi, variabili, fissi con «di cui
  personale», MOL, in % dei ricavi); **Punto di pareggio sul MOL** (decisione 4) con il mini
  grafico del margine di sicurezza, la formula dell'anno 1 e la tabella; **Conto economico fino
  all'ante imposte** (valore della produzione, costi variabili, costi fissi, MOL, ammortamenti,
  risultato operativo, oneri finanziari, ante imposte).

**Il pareggio lo dichiara il motore**, `details['pareggio']` per ogni anno:
`costi_variabili` = parte variabile di materie e servizi; `costi_fissi` = parte fissa di materie e
servizi + personale + godimento + oneri diversi; `costi_fissi_operativi` = costi fissi − altri
ricavi; `margine_contribuzione_pct` = (ricavi − costi variabili) / ricavi × 100;
`fatturato_pareggio` = costi fissi operativi / margine di contribuzione; `margine_sicurezza` =
ricavi − fatturato di pareggio; `margine_sicurezza_pct`. Con ricavi o margine non positivi i tre
ultimi valori sono `null`, mai zero. Con un override di `ce05`/`ce06` la parte fissa/variabile non
è definita (`ce05_fixed` null) e tutto il blocco è `null`: l'anteprima marca l'anno.

### 4.4 Capitale circolante

Come oggi per i giorni medi. **Le voci minori dello SP e i driver di volume (`sp_indexing`) escono
di qui e vanno al passo 6.** In testa, quando `sp16d` dell'anno base è zero e i costi d'acquisto
(`ce05 + ce06 + ce07`) sono positivi, l'avviso (decisione 8): «**Non risultano debiti verso
fornitori nell'anno di partenza. Controllare le riclassifiche dei debiti!** I costi di acquisto del
{anno} sono {importo}, i giorni di pagamento non si possono calcolare. Gli altri debiti a breve
valgono {importo}.» Lo stesso avviso compare al passo 5 sulla riga dei fornitori.

### 4.5 Patrimoniale pregresso

Sottotitolo: «I saldi al 31/12/{anno base} e come si chiudono. Le voci a breve si liquidano nel
primo anno del piano; quelle oltre 12 mesi le scadenzi tu, anno per anno.»

**Regola di base (il proprietario):** crediti e debiti a breve si liquidano nel primo anno del
piano. Chi vuole giocare su crediti poco esigibili o debiti rateizzati li riclassifica oltre 12 mesi
in Rettifiche (o nell'infrannuale) e li scadenzia qui.

Layout: in alto due colonne — a sinistra «A breve · si chiudono nel {anno 1}» e il suggerimento
sulle Rettifiche, a destra l'anteprima **Scadenziamento pregresso** (flussi di cassa) — poi tre
card **a tutta larghezza**: «Altre voci oltre 12 mesi · scadenziamento a mano», «Debiti verso
banche», «Altri finanziatori».

**A breve.** Elenco in sola lettura: crediti verso clienti (incasso), debiti verso fornitori
(pagamento; con l'avviso se zero), debiti tributari a breve («saldo pagato nel {anno 1}»), debiti
previdenziali, altri debiti a breve; più la riga «Debiti verso banche e altri finanziatori: non si
chiudono per regola». Persistenza: il piano `pregresso` di oggi, che il wizard **compone**: `amounts[0]` = massa a
breve dell'anno base + scadenziamento dell'anno 1 della parte oltre; `amounts[i>0]` =
scadenziamento dell'anno i+1 della parte oltre. La ricomposizione all'apertura è l'inversa (massa
a breve letta dal bilancio base). Il piano si scrive **sempre** per crediti commerciali e debiti
verso fornitori (il motore li rigenera dal driver: il pregresso si chiude, il nuovo nasce dai
giorni medi); per previdenziali e altri debiti **solo se c'è massa oltre 12 mesi** da scadenziare,
perché con un piano il motore li estingue e non li rigenera (`_net_of_pregresso`, Ruling 17):
senza massa oltre restano governati dalle regole del passo 6. È un limite del motore, dichiarato
nella nota di destino della riga, non un obiettivo di questo lotto.

**Altre voci oltre 12 mesi.** Tabella: voce · al 31/12 · un importo per anno · «resta». Righe:
crediti oltre 12 mesi (commerciali: `sp07` meno tributari e imposte anticipate), altri debiti oltre
(`sp17g`), fornitori oltre (`sp17d`, solo se > 0), previdenziali oltre (`sp17f`, solo se > 0), e
la riga **in sola lettura** «Debiti tributari rateizzati · si scadenziano al passo 7». Sui crediti
la casella «**non incassati nel piano** (es. infragruppo)» (decisione 6): spegne le caselle e scrive
0 su ogni anno; persistita in `pregresso.crediti_commerciali.non_incassato`. La colonna «resta» ha
tre stati neutri: «chiuso», «resta aperto», «nessun movimento nel piano» (decisione 7: nessun
blocco e nessun avviso); «oltre il saldo» in rosso quando la somma supera la massa (il motore lo
rifiuta, `validate_runoff`).

**Debiti verso banche.** Occhiello: «{totale} € nel bilancio {anno} · di cui {sp16a} € a breve».

1. *Dividi i debiti a breve* (decisione 5): **Fidi e anticipi su fatture** (`bank_lines_amount`,
   con la regola `bank_lines_rule` «Costanti» / «Seguono i ricavi» e il tasso `bank_lines_rate`) e,
   calcolata, la **quota dei mutui entro 12 mesi** = `sp16a` base − fidi («è la rata {anno 1} dei
   finanziamenti qui sotto»). Fidi oltre `sp16a` base: «da correggere», e il motore rifiuta.
2. *Scadenzia i finanziamenti*: tabella finanziamento · residuo al 31/12 · tasso · capitale
   rimborsato per anno · «resta» · elimina. Persistenza: `financing_loans` del primo anno con
   `opening_residual` e la nuova lista `repayments` (un importo per anno di piano) al posto di
   durata/preammortamento/maxirata. «+ Aggiungi finanziamento», «Unisci in un solo finanziamento»
   (somma i residui, tasso medio ponderato, rimborsi sommati per anno): «Per fare in fretta: un
   unico finanziamento con il totale, e scadenzi quello.»
3. Controlli, non bloccanti a schermo ma **bloccanti al salvataggio** dove indicato: «Fidi + residui
   dei finanziamenti = debiti verso banche nel bilancio» (quadra / differenza; **il motore
   rifiuta** una differenza oltre 0,01, come oggi per i soli residui); «Rimborsi {anno 1} dei
   finanziamenti vs quota dei mutui entro 12 mesi» (coerente / «ne scadono N € in più» / «N € oltre
   la quota a breve»; solo informativo).

**Altri finanziatori.** Stessa tabella (finanziatore · residuo · tasso · capitale per anno ·
resta), persistita in `other_lenders` (lista sul primo anno). «Anni vuoti = nessun rimborso nel
piano: il debito resta in bilancio oltre la fine del piano.» Controllo: somma dei residui =
`sp16b + sp17b` dell'anno base (il motore rifiuta oltre 0,01).

**Scadenziamento pregresso** (anteprima, flussi per anno, letti dai `details`): incasso crediti
clienti (`pregresso.crediti_commerciali.closed` dell'anno 1, parte a breve), pagamento fornitori,
saldo debiti tributari (`imposte.saldo_paid`), previdenziali e altri a breve, finanziamenti bancari
esistenti (Σ `debito_bancario.contratti[].rimborso` dei contratti col residuo), fidi e anticipi ·
variazione (`debito_bancario.fidi`), altri finanziatori (`altri_finanziatori.rimborso`), tributari
rateizzati (`imposte.rate_paid`), altri debiti oltre (`pregresso.altri_debiti.closed`, anni ≥ 2),
incasso crediti oltre; totale «Cassa netta del pregresso» e «debito pregresso ancora aperto a fine
anno».

### 4.6 Patrimoniale piano

Sottotitolo: «Ciò che il previsionale genera: voci minori, investimenti, nuova finanza. La cassa
chiude il foglio.»

Colonna sinistra:

- **Voci minori · regola nel piano**: le righe di oggi del passo 4 (`minorFieldsRows`, driver
  `sp_indexing`, «scalano col personale» per i previdenziali), con la nota «il saldo del {anno
  base} si chiude al passo 5, qui si genera quello nuovo». Crediti tributari e imposte anticipate:
  «governati dalle imposte · passo 7».
- **Fondo TFR**: occhiello «{sp15} € al 31/12/{anno}». Riga «Accantonamento annuo · retribuzioni /
  13,5» con l'interruttore «versato a fondi esterni o INPS» (`tfr_accrual_suspended`, invariato).
  Tabella per anno: accantonamento (sola lettura, dai `details['tfr']`), **Liquidazioni**
  (`tfr_payments`, per anno), **Fondo a fine anno** con «oltre il fondo» in rosso quando la
  liquidazione supera fondo + accantonamento (il motore rifiuta).
- **Nuovi investimenti**: come oggi (materiali, immateriali per anno; due tassi di ammortamento).
- **Nuovi finanziamenti**: una card per finanziamento — nome («Nuovo finanziamento BPM»), importo,
  erogato nel (anno di piano), durata, preammortamento, tasso — con il riepilogo «500.000 € · 2027
  · rata 100.000 €/anno dal 2029». Persistenza: `financing_loans` con `amount > 0` sulla riga
  dell'anno di erogazione (il motore già li gestisce, contratto per contratto). «+ Aggiungi
  finanziamento» propone il primo anno di piano libero. I tre campi legacy `financing_amount`,
  `financing_duration_years`, `financing_interest_rate` **non si mostrano più**: la migrazione li
  converte (§6).
- **Cassa e scoperto**: «Concedi lo scoperto di conto corrente» + tetto (come oggi); «Usa la cassa
  in eccesso per ridurre fidi e anticipi» + cassa minima (decisione 9: «i mutui e i nuovi
  finanziamenti seguono solo i loro rimborsi. Lo scoperto si chiude comunque da solo appena la
  cassa torna positiva»). Le cessioni di cespiti restano nell'accordion «Mostra tutte».

Colonna destra, letta dai `details`:

- **Debito, cassa e PFN**: fidi e anticipi (chip «passo 5»), «ridotti con la cassa in eccesso» (se
  sweep), finanziamenti bancari esistenti, **una riga per nuovo finanziamento** col suo nome e il
  chip «nuovo», scoperto generato dal piano, altri finanziatori, fondo TFR · liquidazioni
  nell'anno, immobilizzazioni nette, cassa («a saldo»), posizione finanziaria netta, PFN / MOL.
  Sotto, gli avvisi di oggi (fabbisogno, tetto, scoperto dichiarato, cassa positiva).
- **Altri crediti e debiti del piano** (dalle voci minori): crediti e attività (altri crediti a
  breve `sp06g`, ratei attivi `sp10`, crediti tributari «dalle imposte, passo 7» `sp06e`), totale;
  debiti e fondi (previdenziali `sp16f`, altri debiti a breve `sp16g`, fondi rischi `sp14`, ratei
  passivi `sp18`), totale; «Effetto sulla cassa nell'anno · + libera · − assorbe» = (Δ passivo −
  Δ attivo) sull'anno precedente. Ogni riga porta la regola («costante», «segue i ricavi», …).

### 4.7 Imposte

Invariato. I due rimandi in fondo dicono «Debiti tributari {anno} a breve · saldo pagato nel {anno
1} · passo 5» e tengono la tabella dei rateizzati dov'è.

### 4.8 Scenari già salvati (decisione 1)

Alla prima apertura di uno scenario **senza `inflation_pct`** (la firma di un salvataggio
precedente a questo lotto) la mappa idratata passa da `migraScenario` (modulo puro), che:

**ricalcola** — (a) parte variabile: `variable_*_growth_pct` ← `revenue_growth_pct` dello stesso
anno dove diversi; (b) parte fissa: valori tenuti, `*_growth_auto = false` («sono già un'ipotesi
scritta dall'utente»); (c) «rimborso in N anni» delle banche → un contratto «Debiti verso banche ·
da "rimborso in N anni"» con `opening_residual` = debito bancario base e `repayments` = rate uguali
(debito / N) per gli anni di piano, `existing_debt_repayment_years = null`; contratti già
dettagliati con `duration_years` **restano come sono** (il kernel li accetta ancora); (d) «rimborso
in N anni» degli altri finanziatori → una voce di `other_lenders` allo stesso modo; (e)
`financing_amount > 0` di un anno → una voce di `financing_loans` «Nuovo finanziamento {anno}»,
campi legacy a zero (il tasso legacy resta come `bank_lines_rate` se non c'è altro: è il tasso dello
scoperto); (f) `bank_lines_amount = 0`, `bank_lines_rule = "costante"`; (g) `inflation_pct = 2`;

**segnala da integrare** — passo 1 (inflazione: «il vecchio scenario non la salvava»); passo 5
(dividere `sp16a` base fra fidi e quota mutui; spacchettare o confermare il contratto unico; voci
oltre 12 mesi non scadenziate se `pregresso` è assente).

A schermo: la card a due colonne «ricalcolato / da integrare» sopra il primo passo, con i rimandi
ai passi; nella barra dei passi il badge «da integrare» sui passi 1 e 5 finché non si salva. La
mappa migrata è **sporca** (l'anteprima gira su quella) e si persiste al primo salvataggio; CE Prev.
e SP Prev. mostrano il previsionale vecchio fino ad allora, e la card lo dice.

## 5. Il motore

Tutti gli interventi sono **additivi**: senza i campi nuovi il motore fa esattamente quello di
prima, al centesimo (banco di parità a 0 divergenze). Ogni valore che il motore usa lo dichiara nei
`details` (dichiarato = persistito).

### 5.1 Capitale rimborsato anno per anno sui contratti (`repayments`)

`FinancingLoanInput` accetta `repayments: List[Decimal]` (uno per anno di piano, indice 0 = primo
anno). Con `repayments` presente: `duration_years` facoltativa (ignorata), `grace_years` e
`balloon_pct` devono essere zero, `opening_residual > 0` e `amount = 0` (è il modo di descrivere il
**pregresso**; un prestito nuovo usa durata e preammortamento come oggi). Validazioni: nessun
importo negativo; somma ≤ residuo + 0,01 («la somma dei rimborsi supera il residuo»); lunghezza ≤
orizzonte. Il kernel `new_financing_schedule` legge `repayments[target_year − year]` (zero oltre la
lista: il residuo **resta aperto**, decisione 7), capped al residuo di apertura; interessi = tasso ×
residuo di apertura, come oggi. `contratti_da_riga_finanziamento` porta `repayments` nel contratto.
L'infrannuale non le usa (i suoi contratti restano a durata).

### 5.2 Fidi e anticipi separati (`bank_lines_*`), sweep solo su di loro

Sulla riga del primo anno: `bank_lines_amount` (≥ 0, ≤ `sp16a` base + 0,01, altrimenti «Fidi e
anticipi (X) superano i debiti verso banche a breve dell'anno base (Y)»), `bank_lines_rule`
(`costante` | `ricavi`), `bank_lines_rate` (%). **Regime esplicito** = `bank_lines_amount` non
nullo. In quel regime:

- `assemble_financing` controlla `fidi + Σ opening_residual = base_bank_debt` (±0,01; messaggio
  «Fidi e anticipi (X) più i residui dei finanziamenti (Y) devono coincidere con il debito bancario
  dell'anno base (Z)»); `existing_debt_repayment_years` è ignorato e dichiarato tale;
- i fidi sono uno **stato** per anno: apertura = `bank_lines_amount` (anno 1) o `fidi.residuo`
  dell'anno prima (`prev_details`); con regola `ricavi` si scalano di `ce01_N / ce01_{N−1}`; lo
  sweep (`cash_sweep_enabled`) rimborsa **solo i fidi**, mai i contratti (`_Sweep.breve_disponibile
  = fidi`, `lungo_disponibile = 0`, `attivo` non più spento dai contratti); lo scoperto resta primo
  per costruzione;
- oneri: `fidi_apertura × bank_lines_rate` in `ce15` (`details['oneri_fidi']`), e il tasso dello
  **scoperto** è `bank_lines_rate` (oggi `financing_interest_rate`, che il wizard non scrive più);
- ricomposizione di fine anno (riclassifica, nessun flusso): `sp16a` = fidi residui + Σ rata
  dell'anno **dopo** dei contratti pregressi + quota a breve dei prestiti nuovi + scoperto; `sp17a`
  = il resto. Oggi i contratti pregressi riducono «prima il breve poi il lungo» senza riclassifica:
  la regola nuova vale solo nel regime esplicito;
- `details['debito_bancario']['fidi'] = {apertura, variazione_ricavi, rimborso_sweep, residuo,
  regola}` e i contratti pregressi dichiarano `breve` = rata dell'anno dopo; l'invariante Σ`breve`
  + `scoperto_residuo` = `sp16a`, Σ`lungo` = `sp17a` resta.

### 5.3 Altri finanziatori per anno (`other_lenders`)

Lista sul primo anno: `{name, opening_residual, interest_rate, repayments}` (stesse validazioni di
5.1; somma dei residui = `sp16b + sp17b` base ±0,01, messaggio «La somma dei residui degli altri
finanziatori (X) deve coincidere con i debiti verso altri finanziatori dell'anno base (Y)»).
Ammessa solo nel regime esplicito (5.2), altrimenti «Gli altri finanziatori per anno richiedono la
divisione dei debiti bancari a breve del passo Patrimoniale pregresso». Con la lista:
`altri_finanz_repayment_years` ignorato; ogni anno `sp16b` = Σ rata dell'anno dopo, `sp17b` = Σ
residuo − `sp16b`; interessi = tasso × residuo di apertura in `ce15`;
`details['altri_finanziatori'] = {apertura, rimborso, interessi, breve, lungo, contratti: [{indice,
nome, residuo_iniziale, rimborso, interessi, residuo}], mode: 'contratti' | 'anni' | 'legacy'}`,
dichiarato sempre.

### 5.4 Liquidazioni TFR (`tfr_payments`)

Per anno, `≥ 0`, default 0. `sp15 = prev + accantonamento (0 se sospeso) − tfr_payments`; se la
liquidazione supera fondo + accantonamento il motore rifiuta: «Liquidazioni TFR {anno}: {X}
superano il fondo disponibile ({Y}); correggi al passo «Patrimoniale piano»». L'uscita di cassa
passa dal plug (il passivo scende); il rendiconto la legge già dal movimento del fondo
(`cashflow_detailed.py`, `tfr_paid`). `details['tfr'] = {apertura, accantonamento, liquidazioni,
chiusura, sospeso}`, sempre.

### 5.5 Pareggio e crediti non incassati

`details['pareggio']` (§4.3). `pregresso.crediti_commerciali.non_incassato` è accettato dallo
schema, persistito e riportato in `details['pregresso']['crediti_commerciali']['non_incassato']`;
il motore non lo usa (un piano a zero sulla parte oltre lascia il residuo aperto per costruzione).

### 5.6 I nomi dei passi nei messaggi

`_PREGRESSO_PASSO_DEFAULT = "Patrimoniale pregresso"`; i tributari restano «Imposte». Il client
(`stepForErrorMessage`) manda a `patrimoniale-pregresso` i messaggi che lo nominano e a
`patrimoniale-piano` quelli sullo scoperto, sul tetto e sul TFR.

## 6. Modello dati

Otto colonne nuove su `budget_assumptions`, tutte additive (`migrate_db.py`):

| Colonna | Tipo | Dove vive | Default / legacy |
|---|---|---|---|
| `inflation_pct` | NUMERIC(10,6) NULL | ogni riga (stesso valore) | NULL = scenario precedente |
| `fixed_materials_growth_auto` | BOOLEAN NOT NULL DEFAULT 0 | ogni riga | 0 = valore scritto dall'utente |
| `fixed_services_growth_auto` | BOOLEAN NOT NULL DEFAULT 0 | ogni riga | idem |
| `bank_lines_amount` | NUMERIC(15,2) NULL | prima riga | NULL = regime di oggi |
| `bank_lines_rule` | VARCHAR(16) NULL | prima riga | `costante` |
| `bank_lines_rate` | NUMERIC(10,6) NULL | prima riga | NULL = 0 |
| `other_lenders` | TEXT (JSON) NULL | prima riga | NULL = `altri_finanz_repayment_years` |
| `tfr_payments` | NUMERIC(15,2) NOT NULL DEFAULT 0 | ogni riga | 0 |

Più due campi dentro JSON esistenti: `financing_loans[].repayments` e
`pregresso.crediti_commerciali.non_incassato`. I campi nuovi entrano nel catalogo delle sezioni del
report (`contracts/final_report_assumption_sections.json`, chiavi dei passi rinominate:
`costi` assorbe `altre-voci-ce`; `patrimoniale-pregresso` e `patrimoniale-piano` al posto di
`pregresso-nuovo`; le voci minori passano da `circolante` a `patrimoniale-piano`) — altrimenti la
parità dei campi morti (`tests/test_m1_05b_assumption_sections.py`) li segnala.

## 7. Interfaccia: dove vive ogni decisione

Nessun componente decide nulla (regola del repo: niente jsdom). Moduli puri nuovi in `lib/`, ognuno
con la sua suite: `budget-migrazione.ts` (§4.8), `budget-pareggio.ts` (lettura di
`details['pareggio']` e geometria del mini grafico), `budget-pregresso-oltre.ts` (composizione
piano ⇄ tabella «oltre 12 mesi», stati «resta»), `budget-pregresso-flussi.ts` (anteprima
«Scadenziamento pregresso»), `budget-finanziamenti-pregresso.ts` (righe dei contratti con
`repayments`, «resta», controlli, unione), `budget-piano-step.ts` (TFR, nuovi finanziamenti,
anteprime «Debito, cassa e PFN» e «Altri crediti e debiti del piano»), `budget-fornitori-zero.ts`.
`budget-wizard-steps.ts` cambia chiavi, titoli, sottotitoli e `STEP_FIELDS`; `budget-horizon.ts`
idrata e rimanda i campi nuovi (l'elenco congelato passa da 91 a 99 chiavi).

## 8. Ordine di esecuzione

Due ondate. **A — motore** (Python, ogni task con banco di parità a 0 divergenze sui profili
esistenti e un profilo nuovo per il caso che introduce): schema e migrazione → kernel `repayments`
→ fidi e sweep → altri finanziatori → TFR → pareggio, `non_incassato`, nomi dei passi → profili del
banco. **B — interfaccia**: tipi, idratazione, passi e catalogo → migrazione degli scenari salvati →
passi 1-2 → passo 3 → passo 4 → passo 5 (due task) → passo 6 → passo 7, wizard, documentazione →
verifica di fine lotto (suite, vitest, tsc, banco, collaudo a schermo, `/riallinea`).

## 9. Domande aperte per il proprietario

1. I debiti tributari rateizzati: restano al passo 7 fino ai dettagli del commercialista (§3), o
   passano subito al passo 5 come nel prototipo?
2. Il riutilizzo dei fidi quando la cassa manca (§3): resta fuori?
3. Il tasso dello scoperto passa da `financing_interest_rate` a `bank_lines_rate` (§5.2): va bene
   che sia un tasso solo per fidi e scoperto?
