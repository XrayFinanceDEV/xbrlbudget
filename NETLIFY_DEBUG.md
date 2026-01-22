# Netlify Path Resolution Debug

## Issue
Netlify build fails with: `Module not found: Can't resolve '@/lib/api'`

## Files Added/Updated

### 1. frontend/tsconfig.json
```json
{
  "compilerOptions": {
    "baseUrl": ".",  // ← Added this
    "paths": {
      "@/*": ["./*"]
    }
  }
}
```

### 2. frontend/jsconfig.json (NEW)
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./*"]
    }
  }
}
```

### 3. frontend/next.config.ts (UPDATED)
```typescript
webpack: (config) => {
  config.resolve.alias = {
    ...config.resolve.alias,
    '@': path.resolve(__dirname, '.'),
  };
  return config;
}
```

## If Build Still Fails

### Option 1: Clear Netlify Deploy Cache

1. Go to Netlify Dashboard
2. Site settings → Build & deploy → Build settings
3. Scroll to "Build image selection"
4. Click "Clear cache and retry deploy"

### Option 2: Trigger Clean Deploy

In Netlify Dashboard:
- Deploys → Trigger deploy → **Clear cache and deploy site**

### Option 3: Check Environment

Verify in Netlify build logs that:
```
✓ Node version: 20
✓ Build directory: /opt/build/repo/frontend
✓ Files exist: lib/api.ts, lib/formatters.ts
```

### Option 4: Manual Verification

Check what Netlify sees:
```bash
# In build logs, look for:
ls -la lib/
# Should show: api.ts, formatters.ts
```

## Commits Applied

1. `8952701` - Added jsconfig.json and webpack alias
2. `[latest]` - Added baseUrl to tsconfig.json

## Next Steps if This Doesn't Work

If path resolution still fails, we may need to:
1. Convert all `@/lib/*` imports to relative imports (`../lib/*`)
2. Or use a custom webpack configuration plugin
3. Or check if there's a file system case-sensitivity issue

## Local Build Status
✓ Works perfectly with current configuration
