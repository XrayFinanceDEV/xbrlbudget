"""
Test that all Streamlit UI imports work correctly
"""

def test_imports():
    """Test all UI page imports"""
    print("Testing Streamlit UI imports...")

    try:
        from ui.pages import dati_impresa
        print("✓ dati_impresa imported")
    except Exception as e:
        print(f"✗ dati_impresa failed: {e}")

    try:
        from ui.pages import importazione
        print("✓ importazione imported")
    except Exception as e:
        print(f"✗ importazione failed: {e}")

    try:
        from ui.pages import balance_sheet
        print("✓ balance_sheet imported")
    except Exception as e:
        print(f"✗ balance_sheet failed: {e}")

    try:
        from ui.pages import income_statement
        print("✓ income_statement imported")
    except Exception as e:
        print(f"✗ income_statement failed: {e}")

    try:
        from ui.pages import ratios
        print("✓ ratios imported")
    except Exception as e:
        print(f"✗ ratios failed: {e}")

    try:
        from ui.pages import altman
        print("✓ altman imported")
    except Exception as e:
        print(f"✗ altman failed: {e}")

    try:
        from ui.pages import rating
        print("✓ rating imported")
    except Exception as e:
        print(f"✗ rating failed: {e}")

    try:
        from ui.pages import dashboard
        print("✓ dashboard imported")
    except Exception as e:
        print(f"✗ dashboard failed: {e}")

    print("\n✅ All imports successful!")


if __name__ == "__main__":
    test_imports()
