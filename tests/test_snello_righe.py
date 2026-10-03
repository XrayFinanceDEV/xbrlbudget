import time
from decimal import Decimal as D

from importers.detail_enrichment import SourceRow
from importers.import_snello import righe as R


def test_importi_con_segni_e_sottolineature():
    assert R.importi("CASSA 1.199,64 A 4.251,97 3.119,94 D") == [(D("1199.64"), "A"), (D("4251.97"), ""), (D("3119.94"), "D")]
    assert R.importi("riserva legale _3_.09_4_,_3_1_") == [(D("3094.31"), "")]
    assert R.importi("Beni non superiori a € 516,46 24.087,77")[-1] == (D("24087.77"), "")
    assert R.importi("Perdite (1.500,00)") == [(D("-1500.00"), "")]
    assert R.importi("conto 10000001673 c/c 320.100,68") == [(D("320100.68"), "")]


def test_etichetta():
    assert R.etichetta("10101 CASSA CONTANTI 839,66 D 2.000,00") == "10101 CASSA CONTANTI"


def test_regola_e_saldo():
    assert R.regola_colonna(["saldo_precedente", "dare", "avere", "saldo_corrente"]) == {"n": 4, "k": 3}
    assert R.regola_colonna(["saldo_corrente", "saldo_precedente", "variazione", "percentuale"]) == {"n": 4, "k": 0}
    assert R.regola_colonna(["dare", "avere"]) == {}
    r4 = SourceRow("p1r1", 1, "T", "X 10,00 D 5,00 3,00 12,00 A", (D("10"), D("5"), D("3"), D("12")))
    assert R.saldo(r4, {"n": 4, "k": 3}) == D("-12.00")
    r1 = SourceRow("p1r2", 1, "T", "X 7,00", (D("7"),))
    assert R.saldo(r1, {"n": 4, "k": 3}) == D("7.00")          # un solo importo e il saldo e' l'ultima colonna
    r2 = SourceRow("p1r3", 1, "T", "X 7,00 8,00", (D("7"), D("8")))
    assert R.saldo(r2, {"n": 4, "k": 1}) is None               # ambiguo: dichiarato, non indovinato
    assert R.saldo(r1, {}) == D("7.00")                        # senza struttura: l'ultimo importo


def _r(i, valore, lato="L", testo=None):
    return R.Riga(id=str(i), pagina=1, lato=lato, testo=testo or f"conto {i}", valore=None if valore is None else D(valore))


def test_totali_dopo_i_figli_catene_e_somme_zero():
    righe = [_r(1, "100"), _r(2, "50"), _r(3, "150", testo="mastro A"),        # totale dopo i figli
             _r(4, "30"), _r(5, "30", testo="mastro B"), _r(6, "30", testo="gruppo B"),  # catena
             _r(7, "10"), _r(8, "-10"), _r(9, "5"), _r(10, "5", testo="mastro C")]       # coppia a somma zero dentro
    direzioni = R.marca_totali(righe)
    assert direzioni.most_common(1)[0][0] == -1
    tot = {r.id for r in righe if r.totale}
    assert {"3", "5", "6", "10"} <= tot
    assert "4" not in tot and "1" not in tot
    assert sum(r.valore for r in R.foglie(righe)) == D("185")   # 100+50+30+10-10+5


def test_totali_prima_dei_figli_e_lati_separati():
    righe = [_r(1, "80", testo="mastro"), _r(2, "50"), _r(3, "30"),
             _r(4, "80", lato="R", testo="mastro passivo"), _r(5, "80", lato="R")]
    R.marca_totali(righe)
    assert [r.id for r in righe if r.totale] == ["1", "4"]
    assert righe[1].mastro == "mastro"


def test_tre_gruppi_con_totali_uguali():
    # senza confine di gruppo, l'apprendimento a coppie vota anche +1 (il "30" del gruppo
    # accanto somma per caso al totale di questo): le due passate forzate per intero, non
    # il solo voto a coppie, devono scegliere -1 e lasciare "tot C" fra i totali.
    righe = [_r(1, "10"), _r(2, "20"), _r(3, "30", testo="tot A"),
             _r(4, "12"), _r(5, "18"), _r(6, "30", testo="tot B"),
             _r(7, "10"), _r(8, "20"), _r(9, "30", testo="tot C")]
    R.marca_totali(righe)
    assert {r.id for r in righe if r.totale} == {"3", "6", "9"}
    assert sum(r.valore for r in R.foglie(righe)) == D("90")


def test_foglie_uguali_senza_totali():
    # due importi uguali in fila non sono il totale del terzo: senza un gruppo vero (k>=2)
    # da nessuna parte del documento, nessuna catena (k=1) va marcata.
    righe = [_r(1, "80"), _r(2, "80"), _r(3, "50")]
    R.marca_totali(righe)
    assert not any(r.totale for r in righe)
    assert sum(r.valore for r in R.foglie(righe)) == D("210")


def test_catena_ammessa_se_ci_sono_gruppi():
    # un gruppo vero (k>=2) c'e': la catena (k=1) nella stessa direzione resta ammessa.
    righe = [_r(1, "100"), _r(2, "50"), _r(3, "150", testo="mastro A"),
             _r(4, "30"), _r(5, "30", testo="mastro B")]
    R.marca_totali(righe)
    assert {r.id for r in righe if r.totale} == {"3", "5"}
    assert sum(r.valore for r in R.foglie(righe)) == D("180")


def test_senza_valori_non_va_in_crash():
    assert not R.marca_totali([])
    righe = [_r(1, None), _r(2, None), _r(3, None)]
    assert not R.marca_totali(righe)
    assert not any(r.totale for r in righe)


def test_prestazioni_duemila_righe():
    # 666 gruppi (a, b, a+b "tot") su lati alternati L/R, valori senza alcuna collisione fra
    # gruppi (intervalli disgiunti), piu' una piccola catena in coda: deve restare sotto un
    # secondo anche con ~2000 righe, senza cambiare il risultato (ogni terza riga e' il totale).
    righe = []
    for g in range(666):
        a, b = 10000 + g * 10, 20000 + g * 10
        lato = "L" if g % 2 == 0 else "R"
        righe.append(_r(f"{g}a", str(a), lato=lato))
        righe.append(_r(f"{g}b", str(b), lato=lato))
        righe.append(_r(f"{g}tot", str(a + b), lato=lato, testo=f"tot {g}"))
    righe.append(_r("c1", "99999999"))
    righe.append(_r("c2", "99999999", testo="mastro catena"))

    inizio = time.perf_counter()
    R.marca_totali(righe)
    durata = time.perf_counter() - inizio

    assert durata < 1.0, f"marca_totali troppo lento su 2000 righe: {durata:.2f}s"
    attesi = {f"{g}tot" for g in range(666)} | {"c2"}
    assert {r.id for r in righe if r.totale} == attesi


def test_gerarchia_a_tre_livelli_totali_dopo_i_figli():
    # foglie -> I/II/III (livello 1) -> B (livello 2, = I+II+III) -> Totale (livello 3, = B+C):
    # un totale appena marcato deve restare disponibile come addendo per il livello sopra, o
    # B e Totale restano foglie non riconosciute (diagnosi AMBIENTA, marca_totali a 2 livelli).
    # Importi su scale ben separate: nessuna somma parziale di un gruppo deve poter collidere
    # per caso col valore di un altro (il rischio di un test con numeri tondi ripetuti).
    righe = [
        _r("i1", "11"), _r("i2", "22"), _r("I", "33", testo="I"),
        _r("ii1", "101"), _r("ii2", "202"), _r("II", "303", testo="II"),
        _r("iii1", "1009"), _r("iii2", "2018"), _r("III", "3027", testo="III"),
        _r("B", "3363", testo="B"),
        _r("C", "50000"),
        _r("Totale", "53363", testo="Totale attivo"),
    ]
    direzioni = R.marca_totali(righe)
    assert direzioni.most_common(1)[0][0] == -1
    tot = {r.id for r in righe if r.totale}
    assert tot == {"I", "II", "III", "B", "Totale"}
    assert sum(r.valore for r in R.foglie(righe)) == D("53363")


def test_gerarchia_a_tre_livelli_totali_prima_dei_figli():
    # stessa gerarchia, ma col totale che PRECEDE i propri figli (come nel documento AMBIENTA
    # reale: "B) Immobilizzazioni" e' stampato prima di "I.", "II.", "III.").
    righe = [
        _r("Totale", "53363", testo="Totale attivo"),
        _r("B", "3363", testo="B"),
        _r("I", "33", testo="I"), _r("i1", "11"), _r("i2", "22"),
        _r("II", "303", testo="II"), _r("ii1", "101"), _r("ii2", "202"),
        _r("III", "3027", testo="III"), _r("iii1", "1009"), _r("iii2", "2018"),
        _r("C", "50000"),
    ]
    direzioni = R.marca_totali(righe)
    assert direzioni.most_common(1)[0][0] == 1
    tot = {r.id for r in righe if r.totale}
    assert tot == {"I", "II", "III", "B", "Totale"}
    assert sum(r.valore for r in R.foglie(righe)) == D("53363")


def test_forma_ambienta_totali_lettera_e_stato_patrimoniale():
    # Forma ricostruita dalla diagnosi (diagnosi-ambienta-verifica.md §4): importi e didascalie
    # reali di AMBIENTA, totale che precede i figli come nel documento vero. Prima del punto
    # fisso, "B) Immobilizzazioni", "C) Attivo circolante" e "STATO PATRIMONIALE ATTIVO"
    # restavano foglie non riconosciute anche quando i loro figli erano tutti presenti.
    righe = [
        _r("attivo", "2352461.64", testo="STATO PATRIMONIALE ATTIVO"),
        _r("B", "489671.44", testo="B) Immobilizzazioni"),
        _r("I", "346304.85", testo="I. Immobilizzazioni Immateriali"),
        _r("II", "90816.59", testo="II. Immobilizzazioni Materiali"),
        _r("III", "52550.00", testo="III. Immobilizzazioni Finanziarie"),
        _r("C", "1646563.90", testo="C) Attivo circolante"),
        _r("Ci", "287526.55", testo="I. Rimanenze"),
        _r("Cii", "1337272.64", testo="II. Crediti"),
        _r("Civ", "21764.71", testo="IV. Disponibilita' liquide"),
        _r("D", "216226.30", testo="D) Ratei e risconti attivi"),
    ]
    R.marca_totali(righe)
    tot = {r.id for r in righe if r.totale}
    assert tot == {"attivo", "B", "C"}
    assert sum(r.valore for r in R.foglie(righe)) == D("2352461.64")


def test_mastro_a_figlio_unico_non_raddoppia_dentro_un_totale_di_livello_superiore():
    # Forma reale (diagnosi TM 589/590, Task 20): "09 RIMANENZE" precede i suoi due membri
    # "09.01" (due figli propri, risolvibile a k=2) e "09.03" (un solo figlio, risolvibile
    # solo a k=1). Prima del fix, il cammino k>=2 di "09" consumava "09.03" come membro
    # grezzo prima che la passata k=1 lo risolvesse: "09.03" e il suo unico figlio restavano
    # ENTRAMBI foglie con lo stesso importo (40.000,00), raddoppiando la massa.
    righe = [
        _r("09", "231250.00", testo="09 RIMANENZE"),
        _r("0901", "191250.00", testo="09.01 RIMANENZE DI MAGAZZINO"),
        _r("090101", "100000.00"),
        _r("090102", "91250.00"),
        _r("0903", "40000.00", testo="09.03 LAVORI IN CORSO"),
        _r("090301", "40000.00", testo="09.03.01 Lavori in corso su ordinazione"),
    ]
    R.marca_totali(righe)
    tot = {r.id for r in righe if r.totale}
    assert tot == {"09", "0901", "0903"}
    foglie = {r.id for r in R.foglie(righe)}
    assert foglie == {"090101", "090102", "090301"}
    assert sum(r.valore for r in R.foglie(righe)) == D("231250.00")
    # "09.03" resta un mastro dichiarato (mastro del proprio figlio) anche se e' a sua volta
    # consumato come membro di "09": le due cose coesistono, come per ogni totale intermedio.
    by_id = {r.id: r for r in righe}
    assert by_id["090301"].mastro == "09.03 LAVORI IN CORSO"
    assert by_id["0903"].mastro == "09 RIMANENZE"


def test_totale_di_terzo_livello_non_scavalca_un_totale_intermedio_non_ancora_risolto():
    # Ogni gruppo di primo livello ha piu' foglie del tetto di 80 membri per candidato (90 in
    # tutto per I+II+III): "B" non puo' essere raggiunto sommando le 90 foglie grezze in una
    # volta sola (il tetto lo impedisce), quindi l'unico modo di trovarlo e' che I, II, III
    # tornino disponibili come addendi DOPO essere stati risolti. Valori come potenze di 2
    # distinte (nessuna somma parziale puo' mai coincidere per caso con un'altra) cosi' un
    # totale di livello superiore ("Totale") scandito piu' avanti nella stessa passata non puo'
    # scavalcare "B" ancora irrisolto sommando le sue foglie rimaste vive per coincidenza.
    def gruppo(base, n=30):
        foglie = [2 ** (base + k) for k in range(n)]
        return foglie, sum(foglie)

    foglie_i, I = gruppo(0)
    foglie_ii, II = gruppo(30)
    foglie_iii, III = gruppo(60)
    C = 2 ** 90
    B = I + II + III
    Totale = B + C

    righe = [_r(f"i{k}", str(v)) for k, v in enumerate(foglie_i)]
    righe.append(_r("I", str(I), testo="I"))
    righe += [_r(f"ii{k}", str(v)) for k, v in enumerate(foglie_ii)]
    righe.append(_r("II", str(II), testo="II"))
    righe += [_r(f"iii{k}", str(v)) for k, v in enumerate(foglie_iii)]
    righe.append(_r("III", str(III), testo="III"))
    righe.append(_r("B", str(B), testo="B"))
    righe.append(_r("C", str(C)))
    righe.append(_r("Totale", str(Totale), testo="Totale attivo"))

    R.marca_totali(righe)
    tot = {r.id for r in righe if r.totale}
    assert tot == {"I", "II", "III", "B", "Totale"}
    assert sum(r.valore for r in R.foglie(righe)) == D(str(Totale))


# --- Task 27, item 5 (diagnosi budget_243): un importo dentro la descrizione non e' un importo ---

def _riga_fisica(id_, testo, importi, posizioni, pagina=1, lato="L", sezione="ce"):
    from types import SimpleNamespace as N
    return N(id=id_, page=pagina, side=lato, text=testo, amounts=tuple(D(i) for i in importi),
             positions=tuple(posizioni), code="", kinds=(), statement=sezione)


def _righe_243(monkeypatch):
    """Come la pagina 4 di budget_243: i conti hanno l'importo in colonna (x ~ 250-270), e la
    descrizione di 622407 va a capo su una riga fisica propria ('inferiore euro 516,46') il cui
    numero sta a x = 123, dentro la descrizione."""
    from importers import detail_enrichment as DE
    from importers.import_snello import righe as R

    fisiche = [
        _riga_fisica("r1", "622301 Ammortamento attrezzatura 26.870,85", ["26870.85"], [252.0]),
        _riga_fisica("r2", "622401 Ammortamento mobili 1.893,43", ["1893.43"], [256.9]),
        _riga_fisica("r3", "622402 Ammortamento macchine ufficio 2.855,77", ["2855.77"], [256.9]),
        _riga_fisica("r4", "622406 Ammortamento autoveicoli 14.720,18", ["14720.18"], [252.0]),
        _riga_fisica("r5", "622407 Ammortamento altri beni valore 339,34", ["339.34"], [263.7]),
        _riga_fisica("r6", "inferiore euro 516,46", ["516.46"], [123.1]),
        _riga_fisica("r7", "640102 Imposta di bollo 10,00", ["10.00"], [268.5]),
        _riga_fisica("r8", "640301 Imposta di registro 738,50", ["738.50"], [263.7]),
        _riga_fisica("r9", "640501 Diritti camerali 198,79", ["198.79"], [263.7]),
        _riga_fisica("r10", "650219 Sanzioni 2.090,05", ["2090.05"], [256.9]),
    ]
    monkeypatch.setattr(DE, "collect_source_rows", lambda *a, **k: fisiche)
    return R


def test_importo_preceduto_da_euro_e_fuori_colonna_resta_nella_descrizione(monkeypatch):
    R = _righe_243(monkeypatch)
    righe = R.righe_da_pdf("x.pdf", None, ["saldo_finale"])
    r6 = next(r for r in righe if r.id == "r6")
    assert r6.valore is None                       # non e' un importo
    assert "euro 516,46" in r6.testo               # la descrizione resta intera
    assert sum(1 for r in righe if r.valore is not None) == 9
    assert [r.valore for r in R.foglie(righe)].count(D("516.46")) == 0


def test_importo_dopo_euro_ma_in_colonna_resta_un_importo(monkeypatch):
    """«Rettifiche per arrotondamento Euro 393,82» e «Cassa Euro 239.126,40»: la valuta e'
    il prefisso della colonna, allineata alle altre righe - non una descrizione."""
    from importers import detail_enrichment as DE
    from importers.import_snello import righe as R

    fisiche = [_riga_fisica(f"r{i}", f"6{i}00 Conto {i} 1.0{i},00", [f"10{i}"], [252.0]) for i in range(1, 9)]
    fisiche.append(_riga_fisica("rx", "7000 Cassa Euro 239.126,40", ["239126.40"], [250.0]))
    monkeypatch.setattr(DE, "collect_source_rows", lambda *a, **k: fisiche)
    righe = R.righe_da_pdf("x.pdf", None, ["saldo_finale"])
    assert next(r for r in righe if r.id == "rx").valore == D("239126.40")


def test_importo_dopo_euro_con_altri_importi_nella_riga_non_si_tocca(monkeypatch):
    """Piu' importi nella riga: quello dopo «Euro» e' la prima colonna, mai una descrizione."""
    from importers import detail_enrichment as DE
    from importers.import_snello import righe as R

    fisiche = [_riga_fisica(f"r{i}", f"6{i}00 Conto {i} 1.0{i},00", [f"10{i}"], [252.0]) for i in range(1, 9)]
    fisiche.append(_riga_fisica("rz", "3650 Rettifiche per arrotondamento Euro 393,82 1.027,37",
                                ["393.82", "1027.37"], [120.0, 190.0]))
    monkeypatch.setattr(DE, "collect_source_rows", lambda *a, **k: fisiche)
    righe = R.righe_da_pdf("x.pdf", None, ["saldo_corrente", "saldo_precedente"])
    assert next(r for r in righe if r.id == "rz").valore == D("393.82")


def test_riga_con_saldo_sporco_dopo_la_descrizione_con_euro_non_si_tocca(monkeypatch):
    """budget_615: «beni di costo unitario inf. euro 516,46» seguito dal saldo scritto con
    sottolineature (che il lettore fisico non vede come importo): il saldo e' l'ultimo, non il 516,46."""
    from importers import detail_enrichment as DE
    from importers.import_snello import righe as R

    fisiche = [_riga_fisica(f"r{i}", f"6{i}00 Conto {i} 1.0{i},00", [f"10{i}"], [252.0]) for i in range(1, 9)]
    fisiche.append(_riga_fisica("rs", "703115 000 - beni di costo unitario inf. euro 516,46 _1_.46_1_,_8_6_",
                                ["516.46"], [60.0]))
    monkeypatch.setattr(DE, "collect_source_rows", lambda *a, **k: fisiche)
    righe = R.righe_da_pdf("x.pdf", None, ["saldo_finale"])
    assert next(r for r in righe if r.id == "rs").valore == D("1461.86")
