import json
import time
from typing import Annotated, TypedDict

from cohere.manually_maintained.cohere_aws import rerank
from langchain_core.outputs import Generation
from langsmith import traceable
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition
from src.ai_manager.ai_manager import get_rails_config, tools_by_name, llm_chat, llm_with_tools, config
from src.ai_manager.db_manager import DBManager
from src.ai_manager.prompt import PRODUCT_SEARCH_SYSTEM_PROMPT
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from langgraph.cache.memory import InMemoryCache
from langgraph.types import CachePolicy

from uuid import uuid4

from src.ai_manager.utils import Utils


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
    def call_model(state: State):


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

        if intent == "product_info" and matched_product:
            model = llm_chat

        elif intent == "rag_node":
            model = llm_chat

        else:
            model = llm_with_tools



        ########################################################
        # 5. Build dynamic context
        ########################################################

        dynamic_context = []

        if state.get("retrieved_context"):
            dynamic_context.append(
                f"""
                Relevant Policy Information:
                {state["retrieved_context"]}

                Rules for using the above policy information:
                - Answer ONLY using what is explicitly stated above. Do not add details,
                  percentages, timelines, or conditions that are not written here.
                - The text above may contain MULTIPLE, UNRELATED policy sections (e.g. one
                  about missing items, another about general returns, another about refund
                  tiers). Identify which single section actually matches the user's
                  specific question, and IGNORE the other sections even if they mention
                  similar words like "refund" or "days".
                - Do NOT combine numbers or rules from one section with a different section.
                  For example, refund percentage tiers under "Return & Refund Policy" apply
                  only to standard product returns — do not apply them to missing items,
                  damaged items, or any other scenario unless explicitly stated there too.
                - If the matching section does not mention a refund percentage, timeline, or
                  resolution process, say so plainly instead of inferring one from elsewhere.
                """
            )

        if state.get("search_results"):

            dynamic_context.append(
                f"""
                    Latest Search Results {json.dumps(state["search_results"], indent=2)}
                    These are the latest search results.Use ONLY these products.
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

        #
        # Cart context (only when required)
        #
        if intent in ("add_to_cart", "get cart details"):

            if state.get("cart"):
                dynamic_context.append(
                    f"""Current Cart {json.dumps(state["cart"], indent=2)}"""
                    )

            if state.get("cart_details"):
                dynamic_context.append(
                    f"""Latest Cart Details {json.dumps(state["cart_details"], indent=2)}"""
                                )


        ########################################################
        # 6. Keep only latest human message
        ########################################################

        history = []

        for msg in reversed(state["messages"]):

            if isinstance(msg, HumanMessage):
                history.append(msg)
                break

        history.reverse()

        ########################################################
        # 7. Build prompt
        ########################################################

        system_prompt = PRODUCT_SEARCH_SYSTEM_PROMPT

        if dynamic_context:
            system_prompt += "\n\n" + "\n\n".join(dynamic_context)

        messages = [
            SystemMessage(content=system_prompt),
            *GraphOrchestrator.build_chat_history(state["messages"]),
        ]


        total_chars = 0

        for i, msg in enumerate(messages):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)

            total_chars += len(content)

        print("=" * 80)
        print(f"Total Prompt Characters : {total_chars}")
        print("=" * 80)

        response = model.invoke(messages)

        return {
            "messages": [response]
        }

    @staticmethod
    @traceable
    def custom_tool_node(state: State):

        last_ai = state["messages"][-1]

        outputs = []

        updates = {}

        for tool_call in last_ai.tool_calls:

            tool = tools_by_name[tool_call["name"]]

            tool_args = dict(tool_call["args"])

            # Inject graph state manually
            tool_args["state"] = state

            result = tool.invoke(tool_args)

            outputs.append(
                ToolMessage(
                    content=json.dumps(result),
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"]
                )
            )

            ###################################################
            # Save tool outputs into graph state
            ###################################################

            if tool_call["name"] == "search_product":

                updates["search_results"] = result["products"]
                updates["product_memory"] = result["product_memory"]
                updates["search_completed"] = True

            elif tool_call["name"] == "add_product_to_cart":

                updates["cart"] = result["data"]

            elif tool_call["name"] == "get_cart":

                updates["cart_details"] = result["data"]

        return {
            "messages": outputs,
            **updates
        }

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
    def memory_write_node(state: State):

        query = state["messages"][-1].content

        result = DBManager.insert_into_mem0_db(messages=query, customer_id=config["configurable"]["thread_id"])
        #
        # retrived_messages = DBManager.retrieve_from_mem0_db(customer_id=config["configurable"]["thread_id"])

        print("result of memory write :", result)

        # print("retrived_messages from mem0 database:", retrived_messages)



        return {
            "memory_results": result
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
    def create_graph_builder():

        graph = StateGraph(State)

    # -----------------------------
    # Add nodes FIRST
    # -----------------------------

        graph.add_node("rails", GraphOrchestrator.guardrails_node)

        graph.add_node("intent_router", GraphOrchestrator.intent_router_node)

        graph.add_node("product_memory_router", GraphOrchestrator.product_memory_router_node)

        graph.add_node("agent", GraphOrchestrator.call_model)

        graph.add_node("tools", GraphOrchestrator.custom_tool_node, cache_policy=CachePolicy(ttl=240))

        graph.add_node("product_not_found", GraphOrchestrator.product_not_found_node)

        graph.add_node("memory_write", GraphOrchestrator.memory_write_node)

        graph.add_node("rag_node", GraphOrchestrator.rag_node)

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

        graph.add_edge(
            "rag_node",
            "agent"
        )
        cache = InMemoryCache()
        checkpointer = DBManager.get_checkpointer()
        graph_builder = graph.compile(checkpointer=checkpointer, cache=cache)

        print("in memory cache", cache._cache)

        return graph_builder

def get_graph():
    return GraphOrchestrator.create_graph_builder()