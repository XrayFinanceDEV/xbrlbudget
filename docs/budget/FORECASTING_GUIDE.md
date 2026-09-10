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
| 1 | Scenario | nome, anno base, orizzonte | Impostazione |
| 2 | Fatturato | ricavi e altri ricavi | Conto economico |
| 3 | Costi principali | quota fissa e variabile | Conto economico |
| 4 | Altre voci CE | voci minori e automatiche | Conto economico |
| 5 | Capitale circolante | giorni medi | Stato patrimoniale |
| 6 | Pregresso e nuovo | debiti, finanziamenti, investimenti | Stato patrimoniale |
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
- **Punto di partenza**: la casella **Inflazione attesa** (%) e una tabella con una riga per
  ciascuna voce (**Ricavi**, **Altri ricavi**, **Materie prime**, **Servizi**, **Godimento
  beni**, **Personale**, **Oneri diversi**), la colonna **Trend storico** e una colonna per ogni
  anno di piano. Il pulsante **«Riparti dalla tendenza»** sovrascrive le ipotesi correnti su
  tutto l'orizzonte per quelle voci; con un solo anno storico la schermata avvisa che il trend
  non è calcolabile e che verranno usati i valori di inflazione.

**Che cosa ne fa il motore**

Nulla, a questo passo: le percentuali della tabella sono ipotesi che verranno salvate con le
altre. È il passo in cui si decide l'orizzonte, cioè quante righe di ipotesi il salvataggio
porterà con sé.

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

## Passo 3 · Costi principali

**Che cosa inserisci**

- Due slider, **Materie prime** e **Servizi**, con la casella **「% fissa»** accanto: «Quanto di
  questi costi è fisso». Sotto ciascuno, la barra *Fissa · …* / *Variabile · …* sull'importo
  dell'anno base. La guida a schermo: la quota fissa segue l'inflazione, la quota variabile segue
  i ricavi; lo slider vale per tutti gli anni previsti, e per differenziarli serve la riga
  «quota fissa» della tabella, che si compila anno per anno. Se gli anni hanno quote diverse,
  la schermata avvisa che muovendo lo slider — o digitando nella casella — verranno allineati a
  quello che imposti.
- La tabella, in tre gruppi: **Quota fissa, anno per anno** (*Materie prime · quota fissa (%)*,
  *Servizi · quota fissa (%)*), **Costi variabili** (*Materie prime · parte variabile*, *Servizi
  · parte variabile*), **Costi fissi** (*Materie prime · parte fissa*, *Servizi · parte fissa*),
  più **Personale** e **Godimento beni di terzi**.
- **«Allinea le variabili ai ricavi»**: scrive sulle due parti variabili, anno per anno, la
  crescita dei ricavi di quell'anno.

**Che cosa ne fa il motore**

Le materie prime e i servizi sono spesati in due componenti, fissa e variabile: la quota fissa di
default è il **40%** ed è modificabile su ogni riga di ipotesi. Il motore restituisce per entrambe
le voci i due addendi — la parte fissa e la parte variabile — che diventano **nulli** quando quella
voce è stata forzata in CE Prev. con un importo assoluto: su un importo forzato la scomposizione
non è definita, e l'anteprima marca la cella invece di mostrare un numero che il motore non ha
usato. Le caselle di crescita di quegli stessi anni si spengono con la loro spiegazione: «Forzato
in CE Prev.: in quest'anno la voce è un importo assoluto, quindi questa percentuale non ha
effetto. Si azzera dal dialogo Ricalcola».

**Che cosa mostra l'anteprima**

«Costi principali e margine»: ricavi, **costi principali** e i loro *di cui fissi* / *di cui
variabili*, le quattro voci, il **MOL stimato**, tutte le percentuali calcolate sui ricavi
dell'anno; le barre fissi/variabili anno per anno e il peso dei fissi fra il primo e l'ultimo
anno. In fondo, una riga sola sui **debiti verso fornitori** calcolati «con i giorni di
pagamento fermi all'anno base»: qui restano quelli dell'ultimo bilancio per non mescolare le
ipotesi, i giorni medi si regolano al passo 5.

---

## Passo 4 · Altre voci CE

**Che cosa inserisci**

- «Voci minori · variazione %»: una riga, **Altri costi (oneri diversi)**.
- «Calcolate dal piano», con il contrassegno *automatico*: **Ammortamenti** (quote sull'anno base
  più la percentuale dei nuovi investimenti impostata al passo 6), **Oneri finanziari** (sul
  debito del passo 6), **Imposte** (con l'aliquota del passo 7).

**Che cosa ne fa il motore**

Queste tre non hanno una casella: le produce. Sugli oneri finanziari il motore scrive qui gli
interessi del finanziamento nuovo e quelli dello scoperto, calcolati sul residuo **di apertura**
dell'anno, mai su quello che l'anno stesso genera. Sulle imposte, l'aliquota che il piano usa
davvero è quella **effettiva** dell'anno base — imposte su risultato ante imposte, scartata se
oltre il 60% — e il valore forzato nel passo 7 entra in gioco solo quando quell'aliquota non è
derivabile. La schermata lo dice con una riga: un valore forzato a mano nel CE previsionale
vince sempre su queste regole e resta finché non lo azzeri dal dialogo Ricalcola.

**Che cosa mostra l'anteprima**

«Conto economico sintetico»: valore della produzione, costi principali, altre voci dei costi,
**MOL**, ammortamenti e svalutazioni, **risultato operativo**, l'area finanziaria e straordinaria
e il **risultato ante imposte**, in cascata, così che la somma torni esattamente sul risultato.

---

## Passo 5 · Capitale circolante

**Che cosa inserisci**

- «Giorni medi», tre righe: **Giorni incasso clienti (DSO)**, **Giorni rotazione magazzino
  (DIO)**, **Giorni pagamento fornitori (DPO)**. Il campo è annullabile e il segnaposto mostra
  *auto N*: vuoto significa «usa il valore derivato dall'anno base», mai «zero giorni». La nota
  sotto ricorda che i giorni dell'anno base sono calcolati sui soli crediti e debiti commerciali,
  su 360 giorni, e che le voci non commerciali non seguono i ricavi.
- «Voci minori dell'attivo e del passivo · andamento nel piano»: una riga per ciascuna delle
  quindici voci (crediti oltre 12 mesi, crediti verso soci, immobilizzazioni finanziarie,
  crediti tributari, imposte anticipate entro e oltre, attività finanziarie, ratei e risconti
  attivi, fondi per rischi e oneri, debiti previdenziali entro e oltre, debiti fornitori oltre,
  altri debiti entro e oltre, ratei e risconti passivi) con l'importo base e, dove il motore può
  agganciarla, un selettore: **Costante (variazione %)** oppure **Cresce con i ricavi / gli
  acquisti (materie e servizi) / il costo del personale**. Sotto ogni voce, la frase che dice
  come si muoverà nel piano.
- **«Variazione % per anno»** (accordion): le stesse voci come percentuali, anno per anno.
- Due interruttori: **Debiti previdenziali scalano col costo del personale** e **TFR versato a
  INPS/fondi (accantonamento sospeso)**.

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
- Una voce lasciata su «Costante (variazione %)» senza scrivere una percentuale resta **ferma**
  per tutto il piano. L'aggancio a un driver di volume ha invece la forma *stock dell'anno base ×
  fattore del driver*: indicizzare sulla base non accumula deriva, mentre un *prev × (1 + %)*
  composto per cinque anni sì. Il motore legge l'aggancio riga per riga, la schermata lo scrive su
  tutti gli anni di piano leggendo la scelta del primo anno.
- Alcune voci hanno già un padrone e il selettore non le offre nemmeno: i crediti tributari e le
  imposte anticipate seguono la posizione fiscale, e i crediti oltre l'esercizio seguono la propria
  percentuale insieme al piano dei crediti commerciali. Nel motore le voci agganciabili sono undici
  codici, e fra essi non ci sono i debiti bancari, che seguono il piano di rimborso. Se una voce ha
  un piano di scadenziamento al passo 6, è il piano a governarla: lì l'interfaccia toglie il driver
  invece di proportelo e poi buttarlo via.
- L'interruttore **Debiti previdenziali scalano col costo del personale** quando è acceso è già
  lui l'indicizzazione di quelle due voci: prevale su qualunque driver scelto per esse.
- Dove il driver è acceso, la **percentuale di crescita della stessa voce non ha alcun effetto**:
  il driver vince, e il motore lo dichiara riga per riga.

**Che cosa mostra l'anteprima**

«Circolante proiettato»: crediti commerciali, rimanenze, debiti verso fornitori, il **capitale
circolante commerciale** con la sua incidenza sui ricavi e l'**assorbimento di cassa
nell'anno**. Nelle celle compaiono i giorni **effettivamente applicati**, che sono i tuoi se li
hai scritti, altrimenti quelli derivati — e su un giorno scartato perché degenere, il giorno che
quel saldo riporta davvero.

---

## Passo 6 · Pregresso e nuovo

«A sinistra il bilancio che c'è già e come si scadenzia. A destra quello che il piano genera. Non
si mescolano.»

**Che cosa inserisci**

- **Scadenziamento del pregresso** (saldi al 31/12 dell'anno base): **Debiti bancari esistenti** e
  **Altri finanziatori**, ognuno con «rimborso in *n* anni». La nota avvisa che con un piano
  dettagliato in «Finanziamenti» la durata generica viene ignorata: vale il piano.
- **Pregresso del circolante**: la tabella dello scadenziamento dei quattro saldi che si
  scadenziano qui — **Crediti commerciali**, **Debiti verso fornitori**, **Debiti
  previdenziali**, **Altri debiti** — con l'interruttore **€ / %**, una colonna di apertura e una
  per anno di piano più il residuo. I **Debiti tributari** sono elencati ma non si scadenziano
  qui: seguono la posizione fiscale e si regolano al passo Imposte.
- **Finanziamenti — esistenti e nuovi**, contratto per contratto: *Descrizione*, **Residuo
  iniziale** (quota di debito già in essere, ammessa solo nel primo anno di piano), **Nuova
  erogazione**, *Durata*, *Tasso %*, *Preamm. anni*, *Balloon %*, con il riepilogo **Debito
  bancario {anno base} / Residui inseriti / Ancora da coprire**. Finché la differenza non è zero
  al centesimo il previsionale viene rifiutato.
- **Generato dal previsionale**, a destra: *Nuovo finanziamento* (**Importo €**, **Durata
  (anni)**, **Tasso %**), *Nuovi investimenti* (**Investimenti materiali €**, **Investimenti
  immateriali €**), **Scoperto di conto corrente** — casella *«Concedi lo scoperto: il fabbisogno
  scoperto diventa debito bancario a breve»* e, con quella accesa, il **Tetto dello scoperto €**
  (vuoto = senza tetto) — e l'accordion **«Mostra tutte»** con i due tassi di ammortamento dei
  nuovi investimenti, le **cessioni** (valore contabile netto e corrispettivo), la **cassa minima
  del cash sweep** e l'interruttore **Cash sweep**.

**Che cosa ne fa il motore**

- **Il piano del pregresso sta su una riga sola, il primo anno di piano**: è una fotografia
  dell'anno base, non un'ipotesi per anno. Il saldo di apertura deve coincidere col bilancio base
  entro un centesimo, e la somma di quanto scadenzi più l'inesigibile non può superare la massa:
  superarla è un errore, non un troncamento, perché incassare più di quanto c'è inventa cassa.
  L'inesigibile esiste solo sui crediti commerciali e va in svalutazione nel conto economico; se
  un override del CE forza quella svalutazione, l'inesigibile scadenziato non può essere
  scaricato e resta a bilancio — il motore lo dichiara e la schermata te lo mostra.
- **Senza un piano, ogni saldo segue la formula di sempre** al centesimo. **Con un piano, il lato
  oltre l'esercizio è interamente pregresso**: il motore rigenera dalla formula di oggi solo la
  parte a breve, il resto del residuo resta lì per tutto il piano e la percentuale di crescita di
  quella voce smette di applicarsi.
- **Il finanziamento nuovo** segue il proprio calendario: quote capitale costanti dopo
  l'eventuale preammortamento, maxirata insieme all'ultima rata, interessi in conto economico sul
  residuo di apertura. La quota che il calendario rimborsa **nell'anno dopo** sta a breve nel
  passivo, il resto oltre: è una riclassificazione, non un flusso — risultato e, finché non
  forzi quei campi, cassa e debito bancario totale non cambiano — ma è ciò che rende giusti CCN,
  current ratio e circolante di Altman.
- **La cassa è il pareggio e pareggia solo verso l'alto**: un fabbisogno non si converte da sé in
  debito a breve. È la casella dello scoperto a decidere (sotto).
- **Il cash sweep** usa la cassa in eccesso per rimborsare debito: prima il debito bancario
  pregresso e poi il prestito nuovo. Con lo scoperto acceso la cassa libera rimborsa prima lo
  scoperto, **anche sotto la cassa minima** impostata: tenere liquidità pagando gli interessi sullo
  scoperto non avrebbe senso, e il motore dichiara quanta cassa è finita sotto quel minimo.

**Che cosa mostra l'anteprima**

«Debito, cassa e PFN»: debiti bancari, altri finanziatori, immobilizzazioni nette, **cassa** e
**posizione finanziaria netta**, più il pregresso scadenziato saldo per saldo (residuo a breve,
oltre l'esercizio, chiuso nell'anno, di cui inesigibile). Sotto, gli avvisi che il motore
dichiara: lo scoperto acceso con il fabbisogno di picco, la cassa che il piano consuma anche dove
resta positiva, la cassa che chiude sotto il minimo per rimborsare lo scoperto, e — quando non c'è
niente di tutto questo — la conferma «La cassa resta positiva in tutti gli anni: nessun fabbisogno
da coprire».

---

## Passo 7 · Imposte

**Che cosa inserisci**

- **Aliquota effettiva {anno base}**: imposta su risultato ante imposte, in sola lettura, con il
  contrassegno *usata dal piano* quando è quella che il motore applicherà.
- **Aliquota forzata**: vuota = usa l'effettiva, o il 27,9% (IRES + IRAP) quando l'effettiva non è
  derivabile. Quando il piano usa un'aliquota diversa da quella dell'anno base compare la riga
  **«Aliquota usata dal piano»** con il perché.
- **Acconti versati nell'anno**, anno per anno.
- **Mastrino imposte anticipate e differite**: righe di *Descrizione*, *Apertura*, *Incrementi*,
  *Riversamenti* e un'aliquota per riga.
- **Pagamento dei debiti tributari**: il **Saldo dell'anno precedente** (si versa per intero nel
  primo anno di piano), il **Rateizzato** in sola lettura — è ciò che il saldo non copre —, il
  **piano delle rate** con il selettore **«N rate uguali»**, e l'**Acconto sull'imposta dell'anno
  prima** in percentuale, la cui chiosa ricorda che un acconto per anno, **se maggiore di zero**,
  la scavalca.
- **«Posizione tributaria manuale»** (accordion): *Debiti tributari entro %* e, solo quando è
  attiva la via manuale, *Debiti tributari oltre %*.

**Che cosa ne fa il motore**

Le imposte si pagano **a saldo + acconto**, non si accumulano: il debito generato a fine anno N
esce come saldo nell'anno N+1, al netto del credito tributario di apertura fino a capienza, e
l'acconto di N è di default il **100%** dell'imposta N−1 — o l'importo che hai scritto in
«Acconti versati nell'anno», **a condizione che sia maggiore di zero**: zero in quella casella non
vuol dire «zero acconti», vuol dire «non dichiarato», e il motore ricade sulla percentuale. Le
rate del piano scadenziano il solo rateizzato, mai il saldo.

La **via manuale** è un'alternativa, non un complemento: valorizzare una percentuale su
*Debiti tributari entro* (o su *Crediti tributari* al passo 5) fa muovere i debiti tributari per
crescita e **ignora il piano** di saldo, rate e acconti. Quando succede, il motore lo dichiara e la
schermata lo dice.

Sull'aliquota, quello che scrivi qui è un **ripiego**: il motore usa l'effettiva dell'anno base
quando è derivabile e legge il campo forzato solo quando non lo è. E se in CE Prev. hai forzato a
importo una riga imposte, su quell'anno **nessuna aliquota viene applicata**: quell'importo è
l'imposta.

**Che cosa mostra l'anteprima**

«Imposte e risultato netto»: risultato ante imposte, imposte, **utile netto** e i debiti tributari
a fine anno; sotto, i **pagamenti dell'anno** — imposte correnti, saldo dell'anno precedente
versato, acconti versati, rate del rateizzato, **uscita di cassa per imposte** e saldo d'imposta
da versare l'anno dopo. Gli anni sulla via manuale restano vuoti con la nota «posizione tributaria
manuale»: il motore dichiara zero invece di inventare importi che non ha pagato.

È l'ultimo passo: qui il wizard si chiude, e il previsionale completo si legge e si ritocca nelle
schede **CE Prev.** e **SP Prev.**

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
  dell'analisi lo dichiara. Succede justamente quando il salvataggio ha registrato le ipotesi ma
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
