"""Il dettaglio di un aggregato che il codice ha letto ma non sa ripartire: Qwen nomina la
voce di legge dei conti sotto, il codice decide (importers/dettaglio_dal_modello.py).

Caso guida: Unicarton 31/08/2026, mastro 67 COSTI PERSONALE DIPENDENTE 238.731,12 con
Retribuzioni lorde 179.047,90, Contributi INPS 52.997,00 e costi diversi 6.686,22. Le
parole chiave del lettore delle contrapposte non riconoscono RETRIBUZIONI ne' INPS, e
tutto finiva in ce08d.

Il modello e' sostituito da una funzione finta con la stessa firma di
lettura._testo(system, user, max_tokens): nessuna rete.

Run: python -m pytest tests/test_dettaglio_dal_modello.py -v
"""
import re
from decimal import Decimal as D

from importers import dettaglio_dal_modello as ddm

PERSONALE = [
    ("67", "COSTI PERSONALE DIPENDENTE", D("238731.12")),
    ("67.01", "COSTI PERSONALE DIPENDENTE", D("232044.90")),
    ("67.01.01", "Retribuzioni lorde", D("179047.90")),
    ("67.01.01.01", "Retribuzioni lorde dipendenti ordinari", D("179047.90")),
    ("67.01.03", "Contributi INPS", D("52997.00")),
    ("67.01.03.01", "Contributi INPS dipendenti ordinari", D("52997.00")),
    ("67.03", "COSTI DIVERSI PERSONALE DIPENDENTE", D("6686.22")),
    ("67.03.03", "Indenn.trasf.e altri rimb.spese dipend.", D("2618.95")),
    ("67.03.13", "Ricerca, formazione e addestramento", D("333.00")),
    ("67.03.25", "Visite mediche periodiche ai dipendenti", D("1157.00")),
    ("67.03.51", "Altri costi per il personale dipendente", D("630.00")),
    ("67.03.90", "Spese di vestiario personale dipendente", D("1947.27")),
]


def _figli(righe):
    def figli(c):
        pref = c + "."
        return [r for r in righe if r[0].startswith(pref) and "." not in r[0][len(pref):]]
    return figli


def _modello(regole):
    """Un Qwen finto: per ogni riga 'n|testo ...' del blocco risponde 'n percorso' secondo la
    prima parola chiave che trova; le chiamate restano contate."""
    chiamate = []

    def chiama(system, user, max_tokens):
        chiamate.append(user)
        out = []
        for linea in user.splitlines():
            m = re.match(r"^(\d+)\|(.*)$", linea)
            if not m:
                continue
            for parola, percorso in regole:
                if parola in m.group(2).upper():
                    out.append(f"{m.group(1)} {percorso}")
                    break
        return "\n".join(out)

    chiama.chiamate = chiamate
    return chiama


QWEN_PERSONALE = _modello([("RETRIBUZ", "CE.B.9.a"), ("INPS", "CE.B.9.b"),
                          ("COSTI DIVERSI", "CE.B.9.e"), ("", "CE.B.9.e")])


def test_le_foglie_scendono_solo_dove_i_figli_sommano_al_padre():
    foglie = ddm.foglie("67", "COSTI PERSONALE DIPENDENTE", D("238731.12"), _figli(PERSONALE))
    assert [f[0] for f in foglie] == [
        "67.01.01.01", "67.01.03.01", "67.03.03", "67.03.13", "67.03.25", "67.03.51", "67.03.90"]
    rotto = [r if r[0] != "67.03.90" else (r[0], r[1], D("1")) for r in PERSONALE]
    foglie = ddm.foglie("67", "COSTI PERSONALE DIPENDENTE", D("238731.12"), _figli(rotto))
    # 67.03 non quadra piu' coi suoi conti: resta foglia intera, gli altri rami scendono
    assert [f[0] for f in foglie] == ["67.01.01.01", "67.01.03.01", "67.03"]


def _da_dettagliare():
    return [ddm.albero("ce08", "67", "COSTI PERSONALE DIPENDENTE", D("238731.12"),
                       _figli(PERSONALE))]


def test_il_personale_di_unicarton_si_ripartisce_sulle_voci_di_b9():
    ce = {"ce08_costi_personale": D("238731.12"), "_ce_da_dettagliare": _da_dettagliare()}
    ce, report = ddm.dettaglia(ce, chiama=QWEN_PERSONALE)
    assert ce["ce08b_salari_stipendi"] == D("179047.90")
    assert ce["ce08c_oneri_sociali"] == D("52997.00")
    assert ce["ce08d_altri_costi_personale"] == D("6686.22")
    assert ce["ce08_costi_personale"] == D("238731.12")      # l'aggregato non si tocca
    assert "_ce_da_dettagliare" not in ce
    assert report["status"] == "applicato"
    assert report["spiegato"] == "238731.12" and report["non_spiegato"] == "0.00"


def test_una_foglia_che_il_modello_porta_fuori_dall_aggregato_resta_non_spiegata():
    """Il modello propone, il codice decide: una voce che non e' una sotto-voce di B.9 non
    sposta massa fuori dal personale (resta a finalize_pdf_residuals, dichiarata)."""
    qwen = _modello([("RETRIBUZ", "CE.B.9.a"), ("INPS", "CE.B.7"), ("", "CE.B.9.e")])
    ce = {"ce08_costi_personale": D("238731.12"), "_ce_da_dettagliare": _da_dettagliare()}
    ce, report = ddm.dettaglia(ce, chiama=qwen)
    assert ce["ce08b_salari_stipendi"] == D("179047.90")
    assert "ce08c_oneri_sociali" not in ce
    assert "ce06_servizi" not in ce
    assert report["non_spiegato"] == "52997.00"
    assert report["alberi"][0]["respinte"] == [["67.01.03.01", "Contributi INPS dipendenti ordinari",
                                                "52997.00", "CE.B.7"]]


def test_i_dettagli_gia_letti_si_sommano_non_si_sostituiscono():
    ce = {"ce08_costi_personale": D("240000.00"), "ce08a_tfr_accrual": D("1268.88"),
          "_ce_da_dettagliare": _da_dettagliare()}
    ce, _ = ddm.dettaglia(ce, chiama=QWEN_PERSONALE)
    assert ce["ce08a_tfr_accrual"] == D("1268.88")
    assert ce["ce08b_salari_stipendi"] == D("179047.90")


def test_senza_modello_non_cambia_nulla_e_lo_dice():
    def guasto(system, user, max_tokens):
        raise RuntimeError("gx10 non risponde")

    ce = {"ce08_costi_personale": D("238731.12"), "_ce_da_dettagliare": _da_dettagliare()}
    ce, report = ddm.dettaglia(ce, chiama=guasto)
    assert ce == {"ce08_costi_personale": D("238731.12")}
    assert report["status"] == "errore"
    ce, report = ddm.dettaglia({"ce08_costi_personale": D("1")}, chiama=guasto)
    assert report["status"] == "niente_da_dettagliare"


def test_una_sola_chiamata_per_pochi_conti():
    qwen = _modello([("RETRIBUZ", "CE.B.9.a"), ("INPS", "CE.B.9.b"), ("", "CE.B.9.e")])
    ddm.dettaglia({"ce08_costi_personale": D("238731.12"), "_ce_da_dettagliare": _da_dettagliare()},
                  chiama=qwen)
    assert len(qwen.chiamate) == 1


def test_il_lettore_delle_contrapposte_dichiara_il_mastro_del_personale():
    """Il lettore delle contrapposte (qui dalle tabelle MinerU di Unicarton) mette
    l'aggregato in ce08 e dichiara il mastro con le sue foglie in _ce_da_dettagliare."""
    import os
    from types import SimpleNamespace

    from importers.mineru_contrapposte import pdf_da_tabelle
    from importers.situazione_contabile_parser import extract_situazione_contabile
    from tests.test_mineru_contrapposte import SP, _tabella

    ce_tab = _tabella("CONTO ECONOMICO", [
        ["Costi", "Ricavi"],
        ["Codice", "Descrizione", "Importo", "Codice", "Descrizione", "Importo"],
        ["55", "ACQUISTI DI BENI", "180.000,00", "47", "RICAVI DELLE VENDITE", "300.000,00"],
        ["55.01", "Acquisti materie prime", "180.000,00", "47.01", "Vendite prodotti", "300.000,00"],
        ["67", "COSTI PERSONALE DIPENDENTE", "60.000,00", "", "", ""],
        ["67.01", "Retribuzioni lorde", "45.000,00", "", "", ""],
        ["67.03", "Contributi INPS", "15.000,00", "", "", ""],
        ["Totale costi                                  240.000,00", "",
         "Totale ricavi                                   300.000,00"],
        ["Utile d'esercizio                                 60.000,00", ""],
    ])
    percorso = pdf_da_tabelle(SimpleNamespace(tables=(SP, ce_tab)))
    try:
        bs, ce = extract_situazione_contabile(percorso)
    finally:
        os.remove(percorso)
    assert ce["ce08"] == D("60000.00")
    [a] = ce["_ce_da_dettagliare"]
    # questo percorso del lettore normalizza i codici alle sole cifre: sono identificativi
    assert a["aggregato"] == "ce08" and a["codice"] == "67"
    assert [(f[0], f[2]) for f in a["foglie"]] == [("6701", D("45000.00")), ("6703", D("15000.00"))]
