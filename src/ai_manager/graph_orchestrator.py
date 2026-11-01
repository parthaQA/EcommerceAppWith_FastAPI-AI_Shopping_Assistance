import asyncio
import json
from typing import Annotated, TypedDict
from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langsmith import traceable
from langchain_core.messages import SystemMessage, BaseMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from pydantic import ValidationError

from src.ai_manager.ai_manager import get_rails_config, llm_with_tools, tools
from src.ai_manager.dtos import ToolResult
from src.ai_manager.prompt import PRODUCT_SEARCH_SYSTEM_PROMPT, OFF_TOPIC_REPLY
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from psycopg_pool import AsyncConnectionPool

from src.ai_manager.settings import AISettings
from src.ai_manager.utils import Utils
from src.utils.settings import settings

import logging

logger = logging.getLogger(__name__)

class State(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]
    mobile: str
    location: str
    search_results: list[dict]
    cart: dict
    product_memory: dict
    cart_details: dict
    search_completed: bool
    guardrail_blocked: bool
    requested_product: dict
    retrieved_context: str
    retrieved_documents: list
    memory_results: dict


class GraphOrchestrator:
    _pool: AsyncConnectionPool | None = None
    _graph = None


    # -------------------------------------------------------
    # Agent Node
    # -------------------------------------------------------
    @staticmethod
    @traceable
    async def guardrails_node(state: State):
        reset = {"guardrail_blocked": False, "search_completed": False, "retrieved_context": ""}

        print("state messages :", state["messages"])
        #current human message or query
        query = state["messages"][-1].content.strip()

        print("Guardrails Node: Last human message:", query)

        #last ai message
        last_ai_text = ""
        for m in reversed(state["messages"][:-1]):
            if isinstance(m, AIMessage) and str(m.content).strip():
                print("Guardrails Node: Last AI message:", m.content)
                last_ai_text = str(m.content)[:300]
                break

        rail_messages = []
        if last_ai_text:
            rail_messages.append({"role": "assistant", "content": last_ai_text})
        rail_messages.append({"role": "user", "content": query})

        print("Guardrails Node: Rail messages:", rail_messages)

        result = await get_rails_config().generate_async(
            messages=rail_messages,
            options={"rails": ["input"]},
        )

        print("Guardrails Node: Rails result:", result)
        print("Guardrails Node: Rails result response:", result.response)

        # A blocked message comes back as the refusal text; an allowed one comes back empty
        reply = ""
        if result.response:
            first = result.response[0]
            reply = (first.get("content", "") if isinstance(first, dict) else str(first)) or ""

        reply_text = reply.strip()
        print("Guardrails Node: reply text message :", reply_text)
        print("Guardrails Node: reply text type:", type(reply_text))
        # Allowed messages come back as an echo of the input; blocked ones come back as the refusal text.
        blocked = bool(reply_text and reply_text != query.strip())

        print("Guardrails Node: blocked message:", blocked)

        if blocked:
            return {
                "messages": [AIMessage(content=OFF_TOPIC_REPLY)],
                "guardrail_blocked": True,
            }

        return reset

    @staticmethod
    def guardrail_router(state: State):

        if state.get("guardrail_blocked"):
            return "blocked"

        return "allowed"


    @staticmethod
    @traceable
    async def call_model(state: State, config: RunnableConfig):
        # Current question
        question = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                question = msg.content.lower()
                break

        # Matching product from memory
        matched_product = None
        for product in (state.get("product_memory") or {}).values():
            name = (product.get("name") or "").lower()
            if name and name in question:
                matched_product = product
                break

        model = llm_with_tools.bind()

        # Dynamic context
        dynamic_context = []

        if state.get("retrieved_context"):
            dynamic_context.append(
                "Relevant Policy Information:\n"
                f"{state['retrieved_context']}\n\n"
                "Answer only from this policy text. If it doesn't cover the question, say so."
            )

        if state.get("search_results"):
            dynamic_context.append(
                f"""Latest Search Results {json.dumps(state["search_results"], indent=2)}
                These are the latest search results. Use ONLY these products.
                Do not search again unless the user asks for a different product."""
            )
        elif matched_product:
            dynamic_context.append(
                f"""Current Product {json.dumps(matched_product, indent=2)}
                This product already exists in memory. Reuse this information.
                Do not search again."""
            )

        if state.get("memory_results"):
            dynamic_context.append(
                f"User memory (use for personalization):\n"
                f"{json.dumps(state['memory_results'], indent=2, default=str)}"
            )

        if state.get("cart"):
            dynamic_context.append(f"Current Cart {json.dumps(state['cart'], indent=2)}")

        if state.get("cart_details"):
            dynamic_context.append(f"Latest Cart Details {json.dumps(state['cart_details'], indent=2)}")

        # Prompt
        system_prompt = PRODUCT_SEARCH_SYSTEM_PROMPT
        if dynamic_context:
            system_prompt += "\n\n" + "\n\n".join(dynamic_context)

        messages = [
            SystemMessage(content=system_prompt),
            *Utils.build_chat_history(state["messages"]),
        ]

        response = await model.ainvoke(messages, config)
        return {"messages": [response]}

    @staticmethod
    @traceable
    async def custom_tool_node(state: State, config: RunnableConfig):
        tools_by_name = {t.name: t for t in tools}
        print("tools by name :", tools_by_name)
        last_ai = state["messages"][-1]
        print("Last AI message:", last_ai)


        outputs: list[ToolMessage] = []
        updates: dict = {}

        for tool_call in last_ai.tool_calls:
            tool_name = tool_call["name"]
            tool = tools_by_name.get(tool_name)

            if tool is None:

                result = Utils.capture_error("UNKNOWN_TOOL", f"Tool '{tool_name}' does not exist.")
            else :

                call = {
                **tool_call,
                "type": "tool_call",
                "args": {**tool_call["args"], "state": state},
                }

                try:
                    raw_result = await asyncio.wait_for(tool.ainvoke(call, config), timeout=20)

                    print("result of tool :", raw_result)

                    content = raw_result.content if isinstance(raw_result, ToolMessage) else raw_result
                    print("content of tool", content)
                    if isinstance(content, str):
                        content = json.loads(content)
                    result = ToolResult.model_validate(content)

                except asyncio.TimeoutError:
                    result = Utils.capture_error("TIMEOUT", "That took too long. Please try again.")
                except (json.JSONDecodeError, ValidationError):
                    # the tool did not return the ToolResult shape
                    result = Utils.capture_error("INVALID_RESPONSE", "Something went wrong. Please try again.")
                except Exception:
                    result = Utils.capture_error("TOOL_FAILURE", "Something went wrong. Please try again.")


            ok = result.success

            # ---- every tool call gets exactly one ToolMessage; `internal` is excluded ----
            outputs.append(ToolMessage(
                content=result.model_dump_json(exclude={"internal"}, exclude_none=True),
                tool_call_id=tool_call["id"],
                name=tool_name,
                status="success" if ok else "error",
            ))

            # ---- state is updated only on success ----
            if not ok:
                continue

            try:
                if tool_name == "search_product":
                    new_products = result.internal.get("product_memory")
                    if not new_products:
                        continue

                    # read from updates first so two searches in one turn merge
                    base = updates.get("product_memory", state.get("product_memory") or {})
                    memory = {**base, **new_products}

                    # more than 5 products: reset, and keep only this search's products
                    if len(memory) > 5:
                        memory = new_products

                    updates["search_results"] = result.internal.get("search_results", [])
                    updates["product_memory"] = memory
                    updates["search_completed"] = True

                elif tool_name == "add_product_to_cart":
                    updates["cart"] = result.data

                elif tool_name == "get_cart_tool":
                    updates["cart_details"] = result.data

                elif tool_name == "search_user_memory":
                    updates["memory_results"] = result.data

                elif tool_name == "search_policy":
                    updates["retrieved_context"] = result.data or ""

            except Exception:
                logger.exception("State update failed for tool %s", tool_name)

        return {"messages": outputs, **updates}

    @staticmethod
    def after_tool_router(state: State):
        if state.get("search_completed") and not state.get("search_results"):
            return "not_found"
        return "agent"


    @staticmethod
    @traceable
    def product_not_found_node(state: State):
        return {
            "messages": [
                AIMessage(
                    content=(
                        "I couldn't find any matching products. "
                        "Would you like to search again?"
                    )
                )
            ]
        }


    @staticmethod
    def create_graph_builder(checkpointer=None):
        graph = StateGraph(State)

        # -----------------------------
        # Nodes
        # -----------------------------
        graph.add_node("rails", GraphOrchestrator.guardrails_node)
        graph.add_node("agent", GraphOrchestrator.call_model)
        graph.add_node("tools", GraphOrchestrator.custom_tool_node)
        graph.add_node("product_not_found", GraphOrchestrator.product_not_found_node)

        # -----------------------------
        # Edges
        # -----------------------------
        graph.add_edge(START, "rails")

        graph.add_conditional_edges(
            "rails",
            GraphOrchestrator.guardrail_router,
            {"blocked": END, "allowed": "agent"},
        )

        graph.add_conditional_edges(
            "agent",
            tools_condition,
            {"tools": "tools", "__end__": END},
        )

        graph.add_conditional_edges(
            "tools",
            GraphOrchestrator.after_tool_router,
            {"agent": "agent", "not_found": "product_not_found"},
        )

        graph.add_edge("product_not_found", END)

        return graph.compile(checkpointer=checkpointer)



    @classmethod
    async def acreate_graph_builder(cls):
        if cls._graph is not None:
            return cls._graph

        cls._pool = AsyncConnectionPool(
            conninfo=settings.DB_CONNECTION_PSYCOPG,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            )
        await cls._pool.open()

        checkpointer = AsyncPostgresSaver(cls._pool)
        await checkpointer.setup()

        cls._graph = cls.create_graph_builder(checkpointer=checkpointer)
        return cls._graph

    @classmethod
    async def aclose(cls) -> None:
        if cls._pool is not None:
            await cls._pool.close()
        cls._pool = None
        cls._graph = None

    @staticmethod
    async def get_graph():
        return await GraphOrchestrator.acreate_graph_builder()