"""Indicatori della crisi d'impresa in Python (`calculations/crisi_impresa.py`).

Portati da `frontend/lib/pratica-indicators.ts` (calcolo, punteggio, rating):
i casi sono quelli di `pratica-indicators.test.ts`, stessi fixture e stessi
numeri attesi, perche' il motore TS si cancella dopo questo porto e questi
test diventano l'unica rete sul calcolo.
"""
from decimal import Decimal

import pytest

from calculations.crisi_impresa import (
    CHIAVI_PUNTEGGIO,
    INDICATORI,
    calcola_indicatori,
    indicatori_come_mappa,
    punteggi_crisi,
    punteggio,
    rating_crisi,
)

D = Decimal

# Azienda sana: utile, poco debito, buona liquidita'.
BS_SANA = {
    "sp02_immob_immateriali": 20_000,
    "sp03_immob_materiali": 300_000,
    "sp05_rimanenze": 150_000,
    "sp06_crediti_breve": 250_000,
    "sp09_disponibilita_liquide": 80_000,
    "sp11_capitale": 100_000,
    "sp12_riserve": 250_000,
    "sp13_utile_perdita": 90_000,
    "sp16_debiti_breve": 260_000,
    "sp16a_debiti_banche_breve": 60_000,
    "sp17_debiti_lungo": 100_000,
    "sp17a_debiti_banche_lungo": 100_000,
}
CE_SANA = {
    "ce01_ricavi_vendite": 1_200_000,
    "ce05_materie_prime": 400_000,
    "ce06_servizi": 300_000,
    "ce08_costi_personale": 250_000,
    "ce09_ammortamenti": 50_000,
    "ce15_oneri_finanziari": 12_000,
    "ce20_imposte": 30_000,
}
BS_CON_SP07 = {**BS_SANA, "sp07_crediti_lungo": 120_000}


def close(a, b, places=6):
    return abs(D(a) - D(b)) < D(10) ** -places


class TestCalcolo:
    ind = calcola_indicatori(BS_SANA, CE_SANA)

    def test_ogni_valore_e_decimal(self):
        for valore in self.ind:
            assert isinstance(valore, Decimal)

    def test_ebitda_esclude_gli_ammortamenti(self):
        assert self.ind.ebitda_raw == D(250_000)

    def test_margine_ebitda_in_percentuale_assoluta(self):
        assert close(self.ind.ebitda_margin, D(250_000) / D(1_200_000) * 100)

    def test_bilancio_vuoto_non_solleva(self):
        vuoto = calcola_indicatori({}, {})
        assert all(v == 0 for v in vuoto)

    def test_sp07_entra_nel_totale_attivo(self):
        con = calcola_indicatori(BS_CON_SP07, CE_SANA)
        assert close(con.indipendenza, D(440_000) / D(920_000) * 100)
        assert close(con.roi, D(200_000) / D(920_000) * 100)

    def test_sp07_non_entra_nel_circolante(self):
        con = calcola_indicatori(BS_CON_SP07, CE_SANA)
        assert close(con.current_ratio, D(480_000) / D(260_000))

    def test_pfn_dai_soli_debiti_bancari_quando_ci_sono(self):
        # 60.000 + 100.000 di banche meno 80.000 di cassa
        assert self.ind.pfn == D(80_000)

    def test_pfn_senza_dettaglio_usa_il_totale_dei_debiti(self):
        bs = {"sp16_debiti_breve": 300, "sp17_debiti_lungo": 200, "sp09_disponibilita_liquide": 50}
        assert calcola_indicatori(bs, {}).pfn == D(450)

    def test_pfn_con_dettaglio_non_bancario_sottrae_il_noto(self):
        bs = {"sp16_debiti_breve": 300, "sp16d_debiti_fornitori_breve": 100,
              "sp17_debiti_lungo": 200, "sp09_disponibilita_liquide": 50}
        assert calcola_indicatori(bs, {}).pfn == D(350)

    def test_of_revenue_e_oneri_sui_ricavi(self):
        assert close(self.ind.of_revenue, D(12_000) / D(1_200_000) * 100)
        assert close(self.ind.of_mol, D(12_000) / D(250_000) * 100)

    def test_accetta_float_e_none(self):
        ind = calcola_indicatori({"sp09_disponibilita_liquide": 10.5, "sp16_debiti_breve": None}, {})
        assert ind.pfn == D("-10.5")


class TestPunteggio:
    ind = calcola_indicatori(BS_SANA, CE_SANA)

    def test_ogni_punteggio_sta_fra_zero_e_uno(self):
        for chiave, _, _ in INDICATORI:
            assert D(0) <= punteggio(chiave, self.ind) <= D(1)

    def test_ebitda_negativo_con_pfn_positiva_vale_zero(self):
        ind = calcola_indicatori(BS_SANA, {"ce01_ricavi_vendite": 100, "ce05_materie_prime": 500})
        assert punteggio("pfn_ebitda", ind) == 0
        assert punteggio("pfn", ind) == 0

    def test_ebitda_negativo_senza_oneri_of_mol_neutro(self):
        ind = calcola_indicatori(BS_SANA, {"ce01_ricavi_vendite": 100, "ce05_materie_prime": 500})
        assert punteggio("of_mol", ind) == D("0.5")

    def test_of_revenue_interpola_fra_uno_e_cinque(self):
        ind = calcola_indicatori({}, {"ce01_ricavi_vendite": 1000, "ce15_oneri_finanziari": 30})
        assert punteggio("of_revenue", ind) == D("0.5")

    def test_of_revenue_a_ricavi_zero_e_neutro_non_eccellente(self):
        ind = calcola_indicatori({}, {"ce15_oneri_finanziari": 30})
        assert punteggio("of_revenue", ind) == D("0.5")

    def test_of_revenue_senza_oneri_con_ricavi_e_eccellente(self):
        ind = calcola_indicatori({}, {"ce01_ricavi_vendite": 1000})
        assert punteggio("of_revenue", ind) == 1

    def test_dscr_senza_oneri_e_neutro(self):
        ind = calcola_indicatori(BS_SANA, {**CE_SANA, "ce15_oneri_finanziari": 0})
        assert punteggio("dscr", ind) == D("0.5")

    def test_dscr_basso_resta_zero(self):
        ind = calcola_indicatori(BS_SANA, {**CE_SANA, "ce15_oneri_finanziari": 300_000})
        assert punteggio("dscr", ind) == 0

    def test_roe_a_patrimonio_nullo_o_negativo_e_neutro(self):
        for pn in (0, -100_000):
            bs = {**BS_SANA, "sp11_capitale": pn, "sp12_riserve": 0, "sp13_utile_perdita": 0}
            assert punteggio("roe", calcola_indicatori(bs, CE_SANA)) == D("0.5")

    def test_perdita_vera_a_patrimonio_positivo_vale_zero(self):
        ce = {**CE_SANA, "ce05_materie_prime": 1_000_000}
        assert punteggio("roe", calcola_indicatori(BS_SANA, ce)) == 0


class TestRating:
    def test_of_revenue_fuori_dal_punteggio(self):
        assert "of_revenue" not in CHIAVI_PUNTEGGIO
        assert "of_mol" in CHIAVI_PUNTEGGIO
        assert len(CHIAVI_PUNTEGGIO) == len(INDICATORI) - 1 == 14

    def test_punteggi_allineati_alle_chiavi(self):
        ind = calcola_indicatori(BS_SANA, CE_SANA)
        assert punteggi_crisi(ind) == [punteggio(k, ind) for k in CHIAVI_PUNTEGGIO]

    @pytest.mark.parametrize("punteggi,segnali,atteso", [
        ([1, 1, 1, D("0.9")], 0, "A3"),
        ([D("0.1"), D("0.2"), 1, 1], 0, "A2"),
        ([0, 0, 0, 1], 0, "A1"),
        ([0] * 5, 0, "B3"),
        ([1, 1], 1, "B2"),
        ([1, 1], 2, "B1"),
        ([1, 1, 1, 1], 3, "C3"),
        ([0] * 7, 0, "C2"),
        ([0] * 8, 3, "C1"),
        ([0] * 5, 4, "D"),
    ])
    def test_bande(self, punteggi, segnali, atteso):
        assert rating_crisi([D(p) for p in punteggi], segnali).codice == atteso

    def test_i_segnali_peggiorano_il_rating(self):
        assert rating_crisi([D(1)] * 4, 0).codice == "A3"
        assert rating_crisi([D(1)] * 4, 3).codice == "C3"

    def test_soglia_oltre_e_stretta(self):
        # 0,33 non e' «oltre»: la soglia e' `< 0,33`
        assert rating_crisi([D("0.33")], 0).codice == "A3"


def test_mappa_usa_le_chiavi_del_client():
    mappa = indicatori_come_mappa(calcola_indicatori(BS_SANA, CE_SANA))
    assert mappa["_ebitda_raw"] == D(250_000)
    assert "ebitda_raw" not in mappa
    assert {k for k, _, _ in INDICATORI} <= set(mappa)
