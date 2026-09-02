"""
JWT Authentication for Supabase tokens (postMessage from parent iframe).
Dev mode bypass via DEV_USER_ID environment variable.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import NamedTuple, Optional
import jwt

from app.core.config import settings

# Optional bearer token - allows requests without Authorization header in dev mode
security = HTTPBearer(auto_error=False)


class CurrentUser(NamedTuple):
    id: str
    email: Optional[str]


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> CurrentUser:
    """
    Extract user id (+ email when available) from Supabase JWT or dev fallback.

    Priority:
    1. Authorization header present → validate JWT, extract sub + email claims
    2. No header + DEV_USER_ID set → return DEV_USER_ID (dev mode)
    3. Otherwise → 401 Unauthorized
    """
    # Case 1: JWT token provided
    if credentials and credentials.credentials:
        token = credentials.credentials

        if not settings.SUPABASE_JWT_SECRET:
            # Il token non è verificabile. Con DEV_USER_ID impostato non è una
            # configurazione sbagliata: è il normale avvio in sviluppo, e un
            # token che non si può controllare non vale più di nessun token —
            # 401, che è lo stato su cui il frontend ri-chiede il token al
            # parent dell'iframe (`frontend/lib/api.ts`). Il fallback
            # DEV_USER_ID non lo riscatta: varrebbe qualunque stringa, e un
            # token davvero rotto non si vedrebbe mai. Senza DEV_USER_ID,
            # invece, è il server a essere configurato male e resta un 500: un
            # 401 manderebbe l'iframe a ri-chiedere all'infinito un token che
            # questo server non potrà mai accettare.
            if settings.DEV_USER_ID:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token cannot be verified: SUPABASE_JWT_SECRET not configured",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SUPABASE_JWT_SECRET not configured",
            )

        try:
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing 'sub' claim",
                headers={"WWW-Authenticate": "Bearer"},
            )

        email = payload.get("email") or (payload.get("user_metadata") or {}).get("email")
        return CurrentUser(id=user_id, email=email)

    # Case 2: Dev mode fallback
    if settings.DEV_USER_ID:
        return CurrentUser(id=settings.DEV_USER_ID, email=None)

    # Case 3: No auth
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user_id(user: CurrentUser = Depends(get_current_user)) -> str:
    """Backwards-compatible shim — most routes only need the user id."""
    return user.id
