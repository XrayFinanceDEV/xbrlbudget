"""Per-account reliability verdicts.

UNRELIABLE requires POSITIVE evidence of contradiction, never the mere absence
of a control - otherwise every route A/B file (which runs no contra scan) and
every abbreviated statement would be blocked.
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.reliability import (  # noqa: E402
    AccountStatus,
    ReliabilityReport,
    assess,
)

D = Decimal


def _bs(**over):
    base = {
        "sp02_immob_immateriali": D("6000"),
        "sp03_immob_materiali": D("1500000"),
        "sp11_capitale": D("10000"),
        "sp12_riserve": D("800000"),
        "sp13_utile_perdita": D("100000"),
        "sp16_debiti_breve": D("220000"),
        "sp16a_debiti_banche_breve": D("7000"),
        "sp16d_debiti_fornitori_breve": D("213000"),
        "sp17_debiti_lungo": D("0"),
        "totale_attivo": D("2000000"),
        "totale_passivo": D("2000000"),
    }
    base.update(over)
    return base


# ---------------------------------------------------------- immobilizzazioni

def test_contra_detected_but_not_applied_is_unreliable():
    """The 613 shape: the scan found 2,25M of fondi and then discarded them."""
    bs = _bs(_contra_detected=D("2247715.70"), _contra_applied=D("0"),
             _contra_reason="contro rilevati ma non applicati")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.UNRELIABLE
    assert r.all_critical_ok is False


def test_contra_applied_is_verified():
    bs = _bs(_contra_detected=D("2247715.70"), _contra_applied=D("2247715.70"),
             _contra_reason="applicato")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.VERIFIED


def test_no_contra_mass_found_is_derived_not_unreliable():
    bs = _bs(_contra_detected=D("0"), _contra_applied=D("0"),
             _contra_reason="nessuna massa contro")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.DERIVED


def test_route_ab_without_any_contra_metadata_is_derived():
    """Route A/B never runs a contra scan; absence of metadata must not block."""
    r = assess(_bs(), {})
    assert r.immobilizzazioni is AccountStatus.DERIVED
    assert r.all_critical_ok is True


# ---------------------------------------------------------- patrimonio netto

def test_pn_matching_the_printed_control_is_verified():
    r = assess(_bs(), {}, declared={"patrimonio_netto": D("910000")})
    assert r.patrimonio_netto is AccountStatus.VERIFIED


def test_pn_contradicting_the_printed_control_is_unreliable():
    r = assess(_bs(), {}, declared={"patrimonio_netto": D("500000")})
    assert r.patrimonio_netto is AccountStatus.UNRELIABLE
    assert r.all_critical_ok is False


def test_pn_without_a_printed_control_is_derived():
    r = assess(_bs(), {}, declared={})
    assert r.patrimonio_netto is AccountStatus.DERIVED


# ------------------------------------------------------------ debiti banche

def test_explicit_bank_subfields_are_verified():
    r = assess(_bs(), {})
    assert r.debiti_banche is AccountStatus.VERIFIED


def test_material_aggregate_gap_is_unreliable():
    """base_bank_debt assigns any aggregate/detail gap to BANKS, so a material
    gap means the bank figure is invented rather than read."""
    bs = _bs(sp16_debiti_breve=D("500000"))   # 280k unexplained
    r = assess(bs, {})
    assert r.debiti_banche is AccountStatus.UNRELIABLE


def test_immaterial_aggregate_gap_is_tolerated():
    bs = _bs(sp16_debiti_breve=D("220500"))   # 500 gap, below M=2000
    r = assess(bs, {})
    assert r.debiti_banche is not AccountStatus.UNRELIABLE


def test_no_bank_debt_and_no_gap_is_derived():
    bs = _bs(sp16a_debiti_banche_breve=D("0"),
             sp16d_debiti_fornitori_breve=D("220000"))
    r = assess(bs, {})
    assert r.debiti_banche is AccountStatus.DERIVED


# ------------------------------------------------------------------ payload

def test_to_dict_is_json_safe_and_carries_reasons():
    import json
    r = assess(_bs(), {})
    payload = r.to_dict()
    json.dumps(payload)          # must not raise
    assert set(payload) >= {"immobilizzazioni", "patrimonio_netto",
                            "debiti_banche", "all_critical_ok"}
    assert payload["immobilizzazioni"]["status"] == "derived"
    assert isinstance(payload["immobilizzazioni"]["reason"], str)


def test_unclassified_mass_is_carried_through_and_json_safe():
    import json
    bs = _bs(_unclassified_mass=D("4321.55"))
    r = assess(bs, {})
    assert r.unclassified_mass == D("4321.55")
    payload = r.to_dict()
    json.dumps(payload)          # must not raise
    assert payload["unclassified_mass"] == "4321.55"


# --- massa non classificata: due zeri che non sono lo stesso zero ------------
#
# #18 ha introdotto `_unclassified_mass_measured` per distinguere «il documento
# stampa un totale di sezione, l'abbiamo confrontato, non manca massa» da «il
# documento non stampa alcun totale, quindi non c'era nulla contro cui
# misurare». La distinzione pero' non arrivava a nessuno: `assess` leggeva il
# solo importo, e a valle i due casi restavano indistinguibili — che e'
# esattamente il difetto che la chiave doveva togliere.


def test_zero_misurato_e_un_verdetto_positivo():
    r = assess(_bs(_unclassified_mass=D("0"),
                   _unclassified_mass_measured=D("1")), {})
    assert r.massa_non_classificata is AccountStatus.VERIFIED
    assert r.unclassified_mass == D("0")


def test_zero_non_misurato_non_e_un_verdetto_positivo_ma_resta_derived():
    # Il file di #18 (AMB AMBIENTA) non stampa nessuna riga «Totale …»: i
    # totali stanno nelle intestazioni di sezione. E' un layout legittimo e
    # diffuso, quindi «non lo so» non puo' diventare UNRELIABLE — un verdetto
    # negativo vuole una contraddizione, non un controllo assente.
    r = assess(_bs(_unclassified_mass=D("0"),
                   _unclassified_mass_measured=D("0")), {})
    assert r.massa_non_classificata is AccountStatus.DERIVED
    assert r.massa_non_classificata is not AccountStatus.VERIFIED


def test_chiave_measured_assente_vale_non_misurato():
    # Una chiave assente a valle vale zero, quindi tacere equivale a
    # dichiararsi puliti: qui vale «non lo so», non «pulito».
    r = assess(_bs(_unclassified_mass=D("0")), {})
    assert r.massa_non_classificata is AccountStatus.DERIVED


def test_massa_misurata_e_materiale_e_una_contraddizione():
    # 178.663,25 di ratei passivi stampati che non arrivano in nessun campo,
    # contro un totale di controllo che li stampa: questa e' una
    # contraddizione, non un controllo mancante.
    r = assess(_bs(_unclassified_mass=D("178663.25"),
                   _unclassified_mass_measured=D("1")), {})
    assert r.massa_non_classificata is AccountStatus.UNRELIABLE


def test_massa_misurata_ma_sotto_soglia_resta_verificata():
    # Soglia di materialita': max(1.000; 0,1% dell'attivo) = 2.000 su 2.000.000.
    r = assess(_bs(_unclassified_mass=D("500"),
                   _unclassified_mass_measured=D("1")), {})
    assert r.massa_non_classificata is AccountStatus.VERIFIED


def test_to_dict_resta_compatibile_e_porta_la_distinzione():
    import json
    payload = assess(_bs(_unclassified_mass=D("4321.55"),
                         _unclassified_mass_measured=D("1")), {}).to_dict()
    json.dumps(payload)
    # I lettori di oggi non si rompono: la chiave storica e il suo formato
    # (stringa) restano quelli.
    assert payload["unclassified_mass"] == "4321.55"
    assert payload["massa_non_classificata"]["status"] == "unreliable"
    assert isinstance(payload["massa_non_classificata"]["reason"], str)


def test_la_massa_non_classificata_non_entra_nel_cancello_dei_tre_conti():
    # `all_critical_ok` e' il verdetto sui TRE conti che decidono ogni KPI, ed
    # e' letto dal backend per conservare l'esito d'importazione: allargarlo a
    # un quarto conto cambierebbe il gating su file reali senza che nessuno
    # l'abbia deciso. La distinzione si legge dal proprio campo.
    r = assess(_bs(_unclassified_mass=D("178663.25"),
                   _unclassified_mass_measured=D("1")), {})
    assert r.massa_non_classificata is AccountStatus.UNRELIABLE
    assert r.all_critical_ok is True
