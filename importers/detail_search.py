"""Bounded, exhaustive-on-extracted-rows detail search with explicit coverage.

Rows have one owning chunk. Overlap/headers are context-only and never spendable
cells. All successful proposals are reduced together, not one chunk at a time.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from decimal import Decimal
import os
import re
import time

from importers import detail_enrichment as de

CHUNK_CHARS = 45_000
CONTEXT_CHARS = 6_000
SEARCH_SECONDS = 240.0


@dataclass
class SearchChunk:
    index: int
    primary: list
    context: list
    error: str | None = None


def active_families(balances):
    return {period: [a for a in de.ANALYTICAL_FAMILIES if Decimal(str(bs.get(a) or 0)) > 0]
            for period, bs in balances.items() if bs is not None}


def plan_chunks(rows, max_chars=None):
    """No source row is truncated or filtered, including narrative note pages.

    At boundaries carry document/section/column headings, ledger ancestors and
    the preceding rows. Context copies retain captions but have no usable cells.
    A single oversized row is an explicit failed unit; later rows still run.
    """
    limit = min(max_chars or CHUNK_CHARS, de.MAX_SOURCE_CHARS)
    reserve = min(CONTEXT_CHARS, limit // 4)
    primary_limit = limit - reserve
    chunks, start, used = [], 0, 0
    for index, row in enumerate(rows):
        size = len(de.source_line(row)) + 1
        if used and used + size > primary_limit:
            chunks.append(SearchChunk(len(chunks), rows[start:index], []))
            start, used = index, 0
        if size > primary_limit:
            chunks.append(SearchChunk(len(chunks), [row], [], 'source_row_too_large' if size > limit else None))
            start, used = index + 1, 0
        else:
            used += size
    if used:
        chunks.append(SearchChunk(len(chunks), rows[start:], []))

    previous, headings, ancestors = [], {}, {}
    for chunk in chunks:
        primary_ids = {r.id for r in chunk.primary}
        relevant = []
        for row in chunk.primary:
            code = row.code.replace('/', '.').split('.*', 1)[0]
            parts = code.split('.')
            for depth in range(1, len(parts)):
                ancestor = ancestors.get((row.side, '.'.join(parts[:depth])))
                if ancestor:
                    relevant.append(ancestor)
        candidates = list(headings.values()) + relevant + previous[-12:]
        seen, context_size = set(), 0
        room = min(reserve, limit - sum(len(de.source_line(r)) + 1 for r in chunk.primary))
        for row in candidates:
            if row.id in seen or row.id in primary_ids:
                continue
            seen.add(row.id)
            context = replace(row, id='context:' + row.id, text='CONTESTO NON CITABILE: ' + row.text,
                              amounts=(), positions=(), kinds=())
            size = len(de.source_line(context)) + 1
            if context_size + size <= room:
                chunk.context.append(context)
                context_size += size
        for row in chunk.primary:
            upper = row.text.upper()
            for name, pattern in (
                ('period', r'CORRENTE.*(?:PRECEDENTE|COMPARATO)|\d{2}[-/]\d{2}[-/]20\d{2}'),
                ('statement', r'STATO PATRIMONIALE|CONTO ECONOMICO|NOTA INTEGRATIVA'),
                ('family', r'RIMANENZE|CREDITI|DEBITI'),
                ('columns', r'VALORE.*(?:INIZIO|FINE)|ENTRO.*OLTRE'),
            ):
                if not row.code and len(row.text) < 500 and re.search(pattern, upper):
                    headings[name] = row
            if row.code:
                ancestors[row.side, row.code.replace('/', '.').split('.*', 1)[0]] = row
        previous.extend(chunk.primary)
    return chunks


def search_details(rows, balances, fiscal_year, *, reader=None, max_chars=None, max_seconds=None):
    reader = reader or de.read_details
    chunks = plan_chunks(rows, max_chars)
    families = active_families(balances)
    allowed = {(period, a) for period, aa in families.items() for a in aa}
    try:
        budget = float(os.environ.get('PDF_DETAIL_SEARCH_SECONDS', SEARCH_SECONDS)) if max_seconds is None else max_seconds
        if not 0 < budget <= 3600:
            raise ValueError('invalid budget')
    except (TypeError, ValueError):
        budget = SEARCH_SECONDS
    deadline = time.monotonic() + budget

    def run(chunk):
        audit = {'index': chunk.index, 'first_row': chunk.primary[0].id,
                 'last_row': chunk.primary[-1].id, 'rows': len(chunk.primary),
                 'pages': sorted({r.page for r in chunk.primary}),
                 'context_rows': [r.id.removeprefix('context:') for r in chunk.context]}
        if chunk.error or time.monotonic() >= deadline:
            return [], {**audit, 'status': 'not_searched', 'reason': chunk.error or 'time_budget_exhausted'}
        try:
            reading = reader(chunk.context + chunk.primary, balances, fiscal_year)
            owned = {r.id: r for r in chunk.primary}
            proposals, rejected = [], 0
            for proposal in reading.proposals:
                if (proposal.period, proposal.aggregate) not in allowed:
                    rejected += max(1, len(proposal.items))
                    continue
                items = []
                for item in proposal.items:
                    row = owned.get(item.row)
                    if (row is None or item.column >= len(row.amounts)
                            or item.field not in de.ANALYTICAL_FAMILIES[proposal.aggregate]):
                        rejected += 1
                    else:
                        items.append(item)
                if items:
                    proposals.append(proposal.model_copy(update={'items': items}))
            return proposals, {**audit, 'status': 'partial' if rejected else 'completed',
                               'invalid_references': rejected, 'proposals': len(proposals)}
        except Exception as exc:
            # Exception messages may contain API credentials/request content.
            # Persist only the type and continue with other pages.
            return [], {**audit, 'status': 'failed', 'reason': (
                exc.reason if isinstance(exc, de.DetailReadError) else type(exc).__name__)}

    # Notes are often at the end. Start there and at the beginning concurrently
    # so a time budget cannot consistently starve the supplementary tables.
    scheduled = chunks[-1:] + chunks[:-1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, scheduled))
    results.sort(key=lambda item: item[1]['index'])
    proposals, seen = [], set()
    for found, _ in results:
        for proposal in found:
            items = []
            for item in proposal.items:
                key = (proposal.period, proposal.aggregate, item.field, item.row, item.column)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
            if items:
                proposals.append(proposal.model_copy(update={'items': items}))
    audits = [audit for _, audit in results]
    completed = sum(a['status'] == 'completed' for a in audits)
    report = {'status': 'complete' if audits and completed == len(audits) else 'partial' if any(
                  a['status'] in ('completed', 'partial') for a in audits) else 'not_searched',
              'scope': 'all_extracted_rows_not_visual_page_verification',
              'rows_total': len(rows), 'rows_completed': sum(a['rows'] for a in audits if a['status'] == 'completed'),
              'chunks_planned': len(chunks), 'chunks_completed': completed,
              'chunks': audits, 'time_budget_seconds': budget}
    return de.DetailReading(proposals=proposals), report


def finish_search_report(report, balances, proposals=()):
    """Distinguish coverage from accounting acceptance for EVERY active family."""
    search = report.setdefault('search', {'status': 'not_searched', 'reason': report.get('reason', 'unavailable'),
                                          'rows_total': report.get('source_rows_total'), 'rows_completed': 0,
                                          'chunks_planned': 0, 'chunks_completed': 0, 'chunks': []})
    if not any(active_families(balances).values()):
        search['status'] = 'not_applicable'
        report['warnings'] = []
        return report
    warnings = []
    incomplete = search['status'] != 'complete'
    if incomplete:
        reason = search.get('reason') or report.get('reason') or 'blocchi non completati o riferimenti non validi'
        warnings.append('RICERCA DETTAGLI NON COMPLETA: ' + reason +
                        '. I dettagli non trovati non sono dichiarati assenti; il residuo resta nel contenitore previsto.')
    for period, aggregates in active_families(balances).items():
        period_report = report.setdefault('periods', {}).setdefault(period, {'families': {}, 'rejected': []})
        outcomes = {}
        for aggregate in aggregates:
            accepted = period_report.get('families', {}).get(aggregate, {}).get('evidence', [])
            proposed = sum(len(p.items) for p in proposals if p.period == period and p.aggregate == aggregate)
            outcome = ('details_accepted' if accepted else 'proposals_not_accepted' if proposed else
                       'unknown' if incomplete else 'no_details_found')
            outcomes[aggregate] = {'status': search['status'], 'outcome': outcome,
                                   'proposed_cells': proposed, 'accepted_cells': len(accepted)}
            if proposed and not accepted:
                warnings.append(f'DETTAGLI NON APPLICATI [{period}/{aggregate}]: proposte non riconciliate; consultare i motivi di rifiuto.')
        period_report['search_families'] = outcomes
    report['warnings'] = warnings
    return report
