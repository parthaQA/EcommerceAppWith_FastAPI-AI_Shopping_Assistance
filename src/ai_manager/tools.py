import asyncio
from pprint import pprint
from typing import Annotated

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_manager.db_manager import DBManager
from src.ai_manager.dtos import build_search_response
from src.ai_manager.utils import Utils
from src.cart.cart_service import CartService
from langgraph.types import interrupt

from src.cart.dtos import CartResponseSchema, CartItemSchema
from src.cart.models import CartItemModel
from src.products.dtos import ProductResponseSchema
from src.products.product_service import ProductService
from src.utils.db import get_db_ctx
from src.utils.es_client import get_es_client
from typing import Annotated
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from langsmith import traceable

from src.ai_manager.settings import ai_settings


class Tools:

    @staticmethod
    @tool
    async def search_product(
            product_name: str,
            config: RunnableConfig,
            state: Annotated[dict, InjectedState],
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

        searched_product = None
        product_id = None

        async with get_db_ctx() as db:
            products = await ProductService.search_by_name(
                product_name, customer_id, db, get_es_client()
            )

        results = [
            {
                "name": p.product_name,
                "price": p.product_price,
                "available": p.product_quantity > 0,
                "quantity": p.product_quantity,
                "product_id": p.product_id,
            }
            for p in products
        ]

        print("search result :", results)

        for prod in results:
            if prod["name"].lower() == product_name.lower():
                searched_product = prod["name"]
                product_id = prod["product_id"]
                break

        print("searched product", searched_product)
        print("product id", product_id)

        if product_id is None:

            return {
                "success": False,
                "message": f"{product_name} is not available in the stock"
            }


        return {
            "success": True,
            "search_results": results,
            "product_memory": {str(p["product_id"]): p for p in results},
            "raw_response": build_search_response(
                product_name, results[:ai_settings.PRODUCT_SEARCH_RESULTS_TO_LLM]
            ),
        }



    @staticmethod
    @tool
    async def add_product_to_cart(
            config: RunnableConfig,
            product_name: str,
            state: Annotated[dict, InjectedState],
            quantity: int = 1,
        ):
        """
        add products to cart.

        Use this tool whenever the user asks:
        - add products to cart
        - if user does not explicit gives quantity of product then
            add 1 quantity of the product

        Returns:
        cart details where product name, price are mentioned
        """
        location = state.get("location", "")
        customer_id = Utils.get_customer_id(config)
        memory = state.get("product_memory", {})
        print("memory :", memory)

        searched_product = None
        product_id = None

        async with get_db_ctx() as db:
            products_details = await ProductService.search_by_name(
                    product_name, customer_id, db, get_es_client()
                )

            results = [
                    {
                        "name": p.product_name,
                        "price": p.product_price,
                        "available": p.product_quantity > 0,
                        "quantity": p.product_quantity,
                        "product_id": p.product_id,
                    }
            for p in products_details
                ]
            print("structured", results)


        for prod in results:
            if prod["name"].lower() == product_name.lower():
                searched_product = prod["name"]
                product_id = prod["product_id"]
                break


        print("searched product", searched_product)
        print("product id", product_id)

        if product_id is None:

            return {
                "success" : False,
                "message": f"{product_name} is not available in the stock"
            }


        cart_details = ""
        async with get_db_ctx() as db:
            cart_details = await CartService.create_cart(customer_id=customer_id, location=location, db=db)
            cart = cart_details["cart"]
            cart_id = cart.cart_id  # the string ID, e.g. "07494205-d52d-486d-a9d7-3b01600ac4b3"

            print("cart id", cart_id)


        if not cart_details:
            return {
                "success": False,
                "message": "cart is not created successfully",
            }

        create_payload = CartItemSchema(
                product_id=product_id,
                quantity=quantity,
                is_checkout=True,
            )
        print("create payload :", create_payload.model_dump())

        cart_response = await CartService.add_product(customer_id=customer_id,cart_id=cart_id,
                                                              body=create_payload, db=db)

        print("response of cart :", cart_response)

        fetch_cart_details = await CartService.create_cart(customer_id=customer_id, location=location, db=db)

        print("fetch cart details key", fetch_cart_details.keys())

        products = [
            ProductResponseSchema.model_validate(product).model_copy(
                update={"product_quantity": item.quantity}
            )
            for item, product in fetch_cart_details["items"]
        ]

        extracted = {
            "total_bill": fetch_cart_details["total_bill"],
            "total_product_quantity": fetch_cart_details["total_product_quantity"],
            "cart_products": [{"product_details": [p.model_dump(mode="json") for p in products]}],
        }

        print("extracted :", extracted)

        return {
                "success": True,
                "data": extracted,
                "message": "cart is retrieved successfully",
        }

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


    @tool
    @staticmethod
    async def save_user_meomry(fact: str, config: RunnableConfig) -> dict:
        """Save a durable fact or preference about the user (diet, preferred products,
            payment preference, delivery notes). Use only when the user states something worth
           remembering or explicitly asks you to save it. for example : save my address
           as default address."""

        customer_id = Utils.get_customer_id(config)

        result = await asyncio.to_thread(DBManager.insert_into_mem0_db(messages=fact, customer_id=customer_id))
        return {"status": "saved",
                "message": f"f{fact} saved successfully.",
                "memory_results": result
                }

    @tool
    @staticmethod
    async def search_user_memory(query: str, config: RunnableConfig) -> dict:
        """Look up saved preferences or facts about this user. Use when a
        user ask a personal context. for example : what is my default address?"""

        customer_id = Utils.get_customer_id(config)
        memories = await asyncio.to_thread(
            DBManager.retrieve_from_mem0_db, customer_id=customer_id, query=query
        )
        return {"raw_response": memories, "memory_results": memories}


    @tool
    @staticmethod
    async def search_policy(
            query: str,
            state: Annotated[dict, InjectedState],
    ) -> dict:
        """Look up store policies: refunds, returns, exchanges, terms and conditions,
        delivery rules. Use for any question about company rules. Do NOT use for
        product price or availability. Pass a short standalone question."""

        context = await asyncio.to_thread(
            DBManager.retrieve_policy,
            state["messages"][:-1],  # exclude the AI tool-call message
            query,
            state.get("eval_mode", False),
        )
        return {
            "raw_response": {
                "status": "ok" if context else "no_results",
                "note": "Policy text is in your system prompt." if context
                else "No relevant policy found. Tell the user you don't have that information.",
            },
            "retrieved_context": context,
        }

    @classmethod
    def all(cls) -> list:
        return [cls.search_product, cls.save_user_meomry, cls.search_user_memory, cls.search_policy, cls.add_product_to_cart]