# Netlify Deployment Checklist

Use this checklist before deploying to Netlify.

## Pre-Deployment

- [ ] Backend API is deployed and accessible via HTTPS
- [ ] Backend CORS is configured to allow Netlify domain
- [ ] All features tested locally with production build (`npm run build && npm start`)
- [ ] Environment variables documented in `.env.example`
- [ ] Git repository is up to date
- [ ] No sensitive data in code (API keys, passwords, etc.)

## Netlify Configuration

- [ ] `netlify.toml` file is present in frontend directory
- [ ] Node version specified (Node 20)
- [ ] Build command configured: `npm run build`
- [ ] Base directory set to `frontend` (if in monorepo)

## Environment Variables (Set in Netlify Dashboard)

- [ ] `NEXT_PUBLIC_API_URL` = `https://kpsfinanciallab.w3pro.it:8001/api/v1`

**How to set:**
1. Netlify Dashboard → Site settings → Environment variables
2. Add variable: `NEXT_PUBLIC_API_URL`
3. Value: `https://kpsfinanciallab.w3pro.it:8001/api/v1`
4. Save and redeploy

**Note:** Backend is hosted at `https://kpsfinanciallab.w3pro.it:8001` (port 8001)

## First Deployment

- [ ] Connect Git repository to Netlify
- [ ] Configure build settings:
  - Base directory: `frontend`
  - Build command: `npm run build`
  - Publish directory: (leave empty for auto-detect)
- [ ] Set environment variables (see above)
- [ ] Trigger deployment
- [ ] Wait for build to complete (~2-3 minutes)
- [ ] Verify site is live

## Post-Deployment Testing

- [ ] Homepage loads correctly
- [ ] Navigation works (all pages accessible)
- [ ] API connection works (check browser console for errors)
- [ ] Company list loads (test `/` page)
- [ ] Import feature works (test `/import` page)
- [ ] Financial analysis displays (test `/analysis` page)
- [ ] No console errors in browser DevTools

## Backend CORS Update

After getting Netlify URL, update backend CORS on the server:

1. SSH into your server: `kpsfinanciallab.w3pro.it`
2. Edit backend config: `backend/app/core/config.py`
3. Add your Netlify URL to `BACKEND_CORS_ORIGINS`:

```python
BACKEND_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "https://*.netlify.app",  # Wildcard for Netlify
    "https://your-actual-site.netlify.app",  # Your specific URL
]
```

4. Restart backend service:
```bash
cd backend
source venv/bin/activate
# Kill existing process and restart
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**Backend URL:** `https://kpsfinanciallab.w3pro.it:8001/api/v1`

## Optional: Custom Domain

- [ ] Purchase domain (e.g., from Namecheap, Google Domains)
- [ ] Add custom domain in Netlify (Site settings → Domain management)
- [ ] Configure DNS records (Netlify provides instructions)
- [ ] Wait for DNS propagation (~5 minutes to 48 hours)
- [ ] Verify HTTPS certificate is active (automatic via Let's Encrypt)
- [ ] Update backend CORS to include custom domain

## Continuous Deployment

Once configured, future deployments are automatic:

1. Make changes locally
2. Commit and push to Git: `git push origin main`
3. Netlify detects push and rebuilds automatically
4. Site updates in ~2-3 minutes

## Troubleshooting

### Build Fails
- Check build logs in Netlify dashboard
- Verify Node version compatibility
- Test local build: `npm run build`

### API Not Working
- Check `NEXT_PUBLIC_API_URL` is set correctly
- Check backend CORS allows Netlify domain
- Check browser console for errors
- Test API directly: `curl https://your-backend-api.com/api/v1/companies`

### Environment Variable Not Applied
- Redeploy after changing environment variables
- Clear cache and retry deploy
- Verify variable name starts with `NEXT_PUBLIC_`

## Quick Commands

```bash
# Test production build locally
npm run build
npm start

# Check environment variables
netlify env:list

# Deploy manually
netlify deploy --prod

# View deploy logs
netlify logs

# Rollback to previous deploy
netlify rollback
```

## Support Resources

- [Netlify Docs](https://docs.netlify.com/)
- [Next.js on Netlify](https://docs.netlify.com/frameworks/next-js/overview/)
- [Deployment Guide](./README_DEPLOYMENT.md)

---

**Last Updated:** 2026-01-22

**Deployment Status:** ⏳ Ready for deployment
