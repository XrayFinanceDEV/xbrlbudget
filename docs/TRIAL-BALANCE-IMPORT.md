# Trial Balance (Situazione Contabile) Import — Design Document

Universal parser for Italian trial balance PDFs from any ERP system.

## Problem

Italian ERP systems (AGO, DEPI, Dylog, Zucchetti, TeamSystem, etc.) each use different account numbering schemes:
- DEPI: `XX/YY/ZZZ` (e.g. `03/05/005`)
- AGO: 8-digit codes (e.g. `13065000`)
- Others: 5-digit, 6-digit, alphanumeric, etc.

Building a parser per ERP is not scalable. But all Italian trial balances share:
1. **Italian account descriptions** following standard OIC terminology
2. **Subtotal hierarchy** with recognizable category titles
3. **Section structure**: ATTIVO / PASSIVO / COSTI / RICAVI

## Approach: Subtotal-Based Classification

Instead of classifying individual GL accounts, classify **subtotal rows** and take their amounts directly.

### Key Insight

Trial balances are structured as:
```
SUBTOTAL HEADER — "Debiti verso banche (EE)"         7.156,53
  103435 002 - Carta di credito intesa 3384              222,00
  204675 001 - BANCA C/MUTUI IPOT.ESIG.ENTRO ES       6.934,45
  204680 001 - INTESA S.PAOLO PREST.CHIROGRAFAR            0,08
SUBTOTAL HEADER — "Debiti verso banche (OE)"        42.490,98
  204710 001 - Mutuo Oltre Es. Intesa N.1213368       42.490,98
```

The ERP already computed the subtotals. We just need to:
1. **Identify subtotal rows** (recognizable by formatting: bold, indentation, `***` codes, or amount-only lines with descriptive titles)
2. **Map subtotal description → IV CEE field**
3. **Use the subtotal amount** (ignore individual GL detail lines)
4. **Reconcile against section totals** (TOTALE ATTIVO, TOTALE PASSIVO, TOTALE A PAREGGIO)

### Why Not Classify Individual Accounts?

- Too many variations across ERPs (thousands of GL account names)
- Many detail accounts are ambiguous without context (e.g. "Conto corrente" could be asset or liability)
- Subtotals are always present and always labeled with standard Italian categories
- The ERP already summed the details — no point re-doing it

## Subtotal → IV CEE Mapping

### Balance Sheet (Stato Patrimoniale)

| Subtotal Description Keywords | IV CEE | DB Field |
|-------------------------------|--------|----------|
| immobilizzazioni immateriali, oneri pluriennali | B.I | sp02 |
| immobilizzazioni materiali, macchine, impianti, fabbricati, terreni | B.II | sp03 |
| immobilizzazioni finanziarie, partecipazioni (immob) | B.III | sp04 |
| rimanenze, merci, prodotti finiti, materie prime, lavori in corso | C.I | sp05 |
| crediti v/clienti, crediti commerciali | C.II.1 | sp06a / sp07a |
| crediti v/controllate | C.II.2 | sp06b / sp07b |
| crediti v/collegate | C.II.3 | sp06c / sp07c |
| crediti v/controllanti | C.II.4 | sp06d / sp07d |
| crediti tributari, erario, IVA, IRES, IRAP | C.II.5-bis | sp06e / sp07e |
| imposte anticipate | C.II.5-ter | sp06f / sp07f |
| crediti v/altri, crediti diversi | C.II.5-quater | sp06g / sp07g |
| attività finanziarie (non immob), titoli | C.III | sp08 |
| disponibilità liquide, depositi bancari, cassa, banca c/c | C.IV | sp09 |
| ratei e risconti attivi | D attivo | sp10 |
| capitale sociale | A.I | sp11 |
| riserva legale, riserve, sovrapprezzo | A.II-VIII | sp12 |
| utili/perdite portati a nuovo | A.VIII | sp12g |
| utile/perdita d'esercizio | A.IX | sp13 |
| fondi rischi, fondi per rischi e oneri | B passivo | sp14 |
| TFR, trattamento fine rapporto | C passivo | sp15 |
| debiti verso banche | D.4 | sp16a / sp17a |
| debiti v/altri finanziatori, debiti v/soci finanziamenti | D.3/5 | sp16b / sp17b |
| obbligazioni | D.1/2 | sp16c / sp17c |
| debiti verso fornitori | D.7 | sp16d / sp17d |
| debiti tributari | D.12 | sp16e / sp17e |
| debiti previdenziali, INPS, istituti previdenza | D.13 | sp16f / sp17f |
| altri debiti | D.14 | sp16g / sp17g |
| ratei e risconti passivi | E passivo | sp18 |

### Breve/Lungo (Entro/Oltre) Detection

Many ERPs mark maturity directly:
- `(EE)` or `(entro esercizio)` or `entro 12 mesi` → breve (sp06/sp16)
- `(OE)` or `(oltre esercizio)` or `oltre 12 mesi` → lungo (sp07/sp17)

If not marked, use the section context:
- Under "ATTIVO CIRCOLANTE" → breve by default
- Under "IMMOBILIZZAZIONI" → assets (sp02-sp04), not credits

### Income Statement (Conto Economico)

| Subtotal Description Keywords | IV CEE | DB Field |
|-------------------------------|--------|----------|
| ricavi vendite, ricavi prestazioni, fatturato | A.1 | ce01 |
| variazioni rimanenze prodotti | A.2 | ce02 |
| incrementi immobilizzazioni, lavori interni | A.4 | ce03 |
| altri ricavi, contributi esercizio | A.5 | ce04 |
| materie prime, acquisti merci | B.6 | ce05 |
| servizi, consulenze, utenze, manutenzioni | B.7 | ce06 |
| godimento beni terzi, affitti, leasing, noleggi | B.8 | ce07 |
| costi personale, salari, stipendi | B.9 tot | ce08 |
| salari e stipendi | B.9a | ce08b |
| oneri sociali | B.9b | ce08c |
| TFR (accantonamento) | B.9c | ce08a |
| altri costi personale | B.9e | ce08d |
| ammortamenti (totale) | B.10 tot | ce09 |
| ammortamento immateriali | B.10a | ce09a |
| ammortamento materiali | B.10b | ce09b |
| svalutazioni immobilizzazioni | B.10c | ce09c |
| svalutazione crediti | B.10d | ce09d |
| variazioni rimanenze materie prime | B.11 | ce10 |
| accantonamenti rischi | B.12 | ce11 |
| altri accantonamenti | B.13 | ce11b |
| oneri diversi gestione, imposte indirette | B.14 | ce12 |
| proventi partecipazioni, dividendi | C.15 | ce13 |
| altri proventi finanziari, interessi attivi | C.16 | ce14 |
| oneri finanziari, interessi passivi | C.17 | ce15 |
| utili/perdite cambi | C.17-bis | ce16 |
| rivalutazioni (finanziarie) | D.18 | ce17a |
| svalutazioni (finanziarie) | D.19 | ce17b |
| proventi straordinari | E.20 | ce18 |
| oneri straordinari | E.21 | ce19 |
| imposte, IRES, IRAP, imposte correnti | 22 | ce20 |

## Algorithm

```
1. EXTRACT TEXT
   - PyMuPDF text extraction (all pages)
   - Detect two-column layout (ATTIVO | PASSIVO side by side) or single-column

2. IDENTIFY STRUCTURE
   - Find section markers: "ATTIVITA'", "PASSIVITA'", "CONTO ECONOMICO"
   - Find "TOTALE ATTIVITA'", "TOTALE PASSIVITA'", "TOTALE A PAREGGIO" for reconciliation anchors

3. PARSE LINES
   - For each line, classify as:
     a) SUBTOTAL ROW: description matches a known category keyword + has an amount
     b) DETAIL ROW: has account code + description + amount (skip — we use subtotals)
     c) SECTION TOTAL: "TOTALE ..." (reconciliation anchor)
   - Subtotal detection heuristics:
     - Bold formatting (if available from PDF metadata)
     - Lines with *** or ** codes (DEPI format)
     - Lines with 8-digit codes that are round subtotals (AGO format)
     - Lines where description is a known IV CEE category

4. MAP SUBTOTALS → IV CEE
   - Match subtotal description against keyword table (fuzzy, case-insensitive)
   - Determine breve/lungo from (EE)/(OE) suffix or section context
   - Assign amount to corresponding sp/ce field

5. CONTEXT INHERITANCE (fallback)
   - If a line can't be classified but appears between two known subtotals,
     it inherits the parent category
   - E.g., lines after "Costi per servizi" and before next subtotal → all ce06

6. RECONCILE
   - Sum sp01-sp10 must equal TOTALE ATTIVO (or close)
   - Sum sp11-sp18 must equal TOTALE PASSIVO
   - If gap exists, allocate to catch-all fields (sp06g, sp16g, etc.)
   - Flag large discrepancies as warnings
```

## Two-Column Layout Handling

Many trial balances show ATTIVO and PASSIVO side by side:
```
        ATTIVITA'                          |         PASSIVITA'
13065000 - Oneri Pluriennali     39.841,17 | 31000000 - Capitale          2.000,00
```

Detection: if amounts appear in both left and right halves of the page, it's two-column.
Split each line at the midpoint and process left (ATTIVO) and right (PASSIVO) independently.

## Test Files

| File | Format | Codes | Status |
|------|--------|-------|--------|
| `docs/debug2/0530edc5-*.pdf` | DEPI | XX/YY/ZZZ | Working (existing parser) |
| `docs/debug2/806322ed-*.pdf` | DEPI | XX/YY/ZZZ | Working (existing parser) |
| `docs/debug2/0_Infra 30.09*.pdf` | AGO | 8-digit | Detected, not parsed yet |

## Implementation Notes

- Keep existing `situazione_contabile_parser.py` for DEPI format (it works well)
- Add new `trial_balance_parser.py` with the universal description-based approach
- Auto-detection in `pdf_importer.py` already routes trial balances away from LLM
- No API key needed — fully deterministic
- Should handle partial-year (infrannuale) trial balances too (same format, shorter period)
