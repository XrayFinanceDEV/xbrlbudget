# Report Business plan — specifica

**Data:** 2026-09-23 · **Branch:** `feat/report-business-plan`

**Riferimento:** `BUSINESS PLAN RIVISITATO.pdf`, preparato dal committente (19 pagine, ReportLab + matplotlib,
font Carlito). Il file non è in git; il banco di prova lo legge da `tests/.banco-business-plan/riferimento.pdf`.

**Spike che fa da banco:** le pagine 4, 6 e 7 del riferimento sono state ricostruite con ReportLab + matplotlib
sugli stessi numeri e risultano sovrapponibili, a meno di pochi punti (artifact
`https://claude.ai/artifact/4tac7R7xVYtyup6t92BRnh`). Il proprietario le ha giudicate «perfette»: sono il
banco di prova del lavoro.

## 1. Che cosa si costruisce

Un secondo report PDF, **accanto** al dossier Typst esistente: il dossier, il report intermedio e `/report`
restano come sono. Il nuovo report riproduce il layout del riferimento (copertina, sezioni 1–10, Allegati A–E),
ma con i numeri che il motore calcola per la pratica, qualunque essa sia.

## 2. Decisioni prese con il proprietario

| # | Decisione |
|---|---|
| D1 | Il branch è `feat/report-business-plan`, in un worktree separato creato da `main` (264f1c9). |
| D2 | Il motore è **ReportLab** per le pagine e **matplotlib** per i grafici (PNG da 7,2″ di larghezza a 220 dpi, sfondo trasparente). Non si usa Typst e non si tocca `dossier-base`. |
| D3 | I testi (punti chiave, punti di forza e di debolezza, azioni, «Lettura», sottotitoli dinamici) sono **deterministici**: regole con soglie esplicite, senza LLM. Stesso input, stesso testo. |
| D4 | Il report stampa **tutti e tre i workflow**: infrannuale→budget (AMBIENTA), budget da bilancio annuale, Startup. Cambia solo la sezione 9. |
| D5 | Su `/report` c'è un selettore «Modello: Business plan \| Dossier», con Business plan come default. Il dossier resta intatto. |
| D6 | Il font è **Lato** (OFL, incorporato), al posto di Carlito, da cui Lato deriva. |
| D7 | La fonte unica dei numeri è `FinalReportModelV2` (`assemble_final_report(schema_version=2)`). Il report non ricalcola indicatori; deriva solo somme e differenze di righe già presenti (§4). |

## 3. Colonne e legenda

| Workflow | Colonna base | Etichetta | Legenda nel piè di pagina |
|---|---|---|---|
| infrannuale | `closing:{anno}` | `2026 F` | F = forecast · P = previsione di piano |
| bilancio | l'ultima `historical:{anno}` | `2024 C` | C = consuntivo · P = previsione di piano |
| startup | nessuna: `historical` è solo un bilancio d'apertura | — | P = previsione di piano |

Gli anni di piano sono i periodi `forecast:{anno}`, con etichetta `{anno} P`. Il progressivo rettificato
(`adjusted:{anno}`, etichetta `6M 2026 R`) compare solo nella sezione 9 e nell'Allegato D.

## 4. Convenzioni dichiarate in pagina

- **DSCR (proxy)** = (EBITDA − imposte) / oneri finanziari, come in `calculations/report_indicators.py`. Non comprende la quota capitale e lo si scrive.
- **PFN** e **PFN/EBITDA** sono quelli del motore (`practice.pfn`). I «Debiti finanziari» della sintesi sono PFN + liquidità, quindi coerenti per costruzione. Se esistono debiti verso altri finanziatori fuori PFN, li si dichiara in nota.
- **DSO/DIO/DPO e ciclo monetario** vengono dal motore degli indici su base 360, calcolati su tutti i crediti e debiti del circolante; lo dice il sottotitolo.
- **ROS** = EBIT / ricavi nelle pagine di lettura e nell'Allegato D. L'Allegato E omette le quattro voci che duplicano l'Allegato D (ROE, ROI, ROS, EBITDA margin), perché hanno un'altra convenzione.
- **Costi operativi** = costi della produzione − ammortamenti e svalutazioni (`production_cost − ce09`).
- Un valore assente si stampa come `n.d.` e non diventa zero; nei grafici una barra assente non si disegna.

## 5. Stato del documento

`POST /companies/{id}/scenarios/{sid}/business-plan/pdf` con corpo `{"document_state": "draft" | "final"}`.
- `draft` stampa sempre, con «BOZZA» nell'intestazione.
- `final` richiede `readiness.status == "ready"`, altrimenti risponde 409.
- Il PDF non scrive nulla sul DB e non chiama l'AI.

## 6. Banco di prova

1. **Banco strutturale**: le sezioni 2, 4 e 5, rese dai numeri del riferimento (`tests/fixtures/business_plan/banco_ambienta.json`), si confrontano riquadro per riquadro con le pagine 4, 6 e 7 del riferimento. Si confrontano i rettangoli pieni per colore, le immagini dei grafici e la fascia d'intestazione. Tolleranze: 8 pt su `y0`, 3 pt sull'altezza, 2 pt su `x0`/`x1`. Lo spike le rispetta con un massimo di 6,1 pt.
2. **Banco visivo**: le 19 pagine di AMBIENTA, lette dal DB, si affiancano al riferimento in PNG. La vision le guarda prima della consegna (regola «l'artifact vincola il layout»).
3. **Banco dei workflow**: AMBIENTA (575/18, infrannuale), AIC SRL (21/16, bilancio) e STARTUP SRL (628/24, startup), su una copia del DB locale. Il PDF si apre, ha l'indice coerente e nessuna eccezione.
