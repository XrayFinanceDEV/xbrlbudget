# Dossier Report Budget — specifica consolidata

**Data:** 2026-09-15

**Stato:** requisiti concordati per implementare il dossier di produzione.

**Dipendenze:** [Report finale della pratica](2026-09-13-report-finale-pratica-design.md),
[PDF Typst](2026-09-13-report-pdf-typst-design.md),
[piano di implementazione](../plans/2026-09-13-report-finale-e-pdf-typst.md).

Questa spec consolida le richieste successive al milestone M1: estetica del dossier
CR, approfondimento degli indicatori, Allegati completi, commento per ogni pagina
e titolo neutrale. Prevale sui passaggi precedenti che prevedevano una conclusione
finanziaria come titolo o la sospensione in attesa del formato estetico.
Lo spike tecnico e i relativi gate rimangono necessari; l'anteprima Chromium è
un riferimento grafico e non il renderer ufficiale.

## 1. Titolo e identità

Il titolo è `Report Budget {primo anno} - {ultimo anno}`. Esempi:

| Orizzonte del budget | Titolo |
|---|---|
| 2027 | Report Budget 2027 |
| 2027, 2028, 2029 | Report Budget 2027 - 2029 |
| 2027–2031 | Report Budget 2027 - 2031 |

Gli anni sono gli anni di previsione effettivi, ordinati, dichiarati dal backend.
La chiusura stimata 2026 non entra nel titolo di un budget 2027–2029. L'assenza
degli anni necessari è un'incompletezza della pratica; non si inventa un periodo.
Il titolo è identico in copertina, metadati PDF e intestazione principale web.
Non dipende dall'AI, dalle conclusioni o dal testo dei commenti.
Azienda, scenario, data infrannuale, chiusura, preparatore e stato sono metadati
separati. Margini e indebitamento si commentano nella sintesi e nelle sezioni.

## 2. Composizione

La stampa riprende il dossier CR: A4 verticale, copertina blu petrolio, IBM Plex
Sans incorporato, KPI laterali, grafici essenziali, tabelle con righe sottili,
fonti, header/footer e indice. Mantiene la palette della spec PDF e una resa
leggibile in scala di grigi. La leggibilità prevale sul numero di pagine.

Le dodici sezioni logiche M1 rimangono stabili; la dodicesima si presenta come
**Allegati e metodologia**. Gli approfondimenti possono occupare più pagine:

1. copertina e perimetro;
2. sintesi esecutiva;
3. dati di partenza e qualità;
4. rettifiche e riconciliazione;
5. chiusura attesa, solo per la pratica infrannuale;
6. ipotesi del piano;
7. conto economico previsionale;
8. stato patrimoniale previsionale;
9. flussi di cassa e sostenibilità;
10. indicatori e relativi approfondimenti;
11. diagnostica e azioni;
12. Allegati e metodologia.

I tre workflow rimangono supportati. Osservato, rettificato, stimato a chiusura e
previsionale sono distinti tramite periodo e legenda. Non si equiparano nove mesi
di conto economico a dodici senza una nota di comparabilità.
L'anteprima v4 illustra il livello di dettaglio; le sue 33 pagine non sono un vincolo.
La successiva correzione del titolo sostituisce la frase di copertina dell'anteprima.

## 3. Modello canonico v2

Il dossier richiede `FinalReportModel v2`. Il v1 implementato ha una validazione
di esattamente sei serie e sei blocchi principali; ampliare quelle serie come se
fossero v1 romperebbe i client attuali. Il backend assembla il v2 dagli stessi
servizi e dati persistiti. React e Typst non accedono a endpoint separati di analisi
per completarlo e non calcolano formule, subtotali, classificazioni o punteggi.

Il v2 conserva i blocchi economici M1 e aggiunge questi contratti:

| Blocco | Contenuto minimo |
|---|---|
| `document` | titolo neutrale, anni del budget, lingua, unità di presentazione |
| `detailed_statements` | CE, SP e rendiconto: periodi, righe ordinate, codice, etichetta, padre, livello, tipo riga, applicabilità, valori e fonte |
| `indicator_catalog` | ID, etichetta, unità, convenzione/metodologia, base e periodo, valori nullable, ragioni di indisponibilità e soglie soltanto se autorevoli |
| `chart_series` | sei serie M1 conservate e serie aggiuntive del dossier con identificatori stabili |
| `editorial_plan` | versione layout, font/asset, hash piano, pagine ordinate, contenuti e parti di prospetto, riferimenti alle note e limiti dello spazio riservato |
| `editorial_notes` | ID stabile, contenuti di riferimento, testo, provenienza, data, hash delle fonti, revisione e freschezza |

I valori finanziari rimangono decimal string; zero e null sono distinti.
I metadati delle unità eliminano l'ambiguità dei calcoli v1 appiattiti senza unità.
Le gerarchie e i subtotali sono espliciti, non dedotti dal renderer dai codici.
Il piano editoriale non contiene formule di bilancio.

La transizione è esplicita: `GET final-report?schema_version=2` serve il dossier,
mentre il default v1 viene mantenuto durante l'aggiornamento del client. Il client
nuovo richiede v2; il server dichiara sempre la versione restituita. Una versione
non supportata produce un errore esplicito. Fixture e test v1 restano di regressione;
non vengono rigenerati silenziosamente come v2. Il cambio del default, se necessario,
è un rilascio coordinato dopo il collaudo del nuovo client.

## 4. Indicatori e grafici

Il catalogo parte dai quindici `INDICATOR_DEFS` della pratica e dalle famiglie di
`report-ratios`: liquidità, solvibilità, redditività, copertura, rotazione,
redditività estesa ed efficienza. Mantiene nomi, unità e convenzioni delle fonti.

| Approfondimento | Rappresentazione preferita |
|---|---|
| Infrannuale e chiusura | punti collegati con valori espliciti e nota sulla durata |
| CCN, tesoreria e struttura | barre divergenti e linea dello zero |
| Liquidità corrente e immediata | linee affiancate con unità in volte |
| ROI, ROE, ROS e margini | piccoli grafici omogenei in percentuale |
| Autonomia e copertura immobilizzazioni | andamento e soglie disponibili dal modello |
| PFN/EBITDA e coperture del debito | grafici distinti quando basi e scale differiscono |
| DSO, DIO, DPO e ciclo monetario | linee in giorni, con base di calcolo dichiarata |
| Impieghi, fonti e incidenze economiche | barre al 100% e confronti delle incidenze |
| Ricavi, break-even e margine di sicurezza | ricavi/pareggio e grafico percentuale separato |
| Altman, FGPMI ed EM-Score disponibili | andamento e componenti/classi del servizio autorevole |

Non tutte le rappresentazioni sono obbligatorie quando mancano i dati. Il motivo
è dichiarato; non si completa una serie con zero né si inventano classi o soglie.
Il DSCR della pratica e altre coperture con convenzioni differenti hanno metadati
e label che le distinguono. Il renderer non sostituisce una formula con un'altra.
I grafici sono vettoriali e accompagnati da valori tabellari o rinvio agli Allegati.

## 5. Allegati completi

Gli Allegati hanno un indice con pagine effettive e rinvii dal corpo:

- CE completo, comprese componenti economiche e subtotali disponibili;
- SP completo, con crediti/debiti entro e oltre dodici mesi, riserve e sottovoci;
- rendiconto indiretto completo e riconciliazione della cassa;
- rettifiche, contropartite, motivazioni e riconciliazione prima/delta/dopo;
- matrice di tutte le ipotesi applicabili e provenienza per anno;
- prestiti, debiti pregressi, scadenziamenti e differenze temporanee disponibili;
- tabella completa degli indicatori e dettaglio dei punteggi disponibili;
- metodologia e fonti.

La copertura segue `INCOME_STATEMENT_ROWS`, `BALANCE_STATEMENT_ROWS` e la struttura
`CF_ROWS` già presenti nel progetto. I conteggi del campione (47 CE, 86 SP, 47 CF)
sono riferimenti dell'attuale catalogo, non numeri da fissare nei test di produzione.
I controlli confrontano gli ID e la molteplicità delle righe applicabili del modello.
Nessun Allegato è soltanto un rinvio ai prospetti sintetici. In stampa i prospetti
sono aperti per intero, ripetono gli header e mantengono il contesto della voce padre
nelle continuazioni. Dati o dettagli indisponibili sono dichiarati.

## 6. Commento su ogni pagina

Ogni pagina fisica contiene una nota pertinente, anche breve, inclusi copertina,
indice, continuazioni degli Allegati e metodologia. Due o tre frasi sono normalmente
sufficienti. Il corpo può conservare i sei commenti principali più articolati.
Le note dei prospetti spiegano le voci o i movimenti esposti; non duplicano la
stessa conclusione su tutte le pagine di un Allegato.

Il piano editoriale viene costruito prima della generazione delle note, con font,
dimensioni dei grafici e spazio dei commenti fissati. Le parti dei prospetti hanno
ID basati sul contenuto e sulle righe, non sul solo numero di pagina. I limiti di
una nota sono verificati con le metriche del font e del riquadro; non si troncano
commenti manuali per farli rientrare. Le pagine non possono espandersi implicitamente
oltre il piano: se la composizione cambia si ricalcolano piano e associazioni.

La preparazione del piano è deterministica e non invoca l'AI. La generazione AI
è un'azione esplicita, in batch di contesti pertinenti; produce i sei blocchi
principali e le note richieste dal piano. Una nota di lettura neutrale può essere
costruita dal backend dal perimetro e dai metadati, con provenienza `automatic`:
non è presentata come una valutazione AI e non inventa risultati finanziari.
Il budget di token e la dimensione dei batch dipendono dal numero dei contenuti;
una risposta parziale non è trattata come copertura completa. Le note valide
già salvate restano disponibili quando un batch fallisce, con diagnostica dei
contenuti mancanti e possibilità di rigenerare soltanto quelli interessati.
Queste note di base consentono la copertura anche senza il provider AI; il backend
le include nel modello canonico. Le note AI e quelle dell'utente sono persistite;
le note automatiche sono riproducibili e fanno parte dello snapshot esportato.

Il client permette di modificare le note, vedere provenienza/freschezza e
rigenerare i soli contenuti selezionati. Le modifiche manuali non sono sovrascritte.
Gli ID non riconosciuti, un piano superato o conflitti di revisione sono rifiutati
esplicitamente. Un testo che non rientra nel limite editoriale è segnalato prima
del salvataggio/esportazione, senza tagli silenziosi.

Le nuove operazioni di preparazione/generazione/salvataggio ricevono solo gli ID
e le revisioni attese; il backend ricostruisce il contesto autorizzato. Non si
accetta dal browser il dato finanziario come fonte per la generazione. `GET` resta
senza scritture e senza chiamate AI. L'export usa piano e note dello snapshot,
non rigenera testi e non avvia una chiamata LLM per ogni pagina.

Il cambio di una fonte rende osservabile la freschezza delle note interessate;
quello di layout, font o parti dei prospetti invalida le associazioni del piano.
Gli hash economici e del piano escludono il testo generato, così una generazione
non rende immediatamente obsoleta se stessa. Il `model_hash` finale include i testi.

## 7. Prontezza e validazione

La readiness economica M1 rimane valida. Il PDF finale verifica inoltre piano
attuale e una nota valida per ogni pagina; note mancanti, associazioni errate o
commenti che non rientrano nel riquadro impediscono un PDF finale incompleto.
I blocchi AI principali possono mantenere i warning già previsti quando una nota
breve neutrale e valida copre comunque la pagina. Lo stato delle note obsoletate
è dichiarato; le note richieste per la finalizzazione devono riferirsi alle fonti
correnti, oppure essere revisionate esplicitamente dall'utente.

Il draft usa note di lettura di base fornite dal backend quando disponibili e
mantiene watermark e diagnostica. Il renderer non inventa commenti finanziari.
Un fallimento di impaginazione è un errore del documento, non una correzione
silenziosa dei dati della pratica.

Accettazione:

1. titoli neutrali corretti per orizzonti di uno, tre e cinque anni;
2. documenti coerenti nei workflow infrannuale, bilancio e startup;
3. dati e subtotali identici tra modello, web e PDF;
4. Allegati con tutte le righe applicabili, senza ritagli o perdite;
5. commento presente nel PDF per ciascuna pagina del piano, verificando il testo;
6. note brevi senza duplicazioni automatiche e testi manuali protetti;
7. null, negativi, etichette lunghe e note al limite gestiti correttamente;
8. cambio di dati/layout con freschezza e associazioni aggiornate;
9. font e grafici leggibili, offline, vettoriali e verificati in scala di grigi;
10. transizione v1/v2, auth, ownership e validazione del PDF coperti dai test.

## 8. Sequenza di consegna

Il piano aggiunge M2-00B (contratto/assembler v2), M2-02A (piano editoriale e metriche)
e M2-00C (note e client v2). Il runtime e il gate Typst restano indipendenti dalla
conferma estetica. Grafici a dimensioni fissate precedono il completamento del
piano; note e template definitivo consumano quel piano. Harness semantico,
API PDF, packaging e collaudo chiudono la consegna. I task già integrati di M1
non si riaprono: la loro estensione è esplicita nei nuovi task M2.
