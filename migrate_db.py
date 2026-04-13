"""
Safe database migration script — adds all missing columns without touching existing data.
Run on production: python migrate_db.py [path/to/financial_analysis.db]
"""
import sqlite3
import sys
import os

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "financial_analysis.db")

print(f"Migrating: {DB_PATH}")

MIGRATIONS = {
    "forecast_income_statements": [
        ("ce03a_incrementi_immobilizzazioni",  "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce08a_tfr_accrual",                  "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce08b_salari_stipendi",              "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce08c_oneri_sociali",                "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce08d_altri_costi_personale",        "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce09a_ammort_immateriali",           "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce09b_ammort_materiali",             "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce09c_svalutazioni",                 "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce09d_svalutazione_crediti",         "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce11b_altri_accantonamenti",         "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce17a_rivalutazioni",                "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce17b_svalutazioni",                 "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
    ],
    "income_statements": [
        ("ce03a_incrementi_immobilizzazioni",  "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce08a_tfr_accrual",                  "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce08b_salari_stipendi",              "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce08c_oneri_sociali",                "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce08d_altri_costi_personale",        "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce09d_svalutazione_crediti",         "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce11b_altri_accantonamenti",         "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce17a_rivalutazioni",                "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("ce17b_svalutazioni",                 "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
    ],
    "balance_sheets": [
        ("sp06a_crediti_clienti_breve",        "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp06b_crediti_controllate_breve",    "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp06c_crediti_collegate_breve",      "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp06d_crediti_controllanti_breve",   "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp06e_crediti_tributari_breve",      "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp06f_imposte_anticipate_breve",     "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp06g_crediti_altri_breve",          "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp07a_crediti_clienti_lungo",        "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp07b_crediti_controllate_lungo",    "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp07c_crediti_collegate_lungo",      "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp07d_crediti_controllanti_lungo",   "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp07e_crediti_tributari_lungo",      "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp07f_imposte_anticipate_lungo",     "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp07g_crediti_altri_lungo",          "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp05a_materie_prime",                "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp05b_prodotti_in_corso",            "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp05c_lavori_in_corso",              "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp05d_prodotti_finiti",              "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("sp05e_acconti",                      "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
    ],
    "financial_years": [
        ("period_months",                      "INTEGER"),
        ("original_bs_snapshot",               "TEXT"),
        ("original_is_snapshot",               "TEXT"),
    ],
    "budget_scenarios": [
        ("scenario_type",                      "VARCHAR(20) DEFAULT 'budget' NOT NULL"),
        ("period_months",                      "INTEGER"),
        ("ai_comment_dashboard",               "TEXT"),
        ("ai_comment_composition",             "TEXT"),
        ("ai_comment_income_margins",          "TEXT"),
        ("ai_comment_structural",              "TEXT"),
        ("ai_comment_liquidity",               "TEXT"),
        ("ai_comment_solvency",                "TEXT"),
        ("ai_comment_profitability",           "TEXT"),
        ("ai_comment_efficiency",              "TEXT"),
        ("ai_comment_break_even",              "TEXT"),
        ("ai_comment_cashflow",                "TEXT"),
    ],
    "budget_assumptions": [
        ("intangible_investments",             "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("tangible_investments",               "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("dso_days",                           "NUMERIC(10,2)"),
        ("dio_days",                           "NUMERIC(10,2)"),
        ("dpo_days",                           "NUMERIC(10,2)"),
        ("existing_debt_repayment_years",      "NUMERIC(10,2)"),
        ("sp01_growth_pct",                    "NUMERIC(10,6)"),
        ("sp04_growth_pct",                    "NUMERIC(10,6)"),
        ("sp08_growth_pct",                    "NUMERIC(10,6)"),
        ("sp10_growth_pct",                    "NUMERIC(10,6)"),
        ("sp14_growth_pct",                    "NUMERIC(10,6)"),
        ("sp16e_growth_pct",                   "NUMERIC(10,6)"),
        ("sp16f_growth_pct",                   "NUMERIC(10,6)"),
        ("sp16g_growth_pct",                   "NUMERIC(10,6)"),
        ("sp17d_growth_pct",                   "NUMERIC(10,6)"),
        ("sp17e_growth_pct",                   "NUMERIC(10,6)"),
        ("sp17f_growth_pct",                   "NUMERIC(10,6)"),
        ("sp17g_growth_pct",                   "NUMERIC(10,6)"),
        ("sp18_growth_pct",                    "NUMERIC(10,6)"),
        ("variable_materials_growth_pct",      "NUMERIC(10,6) DEFAULT 0 NOT NULL"),
        ("fixed_materials_growth_pct",         "NUMERIC(10,6) DEFAULT 0 NOT NULL"),
        ("variable_services_growth_pct",       "NUMERIC(10,6) DEFAULT 0 NOT NULL"),
        ("fixed_services_growth_pct",          "NUMERIC(10,6) DEFAULT 0 NOT NULL"),
        ("fixed_materials_percentage",         "NUMERIC(10,6) DEFAULT 40 NOT NULL"),
        ("fixed_services_percentage",          "NUMERIC(10,6) DEFAULT 40 NOT NULL"),
        ("financing_amount",                   "NUMERIC(15,2) DEFAULT 0 NOT NULL"),
        ("financing_duration_years",           "NUMERIC(10,2) DEFAULT 0 NOT NULL"),
        ("financing_interest_rate",            "NUMERIC(10,6) DEFAULT 0 NOT NULL"),
        ("ce02_override",                      "NUMERIC(15,2)"),
        ("ce03_override",                      "NUMERIC(15,2)"),
        ("ce10_override",                      "NUMERIC(15,2)"),
        ("ce11_override",                      "NUMERIC(15,2)"),
        ("ce13_override",                      "NUMERIC(15,2)"),
        ("ce14_override",                      "NUMERIC(15,2)"),
        ("ce15_override",                      "NUMERIC(15,2)"),
        ("ce16_override",                      "NUMERIC(15,2)"),
        ("ce17_override",                      "NUMERIC(15,2)"),
        ("ce18_override",                      "NUMERIC(15,2)"),
        ("ce19_override",                      "NUMERIC(15,2)"),
        ("depreciation_rate_intangible",       "NUMERIC(10,6) DEFAULT 20 NOT NULL"),
    ],
}

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

added = 0
skipped = 0
for table, columns in MIGRATIONS.items():
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}

    for col, typedef in columns:
        if col in existing:
            skipped += 1
        else:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            print(f"  ADD   {table}.{col}")
            added += 1

conn.commit()
conn.close()
print(f"\nDone. Added {added} columns, skipped {skipped} (already existed).")
