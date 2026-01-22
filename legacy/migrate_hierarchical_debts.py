#!/usr/bin/env python3
"""
Database Migration Script - Add Hierarchical Debt and Depreciation Fields
Adds detailed debt breakdown fields and depreciation split fields
"""
import sys
from sqlalchemy import text
from database.db import SessionLocal

def migrate_add_hierarchical_fields():
    """Add hierarchical debt and depreciation fields to existing tables"""
    db = SessionLocal()

    try:
        print("=" * 80)
        print("DATABASE MIGRATION: Adding Hierarchical Debt and Depreciation Fields")
        print("=" * 80)

        # Check which tables exist
        result = db.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result.fetchall()]

        print(f"\n✓ Found {len(tables)} tables in database")

        # === BALANCE SHEETS TABLE ===
        if 'balance_sheets' in tables:
            print("\n📊 Migrating balance_sheets table...")

            # Check if new fields already exist
            result = db.execute(text("PRAGMA table_info(balance_sheets)"))
            columns = [row[1] for row in result.fetchall()]

            fields_to_add = []

            # Financial debt fields
            if 'sp16a_debiti_banche_breve' not in columns:
                fields_to_add.extend([
                    "sp16a_debiti_banche_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17a_debiti_banche_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16b_debiti_altri_finanz_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17b_debiti_altri_finanz_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16c_debiti_obbligazioni_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17c_debiti_obbligazioni_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL"
                ])

            # Operating debt fields
            if 'sp16d_debiti_fornitori_breve' not in columns:
                fields_to_add.extend([
                    "sp16d_debiti_fornitori_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17d_debiti_fornitori_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16e_debiti_tributari_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17e_debiti_tributari_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16f_debiti_previdenza_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17f_debiti_previdenza_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16g_altri_debiti_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17g_altri_debiti_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL"
                ])

            if fields_to_add:
                for field in fields_to_add:
                    try:
                        sql = f"ALTER TABLE balance_sheets ADD COLUMN {field}"
                        db.execute(text(sql))
                        print(f"   ✓ Added {field.split()[0]}")
                    except Exception as e:
                        print(f"   ⚠ Skipping {field.split()[0]}: {str(e)}")

                db.commit()
                print(f"   ✓ Added {len(fields_to_add)} new fields to balance_sheets")
            else:
                print("   ✓ All fields already exist in balance_sheets")

        # === FORECAST BALANCE SHEETS TABLE ===
        if 'forecast_balance_sheets' in tables:
            print("\n📊 Migrating forecast_balance_sheets table...")

            result = db.execute(text("PRAGMA table_info(forecast_balance_sheets)"))
            columns = [row[1] for row in result.fetchall()]

            fields_to_add = []

            # Financial debt fields
            if 'sp16a_debiti_banche_breve' not in columns:
                fields_to_add.extend([
                    "sp16a_debiti_banche_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17a_debiti_banche_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16b_debiti_altri_finanz_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17b_debiti_altri_finanz_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16c_debiti_obbligazioni_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17c_debiti_obbligazioni_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL"
                ])

            # Operating debt fields
            if 'sp16d_debiti_fornitori_breve' not in columns:
                fields_to_add.extend([
                    "sp16d_debiti_fornitori_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17d_debiti_fornitori_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16e_debiti_tributari_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17e_debiti_tributari_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16f_debiti_previdenza_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17f_debiti_previdenza_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp16g_altri_debiti_breve NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "sp17g_altri_debiti_lungo NUMERIC(15, 2) DEFAULT 0 NOT NULL"
                ])

            if fields_to_add:
                for field in fields_to_add:
                    try:
                        sql = f"ALTER TABLE forecast_balance_sheets ADD COLUMN {field}"
                        db.execute(text(sql))
                        print(f"   ✓ Added {field.split()[0]}")
                    except Exception as e:
                        print(f"   ⚠ Skipping {field.split()[0]}: {str(e)}")

                db.commit()
                print(f"   ✓ Added {len(fields_to_add)} new fields to forecast_balance_sheets")
            else:
                print("   ✓ All fields already exist in forecast_balance_sheets")

        # === INCOME STATEMENTS TABLE ===
        if 'income_statements' in tables:
            print("\n📊 Migrating income_statements table...")

            result = db.execute(text("PRAGMA table_info(income_statements)"))
            columns = [row[1] for row in result.fetchall()]

            fields_to_add = []

            # Depreciation split fields
            if 'ce09a_ammort_immateriali' not in columns:
                fields_to_add.extend([
                    "ce09a_ammort_immateriali NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "ce09b_ammort_materiali NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "ce09c_svalutazioni NUMERIC(15, 2) DEFAULT 0 NOT NULL"
                ])

            if fields_to_add:
                for field in fields_to_add:
                    try:
                        sql = f"ALTER TABLE income_statements ADD COLUMN {field}"
                        db.execute(text(sql))
                        print(f"   ✓ Added {field.split()[0]}")
                    except Exception as e:
                        print(f"   ⚠ Skipping {field.split()[0]}: {str(e)}")

                db.commit()
                print(f"   ✓ Added {len(fields_to_add)} new fields to income_statements")
            else:
                print("   ✓ All fields already exist in income_statements")

        # === FORECAST INCOME STATEMENTS TABLE ===
        if 'forecast_income_statements' in tables:
            print("\n📊 Migrating forecast_income_statements table...")

            result = db.execute(text("PRAGMA table_info(forecast_income_statements)"))
            columns = [row[1] for row in result.fetchall()]

            fields_to_add = []

            # Depreciation split fields
            if 'ce09a_ammort_immateriali' not in columns:
                fields_to_add.extend([
                    "ce09a_ammort_immateriali NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "ce09b_ammort_materiali NUMERIC(15, 2) DEFAULT 0 NOT NULL",
                    "ce09c_svalutazioni NUMERIC(15, 2) DEFAULT 0 NOT NULL"
                ])

            if fields_to_add:
                for field in fields_to_add:
                    try:
                        sql = f"ALTER TABLE forecast_income_statements ADD COLUMN {field}"
                        db.execute(text(sql))
                        print(f"   ✓ Added {field.split()[0]}")
                    except Exception as e:
                        print(f"   ⚠ Skipping {field.split()[0]}: {str(e)}")

                db.commit()
                print(f"   ✓ Added {len(fields_to_add)} new fields to forecast_income_statements")
            else:
                print("   ✓ All fields already exist in forecast_income_statements")

        print("\n" + "=" * 80)
        print("✅ Migration completed successfully!")
        print("=" * 80)
        print("\nNew fields added:")
        print("  Balance Sheets:")
        print("    - sp16a-g_* (short-term debt details)")
        print("    - sp17a-g_* (long-term debt details)")
        print("  Income Statements:")
        print("    - ce09a_ammort_immateriali (intangible depreciation)")
        print("    - ce09b_ammort_materiali (tangible depreciation)")
        print("    - ce09c_svalutazioni (write-downs)")
        print("\n⚠️  IMPORTANT: Re-import XBRL files to populate the new fields!")

    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_add_hierarchical_fields()
