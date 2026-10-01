from sqlalchemy import Column, ForeignKey, String, DateTime, Integer
from src.utils.db import BASE
from src.utils.helper import Helper
from datetime import datetime, timezone


class OrderModel(BASE):
    __tablename__ = "orders"

    id = Column(String(20), primary_key=True, unique=True, nullable=False)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    cart_id = Column(String, ForeignKey("cart.cart_id"))
    address_id = Column(Integer, ForeignKey("delivery_address.id"))
    payment_mode = Column(String, nullable=False)
    order_status = Column(String, nullable=False)
    payment_status = Column(String, nullable=False)
    created_date = Column(DateTime, default=datetime.utcnow())
    modified_date = Column(DateTime, default=datetime.utcnow())


class OrderItemModel(BASE):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, autoincrement=True)

    order_id = Column(
        String(20),
        ForeignKey("orders.id"),
        nullable=False
    )

    product_id = Column(
        Integer,
        ForeignKey("products.product_id"),
        nullable=False
    )

    quantity = Column(Integer, nullable=False)