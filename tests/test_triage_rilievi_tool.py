from tools.triage_rilievi import LETTURE, cartella_uscita, esiti_junit, riga_foglio, senza_fails, verdetto


def test_tabella_del_verdetto():
    assert verdetto("fail", "fail") == "Confermato"
    assert verdetto("fail", "pass") == "Risolto (2026-09-24)"
    assert verdetto("pass", "pass") == "Non riprodotto"
    assert verdetto("pass", "fail") == "Regressione"
    assert verdetto("skip", "fail") == "Confermato (n/a su 62bfed1)"
    assert verdetto("skip", "pass") == "Non riprodotto (n/a su 62bfed1)"
    assert verdetto(None, None) == "Senza test"


def test_esiti_junit_prende_il_peggiore_per_rilievo(tmp_path):
    x = tmp_path / "r.xml"
    x.write_text(
        '<testsuites><testsuite>'
        '<testcase name="test_A01_scostamento"/>'
        '<testcase name="test_A01_bis_salvataggio"><failure message="x"/></testcase>'
        '<testcase name="test_C02_dso"><skipped/></testcase>'
        '<testcase name="A06 un solo comando"/>'
        '<testcase name="rilievi AMBIENTA · wizard &gt; A03 il passo Imposte"/>'
        '<testcase name="test_kit_la_base"/>'
        '</testsuite></testsuites>')
    assert esiti_junit(x) == {"A01": "fail", "C02": "skip", "A06": "pass", "A03": "pass"}


def test_cartella_uscita_crea_gitignore(tmp_path):
    out = cartella_uscita(tmp_path)
    assert (out / ".gitignore").exists()
    assert (out / ".gitignore").read_text() == "*\n"
    assert out == tmp_path / ".superpowers" / "triage"


def test_esiti_junit_un_xfail_rimasto_vale_rosso_e_un_xpass_vale_verde(tmp_path):
    """Difesa se il banco gira senza --runxfail: xfail = rilievo confermato, XPASS(strict) = test passato."""
    x = tmp_path / "r.xml"
    x.write_text(
        '<testsuites><testsuite>'
        '<testcase name="test_B01_rimanenze"><skipped type="pytest.xfail" message="B01 confermato"/></testcase>'
        '<testcase name="test_B02_ammortamento"><failure message="[XPASS(strict)] B02 confermato"/></testcase>'
        '<testcase name="test_C02_dso"><skipped type="pytest.skip" message="n/a"/></testcase>'
        '</testsuite></testsuites>')
    assert esiti_junit(x) == {"B01": "fail", "B02": "pass", "C02": "skip"}


def test_senza_fails_toglie_il_marcatore_vitest():
    testo = 'it.fails("A01 x", () => {});\n  it("A03 y", () => {});\nit.fails ("A05 z", f);\n'
    assert senza_fails(testo) == 'it("A01 x", () => {});\n  it("A03 y", () => {});\nit("A05 z", f);\n'


def test_riga_foglio_meccanica_senza_lettura():
    stato, nota = riga_foglio("B01", {"B01": "fail"}, {"B01": "fail"}, letture={})
    assert stato == "Confermato"
    assert nota == "banco: 62bfed1=fail, HEAD=fail"


def test_riga_foglio_la_lettura_prevale_e_tiene_il_banco_nella_nota():
    letture = {"A05": ("Comportamento voluto", "passare a Manuale congela la crescita")}
    stato, nota = riga_foglio("A05", {"A05": "pass"}, {"A05": "pass"}, letture=letture)
    assert stato == "Comportamento voluto"
    assert nota == "passare a Manuale congela la crescita — banco: 62bfed1=pass, HEAD=pass"


def test_letture_coprono_i_rilievi_letti_a_mano():
    assert {"A01", "A03", "A04", "A05", "A06", "B04", "E05"} <= set(LETTURE)
