# Update — Modifiche da eseguire

> **Come si usa:** scrivi le modifiche nei blocchi `## Richiesta` qui in fondo.
> Quando è pronto, dimmi **"esegui update.md"** e parto con la procedura qui sotto.
> Per micro-modifiche al volo puoi anche scrivermele direttamente in chat, senza questo file.

---

## Procedura concordata

Per ogni richiesta seguo questi passi:

1. **Analisi** — leggo i file `.md` e il codice coinvolto (se non già nel contesto della chat).
2. **Domande (se servono)** — dopo aver letto il codice, se ci sono ambiguità o scelte da fare, te le chiedo. Spesso questo passo si fonde col 3.
3. **Proposta + approvazione** — ti presento la soluzione in **modalità Piano** e **aspetto il tuo "ok"** prima di toccare il codice.
4. **Esecuzione** — implemento le modifiche approvate.
5. **Review & test** — faccio partire uno o più agenti per revisione/test, secondo il livello indicato nella richiesta (vedi `review:`).
6. **Riscontro** — ti riporto cosa ho cambiato, cosa ho **verificato davvero** (build/lint/test) e cosa resta da controllare a mano.

### Livelli di review (campo `review:` in ogni richiesta)
- `no` — modifica banale, nessuna review.
- `leggera` — code-review veloce sul diff.
- `completa` — code-review + test (es. e2e Playwright / pytest backend).

### Convenzioni
- **Un blocco `## Richiesta` per ogni modifica**, separati da `---`.
- Indica sempre i **file/punti coinvolti** quando li conosci: parto più mirato e sbaglio meno.

---
---

## Richiesta 1  — ESEGUITA (2026-07-09)

**Cosa:**
<!-- Descrivi cosa modificare/aggiungere/correggere -->
[sistema questi errori partendo da file .txt](../../../Users/user/Downloads/sistemazione)

**File/punti coinvolti:**
<!-- Es: components/reports-table.tsx (colonna scoring), report_banche/... -->


**Vincoli / da NON rompere:**
<!-- Comportamenti da preservare, preferenze -->

**review:** leggera   <!-- no | leggera | completa -->

**Note:**

### Esito (screenshot = app in PRODUZIONE, indietro rispetto al codice locale)
Molti punti "TEORICAMENTE GIÀ FATTI" erano già risolti in locale (TFR che cresce,
% anno-su-anno, debito che ammortizza a zero, debiti tributari non più negativi,
logica previdenza-scala-col-personale). Interventi effettivi:

- **G1 (motore):** crediti tributari (sp06e) e imposte anticipate (sp06f) NON scalano
  più con i ricavi/DSO — portati avanti costanti; DSO guida solo i crediti commerciali.
  `calculations/forecast_engine.py`.
- **G1 (celle manuali):** nuovi campi `sp06e_growth_pct` / `sp06f_growth_pct` (default
  costanti) — `database/models.py`, `migrate_db.py`, `backend/app/schemas/budget.py`,
  `backend/app/services/assumptions_service.py`, `frontend/types/api.ts`,
  `assumption-rows.ts` (Avanzate → Stato patrimoniale), hydrate in `budget/page.tsx`.
- **G2:** toggle "Debiti previdenziali scalano col costo del personale" esposto in UI
  (logica già presente nel motore) — `assumption-rows.ts`.
- **G3:** celle budget ora selezionano il valore al focus (digiti e sostituisci) —
  `AssumptionsGrid.tsx`; "Nuovo finanziamento: durata (anni)" ora cancellabile
  (`nullable`) — `assumption-rows.ts`.
- **G4:** Report → Stato Patrimoniale ora a DETTAGLIO IV-CEE (come Proiezioni
  patrimoniali), non più solo macro-voci — `report-appendices.tsx`.
- **G5:** Report → Rendiconto Finanziario esteso al dettaglio OIC (metodo indiretto
  A/B/C completo), usando i dati già presenti in /analysis — `report-cashflow.tsx`.
- **G6 (miliardi vs milioni):** NON toccato su richiesta (serve file di esempio; il
  sospetto è `pdf_mapper.parse_italian_number`, lato import, ad alto rischio regressione).

Verificato: migrazione DB ok (2 colonne), test sintetico motore (tributari/imposte
anticipate restano costanti mentre i clienti crescono coi ricavi), `tsc` frontend
pulito, import backend ok.

### Fix aggiuntivi da code-review (perdita dati sul flusso budget)
- **Override CE azzerati al salvataggio:** la hydration ometteva ~15 colonne
  `ce*_override` (ce04, ce08a-d, ce09, ce09a-d, ce11b, ce12, ce17a/b, ce20); "Salva e
  Calcola" (delete+reinsert) le azzerava, cancellando gli override fatti su
  `/forecast/income`. Ora tutte hydrate → sopravvivono. `budget/page.tsx`.
- **Anno base sbagliato in modifica scenario:** `baseYear` era `Math.max(...years)`
  anche per scenari esistenti → orizzonte disallineato dalle assunzioni salvate se
  arrivava un anno più recente. Ora usa `scenario.base_year` (fallback a max solo per
  scenari NUOVI). `budget/page.tsx`.


---

