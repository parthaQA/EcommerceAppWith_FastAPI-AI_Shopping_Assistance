from typing import List

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.controller import CustomerController
from src.customers.dtos import (
    CustomerLoginSchema,
    CustomerRegisterSchema,
    CustomerRegistrationResponseSchema,
    CustomerResponseSchema,
    CustomerSchema,
    SavedAddressSchema,
)
from src.utils.auth import AuthUser, get_current_user
from src.utils.db import get_db

customer_routes = APIRouter(prefix="/customers")

@customer_routes.post(
    path="/create",
    response_model=CustomerResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer",
)
async def create_customer(
    body: CustomerSchema,
    db: AsyncSession = Depends(get_db),
):
    return await CustomerController().create_customer(body, db)

@customer_routes.get(
    path="/all",
    response_model=List[CustomerResponseSchema],
    status_code=status.HTTP_200_OK,
    summary="Get all customers",
)
async def get_all_customers(
    db: AsyncSession = Depends(get_db),
):
    return await CustomerController().get_all_customers(db)

@customer_routes.get(
    path="/is_auth",
    status_code=status.HTTP_200_OK,
    summary="authenticate a customer",
)
async def is_authenticated(request: Request):
    return await CustomerController().is_authenticated(request)

@customer_routes.post(
    path="/address/add",
    status_code=status.HTTP_200_OK,
    summary="Save an address for future use",
)
async def save_address(
    body: SavedAddressSchema,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await CustomerController().save_address(user, body, db)

@customer_routes.get(
    path="/{customer_id}",
    response_model=CustomerResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Get customer by id",
)
async def get_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await CustomerController().get_customer_by_id(
        customer_id=customer_id,
        db=db,
    )


@customer_routes.post(
    path="/register",
    response_model=CustomerRegistrationResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Register a new customer",
)
async def register_customer(
    body: CustomerRegisterSchema,
    db: AsyncSession = Depends(get_db),
):
    return await CustomerController().register_customer(body, db)


@customer_routes.post(
    path="/login",
    status_code=status.HTTP_200_OK,
    summary="Login a customer",
)
async def customer_login(
    request: Request,
    body: CustomerLoginSchema,
    db: AsyncSession = Depends(get_db),
):
    return await CustomerController().customer_login(body, db, request)
