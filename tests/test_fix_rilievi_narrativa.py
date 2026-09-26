"""Test mirati del lotto 2 fix rilievi (2026-09-26) sulla narrativa del Business plan, per le
regole che non sono già coperte, con dati reali, da tests/test_rilievi_ambienta.py — qui la
`BusinessPlanData` è costruita a mano per isolare il ramo `of_mol` senza generare un intero
previsionale.
"""
from decimal import Decimal as D

from backend.app.renderers.business_plan.data import BusinessPlanData, Column
from backend.app.renderers.business_plan.narrative import key_points

FRASE = "gli oneri finanziari passano"


def _colonne():
    return (
        Column(period_id="historical:2026", year=2026, label="2026 C", is_base=True),
        Column(period_id="forecast:2027", year=2027, label="2027 P", is_base=False),
        Column(period_id="forecast:2028", year=2028, label="2028 P", is_base=False),
    )


def _dati(of_mol_base):
    return BusinessPlanData(
        company_name="TEST",
        workflow="bilancio",
        columns=_colonne(),
        base_description="",
        values={
            # dscr non-None su almeno un anno di piano perché la frase C09 vive dentro quel blocco
            "dscr": (None, D("1.5"), D("1.8")),
            "of_mol": (of_mol_base, D("20"), D("10")),
        },
    )


def _testo(data: BusinessPlanData) -> str:
    return " ".join(t for _, t in key_points(data))


def test_C09_oneri_su_mol_base_presente_parte_dalla_base():
    """La colonna base ha `of_mol`: la frase parte da lì, non dal primo anno di piano."""
    testo = _testo(_dati(D("30")))
    assert f"{FRASE} dal 30,00% al 10,00% del MOL" in testo


def test_C09_oneri_su_mol_base_none_ripiega_sul_primo_anno_di_piano():
    """La colonna base non ha `of_mol` (None): la frase ripiega sul primo anno di piano, come si
    comportava prima del fix — non deve sparire né sollevare un'eccezione."""
    testo = _testo(_dati(None))
    assert f"{FRASE} dal 20,00% al 10,00% del MOL" in testo


def test_C09_oneri_su_mol_assente_ovunque_non_produce_la_frase():
    """Né la base né il piano hanno `of_mol`: nessuna frase inventata."""
    data = BusinessPlanData(
        company_name="TEST",
        workflow="bilancio",
        columns=_colonne(),
        base_description="",
        values={"dscr": (None, D("1.5"), D("1.8"))},
    )
    assert FRASE not in _testo(data)
