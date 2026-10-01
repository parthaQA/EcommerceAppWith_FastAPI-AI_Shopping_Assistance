from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.cart.controller import CartController
from src.cart.dtos import (
    CartItemSchema,
    DeliveryAddressSchema,
    PaymentPreferenceSchema,
)
from src.utils.auth import AuthUser, get_current_user
from src.utils.db import get_db

cart_routes = APIRouter(
    prefix="/cart",
    dependencies=[Depends(get_current_user)],
)


@cart_routes.get(
    path="/get",
    status_code=status.HTTP_200_OK,
    summary="Get a new cart",
)
async def get_cart(
    location: Annotated[str, Query(...)],
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CartController.get_cart(user, location, db)


@cart_routes.post(
    path="/{cart_id}/products/add",
    status_code=status.HTTP_201_CREATED,
    summary="Add a product to the cart",
)
async def add_product_to_cart(
    cart_id: str,
    body: CartItemSchema,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CartController.add_product_to_cart(user, cart_id, body, db)


@cart_routes.post(
    path="/{cart_id}/products/reset",
    status_code=status.HTTP_200_OK,
    summary="Reset products from the cart",
)
async def reset_cart(
    cart_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CartController.reset_cart(user, cart_id, db)


@cart_routes.post(
    path="/{cart_id}/delivery/add-address",
    status_code=status.HTTP_200_OK,
    summary="add deilvery address from the cart",
)
async def add_delivery_address(
    cart_id: str,
    body: DeliveryAddressSchema,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CartController.add_delivery_address(user, cart_id, body, db)


@cart_routes.post(
    path="/{cart_id}/payment/add-preference",
    status_code=status.HTTP_200_OK,
    summary="add payment preference to the cart",
)
async def add_payment_preference(
    cart_id: str,
    body: PaymentPreferenceSchema,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CartController.add_payment_preference(user, cart_id, body, db)
