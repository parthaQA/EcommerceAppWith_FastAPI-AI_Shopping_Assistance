"""JWT-based authentication dependency for FastAPI routes."""

from typing import Final

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.utils.settings import settings

_bearer = HTTPBearer(auto_error=True)
_ALLOWED_ALGORITHMS: Final[set[str]] = {"HS256", "HS512"}


class AuthUser(BaseModel):
    """Represents the authenticated customer for the current request."""

    customer_id: str
    mobile: int | None = None


def decode_access_token(token: str) -> dict:
    """Verify a JWT's signature and expiry, and return its claims.

    Raises:
        HTTPException: 500 if the configured algorithm isn't allow-listed,
            401 if the token is expired or otherwise invalid.
    """
    algorithm = settings.ALGORITHM
    if algorithm not in _ALLOWED_ALGORITHMS:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid JWT algorithm configuration",
        )

    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[algorithm],
            options={"require": ["exp", "customer_id"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc


def _extract_mobile(payload: dict) -> int | None:
    """Best-effort parse of the optional `mobile` claim.

    A malformed or missing value degrades to `None` rather than failing
    the whole auth flow, since mobile is not required for identity.
    """
    mobile = payload.get("mobile")
    if mobile is None:
        return None
    try:
        return int(mobile)
    except (TypeError, ValueError):
        return None


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> AuthUser:
    """Resolve the authenticated customer from the request's bearer token.

    Also cross-checks an optional `customer_id` header against the token's
    claim, as a defense-in-depth measure against spoofed headers.
    """
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization scheme",
        )

    payload = decode_access_token(credentials.credentials)

    customer_id = str(payload.get("customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    header_customer_id = request.headers.get("customer_id")
    if header_customer_id and header_customer_id.strip() != customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer ID and token mismatch",
        )

    return AuthUser(
        customer_id=customer_id,
        mobile=_extract_mobile(payload),
    )