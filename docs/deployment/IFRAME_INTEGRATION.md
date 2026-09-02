# Embedding XBRL Budget in Formula Finance (iframe + JWT)

## Overview

The XBRL Budget app runs as a Docker container (nginx + backend + frontend on port 80) and is embedded as an iframe inside Formula Finance. Authentication flows via `postMessage`: the parent sends the Supabase JWT to the iframe, and the budget backend validates it using the same Supabase JWT secret.

```
┌─────────────────────────────────────────────────────┐
│  Formula Finance (parent)                           │
│  https://app.formulafinance.it                      │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  XBRL Budget (iframe)                         │  │
│  │  https://budget.formulafinance.it             │  │
│  │                                               │  │
│  │  1. Sends REQUEST_AUTH_TOKEN on load          │  │
│  │  2. Receives AUTH_TOKEN from parent           │  │
│  │  3. Uses JWT for all API calls                │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Step 1: Deploy Budget App (Docker)

The budget app runs as a single Docker Compose stack behind nginx on port 80.

```bash
cd /home/peter/DEV/budget

# Production: set real Supabase JWT secret + allowed origins
SUPABASE_JWT_SECRET=your-supabase-jwt-secret \
ALLOWED_ORIGINS=https://app.formulafinance.it \
docker compose up -d
```

**Environment variables for `docker-compose.yml`:**

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_JWT_SECRET` | Yes (prod) | Supabase project JWT secret (HS256). Find it in Supabase Dashboard → Settings → API → JWT Secret |
| `ALLOWED_ORIGINS` | Yes (prod) | Formula Finance origin for CORS (e.g. `https://app.formulafinance.it`) |
| `DEV_USER_ID` | No | Set only for local dev to bypass JWT (e.g. `dev-user-001`) |
| `ANTHROPIC_API_KEY` | No | For AI comment generation feature |
| `MAX_COMPANIES_PER_USER` | No | Default: 50 |

**Important:** The `SUPABASE_JWT_SECRET` must match the one from the same Supabase project that Formula Finance uses. Both apps must share the same Supabase project so that user IDs (`sub` claim) are consistent.

---

## Step 2: Add iframe Page in Formula Finance

Create a new page in Formula Finance that embeds the budget app.

### Option A: Dedicated page (recommended)

Create `app/budget/page.tsx`:

```tsx
"use client"

import { useEffect, useRef, useCallback } from "react"
import { createBrowserClient } from "@supabase/ssr"
import { AuthGuard } from "@/components/auth-guard"

const BUDGET_APP_URL = process.env.NEXT_PUBLIC_BUDGET_URL || "https://budget.formulafinance.it"

const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

function BudgetPage() {
  const iframeRef = useRef<HTMLIFrameElement>(null)

  const sendToken = useCallback(async () => {
    const { data: { session } } = await supabase.auth.getSession()
    if (session?.access_token && iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        { type: "AUTH_TOKEN", token: session.access_token },
        BUDGET_APP_URL
      )
    }
  }, [])

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Security: only accept messages from budget app origin
      if (event.origin !== BUDGET_APP_URL) return

      if (event.data?.type === "REQUEST_AUTH_TOKEN") {
        sendToken()
      }
    }

    window.addEventListener("message", handleMessage)
    return () => window.removeEventListener("message", handleMessage)
  }, [sendToken])

  // Also send token on auth state change (token refresh)
  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        if (session?.access_token && iframeRef.current?.contentWindow) {
          iframeRef.current.contentWindow.postMessage(
            { type: "AUTH_TOKEN", token: session.access_token },
            BUDGET_APP_URL
          )
        }
        if (!session) {
          iframeRef.current?.contentWindow?.postMessage(
            { type: "AUTH_LOGOUT" },
            BUDGET_APP_URL
          )
        }
      }
    )
    return () => subscription.unsubscribe()
  }, [])

  return (
    <div className="h-[calc(100vh-4rem)] w-full">
      <iframe
        ref={iframeRef}
        src={BUDGET_APP_URL}
        className="w-full h-full border-0"
        title="XBRL Budget"
        allow="fullscreen"
      />
    </div>
  )
}

export default function BudgetPageWrapper() {
  return (
    <AuthGuard>
      <BudgetPage />
    </AuthGuard>
  )
}
```

### Option B: Embed in reports page

If you want budget as a section within an existing page, use the same iframe + postMessage pattern but embedded in the relevant component.

---

## Step 3: Add Environment Variable

Add to Formula Finance's `.env.local`:

```bash
# Budget app URL (Docker container)
NEXT_PUBLIC_BUDGET_URL=https://budget.formulafinance.it
```

For local development:
```bash
NEXT_PUBLIC_BUDGET_URL=http://localhost:80
```

---

## Step 4: Add Navigation Link

Add "Budget" to the sidebar navigation in Formula Finance.

In `components/app-sidebar.tsx` (or wherever nav items are defined), add:

```tsx
{
  title: "Budget",
  url: "/budget",
  icon: Calculator, // from lucide-react
}
```

---

## Step 5: Configure CORS on Budget Backend

The budget backend already supports `ALLOWED_ORIGINS`. In production, set it to the Formula Finance domain:

```bash
# docker-compose.yml already passes this through
ALLOWED_ORIGINS=https://app.formulafinance.it
```

This is handled in `backend/app/main.py` CORS middleware.

---

## PostMessage Protocol Reference

The budget app's `AuthContext.tsx` implements this protocol:

### Messages: Parent → Child (iframe)

| Message | When to send | Payload |
|---------|-------------|---------|
| `AUTH_TOKEN` | On `REQUEST_AUTH_TOKEN` + on token refresh | `{ type: "AUTH_TOKEN", token: "eyJ..." }` |
| `AUTH_LOGOUT` | On user logout | `{ type: "AUTH_LOGOUT" }` |

### Messages: Child (iframe) → Parent

| Message | When sent | Payload |
|---------|----------|---------|
| `REQUEST_AUTH_TOKEN` | On iframe load + on 401 API response | `{ type: "REQUEST_AUTH_TOKEN" }` |

### Flow

```
1. User navigates to /budget in Formula Finance
2. iframe loads budget app
3. Budget AuthContext detects it's in iframe (window.parent !== window)
4. Budget sends: parent.postMessage({ type: "REQUEST_AUTH_TOKEN" })
5. Formula Finance receives message, calls supabase.auth.getSession()
6. Formula Finance sends: iframe.postMessage({ type: "AUTH_TOKEN", token: jwt })
7. Budget AuthContext stores token, syncs to API client
8. All budget API calls now include: Authorization: Bearer <jwt>
9. Budget backend validates JWT with same SUPABASE_JWT_SECRET
10. user_id extracted from JWT "sub" claim → all data scoped per user
```

### Token Refresh

When a budget API call returns 401 (token expired):
1. Budget API client sends `REQUEST_AUTH_TOKEN` to parent
2. Parent fetches fresh session from Supabase (auto-refreshed)
3. Parent sends new `AUTH_TOKEN`
4. User retries their action (no manual refresh needed)

**Every rejected token comes out as 401**, never 500, because step 1 is what triggers the
refresh — a truncated, unsigned, wrongly-signed, expired or `sub`-less token, and also a
well-formed token sent to a dev backend that has `DEV_USER_ID` but no `SUPABASE_JWT_SECRET`
(there the token simply cannot be verified, and the dev fallback does **not** rescue it).
The one case that stays **500** is a server with neither secret nor `DEV_USER_ID`: that is a
deployment error, and a 401 would send the parent into refreshing a token this server can
never accept. Pinned by `tests/test_auth_jwt.py`.

### Testing auth with a real token

A backend started with `DEV_USER_ID` alone cannot verify anything, so **a perfectly valid
Supabase token gets 401 there too**. To exercise the real path, start it with the secret —
keeping `DEV_USER_ID` as well is the useful local combination, because then an
un-authenticated call still falls back to the dev tenant:

```bash
# .env.staging already carries the secret of the Formula Finance Supabase project
cd backend && source venv/bin/activate
env DEV_USER_ID=dev-user-001 SUPABASE_JWT_SECRET="$(grep -m1 '^SUPABASE_JWT_SECRET=' ../.env.staging | cut -d= -f2-)" \
  uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Get a token with `scripts/get_test_jwt.py`. It logs in through the FastAPI backend —
`POST /api/v1/users/token` on `api_server_it`, an OAuth2 password form that forwards to
`supabase.auth.sign_in_with_password` — so it needs no Supabase anon key, and the token comes
back by the same route the iframe gets it. The script holds no credentials of its own; put
them in a `.env*.local` file, a pattern `.gitignore` covers at any depth, because **test
credentials must never be committed**:

```bash
# .env.test.local  (gitignored)
export API_BASE_URL="https://api.kpsfinanciallab.it"   # facoltativa, e' il default
export TEST_USER_EMAIL="..."
export TEST_USER_PASSWORD="..."
```

```bash
source .env.test.local
TOKEN=$(python scripts/get_test_jwt.py)
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/companies
```

The two `@live_only` tests at the end of `tests/test_auth_jwt.py` do exactly this and **skip**
when those variables are absent, so the suite stays runnable without secrets or network. They
pin what a hand-signed token cannot: that the real token shape — HS256, `aud: "authenticated"`,
uuid `sub` — passes. That `aud` is why `jwt.decode` runs with `verify_aud: False`; checking the
audience would reject every production token.

The response is scoped to the token's `sub`, so a real token and the `DEV_USER_ID` fallback see
**different companies** on the same server — that is the multi-tenancy working, not a bug.

---

## Security Checklist

- [ ] **Same Supabase project**: Budget backend uses the same `SUPABASE_JWT_SECRET` as Formula Finance
- [ ] **Origin validation**: Parent checks `event.origin === BUDGET_APP_URL` before handling messages
- [ ] **CORS**: Budget backend `ALLOWED_ORIGINS` set to Formula Finance domain
- [ ] **HTTPS**: Both apps served over HTTPS in production
- [ ] **No DEV_USER_ID in production**: Remove `DEV_USER_ID` env var in production deployment
- [ ] **postMessage target**: Use specific origin (not `"*"`) when sending tokens

---

## Local Development Setup

Run both apps locally:

```bash
# Terminal 1: Budget app (Docker)
cd /home/peter/DEV/budget
DEV_USER_ID=dev-user-001 docker compose up -d
# Budget available at http://localhost:80

# Terminal 2: Formula Finance
cd /home/peter/DEV/formulafinance
# Add to .env.local: NEXT_PUBLIC_BUDGET_URL=http://localhost:80
npm run dev
# Formula Finance at http://localhost:3000
# Navigate to http://localhost:3000/budget
```

**Note:** In dev mode with `DEV_USER_ID`, the budget app's auth timeout (1s) kicks in and allows unauthenticated access, so the iframe works even without the postMessage flow. For testing the full auth flow locally, remove `DEV_USER_ID` and set `SUPABASE_JWT_SECRET` on the budget container.

---

## DNS / Reverse Proxy (Production)

In production, the budget Docker container needs to be reachable at a URL. Two common setups:

### Subdomain (recommended)
- `budget.formulafinance.it` → points to the server running Docker
- nginx on port 80 inside Docker handles routing
- Add SSL via Cloudflare, Traefik, or a host-level nginx with Let's Encrypt

### Path-based (alternative)
- `app.formulafinance.it/budget/` → reverse proxy to Docker port 80
- Requires setting `basePath: '/budget'` in Next.js config inside the budget app
- More complex, subdomain approach is simpler
