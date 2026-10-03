from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.customer_service import CustomerService
from src.customers.dtos import (
    CustomerLoginSchema,
    CustomerRegisterSchema,
    CustomerSchema,
    SavedAddressSchema,
)
from src.utils.auth import AuthUser


class CustomerController:

    async def create_customer(self, body: CustomerSchema, db: AsyncSession):
        return await CustomerService.create(body, db)

    async def get_all_customers(self, db: AsyncSession):
        return await CustomerService.get_all(db)

    async def get_customer_by_id(self, customer_id: str, db: AsyncSession):
        return await CustomerService.get_by_id(customer_id, db)

    async def register_customer(self, body: CustomerRegisterSchema, db: AsyncSession):
        return await CustomerService.register(body, db)

    async def save_address(
        self,
        user: AuthUser,
        body: SavedAddressSchema,
        db: AsyncSession,
    ):
        saved_address = await CustomerService.save_address(
            user.customer_id,
            body,
            db,
        )
        return {
            "success": True,
            "data": saved_address,
            "message": "Address saved successfully",
        }

    async def customer_login(
        self,
        body: CustomerLoginSchema,
        db: AsyncSession,
        request: Request,
    ):
        return await CustomerService.login(body, db, request)

    async def customer_login_internal(
        self,
        body: CustomerLoginSchema,
        db: AsyncSession,
    ):
        return await CustomerService.login_internal(body, db)

    @staticmethod
    async def is_authenticated(request: Request):
        return await CustomerService.is_authenticated(request)
