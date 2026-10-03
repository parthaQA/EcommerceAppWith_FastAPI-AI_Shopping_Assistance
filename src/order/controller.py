from sqlalchemy.ext.asyncio import AsyncSession

from src.order.dtos import OrderSchema
from src.order.order_service import OrderService, auto_accept_pending_orders
from src.utils.auth import AuthUser

__all__ = ["OrderController", "auto_accept_pending_orders"]


class OrderController:

    @staticmethod
    async def create_order(user: AuthUser, body: OrderSchema, db: AsyncSession):
        data = await OrderService.create(user.customer_id, body, db)
        return {
            "success": True,
            "data": data,
            "message": "Order created successfully",
        }

    @staticmethod
    async def get_order_details_by_order_id(
        user: AuthUser,
        order_id: str,
        db: AsyncSession,
    ):
        data = await OrderService.get_details_by_order_id(
            user.customer_id,
            order_id,
            db,
        )
        return {
            "success": True,
            "data": data,
            "message": "Order details retrieved successfully",
        }

    @staticmethod
    async def get_all_order_details_by_customer(
        user: AuthUser,
        db: AsyncSession,
    ):
        data = await OrderService.get_all_by_customer(user.customer_id, db)
        if not data:
            return {
                "success": True,
                "data": [],
                "message": "No orders found",
            }
        return {
            "success": True,
            "data": data,
            "message": "Order details retrieved successfully",
        }

    @staticmethod
    async def cancel_order(
        user: AuthUser,
        order_id: str,
        db: AsyncSession,
    ):
        order = await OrderService.cancel(user.customer_id, order_id, db)
        return {
            "success": True,
            "data": order,
            "message": "Order cancelled successfully",
        }
