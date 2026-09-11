"""Lo sweep rimborsa solo il debito bancario pregresso SENZA piano, sulla cassa di dopo gli override (lotto 3A, Task 2).

Decisione 3 del proprietario: i finanziamenti con un piano seguono solo il loro piano (contratti della griglia,
`financing_amount`, pregresso con `existing_debt_repayment_years`). Lo sweep rimborsa lo scoperto (sulla cassa netta,
come prima) e il debito bancario pregresso SENZA piano, prima a breve poi a lungo; la cassa eccedente resta. Decide sulla
cassa di DOPO gli `sp_overrides` (rilievo I2 della revisione finale del lotto 2).

Oracolo: il gemello senza sweep sullo snapshot `452112d`, meno il pregresso senza piano rimborsabile dalla cassa sopra
il minimo, anno per anno.
"""
import json
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP09, SP16A, SP17A = "sp09_disponibilita_liquide", "sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo"
BREVE, LUNGO = D("12345.67"), D("23456.79")
SWEEP0 = {"cash_sweep_enabled": True, "cash_sweep_min_cash": 0}
PRESTITO = {"financing_amount": 100000.38, "financing_duration_years": 4, "financing_interest_rate": 4.35}


def _riga(anno, crescita=3, aliquota=27.9, **extra):
    riga = {"forecast_year": anno, "revenue_growth_pct": crescita, "tax_rate": aliquota}
    riga.update(extra)
    return riga


def _dec(valore):
    return D(str(valore))


def _genera(user, rows, breve=None, lungo=None):
    """`(risposta del bulk, {anno: (sp, ce, details)}, errore dell'anteprima)` dal percorso persistito.

    Con `breve`/`lungo` il debito bancario pregresso del kit (50.000 su `sp17a`) si sostituisce con quello
    dato; la cassa riassorbe la differenza.
    """
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            if breve is not None:
                fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
                b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
                delta_lungo = lungo - b.sp17a_debiti_banche_lungo
                b.sp16a_debiti_banche_breve = breve
                b.sp16_debiti_breve += breve
                b.sp17a_debiti_banche_lungo = lungo
                b.sp17_debiti_lungo += delta_lungo
                b.sp09_disponibilita_liquide += breve + delta_lungo
                db.commit()
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc)
            db.commit()
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            det = {a["year"]: a["details"] for a in prev["forecast_years"]}
            anni = {}
            if res["forecast_generated"]:
                anni = {anno: (sp, ce, det.get(anno)) for anno, sp, ce in read_forecast_maps(db, sc.id)}
            return res, anni, prev["error"]
    finally:
        engine.dispose()


def _confronta(anni, attesi, campi):
    fuori = []
    for anno, valori in attesi.items():
        sp, ce, _det = anni[anno]
        for (etichetta, dove, chiave), atteso in zip(campi, valori):
            letto = (sp if dove == "sp" else ce)[chiave]
            if letto != D(atteso):
                fuori.append(f"{anno} {etichetta}: {letto}, atteso {atteso}")
    return fuori


CAMPI_CASSA_DEBITO_ONERI = (("sp09", "sp", SP09), ("sp16a", "sp", SP16A), ("sp17a", "sp", SP17A),
                            ("ce15", "ce", "ce15_oneri_finanziari"))


def test_il_prestito_nuovo_segue_il_piano_e_la_cassa_eccedente_resta():
    """Sonda della ricognizione (voce 5), kit: 80.000 / 5 anni / 5% nel 2027, sweep a soglia zero.

    Oggi: `sp16a` e `sp17a` a 0,00 ogni anno, `ce15` 9.000 / 8.200 / 7.400 / 6.600. Dopo: quota a breve 16.000,00, il
    resto a lungo, gli stessi interessi, la cassa piu' alta del capitale non rimborsato; lo sweep paga nel 2027 i 50.000
    di pregresso senza piano del kit.
    """
    rows = [_riga(2027, financing_amount=80000, financing_duration_years=5, financing_interest_rate=5, **SWEEP0)]
    rows += [_riga(anno, **SWEEP0) for anno in (2028, 2029, 2030)]
    res, anni, errore = _genera("sweep-p5", rows)
    assert res["forecast_generated"] is True, res["message"]
    assert errore is None
    fuori = _confronta(anni, {
        2027: ("119122.22", "16000.00", "48000.00", "9000.00"),
        2028: ("223995.44", "16000.00", "32000.00", "8200.00"),
        2029: ("343211.41", "16000.00", "16000.00", "7400.00"),
        2030: ("477183.12", "16000.00", "0.00", "6600.00"),
    }, CAMPI_CASSA_DEBITO_ONERI)
    assert not fuori, "\n".join(fuori)
    debito = anni[2027][2]["debito_bancario"]
    assert _dec(debito["pregresso_senza_piano"]["rimborso_sweep"]) == D("50000.00")
    assert debito["pregresso_piano_anni"] is None
    (contratto,) = debito["contratti"]
    assert [_dec(contratto[k]) for k in ("erogato", "rimborso", "interessi", "breve", "lungo")] == [
        D("80000.00"), D("16000.00"), D("4000.00"), D("16000.00"), D("48000.00")]


def _righe_i2(scoperto, aliquota=24):
    """Caso I2 della revisione finale, kit: `sp08` forzato a 100.000 nel 2027, minimo 10.000, sweep acceso.

    Due aliquote, entrambe misurate in «Numeri ricontrollati» §1 e in `misure.md` §4.1: **24** riproduce esattamente
    la sonda della revisione finale del lotto 2, che scriveva le righe sull'ORM dove il default di colonna di
    `tax_rate` e' 24, ed e' l'aliquota con cui la spec cita gli 11.053,98 di fabbisogno. **27,9** e' l'aliquota che
    ogni schermata reale invia (CLAUDE.md, «Tax rate: the 24 in the schema is not what runs»: nessuno schermo la
    manda mai) — il caso rappresentativo del percorso di produzione, con un fabbisogno piu' alto (14.563,20: meno
    imposta pagata sull'utile ante, a parita' di crescita e di override, avrebbe lasciato piu' cassa; qui e' il
    contrario, il 27,9 sottrae piu' cassa del 24 e il fabbisogno cresce).
    """
    rows = []
    for i, anno in enumerate((2027, 2028, 2029)):
        riga = _riga(anno, crescita=3.33, aliquota=aliquota, sp06e_growth_pct=0, sp16e_growth_pct=0,
                     cash_sweep_enabled=True, cash_sweep_min_cash=10000, overdraft_allowed=scoperto)
        if i == 0:
            riga["sp_overrides"] = {"sp08_attivita_finanziarie": 100000}
        rows.append(riga)
    return rows


@pytest.mark.parametrize("scoperto", [False, True], ids=["scoperto non concesso", "scoperto concesso"])
def test_lo_sweep_decide_sulla_cassa_di_dopo_gli_override(scoperto):
    """Oggi: senza scoperto il previsionale si ferma per 11.053,98 di fabbisogno; con lo scoperto `sp17a` va a zero e
    `sp16a` porta 11.053,98 di scoperto. Dopo: la cassa post-override paga 28.946,02 di pregresso e resta al minimo."""
    res, anni, errore = _genera(f"sweep-i2-{scoperto}", _righe_i2(scoperto))
    assert res["forecast_generated"] is True, res["message"]
    assert errore is None
    fuori = _confronta(anni, {
        2027: ("10000.00", "0.00", "21053.98"),
        2028: ("113393.98", "0.00", "0.00"),
        2029: ("253860.09", "0.00", "0.00"),
    }, CAMPI_CASSA_DEBITO_ONERI[:3])
    fuori += [f"{a} scoperto_residuo {anni[a][2]['scoperto_residuo']}" for a in anni if _dec(anni[a][2]["scoperto_residuo"]) != 0]
    assert not fuori, "\n".join(fuori)
    rimborsi = [_dec(anni[a][2]["debito_bancario"]["pregresso_senza_piano"]["rimborso_sweep"]) for a in (2027, 2028, 2029)]
    assert rimborsi == [D("28946.02"), D("21053.98"), D("0.00")]


@pytest.mark.parametrize("scoperto", [False, True], ids=["scoperto non concesso", "scoperto concesso"])
def test_lo_sweep_decide_sulla_cassa_di_dopo_gli_override_aliquota_27_9(scoperto):
    """Stesso caso I2 del test gemello, con l'aliquota **27,9** che ogni schermata reale invia (CLAUDE.md, «Tax rate:
    the 24 in the schema is not what runs»): il gemello con 24 riproduce solo la sonda della revisione finale del
    lotto 2, questo e' il caso che il percorso di produzione esercita davvero. Oggi (senza il fix di questo task) il
    fabbisogno e' 14.563,20, contro gli 11.053,98 dell'aliquota 24. Dopo: la cassa post-override lo assorbe per
    intero come col 24, e il previsionale riesce con o senza scoperto concesso.

    Attesi da «Numeri ricontrollati» §1 e da `misure.md` §4.1: solo questi tre campi sono misurati la' (non i nove
    del test gemello), quindi solo questi tre si verificano — gli altri non si inventano.
    """
    res, anni, errore = _genera(f"sweep-i2-279-{scoperto}", _righe_i2(scoperto, aliquota=27.9))
    assert res["forecast_generated"] is True, res["message"]
    assert errore is None
    attesi = {2027: ("sp17a", SP17A, "24563.20"), 2028: ("sp09", SP09, "105570.37"), 2029: ("sp09", SP09, "240890.12")}
    fuori = []
    for anno, (etichetta, chiave, atteso) in attesi.items():
        letto = anni[anno][0][chiave]
        if letto != D(atteso):
            fuori.append(f"{anno} {etichetta}: {letto}, atteso {atteso}")
    assert not fuori, "\n".join(fuori)


CON_PIANO = {
    "anni di rimborso": (
        [_riga(anno, existing_debt_repayment_years=3) for anno in (2027, 2028, 2029)],
        {2027: ("82990.53", "411.52", "23456.79"), 2028: ("194013.60", "0.00", "11934.16"), 2029: ("318802.62", "0.00", "0.01")},
    ),
    "contratti col residuo iniziale": (
        [_riga(2027, financing_loans=[{"name": "Pregresso", "amount": 0, "opening_residual": 35802.46,
                                        "duration_years": 5, "interest_rate": 4}]), _riga(2028), _riga(2029)],
        {2027: ("91332.09", "5185.18", "23456.79"), 2028: ("209987.69", "0.00", "21481.48"), 2029: ("342615.76", "0.00", "14320.99")},
    ),
}


@pytest.mark.parametrize("nome", list(CON_PIANO))
def test_un_pregresso_con_un_piano_non_e_toccato_dallo_sweep(nome):
    """Base banca (12.345,67 a breve, 23.456,79 a lungo). Con un piano lo sweep a soglia zero non ha nulla da
    rimborsare: lo scenario e' identico, cella per cella, al gemello senza sweep. Oggi lo sweep chiude tutto nel 2027."""
    righe, ancore = CON_PIANO[nome]
    _res_g, gemello, _ = _genera(f"gemello-{nome}", righe, BREVE, LUNGO)
    res, sweep, _errore = _genera(f"sweep-{nome}", [dict(r, **SWEEP0) for r in righe], BREVE, LUNGO)
    assert res["forecast_generated"] is True, res["message"]
    fuori = _confronta(sweep, ancore, CAMPI_CASSA_DEBITO_ONERI[:3])
    for anno in ancore:
        sp, ce, _ = sweep[anno]
        sp_g, ce_g, _ = gemello[anno]
        fuori += [f"{anno} {k}: sweep {sp[k]}, gemello {sp_g[k]}" for k in sp if sp[k] != sp_g[k]]
        fuori += [f"{anno} {k}: sweep {ce[k]}, gemello {ce_g[k]}" for k in ce if ce[k] != ce_g[k]]
    assert not fuori, "\n".join(fuori)


def test_senza_piano_lo_sweep_paga_il_pregresso_prima_a_breve_poi_a_lungo_e_mai_il_prestito():
    """Base banca, prestito 100.000,38 / 4 anni / 4,35% nel 2027, sweep a soglia zero. Oggi `sp16a` e `sp17a` a zero."""
    rows = [_riga(2027, **PRESTITO, **SWEEP0), _riga(2028, **SWEEP0), _riga(2029, **SWEEP0)]
    res, anni, errore = _genera("sweep-senza-piano", rows, BREVE, LUNGO)
    assert res["forecast_generated"] is True, res["message"]
    fuori = _confronta(anni, {
        2027: ("129772.48", "25000.09", "50000.20", "9350.02"),
        2028: ("225680.76", "25000.09", "25000.11", "8262.51"),
        2029: ("336139.07", "25000.09", "0.02", "7175.01"),
    }, CAMPI_CASSA_DEBITO_ONERI)
    assert not fuori, "\n".join(fuori)
    senza_piano = anni[2027][2]["debito_bancario"]["pregresso_senza_piano"]
    assert [_dec(senza_piano[k]) for k in ("apertura", "rimborso_sweep", "breve", "lungo")] == [
        D("35802.46"), D("35802.46"), D("0.00"), D("0.00")]


def test_lo_sweep_paga_il_pregresso_senza_piano_solo_dopo_lo_scoperto():
    """Base banca. 2027: un investimento apre 255.075,69 di scoperto. 2028: la cassa netta lo riduce a 128.224,59,
    niente da rimborsare. 2029: chiude lo scoperto e con i 24.530,92 che restano paga tutto il breve pregresso
    (12.345,67) e 12.185,25 del lungo. Oggi il 2029 chiude con 0,01 di cassa e 11.271,55 su `sp17a`: lo sweep
    decideva sulla cassa grezza, prima del centesimo."""
    comuni = {"overdraft_allowed": True, "financing_interest_rate": 6.13}
    rows = [_riga(2027, tangible_investments=350000.37, **comuni), _riga(2028, **comuni, **SWEEP0),
            _riga(2029, **comuni, **SWEEP0)]
    res, anni, errore = _genera("sweep-dopo-scoperto", rows, BREVE, LUNGO)
    assert res["forecast_generated"] is True, res["message"]
    fuori = _confronta(anni, {
        2027: ("0.00", "267421.36", "23456.79"),
        2028: ("0.00", "140570.26", "23456.79"),
        2029: ("0.00", "0.00", "11271.54"),
    }, CAMPI_CASSA_DEBITO_ONERI[:3])
    assert not fuori, "\n".join(fuori)
    assert [_dec(anni[a][2]["scoperto_residuo"]) for a in (2027, 2028, 2029)] == [D("255075.69"), D("128224.59"), D("0")]
    senza_piano = anni[2029][2]["debito_bancario"]["pregresso_senza_piano"]
    assert [_dec(senza_piano[k]) for k in ("rimborso_sweep", "breve", "lungo")] == [D("24530.92"), D("0.00"), D("11271.54")]


def test_debito_bancario_quadra_con_sp16a_e_sp17a_su_tutta_la_griglia_del_banco(tmp_path):
    """L'invariante della spec §4.1 su ogni anno di ogni scenario del banco (seme 20260910, 4 anni): somma dei `breve`
    piu' `scoperto_residuo` = `sp16a`, somma dei `lungo` = `sp17a`, al centesimo. Gira il driver del banco
    sull'albero corrente, in un sottoprocesso."""
    from scripts import parita_motore as banco
    ingresso, uscita, driver = tmp_path / "in.json", tmp_path / "out.json", tmp_path / "driver.py"
    ingresso.write_text(json.dumps({"scenari": banco.costruisci_griglia(20260910, 4)}), encoding="utf-8")
    driver.write_text(banco.DRIVER, encoding="utf-8")
    esiti = banco.esegui_driver(Path(sys.executable), driver, banco.REPO_ROOT, ingresso, uscita)
    fuori, anni_visti = [], 0
    for sid, esito in sorted(esiti.items()):
        for anno in esito["anni"]:
            det, sp = anno["details"], anno["balance_sheet"]
            dove = f"[{sid} · {anno['anno']}]"
            if "prestiti_nuovi_quota_breve" in det:
                fuori.append(f"{dove} prestiti_nuovi_quota_breve ancora dichiarata")
            debito = det.get("debito_bancario")
            if not isinstance(debito, dict):
                fuori.append(f"{dove} debito_bancario non dichiarato")
                continue
            anni_visti += 1
            if debito.get("pregresso_senza_piano") and debito.get("pregresso_piano_anni"):
                fuori.append(f"{dove} pregresso senza piano e con anni di rimborso insieme")
            componenti = [c for c in (debito.get("pregresso_senza_piano"), debito.get("pregresso_piano_anni")) if c]
            componenti += list(debito.get("contratti") or [])
            breve = sum((D(str(c["breve"])) for c in componenti), D("0")) + D(str(det.get("scoperto_residuo") or 0))
            lungo = sum((D(str(c["lungo"])) for c in componenti), D("0"))
            if breve != D(sp[SP16A]):
                fuori.append(f"{dove} breve {breve} != sp16a {sp[SP16A]}")
            if lungo != D(sp[SP17A]):
                fuori.append(f"{dove} lungo {lungo} != sp17a {sp[SP17A]}")
    assert anni_visti >= 380, f"troppo pochi anni-scenario confrontati: {anni_visti}"
    assert not fuori, f"{len(fuori)} violazioni:\n" + "\n".join(fuori[:40])
