from tools.triage_rilievi import esiti_junit, verdetto


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
