# Previsionale — la guida di chi costruisce il budget

Il previsionale parte da un anno base già importato e proietta il conto economico e lo stato
patrimoniale fino a **cinque anni avanti** (la schermata di partenza offre 3 o 5 anni, il campo
ne accetta da 1 a 5). Tutte le ipotesi dello scenario vengono scritte in un solo salvataggio,
che è anche quello che genera il calcolo.

Le tre cose che il motore fa sempre, e che vale avere in mente mentre si compila:

- **La cassa è la voce di pareggio**, e pareggia **solo verso l'alto**: un residuo negativo non
  diventa mai, da solo, debito a breve. È un fabbisogno, e il che cosa succeda di lì lo decide
  il passo 6 con una casella sola.
- **Il modello è per anno, l'interfaccia spesso no.** Quasi ogni campo si compila anno per anno;
  dove l'interfaccia offre una casella unica — lo slider della quota fissa, gli interruttori, la
  scelta del driver di volume — quel valore viene scritto su **tutti** gli anni di piano. Una cosa
  sola vive invece esclusivamente sulla riga del **primo** anno: il piano di scadenziamento del
  pregresso.
- **Un valore forzato a mano vince sempre sulla percentuale di crescita** della stessa riga, e
  sopravvive al salvataggio.

Il percorso a sette passi è la via normale per uno scenario nato da un bilancio; sostituisce la
vecchia scheda «Ipotesi» e non tocca il percorso Startup, che ha il proprio modulo.

## Come è fatto il percorso

| # | Passo | Sottotitolo a schermo | Gruppo |
|---|---|---|---|
| 1 | Scenario | nome, anno base, orizzonte, inflazione | Impostazione |
| 2 | Fatturato | ricavi e altri ricavi | Conto economico |
| 3 | Costi | quota fissa, inflazione, ipotesi manuali | Conto economico |
| 4 | Capitale circolante | giorni medi | Stato patrimoniale |
| 5 | Patrimoniale pregresso | come si chiude ciò che c'è già | Stato patrimoniale |
| 6 | Patrimoniale piano | ciò che il previsionale genera | Stato patrimoniale |
| 7 | Imposte | aliquota e pagamento | Stato patrimoniale |

Ogni passo (tranne il primo) ha a destra un'**anteprima**: è lo stesso motore del calcolo finale,
richiamato a ogni modifica con un breve ritardo, che gira sulle ipotesi tali e quali le stai
vedendo a schermo e **non scrive nulla**. Risponde 200 anche quando il piano si ferma a metà:
quello che conta è l'errore che porta dentro, non lo status. Gli anni che mancano in fondo
all'anteprima non sono anni saltati per un difetto di video, sono gli anni che il motore non ha
raggiunto.

Il tasto principale è «Avanti» sui primi sei passi; all'ultimo diventa **«Salva e calcola
previsionale»**.

---

## Passo 1 · Scenario

**Che cosa inserisci**

- **Nome scenario** — obbligatorio, senza questo il salvataggio non parte (es. «Budget 2026-2028»).
- **Anno base** — di sola lettura, mostra l'anno del bilancio annuale importato.
- **Descrizione** e **Scenario attivo**.
- **Orizzonte di piano**: i pulsanti **3 anni** / **5 anni** o la casella numerica (1-5). La nota
  sotto avvisa che se accorci l'orizzonte, al primo «Salva e calcola previsionale» le ipotesi
  degli anni tolti vengono cancellate insieme ai loro anni di proiezione. Non è una cautela
  superflua: la generazione fa l'upsert dei soli anni che hanno un'ipotesi, quindi passando da 5
  anni a 3 ne resterebbero due fantasma, con i numeri del salvataggio precedente, che analisi,
  rendiconto e report continuano a mostrare.
- **Punto di partenza**: la casella **Inflazione attesa** (%), che è un'ipotesi vera e propria —
  si salva (`inflation_pct`) come tutte le altre, sulla riga di ogni anno di piano. Sotto, una
  tabella di sola lettura con la **tendenza storica** (confronto fra gli ultimi due anni storici)
  di ciascuna voce — Ricavi, Altri ricavi, Materie prime, Servizi, Godimento beni, Personale,
  Oneri diversi — puro riferimento: nessun pulsante la riporta sulle ipotesi. Con un solo anno
  storico la schermata avvisa che il trend non è calcolabile e che verranno usati i valori di
  inflazione.

**Che cosa ne fa il motore**

Nulla a questo passo: l'inflazione è un'ipotesi che si salva con le altre e verrà letta al passo 3,
dove precompila la crescita della parte fissa di materie prime e servizi (correggibile lì, anno
per anno). Non tocca i ricavi, che partono da 0 al passo 2. È anche il passo in cui si decide
l'orizzonte, cioè quante righe di ipotesi il salvataggio porterà con sé.

Non c'è più un seme dalla tendenza storica: il vecchio pulsante «Riparti dalla tendenza», che
sovrascriveva le ipotesi correnti con il trend calcolato, è sparito. Il piano parte sempre da 0 al
passo 2, e la tabella della tendenza resta un riferimento, mai un punto di partenza.

**Che cosa mostra l'anteprima**

Nessuna chiamata di anteprima: la scheda a destra («Bilancio {anno base} · anno base») ricapitola
lo storico già caricato — ricavi, l'incidenza di materie, servizi e personale sui ricavi, il MOL
e i giorni DSO/DIO/DPO. Se sotto il titolo compaiono altre colonne, sono gli **anni storici
precedenti**, non anni di previsione: la schermata lo dice, perché altrove nel wizard quelle
colonne significano l'esatto contrario.

---

## Passo 2 · Fatturato

**Che cosa inserisci**

Una tabella «Variazione % sull'anno precedente» con due righe: **Ricavi delle vendite** e **Altri
ricavi e proventi**, la colonna dell'anno base in euro e una colonna per anno di piano. La nota
sotto la tabella lo ripete: le percentuali si applicano all'anno precedente, non all'anno base.

**Che cosa ne fa il motore**

Sono le due curve che tutto il resto insegue: il circolante scala con i ricavi e i costi
previsionali, override del conto economico compresi. E un override sulla riga (lo si mette in CE
Prev.) spegne la percentuale: si può cambiare questa casella quanto si vuole, il ricavo
previsionale non si muove.

**Che cosa mostra l'anteprima**

«Ricavi proiettati»: il ricavo anno per anno con la variazione percentuale e quella assoluta, gli
altri ricavi, il **valore della produzione** e la **crescita cumulata sull'anno base**, più un
mini-grafico a barre con l'anno base e gli anni proiettati sulla stessa scala. Se il motore si è
fermato a metà, le colonne in cima sono solo gli anni che ha davvero prodotto.

---

## Passo 3 · Costi

**Che cosa inserisci**

- Due slider, **Materie prime** e **Servizi**, con la casella **«% fissa»** accanto: «Al variare
  del fatturato, quale parte resta costante?». Sotto ciascuno, la barra *Fissa · …* / *Variabile ·
  …* sull'importo dell'anno base. La legenda: la parte variabile segue il fatturato in proporzione
  — nessuna ipotesi da inserire —, la parte fissa parte dall'inflazione, correggibile qui sotto.
  Se gli anni hanno quote diverse, la schermata avvisa che muovendo lo slider — o digitando nella
  casella — li allinei tutti a quello che imposti.
- La tabella **«Come si muovono i costi»**, in due gruppi:
  - **Parte fissa** (*Materie prime · fissa*, *Servizi · fissa*): precompilata con l'inflazione
    del passo 1. Una casella **azzurra** segue l'inflazione: cambia se la cambi al passo 1. Una
    casella che hai scritto tu resta tua; svuotarla la riporta automatica. Il pulsante **«Riallinea
    all'inflazione»** rimette tutte le caselle in automatico.
  - **Ipotesi manuali** (*Personale*, *Godimento beni di terzi*, *Oneri diversi di gestione*):
    partono da 0, variazione % sull'anno precedente.
  - La parte variabile non ha più una riga: segue i ricavi del passo 2 per costruzione, senza
    alcuna ipotesi da scrivere. Sono sparite anche la vecchia riga «quota fissa anno per anno» (lo
    slider resta l'unico modo di differenziarla per anno) e le due righe della parte variabile.
- Card **«Calcolate in altri passi»** (automatico): **Ammortamenti** (quote esistenti più i nuovi
  investimenti → passo 6), **Oneri finanziari** (mutui esistenti, nuovi finanziamenti, scoperto →
  passi 5 e 6), **Imposte** (aliquota proposta dall'ultimo consuntivo depositato, o scelta → passo 7); un valore forzato a mano in
  CE Prev. vince comunque su queste regole, finché non lo azzeri dal dialogo Ricalcola.

**Che cosa ne fa il motore**

Le materie prime e i servizi sono spesati in due componenti, fissa e variabile: la quota fissa di
default è il **40%** ed è modificabile su ogni riga di ipotesi. Il motore restituisce per entrambe
le voci i due addendi — la parte fissa e la parte variabile — che diventano **nulli** quando quella
voce è stata forzata in CE Prev. con un importo assoluto: su un importo forzato la scomposizione
non è definita, e l'anteprima marca la cella invece di mostrare un numero che il motore non ha
usato.

**Il pareggio lo dichiara il motore**, `details['pareggio']` per ogni anno: `costi_variabili` =
parte variabile di materie e servizi; `costi_fissi` = parte fissa di materie e servizi + personale
+ godimento + oneri diversi; `costi_fissi_operativi` = costi fissi − altri ricavi, lavori interni e variazioni di rimanenze di prodotti + variazioni di rimanenze di materie e accantonamenti (cosi' il pareggio si calcola sul MOL del CE);
`margine_contribuzione_pct` = (ricavi − costi variabili) / ricavi × 100; `fatturato_pareggio` =
costi fissi operativi / margine di contribuzione; `margine_sicurezza` = ricavi − fatturato di
pareggio; `margine_sicurezza_pct`. Con ricavi o margine non positivi i tre ultimi valori sono
`null`, mai zero; con un override di `ce05`/`ce06` la scomposizione fisso/variabile non è definita
e tutto il blocco è `null`, sull'anno interessato.

**Che cosa mostra l'anteprima**

- **«Costi e margine»**: ricavi, i **costi principali** con i loro *di cui fissi* / *di cui
  variabili*, la riga *di cui personale*, il **MOL**, tutto in percentuale sui ricavi dell'anno.
- **«Punto di pareggio sul MOL»**: un mini-grafico a barre con la tacca del fatturato di pareggio
  e il margine di sicurezza (verde sopra il pareggio, rosso sotto), la formula dell'anno 1 con i
  numeri veri sostituiti dentro il testo, e la tabella (ricavi del piano, margine di
  contribuzione, pareggio sul MOL, margine di sicurezza in % e in €). Un anno non definito (materie
  prime o servizi forzati in CE Prev.) non ha una tacca da disegnare, e lo dichiara.
- **«Conto economico fino all'ante imposte»**: valore della produzione, costi variabili, costi
  fissi, MOL, ammortamenti, risultato operativo, oneri finanziari, ante imposte, in cascata.

---

## Passo 4 · Capitale circolante

**Che cosa inserisci**

- «Giorni medi», tre righe: **Giorni incasso clienti (DSO)**, **Giorni rotazione magazzino
  (DIO)**, **Giorni pagamento fornitori (DPO)**. Il campo è annullabile e il segnaposto mostra
  *auto N*: vuoto significa «usa il valore derivato dall'anno base», mai «zero giorni». La nota
  sotto ricorda che i giorni dell'anno base sono calcolati sui soli crediti e debiti commerciali,
  su 360 giorni, e che crediti e debiti dell'anno base si chiudono nell'anno successivo (passo 5):
  questi giorni generano quelli nuovi.
- Quando i **debiti verso fornitori** dell'anno base (`sp16d`) sono zero e i costi d'acquisto
  (`ce05 + ce06 + ce07`) sono positivi, un avviso in testa: «**Non risultano debiti verso
  fornitori nell'anno di partenza. Controllare le riclassifiche dei debiti!** I costi di acquisto
  del {anno} sono {importo}, i giorni di pagamento non si possono calcolare. Gli altri debiti a
  breve valgono {importo}.» Lo stesso avviso, in forma breve, compare al passo 5 sulla riga dei
  fornitori.
- Le voci minori dello stato patrimoniale e i driver di volume (`sp_indexing`) non stanno più
  qui: sono al passo 6 «Patrimoniale piano».

**Che cosa ne fa il motore**

- I giorni non impostati esplicitamente li **deriva dall'anno base su 360 giorni**, e li deriva
  dai saldi **commerciali**, non dagli aggregati: i crediti tributari e le imposte anticipate
  restano fuori dal DSO perché dipendono dalla posizione fiscale, non dal giro d'affari; il DIO
  ha come denominatore il **ricavo**, non gli acquisti; il DPO guarda i soli **debiti verso
  fornitori**. Il circolante scala poi su ricavi e costi previsionali, override compresi.
- Su un giorno **dedotto** il motore controlla anche che il rapporto non sia degenerato (oltre
  un anno di rotazione, o un denominatore non positivo): in quel caso **riporta il saldo
  dell'anno base invece di scalarlo** e lo dichiara, e questo passo te lo mostra con un avviso.
  Un giorno che hai **scritto tu** non passa da quella guardia: è una scelta, non una derivazione.

**Che cosa mostra l'anteprima**

«Circolante proiettato»: crediti commerciali, rimanenze, debiti verso fornitori, il **capitale
circolante commerciale** con la sua incidenza sui ricavi e l'**assorbimento di cassa
nell'anno**. Nelle celle compaiono i giorni **effettivamente applicati** — i tuoi se li hai
scritti, altrimenti quelli derivati — e sotto la tabella, un avviso per ogni giorno scartato
perché degenere, col saldo che quel giorno riporta davvero.

---

## Passo 5 · Patrimoniale pregresso

«I saldi al 31/12/{anno base} e come si chiudono. Le voci a breve si liquidano nel primo anno del
piano; quelle oltre 12 mesi le scadenzi tu, anno per anno.»

**Regola di base**: crediti e debiti a breve si liquidano nel primo anno del piano — non c'è
un'ipotesi da scrivere. Chi vuole giocare su crediti poco esigibili o debiti rateizzati li
riclassifica oltre 12 mesi in Rettifiche (o nell'infrannuale) e li scadenzia qui.

**Che cosa inserisci**

- **A breve · si chiudono nel {anno 1}** (sola lettura, a sinistra): crediti verso clienti
  (incasso), debiti verso fornitori (pagamento; con l'avviso se l'anno base non ne ha), debiti
  tributari a breve («saldo pagato nel {anno 1}»), debiti previdenziali, altri debiti a breve; più
  la riga «Debiti verso banche e altri finanziatori: non si chiudono per regola — fidi e anticipi
  si rinnovano, i finanziamenti li scadenzi nella card sotto».
- **Altre voci oltre 12 mesi · scadenziamento a mano** (tutta larghezza): tabella *voce · al
  31/12 · un importo per anno · resta*. Righe: **crediti oltre 12 mesi** (commerciali, al netto di
  tributari e imposte anticipate), **altri debiti oltre**, **fornitori oltre** (solo se > 0),
  **previdenziali oltre** (solo se > 0), **debiti tributari rateizzati** — al 31/12 il rateizzato
  del piano tributario (non l'intera massa: il saldo a breve non entra in questa riga, si versa
  per intero nel primo anno di piano), un importo per anno, con la nota «Rate della
  rateizzazione: escono di cassa nell'anno. Il saldo a breve si paga nel {anno 1}.». Sui crediti,
  la casella **«non incassati nel piano (es. infragruppo)»**: spegne le caselle e scrive 0 su ogni
  anno. La colonna «resta» ha tre stati neutri — «chiuso», «resta aperto», «nessun movimento nel
  piano» — e «oltre il saldo» in rosso quando la somma supera la massa (il motore lo rifiuta).
- **Debiti verso banche** (tutta larghezza): occhiello «{totale} € nel bilancio {anno} · di cui
  {sp16a} € a breve».
  1. *Dividi i debiti a breve*: **Fidi e anticipi su fatture** (importo, con la regola
     **Costanti** / **Seguono i ricavi** e un tasso) e, calcolata, la **quota dei mutui entro 12
     mesi** = debiti bancari a breve dell'anno base − fidi. Fidi oltre quel totale: «da
     correggere», il motore rifiuta. Una nota: «Se la cassa va in negativo il piano riutilizza i
     fidi; oltre questo importo compare un avviso.»
  2. *Scadenzia i finanziamenti*: tabella *finanziamento · residuo al 31/12 · tasso · capitale
     rimborsato per anno · resta · elimina*. «+ Aggiungi finanziamento», «Unisci in un solo
     finanziamento» (somma i residui, tasso medio ponderato, rimborsi sommati per anno).
  3. Controlli: «Fidi + residui dei finanziamenti = debiti verso banche nel bilancio» (quadra /
     differenza — bloccante al salvataggio, oltre 0,01); «Rimborsi {anno 1} dei finanziamenti vs
     quota dei mutui entro 12 mesi» (coerente / differenza — solo informativo).
- **Altri finanziatori** (tutta larghezza): stessa tabella (finanziatore · residuo · tasso ·
  capitale per anno · resta). «Anni vuoti = nessun rimborso nel piano: il debito resta in bilancio
  oltre la fine del piano.» Controllo: la somma dei residui deve coincidere con i debiti verso
  altri finanziatori dell'anno base (bloccante, oltre 0,01).

**Che cosa ne fa il motore**

- **Il breve si liquida nel primo anno di piano, per regola** — il saldo di apertura deve
  coincidere col bilancio base entro un centesimo, e la somma di quanto scadenzi oltre 12 mesi
  più l'inesigibile non può superare la massa: superarla è un errore, non un troncamento.
- **Senza un piano, ogni saldo segue la formula di sempre** al centesimo. **Con un piano, il lato
  oltre l'esercizio è interamente pregresso**: la percentuale di crescita di quella voce smette di
  applicarsi finché il piano non la esaurisce. Il piano si scrive **sempre** per crediti
  commerciali e debiti verso fornitori (il motore li rigenera dal driver del passo 4: il pregresso
  si chiude, il nuovo nasce dai giorni medi); per previdenziali e altri debiti **solo se c'è massa
  oltre 12 mesi**, perché con un piano il motore li estingue e non li rigenera — senza massa oltre
  restano governati dalle regole del passo 6.
- **Debiti tributari rateizzati**: il piano nasce solo se il debito oltre 12 mesi dell'anno base
  (`sp17e`) è positivo — apertura = debito tributario totale, saldo = la parte a breve (si versa
  per intero nel primo anno), rateizzato = la parte oltre. Solo il **rateizzato** entra nello
  scadenziamento, mai il saldo. Senza debito oltre, nessun piano: il tributario si paga tutto come
  saldo nel primo anno, come sempre.
- **Fidi e anticipi** sono un regime a parte dai mutui: quando li dividi, il cash sweep del passo
  6 (se acceso) rimborsa prima loro, e solo dopo il debito bancario pregresso senza piano. **Se la
  cassa va in negativo, il piano riutilizza i fidi invece di fermarsi o aprire uno scoperto**: il
  fabbisogno tira sul residuo dei fidi, fino a concorrenza di quanto serve; oltre l'importo di
  partenza il motore calcola comunque il piano e **dichiara un avviso**, in euro, con l'anno e
  l'eccedenza. Un override sullo stesso totale (`sp16a`/`sp16`) con un fabbisogno aperto si
  rifiuta: il totale forzato non lascia posto al tiraggio.
- I **finanziamenti pregressi** scadenziano il capitale rimborsato **anno per anno**: la quota che
  cade l'anno dopo sta a breve nel passivo, il resto oltre. **Gli altri finanziatori** seguono lo
  stesso schema, per proprio conto.

**Che cosa mostra l'anteprima**

**«Scadenziamento pregresso · flussi di cassa»**, per anno, in due gruppi:
- **A breve**: incasso crediti verso clienti, pagamento fornitori, saldo debiti tributari,
  debiti previdenziali e altri a breve.
- **Finanziamenti e oltre 12 mesi**: finanziamenti bancari esistenti, fidi e anticipi ·
  variazione, altri finanziatori, tributari rateizzati, altri debiti oltre 12 mesi, incasso
  crediti oltre 12 mesi.

In fondo, **«Cassa netta del pregresso»** (la somma di tutte le righe sopra) e **«debito pregresso
ancora aperto a fine anno»** — quest'ultima non è un flusso, è ciò che di pregresso resta a
bilancio: i nuovi finanziamenti hanno il loro spazio al passo 6.

---

## Passo 6 · Patrimoniale piano

«Ciò che il previsionale genera: voci minori, investimenti, nuova finanza. La cassa chiude il
foglio.»

**Che cosa inserisci**

- **Voci minori · regola nel piano**: una riga per ciascuna delle quindici voci minori
  dell'attivo e del passivo (crediti oltre 12 mesi, crediti verso soci, immobilizzazioni
  finanziarie, crediti tributari, imposte anticipate entro e oltre, attività finanziarie, ratei e
  risconti attivi, fondi per rischi e oneri, debiti previdenziali entro e oltre, debiti fornitori
  oltre, altri debiti entro e oltre, ratei e risconti passivi), con l'importo base e, dove il
  motore può agganciarla, un selettore: **Costante (variazione %)** oppure **Cresce con i ricavi /
  gli acquisti (materie e servizi) / il costo del personale**. Nota: «il saldo del {anno base} si
  chiude al passo 5, qui si genera quello nuovo»; crediti tributari e imposte anticipate portano
  invece «governati dalle imposte · passo 7». **«Variazione % per anno»** (accordion): le stesse
  voci come percentuali, anno per anno. Interruttore **Debiti previdenziali scalano col costo del
  personale**.
- **Fondo TFR**: occhiello «{sp15} € al 31/12/{anno}». Interruttore «Accantonamento annuo ·
  retribuzioni / 13,5 — versato a fondi esterni o INPS» (`tfr_accrual_suspended`). Tabella per
  anno: **Accantonamento** (sola lettura), **Liquidazioni** (`tfr_payments`, un importo per anno:
  pensionamenti, dimissioni, licenziamenti — escono di cassa nell'anno e riducono il fondo),
  **Fondo a fine anno** con «oltre il fondo» in rosso quando la liquidazione supera fondo +
  accantonamento (il motore rifiuta).
- **Nuovi investimenti**: come oggi, materiali e immateriali, per anno.
- **Nuovi finanziamenti**: una card per finanziamento — **Nome** (es. «Nuovo finanziamento BPM»),
  **Importo €**, **Erogato nel** (l'anno di piano), **Durata**, **Preammortamento**, **Tasso %** —
  con il riepilogo «500.000 € · 2027 · rata 100.000 €/anno dal 2029». «+ Aggiungi finanziamento»
  propone il primo anno di piano libero. I tre campi legacy (importo unico, durata, tasso di un
  solo finanziamento) non si mostrano più: la migrazione degli scenari salvati li converte (vedi
  sotto).
- **Cassa e scoperto**: se hai diviso i debiti bancari a breve al passo 5 (fidi e anticipi
  separati), qui non ci sono più la casella «Concedi lo scoperto» né il tetto — al loro posto la
  nota «Se la cassa va in negativo il piano riutilizza i fidi; oltre l'importo di partenza compare
  un avviso.». Senza quella divisione, resta l'interruttore **Concedi lo scoperto: il fabbisogno
  scoperto diventa debito bancario a breve** (spento di default) e, acceso, il **Tetto dello
  scoperto €** (vuoto = senza tetto). Resta sempre **Usa la cassa in eccesso per ridurre fidi e
  anticipi** più la **cassa minima** del cash sweep: i mutui e i nuovi finanziamenti seguono solo
  i loro rimborsi, e lo scoperto si chiude da solo appena la cassa torna positiva. L'accordion
  **«Mostra tutte»** porta i due tassi di ammortamento dei nuovi investimenti e le **cessioni**
  (valore contabile netto e corrispettivo).

**Che cosa ne fa il motore**

- Una voce minore lasciata su «Costante (variazione %)» senza percentuale resta **ferma** per
  tutto il piano. L'aggancio a un driver ha la forma *stock dell'anno base × fattore del driver*:
  non accumula deriva come un *prev × (1 + %)* composto per cinque anni. Alcune voci hanno già un
  padrone e il selettore non le offre: i crediti tributari e le imposte anticipate seguono la
  posizione fiscale, i crediti oltre l'esercizio seguono il piano del passo 5. Dove un piano del
  passo 5 già governa una voce (fornitori, previdenziali, altri debiti oltre), l'interfaccia toglie
  il driver invece di proporlo e poi ignorarlo.
- **TFR**: il fondo a fine anno è il precedente più l'accantonamento (zero se sospeso) meno le
  liquidazioni; oltre fondo + accantonamento il motore rifiuta, con un messaggio che nomina questo
  passo. L'uscita di cassa passa dal plug, il rendiconto la legge dal movimento del fondo.
- **Nuovi finanziamenti**: ciascuno ha il proprio calendario — quote capitale costanti dopo
  l'eventuale preammortamento, interessi sul residuo di apertura. La quota che cade l'anno dopo sta
  a breve, il resto oltre.
- **La cassa è il pareggio e pareggia solo verso l'alto.** Se hai diviso fidi e mutui al passo 5,
  un fabbisogno tira sui fidi (descritto lì) e il piano non si ferma mai per questo. Senza quella
  divisione vale la regola di sempre: spento, il motore si ferma sul primo anno che non si
  finanzia; acceso, il fabbisogno diventa uno scoperto generato dal piano, con gli interessi in
  conto economico sullo scoperto di apertura, al tasso del nuovo finanziamento.
- **Il cash sweep** usa la cassa in eccesso per rimborsare il debito che non ha un piano — con
  fidi separati, prima loro; altrimenti lo scoperto — e poi il debito bancario pregresso senza
  anni di rimborso e senza contratti, a breve e poi a lungo. I finanziamenti con un piano seguono
  solo il proprio calendario, e la cassa in più resta in cassa. La cassa libera rimborsa comunque
  per prima il debito senza piano, anche sotto la cassa minima impostata; il motore dichiara
  quanta cassa è finita sotto quel minimo.

**Che cosa mostra l'anteprima**

- **«Debito, cassa e PFN»**: fidi e anticipi (con «ridotti con la cassa in eccesso» sotto, se lo
  sweep li ha rimborsati), finanziamenti bancari esistenti, **una riga per ciascun nuovo
  finanziamento** col proprio nome, scoperto di conto corrente generato dal piano, altri
  finanziatori, fondo TFR · liquidazioni nell'anno, immobilizzazioni nette, **cassa**, **posizione
  finanziaria netta**, **PFN / MOL** (un multiplo, non una percentuale). Sotto, gli avvisi che il
  motore dichiara: lo scoperto acceso con il fabbisogno di picco, il tetto superato, la cassa che
  il piano consuma anche dove resta positiva, la cassa che chiude sotto il minimo, i fidi tirati
  oltre l'importo di partenza — o, quando non c'è niente di tutto questo, la conferma «La cassa
  resta positiva in tutti gli anni: nessun fabbisogno da coprire».
- **«Altri crediti e debiti del piano · dalle voci minori»**: **crediti e attività** (altri
  crediti a breve, ratei attivi, crediti tributari) con il totale; **debiti e fondi**
  (previdenziali, altri debiti a breve, fondi rischi, ratei passivi) con il totale; **«Effetto
  sulla cassa nell'anno · + libera · − assorbe»** = variazione del passivo meno variazione
  dell'attivo sull'anno precedente. Ogni riga porta la propria regola («costante», «segue i
  ricavi», …).

---

## Passo 7 · Imposte

**Che cosa inserisci**

- **Aliquota proposta**: in sola lettura, l'aliquota effettiva dell'ultimo bilancio annuale
  **depositato** (mai un anno promosso dall'infrannuale), con il ripiego 27,9% (IRES + IRAP)
  quando nessun consuntivo la esprime. Accanto, quando il piano ne usa un'altra, il pulsante
  **«Usa la proposta»**.
- **Aliquota del piano**: modificabile, ed è quella che il motore applica. Il vuoto non vuol dire
  niente: la casella ricade sul 27,9%, non sull'effettiva.
- **«Aliquota usata dal piano»**: compare solo quando c'è qualcosa da dichiarare — il piano usa
  un'aliquota diversa dalla proposta, o un `ce20_override` sostituisce l'aliquota con un importo
  su uno o più anni.
- **Acconto sull'imposta dell'anno prima**, in percentuale: la regola con cui il motore calcola
  l'acconto quando non è dichiarato un importo (vuoto = 100%).
- **Acconti versati nell'anno**, anno per anno: un importo qui sostituisce quella percentuale.
- **«Posizione tributaria manuale»** (accordion): *Debiti tributari entro %* e, solo quando è
  attiva la via manuale, *Debiti tributari oltre %*.
- In fondo, un rimando: **«Debiti tributari {anno} a breve · saldo pagato nel {anno 1} · passo
  5»**. Il saldo dell'anno precedente, il rateizzato e il piano delle rate — con la scorciatoia
  «N rate uguali» — non stanno più qui: si scadenziano al passo 5 **«Patrimoniale pregresso»**,
  nella card «Altre voci oltre 12 mesi».

Il **mastrino delle imposte anticipate e differite** non c'è più: dal 2026-09-18 le anticipate non
passano dal conto economico (commercialista) e il motore budget le ignora — `sp06f`/`sp07f`
restano quelle del consuntivo per tutto il piano e si cambiano solo con un override dello SP
previsionale.

**Che cosa ne fa il motore**

Le imposte si pagano **a saldo + acconto**, non si accumulano: il debito generato a fine anno N
esce come saldo **per intero** nell'anno N+1, e un credito d'imposta dell'anno prima si compensa
a sua volta per intero — anche oltre gli acconti, non solo fino alla capienza del saldo; e
l'acconto di N è di default il **100%** dell'imposta N−1 — o l'importo che hai scritto in
«Acconti versati nell'anno», **a condizione che sia maggiore di zero**: zero in quella casella non
vuol dire «zero acconti», vuol dire «non dichiarato», e il motore ricade sulla percentuale. Le
rate del piano, scadenziate al passo 5, muovono il solo rateizzato, mai il saldo.

La **via manuale** è un'alternativa, non un complemento: valorizzare una percentuale su
*Debiti tributari entro* (o su *Crediti tributari* al passo 4) fa muovere i debiti tributari per
crescita e **ignora il piano** di saldo, rate e acconti scadenziato al passo 5. Quando succede, il
motore lo dichiara e la schermata lo dice.

Sull'aliquota, **quello che scrivi è quello che gira** (commercialista, 2026-09-18): il motore
applica `tax_rate` così com'è (`ForecastEngine._tax_components`). L'effettiva dell'anno base non
vince più in silenzio — la usa solo la *proposta*, che è un suggerimento del server
(`GET /companies/{id}/years/{anno}/aliquota-proposta`, dove vivono il cap al 60% e il ripiego
27,9%), e il motore non la legge affatto. L'unica cosa che scavalca l'aliquota è un importo: se in
CE Prev. hai forzato a importo una riga imposte, su quell'anno **nessuna aliquota viene applicata**
— quell'importo è l'imposta.

> Gli scenari salvati prima del 2026-09-18 vanno migrati una volta
> (`scripts/migra_imposte_commercialista.py`, prova per default, `--apply` per scrivere): senza,
> applicano l'aliquota salvata invece dell'effettiva che il motore derivava per loro.

**Che cosa mostra l'anteprima**

«Imposte e risultato netto»: risultato ante imposte, imposte, **utile netto** e i debiti tributari
a fine anno; sotto, i **pagamenti dell'anno** — imposte correnti, saldo dell'anno precedente
versato, acconti versati, rate del rateizzato, **uscita di cassa per imposte** e saldo d'imposta
da versare l'anno dopo. Gli anni sulla via manuale restano vuoti con la nota «posizione tributaria
manuale»: il motore dichiara zero invece di inventare importi che non ha pagato.

È l'ultimo passo: qui il wizard si chiude, e il previsionale completo si legge e si ritocca nelle
schede **CE Prev.** e **SP Prev.**

---

## Scenari salvati prima del 15/09/2026

Uno scenario salvato prima di questo giro di rilievi non ha un'inflazione salvata
(`inflation_pct`): è il segno che lo riconosce. Alla prima apertura, prima ancora che tu tocchi
qualcosa, il wizard **migra in memoria** le sue ipotesi — non le salva finché non premi tu un
tasto — e mostra sopra il primo passo una card a due colonne: **«Ricalcolato · All'apertura»** e
**«Da integrare · Serve il tuo intervento»**, quest'ultima con un rimando al passo giusto per ogni
voce. Nella barra dei passi, un badge «da integrare» segna i passi 1 e 5 finché non salvi.

**Che cosa il wizard ricalcola da solo**

- La **parte variabile** di materie prime e servizi segue da ora in poi i ricavi: le vecchie
  percentuali, se diverse, vengono sostituite.
- La **parte fissa** resta quella che avevi scritto, ma non è più «automatica»: è già un'ipotesi
  tua, e non segue più l'inflazione del passo 1 finché non la svuoti.
- Un vecchio **«rimborso in N anni»** sui debiti bancari diventa un finanziamento con nome
  («Debiti verso banche · da "rimborso in N anni"»), con rate uguali per gli anni di piano; lo
  stesso per gli altri finanziatori. Un contratto già scadenziato in dettaglio resta com'è.
- Un vecchio **importo di nuovo finanziamento** (`financing_amount`) diventa un contratto
  «Nuovo finanziamento {anno}», e i tre campi legacy si azzerano.
- **Fidi e anticipi** partono da 0 con la regola «Costanti»: la divisione dei debiti a breve resta
  da fare (sotto).
- **L'inflazione** si imposta al 2%: il vecchio scenario non la salvava.

**Che cosa resta da fare**

- **Passo 1**: l'inflazione è impostata al 2% per ripiego — controllala.
- **Passo 5**: dividi i debiti verso banche a breve fra fidi e anticipi e quota dei mutui; il
  debito bancario pregresso è arrivato come un solo finanziamento da scadenziare (spacchettalo nei
  contratti veri, o confermalo com'è). Se lo scenario non aveva un piano di pregresso, verifica se
  tributari rateizzati, altri debiti e crediti hanno movimenti nel piano, o restano aperti.

La mappa migrata è **sporca**: l'anteprima gira già su quella, ma **CE Prev. e SP Prev. mostrano
ancora il previsionale calcolato prima** finché non premi «Salva e calcola previsionale» — la card
lo dice esplicitamente. Dopo il primo salvataggio riuscito la card sparisce, e non ricompare.

---

## Salvare e generare

Il tasto **«Salva e calcola previsionale»** fa una sola chiamata: scrive tutte le righe di ipotesi
dello scenario e, subito dopo, esegue il motore. Due verità da tenere separate, perché la schermata
le mostra insieme:

- **Il salvataggio delle ipotesi è una cosa, il previsionale un'altra.** Una generazione rifiutata
  arriva comunque con un «riuscito»: le ipotesi restano salvate, e a non essere generato è il
  piano. Il wizard lo legge dal campo giusto e te lo dice in un avviso, con la ragione; quando la
  ragione è un fabbisogno scoperto ti riporta al passo 6, dove lo scoperto si concede, negli altri
  casi al passo 7.
- **Un previsionale mostrato può essere più vecchio delle ipotesi salvate**, e la schermata
  dell'analisi lo dichiara. Succede appunto quando il salvataggio ha registrato le ipotesi ma
  il motore si è fermato: le pagine successive continuano a mostrare i numeri della generazione
  precedente.

Gli altri due modi di rigenerare passano da un'altra porta e falliscono in modo diverso:
«Ricalcola» rigenera senza scrivere nulla e risponde con un errore vero, e lo stesso vale per le
modifiche puntuali del conto economico. Lo stesso errore, due esiti diversi a seconda della porta.

---

## Modificare CE Prev. e SP Prev.

Ogni riga del conto economico e dello stato patrimoniale previsto si può forzare a un importo
assoluto in euro. Sono **due meccanismi distinti**, e la differenza si vede quando si azzera.

- **CE Prev.** — una cella in linea, la modifica resta gialla finché non premi **«Aggiorna
  Previsionale»**, che manda tutto in un'unica chiamata e rigenera una volta sola alla fine. Una
  cella svuotata toglie l'override e restituisce la riga al motore. Un override già salvato si
  riconosce dalla sottolineatura.
- **SP Prev.** — le celle scrivono in un sacco di valori a parte, che i due motori applicano in
  coda al calcolo dello stato patrimoniale. Tre comportamenti da sapere: una chiave che non
  esiste nel risultato viene **ignorata in silenzio**; ogni valore è **riportato a zero se
  negativo** (le uniche eccezioni sono il risultato d'esercizio e la riserva per azioni proprie),
  quindi un importo negativo o scritto male non dà errore, dà uno zero; e il dettaglio vince
  sull'aggregato, con la cassa che resta il pareggio a meno di non forzarla esplicitamente.
  Forzare la cassa di un anno che squilibra il foglio non si chiude più con uno zero: il
  fabbisogno si misura una volta sola, **dopo** l'override, e lì il motore o si ferma con un
  errore o lo converte in scoperto, se concesso.

**Precedenze e azzeramenti**

- Un override vince sempre sulla percentuale di crescita della stessa riga, e **sopravvive al
  salvataggio**: puoi cambiare «Ricavi delle vendite» quanto vuoi, se la riga è forzata il
  previsionale non si muove.
- **«Salva e calcola previsionale» non azzera alcun override.**
- **«Ricalcola» li azzera solo se spunti «Azzera le modifiche manuali del CE previsionale»**, e
  azzera solo le colonne del conto economico: **gli override di stato patrimoniale restano**. La
  casella dice «del CE», ed è onesta: chi la spunta aspettandosi il previsionale puro del motore
  si tiene comunque gli override dello SP.
- Su **SP Prev.**, un override su *debiti bancari entro l'esercizio* fissa un totale che **contiene**
  la quota del prestito nuovo che scade l'anno dopo; uno su *debiti bancari oltre l'esercizio* fissa
  solo la parte **oltre** la quota. I due override muovono cassa e debito bancario della quota, in
  direzioni opposte.

---

## Scoperto di conto corrente

> **Con i fidi separati al passo 5 questa sezione non si applica.** Il wizard separa sempre fidi e
> anticipi dai mutui, e in quel caso un fabbisogno non apre scoperto e non ferma il piano: il motore
> riutilizza i fidi, e oltre l'importo del bilancio di partenza mostra un avviso (vedi «Passo 5 ·
> Patrimoniale pregresso» e «Passo 6 · Patrimoniale piano»). Quanto segue vale per gli scenari che non
> dichiarano i fidi, cioè quelli scritti via API senza `bank_lines_amount`.

La cassa del previsionale pareggia solo verso l'alto: quando le ipotesi non si finanziano da sé,
il residuo negativo è un **fabbisogno scoperto**. Che cosa ne è di quel numero è una tua scelta,
una casella al passo 6, **spenta di default**.

- **Spento:** il motore **si ferma** e non produce nulla, sul primo anno che non si finanzia. Non
  è un guasto e riprovare non serve: la via d'uscita è un'ipotesi di finanziamento in più, meno
  investimenti, o un rimborso più lungo del debito pregresso. Uno scoperto già aperto in un anno
  precedente può essere rimborsato, non aumentato.
- **Acceso:** il fabbisogno diventa uno **scoperto generato dal piano**, tenuto separato — anche
  nell'aritmetica, non solo nelle note — dal debito bancario pregresso e dal finanziamento nuovo,
  così che le rate dell'uno e dell'altro rimborsino solo il proprio debito. Gli interessi vanno in
  conto economico sullo scoperto **di apertura**, a tasso del nuovo finanziamento. La cassa libera
  non convive con lo scoperto: prima rimborsa quello.

È il modo per misurare **quanta finanza richiedono queste ipotesi**: lo scoperto nato ogni anno,
quello residuo a fine anno, il **fabbisogno di picco** con l'anno in cui cade e la cassa assorbita
sono dichiarati ogni anno, anche a zero, e compaiono negli avvisi dell'anteprima al passo 6.

**Il tetto**, se lo imposti, è confrontato con lo scoperto **in essere a fine anno**: sopra, il
motore si ferma di nuovo. **Un override di stato patrimoniale** sui debiti bancari a breve fissa
il totale e vince: lo scoperto ne discende, e con un fabbisogno in corso nessuna ripartizione fra
banca e scoperto è coerente — il motore rifiuta la combinazione con un messaggio esplicito invece
di superare il totale forzato.

---

**Vedi anche:** [API-PREVISIONALE.md](API-PREVISIONALE.md) per i corpi delle chiamate e le precedenze
formali, [../frontend/PRATICA-PERCORSO.md](../frontend/PRATICA-PERCORSO.md) per il percorso dentro
una pratica.

---

## Report finale canonico

La pagina **Report finale** non ricostruisce conti, grafici o commenti nel browser: carica una
sola volta il modello finale assemblato dal server e lo rende nell'ordine editoriale canonico.
Vale per le tre pratiche: **bilancio** (annuale), **infrannuale** (con scenario sorgente e dati di
chiusura) e **startup**. Scegli uno scenario budget, attendi il caricamento e usa il tasto
**Riprova** se la lettura fallisce; uno stato di caricamento, un errore recuperabile e un modello
con schema non supportato sono casi distinti, non un report parzialmente interpretato.

Il report ha queste **12 sezioni**, nello stesso ordine dell'indice: Copertina e perimetro;
Sintesi esecutiva; Origine e qualità dei dati; Rettifiche apportate; Dall'infrannuale alla
chiusura; Ipotesi del budget; Conto economico previsionale; Stato patrimoniale previsionale;
Flussi di cassa e sostenibilità finanziaria; Indicatori e rischi; Diagnostica e punti da
verificare; Appendici e metodologia. La sezione di chiusura è significativa per l'infrannuale;
nelle altre due pratiche il modello dichiara esplicitamente che quei dati non si applicano.

Prima di usare il report come consegna, leggi il banner di **readiness** (`ready`, `draft` o
`blocked`) e la diagnostica. Il modello espone anche qualità delle fonti, rettifiche, chiusura,
ipotesi, revisione delle sorgenti e freschezza di previsionale/narrazione: sono dati forniti dal
server, non deduzioni della pagina. Se le ipotesi sono più recenti del previsionale, il banner
chiede di rigenerare; l'azione genera il forecast e poi ricarica il modello finale. Non è un
semplice refresh e non modifica i commenti narrativi.

### Grafici, commenti e stampa

Le sei serie server-provided sono: risultati economici, margini, flussi di cassa, liquidità e
debito, giorni del capitale circolante e copertura. Ogni grafico offre anche una tabella testuale
accessibile con categorie e valori: la tabella è l'alternativa leggibile da tecnologie assistive e
non una seconda elaborazione. Le sei narrazioni corrispondono a sintesi esecutiva, rettifiche e
chiusura, ipotesi di budget, prospettiva economica, prospettiva finanziaria, rischi e azioni.

**Rigenera commenti** è esplicito: richiede al server una nuova narrazione e aggiorna il modello.
Ogni commento può invece essere modificato e salvato esplicitamente, senza chiamare il modello
linguistico. Provenienza (`ai`, `user`, `migrated`) e freschezza (`fresh`, `stale`, `missing`)
restano visibili, quindi una prosa vecchia non diventa una conclusione corrente per errore.
**Anteprima stampa** usa la stampa del browser soltanto per la revisione visiva: non produce il
PDF ufficiale e non è una procedura di esportazione certificata.

Gli importi del modello finale sono `DecimalString`: stringhe JSON decimali, non numeri JSON né
valori formattati per la UI. La forma accettata è `^-?(?:0|[1-9]\\d*)(?:\\.\\d+)?$`; non sono
ammessi esponente, separatore delle migliaia, virgola decimale, `NaN` o infinito. Il client può
formattare tali stringhe per la lettura, ma non deve ricalcolare né sostituirle con floating point.
