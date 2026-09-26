"""A02 (lotto 2 fix rilievi, 2026-09-26): il BEP degli anni di piano viene da
`ForecastYear.engine_meta['pareggio']` del motore, mai più dalla ripartizione
60/40 (o quella delle ipotesi) lato report. File separato da
`test_fix_rilievi_report.py`, in modifica concorrente da un altro agente su
questo stesso giro (Task 3, stesso lotto)."""
from decimal import Decimal as D

import pytest

from tests.rilievi_kit import genera, generato, piano, righe

_PAREGGIO_KEYS = ("fixed_costs", "variable_costs", "contribution_margin", "break_even_revenue", "safety_margin_pct")


def _bp():
    pytest.importorskip("backend.app.renderers.business_plan.data")


def test_bep_con_engine_meta_null_e_dichiarato_non_ricalcolato():
    """(b) Un anno di piano con `engine_meta` NULL (via `ritocca`): `data.v('bep')`
    di quell'anno è `None`, e la serie strutturale `break_even` del report dichiara
    `engine_meta_missing` su ogni sua chiave — mai un numero ricalcolato con la
    quota 60/40. Gli altri anni di piano, non toccati dal ritocco, restano
    dichiarati dal motore."""
    _bp()

    def ritocca(db, scenario_id):
        from database.models import ForecastYear
        row = db.query(ForecastYear).filter_by(scenario_id=scenario_id, year=2028).one()
        row.engine_meta = None

    e = generato(genera(righe(), report=True, ritocca=ritocca))
    assert piano(e.data, "bep")[e.data.plan_years.index(2028)] is None
    for year in (2027, 2029):
        assert piano(e.data, "bep")[e.data.plan_years.index(year)] is not None, year

    group_be = next(g for g in e.rep.structure_series if g.id == "break_even")
    period_idx = next(i for i, p in enumerate(group_be.periods) if p.year == 2028)
    series_be = {s.id: s for s in group_be.series}
    for key in _PAREGGIO_KEYS:
        assert series_be[key].values[period_idx] is None, key
        assert series_be[key].unavailable_reasons[period_idx] == "engine_meta_missing", key


def test_bep_del_piano_riporta_i_valori_dichiarati_dal_motore():
    """Controparte positiva: senza ritocchi, `costi_variabili`/`fixed_costs`/`bep`
    del report coincidono (a meno di arrotondamento) con
    `ForecastYear.engine_meta['pareggio']` persistito — non con una quota fissa di
    default. Su AMBIENTA `costi_fissi_operativi` ≠ `costi_fissi` (ce03 lavori
    interni e ce04 altri ricavi non sono zero nella base): una mappatura sbagliata
    di `fixed_costs` su `costi_fissi` invece che su `costi_fissi_operativi`
    farebbe fallire l'assert sotto, non solo "un numero diverso per caso"."""
    _bp()
    e = generato(genera(righe(), report=True))
    group_be = next(g for g in e.rep.structure_series if g.id == "break_even")
    series_be = {s.id: s for s in group_be.series}
    for year in (2027, 2028, 2029):
        idx = next(i for i, p in enumerate(group_be.periods) if p.year == year)
        par = e.meta[year]["pareggio"]
        assert par is not None, year
        assert D(par["costi_fissi_operativi"]) != D(par["costi_fissi"]), year
        assert series_be["variable_costs"].values[idx] == D(par["costi_variabili"]), year
        assert series_be["fixed_costs"].values[idx] == D(par["costi_fissi_operativi"]), year
        assert series_be["break_even_revenue"].values[idx] == D(par["fatturato_pareggio"]), year


def test_f5_colonna_base_stessa_regola_del_motore_niente_finto_risanamento():
    """F5 (decisione del proprietario, 2026-09-26): a crescita zero la colonna base del pareggio
    usa la STESSA regola del motore (`calculations.projection_common.punto_di_pareggio`), con le
    quote fisso/variabile del PRIMO anno di piano — mai più il 40% spalmato sulle cinque voci
    operative canoniche (`calculate_break_even_analysis`), che su AMBIENTA (righe() a crescita
    zero) dava un margine di sicurezza NEGATIVO in base (-4,31%, misurato con la vecchia formula:
    costi 4.178.596 × 40%/60%, MdC 38,99%, bep 4.286.693) contro un piano positivo (4,81%): un
    finto risanamento che il testo raccontava come «negativo nel 2026 ... positivo dal 2027».
    Oracolo: i costi variabili di base coincidono ESATTAMENTE con quelli del primo anno di piano
    (ogni ipotesi di crescita è a zero, ce05/ce06 non cambiano), e il margine di sicurezza di base
    è ora positivo come il piano — niente più «diventa positivo dal»."""
    _bp()
    from backend.app.renderers.business_plan import narrative
    e = generato(genera(righe(), report=True))
    group_be = next(g for g in e.rep.structure_series if g.id == "break_even")
    series_be = {s.id: s for s in group_be.series}
    base_idx = next(i for i, p in enumerate(group_be.periods) if p.basis == "historical")
    piano_idx = next(i for i, p in enumerate(group_be.periods) if p.year == 2027)
    assert series_be["variable_costs"].values[base_idx] == series_be["variable_costs"].values[piano_idx]
    ms_base = e.data.v("margine_sicurezza")[0]
    ms_piano = e.data.v("margine_sicurezza")[e.data.plan_idx[0]]
    assert ms_base > 0, ms_base
    assert ms_piano > 0, ms_piano
    testo = " ".join(t for _, t in narrative.key_points(e.data))
    assert "diventa positivo dal" not in testo, testo
