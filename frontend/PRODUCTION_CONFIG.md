# Production Configuration

## Backend URL

The production backend is hosted at:
```
https://kpsfinanciallab.w3pro.it:8001
```

API Base URL (with /api/v1):
```
https://kpsfinanciallab.w3pro.it:8001/api/v1
```

## Frontend Environment Variable

When deploying to Netlify, set this environment variable:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | `https://kpsfinanciallab.w3pro.it:8001/api/v1` |

### How to Set in Netlify

1. Go to your site in Netlify Dashboard
2. Navigate to: **Site settings** → **Environment variables**
3. Click **Add a variable**
4. Enter:
   - **Key:** `NEXT_PUBLIC_API_URL`
   - **Value:** `https://kpsfinanciallab.w3pro.it:8001/api/v1`
5. Click **Create variable**
6. Trigger a new deploy to apply changes

## Backend CORS Configuration

After deploying the frontend to Netlify, you'll get a URL like:
- `https://your-site-name.netlify.app`

**You must add this URL to the backend CORS configuration:**

1. Open `backend/app/core/config.py`
2. Update `BACKEND_CORS_ORIGINS` to include your Netlify URL:

```python
BACKEND_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",  # Local development
    "https://*.netlify.app",  # Netlify (wildcard)
    "https://your-actual-site.netlify.app",  # Your specific Netlify URL
]
```

3. Restart the backend service:
```bash
cd backend
source venv/bin/activate
# Kill existing uvicorn process
# Restart:
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

## SSL/HTTPS Considerations

The backend uses HTTPS with a custom port (8001). Ensure:

1. ✅ SSL certificate is valid for `kpsfinanciallab.w3pro.it`
2. ✅ Port 8001 is open and accessible from the internet
3. ✅ Firewall allows HTTPS traffic on port 8001
4. ✅ CORS is configured to allow requests from Netlify

## Testing Backend Connection

### From Command Line
```bash
# Test if backend is accessible
curl https://kpsfinanciallab.w3pro.it:8001/api/v1/companies

# Expected response: JSON array of companies or []
```

### From Browser Console (after deployment)
```javascript
// Open your Netlify site
// Open browser DevTools → Console
fetch('https://kpsfinanciallab.w3pro.it:8001/api/v1/companies')
  .then(r => r.json())
  .then(console.log)
  .catch(console.error)

// Should return companies array or CORS error if not configured
```

## Common Issues & Solutions

### Issue: CORS Error in Browser

**Symptom:**
```
Access to fetch at 'https://kpsfinanciallab.w3pro.it:8001/api/v1/companies'
from origin 'https://your-site.netlify.app' has been blocked by CORS policy
```

**Solution:**
Add your Netlify domain to backend CORS (see above)

### Issue: SSL Certificate Error

**Symptom:**
```
NET::ERR_CERT_AUTHORITY_INVALID
```

**Solution:**
- Ensure SSL certificate is valid for `kpsfinanciallab.w3pro.it`
- Check certificate expiration date
- Verify certificate chain is complete

### Issue: Connection Timeout

**Symptom:**
```
Failed to fetch
TypeError: NetworkError when attempting to fetch resource
```

**Solution:**
- Check if port 8001 is accessible from internet
- Verify firewall rules
- Test with curl from different network

### Issue: 502 Bad Gateway

**Symptom:**
```
502 Bad Gateway
```

**Solution:**
- Backend service may be down
- Check backend logs: `journalctl -u your-backend-service`
- Restart backend service

## Production Deployment Checklist

- [ ] Backend is running on `https://kpsfinanciallab.w3pro.it:8001`
- [ ] Backend API responds to `/api/v1/companies` (test with curl)
- [ ] SSL certificate is valid
- [ ] Port 8001 is accessible from internet
- [ ] Frontend is deployed to Netlify
- [ ] `NEXT_PUBLIC_API_URL` is set in Netlify environment variables
- [ ] Netlify domain is added to backend CORS
- [ ] Backend service restarted after CORS update
- [ ] Test API calls from frontend work (no CORS errors)
- [ ] All features tested in production

## Monitoring

### Backend Health Check
```bash
# Check if backend is responsive
curl -f https://kpsfinanciallab.w3pro.it:8001/api/v1/companies || echo "Backend down"
```

### Frontend Health Check
```bash
# Check if frontend is accessible
curl -f https://your-site.netlify.app || echo "Frontend down"
```

## Support

If you encounter issues:

1. Check backend logs on your server
2. Check Netlify deploy logs in dashboard
3. Use browser DevTools → Network tab to inspect requests
4. Verify environment variables are set correctly

---

**Last Updated:** 2026-01-22
**Backend URL:** https://kpsfinanciallab.w3pro.it:8001/api/v1
**Frontend:** To be deployed on Netlify
