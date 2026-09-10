"""Rilievo I3 della revisione finale: il residuo di quadratura atterrava su
`sp16c`/`sp17c` (obbligazioni) — su scenari SENZA piano e SENZA indicizzazione,
e con segno negativo su aziende che di obbligazioni non ne hanno.

La causa era doppia, e doppia e' la prova:

* **(a)** `compute_forecast` includeva `_declared_sp_fields()` in `forced_fields`
  **sempre**, congelando cosi' le 8 righe dei quattro saldi anche quando nessun
  piano le scriveva: con il secchio `sp16g` forzato e `a` protetto, il cammino a
  ritroso posava il residuo sul primo campo libero — `sp16c`, un confine PFN e
  (dopo questo lotto) il confine operativo/finanziario del rendiconto. La
  sonda 40f0332 vs head su uno scenario a 5 anni, via tributaria manuale, senza
  piano ne' indicizzazione, misurava la divergenza su 6 percentuali di crescita
  su 8 (G=1,11 → +0,01/+0,02 dal 2028; G=2,22 → −0,01…−0,02; G=7,77 → −0,01 per
  quattro anni). Qui si fissa il lato pulito: su quello scenario `sp16c`/`sp17c`
  e gli altri finanziari NON SI MUOVONO MAI, e ogni posatura finita in
  `residuo_quadratura` nomina solo il proprio secchio o il proprio aggregato.

* **(b)** Il ripiego del cammino ora esclude PER CATEGORIA `a`/`b`/`c`
  (`_BANK_DEBT_FIELDS_SP16`/`_SP17`), e quando non resta nessun operativo libero
  il residuo non torna piu' sul secchio (che forzato e' per definizione):
  segue la somma delle righe nell'AGGREGATO, perche' l'aggregato del gruppo
  DEBITI E' la loro somma (riga `sp16 = sp16a + … + sp16g`). Ma questo vale
  solo se l'aggregato stesso non e' forzato: un `sp_overrides` su `sp16` fissa
  il totale, e li' il centesimo resta al secchio, dichiarato.
"""
from decimal import Decimal as D

import pytest

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from calculations.forecast_engine import ForecastEngine
from tests.e2e_kit import memory_sessions, read_forecast_maps

from tests.test_forecast_dichiarato_vs_persistito import (
    _base_year, INVESTIMENTI_SOTTO_CENTESIMO, PIANI,
)

# Le righe FINANZIARIE dei due gruppi: mai destinazione di un residuo.
_FINANZIARIE = (
    "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
    "sp16c_debiti_obbligazioni_breve", "sp17a_debiti_banche_lungo",
    "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo",
)
_DESTINAZIONI_AMMESSE = {
    "sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo",
    "sp16d_debiti_fornitori_breve", "sp17d_debiti_fornitori_lungo",
    "sp16e_debiti_tributari_breve", "sp17e_debiti_tributari_lungo",
    "sp16f_debiti_previdenza_breve", "sp17f_debiti_previdenza_lungo",
    "sp16_debiti_breve", "sp17_debiti_lungo",   # reintegro dell'aggregato
}


@pytest.mark.parametrize("crescita", ["1.11", "2.22", "7.77"])
def test_scenario_quinquennale_legacy_i_finanziari_non_si_muovono_mai(monkeypatch, crescita):
    """Lo scenario esatto della sonda della revisione: fixture con massa su ogni
    voce (il `_base_year` della batteria dichiarato-vs-persistito), 5 anni, via
    tributaria MANUALE (le tre percentenze `sp*e_growth_pct` a zero), nessun
    piano, nessuna indicizzazione, nessuno scoperto. Un atterraggio su una riga
    diversa dal proprio secchio/aggregato appare in `residuo_quadratura` — e li'
    i nomi dei sei finanziari non devono comparire MAI. (La sonda della
    revisione misurava il centesimo anche su questo percorso; qui non si
    riproduce: senza rate a terzi l'aggregato coincide col totale delle righe
    al centesimo e il residuo e' zero — il test resta come guardia, il red
    lo porta il test col piano qui sotto.)"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    user = f"i3-legacy-{crescita}"
    try:
        with sessions() as db:
            company_id = _base_year(db, user)
            rows = [
                {"forecast_year": y, "revenue_growth_pct": D(crescita),
                 "sp06e_growth_pct": 0, "sp16e_growth_pct": 0, "sp17e_growth_pct": 0,
                 **INVESTIMENTI_SOTTO_CENTESIMO}
                for y in range(2027, 2032)
            ]
            sc = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="i3", base_year=2026,
                                     scenario_type="budget"),
                user_id=user, db=db)
            res = budget_scenarios.bulk_upsert_assumptions(
                company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
                user_id=user, db=db)
            assert res["forecast_generated"] is True, res["message"]
            for _year, bs, _ce in read_forecast_maps(db, sc.id):
                # Il fixture non ha obbligazioni: devono restarci a zero per sempre.
                for campo in _FINANZIARIE:
                    if campo.endswith("obbligazioni_breve") or campo.endswith("obbligazioni_lungo"):
                        assert bs[campo] == D("0.00"), \
                            f"{campo} si e' mosso: {bs[campo]}"
            prev = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=user, db=db)
            for anno in prev["forecast_years"]:
                for posa in anno["details"].get("residuo_quadratura") or []:
                    assert posa["campo"] in _DESTINAZIONI_AMMESSE, (
                        f"{anno['year']}: residuo {posa['importo']} posato su "
                        f"{posa['campo']} — fuori dal gruppo operativo")
    finally:
        engine.dispose()


@pytest.mark.parametrize("nome_piano", ["altri debiti", "fornitori + tributari"])
@pytest.mark.parametrize("crescita", ["1.11", "3.33"])
def test_piano_quinquennale_il_residuo_non_raggiunge_i_finanziari(
        monkeypatch, nome_piano, crescita):
    """La riproduzione esatta della misura della revisione: piano con rate a
    terzi (le uniche che producono frazioni sotto il centesimo), 5 anni.
    Sulla testa precedente il `residuo_quadratura` nomina
    `sp16c_debiti_obbligazioni_breve` per −0,01 (misurato: 2027/2028 su
    entrambi i piani) — debito obbligazionario NEGATIVO su un'azienda che non
    ne ha, scritto da un centesimo di arrotondamento. Qui si fissa che nessun
    finanziario riceve posature e che le obbligazioni restano a zero."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    user = f"i3-piano-{nome_piano}-{crescita}"
    try:
        with sessions() as db:
            company_id = _base_year(db, user)
            rows = [{"forecast_year": y, "revenue_growth_pct": D(crescita)}
                    for y in range(2027, 2032)]
            rows[0]["pregresso"] = PIANI[nome_piano]
            sc = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="i3p", base_year=2026,
                                     scenario_type="budget"),
                user_id=user, db=db)
            res = budget_scenarios.bulk_upsert_assumptions(
                company_id, sc.id, request={"assumptions": rows, "auto_generate": True},
                user_id=user, db=db)
            assert res["forecast_generated"] is True, res["message"]
            prev = budget_scenarios.preview_forecast_route(
                company_id, sc.id, request={"assumptions": rows}, user_id=user, db=db)
            for anno in prev["forecast_years"]:
                for posa in anno["details"].get("residuo_quadratura") or []:
                    assert posa["campo"] not in _FINANZIARIE, (
                        f"{anno['year']}: residuo {posa['importo']} posato su "
                        f"{posa['campo']} — il cammino raggiunge ancora il "
                        f"debito finanziario")
            for _year, bs, _ce in read_forecast_maps(db, sc.id):
                assert bs["sp16c_debiti_obbligazioni_breve"] == D("0.00"), \
                    f"{_year}: obbligazioni a {bs['sp16c_debiti_obbligazioni_breve']}"
                assert bs["sp17c_debiti_obbligazioni_lungo"] == D("0.00"), \
                    f"{_year}: obbligazioni lunghe a {bs['sp17c_debiti_obbligazioni_lungo']}"
    finally:
        engine.dispose()


# ── (b) la regola del reintegro, in laboratorio ──
#
# Stessa palestra di `test_forecast_residuo_sp16a_sp17a.py`: la normalizzazione
# chiamata diretta, senza DB. Qui si fissa PERO' il discrimine nuovo: il
# reintegro dell'aggregato scatta quando NON RESTA nessun operativo libero,
# e non scatta (non deve scattare) se ne resta uno: il centesimo va a lui,
# che e' il comportamento di sempre.

_DETTAGLI_16 = {
    "sp16a_debiti_banche_breve": D("1000.00"),
    "sp16b_debiti_altri_finanz_breve": D("200.00"),
    "sp16c_debiti_obbligazioni_breve": D("300.00"),
    "sp16d_debiti_fornitori_breve": D("4000.00"),
    "sp16e_debiti_tributari_breve": D("500.00"),
    "sp16f_debiti_previdenza_breve": D("600.00"),
    "sp16g_altri_debiti_breve": D("700.00"),
}
_RESIDUO = D("0.03")


def _valori_16():
    v = dict(_DETTAGLI_16)
    v["sp16_debiti_breve"] = sum(_DETTAGLI_16.values(), D("0")) + _RESIDUO
    return v


def test_operativo_libero_il_residuo_va_a_lui_non_all_aggregato():
    """Con `d`/`e`/`g` forzati ma `f` libero, il residuo va su `f`: il
    reintegro dell'aggregato e' il ripiego dei ripieghi, non la prima scelta."""
    forzati = frozenset({
        "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve",
        "sp16d_debiti_fornitori_breve", "sp16e_debiti_tributari_breve",
        "sp16g_altri_debiti_breve", "sp16a_debiti_banche_breve",
    })
    esito = ForecastEngine._normalize_balance_sheet_cents(
        _valori_16(), forced_fields=forzati, recompute_cash=False,
    )
    assert esito["sp16f_debiti_previdenza_breve"] == D("600.00") + _RESIDUO
    assert esito["sp16_debiti_breve"] == sum(_DETTAGLI_16.values(), D("0")) + _RESIDUO


def test_aggregato_forzato_il_residuo_torna_al_secchio_dichiarato():
    """Con il gruppo interamente forzato E l'aggregato fissato da uno
    `sp_overrides` su `sp16`, l'aggregato non si muove: il centesimo resta sul
    secchio e lo dichiara `residuo_quadratura` — posatura onesta, non silente."""
    forzati = frozenset(_DETTAGLI_16) | {"sp16_debiti_breve"}
    details = {}
    esito = ForecastEngine._normalize_balance_sheet_cents(
        _valori_16(), forced_fields=forzati, recompute_cash=False, details=details,
    )
    assert esito["sp16_debiti_breve"] == sum(_DETTAGLI_16.values(), D("0")) + _RESIDUO
    assert esito["sp16g_altri_debiti_breve"] == D("700.00") + _RESIDUO
    assert details["residuo_quadratura"] == [{"campo": "sp16g_altri_debiti_breve",
                                              "importo": _RESIDUO}]


def test_reintegro_dell_aggregato_quando_non_resta_niente_libero():
    """Gruppo interamente forzato, aggregato NO: segue la somma delle righe,
    e la posatura nomina l'aggregato (chiave dichiarata anche qui)."""
    forzati = frozenset(_DETTAGLI_16)
    details = {}
    esito = ForecastEngine._normalize_balance_sheet_cents(
        _valori_16(), forced_fields=forzati, recompute_cash=False, details=details,
    )
    assert esito["sp16_debiti_breve"] == sum(_DETTAGLI_16.values(), D("0"))
    for campo, val in _DETTAGLI_16.items():
        assert esito[campo] == val, f"{campo} mosso: {esito[campo]} != {val}"
    assert details["residuo_quadratura"] == [{"campo": "sp16_debiti_breve",
                                              "importo": -_RESIDUO}]
