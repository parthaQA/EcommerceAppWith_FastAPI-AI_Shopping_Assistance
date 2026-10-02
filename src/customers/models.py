from sqlalchemy import Column, String, Boolean, DateTime, BigInteger, Integer, ForeignKey
from src.utils.db import BASE
from src.utils.helper import Helper
from datetime import datetime, timezone


class CustomerModel(BASE):
    __tablename__ = "customers"

    id = Column(String(10), primary_key=True, unique=True,
                default=Helper.generate_customer_id)
    name = Column(String)
    gender = Column(String)
    mobile= Column(BigInteger)
    email = Column(String)
    address = Column(String)
    pincode = Column(Integer)
    is_active = Column(Boolean, default=False)
    created_date =  Column(
    DateTime(timezone=True),
    default=lambda: datetime.now(timezone.utc)
)


class CustomerRegistrationModel(BASE):
    __tablename__ = "customer_credential"
    id = Column(Integer, primary_key=True, index=True)
    mobile = Column(BigInteger, unique=True, index=True, nullable=False)
    password= Column(String)


class RefreshTokenModel(BASE):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    mobile = Column(String, index=True)
    token = Column(String, unique=True, index=True)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


class SavedAddressModel(BASE):
    __tablename__ = "saved_address"

    id = Column(Integer, primary_key=True, unique=True, autoincrement=True, nullable=False)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    address = Column(String, nullable=False)
    pincode = Column(Integer, nullable=False)
    city = Column(String, nullable=False)
    created_date = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )