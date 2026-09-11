"""La griglia del banco di parità: i tre profili nuovi del giro 2 esistono e fanno
quello che dicono, PRIMA di usarli come prova di una correzione.

**Perche' questo file esiste.** `scripts/parita_motore.py` non aveva nessuna prova
sulla propria griglia: un profilo che non arriva mai al motore — perche' la massa
del fixture e' zero, perche' il segnaposto non si sostituisce, perche' le rate non
sono frazionarie — e' INERTE, e un banco inerte dice «0 divergenze» come se fosse
un'assoluzione. E' il modo in cui I-a e I-3 sono rimasti invisibili: la revisione
li misura fuori griglia, con sonde usa-e-getta (`dump_batteria.py`, `sonda_i3.py`),
proprio perche' nessun profilo li raggiungeva. Qui la griglia la si guarda.

**Che cosa afferma.**

1. I tre profili nuovi (`pregresso_tributari_mezzo_cent`, `pregresso_altri`,
   `override_aggregato`) sono in `PROFILI`, in CODA, e la griglia li produce per
   ogni fixture (`costruisci_griglia` = fixture × profili, ids distinti).
2. Dove il profilo deve produrre un piano, il piano c'e' e le rate portano il
   MEZZO centesimo che serve a I-a e a I-3: un `residual_short` tondo non
   distingue la condizione quantizzata da una non quantizzata — dicono la
   stessa cosa, e il test sarebbe vuoto.
3. Dove il profilo NON deve produrre un piano (massa zero su quel fixture) il
   piano e' vuoto, non un piano con `opening` sbagliato: `validate_pregresso`
   lo rifiuterebbe e il banco racconterebbe un errore al posto di un numero.
4. `override_aggregato` forza il totale REALE del fixture + 15.000,37: il
   segnaposto "0" del profilo non arriva mai al motore.
5. Il fixture `altri` ha massa `altri_debiti` diversa da zero, quadra, e i suoi
   dettagli dei due gruppi debiti sommano agli aggregati: un fixture che non
   quadra non e' forecastabile, e il profilo che doveva testare ci sbatte
   sopra in silenzio.
"""
from decimal import Decimal as D
from pathlib import Path

import pytest

from calculations.forecast_engine import validate_pregresso
from scripts.parita_motore import FIXTURES, PROFILI, costruisci_griglia

SEME = 20260910
NUOVI = ("pregresso_tributari_mezzo_cent", "pregresso_altri", "override_aggregato",
         "pregresso_mezzo_cent_con_override")


def _bs_di(fixture):
    """Il bilancio base di un fixture, gia' scalato come lo usa la griglia."""
    for nome, bs, _ce, scala in FIXTURES:
        if nome == fixture:
            return {k: (v * scala).quantize(D("0.01")) for k, v in bs.items()}
    pytest.fail(f"fixture {fixture!r} non nella griglia: {[f[0] for f in FIXTURES]}")


def _scenario(sid, anni=2):
    g = _griglia(anni)
    if sid not in g:
        pytest.fail(f"la griglia non produce lo scenario {sid!r}: "
                    f"profili {[p for p in PROFILI]}, fixture {[f[0] for f in FIXTURES]}")
    return g[sid]


class _Bs:
    """Il «bilancio base» che `validate_pregresso` legge con `getattr`."""

    def __init__(self, valori):
        self._v = dict(valori)

    def __getattr__(self, nome):
        return self._v.get(nome)


def _griglia(anni=2):
    return {s["id"]: s for s in costruisci_griglia(SEME, anni)}


def _valori(scenario):
    return [a["valori"] for a in scenario["anni"]]


def _ha_mezzo_centesimo(amounts) -> bool:
    return any((D(str(a)) * 100) % 1 != 0 for a in amounts)


def test_i_tre_profili_nuovi_sono_in_coda_a_PROFILI():
    nomi = list(PROFILI)
    assert tuple(nomi[-4:]) == NUOVI, f"non sono in coda, e le estrazioni cambierebbero: {nomi}"
    assert len(nomi) == len(set(nomi))


def test_la_griglia_e_fixture_per_profili_e_ids_distinti():
    for anni in (2, 5):
        g = costruisci_griglia(SEME, anni)
        assert len(g) == len(FIXTURES) * len(PROFILI)
        ids = [s["id"] for s in g]
        assert len(set(ids)) == len(ids)
        for nome in NUOVI:
            assert sum(1 for i in ids if i.endswith("__" + nome)) == len(FIXTURES), nome
        # Stesso seme, stessa griglia: il confronto fra due versioni e' valido
        # solo perche' l'input non cambia fra le due esecuzioni.
        assert ids == [s["id"] for s in costruisci_griglia(SEME, anni)]


@pytest.mark.parametrize("fixture", ["tributari", "base"])
def test_pregresso_tributari_mezzo_cent_piano_dove_la_massa_c_e(fixture):
    scenario = _scenario(f"{fixture}__pregresso_tributari_mezzo_cent")
    piano = scenario["anni"][0]["valori"].get("pregresso")
    assert piano is not None, "il segnaposto del profilo non e' stato risolto"
    if fixture == "base":
        # `base` non ha un euro di `sp16e`/`sp17e`: scadenziare un euro che non
        # c'e' alzerebbe un errore, non un piano a zero.
        assert piano == {}, piano
        return
    trib = piano["debiti_tributari"]
    assert D(str(trib["opening"])) == D(str(trib["saldo"])) + D(str(trib["rateizzato"]))
    assert _ha_mezzo_centesimo(trib["amounts"]), \
        f"rate tonde: nessun `residual_short` sotto il centesimo, {trib['amounts']}"
    assert sum(D(str(a)) for a in trib["amounts"]) <= D(str(trib["rateizzato"])) + D("0.01")
    # Il piano deve essere ACCETTATO da `validate_pregresso` o lo scenario
    # sbatte su un errore di validazione invece di arrivare al motore.
    bs = {k: D(v) for k, v in scenario["bs"].items()}
    valido = validate_pregresso(piano, _Bs(bs), 2)
    assert "debiti_tributari" in valido
    assert D(str(valido["debiti_tributari"]["rateizzato"])) > 0


def test_pregresso_altri_piano_sul_fixture_con_la_massa():
    bs_altri = _bs_di("altri")
    scenario = _scenario("altri__pregresso_altri")
    altri = scenario["anni"][0]["valori"]["pregresso"]["altri_debiti"]
    assert D(str(altri["opening"])) == bs_altri["sp16g_altri_debiti_breve"] + \
        bs_altri["sp17g_altri_debiti_lungo"]
    assert _ha_mezzo_centesimo(altri["amounts"]), \
        f"rate tonde: il secchio forzato non produce alcun residuo, {altri['amounts']}"
    # SUGLI ALTRI fixture il profilo e' inerente di proposito: la massa e' zero.
    for fixture, _bs, _ce, _scala in FIXTURES:
        if fixture == "altri":
            continue
        assert _scenario(f"{fixture}__pregresso_altri")["anni"][0]["valori"]["pregresso"] == {}


def test_override_aggregato_forza_il_totale_del_fixture_non_il_segnaposto():
    for fixture, bs_base, _ce, scala in FIXTURES:
        scenario = _scenario(f"{fixture}__override_aggregato", anni=5)
        atteso = (D(str(bs_base["sp16_debiti_breve"])) * scala).quantize(D("0.01")) + D("15000.37")
        for v in _valori(scenario):
            ov = v["sp_overrides"]
            assert list(ov) == ["sp16_debiti_breve"], f"{fixture}: {ov}"
            assert D(str(ov["sp16_debiti_breve"])) == atteso, (fixture, ov)
            assert "pregresso" not in v, f"{fixture}: un profilo di solo override non pianifica"
        assert "pregresso" not in scenario["anni"][0]["valori"]


def test_un_piano_sopra_la_massa_non_e_un_silenzio():
    """Il verso giusto della scelta di `profilo_pregresso_altri`: su un fixture
    senza massa il profilo NON emette un piano (`{}`), perche' un piano con
    l'`opening` sbagliato deve essere RUMOROSO — `validate_pregresso` alza, e
    il banco lo scrive nell'`errore` dello scenario. Se un domani il profilo
    emitsse comunque un piano, questo test resta verde (la guardia c'e') e
    quello sul `{}` diventa rosso: le due cose insieme raccontano quale dei due
    destini ha scelto il profilo."""
    with pytest.raises(ValueError) as esc:
        validate_pregresso({"altri_debiti": {"opening": 55000,
                                             "amounts": [18333.335, 18333.335]}},
                           _Bs({}), 2)
    assert "altri debiti" in str(esc.value), str(esc.value)


def test_il_piano_di_un_profile_a_zero_massa_non_arriva_al_motore():
    scenario = _scenario("base__pregresso_altri")
    assert scenario["anni"][0]["valori"]["pregresso"] == {}
    for a in scenario["anni"][1:]:
        assert "pregresso" not in a["valori"], "il piano vive solo sulla prima riga"


def test_il_fixture_altri_quadra_e_i_debiti_sommano_agli_aggregati():
    bs = _bs_di("altri")
    attivo = sum(v for k, v in bs.items() if k in (
        "sp02_immob_immateriali", "sp03_immob_materiali", "sp05_rimanenze",
        "sp06_crediti_breve", "sp09_disponibilita_liquide"))
    passivo = sum(v for k, v in bs.items() if k in (
        "sp11_capitale", "sp12_riserve", "sp13_utile_perdita", "sp15_tfr",
        "sp16_debiti_breve", "sp17_debiti_lungo"))
    assert attivo == passivo, (attivo, passivo)
    assert bs["sp16g_altri_debiti_breve"] + bs["sp17g_altri_debiti_lungo"] > 0
    assert bs["sp16_debiti_breve"] == bs["sp16d_debiti_fornitori_breve"] + bs["sp16g_altri_debiti_breve"]
    assert bs["sp17_debiti_lungo"] == bs["sp17a_debiti_banche_lungo"] + bs["sp17g_altri_debiti_lungo"]


def test_nei_profili_nuovi_nessun_segnaposto_arriva_al_motore():
    """`_pregresso_chiavi`/`_pregresso_frazioni`/`_pregresso_mezzo_cent` NON sono
    colonne di `BudgetAssumptions`: se restassero nel `valori` il driver del banco
    le ignorerebbe in silenzio e il profilo sarebbe un `neutro` travestito."""
    chiavi_interne = {"_pregresso_chiavi", "_pregresso_frazioni", "_pregresso_mezzo_cent"}
    for sid, scenario in _griglia(5).items():
        for v in _valori(scenario):
            assert not (chiavi_interne & set(v)), (sid, sorted(chiavi_interne & set(v)))


def test_script_di_parita_non_ha_profili_fantasma():
    """Ogni profilo dichiarato in coda a `PROFILI` deve comparire in almeno un id."""
    for nome in PROFILI:
        assert any(sid.endswith("__" + nome) for sid in _griglia()), nome


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
