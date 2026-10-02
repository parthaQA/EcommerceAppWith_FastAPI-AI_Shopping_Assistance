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
from src.utils.auth import AuthUser
from src.utils.helper import Helper
from src.utils.settings import settings


class CustomerController:

    async def create_customer(self, body: CustomerSchema, db: AsyncSession):
        result = await db.execute(
            select(CustomerModel).where(CustomerModel.mobile == body.mobile)
        )
        if result.scalars().first():
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

    async def get_all_customers(self, db: AsyncSession):
        result = await db.execute(select(CustomerModel))
        return result.scalars().all()

    async def get_customer_by_id(
        self,
        customer_id: str,
        db: AsyncSession,
    ):
        customer = await db.get(CustomerModel, customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    async def register_customer(
        self,
        body: CustomerRegisterSchema,
        db: AsyncSession,
    ):
        result = await db.execute(
            select(CustomerModel).where(CustomerModel.mobile == body.mobile)
        )
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail="Customer not found")

        result = await db.execute(
            select(CustomerRegistrationModel).where(
                CustomerRegistrationModel.mobile == body.mobile
            )
        )
        if result.scalars().first():
            raise HTTPException(status_code=400, detail="number already exist")

        hashed_password = await Helper.hash_password(body.password)
        customer_registration_data = CustomerRegistrationModel(
            mobile=body.mobile,
            password=hashed_password,
        )
        db.add(customer_registration_data)
        await db.commit()
        await db.refresh(customer_registration_data)
        return customer_registration_data

    async def save_address(
        self,
        user: AuthUser,
        body: SavedAddressSchema,
        db: AsyncSession,
    ):
        customer = await db.get(CustomerModel, user.customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        if not (560001 <= body.pincode <= 560114):
            raise HTTPException(
                status_code=400,
                detail="Delivery is available only for pincodes between 560001 and 560114",
            )

        saved_address = SavedAddressModel(
            customer_id=user.customer_id,
            address=body.address,
            pincode=body.pincode,
            city=body.city,
        )
        db.add(saved_address)
        await db.commit()
        await db.refresh(saved_address)

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
        await Helper.check_rate_limit(request, body.mobile)
        try:
            tokens = await self.customer_login_internal(body, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                await Helper.increment_login_attempt(request, body.mobile)
            raise
        await Helper.clear_login_attempt(request, body.mobile)
        return tokens

    async def customer_login_internal(
        self,
        body: CustomerLoginSchema,
        db: AsyncSession,
    ):
        result = await db.execute(
            select(CustomerModel).where(CustomerModel.mobile == body.mobile)
        )
        customer = result.scalars().first()

        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        result = await db.execute(
            select(CustomerRegistrationModel).where(
                CustomerRegistrationModel.mobile == body.mobile
            )
        )
        registration = result.scalars().first()

        if not registration:
            raise HTTPException(status_code=401, detail="Unauthorized")

        if not await Helper.check_password(body.password, registration.password):
            raise HTTPException(status_code=401, detail="Wrong password")

        # --- Access token (short-lived, stateless) ---
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

        # --- Refresh token (long-lived, stored + revocable) ---
        raw_refresh_token = Helper.generate_refresh_token()
        refresh_expires_at = datetime.utcnow() + timedelta(
            days=settings.REFRESH_TOKEN_EXP_DAYS
        )

        db.add(
            RefreshTokenModel(
                mobile=str(registration.mobile),
                token=Helper.hash_token(raw_refresh_token),  # store hash, not raw value
                expires_at=refresh_expires_at,
            )
        )
        await db.commit()

        return {
            "customer_id": customer.id,
            "mobile": registration.mobile,
            "access_token": access_token,
            "refresh_token": raw_refresh_token,  # raw value goes to the client only
            "token_type": "bearer",
        }

    @staticmethod
    async def is_authenticated(request: Request):
        auth_header = request.headers.get("Authorization")
        customer_id = request.headers.get("customer_id")

        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing token")

        if not customer_id:
            raise HTTPException(
                status_code=401,
                detail="Missing customer_id header"
            )

        try:
            token = auth_header.split(" ")[1]

            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )

            token_customer_id = str(payload.get("customer_id"))

            if token_customer_id != str(customer_id):
                raise HTTPException(
                    status_code=403,
                    detail="Customer ID and token mismatch"
                )

            return {
                "message": "Authenticated",
                "customer_id": token_customer_id,
                "mobile": payload.get("mobile")
            }

        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")

        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
