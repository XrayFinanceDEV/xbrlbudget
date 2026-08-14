"""Tests per il riscatto vision per sezione (route C).

Spec: docs/superpowers/specs/2026-08-14-riscatto-vision-route-c-design.md
Run:  python -m pytest tests/test_vision_rescue.py -v

Nessun test in questo file effettua una chiamata di rete: la risposta vision e'
sempre passata con un doppio.
"""
import os
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.pdf_extractor_llm import _declared_control_totals  # noqa: E402

D = Decimal


# ------------------------------------------------- ancore dichiarate del CE

def test_declared_totals_legge_i_totali_del_conto_economico():
    text = (
        "CONTO ECONOMICO\n"
        "73020005 Amm.to immobilizzazioni materiali 4.656,95\n"
        "TOTALE COSTI 2.482.879,59\n"
        "TOTALE RICAVI 2.491.786,38\n"
        "UTILE D'ESERCIZIO 8.906,79\n"
    )
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] == D("2482879.59")
    assert out["ricavi"] == D("2491786.38")
    assert out["utile"] == D("8906.79")


def test_declared_totals_costi_ricavi_sono_none_se_non_stampati():
    text = "STATO PATRIMONIALE\nTOTALE ATTIVO 1.000,00\nTOTALE PASSIVO 1.000,00\n"
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] is None
    assert out["ricavi"] is None


def test_declared_totals_costi_ricavi_tollerano_le_intestazioni_spaziate():
    text = "T O T A L E   C O S T I 1.234,56\nT O T A L E   R I C A V I 2.345,67\n"
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] == D("1234.56")
    assert out["ricavi"] == D("2345.67")


def test_declared_totals_non_scambia_il_subtotale_b_per_il_totale_costi():
    # "Totale costi della produzione (B)" e' un subtotale di sezione dello schema
    # IV-CEE. Un bilancio ordinario non stampa affatto un totale costi complessivo:
    # l'ancora deve tornare None, non il subtotale.
    text = (
        "Totale valore della produzione (A) 392.761,56\n"
        "Totale costi della produzione (B) 311.646,32\n"
        "Utile dell'esercizio 45.000,00\n"
    )
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] is None
    assert out["ricavi"] is None


def test_declared_totals_legge_ancora_il_totale_costi_di_una_situazione_contabile():
    # Il caso che serve: una situazione contabile stampa i totali di colonna, e
    # quelli devono continuare a leggersi anche se il documento cita altrove i
    # subtotali di schema.
    text = (
        "Totale costi della produzione (B) 311.646,32\n"
        "TOTALE COSTI 2.482.879,59\n"
        "TOTALE RICAVI 2.491.786,38\n"
    )
    out = _declared_control_totals("ignorato.pdf", text=text)
    assert out["costi"] == D("2482879.59")
    assert out["ricavi"] == D("2491786.38")


from importers.situazione_contabile_parser import (  # noqa: E402
    classify_attivo,
    classify_costi,
    classify_passivo,
    classify_ricavi,
)


# ------------------------------------------------- classificatori promossi

def test_classify_attivo_banche_e_cassa_sul_lato_attivo():
    # Nel layout contrapposte il LATO e' verita': BANCHE in colonna attivo e'
    # liquidita', non il fallback generico dei crediti.
    assert classify_attivo("BANCHE C/C") == ("sp09", True)


def test_classify_attivo_categoria_legale_esatta_ferma_la_discesa():
    assert classify_attivo("IMMOBILIZZAZIONI MATERIALI") == ("sp03", True)


def test_classify_passivo_fondo_ammortamento_e_un_contro_conto():
    field, _specific = classify_passivo("F.DO AMM.TO IMMOBILIZZAZIONI MATERIALI")
    assert field == "depr_sp03"


def test_classify_passivo_tipizza_i_debiti_per_creditore():
    assert classify_passivo("DEBITI VERSO FORNITORI")[0].startswith("sp16")


def test_classify_costi_e_ricavi_hanno_catch_all_distinti():
    assert classify_costi("VOCE SCONOSCIUTA XYZ") == ("ce12", False)
    assert classify_ricavi("VOCE SCONOSCIUTA XYZ") == ("ce04", False)


from importers.situazione_contabile_parser import (  # noqa: E402
    build_ce_from_vision,
    build_sp_from_vision,
)


# ------------------------------------------------- montaggio di una sezione

def test_build_sp_netta_i_fondi_dall_attivo():
    rows = [
        ("01", "IMMOBILIZZAZIONI MATERIALI", D("1000.00"), "left"),
        ("02", "F.DO AMM.TO IMMOBILIZZAZIONI MATERIALI", D("400.00"), "right"),
        ("20", "DEBITI VERSO FORNITORI", D("600.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("0"))
    assert bs["sp03"] == D("600.00")          # 1000 lordo - 400 fondo
    assert bs["_netted_contra"] == D("400.00")
    assert bs["totale_attivo"] == D("600.00")
    assert bs["totale_passivo"] == D("600.00")


def test_build_sp_scrive_il_risultato_ricevuto_e_non_lo_inventa():
    rows = [
        ("01", "CASSA", D("150.00"), "left"),
        ("20", "DEBITI VERSO FORNITORI", D("100.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("50.00"))
    assert bs["sp13"] == D("50.00")
    assert bs["totale_passivo"] == D("150.00")   # 100 debiti + 50 utile


def test_build_sp_tipizza_i_debiti_per_creditore():
    rows = [
        ("01", "CASSA", D("300.00"), "left"),
        ("20", "DEBITI VERSO FORNITORI", D("200.00"), "right"),
        ("21", "BANCHE C/C PASSIVI", D("100.00"), "right"),
    ]
    bs = build_sp_from_vision(rows, utile=D("0"))
    assert bs["sp16"] == D("300.00")                       # aggregato invariato
    assert bs["sp16d_debiti_fornitori_breve"] == D("200.00")
    assert bs["sp16a_debiti_banche_breve"] == D("100.00")


def test_build_ce_usa_la_colonna_come_direzione():
    rows = [
        ("60", "ACQUISTI MATERIE PRIME", D("500.00"), "left"),
        ("70", "RICAVI DELLE VENDITE", D("800.00"), "right"),
    ]
    ce = build_ce_from_vision(rows)
    assert ce["ce05"] == D("500.00")
    assert ce["ce01"] == D("800.00")


def test_build_ce_non_manda_un_costo_su_una_voce_di_ricavo():
    # DIFFERENZE CAMBIO PASSIVE risolve su un nodo di GUADAGNO nell'albero
    # condiviso: sulla colonna dei costi deve cadere sul catch-all neutro, mai
    # su ce16 (che ALZEREBBE il risultato, spostandolo di 2x).
    rows = [("75", "DIFFERENZE CAMBIO PASSIVE", D("90.00"), "left")]
    ce = build_ce_from_vision(rows)
    assert ce.get("ce16", D("0")) == D("0")
    assert sum(v for k, v in ce.items() if k.startswith("ce")) >= D("90.00")


def test_build_ce_arrotola_i_sottocampi_sul_padre():
    rows = [("64", "SALARI E STIPENDI", D("300.00"), "left")]
    ce = build_ce_from_vision(rows)
    assert ce["ce08"] == D("300.00")
    assert ce["ce08b_salari_stipendi"] == D("300.00")


from importers import vision_rescue as vr  # noqa: E402


class _FakeBlock:
    type = "tool_use"

    def __init__(self, payload):
        self.input = payload


class _FakeResponse:
    def __init__(self, payload):
        self.content = [_FakeBlock(payload)]


class _FakeMessages:
    def __init__(self, payload_or_exc):
        self._p = payload_or_exc
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if isinstance(self._p, Exception):
            raise self._p
        return _FakeResponse(self._p)


class _FakeClient:
    """Doppio del client anthropic: nessuna chiamata di rete."""

    def __init__(self, payload_or_exc):
        self.messages = _FakeMessages(payload_or_exc)


_PAYLOAD_CE = {
    "mastri": [
        {"codice": "73020005", "descrizione": "Amm.to immobilizzazioni materiali",
         "importo": "4.656,95", "colonna": "left"},
        {"codice": "706440000", "descrizione": "amm.to fabbricati",
         "importo": "486,93", "colonna": "left"},
        {"codice": "70000005", "descrizione": "Ricavi delle vendite",
         "importo": "2.491.786,38", "colonna": "right"},
    ],
    "totale_sinistra": "2.482.879,59",
    "totale_destra": "2.491.786,38",
    "utile": "8.906,79",
    "perdita": None,
}


def test_parse_amount_formato_italiano():
    assert vr.parse_amount("1.426.002,20") == D("1426002.20")
    assert vr.parse_amount("4.656,95") == D("4656.95")
    assert vr.parse_amount("") is None
    assert vr.parse_amount("n.d.") is None


def test_mastro_level_rows_scarta_i_dettagli_piu_lunghi():
    # I dettagli a 9 cifre la vision li sbaglia (spec, sezione Evidenza) e non
    # servono: il mastro porta gia' l'intero importo della voce.
    rows = [
        vr.VisionRow("73020005", "Amm.to", D("4656.95"), "left"),
        vr.VisionRow("706440000", "amm.to fabbricati", D("486.93"), "left"),
    ]
    kept = vr.mastro_level_rows(rows)
    assert [r.code for r in kept] == ["73020005"]


def test_mastro_level_rows_ignora_le_righe_senza_codice():
    rows = [
        vr.VisionRow("73020005", "Amm.to", D("4656.95"), "left"),
        vr.VisionRow("", "TOTALE COSTI", D("2482879.59"), "left"),
    ]
    assert [r.code for r in vr.mastro_level_rows(rows)] == ["73020005"]


def test_read_section_monta_righe_e_totali():
    got = vr.read_section("ignorato.pdf", [0], "ce",
                          client=_FakeClient(_PAYLOAD_CE),
                          images=["ZmFrZQ=="])
    assert got is not None
    assert got.section == "ce"
    assert [r.code for r in got.rows] == ["73020005", "70000005"]
    assert got.totals["left"] == D("2482879.59")
    assert got.totals["right"] == D("2491786.38")
    assert got.totals["utile"] == D("8906.79")
    assert got.totals["perdita"] is None


def test_read_section_rifiuta_una_sezione_oltre_il_tetto_di_pagine():
    fake = _FakeClient(_PAYLOAD_CE)
    assert vr.read_section("ignorato.pdf", list(range(vr.MAX_RESCUE_PAGES + 1)), "ce",
                           client=fake, images=["ZmFrZQ=="]) is None
    assert fake.messages.calls == 0, "il tetto deve fermare PRIMA di spendere una chiamata"


def test_read_section_senza_pagine_non_chiama_il_modello():
    fake = _FakeClient(_PAYLOAD_CE)
    assert vr.read_section("ignorato.pdf", [], "ce", client=fake, images=[]) is None
    assert fake.messages.calls == 0


def test_read_section_restituisce_none_se_il_modello_esplode():
    fake = _FakeClient(RuntimeError("API irraggiungibile"))
    assert vr.read_section("ignorato.pdf", [0], "ce",
                           client=fake, images=["ZmFrZQ=="]) is None


def test_read_section_restituisce_none_su_risposta_malformata():
    fake = _FakeClient({"mastri": "non e' una lista"})
    assert vr.read_section("ignorato.pdf", [0], "ce",
                           client=fake, images=["ZmFrZQ=="]) is None


def test_read_section_fa_un_solo_tentativo():
    fake = _FakeClient(_PAYLOAD_CE)
    vr.read_section("ignorato.pdf", [0], "ce", client=fake, images=["ZmFrZQ=="])
    assert fake.messages.calls == 1


def test_normalize_column_riconosce_le_grafie_italiane():
    assert vr.normalize_column("left") == "left"
    assert vr.normalize_column("Sinistra") == "left"
    assert vr.normalize_column("DARE") == "left"
    assert vr.normalize_column("right") == "right"
    assert vr.normalize_column("destra") == "right"
    assert vr.normalize_column("AVERE") == "right"


def test_normalize_column_none_quando_non_e_riconoscibile():
    assert vr.normalize_column("") is None
    assert vr.normalize_column(None) is None
    assert vr.normalize_column("boh") is None


def test_read_section_scarta_una_riga_senza_colonna_riconoscibile():
    # La colonna e' verita' sul lato: una riga di cui non si sa il lato non si
    # indovina, si scarta. Il cancello vedra' il totale piu' corto.
    payload = {
        "mastri": [
            {"codice": "70", "descrizione": "RICAVI", "importo": "100,00",
             "colonna": "destra"},
            {"codice": "73", "descrizione": "IGNOTO", "importo": "50,00",
             "colonna": "boh"},
        ],
        "totale_sinistra": "0,00", "totale_destra": "100,00",
        "utile": None, "perdita": None,
    }
    got = vr.read_section("ignorato.pdf", [0], "ce",
                          client=_FakeClient(payload), images=["ZmFrZQ=="])
    assert [r.code for r in got.rows] == ["70"]
    assert got.rows[0].column == "right"


from importers.iv_cee_hierarchy import check_quadratura  # noqa: E402


def _sezione(section, left, right, utile=None, perdita=None):
    return vr.VisionSection(section=section, rows=(),
                            totals={"left": left, "right": right,
                                    "utile": utile, "perdita": perdita})


# ------------------------------------------------- cancello: coerenza interna

def test_coerenza_sp_attivo_uguale_passivo_piu_utile():
    assert vr.totals_are_coherent(_sezione("sp", D("1000"), D("950"), utile=D("50")))


def test_coerenza_sp_attivo_piu_perdita_uguale_passivo():
    assert vr.totals_are_coherent(_sezione("sp", D("950"), D("1000"), perdita=D("50")))


def test_coerenza_ce_costi_piu_utile_uguale_ricavi():
    assert vr.totals_are_coherent(
        _sezione("ce", D("2482879.59"), D("2491786.38"), utile=D("8906.79")))


def test_incoerenza_quando_i_totali_non_tornano():
    assert not vr.totals_are_coherent(
        _sezione("ce", D("2482879.59"), D("2491786.38"), utile=D("1000")))


def test_incoerenza_quando_manca_un_totale():
    assert not vr.totals_are_coherent(_sezione("sp", D("1000"), None, utile=D("50")))


# ------------------------------------------------- cancello: scelta dell'ancora

def test_ancora_preferisce_i_totali_vision_quando_sono_coerenti():
    # budget_623: le ancore di TESTO si contraddicono (il passivo letto dal testo e'
    # 2.420.397,40 mentre il PDF stampa 2.454.987,65). La coerenza interna dei totali
    # vision e' cio' che autorizza a preferirli.
    sec = _sezione("sp", D("2420397.40"), D("2370397.40"), utile=D("50000"))
    declared = {"attivo": D("2420397.40"), "passivo": D("2454987.65"), "pareggio": None}
    assert vr.section_anchor(sec, declared) == D("2420397.40")


def test_ancora_ricade_sul_testo_quando_i_totali_vision_non_sono_coerenti():
    sec = _sezione("sp", D("999"), D("111"), utile=D("1"))
    declared = {"attivo": D("2000"), "passivo": None, "pareggio": None}
    assert vr.section_anchor(sec, declared) == D("2000")


def test_ancora_none_quando_nessun_insieme_e_utilizzabile():
    sec = _sezione("sp", None, None)
    assert vr.section_anchor(sec, {"attivo": None, "passivo": None, "pareggio": None}) is None


# ------------------------------------------------- cancello: verdetto

_BS_ROTTO = {"sp09_disponibilita_liquide": D("700"), "sp16_debiti_breve": D("1000"),
             "totale_attivo": D("700"), "totale_passivo": D("1000")}
_BS_SANO = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("1000"),
            "totale_attivo": D("1000"), "totale_passivo": D("1000")}


def test_accetta_un_riscatto_che_riconcilia_e_migliora():
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(_BS_ROTTO), after=check_quadratura(_BS_SANO))
    assert ok, motivo


def test_rifiuta_un_riscatto_che_non_riconcilia_al_totale_stampato():
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("600"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(_BS_ROTTO), after=check_quadratura(_BS_SANO))
    assert not ok
    assert "riconcilia" in motivo


def test_rifiuta_un_riscatto_che_peggiora_la_quadratura():
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(_BS_SANO), after=check_quadratura(_BS_ROTTO))
    assert not ok
    # Fix round 1: il messaggio unificato del gate 3 (badness scalare) e' "non
    # migliora", non piu' "peggiora" — vedi test_rifiuta_quando_nulla_e_cambiato
    # e i test badness sotto per la distinzione fra i due casi.
    assert "non migliora" in motivo


def test_rifiuta_un_riscatto_vuoto():
    # Deve cadere sul controllo del VUOTO, non su quello del totale stampato: percio'
    # il totale ricostruito coincide con l'ancora e l'unica cosa che non va e' che il
    # foglio risultante e' vuoto.
    vuoto = {"totale_attivo": D("0"), "totale_passivo": D("0")}
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(_BS_ROTTO), after=check_quadratura(vuoto))
    assert not ok
    assert "vuota" in motivo


def test_rifiuta_quando_non_c_e_nessuna_ancora():
    sec = _sezione("sp", None, None)
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": None, "passivo": None, "pareggio": None},
        before=check_quadratura(_BS_ROTTO), after=check_quadratura(_BS_SANO))
    assert not ok
    assert "ancora" in motivo


# ------------------------------------------------- fix round 1: gate 3 come badness scalare

def test_accetta_un_riscatto_che_smaschera_anche_se_lascia_un_piccolo_sbilancio():
    # QUADRATURA MASCHERATA e' uno dei quattro inneschi del riscatto: un riscatto che
    # azzera il residuo non classificato deve poter passare anche se lascia uno
    # sbilancio molto piu' piccolo del residuo che ha tolto.
    mascherato = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("1000"),
                  "totale_attivo": D("1000"), "totale_passivo": D("1000"),
                  "_plug_residual": D("200")}
    onesto = {"sp09_disponibilita_liquide": D("990"), "sp16_debiti_breve": D("1000"),
              "totale_attivo": D("990"), "totale_passivo": D("1000")}
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(mascherato), after=check_quadratura(onesto))
    assert ok, motivo


def test_rifiuta_un_riscatto_che_dimezza_il_residuo_triplicando_lo_sbilancio():
    # sbilancio -30 -> -90 (triplicato), residuo 100 -> 50 (dimezzato): la somma
    # peggiora comunque (130 -> 140), perche' l'aumento dello sbilancio (60) supera
    # la riduzione del residuo (50).
    prima = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("1030"),
             "totale_attivo": D("1000"), "totale_passivo": D("1030"),
             "_plug_residual": D("100")}
    dopo = {"sp09_disponibilita_liquide": D("940"), "sp16_debiti_breve": D("1030"),
            "totale_attivo": D("940"), "totale_passivo": D("1030"),
            "_plug_residual": D("50")}
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(prima), after=check_quadratura(dopo))
    assert not ok
    assert "non migliora" in motivo


def test_rifiuta_un_riscatto_che_rompe_l_identita_utile_ce_sp13():
    bs = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("900"),
          "sp13_utile_perdita": D("100"), "totale_attivo": D("1000"),
          "totale_passivo": D("1000")}
    ce_ok = {"ce01_ricavi_vendite": D("1100"), "ce05_materie_prime": D("1000")}
    ce_rotto = {"ce01_ricavi_vendite": D("5000"), "ce05_materie_prime": D("1000")}
    sec = _sezione("ce", D("1000"), D("1100"), utile=D("100"))
    ok, motivo = vr.accept_rescue(
        section="ce", rebuilt_total=D("1000"), sec=sec,
        declared={"costi": D("1000"), "ricavi": D("1100")},
        before=check_quadratura(bs, ce_ok), after=check_quadratura(bs, ce_rotto))
    assert not ok
    assert "identita" in motivo


def test_rifiuta_quando_nulla_e_cambiato():
    # Tutte e tre le metriche identiche: non e' un miglioramento, quindi si scarta.
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    q = check_quadratura(_BS_ROTTO)
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=q, after=q)
    assert not ok
    assert "non migliora" in motivo


def test_ancora_ce_ricade_sui_costi_dichiarati():
    sec = _sezione("ce", D("999"), D("111"), utile=D("1"))   # incoerenti
    assert vr.section_anchor(sec, {"costi": D("2000"), "ricavi": D("2100")}) == D("2000")


def test_reconcile_tolerance_e_la_regola_del_repo():
    assert vr.reconcile_tolerance(D("1000")) == D("50")        # pavimento assoluto
    assert vr.reconcile_tolerance(D("1000000")) == D("5000")   # 0,5%


# ------------------------------------------------- fix round 1: vision_result

def test_vision_result_segue_il_ramo_che_valida_non_l_ordine_delle_chiavi():
    # Il documento stampa ENTRAMBE le didascalie: solo il ramo della perdita torna.
    sec = _sezione("sp", D("950"), D("1000"), utile=D("70"), perdita=D("50"))
    assert vr.vision_result(sec) == D("-50")


def test_vision_result_utile_quando_e_il_ramo_dell_utile_a_tornare():
    sec = _sezione("sp", D("1000"), D("950"), utile=D("50"), perdita=D("70"))
    assert vr.vision_result(sec) == D("50")


def test_vision_result_ce_perdita():
    # Il documento stampa entrambe le didascalie: solo il ramo della perdita torna.
    # costi == ricavi + perdita
    sec = _sezione("ce", D("1000"), D("950"), utile=D("60"), perdita=D("50"))
    assert vr.vision_result(sec) == D("-50")


def test_vision_result_none_se_i_totali_non_sono_coerenti():
    assert vr.vision_result(_sezione("sp", D("1000"), D("111"), utile=D("1"))) is None


def test_totals_are_coherent_e_vision_result_non_divergono():
    casi = [
        _sezione("sp", D("1000"), D("950"), utile=D("50")),
        _sezione("sp", D("950"), D("1000"), perdita=D("50")),
        _sezione("ce", D("1000"), D("1100"), utile=D("100")),
        _sezione("ce", D("1000"), D("950"), perdita=D("50")),
        _sezione("sp", D("1000"), D("111"), utile=D("1")),
        _sezione("sp", None, None),
    ]
    for sec in casi:
        assert vr.totals_are_coherent(sec) == (vr.vision_result(sec) is not None)


# ------------------------------------------------- fix round 2: il tetto su fixed_identity

def test_rifiuta_un_riscatto_che_ripara_l_identita_ma_sbilancia_il_foglio():
    # Riparare sp13 non e' una licenza illimitata: il gate 1 misura la sola colonna
    # di sinistra, quindi un passivo ricostruito male non lo vedrebbe nessuno.
    bs_prima = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("1000"),
                "sp13_utile_perdita": D("0"),
                "totale_attivo": D("1000"), "totale_passivo": D("1000")}
    bs_dopo = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("1400"),
               "sp13_utile_perdita": D("100"),
               "totale_attivo": D("1000"), "totale_passivo": D("1500")}
    ce = {"ce01_ricavi_vendite": D("1100"), "ce05_materie_prime": D("1000")}
    sec = _sezione("sp", D("1000"), D("1000"), utile=D("0"))
    ok, motivo = vr.accept_rescue(
        section="sp", rebuilt_total=D("1000"), sec=sec,
        declared={"attivo": D("1000"), "passivo": D("1000"), "pareggio": None},
        before=check_quadratura(bs_prima, ce), after=check_quadratura(bs_dopo, ce))
    assert not ok
    assert "sbilancia" in motivo


def test_accetta_un_riscatto_ce_che_ripara_l_identita_senza_toccare_lo_sp():
    # Il caso budget_624: lo SP quadra gia', il CE no. Il bilancio non cambia, quindi
    # lo scarto complessivo resta identico: solo la riparazione dell'identita' puo'
    # far passare questo riscatto, e deve passare.
    bs = {"sp09_disponibilita_liquide": D("1000"), "sp16_debiti_breve": D("900"),
          "sp13_utile_perdita": D("100"),
          "totale_attivo": D("1000"), "totale_passivo": D("1000")}
    ce_rotto = {"ce01_ricavi_vendite": D("1100"), "ce05_materie_prime": D("400")}
    ce_giusto = {"ce01_ricavi_vendite": D("1100"), "ce05_materie_prime": D("1000")}
    sec = _sezione("ce", D("1000"), D("1100"), utile=D("100"))
    ok, motivo = vr.accept_rescue(
        section="ce", rebuilt_total=D("1000"), sec=sec,
        declared={"costi": D("1000"), "ricavi": D("1100")},
        before=check_quadratura(bs, ce_rotto), after=check_quadratura(bs, ce_giusto))
    assert ok, motivo


# ------------------------------------------------- innesco in pdf_importer

from importers.pdf_importer import _apply_vision_rescue  # noqa: E402


_BS_624 = {   # SP corretto: quadra. Il rotto e' il CE.
    "sp09_disponibilita_liquide": D("2181734.09"),
    "sp16_debiti_breve": D("2172827.30"),
    "sp13_utile_perdita": D("8906.79"),
    "totale_attivo": D("2181734.09"), "totale_passivo": D("2181734.09"),
}
_CE_624_ROTTO = {"ce01_ricavi_vendite": D("2491786.38"),
                 "ce05_materie_prime": D("938766.79")}


def test_non_viene_invocato_su_un_foglio_che_gia_quadra():
    chiamate = []

    def _reader(*a, **kw):
        chiamate.append(a)
        return None

    ce_ok = {"ce01_ricavi_vendite": D("2491786.38"),
             "ce05_materie_prime": D("2482879.59")}
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_624), dict(ce_ok),
        declared={}, donor_bs=None, ocr_text=None, reader=_reader)
    assert riscattate == []
    assert chiamate == [], "nessuna chiamata vision su un foglio sano"
    assert ce == ce_ok


def test_un_eccezione_nel_riscatto_lascia_il_foglio_intatto(monkeypatch):
    # section_pages e' doppiata perche' l'eccezione arrivi DAVVERO dal lettore:
    # con un percorso inesistente il riscatto uscirebbe prima di chiamarlo, e il
    # test passerebbe senza aver mai esercitato il ramo che dichiara di provare.
    monkeypatch.setattr(
        "importers.situazione_contabile_parser.section_pages",
        lambda _p: {"sp": [0], "ce": [1]},
    )

    def _reader(*a, **kw):
        raise RuntimeError("boom")

    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_624), dict(_CE_624_ROTTO),
        declared={}, donor_bs=None, ocr_text=None, reader=_reader)
    assert riscattate == []
    assert bs == _BS_624
    assert ce == _CE_624_ROTTO


def test_un_riscatto_ce_che_riconcilia_sostituisce_il_conto_economico(monkeypatch):
    # La sezione CE riletta chiude il divario misurato: costi 2.482.879,59 contro i
    # 938.766,79 letti dal testo, utile 8.906,79 = sp13.
    sec = vr.VisionSection(
        section="ce",
        rows=(vr.VisionRow("73", "ACQUISTI MATERIE PRIME", D("2482879.59"), "left"),
              vr.VisionRow("70", "RICAVI DELLE VENDITE", D("2491786.38"), "right")),
        totals={"left": D("2482879.59"), "right": D("2491786.38"),
                "utile": D("8906.79"), "perdita": None},
    )
    monkeypatch.setattr(
        "importers.situazione_contabile_parser.section_pages",
        lambda _p: {"sp": [0], "ce": [1]},
    )
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_624), dict(_CE_624_ROTTO),
        declared={"costi": D("2482879.59"), "ricavi": D("2491786.38")},
        donor_bs=None, ocr_text=None, reader=lambda *a, **kw: sec)
    assert riscattate == ["ce"]
    assert ce["ce05_materie_prime"] == D("2482879.59")
    assert bs == _BS_624, "il riscatto del CE non tocca lo stato patrimoniale"


def test_un_riscatto_ce_che_non_riconcilia_viene_scartato(monkeypatch):
    sec = vr.VisionSection(
        section="ce",
        rows=(vr.VisionRow("73", "ACQUISTI MATERIE PRIME", D("100000.00"), "left"),
              vr.VisionRow("70", "RICAVI DELLE VENDITE", D("2491786.38"), "right")),
        totals={"left": D("2482879.59"), "right": D("2491786.38"),
                "utile": D("8906.79"), "perdita": None},
    )
    monkeypatch.setattr(
        "importers.situazione_contabile_parser.section_pages",
        lambda _p: {"sp": [0], "ce": [1]},
    )
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_624), dict(_CE_624_ROTTO),
        declared={"costi": D("2482879.59"), "ricavi": D("2491786.38")},
        donor_bs=None, ocr_text=None, reader=lambda *a, **kw: sec)
    assert riscattate == []
    assert ce == _CE_624_ROTTO


# --- lo stato patrimoniale -------------------------------------------------

_BS_SBILANCIATO = {"sp09_disponibilita_liquide": D("1000"),
                   "sp16_debiti_breve": D("900"),
                   "sp13_utile_perdita": D("0")}


def _patch_pagine(monkeypatch):
    monkeypatch.setattr(
        "importers.situazione_contabile_parser.section_pages",
        lambda _p: {"sp": [0], "ce": [1]},
    )


def test_un_riscatto_sp_che_riconcilia_sostituisce_lo_stato_patrimoniale(monkeypatch):
    _patch_pagine(monkeypatch)
    sec = vr.VisionSection(
        section="sp",
        rows=(vr.VisionRow("10", "CASSA", D("1000"), "left"),
              vr.VisionRow("20", "DEBITI V/FORNITORI", D("900"), "right")),
        totals={"left": D("1000"), "right": D("900"),
                "utile": D("100"), "perdita": None},
    )
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_SBILANCIATO), {},
        declared={}, donor_bs=None, ocr_text=None, reader=lambda *a, **kw: sec)
    assert riscattate == ["sp"]
    assert bs["sp13_utile_perdita"] == D("100")
    assert bs["sp09_disponibilita_liquide"] == D("1000")
    assert ce == {}, "il riscatto dello SP non tocca il conto economico"


def test_il_segno_del_risultato_sp_lo_decide_l_identita_che_valida(monkeypatch):
    # Il documento stampa SIA un utile SIA una perdita: e' il ramo della perdita
    # che fa tornare i totali (attivo + perdita == passivo). Prendere l'utile per
    # primo bookerebbe +100 al posto di -100 — un errore di 2x sul risultato che il
    # primo cancello, che misura la sola colonna di sinistra, non vedrebbe.
    _patch_pagine(monkeypatch)
    sec = vr.VisionSection(
        section="sp",
        rows=(vr.VisionRow("10", "CASSA", D("900"), "left"),
              vr.VisionRow("20", "DEBITI V/FORNITORI", D("1000"), "right")),
        totals={"left": D("900"), "right": D("1000"),
                "utile": D("100"), "perdita": D("100")},
    )
    prima = {"sp09_disponibilita_liquide": D("900"),
             "sp16_debiti_breve": D("1000"),
             "sp13_utile_perdita": D("0")}
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(prima), {},
        declared={}, donor_bs=None, ocr_text=None, reader=lambda *a, **kw: sec)
    assert riscattate == ["sp"]
    assert bs["sp13_utile_perdita"] == D("-100")


def test_totali_vision_incoerenti_non_producono_un_riscatto_sp(monkeypatch):
    # Nessuna delle due identita' torna: il risultato non si indovina, il foglio
    # resta com'e'.
    _patch_pagine(monkeypatch)
    sec = vr.VisionSection(
        section="sp",
        rows=(vr.VisionRow("10", "CASSA", D("1000"), "left"),
              vr.VisionRow("20", "DEBITI V/FORNITORI", D("900"), "right")),
        totals={"left": D("1000"), "right": D("900"),
                "utile": None, "perdita": None},
    )
    bs, ce, riscattate = _apply_vision_rescue(
        "ignorato.pdf", dict(_BS_SBILANCIATO), {},
        declared={}, donor_bs=None, ocr_text=None, reader=lambda *a, **kw: sec)
    assert riscattate == []
    assert bs == _BS_SBILANCIATO
