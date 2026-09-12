# Ondata finale di correzioni — XBRL Budget — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chiudere i quattro difetti trovati dal collaudo del lotto 3A (debito bancario e crediti
azzerati nell'infrannuale, promote che ignora l'uscita di cassa tributaria, la percentuale che
esplode a schermo, gli importi all'americana nei messaggi di quadratura) più i rilievi minori
rimasti parcheggiati (reti di test che non mordono, codice morto, due buchi nello schema del
bulk) — l'ultima ondata prevista per l'app, decisione del proprietario 2026-09-12.

**Architecture:** I primi tre task toccano in sequenza lo stesso metodo di
`calculations/intra_year_engine.py` (`_project_balance_sheet`, il ramo con anno di riferimento):
il debito finanziario (`sp16a-c`/`sp17a-c`) e la composizione dei crediti (`sp06`/`sp07`) si
portano avanti esatti dal periodo parziale invece che dalla proporzione di un anno di riferimento
diverso, e l'uscita di cassa tributaria di fine anno diventa un conguaglio esplicito su un campo
neutro invece di un effetto collaterale della sostituzione fiscale. I successivi quattro task sono
indipendenti fra loro e dai primi tre: un helper di formattazione condiviso nel frontend
(`deltaPct`), gli importi in formato italiano nei messaggi di quadratura di tre moduli di import,
due reti di test rese cieche da una copertura solo indiretta, e la rimozione di codice morto più
due correzioni allo schema tipizzato del bulk delle ipotesi. L'ultimo task verifica l'intera
ondata: suite, banco di parità del motore budget (mai toccato), misure prima/dopo su tutti gli
scenari infrannuali del database, collaudo a schermo, riallineamento della documentazione.

**Tech Stack:** Python 3 + SQLAlchemy + FastAPI + Pydantic (motori in `calculations/`, servizi in
`backend/app/services/`, rotte in `backend/app/api/v1/`), Next.js 15 + TypeScript + Vitest
(`environment: node`), SQLite in memoria nei test, banco di parità `scripts/parita_motore.py` +
`scripts/parita_riepilogo.py`.

**Spec:** `.superpowers/sdd/2026-09-11-indagine-difetti-collaudo-3a/indagine-1-debito-bancario.md`
(difetto 1, debito finanziario), `indagine-2-promote.md` + `verifica-2-bisezione.md` (difetti 2 e
4, promote e formato americano), `indagine-3-stampa-percentuale.md` (difetto 3, percentuale),
`progress.md` (decisioni del coordinatore e perimetro dell'ondata) — tutti nella stessa cartella.
Le bozze eseguite che questo piano assembla: `bozza-task-B.md`, `bozza-task-R.md`,
`bozza-task-T.md`, `bozza-task-P-F.md`, `bozza-task-M.md`, stessa cartella.

## Global Constraints

- **Base:** `feat/scadenziamento-pregresso` al commit `0f7614a` — ogni task parte da lì (o dal
  commit del task precedente, per 1→2→3).
- **Suite Python di riferimento.** Comando esatto:
  `env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests -q --ignore=tests/corpus -p no:cacheprovider -W ignore::DeprecationWarning`.
  CLAUDE.md e le bozze citano `1005 passed, 62 skipped, 0 xfailed, 0 failed` su `0f7614a`; **misurato
  di nuovo nell'ambiente di questa sessione, stesso comando, stesso commit**: `1058 passed,
  9 skipped, 0 failed` — la cifra esatta dipende dall'ambiente disponibile (bozza-task-B e
  bozza-task-T lo segnalano già: `ANTHROPIC_API_KEY` abilita o disabilita test altrimenti
  saltati, e la composizione della suite può essere cambiata da lavoro concluso dopo `0f7614a` su
  altri branch). **Ogni task stabilisce il proprio numero di riferimento PRIMA della propria patch,
  nello stesso ambiente in cui la applica** — l'invariante che conta davvero, in ogni Step "suite
  intera" di questo piano, è che il conteggio di `failed` non aumenti, non che combaci con una
  cifra fissata altrove.
- **Frontend di riferimento.** `cd frontend && npx vitest run` → **46 file, 721 test** (misurato in
  questa sessione, `0f7614a`); `npx tsc --noEmit` pulito (misurato).
- **Banco di parità del motore budget** (`scripts/parita_motore.py`): **il motore budget
  (`calculations/forecast_engine.py`) non si tocca in nessun task di questa ondata** — ogni task
  che lo cita lo fa come controllo negativo, atteso a **0 divergenze** rispetto a `0f7614a`.
- **Denaro in `Decimal`, mai `float`.** Percentuali assolute (25,5 = 25,5%, mai 0,255).
- **Messaggi rivolti all'utente in italiano**, importi in formato europeo: `eur_it()`
  (`calculations/projection_common.py`) lato Python, l'helper `_it_amount` già presente in
  `importers/pdf_importer.py` dove serve senza un nuovo import; lato frontend, `formatEuro`/
  `formatPct`/il nuovo `deltaPct` (`frontend/lib/pratica-format.ts`).
- **Terminatori di riga.** `calculations/intra_year_engine.py` ha terminatori **misti** (CRLF sulla
  maggior parte del file, LF sui blocchi aggiunti dal lotto 3A) — **non normalizzare mai l'intero
  file**: ogni patch di questo piano opera per numero di riga/ancora testuale esatta su
  `splitlines(keepends=True)`, sceglie il terminatore delle righe nuove in base alla zona in cui
  cadono, e verifica `git diff --stat` prima di committare (uno scarto di centinaia di righe indica
  una normalizzazione accidentale, da annullare). `backend/app/api/v1/financial_years.py` ha lo
  stesso problema (misto); le righe toccate dal Task 5 sono in una zona LF, verificato. I quattro
  file frontend del Task 4 (`StampaContent.tsx`, `ComparisonTable.tsx`, `ProjectionTable.tsx`,
  `pratica-statement-rows.ts`) sono **CRLF puri**: si riconvertono a CRLF dopo ogni edit (l'harness
  normalizza CRLF→LF su un file toccato). `frontend/lib/pratica-format.ts` e
  `importers/iv_cee_hierarchy.py` sono **LF puri**: nessuna precauzione.
- **Nessun nome di azienda cliente nei rapporti**: solo id azienda/scenario/anno.
- **Git:** un commit per task, messaggio da file (`git commit -F -`), `git add` dei file **per
  nome** (mai `-A` né `.`). Le due righe finali di ogni commit:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01C8chDC8b297itUaoK1TQNW
  ```
- **Documentazione nello stesso commit del comportamento che descrive**: `CLAUDE.md`,
  `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md`, `docs/frontend/INDICATORI-E-STAMPA.md`,
  `docs/import/REGOLE-IMPORT-04-QUADRATURE.md` — ciascun task aggiorna solo quelli che
  effettivamente tocca (indicato per task sotto).
- **Un test esistente che diventa rosso si corregge solo se il task lo nomina.** Altrimenti ci si
  ferma e lo si riferisce: è quasi sempre un difetto del codice nuovo, non del test.
- **Codice che cambia sotto i piedi.** I numeri di riga citati in questo piano sono quelli
  verificati dalle bozze sullo snapshot indicato per ciascun task (`0f7614a` nudo, o il file già
  patchato dal task precedente quando esplicitamente detto). Chi esegue rilegge sempre l'ancora
  testuale, non si fida ciecamente del numero se il file è cambiato.

## File map (file toccati dall'ondata)

| File | Task | Natura del tocco |
|---|---|---|
| `calculations/intra_year_engine.py` | 1, 2, 3 | Stesso metodo (`_project_balance_sheet`, ramo con riferimento), in sequenza — vedi «Interfaces» di ciascun task |
| `calculations/intra_year_engine.py` (`_financing_contracts`, righe 236-253/802/937) | 7 | Area **diversa** dello stesso file, non tocca dove 1-3 scrivono, ma i numeri di riga a valle si spostano — vedi Task 7 «Interfaces» |
| `tests/test_intra_year_debito_bancario.py` | 1 | Estensione (3 test nuovi) |
| `tests/test_intra_year_crediti_commerciali.py` | 2 | Nuovo file |
| `tests/test_intra_year_imposte.py` | 3 | Estensione (3 test nuovi) |
| `tests/test_intra_year_override_cassa.py` | 6 | Estensione (1 test nuovo) |
| `tests/test_http_full_cycle.py` | 6 | Una riga (confronto diretto invece di doppio `abs`) |
| `tests/test_parita_riepilogo.py` | 6 | Estensione (1 test nuovo) |
| `calculations/forecast_engine.py` | 7 | Un alias morto rimosso, commento corretto — **motore budget, ma solo alias/commenti: nessuna riga di calcolo cambia** |
| `tests/test_projection_common_debito_bancario.py` | 7 | Aggiornato per l'alias rimosso |
| `backend/app/services/assumptions_service.py` | 7 | `_senza_null` (sp_indexing), messaggio errore campo sconosciuto |
| `backend/app/schemas/budget.py` | 7 | `BudgetAssumptionsBulkRow.model_config = ConfigDict(extra="forbid")` |
| `tests/test_bulk_tipizzato.py` | 7 | Estensione (2 casi) |
| `frontend/lib/pratica-format.ts` | 4 | Nuovo export `deltaPct`, rete secondaria in `formatPct` |
| `frontend/lib/pratica-format.test.ts` | 4 | Nuovo file |
| `frontend/components/pratica/StampaContent.tsx` | 4 | `deltaFmt` riusa `deltaPct` |
| `frontend/components/pratica/ComparisonTable.tsx` | 4 | Stessa sostituzione |
| `frontend/components/pratica/ProjectionTable.tsx` | 4 | Stessa sostituzione |
| `frontend/lib/pratica-statement-rows.ts` | 4 | `safePct` (due copie) riusa `deltaPct` |
| `importers/iv_cee_hierarchy.py` | 5 | 8 messaggi da `{x:,.2f}` a `eur_it(x)` |
| `backend/app/api/v1/financial_years.py` | 5 | 3 messaggi della guardia Rettifiche, stesso trattamento (perimetro esteso dal coordinatore) |
| `importers/pdf_importer.py` | 5 | 3 messaggi di route C, con l'helper locale `_it_amount` già presente (perimetro esteso dal coordinatore) |
| `tests/test_messaggi_italiani.py` | 5 | Estensione (1 test nuovo, + 2 test aggiuntivi per i siti estesi) |
| `CLAUDE.md` | 1, 2, 3 | § Intra-Year Engine (tre paragrafi distinti) |
| `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` | 1, 2, 3 | §5, tre punti distinti dello stesso paragrafo |
| `docs/frontend/INDICATORI-E-STAMPA.md` | 4 | Nuova sezione breve su `deltaPct` |
| `docs/import/REGOLE-IMPORT-04-QUADRATURE.md` | 5 | Nota di chiusura §5 sul formato degli importi |
| `scripts/parita_motore.py` | — | **Non toccato in questo piano**: F-ii (bozza-task-M) resta fuori, vedi «Fuori perimetro» |

## Ordine dei task

I Task 1, 2, 3 toccano **lo stesso file nello stesso metodo**, in sequenza obbligata (ciascuno
scritto sul file **già patchato** dal precedente — verificato eseguendo le patch in sequenza
durante la stesura delle bozze). I Task 4-7 sono indipendenti fra loro e dai primi tre: possono
girare in parallelo, in qualunque ordine, purché tutti finiscano prima del Task 8. Il Task 8
verifica l'intera ondata.

```
Task 1 (B) → Task 2 (R) → Task 3 (T)      [in serie, stesso file]
Task 4 (P) ‖ Task 5 (F) ‖ Task 6 (M/1) ‖ Task 7 (M/2)   [indipendenti]
Task 8 — verifica di fine ondata (dopo tutti gli altri)
```

---

### Task 1: Il debito finanziario dell'infrannuale si porta avanti dal parziale, non dalla proporzione del riferimento

**Files:**
- Modify: `calculations/intra_year_engine.py` (ramo **con riferimento** di `_project_balance_sheet`)
- Modify: `CLAUDE.md` (§ Intra-Year Engine, paragrafo sul debito bancario)
- Modify: `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` (§5, riga «Debiti a breve» + sezione «Le
  sotto-voci si distribuiscono, mai si inventano»)
- Test: `tests/test_intra_year_debito_bancario.py` (estensione: 3 test nuovi, 9 esistenti invariati)

**Interfaces:**
- Consumes: nulla di nuovo da altri task di questa ondata — parte da `0f7614a` nudo.
- Produces (per il Task 2, che si applica **sopra** questo): all'interno del ramo con riferimento
  di `_project_balance_sheet`, dopo questo Change esistono le variabili locali
  `partial_sp16a`/`partial_sp16b`/`partial_sp16c`, `partial_sp16_fin`, `partial_sp16_operativo`,
  `partial_sp17a`/`b`/`c`, `partial_sp17_fin`, `sp16_operativo`, `sp17_operativo`,
  `ref_sp16_operativo` (il Task 2 le legge, non le tocca). Le chiamate finali diventano:
  `sp16a, sp16b, sp16c = partial_sp16a, partial_sp16b, partial_sp16c` seguito da
  `sp16d, sp16e, sp16f, sp16g = self._distribute_sp16_operativo(ref_bs, sp16_operativo)`, e lo
  stesso schema per `sp17` — è **esattamente questo blocco di 2 righe per aggregato** che il
  Task 2 sostituisce con la propria versione più ampia (stessi nomi di variabile in input).
  Nuovi metodi che restano invariati da qui in avanti: `_distribute_sp16_operativo`,
  `_distribute_sp17_operativo` (Task 2 li richiama così come sono). Nuova diagnostica:
  `reference_financial_debt_undetailed` (severità `warning`) — il Task 2 introduce l'equivalente
  per i crediti (`reference_receivables_undetailed`) nello stesso stile, senza toccare questa.
  Nuovo parametro opzionale su `_scaled_or_carried`: `carried_value=None` — invariato dal Task 2.

**Target.** Uno scenario infrannuale il cui bilancio di riferimento non ha dettaglio finanziario
(banche/altri finanziatori/obbligazioni tutte a zero, tutto il totale nel secchio di ripiego
`sp16g`/`sp17g` — il 98% dei bilanci annuali completi del database) azzera il debito bancario
**reale** del periodo parziale nella proiezione: `sp16a`/`sp17a` escono 0,00 anche quando il
parziale ne dichiara centinaia di migliaia di euro. Il foglio quadra lo stesso (è l'aggregato
`sp16`/`sp17` a restare giusto), quindi nessun controllo se ne accorge — ma la **PFN**, che legge
solo le sottovoci finanziarie, si sposta di quasi un milione di euro sul caso di prova
dell'indagine (azienda id 237, scenario id 18: da −1.086.291,98 a −112.553,30 nella prova minima).

**Decisione del coordinatore da implementare (non riaprire l'indagine):** opzione **B + C** di
`indagine-1-debito-bancario.md` §7 — il debito finanziario (`sp16a-c`/`sp17a-c`) si porta avanti
dal parziale come blocco a sé (rettificato solo dai piani espliciti di `_apply_debt_repayment`,
lotto 3A Task 4), rotazione dei costi e ripartizione per riferimento solo sul residuo operativo
(`d-g`); più una diagnostica quando il riferimento non ha dettaglio finanziario e il parziale sì.
Scartata la A (sostituire `ref_bs` con `partial_bs` nelle chiamate esistenti): toglie lo zero ma
scala un mutuo con la rotazione dei costi, economicamente sbagliato.

## Da leggere prima, per simbolo

- `.superpowers/sdd/2026-09-11-indagine-difetti-collaudo-3a/indagine-1-debito-bancario.md` — l'intero
  documento: §2 (traccia riga per riga della causa), §3 (il caso che "funziona" oggi, azienda 21
  scenario 4 — **cambia comunque numero dopo questa correzione**, vedi «Le 8 misure» sotto), §5 (la
  prova minima, opzione A, scartata), §6 (impatto: 1 scenario su 8 oggi, rischio sistemico al 98% dei
  bilanci annuali), §7 (le tre opzioni).
- `CLAUDE.md` § «Intra-Year Engine (Infrannuale)», l'intera sezione — in particolare la frase da
  correggere (paragrafo "Working capital", il testo esatto è riportato in «Documentazione» sotto).
- `CLAUDE.md` § «Invarianti e trappole › Contabilità/Estrazione»: *"Un errore dentro un aggregato è
  accettato... un errore che attraversa un aggregato o un confine di KPI no"* — è esattamente la
  riga di impatto (l'aggregato `sp16`/`sp17` resta giusto, la PFN no); *"La massa non riconosciuta
  va in un sotto-campo esplicito, mai su un aggregato"* — governa il residuo operativo, non
  toccato da questo task; *"Un estrattore dichiara sempre le proprie chiavi diagnostiche, anche a
  zero"* — la nuova diagnostica si dichiara solo quando la condizione scatta, mai un "nessun
  problema" ad ogni proiezione.

### Codice — stato attuale, verificato a `0f7614a` (numeri di riga confermati con `grep -n`)

`_scaled_or_carried` (righe 1007-1045), il fallback che carica la giacenza osservata quando il
rapporto di rotazione è degenere:

```python
    def _scaled_or_carried(self, field, ref_stock, ref_base, projected_base, partial_bs):
        ...
        ratio = _turnover_ratio(ref_stock, ref_base, max_ratio=max_ratio)
        if ratio is not None:
            return projected_base * ratio

        carried = _get_field(partial_bs, field)
        self._diagnostics.append({
            'code': 'degenerate_turnover_ratio',
            ...
        })
        return carried
```

Il ramo con riferimento di `_project_balance_sheet` (righe 1110-1119, il calcolo dei valori di
riferimento):

```python
        ref_revenue = _get_field(ref_inc, 'ce01_ricavi_vendite')
        ref_sp05 = _get_field(ref_bs, 'sp05_rimanenze')
        ref_sp06 = _get_field(ref_bs, 'sp06_crediti_breve')
        ref_sp07 = _get_field(ref_bs, 'sp07_crediti_lungo')
        ref_sp16 = _get_field(ref_bs, 'sp16_debiti_breve')          # <-- riga 1114, l'AGGREGATO intero
        ref_costs = (
            _get_field(ref_inc, 'ce05_materie_prime') +
            _get_field(ref_inc, 'ce06_servizi') +
            _get_field(ref_inc, 'ce07_godimento_beni')
        )
```

righe 1176-1199, dove la massa si perde (`sp16` include il debito bancario e viene scalato dalla
rotazione dei costi; `sp17` è già portato avanti esatto dal parziale a livello di aggregato, ma **poi
ridistribuito** con le proporzioni sbagliate):

```python
        # Short-term debt: proportional to operating costs (turnover ratio)
        sp16 = self._scaled_or_carried(
            'sp16_debiti_breve', ref_sp16, ref_costs, projected_costs, partial_bs,
        )

        # Long-term debt starts from the actual YTD balance; only explicit repayment
        # and financing assumptions may change it.
        sp17 = _get_field(partial_bs, 'sp17_debiti_lungo')
        sp18 = _get_field(partial_bs, 'sp18_ratei_risconti_passivi')

        ...
        sp16a, sp16b, sp16c, sp16d, sp16e, sp16f, sp16g = self._distribute_sp16(ref_bs, sp16)   # <-- riga 1198
        sp17a, sp17b, sp17c, sp17d, sp17e, sp17f, sp17g = self._distribute_sp17(ref_bs, sp17)   # <-- riga 1199
```

`_distribute_sp16` (righe 1772-1807), il meccanismo esatto della perdita: quando `ref_bs` ha **tutto**
il totale in `sp16g` (nessun'altra sottovoce diversa da zero), `r` moltiplica zero per ogni categoria
tranne `g`, e l'intera massa proiettata — banca compresa — finisce lì:

```python
    def _distribute_sp16(self, ref_bs, sp16_total):
        """Distribute sp16 into sub-categories proportionally from reference."""
        total = (
            _get_field(ref_bs, 'sp16a_debiti_banche_breve') +
            ... +
            _get_field(ref_bs, 'sp16g_altri_debiti_breve')
        )
        if total > 0:
            r = sp16_total / total
            return (
                _get_field(ref_bs, 'sp16a_debiti_banche_breve') * r,
                ...
            )
        if sp16_total != 0:
            self._diagnostics.append({'code': 'missing_short_debt_breakdown', 'severity': 'error', ...})
        return (Decimal('0'),) * 7
```

`_distribute_sp17` (righe 1809-1831) è **identico**, sulle 7 sottovoci di `sp17`, **senza** la
diagnostica `missing_short_debt_breakdown` sul `total==0` (asimmetria pre-esistente, non introdotta
né corretta da questo task).

`_apply_debt_repayment` (righe 1598-1657) — **non toccata da questo task**: riceve in input
esattamente `sp16a`/`sp17a`/`sp17b` prodotti dalle righe sopra.

Il ramo **senza** riferimento, `_project_balance_sheet_annualized` (righe 1354-1495) — **verificato,
non si tocca**: righe 1432-1433 portano avanti `sp16`/`sp17` esatti dal parziale, e righe 1447-1448
chiamano `_distribute_sp16(partial_bs, sp16)`/`_distribute_sp17(partial_bs, sp17)` — **già** con
`partial_bs` come sorgente delle proporzioni, non `ref_bs`: già coerente con la correzione.

`calculations/projection_common.py:49-52`, `eur_it` — già importato in `intra_year_engine.py`, usato
dal messaggio della nuova diagnostica:

```python
def eur_it(amount: Decimal) -> str:
    """1234567.891 -> '1.234.567,89' (ROUND_HALF_UP, come la quantizzazione del motore)."""
    q = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
```

`tests/test_intra_year_debito_bancario.py` (115 righe, esiste dal lotto 3A Task 4) — leggilo per
intero: definisce già `_sessione()` e `_proietta()` (costruisce un'azienda con **lo stesso** stato
patrimoniale sia per l'anno di riferimento sia per il parziale — quindi non esercita mai la
ripartizione riferimento-vs-parziale: tutti i suoi 9 test restano verdi immutati). Importa già
`IntraYearEngine`, `Base`, `BalanceSheet`, `BudgetAssumptions`, `BudgetScenario`, `Company`,
`FinancialYear`, `ForecastYear`, `IncomeStatement`.

## Trappole note

- **`calculations/intra_year_engine.py` ha terminatori di riga MISTI** (CRLF sulla maggior parte del
  file, LF su blocchi aggiunti più di recente: le righe 1007-1182 sono CRLF, le righe 1183-1199 sono
  LF, transizione esattamente fra riga 1182 e 1183). **Non normalizzare mai l'intero file**: opera
  per numero di riga esatto su `splitlines(keepends=True)` (preserva il terminatore originale di
  ogni riga non toccata) e scegli il terminatore delle righe NUOVE in base alla zona in cui cadono
  (CRLF nel blocco CRLF, LF nel blocco LF che inizia a riga 1183). Lo script del Change produce un
  diff di **159 inserzioni, 8 cancellazioni** — nessuna riga estranea toccata (misurato).
- **Denaro in `Decimal`, mai `float`.** Ogni valore nuovo (`ref_sp16_operativo`,
  `partial_sp16_fin`, `partial_sp16_operativo`, `sp16_operativo`, e i corrispondenti per `sp17`) è
  costruito da `_get_field(...)` con `+`/`-` fra `Decimal`.
- **Il motore budget (`calculations/forecast_engine.py`) non si tocca.** `base_bank_debt` e le altre
  funzioni di `projection_common.py` restano invariate.
- **I messaggi dei motori sono in italiano dal lotto 3A Task 8.** Il messaggio della nuova
  diagnostica è in italiano fin dalla prima stesura, con `eur_it()` per l'importo.
- **Non riaprire l'indagine.** Le opzioni A e C erano già state confrontate e scartate/integrate dal
  coordinatore: questo task implementa B (strutturale) + C (diagnostica), non torna a proporre A.
- **`_distribute_sp06`/`_distribute_sp07` non si toccano in questo task**: uno Step di sola misura
  (Step 9) conta le coppie a rischio e basta — il Task 2 le corregge.

## Change

Un solo file di produzione, `calculations/intra_year_engine.py`. Cinque punti, applicati **in un
solo script**, per garantire che i numeri di riga restino coerenti fra un'edit e l'altra e per
preservare i terminatori riga per riga:

1. `_scaled_or_carried` guadagna un parametro opzionale `carried_value`, per poter passare un
   fallback **diverso** dal valore dell'intero campo aggregato (il residuo operativo).
2. Un nuovo metodo, `_declare_reference_financial_debt_undetailed`, dichiara la diagnostica quando
   serve.
3. Nel ramo con riferimento: `ref_sp16` (l'intero aggregato di riferimento) diventa
   `ref_sp16_operativo` (l'aggregato **meno** le tre voci finanziarie del riferimento) — la base su
   cui si calcola il rapporto di rotazione dei costi non include più il debito bancario.
4. Il debito finanziario (`sp16a/b/c`) viene letto **esatto dal parziale** come blocco a sé, la
   diagnostica viene valutata, e solo il **residuo operativo** (`sp16_debiti_breve` del parziale
   meno quel blocco) passa da `_scaled_or_carried` con la nuova base. Stessa cosa per `sp17`.
5. Le due chiamate `_distribute_sp16(ref_bs, sp16)` / `_distribute_sp17(ref_bs, sp17)` diventano:
   `sp16a/b/c` = i valori del parziale già letti al punto 4; `sp16d/e/f/g` = il nuovo metodo
   `_distribute_sp16_operativo(ref_bs, sp16_operativo)`, che fa esattamente ciò che
   `_distribute_sp16` faceva ma **solo sulle 4 categorie operative**. Idem per `sp17`.

**Come si ricompone l'aggregato**, in una riga: `sp16 = partial_sp16_fin + sp16_operativo` (dove
`partial_sp16_fin = partial_sp16a + partial_sp16b + partial_sp16c`, letto dal parziale); per
`sp17`, l'aggregato **non cambia** (era già `_get_field(partial_bs, 'sp17_debiti_lungo')`),
cambia solo come lo si spacca: `sp17_operativo = sp17 - partial_sp17_fin`, distribuito su `d/e/f/g`.

Script di patch (letto per intero, non un frammento): opera su `splitlines(keepends=True)`,
verifica ogni ancora con un `assert` esplicito prima di scrivere, e sceglie CRLF o LF riga per riga
in base alla zona in cui cade (mai una normalizzazione globale):

```python
"""Patch calculations/intra_year_engine.py preserving each line's own terminator
(the file mixes CRLF and LF: never normalize it wholesale). Operates by exact
1-based line number, verified against `0f7614a` with `grep -n`."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "calculations/intra_year_engine.py"

with open(path, "rb") as f:
    raw = f.read()
lines = raw.splitlines(keepends=True)  # each entry keeps its own b"\r\n" or b"\n"


def at(n):  # 1-based line number -> 0-based index
    return n - 1


def expect(n, needle):
    line = lines[at(n)]
    if needle.encode() not in line:
        raise SystemExit(f"ANCHOR MISMATCH at line {n}: {line!r} does not contain {needle!r}")


# --- anchors (fail loudly if the file has drifted since 0f7614a) ---
expect(1007, "def _scaled_or_carried(self, field, ref_stock, ref_base, projected_base, partial_bs):")
expect(1031, "carried = _get_field(partial_bs, field)")
expect(1046, "")  # blank line before _project_balance_sheet
expect(1047, "def _project_balance_sheet(")
expect(1114, "ref_sp16 = _get_field(ref_bs, 'sp16_debiti_breve')")
expect(1176, "# Short-term debt: proportional to operating costs (turnover ratio)")
expect(1179, ")")  # closing paren of the old sp16 = self._scaled_or_carried(...) call
expect(1183, "sp17 = _get_field(partial_bs, 'sp17_debiti_lungo')")
expect(1184, "sp18 = _get_field(partial_bs, 'sp18_ratei_risconti_passivi')")
expect(1198, "sp16a, sp16b, sp16c, sp16d, sp16e, sp16f, sp16g = self._distribute_sp16(ref_bs, sp16)")
expect(1199, "sp17a, sp17b, sp17c, sp17d, sp17e, sp17f, sp17g = self._distribute_sp17(ref_bs, sp17)")
expect(1831, "return (Decimal('0'),) * 7")
expect(1833, "def _save_forecast(self, scenario_id: int, year: int, bs_data: Dict, inc_data: Dict):")

CRLF = b"\r\n"
LF = b"\n"

new_lines = []

# 1) lines 1..1006 unchanged
new_lines += lines[: at(1007)]

# 2) line 1007: new signature (same CRLF style as original line)
new_lines.append(
    b"    def _scaled_or_carried(self, field, ref_stock, ref_base, projected_base, partial_bs, carried_value=None):" + CRLF
)

# 3) lines 1008..1030 unchanged
new_lines += lines[at(1008): at(1031)]

# 4) line 1031: carried_value override
new_lines.append(
    b"        carried = _get_field(partial_bs, field) if carried_value is None else carried_value" + CRLF
)

# 5) lines 1032..1046 unchanged (rest of _scaled_or_carried + blank line before _project_balance_sheet)
new_lines += lines[at(1032): at(1047)]

# 6) NEW helper method, inserted before `def _project_balance_sheet(` (line 1047).
#    Same CRLF style as the surrounding method bodies.
helper = """    def _declare_reference_financial_debt_undetailed(self, aggregate, ref_bs, partial_fields):
        \"\"\"Dichiara quando il bilancio di riferimento non ha ALCUN dettaglio
        finanziario (banche/altri finanziatori/obbligazioni) su ``aggregate``
        (``sp16`` o ``sp17``) mentre il periodo parziale sì. Non è un errore:
        è il motivo per cui il debito finanziario proiettato viene portato
        avanti dal parziale come blocco a sé invece che dalla proporzione del
        riferimento (decisione B, indagine-1-debito-bancario.md, 2026-09-11).
        Fedele alla convenzione già in uso in questo motore per le altre
        diagnostiche di questa famiglia (``degenerate_turnover_ratio``,
        ``missing_short_debt_breakdown``): si dichiara solo quando la
        condizione scatta davvero, mai un \\"nessun problema\\" ad ogni
        proiezione -- l'assenza della chiave vale zero, non un tacere.\"\"\"
        ref_fin_fields = {
            'sp16': (
                'sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                'sp16c_debiti_obbligazioni_breve',
            ),
            'sp17': (
                'sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                'sp17c_debiti_obbligazioni_lungo',
            ),
        }[aggregate]
        ref_has_detail = any(
            _get_field(ref_bs, f) != 0 for f in ref_fin_fields
        )
        partial_amounts = {f: v for f, v in partial_fields if v != 0}
        if ref_has_detail or not partial_amounts:
            return
        totale = sum(partial_amounts.values(), Decimal('0'))
        self._diagnostics.append({
            'code': 'reference_financial_debt_undetailed',
            'severity': 'warning',
            'aggregate': aggregate,
            'fields': {f: str(v) for f, v in partial_amounts.items()},
            'amount': str(totale),
            'message': (
                f"Il bilancio di riferimento non ha dettaglio finanziario su "
                f"{aggregate} (banche/altri finanziatori/obbligazioni tutte a "
                f"zero): il debito finanziario del periodo parziale "
                f"({eur_it(totale)}) è stato portato avanti così com'è, non "
                f"ridistribuito con le proporzioni del riferimento."
            ),
        })

"""
new_lines.append(helper.encode("utf-8").replace(b"\n", CRLF))

# 7) line 1047 (`def _project_balance_sheet(`) onward, unchanged up to line 1113
new_lines += lines[at(1047): at(1114)]

# 8) line 1114: replace `ref_sp16 = ...` with the operating-only ref stock
block_1114 = (
    b"        # Financial debt (banche/altri finanziatori/obbligazioni) is not driven" + CRLF +
    b"        # by operating costs: it is carried forward from the partial year as" + CRLF +
    b"        # its own block (below), never scaled by this ratio. Only the" + CRLF +
    b"        # OPERATING residual of sp16 (fornitori/tributari/previdenziali/altri)" + CRLF +
    b"        # rotates with the reference year's cost turnover." + CRLF +
    b"        ref_sp16_operativo = (" + CRLF +
    b"            _get_field(ref_bs, 'sp16_debiti_breve')" + CRLF +
    b"            - _get_field(ref_bs, 'sp16a_debiti_banche_breve')" + CRLF +
    b"            - _get_field(ref_bs, 'sp16b_debiti_altri_finanz_breve')" + CRLF +
    b"            - _get_field(ref_bs, 'sp16c_debiti_obbligazioni_breve')" + CRLF +
    b"        )" + CRLF
)
new_lines.append(block_1114)

# 9) lines 1115..1175 unchanged
new_lines += lines[at(1115): at(1176)]

# 10) lines 1176..1179 (comment + sp16 = self._scaled_or_carried( ... )) replaced.
block_sp16 = (
    b"        # Financial debt (banche/altri finanziatori/obbligazioni) is carried" + CRLF +
    b"        # forward from the partial year as its own block -- exactly like sp17" + CRLF +
    b"        # below -- and is changed only by the explicit repayment/financing" + CRLF +
    b"        # rules in _apply_debt_repayment. It is never scaled by the" + CRLF +
    b"        # cost-turnover ratio and never redistributed with the reference" + CRLF +
    b"        # year's proportions (decisione B, indagine-1-debito-bancario.md):" + CRLF +
    b"        # a real mutuo is not driven by fatturato/costi. Only the OPERATING" + CRLF +
    b"        # residual (fornitori/tributari/previdenziali/altri) rotates." + CRLF +
    b"        partial_sp16a = _get_field(partial_bs, 'sp16a_debiti_banche_breve')" + CRLF +
    b"        partial_sp16b = _get_field(partial_bs, 'sp16b_debiti_altri_finanz_breve')" + CRLF +
    b"        partial_sp16c = _get_field(partial_bs, 'sp16c_debiti_obbligazioni_breve')" + CRLF +
    b"        partial_sp16_fin = partial_sp16a + partial_sp16b + partial_sp16c" + CRLF +
    b"        partial_sp16_operativo = (" + CRLF +
    b"            _get_field(partial_bs, 'sp16_debiti_breve') - partial_sp16_fin" + CRLF +
    b"        )" + CRLF +
    b"        self._declare_reference_financial_debt_undetailed(" + CRLF +
    b"            'sp16', ref_bs," + CRLF +
    b"            (" + CRLF +
    b"                ('sp16a_debiti_banche_breve', partial_sp16a)," + CRLF +
    b"                ('sp16b_debiti_altri_finanz_breve', partial_sp16b)," + CRLF +
    b"                ('sp16c_debiti_obbligazioni_breve', partial_sp16c)," + CRLF +
    b"            )," + CRLF +
    b"        )" + CRLF +
    CRLF +
    b"        # Short-term OPERATING debt: proportional to operating costs (turnover ratio)" + CRLF +
    b"        sp16_operativo = self._scaled_or_carried(" + CRLF +
    b"            'sp16_debiti_breve_operativo', ref_sp16_operativo, ref_costs," + CRLF +
    b"            projected_costs, partial_bs, carried_value=partial_sp16_operativo," + CRLF +
    b"        )" + CRLF +
    b"        sp16 = partial_sp16_fin + sp16_operativo" + CRLF
)
new_lines.append(block_sp16)

# 11) lines 1180..1182 (blank + two comment lines before `sp17 = ...`) unchanged
new_lines += lines[at(1180): at(1183)]

# 12) line 1183 (`sp17 = _get_field(...)`) unchanged, THEN insert new LF lines
#     (matches the file's existing LF style from here on) before line 1184.
new_lines.append(lines[at(1183)])
extra_sp17 = (
    b"        partial_sp17a = _get_field(partial_bs, 'sp17a_debiti_banche_lungo')" + LF +
    b"        partial_sp17b = _get_field(partial_bs, 'sp17b_debiti_altri_finanz_lungo')" + LF +
    b"        partial_sp17c = _get_field(partial_bs, 'sp17c_debiti_obbligazioni_lungo')" + LF +
    b"        partial_sp17_fin = partial_sp17a + partial_sp17b + partial_sp17c" + LF +
    b"        self._declare_reference_financial_debt_undetailed(" + LF +
    b"            'sp17', ref_bs," + LF +
    b"            (" + LF +
    b"                ('sp17a_debiti_banche_lungo', partial_sp17a)," + LF +
    b"                ('sp17b_debiti_altri_finanz_lungo', partial_sp17b)," + LF +
    b"                ('sp17c_debiti_obbligazioni_lungo', partial_sp17c)," + LF +
    b"            )," + LF +
    b"        )" + LF
)
new_lines.append(extra_sp17)

# 13) lines 1184..1197 unchanged (sp18 = ... through the line before the distribute calls)
new_lines += lines[at(1184): at(1198)]

# 14) lines 1198..1199 (distribute calls) replaced
block_dist = (
    b"        sp16a, sp16b, sp16c = partial_sp16a, partial_sp16b, partial_sp16c" + LF +
    b"        sp16d, sp16e, sp16f, sp16g = self._distribute_sp16_operativo(" + LF +
    b"            ref_bs, sp16_operativo" + LF +
    b"        )" + LF +
    b"        sp17a, sp17b, sp17c = partial_sp17a, partial_sp17b, partial_sp17c" + LF +
    b"        sp17_operativo = sp17 - partial_sp17_fin" + LF +
    b"        sp17d, sp17e, sp17f, sp17g = self._distribute_sp17_operativo(" + LF +
    b"            ref_bs, sp17_operativo" + LF +
    b"        )" + LF
)
new_lines.append(block_dist)

# 15) lines 1200..1831 unchanged (rest of _project_balance_sheet, the annualized
#     branch, _apply_debt_repayment, _distribute_sp02.._distribute_sp17 -- none
#     of these are touched)
new_lines += lines[at(1200): at(1832)]

# 16) NEW methods, inserted between `_distribute_sp17`'s end (line 1831) and the
#     blank line before `_save_forecast` (line 1832). Same CRLF style as neighbours.
new_methods = """    def _distribute_sp16_operativo(self, ref_bs, sp16_operativo_total):
        \"\"\"Distribute only the OPERATING residual of sp16 (fornitori/
        tributari/previdenziali/altri) using the reference year's
        proportions. Financial debt (banche/altri finanziatori/obbligazioni,
        sp16a-c) is never part of this residual: it is carried forward from
        the partial year as its own block (decisione B,
        indagine-1-debito-bancario.md) and is not touched here.\"\"\"
        fields = (
            'sp16d_debiti_fornitori_breve', 'sp16e_debiti_tributari_breve',
            'sp16f_debiti_previdenza_breve', 'sp16g_altri_debiti_breve',
        )
        total = sum((_get_field(ref_bs, f) for f in fields), Decimal('0'))
        if total > 0:
            r = sp16_operativo_total / total
            return tuple(_get_field(ref_bs, f) * r for f in fields)
        if sp16_operativo_total != 0:
            self._diagnostics.append({
                'code': 'missing_short_debt_breakdown',
                'severity': 'error',
                'amount': str(sp16_operativo_total),
                'message': (
                    "La ripartizione del debito operativo a breve (fornitori/"
                    "tributario/previdenziale/altri) non è disponibile: "
                    "nessuna categoria è stata inventata."
                ),
            })
        return (Decimal('0'),) * 4

    def _distribute_sp17_operativo(self, ref_bs, sp17_operativo_total):
        \"\"\"Distribute only the OPERATING residual of sp17 -- mirrors
        _distribute_sp16_operativo for the long-term side.\"\"\"
        fields = (
            'sp17d_debiti_fornitori_lungo', 'sp17e_debiti_tributari_lungo',
            'sp17f_debiti_previdenza_lungo', 'sp17g_altri_debiti_lungo',
        )
        total = sum((_get_field(ref_bs, f) for f in fields), Decimal('0'))
        if total > 0:
            r = sp17_operativo_total / total
            return tuple(_get_field(ref_bs, f) * r for f in fields)
        if sp17_operativo_total != 0:
            self._diagnostics.append({
                'code': 'missing_short_debt_breakdown',
                'severity': 'error',
                'amount': str(sp17_operativo_total),
                'message': (
                    "La ripartizione del debito operativo a lungo (fornitori/"
                    "tributario/previdenziale/altri) non è disponibile: "
                    "nessuna categoria è stata inventata."
                ),
            })
        return (Decimal('0'),) * 4

"""
new_lines.append(("\n" + new_methods.rstrip("\n") + "\n").encode("utf-8").replace(b"\n", CRLF))

# 17) lines 1832.. end unchanged (the blank line already there keeps exactly one
#     blank line before `_save_forecast`)
new_lines += lines[at(1832):]

with open(path, "wb") as f:
    f.write(b"".join(new_lines))

print("patched", path)
```

## Constraints

- Nessun cambiamento a `calculations/forecast_engine.py` né a `calculations/projection_common.py`.
- Nessun cambiamento al ramo `_project_balance_sheet_annualized` (righe 1354-1495): è già corretto.
- Nessun cambiamento a `_distribute_sp06`/`_distribute_sp07`: si misurano (Step 9), non si
  correggono in questo task — il Task 2 se ne occupa.
- Nessun cambiamento a `_apply_debt_repayment`: riceve un input diverso (corretto invece di
  azzerato), ma il suo codice non cambia di una riga.
- Denaro sempre in `Decimal`; messaggio della diagnostica sempre in italiano con `eur_it()`.
- Terminatori di riga: CRLF e LF preservati esattamente dove erano; nessuna normalizzazione globale
  del file.
- Il motore budget non si tocca: il banco di parità (`scripts/parita_motore.py`) deve restare a 0
  divergenze (Step 11).

## Ownership

`calculations/intra_year_engine.py`, `tests/test_intra_year_debito_bancario.py` (estensione, non
nuovo file), `CLAUDE.md` (§ Intra-Year Engine), `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` (§5).

## Step

- [ ] **Step 1: Base.** `cd /home/peter/DEV/budget && git rev-parse HEAD` (deve stampare
  `0f7614a...`; annotalo per il rapporto di fine task).

- [ ] **Step 2: Test nuovi, prova rossa.** Aggiungi in coda a
  `tests/test_intra_year_debito_bancario.py` (dopo l'ultimo test esistente,
  `test_la_proiezione_persiste_la_ripartizione_e_la_cassa_non_cambia`):

```python


def _stato_sp16(**over):
    """Stato patrimoniale minimo per i tre test nuovi (indagine-1-debito-bancario.md):
    solo i campi di sp16/sp17 e il minimo per far quadrare Attivo=Passivo (sp09, sp11)."""
    zero = D("0")
    base = dict(
        sp16_debiti_breve=zero, sp16a_debiti_banche_breve=zero, sp16b_debiti_altri_finanz_breve=zero,
        sp16c_debiti_obbligazioni_breve=zero, sp16d_debiti_fornitori_breve=zero, sp16e_debiti_tributari_breve=zero,
        sp16f_debiti_previdenza_breve=zero, sp16g_altri_debiti_breve=zero,
        sp17_debiti_lungo=zero, sp17a_debiti_banche_lungo=zero, sp17b_debiti_altri_finanz_lungo=zero,
        sp17c_debiti_obbligazioni_lungo=zero, sp17d_debiti_fornitori_lungo=zero, sp17e_debiti_tributari_lungo=zero,
        sp17f_debiti_previdenza_lungo=zero, sp17g_altri_debiti_lungo=zero,
        sp09_disponibilita_liquide=D("500000"), sp11_capitale=D("100000"),
    )
    base.update(over)
    return base


def _proietta_con_riferimento(stato_riferimento, stato_parziale, **ipotesi):
    """Come _proietta, ma con uno stato patrimoniale DIVERSO per l'anno di
    riferimento (2024, pieno) e per il parziale (2025, 9 mesi) -- _proietta usa
    lo stesso stato per entrambi, quindi non puo' esercitare la ripartizione
    reference vs. partial che ha causato indagine-1-debito-bancario.md."""
    db = _sessione()
    azienda = Company(name="Banca infra 2", tax_id="BANCA-INFRA-2", sector=1)
    db.add(azienda)
    db.flush()
    fy_ref = FinancialYear(company_id=azienda.id, year=2024, period_months=None,
                           validation_status="verified", forecastable=True)
    db.add(fy_ref); db.flush()
    db.add(BalanceSheet(financial_year_id=fy_ref.id, **stato_riferimento))
    db.add(IncomeStatement(financial_year_id=fy_ref.id))
    fy_par = FinancialYear(company_id=azienda.id, year=2025, period_months=9,
                           validation_status="verified", forecastable=True)
    db.add(fy_par); db.flush()
    db.add(BalanceSheet(financial_year_id=fy_par.id, **stato_parziale))
    db.add(IncomeStatement(financial_year_id=fy_par.id))
    scenario = BudgetScenario(company_id=azienda.id, name="infra2", base_year=2024,
                              scenario_type="infrannuale", period_months=9)
    db.add(scenario); db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"), **ipotesi))
    db.commit()
    result = IntraYearEngine(db).generate_projection(scenario.id)
    sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return sp, result['diagnostics']


def test_il_debito_bancario_si_porta_avanti_dal_parziale_quando_il_riferimento_non_ha_dettaglio():
    """indagine-1-debito-bancario.md: un riferimento senza dettaglio finanziario
    (tutto sp16g, il 98% dei bilanci annuali del database) NON deve azzerare il
    debito bancario reale del parziale. Prima della correzione: sp16a 0,00."""
    ref = _stato_sp16(sp16_debiti_breve=D("100000"), sp16g_altri_debiti_breve=D("100000"),
                       sp09_disponibilita_liquide=D("200000"))
    parziale = _stato_sp16(sp16_debiti_breve=D("50000"), sp16a_debiti_banche_breve=D("30000"),
                            sp16d_debiti_fornitori_breve=D("20000"), sp09_disponibilita_liquide=D("150000"))
    sp, diagnostics = _proietta_con_riferimento(ref, parziale)
    assert sp.sp16a_debiti_banche_breve == D("30000.00")
    assert sp.sp16_debiti_breve == D("50000.00")
    codici = [d['code'] for d in diagnostics]
    assert 'reference_financial_debt_undetailed' in codici
    diag = next(d for d in diagnostics if d['code'] == 'reference_financial_debt_undetailed')
    assert diag['aggregate'] == 'sp16'
    assert diag['severity'] == 'warning'
    assert diag['fields'] == {'sp16a_debiti_banche_breve': '30000.00'}


def test_nessuna_regressione_quando_il_riferimento_ha_dettaglio_bancario():
    """Il caso "che funziona" di indagine-1 (fase 2, azienda 21/scenario 4): il
    riferimento ha una propria quota bancaria, diversa da quella del parziale.
    Prima della correzione la quota veniva comunque RISCALATA sulla proporzione
    del riferimento (40% del totale, qui 32.000,00); dopo, il debito bancario
    prende il valore ESATTO del parziale (25.000,00), mai una proporzione presa
    da un anno diverso."""
    ref = _stato_sp16(sp16_debiti_breve=D("100000"), sp16a_debiti_banche_breve=D("40000"),
                       sp16d_debiti_fornitori_breve=D("60000"), sp09_disponibilita_liquide=D("200000"))
    parziale = _stato_sp16(sp16_debiti_breve=D("80000"), sp16a_debiti_banche_breve=D("25000"),
                            sp16d_debiti_fornitori_breve=D("55000"), sp09_disponibilita_liquide=D("180000"))
    sp, diagnostics = _proietta_con_riferimento(ref, parziale)
    assert sp.sp16a_debiti_banche_breve == D("25000.00")
    assert not any(d['code'] == 'reference_financial_debt_undetailed' for d in diagnostics)


def test_il_debito_bancario_scende_della_rata_non_della_rotazione():
    """Riferimento senza dettaglio finanziario + piano di rimborso attivo
    (existing_debt_repayment_years=5): il debito bancario del parziale
    (100.000,00) scende della RATA (100.000,00/5=20.000,00), non della
    proporzione del riferimento (che lo azzererebbe)."""
    ref = _stato_sp16(sp16_debiti_breve=D("100000"), sp16g_altri_debiti_breve=D("100000"),
                       sp09_disponibilita_liquide=D("200000"))
    parziale = _stato_sp16(sp16_debiti_breve=D("120000"), sp16a_debiti_banche_breve=D("100000"),
                            sp16d_debiti_fornitori_breve=D("20000"), sp09_disponibilita_liquide=D("220000"))
    sp, diagnostics = _proietta_con_riferimento(ref, parziale, existing_debt_repayment_years=D("5"))
    assert sp.sp16a_debiti_banche_breve == D("80000.00")
    assert any(d['code'] == 'reference_financial_debt_undetailed' for d in diagnostics)
```

- [ ] **Step 3: Prova rossa.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_intra_year_debito_bancario.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **2 dei 3 test nuovi FALLISCONO** (`test_il_debito_bancario_si_porta_avanti_dal_parziale...`
  su `sp16a == 30000.00` — oggi produce `0.00`; `test_il_debito_bancario_scende_della_rata...` su
  `sp16a == 80000.00` — oggi produce `0.00`), il terzo (non-regressione) fallisce anch'esso, ma su un
  valore diverso da zero: `sp16a == 25000.00` — oggi produce `32000.00` (il vecchio comportamento,
  che riscala sulla proporzione del riferimento). I 9 test esistenti restano verdi.

- [ ] **Step 4: Verifica i terminatori di riga prima di toccare il file.**
  ```bash
  file calculations/intra_year_engine.py
  ```
  Atteso: "with CRLF, LF line terminators" (misti).

- [ ] **Step 5: Implementa il Change.** Salva lo script della sezione «Change» come
  `/tmp/patch_task_1.py` ed eseguilo:
  ```bash
  cd /home/peter/DEV/budget
  python3 /tmp/patch_task_1.py calculations/intra_year_engine.py
  ```
  Atteso: stampa `patched calculations/intra_year_engine.py`, nessun `ANCHOR MISMATCH`. Se compare un
  `ANCHOR MISMATCH`, il file è cambiato: fermarsi e riadattare gli ancoraggi al codice attuale prima
  di procedere — non forzare la patch.

- [ ] **Step 6: Verifica sintattica e diff minimo.**
  ```bash
  python3 -c "import ast; ast.parse(open('calculations/intra_year_engine.py', encoding='utf-8').read())" && echo "syntax ok"
  file calculations/intra_year_engine.py
  git diff --stat calculations/intra_year_engine.py
  ```
  Atteso: `syntax ok`; ancora "with CRLF, LF line terminators"; `git diff --stat` mostra circa **159
  inserzioni, 8 cancellazioni** su un solo file. Uno scarto grande (centinaia di righe cancellate)
  indica quasi certamente una normalizzazione accidentale dei terminatori: fermarsi e controllare
  `git diff` per intero prima di proseguire.

- [ ] **Step 7: Verde.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_intra_year_debito_bancario.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **12 passed** (9 esistenti + 3 nuovi).

- [ ] **Step 8: Le 8 misure — prima/dopo sugli scenari infrannuali del database.** Su una **copia**
  del database:
  ```bash
  sqlite3 financial_analysis.db ".backup '/tmp/task1_db.sqlite'"
  ```
  Per ciascuno degli 8 scenari `infrannuale` presenti nel database — **verifica prima l'elenco
  corrente** con
  `sqlite3 /tmp/task1_db.sqlite "select id from budget_scenarios where scenario_type='infrannuale'"`
  (id 1, 3, 4, 5, 8, 9, 12, 18 alla data di stesura di questo piano, dei quali 5 su 8 generano una
  proiezione — 3, id 1/3/9, falliscono già oggi per dati mancanti, condizione pre-esistente non
  causata da questo task) — genera la proiezione **prima** della patch e **dopo**, leggendo
  `sp16a/b/c`, `sp17a/b/c`, gli aggregati `sp16`/`sp17`, `sp09`, lo sbilancio (Attivo − Passivo) e
  la PFN (`sp16a+b+c+sp17a+b+c − sp09`) dal `ForecastBalanceSheet` prodotto. Valori misurati durante
  la stesura di questa bozza (annotali di nuovo nell'ambiente reale, potrebbero essere leggermente
  diversi se il database di sviluppo è cambiato):

  | Scenario | Azienda | Riferimento → Parziale | Campo | Prima | Dopo |
  |---|---|---|---|---:|---:|
  | 4 | id 21 | 2025 (pieno, **con** dettaglio bancario) → 2026 9m | `sp16a` | 370.214,75 | 355.381,20 |
  | 4 | id 21 | idem | `sp16` (aggregato) | 706.434,97 | 727.215,91 |
  | 4 | id 21 | idem | `sp09` | 0,00 | 15.271,65 |
  | 4 | id 21 | idem | **sbilancio** | **5.509,29** | **0,00** |
  | 4 | id 21 | idem | PFN | 370.214,75 | 340.109,55 |
  | 5 | id 21 | 2024 (pieno) → 2025 (period_months=12, caso limite) | tutti | invariati | invariati |
  | 8 | id 48 | 2025 (pieno, un po' di dettaglio bancario) → 2026 5m | `sp16a` | 4.051,19 | 1.161.731,57 |
  | 8 | id 48 | idem | `sp17a`/`sp17b` | 178.131,87 / 0,00 | 219.911,54 / 62.500,00 |
  | 8 | id 48 | idem | **sbilancio** | **24.524,62** | **0,00** |
  | 8 | id 48 | idem | PFN | 182.183,06 | 310.987,35 |
  | 12 | id 50 | 2026 (pieno) → 2026 9m | tutti | invariati | invariati |
  | 18 | id 237 | 2025 (pieno, **senza** alcun dettaglio finanziario) → 2026 6m | `sp16a` | **0,00** | **353.408,65** |
  | 18 | id 237 | idem | `sp17a`/`sp17b` | 0,00 / 0,00 | 467.528,52 / 36.503,74 |
  | 18 | id 237 | idem | `sp16` (aggregato) | 1.725.761,50 | 2.079.170,15 |
  | 18 | id 237 | idem | `sp09` | 1.086.291,98 | 1.439.700,63 |
  | 18 | id 237 | idem | **PFN** | **−1.086.291,98** | **−582.259,72** |

  **Nota per chi esegue**: lo sbilancio residuo degli scenari 4 e 8 **sparisce** dopo questa
  correzione (5.509,29 → 0,00 e 24.524,62 → 0,00) — è un fatto misurato durante questo Step, non un
  effetto richiesto dal Target. Non risolve né tocca il difetto tributario del promote: quello è il
  Task 3, che ri-misura questo stesso scenario **dopo** anche il Task 2 (vedi Task 3, Step di
  ri-misura). Annotalo nel rapporto di fine task, non correggerlo qui.

- [ ] **Step 9: Misura (non corregge) il rischio sui crediti — `_distribute_sp06`/
  `_distribute_sp07`.** Sulla stessa copia del database, esegui (script completo, sola lettura):

  ```python
  """Misura (non corregge) quante coppie riferimento/parziale del database avrebbero
  lo stesso azzeramento del difetto 1, ma sui CREDITI (_distribute_sp06/_distribute_sp07)
  invece che sui debiti finanziari. Sola lettura: usare SEMPRE una copia del DB.

  Uso: python misura_rischio_crediti.py /percorso/copia/db.sqlite
  """
  import sqlite3
  import sys

  REAL_FIELDS_06 = [
      "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
      "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
      "sp06f_imposte_anticipate_breve",  # sp06e (tributari) e' ricalcolato a parte, escluso
  ]
  REAL_FIELDS_07 = [
      "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
      "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
      "sp07f_imposte_anticipate_lungo",
  ]


  def righe(conn, aggregate_field, real_fields):
      cols = ", ".join(["fy.id", "fy.company_id", "fy.year", "fy.period_months", aggregate_field] + real_fields)
      cur = conn.execute(f"""
          SELECT {cols}
          FROM financial_years fy JOIN balance_sheets bs ON bs.financial_year_id = fy.id
      """)
      out = {}
      for row in cur.fetchall():
          fy_id, company_id, year, period_months = row[0], row[1], row[2], row[3]
          aggregate = row[4]
          real_sum = sum(row[5:])
          out[fy_id] = dict(company_id=company_id, year=year, period_months=period_months,
                             aggregate=aggregate, real_sum=real_sum)
      return out


  def main(db_path):
      conn = sqlite3.connect(db_path)
      rischi = []
      for aggregate_field, real_fields, nome in (
          ("sp06_crediti_breve", REAL_FIELDS_06, "sp06"),
          ("sp07_crediti_lungo", REAL_FIELDS_07, "sp07"),
      ):
          dati = righe(conn, aggregate_field, real_fields)
          per_company = {}
          for fy_id, d in dati.items():
              per_company.setdefault(d["company_id"], []).append((fy_id, d))
          for company_id, anni in per_company.items():
              pieni = [(i, d) for i, d in anni if d["period_months"] in (None, 12)]
              parziali = [(i, d) for i, d in anni if d["period_months"] not in (None, 12)]
              for pid, pd in parziali:
                  for rid, rd in pieni:
                      ref_undetailed = rd["aggregate"] and rd["real_sum"] == 0
                      partial_has_detail = pd["real_sum"] > 0
                      if ref_undetailed and partial_has_detail:
                          rischi.append(dict(
                              aggregate=nome, company_id=company_id,
                              ref_fy=rid, ref_year=rd["year"],
                              partial_fy=pid, partial_year=pd["year"],
                              partial_period_months=pd["period_months"],
                              importo_a_rischio=pd["real_sum"],
                          ))
      print(f"Coppie a rischio trovate: {len(rischi)}")
      for r in rischi:
          print(f"  {r['aggregate']}: azienda {r['company_id']}, riferimento {r['ref_year']} (fy {r['ref_fy']}) "
                f"-> parziale {r['partial_year']} {r['partial_period_months']}m (fy {r['partial_fy']}), "
                f"importo reale a rischio {r['importo_a_rischio']:.2f}")


  if __name__ == "__main__":
      main(sys.argv[1] if len(sys.argv) > 1 else "financial_analysis.db")
  ```

  ```bash
  python3 misura_rischio_crediti.py /tmp/task1_db.sqlite
  ```

  **Risultato misurato durante la stesura di questo piano** (database del repository):

  ```
  Coppie a rischio trovate: 3
    sp06: azienda 237, riferimento 2025 (fy 192) -> parziale 2026 6m (fy 190), importo reale a rischio 1090958.55
    sp06: azienda 237, riferimento 2024 (fy 193) -> parziale 2026 6m (fy 190), importo reale a rischio 1090958.55
    sp06: azienda 237, riferimento 2026 (fy 207) -> parziale 2026 6m (fy 190), importo reale a rischio 1090958.55
  ```

  Lettura: **una sola azienda coinvolta (id 237, la stessa del difetto 1)**, una sola massa reale
  a rischio (1.090.958,55 di crediti clienti a breve, `sp06a`) — le 3 righe sono lo stesso parziale
  confrontato con 3 candidati di riferimento diversi, non 3 aziende diverse. Il Task 2 corregge
  esattamente questo rischio. **Non correggere `_distribute_sp06`/`_distribute_sp07` in questo
  Step**: riporta il risultato nel rapporto di fine task.

- [ ] **Step 10: Suite completa.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests -q \
    --ignore=tests/corpus -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Esegui **prima** della patch (per stabilire il tuo proprio numero di riferimento in questo
  ambiente) e **dopo**: il conteggio di `failed` non deve aumentare.

- [ ] **Step 11: Banco di parità del motore budget (controllo negativo — il motore budget non si
  tocca).**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py 0f7614a --anni 4 --controllo-negativo
  ```
  Atteso: 0 divergenze, esattamente come prima di questo task.

- [ ] **Step 12: Documentazione — CLAUDE.md.** In `CLAUDE.md`, § «Intra-Year Engine (Infrannuale)»,
  sostituisci:

  **Prima:**
  ```
  Bank debt follows the budget engine's rules from the shared code (`projection_common.contratti_da_riga_finanziamento`,
  `separa_prestiti_nuovi`, `quota_breve_prestiti_nuovi`): pre-existing bank debt keeps its own split and is reduced only by
  its own instalments, a new loan amortises on its own with next year's instalment in `sp16a`.
  ```

  **Dopo:**
  ```
  Financial debt (`sp16a-c`/`sp17a-c`: banks, other lenders, bonds) is carried forward from the
  partial year's own split, as its own block — never rebuilt from the reference year's proportions,
  because a real loan is not driven by turnover. Only the operating residual of `sp16`/`sp17`
  (fornitori/tributari/previdenziali/altri) still rotates on the reference year's cost-turnover
  ratio. When the reference year has no financial-debt detail at all while the partial year does
  (98% of full-year balance sheets have none — see the bullet above on `base_bank_debt`), the split
  used to be silently reclassified into "altri debiti" (indagine-1-debito-bancario.md, 2026-09-11);
  now it is declared, `reference_financial_debt_undetailed` (severity `warning`). Bank debt is then
  reduced only by its own instalments via the shared code
  (`projection_common.contratti_da_riga_finanziamento`, `separa_prestiti_nuovi`,
  `quota_breve_prestiti_nuovi`): pre-existing bank debt keeps its own split, a new loan amortises on
  its own with next year's instalment in `sp16a`.
  ```

- [ ] **Step 13: Documentazione — REGOLE-IMPORT-05-INFRANNUALE.md.** Due punti in
  `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5.

  **Riga della tabella «Il roll-forward dello Stato Patrimoniale» — prima:**
  ```
  | **Debiti a breve** | con riferimento: proporzionali ai costi operativi proiettati (salvo rapporto degenere, sotto); senza: invariati |
  ```

  **Dopo:**
  ```
  | **Debiti a breve** | **debito finanziario (banche/altri finanziatori/obbligazioni)**: invariato dal parziale, come i debiti a lungo sotto; **residuo operativo** (fornitori/tributari/previdenziali/altri): con riferimento proporzionale ai costi operativi proiettati (salvo rapporto degenere, sotto), senza riferimento invariato |
  ```

  **Sezione «Le sotto-voci si distribuiscono, mai si inventano» — prima:**
  ```
  Le quote si distribuiscono **proporzionalmente** alla fonte (il riferimento nel regime 1, il
  parziale nel regime 2). Se la fonte non ha alcuna ripartizione, tutte le quote sono **zero** più
  un diagnostico: *"La ripartizione dei debiti a breve non è disponibile: nessuna categoria è stata inventata."* —
  esplicitamente **non** uno split 40/60 fra finanziario e operativo.
  ```

  **Dopo:**
  ```
  Vale per il **residuo operativo** di `sp16`/`sp17` (fornitori/tributari/previdenziali/altri): le
  quote si distribuiscono **proporzionalmente** alla fonte (il riferimento nel regime 1, il parziale
  nel regime 2). Se la fonte non ha alcuna ripartizione operativa, tutte le quote sono **zero** più
  un diagnostico: *"La ripartizione del debito operativo a breve (fornitori/tributario/previdenziale/
  altri) non è disponibile: nessuna categoria è stata inventata."*

  Il **debito finanziario** (banche/altri finanziatori/obbligazioni, `sp16a-c`/`sp17a-c`) **non**
  segue questa regola: si porta avanti dal parziale come blocco a sé, in ENTRAMBI i regimi — mai
  dalla proporzione del riferimento — perché un mutuo non è trainato dal fatturato o dai costi
  operativi (`indagine-1-debito-bancario.md`, 2026-09-11). Quando il riferimento non ha alcun
  dettaglio finanziario (nessuna delle tre categorie popolata) e il parziale sì, il motore lo
  dichiara con `reference_financial_debt_undetailed` (severità *warning*: non è un errore, è il
  motivo per cui la ripartizione viene dal parziale invece che dal riferimento).
  ```

- [ ] **Step 14: Commit.**
  ```bash
  git add calculations/intra_year_engine.py tests/test_intra_year_debito_bancario.py \
    CLAUDE.md docs/import/REGOLE-IMPORT-05-INFRANNUALE.md
  git commit -F - <<'EOF'
  fix(infrannuale): il debito finanziario si porta avanti dal parziale, non dalla proporzione del riferimento

  _distribute_sp16/_distribute_sp17 (calculations/intra_year_engine.py) ridistribuivano l'intero
  debito a breve/lungo proiettato -- banca compresa -- con le proporzioni del bilancio di
  RIFERIMENTO. Quando il riferimento non ha dettaglio finanziario (98% dei bilanci annuali completi
  del database, tutto nel secchio 'altri debiti'), la quota bancaria del riferimento e' zero per
  costruzione e l'intero debito bancario reale del parziale spariva in 'altri debiti': il foglio
  quadrava, ma la PFN si spostava di quasi un milione di euro sul caso di collaudo (azienda id 237,
  scenario id 18: -1.086.291,98 -> -582.259,72).

  Il debito finanziario (sp16a-c/sp17a-c) si porta ora avanti ESATTO dal parziale, come blocco a se',
  rettificato solo dai piani espliciti gia' esistenti (_apply_debt_repayment, lotto 3A Task 4). Solo
  il residuo operativo (fornitori/tributari/previdenziali/altri) continua a scalare sulla rotazione
  dei costi operativi e a ridistribuirsi con le proporzioni del riferimento, come prima. Una nuova
  diagnostica, reference_financial_debt_undetailed (severita' warning), si dichiara quando il
  riferimento non ha alcun dettaglio finanziario e il parziale si'.

  La correzione cambia i numeri anche di scenari il cui riferimento HA dettaglio bancario (misurato
  su tutti gli scenari infrannuale del database: azienda id 21 scenario 4, azienda id 48 scenario 8)
  perche' prima la quota bancaria veniva comunque diluita nella rotazione dei costi applicata
  all'intero aggregato -- economicamente sbagliato per un mutuo, che non e' trainato dal fatturato.

  _distribute_sp06/_distribute_sp07 (crediti) hanno lo stesso schema ("Mirrors _distribute_sp16") e
  la stessa azienda del difetto qui sopra (id 237) e' l'unica a rischio anche li', sul lato breve
  (sp06a, 1.090.958,55): misurato, corretto dal Task successivo di questa ondata.

  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01C8chDC8b297itUaoK1TQNW
  EOF
  ```

## Observable acceptance

12 test verdi su `tests/test_intra_year_debito_bancario.py` (9 esistenti invariati + 3 nuovi); la
suite completa non aumenta il numero di `failed` rispetto alla propria baseline pre-patch nello
stesso ambiente; il banco di parità del motore budget resta a 0 divergenze; sullo scenario di
collaudo (azienda id 237, scenario id 18) la proiezione mostra `sp16a` 353.408,65 e `sp17a` 467.528,52
(mai più 0,00) con la diagnostica `reference_financial_debt_undetailed` dichiarata; sugli scenari il
cui riferimento ha dettaglio bancario (azienda id 21 scenario 4, azienda id 48 scenario 8) il debito
bancario proiettato coincide con quello del parziale rettificato dai soli piani espliciti, mai con
una proporzione presa dal riferimento; `_distribute_sp06`/`_distribute_sp07` restano invariati e il
rischio misurato (azienda id 237, `sp06a`, 1.090.958,55) è riportato nel rapporto di fine task, per il
Task 2; `git diff --stat` su `calculations/intra_year_engine.py` mostra solo le righe effettivamente
cambiate, mai il file intero; CLAUDE.md e `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` allineati
nello stesso commit.

---

### Task 2: La composizione dei crediti nell'infrannuale viene dal parziale, non dalla proporzione del riferimento; i campi governati altrove non perdono più massa

**Files:**
- Modify: `calculations/intra_year_engine.py` (stesso metodo del Task 1, **applicato sopra** la sua
  patch)
- Modify: `CLAUDE.md` (§ Intra-Year Engine, paragrafo «Working capital»)
- Modify: `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` (§5, riga «Crediti a breve» + terzo
  paragrafo dopo il testo del Task 1)
- Test: `tests/test_intra_year_crediti_commerciali.py` (nuovo file)

**Interfaces:**
- Consumes (dal Task 1, già applicato): il file di partenza per questo Change **non** è `0f7614a`
  nudo — è il file **già patchato** dal Task 1. Le variabili locali `partial_sp16a/b/c`,
  `partial_sp16_fin`, `partial_sp16_operativo`, `partial_sp17a/b/c`, `partial_sp17_fin`,
  `sp16_operativo`, `sp17_operativo` (introdotte dal Task 1) esistono già nel punto in cui questo
  Change inserisce codice, e **non si toccano**. I metodi `_distribute_sp16_operativo`/
  `_distribute_sp17_operativo` (Task 1) restano invariati e vengono richiamati **dentro** il blocco
  che questo Change sostituisce (vedi Change, punto 4: le chiamate a questi due metodi vengono
  **spostate**, non riscritte, dentro il nuovo blocco unico che gestisce sia `sp16`/`sp17` sia
  `sp06`/`sp07`). La diagnostica `reference_financial_debt_undetailed` (Task 1) resta invariata; lo
  stile viene riusato per la nuova `reference_receivables_undetailed`.
- Produces (per il Task 3, che si applica **sopra** questo): la posizione tributaria
  (`current_tax`, `deferred`, `manual_tax_position`, `sp06e_governed`, `sp16e_governed`,
  `sp06f_governed`, `sp07f_governed`, `sp14b_governed`, e — **solo quando `not manual_tax_position`**
  — la variabile locale `posizione` restituita da `posizione_tributaria_fine_anno(...)`) si
  calcolano ora **all'inizio** del blocco, prima di ogni chiamata a `_distribute_*`, non più subito
  prima della singola riga `sp06e, sp16e = posizione.closing_credit, posizione.closing_debt` (quella
  riga **non esiste più** come tale dopo questo Change). L'overwrite dei campi governati avviene in
  **due punti separati e non simmetrici**, e il Task 3 deve conoscerli esattamente:
  - `sp06e`/`sp06f`/`sp07f`: sovrascritti **subito dopo** le chiamate a
    `_distribute_sp06_operativo`/`_distribute_sp07_operativo` (`if sp06e_governed is not None: sp06e
    = sp06e_governed`, ecc.) — **prima** che `sp16`/`sp17` vengano nemmeno calcolati.
  - `sp16e`: sovrascritto **per ultimo**, dopo le quattro righe di riassorbimento
    (`sp06g += max(...)`, `sp07g += max(...)`, `sp16g += max(...)`, `sp17g += max(...)`), con
    `if not manual_tax_position: sp16e = sp16e_governed` — quest'ultima riga è **esattamente
    l'ancora** su cui il Task 3 innesta il proprio conguaglio (vedi Task 3, «Interfaces»): il
    conguaglio va inserito **subito prima** di questa riga, leggendo `sp16e` (che a quel punto vale
    ancora la quota-riferimento prodotta da `_distribute_sp16_operativo`, non il valore governato) e
    `posizione.closing_debt`/`posizione.cash_out`. **Sul lato crediti la stessa fuga non esiste
    più**: `sp06e` è già al valore governato quando la riga `sp06g += max(0, sp06 - sum(...))`
    esegue, quindi l'aggregato `sp06` non perde mai massa per la sostituzione — il Task 3 non deve
    (e non può, senza reintrodurre il difetto che questo task chiude) aggiungere un termine
    simmetrico su `sp06g`.

**Target.** `_distribute_sp06`/`_distribute_sp07` hanno **la stessa firma e lo stesso schema** di
`_distribute_sp16`/`_distribute_sp17` (il commento nel codice dice esplicitamente "Mirrors
`_distribute_sp16`") — stesso difetto: quando il riferimento non ha dettaglio reale sui crediti, il
credito verso clienti **reale** del parziale sparisce in "altri crediti" (misurato: 1.090.958,55 su
azienda id 237, l'unica coppia reale a rischio nel database secondo la misura del Task 1). **Un
secondo difetto, indipendente, scoperto misurando questo task**: i campi **governati altrove**
(`sp06e` dalla posizione tributaria, `sp06f`/`sp07f` dalle differite) ricevevano comunque una quota
dalla ripartizione proporzionale, quota che il calcolo fiscale poi **scarta** sovrascrivendola — la
massa scartata spariva in cassa senza alcun flusso (misurato: azienda id 48 scenario id 8,
39.781,69). Una correzione che si limitasse a scambiare `ref_bs` con `partial_bs` (l'opzione A,
scartata anche per il debito) avrebbe **peggiorato** il secondo difetto, non risolto: misurato,
quello scambio da solo dà un DSO di 75 giorni invece di 87 su azienda 237 (un salto quasi
interamente dovuto alla fuga fiscale), mentre la correzione scelta qui lo riduce a 85 giorni (un
movimento reale e piccolo). Il Change qui sotto risolve **entrambi**.

## Da leggere prima, per simbolo

- `.superpowers/sdd/2026-09-11-indagine-difetti-collaudo-3a/indagine-1-debito-bancario.md` §7 —
  cita esplicitamente `_distribute_sp06`/`_distribute_sp07` come rischio non approfondito.
- Il Task 1 di questo piano — l'intero task: questo si applica **dopo** il suo Change (vedi
  «Interfaces» sopra).
- `CLAUDE.md` § «Invarianti e trappole › Estrazione»: *"La massa non riconosciuta va in un
  sotto-campo esplicito, mai su un aggregato"* — governa il punto 1 del Target: la massa dei campi
  governati non si "perde" mai.
- `CLAUDE.md` § «Invarianti e trappole › Quadratura, diagnostica e verdetti»: *"Un estrattore
  dichiara sempre le proprie chiavi diagnostiche, anche a zero"*; *"Un difetto che quadra si
  corregge a monte, non aggiungendo un controllo a valle"* — il secondo difetto di questo task (la
  fuga fiscale) è esattamente un difetto che quadra: lo SP persistito torna sempre a zero di
  sbilancio (la cassa assorbe), quindi nessun gate esistente lo vede; si corregge a monte,
  escludendo i campi governati dalla ripartizione.

### Codice — stato attuale, verificato sul file **già patchato dal Task 1**

Il ramo con riferimento di `_project_balance_sheet`, dove oggi la composizione dei crediti si
prende dal riferimento (righe 1287-1288 sul file patchato dal Task 1):

```python
        sp06a, sp06b, sp06c, sp06d, sp06e, sp06f, sp06g = self._distribute_sp06(ref_bs, sp06)
        sp07a, sp07b, sp07c, sp07d, sp07e, sp07f, sp07g = self._distribute_sp07(ref_bs, sp07)
```

`_distribute_sp06` (righe 1818-1836 sul file patchato dal Task 1), il meccanismo esatto della
perdita — quando `ref_bs` ha **tutto** il totale in `sp06g`, il rapporto moltiplica zero per ogni
categoria tranne `g`, e l'intera massa proiettata finisce lì. **A differenza di `_distribute_sp16`,
qui non c'è nemmeno una diagnostica quando il totale del riferimento è zero**:

```python
    def _distribute_sp06(self, ref_bs, sp06_total):
        """Distribute sp06 (current receivables) into sub-categories proportionally
        from the base year, so detail lines — notably 'crediti tributari' (sp06e) —
        move WITH the projected aggregate instead of staying frozen (P3). Mirrors
        _distribute_sp16. When the base year has no sub-detail (abbreviato: only the
        aggregate populated) it returns zeros and the frontend reconciler plugs the
        gap into 'altri', same as the debiti side."""
        fields = (
            'sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
            'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
            'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
            'sp06g_crediti_altri_breve',
        )
        total = sum((_get_field(ref_bs, f) for f in fields), Decimal('0'))
        if total > 0:
            r = sp06_total / total
            return tuple(_get_field(ref_bs, f) * r for f in fields)
        return (Decimal('0'),) * 7
```

`_distribute_sp07` (righe 1837-1849) è identico sulle 7 sottovoci di `sp07`.

**Il secondo difetto — dove la massa governata si perde**, righe 1299-1336 (post Task 1, invariate
da quel Change): la ripartizione assegna già una quota a `sp06e` in proporzione a `ref_bs`; poi il
calcolo fiscale **sovrascrive** `sp06e` (e, quando ci sono differite, `sp06f`/`sp07f`) col proprio
valore — ma la riga di riassorbimento (`sp06g += max(0, sp06 - sum(...))`) **è già passata**, PRIMA
di questa sovrascrittura: qualunque quota che la ripartizione aveva messo in `sp06e`/`sp06f` e che
la sovrascrittura toglie non viene mai recuperata in nessun campo. La cassa (`sp09`) assorbe
silenziosamente la differenza:

```python
        current_tax, deferred, _ = _tax_components(projected_inc, assumption)
        tax_lines = getattr(assumption, 'tax_temporary_differences', None) or []
        if tax_lines:
            sp06f = deferred['short_asset']          # sovrascrive SENZA restituire la quota tolta
            sp07f = deferred['long_asset']
            sp14b = deferred['liability']
            sp14 = sp14a + sp14b + sp14c + sp14d
        manual_tax_position = (
            getattr(assumption, 'sp06e_growth_pct', None) is not None
            or getattr(assumption, 'sp16e_growth_pct', None) is not None
        )
        if not manual_tax_position:
            ...
            sp06e, sp16e = posizione.closing_credit, posizione.closing_debt   # idem per sp06e
        sp06 = sp06a + sp06b + sp06c + sp06d + sp06e + sp06f + sp06g   # qui la massa manca
```

Il ramo **senza** riferimento, `_project_balance_sheet_annualized` — **verificato, non si tocca**:
usa già `_distribute_sp06(partial_bs, sp06)`/`_distribute_sp07(partial_bs, sp07)` (fonte =
parziale), ma **ha lo stesso secondo difetto** (la sovrascrittura fiscale segue la stessa
sequenza) — non approfondito qui: nessuno scenario del database lo esercita, e resta fuori dal
Target di questo task per lo stesso motivo per cui il Task 1 non lo tocca per il debito. Riportato
nel rapporto di fine task, non corretto.

## Trappole note

- **`calculations/intra_year_engine.py` ha terminatori di riga MISTI**, e la patch del Task 1 ha
  già inserito un blocco LF fra la riga 1183 e la fine del metodo. **Non normalizzare mai l'intero
  file.** Lo script del Change opera per numero di riga esatto su `splitlines(keepends=True)`,
  usa **sempre** `rb`/`wb` — **mai** `open(path, encoding=...)` in modalità testo: la modalità testo
  traduce `\r\n` → `\n` in lettura e riscrive con `\n` ovunque, normalizzando l'INTERO file in
  silenzio (osservato durante la stesura di questa bozza: `git diff --stat` è passato da ~180 righe
  attese a **1598 inserzioni / 1461 cancellazioni** su un file di 2025 righe con uno script in
  modalità testo — corretto riscrivendolo in `rb`/`wb` puro, tornando a **179 inserzioni, 25
  cancellazioni**). Verificare sempre `git diff --stat` prima di fidarsi di una patch su questo
  file.
- **Denaro in `Decimal`, mai `float`.** Ogni valore nuovo (`sp06e_governed`, `sp06f_governed`,
  `sp07f_governed`, `sp06_governed_mass`, `sp07_governed_mass`, il residuo operativo) è costruito
  da `_get_field(...)` con `+`/`-` fra `Decimal`.
- **I messaggi dei motori sono in italiano dal lotto 3A Task 8.** Il messaggio della nuova
  diagnostica e dei due nuovi errori di ripartizione mancante sono in italiano, con `eur_it()`.
- **Non toccare `_distribute_sp16_operativo`/`_distribute_sp17_operativo`/`_apply_debt_repayment`.**
  Sono il Change del Task 1, già corretto; questo task tocca **solo** `sp06`/`sp07` e il punto in
  cui si calcola la posizione tributaria/le differite (spostato prima, non riscritto).
- **Il motore budget non si tocca**, come per il Task 1.
- **Spostare il calcolo fiscale prima della ripartizione è sicuro solo perché non dipende da nulla
  che quella ripartizione calcola.** `_tax_components(projected_inc, assumption)` e
  `posizione_tributaria_fine_anno(...)` leggono solo `projected_inc`, `assumption`, `partial_bs`,
  `partial_inc`, `ref_inc` — **mai** `sp06`/`sp07`/`sp16`/`sp17` o le loro sottovoci.
- **Un secondo difetto scoperto durante la misura, non corretto qui**: il ramo annualizzato ha lo
  stesso ordine sbagliato (riassorbimento prima della sovrascrittura fiscale).
- **Una sotto-voce già negativa nel parziale può comparire negativa nella proiezione** — misurato
  sull'azienda id 48, scenario id 8: `sp06g_crediti_altri_breve` del parziale è **già** -12.050,69
  nel database (un residuo di un'estrazione precedente, non introdotto da questo task). **Non
  clampare**: per «diagnose, never fabricate» un valore negativo già presente nella fonte non va
  nascosto; resta un'anomalia dell'import di quell'azienda, da correggere in Rettifiche.

## Change

Un solo file di produzione, `calculations/intra_year_engine.py`. Applicato **dopo** lo script del
Task 1, sullo stesso file. Quattro punti:

1. La posizione tributaria (`current_tax`, `deferred`, `manual_tax_position`, `posizione` quando
   applicabile) si calcola **prima** della sezione che ripartisce gli attivi/passivi — stesso
   codice, **spostato** più in alto. Da questo calcolo si derivano `sp06e_governed`/
   `sp16e_governed` (posizione tributaria, se non manuale) e `sp06f_governed`/`sp07f_governed`/
   `sp14b_governed` (differite, se impostate) — `None` quando quel meccanismo non governa il campo.
2. Due nuovi metodi, `_distribute_sp06_operativo`/`_distribute_sp07_operativo`, mirror esatti di
   `_distribute_sp16_operativo`/`_distribute_sp17_operativo` (Task 1): distribuiscono **solo** il
   residuo passato loro (l'aggregato meno la massa già governata) sulle sotto-voci **non** escluse,
   usando le proporzioni della fonte passata — **sempre `partial_bs`**, mai `ref_bs`. Un parametro
   `escludi` toglie dal pool le voci il cui valore arriva da altrove. Quando anche il pool ammesso
   ha fonte a zero e il residuo è diverso da zero, dichiarano
   `missing_short_receivables_breakdown`/`missing_long_receivables_breakdown` (severità `error`).
3. Un nuovo metodo, `_declare_reference_receivables_undetailed(aggregate, ref_bs, partial_bs)`:
   dichiara `reference_receivables_undetailed` quando il riferimento non ha **alcuna** delle 6
   sotto-voci reali diversa da zero mentre il parziale sì.
4. Le due chiamate a `_distribute_sp06(ref_bs, sp06)`/`_distribute_sp07(ref_bs, sp07)` diventano: i
   campi governati (`sp06e`/`sp06f`/`sp07f`, quando applicabile) si assegnano dai valori già
   calcolati al punto 1; il residuo passa da `_distribute_sp06_operativo(partial_bs, residuo,
   escludi)`. La riga di riassorbimento (`sp06g += max(0, sp06 - sum(...))`, invariata) ora opera
   **dopo** che i campi governati sono già al loro valore finale.

Script di patch (letto per intero, `rb`/`wb`, ancorato al file **già patchato dal Task 1**):

```python
"""Patch calculations/intra_year_engine.py (GIA' patchato dal Task 1),
preservando i terminatori di riga riga per riga -- mai in modalita' testo
(mai `open(path, encoding=...)`: Python traduce \r\n -> \n in lettura e
riscrive con \n ovunque, normalizzando l'INTERO file). Sempre `rb`/`wb`,
sempre per numero di riga esatto, verificato con `expect()` prima di scrivere."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "calculations/intra_year_engine.py"

with open(path, "rb") as f:
    raw = f.read()
lines = raw.splitlines(keepends=True)


def at(n):
    return n - 1


def expect(n, needle):
    line = lines[at(n)]
    if needle.encode() not in line:
        raise SystemExit(f"ANCHOR MISMATCH at line {n}: {line!r} does not contain {needle!r}")


# --- anchors (fail loudly if the file has drifted since Task 1's patch) ---
expect(1278, "# Break down debts before applying creditor-specific movements")
expect(1287, "self._distribute_sp06(ref_bs, sp06)")
expect(1288, "self._distribute_sp07(ref_bs, sp07)")
expect(1312, "current_tax, deferred, _ = _tax_components(projected_inc, assumption)")
expect(1335, "sp06e, sp16e = posizione.closing_credit, posizione.closing_debt")
expect(1336, "sp06 = sp06a + sp06b + sp06c + sp06d + sp06e + sp06f + sp06g")
expect(1818, "def _distribute_sp06(self, ref_bs, sp06_total):")
expect(1837, "def _distribute_sp07(self, ref_bs, sp07_total):")
expect(1849, "return (Decimal('0'),) * 7")
expect(1850, "")
expect(1851, "def _distribute_sp04(self, ref_bs, sp04_total):")

LF = b"\n"

new_lines = []

# 1) lines 1..1277 unchanged
new_lines += lines[: at(1278)]

# 2) lines 1278-1336 REPLACED: tax position derived FIRST, sp06e/sp06f/sp07f
#    excluded from the turnover-driven split before it runs.
block_new = '''        # Tax position is derived BEFORE the receivables split, not after:
        # sp06e (crediti tributari) and, when deferred-tax lines are set,
        # sp06f/sp07f are GOVERNED fields -- their value comes from the tax
        # kernel / deferred-tax mechanism, never from a turnover-driven
        # proportional split. Computing them first lets the operating pool
        # exclude them up front, so no mass is ever assigned to them by
        # _distribute_sp06_operativo/_distribute_sp07_operativo and then
        # discarded (indagine-2, 2026-09-12): a naive split that still
        # includes them can assign a share to sp06e which the tax kernel then
        # overwrites, and the discarded mass silently reappears as cash --
        # measured on azienda 48 scenario 8, ~39.781,69.
        current_tax, deferred, _ = _tax_components(projected_inc, assumption)
        tax_lines = getattr(assumption, 'tax_temporary_differences', None) or []
        manual_tax_position = (
            getattr(assumption, 'sp06e_growth_pct', None) is not None
            or getattr(assumption, 'sp16e_growth_pct', None) is not None
        )
        sp06e_governed = None
        sp16e_governed = None
        if not manual_tax_position:
            remaining_current_tax = max(
                Decimal('0'), current_tax - _get_field(partial_inc, 'ce20_imposte')
            )
            posizione = posizione_tributaria_fine_anno(
                opening_credit=_get_field(partial_bs, 'sp06e_crediti_tributari_breve'),
                opening_debt=_get_field(partial_bs, 'sp16e_debiti_tributari_breve'),
                remaining_current_tax=remaining_current_tax,
                current_tax=current_tax,
                reference_tax=_get_field(ref_inc, 'ce20_imposte'),
                explicit_advances=getattr(assumption, 'tax_advances_paid', None),
            )
            sp06e_governed, sp16e_governed = posizione.closing_credit, posizione.closing_debt
        sp06f_governed = None
        sp07f_governed = None
        sp14b_governed = None
        if tax_lines:
            sp06f_governed = deferred['short_asset']
            sp07f_governed = deferred['long_asset']
            sp14b_governed = deferred['liability']

        # Break down debts before applying creditor-specific movements. The bank
        # repayment uses total bank exposure and pays the short bucket first;
        # bonds and operating debts are left untouched.
        sp02a, sp02b, sp02c, sp02d, sp02e, sp02f, sp02g = self._distribute_sp02(
            partial_bs, sp02
        )
        sp03a, sp03b, sp03c, sp03d, sp03e = self._distribute_sp03(partial_bs, sp03)
        sp04a, sp04b, sp04c, sp04d, sp04e = self._distribute_sp04(ref_bs, sp04)
        sp05a, sp05b, sp05c, sp05d, sp05e = self._distribute_sp05(ref_bs, sp05)
        # Receivables: composition of the OPERATING residual (never sp06e/
        # sp06f/sp07f when they are governed above) comes from the PARTIAL
        # year's own mix -- never a different year's, exactly like the
        # financial debt block (Task 1) -- because the reference lacking
        # receivables detail used to zero out real trade receivables
        # silently (indagine-2, azienda 237: 1.090.958,55 masked as 'altri
        # crediti'). Declared, never silent, when the reference gives no
        # corroborating detail at all.
        self._declare_reference_receivables_undetailed('sp06', ref_bs, partial_bs)
        self._declare_reference_receivables_undetailed('sp07', ref_bs, partial_bs)
        sp06_escludi = (
            (('sp06e_crediti_tributari_breve',) if sp06e_governed is not None else ())
            + (('sp06f_imposte_anticipate_breve',) if sp06f_governed is not None else ())
        )
        sp07_escludi = (
            ('sp07f_imposte_anticipate_lungo',) if sp07f_governed is not None else ()
        )
        sp06_governed_mass = (sp06e_governed or Decimal('0')) + (sp06f_governed or Decimal('0'))
        sp07_governed_mass = sp07f_governed or Decimal('0')
        sp06a, sp06b, sp06c, sp06d, sp06e, sp06f, sp06g = self._distribute_sp06_operativo(
            partial_bs, sp06 - sp06_governed_mass, sp06_escludi
        )
        sp07a, sp07b, sp07c, sp07d, sp07e, sp07f, sp07g = self._distribute_sp07_operativo(
            partial_bs, sp07 - sp07_governed_mass, sp07_escludi
        )
        if sp06e_governed is not None:
            sp06e = sp06e_governed
        if sp06f_governed is not None:
            sp06f = sp06f_governed
        if sp07f_governed is not None:
            sp07f = sp07f_governed
        sp14a, sp14b, sp14c, sp14d = self._distribute_sp14(partial_bs, sp14)
        if sp14b_governed is not None:
            sp14b = sp14b_governed
            sp14 = sp14a + sp14b + sp14c + sp14d
        sp16a, sp16b, sp16c = partial_sp16a, partial_sp16b, partial_sp16c
        sp16d, sp16e, sp16f, sp16g = self._distribute_sp16_operativo(
            ref_bs, sp16_operativo
        )
        sp17a, sp17b, sp17c = partial_sp17a, partial_sp17b, partial_sp17c
        sp17_operativo = sp17 - partial_sp17_fin
        sp17d, sp17e, sp17f, sp17g = self._distribute_sp17_operativo(
            ref_bs, sp17_operativo
        )
        sp06g += max(Decimal('0'), sp06 - sum(
            (sp06a, sp06b, sp06c, sp06d, sp06e, sp06f, sp06g), Decimal('0')
        ))
        sp07g += max(Decimal('0'), sp07 - sum(
            (sp07a, sp07b, sp07c, sp07d, sp07e, sp07f, sp07g), Decimal('0')
        ))
        sp16g += max(Decimal('0'), sp16 - sum(
            (sp16a, sp16b, sp16c, sp16d, sp16e, sp16f, sp16g), Decimal('0')
        ))
        sp17g += max(Decimal('0'), sp17 - sum(
            (sp17a, sp17b, sp17c, sp17d, sp17e, sp17f, sp17g), Decimal('0')
        ))

        if not manual_tax_position:
            sp16e = sp16e_governed
'''
new_lines.append(block_new.encode("utf-8"))

# 3) lines 1336..1817 unchanged
new_lines += lines[at(1336): at(1818)]

# 4) NEW methods inserted right after line 1849 (end of _distribute_sp07,
#    still LF zone), BEFORE the existing CRLF blank line 1850.
new_lines += lines[at(1818): at(1850)]

new_methods = '''    def _declare_reference_receivables_undetailed(self, aggregate, ref_bs, partial_bs):
        """Dichiara quando il bilancio di riferimento non ha ALCUN dettaglio
        REALE sui crediti (nessuna delle 6 sotto-voci di ``aggregate``, escluso
        il secchio di ripiego 'g') mentre il periodo parziale si': la
        composizione usata (sempre quella del parziale, mai quella del
        riferimento) non e' corroborata dal riferimento. Diagnostica
        informativa: a differenza del debito finanziario (Task 1), qui non
        azzera piu' nulla -- _distribute_sp06_operativo/_distribute_sp07_operativo
        leggono sempre partial_bs -- quindi non segnala un ramo di calcolo
        diverso, solo una qualita' del dato di riferimento (indagine-2,
        2026-09-12)."""
        fields = {
            'sp06': (
                'sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
                'sp06g_crediti_altri_breve',
            ),
            'sp07': (
                'sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
                'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
                'sp07e_crediti_tributari_lungo', 'sp07f_imposte_anticipate_lungo',
                'sp07g_crediti_altri_lungo',
            ),
        }[aggregate]
        # 'g' e' il secchio di ripiego: un riferimento che ha SOLO 'g' non da'
        # alcun segnale reale sulla composizione (esattamente come per il
        # debito finanziario, dove si guardano solo le 3 voci reali, mai il
        # ripiego). Le altre 6 voci sono la 'detail' che conta.
        campi_reali = fields[:-1]
        ref_has_detail = any(_get_field(ref_bs, f) != 0 for f in campi_reali)
        partial_total = sum((_get_field(partial_bs, f) for f in fields), Decimal('0'))
        if ref_has_detail or partial_total == 0:
            return
        self._diagnostics.append({
            'code': 'reference_receivables_undetailed',
            'severity': 'warning',
            'aggregate': aggregate,
            'amount': str(partial_total),
            'message': (
                f"Il bilancio di riferimento non ha dettaglio sui crediti su "
                f"{aggregate}: la ripartizione ({eur_it(partial_total)}) usa la "
                f"composizione del periodo parziale, non corroborata dal "
                f"riferimento."
            ),
        })

    def _distribute_sp06_operativo(self, source_bs, sp06_operativo_total, escludi=()):
        """Distribuisce solo il residuo di sp06 NON governato altrove (sp06e
        dal cuneo fiscale, sp06f dalle differite quando impostate) usando la
        composizione del PARZIALE -- mai di un anno diverso -- esattamente
        come il debito finanziario (Task 1). I campi in ``escludi`` non
        ricevono mai una quota: il loro valore viene assegnato altrove, dal
        chiamante."""
        fields = (
            'sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
            'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
            'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
            'sp06g_crediti_altri_breve',
        )
        pool = tuple(f for f in fields if f not in escludi)
        total = sum((_get_field(source_bs, f) for f in pool), Decimal('0'))
        shares = {}
        if total > 0:
            r = sp06_operativo_total / total
            shares = {f: _get_field(source_bs, f) * r for f in pool}
        elif sp06_operativo_total != 0:
            self._diagnostics.append({
                'code': 'missing_short_receivables_breakdown',
                'severity': 'error',
                'amount': str(sp06_operativo_total),
                'message': (
                    "La ripartizione dei crediti operativi a breve non e' "
                    "disponibile: nessuna categoria e' stata inventata."
                ),
            })
        return tuple(shares.get(f, Decimal('0')) for f in fields)

    def _distribute_sp07_operativo(self, source_bs, sp07_operativo_total, escludi=()):
        """Mirror di _distribute_sp06_operativo per i crediti a lungo."""
        fields = (
            'sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
            'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
            'sp07e_crediti_tributari_lungo', 'sp07f_imposte_anticipate_lungo',
            'sp07g_crediti_altri_lungo',
        )
        pool = tuple(f for f in fields if f not in escludi)
        total = sum((_get_field(source_bs, f) for f in pool), Decimal('0'))
        shares = {}
        if total > 0:
            r = sp07_operativo_total / total
            shares = {f: _get_field(source_bs, f) * r for f in pool}
        elif sp07_operativo_total != 0:
            self._diagnostics.append({
                'code': 'missing_long_receivables_breakdown',
                'severity': 'error',
                'amount': str(sp07_operativo_total),
                'message': (
                    "La ripartizione dei crediti operativi a lungo non e' "
                    "disponibile: nessuna categoria e' stata inventata."
                ),
            })
        return tuple(shares.get(f, Decimal('0')) for f in fields)

'''
new_lines.append(new_methods.encode("utf-8"))

# 5) line 1850 (CRLF blank) onward, unchanged to end of file
new_lines += lines[at(1850):]

with open(path, "wb") as f:
    f.write(b"".join(new_lines))

print("patched", path)
```

## Constraints

- Nessun cambiamento a `calculations/forecast_engine.py` né a `calculations/projection_common.py`.
- Nessun cambiamento a `_distribute_sp16_operativo`/`_distribute_sp17_operativo`/
  `_apply_debt_repayment` né a `_distribute_sp02`/`_distribute_sp03`/`_distribute_sp04`/
  `_distribute_sp05`/`_distribute_sp14`: sono invariati, letti soltanto.
- Nessun cambiamento a `_distribute_sp06`/`_distribute_sp07` (i vecchi metodi a 7 campi): restano
  usati, **invariati**, dal ramo `_project_balance_sheet_annualized`.
- Nessun cambiamento al ramo `_project_balance_sheet_annualized`: ha lo stesso secondo difetto ma
  nessuno scenario del database lo esercita; riportato nel rapporto di fine task, non corretto qui.
- Denaro sempre in `Decimal`; messaggi delle diagnostiche sempre in italiano con `eur_it()`.
- Terminatori di riga: CRLF e LF preservati esattamente dove erano; script sempre `rb`/`wb`, mai
  modalità testo.
- Il motore budget non si tocca: il banco di parità deve restare a 0 divergenze (Step 10).
- Una sotto-voce negativa già presente nella fonte (`sp06g` del parziale, azienda id 48) **non si
  clampa**: si propaga, si segnala nel rapporto di fine task, non si nasconde.

## Ownership

`calculations/intra_year_engine.py` (dopo il Change del Task 1),
`tests/test_intra_year_crediti_commerciali.py` (nuovo file), `CLAUDE.md` (§ Intra-Year Engine ›
Working capital), `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` (§5, dopo l'edit del Task 1).

## Step

- [ ] **Step 1: Base.** Il Change del Task 1 deve essere già applicato e collaudato (12 test verdi
  su `tests/test_intra_year_debito_bancario.py`, banco di parità a 0 divergenze) **prima** di
  eseguire questo Step 1. `git rev-parse HEAD` deve stampare il commit del Task 1, non `0f7614a`
  nudo.

- [ ] **Step 2: Test nuovi, prova rossa.** Crea `tests/test_intra_year_crediti_commerciali.py` (file
  nuovo, non un'estensione — i crediti non condividono fixture con
  `test_intra_year_debito_bancario.py`):

```python
"""_distribute_sp06/_distribute_sp07 ripartivano i crediti proiettati con le
proporzioni del bilancio di RIFERIMENTO -- lo stesso schema del debito
bancario (indagine-1, test_intra_year_debito_bancario.py), "Mirrors
_distribute_sp16" per commento del codice. Quando il riferimento non ha
dettaglio reale sui crediti (tutto il totale in 'g', il secchio di ripiego --
il caso comune per un bilancio da schema di legge) l'intera massa dei crediti
commerciali del parziale (verso clienti, sp06a/sp07a) veniva riclassificata
in 'altri crediti' senza alcuna diagnostica (indagine-2, 2026-09-12).

A differenza del debito bancario, i crediti commerciali SONO trainati dal
fatturato (rotazione/DSO): l'aggregato sp06/sp07 continua a scalare sulla
rotazione dei costi/ricavi del riferimento come prima -- cambia solo la fonte
delle PROPORZIONI con cui l'aggregato si ripartisce fra le sotto-voci, che
diventa il parziale (il dato reale, gia' classificato), mai il riferimento.

Un secondo difetto, indipendente da quale fonte si usi per le proporzioni: i
campi GOVERNATI altrove (sp06e dalla posizione tributaria, sp06f/sp07f dalle
differite quando impostate) potevano ricevere comunque una quota dalla
ripartizione proporzionale, quota poi scartata dal calcolo fiscale che li
sovrascrive -- la massa scartata spariva in cassa senza alcun flusso
(indagine-2: 40.000,00 su un caso sintetico, TEST C sotto). Ora quei campi
sono esclusi dalla ripartizione PRIMA che avvenga, cosi' la massa non si
perde mai.
"""
from decimal import Decimal as D

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from calculations.intra_year_engine import IntraYearEngine
from database.db import Base
from database.models import (BalanceSheet, BudgetAssumptions, BudgetScenario, Company, FinancialYear, ForecastYear,
                             IncomeStatement)


def _sessione():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _stato_sp06(**over):
    """Stato patrimoniale minimo per i test di questo file: solo i campi di
    sp06/sp07 e il minimo per far quadrare Attivo=Passivo (sp09, sp11)."""
    zero = D("0")
    base = dict(
        sp06_crediti_breve=zero, sp06a_crediti_clienti_breve=zero, sp06b_crediti_controllate_breve=zero,
        sp06c_crediti_collegate_breve=zero, sp06d_crediti_controllanti_breve=zero,
        sp06e_crediti_tributari_breve=zero, sp06f_imposte_anticipate_breve=zero, sp06g_crediti_altri_breve=zero,
        sp07_crediti_lungo=zero, sp07a_crediti_clienti_lungo=zero, sp07b_crediti_controllate_lungo=zero,
        sp07c_crediti_collegate_lungo=zero, sp07d_crediti_controllanti_lungo=zero,
        sp07e_crediti_tributari_lungo=zero, sp07f_imposte_anticipate_lungo=zero, sp07g_crediti_altri_lungo=zero,
        sp09_disponibilita_liquide=D("500000"), sp11_capitale=D("100000"),
    )
    base.update(over)
    return base


def _proietta_crediti(stato_riferimento, ricavi_riferimento, stato_parziale, **ipotesi):
    """Costruisce un'azienda con uno stato patrimoniale DIVERSO per l'anno di
    riferimento (2025, pieno) e per il parziale (2026, 6 mesi): il ricavo del
    riferimento e la crescita a 0% (default) rendono l'aggregato sp06
    proiettato ESATTAMENTE uguale a ``ref_sp06`` (rapporto di rotazione non
    degenere, nessuno scalamento) -- cosi' un test su massa conservata non
    dipende dall'aritmetica della rotazione, solo dalla ripartizione."""
    db = _sessione()
    azienda = Company(name="Crediti infrannuale", tax_id="CREDITI-INFRA", sector=1)
    db.add(azienda); db.flush()
    fy_ref = FinancialYear(company_id=azienda.id, year=2025, period_months=None,
                           validation_status="verified", forecastable=True)
    db.add(fy_ref); db.flush()
    db.add(BalanceSheet(financial_year_id=fy_ref.id, **stato_riferimento))
    # ce05 = ce01 pareggia l'utile del CE a zero, coerente con sp13=0 di _stato_sp06
    # (il motore rifiuta un anno di riferimento il cui utile CE non torna con sp13).
    db.add(IncomeStatement(financial_year_id=fy_ref.id, ce01_ricavi_vendite=ricavi_riferimento,
                           ce05_materie_prime=ricavi_riferimento))
    fy_par = FinancialYear(company_id=azienda.id, year=2026, period_months=6,
                           validation_status="verified", forecastable=True)
    db.add(fy_par); db.flush()
    db.add(BalanceSheet(financial_year_id=fy_par.id, **stato_parziale))
    db.add(IncomeStatement(financial_year_id=fy_par.id))
    scenario = BudgetScenario(company_id=azienda.id, name="crediti-test", base_year=2025,
                              scenario_type="infrannuale", period_months=6)
    db.add(scenario); db.flush()
    db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2026, tax_rate=D("0"),
                             fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"), **ipotesi))
    db.commit()
    result = IntraYearEngine(db).generate_projection(scenario.id)
    bs = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
    return bs, result['diagnostics']


# Fixture comune ai tre test: lo stesso parziale (6 mesi), con crediti verso
# clienti reali (sp06a) e una piccola quota tributaria e "altri".
_RIF_TOTALE = D("200000")
_PARZIALE = _stato_sp06(
    sp06_crediti_breve=D("120000"), sp06a_crediti_clienti_breve=D("90000"),
    sp06e_crediti_tributari_breve=D("5000"), sp06g_crediti_altri_breve=D("25000"),
    sp11_capitale=D("620000"),
)


def test_i_crediti_verso_clienti_si_portano_avanti_dal_parziale_quando_il_riferimento_non_ha_dettaglio():
    """Il riferimento ha l'intero sp06 nel secchio di ripiego 'g' (nessuna
    voce reale, il caso comune -- il 98% dei bilanci annuali completi del
    database secondo indagine-1 §6): il credito verso clienti REALE del
    parziale (90.000,00 su 120.000,00) non deve sparire in 'altri crediti'.
    Prima della correzione: sp06a 0,00 (indagine-2)."""
    ref = _stato_sp06(sp06_crediti_breve=_RIF_TOTALE, sp06g_crediti_altri_breve=_RIF_TOTALE,
                       sp11_capitale=D("700000"))
    bs, diagnostics = _proietta_crediti(ref, D("1000000"), _PARZIALE)
    assert bs.sp06_crediti_breve == D("200000.00")  # aggregato: rotazione non degenere, invariata
    assert bs.sp06a_crediti_clienti_breve == D("156521.74")  # non piu' zero
    codici = [d['code'] for d in diagnostics]
    assert 'reference_receivables_undetailed' in codici
    diag = next(d for d in diagnostics if d['code'] == 'reference_receivables_undetailed')
    assert diag['aggregate'] == 'sp06'
    assert diag['severity'] == 'warning'


def test_la_composizione_segue_il_parziale_anche_quando_il_riferimento_ha_dettaglio():
    """Il riferimento ha una propria quota clienti (160.000,00 su 200.000,00,
    80%): prima della correzione quella proporzione (80%) veniva applicata
    all'aggregato proiettato, dando sp06a = 160.000,00. Dopo, la composizione
    usata e' sempre quella del parziale (mai quella del riferimento, quale
    che sia): stesso risultato di quando il riferimento non ha dettaglio
    affatto (156.521,74), e nessuna diagnostica -- il riferimento avrebbe
    dato un segnale reale, semplicemente non e' piu' quello che conta."""
    ref = _stato_sp06(sp06_crediti_breve=_RIF_TOTALE, sp06a_crediti_clienti_breve=D("160000"),
                       sp06g_crediti_altri_breve=D("40000"), sp11_capitale=D("700000"))
    bs, diagnostics = _proietta_crediti(ref, D("1000000"), _PARZIALE)
    assert bs.sp06a_crediti_clienti_breve == D("156521.74")
    assert not any(d['code'] == 'reference_receivables_undetailed' for d in diagnostics)


def test_il_credito_tributario_non_riceve_una_quota_dalla_ripartizione_poi_scartata():
    """Il riferimento ha una quota REALE di crediti tributari (sp06e =
    40.000,00 su 200.000,00): una ripartizione ingenua le assegnerebbe una
    quota proporzionale, che il calcolo fiscale automatico (manual_tax_position
    False, nessun sp06e_growth_pct/sp16e_growth_pct impostato) scarta subito
    dopo sostituendola col proprio valore -- la massa scartata spariva in
    cassa (indagine-2): prima della correzione sp06 finale 160.000,00 invece
    di 200.000,00 (mancano esattamente i 40.000,00 di sp06e), sp09
    460.000,00 invece di 420.000,00. Dopo: sp06e e' escluso dalla
    ripartizione PRIMA che avvenga, e l'aggregato torna a conservare la
    massa esattamente."""
    ref = _stato_sp06(sp06_crediti_breve=_RIF_TOTALE, sp06e_crediti_tributari_breve=D("40000"),
                       sp06g_crediti_altri_breve=D("160000"), sp11_capitale=D("700000"))
    bs, _diagnostics = _proietta_crediti(ref, D("1000000"), _PARZIALE)
    assert bs.sp06_crediti_breve == D("200000.00")  # nessuna massa persa
    assert bs.sp09_disponibilita_liquide == D("420000.00")
```

- [ ] **Step 3: Prova rossa.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_intra_year_crediti_commerciali.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **3 failed**. `test_i_crediti_verso_clienti...` fallisce su `sp06a == 0.00` invece di
  `156521.74`; `test_la_composizione_segue_il_parziale...` fallisce su `sp06a == 160000.00` invece
  di `156521.74` (la vecchia proporzione del riferimento, 80%); `test_il_credito_tributario...`
  fallisce su `sp06 == 160000.00` invece di `200000.00` (i 40.000,00 di `sp06e` scartati e mai
  recuperati).

- [ ] **Step 4: Verifica i terminatori di riga prima di toccare il file.**
  ```bash
  file calculations/intra_year_engine.py
  ```
  Atteso: "with CRLF, LF line terminators" (misti, come lasciati dalla patch del Task 1).

- [ ] **Step 5: Implementa il Change.** Salva lo script della sezione «Change» come
  `/tmp/patch_task_2.py` ed eseguilo:
  ```bash
  cd /home/peter/DEV/budget
  python3 /tmp/patch_task_2.py calculations/intra_year_engine.py
  ```
  Atteso: stampa `patched calculations/intra_year_engine.py`, nessun `ANCHOR MISMATCH`. Un
  `ANCHOR MISMATCH` significa che il file (già patchato dal Task 1) è cambiato dalla base su cui
  questo Change è scritto: fermarsi e riadattare gli ancoraggi prima di procedere.

- [ ] **Step 6: Verifica sintattica e diff minimo.**
  ```bash
  python3 -c "import ast; ast.parse(open('calculations/intra_year_engine.py', encoding='utf-8').read())" && echo "syntax ok"
  file calculations/intra_year_engine.py
  git diff --stat calculations/intra_year_engine.py
  ```
  Atteso: `syntax ok`; ancora "with CRLF, LF line terminators"; `git diff --stat` mostra circa **179
  inserzioni, 25 cancellazioni** (questo diff è **solo** il Change di questo task, non cumulativo
  con quello del Task 1 che lo precede). Uno scarto grande indica quasi certamente una
  normalizzazione accidentale dei terminatori: fermarsi e controllare `git diff` per intero.

- [ ] **Step 7: Verde.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_intra_year_crediti_commerciali.py tests/test_intra_year_debito_bancario.py \
    -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **15 passed** (3 nuovi di questo task + 12 del Task 1, invariati).

- [ ] **Step 8: Le misure — prima/dopo sugli scenari infrannuali del database, con la patch del
  Task 1 già applicata.** Su una **copia** del database:
  ```bash
  sqlite3 financial_analysis.db ".backup '/tmp/task2_db.sqlite'"
  ```
  Per ciascuno degli 8 scenari `infrannuale` (verifica prima l'elenco corrente con
  `sqlite3 /tmp/task2_db.sqlite "select id from budget_scenarios where scenario_type='infrannuale'"`),
  genera la proiezione con **solo** il Task 1 applicato ("prima" per questo task) e con Task 1
  **+** questo Change ("dopo"), leggendo `sp06a-g`, `sp07a-g`, `sp09`, il DSO
  (`FinancialRatiosCalculator.calculate_activity_ratios().receivables_turnover_days`), CCN,
  current/quick ratio, PFN (invariata da questo task, per contesto), e lo sbilancio. Valori
  misurati durante la stesura di questo piano:

  | Scenario | Azienda | Riferimento → Parziale | Campo | Prima (solo 1) | Dopo (1 + 2) |
  |---|---|---|---|---:|---:|
  | 4 | id 21 | 2025 (pieno) → 2026 9m | `sp06` (aggregato) | 1.100.048,38 | 1.100.048,38 |
  | 4 | id 21 | idem | `sp06a`/`sp06g` | 0,00 / 1.100.048,38 | 0,00 / 1.100.048,38 |
  | 5 | id 21 | 2024 (pieno) → 2025 (12m) | tutti | invariati | invariati |
  | 8 | id 48 | 2025 (pieno, un po' di dettaglio) → 2026 5m | `sp06` (aggregato) | 181.047,91 | 220.829,60 |
  | 8 | id 48 | idem | `sp06a` | 124.553,79 | 222.151,21 |
  | 8 | id 48 | idem | `sp06g` | 56.494,12 | **-1.321,61** |
  | 8 | id 48 | idem | **sbilancio** | 0,00 | 0,00 |
  | 12 | id 50 | 2025 (pieno) → 2026 9m | tutti | invariati | invariati |
  | 18 | id 237 | 2025 (pieno, **senza** dettaglio reale) → 2026 6m | `sp06a` | **0,00** | **881.762,50** |
  | 18 | id 237 | idem | `sp06` (aggregato) | 972.440,13 | 943.667,13 |
  | 18 | id 237 | idem | `sp09` | 1.439.700,63 | 1.468.473,63 |
  | 18 | id 237 | idem | **sbilancio** | 0,00 | 0,00 |
  | 18 | id 237 | idem | diagnostica | nessuna sui crediti | `reference_receivables_undetailed` su `sp06`/`sp07` |

  **Sull'azienda 48, `sp06g` diventa negativo (-1.321,61)**: annotalo nel rapporto — non è un
  difetto di questo Change (vedi «Trappole note»: il parziale importato ha già `sp06g` negativo,
  -12.050,69, un residuo di un'estrazione precedente; usare la composizione del parziale come
  fonte propaga quel segno, che prima appariva positivo solo perché la fonte era il riferimento,
  senza quell'anomalia). Non clamparlo.

  **Misura coi calcolatori veri, azienda id 237, scenario id 18** (`FinancialRatiosCalculator`,
  `AltmanCalculator`, `FGPMICalculator`, sullo stesso `ForecastYear`, prima = solo Task 1, dopo =
  Task 1 + questo Change):

  | Indicatore | Prima (solo 1) | Dopo (1 + 2) |
  |---|---:|---:|
  | `sp06a_crediti_clienti_breve` | 0,00 | 881.762,50 |
  | `receivables_turnover_days` (DSO) | 87 giorni | 85 giorni |
  | CCN | 641.678,64 | 641.678,64 (invariato) |
  | Current ratio | 1,3086 | 1,3086 (invariato) |
  | Debt/Equity | 5,6003 | 5,6003 (invariato) |
  | Altman Z-Score | 5,36 (safe) | 5,36 (safe) (invariato) |
  | FGPMI | classe 3, AA, 89/105 | classe 3, AA, 89/105 (invariato) |

  Conferma la regola di CLAUDE.md «un errore dentro un aggregato è accettato, un errore che
  attraversa un confine di KPI no»: CCN, indici di liquidità, Debt/Equity, Altman e FGPMI restano
  identici (leggono l'aggregato, che quadra prima e dopo). Il DSO si sposta di soli 2 giorni
  (87 → 85) — un movimento piccolo e reale, non l'artefatto di 12 giorni (87 → 75) che una
  correzione più ingenua (scambiare solo la fonte, senza escludere i campi governati) avrebbe
  prodotto.

- [ ] **Step 9: Suite completa — riferimento e file collegati.** Prima il sottoinsieme mirato:
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_intra_year_end_to_end_periods.py tests/test_intra_year_imposte.py \
    tests/test_intra_year_override_cassa.py tests/test_intra_year_plug_negativo.py \
    tests/test_intra_year_semantics.py tests/test_turnover_degenere.py \
    tests/test_forecast_magazzino_settore.py tests/test_forecast_preview.py \
    tests/test_forecast_stale.py tests/test_budget_remediation_plan.py \
    tests/test_standard_ivcee_parser.py tests/test_intra_year_debito_bancario.py \
    tests/test_intra_year_crediti_commerciali.py \
    -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: nessun `failed` nuovo rispetto alla propria baseline. Poi la suite intera:
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests -q \
    --ignore=tests/corpus -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Esegui **prima** del Change di questo task (per stabilire il proprio numero di riferimento
  nell'ambiente in cui lo si applica) e **dopo**: il conteggio di `failed` non deve aumentare.

- [ ] **Step 10: Banco di parità del motore budget (controllo negativo).**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py 0f7614a --anni 4 --controllo-negativo
  ```
  Atteso: 0 divergenze.

- [ ] **Step 11: Documentazione — CLAUDE.md.** In `CLAUDE.md`, § «Intra-Year Engine (Infrannuale)»,
  paragrafo **Working capital** (non toccato dal Task 1), sostituisci:

  **Prima** (ultima frase del paragrafo, subito prima del rimando a REGOLE-IMPORT-05 §5):
  ```
  ...(`degenerate_turnover_ratio`, `_derived_days` in
  `calculations/forecast_engine.py`, Task 14 of this lotto), not shared with the one
  here.
  → `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5
  ```

  **Dopo:**
  ```
  ...(`degenerate_turnover_ratio`, `_derived_days` in
  `calculations/forecast_engine.py`, Task 14 of this lotto), not shared with the one
  here. Receivables (`sp06`/`sp07`) split into sub-categories using the **partial** year's own mix,
  never the reference's, in either regime: a reference lacking real receivables detail (98% of
  full-year balance sheets, same precondition as the bank-debt defect above) used to reclassify real
  trade receivables into "altri crediti" silently (indagine-2, 2026-09-12: 1.090.958,55 on the test
  company). Tax receivables (`sp06e`) and prepaid taxes (`sp06f`/`sp07f`, when temporary-difference
  lines are set) are excluded from that split *before* it runs — their value comes from the year-end
  tax settlement / deferred-tax mechanism, never a proportional share that gets discarded afterward,
  which used to leak into cash silently (39.781,69 on a real scenario, no diagnostic). A reference
  lacking real receivables detail while the partial has some declares
  `reference_receivables_undetailed` (severity `warning`) — informational only: the split always
  comes from the partial, with or without the signal.
  → `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` §5
  ```

- [ ] **Step 12: Documentazione — REGOLE-IMPORT-05-INFRANNUALE.md.** Due punti §5, **dopo** l'edit
  del Task 1.

  **Riga della tabella «Il roll-forward dello Stato Patrimoniale» — prima (invariata dal Task 1):**
  ```
  | **Crediti a breve** | con riferimento: proporzionali ai ricavi proiettati (salvo rapporto degenere, sotto); poi meno la **svalutazione residua** |
  ```

  **Dopo:**
  ```
  | **Crediti a breve** | **aggregato**: con riferimento, proporzionale ai ricavi proiettati (salvo rapporto degenere, sotto), poi meno la **svalutazione residua**; **composizione** (verso clienti/controllate/collegate/controllanti/altri): sempre dal parziale, mai dal riferimento — crediti tributari e imposte anticipate esclusi, governati altrove |
  ```

  **Sezione «Le sotto-voci si distribuiscono, mai si inventano» — dopo il testo del Task 1**,
  aggiungi un terzo paragrafo:
  ```
  I **crediti a breve e a lungo** (`sp06`/`sp07`) seguono una regola diversa da entrambe le
  precedenti: l'aggregato resta trainato dal fatturato (rotazione/DSO, sopra), ma la
  **composizione** delle sotto-voci (verso clienti/controllate/collegate/controllanti/altri) viene
  **sempre** dal parziale — mai dal riferimento, in nessuno dei due regimi — perché un riferimento
  senza dettaglio reale (il 98% dei bilanci annuali completi, come per il debito) riclassificava in
  silenzio il credito verso clienti in "altri crediti" (`indagine-2`, 2026-09-12). Il credito
  tributario (`sp06e`) e le imposte anticipate (`sp06f`/`sp07f`, quando impostate esplicitamente)
  sono **esclusi** dalla ripartizione prima che avvenga — il loro valore viene dalla posizione
  tributaria di fine anno o dalle differite, mai da una quota proporzionale che verrebbe poi
  scartata: prima di questa correzione quella quota scartata spariva silenziosamente in cassa (fino
  a 39.781,69 su un caso reale). Quando il riferimento non ha alcun dettaglio reale sui crediti (solo
  il secchio "altri") e il parziale sì, il motore lo dichiara con
  `reference_receivables_undetailed` (severità *warning*, informativo: la ripartizione viene comunque
  dal parziale, con o senza il segnale).
  ```

- [ ] **Step 13: Commit.**
  ```bash
  git add calculations/intra_year_engine.py tests/test_intra_year_crediti_commerciali.py \
    CLAUDE.md docs/import/REGOLE-IMPORT-05-INFRANNUALE.md
  git commit -F - <<'EOF'
  fix(infrannuale): i crediti si ripartiscono dal parziale, e i campi governati non perdono massa

  _distribute_sp06/_distribute_sp07 (calculations/intra_year_engine.py) ripartivano i crediti
  proiettati -- verso clienti compreso -- con le proporzioni del bilancio di RIFERIMENTO, lo stesso
  schema del debito bancario (indagine-1-debito-bancario.md, gia' corretto). Quando il riferimento
  non ha dettaglio reale sui crediti (98% dei bilanci annuali completi del database), il credito
  verso clienti REALE del periodo parziale spariva in 'altri crediti': misurato su azienda id 237,
  1.090.958,55.

  Un secondo difetto, indipendente da quale fonte alimenta la ripartizione: i campi governati
  altrove (sp06e dalla posizione tributaria, sp06f/sp07f dalle differite) ricevevano comunque una
  quota dalla ripartizione proporzionale, quota che il calcolo fiscale scartava subito dopo senza
  recupero -- la massa scartata spariva in cassa. Misurato su azienda id 48, scenario id 8:
  39.781,69.

  La composizione dei crediti si ripartisce ora SEMPRE dal parziale (mai dal riferimento, in
  nessuno dei due regimi): a differenza del debito bancario, i crediti commerciali SONO trainati dal
  fatturato, quindi la composizione corrente e' un predittore migliore di quella di un anno diverso
  -- l'aggregato continua a scalare sulla rotazione ricavi/costi come prima, cambia solo la fonte
  delle proporzioni di ripartizione. I campi governati (sp06e, sp06f/sp07f quando impostati) sono
  ora esclusi dalla ripartizione PRIMA che avvenga, cosi' la massa non si perde mai. Una nuova
  diagnostica, reference_receivables_undetailed (severita' warning), si dichiara quando il
  riferimento non ha alcun dettaglio reale sui crediti.

  Sull'azienda id 237 (scenario id 18) il credito verso clienti proiettato passa da 0,00 a
  881.762,50; il DSO si sposta di 2 giorni (87 -> 85), un movimento piccolo e reale -- non i 12
  giorni che una correzione piu' ingenua (solo lo scambio di fonte, senza escludere i campi
  governati) avrebbe prodotto, quasi interamente dovuti alla fuga fiscale che si sarebbe aggravata
  anziche' risolversi. CCN, current/quick ratio, Altman e FGPMI restano identici: leggono
  l'aggregato, che quadra in entrambe le versioni.

  Il ramo _project_balance_sheet_annualized (senza riferimento) ha lo stesso secondo difetto
  (l'ordine riassorbimento/sovrascrittura fiscale), ma nessuno scenario del database lo esercita:
  misurato, non corretto in questo commit -- riportato nel rapporto di fine task.

  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01C8chDC8b297itUaoK1TQNW
  EOF
  ```

## Observable acceptance

15 test verdi (12 del Task 1, invariati + 3 nuovi su `tests/test_intra_year_crediti_commerciali.py`);
la suite mirata dei file che chiamano `generate_projection` resta a 0 `failed` rispetto alla propria
baseline; la suite completa non aumenta il numero di `failed`; il banco di parità del motore budget
resta a 0 divergenze; sullo scenario di collaudo (azienda id 237, scenario id 18) la proiezione
mostra `sp06a` 881.762,50 (mai più 0,00) con la diagnostica `reference_receivables_undetailed`
dichiarata su `sp06` e `sp07`; sullo scenario dell'azienda id 48 (scenario id 8) l'aggregato `sp06`
proiettato torna a coincidere esattamente col totale trainato dalla rotazione sui ricavi (nessuna
fuga fiscale residua); `_distribute_sp06`/`_distribute_sp07` (i vecchi metodi, ramo annualizzato)
restano invariati; `git diff --stat` mostra solo le righe effettivamente cambiate da questo task,
mai il file intero; CLAUDE.md e `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` allineati nello stesso
commit.

---

### Task 3: L'uscita di cassa tributaria dell'infrannuale diventa esplicita, non un effetto collaterale

**Files:**
- Modify: `calculations/intra_year_engine.py` (due punti identici, `_project_balance_sheet` e
  `_project_balance_sheet_annualized`; **adattati** per applicarsi sopra Task 1 + Task 2, vedi
  «Interfaces» e «Adattamento dopo il Task 2» sotto — **questo task non è la bozza-task-T applicata
  alla lettera**: la bozza è stata scritta e misurata sopra Task 1 da solo, senza Task 2, e questo
  piano la adatta esplicitamente)
- Modify: `CLAUDE.md` (§ Intra-Year Engine, paragrafo sulla proiezione/imposte al 31/12)
- Modify: `docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` (paragrafo «La posizione tributaria al
  31/12»)
- Test: `tests/test_intra_year_imposte.py` (estensione: test sintetici nuovi)

**Interfaces:**
- Consumes (dai Task 1 e 2, già applicati): il Task 2 **ha già ristrutturato** il punto esatto su
  cui la bozza originale di questo task si innestava. Prima del Task 2, la sostituzione tributaria
  era una singola riga, `sp06e, sp16e = posizione.closing_credit, posizione.closing_debt`, subito
  dopo la chiamata a `posizione_tributaria_fine_anno(...)`. **Dopo il Task 2 quella riga non esiste
  più come tale**: la posizione tributaria si calcola all'inizio del blocco (`sp06e_governed`,
  `sp16e_governed`, variabile locale `posizione` quando `not manual_tax_position`), e la sua
  applicazione è spezzata in due punti non simmetrici (vedi Task 2, «Interfaces», già descritto lì
  per intero):
  - `sp06e` viene già sovrascritto **presto** (`if sp06e_governed is not None: sp06e =
    sp06e_governed`), **prima** che `sp16d/e/f/g` vengano calcolati, e **prima** della riga
    `sp06g += max(0, sp06 - sum(...))` — quindi l'aggregato `sp06` **non perde mai massa** per
    questa sostituzione (è esattamente ciò che il Task 2 ha corretto): non c'è più alcun
    "implicit cash effect" residuo sul lato crediti da compensare.
  - `sp16e` viene sovrascritto **per ultimo**, con `if not manual_tax_position: sp16e =
    sp16e_governed`, **dopo** le quattro righe di riassorbimento (`sp06g += ...`, `sp07g += ...`,
    `sp16g += ...`, `sp17g += ...`). A quel punto `sp16e` vale ancora la quota-riferimento prodotta
    da `_distribute_sp16_operativo` (Task 1) — **esattamente la stessa situazione che la bozza
    originale descriveva per l'unica riga `sp16e`, sopravvissuta identica nella sostanza**, solo
    spostata più in basso nel metodo.
- Produces: nessun'altra variabile nuova per un task successivo — questo è l'ultimo dei tre task
  sequenziali su questo file.

**Target.** Il fabbisogno di cassa che la proiezione infrannuale dichiara
(`unfunded_financing_requirement` e, per riflesso, lo sbilancio del promote) deve coincidere col
vero importo che la posizione tributaria fa uscire di cassa entro il 31/12 (`cash_out`), non con un
effetto collaterale della ripartizione per riferimento di `sp16`. Nessuna modifica al clamp-a-zero
né alla decisione del proprietario sullo scoperto di c/c.

**Difetto di origine:** indagine-2 (`indagine-2-promote.md`) e la bisezione che lo verifica
(`verifica-2-bisezione.md`). Azienda id 21, scenario id 3: il promote infrannuale è rifiutato per
sbilancio, e il verdetto della bisezione (che questo task non riapre) è che il rifiuto è nella
sostanza giusto — il debito tributario d'apertura supera davvero la cassa del parziale — ma **il
modo in cui il numero emerge è un difetto**: `cash_out`
(`calculations.projection_common.posizione_tributaria_fine_anno`) è calcolato e **mai letto**
altrove nel motore infrannuale.

**Perché questo task non è la bozza applicata alla lettera.** `bozza-task-T.md` è stata scritta e
misurata (Tabella B della bozza) sopra **solo** il Task 1, senza il Task 2 — il coordinatore lo ha
segnalato esplicitamente nell'assemblaggio di questo piano: l'ordine deciso è 1 → 2 → 3, e le
misure della bozza vanno rifatte dopo anche il Task 2. La bozza stessa registra il numero
"1.856,76" (azienda id 21) come misurato con **solo** il Task 1 sopra HEAD, avvisando che
"l'osservabile vincolante è fabbisogno dichiarato = sbilancio, promote rifiutato, non il numero
esatto" — esattamente il caveat che questo task eredita e allarga al Task 2. Il Change sotto è
quindi **derivato dall'ancora della bozza, riletto sul codice come lo lascia il Task 2** (non un
copia-incolla): la sua correttezza si verifica sul comportamento algebrico (vedi «Perché il
conguaglio è quello giusto» sotto), non sul numero assoluto — che lo Step di ri-misura stabilisce
per davvero.

## Da leggere prima, per simbolo

- `calculations/projection_common.py:338-362` — `PosizioneTributariaFineAnno` (dataclass, campo
  `cash_out`) e `posizione_tributaria_fine_anno`. Non si tocca in questo task.
- La chiamata a `ForecastEngine._normalize_balance_sheet_cents(projected_bs, recompute_cash=True)`
  dentro `generate_projection`, **subito dopo** `_project_balance_sheet`/
  `_project_balance_sheet_annualized`: quel metodo (condiviso col motore budget) **ricalcola `sp09`
  da zero** come Σpassivo − Σattivo, ignorando qualunque valore che il metodo di proiezione avesse
  scritto sulla chiave `sp09_disponibilita_liquide`. **Qualunque riga scritta su `sp09` dentro
  `_project_balance_sheet` è quindi inerte**: la correzione deve operare su un campo AGGREGATO che
  sopravvive al ricalcolo (`sp16g`), non sulla cassa — verificato dalla bozza con una prima prova
  negativa (vedi sotto).
- Task 1 e Task 2 di questo stesso piano — entrambi per intero: questo si applica **dopo** i loro
  Change.
- `backend/app/services/promote_service.py` — dove il gate del promote (`check_quadratura`) legge
  lo sbilancio che questo task cambia di importo, non di logica.
- `tests/test_intra_year_imposte.py` — la fixture `_infrannuale`: concentra **tutto** `sp16` in
  `sp16e` (100%, nessun altro debito a breve) — in questo caso particolare la quota-riferimento
  coincide ESATTAMENTE col vero saldo di apertura, quindi il difetto non si esercita mai in questa
  suite: da qui la necessità di test sintetici nuovi con composizione mista.

### Prima prova (negativa, importante) — perché la correzione non può stare sulla riga della cassa

Applicare `cash_out` come si potrebbe leggere alla lettera — `sp09 = total_liabilities -
total_assets_no_cash - tax_cash_out` dentro `_project_balance_sheet` — **non cambia nulla**:
misurato dalla bozza, lo stesso scenario con questa riga aggiunta produce lo stesso identico
output di prima. Causa: il ricalcolo condiviso con `ForecastEngine._normalize_balance_sheet_cents`
scarta qualunque valore scritto su `sp09` in questo metodo.

### La correzione — dove si aggancia, e perché sul lato debito soltanto

Nel codice **come lo lascia il Task 2**, la correzione si aggancia **subito prima** della riga
finale `if not manual_tax_position: sp16e = sp16e_governed` (l'ultima riga del blocco introdotto
dal Task 2, appena prima della fine del metodo che questo task tocca). A quel punto:

- `sp16e` vale ancora la quota-riferimento (da `_distribute_sp16_operativo`, Task 1) — il valore
  "prima" della sostituzione tributaria, esattamente come nella bozza originale.
- `sp06e` **non** serve più in questo calcolo: il Task 2 lo ha già portato al suo valore governato
  molto più in alto nello stesso blocco, **prima** che `sp06g += max(0, sp06 - sum(...))`
  eseguisse — quindi la sostituzione su `sp06e` **non lascia più alcun residuo implicito
  sull'aggregato `sp06`** (è esattamente il difetto che il Task 2 ha chiuso). La formula originale
  della bozza, `implicit_cash_effect = (posizione.closing_debt - sp16e) - (posizione.closing_credit
  - sp06e)`, aveva un termine per il lato credito perché **prima** del Task 2 anche `sp06e`
  subiva la stessa fuga della quota-riferimento scartata senza recupero. **Dopo il Task 2 quel
  termine è già zero per costruzione** (il Task 2 lo ha reso tale): includerlo di nuovo qui
  sarebbe ridondante, non sbagliato in modo che cambi il risultato (sarebbe `posizione.closing_credit
  - sp06e = posizione.closing_credit - posizione.closing_credit = 0` dato che `sp06e` a quel punto
  vale già `sp06e_governed = posizione.closing_credit`), ma va scritto in modo che non dipenda da
  un'uguaglianza implicita — il Change sotto usa solo il termine debito, esplicitamente.

Il conguaglio adattato:

```python
        if not manual_tax_position:
            # `cash_out` e' l'importo che la posizione tributaria dichiara di far uscire
            # di cassa entro il 31/12 (spec lotto 3A Task 5). Non si scrive mai su `sp09`
            # qui: il CASH PLUG viene ricalcolato da zero da
            # ForecastEngine._normalize_balance_sheet_cents(recompute_cash=True) in
            # generate_projection, che ignora qualunque valore assegnato a `sp09` in
            # questo metodo -- l'unico canale che sopravvive al ricalcolo e' un campo
            # aggregato. A questo punto del metodo (dopo il Task 2) `sp06e` e' gia' al
            # suo valore governato (il Task 2 lo applica PRIMA del riassorbimento su
            # sp06g, quindi l'aggregato sp06 non perde mai massa per questa
            # sostituzione: nessun termine di credito residuo da compensare qui). Resta
            # da compensare solo il lato debito: `sp16e` vale ancora la quota-riferimento
            # che _distribute_sp16_operativo (Task 1) ha proiettato dalle proporzioni
            # dell'anno di riferimento -- un numero senza relazione col vero debito
            # tributario del parziale. Il conguaglio riporta l'effetto di cassa di
            # questa sostituzione esattamente a `-cash_out`, riassorbendo la differenza
            # nel campo neutro del gruppo passivo (`sp16g`, lo stesso che assorbe il
            # residuo di arrotondamento due blocchi sopra) -- mai su un debito
            # finanziario o un fondo fiscale.
            implicit_cash_effect = posizione.closing_debt - sp16e
            sp16g += -posizione.cash_out - implicit_cash_effect
            if sp16g < 0:
                # Il vero saldo tributario da versare supera quanto la rotazione dei
                # costi operativi aveva stimato per le imposte: il campo neutro non
                # basta. Si dichiara e si azzera, mai un "altri debiti" negativo
                # silenzioso -- il fabbisogno di cassa resta comunque misurato dal CASH
                # PLUG, sotto.
                self._diagnostics.append({
                    'code': 'tax_settlement_reclass_below_zero',
                    'severity': 'warning',
                    'amount': str(-sp16g),
                    'message': (
                        "Il saldo tributario vero da versare entro fine anno supera la quota che "
                        "la rotazione dei costi operativi aveva stimato per le imposte: il campo "
                        "neutro del gruppo sarebbe negativo ed è stato riportato a zero; il "
                        "fabbisogno di cassa reale resta comunque misurato nel plug."
                    ),
                })
                sp16g = Decimal('0')
            sp16e = sp16e_governed
```

Questo blocco **sostituisce** le due righe finali che il Task 2 lascia (`if not manual_tax_position:
sp16e = sp16e_governed`), nello stesso punto, nello stesso file, in **entrambi** i metodi
(`_project_balance_sheet` e `_project_balance_sheet_annualized` — verificare che quest'ultimo abbia
la stessa struttura dopo Task 1+2, dato che il Task 2 non lo tocca esplicitamente per il secondo
difetto ma la sua fixture di ripartizione crediti è `_distribute_sp06(partial_bs, sp06)` invariata:
il punto d'aggancio per la posizione tributaria in quel ramo resta la stessa sequenza
originaria — vedi Step 1 sotto, che impone di rileggere l'ancora esatta su quel ramo prima di
applicare la stessa patch).

**Perché non conta due volte.** Il CASH PLUG (`sp09 = total_liabilities - total_assets_no_cash`,
invariato) legge `sp16` una sola volta, già ricomposto da `sp16a+...+sp16g` con `sp16g` corretto.
Sia `x = sp16e` il valore PRIMA della sostituzione (la quota-riferimento). L'effetto sul CASH PLUG
di sostituire `x → closing_debt` **senza** conguaglio è `Δsp09 = closing_debt − x`. Il conguaglio
aggiunge `correzione = −cash_out − Δsp09` a `sp16g` (un campo del passivo): questo sposta `sp09` di
esattamente `+correzione`. Il totale è quindi `Δsp09 + correzione = Δsp09 + (−cash_out − Δsp09) =
−cash_out`, **sempre**, qualunque siano `x`, `closing_debt` — non solo nel caso particolare
misurato.

## Trappole note

- **Terminatori misti** in `calculations/intra_year_engine.py`, ereditati dal Task 1 e dal Task 2:
  l'esatto punto d'inserimento di questo Change va verificato con `file`/`grep` sul codice **come
  lo lasciano i due task precedenti**, non sui numeri di riga di `0f7614a` nudo — la bozza
  originale citava le righe 1236/1488 di un albero **senza** Task 2; dopo il Task 2 quelle righe
  sono spostate e ristrutturate (vedi «Interfaces» sopra). Ancora testuale da cercare:
  `if not manual_tax_position:\n            sp16e = sp16e_governed` (le ultime due righe del blocco
  del Task 2) — **in entrambi i metodi**.
- **`Decimal` ovunque**: `posizione.cash_out`, `posizione.closing_debt` sono già `Decimal`;
  `sp16g`/`sp16e` sono `Decimal` per costruzione in questo file.
- **Messaggi nuovi in italiano**: il messaggio della diagnostica `tax_settlement_reclass_below_zero`
  è in italiano; non usa `eur_it` (a differenza del Task 5, modulo diverso) perché l'importo va
  dentro un `amount` strutturato, come `unfunded_financing_requirement` e
  `missing_short_debt_breakdown` nello stesso file.
- **Il rischio di contare `cash_out` due volte non dà errore, sposta la cassa silenziosamente**: la
  prima prova negativa (sopra) lo dimostra nel verso opposto atteso (non un doppio conteggio, un
  conteggio nullo, perché la riga scritta su `sp09` viene scartata dal ricalcolo condiviso).
- **Inquinamento del database di prova fra run ripetuti**: `generate_projection` e
  `promote_projection_to_financial_year` fanno `commit()`; un `db.rollback()` a fine script non
  disfa un commit già avvenuto. **Ogni misura pulita ripete `sqlite3 .backup` da capo** prima di
  ogni singolo scenario che tocca `promote`.
- **Nessun caso, fra quelli misurabili nel DB disponibile, mostra `sp16g` negativo** (la guardia
  `tax_settlement_reclass_below_zero` non si è mai attivata nelle misure fatte finora): resta una
  guardia difensiva, esercitata solo dal test sintetico dedicato (Step 3).

## Constraints

- Nessuna modifica a `posizione_tributaria_fine_anno`/`tax_settlement_saldo_acconto` in
  `projection_common.py`: sono corrette, condivise col motore budget.
- Nessuna modifica al CASH PLUG, al clamp a zero, o alla diagnostica
  `unfunded_financing_requirement`: la decisione del proprietario sullo scoperto di c/c e sul
  rifiuto del promote non cambia.
- Nessuna modifica a `_distribute_sp16_operativo`/`_distribute_sp17_operativo`/
  `_distribute_sp06_operativo`/`_distribute_sp07_operativo` (territorio dei Task 1 e 2): questo
  task legge il loro output, non lo cambia.
- Il motore budget non è toccato.
- Il conguaglio si posa **sempre** su `sp16g` (mai su un campo finanziario, un fondo fiscale o una
  riserva).

## Ownership

`calculations/intra_year_engine.py` (i due punti indicati, dopo il Change dei Task 1 e 2),
`tests/test_intra_year_imposte.py` (nuovi test sintetici), CLAUDE.md e
`docs/import/REGOLE-IMPORT-05-INFRANNUALE.md`.

## Step

- [ ] **Step 1: Base.** I Change dei Task 1 e 2 devono essere già applicati e collaudati (15 test
  verdi fra `tests/test_intra_year_debito_bancario.py` e
  `tests/test_intra_year_crediti_commerciali.py`, banco di parità a 0 divergenze). `git rev-parse
  HEAD` deve stampare il commit del Task 2. **Rileggi l'ancora esatta** su entrambi i metodi
  (`_project_balance_sheet` e `_project_balance_sheet_annualized`) con:
  ```bash
  grep -n "sp16e = sp16e_governed" calculations/intra_year_engine.py
  ```
  Atteso: **due** occorrenze (una per metodo). Se il testo circostante non corrisponde a quanto
  descritto in «Interfaces»/«La correzione», fermarsi e riadattare l'ancora prima di procedere — il
  Task 2, per costruzione, non tocca `_project_balance_sheet_annualized` con lo stesso schema
  esplicito (non ha lì i campi `sp06e_governed` derivati in anticipo, dato che quel ramo usa
  `_distribute_sp06(partial_bs, sp06)`, non `_distribute_sp06_operativo`): verifica se quel ramo ha
  comunque una riga equivalente `sp16e = posizione.closing_debt` (con o senza il condizionale
  `manual_tax_position`) prima di applicare lo stesso Change lì — se la struttura è diversa da
  quella descritta sopra, adatta l'ancora e annota lo scarto nel rapporto di fine task invece di
  forzare un testo che non c'è.

- [ ] **Step 2: Copia di lavoro.**
  ```bash
  sqlite3 financial_analysis.db ".backup '/tmp/task3_db_prima.sqlite'"
  ```
  Una copia dedicata, mai riusata per più di uno scenario che chiami `promote`.

- [ ] **Step 3: Prova rossa (sintetica, unit-level).** Estendi `tests/test_intra_year_imposte.py`
  con un caso a composizione MISTA di `sp16` (a differenza della fixture esistente, concentrata al
  100% in `sp16e`), che oggi produce un fabbisogno dichiarato diverso dal vero `cash_out`:

  ```python
  def test_il_fabbisogno_dichiarato_coincide_col_vero_cash_out_su_sp16_misto():
      """sp16 di riferimento diviso fra banca e tributario (non 100% tributario come
      _infrannuale): la quota-riferimento di sp16e (da _distribute_sp16_operativo, Task 1)
      diverge dal vero saldo di apertura del parziale, e prima di questo Change quella
      divergenza si perdeva senza flusso di cassa esplicito. Adattare i valori concreti allo
      schema di _infrannuale/_sessione gia' in uso in questo file (fixture con riferimento
      pieno + parziale, tax_rate e crescita a 0 dove non serve isolare altro)."""
      # ... costruire riferimento con sp16 diviso fra sp16a (banca) e sp16e (tributario),
      # parziale con un vero debito tributario di apertura diverso dalla quota-riferimento
      # implicita, assumption con perdita (ce20_override=0 o utile nullo) cosi' cash_out
      # e' calcolabile a mano dal solo debito d'apertura.
      ...
      assert D(str(bs.sp09_disponibilita_liquide)) == cassa_attesa_calcolata_a_mano
      # e, se il fabbisogno e' negativo: l'ammontare della diagnostica
      # unfunded_financing_requirement coincide con |sbilancio| a meno di 0,01
  ```
  Aggiungi anche un secondo caso sintetico con `sp06e` di apertura > 0 (credito tributario, non
  debito) per verificare che il Task 2 abbia davvero chiuso il lato credito (nessun conguaglio
  aggiuntivo necessario lì), e un terzo che spinga deliberatamente `sp16g` sotto zero per esercitare
  la diagnostica `tax_settlement_reclass_below_zero` (mai osservata nelle misure fatte finora).
  Esegui e conferma che **fallisce** sul codice Task 1+2 (prima di questo Change) con l'output
  sbagliato (la quota-riferimento, non `cash_out`).

- [ ] **Step 4: Applica il Change** (il blocco adattato sopra, in entrambi i metodi, sull'ancora
  verificata allo Step 1).

- [ ] **Step 5: Verde.**
  ```bash
  cd /home/peter/DEV/budget
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_intra_year_imposte.py -q \
    -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: tutti i test passano, inclusi i nuovi (nessuna asserzione esistente cambia: la fixture
  `_infrannuale` concentra tutto `sp16` in `sp16e`, quindi la quota-riferimento pre-Change coincide
  già col vero saldo — il conguaglio vale zero su quella fixture, prima e dopo).

- [ ] **Step 6: Non-regressione mirata.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest \
    tests/test_lifecycle_repeat.py tests/test_http_full_cycle.py \
    tests/test_standard_ivcee_parser.py tests/test_intra_year_debito_bancario.py \
    tests/test_intra_year_crediti_commerciali.py \
    -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: nessuna regressione rispetto alla baseline post Task 1+2.

- [ ] **Step 7: Suite intera.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests -q --ignore=tests/corpus \
    -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: `failed` non aumenta rispetto alla baseline stabilita post Task 1+2, nello stesso
  ambiente.

- [ ] **Step 8: Ri-misura sul caso reale, CON i Task 1 e 2 già applicati — Step obbligatorio, non
  facoltativo.** Ricostruisci lo scenario di collaudo (azienda id 21, base 2025, parziale 9M 2026)
  su una copia fresca del database, sull'albero con i Change dei Task 1 e 2 **già applicati**, e
  misura, **senza** questo Change: il promote **riesce** (sbilancio 0,00 — misurato dal Task 1,
  Step 8: la sola patch del Task 1 azzera lo sbilancio di questo scenario, il che **violerebbe** la
  decisione del proprietario se questo Task 3 non venisse applicato sopra). Poi, **con** questo
  Change applicato: misura di nuovo sbilancio, importo di `unfunded_financing_requirement`, esito
  del promote. **Avvertenza esplicita**: la bozza originale (`bozza-task-T.md`) aveva misurato
  questo stesso scenario con **solo** il Task 1 applicato (senza il Task 2) e aveva trovato uno
  sbilancio di **1.856,76** — quel numero **non è vincolante qui**, perché il Task 2 cambia anche il
  totale `sp06`/`sp07` e quindi la cassa strutturale dello scenario prima di qualunque aggiustamento
  tributario (misurato dal Task 2, Step 8: `sp09` dell'azienda 237 si sposta di 28.773,00 fra "solo
  Task 1" e "Task 1+2"; un movimento della stessa natura, anche se di importo diverso, è atteso
  anche sull'azienda 21). **L'osservabile vincolante è qualitativo**: fabbisogno dichiarato in
  `unfunded_financing_requirement` uguale allo sbilancio finale (a meno di 0,01), e promote
  **rifiutato** — non il numero esatto 1.856,76. Annota nel rapporto di fine task il numero
  effettivamente misurato con Task 1+2+3 insieme, per sostituirlo alle citazioni di questo piano
  nell'aggiornamento finale della documentazione (Step 10). Ripeti anche sull'azienda id 50 (cassa
  abbondante, il Task 1 è un no-op lì) e conferma che il promote resta accettato con una cassa
  ridotta esattamente del vero saldo tributario ora pagato (misurato dalla bozza, isolatamente:
  11.398,00 — verifica se lo stesso numero regge anche sopra Task 1+2, dato che quello scenario non
  ha dettaglio bancario da correggere).

- [ ] **Step 9: Verifica l'assenza di doppio conteggio con un calcolo indipendente.** Per lo
  scenario dell'azienda id 21 (Step 8): con un `print` di debug temporaneo (rimosso prima del
  commit), leggi `cash_out` e la quota-riferimento pre-sostituzione di `sp16e` **sull'albero
  Task 1+2** (non quelli della bozza, calcolati su Task 1 da solo); verifica che
  `cassa_con_Change − cassa_senza_Change == -cash_out` esattamente (a meno di 0,01), come impone la
  dimostrazione algebrica in «La correzione» sopra. Se lo scarto misurato non coincide con
  `-cash_out`, fermarsi: l'ancora dello Step 1 potrebbe non essere quella giusta sul ramo toccato,
  o `_project_balance_sheet_annualized` potrebbe avere una struttura diversa da quella assunta.

- [ ] **Step 10: Documentazione.**
  - **CLAUDE.md**, sezione «Intra-Year Engine (Infrannuale)», frase attuale:
    > "...taxes are recomputed on projected pre-tax profit, and at 31/12 only the current year's
    > balance remains: tax of the year minus the advances paid in the year (`tax_advances_paid` if
    > greater than zero, otherwise 100% of the reference year's `ce20`); whatever was open at the
    > partial month leaves cash by year end (`projection_common.posizione_tributaria_fine_anno`),
    > so a budget born from the promote no longer inherits it."

    Diventa:
    > "...taxes are recomputed on projected pre-tax profit, and at 31/12 only the current year's
    > balance remains: tax of the year minus the advances paid in the year (`tax_advances_paid` if
    > greater than zero, otherwise 100% of the reference year's `ce20`); whatever was open at the
    > partial month leaves cash by year end — `projection_common.posizione_tributaria_fine_anno`
    > computes the amount (`cash_out`) and `intra_year_engine` applies it against the group's
    > neutral field (`sp16g`), **never against `sp09` directly** (the shared cash recompute in
    > `ForecastEngine._normalize_balance_sheet_cents(recompute_cash=True)`, called by every
    > `generate_projection`, would silently discard a direct write to `sp09`) — so a budget born
    > from the promote no longer inherits it. **Historical defect, fixed in this wave:** before
    > this fix `cash_out` was computed and never read anywhere; the `sp16e` swap alone moved cash
    > only by coincidence, exactly when the pre-swap value (a reference-year proportional share,
    > `_distribute_sp16_operativo`) already matched the partial year's true balance — on a mixed
    > `sp16` composition it understated the true cash effect."
  - **`docs/import/REGOLE-IMPORT-05-INFRANNUALE.md`**, paragrafo "La posizione tributaria al
    31/12", frase attuale:
    > "Nel motore la cassa resta il plug, quindi è il kernel a dichiarare `cash_out` e il test
    > end-to-end a verificarlo."

    Diventa (aggiunta, non sostituzione):
    > "Nel motore la cassa resta il plug: `cash_out` non tocca mai `sp09` direttamente (il
    > ricalcolo di `ForecastEngine._normalize_balance_sheet_cents(recompute_cash=True)`, condiviso
    > col motore budget, lo scarterebbe), ma il campo neutro del gruppo passivo (`sp16g`) che il
    > plug legge — cosicché il fabbisogno dichiarato coincide sempre con `cash_out`, anche quando
    > la ripartizione per riferimento di `sp16` non concentra tutta la massa nella voce tributaria
    > (prima di questa correzione la coincidenza valeva solo per caso, quando la quota-riferimento
    > eguagliava il vero saldo di apertura del parziale — il test end-to-end esistente non lo
    > esercitava, perché la sua fixture concentra tutto `sp16` in `sp16e`)."

- [ ] **Step 11: Commit.**
  ```bash
  git add calculations/intra_year_engine.py tests/test_intra_year_imposte.py \
    CLAUDE.md docs/import/REGOLE-IMPORT-05-INFRANNUALE.md
  git commit -F - <<'EOF'
  fix(infrannuale): l'uscita di cassa tributaria diventa esplicita, non un effetto collaterale

  cash_out (calculations/projection_common.posizione_tributaria_fine_anno) era calcolato e mai
  letto altrove nel motore infrannuale: il suo effetto sulla cassa proiettata emergeva solo per
  differenza implicita fra la quota-riferimento che _distribute_sp16_operativo aveva proiettato per
  sp16e e il vero saldo tributario -- coincideva col vero cash_out solo per caso, quando le due
  cifre si somigliavano.

  Un conguaglio esplicito, applicato sul campo neutro del gruppo passivo (sp16g, lo stesso che
  assorbe il residuo di arrotondamento) subito prima della sostituzione finale di sp16e, riporta
  l'effetto di cassa della sostituzione esattamente a -cash_out, dimostrato algebricamente
  indipendente dai valori di partenza. Mai una scrittura diretta su sp09: il ricalcolo condiviso con
  il motore budget (ForecastEngine._normalize_balance_sheet_cents(recompute_cash=True)) la
  scarterebbe in silenzio, come verificato con una prima prova negativa.

  Applicato sopra i Task di questa ondata che portano il debito finanziario e i crediti dal
  parziale: quei due task avevano gia' chiuso lo stesso difetto sul lato credito (sp06e), quindi
  qui resta solo il termine debito. Sullo scenario di collaudo (azienda id 21) il fabbisogno
  dichiarato torna a coincidere con lo sbilancio e il promote resta rifiutato, come vuole la
  decisione del proprietario sullo scoperto tributario d'apertura -- il numero esatto e' misurato
  nello Step 8 di questo task, non ereditato dalla bozza (scritta sopra un solo dei due task
  precedenti).

  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01C8chDC8b297itUaoK1TQNW
  EOF
  ```

## Observable acceptance

I test sintetici nuovi su `tests/test_intra_year_imposte.py` passano (composizione mista, credito
tributario, guardia sotto-zero); i 9 test esistenti restano invariati (fixture al 100% su `sp16e`,
conguaglio nullo per costruzione); `tests/test_lifecycle_repeat.py`, `tests/test_http_full_cycle.py`,
`tests/test_standard_ivcee_parser.py` invariati; suite intera senza aumento di `failed`; **sullo
scenario di collaudo (azienda id 21), dopo Task 1+2+3 insieme**: il fabbisogno dichiarato in
`unfunded_financing_requirement` coincide con lo sbilancio (a meno di 0,01) e il promote è
**rifiutato** — il numero esatto è quello misurato allo Step 8, non 1.856,76 né 24.165,53 (entrambi
misurati su basi diverse da questo piano); sull'azienda id 50 il promote resta accettato con una
cassa ridotta del vero saldo tributario; CLAUDE.md e
`docs/import/REGOLE-IMPORT-05-INFRANNUALE.md` allineati nello stesso commit.

---

### Task 4: Una sola percentuale di variazione, che non esplode su un riferimento nullo al centesimo

**Files:**
- Modify: `frontend/lib/pratica-format.ts` (nuovo export `deltaPct`, rete secondaria in `formatPct`)
- Create: `frontend/lib/pratica-format.test.ts`
- Modify: `frontend/components/pratica/StampaContent.tsx`
- Modify: `frontend/components/pratica/ComparisonTable.tsx`
- Modify: `frontend/components/pratica/ProjectionTable.tsx`
- Modify: `frontend/lib/pratica-statement-rows.ts`
- Modify: `docs/frontend/INDICATORI-E-STAMPA.md` (nuova sezione breve)

**Interfaces:**
- Consumes: nulla dagli altri task di questa ondata — file interamente disgiunti (frontend, mai
  `calculations/intra_year_engine.py`).
- Produces: `deltaPct(current: number, reference: number): number | null` in
  `frontend/lib/pratica-format.ts` — nessun altro task di questa ondata lo consuma, ma resta
  l'helper condiviso per qualunque vista futura che debba confrontare un valore con un riferimento.

**Target.** Riga "DIFFERENZA (Attivo - Passivo)" della tab Stampa/Confronto/Proiezione:
`+2366097483366300.0%` quando il riferimento è una somma client di ~10 `float` che per costruzione
contabile dovrebbe annullarsi ma lascia un residuo `~1e-9`..`~1e-13` invece di `0` letterale. Un
helper condiviso `deltaPct` sostituisce tre implementazioni inline duplicate della stessa formula
(`((x - ref) / Math.abs(ref)) * 100`, guardia `=== 0`/`!== 0` esatta), arrotondando il riferimento al
centesimo — la stessa tolleranza di quadratura di `config.py:235`
(`VALIDATION_RULES["balance_sheet_tolerance"] = 0.01`) — prima di deciderlo "assente". Più una rete
di sicurezza in `formatPct` per un valore non finito, e la stessa correzione sul campo
`pct_of_reference` (`safePct`, oggi duplicato due volte in `lib/pratica-statement-rows.ts`, mai reso
da nessuna vista ma stesso rischio latente).

## Da leggere prima, per simbolo

- `frontend/lib/pratica-format.ts` — file **già esistente** (4 export: `MONTH_LABELS`,
  `SECTOR_OPTIONS`, `formatEuro`, `formatPct`, `formatInputNumber`, `parseInputNumber`), 51 righe,
  terminatori **LF puri**: è il posto giusto per `deltaPct`, non un nuovo file — nessun altro
  modulo `lib/pratica-*` ha una responsabilità di formattazione più specifica. `formatPct` oggi
  (riga 34-36):
  ```ts
  export function formatPct(value: number): string {
    return `${value.toFixed(1)}%`;
  }
  ```
- `frontend/components/pratica/StampaContent.tsx` — CRLF. `deltaFmt` righe 206-214:
  ```ts
  const deltaFmt = (proj: number, ref: number) => {
    if (ref === 0) return <span className="text-muted-foreground">-</span>;
    const d = ((proj - ref) / Math.abs(ref)) * 100;
    return (
      <span className={d > 1 ? "text-green-600 dark:text-green-400" : d < -1 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"}>
        {d > 0 ? "+" : ""}{formatPct(d)}
      </span>
    );
  };
  ```
  Chiamata quattro volte: righe 477, 522, 573, 628. Import di riga 32:
  `import { formatEuro, formatPct } from "@/lib/pratica-format";`.
- `frontend/components/pratica/ComparisonTable.tsx` — CRLF. Blocco righe 197-226 (IIFE dentro la
  `map`); il calcolo è alle righe 202-204:
  ```ts
  const delta = item.reference_value !== 0
    ? ((compareValue - item.reference_value) / Math.abs(item.reference_value)) * 100
    : 0;
  ```
  `compareValue` (riga 198) è `showAnnualized ? item.annualized_value : item.partial_value`, già
  guardato da `isNaN(compareValue)` (righe 199-201). Import di riga 12:
  `import { formatEuro, formatPct } from "@/lib/pratica-format";`. Questa tabella è riusata **sia**
  dalla tab Confronto **sia** dalla tab Proiezione per lo SP.
- `frontend/components/pratica/ProjectionTable.tsx` — CRLF. Calcolo righe 165-167:
  ```ts
  const delta = item.reference_value !== 0
    ? ((projValue - item.reference_value) / Math.abs(item.reference_value)) * 100
    : 0;
  ```
  Reso alle righe 224-240. Import righe 13-18.
- `frontend/lib/pratica-statement-rows.ts` — CRLF. **Due copie identiche** di `safePct`: riga 32
  dentro `buildBalanceItemsWithTotals`, riga 203 dentro `buildIncomeItemsWithEbitda`:
  ```ts
  const safePct = (a: number, b: number) => (b !== 0 ? (a / b) * 100 : 0);
  ```
  Nessuna vista trovata legge `item.pct_of_reference` (Stampa/Confronto/Proiezione ricalcolano
  `delta` per conto proprio): campo silenziosamente inerte oggi, ma un rischio identico se qualcuno
  lo rendesse in futuro.
- `config.py:235` — `"balance_sheet_tolerance": 0.01` dentro `VALIDATION_RULES`: la tolleranza di
  quadratura Attivo=Passivo citata da CLAUDE.md. `deltaPct` la riusa concettualmente (stesso ordine
  di grandezza, non lo stesso valore Python — non c'è un modo pulito di importare una costante
  Python in TypeScript qui; il commento nel codice lo dichiara esplicitamente).
- Convenzione di resa già in uso nel progetto per un valore "indefinito" (verificata a grep in
  `RettificheTab.tsx`, `ComparisonTable.tsx`, `StampaContent.tsx`): sempre un trattino `"-"`
  semplice, colorato `text-muted-foreground` — **mai** un valore numerico di ripiego.

## Trappole note (CLAUDE.md › Invarianti e trappole › Frontend)

- `lib/pratica-*` non importa mai da `app/` o da `components/`: `pratica-format.ts` non deve
  introdurre un simile import — resta una funzione pura testabile in `environment: node`.
- Gli elenchi di **codici** congelati in `ivcee-catalog-parity.test.ts` non si toccano; questo task
  non tocca codici SP/CE, solo la resa di una percentuale.
- I quattro componenti CRLF (`ComparisonTable.tsx`, `ProjectionTable.tsx`, `StampaContent.tsx`,
  `pratica-statement-rows.ts`) vanno preservati: l'editor del harness normalizza CRLF→LF su un file
  toccato, quindi dopo ogni modifica va **riconvertito** a CRLF e va controllato `git diff --stat`.

## Change

1. `frontend/lib/pratica-format.ts` — aggiungi, dopo `formatPct`:

```ts
/**
 * Percentuale di variazione fra un valore corrente e un riferimento, `null` quando il
 * riferimento è zero AL CENTESIMO (stessa tolleranza di quadratura di `config.py:235`,
 * `VALIDATION_RULES["balance_sheet_tolerance"] = 0.01`), non zero esatto.
 *
 * Perché: un riferimento che per identità contabile DOVREBBE annullarsi (es. la riga
 * "DIFFERENZA (Attivo - Passivo)" di Stampa/Confronto/Proiezione) arriva dal backend come somma
 * di ~10 `float` via Decimal→float (`DecimalJSONResponse`); la somma in virgola mobile non è
 * associativa e può lasciare un residuo dell'ordine di 1e-9..1e-13 invece di 0 letterale.
 * Dividere uno sbilancio vero anche piccolo per un residuo di quell'ordine dà una percentuale a
 * 12-15 cifre (osservato: +2366097483366300.0%, indagine-3 del 2026-09-11). Un confronto con
 * zero esatto non intercetta il residuo; arrotondare al centesimo prima del confronto sì, e non
 * sposta nessuna riga sana (il residuo è ~9 ordini di grandezza sotto un centesimo).
 */
export function deltaPct(current: number, reference: number): number | null {
  if (Math.round(reference * 100) === 0) return null;
  return ((current - reference) / Math.abs(reference)) * 100;
}
```

2. `frontend/lib/pratica-format.ts` — rete secondaria in `formatPct`, **solo** per un valore non
   finito (niente tetto di magnitudine: un tetto fisso potrebbe nascondere un'anomalia reale molto
   grande ma legittima — la causa dell'esplosione è già rimossa alla fonte da `deltaPct` nei tre
   siti che lo usano):

```ts
export function formatPct(value: number): string {
  if (!Number.isFinite(value)) return "-";
  return `${value.toFixed(1)}%`;
}
```

3. `frontend/components/pratica/StampaContent.tsx`:
   - Riga 32, aggiungi `deltaPct` all'import:
     ```ts
     import { formatEuro, formatPct, deltaPct } from "@/lib/pratica-format";
     ```
   - Righe 206-214, sostituisci `deltaFmt`:
     ```ts
     const deltaFmt = (proj: number, ref: number) => {
       const d = deltaPct(proj, ref);
       if (d === null) return <span className="text-muted-foreground">-</span>;
       return (
         <span className={d > 1 ? "text-green-600 dark:text-green-400" : d < -1 ? "text-red-600 dark:text-red-400" : "text-muted-foreground"}>
           {d > 0 ? "+" : ""}{formatPct(d)}
         </span>
       );
     };
     ```
   - Le quattro chiamate (righe 477, 522, 573, 628) non cambiano: stessa firma `(proj, ref)`.

4. `frontend/components/pratica/ComparisonTable.tsx`:
   - Riga 12, aggiungi `deltaPct` all'import:
     ```ts
     import { formatEuro, formatPct, deltaPct } from "@/lib/pratica-format";
     ```
   - Righe 197-226, sostituisci l'IIFE:
     ```tsx
     {(() => {
       const compareValue = showAnnualized ? item.annualized_value : item.partial_value;
       if (isNaN(compareValue)) {
         return <TableCell className="text-right text-sm text-muted-foreground">-</TableCell>;
       }
       const delta = deltaPct(compareValue, item.reference_value);
       if (delta === null) {
         return <TableCell className="text-right text-sm text-muted-foreground">-</TableCell>;
       }
       const isPositive = delta > 1;
       const isNegative = delta < -1;
       return (
         <TableCell className="text-right text-sm">
           {isPctRow ? (
             <span className="text-muted-foreground">-</span>
           ) : (
             <span
               className={
                 isPositive
                   ? "text-green-600 dark:text-green-400"
                   : isNegative
                   ? "text-red-600 dark:text-red-400"
                   : "text-muted-foreground"
               }
             >
               {delta > 0 ? "+" : ""}{formatPct(delta)}
             </span>
           )}
         </TableCell>
       );
     })()}
     ```
   - Nota: `isPctRow` continua a vincere (mostra sempre `-`) come oggi — nessun cambiamento a quel
     ramo, solo al calcolo di `delta`.

5. `frontend/components/pratica/ProjectionTable.tsx`:
   - Riga 18 (chiusura import), aggiungi `deltaPct`:
     ```ts
     import {
       formatEuro,
       formatPct,
       formatInputNumber,
       parseInputNumber,
       deltaPct,
     } from "@/lib/pratica-format";
     ```
   - Righe 165-169, sostituisci:
     ```ts
     const delta = deltaPct(projValue, item.reference_value);
     const isPositive = delta !== null && delta > 1;
     const isNegative = delta !== null && delta < -1;
     ```
   - Righe 224-240 (blocco "Delta %"), sostituisci:
     ```tsx
     <TableCell className="text-right text-sm">
       {isPctRow || delta === null ? (
         <span className="text-muted-foreground">-</span>
       ) : (
         <span
           className={
             isPositive
               ? "text-green-600 dark:text-green-400"
               : isNegative
               ? "text-red-600 dark:text-red-400"
               : "text-muted-foreground"
           }
         >
           {delta > 0 ? "+" : ""}{formatPct(delta)}
         </span>
       )}
     </TableCell>
     ```

6. `frontend/lib/pratica-statement-rows.ts` — sostituisci **entrambe** le copie di `safePct` (righe
   32 e 203) con `deltaPct` importato da `./pratica-format`. Import in cima al file (dopo
   `import { labelOf } from "@/lib/ivcee-catalog";`):
   ```ts
   import { deltaPct } from "@/lib/pratica-format";
   ```
   Riga 32 (dentro `buildBalanceItemsWithTotals`) e riga 203 (dentro `buildIncomeItemsWithEbitda`):
   ```ts
   const safePct = (a: number, b: number) => deltaPct(a, b) ?? 0;
   ```
   **Decisione presa in questo piano** (nella bozza era lasciata al coordinatore): si assorbe a `0`,
   non si propaga `null` fino a `pct_of_reference` — nessuna vista legge oggi quel campo
   (verificato: nessun hit per `.pct_of_reference` in `frontend/components` o `frontend/app`), e
   propagare `null` cambierebbe il tipo `IntraYearComparisonItem` in `frontend/types/api.ts` per un
   consumo che non esiste. Il rischio che questo chiude è che una futura vista che rendesse
   `pct_of_reference` userebbe comunque `deltaPct`, non una terza copia di `b !== 0 ? … : 0`.

## Constraints

- Nessun cambiamento ai codici SP/CE, alle etichette o all'ordine delle righe: solo alla resa della
  percentuale.
- Tutte le righe "sane" della tabella (crescita, EBIT, debiti previdenziali) restano identiche al
  decimo di punto.
- Nessun tetto numerico arbitrario in `formatPct`.
- CRLF preservato su `StampaContent.tsx`, `ComparisonTable.tsx`, `ProjectionTable.tsx`,
  `pratica-statement-rows.ts`; `pratica-format.ts` è LF puro e resta tale.

## Ownership

`frontend/lib/pratica-format.ts`, `frontend/lib/pratica-format.test.ts` (nuovo),
`frontend/components/pratica/StampaContent.tsx`, `frontend/components/pratica/ComparisonTable.tsx`,
`frontend/components/pratica/ProjectionTable.tsx`, `frontend/lib/pratica-statement-rows.ts`,
`docs/frontend/INDICATORI-E-STAMPA.md`.

## Step

- [ ] **Step 1: Base.** `cd /home/peter/DEV/budget && git rev-parse HEAD` (deve stampare
  `0f7614a...`).

- [ ] **Step 2: Test nuovo, prova rossa.** Crea `frontend/lib/pratica-format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { deltaPct, formatPct } from "./pratica-format";

describe("deltaPct", () => {
  it("torna null quando il riferimento e' un residuo di somma float sotto il centesimo (indagine-3, 2026-09-11)", () => {
    // Stesso ordine di grandezza del residuo riprodotto: 3.725290298461914e-9, con lo
    // sbilancio reale del collaudo (5.509,29) come valore corrente.
    expect(deltaPct(5509.29, 3.725290298461914e-9)).toBeNull();
  });

  it("torna null quando il riferimento e' zero letterale (caso gia' gestito prima del fix)", () => {
    expect(deltaPct(5509.29, 0)).toBeNull();
  });

  it("torna null appena sotto il centesimo (0,004 arrotonda a zero)", () => {
    expect(deltaPct(1000, 0.004)).toBeNull();
  });

  it("calcola normalmente a un centesimo esatto (0,01 non arrotonda a zero)", () => {
    // (1000 - 0.01) / 0.01 * 100 = 9999900
    expect(deltaPct(1000, 0.01)).toBeCloseTo(9999900, 0);
  });

  it("riga sana: ricavi 1.000.000 -> 1.100.000 e' +10,0%, invariata dal fix", () => {
    expect(deltaPct(1100000, 1000000)).toBeCloseTo(10, 6);
  });

  it("riga sana: EBIT storico -50.000 -> proiezione -40.000 e' +20,0%, invariata dal fix", () => {
    expect(deltaPct(-40000, -50000)).toBeCloseTo(20, 6);
  });

  it("riga sana: debiti previdenziali 12.345,67 -> 15.000 e' ~21,5%, invariata dal fix", () => {
    expect(deltaPct(15000, 12345.67)).toBeCloseTo(21.503, 2);
  });
});

describe("formatPct rete secondaria", () => {
  it("un valore normale non cambia", () => {
    expect(formatPct(21.5)).toBe("21.5%");
  });

  it("NaN si rende come indefinito (-), non come testo NaN%", () => {
    expect(formatPct(NaN)).toBe("-");
  });

  it("Infinity si rende come indefinito (-), non come numero enorme", () => {
    expect(formatPct(Infinity)).toBe("-");
    expect(formatPct(-Infinity)).toBe("-");
  });
});
```

  Nota: `formatPct` usa `toFixed(1)` con `.` come separatore decimale (non è una resa italiana —
  quella la fa `Intl.NumberFormat` altrove, es. `formatEuro`); il test rispecchia il comportamento
  **attuale** di `formatPct`, non introduce un cambiamento di locale non richiesto da questo task.

- [ ] **Step 3: Prova rossa.**
  ```bash
  test -e /home/peter/DEV/budget/frontend/node_modules || echo "node_modules assente: npm install prima di procedere"
  cd /home/peter/DEV/budget/frontend && npx vitest run lib/pratica-format.test.ts
  ```
  Atteso: FAIL — `deltaPct` non è esportato da `pratica-format.ts` (errore di importazione, non
  un'asserzione fallita).

- [ ] **Step 4: Implementa i punti 1-2 del Change** (solo `pratica-format.ts`, LF puro).

- [ ] **Step 5: Verde parziale.**
  ```bash
  cd /home/peter/DEV/budget/frontend && npx vitest run lib/pratica-format.test.ts
  ```
  Atteso: 9 passed.

- [ ] **Step 6: Prima di toccare i file CRLF, verifica i terminatori.**
  ```bash
  cd /home/peter/DEV/budget
  file frontend/components/pratica/StampaContent.tsx frontend/components/pratica/ComparisonTable.tsx frontend/components/pratica/ProjectionTable.tsx frontend/lib/pratica-statement-rows.ts
  ```
  Atteso: tutti e quattro riportano "with CRLF line terminators".

- [ ] **Step 7: Implementa i punti 3-6 del Change** (i quattro file CRLF).

- [ ] **Step 8: Riporta a CRLF ogni file toccato allo Step 7**, uno per uno:
  ```bash
  cd /home/peter/DEV/budget
  for f in frontend/components/pratica/StampaContent.tsx frontend/components/pratica/ComparisonTable.tsx frontend/components/pratica/ProjectionTable.tsx frontend/lib/pratica-statement-rows.ts; do
    /home/peter/DEV/budget/backend/venv/bin/python -c "import sys;p=sys.argv[1];b=open(p,'rb').read().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n');open(p,'wb').write(b)" "$f"
  done
  git diff --stat
  ```
  Controlla che `git diff --stat` conti solo le righe davvero cambiate per ciascun file — se un file
  mostra più righe cambiate di quelle toccate dal Change, è un file riscritto per intero: fermarsi
  e correggere prima di proseguire.

- [ ] **Step 9: Verde completo.**
  ```bash
  cd /home/peter/DEV/budget/frontend && npx vitest run lib/pratica-format.test.ts
  ```
  Atteso: 9 passed.

- [ ] **Step 10: Tipi e suite esistente.**
  ```bash
  cd /home/peter/DEV/budget/frontend
  npx tsc --noEmit
  npx vitest run
  ```
  Atteso: `tsc` pulito; `ivcee-catalog-parity.test.ts` e il resto della suite verdi (nessun codice
  SP/CE toccato da questo task).

- [ ] **Step 11: Documentazione — `docs/frontend/INDICATORI-E-STAMPA.md`.** Aggiungi, dopo la
  sezione «Limite noto: il denominatore dei rapporti percentuali» (in coda al file), una nuova
  sezione:
  ```
  ## La riga DIFFERENZA (Attivo − Passivo): `deltaPct`

  Prima di questo task, la percentuale di variazione di Stampa/Confronto/Proiezione confrontava il
  riferimento con zero ESATTO: sulla riga «DIFFERENZA (Attivo - Passivo)» — un valore che per
  identità contabile dovrebbe annullarsi, ma arriva dal backend come somma client di ~10 `float`
  (`Decimal` → `float` via `DecimalJSONResponse`) che lascia un residuo `~1e-9..1e-13` invece di `0`
  letterale — dividere uno sbilancio vero, anche piccolo, per un residuo di quell'ordine dava una
  percentuale a 12-15 cifre (`+2366097483366300.0%`, indagine del 2026-09-11).

  `deltaPct` (`frontend/lib/pratica-format.ts`) arrotonda il riferimento al centesimo — la stessa
  tolleranza di quadratura di `config.py:235` — prima di deciderlo "assente" (`null`, reso come
  `-`): usato da `StampaContent.tsx`, `ComparisonTable.tsx` e `ProjectionTable.tsx`, le tre copie
  inline della stessa formula sono sparite. `formatPct` ha in più una rete secondaria per un
  valore non finito (`NaN`/`Infinity` → `-`), senza alcun tetto di magnitudine: un tetto fisso
  nasconderebbe un'anomalia reale molto grande ma legittima, e la causa dell'esplosione è già
  rimossa alla fonte.
  ```

- [ ] **Step 12: Commit.**
  ```bash
  git add frontend/lib/pratica-format.ts frontend/lib/pratica-format.test.ts \
    frontend/components/pratica/StampaContent.tsx frontend/components/pratica/ComparisonTable.tsx \
    frontend/components/pratica/ProjectionTable.tsx frontend/lib/pratica-statement-rows.ts \
    docs/frontend/INDICATORI-E-STAMPA.md
  git commit -F - <<'EOF'
  fix(pratica): una percentuale di variazione condivisa non esplode su un riferimento nullo al centesimo

  `deltaPct` (frontend/lib/pratica-format.ts) sostituisce tre copie inline della stessa formula in
  StampaContent, ComparisonTable e ProjectionTable: arrotonda il riferimento al centesimo (tolleranza
  di config.py:235) prima di deciderlo "assente", invece di confrontarlo con zero esatto. Risolve la
  riga DIFFERENZA (Attivo - Passivo) che mostrava +2366097483366300.0% quando il riferimento era un
  residuo di somma float (indagine-3, 2026-09-11). formatPct guadagna una rete secondaria per i
  valori non finiti (NaN/Infinity -> "-"), senza tetto di magnitudine arbitrario. safePct
  (lib/pratica-statement-rows.ts, due copie, campo pct_of_reference mai reso) riusa lo stesso
  helper, assorbendo null a zero.

  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01C8chDC8b297itUaoK1TQNW
  EOF
  ```

## Observable acceptance

9 test nuovi verdi su `pratica-format.test.ts`; `npx tsc --noEmit` pulito; `npx vitest run` (suite
intera) verde, `ivcee-catalog-parity.test.ts` compreso; la riga DIFFERENZA della tab
Stampa/Confronto/Proiezione mostra `-` invece di una percentuale a 12-15 cifre quando lo storico
quadra al centesimo e la proiezione no; nessuna riga sana della tabella cambia valore;
`docs/frontend/INDICATORI-E-STAMPA.md` allineato nello stesso commit.

---

### Task 5: I messaggi di quadratura dicono gli importi all'europea

**Files:**
- Modify: `importers/iv_cee_hierarchy.py` (8 occorrenze)
- Modify: `backend/app/api/v1/financial_years.py` (3 occorrenze — perimetro esteso dal
  coordinatore in fase di assemblaggio, vedi «Perimetro esteso» sotto)
- Modify: `importers/pdf_importer.py` (3 occorrenze, helper locale `_it_amount` già presente —
  stesso perimetro esteso)
- Test: `tests/test_messaggi_italiani.py` (estensione: 3 test nuovi, uno per modulo)
- Modify: `docs/import/REGOLE-IMPORT-04-QUADRATURE.md` (nota di chiusura §5)

**Interfaces:**
- Consumes: nulla dagli altri task di questa ondata — tre file indipendenti da
  `calculations/intra_year_engine.py` e dal frontend.
- Produces: nessuna interfaccia nuova per altri task; `eur_it` (già esistente in
  `calculations/projection_common.py`) e `_it_amount` (già esistente in `importers/pdf_importer.py`)
  restano gli unici due helper di formattazione italiana per gli importi lato Python — nessun terzo
  ne nasce qui.

**Target.** Le 8 occorrenze di formattazione all'americana (`{x:,.2f}`/`{x:.1f}`) in
`importers/iv_cee_hierarchy.py` diventano `eur_it(x)` (da `calculations.projection_common`, già
usato per il messaggio gemello del motore budget, `Fabbisogno finanziario scoperto`). Nessun ciclo
di import (verificato: `iv_cee_hierarchy.py` già importa da `calculations.ce_result` nello stesso
verso; `projection_common.py` non importa mai da `importers/`).

**Perimetro esteso dal coordinatore.** La bozza originale (`bozza-task-P-F.md`) limitava il Change
a `importers/iv_cee_hierarchy.py`, elencando **9 altri file** con lo stesso schema come «fuori
perimetro» con la loro motivazione — tutti restano fuori **tranne due**, che quella stessa bozza
segnalava come «candidato forte per un task gemello» perché user-facing con lo stesso difetto di
classe: il coordinatore, in fase di assemblaggio di questo piano, li ha portati **dentro** questo
task come secondo blocco di Change, invece di farne un task gemello — stessa classe di difetto,
stessa prova, un solo giro di revisione:

- `backend/app/api/v1/financial_years.py:449,451,454` — il 400 della guardia `PUT /adjustments`
  (Rettifiche): `f"Attivo−Passivo {cur_imb:,.2f}→{new_imb:,.2f}"`, idem per `CE−SP13` e
  `aggregati−dettagli`. Verificato fino all'HTTP: `raise HTTPException(400, detail="Rettifiche
  contabilmente incoerenti: " + "; ".join(worsened) + ...)` — stesso schema del 400 di `/promote`,
  stesso bug di classe, un componente diverso (Rettifiche, non import/promote).
- `importers/pdf_importer.py:1385,1387,1398` — route C (situazione contabile):
  `others = ", ".join(f"{s}={r:,.0f}" ...)`, `f"... {residual:,.0f}); candidati: {others}"`,
  `f"BILANCIO NON QUADRATO ({_sev}): residuo {residual:,.0f} ..."`. Verificato fino al DOM: questi
  finiscono in `sc_quadratura_warnings`, che confluisce in `warnings` restituito dall'endpoint di
  import e reso **parola per parola** da `frontend/components/import/ImportPanel.tsx:348-350`. Il
  file ha **già** un helper italiano locale, `_it_amount` (righe 76-78:
  `f"{value:,.2f}".replace(',', '#').replace('.', ',').replace('#', '.')`), usato altrove nello
  stesso file ma **non** su queste tre righe: nessun import nuovo, si applica l'helper già presente.
  **Nota di precisione**: `_it_amount` produce sempre 2 decimali; le tre righe originali usano
  `:,.0f` (0 decimali). Applicare `_it_amount` sposta questi tre messaggi da 0 a 2 decimali — una
  precisione maggiore, coerente col resto dell'app (`eur_it` produce sempre 2 decimali anch'esso),
  non un secondo difetto: dichiaralo nel commit come scelta esplicita, non come effetto collaterale
  silenzioso.

## Da leggere prima, per simbolo

- `calculations/projection_common.py:49-52` — `eur_it`, già esistente:
  ```python
  def eur_it(amount: Decimal) -> str:
      """1234567.891 -> '1.234.567,89' (ROUND_HALF_UP, come la quantizzazione del motore)."""
      q = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
      return f"{q:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
  ```
- `importers/iv_cee_hierarchy.py:22-30` — import di testa: già `from calculations.ce_result import
  calculate_ce_result` (riga 30). Aggiungere `from calculations.projection_common import eur_it`
  non introduce una direzione di import nuova, solo un secondo simbolo dallo stesso pacchetto.
- `calculations/projection_common.py:20-22` — import di testa: **nessun import da `importers.*`**
  in tutto il file (verificato con `grep -n "^import\|^from"`). Nessun ciclo possibile.
- `calculations/intra_year_engine.py:355` (numero di riga pre-Task-1/2/3, verificare che l'import
  resti locale a una funzione dopo quei task) — **unico** punto in `calculations/` che importa da
  `importers.iv_cee_hierarchy`, ed è un import **locale a una funzione** (deferred): irrilevante
  per la freccia di questo task (va verso `iv_cee_hierarchy`, non verso `projection_common`).
- `backend/app/services/promote_service.py` — chi consuma i `warnings` di `check_quadratura` nel
  messaggio del 400: concatena `validation.warnings` così come sono, non li riformatta — la
  correzione a monte in `iv_cee_hierarchy.py` basta.
- `tests/test_quadratura_gates.py:110-123` — due test su `check_quadratura` che **non** controllano
  il formato numerico del messaggio (solo `"BILANCIO NON QUADRATO" in w`): restano verdi senza
  modifiche.
- `tests/test_messaggi_italiani.py` — file del lotto 3A Task 8. Il suo perimetro dichiarato
  (`FRASI_INGLESI`) **non** copre `importers/iv_cee_hierarchy.py`, `financial_years.py` né
  `pdf_importer.py`: fuori dal perimetro di quel task per titolo dello stesso commit (riguardava
  l'inglese-vs-italiano del *testo*, non il formato dei *numeri* dentro un testo già in italiano).
  Il test `test_il_fabbisogno_scoperto_si_dice_in_italiano_con_l_importo_all_europea` è il modello
  di stile da seguire per i test nuovi di questo task.

## Trappole note (CLAUDE.md › Invarianti e trappole › Contabilità / Quadratura)

- Diagnose, never fabricate: questo task cambia solo **come si scrive** l'importo nel messaggio,
  mai il valore diagnostico stesso (`sbilancio`, `plug`, `diff`, `gap`, `cur_imb`/`new_imb`,
  `residual` restano gli stessi `Decimal`).
- Un estrattore dichiara sempre le proprie chiavi diagnostiche, anche a zero: `eur_it`/`_it_amount`
  non cambiano quali messaggi vengono emessi, solo la loro resa testuale.
- `importers/iv_cee_hierarchy.py` è condiviso con l'app Streamlit legacy e con l'import dei PDF (CSV
  e XBRL passano dagli stessi `warnings` di `check_quadratura`): un cambiamento qui raggiunge
  **tutte** le rotte che chiamano `check_quadratura`, non solo il promote — effetto voluto.
- `backend/app/api/v1/financial_years.py` ha terminatori **misti** — le righe toccate (449-454)
  sono in una zona **LF** (verificato con uno script che legge `splitlines(keepends=True)` e
  confronta i terminatori riga per riga); nessuna riconversione necessaria lì, ma non normalizzare
  mai l'intero file. `importers/pdf_importer.py` e `importers/iv_cee_hierarchy.py` sono **LF puri**.

## Le 8 occorrenze in `importers/iv_cee_hierarchy.py` — testo prima/dopo, verificate a `0f7614a`

| # | Riga | Prima | Dopo |
|---|---|---|---|
| 1 | `:492-493` | `f"ESTRAZIONE VUOTA: attivo {att:,.2f} / passivo {pas:,.2f} ~ 0 " f"— nessun dato estratto (NON quadra)"` | `f"ESTRAZIONE VUOTA: attivo {eur_it(att)} / passivo {eur_it(pas)} ~ 0 " f"— nessun dato estratto (NON quadra)"` |
| 2 | `:495-496` | `f"BILANCIO NON QUADRATO: attivo {att:,.2f} != passivo {pas:,.2f} " f"(sbilancio {sbil:,.2f})"` | `f"BILANCIO NON QUADRATO: attivo {eur_it(att)} != passivo {eur_it(pas)} " f"(sbilancio {eur_it(sbil)})"` |
| 3 | `:507` | `f"QUADRATURA MASCHERATA: residuo {plug:,.2f} ({100 * plug / att:.1f}% "` | `f"QUADRATURA MASCHERATA: residuo {eur_it(plug)} ({100 * plug / att:.1f}% "` (il `{:.1f}%` resta: è una percentuale, non un importo) |
| 4 | `:523-524` | `f"Utile CE {utile_ce:,.2f} != sp13 {sp13:,.2f} " f"(diff {utile_ce - sp13:,.2f})"` | `f"Utile CE {eur_it(utile_ce)} != sp13 {eur_it(sp13)} " f"(diff {eur_it(utile_ce - sp13)})"` |
| 5 | `:531` | `f"di {diff:,.2f}"` (dentro `"GERARCHIA INCOERENTE: {aggregate} differisce dalla somma dettagli di {diff:,.2f}"`) | `f"di {eur_it(diff)}"` |
| 6 | `:618-619` | `f"[{label}] IV-CEE non quadrato: attivo {att:,.2f}, passivo {pas:,.2f}, " f"differenza {gap:,.2f}; nessun valore contabile è stato modificato"` | `f"[{label}] IV-CEE non quadrato: attivo {eur_it(att)}, passivo {eur_it(pas)}, " f"differenza {eur_it(gap)}; nessun valore contabile è stato modificato"` |
| 7 | `:671-672` | `f"[{label}] massa stampata NON classificata: {shortfall:,.2f} " f"(attivo classificato {att:,.2f}, passivo {pas:,.2f})"` | `f"[{label}] massa stampata NON classificata: {eur_it(shortfall)} " f"(attivo classificato {eur_it(att)}, passivo {eur_it(pas)})"` |
| 8 | `:728-729` | `f"[{label}] CE↔SP incoerente: utile CE {ce_result:,.2f}, sp13 {sp13:,.2f}, " f"differenza {gap:,.2f}; nessuna voce CE/SP è stata modificata"` | `f"[{label}] CE↔SP incoerente: utile CE {eur_it(ce_result)}, sp13 {eur_it(sp13)}, " f"differenza {eur_it(gap)}; nessuna voce CE/SP è stata modificata"` |

Nota sul #3: `{100 * plug / att:.1f}%` resta `.1f`, non `eur_it`: è una percentuale, non un
importo. Le righe 1, 6, 7 sono `logger.warning`/`logger.info` (non finiscono nel 400 di `/promote`,
ma sono lette da chi diagnostica un import — la coerenza vale anche lì).

## Perimetro — altri `:,.2f`/`:,.0f`/`:.1f` trovati fuori dai tre moduli in Change (git grep). Restano fuori, con la ragione

| File | Utente-facing? | Perché resta fuori |
|---|---|---|
| `importers/reliability.py:120,122,137,139,140,154,158,189,190,192` | No, verificato: nessun hit in `frontend/` per `critical_accounts`/`*_reason` | Diagnostica interna non renderizzata a schermo oggi |
| `importers/xbrl_parser_enhanced.py:1330-1331` | Non verificato fino in fondo, stesso pattern di `reliability.py` | Modulo diverso (XBRL), diagnostica interna |
| `importers/vision_rescue.py:416,561-562,579-580,603-605,616-617,619-620` | Non verificato fino in fondo | Ritorni `(bool, str)` interni, consumati da `pdf_importer.py` per decidere, non necessariamente propagati come testo |
| `importers/pdf_extractor_llm.py:3857,3952-3953` | No (riga 3857: prompt per l'LLM, non UI) | Categoria diversa: testo per un LLM, non output per un utente |
| `importers/situazione_contabile_parser.py:2597` | Non verificato, probabile log interno | Stesso schema di `reliability.py` |
| `backend/app/services/ai_comments_service.py` (10 righe) | No, indirettamente: alimenta il prompt di Haiku, non è mai mostrato direttamente | Input per un LLM, non output per un utente |
| `backend/app/api/v1/imports.py:59,140,417` | Sì, ma testo **già in inglese** ("File too large... 50MB") | Categoria diversa: non un messaggio italiano con un numero all'americana |

## Change

1. `importers/iv_cee_hierarchy.py` — aggiungi l'import (dopo la riga 30, subito sotto `from
   calculations.ce_result import calculate_ce_result`):
   ```python
   from calculations.projection_common import eur_it
   ```
2. Applica le 8 sostituzioni della tabella sopra — **solo** l'importo dentro `eur_it(...)`, non il
   resto della stringa f.

3. `backend/app/api/v1/financial_years.py` — aggiungi l'import (vicino agli altri import di testa,
   dopo `from decimal import Decimal`):
   ```python
   from calculations.projection_common import eur_it
   ```
   Sostituisci le tre righe (numeri verificati a `0f7614a`):
   ```python
   # PRIMA (righe 449, 451, 453-454)
       worsened.append(f"Attivo−Passivo {cur_imb:,.2f}→{new_imb:,.2f}")
       ...
       worsened.append(f"CE−SP13 {cur_ce_gap:,.2f}→{new_ce_gap:,.2f}")
       ...
           f"aggregati−dettagli {cur_hierarchy_gap:,.2f}→{new_hierarchy_gap:,.2f}"

   # DOPO
       worsened.append(f"Attivo−Passivo {eur_it(cur_imb)}→{eur_it(new_imb)}")
       ...
       worsened.append(f"CE−SP13 {eur_it(cur_ce_gap)}→{eur_it(new_ce_gap)}")
       ...
           f"aggregati−dettagli {eur_it(cur_hierarchy_gap)}→{eur_it(new_hierarchy_gap)}"
   ```

4. `importers/pdf_importer.py` — **nessun import nuovo**: usa l'helper locale già presente
   (`_it_amount`, righe 76-78). Sostituisci le tre righe (numeri verificati a `0f7614a`):
   ```python
   # PRIMA (riga 1385)
                   others = ", ".join(f"{s}={r:,.0f}" for r, _b, _c, s in candidates)
   # DOPO
                   others = ", ".join(f"{s}={_it_amount(r)}" for r, _b, _c, s in candidates)

   # PRIMA (riga 1387)
                   logger.info(f"Route C: scelto estrattore '{source}' (residuo minore "
                               f"{residual:,.0f}); candidati: {others}")
   # DOPO
                   logger.info(f"Route C: scelto estrattore '{source}' (residuo minore "
                               f"{_it_amount(residual)}); candidati: {others}")

   # PRIMA (riga 1398)
                       f"BILANCIO NON QUADRATO ({_sev}): residuo {residual:,.0f} "
   # DOPO
                       f"BILANCIO NON QUADRATO ({_sev}): residuo {_it_amount(residual)} "
   ```
   Nota di precisione: `_it_amount` produce sempre 2 decimali (`_it_amount` non ha una variante a 0
   decimali) — questi tre messaggi passano da "residuo 12.345" a "residuo 12.345,00": una
   precisione maggiore, coerente con `eur_it` (sempre 2 decimali) e con l'helper stesso già usato
   altrove in questo file, non un secondo difetto. Il `{_pct:.0f}%` della stessa riga (percentuale)
   resta invariato.

## Constraints

- Nessun cambiamento al valore diagnostico (`Decimal`) restituito da `check_quadratura`,
  `_aggregate_detail_differences`, `enforce_ce_sp_identity`, `declare_unclassified_mass`, né a
  `_bs_imbalance`/`_validation_magnitudes` in `financial_years.py`, né a `residual`/`_pct` in
  `pdf_importer.py`: solo il testo dei messaggi/log cambia.
- Nessuna modifica a `backend/app/services/promote_service.py` né ad altri chiamanti di
  `check_quadratura`: la correzione a monte in `iv_cee_hierarchy.py` basta.
- Nessuna estensione del perimetro oltre i tre file elencati: `reliability.py`,
  `xbrl_parser_enhanced.py`, `vision_rescue.py`, `pdf_extractor_llm.py`,
  `situazione_contabile_parser.py`, `ai_comments_service.py`, `imports.py` restano fuori, con la
  loro motivazione nella tabella «Perimetro» sopra.
- `importers/iv_cee_hierarchy.py` e `importers/pdf_importer.py` sono LF puri: nessuna precauzione
  di terminatori. `backend/app/api/v1/financial_years.py` ha terminatori misti, ma le righe 449-454
  sono in zona LF (verificato): nessuna riconversione necessaria, ma **non** normalizzare l'intero
  file — verifica comunque `git diff --stat` dopo l'edit.

## Ownership

`importers/iv_cee_hierarchy.py`, `backend/app/api/v1/financial_years.py`,
`importers/pdf_importer.py`, `tests/test_messaggi_italiani.py` (estensione),
`docs/import/REGOLE-IMPORT-04-QUADRATURE.md`.

## Step

- [ ] **Step 1: Base.** `cd /home/peter/DEV/budget && git rev-parse HEAD` (deve stampare
  `0f7614a...`).

- [ ] **Step 2: Test nuovo (`iv_cee_hierarchy.py`), prova rossa.** Aggiungi a
  `tests/test_messaggi_italiani.py`, in coda al file:

```python


def test_check_quadratura_dice_lo_sbilancio_all_europea():
    """Il 400 di POST /scenarios/{id}/promote (promote_service.py) concatena
    validation.warnings senza riformattarli: se check_quadratura scrive gli importi
    all'americana, il 400 li mostra all'americana (indagine-2, parte B, 2026-09-11:
    '1,470,357.32' invece di '1.470.357,32'). Sbilancio scelto identico a quello del
    collaudo: 5.509,29."""
    from decimal import Decimal as D

    from importers.iv_cee_hierarchy import check_quadratura

    bs = {"sp09_disponibilita_liquide": D("1470357.32"), "sp11_capitale": D("1464848.03")}
    q = check_quadratura(bs, None)
    assert not q.quadra
    messaggio = "; ".join(q.warnings)
    assert "5.509,29" in messaggio, messaggio
    assert "1.470.357,32" in messaggio, messaggio
    assert "1.464.848,03" in messaggio, messaggio
    assert "5,509.29" not in messaggio, messaggio
    assert "1,470,357.32" not in messaggio, messaggio


def test_save_adjustments_worsening_message_is_italian_formatted():
    """PUT /adjustments (save_adjustments, backend/app/api/v1/financial_years.py) rifiuta una
    modifica che peggiora lo sbilancio con un 400 il cui messaggio, prima di questa correzione,
    formattava gli importi all'americana -- stesso difetto di classe di
    importers/iv_cee_hierarchy.py (indagine-2 parte B), perimetro esteso dal coordinatore
    nell'assemblaggio di questo piano. Costruzione ORM diretta (sqlite in memoria), niente
    import PDF: save_adjustments si chiama come funzione semplice, senza passare per FastAPI
    (stesso pattern di tests/test_lifecycle_repeat.py, righe 184/204/248)."""
    from decimal import Decimal as D

    import pytest
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.api.v1 import financial_years
    from backend.app.schemas.adjustments import AdjustmentsUpdate
    from database.db import Base
    from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="IT AMOUNT SRL", tax_id="ITAMOUNT01", sector=1, user_id="msg-it")
    db.add(azienda); db.flush()
    fy = FinancialYear(company_id=azienda.id, year=2026, period_months=None,
                        validation_status="verified", forecastable=True)
    db.add(fy); db.flush()
    db.add(BalanceSheet(financial_year_id=fy.id, sp09_disponibilita_liquide=D("100000"),
                         sp11_capitale=D("100000")))
    db.add(IncomeStatement(financial_year_id=fy.id))
    db.commit()

    with pytest.raises(HTTPException) as esc:
        financial_years.save_adjustments(
            azienda.id, 2026,
            AdjustmentsUpdate(
                balance_sheet={"sp09_disponibilita_liquide": D("1334567.89")},
                income_statement={}, rettifiche_log=[],
            ),
            period_months=None, user_id="msg-it", db=db,
        )
    detail = esc.value.detail
    assert esc.value.status_code == 400
    assert "1.234.567,89" in detail, detail
    assert "1,234,567.89" not in detail, detail


def test_route_c_bilancio_non_quadrato_usa_it_amount():
    """Route C (situazione contabile, importers/pdf_importer.py:1385-1398) formattava il residuo
    non classificato con {:,.0f} -- stesso difetto di classe, propagato parola per parola dal
    frontend (ImportPanel.tsx). L'helper _it_amount e' gia' presente nello stesso file: questo
    test lo esercita direttamente (una prova end-to-end con un documento route-C ambiguo e'
    fuori dal perimetro pratico di questo task -- vedi la nota di onestà nel rapporto di fine
    task)."""
    from decimal import Decimal as D

    from importers.pdf_importer import _it_amount

    assert _it_amount(D("12345.6")) == "12.345,60"
    assert _it_amount(D("1234567.89")) == "1.234.567,89"


def test_nessun_formato_americano_residuo_nei_tre_moduli_del_perimetro():
    """Grep-based: nessuna delle righe toccate da questo task deve piu' contenere un formato
    americano (`:,.2f` o `:,.0f` su un importo). Non sostituisce le prove sopra (che verificano
    anche il comportamento), ma chiude il perimetro con una rete che non dipende da un fixture."""
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    for percorso in (
        "importers/iv_cee_hierarchy.py",
        "backend/app/api/v1/financial_years.py",
        "importers/pdf_importer.py",
    ):
        testo = (repo / percorso).read_text(encoding="utf-8")
        # Cerca solo negli hunk che questo task tocca, non nel resto del file: qui si assume che
        # il task NON introduca NUOVE occorrenze `:,.2f`/`:,.0f` su un importo diagnostico -- una
        # rete larga (l'intero file) e' accettabile perche' i tre moduli non hanno altri importi
        # diagnostici del genere fuori dal perimetro di questo task (verificato a grep prima di
        # scrivere questo test).
        assert not re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*:,\.(0|1|2)f\}", testo), percorso
```

- [ ] **Step 3: Prova rossa.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_messaggi_italiani.py::test_check_quadratura_dice_lo_sbilancio_all_europea \
    tests/test_messaggi_italiani.py::test_save_adjustments_worsening_message_is_italian_formatted \
    tests/test_messaggi_italiani.py::test_route_c_bilancio_non_quadrato_usa_it_amount \
    tests/test_messaggi_italiani.py::test_nessun_formato_americano_residuo_nei_tre_moduli_del_perimetro \
    -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: i primi due FALLISCONO sulle asserzioni con il formato italiano atteso (oggi il messaggio
  contiene la forma americana); il terzo (`_it_amount` diretto) **passa già oggi** (l'helper esiste
  e funziona, non è ancora richiamato dalle tre righe di route C — questo test non prova il
  Change, prova solo che l'helper è pronto: annotalo nel rapporto, non è un errore); il quarto
  FALLISCE (il grep trova ancora `:,.2f`/`:,.0f` nei tre file). Verificare che ogni fallimento sia
  sull'asserzione, non su un errore di importazione a monte.

- [ ] **Step 4: Implementa il Change** (i quattro punti sopra, sui tre file).

- [ ] **Step 5: Verde.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_messaggi_italiani.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: tutti passed (i test esistenti del lotto 3A Task 8 invariati + i 4 nuovi).

- [ ] **Step 6: Non-regressione — test che leggono `check_quadratura`/`iv_cee_hierarchy` o il
  formato americano.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_quadratura_gates.py tests/test_messaggi_italiani.py tests/test_lifecycle_repeat.py \
    tests/test_unbalanced_import.py tests/test_import_semantic_validation.py \
    tests/test_reliability_gating.py tests/test_source_detail_reconcile.py \
    -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: tutti verdi. Se uno di questi file **dovesse** risultare rosso su un'asserzione di testo
  con virgole americane, è un test che questo task non aveva nominato: fermarsi e riferirlo, non
  correggerlo silenziosamente.

- [ ] **Step 7: Suite import più ampia** (per l'ampiezza del modulo condiviso):
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest \
    tests/test_calculations.py tests/test_bkps_xbrl.py tests/test_complete_import.py tests/test_db.py \
    tests/test_xbrl_csv_full_cycle.py tests/test_enhanced_parser.py tests/test_vision_rescue.py \
    tests/test_reserves_fix.py tests/test_prod_route_c.py tests/test_standard_ivcee_parser.py \
    tests/test_fondo_amm_grafie.py tests/test_priority_mapping.py tests/test_fgpmi.py \
    tests/test_csv_import.py tests/test_xbrl_import.py tests/test_hierarchical_import.py \
    -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Nessuno di questi confronta il messaggio contro una stringa col separatore all'americana; se uno
  di questi file risultasse rosso su un'asserzione di testo, correggerlo nello stesso commit di
  questo task (stessa classe di correzione), non come allargamento di perimetro.

- [ ] **Step 8: Onestà sul limite di questo Step per `pdf_importer.py`.** Una prova end-to-end di
  route C (situazione contabile con contrapposte, candidati multipli, residuo non classificato) non
  è stata costruita in questo piano: richiede sintetizzare un documento con colonne contrapposte
  ambigue, fuori scala per un task di formattazione. Il test `test_route_c_bilancio_non_quadrato_usa_it_amount`
  (Step 2) verifica **l'helper**, non l'intero percorso; il grep dello Step 2 (quarto test) verifica
  che le righe non contengano più il pattern americano. Se il collaudo del Task 8 (verifica finale
  di questa ondata) esercita un percorso di import route C con residuo, verificare **a schermo**
  che il messaggio mostri il formato italiano — annotalo nel brief del collaudo (Task 8, percorso
  dedicato a questo task).

- [ ] **Step 9: Documentazione — `docs/import/REGOLE-IMPORT-04-QUADRATURE.md`.** In fondo alla
  sezione «5. I messaggi di rifiuto, in ordine di precedenza», dopo il paragrafo «Il controllo del
  CE viene saltato del tutto se il documento stampa una riga imposte.», aggiungi:
  ```
  Gli importi dentro questi messaggi — e quelli delle diagnostiche di quadratura più a valle
  (`check_quadratura` in `importers/iv_cee_hierarchy.py`: ESTRAZIONE VUOTA, BILANCIO NON QUADRATO,
  QUADRATURA MASCHERATA, GERARCHIA INCOERENTE, CE↔SP incoerente; il 400 della guardia Rettifiche in
  `backend/app/api/v1/financial_years.py`; gli avvisi di route C in `importers/pdf_importer.py`) —
  si scrivono in formato italiano (`eur_it`/l'helper locale `_it_amount`), mai `{x:,.2f}` alla
  americana: un messaggio in italiano con "1,470,357.32" invece di "1.470.357,32" è stato un
  difetto reale, corretto in un'ondata successiva al lotto 3A (indagine-2-promote.md, 2026-09-11).
  ```

- [ ] **Step 10: Commit.**
  ```bash
  git add importers/iv_cee_hierarchy.py backend/app/api/v1/financial_years.py \
    importers/pdf_importer.py tests/test_messaggi_italiani.py \
    docs/import/REGOLE-IMPORT-04-QUADRATURE.md
  git commit -F - <<'EOF'
  fix(import): i messaggi di quadratura dicono gli importi all'europea

  Le 8 occorrenze di {x:,.2f}/{x:.1f} in importers/iv_cee_hierarchy.py (ESTRAZIONE VUOTA, BILANCIO
  NON QUADRATO, QUADRATURA MASCHERATA, Utile CE != sp13, GERARCHIA INCOERENTE, IV-CEE non quadrato,
  massa stampata NON classificata, CE<->SP incoerente) ora passano da eur_it (gia' usato dal motore
  budget per lo stesso genere di messaggio). Il 400 di POST /scenarios/{id}/promote, che concatena
  questi warnings senza riformattarli (promote_service.py), mostrava "1,470,357.32" invece di
  "1.470.357,32" (indagine-2, parte B, 2026-09-11).

  Perimetro esteso in fase di assemblaggio a due siti user-facing gemelli con lo stesso difetto di
  classe: il 400 della guardia Rettifiche (backend/app/api/v1/financial_years.py, PUT /adjustments,
  ora con eur_it) e i tre avvisi di route C (importers/pdf_importer.py, gia' con l'helper locale
  _it_amount ma non applicato li' -- ora si', con un piccolo aumento di precisione da 0 a 2
  decimali, coerente col resto dell'app).

  Nessun ciclo di import: iv_cee_hierarchy.py importa gia' da calculations.ce_result nello stesso
  verso, e projection_common non importa mai da importers/.

  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01C8chDC8b297itUaoK1TQNW
  EOF
  ```

## Observable acceptance

I 4 test nuovi passano; nessuno degli 8+15 file di non-regressione elencati diventa rosso; il 400
di `/promote` sullo scenario del collaudo (id 21) mostra `1.470.357,32`/`1.464.848,03`/`5.509,29`,
mai la forma con virgole; il 400 di `PUT /adjustments` su una modifica che peggiora lo sbilancio
mostra gli importi in formato italiano; i tre avvisi di route C in `pdf_importer.py` usano
`_it_amount`; `grep -n ':,\.2f\|:,\.0f' importers/iv_cee_hierarchy.py backend/app/api/v1/financial_years.py importers/pdf_importer.py`
non deve restituire nulla sulle righe toccate da questo task;
`docs/import/REGOLE-IMPORT-04-QUADRATURE.md` allineato nello stesso commit.

---

### Task 6: Reti di test che non mordono

**Files:**
- Modify: `tests/test_http_full_cycle.py` (una riga, sotto-task A)
- Modify: `tests/test_parita_riepilogo.py` (un test nuovo, sotto-task D)
- Modify: `tests/test_intra_year_override_cassa.py` (fixture estesa + un test nuovo, sotto-task F-i)

**Interfaces:**
- Consumes: nessuna interfaccia dai Task 1-5 — tre file di test indipendenti. Il sotto-task F-i
  legge (sola lettura, nessuna modifica) `calculations/intra_year_engine.py:591-600`
  (`generate_projection`, il blocco del ricalcolo cassa incondizionato) e
  `calculations/forecast_engine.py:1970-2044` (`_apply_sp_overrides`) — **entrambe le zone sono
  fuori dalle aree toccate dai Task 1/2/3** (che lavorano dentro `_project_balance_sheet`/
  `_project_balance_sheet_annualized`, non dentro `generate_projection`): verificato che i Task 1 e
  2 non inseriscono nulla prima della riga 1007 del file (dove le loro patch iniziano), quindi le
  righe 591-600 restano a quel numero anche dopo i Task 1-3. Nessuna interferenza attesa.
- Produces: nessuna — questo task non tocca codice di produzione (per costruzione, vedi «Perché due
  task, non uno» sotto): irrobustisce solo reti di test esistenti.

**Perché due task, non uno (M diventa Task 6 e Task 7 di questo piano).** L'elenco verificato del
coordinatore si divide da solo in due perimetri disgiunti: A, D, F-i (questo task) **non toccano
codice di produzione** — irrobustiscono reti di test; B, C, E (Task 7) toccano `calculations/`,
`backend/app/services/` e `backend/app/schemas/`, con i loro test. Un solo task avrebbe mescolato
"verificare che una rete morda" con "cambiare che cosa il motore accetta": due rischi di natura
diversa. **F-ii non entra in questo piano**: misurato durante la stesura della bozza che
l'aggiunta proposta alla griglia del banco (`scripts/parita_motore.py`) **non** innesca in modo
affidabile il residuo che dovrebbe provare (0 anni su 4 col seme di default), mentre il test
dedicato `tests/test_forecast_residuo_neutro.py::test_con_tutti_i_debiti_operativi_pianificati_...`
certifica già il contratto in modo deterministico ed è verde. Ruling del coordinatore: **si chiude
senza modifiche**, riportando questa misura come prova — vedi «Fuori perimetro» in fondo al piano.

---

### A — `test_http_full_cycle.py:214`, il doppio `abs` non vede un'inversione di segno

**Target.** `assert abs(abs(sbilancio) - gap) < Decimal("0.01")` è cieco a un'inversione di segno di
`sbilancio`: `gap` è sempre positivo per costruzione, ma il doppio `abs` rende il confronto
invariante rispetto al segno di `sbilancio`. Il gemello dichiarato dal commento del coordinatore
(`tests/test_standard_ivcee_parser.py:822`) usa il confronto diretto, senza il secondo `abs`, ed è
verde.

**Da leggere prima, per simbolo.**
- `tests/test_http_full_cycle.py:214` — oggi: `assert abs(abs(sbilancio) - gap) < Decimal("0.01")`.
  `sbilancio = Decimal(str(fb["total_assets"])) - Decimal(str(total_liabilities))` (riga 211), `gap`
  è il `Decimal` di `unfunded_financing_requirement["amount"]` — sempre positivo per costruzione
  (`amount: str(-cassa)` o `str(funding_gap)`, sempre `abs(...)` o un residuo negato in
  `calculations/intra_year_engine.py`).
- `tests/test_standard_ivcee_parser.py:822` — dentro
  `test_full_workflow_matrix_partial_gap_equals_declared_amount`: `assert abs(gap - sbilancio) <
  Decimal("0.01")`. Confronto diretto, senza il secondo `abs`. Verde oggi: **3 passed**.
- Misurato con una sonda: sullo scenario reale del test, `sbilancio = 898943.51`, `gap =
  898943.51` — segno concorde, il confronto diretto passa quanto quello a doppio `abs`. Un'inversione
  di segno di `sbilancio` (mutazione: `sbilancio_mutato = -sbilancio`) dà: doppio `abs` (oggi)
  `abs(abs(-898943.51) - 898943.51) = 0 < 0.01` → **passa**, cieco; diretto (proposto)
  `abs(-898943.51 - 898943.51) = 1797887.02 < 0.01` → **False**, lo coglie.

**Change.** `tests/test_http_full_cycle.py`, riga 214:
```python
# PRIMA
    assert abs(abs(sbilancio) - gap) < Decimal("0.01")
# DOPO
    assert abs(sbilancio - gap) < Decimal("0.01")
```
Nessun altro cambiamento: `gap` e `sbilancio` restano quelli di oggi, solo la forma del confronto si
allinea al gemello.

**Constraints.** Il valore misurato (898943.51) non cambia: la correzione è solo alla forma del
confronto, non al calcolo che produce `sbilancio`/`gap`.

**Ownership.** `tests/test_http_full_cycle.py`.

- [ ] **Step A1.** `cd /home/peter/DEV/budget && git rev-parse HEAD` (deve stampare `0f7614a...`).
- [ ] **Step A2 — prova che il difetto è reale, non solo teorico.** Applica temporaneamente, su una
  COPIA, la mutazione «segno invertito» subito prima dell'assert:
  ```bash
  cp tests/test_http_full_cycle.py tests/_probe_sign_A.py
  python3 -c "
  import re
  p = 'tests/_probe_sign_A.py'
  s = open(p).read()
  s = s.replace('    sbilancio = Decimal(str(fb[\"total_assets\"])) - Decimal(str(total_liabilities))',
                '    sbilancio = -(Decimal(str(fb[\"total_assets\"])) - Decimal(str(total_liabilities)))')
  open(p, 'w').write(s)
  "
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/_probe_sign_A.py::test_http_full_cycle_import_to_analysis -q -p no:cacheprovider -W ignore::DeprecationWarning
  rm tests/_probe_sign_A.py
  ```
  Atteso: **passa** ancora (il doppio `abs` del test originale è cieco all'inversione) — questa è
  la "prova rossa" del difetto di RETE, non del codice di produzione. Rimuovi
  `tests/_probe_sign_A.py` subito dopo (mai committarlo).
- [ ] **Step A3.** Applica il Change (riga 214).
- [ ] **Step A4 — verde sul comportamento reale.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_http_full_cycle.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **18 passed** (stesso numero di oggi: il Change non cambia nessun valore, solo la forma
  del confronto, e sul codice reale `sbilancio`/`gap` hanno segno concorde).
- [ ] **Step A5 — ripeti la Step A2 sul file corretto**, per mostrare che ora coglie l'inversione:
  ripeti la stessa mutazione sul file con il Change applicato → atteso **FAIL** su
  `assert abs(sbilancio - gap) < Decimal("0.01")`. Rimuovi di nuovo la copia sonda.

**Observable acceptance.** `tests/test_http_full_cycle.py` verde (18 passed) con il confronto
diretto; la sonda d'inversione di segno (Step A5) fallisce, a differenza di prima (Step A2).

---

### D — `parita_riepilogo.py`, il caso "nessun pattern ammette niente" non è fissato

**Target.** Con `--attese` (anche vuoto), ogni divergenza il cui `f"{scenario}|{campo}"` non
combacia con NESSUN pattern finisce in `fuori`; l'uscita è 1 se `fuori` non è vuoto. Verificato a
mano: comportamento corretto, ma nessun test esistente lo esercita.

**Da leggere prima, per simbolo.**
- `scripts/parita_riepilogo.py` — con `--attese` (anche vuoto: `nargs="*"`, `default=None` solo se
  l'opzione è del tutto assente).
- `tests/test_parita_riepilogo.py:36-39` — tre test esistono, nessuno passa `--attese` con una
  lista che non ammette nulla.

**Change.** Nessuno a `scripts/parita_riepilogo.py`: il comportamento è già quello dichiarato,
manca solo il test.

**Ownership.** `tests/test_parita_riepilogo.py`.

- [ ] **Step D1.** `git rev-parse HEAD` (`0f7614a...`).
- [ ] **Step D2 — prova rossa.** Aggiungi in coda a `tests/test_parita_riepilogo.py`:
  ```python
  def test_nessun_pattern_ammette_nulla_tutte_fuori_uscita_uno(tmp_path):
      esito = _esegui(_json(tmp_path), "--attese")
      assert esito.returncode == 1, esito.stdout
      assert "fuori dalle attese: 3" in esito.stdout
      assert "[base__finanziamento · 2028] balance_sheet.sp17a_debiti_banche_lungo: 0,00 -> 10,00" in esito.stdout
      assert "[banca__finanziamento · 2028] balance_sheet.sp17a_debiti_banche_lungo: 1,00 -> 2,00" in esito.stdout
      assert "[base__crescita · 2027] income_statement.ce15_oneri_finanziari: 1,00 -> 2,00" in esito.stdout
  ```
  Esegui:
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_parita_riepilogo.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso PRIMA di questo Step: 3 passed (il test è nuovo, non c'è nulla da rompere — la "prova
  rossa" qui è che lo script **non aveva alcun test** su questo ramo, non un'asserzione che
  fallisce). Aggiungendo il test si passa direttamente a verde.
- [ ] **Step D3 — verde.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_parita_riepilogo.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **4 passed**.

**Observable acceptance.** `tests/test_parita_riepilogo.py` a 4 test, il caso limite ("nessun
pattern ammette nulla") fissato con l'uscita esatta (1, "fuori dalle attese: 3", le tre righe).

---

### F-i — Il test nuovo del Task 11 (lotto 3A) non protegge la propria estensione

**Target.** `tests/test_intra_year_override_cassa.py` (Task 11 del lotto 3A, `recompute_cash` reso
incondizionato in `generate_projection`) oggi passa anche se si ripristina il vecchio
`recompute_cash=not ha_errori`: i suoi tre scenari non hanno mai una diagnostica `error` PRIMA
dell'override, quindi `ha_errori` era già `False` col codice vecchio. La rete regge solo grazie a
`test_standard_ivcee_parser.py` (non nel suo ownership).

**Da leggere prima, per simbolo.**
- `calculations/intra_year_engine.py:591-600` — il blocco che il Task 11 (lotto 3A) ha reso
  incondizionato:
  ```python
  self._diagnostics = [
      diagnostic for diagnostic in self._diagnostics
      if diagnostic.get('code') != 'unfunded_financing_requirement'
  ]
  projected_bs = ForecastEngine._normalize_balance_sheet_cents(
      projected_bs, recompute_cash=True
  )
  ```
- `calculations/forecast_engine.py:1970-2044` (`_apply_sp_overrides`) — **scoperta della verifica,
  non ipotesi**: per QUALUNQUE override diverso da `sp09_disponibilita_liquide`,
  `_apply_sp_overrides` **già** ricalcola la cassa da sé, indipendentemente da `recompute_cash`.
  Misurato su copie isolate: un override su `sp11_capitale` da solo dà la STESSA cassa finale in
  entrambe le versioni (2955,00), perché `_apply_sp_overrides` la corregge comunque PRIMA che
  `recompute_cash` conti. Il Task 11 protegge quindi un caso più stretto: un override che tocca
  **anche** `sp09_disponibilita_liquide` (l'unico campo escluso dal ricalcolo di
  `_apply_sp_overrides`) **e** una diagnostica `error` già presente PRIMA del ricalcolo finale.
- `calculations/intra_year_engine.py:1791-1802` (`_distribute_sp16`, **non toccata** dai Task 1/2 di
  questo piano: quelli introducono `_distribute_sp16_operativo` accanto a `_distribute_sp16`, senza
  rimuoverla — resta usata dal ramo annualizzato) — la diagnostica `error`
  `missing_short_debt_breakdown` (usata per la sonda) si genera quando l'anno di RIFERIMENTO non ha
  alcun dettaglio `sp16a..g` mentre il totale da distribuire non è zero. **Non basta** mettere
  l'aggregato `sp16_debiti_breve` sul solo anno parziale senza un suo dettaglio coerente:
  `_validate_forecast_source` (`always_blocking = {"sp16_debiti_breve", "sp17_debiti_lungo"}`)
  rifiuta un anno la cui PROPRIA aggregato/dettaglio non coincide. La costruzione che funziona:
  l'anno parziale ha SIA l'aggregato SIA il proprio dettaglio coerente, e SOLO l'anno di
  riferimento resta senza alcun dettaglio `sp16a..g`.
- Numeri misurati (stessa sonda a due moduli): fixture `_proietta` esistente (2024 senza mesi,
  utile 0; 2025 a 9 mesi, utile 100), con l'anno 2025 esteso da `sp16_debiti_breve=400,
  sp16d_debiti_fornitori_breve=400, sp09_disponibilita_liquide=1500` e override
  `{"sp11_capitale": 2000, "sp09_disponibilita_liquide": 1}`:
  - codice attuale (`recompute_cash=True` incondizionato): cassa persistita **2955,00**;
  - mutazione A (`ha_errori` ripristinato, `recompute_cash=not ha_errori`): `ha_errori` è **True**
    (la diagnostica `missing_short_debt_breakdown` sopravvive alla ripulitura, che filtra solo
    `unfunded_financing_requirement`) → `recompute_cash=False` → cassa persistita **1,00**, il
    valore letterale dell'override, foglio sbilanciato di 2.954,00 — esattamente il difetto
    storico che il Task 11 ha chiuso.

**Change.** Nessuno a `calculations/intra_year_engine.py` (il codice è già quello giusto): solo un
test nuovo.

**Ownership.** `tests/test_intra_year_override_cassa.py`.

- [ ] **Step F-i.1.** `git rev-parse HEAD` (`0f7614a...`).
- [ ] **Step F-i.2 — estendi la fixture** (retrocompatibile: il default riproduce il comportamento
  di oggi per i tre test esistenti):
  ```python
  def _proietta(override, rompi_ripartizione_breve=False):
      engine = create_engine("sqlite:///:memory:")
      Base.metadata.create_all(engine)
      db = sessionmaker(bind=engine)()
      azienda = Company(name="Override infra", tax_id="OVERRIDE-INFRA", sector=1)
      db.add(azienda)
      db.flush()
      for anno, mesi, utile in ((2024, None, D("0")), (2025, 9, D("100"))):
          fy = FinancialYear(company_id=azienda.id, year=anno, period_months=mesi, validation_status="verified", forecastable=True)
          db.add(fy)
          db.flush()
          cassa = D("1000") + utile
          kwargs = dict(financial_year_id=fy.id, sp11_capitale=D("1000"), sp13_utile_perdita=utile)
          if rompi_ripartizione_breve and anno == 2025:
              # Il parziale ha un sp16 aggregato con un dettaglio coerente CON SE STESSO
              # (sp16d = 400 = sp16_debiti_breve): non e' questo che rompe la ripartizione.
              # E' l'anno di riferimento (2024, sotto, senza alcun dettaglio sp16a..g) a
              # lasciare `_distribute_sp16` senza una proporzione da applicare
              # (calculations/intra_year_engine.py:1791-1802): la diagnostica
              # `missing_short_debt_breakdown` (severita' 'error') nasce PRIMA di ogni
              # override, indipendente da esso.
              kwargs["sp16_debiti_breve"] = D("400")
              kwargs["sp16d_debiti_fornitori_breve"] = D("400")
              cassa += D("400")
          kwargs["sp09_disponibilita_liquide"] = cassa
          db.add(BalanceSheet(**kwargs))
          db.add(IncomeStatement(financial_year_id=fy.id, ce01_ricavi_vendite=utile))
      scenario = BudgetScenario(company_id=azienda.id, name="infra", base_year=2024, scenario_type="infrannuale", period_months=9)
      db.add(scenario)
      db.flush()
      db.add(BudgetAssumptions(scenario_id=scenario.id, forecast_year=2025, tax_rate=D("0"),
                               fixed_materials_percentage=D("0"), fixed_services_percentage=D("0"),
                               ce01_override=D("555"), sp_overrides=override))
      db.commit()
      esito = IntraYearEngine(db).generate_projection(scenario.id)
      sp = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario.id).one().balance_sheet
      fabbisogni = [d for d in esito["diagnostics"] if d["code"] == "unfunded_financing_requirement"]
      return db, scenario, sp.sp09_disponibilita_liquide, fabbisogni
  ```
  (Nota: `db.add(BalanceSheet(**kwargs))` sostituisce la costruzione inline di oggi — verificare che
  nessun altro campo della vecchia riga si perda nel merge, `sp13_utile_perdita`/`sp11_capitale`
  compresi.)
- [ ] **Step F-i.3 — il test nuovo**, in coda al file:
  ```python
  def test_recompute_cash_gira_anche_con_una_diagnostica_derrore_gia_presente():
      """Task 11 (lotto 3A): il terzo passo del ricalcolo cassa in `generate_projection`
      (`_normalize_balance_sheet_cents(recompute_cash=True)`) deve girare SEMPRE, non solo in
      assenza di diagnostiche d'errore preesistenti. Prima del fix era condizionato a
      `not ha_errori`: con una diagnostica d'errore gia' presente (qui
      `missing_short_debt_breakdown`, innescata da un anno di riferimento senza dettaglio sp16
      mentre il parziale ne dichiara uno coerente con se stesso) e un override che tocca ANCHE
      `sp09` (l'unico campo che esclude il ricalcolo automatico gia' interno a
      `_apply_sp_overrides`), la vecchia condizione lasciava la cassa congelata al valore
      letterale dell'override (1,00), sbilanciando il foglio persistito di 2.954,00. La rete
      esistente in questo file non lo vedeva: nei suoi tre scenari nessuna diagnostica d'errore
      precede l'override, quindi `ha_errori` era gia' `False` anche col codice vecchio."""
      _db, _scenario, cassa, fabbisogni = _proietta(
          {"sp11_capitale": 2000, "sp09_disponibilita_liquide": 1}, rompi_ripartizione_breve=True,
      )
      assert cassa == D("2955.00"), f"cassa persistita {cassa}: il ricalcolo dopo l'override non e' girato"
      assert fabbisogni == []
  ```
- [ ] **Step F-i.4 — verde sul codice attuale.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_intra_year_override_cassa.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **4 passed** (i 3 di prima, invariati, più il nuovo).
- [ ] **Step F-i.5 — prova rossa via mutazione (dimostra che la rete ora morde).** Su una COPIA
  del solo file di produzione (mai sul worktree — `cp calculations/intra_year_engine.py
  /tmp/probe_ha_errori.py`, patch delle sole righe 591-600 per ripristinare
  `ha_errori = any(d.get('severity') == 'error' for d in self._diagnostics)` e
  `recompute_cash=not ha_errori`), sostituisci temporaneamente
  `calculations/intra_year_engine.py` con la copia mutata (`cp /tmp/probe_ha_errori.py
  calculations/intra_year_engine.py`), lancia:
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_intra_year_override_cassa.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **1 failed** (solo il test nuovo, su `cassa == D("2955.00")`, con cassa reale `1.00`) —
  **3 passed** (gli altri tre restano ciechi, comportamento già noto e non è compito di questo
  task cambiarlo). Poi **ripristina immediatamente** `git checkout -- calculations/intra_year_engine.py`
  e riverifica **4 passed**. **Nota per questo piano**: se i Task 1/2/3 sono già stati applicati
  quando si esegue questo Step, la mutazione va costruita sul file **come lo lasciano** quei task
  (righe 591-600 dovrebbero comunque restare al loro numero, verificato: nessuna delle patch dei
  Task 1/2/3 inserisce codice prima della riga 1007 del file originale) — verifica comunque con
  `grep -n "recompute_cash=True"` prima di patchare, invece di fidarti ciecamente del numero di riga.
- [ ] **Step F-i.6 — non regressione sul resto del motore infrannuale.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_intra_year_plug_negativo.py tests/test_intra_year_semantics.py tests/test_intra_year_end_to_end_periods.py tests/test_intra_year_debito_bancario.py tests/test_intra_year_imposte.py tests/test_http_full_cycle.py tests/test_standard_ivcee_parser.py tests/test_intra_year_crediti_commerciali.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: tutti verdi, nessun numero diverso da oggi (il Change è solo un test nuovo, nessun codice
  di produzione toccato).

**Observable acceptance.** `tests/test_intra_year_override_cassa.py` a 4 test verdi; la mutazione
temporanea dello Step F-i.5 fa fallire SOLO il test nuovo (dimostrazione che la rete ora copre
l'estensione del Task 11 del lotto 3A da sola, senza dipendere da `test_standard_ivcee_parser.py`).

---

### Task 7: Codice morto, alias e schemi del bulk

**Files:**
- Modify: `calculations/intra_year_engine.py` (sotto-task B — area **diversa** da quella dei Task
  1/2/3, vedi «Interfaces»)
- Modify: `calculations/forecast_engine.py` (sotto-task C — solo alias/commenti, nessuna riga di
  calcolo)
- Modify: `tests/test_projection_common_debito_bancario.py` (sotto-task C)
- Modify: `backend/app/services/assumptions_service.py` (sotto-task E)
- Modify: `backend/app/schemas/budget.py` (sotto-task E)
- Modify: `tests/test_bulk_tipizzato.py` (sotto-task E)

**Interfaces:**
- Consumes: nessuna interfaccia diretta dai Task 1-5. **Attenzione al file condiviso**: il
  sotto-task B tocca `calculations/intra_year_engine.py`, lo **stesso file** dei Task 1/2/3, ma
  un'area completamente diversa (`_financing_contracts`, righe 236-253 e le sue tre chiamate — non
  dentro `_project_balance_sheet`/`_project_balance_sheet_annualized`). Se questo task viene
  eseguito **dopo** i Task 1/2/3 (ordine consigliato, dato che quei tre sono in serie e più
  prioritari), **i numeri di riga citati sotto sono quelli di `0f7614a` nudo e vanno rilocalizzati**:
  la definizione (riga 236) e le prime due chiamate (righe 802, 937) restano invariate — nessuna
  patch dei Task 1/2/3 inserisce codice prima della riga 1007 del file originale, verificato — ma
  la **terza chiamata (riga 1615 su `0f7614a`)** cade dentro l'intervallo che i Task 1 e 2
  riscrivono (le loro patch inseriscono complessivamente ≈310 righe nette fra le righe 1007 e
  1850): quella riga si è spostata. **Localizza tutti e tre i siti con `git grep -n
  "_financing_contracts("` invece di fidarti dei numeri di riga**, in qualunque ordine questo task
  giri rispetto ai Task 1/2/3.
- Produces: nessuna interfaccia per altri task di questa ondata.

**Perché due task, non uno** — vedi Task 6, stessa spiegazione (A/D/F-i non toccano codice di
produzione, B/C/E sì). **G non ha un task**: tre voci già verificate chiuse sul codice (non sul
verbale) — vedi «Fuori perimetro» in fondo al piano.

---

### B — `_financing_contracts(assumption, include_opening=True)`: il parametro non ha chiamanti

**Da leggere prima, per simbolo.**
- `calculations/intra_year_engine.py:236-253` (numero di riga di `0f7614a` — **rilocalizza con grep
  se i Task 1/2/3 sono già stati applicati**, vedi «Interfaces») — la funzione, col parametro:
  ```python
  def _financing_contracts(assumption, include_opening=True):
      """Normalize legacy and detailed financing inputs for the shared kernel."""
      year = int(getattr(assumption, 'forecast_year', 0) or 0)
      loans = []
      legacy_amount = Decimal(str(getattr(assumption, 'financing_amount', None) or 0))
      legacy_duration = Decimal(str(getattr(assumption, 'financing_duration_years', None) or 0))
      if legacy_amount > 0 and legacy_duration > 0:
          loans.append({
              'year': year,
              'amount': legacy_amount,
              'duration': legacy_duration,
              'rate': Decimal(str(getattr(assumption, 'financing_interest_rate', None) or 0)) / Decimal('100'),
          })
      for loan in (getattr(assumption, 'financing_loans', None) or []):
          for contract in contratti_da_riga_finanziamento(loan, year):
              if not include_opening and e_contratto_pregresso(contract):
                  continue
              loans.append(contract)
      return loans
  ```
- `git grep -n "_financing_contracts"` sull'intero repo: **quattro** occorrenze totali — la
  definizione e tre chiamate, **tutte** con `include_opening=True`. Nessun test, nessun altro
  modulo lo chiama con `False` o senza l'argomento. Il ramo `if not include_opening and
  e_contratto_pregresso(contract): continue` non esegue mai.
- `e_contratto_pregresso` resta necessario altrove nello stesso file (`pregressi = [c for c in
  contracts if e_contratto_pregresso(c)]`): l'import da `calculations.projection_common` non si
  tocca.

**Change.** `calculations/intra_year_engine.py`:
1. Firma e corpo:
   ```python
   # PRIMA
   def _financing_contracts(assumption, include_opening=True):
       ...
           for contract in contratti_da_riga_finanziamento(loan, year):
               if not include_opening and e_contratto_pregresso(contract):
                   continue
               loans.append(contract)
       return loans

   # DOPO
   def _financing_contracts(assumption):
       """Normalize legacy and detailed financing inputs for the shared kernel."""
       year = int(getattr(assumption, 'forecast_year', 0) or 0)
       loans = []
       legacy_amount = Decimal(str(getattr(assumption, 'financing_amount', None) or 0))
       legacy_duration = Decimal(str(getattr(assumption, 'financing_duration_years', None) or 0))
       if legacy_amount > 0 and legacy_duration > 0:
           loans.append({
               'year': year,
               'amount': legacy_amount,
               'duration': legacy_duration,
               'rate': Decimal(str(getattr(assumption, 'financing_interest_rate', None) or 0)) / Decimal('100'),
           })
       for loan in (getattr(assumption, 'financing_loans', None) or []):
           for contract in contratti_da_riga_finanziamento(loan, year):
               loans.append(contract)
       return loans
   ```
2. Le tre chiamate (righe 802, 937, 1615 su `0f7614a` — rilocalizza con grep):
   `_financing_contracts(assumption, include_opening=True)` → `_financing_contracts(assumption)`.

**Constraints.** Nessun cambiamento di comportamento: il parametro non aveva mai un valore diverso
da `True` in produzione o nei test, quindi il ramo tolto non eseguiva mai. Nessun test da scrivere
per "coprire" un comportamento che non esiste più: la prova è che la suite resta identica.

**Ownership.** `calculations/intra_year_engine.py`.

- [ ] **Step B1.** `git rev-parse HEAD`.
- [ ] **Step B2 — baseline.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_intra_year_*.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Annota il numero di test verdi PRIMA del Change (nessuna prova rossa attesa: è una rimozione di
  codice morto — la prova è l'identità del numero di test verdi prima/dopo).
- [ ] **Step B3.** Localizza i tre siti con `git grep -n "_financing_contracts("` e applica il
  Change.
- [ ] **Step B4 — stesso numero, invariato.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_intra_year_*.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **stesso numero** dello Step B2, nessun fallimento nuovo.
- [ ] **Step B5 — banco di parità del motore infrannuale**, se lo script copre l'infrannuale
  (verificato: il banco `scripts/parita_motore.py` usa solo `ForecastEngine`/`compute_forecast`,
  scenario `scenario_type="budget"` — questo step si salta, annotalo nel rapporto).

**Observable acceptance.** `_financing_contracts` a un solo parametro; `git grep -n
"include_opening"` non restituisce nulla; suite `test_intra_year_*.py` invariata nel numero di
test verdi.

---

### C — Alias del debito bancario in `forecast_engine.py`: uno morto, tre vivi

**Da leggere prima, per simbolo.**
- `calculations/forecast_engine.py:486-491`, oggi:
  ```python
  # Le regole del debito bancario vivono in `projection_common` (lotto 3A, Task 3): questi nomi restano per
  # chi li importa dal motore budget (test e helper del Task 2).
  _ha_residuo_pregresso = e_contratto_pregresso
  _e_contratto_pregresso = e_contratto_pregresso
  _residuo_prestiti_nuovi = residuo_prestiti_nuovi
  _quota_breve_prestiti_nuovi = quota_breve_prestiti_nuovi
  ```
  Il commento è impreciso per TRE dei quattro nomi: `git grep -n` mostra che
  `_ha_residuo_pregresso`, `_e_contratto_pregresso`, `_quota_breve_prestiti_nuovi` sono usati
  **dentro lo stesso file** (`_contratti_dell_anno`, `assemble_financing`/
  `_calculate_balance_sheet`) — non "restano solo per chi li importa dai test", sono le
  abbreviazioni interne che il motore usa ogni giorno. Toglierli richiederebbe rinominare sei siti
  di chiamata per un guadagno nullo: **restano**, ma il commento che li introduce va corretto.
- **`_residuo_prestiti_nuovi` è diverso**: `git grep -n "_residuo_prestiti_nuovi"` sull'intero repo
  restituisce **solo** la sua definizione e una riga di test
  (`tests/test_projection_common_debito_bancario.py:59`, un confronto di identità). **Zero
  chiamanti dentro `forecast_engine.py`**: il kernel `residuo_prestiti_nuovi` (importato da
  `projection_common`) è citato in un docstring (`_residuo_contratto`) solo come paragone
  concettuale, mai chiamato — la logica equivalente è reimplementata localmente in
  `_residuo_contratto` con `new_financing_schedule`. L'alias è morto.
- `tests/test_projection_common_debito_bancario.py:1-4` (docstring) e riga 59: citano
  `forecast_engine._residuo_prestiti_nuovi` come se fosse un fatto del codice — dopo la rimozione
  sarebbe un riferimento a un nome che non esiste più.

**Change.**

1. `calculations/forecast_engine.py`, righe 486-491:
   ```python
   # PRIMA
   # Le regole del debito bancario vivono in `projection_common` (lotto 3A, Task 3): questi nomi restano per
   # chi li importa dal motore budget (test e helper del Task 2).
   _ha_residuo_pregresso = e_contratto_pregresso
   _e_contratto_pregresso = e_contratto_pregresso
   _residuo_prestiti_nuovi = residuo_prestiti_nuovi
   _quota_breve_prestiti_nuovi = quota_breve_prestiti_nuovi

   # DOPO
   # Le regole del debito bancario vivono in `projection_common` (lotto 3A, Task 3). Questi TRE nomi
   # restano perche' il corpo di QUESTO modulo li usa ancora come proprie abbreviazioni interne, non
   # solo chi li importa dai test: `_ha_residuo_pregresso`/`_e_contratto_pregresso` in
   # `_contratti_dell_anno`, `assemble_financing`, `_calculate_balance_sheet`;
   # `_quota_breve_prestiti_nuovi` in `_contratti_dell_anno` e `_calculate_balance_sheet`. Un quarto
   # alias, `_residuo_prestiti_nuovi`, non aveva invece alcun chiamante qui dentro (il kernel
   # equivalente e' reimplementato localmente da `_residuo_contratto`): rimosso -- il test che ne
   # confrontava l'identita' importa ora `projection_common.residuo_prestiti_nuovi` direttamente.
   _ha_residuo_pregresso = e_contratto_pregresso
   _e_contratto_pregresso = e_contratto_pregresso
   _quota_breve_prestiti_nuovi = quota_breve_prestiti_nuovi
   ```

2. `tests/test_projection_common_debito_bancario.py`, docstring di testa (righe 1-4):
   ```python
   # PRIMA
   """Le tre regole del debito bancario vivono in `projection_common` e il motore budget le usa (lotto 3A, Task 3).

   Numeri: la catena del prestito 100.000,38 / 4 anni / 4,35% erogato nel 2027, misurata sullo snapshot `452112d`
   con `forecast_engine._residuo_prestiti_nuovi` e `_quota_breve_prestiti_nuovi`.
   """

   # DOPO
   """Le tre regole del debito bancario vivono in `projection_common` e il motore budget le usa (lotto 3A, Task 3).

   Numeri: la catena del prestito 100.000,38 / 4 anni / 4,35% erogato nel 2027, misurata sullo snapshot `452112d`
   con `projection_common.residuo_prestiti_nuovi` e `forecast_engine._quota_breve_prestiti_nuovi` (il solo dei
   due che il motore usa ancora come proprio alias interno -- `_residuo_prestiti_nuovi` era un alias morto,
   rimosso in questo task).
   """
   ```

3. Stesso file, righe 58-61 (`test_il_motore_budget_usa_le_funzioni_condivise_non_una_copia`):
   ```python
   # PRIMA
   def test_il_motore_budget_usa_le_funzioni_condivise_non_una_copia():
       assert motore_budget._residuo_prestiti_nuovi is getattr(comune, "residuo_prestiti_nuovi", None)
       assert motore_budget._quota_breve_prestiti_nuovi is getattr(comune, "quota_breve_prestiti_nuovi", None)
       assert motore_budget._e_contratto_pregresso is getattr(comune, "e_contratto_pregresso", None)

   # DOPO
   def test_il_motore_budget_usa_le_funzioni_condivise_non_una_copia():
       # `_residuo_prestiti_nuovi` non e' piu' un alias di forecast_engine (Task 7/C, rimosso: zero
       # chiamanti interni). Il kernel si testa qui direttamente, non via un alias del motore budget.
       assert callable(getattr(comune, "residuo_prestiti_nuovi", None))
       assert motore_budget._quota_breve_prestiti_nuovi is getattr(comune, "quota_breve_prestiti_nuovi", None)
       assert motore_budget._e_contratto_pregresso is getattr(comune, "e_contratto_pregresso", None)
   ```

**Constraints.** `_ha_residuo_pregresso`, `_e_contratto_pregresso`, `_quota_breve_prestiti_nuovi`
NON si toccano (sono vivi, usati internamente): questo task non li rinomina né li rimuove. Solo
`_residuo_prestiti_nuovi` si rimuove, ed è l'unico dei quattro senza chiamanti di produzione.
**Il motore budget non cambia comportamento**: solo alias/commenti, nessuna riga di calcolo — il
banco di parità resta a 0 divergenze per costruzione (nessuna riga di `_calculate_balance_sheet`,
`assemble_financing` o `compute_forecast` cambia).

**Ownership.** `calculations/forecast_engine.py`, `tests/test_projection_common_debito_bancario.py`.

- [ ] **Step C1.** `git rev-parse HEAD` (`0f7614a...`).
- [ ] **Step C2 — baseline.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_projection_common_debito_bancario.py tests/test_forecast_prestito_quota_breve.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **22 passed** (misurato su `0f7614a`).
- [ ] **Step C3.** Applica il Change (i tre punti).
- [ ] **Step C4 — verde.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_projection_common_debito_bancario.py tests/test_forecast_prestito_quota_breve.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **22 passed** (stesso numero: si toglie un'asserzione e se ne aggiungono due equivalenti
  nello stesso test, il conteggio dei test — non delle asserzioni — non cambia).
- [ ] **Step C5 — nessun altro chiamante dell'alias morto.**
  ```bash
  git grep -n "_residuo_prestiti_nuovi"
  ```
  Atteso: nessun risultato.
- [ ] **Step C6 — non regressione più ampia.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_forecast_*.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: nessuna regressione (ri-annotare il numero reale al momento dell'esecuzione).
- [ ] **Step C7 — banco di parità (controllo negativo, il motore budget non cambia).**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python scripts/parita_motore.py 0f7614a --anni 4 --controllo-negativo
  ```
  Atteso: 0 divergenze.

**Observable acceptance.** `git grep -n "_residuo_prestiti_nuovi"` vuoto; le due suite mirate
restano a 22 passed; nessun'altra regressione su `test_forecast_*.py`; banco di parità a 0
divergenze.

---

### E — Schema del bulk: `sp_indexing` con `null` annidato, e un campo sconosciuto accettato in silenzio

**Da leggere prima, per simbolo.**
- `backend/app/services/assumptions_service.py:122-134` (`_senza_null`) — pulisce i `null` di primo
  livello e dentro `financing_loans`, `tax_temporary_differences`, `sp_overrides`, `pregresso`.
  **Non tocca `sp_indexing`.**
- `backend/app/schemas/budget.py:96` — `SpIndexingDriver = Literal["ricavi", "acquisti",
  "personale"]`; `sp_indexing: Optional[Dict[str, SpIndexingDriver]]`: il VALORE di ogni chiave
  deve essere una di quelle tre stringhe, `None` non è ammesso dal tipo.
- **Misurato**: `BudgetAssumptionsBulkRow(**_senza_null({"scenario_id": 1, "forecast_year": 2026,
  "sp_indexing": {"sp16g": None, "sp17g": "ricavi"}}))` alza `ValidationError: sp_indexing.sp16g
  Input should be 'ricavi', 'acquisti' or 'personale' [type=literal_error, input_value=None, ...]`
  — un 422 sull'intero bulk, anche se le altre 31 colonne sono valide. Il docstring di
  `_senza_null` dice "`null` dal client vale «campo omesso»": vale per
  `sp_overrides`/`pregresso`/`financing_loans` ma non per `sp_indexing` — incoerenza, non un
  rifiuto intenzionale.
- `calculations/forecast_engine.py:1373-1420` (`_resolve_sp_indexing`) — se il `null` arrivasse
  fino al motore (bypassando lo schema), verrebbe trattato come "driver sconosciuto" e IGNORATO,
  senza errore: il motore stesso tollera un valore nullo. Lo schema è quindi PIÙ severo di quanto
  serva.
- **Misurato**, secondo punto: `BudgetAssumptionsBulkRow(**_senza_null({"scenario_id": 1,
  "forecast_year": 2026, "campo_a_caso_che_non_esiste": 42}))` **non alza nulla**: pydantic scarta
  il campo sconosciuto in silenzio (`extra` di default è `"ignore"`). Nessuno schema del bulk ha
  `model_config = ConfigDict(extra=...)`.
- `backend/app/services/assumptions_service.py:137-148` (`validate_bulk_rows`) — è l'UNICO
  chiamante di `BudgetAssumptionsBulkRow`. `extra="forbid"` su questa classe non tocca
  `BudgetAssumptionsCreate`/`BudgetAssumptionsUpdate` (classi sorelle): il raggio d'azione è il solo
  bulk.
- Verificato che il frontend non manda oggi alcun campo fuori schema: `AssumptionsMap = Record<number,
  Partial<BudgetAssumptionsCreate>>` (`frontend/lib/budget-horizon.ts:26`) tipizza ogni riga contro
  l'interfaccia `BudgetAssumptionsCreate`, e `assumptionRowsForSave` fa solo
  `{...assumptions[year], scenario_id, forecast_year}` — nessuno spread di campi extra.

**Change.**

1. `backend/app/services/assumptions_service.py`, dentro `_senza_null` (dopo il blocco
   `sp_overrides`):
   ```python
   # PRIMA (righe 122-134)
   def _senza_null(riga):
       """`null` dal client vale «campo omesso» (`build_assumption_row` lo coalizza sul default): lo si toglie prima dello schema."""
       pulita = {k: v for k, v in riga.items() if v is not None}
       for chiave in ("financing_loans", "tax_temporary_differences"):
           if isinstance(pulita.get(chiave), list):
               pulita[chiave] = [{k: v for k, v in voce.items() if v is not None} if isinstance(voce, dict) else voce
                                 for voce in pulita[chiave]]
       if isinstance(pulita.get("sp_overrides"), dict):
           pulita["sp_overrides"] = {k: v for k, v in pulita["sp_overrides"].items() if v is not None}
       if isinstance(pulita.get("pregresso"), dict):
           pulita["pregresso"] = {k: ({kk: vv for kk, vv in piano.items() if vv is not None} if isinstance(piano, dict) else piano)
                                  for k, piano in pulita["pregresso"].items() if piano is not None}
       return pulita

   # DOPO
   def _senza_null(riga):
       """`null` dal client vale «campo omesso» (`build_assumption_row` lo coalizza sul default): lo si toglie prima dello schema."""
       pulita = {k: v for k, v in riga.items() if v is not None}
       for chiave in ("financing_loans", "tax_temporary_differences"):
           if isinstance(pulita.get(chiave), list):
               pulita[chiave] = [{k: v for k, v in voce.items() if v is not None} if isinstance(voce, dict) else voce
                                 for voce in pulita[chiave]]
       if isinstance(pulita.get("sp_overrides"), dict):
           pulita["sp_overrides"] = {k: v for k, v in pulita["sp_overrides"].items() if v is not None}
       # Come `sp_overrides`: un valore nullo per una voce di `sp_indexing` vale "questa voce non e'
       # indicizzata" (il motore stesso la tratterebbe come "driver sconosciuto", innocuo -- vedi
       # calculations/forecast_engine.py:_resolve_sp_indexing), non un errore di schema. Prima di
       # questa riga un `null` qui dentro alzava 422 sull'INTERO bulk (literal_error sul tipo
       # Literal["ricavi","acquisti","personale"]).
       if isinstance(pulita.get("sp_indexing"), dict):
           pulita["sp_indexing"] = {k: v for k, v in pulita["sp_indexing"].items() if v is not None}
       if isinstance(pulita.get("pregresso"), dict):
           pulita["pregresso"] = {k: ({kk: vv for kk, vv in piano.items() if vv is not None} if isinstance(piano, dict) else piano)
                                  for k, piano in pulita["pregresso"].items() if piano is not None}
       return pulita
   ```

2. `backend/app/schemas/budget.py`, classe `BudgetAssumptionsBulkRow` (righe 269-273):
   ```python
   # PRIMA
   class BudgetAssumptionsBulkRow(BudgetAssumptionsBase):
       """Una riga del bulk `PUT /assumptions`: gli stessi vincoli di `BudgetAssumptionsCreate`, senza `scenario_id` obbligatorio
       (lo scenario e' nel percorso). Serve SOLO a validare: le righe si costruiscono ancora da `build_assumption_row`,
       cosi' un input valido produce esattamente le righe di prima."""
       scenario_id: Optional[int] = None

   # DOPO
   class BudgetAssumptionsBulkRow(BudgetAssumptionsBase):
       """Una riga del bulk `PUT /assumptions`: gli stessi vincoli di `BudgetAssumptionsCreate`, senza `scenario_id` obbligatorio
       (lo scenario e' nel percorso). Serve SOLO a validare: le righe si costruiscono ancora da `build_assumption_row`,
       cosi' un input valido produce esattamente le righe di prima. `extra="forbid"` SOLO qui (non su
       `BudgetAssumptionsBase`/`BudgetAssumptionsCreate`, entrambe usate altrove): un campo sconosciuto
       nel corpo del bulk oggi viene accettato e scartato in silenzio da pydantic (default
       `extra="ignore"`) -- un refuso o un campo rinominato lato frontend non arriva mai a un errore,
       sparisce e basta. `BudgetAssumptionsBulkRow` e' l'unica classe che questo file istanzia da un
       dict di client (`validate_bulk_rows`, unico chiamante); nessun altro schema del bulk cambia."""
       model_config = ConfigDict(extra="forbid")
       scenario_id: Optional[int] = None
   ```

3. `backend/app/services/assumptions_service.py`, dentro `messaggio_errore_campo` (dopo il ramo
   `literal_error`, prima di `string_pattern_mismatch`):
   ```python
   # PRIMA
       elif tipo == "literal_error":
           testo = "valore non ammesso: sono ammessi " + str(ctx.get("expected", "")).replace(" or ", " o ")
       elif tipo == "string_pattern_mismatch":

   # DOPO
       elif tipo == "literal_error":
           testo = "valore non ammesso: sono ammessi " + str(ctx.get("expected", "")).replace(" or ", " o ")
       elif tipo == "extra_forbidden":
           testo = "campo sconosciuto, non ammesso"
       elif tipo == "string_pattern_mismatch":
   ```

**Constraints.**
- `extra="forbid"` va SOLO su `BudgetAssumptionsBulkRow`: non su `BudgetAssumptionsBase` (la classe
  madre, condivisa con `BudgetAssumptionsCreate`, usata da `POST /assumptions` per-anno e da
  `PUT /assumptions/{year}`, fuori dal perimetro di questo task).
- Nessun cambiamento a `build_assumption_row` (che persiste da `data` grezzo, non dal modello
  Pydantic validato): il Change tocca solo la VALIDAZIONE.

**Ownership.** `backend/app/services/assumptions_service.py`, `backend/app/schemas/budget.py`,
`tests/test_bulk_tipizzato.py`.

- [ ] **Step E1.** `git rev-parse HEAD` (`0f7614a...`).
- [ ] **Step E2 — prova rossa, due asserzioni nuove.**
  1. Aggiungi a `CASI` in `tests/test_bulk_tipizzato.py` (dopo `"tasso al 500%"`):
     ```python
         "campo sconosciuto": ({"campo_a_caso_che_non_esiste": 42}, "campo_a_caso_che_non_esiste",
                               "campo sconosciuto, non ammesso (ricevuto: 42)"),
     ```
  2. In `test_i_null_del_client_non_sono_errori_e_un_primo_anno_dopo_base_piu_uno_resta_accettato`,
     nel primo dizionario di `con_null` (dopo la riga `"financing_loans": [...]`):
     ```python
     # PRIMA
                  "financing_loans": [{"name": None, "amount": 50000, "opening_residual": 0, "duration_years": 5,
                                       "interest_rate": 3, "grace_years": None, "balloon_pct": None}]},
                 {"forecast_year": 2028, "revenue_growth_pct": 5},

     # DOPO
                  "financing_loans": [{"name": None, "amount": 50000, "opening_residual": 0, "duration_years": 5,
                                       "interest_rate": 3, "grace_years": None, "balloon_pct": None}],
                  "sp_indexing": {"sp16g": None}},
                 {"forecast_year": 2028, "revenue_growth_pct": 5},
     ```
  Esegui:
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_bulk_tipizzato.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **2 failed, 6 passed** — il caso «campo sconosciuto» fallisce con "DID NOT RAISE
  HTTPException" (oggi il campo sconosciuto passa senza errore); il test dei `null` fallisce con un
  422 reale su `sp_indexing.sp16g` (`literal_error`), non con un'eccezione a monte.
- [ ] **Step E3.** Applica il Change (i tre punti).
- [ ] **Step E4 — verde.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_bulk_tipizzato.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: **8 passed** (i 7 di oggi, invariati, più il nuovo caso `CASI`; il test dei `null` torna
  verde senza cambiare la sua unica asserzione sul risultato finale).
- [ ] **Step E5 — non regressione sul resto del bulk/previsionale.**
  ```bash
  env -u ANTHROPIC_API_KEY backend/venv/bin/python -m pytest tests/test_forecast_indicizzazione.py tests/test_build_assumption_row.py tests/test_forecast_preview.py tests/test_budget_pregresso.py -q -p no:cacheprovider -W ignore::DeprecationWarning
  ```
  Atteso: tutti verdi (nessuno di questi passa un `sp_indexing` con `null` annidato o un campo
  sconosciuto oggi).
- [ ] **Step E6 — tipi frontend, per assicurarsi che nessun chiamante reale sia colpito.**
  ```bash
  cd frontend && npx tsc --noEmit
  ```
  Atteso: pulito.

**Observable acceptance.** `tests/test_bulk_tipizzato.py` a 8 test verdi; un `sp_indexing` con un
valore `null` annidato è accettato (trattato come voce omessa); un campo sconosciuto nel corpo del
bulk risponde 422 con `{"campo": "<nome>", "messaggio": "campo sconosciuto, non ammesso
(ricevuto: ...)"}`, non più accettato in silenzio.

## Commit (Task 7, un solo commit per i tre sotto-task B, C, E)

- [ ] **Commit.**
  ```bash
  git add calculations/intra_year_engine.py calculations/forecast_engine.py \
    tests/test_projection_common_debito_bancario.py \
    backend/app/services/assumptions_service.py backend/app/schemas/budget.py \
    tests/test_bulk_tipizzato.py
  git commit -F - <<'EOF'
  chore: codice morto rimosso, alias corretto, due buchi dello schema del bulk chiusi

  B: _financing_contracts(assumption, include_opening=True) -- il parametro non aveva mai un
  chiamante con include_opening=False (verificato su tutto il repo): rimosso, nessun cambiamento
  di comportamento.

  C: forecast_engine.py aveva quattro alias del debito bancario condiviso in projection_common; il
  commento diceva che restavano "per chi li importa dai test", ma tre su quattro sono usati come
  abbreviazioni interne dal motore stesso. Il quarto, _residuo_prestiti_nuovi, non aveva invece
  alcun chiamante interno: rimosso, il test che ne confrontava l'identita' importa ora il kernel
  condiviso direttamente. Nessuna riga di calcolo cambia: banco di parita' a 0 divergenze.

  E: lo schema tipizzato del bulk delle ipotesi (BudgetAssumptionsBulkRow) rifiutava un valore null
  annidato in sp_indexing con un 422 sull'intero bulk, anche se il motore stesso lo tollera come
  "driver sconosciuto" innocuo -- ora null vale "voce omessa", come per sp_overrides/pregresso. Un
  campo sconosciuto nel corpo del bulk veniva invece accettato e scartato in silenzio da pydantic
  (extra="ignore" di default): ora BudgetAssumptionsBulkRow (sola classe toccata) rifiuta con
  extra="forbid" e un messaggio italiano dedicato.

  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01C8chDC8b297itUaoK1TQNW
  EOF
  ```

---

### Task 8: Verifica di fine ondata

**Esecutore:** chi esegue il piano (suite, banco, riallineamento) + agente `collaudatore` per il
collaudo a schermo · **Ondata:** dopo tutti gli altri sette task.

**Files:**
- Nessuna modifica al codice in questo task: un difetto trovato si riferisce, non si corregge qui.
- Create/Ownership: `.superpowers/sdd/2026-09-12-ondata-finale-correzioni/task-8-report.md` e
  `collaudo-brief.md` (registro di verifica, non si committano — cartella da creare se manca).

**Interfaces:**
- Consumes: i sette task precedenti, tutti applicati e committati sullo stesso branch.
- Produces: nessuna interfaccia — è l'ultimo task dell'ondata.

**Target.** Suite Python e frontend pulite (o ogni fallimento classificato); banco di parità del
motore budget a 0 divergenze (nessun task di questa ondata lo tocca); misure prima/dopo
sull'infrannuale su tutti gli scenari del database; collaudo a schermo dei percorsi toccati;
riallineamento della documentazione sul diff dell'intera ondata.

**Da leggere prima.** I rapporti di fine task dei Task 1-7 (ciascuno annota i propri numeri
prima/dopo, gli scarti misurati rispetto a questo piano, e le osservazioni non richieste dal
proprio Target — in particolare lo scarto Task 1→Task 3 sullo sbilancio dell'azienda id 21, che
questo task deve leggere come numero finale, non ricalcolare da zero).

**Constraints.** Nessuna modifica al codice in questo task. Nessun `git checkout`, `git stash`,
`git reset --hard`. Nessun nome di azienda cliente nei rapporti: solo id.

- [ ] **Step 1: Base dell'ondata.** `git merge-base HEAD main > /tmp/ondata-base` (o, se l'intera
  ondata gira su `feat/scadenziamento-pregresso` senza merge verso `main` in questa fase,
  `git rev-parse 0f7614a > /tmp/ondata-base` — usa il commit realmente antecedente al Task 1).

- [ ] **Step 2: Suite Python intera.**
  ```bash
  env -u ANTHROPIC_API_KEY /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests -q \
    --ignore=tests/corpus -p no:cacheprovider -W ignore::DeprecationWarning 2>&1 | tail -40
  ```
  Ogni fallimento si classifica: file di test toccato dall'ondata
  (`git diff --name-only "$(cat /tmp/ondata-base)" HEAD -- tests`) oppure no. Un fallimento in un
  file non toccato si verifica sul commit base (`0f7614a`, non l'ondata) prima di dirlo
  preesistente. **Non confrontare il conteggio assoluto con `1005 passed, 62 skipped` di CLAUDE.md
  alla lettera**: stabilisci il numero di riferimento eseguendo la stessa suite sul commit base
  `0f7614a`, nello stesso ambiente, e confronta lo scarto — l'unico invariante è che `failed` non
  aumenti (Global Constraints).

- [ ] **Step 3: Frontend.**
  ```bash
  cd /home/peter/DEV/budget/frontend && npx vitest run && npx tsc --noEmit
  ```
  Atteso: 46 file / 721 test più i 9 nuovi del Task 4 (`pratica-format.test.ts`) = **47 file / 730
  test** (ricalcola davvero, non fidarti di questa aritmetica); `tsc` pulito.

- [ ] **Step 4: Banco di parità del motore budget (controllo negativo — nessun task di questa
  ondata tocca `calculations/forecast_engine.py` sul piano del CALCOLO; il Task 7/C tocca solo
  alias e commenti).**
  ```bash
  /home/peter/DEV/budget/backend/venv/bin/python scripts/parita_motore.py "$(cat /tmp/ondata-base)" HEAD --anni 4 --controllo-negativo --json /tmp/ondata-parita.json --log /tmp/ondata-parita.log
  /home/peter/DEV/budget/backend/venv/bin/python scripts/parita_riepilogo.py /tmp/ondata-parita.json
  ```
  Atteso: **0 divergenze**, controllo negativo superato — nessuna riga di output dal riepilogo. Uno
  scarto qui indica una regressione nel Task 7/C (alias) o un effetto collaterale non previsto:
  fermarsi e riferire, non correggere in questo task.

- [ ] **Step 5: Misure prima/dopo sull'infrannuale, su TUTTI gli scenari del database.** Su una
  **copia fresca** del database (`sqlite3 financial_analysis.db ".backup '/tmp/ondata-db.sqlite'"`),
  per ciascuno degli scenari `infrannuale` presenti (`select id from budget_scenarios where
  scenario_type='infrannuale'` — verifica l'elenco corrente, può essere cambiato dal database di
  sviluppo dai tempi di stesura di questo piano), genera la proiezione **sul commit base**
  (`/tmp/ondata-base`, `git worktree add` o `git stash`/copia separata — mai sull'albero di lavoro
  con l'ondata applicata) e **sull'HEAD dell'ondata** (Task 1-7 tutti applicati), leggendo per
  ciascuno scenario: `sp16a/b/c`, `sp17a/b/c`, `sp06a-g`, `sp07a-g`, gli aggregati `sp16`/`sp17`/
  `sp06`/`sp07`, `sp09`, lo sbilancio (Attivo − Passivo), la PFN, il DSO
  (`FinancialRatiosCalculator`), e per gli scenari il cui promote è stato tentato nei rapporti dei
  Task 1-3 (in particolare l'azienda id 21 e l'azienda id 48), l'esito del promote (riuscito/
  rifiutato) e l'importo di `unfunded_financing_requirement` quando presente. Consolida i numeri già
  misurati nei rapporti dei Task 1, 2, 3 (non rimisurare da zero quanto già misurato lì, se il
  database di sviluppo non è cambiato nel frattempo — verificalo con un controllo di conteggio
  scenari e id) in un'unica tabella riepilogativa nel rapporto di questo task, con particolare
  attenzione a:
  - Nessuno scenario mostra uno sbilancio diverso da zero che non sia accompagnato da una
    diagnostica coerente (`unfunded_financing_requirement` o `tax_settlement_reclass_below_zero`).
  - L'azienda id 21 (scenario di collaudo dei Task 1-3): il numero finale di sbilancio/fabbisogno
    dichiarato coincide (lo stesso numero misurato nel rapporto del Task 3, Step 8) e il promote è
    rifiutato.
  - L'azienda id 237 (scenario id 18, il caso citato dalle indagini): `sp16a`/`sp17a` non sono più
    0,00, `sp06a` non è più 0,00, le diagnostiche `reference_financial_debt_undetailed` e
    `reference_receivables_undetailed` sono dichiarate.

- [ ] **Step 6: Brief del collaudo** in `collaudo-brief.md`, per l'agente `collaudatore` (server di
  sviluppo avviati dal coordinatore da `backend/` e `frontend/`, `DEV_USER_ID=dev-user-001`,
  **backend su `http://127.0.0.1:8011`, frontend su `http://localhost:3002`**, con
  `NEXT_PUBLIC_API_URL=http://localhost:8011/api/v1` — stesso schema di
  `.superpowers/sdd/2026-09-10-lotto3a-motori-rendiconto/collaudo-brief.md`, una **copia** del
  database, mai quello reale). Pre-volo obbligatorio (stesso schema del brief citato):
  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8011/api/v1/companies   # atteso 200
  curl -s http://localhost:3002/ | grep -o '<title>[^<]*</title>'                     # NON deve essere FormulaFinance
  curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3002/pratica              # atteso 200
  ```
  Registra a inizio run: `git rev-parse HEAD` del worktree servito dal backend, e `sha1sum` del DB.
  **Id azienda/anno sempre, mai il nome a video.** Cinque percorsi:
  1. **Infrannuale con debito bancario reale e riferimento senza dettaglio finanziario** (azienda id
     237, scenario id 18, o equivalente ricostruito): tab Proiezione — `sp16a`/`sp17a` mostrano il
     valore reale del parziale (non 0,00), `sp06a` (crediti verso clienti) mostra il valore reale
     (non 0,00); tab Confronto — nessuna riga con un valore palesemente azzerato che il parziale
     dichiara diverso da zero.
  2. **Promote di un infrannuale con debito tributario d'apertura eccedente la cassa del parziale**
     (azienda id 21, o equivalente): il promote è rifiutato con un messaggio che nomina lo
     sbilancio, in italiano, importo in formato europeo — coerente col numero misurato allo Step 5.
  3. **Tab Stampa (o Confronto/Proiezione) su uno scenario il cui storico quadra al centesimo**: la
     riga «DIFFERENZA (Attivo − Passivo)» mostra `-`, mai una percentuale a molte cifre.
  4. **Un import PDF route C (situazione contabile) con un residuo non classificato**, o in
     alternativa un `PUT /adjustments` che peggiora deliberatamente lo sbilancio (Rettifiche): il
     messaggio/toast mostra l'importo in formato italiano (punto per le migliaia, virgola per i
     decimali), mai la forma americana.
  5. **Un bulk di ipotesi con un campo sconosciuto o un `sp_indexing` con valore nullo** (dal
     wizard, se raggiungibile a schermo, altrimenti via chiamata diretta all'API dal collaudatore):
     il campo sconosciuto produce un 422 con messaggio italiano; il `null` in `sp_indexing` viene
     accettato senza errore.

- [ ] **Step 7: Collaudo.** Il coordinatore lancia l'agente `collaudatore` col brief; i rilievi
  vanno nel rapporto.

- [ ] **Step 8: Riallineamento.** `/riallinea` sul diff `$(cat /tmp/ondata-base)..HEAD`; i
  `file:riga` corretti meccanicamente si committano a parte, il resto va nel rapporto. Presta
  attenzione in particolare a: la frase di CLAUDE.md sulle "reserves + previous profit" già
  segnalata come errata altrove nel file (fuori perimetro di questa ondata, ma se `/riallinea` la
  incontra di nuovo sul diff, annotalo); ogni citazione di numeri (`1.856,76`, o quale che sia il
  valore finale del Task 3) che questo piano ha lasciato come "misurato allo Step X" — verifica che
  la documentazione aggiornata dai Task 1/2/3 non abbia ereditato un placeholder o un numero
  disallineato dalla misura reale.

- [ ] **Step 9: Rapporto** `task-8-report.md`: esito delle suite (con classificazione dei
  fallimenti), banco (0 divergenze atteso), misure infrannuale consolidate (Step 5), rilievi del
  collaudo, esito di `/riallinea`.

**Observable acceptance.** Suite Python, vitest e `tsc` puliti (o ogni fallimento classificato e
riferito); banco di parità del motore budget a 0 divergenze; misure infrannuale consolidate su
tutti gli scenari del database, coerenti con i rapporti dei Task 1-3; collaudo senza rilievi
bloccanti; `/riallinea` eseguito.

---

## Fuori perimetro

- **I sei issue GitHub aperti** (#24, #48, #50, #51, #52, #53): restano in arretrato, decisione del
  proprietario del 2026-09-12 — l'ultima ondata copre i quattro difetti del collaudo del lotto 3A
  più i minori parcheggiati, non l'arretrato degli issue.
- **F-ii (bozza-task-M, banco `scripts/parita_motore.py` esteso con un profilo/fixture "tutti e
  quattro i debiti operativi pianificati")**: misurato durante la stesura della bozza che
  l'aggiunta proposta **non** innesca in modo affidabile il residuo di quadratura che dovrebbe
  provare (0 anni su 4 col seme di default `20260910`), mentre
  `tests/test_forecast_residuo_neutro.py::test_con_tutti_i_debiti_operativi_pianificati_il_residuo_resta_sul_default_e_si_dichiara`
  (fixture `PIANI_TUTTI`, rate scelte a mano per lasciare un residuo) certifica già il contratto in
  modo deterministico ed è verde. **Ruling del coordinatore: si chiude senza modifiche**, con
  questa misura come prova — aggiungere alla griglia uno scenario che innesca a caso avrebbe reso
  il banco più rumoroso senza aggiungere garanzie reali.
- **G1, G2, G3** (rilievi minori del lotto 2/3A): già chiuse su `0f7614a`, verificato sul codice (non
  sul verbale) durante la stesura di `bozza-task-M.md` — `_realign_sp_declarations` tratta
  `debiti_tributari` come gli altri tre debiti (10 test verdi su
  `tests/test_forecast_dichiarato_vs_persistito.py`); il confronto a riga 1177 di
  `forecast_engine.py` citato come difettoso è oggi prosa di docstring, non codice, e il confronto
  vero usa unità omogenee; `legacyNoteFor("debiti_tributari")` è reso irraggiungibile dal TIPO
  TypeScript (`Exclude<PregressoKey, "debiti_tributari">`), non solo dal comportamento a runtime —
  26 test verdi su `frontend/lib/budget-pregresso-tabella.test.ts`. Non entrano in questo piano.
- **Siti `:,.2f`/`:,.0f` non user-facing elencati dalla bozza del Task 5** (`importers/reliability.py`,
  `importers/xbrl_parser_enhanced.py`, `importers/vision_rescue.py`,
  `importers/pdf_extractor_llm.py`, `importers/situazione_contabile_parser.py`,
  `backend/app/services/ai_comments_service.py`, `backend/app/api/v1/imports.py`): diagnostica
  interna mai renderizzata a schermo, testo per un LLM, o un messaggio già in inglese — nessuno di
  questi è nel Change del Task 5, per la motivazione dettagliata nella sua tabella «Perimetro».

## Copertura

| Difetto/rilievo | Task |
|---|---|
| Difetto 1 — debito finanziario azzerato nell'infrannuale | 1 |
| Debito 1, rischio gemello sui crediti (misurato dal Task 1) | 2 |
| Difetto 2/4 — promote che ignora l'uscita di cassa tributaria, verificato con bisezione | 3 |
| Difetto 3 — la percentuale che esplode a schermo | 4 |
| Difetto 4 (parte) — formato americano in `iv_cee_hierarchy.py`, più due siti user-facing gemelli | 5 |
| Minore A — doppio `abs` cieco a un'inversione di segno | 6 |
| Minore D — caso limite non fissato in `parita_riepilogo.py` | 6 |
| Minore F-i — test del Task 11 (lotto 3A) non protetto | 6 |
| Minore F-ii — non innesca il residuo in modo affidabile | Fuori perimetro (chiuso senza modifiche) |
| Minore B — parametro morto `include_opening` | 7 |
| Minore C — alias morto `_residuo_prestiti_nuovi` | 7 |
| Minore E — `sp_indexing` con `null`, campo sconosciuto accettato in silenzio | 7 |
| Minori G1-G3 | Fuori perimetro (già chiuse) |
| Verifica di fine ondata | 8 |
