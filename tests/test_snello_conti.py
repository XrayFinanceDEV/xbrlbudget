from decimal import Decimal as D

from importers.import_snello.conti import applica_lato, da_coppie, da_foglie
from importers.import_snello.percorsi import NOMI
from importers.import_snello.righe import Riga
from importers.iv_cee_hierarchy import detail_fields

_TIER0 = ("sp02", "sp03", "sp04", "sp11", "sp12", "sp13", "sp16a", "sp17a")


def _f(i, lato, valore, percorso, testo=None):
    return Riga(id=str(i), pagina=1, lato=lato, testo=testo if testo is not None else f"c{i}",
               valore=D(valore), percorso=percorso)


def test_contrapposte_fondo_a_destra_e_cc_passivo():
    """La riga 'R' (20, didascalia generica) e' il risultato corrente scritto come pareggio,
    uguale all'utile del CE (ricavi 100 - servizi 80): e' il caso FORMETAL/two-column (Task 14,
    2026-09-26). Non entra piu' da riga stampata (`risultato_stampato` resta None per il
    percorso 'R': quella chiave serve solo a CE.21/CE.D.21); l'ipotesi "corrente" (esclusa)
    quadra meglio di "precedente" (che duplicherebbe la massa in sp12g) e vince."""
    foglie = [_f(1, "L", "1000", "SPA.B.II.2"), _f(2, "R", "400", "SPA.B.II.2.F"),
              _f(3, "L", "300", "SPA.C.IV.1"), _f(4, "R", "150", "SPA.C.IV.1"),   # c/c stampato fra le passivita'
              _f(5, "R", "500", "SPP.A.I"), _f(6, "R", "250", "SPP.D.7"),
              _f(7, "L", "80", "CE.B.7"), _f(8, "R", "100", "CE.A.1"), _f(9, "R", "20", "R"),
              _f(10, "L", "5", "X")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03b_impianti_macchinari"] == D("600.00")
    assert bs["sp09_disponibilita_liquide"] == D("300.00")
    assert bs["sp16a_debiti_banche_breve"] == D("150.00")
    assert bs["sp16_debiti_breve"] == D("400.00")
    assert ce["ce06_servizi"] == D("80.00") and ce["ce01_ricavi_vendite"] == D("100.00")
    assert bs["sp13_utile_perdita"] == D("20.00")           # utile CE, mai la riga stampata
    assert diag["risultato_stampato"] is None and diag["lato_corretti"] == 1
    assert diag["risultato_ambiguo"] == {"ipotesi": "corrente", "importo": "20.00",
                                         "candidati": [["9", "R", "20.00"]]}
    assert diag["escluse"] == [["10", "X", "5.00"]]


def test_colonna_unica_con_segno():
    foglie = [_f(1, "T", "1000", "SPA.B.II.4"), _f(2, "T", "-300", "SPA.B.II.4.F"),
              _f(3, "T", "-200", "SPP.D.4"), _f(4, "T", "50", "SPP.D.12"),          # erario in dare: e' un credito
              _f(5, "T", "-500", "SPP.A.I"), _f(6, "T", "90", "CE.B.6"), _f(7, "T", "-60", "CE.A.1")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03d_altri_beni"] == D("700.00")
    assert bs["sp16a_debiti_banche_breve"] == D("200.00")
    assert bs["sp06e_crediti_tributari_breve"] == D("50.00")
    assert bs["sp11_capitale"] == D("500.00")
    assert ce["ce05_materie_prime"] == D("90.00") and ce["ce01_ricavi_vendite"] == D("60.00")


def test_applica_lato_non_tocca_i_fondi():
    foglie = [_f(1, "L", "10", "SPA.B.II.2"), _f(2, "R", "4", "SPA.B.II.2.F"), _f(3, "R", "9", "SPP.D.7")]
    assert applica_lato(foglie) == 0
    assert foglie[1].percorso == "SPA.B.II.2.F"


def test_coppie_schema_di_legge_genitore_e_fondo():
    coppie = [("SPA.B.I", D("584094")), ("SPA.B.I.1", D("118720")), ("SPA.B.I.5", D("88362")),
              ("SPA.B.II.2", D("47738")), ("SPA.B.II.2.F", D("17605")),
              ("SPA.C.II.1", D("863659")), ("SPA.C.II.1.E", D("800000")), ("SPA.C.II.1.O", D("63659")),
              ("SPP.D.4", D("100")), ("SPP.D.4", D("100")), ("CE.B.7", D("9")), ("CE.21", D("7422"))]
    bs, ce, diag = da_coppie(coppie)
    assert bs["sp02_immob_immateriali"] == D("207082.00")        # il genitore cade: contano i figli
    assert bs["sp03b_impianti_macchinari"] == D("30133.00")       # fondo sottratto
    assert bs["sp06a_crediti_clienti_breve"] == D("800000.00") and bs["sp07a_crediti_clienti_lungo"] == D("63659.00")
    assert bs["sp16a_debiti_banche_breve"] == D("100.00")         # la voce ripetuta si conta una volta
    assert diag["risultato_stampato"] == "7422.00"


def _nessun_tier0_negativo(bs):
    assert all(bs.get(NOMI[c], D("0.00")) >= 0 for c in _TIER0 if NOMI[c] in bs)


def _coerenza_aggregati(bs, brevi=("sp02", "sp03", "sp04", "sp06", "sp16")):
    """Nessun dettaglio negativo, e l'aggregato resta la somma di quel che completa() gli
    attribuisce (diretto + dettagli): la stessa formula che completa() applica, verificata
    dal lato del risultato."""
    for breve in brevi:
        pieno = NOMI[breve]
        dettagli = [d for d in detail_fields(pieno) if d in bs]
        assert all(bs[d] >= 0 for d in dettagli), f"{pieno}: dettaglio negativo"


def test_fondo_piu_fine_del_lordo_stampato_coppie():
    bs, ce, diag = da_coppie([("SPA.B.II", D("1000")), ("SPA.B.II.2.F", D("400")), ("SPP.D.7", D("600"))])
    assert bs["sp03_immob_materiali"] == D("600.00")
    assert "sp03b_impianti_macchinari" not in bs
    _nessun_tier0_negativo(bs)
    _coerenza_aggregati(bs)
    assert diag["lato_irrisolti"] == []


def test_fondo_piu_fine_del_lordo_stampato_foglie():
    foglie = [_f(1, "L", "1000", "SPA.B.II"), _f(2, "R", "400", "SPA.B.II.2.F"), _f(3, "R", "600", "SPP.D.7")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03_immob_materiali"] == D("600.00")
    assert "sp03b_impianti_macchinari" not in bs
    _nessun_tier0_negativo(bs)
    _coerenza_aggregati(bs)
    assert diag["lato_irrisolti"] == []


def test_lato_senza_contropartita_diventa_fallback_dichiarato():
    foglie = [_f(1, "L", "1000", "SPA.B.II.2"), _f(2, "L", "800", "SPA.C.IV.1"),
              _f(3, "R", "50", "SPA.B.I.1"), _f(4, "R", "500", "SPP.A.I"), _f(5, "R", "600", "SPP.D.7")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp16g_altri_debiti_breve"] == D("50.00")
    assert diag["lato_corretti"] == 0
    assert diag["lato_irrisolti"] == [["3", "SPA.B.I.1", "50.00"]]
    assert "sp02_immob_immateriali" not in bs
    _nessun_tier0_negativo(bs)
    _coerenza_aggregati(bs)


def test_fornitori_stampato_fra_gli_attivi_va_al_credito_di_contropartita():
    foglie = [_f(1, "L", "1000", "SPA.B.II.2"), _f(2, "L", "300", "SPP.D.7"), _f(3, "R", "500", "SPP.A.I")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp06g_crediti_altri_breve"] == D("300.00")
    assert bs["sp06_crediti_breve"] == D("300.00")
    assert diag["lato_corretti"] == 1
    assert diag["lato_irrisolti"] == []
    _nessun_tier0_negativo(bs)
    _coerenza_aggregati(bs)


def test_lato_irrisolti_sempre_presente_anche_vuoto():
    foglie = [_f(1, "L", "10", "SPA.B.II.2"), _f(2, "R", "4", "SPA.B.II.2.F"), _f(3, "R", "9", "SPP.D.7")]
    _, _, diag = da_foglie(foglie)
    assert diag["lato_irrisolti"] == []
    _, _, diag2 = da_coppie([("SPP.D.7", D("9"))])
    assert diag2["lato_irrisolti"] == []


# --- Fix lotto A: patrimonio netto/risultato non passano da applica_lato -------------------


def test_applica_lato_non_tocca_il_patrimonio_netto():
    """SPP.A.* (capitale, riserve, risultati) cambia lato col segno per natura: applica_lato
    non deve toccarlo ne' contarlo, con o senza contropartita nota. Il passivo vota in
    maggioranza Avere (R, 80.000 su due voci) mentre l'utile e' stampato Dare (L, 7.035,31):
    senza l'esclusione l'utile finirebbe corretto/spostato dal voto di maggioranza."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.3"), _f(2, "R", "50000", "SPP.D.7"),
              _f(3, "R", "30000", "SPP.D.4"), _f(4, "L", "7035.31", "SPP.A.IX")]
    n = applica_lato(foglie, [])
    assert n == 0
    assert foglie[3].percorso == "SPP.A.IX"


def test_risultato_di_esercizio_lato_invertito_non_duplica_massa():
    """Riproduce FORMETAL/623: un risultato (percorso ambiguo 'SPP.A.IX') stampato sul lato Dare
    (L) mentre il resto del passivo vota in maggioranza Avere (R, 80.000 su due voci) non deve
    finire nel fallback (che duplicherebbe la massa) ne' cambiare segno: i debiti veri restano
    positivi (non ribaltati dal peso del risultato). Da Task 14 (2026-09-26) sp13 non e' piu' il
    valore letto ma l'utile del CE: qui la riga stampata e il CE dicono la stessa cifra
    (7.035,31 di ricavi, nessun costo), quindi l'ipotesi "corrente" (esclusa, sp13 dal CE) e'
    anche l'unica che non raddoppia la massa - la stessa che sceglie il confronto att-pas."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.3"),
              _f(2, "R", "50000", "SPP.D.7"), _f(3, "R", "30000", "SPP.D.4"),
              _f(4, "L", "7035.31", "SPP.A.IX"), _f(5, "R", "7035.31", "CE.A.1")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp13_utile_perdita"] == D("7035.31")
    assert bs["sp16d_debiti_fornitori_breve"] == D("50000.00")
    assert bs["sp16a_debiti_banche_breve"] == D("30000.00")
    assert bs["sp16_debiti_breve"] == D("80000.00")
    assert diag["lato_irrisolti"] == []
    assert diag["lato_corretti"] == 0
    assert diag["risultato_ambiguo"]["ipotesi"] == "corrente"
    assert bs.get("sp06g_crediti_altri_breve", D("0")) == D("0")
    assert bs.get("sp16g_altri_debiti_breve", D("0")) == D("0")


def test_perdita_portata_a_nuovo_resta_negativa():
    """Una perdita portata a nuovo (SPP.A.VIII) letta col segno gia' corretto (negativo) non
    deve diventare positiva ne' finire fra i crediti: e' patrimonio netto negativo."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.3"), _f(2, "R", "500", "SPP.D.7"),
              _f(3, "R", "-209356.57", "SPP.A.VIII")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp12g_utili_perdite_portati"] == D("-209356.57")
    assert diag["lato_irrisolti"] == []
    assert diag["lato_corretti"] == 0


# --- Fix round 1 (review): un padre con figli non deve raddoppiare la massa in da_foglie ---


def test_padre_con_figli_non_raddoppia_la_massa():
    """Riscontrato in review: un totale di lettera (SPP.D bare) stampato ACCANTO a righe piu'
    specifiche dello stesso gruppo (SPP.D.4, SPP.D.7) e' la stessa massa gia' spiegata dai
    figli: va escluso, mai sommato di nuovo - come gia' fa da_coppie in modo 'legge'. Prima
    del fix: sp16 finiva 10.000 (3.000+2.000 dai figli PIU' 5.000 dal padre bare, che
    campo_da_percorso mappa gia' sull'aggregato sp16 stesso)."""
    foglie = [_f(1, "L", "5000", "SPA.C.IV.3"), _f(2, "R", "3000", "SPP.D.4"),
              _f(3, "R", "2000", "SPP.D.7"), _f(4, "R", "5000", "SPP.D")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp16_debiti_breve"] == D("5000.00")
    assert diag["padri_esclusi"] == [["4", "SPP.D", "5000.00"]]


def test_padre_con_figlio_fondo_non_conta_come_figlio():
    """Un fondo (.F) non e' un figlio ai fini di questa regola, ne' in da_coppie ne' qui: un
    lordo (SPA.B.II) con solo il proprio fondo (SPA.B.II.2.F) fra le altre foglie non va
    escluso come "padre con figli" - resta il caso normale di netting del fondo."""
    foglie = [_f(1, "L", "1000", "SPA.B.II"), _f(2, "R", "400", "SPA.B.II.2.F"),
              _f(3, "R", "600", "SPP.D.7")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp03_immob_materiali"] == D("600.00")
    assert diag["padri_esclusi"] == []


# --- Fix lotto A: riga di risultato stampata due volte, contata una sola volta -------------


def test_risultato_stampato_due_volte_si_conta_una_sola_volta():
    """budget_132: 'RISULTATO DI ESERCIZIO' compare due volte (pagine diverse), STESSA
    didascalia, stesso importo, entrambe classificate SPP.A.IX, nessun codice conto davanti -
    e' lo stesso risultato ristampato, non due conti distinti. Round 3 (review): le due foglie
    ambigue identiche si collassano in UN solo gruppo prima della ricerca combinatoria (mai una
    si' e una no - spaccarle inventerebbe una riserva che per caso quadra il foglio); la seconda
    si dichiara in `risultato_duplicato` e il gruppo pesa per l'intera somma (1.000,00) se
    l'ipotesi fosse 'precedente'. Qui ne' 'corrente' ne' 'precedente' chiudono meglio del
    pareggio (scarto 500 in entrambi i casi): a parita' vince 'corrente', sp13 resta l'utile
    del CE (0, nessuna voce di CE qui) e nessuna riserva fittizia entra in sp12g."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.3"), _f(2, "R", "500", "SPP.D.7"),
              _f(3, "R", "500", "SPP.A.IX", testo="RISULTATO DI ESERCIZIO"),
              _f(4, "R", "500", "SPP.A.IX", testo="RISULTATO DI ESERCIZIO")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp13_utile_perdita"] == D("0.00")
    assert "sp12g_utili_perdite_portati" not in bs
    assert diag["risultato_duplicato"] == [["4", "SPP.A.IX", "500.00"]]
    assert diag["risultato_ambiguo"] == {"ipotesi": "corrente", "importo": "1000.00",
                                         "candidati": [["3", "SPP.A.IX", "500.00"],
                                                       ["4", "SPP.A.IX", "500.00"]]}


def test_percorso_mai_assegnato_va_a_non_mappati_non_a_escluse():
    """Una foglia senza percorso (mai classificata, nemmeno al secondo giro di lettura) e'
    massa reale non classificata: va in non_mappati, mai confusa con 'X' (riga dichiarata
    esplicitamente non contabile dal modello) in escluse."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.3"), _f(2, "R", "500", "SPP.D.7"),
              _f(3, "L", "5", "X"), _f(4, "L", "12.34", None)]
    bs, ce, diag = da_foglie(foglie)
    assert diag["escluse"] == [["3", "X", "5.00"]]
    assert diag["non_mappati"] == [["4", "", "12.34"]]


def test_risultato_diverso_non_si_deduplica():
    """Due percorsi SPP.A.IX con importo DIVERSO (Task 14: da_foglie non li dedup-a mai per
    valore, li tiene entrambi come candidati ambigui indipendenti): sp13 resta l'utile del CE
    (0, nessuna voce di CE qui), scelto perche' l'ipotesi "corrente" quadra meglio di quella che
    sommerebbe le due righe in sp12g."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.3"), _f(2, "R", "1300", "SPP.D.7"),
              _f(3, "R", "500", "SPP.A.IX"), _f(4, "R", "300", "SPP.A.IX")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp13_utile_perdita"] == D("0.00")
    assert diag["risultato_duplicato"] == []
    assert diag["risultato_ambiguo"]["ipotesi"] == "corrente"
    assert diag["risultato_ambiguo"]["candidati"] == [["3", "SPP.A.IX", "500.00"],
                                                       ["4", "SPP.A.IX", "300.00"]]


# --- Task 14 (2026-09-26): il risultato d'esercizio in modo "conti" riusa le regole del ------
# --- vecchio parser best-effort invece di sommare le righe stampate --------------------------


def test_scadenza_non_fa_di_un_conto_il_padre_di_un_altro():
    """Banco 2026-09-26: 'SPA.C.II.5-quater.E' non e' un totale che spiega 'SPA.C.II.5-quater'
    (stesso sotto-conto, solo annotato entro l'esercizio): prima del fix il secondo veniva
    escluso come "padre con figli" e 1.751,05 di massa vera sparivano. Entrambi vanno sommati."""
    foglie = [_f(1, "T", "1000", "SPP.D.7"), _f(2, "T", "1751.05", "SPA.C.II.5-quater"),
              _f(3, "T", "500", "SPA.C.II.5-quater.E")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp06g_crediti_altri_breve"] == D("2251.05")
    assert diag["padri_esclusi"] == []


def test_formetal_utile_stampato_uguale_al_ce_si_conta_una_volta():
    """Bilancio di verifica a due colonne (FORMETAL): 'UTILE DI ESERCIZIO' e' la riga di
    pareggio (percorso 'R'), senza codice conto davanti - candidata corrente. Dal round 2
    (review, 2026-09-26) questa didascalia NON esclude piu' a priori (era il difetto del round
    1: la stessa frase serve anche a riconoscere un pregresso mal didascalizzato, owner:
    "a volte c'e' scritto risultato ma e' quello dell'anno precedente"): passa dall'ipotesi
    ambigua, che sceglie 'corrente' perche' e' l'unica che chiude il foglio a zero (l'importo
    coincide con l'utile del CE)."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "800", "SPP.A.I"),
              _f(3, "R", "200", "R", testo="UTILE DI ESERCIZIO"),
              _f(4, "R", "500", "CE.A.1"), _f(5, "L", "300", "CE.B.7")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp13_utile_perdita"] == D("200.00")
    assert diag["risultato_escluso"] == []
    assert diag["risultato_ambiguo"] == {"ipotesi": "corrente", "importo": "200.00",
                                         "candidati": [["3", "R", "200.00"]]}
    att = bs["sp09_disponibilita_liquide"]
    pas = bs["sp11_capitale"] + bs["sp13_utile_perdita"]
    assert att == pas == D("1000.00")


def test_utile_esercizio_ambiguo_risulta_precedente_se_chiude_il_bilancio():
    """Round 2 (owner: "a volte c'e' scritto risultato ma in realta' e' il risultato dell'anno
    precedente, mentre quello di quest'anno e' la differenza"): una riga 'Utile d'esercizio'
    (percorso 'SPP.A.IX', SENZA codice conto davanti) il cui importo NON coincide con l'utile
    del CE. Dal round 1 questa didascalia non e' piu' una riga di controllo esclusa a priori
    (era il difetto: la stessa frase serve anche a un pregresso mal didascalizzato): passa
    dall'ipotesi ambigua, che qui sceglie 'precedente' (sp12g) perche' e' l'unica che azzera lo
    scarto attivo-passivo."""
    foglie = [_f(1, "L", "1350", "SPA.C.IV.1"), _f(2, "R", "1000", "SPP.A.I"),
              _f(3, "R", "300", "SPP.A.IX", testo="Utile d'esercizio"),
              _f(4, "R", "550", "CE.A.1"), _f(5, "L", "500", "CE.B.7")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp13_utile_perdita"] == D("50.00")
    assert bs["sp12g_utili_perdite_portati"] == D("300.00")
    assert diag["risultato_escluso"] == []
    assert diag["risultato_ambiguo"] == {"ipotesi": "precedente", "importo": "300.00",
                                         "candidati": [["3", "SPP.A.IX", "300.00"]]}


def test_prior_caption_utile_esercizio_precedente_va_a_sp12g_positivo():
    foglie = [_f(1, "L", "500", "SPA.C.IV.1"),
              _f(2, "R", "500", "SPP.A.VIII", testo="UTILE ESERCIZIO PRECEDENTE")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp12g_utili_perdite_portati"] == D("500.00")
    assert diag["risultato_precedente"] == [["2", "SPP.A.VIII", "500.00"]]


def test_prior_caption_perdite_portate_a_nuovo_va_a_sp12g_negativo():
    foglie = [_f(1, "L", "500", "SPA.C.IV.1"),
              _f(2, "L", "500", "SPP.A.VIII", testo="PERDITE PORTATE A NUOVO")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp12g_utili_perdite_portati"] == D("-500.00")
    assert diag["risultato_precedente"] == [["2", "SPP.A.VIII", "-500.00"]]


def test_prior_caption_vince_anche_se_qwen_ha_dato_percorso_ix():
    """La didascalia decide, non il percorso che Qwen ha dato (regola del proprietario:
    'regardless of the path Qwen gave, VIII or IX'): una didascalia di pregresso su un
    percorso 'SPP.A.IX' non passa mai dall'ipotesi ambigua."""
    foglie = [_f(1, "L", "500", "SPA.C.IV.1"),
              _f(2, "R", "500", "SPP.A.IX", testo="UTILI PORTATI A NUOVO")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp12g_utili_perdite_portati"] == D("500.00")
    assert diag["risultato_ambiguo"] is None


def test_riga_di_controllo_totale_a_pareggio_esclusa_mai_sommata():
    """Fix round 1: la didascalia esclude solo un percorso 'R'/'SPP.A.IX' (non classificato
    come conto vero), mai un percorso gia' risolto a un campo normale."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "1000", "SPP.A.I"),
              _f(3, "R", "1000", "R", testo="TOTALE A PAREGGIO")]
    bs, ce, diag = da_foglie(foglie)
    assert diag["risultato_escluso"] == [["3", "R", "1000.00"]]
    assert bs.get("sp16g_altri_debiti_breve", D("0")) == D("0")
    assert bs["sp13_utile_perdita"] == D("0.00")


def test_riga_differenza_attivo_passivo_su_percorso_r_esclusa():
    foglie = [_f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "800", "SPP.A.I"),
              _f(3, "R", "200", "R", testo="DIFFERENZA ATTIVO PASSIVO")]
    bs, ce, diag = da_foglie(foglie)
    assert diag["risultato_escluso"] == [["3", "R", "200.00"]]
    assert diag["risultato_ambiguo"] is None


def test_riga_sbilancio_su_percorso_r_esclusa():
    foglie = [_f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "850", "SPP.A.I"),
              _f(3, "R", "150", "R", testo="Sbilancio")]
    bs, ce, diag = da_foglie(foglie)
    assert diag["risultato_escluso"] == [["3", "R", "150.00"]]
    assert diag["risultato_ambiguo"] is None


def test_differenza_cambi_attivi_conto_vero_non_escluso_dalla_didascalia():
    """Rilievo round 1: 'DIFFERENZA' nella didascalia di un conto vero (differenza cambi,
    CE.C.17-bis -> ce16) non deve escluderlo - il test di pareggio/controllo vale solo sui
    percorsi non classificati ('R', 'SPP.A.IX'), mai su un percorso gia' risolto a un campo
    normale."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "1000", "SPP.A.I"),
              _f(3, "R", "300", "CE.C.17-bis", testo="Differenza cambi attivi")]
    bs, ce, diag = da_foglie(foglie)
    assert ce["ce16_utili_perdite_cambi"] == D("300.00")
    assert diag["risultato_escluso"] == []


def test_totale_rimanenze_iniziali_conto_vero_non_escluso_dalla_didascalia():
    """Rilievo round 1: 'TOTALE' nella didascalia di un conto vero (rimanenze materie prime,
    SPA.C.I.1 -> sp05a) non deve escluderlo - percorso classificato, mai una didascalia a
    scavalcarlo."""
    foglie = [_f(1, "R", "1000", "SPP.D.7"),
              _f(2, "L", "500", "SPA.C.I.1", testo="Totale rimanenze iniziali")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp05a_materie_prime"] == D("500.00")
    assert diag["risultato_escluso"] == []


def test_623_perdita_pregressa_e_corrente_entrambe_in_dare_chiudono_il_bilancio():
    """Riproduce budget_623: una perdita pregressa (209.356,57) e la perdita corrente
    (34.590,25) sono ENTRAMBE stampate sul lato Dare (attivo), come saldi debitori di conti di
    patrimonio netto. La pregressa ha didascalia riconoscibile e va a sp12g col segno dato dalla
    didascalia (negativo), a prescindere dal lato di stampa; la corrente e' ambigua (didascalia
    generica) e l'ipotesi 'corrente' (esclusa, sp13 dal CE) e' l'unica che chiude il bilancio -
    nessuna massa finisce in sp06g/sp16g."""
    foglie = [
        _f(1, "L", "56053.18", "SPA.C.IV.1"),
        _f(2, "R", "300000", "SPP.A.I"),
        _f(3, "L", "209356.57", "SPP.A.VIII", testo="PERDITE PORTATE A NUOVO"),
        _f(4, "L", "34590.25", "SPP.A.IX", testo="PERDITA D'ESERCIZIO"),
        _f(5, "L", "34590.25", "CE.B.7"),
    ]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp12g_utili_perdite_portati"] == D("-209356.57")
    assert bs["sp13_utile_perdita"] == D("-34590.25")
    # "PERDITA D'ESERCIZIO" non ha un codice conto davanti: candidata corrente, passa
    # dall'ipotesi ambigua (round 2) e vince "corrente" perche' e' l'unica che chiude il foglio.
    assert diag["risultato_escluso"] == []
    assert diag["risultato_ambiguo"] == {"ipotesi": "corrente", "importo": "34590.25",
                                         "candidati": [["4", "SPP.A.IX", "34590.25"]]}
    assert bs.get("sp06g_crediti_altri_breve", D("0")) == D("0")
    assert bs.get("sp16g_altri_debiti_breve", D("0")) == D("0")
    att = bs["sp09_disponibilita_liquide"]
    pas = bs["sp11_capitale"] + bs["sp12g_utili_perdite_portati"] + bs["sp13_utile_perdita"]
    assert att == pas == D("56053.18")


# --- Task 15 (2026-09-27): una foglia 'X' con codice conto si riclassifica coi ------------
# --- classificatori a parole del vecchio parser, mai reinventati qui -----------------------


def test_formetal_x_con_codice_conto_si_riclassifica_col_vecchio_parser():
    """FORMETAL, banco 26/09: due mastri '40/00000 DEBITI V/FORNITORI' marcati X da Qwen, uno
    in Dare (13.542,00) uno in Avere (348.578,85) - massa vera che il modello ha rinunciato a
    instradare, non una riga di controllo. classify_passivo riconosce 'FORNITOR' (specifico,
    sp16d); classify_attivo su una descrizione di debito non trova nulla di specifico (sp06
    generico, scartato): un solo candidato, si forza. Il segno lo decide poi lo stesso voto di
    famiglia che gia' governa gli altri debiti del foglio (Avere = normale qui, Dare = contro),
    non un calcolo nuovo: netto 335.036,85 (Avere - Dare)."""
    foglie = [
        _f(1, "L", "1000", "SPA.C.IV.1"),
        _f(2, "R", "800", "SPP.A.I"),
        _f(3, "R", "200", "SPP.D.9"),
        _f(4, "L", "13542.00", "X", testo="40/00000 DEBITI V/FORNITORI"),
        _f(5, "R", "348578.85", "X", testo="40/00000 DEBITI V/FORNITORI"),
    ]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp16d_debiti_fornitori_breve"] == D("335036.85")
    assert diag["riclassificati_vecchio_parser"] == [
        ["4", "40/00000 DEBITI V/FORNITORI", "sp16d", "13542.00"],
        ["5", "40/00000 DEBITI V/FORNITORI", "sp16d", "348578.85"],
    ]
    assert diag["escluse"] == []


def test_senza_percorso_con_codice_conto_si_riclassifica_anche_lei():
    """Non solo 'X': una foglia rimasta senza percorso anche al secondo giro (percorso None)
    ma con un codice di conto in testa al testo e' la stessa massa vera, e si riprova con gli
    stessi classificatori."""
    foglie = [
        _f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "800", "SPP.A.I"), _f(3, "R", "200", "SPP.D.9"),
        _f(4, "R", "300", None, testo="50/00010 DEBITI V/FORNITORI DIVERSI"),
    ]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp16d_debiti_fornitori_breve"] == D("300.00")
    assert diag["non_mappati"] == []
    assert diag["riclassificati_vecchio_parser"] == [
        ["4", "50/00010 DEBITI V/FORNITORI DIVERSI", "sp16d", "300.00"],
    ]


def test_x_senza_codice_conto_non_si_riclassifica():
    """Una riga 'X' il cui testo NON comincia con un codice di conto (una didascalia di
    contesto, non un mastro) resta esclusa come oggi: il test del codice e' condizione
    necessaria, non solo la presenza del percorso 'X'."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "1000", "SPP.A.I"),
              _f(3, "R", "50", "X", testo="RIGA DI SERVIZIO SENZA CODICE")]
    bs, ce, diag = da_foglie(foglie)
    assert diag["riclassificati_vecchio_parser"] == []
    assert diag["escluse"] == [["3", "X", "50.00"]]


def test_x_senza_parole_chiave_non_specifiche_resta_escluso():
    """Se la descrizione non da' un risultato specifico ne' come attivo ne' come passivo
    (nessun classificatore la riconosce: entrambi cadono sul ripiego generico), non si
    sceglie a caso: la foglia resta X/esclusa come oggi (nessuna scommessa)."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "1000", "SPP.A.I"),
              _f(3, "R", "50", "X", testo="90/00000 RIGA GENERICA SENZA PAROLE CHIAVE")]
    bs, ce, diag = da_foglie(foglie)
    assert diag["riclassificati_vecchio_parser"] == []
    assert diag["escluse"] == [["3", "X", "50.00"]]


def test_ce_x_con_codice_conto_si_riclassifica_lato_costi():
    """Una foglia CE marcata 'X' con codice di conto e descrizione di costo del personale
    inequivocabile ('SALARI'): classify_costi la riconosce (specifico, ce08b); sul lato
    ricavi nessuna regola matcha (ce04 generico, scartato) - un solo candidato, si forza."""
    from importers.import_snello.righe import Riga

    foglie = [
        _f(1, "T", "1000", "CE.A.1"),
        Riga(id="2", pagina=1, lato="T", testo="70/000 SALARI E STIPENDI", valore=D("450.00"),
            sezione="ce", percorso="X"),
    ]
    bs, ce, diag = da_foglie(foglie)
    assert ce["ce08b_salari_stipendi"] == D("450.00")
    assert diag["riclassificati_vecchio_parser"] == [["2", "70/000 SALARI E STIPENDI", "ce08b", "450.00"]]


def test_x_su_campo_tier0_non_si_forza_mai():
    """Anche se la descrizione fosse specifica su un campo TIER0 (patrimonio netto), la foglia
    non si forza mai su quel campo: resta X/esclusa, come il vecchio importatore (TIER0_FIELDS
    non e' mai una destinazione di ripiego)."""
    foglie = [_f(1, "L", "1000", "SPA.C.IV.1"), _f(2, "R", "700", "SPP.A.I"),
              _f(3, "R", "300", "X", testo="60/00000 CAPITALE SOCIALE VERSATO")]
    bs, ce, diag = da_foglie(foglie)
    assert diag["riclassificati_vecchio_parser"] == []
    assert diag["escluse"] == [["3", "X", "300.00"]]


# --- Task 15 (2026-09-27): un'immobilizzazione netta ancora negativa si azzera, mai -------
# --- lasciata negativa ne' spostata su un altro campo (stessa regola del vecchio ----------
# --- importatore, build_sp_from_vision) ----------------------------------------------------


def test_immobilizzazione_netta_ancora_negativa_si_azzera_e_si_dichiara():
    """Un fondo che eccede il lordo anche a livello di aggregato (non solo di dettaglio, gia'
    coperto da _netta_fondi_negativi) si azzera - mai lasciato negativo - e l'eccedenza si
    dichiara in diag, cosi' che il chiamante la riporti in report['anomalie']."""
    bs, ce, diag = da_coppie([("SPA.B.II", D("1000")), ("SPA.B.II.F", D("1050")), ("SPP.D.7", D("1050"))])
    assert bs["sp03_immob_materiali"] == D("0.00")
    assert diag["immobilizzazioni_negative_tagliate"] == [["sp03_immob_materiali", "50.00"]]


def test_immobilizzazione_netta_positiva_non_dichiara_nulla():
    bs, ce, diag = da_coppie([("SPA.B.II", D("1000")), ("SPA.B.II.F", D("400")), ("SPP.D.7", D("600"))])
    assert bs["sp03_immob_materiali"] == D("600.00")
    assert diag["immobilizzazioni_negative_tagliate"] == []


def test_gap_reale_non_si_maschera_dietro_l_utile_ce():
    """Riproduce budget_330 (gap reale in un bilancio di verifica, qui -2.505,51): senza alcuna
    riga di risultato in mezzo, sp13 e' comunque l'utile del CE e lo scarto vero resta
    leggibile - nessun secondo passaggio lo maschera."""
    foglie = [_f(1, "L", "1000.00", "SPA.C.IV.1"), _f(2, "R", "3505.51", "SPP.D.7")]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp13_utile_perdita"] == D("0.00")
    att = bs["sp09_disponibilita_liquide"]
    pas = bs["sp16_debiti_breve"] + bs["sp13_utile_perdita"]
    assert att - pas == D("-2505.51")
    assert diag["risultato_ambiguo"] is None


# --- Round 2 (banco FORMETAL-TEST): un codice conto davanti al risultato e' sempre pregresso --


def test_formetal_test_righe_reali_codice_conto_decide_deterministico():
    """Righe reali del banco FORMETAL-TEST (2026-09-26):
    - p1Rr113, 125.543,87, '28/45/090 RISULTATO DI ESERCIZIO' - CON codice conto davanti: e' un
      vero conto di patrimonio netto (durante l'anno il corrente non e' mai registrato su un
      conto), quindi l'anno PRECEDENTE, deterministico - mai un candidato dell'ipotesi ambigua.
    - p2Rr199, 70.353,09, 'UTILE DI ESERCIZIO' - SENZA codice: la riga di quadratura, candidata
      corrente - e qui coincide esattamente con l'utile del CE.
    Prima di questo fix le due righe finivano nella STESSA ipotesi di gruppo (round 1): qui,
    smistate ciascuna per conto proprio, il foglio chiude esattamente - la pregressa in sp12g
    per il suo codice conto, la corrente esclusa perche' l'ipotesi la conferma (scarto zero)."""
    foglie = [
        _f(1, "L", "1195896.96", "SPA.C.IV.1"),
        _f(2, "R", "1000000.00", "SPP.A.I"),
        _f("p1Rr113", "R", "125543.87", "SPP.A.IX", testo="28/45/090 RISULTATO DI ESERCIZIO"),
        _f("p2Rr199", "R", "70353.09", "R", testo="UTILE DI ESERCIZIO"),
        _f(5, "R", "770353.09", "CE.A.1"),
        _f(6, "L", "700000.00", "CE.B.7"),
    ]
    bs, ce, diag = da_foglie(foglie)
    assert bs["sp12g_utili_perdite_portati"] == D("125543.87")
    assert bs["sp13_utile_perdita"] == D("70353.09")
    assert diag["risultato_precedente"] == [["p1Rr113", "SPP.A.IX", "125543.87"]]
    assert diag["risultato_ambiguo"] == {"ipotesi": "corrente", "importo": "70353.09",
                                         "candidati": [["p2Rr199", "R", "70353.09"]]}
    att = bs["sp09_disponibilita_liquide"]
    pas = bs["sp11_capitale"] + bs["sp12g_utili_perdite_portati"] + bs["sp13_utile_perdita"]
    assert att == pas == D("1195896.96")
