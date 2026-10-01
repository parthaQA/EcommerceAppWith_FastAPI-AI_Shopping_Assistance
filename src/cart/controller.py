from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.cart.dtos import (
    CartItemSchema,
    CartProductSchema,
    CartProductsResponseSchema,
    CartResponseSchema,
    DeliveryAddressSchema,
    PaymentPreferenceSchema,
    ProductResponseSchema,
)
from src.cart.models import (
    CartItemModel,
    CartModel,
    DeliveryAddressModel,
    PaymentPreferenceModel,
)
from src.customers.models import CustomerModel
from src.products.models import ProductModel
from src.utils.auth import AuthUser
from src.utils.enums import PaymentMode
from src.utils.helper import Helper


class CartController:

    @staticmethod
    async def _get_owned_cart(
        cart_id: str,
        user: AuthUser,
        db: AsyncSession,
    ) -> CartModel:
        result = await db.execute(
            select(CartModel).where(
                CartModel.cart_id == cart_id,
                CartModel.customer_id == user.customer_id,
            )
        )
        cart = result.scalars().first()
        if not cart:
            raise HTTPException(status_code=404, detail="cart id not found")
        return cart

    @staticmethod
    async def get_cart(user: AuthUser, location: str, db: AsyncSession):
        result = await db.execute(
            select(CustomerModel).where(CustomerModel.id == user.customer_id)
        )
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail="Customer not found")

        cart_id = Helper.generate_cart_id()
        cart = CartModel(
            cart_id=cart_id,
            location=location,
            customer_id=user.customer_id,
        )
        db.add(cart)
        await db.commit()
        await db.refresh(cart)

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
        await CartController._get_owned_cart(cart_id, user, db)

        result = await db.execute(
            select(ProductModel).where(ProductModel.product_id == body.product_id)
        )
        product = result.scalars().first()
        if not product:
            raise HTTPException(status_code=404, detail="product id does not exist")

        if product.product_quantity < body.quantity:
            raise HTTPException(status_code=400, detail="quantity not available")

        cart_products = CartItemModel(
            cart_id=cart_id,
            product_id=body.product_id,
            quantity=body.quantity,
            is_checkout=body.is_checkout,
        )
        db.add(cart_products)
        await db.commit()
        await db.refresh(cart_products)

        result = await db.execute(
            select(CartItemModel).where(CartItemModel.cart_id == cart_id)
        )
        cart_items = result.scalars().all()


        product_ids = [item.product_id for item in cart_items]
        result = await db.execute(
            select(ProductModel).where(ProductModel.product_id.in_(product_ids))
        )
        products_by_id = {p.product_id: p for p in result.scalars().all()}

        products = []
        total_bill = 0
        total_quantity = 0

        for item in cart_items:
            prod = products_by_id.get(item.product_id)
            if prod is None:
                continue  # or handle a missing/deleted product explicitly
            products.append(
                ProductResponseSchema(
                    product_id=prod.product_id,
                    product_name=prod.product_name,
                    product_description=prod.product_description,
                    product_price=prod.product_price,
                    product_quantity=item.quantity,
                )
            )
            total_bill += prod.product_price * item.quantity
            total_quantity += item.quantity

        return {
            "success": True,
            "data": CartProductsResponseSchema(
                cart_id=cart_id,
                total_bill=total_bill,
                total_product_quantity=total_quantity,
                cart_products=CartProductSchema(product_details=products),
            ),
            "message": "product is added to cart",
        }

    @staticmethod
    async def reset_cart(
        user: AuthUser,
        cart_id: str,
        db: AsyncSession,
    ):
        await CartController._get_owned_cart(cart_id, user, db)

        await db.execute(
            delete(CartItemModel).where(CartItemModel.cart_id == cart_id)
        )
        await db.commit()

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
        await CartController._get_owned_cart(cart_id, user, db)

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
        await CartController._get_owned_cart(cart_id, user, db)

        if body.payment_mode not in PaymentMode.values():
            raise HTTPException(
                status_code=400,
                detail="payment mode is not supported",
            )

        result = await db.execute(
            select(PaymentPreferenceModel).where(
                PaymentPreferenceModel.cart_id == cart_id
            )
        )
        payment_preference = result.scalars().first()

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
        await CartController._get_owned_cart(cart_id, user, db)

        result = await db.execute(
            select(CartItemModel, ProductModel)
            .join(
                ProductModel,
                CartItemModel.product_id == ProductModel.product_id,
            )
            .where(CartItemModel.cart_id == cart_id)
        )
        rows = result.all()

        cart_products = []
        for cart_item, product in rows:
            cart_products.append(
                {
                    "product_id": product.product_id,
                    "product_name": product.product_name,
                    "product_description": product.product_description,
                    "product_price": product.product_price,
                    "product_quantity": cart_item.quantity,
                    "product_image_url": product.product_image_url,
                }
            )

        return {"data": cart_products}
