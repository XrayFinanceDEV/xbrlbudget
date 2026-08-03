"""Tre spazi di target: voce civilistica, marcatore di controllo, conto.

Sono tre domande contabili diverse e vanno tenute separate:
  voce    "che riga di legge e'?"        -> db_field, SOLO livello legale
  marker  "e' un totale/una sezione?"    -> non ha db_field: e' cio' che pilota i gate
  conto   "questo conto dove va, e ha    -> db_field + RUOLO (contra/fondo/risultato)
           natura rettificativa?"

Il vecchio resolver aveva solo il primo spazio: per questo il 100% dei marcatori
di controllo del corpus risultava irrisolto, ed e' li' che un'estrazione corretta
viene rifiutata.
"""
import pytest

from importers.label_semantics import classify_label as C


# --- spazio VOCE ---------------------------------------------------------------

def test_voce_grafie_diverse_stessa_voce():
    for desc in ["I. immateriali", "I - Immobilizzazioni immateriali",
                 "Immob. immateriali", "B.I IMMOBILIZZAZIONI IMMATERIALI",
                 "Totale immobilizzazioni immateriali"]:
        hit = C(desc, space="voce", side="attivo")
        assert hit is not None, f"non risolto: {desc}"
        assert hit.target == "sp02_immob_immateriali", f"{desc} -> {hit.target}"


def test_voce_restituisce_una_stringa_non_un_nodo():
    """Il vecchio `resolve` restituisce un Node: i chiamanti che si aspettavano un
    db_field confrontavano mele con pere."""
    hit = C("Immobilizzazioni materiali", space="voce", side="attivo")
    assert isinstance(hit.target, str) and hit.target == "sp03_immob_materiali"


# --- spazio MARKER -------------------------------------------------------------

@pytest.mark.parametrize("desc,want", [
    ("Totale attivo", "__tot_attivo"),
    ("TOTALE ATTIVITA'", "__tot_attivo"),
    ("TOTALE STATO PATRIMONIALE - ATTIVO", "__tot_attivo"),
    ("TOTALE A T T I V I T A", "__tot_attivo"),
    ("Totale passivo", "__tot_passivo"),
    ("Totale passività e netto", "__tot_passivo"),
    ("Stato patrimoniale attivo", "__sez_sp_attivo"),
    ("** A T T I V I T A'", "__sez_sp_attivo"),
    ("** P A S S I V I T A`", "__sez_sp_passivo"),
    ("Conto economico", "__sez_ce"),
    ("Totale a pareggio", "__pareggio"),
    ("Totale a quadratura", "__pareggio"),
    ("Utile d'esercizio", "__utile"),
    ("Utile Stato Patrimoniale", "__utile"),
    ("Perdita dell'esercizio", "__perdita"),
    ("Differenza", "__col_scostamento"),
    ("Scost.", "__col_scostamento"),
])
def test_marker_totali_e_sezioni(desc, want):
    hit = C(desc, space="marker")
    assert hit is not None, f"non risolto: {desc}"
    assert hit.target == want, f"{desc} -> {hit.target}"


def test_risultato_senza_segno_non_e_un_utile():
    """'Risultato del periodo' NON dice se e' utile o perdita: il marker e' neutro,
    il segno lo decide il chiamante (parola 'perdita', importo negativo, lato)."""
    for desc in ["Risultato del periodo", "Risultato d'esercizio",
                 "Risultato dell'esercizio"]:
        hit = C(desc, space="marker")
        assert hit is not None and hit.target == "__risultato", desc


def test_la_voce_di_legge_del_ce_non_e_un_header_di_colonna():
    """budget_176: 'Differenza tra valore e costi di produzione (A-B)' e' una VOCE
    dell'art. 2425 a x=117, NON l'intestazione della colonna analitica a x=460.
    Confondere le due cancella l'intera pagina (cutoff a x>=115)."""
    hit = C("Differenza tra valore e costi di produzione (A-B)", space="marker")
    assert hit is None or hit.target != "__col_scostamento"


def test_marker_non_matcha_per_substring():
    # 'Totale attivo circolante' e' un SUBTOTALE, non il totale dell'attivo
    hit = C("Totale attivo circolante", space="marker")
    assert hit is None or hit.target != "__tot_attivo"


# --- spazio CONTO --------------------------------------------------------------

@pytest.mark.parametrize("desc,side,target,role", [
    ("Fornitori", "passivo", "sp16_debiti_breve", None),
    ("Fatture da ricevere", "passivo", "sp16_debiti_breve", None),
    ("Clienti", "attivo", "sp06_crediti_breve", None),
    ("Banche c/anticipi su fattura", "passivo", "sp16_debiti_breve", None),
    ("Dipendenti c/retribuzioni", "passivo", "sp16_debiti_breve", None),
    ("Erario c/IVA", "passivo", "sp16_debiti_breve", None),
    ("F.do amm.to automezzi", "passivo", "sp03_immob_materiali", "contra_mat"),
    ("F.di ammor.to fabbricati", "passivo", "sp03_immob_materiali", "contra_mat"),
    ("F.do amm.to costi di impianto", "passivo", "sp02_immob_immateriali", "contra_immat"),
    ("Fondo svalutazione crediti", "passivo", "sp06_crediti_breve", "contra_crediti"),
    ("Fondo rischi su crediti", "passivo", "sp06_crediti_breve", "contra_crediti"),
    ("Fondo indennità suppletiva di clientela", "passivo", "sp14_fondi_rischi", "fondo_rischi"),
    ("Fondo manutenzioni cicliche", "passivo", "sp14_fondi_rischi", "fondo_rischi"),
    ("Fondo spese future", "passivo", "sp14_fondi_rischi", "fondo_rischi"),
    ("Fondo T.F.R.", "passivo", "sp15_tfr", None),
])
def test_conto_target_e_ruolo(desc, side, target, role):
    hit = C(desc, space="conto", side=side)
    assert hit is not None, f"non risolto: {desc}"
    assert hit.target == target, f"{desc} -> {hit.target}"
    assert hit.role == role, f"{desc} ruolo -> {hit.role}"


def test_fondo_rischi_su_crediti_e_contra_non_un_passivo():
    """Regola contabile: SVALUT/RISCHI + CREDIT rettifica C.II (i crediti sono al
    netto del fondo per legge), NON e' un fondo del passivo."""
    hit = C("F.di rischi su crediti", space="conto", side="passivo")
    assert hit.target == "sp06_crediti_breve" and hit.role == "contra_crediti"


def test_totali_riconosciuti_anche_abbreviati():
    for desc in ["Totale attività", "Tot. crediti", "T O T A L E   P A S S I V O"]:
        hit = C(desc, space="conto", side="attivo")
        assert hit is not None and hit.role == "totale", desc


def test_risultato_di_esercizio_ha_ruolo_risultato():
    hit = C("Utile di esercizio", space="conto", side="passivo")
    assert hit is not None and hit.role == "risultato"
    # ma l'utile PORTATO A NUOVO e' una riserva, non il risultato del periodo
    hit2 = C("Utili portati a nuovo", space="conto", side="passivo")
    assert hit2 is None or hit2.role != "risultato"


# --- specificita': il difetto simmetrico (corrispondenze FALSE) -----------------

def test_specificita_evita_le_corrispondenze_false():
    """Non solo 'non riconosce': anche 'riconosce la cosa sbagliata'. Una
    classificazione errata non lascia residuo, quindi nessun gate la intercetta."""
    assert C("Cassa previdenziale", space="conto", side="passivo").target != \
        "sp09_disponibilita_liquide"
    hit = C("Debiti rappresentati da titoli", space="conto", side="passivo")
    assert hit is None or not hit.target.startswith("sp08")


def test_sotto_soglia_ritorna_none_non_il_meno_peggio():
    assert C("Zufolo scaramantico aziendale", space="conto", side="attivo") is None


# --- separazione degli spazi ---------------------------------------------------

def test_lo_spazio_voce_non_restituisce_nodi_contra():
    """Il rischio concreto di doppio conteggio sono le RETTIFICHE: un fondo
    ammortamento non e' una riga di bilancio, e' una posta che ne riduce un'altra.
    Se risolvesse anche come 'voce', in aggregazione flat A/B verrebbe sommato
    accanto al cespite che deve invece nettare.

    NB: l'albero IV-CEE porta gia' da prima alcuni alias di livello conto
    ('erario conto', 'cassa', 'mutui', 'banche c/c passivi'), filtrati per lato.
    Non e' questo test a doverli rimuovere."""
    assert C("F.do amm.to automezzi", space="voce") is None
    assert C("Fondo svalutazione crediti", space="voce") is None
    # e nello spazio 'conto' invece ha un ruolo esplicito
    assert C("F.do amm.to automezzi", space="conto", side="passivo").role == "contra_mat"


def test_hit_espone_provenienza_e_specificita():
    hit = C("Immobilizzazioni immateriali", space="voce", side="attivo")
    assert hit.source in ("dizionario", "cache", "llm")
    assert 0.0 <= hit.specificity <= 1.0
    assert hit.reason
