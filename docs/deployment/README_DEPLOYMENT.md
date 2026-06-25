# Deployment Guide - XBRL Budget Frontend

This guide explains how to deploy the Next.js frontend to Netlify.

## Prerequisites

1. A Netlify account (free tier works)
2. Git repository pushed to GitHub/GitLab/Bitbucket
3. Backend API deployed and accessible via HTTPS

## Quick Deploy to Netlify

### Option 1: Netlify UI (Recommended for First Deployment)

1. **Connect Repository**
   - Go to [Netlify](https://app.netlify.com)
   - Click "Add new site" → "Import an existing project"
   - Connect your Git provider and select the repository
   - Select the branch to deploy (e.g., `main`)

2. **Configure Build Settings**
   - Base directory: `frontend`
   - Build command: `npm run build`
   - Publish directory: (leave empty, Netlify auto-detects Next.js)

3. **Set Environment Variables**
   - Go to Site settings → Environment variables
   - Add the following variable:
     ```
     NEXT_PUBLIC_API_URL = https://your-backend-api.com/api/v1
     ```
   - Replace `https://your-backend-api.com/api/v1` with your actual backend URL

4. **Deploy**
   - Click "Deploy site"
   - Wait for build to complete (usually 2-3 minutes)
   - Your site will be live at `https://random-name.netlify.app`

### Option 2: Netlify CLI

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Login to Netlify
netlify login

# Initialize Netlify site (run from frontend directory)
cd frontend
netlify init

# Set environment variables
netlify env:set NEXT_PUBLIC_API_URL "https://your-backend-api.com/api/v1"

# Deploy
netlify deploy --prod
```

## Environment Variables

The frontend requires the following environment variable:

| Variable | Description | Example |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API base URL | `https://api.example.com/api/v1` |

**Important:**
- Must start with `NEXT_PUBLIC_` to be accessible in the browser
- Must include `/api/v1` at the end
- Must use HTTPS in production

## Configuration Files

### netlify.toml
Located at `frontend/netlify.toml`. This file configures:
- Build command and Node version
- Security headers
- Static asset caching
- Optional API proxy (commented out by default)

### .env.example
Template for environment variables. Copy to `.env.local` for local development.

## Backend Requirements

Your backend API must:
1. Be deployed and accessible via HTTPS
2. Have CORS configured to allow requests from your Netlify domain
3. Accept requests from `https://*.netlify.app` and your custom domain

### Backend CORS Configuration

In your backend (`backend/app/core/config.py`), add your Netlify URLs:

```python
BACKEND_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",  # Local development
    "https://your-site.netlify.app",  # Netlify domain
    "https://yourdomain.com",  # Custom domain (if configured)
]
```

## Deployment Workflow

1. **Local Development**
   ```bash
   cd frontend
   npm install
   npm run dev
   # Runs on http://localhost:3000
   ```

2. **Test Production Build Locally**
   ```bash
   npm run build
   npm start
   # Runs production build on http://localhost:3000
   ```

3. **Push to Git**
   ```bash
   git add .
   git commit -m "Prepare for deployment"
   git push origin main
   ```

4. **Automatic Deployment**
   - Netlify detects the push and automatically builds/deploys
   - Check build logs in Netlify dashboard
   - Site updates in ~2-3 minutes

## Custom Domain (Optional)

1. Go to Site settings → Domain management
2. Click "Add custom domain"
3. Follow instructions to configure DNS
4. Netlify provides free HTTPS via Let's Encrypt

## Troubleshooting

### Build Fails

**Check Node Version:**
- Netlify uses Node 20 (configured in `netlify.toml`)
- Locally test with Node 20: `node --version`

**Check Build Logs:**
- View detailed logs in Netlify dashboard
- Common issues: missing dependencies, TypeScript errors

### API Calls Fail

**Check NEXT_PUBLIC_API_URL:**
```bash
# In Netlify dashboard, verify environment variable
netlify env:list
```

**Check CORS:**
- Backend must allow requests from Netlify domain
- Check browser console for CORS errors
- Test API directly: `curl https://your-backend-api.com/api/v1/companies`

**Check Network Tab:**
- Open browser DevTools → Network tab
- Verify API requests are going to correct URL
- Look for 404 or 500 errors

### Environment Variable Not Working

**Remember:**
- Must start with `NEXT_PUBLIC_`
- Requires rebuild after changing
- Not accessible server-side (Next.js 15 App Router)

**Fix:**
1. Update in Netlify dashboard
2. Trigger new deploy (clear cache if needed)

## Performance Optimization

### Next.js Image Optimization

Next.js Image component works automatically on Netlify. No additional configuration needed.

### Static Asset Caching

Configured in `netlify.toml`:
- `/_next/static/*` cached for 1 year
- Automatic cache invalidation on new deploys

### Edge Functions (Optional)

For advanced features, Netlify Edge Functions can run API logic at the edge:
```bash
netlify functions:create
```

## Monitoring

### Build Status
- Netlify dashboard shows build status
- Email notifications on build failure (configurable)

### Analytics
- Enable Netlify Analytics in dashboard
- Shows page views, unique visitors, bandwidth

### Error Tracking
Consider integrating:
- Sentry for error tracking
- LogRocket for session replay
- Google Analytics for user behavior

## Rollback

If a deployment has issues:

1. **Via Netlify UI:**
   - Go to Deploys tab
   - Find previous working deploy
   - Click "Publish deploy"

2. **Via CLI:**
   ```bash
   netlify rollback
   ```

## Cost

- **Free Tier:** 100GB bandwidth, 300 build minutes/month
- **Starter Plan:** $19/month (more bandwidth, faster builds)
- Most small projects fit in free tier

## Security Checklist

- [x] HTTPS enabled (automatic with Netlify)
- [x] Security headers configured (in `netlify.toml`)
- [x] Environment variables set (not in code)
- [x] CORS properly configured on backend
- [ ] Custom domain with HTTPS (optional)
- [ ] DDoS protection enabled (Netlify Pro feature)

## Next Steps After Deployment

1. Test all features in production
2. Set up custom domain (optional)
3. Configure backend CORS for production URL
4. Enable Netlify Analytics
5. Set up monitoring/error tracking
6. Document production URLs for team

## Support

- [Netlify Documentation](https://docs.netlify.com/)
- [Next.js on Netlify](https://docs.netlify.com/frameworks/next-js/overview/)
- [Netlify Community](https://answers.netlify.com/)
