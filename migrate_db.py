#!/usr/bin/env python3
"""
Database Migration Script
Creates all new tables for budget forecasting
"""
from database.db import init_db

if __name__ == "__main__":
    print("🔄 Initializing database...")
    print("📊 Creating tables for budget forecasting...")

    init_db()

    print("✅ Database migration completed!")
    print("📝 New tables created:")
    print("   - budget_scenarios")
    print("   - budget_assumptions")
    print("   - forecast_years")
    print("   - forecast_balance_sheets")
    print("   - forecast_income_statements")
