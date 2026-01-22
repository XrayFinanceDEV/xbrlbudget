# Instructions to See Enhanced Parser Changes

## What Was Updated

✅ **Backend now uses enhanced XBRL parser with reconciliation**

### Files Modified:
1. `/backend/app/api/v1/imports.py` - Now uses `import_xbrl_file_enhanced`
2. `/backend/importers/xbrl_parser_enhanced.py` - Copied enhanced parser
3. `/backend/data/taxonomy_mapping.json` - Updated with new mappings

### Backend Status:
- ✅ Uvicorn server reloaded automatically
- ✅ Enhanced parser is active

## Steps to See the Changes

### Option 1: Reimport XBRL via UI (Recommended)

1. **Open the import page:**
   ```
   http://localhost:3001/import
   ```

2. **Select the XBRL file:**
   - Choose "XBRL (formato italiano)"
   - Select "Aggiorna azienda esistente" mode
   - Make sure your company (BKPS) is selected
   - Upload `BKPS.XBRL` again

3. **Click "Importa XBRL"**
   - The backend will use the enhanced parser
   - Balance sheet will be perfectly balanced (0 € difference)

4. **View the results:**
   - Go to: `http://localhost:3001/forecast/balance`
   - Check the historical columns (2023, 2024)
   - The balance warning should disappear
   - Total Assets should equal Total Liabilities exactly

### Option 2: Direct API Test

Test the backend API directly:

```bash
# From project root
cd /home/peter/DEV/budget

# Make API call
curl -X POST "http://localhost:8000/api/v1/import/xbrl?company_id=1&create_company=false" \
  -F "file=@BKPS.XBRL"
```

Expected response should include:
```json
{
  "success": true,
  "company_name": "BKPS FINANCIAL LAB S.R.L.",
  "years": [2024, 2023],
  "reconciliation_info": {
    "2024": {
      "aggregate_totals": {
        "TotaleAttivo": 205686.0,
        "TotalePassivo": 205686.0,
        "TotaleCrediti": 82472.0
      },
      "reconciliation_adjustments": {}
    }
  }
}
```

### Option 3: Recalculate Forecasts

If you've already created budget scenarios:

1. **Go to budget page:**
   ```
   http://localhost:3001/budget
   ```

2. **Select your scenario**

3. **Click "Ricalcola Previsioni"** (if available)
   - This will regenerate forecasts using the new balanced historical data

4. **View updated forecasts:**
   - Income Statement: `http://localhost:3001/forecast/income`
   - Balance Sheet: `http://localhost:3001/forecast/balance`

## What You Should See After Reimport

### Before (Old Parser):
```
2024 Balance Sheet:
  Total Assets:      €205,627.00
  Total Liabilities: €205,686.00
  DIFFERENCE:        €-59.00  ❌
```

### After (Enhanced Parser):
```
2024 Balance Sheet:
  Total Assets:      €205,686.00
  Total Liabilities: €205,686.00
  DIFFERENCE:        €0.00     ✅
```

### Detailed Breakdown:
```
Credits breakdown:
  Short-term credits:     €82,472.00  (was €82,413.00)
  Includes:
    - Trade receivables:  €82,413.00
    - Deferred tax assets:€59.00      ← Now captured!
```

## Troubleshooting

### If you don't see changes:

1. **Check backend is running:**
   ```bash
   ps aux | grep uvicorn
   ```

2. **Check logs for errors:**
   ```bash
   # Backend should show reload message
   tail -f /tmp/uvicorn.log  # if logging to file
   ```

3. **Force browser cache clear:**
   - Press `Ctrl+Shift+R` (hard refresh)
   - Or clear browser cache completely

4. **Verify import was successful:**
   - Check the success message on import page
   - Should show "Importazione completata!"

5. **Check database directly:**
   ```bash
   cd /home/peter/DEV/budget
   source .venv/bin/activate
   python -c "
   from database.db import SessionLocal
   from database.models import FinancialYear

   db = SessionLocal()
   fy = db.query(FinancialYear).filter_by(year=2024).first()
   bs = fy.balance_sheet
   print(f'Total Assets: €{bs.total_assets:,.2f}')
   print(f'Total Liabilities: €{bs.total_liabilities:,.2f}')
   print(f'Credits (short): €{bs.sp06_crediti_breve:,.2f}')
   print(f'Difference: €{bs.total_assets - bs.total_liabilities:,.2f}')
   "
   ```

### If backend isn't using enhanced parser:

1. **Restart backend manually:**
   ```bash
   # Find and kill the process
   pkill -f uvicorn

   # Restart from backend directory
   cd /home/peter/DEV/budget/backend
   source ../venv/bin/activate
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

2. **Verify imports:**
   ```bash
   cd /home/peter/DEV/budget/backend
   python -c "from importers.xbrl_parser_enhanced import import_xbrl_file_enhanced; print('✓ Import successful')"
   ```

## Expected Timeline

1. **Import XBRL file:** ~5-10 seconds
2. **Backend processing:** Immediate
3. **Frontend refresh:** Immediate (after page reload)
4. **Total time:** < 1 minute

## Verification Checklist

After reimport, verify:

- [ ] Import success message shows on UI
- [ ] Company data updated (check years imported)
- [ ] Balance sheet balances (0 € difference)
- [ ] Credits now €82,472 (was €82,413)
- [ ] No yellow warning banner on forecast pages
- [ ] "DIFFERENZA" row shows €0.00
- [ ] All forecast calculations work correctly

## Need Help?

If issues persist:

1. Check backend logs for errors
2. Verify file permissions on imported files
3. Ensure database isn't locked
4. Try importing a different XBRL file to test
5. Check browser console for JavaScript errors

## Summary

The enhanced parser is now active in your backend! Simply reimport the XBRL file via the UI at `http://localhost:3001/import` and you'll see perfectly balanced financial statements with the 59 € discrepancy resolved.
