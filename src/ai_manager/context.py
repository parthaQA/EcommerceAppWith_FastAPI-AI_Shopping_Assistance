from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession


class MyRuntimeContext(TypedDict):
    db: AsyncSession
    user_id: str
