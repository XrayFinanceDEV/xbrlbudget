"""Task 6: righe di totale e parentela, colonna per colonna. Decide la somma stampata, mai il codice."""
from importers.lettore import Documento, leggi_pdf
from tests.lettore.pdf_sintetico import scrivi_pdf

_X_ETICHETTA = 50
_COLONNE = (400, 480)


def _leggi(tmp_path, voci, nome="t.pdf") -> Documento:
    p = tmp_path / nome
    scrivi_pdf(p, [voci])
    return leggi_pdf(str(p))


def _righe(y0, righe, passo=14, colonne=_COLONNE):
    """`righe`: (etichetta, importo per colonna...) oppure (x, etichetta, importi...) per una riga rientrata."""
    voci = []
    for k, riga in enumerate(righe):
        y = y0 + k * passo
        x = _X_ETICHETTA
        if isinstance(riga[0], (int, float)):
            x, riga = riga[0], riga[1:]
        etichetta, importi = riga[0], riga[1:]
        if etichetta:
            voci.append((x, y, etichetta))
        for colonna, importo in zip(colonne, importi):
            if importo:
                voci.append((colonna, y, importo))
    return voci


def _riga(doc, etichetta):
    trovate = [r for r in doc.righe if r.etichetta == etichetta]
    assert len(trovate) == 1, [r.etichetta for r in doc.righe]
    return trovate[0]


def test_totale_e_figli_su_una_colonna(tmp_path):
    doc = _leggi(tmp_path, _righe(140, [("Conto uno", "100,00"), ("Conto due", "250,00"), ("Conto tre", "470,00"),
                                        ("Totale", "820,00")]))
    totale = _riga(doc, "Totale")
    assert totale.totale
    assert totale.figli[0] == tuple(_riga(doc, e).id for e in ("Conto uno", "Conto due", "Conto tre"))
    assert not any(_riga(doc, e).totale for e in ("Conto uno", "Conto due", "Conto tre"))


def test_totale_che_precede_i_figli(tmp_path):
    # schema con dettaglio: la voce stampa l'importo, poi i conti che la compongono
    doc = _leggi(tmp_path, _righe(140, [("Crediti verso clienti", "820,00"), ("Clienti Italia", "100,00"),
                                        ("Clienti estero", "250,00"), ("Ricevute bancarie", "470,00")]))
    voce = _riga(doc, "Crediti verso clienti")
    assert voce.totale
    assert set(voce.figli[0]) == {_riga(doc, e).id for e in ("Clienti Italia", "Clienti estero", "Ricevute bancarie")}
    assert _riga(doc, "Clienti estero").padre == voce.id


def test_colonna_precedente_che_non_torna(tmp_path):
    # budget_1445: il TFR torna sulla corrente (161.654,36 + 97.660,80 + 128.192,34) e non sulla precedente
    # (401.361,79 stampato, 333.227,76 dai conti): la corrente resta, la precedente si dichiara
    doc = _leggi(tmp_path, _righe(140, [
        ("C) TRATTAMENTO DI FINE RAPPORTO", "387.507,50", "401.361,79"),
        ("Fondo TFR impiegati", "161.654,36", "150.000,00"),
        ("Fondo TFR operai", "97.660,80", "90.000,00"),
        ("Fondo TFR dirigenti", "128.192,34", "93.227,76")]))
    tfr = _riga(doc, "C) TRATTAMENTO DI FINE RAPPORTO")
    assert tfr.totale
    assert len(tfr.figli[0]) == 3
    assert not tfr.figli.get(1)
    avvisi = [a for a in doc.avvisi if "68.134,03" in a]
    assert len(avvisi) == 1
    assert "TRATTAMENTO DI FINE RAPPORTO" in avvisi[0]


def test_mastro_e_foglie_non_si_sommano_due_volte(tmp_path):
    doc = _leggi(tmp_path, _righe(140, [("FORNITORI", "100,00"), ("Fornitore Alfa", "60,00"),
                                        ("Fornitore Beta", "40,00"), ("Totale", "100,00")]))
    mastro, totale = _riga(doc, "FORNITORI"), _riga(doc, "Totale")
    assert mastro.figli[0] == (_riga(doc, "Fornitore Alfa").id, _riga(doc, "Fornitore Beta").id)
    assert totale.figli[0] == (mastro.id,)
    assert _riga(doc, "Fornitore Alfa").padre == mastro.id
    assert mastro.padre == totale.id


def test_prefisso_del_codice_non_decide(tmp_path):
    # AGO: mastri a 8 cifre, conti a 9, nessuno prefisso del proprio mastro; «100000021» comincia perfino col codice
    # dell'altro mastro (10000002), ma la somma lo mette sotto il primo
    righe = [("10000001", "IMMOBILIZZAZIONI", "900,00"), ("100000102", "Terreni", "200,00"),
             ("100000021", "Fabbricati", "700,00"), ("10000002", "CREDITI", "430,00"),
             ("100000201", "Clienti", "180,00"), ("100000202", "Erario", "250,00")]
    voci = []
    for k, (codice, etichetta, importo) in enumerate(righe):
        y = 140 + k * 14
        voci += [(40, y, codice), (110, y, etichetta), (480, y, importo)]
    doc = _leggi(tmp_path, voci)
    immob, crediti = _riga(doc, "IMMOBILIZZAZIONI"), _riga(doc, "CREDITI")
    assert immob.codice == "10000001" and _riga(doc, "Fabbricati").codice == "100000021"
    assert _riga(doc, "Fabbricati").padre == immob.id and _riga(doc, "Fabbricati").padre_verificato
    assert _riga(doc, "Terreni").padre == immob.id
    assert {_riga(doc, e).padre for e in ("Clienti", "Erario")} == {crediti.id}


def test_stampa_all_unita_tollera_un_euro(tmp_path):
    righe = [("Voce uno", "1.200"), ("Voce due", "2.300"), ("Voce tre", "3.700"), ("Totale", "7.201"),
             ("Altra uno", "4.100"), ("Altra due", "5.200"), ("Totale altre", "9.300")]
    doc = _leggi(tmp_path, _righe(140, righe))
    assert doc.profilo.decimali.get(0) is False
    assert _riga(doc, "Totale").totale
    assert len(_riga(doc, "Totale").figli[0]) == 3


def test_al_centesimo_un_euro_non_basta(tmp_path):
    righe = [("Voce uno", "1.200,00"), ("Voce due", "2.300,00"), ("Voce tre", "3.700,00"), ("Totale", "7.201,00"),
             ("Altra uno", "4.100,00"), ("Altra due", "5.200,00"), ("Totale altre", "9.300,00")]
    doc = _leggi(tmp_path, _righe(140, righe))
    assert _riga(doc, "Totale altre").totale
    assert not _riga(doc, "Totale").totale


def test_stessa_descrizione_in_due_mastri(tmp_path):
    doc = _leggi(tmp_path, _righe(140, [("FORNITORI", "400,00"), ("Fornitori Italia", "300,00"), ("Altri", "100,00"),
                                        ("CLIENTI", "250,00"), ("Clienti Italia", "200,00"), ("Altri", "50,00")]))
    altri = [r for r in doc.righe if r.etichetta == "Altri"]
    assert len(altri) == 2
    assert [a.percorso[-1] for a in altri] == ["FORNITORI", "CLIENTI"]
    assert all(a.padre_verificato for a in altri)
    assert [a.padre for a in altri] == [_riga(doc, "FORNITORI").id, _riga(doc, "CLIENTI").id]


def test_mastro_solo_intestazione(tmp_path):
    voci = [(40, 126, "10"), (80, 126, "IMMOBILIZZAZIONI")]
    voci += _righe(140, [("Terreni", "100,00"), ("Fabbricati", "250,00"), ("Impianti", "470,00"),
                         ("Automezzi", "1.010,00")])
    doc = _leggi(tmp_path, voci)
    titolo = next(r for r in doc.righe if "IMMOBILIZZAZIONI" in r.etichetta)
    assert titolo.intestazione
    for e in ("Terreni", "Fabbricati", "Impianti", "Automezzi"):
        conto = _riga(doc, e)
        assert conto.padre == titolo.id
        assert not conto.padre_verificato
        assert "IMMOBILIZZAZIONI" in conto.percorso[-1]
    assert not any(r.totale for r in doc.righe)


def test_percorso_fino_alla_sezione(tmp_path):
    voci = [(50, 112, "STATO PATRIMONIALE")]
    voci += _righe(140, [("DEBITI", "1.000,00"), ("FORNITORI", "700,00"), ("c/anticipi", "300,00"),
                         ("Anticipo Alfa", "100,00"), ("Anticipo Beta", "200,00"), ("Fornitori Italia", "400,00"),
                         ("ALTRI DEBITI", "300,00"), ("Erario", "120,00"), ("Istituti previdenziali", "180,00")])
    doc = _leggi(tmp_path, voci)
    assert _riga(doc, "Anticipo Alfa").percorso == ("SP", "DEBITI", "FORNITORI", "c/anticipi")
    assert _riga(doc, "Anticipo Alfa").padre_verificato
    assert _riga(doc, "c/anticipi").percorso == ("SP", "DEBITI", "FORNITORI")
    assert _riga(doc, "Erario").percorso == ("SP", "DEBITI", "ALTRI DEBITI")


def test_totale_vince_sull_intestazione(tmp_path):
    voci = [(50, 126, "CREDITI")]
    voci += _righe(140, [("Conto Alfa", "100,00"), ("Conto Beta", "50,00"), ("DEBITI DIVERSI", "150,00"),
                         ("Banca", "1.010,00")])
    doc = _leggi(tmp_path, voci)
    debiti = _riga(doc, "DEBITI DIVERSI")
    assert _riga(doc, "CREDITI").intestazione
    for e in ("Conto Alfa", "Conto Beta"):
        assert _riga(doc, e).padre == debiti.id
        assert _riga(doc, e).padre_verificato
        assert _riga(doc, e).percorso[-1] == "DEBITI DIVERSI"
    avvisi = [a for a in doc.avvisi if "CREDITI" in a and "DEBITI DIVERSI" in a]
    assert len(avvisi) == 1


# --------------------------------------------------------------------------------------
# Fix round 1: documenti costruiti a mano, per fissare una regola sola
# --------------------------------------------------------------------------------------

from decimal import Decimal  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from importers.lettore import leggi_importo  # noqa: E402
from importers.lettore.colonne import Colonna  # noqa: E402
from importers.lettore.righe import Riga  # noqa: E402
from importers.lettore.totali import assegna_padri, marca_totali  # noqa: E402


def _documento(righe, *, colonne=1, correnti=(), pagina_di=None, sezione="SP", sezioni=None, tipo="schema"):
    """`righe`: (x, codice, etichetta, importi...) con importi None per una cella vuota; nessun importo = titolo.
    `x` puo' essere una coppia (x del codice, x dell'etichetta)."""
    out = []
    for k, (x, codice, etichetta, *importi) in enumerate(righe, start=1):
        pagina = pagina_di(k) if pagina_di else 1
        x, x_etichetta = x if isinstance(x, tuple) else (x, None)
        celle = {c: leggi_importo(v) for c, v in enumerate(importi) if v is not None}
        out.append(Riga(id=f"p{pagina}r{k}U", pagina=pagina, y=100.0 + k, lato="U", sezione=sezione, codice=codice,
                        etichetta=etichetta, celle=celle, intestazione=not celle, x=x, x_etichetta=x_etichetta))
    cols = [Colonna(c, 400.0 + 80 * c, "U", "esercizio", None, None, None, c in correnti) for c in range(colonne)]
    doc = Documento(out, cols, False, [], SimpleNamespace(decimali={c: True for c in range(colonne)},
                                                          sezioni=sezioni or {}, tipo=tipo))
    marca_totali(doc)
    assegna_padri(doc)
    return doc


def _un_totale_per_colonna(doc):
    visti = {}
    for t in doc.righe:
        for c, figli in t.figli.items():
            for f in figli:
                assert (c, f) not in visti, (f, c, visti[(c, f)], t.id)
                visti[(c, f)] = t.id


def _conto(doc, etichetta):
    return _riga(doc, etichetta)


def test_costo_e_fondo_sotto_una_voce(tmp_path):
    # 1440/1445: «7) Altre» vale costo meno fondo, 0; il totale sopra non si prende la coppia grezza
    doc = _leggi(tmp_path, _righe(140, [("1) Costi di impianto", "300,00"), ("Costo impianto", "500,00"),
                                        ("Fondo impianto", "-200,00"), ("7) Altre", "0,00"),
                                        ("Costo altre", "1.000,00"), ("Fondo altre", "-1.000,00"),
                                        ("Totale I", "300,00")]))
    _un_totale_per_colonna(doc)
    altre = _riga(doc, "7) Altre")
    assert _riga(doc, "Costo altre").padre == altre.id and _riga(doc, "Fondo altre").padre == altre.id
    assert _riga(doc, "Costo altre").id not in _riga(doc, "Totale I").figli.get(0, ())


def test_mastro_e_foglia_non_fanno_un_totale():
    # 302: sulla precedente 2.999 + 2.999 = 5.998 per coincidenza, ma la seconda riga e' la foglia della prima
    doc = _documento([(34, "", "GRUPPO", "25,00", "25,00"), (90, "", "g uno", "10,00", "10,00"),
                      (90, "", "g due", "15,00", "15,00"), (34, "", "AUTOCARRI", "70,00", "60,00"),
                      (34, "", "Fondi", "30,00", "30,00"), (34, "", "F/AMM", "30,00", "30,00")], colonne=2)
    _un_totale_per_colonna(doc)
    assert 1 not in _conto(doc, "AUTOCARRI").figli
    assert _conto(doc, "F/AMM").padre == _conto(doc, "Fondi").id
    assert any("mastro e la sua foglia" in a for a in doc.avvisi)


def test_gemelli_non_sono_verificati():
    # R14, 373: due conti uguali uno sotto l'altro sono fratelli; la catena resta un'ipotesi
    doc = _documento([(20, "", "Fornitori", "300,00"), (20, "", "Alfa", "100,00"), (20, "", "Beta", "200,00"),
                      (20, "", "NOLEGGIO FIAT 600 A", "340,79"), (20, "", "NOLEGGIO FIAT 600 B", "340,79")])
    assert not _conto(doc, "NOLEGGIO FIAT 600 B").padre_verificato
    assert _conto(doc, "Alfa").padre_verificato


def test_catena_solo_all_uguaglianza_esatta():
    # R14, 405: 19,99 non e' il totale di 19,98, anche se la tolleranza delle somme e' un centesimo
    doc = _documento([(20, "", "Fornitori", "300,00"), (20, "", "Alfa", "100,00"), (20, "", "Beta", "200,00"),
                      (20, "", "SELL ERR OU", "19,99"), (20, "", "conto vicino", "19,98")])
    assert not _conto(doc, "SELL ERR OU").totale
    assert _conto(doc, "conto vicino").padre != _conto(doc, "SELL ERR OU").id


def test_figlio_meno_rientrato_rifiutato():
    # R14, 302: un conto a 85 non e' il totale della voce a 34 che lo segue
    doc = _documento([(34, "", "Fornitori", "300,00"), (85, "", "Alfa", "100,00"), (85, "", "Beta", "200,00"),
                      (85, "", "Conto foglia", "500,00"), (34, "", "B) VOCE", "500,00")])
    assert not _conto(doc, "Conto foglia").totale
    assert _conto(doc, "B) VOCE").padre != _conto(doc, "Conto foglia").id


def test_mastro_senza_foglie_chiude_il_suo_gruppo():
    # 1325: «Totale FORNITORI ESTERI» non ha conti stampati, ma chiude comunque il mastro 0702
    doc = _documento([(16, "0702", "FORNITORI ESTERI"), (272, "", "Totale FORNITORI ESTERI:", "1.793.155,12"),
                      (16, "0703", "FATTURE DA RICEVERE"), (62, "07030001", "FATTURE A", "100,00"),
                      (62, "07030002", "FATTURE B", "250,00"), (272, "", "Totale FATTURE DA RICEVERE:", "350,00"),
                      (16, "0704", "NOTE DI CREDITO"), (62, "07040001", "NOTA A", "70,00"),
                      (62, "07040002", "NOTA B", "30,00"), (272, "", "Totale NOTE DI CREDITO:", "100,00")])
    fornitori = _conto(doc, "FORNITORI ESTERI")
    assert _conto(doc, "Totale FATTURE DA RICEVERE:").padre != fornitori.id
    assert _conto(doc, "Totale NOTE DI CREDITO:").padre != fornitori.id
    assert not any("FORNITORI ESTERI" in p for p in _conto(doc, "NOTA A").percorso)
    assert "FATTURE DA RICEVERE" in _conto(doc, "FATTURE A").percorso[-1]
    assert _conto(doc, "Totale FORNITORI ESTERI:").padre is None or \
        _conto(doc, "Totale FORNITORI ESTERI:").padre != _conto(doc, "FATTURE DA RICEVERE").id


def test_testata_di_pagina_non_e_un_titolo():
    # 395, 1325: la riga di testa ripetuta su ogni pagina (a meno delle cifre) non e' il mastro dei conti sotto
    righe = [(20, "", "Ditta ALFA S.R.L. pag. 1"), (20, "", "Conto uno", "10,00"), (20, "", "Conto due", "20,00"),
             (20, "", "Ditta ALFA S.R.L. pag. 2"), (20, "", "Conto tre", "40,00"), (20, "", "Conto quattro", "80,00")]
    doc = _documento(righe, pagina_di=lambda k: 1 if k <= 3 else 2)
    assert all(_conto(doc, e).padre is None for e in ("Conto uno", "Conto tre", "Conto quattro"))


def test_conto_a_saldo_zero_non_e_un_titolo():
    # 680: «10405 STELLE DI MIRABELLA» senza celle fra conti della stessa forma e allo stesso rientro
    doc = _documento([(10, "0104", "CREDITI"), (51, "10403", "ALFA", "10,00"), (51, "10405", "STELLE DI MIRABELLA"),
                      (51, "10406", "BETA", "20,00"), (51, "10407", "GAMMA", "40,00")])
    crediti = _conto(doc, "CREDITI")
    assert _conto(doc, "BETA").padre == crediti.id
    assert _conto(doc, "GAMMA").padre == crediti.id


def test_totale_costi_oltre_ottanta_conti():
    # R15, 1555: centoventi conti di costo sommano esattamente al «Totale Costi»; il tetto di 80 non vale per lui
    importi = [Decimal(100000 + k) + Decimal(k) / 100 for k in range(1, 121)]
    righe = [(20, f"{700000 + k}", f"costo {k}", f"{v:.2f}".replace(".", ",")) for k, v in enumerate(importi, 1)]
    righe.append((20, "", "Totale Costi", f"{sum(importi):.2f}".replace(".", ",")))
    doc = _documento(righe)
    totale = _conto(doc, "Totale Costi")
    assert len(totale.figli[0]) == 120
    assert all(_conto(doc, f"costo {k}").padre == totale.id for k in range(1, 121))


def test_titolo_di_sezione_centrato_vale_per_tutta_la_sezione():
    # 1531: «COSTI, SPESE E PERDITE» centrato a 100, i conti a 20 e nessun totale
    doc = _documento([(100, "", "COSTI, SPESE E PERDITE"), (20, "6001", "acquisti", "10,00"),
                      (20, "6002", "servizi", "25,00"), (20, "6003", "godimento", "70,00")])
    titolo = _conto(doc, "COSTI, SPESE E PERDITE")
    assert all(_conto(doc, e).padre == titolo.id for e in ("acquisti", "servizi", "godimento"))


def test_colonna_non_corrente_non_sposta_il_padre():
    # Important 4: una catena sulla colonna precedente (100 = 100) non porta via Beta dal totale della corrente
    doc = _documento([(20, "", "Crediti", "300,00", "200,00"), (20, "", "Alfa", "100,00", "100,00"),
                      (20, "", "Beta", "200,00", "100,00")], colonne=2, correnti=(0,))
    assert _conto(doc, "Beta").padre == _conto(doc, "Crediti").id
    assert _conto(doc, "Beta").padre_verificato


def test_scarti_dichiarati_una_volta_per_colonna():
    doc = _documento([(20, "", "Crediti", "300,00", "250,00"), (20, "", "Alfa", "100,00", "90,00"),
                      (20, "", "Beta", "200,00", "80,00"), (20, "", "Gamma", "20,00", "11,00"),
                      (20, "", "Delta", "30,00", "12,00"), (20, "", "", "50,00", "45,00")], colonne=2,
                     correnti=(0,))
    scarti = [a for a in doc.avvisi if "non chiude" in a]
    assert len(scarti) == 1
    assert "in 2 voci" in scarti[0]
    assert "senza descrizione di pagina 1 da 50,00" in scarti[0]


def test_intestazione_dentro_un_totale_stampato_prima():
    # minore: un totale stampato prima dei conti, con subito sotto un titolo d'altro nome allo stesso rientro
    doc = _documento([(20, "", "DEBITI DIVERSI", "150,00"), (20, "", "CREDITI"), (20, "", "Conto Alfa", "100,00"),
                      (20, "", "Conto Beta", "50,00")])
    assert _conto(doc, "Conto Alfa").padre == _conto(doc, "DEBITI DIVERSI").id
    assert any("CREDITI" in a and "DEBITI DIVERSI" in a for a in doc.avvisi)


# --------------------------------------------------------------------------------------
# Fix round 2
# --------------------------------------------------------------------------------------

def test_totale_a_zero_non_assorbe_un_blocco():
    # 313: «C) TRATTAMENTO FINE RAPPORTO 0,00» non e' il totale della voce sotto e dei debiti stampati negativi
    doc = _documento([(20, "", "Fornitori", "300,00"), (40, "", "Alfa", "100,00"), (40, "", "Beta", "200,00"),
                      (20, "", "C) TRATTAMENTO FINE RAPPORTO", "0,00"), (20, "", "1) Esigibili entro", "300,00"),
                      (40, "", "debito uno", "-100,00"), (40, "", "debito due", "-150,00"),
                      (40, "", "debito tre", "-50,00")])
    tfr = _conto(doc, "C) TRATTAMENTO FINE RAPPORTO")
    assert not tfr.totale
    assert not any(r.padre == tfr.id for r in doc.righe)


def test_totale_a_zero_di_costo_e_fondo_resta():
    doc = _documento([(20, "", "Fornitori", "300,00"), (40, "", "Alfa", "100,00"), (40, "", "Beta", "200,00"),
                      (20, "", "7) Altre", "0,00"), (40, "", "Costo altre", "1.000,00"),
                      (40, "", "Fondo altre", "-1.000,00")])
    assert _conto(doc, "Costo altre").padre == _conto(doc, "7) Altre").id


def test_rientro_vale_solo_per_le_catene():
    # 1426: le foglie stampate a 72 col prefisso «Passivo» sono figlie vere della voce a 117
    doc = _documento([(117, "", "A) PATRIMONIO NETTO", "300,00"), (72, "", "Passivo A.I) Capitale", "100,00"),
                      (72, "", "Passivo A.IV) Riserva legale", "200,00")])
    voce = _conto(doc, "A) PATRIMONIO NETTO")
    assert voce.totale
    assert _conto(doc, "Passivo A.I) Capitale").padre == voce.id
    assert _conto(doc, "Passivo A.I) Capitale").padre_verificato


def test_prefisso_di_lato_non_e_il_rientro(tmp_path):
    # 1426: «Attivo» a 72 davanti all'etichetta a 117: il rientro della riga e' quello dell'etichetta
    voci = [(117, 140, "B) IMMOBILIZZAZIONI"), (318, 140, "500,00"), (72, 154, "Attivo"), (117, 154, "B.I) Terreni"),
            (318, 154, "200,00"), (72, 168, "Attivo"), (117, 168, "B.II) Fabbricati"), (318, 168, "300,00"),
            (117, 182, "D) RATEI E RISCONTI"), (318, 182, "80,00"), (72, 196, "Attivo"),
            (117, 196, "D) Altri Ratei"), (318, 196, "80,00")]
    doc = _leggi(tmp_path, voci)
    altri = next(r for r in doc.righe if "Altri Ratei" in r.etichetta)
    ratei = next(r for r in doc.righe if r.etichetta == "D) RATEI E RISCONTI")
    assert altri.x is not None and abs(altri.x - 117) < 3
    assert not altri.totale
    assert altri.padre == ratei.id


def test_totale_col_nome_puntato_chiude_il_suo_mastro():
    # 1325: «Totale I.V.A.:» chiude «0608 I.V.A.» anche se i/v/a sembrano enumeratori
    doc = _documento([(16, "0608", "I.V.A."), (272, "", "Totale I.V.A.:", "5.000,00"),
                      (16, "0903", "QUIESCENZA"), (62, "09030001", "F.DO TFR", "100,00"),
                      (62, "09030002", "F.DO ALTRO", "200,00"), (272, "", "Totale QUIESCENZA:", "300,00")])
    assert not any("I.V.A." in p for p in _conto(doc, "F.DO TFR").percorso)
    assert _conto(doc, "Totale QUIESCENZA:").padre != _conto(doc, "I.V.A.").id


def test_il_padre_di_un_totale_sta_piu_a_sinistra_del_suo_titolo():
    # 1325: un mastro fratello aperto allo stesso rientro del titolo non e' il padre del totale
    doc = _documento([(10, "", "PASSIVITA'"), (16, "0702", "FORNITORI ESTERI"), (16, "0703", "FATTURE"),
                      (62, "07030001", "FATTURE A", "100,00"), (62, "07030002", "FATTURE B", "250,00"),
                      (272, "", "Totale FATTURE:", "350,00")])
    totale = _conto(doc, "Totale FATTURE:")
    assert totale.padre != _conto(doc, "FORNITORI ESTERI").id


def test_mastro_a_saldo_zero_non_e_padre_dei_mastri_fratelli():
    # 680: «01999 BILANCIO CHIUSURA/APERTURA» senza importi allo stesso rientro di «0201 BANCHE»
    doc = _documento([(3, "01999", "BILANCIO CHIUSURA/APERTURA"), (3, "0201", "BANCHE", "300,00"),
                      (51, "20101", "BANCA ALFA", "100,00"), (51, "20102", "BANCA BETA", "200,00")])
    assert _conto(doc, "BANCHE").padre != _conto(doc, "BILANCIO CHIUSURA/APERTURA").id


def test_conto_a_zero_allineato_ai_conti_non_e_un_titolo():
    # 680: «00126 3 STELLE DI MIRABELLA» ha un codice d'altra forma (OCR) ma sta dove stanno i conti
    doc = _documento([((10, 40), "0225", "FORNITORI"), ((51, 80), "00125", "ALFA", "10,00"),
                      ((51, 80), "00126 3", "STELLE DI MIRABELLA"), ((51, 80), "00129", "BETA", "20,00"),
                      ((51, 80), "00130", "GAMMA", "40,00")])
    fornitori = _conto(doc, "FORNITORI")
    assert _conto(doc, "BETA").padre == fornitori.id and _conto(doc, "GAMMA").padre == fornitori.id


def test_parametri_della_stampa_non_sono_un_titolo():
    # 1440: «Ordine: Conti Patrimoniali / Economici Modulo: -BILAUE»
    doc = _documento([(20, "", "Ordine: Conti Patrimoniali / Economici Modulo: -BILAUE"),
                      (20, "", "Conto uno", "10,00"), (20, "", "Conto due", "25,00")])
    assert _conto(doc, "Conto uno").padre is None


def test_titolo_di_sezione_non_passa_al_conto_economico():
    # 615: «ATTIVITA'» di pagina 2 non e' il titolo dei costi di pagina 5
    doc = _documento([(100, "", "ATTIVITA'"), (20, "1001", "cassa", "10,00"), (20, "6001", "acquisti", "25,00"),
                      (20, "6002", "servizi", "70,00")],
                     pagina_di=lambda k: 2 if k <= 2 else 5, sezione="", sezioni={2: "SP", 5: "CE"})
    titolo = _conto(doc, "ATTIVITA'")
    assert _conto(doc, "cassa").padre == titolo.id
    assert _conto(doc, "acquisti").padre is None and _conto(doc, "servizi").padre is None


def test_mastro_e_foglia_rientrata_non_sommano_nel_conto_sopra():
    # 1561: 2.520 = «MACCHINE D'UFFICIO» 1.260 (mastro a 24) + la sua foglia 1.260 (a 48), per coincidenza
    doc = _documento([(24, "13105005", "F.DO AMM. MOBILI", "4.172,53"), (48, "201240", "f.do mobili", "1.652,53"),
                      (48, "201245", "f.do dotazioni", "2.520,00"), (24, "13110000", "MACCHINE D'UFFICIO", "1.260,00"),
                      (48, "101280", "macchine elettroniche", "1.260,00"),
                      (24, "13110005", "F.DO AMM. MACCHINE", "94,24"), (48, "201300", "f.do macchine", "94,24")])
    assert _conto(doc, "macchine elettroniche").padre == _conto(doc, "MACCHINE D'UFFICIO").id
    assert not _conto(doc, "f.do dotazioni").totale


def test_riga_di_controllo_meno_rientrata_non_e_figlia_di_un_totale_sopra():
    # 302: «Risultato prima delle imposte» a 65 non e' il totale di «20) Imposte» e «21) Utile dell'esercizio» a 32
    doc = _documento([(32, "", "B) COSTI", "300,00"), (60, "", "costo uno", "100,00"), (60, "", "costo due", "200,00"),
                      (65, "", "Risultato prima delle imposte", "1.000,00"),
                      (32, "", "20) Imposte sul reddito", "240,00"),
                      (32, "", "21) Utile (perdita) dell'esercizio", "760,00")])
    utile = _conto(doc, "21) Utile (perdita) dell'esercizio")
    assert utile.padre != _conto(doc, "Risultato prima delle imposte").id


def test_conto_a_zero_sotto_il_suo_mastro_non_e_un_titolo():
    # 680: «00126 3 STELLE …» col codice rovinato e l'etichetta spostata, sotto «0225 FORNITORI» a 3: e' un conto
    doc = _documento([((3, 30), "0225", "FORNITORI"), ((51, 86), "00126 3", "STELLE DI MIRABELLA"),
                      ((51, 79), "00129", "BETA", "20,00"), ((51, 79), "00130", "GAMMA", "40,00")])
    fornitori = _conto(doc, "FORNITORI")
    assert _conto(doc, "BETA").padre == fornitori.id and _conto(doc, "GAMMA").padre == fornitori.id


def test_chiusura_esatta_vince_su_quella_in_tolleranza():
    # R17, 1478: 14.445,48 = 14.359,62 + 25,93 + 59,94 - 0,01 esatto; le tre foglie da sole fanno 14.445,49, entro
    # il centesimo, e il conto da -0,01 finirebbe nel «TOTALE COSTI» (352.912,81 contro 352.912,82)
    doc = _documento([(20, "680", "ALTRI COSTI", "14.445,48"), (40, "6801", "costo a", "14.359,62"),
                      (40, "6802", "costo b", "25,93"), (40, "6803", "costo c", "59,94"),
                      (40, "6804540", "Resi, sconti, premi", "-0,01"), (20, "690", "ALTRI ONERI", "338.467,34"),
                      (40, "6901", "onere x", "200.000,00"), (40, "6902", "onere y", "138.467,34"),
                      (20, "", "TOTALE COSTI", "352.912,82")])
    mastro = _conto(doc, "ALTRI COSTI")
    assert _conto(doc, "Resi, sconti, premi").padre == mastro.id
    assert _conto(doc, "Resi, sconti, premi").padre_verificato
    assert _conto(doc, "TOTALE COSTI").figli[0] == (mastro.id, _conto(doc, "ALTRI ONERI").id)


def _doc_a_mano(righe, figli):
    """Un Documento costruito a mano, con i figli gia' decisi: per provare `assegna_padri` da sola."""
    from decimal import Decimal
    from importers.lettore.colonne import Colonna
    from importers.lettore.importi import Importo
    from importers.lettore.profilo import Profilo
    from importers.lettore.righe import Riga
    colonne = [Colonna(0, 300.0, "U", "esercizio", None, None, None, True),
               Colonna(1, 420.0, "U", "esercizio", None, None, None, False)]
    out = []
    for k, (etichetta, celle) in enumerate(righe, start=1):
        out.append(Riga(id=f"p1r{k}U", pagina=1, y=10.0 * k, lato="U", sezione="SP", codice="", etichetta=etichetta,
                        celle={c: Importo(Decimal(v), "importo", v) for c, v in celle.items()}, x=0.0))
    per = {r.etichetta: r for r in out}
    for t, per_colonna in figli.items():
        per[t].totale = True
        per[t].figli = {c: tuple(per[f].id for f in fs) for c, fs in per_colonna.items()}
    profilo = Profilo("schema", "", colonne, None, frozenset(), {0: True, 1: True}, [], {1: "SP"}, frozenset(), [])
    return Documento(out, colonne, False, [], profilo), per


def test_r18_gli_stessi_figli_su_ogni_colonna():
    """R18: la colonna 1 prende «esigibili entro», la colonna 2 «Totale crediti», uguali di importo sulla prima: i
    figli della colonna 1 non chiudono la 2, e da li' non viene un padre verificato."""
    from importers.lettore.totali import assegna_padri
    doc, per = _doc_a_mano(
        [("esigibili entro", {0: "46996", 1: "40000"}), ("esigibili oltre", {1: "6000"}),
         ("Totale crediti", {0: "46996", 1: "46000"}), ("Disponibilita", {0: "4", 1: "4"}),
         ("Totale attivo circolante", {0: "47000", 1: "46004"})],
        {"Totale crediti": {1: ["esigibili entro", "esigibili oltre"]},
         "Totale attivo circolante": {0: ["esigibili entro", "Disponibilita"], 1: ["Totale crediti", "Disponibilita"]}})
    assegna_padri(doc)
    assert per["esigibili entro"].padre == per["Totale crediti"].id and per["esigibili entro"].padre_verificato
    assert per["Totale crediti"].padre == per["Totale attivo circolante"].id
    figli_verificati = [r.etichetta for r in doc.righe
                        if r.padre == per["Totale attivo circolante"].id and r.padre_verificato]
    assert "esigibili entro" not in figli_verificati
    assert any("R18" in a for a in doc.avvisi)


def test_risultato_non_e_figlio_verificato_della_riga_sopra():
    """«Risultato prima delle imposte» = imposte + utile, stampati sotto: un'identita' del conto, non una somma."""
    from importers.lettore.totali import assegna_padri
    doc, per = _doc_a_mano(
        [("Risultato prima delle imposte", {0: "43649", 1: "33336"}), ("imposte correnti", {0: "17134", 1: "12310"}),
         ("21) Utile (perdita) dell'esercizio", {0: "26515", 1: "21026"})],
        {"Risultato prima delle imposte": {0: ["imposte correnti", "21) Utile (perdita) dell'esercizio"],
                                           1: ["imposte correnti", "21) Utile (perdita) dell'esercizio"]}})
    assegna_padri(doc)
    assert not per["imposte correnti"].padre_verificato
    assert not per["21) Utile (perdita) dell'esercizio"].padre_verificato


def test_patrimonio_netto_stampato_prima_conta_l_utile():
    """Sullo SP il patrimonio netto stampato prima delle sue voci conta l'utile per davvero: resta verificato."""
    from importers.lettore.totali import assegna_padri
    doc, per = _doc_a_mano(
        [("A) Patrimonio netto", {0: "1300", 1: "1200"}), ("I - Capitale", {0: "1000", 1: "1000"}),
         ("IX - Utile (perdita) dell'esercizio", {0: "300", 1: "200"})],
        {"A) Patrimonio netto": {0: ["I - Capitale", "IX - Utile (perdita) dell'esercizio"],
                                 1: ["I - Capitale", "IX - Utile (perdita) dell'esercizio"]}})
    assegna_padri(doc)
    assert per["IX - Utile (perdita) dell'esercizio"].padre_verificato


def test_totale_stampato_sotto_non_e_figlio_di_una_voce_sopra():
    from importers.lettore.totali import assegna_padri
    doc, per = _doc_a_mano(
        [("esigibili entro", {0: "892428", 1: "800000"}), ("esigibili oltre", {0: "0", 1: "0"}),
         ("Totale crediti", {0: "892428", 1: "800000"}), ("Cassa", {0: "10", 1: "10"})],
        {"esigibili entro": {0: ["esigibili oltre", "Totale crediti"], 1: ["esigibili oltre", "Totale crediti"]},
         "Totale crediti": {0: ["esigibili entro", "esigibili oltre"], 1: ["esigibili entro", "esigibili oltre"]}})
    assegna_padri(doc)
    assert not per["Totale crediti"].padre_verificato


def test_totale_stampato_sopra_tutte_le_sue_voci_resta_verificato():
    """1540: «2 PASSIVO» stampato sopra le sue cinque voci, fra cui «A.14 TOTALE PATRIMONIO NETTO», chiude su
    entrambe le colonne: il totale di controllo stampato sotto e' una sua voce, non lo contiene."""
    from importers.lettore.totali import assegna_padri
    doc, per = _doc_a_mano(
        [("2 PASSIVO", {0: "30278599", 1: "21547525"}), ("A.1 Capitale", {0: "1000000", 1: "1000000"}),
         ("A.2 Riserve", {0: "9000000", 1: "8000000"}), ("A.14 TOTALE PATRIMONIO NETTO", {0: "10000000", 1: "9000000"}),
         ("B Fondi", {0: "278599", 1: "247525"}), ("C TFR", {0: "1000000", 1: "900000"}),
         ("D Debiti", {0: "18000000", 1: "10400000"}), ("E Ratei", {0: "1000000", 1: "1000000"})],
        {"2 PASSIVO": {c: ["A.14 TOTALE PATRIMONIO NETTO", "B Fondi", "C TFR", "D Debiti", "E Ratei"] for c in (0, 1)},
         "A.14 TOTALE PATRIMONIO NETTO": {c: ["A.1 Capitale", "A.2 Riserve"] for c in (0, 1)}})
    assegna_padri(doc)
    for voce in ("A.14 TOTALE PATRIMONIO NETTO", "B Fondi", "E Ratei"):
        assert per[voce].padre == per["2 PASSIVO"].id and per[voce].padre_verificato, voce


def test_riga_di_controllo_non_ha_per_padre_una_sua_voce():
    """201: «Totale crediti» non prende per padre «esigibili entro», stampato sopra di lui e dentro il suo gruppo."""
    from importers.lettore.totali import assegna_padri
    doc, per = _doc_a_mano(
        [("esigibili entro", {0: "46996", 1: "44806"}), ("Totale crediti", {0: "46996", 1: "44806"}),
         ("Disponibilita", {0: "178911", 1: "156291"}), ("Totale attivo circolante", {0: "225907", 1: "201097"})],
        {"esigibili entro": {0: ["Totale crediti"]}, "Totale crediti": {1: ["esigibili entro"]},
         "Totale attivo circolante": {0: ["esigibili entro", "Disponibilita"], 1: ["Totale crediti", "Disponibilita"]}})
    assegna_padri(doc)
    assert per["Totale crediti"].padre != per["esigibili entro"].id


def test_r18_simmetrica_fra_le_colonne_coi_loro_gruppi():
    """409: le colonne scelgono gruppi diversi per lo stesso totale; il disaccordo declassa ENTRAMBI, anche se una
    delle due colonne non e' fra quelle di prova (nessuna corrente, una sola affidabile)."""
    from importers.lettore.totali import _gruppi_incoerenti
    doc, per = _doc_a_mano(
        [("Rimanenze", {0: "10", 1: "10"}), ("esigibili entro", {0: "40", 1: "40"}),
         ("Totale crediti", {0: "40", 1: "40"}), ("IV - Disponibilita", {0: "5", 1: "5"}),
         ("Totale attivo circolante", {0: "55", 1: "55"})],
        {"Totale attivo circolante": {0: ["Rimanenze", "Totale crediti", "IV - Disponibilita"],
                                      1: ["Rimanenze", "esigibili entro", "IV - Disponibilita"]}})
    incoerenti = _gruppi_incoerenti(doc, {1})
    t = per["Totale attivo circolante"].id
    assert (t, 0) in incoerenti and (t, 1) in incoerenti


def test_riga_di_controllo_senza_gruppo_non_e_voce_di_una_riga_sopra():
    """1407: «TOTALE C) PROVENTI E ONERI FINANZIARI» non ha un gruppo suo; «C.16.d» (3,48) = C.17 + TOTALE C e'
    un'identita' per caso, non una somma di figli."""
    from importers.lettore.totali import assegna_padri
    doc, per = _doc_a_mano(
        [("C.16.d Proventi diversi dai precedenti", {0: "3.48", 1: "5.00"}),
         ("C.17 Interessi e altri oneri finanziari", {0: "46.32", 1: "50.00"}),
         ("TOTALE C) PROVENTI E ONERI FINANZIARI", {0: "-42.84", 1: "-45.00"})],
        {"C.16.d Proventi diversi dai precedenti": {
            c: ["C.17 Interessi e altri oneri finanziari", "TOTALE C) PROVENTI E ONERI FINANZIARI"] for c in (0, 1)}})
    assegna_padri(doc)
    assert not per["C.17 Interessi e altri oneri finanziari"].padre_verificato
    assert per["TOTALE C) PROVENTI E ONERI FINANZIARI"].padre != per["C.16.d Proventi diversi dai precedenti"].id


def test_voce_fra_parentesi_si_sottrae():
    # fac-simile OIC: «(Ammortamenti)», «(Fondi di ammortamento)» stampati positivi sono poste rettificative; la voce
    # vale costo meno fondo (3.033.132 - 124.980 = 2.908.152), sotto o sopra che stia il totale
    doc = _documento([(40, "", "Costi", "3.033.132,00"), (40, "", "(Ammortamenti)", "124.980,00"),
                      (30, "", "1) Terreni e fabbricati", "2.908.152,00")])
    terreni = _conto(doc, "1) Terreni e fabbricati")
    assert terreni.totale and _conto(doc, "(Ammortamenti)").padre == terreni.id
    assert _conto(doc, "(Ammortamenti)").padre_verificato
    # la cella resta lo stampato: la sottrazione vale solo per la somma
    assert _conto(doc, "(Ammortamenti)").celle[0].valore > 0
    # 302: la voce stampata sopra le sue componenti
    doc = _documento([(34, "", "B.I) Immobilizzazioni immateriali", "56.444,44"),
                      (34, "", "B.I.4) Marchi", "1.000,00"),
                      (34, "", "B.I.5) Avviamento", "55.444,44"), (34, "", "B.I.5.a) Acquisto di azienda", "71.302,00"),
                      (34, "", "B.I.5.f) (Fondi di ammortamento)", "15.857,56")])
    avviamento = _conto(doc, "B.I.5) Avviamento")
    assert avviamento.totale and _conto(doc, "B.I.5.f) (Fondi di ammortamento)").padre == avviamento.id
    assert _conto(doc, "B.I.5.f) (Fondi di ammortamento)").padre_verificato
    assert _conto(doc, "B.I.5) Avviamento").padre == _conto(doc, "B.I) Immobilizzazioni immateriali").id
    # come totale dei suoi conti (stampati positivi anche loro) la posta vale lo stampato
    doc = _documento([(34, "", "B.II.2) Impianti", "1.141,00"), (34, "", "B.II.2.a) Impianto", "1.630,00"),
                      (85, "", "IMPIANTI SPECIFICI", "1.630,00"),
                      (34, "", "B.II.2.c) (Fondi di ammortamento)", "489,00"), (85, "", "F/AMM.IMPIANTI GENERICI", "139,00"),
                      (85, "", "F/AMM.IMPIANTI SPECIFICI", "350,00")])
    fondi = _conto(doc, "B.II.2.c) (Fondi di ammortamento)")
    assert _conto(doc, "F/AMM.IMPIANTI SPECIFICI").padre == fondi.id and _conto(doc, "F/AMM.IMPIANTI SPECIFICI").padre_verificato
    assert fondi.padre == _conto(doc, "B.II.2) Impianti").id and fondi.padre_verificato


def test_voce_fra_parentesi_senza_nome_di_rettifica_si_somma():
    # «(IRES)» fra parentesi e' una voce, non una sottrazione
    doc = _documento([(30, "", "Imposte correnti"), (40, "", "(IRES)", "100,00"),
                      (40, "", "(IRAP)", "200,00"), (30, "", "Totale imposte", "300,00")])
    assert _conto(doc, "(IRES)").padre == _conto(doc, "Totale imposte").id


def test_di_cui_fra_parentesi_non_si_sottrae():
    # «(di cui già richiamati)» e' un sottoinsieme, non una posta rettificativa
    doc = _documento([(40, "", "Crediti", "300,00"), (40, "", "(di cui esigibili oltre)", "100,00"),
                      (40, "", "Altri", "250,00"), (30, "", "Totale", "650,00")])
    assert _conto(doc, "Totale").totale
    assert _conto(doc, "(di cui esigibili oltre)").padre == _conto(doc, "Totale").id


def test_risultati_del_conto_economico_sono_differenze():
    # 409: A - B, poi il risultato prima delle imposte, poi l'utile meno le imposte
    doc = _documento([(58, "", "1) ricavi delle vendite", "4.369.544,00"), (58, "", "5) altri ricavi", "33.395,00"),
                      (58, "", "Totale valore della produzione", "4.402.939,00"),
                      (58, "", "6) per materie prime", "1.490.475,00"), (58, "", "7) per servizi", "1.113.243,00"),
                      (58, "", "Totale costi della produzione", "2.603.718,00"),
                      (51, "", "Differenza tra valore e costi della produzione (A - B)", "1.799.221,00"),
                      (58, "", "Totale proventi e oneri finanziari", "-2.734,00"),
                      (51, "", "Risultato prima delle imposte", "1.796.487,00"),
                      (58, "", "Totale delle imposte sul reddito dell'esercizio", "83.199,00"),
                      (51, "", "21) Utile (perdita) dell'esercizio", "1.713.288,00")], sezione="CE")
    differenza, risultato = _conto(doc, "Differenza tra valore e costi della produzione (A - B)"), _conto(
        doc, "Risultato prima delle imposte")
    utile = _conto(doc, "21) Utile (perdita) dell'esercizio")
    assert set(differenza.figli[0]) == {_conto(doc, "Totale valore della produzione").id,
                                        _conto(doc, "Totale costi della produzione").id}
    assert _conto(doc, "Totale costi della produzione").padre_verificato
    assert differenza.padre == risultato.id and risultato.padre == utile.id
    assert _conto(doc, "Totale delle imposte sul reddito dell'esercizio").padre == utile.id


def test_risultato_chiude_sopra_anche_coi_totali_stampati_prima():
    # 409: il documento stampa le voci prima dei conti (direzione +1), la differenza chiude comunque le righe sopra
    doc = _documento([(51, "", "A) Valore della produzione", "1.000,00"), (58, "", "1) ricavi", "600,00"),
                      (58, "", "5) altri ricavi", "400,00"),
                      (51, "", "B) Costi della produzione", "700,00"), (58, "", "6) materie", "300,00"),
                      (58, "", "7) servizi", "400,00"),
                      (51, "", "Differenza tra valore e costi della produzione", "300,00")], sezione="CE")
    differenza = _conto(doc, "Differenza tra valore e costi della produzione")
    assert set(differenza.figli[0]) == {_conto(doc, "A) Valore della produzione").id,
                                        _conto(doc, "B) Costi della produzione").id}


def test_costi_si_sottraggono_solo_dentro_un_risultato():
    # fuori da un risultato i costi si sommano come stampati
    doc = _documento([(58, "", "6) per materie prime", "100,00"), (58, "", "7) per servizi", "200,00"),
                      (58, "", "Totale costi della produzione", "300,00"),
                      (58, "", "14) oneri diversi", "50,00"), (51, "", "Totale costi", "350,00")], sezione="CE")
    assert _conto(doc, "Totale costi della produzione").padre == _conto(doc, "Totale costi").id


def test_catene_dei_risultati_prima_dei_risultati():
    # 409: «altri» / «Totale interessi e altri oneri» / «Totale proventi e oneri (-)» sono una catena; il risultato
    # prima delle imposte la trova chiusa, e l'utile trova chiuso il risultato
    doc = _documento([(51, "", "A) Valore della produzione", "1.000,00"), (58, "", "1) ricavi", "600,00"),
                      (58, "", "5) altri ricavi", "400,00"),
                      (51, "", "B) Costi della produzione", "700,00"), (58, "", "6) materie", "300,00"),
                      (58, "", "7) servizi", "400,00"),
                      (51, "", "Differenza tra valore e costi della produzione", "300,00"),
                      (66, "", "altri", "20,00"), (66, "", "Totale interessi e altri oneri finanziari", "20,00"),
                      (58, "", "Totale proventi e oneri finanziari", "-20,00"),
                      (51, "", "Risultato prima delle imposte", "280,00"),
                      (58, "", "Totale delle imposte sul reddito", "80,00"),
                      (51, "", "21) Utile (perdita) dell'esercizio", "200,00")], sezione="CE")
    risultato, utile = _conto(doc, "Risultato prima delle imposte"), _conto(doc, "21) Utile (perdita) dell'esercizio")
    assert _conto(doc, "altri").padre == _conto(doc, "Totale interessi e altri oneri finanziari").id
    assert set(risultato.figli[0]) == {_conto(doc, "Differenza tra valore e costi della produzione").id,
                                       _conto(doc, "Totale proventi e oneri finanziari").id}
    assert set(utile.figli[0]) == {risultato.id, _conto(doc, "Totale delle imposte sul reddito").id}


def test_voce_all_unita_sopra_conti_al_centesimo(tmp_path):
    # 1533, 682: voci e conti nella stessa colonna, le voci stampate all'unita' («4.220»), i conti al centesimo
    # (1.500,40 + 2.719,55 = 4.219,95): il totale stampato all'unita' tollera un euro
    doc = _leggi(tmp_path, _righe(140, [(50, "Crediti verso clienti", "4.220"), (90, "Clienti Italia", "1.500,40"),
                                        (90, "Clienti estero", "2.719,55"), (50, "Disponibilita' liquide", "1.300"),
                                        (90, "Banca uno", "1.120,10"), (90, "Cassa", "179,95")]))
    assert doc.profilo.decimali.get(0) is True
    voce = _riga(doc, "Crediti verso clienti")
    assert voce.totale
    assert _riga(doc, "Clienti estero").padre == voce.id and _riga(doc, "Clienti estero").padre_verificato
    assert _riga(doc, "Cassa").padre == _riga(doc, "Disponibilita' liquide").id


def test_voce_stampata_al_centesimo_non_tollera_un_euro(tmp_path):
    # la stessa voce stampata «4.220,00»: al centesimo, e 4.219,95 non la chiude
    doc = _leggi(tmp_path, _righe(140, [(50, "Crediti verso clienti", "4.220,00"), (90, "Clienti Italia", "1.500,40"),
                                        (90, "Clienti estero", "2.719,55"), (50, "Disponibilita' liquide", "1.300,05"),
                                        (90, "Banca uno", "1.120,10"), (90, "Cassa", "179,95")]))
    assert not _riga(doc, "Crediti verso clienti").totale
    assert _riga(doc, "Disponibilita' liquide").totale


def test_voce_del_passivo_chiude_i_conti_a_marcatore_col_verso_rovesciato(tmp_path):
    # Q2, 1533: voci all'unita' senza marcatore e conti col D/A nella stessa colonna di una sezione unica. I conti
    # hanno il saldo in dare (A negativo): la voce dell'attivo li chiude diritta, quella del passivo rovesciata
    righe = [(50, "Crediti verso clienti", "1.500", None), (90, "Clienti", "1.700,30", "D"),
             (90, "Fondo svalutazione crediti", "200,10", "A"), (50, "Disponibilita' liquide", "2.450", None),
             (90, "Banca uno", "2.000,15", "D"), (90, "Cassa", "449,90", "D"),
             (50, "Debiti verso fornitori", "3.000", None), (90, "Fornitori Italia", "2.000,40", "A"),
             (90, "Fornitori estero", "999,80", "A"), (50, "Debiti tributari", "1.200", None),
             (90, "Erario c/IVA", "1.300,25", "A"), (90, "Erario c/ritenute", "100,15", "D"),
             (90, "Erario c/IRES", "0,10", "A"), (50, "Altri debiti", "800", None),
             (90, "Debiti diversi", "500,20", "A"), (90, "Debiti verso dipendenti", "300,10", "A")]
    voci = []
    for k, (x, etichetta, importo, marcatore) in enumerate(righe):
        y = 140 + k * 14
        voci += [(x, y, etichetta), (400, y, importo)] + ([(404, y, marcatore)] if marcatore else [])
    doc = _leggi(tmp_path, voci)
    assert doc.profilo.marcatori == frozenset({0})
    crediti, debiti = _riga(doc, "Crediti verso clienti"), _riga(doc, "Debiti verso fornitori")
    assert _riga(doc, "Fondo svalutazione crediti").celle[0].valore < 0
    assert crediti.totale and crediti.verso == {}
    assert debiti.totale and debiti.verso == {0: -1}
    assert set(debiti.figli[0]) == {_riga(doc, "Fornitori Italia").id, _riga(doc, "Fornitori estero").id}
    assert _riga(doc, "Fornitori estero").padre_verificato
    # i conti misti del passivo: 1.300,25 A - 100,15 D + 0,10 A = 1.200,20
    assert _riga(doc, "Debiti tributari").verso == {0: -1}
    assert _riga(doc, "Erario c/ritenute").padre == _riga(doc, "Debiti tributari").id


def _parziali_e_totali():
    """638, 1540: i conti nella colonna dei parziali (x 300, al centesimo), le voci in quella dei totali (x 380,
    all'unita'), mai sulla stessa riga; la voce prima dei suoi conti."""
    righe = [(30, "1) Crediti verso clienti", None, "1.183.214"), (40, "Crediti verso privati", "98.180,13", None),
             (40, "Crediti verso enti", "1.084.033,40", None), (40, "Altri clienti", "1.000,20", None),
             (30, "2) Crediti tributari", None, "6.000"), (40, "Erario c/IVA", "2.500,40", None),
             (40, "Erario c/ritenute", "3.499,90", None), (30, "3) Crediti verso altri", None, "12.039"),
             (40, "Crediti diversi", "10.000,00", None), (40, "Depositi cauzionali", "2.039,45", None),
             (30, "Totale crediti", None, "1.201.253"), (30, "4) Disponibilita' liquide", None, "5.300"),
             (54, "Depositi bancari", "5.300,00", None), (63, "Banca uno", "3.000,10", None),
             (63, "Banca due", "2.299,95", None)]
    return _righe(140, righe, colonne=(300, 380))


def test_voce_dei_totali_somma_i_conti_dei_parziali(tmp_path):
    # Q1: la voce della colonna dei totali prende i conti dei parziali fino alla voce dopo, con un euro di tolleranza
    # (1.183.213,73 per 1.183.214); i totali della colonna dei totali sommano solo le voci
    doc = _leggi(tmp_path, _parziali_e_totali())
    assert doc.profilo.coppie == {1: 0}
    clienti = _riga(doc, "1) Crediti verso clienti")
    assert clienti.totale
    assert clienti.figli[0] == tuple(_riga(doc, e).id for e in ("Crediti verso privati", "Crediti verso enti",
                                                                  "Altri clienti"))
    assert _riga(doc, "Crediti verso enti").padre == clienti.id and _riga(doc, "Crediti verso enti").padre_verificato
    assert _riga(doc, "Depositi cauzionali").padre == _riga(doc, "3) Crediti verso altri").id
    assert _riga(doc, "Totale crediti").figli[1] == tuple(_riga(doc, e).id for e in (
        "1) Crediti verso clienti", "2) Crediti tributari", "3) Crediti verso altri"))


def test_coppia_non_somma_due_livelli_dei_parziali(tmp_path):
    # i conti a 63 sotto «Depositi bancari» a 54 (che non li chiude al centesimo): la voce prende la sottovoce, mai la
    # sottovoce e i suoi conti insieme (5.300,00 + 5.300,05 non e' 5.300)
    doc = _leggi(tmp_path, _parziali_e_totali())
    liquide = _riga(doc, "4) Disponibilita' liquide")
    assert liquide.figli.get(0) == (_riga(doc, "Depositi bancari").id,)
    assert not _riga(doc, "Depositi bancari").padre_verificato      # una catena e' un'ipotesi (R14)
    assert _riga(doc, "Banca uno").padre != liquide.id


def test_colonne_affiancate_a_centesimi_non_sono_una_coppia(tmp_path):
    # corrente e precedente che non stampano sulla stessa riga ma entrambe al centesimo: nessuna coppia
    righe = [(30, "Voce uno", "1.200,50", None), (30, "Voce due", None, "2.300,40"), (30, "Voce tre", "3.700,10", None),
             (30, "Voce quattro", None, "4.100,20"), (30, "Voce cinque", "5.200,30", None),
             (30, "Voce sei", None, "6.300,60"), (30, "Voce sette", "7.400,70", None),
             (30, "Voce otto", None, "8.500,80")]
    doc = _leggi(tmp_path, _righe(140, righe, colonne=(300, 380)))
    assert doc.profilo.coppie == {}


def test_titolo_di_una_voce_senza_importo_chiude_la_finestra_dei_parziali(tmp_path):
    # 1540: «1.B.1.4 Concessioni …» non stampa importo nei totali, ma i suoi conti (2.465,81 D e A, netto zero) non
    # sono della voce sopra, anche se la somma tornerebbe lo stesso
    righe = [(30, "1) Crediti verso clienti", None, "1.183.214"), (40, "Crediti verso privati", "98.180,13", None),
             (40, "Crediti verso enti", "1.084.033,40", None), (40, "Altri clienti", "1.000,20", None),
             (30, "2) Crediti verso controllate"), (40, "Controllata alfa", "2.465,81", None),
             (40, "Fondo svalutazione controllata alfa", "-2.465,81", None),
             (30, "3) Crediti tributari", None, "6.000"), (40, "Erario c/IVA", "2.500,40", None),
             (40, "Erario c/ritenute", "3.499,90", None), (30, "4) Crediti verso altri", None, "12.039"),
             (40, "Crediti diversi", "10.000,00", None), (40, "Depositi cauzionali", "2.039,45", None),
             (30, "5) Ratei attivi", None, "1.500"), (40, "Ratei su interessi", "1.500,30", None)]
    doc = _leggi(tmp_path, _righe(140, righe, colonne=(300, 380)))
    assert doc.profilo.coppie == {1: 0}
    clienti = _riga(doc, "1) Crediti verso clienti")
    assert clienti.figli[0] == tuple(_riga(doc, e).id for e in ("Crediti verso privati", "Crediti verso enti",
                                                                  "Altri clienti"))
    assert _riga(doc, "Controllata alfa").padre != clienti.id


def test_voce_di_risultato_stampata_prima_dei_componenti_non_e_di_controllo():
    # 1464: «C) PROVENTI E ONERI FINANZIARI (153.082,01)» apre i suoi componenti: li somma sotto di se', e il risultato
    # prima delle imposte la prende come membro. Il documento stampa le voci prima dei componenti (direzione +1)
    doc = _documento([(46, "", "B) Costi della produzione", "300,00"), (54, "", "6) per materie", "100,00"),
                      (54, "", "7) per servizi", "200,00"),
                      (46, "", "Differenza tra valore e costi della produzione", "219.297,34"),
                      (46, "", "C) PROVENTI E ONERI FINANZIARI", "(153.082,01)"),
                      (54, "", "16) altri proventi finanziari", "4.258,70"),
                      (54, "", "17) interessi e altri oneri finanziari", "(149.529,16)"),
                      (54, "", "17-bis) utili e perdite su cambi", "(7.811,55)"),
                      (46, "", "Risultato prima delle imposte (A - B + - C + - D)", "66.215,33")], sezione="CE")
    voce = _conto(doc, "C) PROVENTI E ONERI FINANZIARI")
    assert voce.figli[0] == tuple(_conto(doc, e).id for e in (
        "16) altri proventi finanziari", "17) interessi e altri oneri finanziari", "17-bis) utili e perdite su cambi"))
    assert _conto(doc, "17-bis) utili e perdite su cambi").padre_verificato
    assert set(_conto(doc, "Risultato prima delle imposte (A - B + - C + - D)").figli[0]) == {
        _conto(doc, "Differenza tra valore e costi della produzione").id, voce.id}


def test_nomi_di_conto_di_una_verifica_non_sono_risultati():
    # su un bilancio di verifica «UTILE ESERCIZIO:» e «Differenza cambi passiva» sono conti: la regola del segno dei
    # risultati vale solo col lessico di legge per intero, e qui gli oneri si sommano come stampati
    doc = _documento([(40, "70101", "Ricavi vendite", "1.000,00"),
                      (40, "80201", "Interessi e altri oneri bancari", "200,00"),
                      (20, "", "UTILE ESERCIZIO:", "1.200,00")], sezione="CE", tipo="verifica")
    utile = _conto(doc, "UTILE ESERCIZIO:")
    assert utile.totale and len(utile.figli[0]) == 2
    from importers.lettore.totali import _risultato
    assert not _risultato(_conto(doc, "UTILE ESERCIZIO:"), schema=False)
    assert _risultato(_conto(doc, "UTILE ESERCIZIO:"), schema=True)


def test_voce_all_unita_con_un_conto_solo_resta_fra_il_conto_e_il_totale(tmp_path):
    # R22, 1533: «contributi in conto esercizio 113.946» sopra il solo conto 113.945,74 non chiude esatta (R14), e il
    # totale sopra in tolleranza prendeva il conto al posto della voce. La voce prende il conto come ipotesi, e il
    # totale somma la voce
    doc = _leggi(tmp_path, _righe(140, [
        (50, "1) ricavi delle vendite e delle prestazioni", "9.419.699"),
        (90, "RICAVI DA CESSIONI DI BENI", "8.712.168,72"), (90, "RICAVI DA PRESTAZIONI", "707.530,30"),
        (50, "contributi in conto esercizio", "113.946"), (90, "CONTRIB. C/ESERCIZIO", "113.945,74"),
        (50, "altri", "65.709"), (90, "RIMBORSI", "60.000,10"), (90, "SOPRAVVENIENZE ATTIVE", "5.709,00"),
        (72, "Totale altri ricavi e proventi", "179.655")]))
    contributi, totale = _riga(doc, "contributi in conto esercizio"), _riga(doc, "Totale altri ricavi e proventi")
    conto = _riga(doc, "CONTRIB. C/ESERCIZIO")
    assert conto.padre == contributi.id and not conto.padre_verificato
    assert set(totale.figli[0]) == {contributi.id, _riga(doc, "altri").id}
    assert contributi.padre == totale.id and contributi.padre_verificato


def test_conto_oltre_l_esercizio_non_salta_la_sua_voce(tmp_path):
    # R22, 208: «Esigibili oltre l'esercizio -2.860» sopra il solo conto -2.860,24: il conto resta sotto «oltre», non
    # finisce direttamente sotto «Totale crediti (II)» perdendo la scadenza
    doc = _leggi(tmp_path, _righe(140, [
        (50, "esigibili entro l'esercizio", "10.500"), (90, "Clienti", "8.000,30"), (90, "Erario", "2.499,90"),
        (50, "Esigibili oltre l'esercizio", "-2.860"), (90, "CREDITO INVESTIM.", "-2.860,24"),
        (40, "Totale crediti (II)", "7.640")]))
    oltre, totale = _riga(doc, "Esigibili oltre l'esercizio"), _riga(doc, "Totale crediti (II)")
    assert _riga(doc, "CREDITO INVESTIM.").padre == oltre.id
    assert _riga(doc, "CREDITO INVESTIM.").id not in totale.figli.get(0, ())
    assert set(totale.figli[0]) == {_riga(doc, "esigibili entro l'esercizio").id, oltre.id}
    assert oltre.padre_verificato


def test_intero_in_colonna_al_centesimo_non_e_una_voce_che_prende_un_padre_sbagliato(tmp_path):
    # il rischio di `_tolleranza_cella`: un conto stampato senza decimali («2.000») fra conti al centesimo non chiude
    # in tolleranza il conto accanto, e nessuno prende un padre verificato sbagliato
    doc = _leggi(tmp_path, _righe(140, [
        (50, "CLIENTI", "4.500,30"), (90, "Cliente alfa", "2.000"), (90, "Cliente beta", "2.000,40"),
        (90, "Cliente gamma", "499,90")]))
    clienti = _riga(doc, "CLIENTI")
    assert set(clienti.figli[0]) == {_riga(doc, e).id for e in ("Cliente alfa", "Cliente beta", "Cliente gamma")}
    assert not _riga(doc, "Cliente alfa").totale
    assert all(_riga(doc, e).padre == clienti.id for e in ("Cliente alfa", "Cliente beta", "Cliente gamma"))


def test_voce_all_unita_sopra_un_totale_dei_suoi_conti(tmp_path):
    # R22, revisione: «4) Disponibilita' liquide 5.300» sopra «Depositi bancari 5.300,05», che chiude esatto i suoi due
    # conti. La sottovoce resta il totale verificato dei conti, e la voce la prende come ipotesi
    doc = _leggi(tmp_path, _righe(140, [
        (30, "Crediti verso clienti", "4.220"), (50, "Clienti Italia", "1.500,40"), (50, "Clienti estero", "2.719,55"),
        (30, "4) Disponibilita' liquide", "5.300"), (54, "Depositi bancari", "5.300,05"),
        (63, "Banca uno", "3.000,10"), (63, "Banca due", "2.299,95"),
        (30, "Altri crediti", "1.000"), (50, "Crediti diversi", "600,20"), (50, "Anticipi", "399,90")]))
    depositi = _riga(doc, "Depositi bancari")
    assert depositi.totale and set(depositi.figli[0]) == {_riga(doc, "Banca uno").id, _riga(doc, "Banca due").id}
    assert _riga(doc, "Banca due").padre == depositi.id and _riga(doc, "Banca due").padre_verificato
    assert depositi.padre == _riga(doc, "4) Disponibilita' liquide").id and not depositi.padre_verificato


# --------------------------------------------------------------------------------------
# Revisione finale: l'API per chi integra
# --------------------------------------------------------------------------------------

_CE_CON_DIFFERENZA = [(51, "", "A) Valore della produzione", "1.000,00"), (58, "", "1) ricavi", "600,00"),
                      (58, "", "5) altri ricavi", "400,00"),
                      (51, "", "B) Costi della produzione", "700,00"), (58, "", "6) materie", "300,00"),
                      (58, "", "7) servizi", "400,00"),
                      (51, "", "Differenza tra valore e costi della produzione", "300,00")]


def test_documento_senza_profilo_si_legge_come_schema_e_lo_dichiara():
    # un profilo senza `tipo` vale «schema» (comportamento invariato), ma il documento lo dice
    righe = _CE_CON_DIFFERENZA
    con = _documento(righe, sezione="CE")
    senza = _documento(righe, sezione="CE")
    senza.profilo = SimpleNamespace(decimali=con.profilo.decimali, sezioni={})
    marca_totali(senza)
    assegna_padri(senza)
    assert [(r.totale, r.figli, r.padre) for r in senza.righe] == [(r.totale, r.figli, r.padre) for r in con.righe]
    assert _conto(senza, "Differenza tra valore e costi della produzione").totale
    assert senza.avvisi == ["documento senza profilo: totali e segni letti come su uno schema di legge"]
    assert not con.avvisi
    marca_totali(senza)
    assert len(senza.avvisi) == 1          # una volta sola, anche rileggendo


def test_tutti_gli_avvisi_prima_il_documento_poi_le_righe_senza_ripetizioni():
    from importers.lettore import Documento
    doc = Documento([], [], False, ["riga b", "doc a", "riga b"], SimpleNamespace(avvisi=["doc a", "doc c"]))
    assert doc.tutti_gli_avvisi() == ["doc a", "doc c", "riga b"]
    assert doc.avvisi == ["riga b", "doc a", "riga b"] and doc.profilo.avvisi == ["doc a", "doc c"]


def test_righe_del_prospetto():
    from importers.lettore import Documento
    righe = [Riga(id=f"p1r{k}U", pagina=1, y=float(k), lato="U", sezione="SP", codice="", etichetta=parte,
                  celle={}, parte=parte) for k, parte in enumerate(("prospetto", "nota", "altro", "prospetto"))]
    doc = Documento(righe, [], False, [], SimpleNamespace(avvisi=[]))
    assert [r.id for r in doc.righe_del_prospetto()] == ["p1r0U", "p1r3U"]


def test_valore_nel_totale_costo_dentro_un_risultato():
    # il costo stampato positivo entra col meno nel risultato; il valore com'e'; la cella resta lo stampato
    from importers.lettore import valore_nel_totale
    doc = _documento(_CE_CON_DIFFERENZA, sezione="CE")
    valore, costi, differenza = (_conto(doc, e) for e in ("A) Valore della produzione", "B) Costi della produzione",
                                                         "Differenza tra valore e costi della produzione"))
    assert set(differenza.figli[0]) == {valore.id, costi.id}
    assert valore_nel_totale(doc, differenza, valore, 0) == Decimal("1000.00")
    assert valore_nel_totale(doc, differenza, costi, 0) == Decimal("-700.00")
    assert costi.celle[0].valore == Decimal("700.00")


def test_valore_nel_totale_conto_a_marcatore_in_una_voce_dal_verso_rovesciato(tmp_path):
    # Q2: sul passivo di una sezione unica i conti in avere (A negativo) chiudono la voce col verso rovesciato
    righe = [(50, "Crediti verso clienti", "1.500", None), (90, "Clienti", "1.700,30", "D"),
             (90, "Fondo svalutazione crediti", "200,10", "A"), (50, "Disponibilita' liquide", "2.450", None),
             (90, "Banca uno", "2.000,15", "D"), (90, "Cassa", "449,90", "D"),
             (50, "Debiti verso fornitori", "3.000", None), (90, "Fornitori Italia", "2.000,40", "A"),
             (90, "Fornitori estero", "999,80", "A"), (50, "Debiti tributari", "1.200", None),
             (90, "Erario c/IVA", "1.300,25", "A"), (90, "Erario c/ritenute", "100,15", "D"),
             (90, "Erario c/IRES", "0,10", "A"), (50, "Altri debiti", "800", None),
             (90, "Debiti diversi", "500,20", "A"), (90, "Debiti verso dipendenti", "300,10", "A")]
    voci = []
    for k, (x, etichetta, importo, marcatore) in enumerate(righe):
        y = 140 + k * 14
        voci += [(x, y, etichetta), (400, y, importo)] + ([(404, y, marcatore)] if marcatore else [])
    doc = _leggi(tmp_path, voci)
    from importers.lettore import valore_nel_totale
    per_id = {r.id: r for r in doc.righe}
    tributari = _riga(doc, "Debiti tributari")
    assert tributari.verso == {0: -1}
    iva, ritenute = _riga(doc, "Erario c/IVA"), _riga(doc, "Erario c/ritenute")
    assert iva.celle[0].valore == Decimal("-1300.25")
    assert valore_nel_totale(doc, tributari, iva, 0) == Decimal("1300.25")
    assert valore_nel_totale(doc, tributari, ritenute, 0) == Decimal("-100.15")
    figli = [per_id[f] for f in tributari.figli[0]]
    assert abs(sum(valore_nel_totale(doc, tributari, f, 0) for f in figli) - tributari.celle[0].valore) <= 1
    # la voce dell'attivo chiude diritta: il fondo in avere resta negativo
    crediti, fondo = _riga(doc, "Crediti verso clienti"), _riga(doc, "Fondo svalutazione crediti")
    assert valore_nel_totale(doc, crediti, fondo, 0) == Decimal("-200.10")


def test_valore_nel_totale_posta_rettificativa():
    from importers.lettore import valore_nel_totale
    doc = _documento([(40, "", "Costi", "3.033.132,00"), (40, "", "(Ammortamenti)", "124.980,00"),
                      (30, "", "1) Terreni e fabbricati", "2.908.152,00")])
    terreni, costi, fondo = (_conto(doc, e) for e in ("1) Terreni e fabbricati", "Costi", "(Ammortamenti)"))
    assert set(terreni.figli[0]) == {costi.id, fondo.id}
    assert valore_nel_totale(doc, terreni, fondo, 0) == Decimal("-124980.00")
    assert valore_nel_totale(doc, terreni, costi, 0) == Decimal("3033132.00")


def test_altre_riserve_all_unita_assorbono_la_riserva_da_arrotondamento(tmp_path):
    # Fase 5, F7 (1533): «VI Altre riserve» all'unita' sopra il solo conto, con uno scarto oltre l'euro: e' la riserva
    # da arrotondamento all'unita', che lo schema mette proprio nelle altre riserve. La voce prende il suo conto
    doc = _leggi(tmp_path, _righe(140, [
        (50, "I Capitale", "10.000"), (90, "CAPITALE SOCIALE", "10.000,00"),
        (50, "VI Altre riserve", "52.410"), (90, "RISERVA STRAORDINARIA", "52.408,70"),
        (50, "IX Utile (perdita) dell'esercizio", "7.500"), (72, "Totale patrimonio netto", "69.910")]))
    riserve = _riga(doc, "VI Altre riserve")
    assert _riga(doc, "RISERVA STRAORDINARIA").padre == riserve.id
    assert riserve.totale and _riga(doc, "RISERVA STRAORDINARIA").id in riserve.figli[0]


def test_voce_all_unita_lontana_piu_di_un_euro_dal_conto_resta_senza_figli(tmp_path):
    # fuori dalle altre riserve lo scarto di arrotondamento resta di un euro: «crediti 5.000» sopra 4.998,70 no
    doc = _leggi(tmp_path, _righe(140, [
        (50, "I Capitale", "10.000"), (90, "CAPITALE SOCIALE", "10.000,00"),
        (50, "crediti tributari", "5.000"), (90, "ERARIO C/IVA", "4.998,70"), (50, "altri", "700")]))
    assert not _riga(doc, "crediti tributari").totale
