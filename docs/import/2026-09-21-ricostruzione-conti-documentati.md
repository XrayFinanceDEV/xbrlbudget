# Importazione: ricostruzione dai conti documentati

Branch `feat/import-analytical-details`; parser `source-ledger-v6-2026-09-21`.

## Perché la sequenza precedente non bastava

La sequenza «macro-voci → dettagli → quadratura» era presente, ma l'ipotesi iniziale
veniva spesso trattata come definitiva. Un dettaglio iniziale sbagliato era protetto
contro le correzioni; una macro-voce erroneamente nulla escludeva la famiglia dalla
ricerca. Inoltre, chiudere le somme non dimostrava che i conti fossero nella famiglia
giusta: liquidità/debiti bancari e clienti/altri crediti potevano essere sbagliati
anche in uno SP apparentemente quadrato.

Questa integrazione introduce una ricostruzione indipendente dalla prima ipotesi.
Non abilita una correzione arbitraria delle macro-voci: può sostituirle soltanto
quando le righe utilizzate ricostruiscono i controlli stampati nella fonte.

## Responsabilità distinte

1. **Fonte e gerarchia** (`ledger_evidence.prepare_ledger`): separa SP e CE anche
   nella stessa pagina, riconosce la gerarchia dei codici e seleziona conti disgiunti.
   Padre e figli non vengono mai sommati insieme. Riporti identici si contano una
   volta; codici ripetuti con importi discordanti richiedono riconciliazione.
2. **Dettagli parziali**: se i figli positivi coprono solo parte del padre, conserva
   i figli e crea il residuo esatto `padre − figli`, con riferimenti e formula
   nell'audit. Non lo presenta come un nuovo conto letto. Se i figli eccedono il
   padre, conserva il padre: non inventa un residuo negativo compensativo.
3. **Interpretazione LLM**: ogni conto selezionato riceve una destinazione e una
   motivazione. Il modello riceve anche le descrizioni delle destinazioni dallo
   schema esistente; non può restituire importi da contabilizzare. Risposte
   incomplete vengono riparate richiedendo solo gli ID mancanti, duplicati o
   incompatibili, senza perdere le classificazioni già valide. I tentativi sono
   limitati; l'esaurimento produce una revisione esplicita.
4. **Vincoli semantici**: il lato del prospetto, gli antenati, la natura esplicita
   della controparte e la scadenza documentata vincolano l'assegnazione. Fondi
   ammortamento/svalutazione rettificano attività; conti bancari passivi non
   aumentano la cassa. Finanziamenti soci e debiti per compensi non diventano
   banche. Restano registrati campo proposto, campo applicato e regola utilizzata.
5. **Riduzione contabile**: `Decimal`, importi e segni della fonte, somma dei
   sottoconti nelle macro-voci, controlli indipendenti di SP e CE. Il risultato SP
   resta quello stampato nello SP; non è riscritto prendendo quello del CE.
6. **Ricerca aggiuntiva e chiusura**: restano attivi la ricerca per blocchi delle
   note/dettagli e il finalizzatore dei residui. La nuova prova può rimuovere una
   classificazione iniziale sbagliata prima di queste fasi. Non vengono alterati
   cassa, utile o altre famiglie per compensare una differenza.

Le scadenze seguono la convenzione richiesta: in assenza di indicazioni, breve;
mutui/finanziamenti, anche soci, lungo. Una scadenza esplicita prevale. Un conto
operativo figlio (anticipazioni, c/c, interessi maturati) non diventa lungo solo
perché il suo padre ha una descrizione generica di finanziamento. Le convenzioni
gestionali sono distinguibili dalla scadenza documentata nell'audit.

Il modello dati non ha una voce «rimanenze non classificate»: nei residui della
nuova ricostruzione resta la convenzione prudente materie prime, salvo natura del
padre documentata. L'audit identifica l'importo convenzionale; non attesta che sia
stato trovato un dettaglio materie prime nella fonte.

## Correzioni complementari

- `legal_path_evidence.py`: legge percorsi qualificati IV CEE e colonne datate,
  distinguendo numero di riga, corrente, comparativo, differenza e percentuale.
  Mantiene centesimi e saldi negativi, senza usare una colonna di variazione come
  saldo. Famiglie incomplete riconosciute non diventano successi silenziosi.
- `detail_enrichment.py`: delimitazione SP/CE per posizione nella pagina,
  riutilizzo del separatore tra sezioni contrapposte, esclusione delle date dai
  codici conto, scadenze abbreviate e tutela delle scadenze già provate.
- `_debt_type`: `C/COMPENSI` non è `C/C`; ritenute sindacali non sono debiti
  tributari; corretta distinzione di finanziamenti soci e forme previdenziali.
- Controllo CE/SP: eliminata la tolleranza proporzionale all'attivo. Le nuove
  ricostruzioni richiedono i controlli della fonte esatti; gli altri percorsi
  mantengono la tolleranza assoluta passata dal chiamante.
- Revisione della fonte vincolante anche per il comparativo. Mancata lettura
  semantica su un ledger supportato non produce una certificazione positiva.
- Diagnosi degli sbilanci: passività prima dell'utile più utile stampato non
  devono essere denunciate come uno sbilancio del documento.

## Verifica

Suite mirata di regressione: **376 superati, 7 saltati**, nessun fallimento.
Copre anche i percorsi preesistenti IV CEE, AGO, dettagli, rettifiche, quadratura,
CSV e XBRL. I nuovi test verificano residui parziali, doppio conteggio, ID mancanti
o duplicati, recupero selettivo LLM, vincoli di lato/scadenza, indisponibilità del
lettore, centesimi, comparativi e incongruenze CE/SP. I PDF privati sono opzionali:
i relativi test sono saltati quando il corpus non è presente.

Importazioni reali: stesso orchestratore dell'API, LLM configurato del progetto,
database SQLite separati in memoria. Riferimento indipendente dalla precedente
lettura visiva delle 16 pagine, non generato dai classificatori modificati.
Artefatti completi di questa sessione in `/tmp/budget-evidence-v6.kD70Zr/`;
riferimento e prova precedente in `/tmp/budget-final-vision.iWzqfi/`.

### Risultati delle importazioni complete

| Documento | SP netto attivo = passivo | Risultato CE / SP | Esito persistito |
|---|---:|---:|---|
| 948 — PMI giugno 2026 | 2.888.604,35 | 200.220,95 / 200.220,95 | `verified`, previsione abilitata |
| 949 — PMI giugno 2025 | 2.584.168,34 | 48.649,70 / 47.903,81 | `unbalanced`, previsione bloccata |
| 967 — COMAP 2025 | 1.125.225,58 | 32.368,64 / 32.368,64 | `verified`, previsione abilitata |
| 967 — COMAP 2024 | 688.939,96 | 220.177,52 / 220.177,52 | `verified`, previsione abilitata |
| 972 — Gerevini 2026 | 2.023.297,78 | 109.083,04 / 109.083,04 | `verified`, previsione abilitata nel test |

**197 campi SP/CE confrontati, nessuna differenza dal riferimento indipendente.**
Il confronto riguarda i campi trascritti nel riferimento, non una certificazione
di ogni possibile classificazione contabile del documento. Le ultime prove
complete hanno richiesto circa 39 s (948), 36 s (949), 7 s (967), 42 s (972).
Le risposte LLM registrate per 949 e 972 sono state anche ricalcolate con gli
ultimi vincoli, ottenendo lo stesso riferimento.

Nel 949 la differenza di **745,89** è realmente stampata tra i due prospetti:
la fonte è trascritta correttamente, ma non viene promossa a bilancio coerente.
Nessuna compensazione in utile, riserve, crediti o debiti.

Nel 972 sono ricostruiti, fra gli altri:

- crediti brevi **396.123,06**: clienti **311.134,11**, tributari **34.193,32**,
  altri **50.795,63**;
- debiti brevi **741.211,64**, distinti dai finanziamenti a lungo;
- debiti lunghi **785.059,38**: banche **725.059,38**, socio **60.000,00**;
- rimanenze SP **191.524,62** e variazioni CE distinte per materia prima e
  prodotto finito; fondi ammortamento e svalutazione nettati una sola volta.

**Avvertenza sul periodo del 972:** il nome indica 31 luglio, l'intestazione
movimenti arriva al 7 agosto. Il test usa sette mesi come ipotesi; la verifica
contabile non certifica tale periodo. Va chiarito prima di usare la previsione.

Durante le ripetizioni sono emerse anche classificazioni LLM errate pur con
quadratura esatta: ritenute sindacali, plusvalenze su cespiti, pedaggi, altri
accantonamenti e saldi fornitori in attivo. Sono state aggiunte prove di
regressione e vincoli sulle descrizioni esplicite; non sono stati inseriti nomi
di aziende, nomi di PDF o importi attesi nelle regole di produzione.

La suite è eseguita con `DATABASE_PATH=:memory:`, `REPORT_GATE_NO_DOTENV=1`
e `PYTHONPATH=.`; le importazioni con LLM usano `tests._import_probe`, che
sostituisce esplicitamente connessione e sessioni con un database in memoria.

## Limiti

Questa è una correzione verificabile dei percorsi esaminati, non una garanzia
universale su qualunque PDF. Il nuovo lettore di conti richiede testo nativo,
gerarchia e totali indipendenti riconoscibili; non sostituisce l'OCR delle
scansioni. Un modello può ancora sbagliare il significato di descrizioni ambigue:
la quadratura da sola non dimostra la correttezza semantica di ogni classificazione.
I limiti e i fallimenti di ricerca restano nel rapporto, con revisione quando
fallisce la ricostruzione supportata.

Non sono state modificate le pratiche esistenti nel database del progetto.
Per aggiornare gli import precedenti occorre una reimportazione con questo parser.
