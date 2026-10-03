from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.customers.dtos import (
    CustomerLoginSchema,
    CustomerRegisterSchema,
    CustomerSchema,
    SavedAddressSchema,
)
from src.customers.models import (
    CustomerModel,
    CustomerRegistrationModel,
    RefreshTokenModel,
    SavedAddressModel,
)
from src.utils.helper import Helper
from src.utils.settings import settings


class CustomerService:

    @staticmethod
    async def create(body: CustomerSchema, db: AsyncSession) -> CustomerModel:
        existing = await db.scalar(
            select(CustomerModel).where(CustomerModel.mobile == body.mobile)
        )
        if existing is not None:
            raise HTTPException(
                status_code=400,
                detail="Customer with this mobile number already exists",
            )

        customer = CustomerModel(
            name=body.name,
            email=body.email,
            gender=body.gender,
            address=body.address,
            mobile=body.mobile,
            pincode=body.pincode,
            is_active=False,
        )
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
        return customer

    @staticmethod
    async def get_all(db: AsyncSession) -> list[CustomerModel]:
        rows = await db.scalars(select(CustomerModel))
        return list(rows.all())

    @staticmethod
    async def get_by_id(customer_id: str, db: AsyncSession) -> CustomerModel:
        customer = await db.get(CustomerModel, customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    @staticmethod
    async def register(
        body: CustomerRegisterSchema,
        db: AsyncSession,
    ) -> CustomerRegistrationModel:
        customer = await db.scalar(
            select(CustomerModel).where(CustomerModel.mobile == body.mobile)
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")

        existing = await db.scalar(
            select(CustomerRegistrationModel).where(
                CustomerRegistrationModel.mobile == body.mobile
            )
        )
        if existing is not None:
            raise HTTPException(status_code=400, detail="number already exist")

        registration = CustomerRegistrationModel(
            mobile=body.mobile,
            password=await Helper.hash_password(body.password),
        )
        db.add(registration)
        await db.commit()
        await db.refresh(registration)
        return registration

    @staticmethod
    async def save_address(
        customer_id: str,
        body: SavedAddressSchema,
        db: AsyncSession,
    ) -> SavedAddressModel:
        customer = await db.get(CustomerModel, customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")

        if not (560001 <= body.pincode <= 560114):
            raise HTTPException(
                status_code=400,
                detail="Delivery is available only for pincodes between 560001 and 560114",
            )

        saved_address = SavedAddressModel(
            customer_id=customer_id,
            address=body.address,
            pincode=body.pincode,
            city=body.city,
        )
        db.add(saved_address)
        await db.commit()
        await db.refresh(saved_address)
        return saved_address

    @staticmethod
    async def login_internal(
        body: CustomerLoginSchema,
        db: AsyncSession,
    ) -> dict:
        customer = await db.scalar(
            select(CustomerModel).where(CustomerModel.mobile == body.mobile)
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")

        registration = await db.scalar(
            select(CustomerRegistrationModel).where(
                CustomerRegistrationModel.mobile == body.mobile
            )
        )
        if registration is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        if not await Helper.check_password(body.password, registration.password):
            raise HTTPException(status_code=401, detail="Wrong password")

        exp_time = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_minutes
        )
        access_token = jwt.encode(
            {
                "customer_id": customer.id,
                "mobile": registration.mobile,
                "exp": exp_time,
                "type": "access",
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )

        raw_refresh_token = Helper.generate_refresh_token()
        refresh_expires_at = datetime.utcnow() + timedelta(
            days=settings.REFRESH_TOKEN_EXP_DAYS
        )
        db.add(
            RefreshTokenModel(
                mobile=str(registration.mobile),
                token=Helper.hash_token(raw_refresh_token),
                expires_at=refresh_expires_at,
            )
        )
        await db.commit()

        return {
            "customer_id": customer.id,
            "mobile": registration.mobile,
            "access_token": access_token,
            "refresh_token": raw_refresh_token,
            "token_type": "bearer",
        }

    @staticmethod
    async def login(
        body: CustomerLoginSchema,
        db: AsyncSession,
        request: Request,
    ) -> dict:
        await Helper.check_rate_limit(request, body.mobile)
        try:
            tokens = await CustomerService.login_internal(body, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                await Helper.increment_login_attempt(request, body.mobile)
            raise
        await Helper.clear_login_attempt(request, body.mobile)
        return tokens

    @staticmethod
    async def is_authenticated(request: Request) -> dict:
        auth_header = request.headers.get("Authorization")
        customer_id = request.headers.get("customer_id")

        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing token")

        if not customer_id:
            raise HTTPException(
                status_code=401,
                detail="Missing customer_id header",
            )

        try:
            token = auth_header.split(" ")[1]
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
            )
            token_customer_id = str(payload.get("customer_id"))
            if token_customer_id != str(customer_id):
                raise HTTPException(
                    status_code=403,
                    detail="Customer ID and token mismatch",
                )
            return {
                "message": "Authenticated",
                "customer_id": token_customer_id,
                "mobile": payload.get("mobile"),
            }
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
