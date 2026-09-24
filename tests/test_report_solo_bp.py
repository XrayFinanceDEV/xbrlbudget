"""Il dossier Typst è staccato da /report (2026-09-24): i suoi testi AI mancanti non tengono più il documento in bozza.

Restano dichiarati come informazione nel modello; gli altri avvisi contano come prima.
"""
from tests.test_final_report_endpoint import client, _url  # noqa: F401  fixture condivisa


def test_testi_ai_mancanti_non_bloccano_il_finale(client):  # noqa: F811
    r = client.get(_url(client, client.ids["scenario"]))
    assert r.status_code == 200, r.text
    body = r.json()
    motivi = [x["code"] for x in body["readiness"]["reasons"]]
    assert "narrative_missing" not in motivi
    assert body["readiness"]["status"] == "ready", motivi
    info = [d for d in body["diagnostics"] if d["code"] == "narrative_missing"]
    assert info and {d["severity"] for d in info} == {"info"}


def test_business_plan_finale_in_pdf_e_word(client):  # noqa: F811
    base = f"/api/v1/companies/{client.ids['company']}/scenarios/{client.ids['scenario']}/business-plan"
    for fmt in ("pdf", "docx"):
        r = client.post(f"{base}/{fmt}", json={"document_state": "final"})
        assert r.status_code == 200, (fmt, r.text)
