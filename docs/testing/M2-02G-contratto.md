# M2-02G — contratto di pagina estratto dalla v4 (fase 1)

Il PDF non si corregge più a vista. Questo contratto è il **contratto meccanico** fra
l'anteprima voluta dal proprietario (`report-finale-anteprima-v4.pdf`, 33 pagine) e il renderer
Typst: è generato da `build-dossier-preview.py`, il generatore dell'anteprima, e descrive **forma e
struttura**, mai i numeri. La fase 2 (altro agente) adegua il catalogo su questo contratto.

| File | Che cosa |
|---|---|
| `contracts/dossier_page_contract.json` | le 33 pagine: ordine, occhiello, sequenza di blocchi e layout di ciascuna |
| `contracts/dossier_style_contract.json` | corpi in pt per ruolo, pesi, colori, spaziature, margini di pagina |
| `tools/dossier_contract/extract_v4_contract.py` | l'estrattore; `--check` fallisce se i JSON divergono dalla sorgente |

Il generatore v4 **non viene mai eseguito su disco** dall'estrattore: le sue scritture sono
disattivate a livello di riga (e il fallback è un errore forte se il sorgente cambia forma), per non
toccare `inbox/artifacts/2026-09-15-report-finale/report-finale-anteprima.html`.

## Che cosa vincola e che cosa è riferimento

Decisione del proprietario (2026-09-18), registrata nel JSON in `binding`:

- **Vincolanti**: elenco e ordine delle 33 pagine, la sequenza e la forma dei blocchi di ciascuna
  (tipo di grafico, numero e nomi delle serie, unità, legenda, colonne e righe di tabella, KPI),
  i valori dello style contract, e il fatto che **ogni pagina abbia il suo riquadro di commento**
  (`has_note`/`note_expected`).
- **Riferimento**: `title`/`headline`/`lede` con `dynamic: true` — la v4 ha titoli scritti a misura
  del campione; nel prodotto il titolo di pagina resta **neutro** e la personalizzazione vive nei
  commenti del piano editoriale. Una headline diversa dalla v4 **non è un difetto**.
- **Non vincolanti**: tutti i numeri. Valori e periodi vengono dal modello v2.
- **Priorità** (proprietario 2026-09-18): pagine 1–18 `priority: "executive"` → seguire il layout
  dell'artifact, è l'obiettivo; pagine 19–33 `priority: "allegati"` → la bozza attuale è già
  accettabile, le differenze lì hanno priorità bassa.
- **`optional: true`**: un blocco che la v4 mostra ma che poggia su contenuto assente dal modello
  (o redazionale del campione). La sua assenza nel prodotto **non è un difetto**; oggi sono 3, tutti
  con il motivo nel JSON: il riquadro «Preparato per/da/versione/riferimento» in copertina (costanti
  di deploy), l'elenco «Decisioni e punti da presidiare» a pag. 2 (testo a due colonne scritto a
  mano), il calendario dei rimborsi nell'Allegato E (assente nel modello, mappatura 12-33 pag. 29).

## Come si legge il contratto di pagina

```jsonc
{
  "order": 4,                      // numero di pagina fisica: 1 = copertina
  "id": "rettifiche",              // = id del catalogo (dossier_catalog/*), stesso spazio dei nomi
  "group": "DATI DI PARTENZA",     // occhiello
  "titles": { "title": "...", "headline": "...", "lede": "...",
              "dynamic": { "title": false, "headline": true, "lede": true } },
  "layout": { "form": "rail+main", "rows": 1, "panel_grids": 0 },
  "priority": "executive",
  "blocks": [ /* in ordine visivo */
    { "type": "kpi_rail", "n_kpis": 4, "kpis": ["rettifiche economiche", "..."] },
    { "type": "chart", "kind": "bar", "title": "Prima e dopo le rettifiche",
      "unit": "€ migliaia", "series": ["Prima", "Dopo"], "n_categories": 3, "legend": "bottom" },
    { "type": "table", "caption": "Riconciliazione del progressivo",
      "n_columns": 4, "n_rows": 9, "variant": "standard", "header_repeated": true }
  ]
}
```

`type` ∈ `kpi_rail · chart · table · note · text · panel_grid · toc · meta_row`. Un `<h3>` di
sezione della v4 non è un blocco: diventa il `caption` del blocco che introduce. `kind` ∈
`bar · line · stacked · dumbbell`; `legend` è la posizione del riquadro legenda; per le tabelle
`header_repeated` viene dal CSS di stampa (`thead{display:table-header-group}`), non da un flag del
template. `variant: "full"` è la tabella estesa degli Allegati A/B (7,8 pt, celle 3,7 pt).

## Come si legge lo style contract

`colors.semantic` sono le sei variabili del CSS (`--deep #003049`, `--mid #669BBC`, `--ink`,
`--muted`, `--rule`, `--amber`), `series_palette` l'ordine dei colori di serie (deep, mid, amber,
light-blue); `type.<ruolo>` porta `size.css` + `size.pt` (px convertiti ×0,75), peso, interlinea e
colore; `spacing` e `page` sono in mm/pt come nel CSS. Corpo pagina 9 pt, titolo 16 pt/600, KPI
15 pt/600 su etichetta 7,8 pt muted, tabella 8 pt con intestazione 7,2 pt/500, nota con titolo
8 pt/600 e testo 9 pt/1.5, margini A4 17/16/19/16 mm, testata 8 mm, piè 10 mm.

## Come si rigenera

```bash
/home/peter/DEV/budget/backend/venv/bin/python tools/dossier_contract/extract_v4_contract.py           # rigenera
/home/peter/DEV/budget/backend/venv/bin/python tools/dossier_contract/extract_v4_contract.py --check    # devolve 0 se i JSON = sorgente
```

`--check` rigenera in memoria e confronta con i JSON commitati (forma canonica: chiavi ordinate);
poi, se esistono, verifica incrociata **sull'HTML e sul PDF v4**: numero di pagine, e per ogni pagina
grafici/tabelle contati nel contratto contro quelli realmente presenti (i titoli dei grafici vengono
cercati nel testo del PDF via `pdftotext`). Il sorgente v4 è identificato dal suo sha256 in
`source`: se qualcuno tocca `build-dossier-preview.py` senza rigenerare, `--check` fallisce. Gli
ancoraggi delle righe da disattivare (scritture, font base64) sono verificati uno a uno: una forma
nuova del sorgente dà un errore esplicito, non un contratto silenziosamente diverso.

## Tabella di corrispondenza — parte executive (pagine 1–18, priorità alta)

Stato: **conforme** = forma già coerente, restano solo le differenze sistematiche sotto; **da
adeguare** = differenza precisa; **non applicabile** = contenuto che nel prodotto non esiste.
Il catalogo citato è `backend/app/renderers/typst/dossier_catalog/`, verificato su AMBIENTA
(azienda 575, scenario 18): 33 pagine, stessi `id` del contratto.

| Pag | id | Stato | Che cosa manca per essere conforme |
|---|---|---|---|
| 1 | `cover` | da adeguare | La copertina Typst ha banda+titolo+strip KPI+indice, ma non il `cover-message`/`cover-caption` in due righe né la nota di apertura come blocco; il meta «Preparato…» è `optional`. Perimetro di M2-02F: qui conta la sequenza dei blocchi del contratto. |
| 2 | `sintesi` | da adeguare | Grafico a **barre** (3 serie × 4 periodi, inclusa la chiusura): `sintesi-andamento` non è in `bars` di `chart-layout.json`, oggi esce a linee. Il blocco «Decisioni e punti da presidiare» è `optional` (testo redazionale). |
| 3 | `fonti` | conforme | 2 tavole (2×9 e 3×4) e 4 KPI come in v4; solo le differenze sistematiche (rail, value-table). |
| 4 | `rettifiche` | conforme | Bar raggruppate Prima/Dopo su 3 aggregati ✓, tavola 4×9 ✓; manca il `<p class="source">` di rimando all'appendice (riga di testo, non blocco). |
| 5 | `chiusura` | conforme | Bar 2 serie su 3 colonne ✓, tavola 4×9 ✓. |
| 6 | `indicatori-infrannuali` | da adeguare | Il contratto chiede un **dumbbell** (righe indicatore, ○ rettificato → ● chiusura, legenda a due marker); `indicatori-infrannuali-confronto` è in `bars` e viene disegnato a barre. |
| 7 | `ipotesi` | conforme | Due tavole come in v4 (driver 4×6 con l'origine dichiarata nell'intestazione di colonna + «sette aree» 2×7); KPI a livello pagina (v4: rail a 4 KPI) — resta la differenza sistematica del rail. |
| 8 | `ce` | da adeguare | Grafico a **linee** ✓ (kind ok), ma serie diverse: v4 = EBITDA margin + **EBIT margin** su 4 periodi **con la chiusura**; bozza = EBITDA % + ROS su 3 anni. EBIT margin alla chiusura è assente nel modello (`chart_series["margins"]` copre solo il piano, mappatura 1–11 pag. 8): estenderlo è lavoro sull'assembler, non sul template. |
| 9 | `sp` | da adeguare | v4 = **barre** (Patrimonio netto + Debiti finanziari, 4 colonne con chiusura); `sp-patrimonio-debito` non è in `bars` e il catalogo proietta 3 soli anni. |
| 10 | `flussi` | da adeguare | v4 = **barre** 3 serie × 3 anni; `flussi-composizione` non è in `bars`. Tavola 4×6 ✓. |
| 11 | `indicatori` | conforme | Linee 3 serie su 4 periodi ✓ con chiusura ✓; tavola 5×4 ✓. |
| 12 | `liquidita` | da adeguare | Servono **due** grafici affiancati: barre (CCN/Tesoreria/Struttura ✓ = `structural_balance`) **più** linee «Liquidità corrente e immediata» (current + quick ratio). Il secondo oggi non esiste; `quick_ratio` è assente nel modello (mappatura 12-33) → nuovo indicatore o serie dichiarata `n.d.`. |
| 13 | `redditivita` | da adeguare | v4 = **panel_grid** di 2 grafici a linee (ROI/ROE | OF/ricavi, OF/MOL); la bozza ha un solo grafico a 4 serie. Serve anche il kind `line` (non è in `bars` ✓ già linee). |
| 14 | `solidita` | da adeguare | Secondo grafico a linee **PFN / EBITDA in «volte»** assente (la riga di tabella c'è, il grafico no); il pannello non è un panel_grid. |
| 15 | `circolante` | da adeguare | v4 = **2** grafici a linee (DSO/DIO/DPO + CCC da solo); la bozza li fonde in un grafico a 4 serie. Differenza di forma (scala giorni unica, seconda serie in evidenza), priorità media dentro le executive. |
| 16 | `composizione` | da adeguare | Il più lontana: v4 = panel_grid di **2 stacked al 100%** (impieghi, fonti) + **dumbbell** delle incidenze di costo; la bozza ha 1 grafico a linee (che il contratto vuole dumbbell) + una tavola di quote che la v4 non ha. Gli stacked sono derivabili dalle righe di SP già canoniche. |
| 17 | `break-even` | da adeguare | Primo grafico a **barre** (Ricavi | Pareggio), non è in `bars`; secondo grafico a linee «Margine di sicurezza %» assente dalla bozza (metrica esistente in report-break-even). |
| 18 | `diagnostica` | da adeguare | v4: rail a 4 KPI + tavola «Priorità di verifica» 3×3 + controlli 2×4; bozza: 2 KPI pagina + 1 sola tavola 2×3. La terza riga dei controlli («9M rettificati + Q4 = chiusura») è assente nel modello (mappatura 12-33) → dichiararla, non inventarla. |

### Differenze sistematiche della parte executive (valgono per tutte le 1–18)

**Stato dopo la fase 2 — traccia A (fondazione del layout).** Le prime tre non sono più differenze
*sistematiche*: il meccanismo esiste, e una pagina che lo dichiara lo ottiene. Quello che resta
su ciascuna pagina è contenuto, non infrastruttura.

1. **Rail KPI — risolto il meccanismo.** Una pagina dichiara `"form": "rail+main"` e il catalogo
   (`dossier_catalog/__init__.py::_apply_page_form`) mette i KPI nel rail da 47 mm e stringe la
   colonna principale a 126 mm; `pagine/comuni.typ::render_page` li rende come `.row` della v4, e
   la striscia KPI in testa non si disegna più (duplicato). Dichiarate: `ipotesi`, `ce`, `sp`,
   `flussi`, `indicatori`, `liquidita`, `solidita`, `break-even`, `diagnostica`, `circolante`.
   Non dichiarate: `redditivita` e `composizione` (chiedono il `panel_grid`, cioè il secondo
   grafico della fase 3) e le pagine 2–6 (in `apertura.py`/`dati.py`, perimetro della traccia
   serie — il meccanismo è pronto, lì si aggiunge una riga). Il numero di KPI del contratto
   (4 per pagina) resta contenuto di fase 3: dove la pagina ne ha 2, il rail ne mostra 2.
2. **Value-table sotto il grafico — disattivata sulle pagine con una forma.** `_apply_page_form`
   scrive `value_table: false` su ogni grafico di una pagina `rail+main`/`full+panels`; `comuni.typ`
   la legge e salta la tabellina. Una pagina che non dichiara forma la mantiene com'era, quindi
   gli allegati non cambiano.
3. **`kind` del grafico — dichiarato.** `shared.chart_kind()` mette `kind` in ogni dict di
   grafico (`bar`, `line`, `stacked`, `dumbbell`); il ripiego resta la lista `bars` di
   `chart-layout.json`, e `charts.typ::kind` legge solo la chiave. `charts.typ` ha ora
   `stacked-plot` (barre orizzontali al 100%, nessuna cifra sul segmento: i numeri restano
   nelle tavole) e `dumbbell-plot` (○ iniziale → ● finale, valori a destra), e
   `panel-grid` per i due grafici affiancati a 86 mm.
4. **Riquadro di commento**: in v4 ogni pagina ha la nota (`has_note: true` su tutte e 33);
   nel catalogo le note sono solo editorial notes, non `items`: la conformità si verifica sul
   piano editoriale, non sul blocco.
5. **Tipografia — applicata e sorvegliata.** Corpo 9 pt, titolo 16/600, occhiello 7,5/500,
   tabella 8 pt con intestazione 7,2/500 muted, legenda 7,6 pt, nota 8/600 + testo 9 pt,
   KPI del rail 15/600 su etichetta 7,8 pt, margine superiore 17 mm. Il fondo pagina resta
   46 mm (non i 19 mm del CSS: lì sotto stanno riquadro di commento e piè, che in Typst sono
   il footer). `test_style_contract_letto_dalla_tipografia` non si limita più al JSON: legge
   i tre file del template e nomina il ruolo che ha smesso di essere applicato.

Le **due colonne della forma** sono un'invariante numerica, non una scelta del template:
47 + 5 + 126 = 178 e 86 + 6 + 86 = 178 (`shared.CHART_WIDTH_RAIL_MM`, `CHART_WIDTH_PANEL_MM`),
e `editorial_plan._validate_records` rivuole la stessa misura nel marcatore Typst. I gutter
sono 5 mm e 6 mm, non i 15 pt dell'artifact: due pannelli da 86 mm con 15 pt di gap
sfonderebbero il corpo di 5,6 mm.

## Tabella di corrispondenza — allegati (pagine 19–33, priorità bassa)

Il proprietario ha già accettato la bozza di queste pagine; le righe servono a misurare, non a
pretendere.

| Pag | id | Stato | Differenza dalla v4 |
|---|---|---|---|
| 19 | `allegati` | conforme | Indice a 13 voci ✓ (nota via piano editoriale). |
| 20–21 | `allegato-A-1/2` | accettabile | v4 6 colonne (con «9M 2026 R») × 24+23 righe; bozza 5 colonne (senza il 9M, coerente con AMBIENTA a 6 mesi → periodi diversi) stesse 2 righe. Variant `full` ✓. |
| 22–25 | `allegato-B-1..4` | accettabile | 4 parti ✓; v4 23+24+24+18 righe (incluse le righe «(segue)»), bozza 24+24+24+14 = 86 righe di catalogo. Le (segue) della v4 (ripetizione del padre a fine pagina) non sono emesse. |
| 26–27 | `allegato-C-1/2` | accettabile | v4 usa `tab` standard 4×24+23 con la colonna 2026 C dentro le righe; bozza 5 colonne, 24+23 ✓. |
| 28 | `allegato-D` | accettabile | v4 due tavole (registro 5×4 + effetto 4×9); bozza una 3×9 in forma «Voce/Delta/Motivazione». |
| 29 | `allegato-E` | accettabile | Bozza 1 tavola 4×12; v4 driver 5×11 (+ calendario rimborsi `optional`, assente nel modello) + fonte. |
| 30 | `allegato-F` | conforme | Indicatore × periodi, 15 righe ✓ (v4: 6 colonne con il 9M; AMBIENTA ha 6 mesi, quindi i periodi cambiano ma il conteggio delle righe — 15 indicatori — è il vincolo). |
| 31–32 | `allegato-G-1/2` | accettabile | v4 spezza 26 indici in 15+11; bozza 13+13. Numero righe totale diverso (split per pagina, non contenuto). |
| 33 | `metodologia` | accettabile | Sequenza v4: nota + tavola fonti (5 righe) + nota limiti + paragrafo; bozza: testo + tavola (4 righe) + nota. Le 5 strutture nominate nella tavola sono le stesse meno «Break-even»; la nota «Limiti del campione» della v4 è in parte superata (Acid Test e leva esistono nel modello, mappatura 12-33 §G). |

## Verifica di accettazione

- `extract_v4_contract.py --check` → exit 0 con crosscheck HTML e PDF «ok» (misurato il
  2026-09-18: 33 pagine, 21 grafici (bar 7 · line 10 · stacked 2 · dumbbell 2), 34 tabelle,
  16 rail, 34 note, 33/33 pagine con nota).
- La tabella sopra copre tutti e 33 gli id del catalogo AMBIENTA e tutto coincide con gli id del
  contratto tranne `cover` (contratto: `copertina`).
- `tests/test_dossier_contract_conformance.py` (fase 2, traccia A) è il confronto meccanico:
  una voce parametrizzata per pagina executive, con il diff fra i blocchi `binding` del
  contratto e `build_inventory()`, e una lista di pagine non conformi dove ogni voce **nomina
  il motivo** in `xfail(strict)`. Una pagina che diventa conforme senza che la voce venga
  rimossa fa fallire la suite; e `test_le_quattro_forme_si_compilano_su_una_pagina_ciascuna`
  compila davvero rail, pannelli, stacked e dumbbell con il probe di layout, per cui una forma
  che esiste nell'inventario ma non nel foglio non basta.
