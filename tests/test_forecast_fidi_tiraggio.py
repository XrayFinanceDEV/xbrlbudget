"""Riutilizzo dei fidi quando la cassa va in negativo (spec 2026-09-15 §5.2-bis).

Stessa base e stesso `_genera` di `tests/test_forecast_fidi.py` (fidi 90.000, un contratto
col residuo da 330.000 con rimborsi [82.500 x 3]). Il fabbisogno dell'anno 1 e' prodotto da
un `sp_overrides` su `sp06a`: la riga e' a giorni, quindi l'importo in piu' rientra
dall'anno dopo e il colpo di cassa e' di un sol anno.

Cassa netta 2027 senza squilibrio: 371.682,22. Per un fabbisogno di ESATTAMENTE 40.000,00
l'override vale 120.000 (stock di formula) + 371.682,22 + 40.000 = 531.682,22.
"""
from decimal import Decimal as D

from tests.test_forecast_fidi import MUTUO, _genera, _rows

SP09 = "sp09_disponibilita_liquide"
SP16A = "sp16a_debiti_banche_breve"
SP06A = "sp06a_crediti_clienti_breve"
R_SQUILIBRIO = D("531682.22")


def _fidi(det, anno):
    return det[anno]["debito_bancario"]["fidi"]


def _quadra(anni, anno):
    bs = anni[anno][0]
    return bs["_total_assets"] == bs["_total_liabilities"]


def test_fabbisogno_tira_sui_fidi_senza_scoperto():
    res, anni, det, _ = _genera("tiraggio-anno1", _rows(sp_overrides={SP06A: R_SQUILIBRIO}))
    assert res["forecast_generated"] is True, res["message"]
    fidi = _fidi(det, 2027)
    assert D(str(fidi["tiraggio"])) == D("40000.00")
    assert D(str(fidi["residuo"])) == D("130000.00")
    assert D(str(fidi["affidamento"])) == D("90000.00")
    assert D(str(fidi["oltre_affidamento"])) == D("40000.00")
    avviso = det[2027]["avviso_fidi"]
    assert avviso is not None and "40.000" in avviso and "90.000" in avviso
    assert D(str(det[2027]["scoperto_residuo"])) == D("0.00")
    assert D(str(det[2027]["scoperto_generato"])) == D("0.00")
    assert anni[2027][0][SP09] == D("0.00")
    # sp16a = residuo dei fidi (90.000 + 40.000) + quota 2028 dei contratti (82.500)
    assert anni[2027][0][SP16A] == D("212500.00")
    assert _quadra(anni, 2027)
    # L'invariante Σ breve + scoperto_residuo = sp16a tiene anche col tiraggio.
    somma_breve = sum(
        (D(str(c["breve"])) for c in det[2027]["debito_bancario"]["contratti"]), D("0")
    ) + D(str(fidi["residuo"]))
    assert somma_breve + D(str(det[2027]["scoperto_residuo"])) == anni[2027][0][SP16A]


def test_l_anno_dopo_lo_sweep_rimborsa_il_tiraggio():
    rows = _rows(sp_overrides={SP06A: R_SQUILIBRIO})
    rows[1].update(cash_sweep_enabled=True, cash_sweep_min_cash=0)
    res, anni, det, _ = _genera("tiraggio-sweep", rows)
    assert res["forecast_generated"] is True, res["message"]
    fidi = _fidi(det, 2028)
    assert D(str(fidi["rimborso_sweep"])) > D("0")
    assert D(str(fidi["oltre_affidamento"])) == D("0.00")
    assert det[2028]["avviso_fidi"] is None
    # Gli oneri dell'anno 2 stanno sull'apertura di 130.000 (tiraggio compreso), al 5%.
    assert D(str(det[2028]["oneri_fidi"])) == D("6500.00")
    assert _quadra(anni, 2028)


def test_regola_ricavi_oltre_affidamento_anche_senza_fabbisogno():
    res, anni, det, _ = _genera(
        "tiraggio-ricavi", _rows(bank_lines_rule="ricavi", revenue_growth_pct=20)
    )
    assert res["forecast_generated"] is True, res["message"]
    fidi = _fidi(det, 2027)
    assert D(str(fidi["tiraggio"])) == D("0.00")
    assert D(str(fidi["residuo"])) == D("108000.00")
    assert D(str(fidi["oltre_affidamento"])) == D("18000.00")
    assert det[2027]["avviso_fidi"] is not None and "18.000" in det[2027]["avviso_fidi"]
    assert anni[2027][0][SP09] >= D("0.00")


def test_override_sp16a_con_fabbisogno_si_rifiuta():
    res, *_ = _genera("tiraggio-override", _rows(
        sp_overrides={SP06A: R_SQUILIBRIO, SP16A: D("172500")}
    ))
    assert res["forecast_generated"] is False
    assert "Fidi e anticipi incompatibili" in res["message"]


def test_fuori_dal_regime_il_fabbisogno_solleva_com_prima():
    rows = [
        {"forecast_year": 2027, "tax_rate": 27.9, "revenue_growth_pct": 0,
         "financing_loans": [MUTUO], "sp_overrides": {SP06A: R_SQUILIBRIO}},
        {"forecast_year": 2028, "tax_rate": 27.9, "revenue_growth_pct": 0},
        {"forecast_year": 2029, "tax_rate": 27.9, "revenue_growth_pct": 0},
    ]
    # Fuori dal regime i 420.000 di banche non sono descrivibili con un contratto
    # da 330.000: l'anno base qui ha 82.500 a breve e 247.500 oltre.
    res, anni, det, _ = _genera("tiraggio-no-regime", rows, breve=D("82500"))
    assert res["forecast_generated"] is False
    assert "Fabbisogno finanziario scoperto" in res["message"]
    # Fuori dal regime nessuna chiave nuova: nient'altro che il messaggio di sempre.
    assert all("avviso_fidi" not in d for d in det.values())
    assert all((d.get("debito_bancario") or {}).get("fidi") is None for d in det.values())
