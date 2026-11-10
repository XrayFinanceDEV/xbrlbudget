"""Le parti pure dello script di punteggio della Fase 0 (`tests/corpus/punteggio.py`), su dati inventati.

Il giro vero fa girare l'importatore sui PDF dei clienti, fuori da git; qui si prova solo che il
confronto con la verità conti giusto: tolleranza, campi assenti a zero, dubbi esclusi, rifiuti attesi,
stabilità fra i giri.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("punteggio", Path(__file__).parent / "corpus" / "punteggio.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


def _vero(**campi):
    return {k: {"valore": v, "stato": "concorde"} for k, v in campi.items()}


def test_tolleranza_di_un_euro_e_campo_assente_vale_zero():
    vero = _vero(sp09=1000.00, sp06a=500.00, ce09a=0.0)
    letto = {"sp09": 1000.90, "sp06a": 498.00}           # ce09a assente: zero, come nel DB
    r = P.confronta_periodo(vero, letto)
    assert r["macro"] == {"giusti": 1, "totali": 1}
    assert r["kpi"] == {"giusti": 1, "totali": 2}
    assert [e["campo"] for e in r["errori"]] == ["sp06a"]
    assert r["errori"][0]["scarto"] == -2.0


def test_i_dubbi_non_pesano_sul_punteggio():
    vero = _vero(sp16=100.0)
    vero["sp16d"] = {"valore": 80.0, "stato": "dubbio"}
    r = P.confronta_periodo(vero, {"sp16": 100.0, "sp16d": 0.0})
    assert r["macro"] == {"giusti": 1, "totali": 1}
    assert r["kpi"] == {"giusti": 0, "totali": 0}
    assert r["dubbi"] == {"giusti": 0, "totali": 1}
    assert r["errori"] == []


def test_rifiuto_atteso_conta_come_esito_giusto():
    assert P.esito_atteso_rispettato("da rifiutare", importato=False)
    assert not P.esito_atteso_rispettato("da rifiutare", importato=True)
    assert P.esito_atteso_rispettato("importabile con avviso", importato=True)
    assert not P.esito_atteso_rispettato("importabile", importato=False)


def test_mesi_del_periodo_solo_per_gli_infrannuali():
    assert P.mesi_del_periodo("2026-01-01..2026-09-30") == 9
    assert P.mesi_del_periodo("2025-09-01..2026-08-31") is None      # esercizio intero non solare
    assert P.mesi_del_periodo("2025-01-01..2025-12-31") is None
    assert P.mesi_del_periodo(None) is None


def test_punteggio_e_sintesi_con_due_giri_diversi():
    vero = {"id": "X", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2025-12", "periodo": "2025-01-01..2025-12-31", "campi": _vero(sp09=10.0, ce01=50.0)},
                        {"fine": "2024-12", "periodo": "2024-01-01..2024-12-31", "campi": _vero(sp09=8.0)}]}
    giri = [
        {"importato": True, "quadra": True, "secondi": 1,
         "esercizi": [{"anno": 2025, "mesi": None, "campi": {"sp09": 10.0, "ce01": 50.0}},
                      {"anno": 2024, "mesi": None, "campi": {"sp09": 8.0}}]},
        {"importato": True, "quadra": True, "secondi": 1,
         "esercizi": [{"anno": 2025, "mesi": None, "campi": {"sp09": 10.0, "ce01": 40.0}}]},
    ]
    d = P.punteggio_documento(vero, giri)
    assert d["giri"][0]["periodi"][0]["macro"] == {"giusti": 2, "totali": 2}
    assert d["giri"][1]["periodi"][0]["macro"] == {"giusti": 1, "totali": 2}
    assert d["giri"][1]["periodi"][1]["salvato"] is False              # anno precedente non salvato
    assert d["stabilita"]["campi_instabili"] == ["ce01"]
    s = P.sintesi([d], {"X": {"tipologia": "ivcee/2-anni"}})
    assert s["esito_giusto"] == 1.0
    assert s["documenti_macro_tutti_esatti"] == 0.5
    assert s["macro_esatti"] == 0.75
    assert s["precedente_macro_esatti"] == 0.5
    assert s["documenti_instabili"] == 1


def test_un_documento_da_rifiutare_non_ha_confronto_dei_campi():
    vero = {"id": "Y", "giudizio_atteso": "da rifiutare", "periodi": [{"fine": "2025-12", "periodo": None, "campi": _vero(ce01=5.0)}]}
    d = P.punteggio_documento(vero, [{"importato": False, "errore": "PDFImportError: solo CE", "esercizi": []}])
    assert d["giri"][0]["esito_giusto"] is True
    assert d["giri"][0]["periodi"] == []


def test_l_esercizio_salvato_si_abbina_per_anno_non_per_posizione():
    assert P.anno_del_periodo("2025-12") == 2025
    assert P.anno_del_periodo(None) is None
    vero = {"id": "Z", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2025-12", "periodo": None, "campi": _vero(sp09=10.0)},
                        {"fine": "2024-12", "periodo": None, "campi": _vero(sp09=8.0)}]}
    giro = {"importato": True, "esercizi": [{"anno": 2026, "mesi": None, "campi": {"sp09": 10.0}}]}
    d = P.punteggio_documento(vero, [giro])
    assert [p["salvato"] for p in d["giri"][0]["periodi"]] == [False, False]   # l'anno sbagliato non conta


def test_un_confronto_infrannuale_salvato_come_anno_intero_si_segnala():
    vero = {"id": "W", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2026-09", "periodo": "2026-01-01..2026-09-30", "campi": _vero(sp09=10.0)},
                        {"fine": "2025-09", "periodo": "2025-01-01..2025-09-30", "campi": _vero(sp09=8.0)}]}
    giro = {"importato": True, "esercizi": [{"anno": 2026, "mesi": 9, "campi": {"sp09": 10.0}},
                                            {"anno": 2025, "mesi": None, "campi": {"sp09": 8.0}}]}
    d = P.punteggio_documento(vero, [giro])
    assert [p["periodo_giusto"] for p in d["giri"][0]["periodi"]] == [True, False]
    assert P.sintesi([d], {"W": {"tipologia": "x"}})["periodo_sbagliato"] == ["W 2025-09"]


# --- lettore di righe (Fase 2) e numeri invariati ----------------------------------------------------

def _giro(giro=1, *, quadra=True, sbil=0.0, utile_ce=None, sp13=None, lettore="assente", campi=None, importato=True,
          errore=None):
    g = {"id": "D", "giro": giro, "importato": importato, "quadra": quadra, "sbilancio": sbil, "errore": errore,
         "utile_ce": utile_ce, "sp13": sp13, "esercizi": [{"anno": 2025, "mesi": None, "campi": campi or {"sp09": 10.0}}]}
    if lettore != "assente":
        g["lettore"] = lettore
    return g


def _blocco(scarto, voce="B.7 Debiti", sezione="SP"):
    return {"voce": voce, "sezione": sezione, "scarto": scarto, "cercato": "debiti verso fornitori"}


def test_lettore_assente_negli_esiti_vecchi_non_solleva():
    a = P.analisi_lettore({"D": [_giro(), _giro(2)]})
    assert a["importati"] == 2 and a["assenti"] == 2
    assert P.righe_lettore(a)[-1].startswith("Lettore assente")


def test_sbilanciato_con_blocco_che_spiega_lo_sbilancio():
    let = {"esito": "ok", "secondi": 1.5, "blocchi_aperti": [_blocco("12.00"), _blocco(-500.0)]}
    g = _giro(quadra=False, sbil=-500.4, lettore=let)
    a = P.analisi_lettore({"D": [g]})
    assert (a["sbilanciati_documenti"], a["sbilanciati_con_blocco_giusto"], a["sbilanciati_spiegati"]) == (1, 1, 1)
    assert a["sbilanciati"][0]["spiega"] is True
    assert a["esiti"] == {"ok": 1} and a["secondi_max"] == 1.5
    md = "\n".join(P.righe_lettore(a))
    assert "| D |" in md and "sì" in md


def test_blocco_con_scarto_diverso_non_spiega_e_la_differenza_utile_conta():
    let = {"esito": "ok", "secondi": 1.0, "blocchi_aperti": [_blocco(300.0)]}
    no = P.analisi_lettore({"D": [_giro(quadra=False, sbil=-500.0, lettore=let)]})
    assert no["sbilanciati_con_blocchi"] == 1 and no["sbilanciati_spiegati"] == 0
    assert no["sbilanciati_con_blocco_giusto"] == 1                # sezione SP per uno sbilancio SP, anche se lo scarto non coincide
    si = P.analisi_lettore({"D": [_giro(quadra=False, sbil=-500.0, utile_ce=1000.0, sp13=700.5, lettore=let)]})
    assert si["sbilanciati_spiegati"] == 1                       # 1000 - 700,5 = 299,5: entro 1 € da 300


def test_sbilanciato_senza_blocchi_e_bilanciato_con_blocchi():
    let_vuoto = {"esito": "ok", "secondi": 0.5, "blocchi_aperti": []}
    let_blocchi = {"esito": "ok", "secondi": 0.5, "blocchi_aperti": [_blocco(9.0), _blocco(7.0)]}
    a = P.analisi_lettore({"A": [_giro(quadra=False, sbil=40.0, lettore=let_vuoto)],
                           "B": [_giro(quadra=True, lettore=let_blocchi)]})
    assert a["sbilanciati_giri"] == 1 and a["sbilanciati_con_blocchi"] == 0
    assert a["sbilanciati_senza_blocchi"] == ["A"]
    assert a["sbilanciati"][0]["blocchi"] == []
    assert a["bilanciati_con_blocchi_documenti"] == ["B"] and a["bilanciati_blocchi"] == 2


def test_un_rifiutato_resta_nel_lettore_e_si_dice_se_e_colpa_del_lettore():
    a = P.analisi_lettore({
        "R": [_giro(importato=False, quadra=None, errore="PDFImportError: solo CE")],
        "L": [_giro(importato=False, quadra=None, errore="Boom in importers/lettore/righe.py",
                    lettore={"esito": "errore", "secondi": 0.1}),
              _giro(2, importato=False, quadra=None, errore="altro", lettore={"esito": "errore", "secondi": 0.1})]})
    assert a["importati"] == 0 and len(a["falliti"]) == 3
    assert a["falliti_per_colpa_del_lettore"] == 2
    assert [f["chiave_lettore"] for f in a["falliti"]] == [False, True, True]
    md = "\n".join(P.righe_lettore(a))
    assert "falliti per colpa del lettore: 2" in md and "Giri non importati" in md


def test_percentuale_ok_sui_documenti_con_testo_e_scansioni_a_parte():
    ok = {"esito": "ok", "secondi": 1.0, "blocchi_aperti": []}
    a = P.analisi_lettore({
        "T1": [_giro(lettore=ok), _giro(2, lettore=ok)],
        "T2": [_giro(lettore=ok), _giro(2, lettore={"esito": "tempo", "secondi": 20.0})],
        "S": [_giro(lettore={"esito": "non_applicabile"}), _giro(2, lettore={"esito": "non_applicabile"})],
        "E": [_giro(lettore={"esito": "errore", "secondi": 0.2})]})
    assert (a["documenti_ok"], a["documenti_con_testo"]) == (1, 3)
    assert (a["giri_ok"], a["giri_con_testo"]) == (3, 5)
    assert a["scansioni"] == ["S"] and a["documenti_non_ok"] == ["T2", "E"]
    md = "\n".join(P.righe_lettore(a))
    assert "1/3 (33.3%)" in md and "3/5 (60.0%)" in md


def test_sbilanciato_per_maggioranza_dei_giri_e_sezione_ce_per_l_utile():
    ce = {"esito": "ok", "secondi": 1.0, "blocchi_aperti": [_blocco(77.0, sezione="CE")]}
    a = P.analisi_lettore({"D": [_giro(quadra=False, sbil=0.0, utile_ce=100.0, sp13=0.0, lettore=ce),
                                 _giro(2, lettore=ce), _giro(3, quadra=False, sbil=0.0, utile_ce=100.0, sp13=0.0, lettore=ce)],
                           "M": [_giro(quadra=False, sbil=9.0, lettore=ce), _giro(2), _giro(3)]})
    assert [d["id"] for d in a["sbilanciati"]] == ["D"]          # M e' sbilanciato in 1 giro su 3: non conta
    assert a["sbilanciati"][0]["giri_sbilanciati"] == "2/3" and a["sbilanciati"][0]["sezione_giusta"] is True
    assert a["sbilanciati"][0]["spiega"] is False                 # sezione giusta, scarto 77 != 100


def test_numeri_invariati_solo_sui_documenti_stabili():
    base = {"S": [_giro(1), _giro(2)],
            "I": [_giro(1, campi={"sp09": 1.0}), _giro(2, campi={"sp09": 2.0})],
            "C": [_giro(1), _giro(2)]}
    nuovi = {"S": [_giro(1), _giro(2)],
             "I": [_giro(1, campi={"sp09": 9.0})],
             "C": [_giro(1), _giro(2, campi={"sp09": 10.0, "ce01": 5.0})]}
    r = P.numeri_invariati(base, nuovi)
    assert r["stabili"] == 2 and r["invarianti"] == 1 and r["quota"] == 0.5
    assert r["instabili_nella_base"] == ["I"]
    assert r["cambiati"][0]["id"] == "C" and r["cambiati"][0]["giri"] == [2]
    assert [d["campo"] for d in r["cambiati"][0]["differenze"]] == ["2025/None ce01"]
    md = "\n".join(P.righe_invarianti(r, "base-x"))
    assert "50.0%" in md and "| C |" in md


def test_l_esito_diverso_dalla_base_e_una_differenza():
    r = P.numeri_invariati({"D": [_giro(1)]}, {"D": [_giro(1, importato=False)]})
    assert r["invarianti"] == 0 and r["cambiati"][0]["differenze"][0]["campo"] == "importato"


def test_un_documento_stabile_senza_giri_nuovi_non_e_invariato():
    base = {"S": [_giro(1), _giro(2)], "M": [_giro(1), _giro(2)]}
    r = P.numeri_invariati(base, {"S": [_giro(1)]})
    assert r["stabili"] == 2 and r["invarianti"] == 1 and r["quota"] == 0.5
    assert r["senza_giri_nuovi"] == ["M"]
    assert "(M)" in "\n".join(P.righe_invarianti(r, "b"))


def test_un_campo_presente_da_una_parte_sola_e_una_differenza_anche_se_zero():
    r = P.numeri_invariati({"D": [_giro(1, campi={"sp09": 1.0})]}, {"D": [_giro(1, campi={"sp09": 1.0, "ce01": 0.0})]})
    assert r["invarianti"] == 0
    assert r["cambiati"][0]["differenze"][0]["campo"] == "2025/None ce01"


def test_i_campi_differenti_di_tutti_i_giri_con_tetto_di_dieci():
    campi = {f"sp{n:02d}": 1.0 for n in range(1, 16)}
    nuovi = {"D": [_giro(1, campi=dict(campi, sp01=5.0)), _giro(2, campi={k: 2.0 for k in campi})]}
    r = P.numeri_invariati({"D": [_giro(1, campi=campi)]}, nuovi)
    c = r["cambiati"][0]
    assert c["giri"] == [1, 2] and c["campi_totali"] == 16 and len(c["differenze"]) == 10


# --- percorso del lettore (Fase 3) ----------------------------------------------------------------------

def _g3(giro=1, *, adottato=False, quadra=True, motivo=None, chiamate=2, voti=3, secondi=4.0, tetto=None,
        tappo=None, precedente="no", id_="D", importato=True, estrattore="llm"):
    lp = {"esito": "adottato" if adottato else "non_adottato", "chiamate": chiamate, "voti": voti, "secondi": secondi}
    if motivo:
        lp["motivo"] = motivo
    if tetto:
        lp["tetto_chiamate"] = 40
    esercizi = [{"anno": 2025, "mesi": None, "campi": {"sp09": 10.0}}]
    if precedente != "no":
        esercizi.append({"anno": 2024, "mesi": precedente, "campi": {"sp09": 9.0}})
    return {"id": id_, "giro": giro, "importato": importato, "quadra": quadra, "estrattore": estrattore, "esercizi": esercizi,
            "snello": {"fonte": "deterministico:lettore" if adottato else "llm", "lettore_percorso": lp,
                       "tappo_importo": tappo, "plug_residual": None}}


CAMP = {"D": {"tipologia": "contrapposte"}, "E": {"tipologia": "ivcee/2-anni"}, "161": {"tipologia": "conti/colonne"},
        "1426": {"tipologia": "conti/colonne"}}


def test_percorso_assente_negli_esiti_vecchi_non_solleva_e_si_dice():
    a = P.analisi_percorso({"D": [_giro(), _giro(2)]}, CAMP)
    assert a == {"presente": False}
    assert "Percorso del lettore assente" in "\n".join(P.righe_percorso(a))


def test_adozione_per_tipologia_e_instabilita():
    giri = {"D": [_g3(1, adottato=True), _g3(2, adottato=True), _g3(3, adottato=True)],
            "E": [_g3(1, adottato=True, id_="E"), _g3(2, id_="E"), _g3(3, id_="E")]}
    a = P.analisi_percorso(giri, CAMP)
    assert a["giri_adottati"] == 4 and a["giri_totali"] == 6
    assert a["per_tipologia"] == {"contrapposte": {"documenti": 1, "adottati": 1},
                                  "ivcee/2-anni": {"documenti": 1, "adottati": 1}}
    assert a["documenti_instabili_adozione"] == ["E"]
    assert "1/3 (instabile)" in "\n".join(P.righe_percorso(a))


def test_bersagli_quadrati_motivo_e_titolo():
    giri = {"161": [_g3(1, adottato=True, id_="161"), _g3(2, adottato=True, id_="161")],
            "1426": [_g3(1, quadra=False, motivo="foglie_non_in_pari", id_="1426"), _g3(2, quadra=True, id_="1426")]}
    a = P.analisi_percorso(giri, CAMP)
    assert a["bersagli_quadrati"] == 1                       # 1426 e' quadrato in un giro solo: non conta
    b1426 = next(b for b in a["bersagli"] if b["id"] == "1426")
    assert b1426["giri"][0]["motivo"] == "foglie_non_in_pari" and b1426["giri"][0]["quadrato"] is False
    md = "\n".join(P.righe_percorso(a))
    assert "**1/9 salvati quadrati**" in md and "foglie_non_in_pari" in md
    assert P.motivo_non_adozione(_g3(1, id_="x")) == "non_adottato"


def test_costo_chiusure_tetto_e_sbilanciati_contro_la_base():
    giri = {"D": [_g3(1, adottato=True, chiamate=2, voti=3, secondi=5.0, tappo="0.4"),
                  _g3(2, adottato=True, chiamate=10, voti=9, secondi=50.0, tetto=True)],
            "E": [_g3(1, quadra=False, id_="E"), _g3(2, quadra=False, id_="E")]}
    base = {"E": [_giro(1, quadra=False, sbil=5.0), _giro(2, quadra=False, sbil=5.0)],
            "D": [_giro(1, quadra=False, sbil=7.0), _giro(2, quadra=False, sbil=7.0)]}
    a = P.analisi_percorso(giri, CAMP, base)
    assert a["chiamate"] == {"mediana": 10, "max": 10} and a["voti"]["max"] == 9 and a["secondi"]["max"] == 50.0
    assert a["tetto_chiamate"] == ["D"] and a["chiusure_documenti"] == ["D"]
    assert a["sbilanciati_ora"] == ["E"] and sorted(a["sbilanciati_base"]) == ["D", "E"]


def test_anno_precedente_e_mesi_diversi_da_none():
    giri = {"D": [_g3(1, adottato=True, precedente=None), _g3(2, adottato=True, precedente=9)]}
    a = P.analisi_percorso(giri, CAMP)
    assert len(a["precedente_salvato"]) == 2
    assert a["precedente_con_mesi"] == [{"id": "D", "giro": 2, "anno": 2024, "mesi": 9}]
    assert "D g2 2024/9" in "\n".join(P.righe_percorso(a))


def test_peggiorati_con_fonte_prima_e_dopo():
    vero = {"id": "D", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2025-12", "periodo": None, "campi": _vero(sp09=10.0, ce01=50.0)}]}
    base_g = [_giro(1, campi={"sp09": 10.0, "ce01": 50.0})]
    base_g[0]["estrattore"] = "llm"
    nuovo_g = [_g3(1, adottato=True)]
    nuovo_g[0]["esercizi"][0]["campi"] = {"sp09": 10.0, "ce01": 1.0}
    p = P.peggiorati([P.punteggio_documento(vero, nuovo_g)], [P.punteggio_documento(vero, base_g)], {"D": nuovo_g}, {"D": base_g})
    assert p[0]["id"] == "D" and p[0]["calo"]["macro"] == (1.0, 0.5)
    assert p[0]["fonte_prima"] == "llm ×1" and p[0]["fonte_dopo"] == "deterministico:lettore ×1" and p[0]["dal_lettore"]
    uguale = P.peggiorati([P.punteggio_documento(vero, base_g)], [P.punteggio_documento(vero, base_g)], {"D": base_g}, {"D": base_g})
    assert uguale == []


def test_rapporto_completo_si_scrive_con_e_senza_percorso(tmp_path):
    vero = {"id": "D", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2025-12", "periodo": None, "campi": _vero(sp09=10.0)}]}
    giri = {"D": [_g3(1, adottato=True)]}
    doc = [P.punteggio_documento(vero, giri["D"])]
    sin = P.sintesi(doc, CAMP)
    meta = {"etichetta": "x", "documenti": 1, "ripetizioni": 1, "commit": "abc", "data": "oggi", "confronto": "b"}
    for percorso in (P.analisi_percorso(giri, CAMP), {"presente": False}):
        P.scrivi_rapporto(tmp_path, doc, sin, meta, P.analisi_lettore(giri), None, percorso, [])
        assert "Percorso del lettore" in (tmp_path / "punteggio.md").read_text()


def test_il_probe_registra_fonte_e_percorso_del_lettore():
    rec = {"import_snello": {"fonte": "deterministico:lettore", "esito": "ok", "lettore_percorso": {"esito": "adottato"},
                             "tappo": {"corrente": {"importo": "0.3"}}}, "plug_residual": "0.3"}
    s = P._snello_compatto(rec)
    assert s["fonte"] == "deterministico:lettore" and s["lettore_percorso"] == {"esito": "adottato"} and s["tappo_importo"] == "0.3"
    assert P._snello_compatto({}) is None


def test_ripiego_classico_usato_e_rifiutati_a_classico_spento():
    a1 = _g3(1); a1["snello"]["ripiego_classico"] = {"usato": True, "motivo": "ripiego"}
    a2 = _g3(2); a2["snello"]["ripiego_classico"] = {"usato": False, "motivo": None}
    s1 = _g3(1, id_="E"); s1["snello"]["ripiego_classico"] = {"usato": True, "motivo": "non_applicabile"}
    r1 = _g3(2, id_="E", importato=False); r1["snello"] = None
    r1["errore"] = "percorso classico spento (IMPORT_RIPIEGO_CLASSICO=0): nessun'altra strada"
    a = P.analisi_percorso({"D": [a1, a2], "E": [s1, r1]}, CAMP)
    rc = a["ripiego_classico"]
    assert rc["giri"] == 2 and rc["documenti"] == ["D", "E"]
    assert rc["motivi"] == {"non_applicabile": ["E"], "ripiego": ["D"]}
    assert rc["rifiutati_classico_spento"] == {"E": 1}
    md = "\n".join(P.righe_percorso(a))
    assert "| Ripiego classico usato: giri / documenti / motivi | 2 / 2 / non_applicabile (E); ripiego (D) |" in md
    assert "| Rifiutati a classico spento (documento ×giri) | E ×1 |" in md
    rec = {"import_snello": {"fonte": "llm", "ripiego_classico": {"usato": True, "motivo": "ripiego"}}}
    assert P._snello_compatto(rec)["ripiego_classico"] == {"usato": True, "motivo": "ripiego"}


# --- modalità corpus (tutti i PDF, senza verità) -----------------------------------------------------

def test_corpus_un_documento_per_contenuto_pdf_soli_fuori_dalle_cartelle_escluse():
    manifesto = {"files": [
        {"sha256": "a" * 64, "format": "pdf", "route_expected": "ivcee",
         "paths": ["2026-07/july_budget/budget_7_X.pdf", "2026-07/budget_7_X.pdf"]},
        {"sha256": "b" * 64, "format": "pdf", "route_expected": "unknown", "paths": ["lotto/budget_9_Y.pdf"]},
        {"sha256": "c" * 64, "format": "pdf", "route_expected": "unknown", "paths": ["lotto/budget_9_Z.pdf"]},
        {"sha256": "d" * 64, "format": "pdf", "route_expected": "unknown", "paths": ["lotto/senza numero.pdf"]},
        {"sha256": "e" * 64, "format": "xbrl", "route_expected": "xbrl", "paths": ["lotto/budget_5.xbrl"]},
        {"sha256": "f" * 64, "format": "pdf", "route_expected": "unknown", "paths": ["2026-07/july_budget/budget_8.pdf"]},
        {"sha256": "1" * 64, "format": "pdf", "route_expected": "ivcee", "paths": ["lotto/qualunque.pdf"]},
    ]}
    campione = {"315": {"id": "315", "sha256": "1" * 64}}
    docs = {d["id"]: d for d in P.documenti_del_corpus(manifesto, campione)}
    assert docs["7"]["path"] == "2026-07/budget_7_X.pdf" and docs["7"]["lotto"] == "2026-07"   # la copia è esclusa
    assert {"9-bbbbbb", "9-cccccc"} <= set(docs)            # stesso numero, contenuti diversi
    assert "sha-dddddddd" in docs
    assert docs["315"]["in_campione"] and not docs["7"]["in_campione"]
    assert len(docs) == 5                                    # niente XBRL, niente file solo nelle cartelle escluse


def test_anno_dal_nome_prima_del_testo_e_date_di_stampa_scartate():
    assert P.anno_dal_documento("al 31/12/2026", "budget_1_ROSSI_2025.pdf") == (2025, "nome del file")
    assert P.anno_dal_documento("", "Bilancino 31-5-26.pdf") == (2026, "nome del file")
    assert P.anno_dal_documento("dal 01/01/2025 al 31/12/2025\nData/Ora 30/09/2026 18:24:22", "x.pdf") == \
        (2025, "data di fine periodo")
    assert P.anno_dal_documento("Data di stampa: 30/06/2026\nPeriodo al 31.03.25", "x.pdf") == (2025, "data di fine periodo")
    assert P.anno_dal_documento("totale 12.31.92 e 15/03/2025", "x.pdf") == (None, "nessuna")   # 2092: oltre il prossimo
    assert P.anno_dal_documento("Esercizio 2024", "x.pdf") == (2024, "parola nel testo")
    assert P.anno_dal_documento("", "scan.pdf") == (None, "nessuna")


def test_rifiuti_attesi_errori_veri_e_servizio():
    assert P.tipo_rifiuto("PDFImportError: Documento non importabile come bilancio completo: solo CE.")["atteso"]
    assert P.tipo_rifiuto("Il documento è un riepilogo di sintesi (poche macro-voci)")["atteso"]
    s = P.tipo_rifiuto("MINERU_UNAVAILABLE: ConnectError: timeout")
    assert s["servizio"] and not s["atteso"]
    assert P.tipo_rifiuto("Importazione non salvata: nessun dato contabile estratto")["tipo"] == "estrazione vuota"
    assert P.tipo_rifiuto("KeyError: 'sp01'") == {"tipo": "altro errore", "atteso": False, "servizio": False}


def _giro_corpus(giro, importato=True, quadra=True, fonte="qwen", campi=None, **extra):
    return {"giro": giro, "importato": importato, "quadra": quadra, "secondi": 10.0 * giro,
            "snello": {"fonte": fonte, "letture_chiamate": 4, "lettore_percorso": {"chiamate": 2}},
            "esercizi": [{"anno": 2025, "mesi": None, "campi": campi or {"sp01": 1.0}}] if importato else [], **extra}


def test_documento_corpus_misura_quadratura_fonte_chiamate_e_instabilita():
    doc = {"id": "9", "lotto": "L", "route_expected": "ivcee", "path": "L/x.pdf", "in_campione": False,
           "anno": 2025, "anno_fonte": "nome del file", "mesi": None}
    stabile = P.documento_corpus(doc, [_giro_corpus(1), _giro_corpus(2)])
    assert stabile["esito"] == "importato" and stabile["quadra"] == "quadrato" and not stabile["instabile"]
    assert stabile["chiamate_mediana"] == 6 and stabile["secondi_max"] == 20.0
    sbil = _giro_corpus(2, quadra=False, fonte="deterministico:lettore", sbilancio=-12.5, utile_ce=100.0, sp13=90.0,
                 campi={"sp01": 2.0})
    d = P.documento_corpus(doc, [_giro_corpus(1), sbil])
    assert d["quadra"] == "misto" and d["sbilancio_sp_max"] == 12.5 and d["utile_ce_sp_max"] == 10.0
    assert d["instabile"] and d["campi_instabili"] == ["sp01"] and d["fonti"] == {"deterministico:lettore": 1, "qwen": 1}
    rif = P.documento_corpus(doc, [_giro_corpus(1, importato=False, errore="riepilogo di sintesi")])
    assert rif["esito"] == "rifiutato" and rif["rifiuto"]["atteso"] and rif["quadra"] is None
    s = P.sintesi_corpus([stabile, d, rif])
    assert s["totale"]["tutti"]["documenti"] == 3 and s["totale"]["tutti"]["rifiutati_attesi"] == 1
    assert s["lotto"]["L"]["sbilanciati"] == 1 and s["route_expected"]["ivcee"]["instabili"] == 1


def test_documento_corpus_col_campione_mette_accanto_macro_e_kpi():
    doc = {"id": "X", "lotto": "L", "route_expected": "ivcee", "path": "p", "in_campione": True,
           "anno": 2025, "anno_fonte": "verità", "mesi": None}
    vero = {"id": "X", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2025-12", "periodo": None, "campi": _vero(sp01=1.0, sp06a=5.0)}]}
    d = P.documento_corpus(doc, [_giro_corpus(1, campi={"sp01": 1.0, "sp06a": 3.0})], vero)
    assert d["macro"] == 1.0 and d["kpi"] == 0.0 and d["esito_giusto"]
