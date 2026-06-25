# Gap Analysis: PDF Report vs /report Implementation

Reference PDF: `docs/OBICON_S.R.L._Relazione_Analisi_Indici_&_Rating_Anni_2023-2023.pdf` (40 pages)

## MATCHING WELL (no changes needed)

- Dashboard gauges (Altman, FGPMI, EM-Score)
- Asset/Liability composition charts
- Income statement trend lines + waterfall + variation table
- Structural analysis (MS/CCN/MT) chart + values
- Altman Z-Score trend + components + multi-year table
- EM-Score multi-year table
- FGPMI indicators chart + table + evolution
- Break-even BEP + safety margin basics
- Appendices: raw BS (sp01-sp18) and IS (ce01-ce20) tables

---

## GAP 1: Italian Descriptions (HIGH PRIORITY)

Every ratio and section in the PDF has 1-5 paragraphs of Italian explanatory text. Our components have zero descriptions.

| Component | Missing Descriptions |
|---|---|
| `report-structural.tsx` | 3.1 MS description (5 paragraphs), 3.2 CCN (4 paragraphs), 3.3 MT (2 paragraphs) |
| `report-ratios.tsx` | Category intros (4.1-4.5) + per-ratio descriptions (4.1.1-4.5.2) = ~20 descriptions total |
| `report-break-even.tsx` | 4.6 intro + 4.6.1 Ricavi BEP, 4.6.2 Margine Sicurezza, 4.6.3 Leva Operativa, 4.6.4 Moltiplicatore |
| `report-scoring.tsx` | Altman history/limitations (2 long paragraphs), EM-Score methodology (1 paragraph), FGPMI Fondo Garanzia description (2 paragraphs) |
| `report-cashflow.tsx` | 8.1-8.6 cashflow ratio descriptions (each has 2-4 paragraphs) |
| `report-notes.tsx` | Full 1.1 Aspetti Introduttivi + 1.2 Aspetti Metodologici text |

### Source text from PDF

#### 1.1 Aspetti Introduttivi
> Gli indici di bilancio e i sistemi di rating sono uno strumento di lettura e analisi della situazione in cui versa l'azienda e permettono di evidenziare in estrema sintesi i fattori di forza e vulnerabilita dell'azienda stessa.
> Lo studio e la comparazione sistematica degli indici e rating di bilancio rappresenta una componente importante per le valutazioni dell'imprenditore e dei suoi manager ma serve soprattutto per i soggetti esterni all'azienda (in primis le banche finanziatrici) per i quali il bilancio resta la principale, se non unica fonte informativa.
> L'analisi per indici si basa sul calcolo, sulla lettura e sull'interpretazione di indicatori ricavabili dalla combinazione, sulla base di rapporti, somme o differenze, di determinate voci di bilancio o desumibili dalle riclassificazioni di bilancio.
> L'obiettivo dell'analisi di bilancio proposta e quello di fornire al lettore delle indicazioni circa lo stato di salute dell'azienda, valutando le prestazioni della stessa e confrontandole nel tempo.
> I rating contabili, assegnando dei punteggi ad alcuni indici specifici di carattere "strategico", consentono di intercettare in maniera piuttosto immediata la situazione dell'azienda oggetto di analisi.
> Il rendiconto finanziario e uno strumento in grado di illustrare le dinamiche finanziarie dell'azienda rilevando la capacita della stessa di produrre (o di assorbire) fonti finanziarie tramite l'attivita operativa ed evidenziando nel tempo gli impieghi in investimenti e il reperimento delle fonti di finanziamento (interno o esterno) utilizzate a copertura degli impieghi.

#### 1.2 Aspetti Metodologici
> Le elaborazioni si basano, per i primi due esercizi a consuntivo, sui dati dei bilanci pubblicati nel Registro delle Imprese e aggregati sulla base di uno schema CEE connotato di minore analiticita, ma adeguato al fine di eseguire un'analisi accurata. In tal modo e possibile analizzare bilanci ordinari, abbreviati e micro in modo uniforme.
> Per i tre esercizi successivi i dati sono frutto di uno sviluppo prospettico dei dati dell'ultimo esercizio a consuntivo sulla base delle variabili di scenario valorizzate per ciascuna delle tre annualita prospettiche.
> I dati sono ulteriormente riclassificati per ottenere uno stato patrimoniale espresso in termini finanziari e un conto economico formulato in base al c.d. "VALORE AGGIUNTO", con evidenziazione dei margini di contribuzione piu rilevanti (EBITDA o MOL, MON, EBIT o RO).
> Le riclassificazioni prevedono anche il calcolo di alcuni dati da utilizzare per l'analisi strutturale o per margini e del break even point.
> Il Rendiconto Finanziario e ottenuto ricorrendo al cosiddetto metodo indiretto e ricostruito esclusivamente sulla base dei dati del conto economico e delle variazioni di stato patrimoniale tra un esercizio e il precedente.

#### 3.1 Margine di Struttura
> Il margine di struttura e dato dalla differenza fra il capitale netto e il valore netto delle immobilizzazioni e indica se i mezzi propri sono in grado di coprire il fabbisogno durevole rappresentato dalle attivita immobilizzate.
> Se il margine e positivo il capitale proprio copre tutto il fabbisogno durevole; se e negativo una parte del fabbisogno durevole e coperto dai debiti (capitale di terzi).
> Una situazione ideale e rappresentata da un margine positivo che evidenzia una situazione di equilibrio finanziario adeguata per realizzare strategie di sviluppo aziendale e operazioni di espansione.
> Un margine negativo evidenzia invece la dipendenza dell'azienda dal capitale di terzi anche per sostenere gli investimenti durevoli. E una situazione frequente che puo essere anche considerata normale purche non vengano superati determinati limiti di indebitamento.

#### 3.2 Capitale Circolante Netto
> Il capitale circolante netto e dato dalla differenza fra le attivita correnti (LI+LD+RD) e le passivita a breve termine (PC) e rappresenta una misura della capacita del management di gestire l'attivita operativa corrente dell'azienda.
> Un giudizio positivo sulla struttura finanziaria prevede che il capitale circolante netto sia abbondantemente positivo, risultando cosi sufficiente per sostenere i debiti in scadenza a breve termine.
> Se e negativo significa invece che l'azienda sta finanziando con fonti a breve termine anche le attivita immobilizzate, esponendosi cosi a rischi di natura finanziaria (non essendo in grado di far fronte in maniera adeguata ai debiti a breve termine utilizzando le attivita correnti).
> Per migliorare tale indice occorre diminuire l'indebitamento a breve termine facendo ricorso a scadenze di piu lungo periodo. Come ulteriore soluzione velocizzare il ciclo delle vendite riducendo i tempi di incasso.

#### 3.3 Margine di Tesoreria
> Il margine di tesoreria e dato dalla differenza fra le attivita liquide immediate e quelle differite (LI+LD) e le passivita a breve termine (PC) ed e uno dei primi indici attraverso i quali viene valutata la condizione di solvibilita dell'azienda, poiche rappresenta la capacita di far fronte ai debiti a breve con le attivita liquide o immediatamente liquidabili.
> Il margine di tesoreria dovrebbe essere positivo; se il margine e negativo allora l'azienda si trova in zona di rischio finanziario, perche, di fronte ad una richiesta di pagamento immediato dei debiti, non avrebbe mezzi monetari sufficienti per farvi fronte.

#### 4.1 Indici di Solidita (category intro)
> Gli indici di solidita mirano a misurare la capacita dell'azienda a perdurare nel tempo. La solidita si puo raggiungere attuando una razionale correlazione tra fonti e impieghi e mantenendo una adeguata indipendenza dai terzi.

#### 4.1.1 Copertura Immob. con Fonti Durevoli
> L'indice rappresenta il rapporto esistente fra i mezzi propri (CN) e le fonti durevoli di terzi (PF) e il totale delle attivita fisse (AF).
> E opportuno che un'azienda abbia a disposizione fonti proprie e fonti durevoli di terzi per importi corrispondenti alle attivita fisse in cui ha investito.
> L'indice e ritenuto corretto se presenta un valore pari o superiore al 100%.

#### 4.1.2 Copertura Immob. con Capitale Proprio
> L'indice rappresenta il rapporto tra i mezzi propri (CN) e il totale delle attivita durevoli (AF).
> Viene espresso un giudizio positivo sul grado di capitalizzazione dell'azienda se l'indice si avvicina al 100%.

#### 4.1.3 Indipendenza dai Terzi
> L'indice rappresenta il rapporto tra i mezzi propri (CN) e le passivita correnti e durature (PC+PF) e indica il grado di finanziamento dell'azienda.
> Non esiste una misura ottimale standard per questo indice ma si ritiene che lo stesso non debba essere troppo inferiore al 50% e comunque non inferiore al 25%. Una piu bassa percentuale indica una eccessiva dipendenza dell'azienda dal capitale di terzi.

#### 4.2 Indici di Liquidita (category intro)
> Gli indici di liquidita (o finanziari) mirano a misurare la capacita dell'azienda a far fronte a propri impegni finanziari in maniera tempestiva, economica e con i normali mezzi a disposizione.
> Tali indici dipendono sia da una buona correlazione fra impieghi correnti e fonti non durevoli e dalla capacita di trasformare velocemente gli investimenti in denaro (tale ultima capacita viene misurata con gli indici di "turnover" o "rinnovo").

#### 4.2.1 Liquidita Corrente / Disponibilita
> L'indice rappresenta il rapporto tra le attivita correnti (LI+LD+RD), c.d. capitale circolante lordo, e le passivita correnti.
> Segnala la capacita dell'azienda di far fronte alle passivita correnti con i mezzi immediatamente disponibili o liquidabili a breve termine.
> Il dato che e ritenuto generalmente corretto non dovrebbe essere di troppo inferiore al 200%.

#### 4.2.2 Acid Test Ratio (ATR)
> L'indice rappresenta il rapporto tra le liquidita immediate e le liquidita differite (LI+LD) e le passivita correnti ed esprime la capacita di far fronte ai debiti a breve utilizzando le disponibilita a breve. Rispetto all'indice precedente si differenzia per il fatto che non si tiene conto delle rimanenze e dei ratei/risconti attivi.
> L'indice e considerato adeguato se supera il 100% poiche in tal caso l'azienda e in grado di far fronte ai debiti correnti con le liquidita immediate o con quelle velocemente liquidabili. Viene considerato ragionevole anche un indice non molto inferiore al 100%. Un valore eccessivamente inferiore segnala invece problemi di solvibilita nel breve periodo.

#### 4.3 Indici di Rotazione e Durata (category intro)
> Gli indici di rotazione rappresentano la velocita di trasformazione degli investimenti in denaro. Non vi sono dati ottimali standard ma se il confronto temporale indica un aumento di velocita significa che e in miglioramento anche la liquidita dell'azienda.
> Dividendo il numero di giorni di un anno solare (360 per convenzione) con gli indici di turnover si ottiene la durata in giorni (media) delle attivita a cui gli indici di turnover si riferiscono.

#### 4.3.1 Turnover del Magazzino
> L'indice rappresenta il rapporto tra i consumi (CO) e le rimanenze (RD al netto delle attivita finanziarie che non costituiscono immobilizzazioni e dei ratei e risconti attivi) e indica la velocita di rinnovamento del magazzino (rispetto agli acquisti di materie prime, sussidiarie, di consumo e di merci).

#### 4.3.2 Turnover dei Crediti
> L'indice rappresenta il rapporto tra le vendite (RIC) e le liquidita differite (LD) e indica la velocita di rinnovo dei crediti.

#### 4.3.3 Turnover dei Debiti
> L'indice rappresenta il rapporto tra la somma dei consumi (CO), i servizi e godimento beni di terzi (AC) e gli altri oneri di gestione (ODG) e le passivita correnti (PC) e indica la velocita di rinnovo dei debiti.

#### 4.3.4 Turnover del CCN
> L'indice rappresenta il rapporto tra le vendite (RIC) e il capitale circolante netto (CCN=[LI+LD+RD]-PC) e indica la velocita di rinnovo delle attivita correnti nette.

#### 4.3.5 Turnover delle Attivita Totali
> L'indice rappresenta il rapporto tra le vendite (RIC) e le attivita totali (TA) e indica la velocita di rinnovamento delle attivita complessive dell'azienda.

#### 4.4 Indici di Redditivita (category intro)
> La redditivita viene analizzata tramite una serie di indicatori che a diverso titolo misurano la capacita dell'azienda di remunerare i propri fattori produttivi di reddito ed e una qualita imprescindibile al fine di poter reperire le fonti necessarie per attuare programmi di sviluppo e di investimenti.

#### 4.4.1 ROE
> Il ROE rappresenta il rapporto tra il risultato netto (RN) e il patrimonio netto (PN) e misura il rendimento del capitale proprio (equity) investito nell'azienda. La misura minima soddisfacente e una percentuale equivalente al tasso rappresentativo del costo del denaro a breve termine ed esente da rischi. Quanto piu supera tale tasso, tanto piu la redditivita e buona.

#### 4.4.2 ROI
> Il ROI rappresenta il rapporto tra il margine operativo netto (MON) e il totale delle attivita investite nell'azienda (TA) e misura la capacita di produrre reddito esclusivamente tramite l'attivita caratteristica segnalando la resa di tutti i mezzi investiti nell'azienda.

#### 4.4.3 ROS
> Il ROS rappresenta il rapporto tra il margine operativo netto (MON) e le vendite (RIC) e misura la resa in termini di margine operativo netto delle vendite effettuate. Indica quindi quanto margine operativo netto si e creato ogni 100 di vendite.

#### 4.4.4 ROD
> Il ROD rappresenta il rapporto tra gli oneri finanziari (OF) e le passivita correnti e durature (PC+PF) e misura il costo medio dei finanziamenti.

#### 4.4.5 ROI - ROD (Spread)
> L'indice misura la differenza tra l'indice di redditivita del capitale investito (ROI) e l'indice del costo del denaro a prestito (ROD) e misura l'"effetto leva finanziaria" che puo risultare positivo o negativo a seconda che il ROI sia maggiore, minore o uguale al ROD.
> ROI > ROD: in tale situazione, per l'azienda si manifesta un "effetto leva" positivo; vi e convenienza ad indebitarsi anche in termini onerosi, in quanto il costo dell'indebitamento e inferiore al beneficio che si ottiene sulla redditivita del capitale investito. Fino a quando il ROI sara maggiore del ROD gli investimenti effettuati con capitale di terzi miglioreranno la capacita reddituale.
> ROI = ROD: siamo in presenza di una situazione di indifferenza economica. In tali casi l'indebitamento oneroso deve essere monitorato con frequenza specie in presenza di forme di indebitamento a tassi variabili. Un semplice rialzo dei tassi, non opportunamente bilanciato da una maggiore redditivita del capitale investito, potrebbe comportare un peggioramento dell'effetto leva riducendo la capacita reddituale.
> ROI < ROD: l'effetto dell'indebitamento oneroso e negativo, ovvero, maggiore e l'indebitamento oneroso, peggiore e il suo effetto in termini di redditivita (peggioramento degli indici di redditivita). Questo fenomeno, non opportunamente monitorato e non prontamente corretto, puo ingenerare un circolo vizioso in grado di innescare un peggioramento continuo della redditivita globale dell'azienda.

#### 4.4.6 Effetto di Leva Finanziaria
> L'indice rappresenta il rapporto fra l'indebitamento a breve e lungo termine (PC+PF) e il capitale netto (CN) e, benche non rappresenti propriamente un indice di redditivita, viene qui analizzato poiche rappresenta la c.d. "leva finanziaria". Maggiore e tale valore e maggiore e la leva finanziaria, cioe l'incidenza dei costi per l'indebitamento sulla redditivita dell'azienda.

#### 4.4.7 MOL sulle Vendite
> L'indice rappresenta il rapporto tra il margine operativo lordo (MOL) e le vendite (RIC) e misura la resa in termini di margine operativo lordo delle vendite effettuate consentendo di identificare l'incidenza dell'attivita caratteristica sul fatturato dell'azienda, prima degli effetti derivanti da ammortamenti e svalutazioni.
> Con tale indice si e in grado di valutare la capacita dell'azienda di ottenere un fatturato che, al netto della copertura dei costi esterni e dei costi del personale, generi un margine congruo alla remunerazione dei fattori produttivi impiegati ed alle aspettative della proprieta.

#### 4.4.8 Incidenza Oneri Finanziari sul Fatturato
> L'indice rappresenta il rapporto tra gli oneri finanziari (OF) e le vendite (RIC) e mette in evidenza quanta parte dei ricavi di vendita e assorbita dagli oneri finanziari.
> Non esiste una misura standard adeguata anche se e ritenuto che oltre certi livelli (6-8%) l'azienda si consideri oppressa dagli oneri finanziari e difficilmente in grado di sopravvivere, salvo che abbia elevati tassi di redditivita delle vendite (ROS).

#### 4.5 Indici di Efficienza (category intro)
> Gli indici di efficienza permettono di analizzare l'incidenza dei fattori produttivi sulla redditivita operativa dell'azienda.
> La crescita nel tempo di tali indici segnala il miglioramento dell'efficienza aziendale.

#### 4.5.1 Rendimento dei Dipendenti
> L'indice rappresenta il rapporto tra le vendite (RIC) e il costo del lavoro (CL) e misura la capacita delle vendite di coprire i costi del lavoro.

#### 4.5.2 Rendimento delle Materie
> L'indice rappresenta il rapporto tra le vendite (RIC) e il costo dei consumi (CO) e misura il "margine di contribuzione" delle vendite.
> Piu l'indice cresce e maggiore e il margine di contribuzione RICAVI - COSTO DELLE MATERIE.

#### 4.6 Break Even Point (intro)
> Il "break even point" (o punto di pareggio) e la quantita di ricavi necessari a coprire la totalita dei costi aziendali. Rappresenta il punto di equilibrio al di sopra del quale si realizza un profitto. Viceversa, sotto quel livello si misura una perdita.

#### 4.6.1 Ricavi BEP
> L'indice rappresenta il valore dei ricavi che consentono di raggiungere il "break even point".
> Nella nostra analisi corrisponde al volume di ricavi che porta ad azzerare il MON (Margine Operativo Netto) determinato nel "Conto Economico Riclassificato a Valore Aggiunto".
> L'importo e dato dal rapporto tra i Costi Fissi e la % del margine di contribuzione.
> La % del margine di contribuzione e data dal rapporto tra i Ricavi e il Margine di Contribuzione.
> Quest'ultimo valore e dato dalla differenza tra i Ricavi e i Costi Variabili.

#### 4.6.2 Margine di Sicurezza
> L'indice indica in che percentuale si discostano i Ricavi Break Even Point dai Ricavi effettivamente conseguiti. Maggiore e tale percentuale e maggiore e la differenza tra i Ricavi effettivi e i Ricavi Break Even Point, il che indica una maggiore capacita di coprire i costi fissi e aumentare la redditivita operativa dell'impresa (potendo in questo modo coprire eventuali altri oneri di gestione non caratteristica e finanziaria).

#### 4.6.3 Leva Operativa
> L'indice rappresenta, nella nostra analisi, il rapporto tra il Margine di Contribuzione e il Margine Operativo Netto (MON). Maggiore e tale indice e maggiore e il beneficio economico derivante da un incremento dei ricavi.

#### 4.6.4 Moltiplicatore dei Costi Fissi
> L'indice, dato dal rapporto tra 1 e il Margine di Contribuzione rapportato ai Ricavi (%MdC), indica di quanto devono aumentare i ricavi per ogni euro di incremento dei costi fissi perche si raggiunga il "Break Even Point".

#### 5. Z-Score di Altman
> Formula: (0,717 * A) + (0,847 * B) + (3,107 * C) + (0,42 * D) + (0,998 * E)
> A = (Attivita Correnti - Passivita Correnti) / Totale Attivita
> B = Utili accumulati e non distribuiti / Totale Attivita
> C = Risultato Operativo / Totale Attivita
> D = Capitale Netto / Debiti Totali
> E = Ricavi / Totale Attivita
>
> L'indice Z-Score di Altman serve per determinare con tecniche statistiche le probabilita di fallimento di una societa. Venne elaborato inizialmente da Edward I. Altman che nel 1968 sviluppo il modello previsionale Z-Score analizzando i dati di bilancio di 66 societa quotate americane, 33 delle quali erano societa solide e 33 delle quali erano societa fallite, con un grado di accuratezza del 95%.
> Sono evidenti i limiti dell'indice di Altman che fotografa un mercato (quello delle quotate americane) totalmente diverso da quello delle PMI italiane e che e scarsamente applicabile nella previsione dell'insolvenza ex ante. Per mitigare almeno in parte i limiti di cui sopra la formula originaria e stata riformulata per renderla piu adattabile alle PMI italiane. Va, in ogni caso, tenuto conto che tale formula e stata elaborata per analizzare societa del comparto manifatturiero e che non tiene conto del fattore "stagionalita" ne, per esempio, di eventuali plusvalori di beni patrimoniali rispetto all'importo indicato a stato patrimoniale. Inoltre, nella lettura dell'indice, va tenuto conto che relativamente alla componente "D = Capitale Netto / Totale Passivita" la formula prevedere l'utilizzo del valore di mercato del "Capitale Netto", e non il valore contabile dello stesso, risultando cosi, in generale, sottovalutata questa componente del calcolo. L'utilizzo del valore di mercato, che in situazioni normali e maggiore del valore contabile, porterebbe a valori migliori dell'indice.
> Resta comunque un indice di riferimento per confrontare i risultati di diversi periodi (per un'analisi di tipo tendenziale) o quelli di diverse aziende.

#### 6. EM-Score di Altman
> Formula: 3,25 + 6,56 * X1 + 3,26 * X2 + 6,72 * X3 + 1,05 * X4
> X1 = Capitale Circolante Netto / Totale Attivita
> X2 = Utili Non Distribuiti / Totale Attivita
> X3 = Risultato Operativo / Totale Attivita
> X4 = Capitale Netto / Debiti Totali
>
> L'EM-Score e un indice che deriva, rappresentandone una evoluzione, dallo Z-Score e permette di ottenere una valutazione del rating del debito delle imprese. L'indice risulta essere un valido strumento per analizzare lo stato di solvibilita di una azienda.
> Il rating del debito e facilmente individuabile da una chiave di lettura con classi di rating, di cui allo schema su riportato, e da una immediata lettura del significato di questo. Altman propone un massimo di 8,15 nel livello di EM-Score il quale corrisponde a un debito con rating "AAA". Al decrescere si arriva a al rating "D", a cui corrisponde una situazione di elevata probabilita di default dell'impresa.
> E opportuno che il rating venga calcolato su piu esercizi per monitorare l'andamento nel tempo e verificare se la tendenza sta migliorando o peggiorando.

#### 7. Rating FGPMI
> Le piccole e medie imprese possono accedere a finanziamenti mediante la concessione di una garanzia pubblica da parte del Fondo di Garanzia Mediocredito Centrale. La garanzia e pero concessa solo alle imprese valutate "economicamente e finanziariamente sane" sulla base dei dati contabili degli ultimi due esercizi.
> I criteri di valutazione variano a seconda del settore di attivita.
> Nella sua applicazione integrale, oltre alle valutazioni basate sugli indici qui riportati, vengono presi in considerazione anche elementi "extracontabili", come ad es. la presenza di sconfinamenti, rate di finanziamenti scadute, segnalazioni da parte della "Centrale Rischi". Rispetto al precedente rating la complessita e maggiore in quanto l'aspetto "Economico/Finanziario" e solo una parte relativa alla valutazione dell'azienda per poter accedere al "Fondo di Garanzia".
> L'intreccio delle valutazioni sia dei dati contabili che di quelli extracontabili portano all'assegnazione di classi di rischio in base al quale valutare la solvibilita dell'azienda.
> Relativamente al "Modulo Economico Finanziario", basato sugli indici di bilancio, all'azienda viene assegnata una classe di rischio che va da 1 a 11 dove piu e alta la classe e maggiore e il rischio di insolvenza.
> Il rating utilizzato si limita evidentemente alla valutazione dei dati contabili; sebbene la valutazione del solo modulo economico finanziario non sia da considerarsi esaustiva, risulta comunque importante per verificare il proprio posizionamento rispetto alla "situazione contabile" dell'azienda.

#### 8.1 Monetizzazione delle Vendite
> L'indice, denominato anche "ROS monetario", misura la capacita dell'impresa di produrre risorse monetarie dalle vendite.
> Maggiore e l'indice e maggiore e la capacita dell'impresa di trasformare valori economici in valori monetari.

#### 8.2 Liquidita del Reddito Operativo
> L'indice rappresenta la capacita del risultato operativo di convertirsi in moneta.
> Non sempre un elevato risultato operativo e indice di elevata capacita monetaria poiche lo stesso puo essere assorbito nel magazzino o nei crediti.
> L'interpretazione di tale indice varia in base al segno del denominatore (RO).
> Risultato operativo > 0: Indice positivo = giudizio positivo (quanto maggiore e l'indice tanto maggiore e la capacita della gestione di creare liquidita). Indice negativo = giudizio negativo (sui risultati reddituali incidono in modo significativo i ricavi non monetari oppure il ciclo monetario e particolarmente lungo).
> Risultato operativo < 0: Indice positivo = giudizio negativo (quanto maggiore e l'indice tanto peggiore e il giudizio sulla situazione finanziaria). Indice negativo = giudizio positivo (sui risultati reddituali incidono in modo significativo i costi non monetari oppure l'azienda beneficia di un ciclo monetario favorevole).

#### 8.3 Autofinanziamento
> Evidenzia la capacita del risultato operativo di trasformarsi in flusso di circolante ed e determinato da costi non monetari quali ammortamenti, accantonamenti, svalutazioni.
> Il giudizio dipende dal segno del denominatore: se il risultato operativo e positivo l'indice dovrebbe assumere, preferibilmente, un valore > 1 sfruttando l'incidenza di costi non monetari; se il risultato operativo caratteristico e negativo l'indice dovrebbe assumere un valore < 1 o, preferibilmente, di segno negativo.

#### 8.4 Conversione in Liquidita dell'Autofinanziamento
> L'indice rappresenta la capacita del flusso circolante di convertirsi in moneta ed e influenzato dalle politiche delle scorte di magazzino e di dilazione dei crediti e debiti commerciali.
> Il valore oscilla tra 0 ed 1: quanto piu l'indice si avvicina all'unita tanto piu sono positivi i riflessi in termini di liquidita.

#### 8.5 Copertura degli Investimenti Netti
> L'indice misura il grado di copertura degli investimenti con le liquidita autogenerate. Se il valore di tale indice e > 1 l'azienda dispone di autonomia finanziaria nella gestione degli investimenti e non ha necessita di ricorrere a fonti esterne di finanziamento.
> L'indice e non significativo se negativo perche i disinvestimenti sono maggiori degli investimenti.

#### 8.6 Incidenza della Gestione Caratteristica Corrente
> L'indice dovrebbe avere un valore superiore all'unita; in particolare: se il flusso finanziario netto (A+/-B+/-C) e positivo il valore dell'indice non dovrebbe mai scendere al di sotto dello zero in quanto la gestione corrente dovrebbe essere la principale area di produzione della liquidita. Se il flusso finanziario netto (A+/-B+/-C) e negativo il valore dell'indice dovrebbe assumere un valore negativo mantenendo comunque un valore assoluto superiore all'unita.

---

## GAP 2: EM-Score Description Mismatch (MEDIUM)

Our `report-types.ts` uses different descriptions from the PDF. Must update:

| Rating | Our Current (WRONG) | PDF Correct |
|---|---|---|
| AAA | Sicurezza massima | Rischio di credito estremamente basso |
| AA+/AA/AA- | Sicurezza elevata / Ampia solvibilita | Rischio di credito molto basso |
| A+/A/A- | Solvibilita / Solvibilita sufficiente | Aspettativa bassa di rischio di credito |
| BBB+/BBB/BBB- | Vulnerabilita / Vulnerabilita elevata | Capacita di rimborso adeguata |
| BB+/BB/BB- | Rischio / Rischio elevato | Possibilita di rischio di credito |
| B+/B/B- | Rischio molto elevato / Rischio altissimo | Significativo rischio di credito |
| CCC+/CCC/CCC- | Rischio di insolvenza / Insolvenza imminente | Forte possibilita di insolvenza |
| D | Insolvenza | Possibile stato di default |

---

## GAP 3: Structural Cross-Matrices (HIGH)

PDF sections 3.4-3.6 show 2x2 relationship assessment matrices. Must add to `report-structural.tsx`.

### 3.4 Relazione MT vs MS

|  | MT Positivo | MT Negativo |
|---|---|---|
| **MS Positivo** | SITUAZIONE OTTIMALE: Adeguata gestione liquidita, livello adeguato capitalizzazione, ottima capacita di credito, possibilita utilizzo liquidita in eccesso | PROBLEMI DI SOLVIBILITA: Difficolta gestione tesoreria, incidenza elevata oneri finanziari, riduzione problemi se esiste capacita credito non utilizzata |
| **MS Negativo** | SCARSA SOLIDITA PATRIMONIALE: Incongruenza tempi scadenza fonti/impieghi, deterioramento affidabilita sistema creditizio, diminuzione capacita competitiva, difficolta dinamica finanziaria | SITUAZIONE PATOLOGICA: Incongruenza tempi scadenza fonti/impieghi, deterioramento affidabilita sistema creditizio, diminuzione capacita competitiva, difficolta dinamica finanziaria |

### 3.5 Relazione CCN vs MS

|  | CCN Positivo | CCN Negativo |
|---|---|---|
| **MS Positivo** | SITUAZIONE OTTIMALE: Livello adeguato capitalizzazione, ottima capacita credito, buona gestione finanziaria | IPOTESI NON POSSIBILE: Se MS positivo non puo essere negativo CCN |
| **MS Negativo** | SCARSA SOLIDITA: Insufficiente capitalizzazione, difficolta ricorso credito, situazione finanziaria difficile (attivita fisse finanziate con debiti medio/lungo) | SITUAZIONE DI ESTREMO PERICOLO: Immobilizzazioni finanziate da passivita correnti, insufficiente capitalizzazione, notevole incidenza oneri finanziari, deterioramento capacita credito, ridotta capacita investimento e sviluppo |

### 3.6 Relazione CCN vs MT

|  | CCN Positivo | CCN Negativo |
|---|---|---|
| **MT Positivo** | SITUAZIONE OTTIMALE: Struttura fonti/impegni buona, ridotta entita rimanenze, buona capacita credito | IPOTESI NON POSSIBILE: Se CCN negativo non puo essere positivo MT |
| **MT Negativo** | SITUAZIONE SCARSA LIQUIDITA: Elevato investimento scorte, buona struttura fonti/impegni ma liquidita ridotta | SITUAZIONE CRITICA: Immobilizzazioni finanziate da debiti correnti, elevato investimento scorte, scarsa liquidita |

---

## GAP 4: Cashflow Ratios - 6 Indices (HIGH)

PDF section 8 has 6 cashflow-specific ratios completely missing from `report-cashflow.tsx`.

| # | Index | Formula |
|---|---|---|
| 8.1 | Monetizzazione Vendite | Flusso operativo (A) / Vendite (RIC) |
| 8.2 | Liquidita Reddito Operativo | Flusso operativo (A) / Risultato Operativo (RO) |
| 8.3 | Autofinanziamento | Flusso dopo variazioni CCN / Risultato Operativo (RO) |
| 8.4 | Conversione Liquidita | Flusso operativo (A) / Flusso dopo variazioni CCN |
| 8.5 | Copertura Investimenti Netti | Flusso operativo (A) / Flusso investimento (B) |
| 8.6 | Incidenza Gestione Caratteristica | Flusso operativo (A) / Flusso netto (A+B+C) |

Note: These may need backend calculation support or can be computed frontend-side from existing cashflow data.

---

## GAP 5: Missing Appendix Sections (MEDIUM)

| PDF Section | Status | Content |
|---|---|---|
| 9.1 SP | HAVE | Raw balance sheet |
| 9.2 CE | HAVE | Raw income statement |
| 9.3 Variabili Scenari | MISSING | Budget assumption variables per forecast year |
| 9.4 SP Riclassificato | MISSING | Reclassified BS: LI, LD, RD, AF, PC, PF, CN |
| 9.5 CE Riclassificato | MISSING | Reclassified IS: RIC, VP, CO, AC, VA, CL, MOL/EBITDA, MON, RO/EBIT, Utile Ordinario, EBT, RN |
| 9.6 Rendiconto Finanziario | MISSING | Full indirect cashflow statement |

---

## GAP 6: Formula Displays (MEDIUM)

Altman and EM-Score sections should show their formulas prominently.

- **Altman**: `(0,717 * A) + (0,847 * B) + (3,107 * C) + (0,42 * D) + (0,998 * E)` with component definitions
- **EM-Score**: `3,25 + 6,56 * X1 + 3,26 * X2 + 6,72 * X3 + 1,05 * X4` with component definitions

---

## GAP 7: Break-Even Extras (LOW-MEDIUM)

Missing from `report-break-even.tsx`:
- **4.6.3 Leva Operativa**: Chart showing MdC vs MON + leva operativa line. Formula: MdC / MON
- **4.6.4 Moltiplicatore Costi Fissi**: Formula: 1 / %MdC

---

## Implementation Priority

1. **Italian descriptions** for all ratios/indices (biggest visual gap)
2. **Structural cross-matrices** (3.4-3.6) with situation assessments
3. **Cashflow ratios** (6 indices in section 8)
4. **EM-Score descriptions** fix (wrong Italian text in report-types.ts)
5. **Appendix additions** (reclassified BS/IS, cashflow statement, scenario variables)
6. **Formula displays** for Altman + EM-Score
7. **Break-even extras** (Leva Operativa, Moltiplicatore)
