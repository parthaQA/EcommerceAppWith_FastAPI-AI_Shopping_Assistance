from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cart.dtos import CartItemSchema, DeliveryAddressSchema, PaymentPreferenceSchema
from src.cart.models import (
    CartItemModel,
    CartModel,
    DeliveryAddressModel,
    PaymentPreferenceModel,
)
from src.customers.models import CustomerModel
from src.products.models import ProductModel
from src.utils.enums import PaymentMode
from src.utils.helper import Helper


class CartService:

    @staticmethod
    async def get_owned_cart(
        cart_id: str,
        customer_id: str,
        db: AsyncSession,
    ) -> CartModel:
        cart = await db.scalar(
            select(CartModel).where(
                CartModel.cart_id == cart_id,
                CartModel.customer_id == customer_id,
            )
        )
        if cart is None:
            raise HTTPException(status_code=404, detail="cart id not found")
        return cart

    @staticmethod
    async def create_cart(
        customer_id: str,
        location: str,
        db: AsyncSession,
    ) -> CartModel:
        customer = await db.scalar(
            select(CustomerModel).where(CustomerModel.id == customer_id)
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")

        cart = CartModel(
            cart_id=Helper.generate_cart_id(),
            location=location,
            customer_id=customer_id,
        )
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
        return cart

    @staticmethod
    async def add_product(
        customer_id: str,
        cart_id: str,
        body: CartItemSchema,
        db: AsyncSession,
    ) -> dict:
        await CartService.get_owned_cart(cart_id, customer_id, db)

        product = await db.scalar(
            select(ProductModel).where(ProductModel.product_id == body.product_id)
        )
        if product is None:
            raise HTTPException(status_code=404, detail="product id does not exist")

        if product.product_quantity < body.quantity:
            raise HTTPException(status_code=400, detail="quantity not available")

        db.add(
            CartItemModel(
                cart_id=cart_id,
                product_id=body.product_id,
                quantity=body.quantity,
                is_checkout=body.is_checkout,
            )
        )
        await db.commit()

        cart_items = (
            await db.scalars(
                select(CartItemModel).where(CartItemModel.cart_id == cart_id)
            )
        ).all()

        product_ids = [item.product_id for item in cart_items]
        products_by_id = {
            p.product_id: p
            for p in (
                await db.scalars(
                    select(ProductModel).where(ProductModel.product_id.in_(product_ids))
                )
            ).all()
        }

        products = []
        total_bill = 0
        total_quantity = 0
        for item in cart_items:
            prod = products_by_id.get(item.product_id)
            if prod is None:
                continue
            products.append(
                {
                    "product_id": prod.product_id,
                    "product_name": prod.product_name,
                    "product_description": prod.product_description,
                    "product_price": prod.product_price,
                    "product_quantity": item.quantity,
                }
            )
            total_bill += prod.product_price * item.quantity
            total_quantity += item.quantity

        return {
            "cart_id": cart_id,
            "total_bill": total_bill,
            "total_product_quantity": total_quantity,
            "products": products,
        }

    @staticmethod
    async def reset_cart(
        customer_id: str,
        cart_id: str,
        db: AsyncSession,
    ) -> str:
        await CartService.get_owned_cart(cart_id, customer_id, db)
        await db.execute(
            delete(CartItemModel).where(CartItemModel.cart_id == cart_id)
        )
        await db.commit()
        return cart_id

    @staticmethod
    async def add_delivery_address(
        customer_id: str,
        cart_id: str,
        body: DeliveryAddressSchema,
        db: AsyncSession,
    ) -> DeliveryAddressModel:
        await CartService.get_owned_cart(cart_id, customer_id, db)

        if not (560001 <= body.pincode <= 560114):
            raise HTTPException(
                status_code=400,
                detail="Delivery is available only for pincodes between 560001 and 560114",
            )

        delivery_address = DeliveryAddressModel(
            cart_id=cart_id,
            address=body.address,
            pincode=body.pincode,
            city=body.city,
        )
        db.add(delivery_address)
        await db.commit()
        await db.refresh(delivery_address)
        return delivery_address

    @staticmethod
    async def add_payment_preference(
        customer_id: str,
        cart_id: str,
        body: PaymentPreferenceSchema,
        db: AsyncSession,
    ) -> PaymentPreferenceModel:
        await CartService.get_owned_cart(cart_id, customer_id, db)

        if body.payment_mode not in PaymentMode.values():
            raise HTTPException(
                status_code=400,
                detail="payment mode is not supported",
            )

        payment_preference = await db.scalar(
            select(PaymentPreferenceModel).where(
                PaymentPreferenceModel.cart_id == cart_id
            )
        )
        if payment_preference:
            payment_preference.payment_mode = body.payment_mode
        else:
            payment_preference = PaymentPreferenceModel(
                cart_id=cart_id,
                payment_mode=body.payment_mode,
            )
            db.add(payment_preference)

        await db.commit()
        await db.refresh(payment_preference)
        return payment_preference

    @staticmethod
    async def get_cart_for_checkout(
        customer_id: str,
        cart_id: str,
        db: AsyncSession,
    ) -> list[dict]:
        await CartService.get_owned_cart(cart_id, customer_id, db)

        rows = (
            await db.execute(
                select(CartItemModel, ProductModel)
                .join(
                    ProductModel,
                    CartItemModel.product_id == ProductModel.product_id,
                )
                .where(CartItemModel.cart_id == cart_id)
            )
        ).all()

        return [
            {
                "product_id": product.product_id,
                "product_name": product.product_name,
                "product_description": product.product_description,
                "product_price": product.product_price,
                "product_quantity": cart_item.quantity,
                "product_image_url": product.product_image_url,
            }
            for cart_item, product in rows
        ]
