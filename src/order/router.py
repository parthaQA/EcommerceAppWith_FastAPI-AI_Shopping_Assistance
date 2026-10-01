from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.order.controller import OrderController
from src.order.dtos import OrderSchema
from src.utils.auth import AuthUser, get_current_user
from src.utils.db import get_db

order_routes = APIRouter(
    prefix="/order",
    dependencies=[Depends(get_current_user)],
)


@order_routes.post(
    path="/create",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new order",
)
async def create_order(
    body: OrderSchema,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OrderController.create_order(user, body, db)


@order_routes.get(
    path="/order-details",
    status_code=status.HTTP_200_OK,
    summary="Get order details by order id",
)
async def get_order_details_by_order_id(
    order_id: Annotated[str, Query(...)],
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OrderController.get_order_details_by_order_id(
        user,
        order_id,
        db,
    )


@order_routes.get(
    path="/all",
    status_code=status.HTTP_200_OK,
    summary="Get all order details by customer",
)
async def get_all_order_details_by_customer(
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OrderController.get_all_order_details_by_customer(user, db)
