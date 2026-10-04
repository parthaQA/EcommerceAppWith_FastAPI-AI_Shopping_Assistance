import json
import time
from typing import Annotated, TypedDict

from fastapi import HTTPException
from langchain_core.outputs import Generation
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langsmith import traceable
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from src.ai_manager.ai_manager import get_rails_config, llm_with_tools, build_chat_model, tools
from src.ai_manager.db_manager import DBManager
from src.ai_manager.prompt import PRODUCT_SEARCH_SYSTEM_PROMPT
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from langgraph.cache.memory import InMemoryCache
from psycopg_pool import AsyncConnectionPool
from src.ai_manager.utils import Utils
from src.utils.settings import settings

import logging

logger = logging.getLogger(__name__)

class State(TypedDict):

    messages: Annotated[list, add_messages]
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


    MAX_HISTORY=1

    # -------------------------------------------------------
    # Agent Node
    # -------------------------------------------------------
    @staticmethod
    @traceable
    def guardrails_node(state: State):

        query = None

        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                query = msg.content
                break

        if not query:
            return {
                "guardrail_blocked": False
            }

        result = get_rails_config().generate(
            messages=[
                {
                    "role": "user",
                    "content": query
                }
            ]
        )

        if isinstance(result, dict):
            assistant_reply = result.get("content", "")
        else:
            assistant_reply = str(result)

        if "[OFF_TOPIC]" in assistant_reply:
            clean_reply = assistant_reply.replace(
                "[OFF_TOPIC]",
                ""
            ).strip()

            return {
                "messages": [
                    AIMessage(content=clean_reply)
                ],
                "guardrail_blocked": True,
            }

        return {
            "guardrail_blocked": False
        }

    @staticmethod
    def guardrail_router(state: State):

        if state.get("guardrail_blocked"):
            return "blocked"

        return "allowed"

    @staticmethod
    def route_intent(state: State):
        start = time.perf_counter()
        query = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                query = msg.content.lower()
                break


        if any(word in query for word in [
            "price",
            "availability",
            "available",
            "stock",
            "quantity"
        ]):
            return "product_info"

        elif any(word in query for word in [
            "add to cart",
            "add",
        ]):
            return "add_to_cart"

        elif any(word in query for word in [
            "cart", "cart details"
        ]):
            return "get cart details"

        elif any(word in query for word in [
                 "remember", "preference", "save", "preferred", "store"]):
            return "memory_write"

        elif any(word in query for word in [
            "refund", "return", "policy", "terms and condition"]):
            return "rag_node"

        print(f"route_intent {time.perf_counter() - start:.2f}s")

        return "general"

    @staticmethod
    def product_memory_router_node(state: State):
        product_name = state["requested_product"]
        memory = state.get("product_memory", {})

        if not product_name:
            return "memory_not_found"

        if product_name.lower() in memory:
            return "memory_found"

        return "memory_not_found"

    @staticmethod
    @traceable
    def route_product_memory(state: State):

        question = state["messages"][-1].content.lower()

        product_memory = state.get("product_memory", {})

        print("\n========== PRODUCT MEMORY ROUTER ==========")
        print("Question :", question)
        print("Products in memory :", list(product_memory.keys()))

        # Check whether any stored product name appears in the question
        for product_name in product_memory.keys():

            if product_name.lower() in question:
                print(f"Memory HIT -> {product_name}")

                return "memory_hit"

        print("Memory MISS")

        return "memory_miss"



    @staticmethod
    def build_chat_history(messages):
        """
        Keep only recent Human/AI conversation.
        Ignore ToolMessages and empty AI tool-call messages.
        """
        history = []

        for msg in messages:

            if isinstance(msg, (HumanMessage, ToolMessage)):
                history.append(msg)

            elif isinstance(msg, AIMessage):
                if msg.content.strip():
                    history.append(msg)

        return history[-GraphOrchestrator.MAX_HISTORY:]

    @staticmethod
    @traceable
    async def call_model(state: State, config: RunnableConfig):  # 1. async + config

        ########################################################
        # 1. Intent
        ########################################################
        intent = GraphOrchestrator.route_intent(state)

        ########################################################
        # 2. Current question
        ########################################################
        question = ""
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                question = msg.content.lower()
                break

        ########################################################
        # 3. Find matching product
        ########################################################
        matched_product = None
        for _, product in state.get("product_memory", {}).items():
            if product["name"].lower() in question:
                matched_product = product
                break

        ########################################################
        # 4. Select model
        ########################################################
        if (intent == "product_info" and matched_product) or intent == "rag_node":
            model = build_chat_model()  # no tools bound
        else:
            model = llm_with_tools

        ########################################################
        # 5. Build dynamic context (unchanged)
        ########################################################
        dynamic_context = []

        if state.get("retrieved_context"):
            dynamic_context.append(
                f"""
                Relevant Policy Information:
                {state["retrieved_context"]}

                ... your existing policy rules text, unchanged ...
                """
            )

        if state.get("search_results"):
            dynamic_context.append(
                f"""
                Latest Search Results {json.dumps(state["search_results"], indent=2)}
                These are the latest search results. Use ONLY these products.
                Do not search again unless the user asks for a different product.
                """
            )
        elif matched_product:
            dynamic_context.append(
                f"""
                Current Product {json.dumps(matched_product, indent=2)}

                This product already exists in memory. Reuse this information.
                Do not search again."""
            )

        if intent in ("add_to_cart", "get cart details"):
            if state.get("cart"):
                dynamic_context.append(f"""Current Cart {json.dumps(state["cart"], indent=2)}""")
            if state.get("cart_details"):
                dynamic_context.append(f"""Latest Cart Details {json.dumps(state["cart_details"], indent=2)}""")

        ########################################################
        # 6. Build prompt
        ########################################################
        system_prompt = PRODUCT_SEARCH_SYSTEM_PROMPT
        if dynamic_context:
            system_prompt += "\n\n" + "\n\n".join(dynamic_context)

        messages = [
            SystemMessage(content=system_prompt),
            *GraphOrchestrator.build_chat_history(state["messages"]),
        ]

        total_chars = sum(
            len(m.content) if isinstance(m.content, str) else len(str(m.content))
            for m in messages
        )
        print("=" * 80)
        print(f"Total Prompt Characters : {total_chars}")
        print("=" * 80)

        ########################################################
        # 7. Call the model (async, with config so tokens stream)
        ########################################################
        response = await model.ainvoke(messages, config)  # 2 + 3

        return {"messages": [response]}

    @staticmethod
    @traceable
    async def custom_tool_node(state: State, config: RunnableConfig):
        tools_by_name = {t.name: t for t in tools}
        last_ai = state["messages"][-1]

        outputs: list[ToolMessage] = []
        updates: dict = {}

        for tool_call in last_ai.tool_calls:
            name = tool_call["name"]
            tool = tools_by_name.get(name)

            def error_message(payload: dict) -> ToolMessage:
                return ToolMessage(
                    content=json.dumps(payload),
                    tool_call_id=tool_call["id"],
                    name=name,
                    status="error",
                )

            if tool is None:
                logger.warning("LLM requested unknown tool: %s", name)
                outputs.append(error_message({"error": 404, "message": f"Unknown tool {name}"}))
                continue

            call = {
                **tool_call,
                "type": "tool_call",
                "args": {**tool_call["args"], "state": state},
            }

            try:
                result = await tool.ainvoke(call, config)
            except HTTPException as e:
                logger.warning("Tool %s failed: %s %s", name, e.status_code, e.detail)
                outputs.append(error_message({"error": e.status_code, "message": str(e.detail)}))
                continue
            except Exception:
                logger.exception("Unexpected error in tool %s", name)  # includes full traceback
                outputs.append(error_message({"error": 500, "message": "Something went wrong on our side"}))
                continue

            content = result.content if isinstance(result, ToolMessage) else result
            try:
                data = json.loads(content) if isinstance(content, str) else content
            except json.JSONDecodeError:
                data = {"result": content}
            if not isinstance(data, dict):
                data = {"result": data}

            outputs.append(ToolMessage(
                content=json.dumps(data.get("raw_response", data), default=str),
                tool_call_id=tool_call["id"],
                name=name,
            ))

            if name == "search_product":
                updates["search_results"] = data["search_results"]
                updates["product_memory"] = {
                    **updates.get("product_memory", {}),
                    **data["product_memory"],
                }
                updates["search_completed"] = True
            elif name == "add_product_to_cart":
                updates["cart"] = data["data"]
            elif name == "get_cart":
                updates["cart_details"] = data["data"]

        return {"messages": outputs, **updates}

    @staticmethod
    def after_tool_router(state: State):

        if (
                state.get("search_completed")
                and not state["search_results"]
        ):
            return "not_found"

        return "agent"

    #####################################################
    # Tools -> Agent
    #####################################################

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
    @traceable
    def intent_router_node(state: State):
        return state

    @staticmethod
    @traceable
    def memory_write_node(state: State, config: RunnableConfig):

        query = state["messages"][-1].content

        result = DBManager.insert_into_mem0_db(messages=query, customer_id=Utils.get_customer_id(config))
        #
        # retrived_messages = DBManager.retrieve_from_mem0_db(customer_id=config["configurable"]["thread_id"])

        print("result of memory write :", result)

        # print("retrived_messages from mem0 database:", retrived_messages)



        return {
            "memory_results": result
        }

    @staticmethod
    @traceable
    def memory_read_node(state: State, config: RunnableConfig):

        query = state["messages"][-1].content
        customer_id = Utils.get_customer_id(config)

        retrieved_messages = DBManager.retrieve_from_mem0_db(
            customer_id=customer_id,
            query=query
        )

        print("Memory search query:", query)
        print("Retrieved memories:", retrieved_messages)

        return {
            "memory_results": retrieved_messages
        }

    @staticmethod
    @traceable
    def rag_node(state: State):
        RERANK_THRESHOLD = 0.05
        EXPECTED_SCORE = 0.2
        embedding_model = DBManager.embedding_model.model_name
        K = 10
        rag_pipeline_version = Utils.get_rag_pipeline_version(
            score_threshold=EXPECTED_SCORE,
            rerank_threshold=RERANK_THRESHOLD,
            k=K,
            reranker=embedding_model)

        query = state["messages"][-1].content
        rewritten_query = DBManager.rewrite_query(state["messages"])
        cache = DBManager.get_rag_cache()

        eval_mode = state.get("eval_mode", False)  # NEW

        cached = None if eval_mode else cache.lookup(  # CHANGED — skip lookup entirely in eval_mode
            prompt=rewritten_query,
            llm_string=rag_pipeline_version
        )
        if cached:
            cached_result = cached[0].text
            print("RAG cache HIT — skipping vector search + rerank")
            return {
                "messages": [
                    AIMessage(content=cached_result)
                ],
                "retrieved_context": cached_result,  # NEW — kept for consistency
                "retrieved_chunks": [cached_result],  # NEW — list form
            }

        print("RAG cache MISS — running full retrieval pipeline")

        vector_store = DBManager.setup_vector_store()

        result = vector_store.similarity_search_with_relevance_scores(
            query=rewritten_query,
            k=K
        )

        filtered = [doc for doc, score in result if score >= EXPECTED_SCORE]

        rerank_doc = Utils.rerank_query_response(query=query, document=filtered)

        top_results = [r for r in rerank_doc.results if r.relevance_score >= RERANK_THRESHOLD]

        if not top_results:
            top_results = rerank_doc.results[:2]

        for result in rerank_doc.results:
            print(f"Score: {result.relevance_score:.4f} | Doc: {filtered[result.index]}")
            print("all the rerank docs :", result.document)
            print("all the rerank docs texts :", result.document.text)

        top_chunks = [  # NEW — list form, built once
            f"[{filtered[r.index].metadata.get('category', 'unknown')}] {filtered[r.index].page_content}"
            for r in top_results
        ]

        retrieved_context = "\n\n".join(top_chunks)  # CHANGED — now built from top_chunks

        if not eval_mode:
            cache.update(
                prompt=rewritten_query,
                llm_string=rag_pipeline_version,
                return_val=[Generation(text=retrieved_context)],
            )

        return {
            "original_query": query,
            "rewritten_query": rewritten_query,
            "retrieved_context": retrieved_context,
            "retrieved_chunks": top_chunks,
        }


    @staticmethod
    def create_graph_builder(checkpointer=None):

        graph = StateGraph(State)

    # -----------------------------
    # Add nodes FIRST
    # -----------------------------

        graph.add_node("rails", GraphOrchestrator.guardrails_node)

        graph.add_node("intent_router", GraphOrchestrator.intent_router_node)

        graph.add_node("product_memory_router", GraphOrchestrator.product_memory_router_node)

        graph.add_node("agent", GraphOrchestrator.call_model)

        graph.add_node("tools", GraphOrchestrator.custom_tool_node)

        graph.add_node("product_not_found", GraphOrchestrator.product_not_found_node)

        graph.add_node("memory_write", GraphOrchestrator.memory_write_node)

        graph.add_node("rag_node", GraphOrchestrator.rag_node)

        graph.add_node(
            "memory_read",
            GraphOrchestrator.memory_read_node
        )

        # -----------------------------
        # Now connect them
        # -----------------------------

        graph.add_edge(
        START,
        "rails"
        )

        graph.add_conditional_edges(
        "rails",
            GraphOrchestrator.guardrail_router,
        {
            "blocked": END,
            "allowed": "intent_router",
                }
        )

        graph.add_conditional_edges(
        "intent_router",
            GraphOrchestrator.route_intent,
        {
            "product_info": "product_memory_router",
            "add_to_cart": "agent",
            "get cart details": "agent",
            "general": "agent",
            "memory_write": "memory_write",
            "memory_read": "memory_read",
            "rag_node": "rag_node",
            }
        )

        graph.add_conditional_edges(
        "product_memory_router",
            GraphOrchestrator.route_product_memory,
        {
            "memory_hit": "agent",
            "memory_miss": "agent",
            }
        )

        graph.add_conditional_edges(
        "agent",
            tools_condition,
        {
            "tools": "tools",
            "__end__": END,
            }
        )

        graph.add_conditional_edges(
        "tools",
            GraphOrchestrator.after_tool_router,
        {
            "agent": "agent",
            "not_found": "product_not_found",
            }
        )

        graph.add_edge(
        "product_not_found",
        END
        )

        graph.add_edge(
            "memory_write",
            "agent"
        )

        graph.add_edge("memory_read", "agent")

        graph.add_edge(
            "rag_node",
            "agent"
        )
        cache = InMemoryCache()

        print("in memory cache", cache._cache)

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