import uuid

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
from src.utils.enums import OrderStatus, PaymentStatus


class OrderController:

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
            "data": create_order,
            "message": "Order created successfully",
        }

    @staticmethod
    async def get_order_details_by_order_id(
        user: AuthUser,
        order_id: str,
        db: AsyncSession,
    ):
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
