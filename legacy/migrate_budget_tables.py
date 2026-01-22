#!/usr/bin/env python3
"""
Migration Script - Update Budget Tables Schema
This script drops and recreates budget-related tables to match the new schema
"""
from database.db import SessionLocal, engine, Base
from database.models import (
    BudgetScenario, BudgetAssumptions, ForecastYear,
    ForecastBalanceSheet, ForecastIncomeStatement
)
from sqlalchemy import inspect, text

def migrate_budget_tables():
    """Drop and recreate budget tables with updated schema"""

    print("🔄 Starting budget tables migration...")

    # Get database session
    db = SessionLocal()

    try:
        # Check which tables exist
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        budget_tables = [
            'forecast_income_statements',
            'forecast_balance_sheets',
            'forecast_years',
            'budget_assumptions',
            'budget_scenarios'
        ]

        # Drop budget tables in correct order (respecting foreign keys)
        print("\n📋 Dropping old budget tables...")
        for table in budget_tables:
            if table in existing_tables:
                print(f"   - Dropping {table}...")
                db.execute(text(f"DROP TABLE IF EXISTS {table}"))
                db.commit()

        print("\n✅ Old tables dropped successfully")

        # Create new tables with updated schema
        print("\n📊 Creating new budget tables with updated schema...")

        # Create only the budget-related tables
        Base.metadata.create_all(
            engine,
            tables=[
                BudgetScenario.__table__,
                BudgetAssumptions.__table__,
                ForecastYear.__table__,
                ForecastBalanceSheet.__table__,
                ForecastIncomeStatement.__table__
            ]
        )

        print("\n✅ New tables created successfully!")
        print("\n📝 Updated tables:")
        for table in budget_tables:
            print(f"   ✓ {table}")

        print("\n✅ Migration completed!")
        print("\n💡 Note: All existing budget scenarios and forecasts have been reset.")
        print("   Your company data and historical financials are unchanged.")

    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 70)
    print("BUDGET TABLES MIGRATION")
    print("=" * 70)
    print("\n⚠️  WARNING: This will delete all existing budget scenarios!")
    print("   Company data and historical financials will NOT be affected.")

    response = input("\n❓ Continue with migration? (yes/no): ").lower().strip()

    if response == 'yes':
        migrate_budget_tables()
    else:
        print("\n❌ Migration cancelled.")
