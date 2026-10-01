import asyncio
import hashlib
import secrets
import uuid

import bcrypt
from fastapi import HTTPException, Request

from src.utils.redis import redis_client
from src.utils.settings import settings


class Helper:

    @staticmethod
    def generate_customer_id():
        return uuid.uuid4().hex[:10].upper()

    @staticmethod
    def generate_hashed_password(password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(),
        ).decode("utf-8")

    @staticmethod
    async def hash_password(password: str) -> str:
        return await asyncio.to_thread(Helper.generate_hashed_password, password)

    @staticmethod
    async def check_password(password: str, hashed_password: str) -> bool:
        return await asyncio.to_thread(
            Helper.verify_password,
            password,
            hashed_password,
        )

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        if not hashed_password:
            return False

        # bcrypt hashes
        if hashed_password.startswith("$2"):
            try:
                return bcrypt.checkpw(
                    password.encode("utf-8"),
                    hashed_password.encode("utf-8"),
                )
            except ValueError:
                return False

        # Legacy unsalted SHA-512 (migrate on next successful login)
        legacy = hashlib.sha512(password.encode("utf-8")).hexdigest()
        return secrets_compare(legacy, hashed_password)

    @staticmethod
    def needs_rehash(hashed_password: str) -> bool:
        return not hashed_password.startswith("$2")

    @staticmethod
    def generate_cart_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    async def check_rate_limit(request: Request, mobile: str | int):
        ip = request.client.host if request.client else "unknown"
        key = f"login:{mobile}:{ip}"
        count = await redis_client.get(key)

        if count and int(count) >= settings.LOGIN_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Too many login attempts. Try again after "
                    f"{settings.LOGIN_LOCKOUT_MINUTES} minutes."
                ),
            )

    @staticmethod
    async def increment_login_attempt(request: Request, mobile: str | int):
        ip = request.client.host if request.client else "unknown"
        key = f"login:{mobile}:{ip}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(
                key,
                settings.LOGIN_LOCKOUT_MINUTES * 60,
            )

    @staticmethod
    async def clear_login_attempt(request: Request, mobile: str | int):
        ip = request.client.host if request.client else "unknown"
        key = f"login:{mobile}:{ip}"
        await redis_client.delete(key)

    @staticmethod
    def generate_refresh_token() -> str:
        """Opaque random string — not a JWT, just a lookup key stored in the DB."""
        return secrets.token_urlsafe(64)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode()).hexdigest()


def secrets_compare(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode(), b.encode()):
        result |= x ^ y
    return result == 0
