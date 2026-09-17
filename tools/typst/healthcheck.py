#!/usr/bin/env python3
"""M2-06B — offline compile smoke for the Docker HEALTHCHECK.

Renders the `runtime-smoke` template bundle through the real, sandboxed
`TypstRenderer` (`TypstRenderer.from_project`, per
`backend/app/renderers/typst/runtime.py`) on a synthetic `FinalReportModelV2`.
The model is built exactly the way `tests/test_final_report_v2.py::fixture_report`
builds one for the integration tests, using only production modules
(`app.schemas.final_report`, `app.services.final_report_dossier`,
`database.models`) plus the small fixture this script ships beside it
(`healthcheck-fixture.json`, a copy of `tests/fixtures/final_report/bilancio.json`
— never the `tests/` package, which is not part of the image). No pytest, no
network, no database connection (SQLAlchemy engine creation is lazy; nothing
here executes a query).

Exit 0 means the compiler, the bundle and the Bubblewrap sandbox all work end
to end. A non-zero exit is what a container whose seccomp/AppArmor profile
forbids `--unshare-user` looks like: see docs/deployment/TYPST-RENDERER.md.

Usage: `python tools/typst/healthcheck.py` (run from anywhere; paths are
resolved from this file's location, not from the current directory).
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]  # tools/typst/healthcheck.py -> tools/typst -> tools -> project root
FIXTURE = HERE.with_name('healthcheck-fixture.json')

for candidate in (str(ROOT), str(ROOT / 'backend')):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def _synthetic_report():
    from app.schemas.final_report import FinalReportModel
    from app.schemas.final_report_v2 import StatementPeriod
    from app.services.final_report_dossier import DossierSource, extend_dossier
    from database.models import BalanceSheet, IncomeStatement

    raw = json.loads(FIXTURE.read_text(encoding='utf-8'))
    report = FinalReportModel.model_validate(raw, context={'skip_hash_validation': True})
    sources = []
    for year in report.forecast.years:
        bs = {c.name: Decimal('0') for c in BalanceSheet.__table__.columns if c.name.startswith('sp')}
        inc = {c.name: Decimal('0') for c in IncomeStatement.__table__.columns if c.name.startswith('ce')}
        bs.update({('sp09_disponibilita_liquide' if l.code == 'cash' else l.code): l.value for l in year.balance_sheet})
        inc.update({('ce01_ricavi_vendite' if l.code == 'revenue' else l.code): l.value for l in year.income_statement})
        sources.append(DossierSource(
            StatementPeriod(id=f'forecast:{year.year}', year=year.year, label=str(year.year),
                             basis='forecast', period_months=12, source='synthetic_fixture'),
            bs, inc, fixed_split=(Decimal('40'), Decimal('40'))))
    return extend_dossier(report, sources)


def main() -> int:
    from app.renderers.typst import RendererError, TypstRenderer

    try:
        renderer = TypstRenderer.from_project(ROOT)
        report = _synthetic_report()
        artifact = renderer.render(report)
    except RendererError as error:
        print(f'typst healthcheck: FAILED category={error.category}', file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001 - any other failure is also a hard-fail for the health check
        print(f'typst healthcheck: FAILED unexpected={error.__class__.__name__}: {error}', file=sys.stderr)
        return 1
    print(f'typst healthcheck: ok pages={artifact.page_count} compiler={artifact.compiler_version} '
          f'elapsed_ms={int(artifact.duration_seconds * 1000)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
