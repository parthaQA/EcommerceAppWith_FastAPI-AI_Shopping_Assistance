from sqlalchemy.ext.asyncio import AsyncSession

from src.cart.cart_service import CartService
from src.cart.dtos import (
    CartItemSchema,
    CartProductSchema,
    CartProductsResponseSchema,
    CartResponseSchema,
    DeliveryAddressSchema,
    PaymentPreferenceSchema,
    ProductResponseSchema,
)
from src.utils.auth import AuthUser


class CartController:

    @staticmethod
    async def _get_owned_cart(cart_id: str, user: AuthUser, db: AsyncSession):
        return await CartService.get_owned_cart(cart_id, user.customer_id, db)

    @staticmethod
    async def get_cart(user: AuthUser, location: str, db: AsyncSession):
        cart = await CartService.create_cart(user.customer_id, location, db)
        return {
            "success": True,
            "data": CartResponseSchema(
                cart_id=cart.cart_id,
                location=cart.location,
                created_date=cart.created_date,
                modified_date=cart.modified_date,
            ),
            "message": "Cart retrieved successfully",
        }

    @staticmethod
    async def add_product_to_cart(
        user: AuthUser,
        cart_id: str,
        body: CartItemSchema,
        db: AsyncSession,
    ):
        result = await CartService.add_product(user.customer_id, cart_id, body, db)
        products = [
            ProductResponseSchema(**product) for product in result["products"]
        ]
        return {
            "success": True,
            "data": CartProductsResponseSchema(
                cart_id=result["cart_id"],
                total_bill=result["total_bill"],
                total_product_quantity=result["total_product_quantity"],
                cart_products=CartProductSchema(product_details=products),
            ),
            "message": "product is added to cart",
        }

    @staticmethod
    async def reset_cart(user: AuthUser, cart_id: str, db: AsyncSession):
        cart_id = await CartService.reset_cart(user.customer_id, cart_id, db)
        return {
            "success": True,
            "data": CartProductsResponseSchema(
                cart_id=cart_id,
                total_bill=0,
                total_product_quantity=0,
                cart_products=CartProductSchema(product_details=[]),
            ),
            "message": "products are removed from cart",
        }

    @staticmethod
    async def add_delivery_address(
        user: AuthUser,
        cart_id: str,
        body: DeliveryAddressSchema,
        db: AsyncSession,
    ):
        delivery_address = await CartService.add_delivery_address(
            user.customer_id,
            cart_id,
            body,
            db,
        )
        return {
            "success": True,
            "data": delivery_address,
            "message": "Delivery address added successfully",
        }

    @staticmethod
    async def add_payment_preference(
        user: AuthUser,
        cart_id: str,
        body: PaymentPreferenceSchema,
        db: AsyncSession,
    ):
        payment_preference = await CartService.add_payment_preference(
            user.customer_id,
            cart_id,
            body,
            db,
        )
        return {
            "success": True,
            "data": payment_preference,
            "message": "Payment preference added successfully",
        }

    @staticmethod
    async def get_cart_for_checkout(
        user: AuthUser,
        cart_id: str,
        db: AsyncSession,
    ):
        cart_products = await CartService.get_cart_for_checkout(
            user.customer_id,
            cart_id,
            db,
        )
        return {"data": cart_products}
