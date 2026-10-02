from datetime import datetime, timedelta

from pydantic import ConfigDict
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from src.utils.db import BASE
from src.utils.enums import PaymentMode


def utcnow_naive() -> datetime:
    return datetime.utcnow()


class CartModel(BASE):
    __tablename__ = "cart"

    cart_id = Column(String, primary_key=True, index=True, unique=True, nullable=False)
    location = Column(String, nullable=False)
    customer_id = Column(String, ForeignKey("customers.id"))
    created_date = Column(DateTime, default=utcnow_naive, nullable=False)
    modified_date = Column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )
    status = Column(String, default="ACTIVE")
    expires_at = Column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(days=7),
    )

    model_config = ConfigDict(from_attributes=True)


class CartItemModel(BASE):
    __tablename__ = "cart_items"

    id = Column(
        Integer,
        autoincrement=True,
        nullable=False,
        primary_key=True,
        unique=True,
    )
    cart_id = Column(String, ForeignKey("cart.cart_id"))
    product_id = Column(Integer, ForeignKey("products.product_id"))
    quantity = Column(Integer, default=1)
    is_checkout = Column(Boolean, default=False, nullable=False)
    created_date = Column(DateTime, default=utcnow_naive, nullable=False)
    modified_date = Column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    model_config = ConfigDict(from_attributes=True)


class DeliveryAddressModel(BASE):
    __tablename__ = "delivery_address"

    id = Column(
        Integer,
        primary_key=True,
        unique=True,
        autoincrement=True,
        nullable=False,
    )
    cart_id = Column(String, ForeignKey("cart.cart_id"))
    address = Column(String, nullable=False)
    pincode = Column(Integer, nullable=False)
    city = Column(String, nullable=False)
    created_date = Column(DateTime, default=utcnow_naive, nullable=False)
    modified_date = Column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    model_config = ConfigDict(from_attributes=True)


class PaymentPreferenceModel(BASE):
    __tablename__ = "payment_preference"

    id = Column(
        Integer,
        primary_key=True,
        unique=True,
        autoincrement=True,
        nullable=False,
    )
    cart_id = Column(String, ForeignKey("cart.cart_id"))
    payment_mode = Column(String, nullable=False, default=PaymentMode.COD)
    created_date = Column(DateTime, default=utcnow_naive, nullable=False)
    modified_date = Column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    model_config = ConfigDict(from_attributes=True)
