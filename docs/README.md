# Documentation Map

This index lists the **current** documentation and where each topic lives. Docs
are organized so that behaviour is described in one authoritative place that
tracks the code; superseded material lives in [`archive/`](archive/).

## Authoritative sources (repo root)

| Document | Scope |
|----------|-------|
| [`README.md`](../README.md) | Project overview, feature list, quick-start, deployment. Start here. |
| [`CLAUDE.md`](../CLAUDE.md) | Architecture & developer guide: shared modules, DB schema, API design, auth/multi-tenancy, calculators, conventions. Single source of truth for code behaviour. |
| [`IMPORT-OVERVIEW.md`](../IMPORT-OVERVIEW.md) | The import pipeline end-to-end: macro-area router (routes A/B/C/OTHER), LLM vs deterministic extraction, IV-CEE leveling, quadratura / anti-masking, CE↔SP identity. |

## Topic guides (`docs/`)

| Document | Scope |
|----------|-------|
| [`TASSONOMIA.md`](TASSONOMIA.md) | IV-CEE field reference: `sp01`–`sp18`, `ce01`–`ce20` and their detail breakdowns, with XBRL tag coverage (2011–2018). |
| [`TRIAL-BALANCE-IMPORT.md`](TRIAL-BALANCE-IMPORT.md) | Route-C (situazione contabile / bilancio di verifica) strategy: subtotal-based mapping to IV-CEE rather than per-GL-account. |
| [`FORECASTING_GUIDE.md`](FORECASTING_GUIDE.md) | End-user guide to budget scenarios: assumptions per year, cost splits, working capital, reviewing forecast output. |
| [`IFRAME_INTEGRATION.md`](IFRAME_INTEGRATION.md) | Embedding the app in Formula Finance via iframe + Supabase JWT `postMessage`; CORS and env vars. |
| [`FINAL-REPORT-PDF.md`](FINAL-REPORT-PDF.md) | Scope/gap analysis of the PDF report output vs the on-screen `/report`. |

## Archive (`docs/archive/`)

Historical and superseded documents — kept for provenance, **not** maintained.
Do not treat them as current; their claims may contradict the code. See
[`archive/README.md`](archive/README.md) for what each was and which current
document replaced it.

## Reference data & samples

- [`examples/`](examples/) — sample bilanci (XBRL/PDF) across gestionali (Zucchetti, Datev/Koinos, Dylog, DEPI, …).
- `kps_extracted.md` / `kps_extracted.json` — a worked extraction example.
