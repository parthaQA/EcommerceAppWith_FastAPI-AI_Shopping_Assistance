from typing import Annotated

from fastapi import HTTPException
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langsmith import traceable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.ai_manager.dtos import build_search_response
from src.ai_manager.utils import Utils
from src.cart.cart_service import CartService
from src.cart.dtos import (
    CartProductSchema,
    CartProductsResponseSchema,
    ProductResponseSchema,
)
from src.cart.models import CartItemModel, CartModel
from src.customers.models import CustomerModel
from src.products.controller import ProductController
from src.products.models import ProductModel
from langgraph.types import interrupt

from src.products.product_service import ProductService
from src.utils.db import get_db_ctx
from src.utils.es_client import get_es_client
from src.utils.helper import Helper
import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from langsmith import traceable

from src.utils.settings import settings


class Tools:

    @tool
    @traceable(name="search_product")
    @staticmethod
    async def search_product(
            name: str,
            config: RunnableConfig,
            state: Annotated[dict, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Search grocery products by product name.

        Use this tool when the user wants to:
        - Find products
        - Check availability
        - See prices

        Args:
            name: Product name or keyword to search for, e.g. "milk" or "basmati rice".
        """
        customer_id = Utils.get_customer_id(config)

        async with get_db_ctx() as db:
            products = await ProductService.search_by_name(
                name, customer_id, db, get_es_client()
            )

        structured = [
            {
                "name": p.product_name,
                "price": p.product_price,
                "available": p.product_quantity > 0,
                "quantity": p.product_quantity,
                "product_id": p.product_id,
            }
            for p in products
        ]

        # Merge into existing memory without mutating the old dict
        memory = {
            **state.get("product_memory", {}),
            **{p["name"].lower(): p for p in structured},
        }

        return {
            "search_results": structured,
            "product_memory": memory,
            "raw_response": build_search_response(name, structured[:settings.PRODUCT_SEARCH_RESULTS_TO_LLM])
        }

    @staticmethod
    def add_product_to_cart_llm(customer_id, db: AsyncSession):

        @tool
        @traceable
        async def add_product_to_cart(
            product_name: str,
            state: Annotated[dict, InjectedState],
            quantity: int = 1,
        ):
            """
            add products to cart.

            Use this tool whenever the user asks:
            - add products to cart
            - Check the searched product is already available in product memory
            - if avaiable use the products from product memory.

            Returns:
            cart details where product name, price are mentioned
            """
            location = state["location"]
            memory = state.get("product_memory", {})
            print("memory :", memory)

            product = memory.get(product_name.lower())
            print("product details : ", product)

            if not product:
                return {
                    "success": False,
                    "message": "Product not found in previous search.",
                }

            product_id = product["product_id"]

            result = await db.execute(
                select(CustomerModel).where(CustomerModel.id == customer_id)
            )
            customer_exists = result.scalars().first()
            if not customer_exists:
                raise HTTPException(status_code=404, detail="Customer not found")

            result = await db.execute(
                select(CartModel).where(CartModel.customer_id == customer_id)
            )
            cart = result.scalars().first()

            if cart:
                cart_id = cart.cart_id
            else:
                cart_id = Helper.generate_cart_id()
                cart = CartModel(
                    cart_id=cart_id,
                    customer_id=customer_id,
                    location=location,
                )
                db.add(cart)
                await db.commit()
                await db.refresh(cart)

            if product["quantity"] < quantity:
                raise HTTPException(status_code=400, detail="quantity not available")

            cart_products = CartItemModel(
                cart_id=cart_id,
                product_id=product_id,
                quantity=quantity,
                is_checkout=True,
            )
            db.add(cart_products)
            await db.commit()
            await db.refresh(cart_products)

            result = await db.execute(
                select(CartItemModel).where(CartItemModel.cart_id == cart_id)
            )
            cart_items = result.scalars().all()

            products = []
            total_bill = 0
            total_quantity = 0

            for item in cart_items:
                result = await db.execute(
                    select(ProductModel).where(
                        ProductModel.product_id == item.product_id
                    )
                )
                prod = result.scalars().first()
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

            cart_response = CartProductsResponseSchema(
                cart_id=cart_id,
                total_bill=total_bill,
                total_product_quantity=total_quantity,
                cart_products=CartProductSchema(product_details=products),
            )

            return {
                "success": True,
                "data": cart_response.model_dump(),
                "message": "product is added to cart",
            }

        return add_product_to_cart

    @staticmethod
    @tool
    def human_assistance(query: str):
        """request human assistance from human
        call this tool when user requires human assistance.
        llm should not provide any assistance"""
        human_response = interrupt({"query": query})
        return human_response["data"]

    @staticmethod
    def get_cart_tool(db: AsyncSession):

        @tool
        @traceable
        async def get_cart(state: Annotated[dict, InjectedState]):
            """call this tool to get the latest cart details
            the cart contains all the latest product details are
            added to cart."""
            cart_id = state["cart"]["cart_id"]
            customer_id = state.get("customer_id")
            if not customer_id:
                raise HTTPException(status_code=401, detail="Customer not authenticated")
            cart_products = await CartService.get_cart_for_checkout(
                str(customer_id),
                cart_id,
                db,
            )
            return {"data": cart_products}

        return get_cart
