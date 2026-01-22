# Deployment Summary - XBRL Budget

## ✅ Preparation Complete

The project is now ready for deployment with the following configuration:

### Backend Configuration

**Hosted at:** `https://kpsfinanciallab.w3pro.it:8001`

**API Endpoint:** `https://kpsfinanciallab.w3pro.it:8001/api/v1`

**CORS Configuration Updated:**
- Added `https://*.netlify.app` wildcard for Netlify deployments
- Located in: `backend/app/core/config.py`

**Database:**
- SQLite database at project root: `/home/peter/DEV/budget/financial_analysis.db`
- Shared by both modern and legacy applications

### Frontend Configuration

**Target Platform:** Netlify

**Environment Variable Required:**
```
NEXT_PUBLIC_API_URL=https://kpsfinanciallab.w3pro.it:8001/api/v1
```

**Configuration Files Created:**
- `netlify.toml` - Netlify deployment configuration
- `.env.example` - Environment variable template
- `PRODUCTION_CONFIG.md` - Production configuration details
- `NETLIFY_CHECKLIST.md` - Step-by-step deployment checklist
- `README_DEPLOYMENT.md` - Comprehensive deployment guide

### Files Modified

**Frontend:**
- `.env.local` - Updated with production backend URL
- `.env.example` - Updated with production backend URL
- `app/*.tsx` - Fixed ESLint errors (unescaped quotes)

**Backend:**
- `app/core/config.py` - Added Netlify to CORS origins

### Project Structure (After Reorganization)

```
budget/
├── backend/                    # FastAPI REST API
│   ├── app/                    # Application code
│   └── venv/                   # Virtual environment
├── frontend/                   # Next.js 15 Frontend
│   ├── app/                    # Next.js pages
│   ├── lib/api.ts              # API client (configured with backend URL)
│   ├── netlify.toml            # ✨ NEW: Netlify config
│   ├── .env.local              # ✨ UPDATED: Production URL
│   ├── .env.example            # ✨ NEW: Template
│   └── PRODUCTION_CONFIG.md    # ✨ NEW: Production guide
├── database/                   # SHARED: ORM models
├── calculations/               # SHARED: Financial calculators
├── importers/                  # SHARED: XBRL/CSV parsers
├── config.py                   # SHARED: Configuration
├── data/                       # SHARED: JSON data
├── legacy/                     # Old Streamlit app
└── financial_analysis.db       # SHARED: Database
```

## Next Steps

### 1. Deploy Backend (if not already deployed)

```bash
# SSH to server: kpsfinanciallab.w3pro.it
cd /path/to/backend
source venv/bin/activate

# Start backend on port 8001
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Or use systemd service (recommended)
sudo systemctl start xbrl-budget-backend
```

**Verify Backend:**
```bash
curl https://kpsfinanciallab.w3pro.it:8001/api/v1/companies
```

### 2. Deploy Frontend to Netlify

**Option A: Via Netlify UI (Recommended)**

1. Go to https://app.netlify.com
2. Click "Add new site" → "Import an existing project"
3. Connect your Git repository
4. Configure build settings:
   - Base directory: `frontend`
   - Build command: `npm run build`
   - Publish directory: (leave empty)
5. Set environment variable:
   - Key: `NEXT_PUBLIC_API_URL`
   - Value: `https://kpsfinanciallab.w3pro.it:8001/api/v1`
6. Click "Deploy site"

**Option B: Via Netlify CLI**

```bash
cd frontend
netlify login
netlify init
netlify env:set NEXT_PUBLIC_API_URL "https://kpsfinanciallab.w3pro.it:8001/api/v1"
netlify deploy --prod
```

### 3. Update Backend CORS

After deployment, you'll get a Netlify URL like `https://your-site.netlify.app`

**Update backend CORS:**

1. SSH to `kpsfinanciallab.w3pro.it`
2. Edit `backend/app/core/config.py`
3. Add your Netlify URL:
```python
BACKEND_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "https://*.netlify.app",  # Already added
    "https://your-actual-site.netlify.app",  # Add this specific URL
]
```
4. Restart backend service

### 4. Verify Deployment

**Test Backend:**
```bash
curl https://kpsfinanciallab.w3pro.it:8001/api/v1/companies
```

**Test Frontend:**
1. Open Netlify URL in browser
2. Open DevTools → Console
3. Check for API errors
4. Test features:
   - Company list loads
   - Import works
   - Analysis displays

## Important Notes

### Backend URL with Custom Port

The backend uses **port 8001** instead of standard 443/80:
- Full URL: `https://kpsfinanciallab.w3pro.it:8001/api/v1`
- Ensure port 8001 is open in firewall
- SSL certificate must be valid for `kpsfinanciallab.w3pro.it`

### Environment Variables

Frontend uses `NEXT_PUBLIC_` prefix for browser-accessible variables:
- Must be set in Netlify dashboard
- Requires rebuild after changes
- Not a security risk (visible in browser)

### CORS is Critical

Without proper CORS configuration:
- Frontend will show: "CORS policy" errors
- API calls will fail
- Solution: Add Netlify domain to backend CORS

## Troubleshooting

### Issue: API calls fail with CORS error

**Solution:**
1. Verify Netlify URL is in backend CORS
2. Restart backend after CORS update
3. Clear browser cache

### Issue: Environment variable not working

**Solution:**
1. Check spelling: `NEXT_PUBLIC_API_URL` (exact)
2. Verify in Netlify: Site settings → Environment variables
3. Trigger new deploy (not just redeploy)

### Issue: Backend unreachable

**Solution:**
1. Test with curl: `curl https://kpsfinanciallab.w3pro.it:8001/api/v1/companies`
2. Check if backend service is running
3. Verify port 8001 is accessible
4. Check SSL certificate validity

## Build Status

✅ Frontend build: **Success** (3.5s)
✅ TypeScript: **No errors**
✅ ESLint: **Only warnings** (non-blocking)
✅ Production ready

## Documentation

- **PRODUCTION_CONFIG.md** - Production-specific configuration
- **NETLIFY_CHECKLIST.md** - Quick deployment checklist
- **README_DEPLOYMENT.md** - Comprehensive deployment guide
- **CLAUDE.md** - Updated project documentation

## Monitoring

After deployment, monitor:
- Netlify deploy logs
- Backend API logs
- Browser console for errors
- API response times

## Support

If issues arise:
1. Check `PRODUCTION_CONFIG.md` for common issues
2. Review Netlify build logs
3. Test backend directly with curl
4. Use browser DevTools → Network tab

---

**Status:** ✅ Ready for deployment
**Backend:** `https://kpsfinanciallab.w3pro.it:8001/api/v1`
**Frontend:** To be deployed on Netlify
**Last Updated:** 2026-01-22
