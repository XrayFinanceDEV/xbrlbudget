# Report infrannuale (ReportLab) — specifica

**Data:** 2026-09-23 · **Branch:** `feat/report-infrannuale` (worktree `../budget-report-inf`, da `main` 2a6ce25)

**Riferimento:** `INFRANNUALE RIVISITATO.pdf`, preparato dal committente (13 pagine, ReportLab + matplotlib, font
Carlito, AMBIENTA 6M 2026). Il file non va in git: il banco lo legge da `tests/.banco-infrannuale/riferimento.pdf`
(gitignored); se manca, i test che lo usano si saltano.

**Spike che fa da banco:** le pagine 4, 6 e 9 ricostruite con il motore del Business plan sugli stessi numeri
coincidono col riferimento entro 0,2 pt su tutti i riquadri, le fasce, le tabelle e i grafici (artifact
`https://claude.ai/artifact/2WCHzurKBSvu5whqGqLvQq`). Il proprietario ha approvato la resa («ok procediamo»).

**Fatto che cambia il banco rispetto al Business plan:** i numeri del riferimento sono quelli del nostro motore.
DSCR 3,026×, margine di tesoreria −67.802,56, ROE del semestre 20,85%, classi D / C2 / D coincidono con
`crisi_infrannuale` sullo scenario infrannuale di AMBIENTA (azienda 575, scenario 17) del DB locale. Il banco
quindi confronta anche le cifre, non solo il layout.

## 1. Che cosa si costruisce

Un nuovo PDF del percorso infrannuale che **sostituisce** il report intermedio Typst come documento scaricato
dalla tab Stampa. Riproduce il layout del riferimento: copertina con i numeri chiave e l'indice, sezioni 1–8,
Allegati A–B, con i numeri della pratica, qualunque essa sia.

Il report intermedio Typst (`intermedio_catalog.py`, `intermedio_renderer.py`, `templates/intermedio/`, rotta
`POST …/infrannuale/report/pdf`) **resta nel codice e nei suoi test**, ma la Stampa non lo chiama più. Il dossier e il
Business plan non si toccano.

## 2. Decisioni prese con il proprietario

| # | Decisione |
|---|---|
| D1 | Branch `feat/report-infrannuale` in un worktree separato da `main`. |
| D2 | Motore: ReportLab + matplotlib, **riusando** il pacchetto `app/renderers/business_plan` (tema, font Lato, formati, tabelle, pannelli, primitive dei grafici). Il nuovo report sta in `app/renderers/infrannuale/`. Le primitive nuove utili a entrambi (il riquadro KPI col bollino) si aggiungono a `business_plan/layout.py` **accanto** a quelle esistenti, senza cambiarle: il banco del Business plan deve restare verde. |
| D3 | Testi deterministici (punti chiave, forza/debolezza, azioni, «Lettura», sottotitoli dinamici): regole con soglie esplicite, nessuna chiamata AI. |
| D4 | Consegna: «Scarica PDF» della tab Stampa produce il nuovo report. Il Typst non si scarica più dall'interfaccia. |
| D5 | Font Lato al posto di Carlito, come nel Business plan. |
| D6 | Fonte dei numeri: `IntermediateReportModel` (`assemble_intermedio`), che porta già CE e SP aggregati per colonna, i prospetti completi, gli indicatori della crisi per periodo e i segnali extracontabili. Il report non ricalcola indicatori: li legge da `crisi_infrannuale`. Deriva solo somme e differenze di righe già presenti (§5). |

## 3. Colonne

| Chiave nel modello | Etichetta | Dove compare |
|---|---|---|
| `storico` | `2025 C` (consuntivo dell'anno di riferimento) | ovunque |
| `infrannuale` | `6M 2026` (`{mesi}M {anno}`) | ovunque |
| `annualizzato` | `Ann. 2026` | solo conto economico (sezioni 2–3, Allegato A) |
| `proiezione` | `2026 F` | ovunque, se la proiezione esiste |

- Lo stato patrimoniale è puntuale: non ha la colonna annualizzata.
- Con `period_months == 12` l'annualizzato non esiste e la colonna non si stampa.
- Senza proiezione le colonne F non si stampano. Le frasi che la usano spariscono, e la copertina lo dichiara:
  «Forecast non ancora generato».
- Colonne di variazione:
  - CE: `Ann. / C` e `F / C`;
  - SP: `6M / C` e `F / C`.
  - Sono variazioni percentuali sul consuntivo; con base zero o assente si stampa `n.d.`.
- Legenda del piè di pagina: «Riservato e confidenziale · C = consuntivo · 6M = infrannuale al 30.06.2026 · Ann. =
  annualizzato · F = forecast». La data è la fine del periodo; la parte «Ann.» cade se manca l'annualizzato, la parte «F»
  se manca la proiezione.

## 4. Contenuto (13 pagine su AMBIENTA)

| Pagina | Sezione | Contenuto e fonte |
|---|---|---|
| 1 | Copertina | Fascia navy con titolo, sottotitoli e 8 riquadri «I numeri chiave» (ricavi 6M, ricavi F vs C, EBITDA F, utile F, PFN C→F, PFN/EBITDA C→F, DSCR C→F, classe F). Indice con le pagine vere (due passate, come il Business plan). |
| 2 | 1 · Sintesi | Pannello «Punti chiave» (6 punti a regole) e «Cruscotto» a 3 colonne (C, 6M, F), a gruppi: conto economico, patrimonio e debito, circolante e liquidità, crisi d'impresa. |
| 3 | 1 · segue | Punti di forza e di debolezza su due colonne; tabella «Azioni prioritarie» (azione, contenuto, indicatori da monitorare). |
| 4 | 2 · Conto economico | 4 riquadri; grafico dei ricavi per periodo con l'EBITDA margin; tabella a 4 colonne più 2 di variazione. |
| 5 | 3 · EBITDA margin e costi | Grafico EBITDA/EBIT/utile per C, Ann., F; costi per natura (4 colonne); incidenza sui ricavi (C, 6M, F); «Lettura». |
| 6 | 4 · Stato patrimoniale | 4 riquadri; grafico a 4 serie raggruppate; tabella dei saldi con `6M / C` e `F / C`; nota sui ratei; «Lettura». |
| 7 | 5 · Circolante e liquidità | 4 riquadri; grafico crediti/rimanenze/fornitori/circolante commerciale; tabella; «Lettura». |
| 8 | 6 · Indebitamento | 4 riquadri; due pannelli DSCR e PFN/EBITDA con la soglia; tabella banche entro/oltre, altri finanziatori, liquidità, PFN, rapporti. |
| 9 | 7 · Crisi d'impresa | 4 riquadri di classe; barre orizzontali «N su 14 oltre soglia»; tabella dei 15 indicatori con l'esito sul forecast. |
| 10 | 8 · Segnali extracontabili | Tabella dei 7 segnali (area, definizione, stato). |
| 11–13 | Allegati A–B | CE completo (C, 6M, Ann., F, Ann./C) e SP completo (C, 6M, F, F/C), con le righe a zero raggruppate in nota. |

## 5. Convenzioni dichiarate in pagina

- **Indicatori** (DSCR, PFN, PFN/EBITDA, liquidità corrente, margini, ROI/ROE/ROS, oneri/MOL, oneri/fatturato):
  sono quelli di `crisi_infrannuale`, per periodo. Per il 6M gli indicatori reddituali sono su base annualizzata, e
  lo dice la nota.
- **Esito di un indicatore**, dal punteggio 0–1 del motore della crisi: sotto 0,33 «oltre soglia» (rosso), fra 0,33
  e 0,66 «attenzione» (ocra `#b7791f`), da 0,66 «in soglia» (teal). La soglia 0,33 è quella del motore
  (`SOGLIA_OLTRE`); 0,66 è ricavata dal riferimento, dove il margine di tesoreria a 0,557 è «attenzione» e il CCN a
  0,691 è «in soglia». «Oneri finanziari / fatturato» si stampa ma non entra nella classe: nota ¹.
- **Colore della classe di rischio**, per codice come nel riferimento: A → teal, B e C → arancio, D → rosso. Il
  `livello` del motore non si usa per il colore: C2 ha livello «rosso» ma il riferimento lo stampa arancio.
- **Capitale circolante commerciale** = crediti verso clienti (entro e oltre 12 mesi) + rimanenze − debiti verso
  fornitori, dai prospetti. Il «capitale circolante netto» della sezione 4 è quello di `SpAggregati.ccn`; il «CCN» delle
  sezioni 5 e 7 è quello del motore della crisi. Le due definizioni diverse si dichiarano in nota, come fa il
  riferimento.
- **Debiti finanziari** = debiti verso banche + altri finanziatori (`SpAggregati.debiti_finanziari`).
- **Costi operativi** = costi della produzione − ammortamenti e svalutazioni (`CeAggregati.costi_operativi`).
- Un valore assente si stampa `n.d.` e non diventa mai zero; una barra assente non si disegna.

## 6. Rotta e interfaccia

- `POST /companies/{company_id}/scenarios/{scenario_id}/infrannuale/pdf`, corpo vuoto `{}` (modello Pydantic con
  `extra="forbid"`).
  - Scenario di un altro utente: 404.
  - Scenario non infrannuale, o bilanci del periodo mancanti: 400, come la rotta Typst.
- Il PDF non scrive nulla sul DB e non chiama l'AI.
- Il nome del file va in RFC 5987 con una variante ASCII, come nel Business plan.
- **Stampa:** «Scarica PDF» chiama la nuova rotta. I sei commenti AI restano a schermo, modificabili come oggi, ma
  **non entrano nel PDF** (D3). Il loro avviso «commenti stantii» non riguarda più il documento e non si manda al
  server.

## 7. Banco di prova

1. **Banco strutturale** (`tests/test_inf_banco.py`): le sezioni 2, 4 e 7, rese dai numeri del riferimento
   (`tests/fixtures/infrannuale/banco_ambienta.json`), si confrontano riquadro per riquadro con le pagine 4, 6 e 9 del
   riferimento. Tolleranze: 8 pt su `y0`, 3 pt sull'altezza, 2 pt su `x0`/`x1`, come per il Business plan. Lo spike le
   rispetta con 0,2 pt.
2. **Banco numerico** (nuovo): AMBIENTA letta da una copia del DB locale (azienda 575, scenario 17) deve stampare
   le cifre del riferimento nelle tabelle delle pagine 2, 4, 6 e 9. Se AMBIENTA cambia nel DB, il test lo dice con la
   cifra nuova; non si allenta.
3. **Banco visivo**: le 13 pagine di AMBIENTA affiancate al riferimento in PNG, guardate con la vision prima della
   consegna.
4. **Banco delle pratiche**: tutti gli scenari infrannuali del DB locale (AIC, AMBIENTA, TM BUSINESS, FORMETAL, D2M) si
   rendono senza eccezioni, con l'indice coerente.
