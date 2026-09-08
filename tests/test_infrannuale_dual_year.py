"""Tests per il ramo infrannuale comparato dell'import PDF IV-CEE (issue #50).

Spec: la issue #50 — il ramo infrannuale tornava direttamente dal prompt a due anni,
senza la mitigazione che il ramo annuale si e' dato contro la perdita di una riga
dell'anno corrente (budget_227).

Run:  python -m pytest tests/test_infrannuale_dual_year.py -v

Nessuna chiamata di rete: la guardia sulla colonna e' logica pura su due dizionari.
Serve proprio a questo — e' l'unica parte della correzione verificabile senza il
corpus dei PDF reali.
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.pdf_importer import _single_year_read_prior_column  # noqa: E402

D = Decimal


def _sheet(attivo, cassa, capitale, risultato):
    return {
        "totale_attivo": D(attivo),
        "totale_passivo": D(attivo),
        "sp09_disponibilita_liquide": D(cassa),
        "sp11_capitale": D(capitale),
        "sp13_utile_perdita": D(risultato),
    }


# La colonna parziale (9 mesi 2025) e quella di raffronto (12 mesi 2024).
PARZIALE = _sheet("500000", "40000", "100000", "30000")
RAFFRONTO = _sheet("470000", "25000", "100000", "45000")


# --------------------------------------------------- la guardia scatta

def test_scatta_quando_il_singolo_anno_ha_letto_la_colonna_di_raffronto():
    """Il caso che la issue teme: su due colonne NON omogenee (9 mesi contro 12)
    l'estrattore a un anno legge la colonna sbagliata. Il foglio quadra lo stesso,
    quindi nessun controllo di quadratura se ne accorge: lo vede solo il confronto
    con il comparato che il passaggio a due anni etichetta esplicitamente."""
    assert _single_year_read_prior_column(RAFFRONTO, PARZIALE, RAFFRONTO) is True


def test_una_differenza_di_arrotondamento_non_salva_dal_verdetto():
    """Leggere la stessa colonna due volte da' gli stessi importi, non importi
    simili: la tolleranza e' quella dell'euro, non una soglia di somiglianza."""
    quasi = dict(RAFFRONTO)
    quasi["sp09_disponibilita_liquide"] = D("25000.40")
    assert _single_year_read_prior_column(quasi, PARZIALE, RAFFRONTO) is True


# --------------------------------------------------- la guardia non scatta

def test_non_scatta_sul_caso_normale():
    assert _single_year_read_prior_column(PARZIALE, PARZIALE, RAFFRONTO) is False


def test_due_colonne_soltanto_simili_non_sono_la_stessa_colonna():
    """Un attivo a 9 mesi e uno a 12 mesi si somigliano — le poste patrimoniali si
    muovono piano. Somigliarsi non basta: il falso positivo qui costerebbe la
    colonna giusta."""
    simile = _sheet("470500", "25100", "100000", "44000")
    assert _single_year_read_prior_column(simile, PARZIALE, RAFFRONTO) is False


def test_senza_comparato_non_si_sa_e_non_si_blocca():
    """Un controllo che manca e' «non lo so», e «non lo so» non blocca."""
    assert _single_year_read_prior_column(PARZIALE, PARZIALE, None) is False
    assert _single_year_read_prior_column(PARZIALE, PARZIALE, {}) is False


def test_senza_il_corrente_del_dual_non_si_sa():
    assert _single_year_read_prior_column(RAFFRONTO, {}, RAFFRONTO) is False


def test_troppe_poche_ancore_non_bastano_per_un_verdetto():
    """Con una sola voce non nulla in comune la coincidenza e' plausibile: si tace."""
    magro = {"totale_attivo": D("470000")}
    assert _single_year_read_prior_column(magro, {"totale_attivo": D("500000")}, magro) is False


def test_un_comparato_identico_al_corrente_non_permette_alcun_verdetto():
    """Se il passaggio a due anni restituisce due colonne uguali, il confronto non
    distingue nulla: non e' una contraddizione, e' assenza di informazione."""
    assert _single_year_read_prior_column(RAFFRONTO, RAFFRONTO, RAFFRONTO) is False


def test_le_chiavi_diagnostiche_non_contano_come_ancore():
    """Una diagnostica non e' una posta di bilancio: se contasse come ancora, due
    letture della STESSA colonna con residui diversi non si riconoscerebbero piu'."""
    prior = dict(RAFFRONTO)
    prior["_plug_residual"] = D("999")
    single = dict(RAFFRONTO)
    single["_plug_residual"] = D("0")
    assert _single_year_read_prior_column(single, PARZIALE, prior) is True


def test_le_voci_a_zero_non_contano_come_ancore():
    """Tre zeri in comune non sono tre prove: un bilancio abbreviato lascia a zero
    intere famiglie di dettaglio, e coinciderebbero fra qualunque coppia di anni."""
    magro_prior = {"totale_attivo": D("470000"), "sp02_immob_immateriali": D("0"),
                   "sp03_immob_materiali": D("0"), "sp05_rimanenze": D("0")}
    magro_single = dict(magro_prior)
    magro_current = {"totale_attivo": D("500000"), "sp02_immob_immateriali": D("0"),
                     "sp03_immob_materiali": D("0"), "sp05_rimanenze": D("0")}
    assert _single_year_read_prior_column(magro_single, magro_current, magro_prior) is False
