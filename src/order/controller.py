import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cart.controller import CartController
from src.cart.models import (
    CartItemModel,
    CartModel,
    DeliveryAddressModel,
    PaymentPreferenceModel,
)
from src.order.dtos import OrderSchema
from src.order.models import OrderItemModel, OrderModel
from src.utils.auth import AuthUser
from src.utils.db import Local_Session
from src.utils.enums import OrderStatus, PaymentStatus
from src.utils.settings import settings


class OrderController:

    @staticmethod
    def _accept_if_due(order: OrderModel) -> bool:
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
    async def _get_owned_order(
        user: AuthUser,
        order_id: str,
        db: AsyncSession,
    ) -> OrderModel:
        result = await db.execute(
            select(OrderModel)
            .join(CartModel, OrderModel.cart_id == CartModel.cart_id)
            .where(
                OrderModel.id == order_id,
                OrderModel.customer_id == user.customer_id,
                CartModel.customer_id == user.customer_id,
            )
        )
        order = result.scalars().first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order

    @staticmethod
    async def create_order(user: AuthUser, body: OrderSchema, db: AsyncSession):
        await CartController._get_owned_cart(body.cart_id, user, db)

        result = await db.execute(
            select(DeliveryAddressModel)
            .join(CartModel, DeliveryAddressModel.cart_id == CartModel.cart_id)
            .where(
                DeliveryAddressModel.cart_id == body.cart_id,
                CartModel.customer_id == user.customer_id,
            )
        )
        delivery_address = result.scalars().first()
        if not delivery_address:
            raise HTTPException(
                status_code=400,
                detail="delivery address is not added",
            )

        result = await db.execute(
            select(PaymentPreferenceModel)
            .join(CartModel, PaymentPreferenceModel.cart_id == CartModel.cart_id)
            .where(
                PaymentPreferenceModel.cart_id == body.cart_id,
                CartModel.customer_id == user.customer_id,
            )
        )
        payment_preference = result.scalars().first()
        if not payment_preference:
            raise HTTPException(
                status_code=400,
                detail="payment preference is not added",
            )

        result = await db.execute(
            select(CartItemModel)
            .join(CartModel, CartItemModel.cart_id == CartModel.cart_id)
            .where(
                CartItemModel.cart_id == body.cart_id,
                CartModel.customer_id == user.customer_id,
            )
        )
        cart_items = result.scalars().all()
        if not cart_items:
            raise HTTPException(status_code=400, detail="Cart is empty")

        payment_mode = payment_preference.payment_mode

        create_order = OrderModel(
            id=f"ORD{uuid.uuid4().hex[:8].upper()}",
            customer_id=user.customer_id,
            cart_id=body.cart_id,
            address_id=delivery_address.id,
            payment_mode=payment_mode,
            order_status=OrderStatus.PENDING,
            payment_status=PaymentStatus.UNPAID,
        )
        db.add(create_order)
        await db.flush()

        for item in cart_items:
            db.add(
                OrderItemModel(
                    order_id=create_order.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                )
            )

        await db.commit()
        await db.refresh(create_order)

        return {
            "success": True,
            "data": {
                "id": create_order.id,
                "cart_id": create_order.cart_id,
                "customer_id": create_order.customer_id,
                "address": delivery_address.address,
                "pincode": delivery_address.pincode,
                "city": delivery_address.city,
                "payment_mode": create_order.payment_mode,
                "order_status": create_order.order_status,
                "payment_status": create_order.payment_status,
                "created_date": create_order.created_date,
                "modified_date": create_order.modified_date,
            },
            "message": "Order created successfully",
        }

    @staticmethod
    async def get_order_details_by_order_id(
        user: AuthUser,
        order_id: str,
        db: AsyncSession,
    ):
        order = await OrderController._get_owned_order(user, order_id, db)
        if OrderController._accept_if_due(order):
            await db.commit()
            await db.refresh(order)

        result = await db.execute(
            select(OrderItemModel).where(OrderItemModel.order_id == order_id)
        )
        order_items = result.scalars().all()

        return {
            "success": True,
            "data": {
                "order": order,
                "order_items": order_items,
            },
            "message": "Order details retrieved successfully",
        }

    @staticmethod
    async def get_all_order_details_by_customer(
        user: AuthUser,
        db: AsyncSession,
    ):
        result = await db.execute(
            select(OrderModel)
            .join(CartModel, OrderModel.cart_id == CartModel.cart_id)
            .where(
                OrderModel.customer_id == user.customer_id,
                CartModel.customer_id == user.customer_id,
            )
        )
        orders = result.scalars().unique().all()
        if not orders:
            return {
                "success": True,
                "data": [],
                "message": "No orders found",
            }

        accepted = False
        for order in orders:
            if OrderController._accept_if_due(order):
                accepted = True
        if accepted:
            await db.commit()

        order_ids = [order.id for order in orders]
        result = await db.execute(
            select(OrderItemModel).where(OrderItemModel.order_id.in_(order_ids))
        )
        items_by_order = {}
        for item in result.scalars().all():
            items_by_order.setdefault(item.order_id, []).append(item)

        return {
            "success": True,
            "data": [
                {
                    "order": order,
                    "order_items": items_by_order.get(order.id, []),
                }
                for order in orders
            ],
            "message": "Order details retrieved successfully",
        }

    @staticmethod
    async def cancel_order(
        user: AuthUser,
        order_id: str,
        db: AsyncSession,
    ):
        order = await OrderController._get_owned_order(user, order_id, db)
        OrderController._accept_if_due(order)

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

        return {
            "success": True,
            "data": order,
            "message": "Order cancelled successfully",
        }


async def auto_accept_pending_orders():
    while True:
        try:
            async with Local_Session() as db:
                cutoff = datetime.utcnow() - timedelta(
                    minutes=settings.ORDER_AUTO_ACCEPT_MINUTES
                )
                result = await db.execute(
                    select(OrderModel).where(
                        OrderModel.order_status == OrderStatus.PENDING,
                        OrderModel.created_date <= cutoff,
                    )
                )
                orders = result.scalars().all()
                now = datetime.utcnow()
                for order in orders:
                    order.order_status = OrderStatus.ACCEPTED
                    order.modified_date = now
                if orders:
                    await db.commit()
        except Exception as exc:
            print(f"Order auto accept failed: {exc}")
        await asyncio.sleep(30)
