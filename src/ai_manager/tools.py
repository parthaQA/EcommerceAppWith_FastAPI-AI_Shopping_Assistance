import asyncio
from pprint import pprint
from typing import Annotated

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai_manager import utils
from src.ai_manager.db_manager import DBManager
from src.ai_manager.dtos import ToolResult
from src.ai_manager.utils import Utils
from src.cart.cart_service import CartService
from langgraph.types import interrupt

from src.cart.dtos import CartResponseSchema, CartItemSchema, CartProductsResponseSchema, DeliveryAddressSchema, \
    PaymentPreferenceSchema
from src.cart.models import CartItemModel
from src.order.order_service import OrderService
from src.products.dtos import ProductResponseSchema
from src.products.product_service import ProductService
from src.utils.db import get_db_ctx
from src.utils.es_client import get_es_client
from typing import Annotated
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command


from src.ai_manager.settings import ai_settings


class Tools:

    @staticmethod
    @tool
    async def search_product(
            product_name: str,
            config: RunnableConfig
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

        # for prod in results:
        #     if prod["name"].lower() == product_name.lower():
        #         searched_product = prod["name"]
        #         product_id = prod["product_id"]
        #         break
        #
        # print("searched product", searched_product)
        # print("product id", product_id)

        if results is None:

            return ToolResult(
                success=False,
                message=f"{product_name} is not available in the stock",
                error_code="NOT_FOUND",
            ).model_dump_json()

        print("exposed data: ", results[:ai_settings.PRODUCT_SEARCH_RESULTS_TO_LLM])

        try:
            return ToolResult(
                success=True,
                message=f"Found {len(results)} products",
                data=results[:ai_settings.PRODUCT_SEARCH_RESULTS_TO_LLM],
                internal={
                    "search_results": results,
                    "product_memory": {str(p["product_id"]): p for p in results},
                },
            ).model_dump_json()
        except Exception:
            print("search_product failed while building result")
            raise



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

            return ToolResult(
                success=False,
                message=f"{product_name} is not available in the stock",
                error_code="NOT_FOUND",
            ).model_dump_json()


        cart_details = ""
        async with get_db_ctx() as db:
            cart_details = await CartService.create_cart(customer_id=customer_id, location=location, db=db)
            cart = cart_details["cart"]
            cart_id = cart.cart_id  # the string ID, e.g. "07494205-d52d-486d-a9d7-3b01600ac4b3"

            print("cart id", cart_id)


        if not cart_details:
            return ToolResult(
                success=False,
                message="Cart is not created",
                error_code="Cart Failure",
            ).model_dump_json()

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

        if extracted:
            return ToolResult(
            success=True,
            message="Added to cart",
            data=extracted,
            ).model_dump_json()

        return ToolResult(
            success=False,
            message="product not added to cart",
            data=extracted,
        ).model_dump_json()

    @staticmethod
    @tool
    def human_assistance(query: str):
        """request human assistance from human
        call this tool when user requires human assistance.
        llm should not provide any assistance"""
        human_response = interrupt({"query": query})
        return human_response["data"]

    @staticmethod
    @tool
    async def get_cart_tool(state: Annotated[dict, InjectedState], config: RunnableConfig) -> dict:

        """call this tool to get the latest cart details
        the cart contains all the latest product details and their prices.
        calculate the total price of the cart and return it to the user."""

        customer_id = Utils.get_customer_id(config)

        location = state.get("location", "")

        try :

            async with get_db_ctx() as db:
                cart_details = await CartService.create_cart(customer_id=customer_id, location=location, db=db)
                cart = cart_details["cart"]
                cart_products = await CartService.get_cart_for_checkout(
                str(customer_id),
                cart.cart_id,
                db,
                )

            print("cart products", cart_products)

        except Exception as e:
            print("Error while fetching cart details:", str(e))
            return ToolResult(
                success=False,
                data={},
                message="Could not load the cart right now. Tell the user there was a problem; do not call this tool again.",
            ).model_dump_json()

        if cart_products:
            extracted = [
                    {
                        "product_name": p.get("product_name"),
                        "product_price": p.get("product_price"),
                        "product_quantity": p.get("product_quantity"),
                    }
                    for p in cart_products
                ]

            print("extracted :", extracted)

            return ToolResult(
                success=True,
                data=extracted,
                message="cart details are fetched sucessfully" if extracted else "cart is empty",
                ).model_dump_json()



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

    @staticmethod
    @tool
    async def remove_product_from_cart(state: Annotated[dict, InjectedState], config: RunnableConfig) -> dict:
        """
           Remove products from the shopping cart.

           Use this tool whenever the user asks:
           - Remove a product from the cart.
           - Delete a product from the cart.
           - Remove all products from the cart.
           - Clear the cart.
           - Empty the shopping cart.

           If the user asks to remove all products, first ask for confirmation to user.
           """

        decision = Utils.ask_confirmation(action="clear_cart", message="...")

        print("decision :", decision)

        if not decision.get("approved"):
            return ToolResult(success=False, message="User cancelled. Cart unchanged.", data={}).model_dump_json()

        location = state.get("location", "")
        customer_id = Utils.get_customer_id(config)

        async with get_db_ctx() as db:
            cart_details = await CartService.create_cart(customer_id=customer_id, location=location, db=db)
            cart = cart_details["cart"]
            cart = await CartService.reset_cart_items(customer_id, cart.cart_id, db)

            if cart :

                return  ToolResult(
                        success=True,
                        message="product is removed from cart",
                        data={},
                        ).model_dump_json()


            return ToolResult(
                    success=False,
                    message="product is not removed from cart",
                    data={},
                ).model_dump_json()

    @staticmethod
    @tool
    async def place_order_tool(state : Annotated[dict, InjectedState], config : RunnableConfig) -> dict:
        """Place an order for the items in the shopping cart.

        Use this tool when the user wants to:
        - Place an order
        - Checkout
        - Complete the purchase

        This tool should only be called after confirming the user's intent to place the order.
        """
        decision = Utils.ask_confirmation(action="place_order", message="Are you sure you want to place the order?")

        print("decision :", decision)

        if not decision.get("approved"):
            return ToolResult(success=False, message="User cancelled. Order not placed.", data={}).model_dump_json()


        customer_id = Utils.get_customer_id(config)
        location = state.get("location", "")

        order_details = {}

        async with get_db_ctx() as db:
            cart_details = await CartService.create_cart(customer_id=customer_id, location=location, db=db)
            cart = cart_details["cart"]

            try:
                place_order_response = await OrderService.create(customer_id=customer_id, body=cart, db=db)

                print("place order response :", place_order_response)

                order_details = {
                    "order_id" : place_order_response.get("id"),
                    "address" : place_order_response.get("address"),
                    "pincode" : place_order_response.get("pincode"),
                    "city" :  place_order_response.get("city"),
                    "payment_mode" : place_order_response.get("payment_mode"),
                    "order_status" : place_order_response.get("order_status"),
                    "payment_status" : place_order_response.get("payment_status")
                }



            except Exception as e:
                print("Error while placing order:", str(e))

                if "delivery address is not added" in str(e) :

                    return ToolResult(
                    success=False,
                    message=f"order is not placed due to {str(e)}. add address in in this format address, city, pincode",
                    data={},
                    ).model_dump_json()

                elif "payment" in str(e):
                    return ToolResult(
                        success=False,
                        message=f"order is not placed due to {str(e)}. add payment mode as COD",
                        data={},
                    ).model_dump_json()



        return ToolResult(
            success=True,
            message="Order has been placed successfully.",
            data=order_details,
        ).model_dump_json()

    @staticmethod
    @tool
    async def add_delivery_address_tool(state : Annotated[dict, InjectedState], config : RunnableConfig, address: str,
                                        pincode: int, city: str) -> dict:
        """Add a delivery address for the user.

        Use this tool when the user wants to:
        - Add a new delivery address
        - ask user for address, pincode and city details
        """
        customer_id = Utils.get_customer_id(config)
        location = state.get("location", "")

        delivery_address = DeliveryAddressSchema(
            address = address,
            pincode = int(pincode),
            city = city
        )

        added_address = {}

        async with get_db_ctx() as db:

            cart_details = await CartService.create_cart(customer_id=customer_id, location=location, db=db)
            cart = cart_details["cart"]
            try:
                address_response = await CartService.add_delivery_address(customer_id=customer_id, cart_id=cart.cart_id, body=delivery_address, db=db)

                added_address = {
                    "delivery_address" : address_response.address,
                    "pincode" : address_response.pincode,
                    "city" : address_response.city
                }

                print("added address :", added_address)

            except Exception as e:

                print(f"error while adding address {str(e)}")

                return ToolResult(
                    success=False,
                    message=f"{str(e)}, address is not added please make sure the format is 'address', 'pincode' and 'city'",
                    data={},
                ).model_dump_json()

        return ToolResult(
            success=True,
            message=f"address is added",
            data=added_address,
        ).model_dump_json()

    @staticmethod
    @tool
    async def add_payment_mode_tool(state: Annotated[dict, InjectedState], config: RunnableConfig, payment_mode: str):
        """Add a payment preference/mode for the user.

                Use this tool when the user wants to:
                - Add a new payment mode
                - ask cash as payment mode
                - if user says I want to make payment with cash then set COD as {payment_mode}
                """
        customer_id = Utils.get_customer_id(config)
        location = state.get("location", "")

        payment_preference = PaymentPreferenceSchema(
            payment_mode=payment_mode.upper(),
        )


        async with get_db_ctx() as db:
            cart_details = await CartService.create_cart(customer_id=customer_id, location=location, db=db)
            cart = cart_details["cart"]
            try:

                payment_response = await CartService.add_payment_preference(customer_id=customer_id, cart_id = cart.cart_id, body = payment_preference, db = db)

                print("payment_response : ", payment_response.payment_mode)

            except Exception as e:
                print(f"payment mode is not added {str(e)}, please make sure payment preference is 'COD'")

                return ToolResult(
                    success=False,
                    message=f"payment mode is not added {str(e)}, please make sure payment preference is 'COD'",
                    data={},
                ).model_dump_json()

        return ToolResult(
            success=True,
            message=f"payment mode is added as {payment_response.payment_mode} ",
            data=payment_response.payment_mode,
        ).model_dump_json()

    @staticmethod
    @tool
    async def order_details_by_id_tool(config: RunnableConfig, order_id: str):

        """call this tool when user wants to know about his/her order details or order status.
        This tool accepts order id as parameter"""

        customer_id = Utils.get_customer_id(config)

        order_details = {}

        async with get_db_ctx() as db:

            try :
                order_details_response = await OrderService.get_details_by_order_id(
                customer_id=customer_id,
                order_id = order_id,
                db = db
                    )

                orders = order_details_response["order"]
                print("order id of order:", orders.id)


                order_details = {
                    "order_id" : orders.id,
                    "status" : orders.order_status,
                    "payment_status" : orders.payment_status,
                    "payment_mode" : orders.payment_mode
                }

            except Exception as e:

                return ToolResult(
                    success=False,
                    message=f"something is wrong with the order {str(e)}",
                    data={},
                ).model_dump_json()

        return ToolResult(
                    success=True,
                    message=f"order detail is fetched successfully {order_details}",
                    data=order_details,
                ).model_dump_json()


    @staticmethod
    @tool
    async def cancel_order_tool(config: RunnableConfig, order_id: str):

        """call this tool when user wants to cancel the order which is in
        pending status"""

        customer_id = Utils.get_customer_id(config)

        cancel_order_details = {}

        async with get_db_ctx() as db:
            try:
                cancel_order_details_response = await OrderService.cancel(
                    customer_id=customer_id,
                    order_id=order_id,
                    db=db
                )

                print("cancel_order details :", cancel_order_details_response.id)

                cancel_order_details = {
                    "order_id" : cancel_order_details_response.id,
                    "order_status" : cancel_order_details_response.order_status,
                    "payment_status" : cancel_order_details_response.payment_status,
                    "payment_mode" :  cancel_order_details_response.payment_mode,
                }

            except Exception as e:

                return ToolResult(
                    success=False,
                    message=f"order cannot be canceled at this this, {str(e)}",
                    data={},
                ).model_dump_json()

        return ToolResult(
            success=True,
            message=f"order detail is fetched successfully {cancel_order_details}",
            data=cancel_order_details,
        ).model_dump_json()



    @classmethod
    def all(cls) -> list:
        return [cls.search_product, cls.save_user_meomry, cls.search_user_memory, cls.search_policy, cls.add_product_to_cart,
                cls.remove_product_from_cart, cls.get_cart_tool, cls.place_order_tool, cls.add_delivery_address_tool, cls.add_payment_mode_tool,
                cls.order_details_by_id_tool, cls.cancel_order_tool]