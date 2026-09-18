"""Le imposte del previsionale secondo il commercialista (2026-09-18).

Spec: docs/superpowers/specs/2026-09-18-imposte-commercialista-design.md.
Base: l'anno ricco della rete con 20.000 di crediti tributari nel consuntivo
(`test_forecast_override_tributario._base_tributi`).
"""
from decimal import Decimal as D

from tests.e2e_kit import memory_sessions
from tests.test_forecast_override_tributario import CREDITO_BASE, _figlia, _genera


def _run(user, **kw):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            return _genera(db, user, **kw)
    finally:
        engine.dispose()


def test_crediti_del_consuntivo_restano_costanti(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    righe = _run("ic-costanti")
    for y in (2027, 2028):
        imposte = righe[y][2]["imposte"]
        assert imposte["crediti_tributari_consuntivo"] == CREDITO_BASE, y
        assert _figlia(righe, y, "sp06e_crediti_tributari_breve") \
            == CREDITO_BASE + D(str(imposte["generated_credit"])), y
    # Primo anno: il credito del consuntivo non si compensa (non e' credito da acconti).
    assert righe[2027][2]["imposte"]["credito_compensato"] == D("0")


def test_credito_da_acconti_si_compensa_e_non_si_accumula(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # 2027: acconti espliciti molto sopra l'imposta dell'anno → chiude a credito.
    righe = _run("ic-compensa", per_anno={2027: {"tax_advances_paid": 60000}})
    i27, i28 = righe[2027][2]["imposte"], righe[2028][2]["imposte"]
    credito_27 = D(str(i27["generated_credit"]))
    assert credito_27 > 0
    assert D(str(i28["credito_compensato"])) == credito_27
    assert D(str(i28["opening_credit_left"])) == D("0")
    # Il 2028 porta solo il consuntivo piu' il SUO credito: quello del 2027 e' chiuso.
    assert _figlia(righe, 2028, "sp06e_crediti_tributari_breve") \
        == CREDITO_BASE + D(str(i28["generated_credit"]))



def test_l_aliquota_scritta_e_quella_applicata_anche_con_storico():
    """Prima l'aliquota effettiva dell'anno base vinceva in silenzio su `tax_rate`
    quando era derivabile (qui 30%). Ora `tax_rate` e' la proposta accettata o
    cambiata dall'utente, e il motore la applica cosi' com'e' (salvo `ce20_override`)."""
    from types import SimpleNamespace as NS
    from calculations.forecast_engine import ForecastEngine
    base = NS(ce01_ricavi_vendite=D("100000"), ce20_imposte=D("30000"))   # pbt 100.000, effettiva 30%
    proiettato = NS(ce01_ricavi_vendite=D("200000"))                     # pbt 200.000
    ipotesi = NS(tax_rate=D("24"), ce20_override=None, tax_temporary_differences=None)
    corrente, _, totale = ForecastEngine._tax_components(base, proiettato, ipotesi)
    assert corrente == D("48000.00")
    assert totale == D("48000.00")
    ipotesi.ce20_override = D("1234")
    assert ForecastEngine._tax_components(base, proiettato, ipotesi)[2] == D("1234")


def test_le_anticipate_non_passano_dal_conto_economico(monkeypatch):
    """Griglia delle differenze temporanee e crescita di `sp06f` non muovono piu'
    niente: le anticipate restano quelle dell'anno base e `ce20` e' la sola
    imposta corrente (commercialista, 2026-09-18)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    piano = _run("ic-ant-piano")
    griglia = [{"name": "x", "kind": "deductible", "maturity": "short",
                "opening_amount": 0, "additions": 100000, "reversals": 0}]
    con = _run("ic-ant-griglia", extra_per_anno={"tutti": {
        "tax_temporary_differences": griglia, "sp06f_growth_pct": 50}})
    for y in (2027, 2028):
        assert con[y][1]["ce20_imposte"] == piano[y][1]["ce20_imposte"], y
        for campo in ("sp06f_imposte_anticipate_breve", "sp07f_imposte_anticipate_lungo",
                      "sp09_disponibilita_liquide", "sp12e_altre_riserve"):
            assert _figlia(con, y, campo) == _figlia(piano, y, campo), (y, campo)


def test_un_override_delle_anticipate_va_a_riserva_non_in_cassa(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    piano = _run("ic-ov-piano")
    con = _run("ic-ov-ant", overrides={2027: {"sp06f_imposte_anticipate_breve": 5000}})
    base_f = _figlia(piano, 2027, "sp06f_imposte_anticipate_breve")
    delta = D("5000") - base_f
    for y in (2027, 2028):   # l'override si porta avanti, e la riserva con lui
        assert _figlia(con, y, "sp06f_imposte_anticipate_breve") == D("5000.00"), y
        assert _figlia(con, y, "sp12e_altre_riserve") \
            == _figlia(piano, y, "sp12e_altre_riserve") + delta, y
        assert _figlia(con, y, "sp09_disponibilita_liquide") \
            == _figlia(piano, y, "sp09_disponibilita_liquide"), y
        assert con[y][1]["ce20_imposte"] == piano[y][1]["ce20_imposte"], y
