import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cart.cart_service import CartService
from src.cart.models import (
    CartItemModel,
    CartModel,
    DeliveryAddressModel,
    PaymentPreferenceModel,
)
from src.order.dtos import OrderSchema
from src.order.models import OrderItemModel, OrderModel
from src.utils.db import Local_Session
from src.utils.enums import OrderStatus, PaymentStatus
from src.utils.settings import settings


class OrderService:

    @staticmethod
    def accept_if_due(order: OrderModel) -> bool:
        if order.order_status != OrderStatus.PENDING or order.created_date is None:
            return False

        created = order.created_date
        if created.tzinfo is not None:
            created = created.replace(tzinfo=None)

        accept_at = created + timedelta(minutes=settings.ORDER_AUTO_ACCEPT_MINUTES)
        if datetime.utcnow() < accept_at:
            return False

        order.order_status = OrderStatus.ACCEPTED
        order.modified_date = datetime.utcnow()
        return True

    @staticmethod
    async def get_owned_order(
        customer_id: str,
        order_id: str,
        db: AsyncSession,
    ) -> OrderModel:
        order = await db.scalar(
            select(OrderModel)
            .join(CartModel, OrderModel.cart_id == CartModel.cart_id)
            .where(
                OrderModel.id == order_id,
                OrderModel.customer_id == customer_id,
                CartModel.customer_id == customer_id,
            )
        )
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return order

    @staticmethod
    async def create(
        customer_id: str,
        body: OrderSchema,
        db: AsyncSession,
    ) -> dict:
        await CartService.get_owned_cart(body.cart_id, customer_id, db)

        delivery_address = await db.scalar(
            select(DeliveryAddressModel)
            .join(CartModel, DeliveryAddressModel.cart_id == CartModel.cart_id)
            .where(
                DeliveryAddressModel.cart_id == body.cart_id,
                CartModel.customer_id == customer_id,
            )
        )
        if delivery_address is None:
            raise HTTPException(
                status_code=400,
                detail="delivery address is not added",
            )

        payment_preference = await db.scalar(
            select(PaymentPreferenceModel)
            .join(CartModel, PaymentPreferenceModel.cart_id == CartModel.cart_id)
            .where(
                PaymentPreferenceModel.cart_id == body.cart_id,
                CartModel.customer_id == customer_id,
            )
        )
        if payment_preference is None:
            raise HTTPException(
                status_code=400,
                detail="payment preference is not added",
            )

        cart_items = (
            await db.scalars(
                select(CartItemModel)
                .join(CartModel, CartItemModel.cart_id == CartModel.cart_id)
                .where(
                    CartItemModel.cart_id == body.cart_id,
                    CartModel.customer_id == customer_id,
                )
            )
        ).all()
        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        order = OrderModel(
            id=f"ORD{uuid.uuid4().hex[:8].upper()}",
            customer_id=customer_id,
            cart_id=body.cart_id,
            address_id=delivery_address.id,
            payment_mode=payment_preference.payment_mode,
            order_status=OrderStatus.PENDING,
            payment_status=PaymentStatus.UNPAID,
        )
        db.add(order)
        await db.flush()

        for item in cart_items:
            db.add(
                OrderItemModel(
                    order_id=order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                )
            )

        await db.commit()
        await db.refresh(order)

        return {
            "id": order.id,
            "cart_id": order.cart_id,
            "customer_id": order.customer_id,
            "address": delivery_address.address,
            "pincode": delivery_address.pincode,
            "city": delivery_address.city,
            "payment_mode": order.payment_mode,
            "order_status": order.order_status,
            "payment_status": order.payment_status,
            "created_date": order.created_date,
            "modified_date": order.modified_date,
        }

    @staticmethod
    async def get_details_by_order_id(
        customer_id: str,
        order_id: str,
        db: AsyncSession,
    ) -> dict:
        order = await OrderService.get_owned_order(customer_id, order_id, db)
        if OrderService.accept_if_due(order):
            await db.commit()
            await db.refresh(order)

        order_items = (
            await db.scalars(
                select(OrderItemModel).where(OrderItemModel.order_id == order_id)
            )
        ).all()
        return {"order": order, "order_items": order_items}

    @staticmethod
    async def get_all_by_customer(customer_id: str, db: AsyncSession) -> list[dict]:
        orders = (
            await db.scalars(
                select(OrderModel)
                .join(CartModel, OrderModel.cart_id == CartModel.cart_id)
                .where(
                    OrderModel.customer_id == customer_id,
                    CartModel.customer_id == customer_id,
                )
            )
        ).unique().all()
        if not orders:
            return []

        accepted = False
        for order in orders:
            if OrderService.accept_if_due(order):
                accepted = True
        if accepted:
            await db.commit()

        order_ids = [order.id for order in orders]
        items_by_order: dict = {}
        for item in (
            await db.scalars(
                select(OrderItemModel).where(OrderItemModel.order_id.in_(order_ids))
            )
        ).all():
            items_by_order.setdefault(item.order_id, []).append(item)

        return [
            {
                "order": order,
                "order_items": items_by_order.get(order.id, []),
            }
            for order in orders
        ]

    @staticmethod
    async def cancel(
        customer_id: str,
        order_id: str,
        db: AsyncSession,
    ) -> OrderModel:
        order = await OrderService.get_owned_order(customer_id, order_id, db)
        OrderService.accept_if_due(order)

        if order.order_status != OrderStatus.PENDING:
            await db.commit()
            raise HTTPException(
                status_code=400,
                detail="Order cannot be cancelled",
            )

        order.order_status = OrderStatus.CANCELLED
        order.modified_date = datetime.utcnow()
        await db.commit()
        await db.refresh(order)
        return order


async def auto_accept_pending_orders():
    while True:
        try:
            async with Local_Session() as db:
                cutoff = datetime.utcnow() - timedelta(
                    minutes=settings.ORDER_AUTO_ACCEPT_MINUTES
                )
                orders = (
                    await db.scalars(
                        select(OrderModel).where(
                            OrderModel.order_status == OrderStatus.PENDING,
                            OrderModel.created_date <= cutoff,
                        )
                    )
                ).all()
                now = datetime.utcnow()
                for order in orders:
                    order.order_status = OrderStatus.ACCEPTED
                    order.modified_date = now
                if orders:
                    await db.commit()
        except Exception as exc:
            print(f"Order auto accept failed: {exc}")
        await asyncio.sleep(30)
