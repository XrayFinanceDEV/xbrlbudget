"""End-to-end API verification for the assumptions-simplification save path.

Prereq: backend running -> cd backend && DEV_USER_ID=dev-user-001 \
    uvicorn app.main:app --host 127.0.0.1 --port 8000

Checks: bulk save with essential-only fields collapses var==fixed, leaves
overrides NULL; a /forecast/income override survives a subsequent bulk save
(full-row hydration semantics); analysis returns forecast years.
Creates a throwaway company and deletes it at the end.
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"


def call(method, path, body=None):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read() or b"null")


def main():
    company = call("POST", "/companies", {"name": "VERIFY SEMPLIFICAZIONE SRL", "sector": 3})
    cid = company["id"]
    try:
        call("POST", f"/companies/{cid}/years", {"company_id": cid, "year": 2025})
        call("PUT", f"/companies/{cid}/years/2025/balance-sheet",
             {"sp09_disponibilita_liquide": 50000, "sp11_capitale": 50000})
        call("PUT", f"/companies/{cid}/years/2025/income-statement",
             {"ce01_ricavi_vendite": 500000, "ce05_materie_prime": 200000,
              "ce06_servizi": 100000, "ce08_costi_personale": 100000,
              "ce20_imposte": 10000})
        scenario = call("POST", f"/companies/{cid}/scenarios",
                        {"company_id": cid, "name": "verify", "base_year": 2025,
                         "scenario_type": "budget"})
        sid = scenario["id"]

        # essential-only bulk save: Materie% dual-written by the form as var==fixed
        rows = [{"forecast_year": y,
                 "revenue_growth_pct": 5.0,
                 "variable_materials_growth_pct": 3.0,
                 "fixed_materials_growth_pct": 3.0,
                 "variable_services_growth_pct": 2.0,
                 "fixed_services_growth_pct": 2.0,
                 "personnel_growth_pct": 1.0,
                 "other_costs_growth_pct": 1.0,
                 "tangible_investments": 10000}
                for y in (2026, 2027, 2028)]
        res = call("PUT", f"/companies/{cid}/scenarios/{sid}/assumptions",
                   {"assumptions": rows, "auto_generate": True})
        assert res.get("forecast_generated"), f"generation failed: {res}"

        saved = call("GET", f"/companies/{cid}/scenarios/{sid}/assumptions")
        assert len(saved) == 3, saved
        for a in saved:
            assert float(a["variable_materials_growth_pct"]) == float(a["fixed_materials_growth_pct"]) == 3.0
            assert a["ce01_override"] is None and a["ce15_override"] is None, \
                "no-op overrides must not be stored"
            assert float(a.get("receivables_short_growth_pct") or 0) == 0

        # override survives a re-save with hydrated rows (form behavior)
        call("PATCH", f"/companies/{cid}/scenarios/{sid}/ce-override",
             {"overrides": [{"forecast_year": 2026, "field": "ce01_override", "value": 600000}]})
        hydrated = call("GET", f"/companies/{cid}/scenarios/{sid}/assumptions")
        call("PUT", f"/companies/{cid}/scenarios/{sid}/assumptions",
             {"assumptions": hydrated, "auto_generate": True})
        after = call("GET", f"/companies/{cid}/scenarios/{sid}/assumptions")
        y26 = next(a for a in after if a["forecast_year"] == 2026)
        assert float(y26["ce01_override"]) == 600000, "override wiped by bulk save"

        analysis = call("GET", f"/companies/{cid}/scenarios/{sid}/analysis")
        assert len(analysis.get("forecast_years", [])) == 3, "analysis missing forecast years"
        print("OK: bulk save, collapse var==fixed, override preservation, analysis")
    finally:
        call("DELETE", f"/companies/{cid}")


if __name__ == "__main__":
    sys.exit(main())
