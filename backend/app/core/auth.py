"""
JWT Authentication for Supabase tokens (postMessage from parent iframe).
Dev mode bypass via DEV_USER_ID environment variable.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import jwt

from app.core.config import settings

# Optional bearer token - allows requests without Authorization header in dev mode
security = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """
    Extract user_id from Supabase JWT or dev fallback.

    Priority:
    1. Authorization header present → validate JWT, extract sub claim
    2. No header + DEV_USER_ID set → return DEV_USER_ID (dev mode)
    3. Otherwise → 401 Unauthorized
    """
    # Case 1: JWT token provided
    if credentials and credentials.credentials:
        token = credentials.credentials

        if not settings.SUPABASE_JWT_SECRET:
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

        return user_id

    # Case 2: Dev mode fallback
    if settings.DEV_USER_ID:
        return settings.DEV_USER_ID

    # Case 3: No auth
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
