import asyncio
import sys
from pathlib import Path
from pprint import pprint

from src.ai_manager.graph_orchestrator import GraphOrchestrator

# streamlit_app.py

# Fast_API/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from src.customers.controller import CustomerController
from src.customers.dtos import CustomerLoginSchema
from src.utils.db import Local_Session
from src.ai_manager.ai_manager import login_response, db
from src.ai_manager.ai_manager import config
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


class StreamlitShoppingAssistant:
    """
    Skeleton application.

    Replace the TODO sections with your existing graph code
    (call_model, custom_tool_node, graph_builder, etc.).
    """

    def __init__(self):
        st.set_page_config(layout="wide", page_title="Shopping Assistant")

        # -------------------------
        # Session Initialization
        # -------------------------

        if "logged_in" not in st.session_state:
            st.session_state.logged_in = False

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        if "first_turn" not in st.session_state:
            st.session_state.first_turn = True

        # Persistent shopping context across Streamlit reruns / user turns.
        # This is separate from the temporary LangGraph input state.
        if "shopping_state" not in st.session_state:
            st.session_state.shopping_state = {
                "customer_id": None,
                "mobile": None,
                "access_token": None,
                "refresh_token": None,
                "location": "6.9270786%2C79.861243",
                "product_memory": {},
                "search_results": [],
                "search_completed": False,
                "cart": None,
            }

        if "debug" not in st.session_state:
            st.session_state.debug = {
                "turns": [],
                "current_turn": {},
                "graph_state": {},
                "events": [],
                "messages": [],
                "tool_requests": [],
                "tool_responses": [],
                "llm_responses": [],
                "timings": [],
                "history": [],
                "errors": [],
                "graph_execution_ms": 0,
            }

        ss = st.session_state
        ss.setdefault("logged_in", False)
        ss.setdefault("chat_history", [])
        ss.setdefault("logs", [])
        ss.setdefault("state", {})
        ss.setdefault("events", [])
        ss.setdefault("tool_calls", [])
        ss.setdefault("usage", {})

    def sidebar(self):
        with st.sidebar:
            st.header("Configuration")
            st.selectbox("Model", ["llama3.1:8b"])
            st.slider("Temperature",0.0,1.0,0.5)
            st.text_input("Thread Id",login_response.get("customer_id"))
            if st.button("Clear Chat"):
                st.session_state.chat_history = []
                st.session_state.first_turn = True

                # Clear conversation-specific shopping context as well.
                if st.session_state.logged_in:
                    ss = st.session_state
                    ss.shopping_state["product_memory"] = {}
                    ss.shopping_state["search_results"] = []
                    ss.shopping_state["search_completed"] = False
                    ss.shopping_state["cart"] = None

                # Clear debug history.
                st.session_state.debug = {
                    "turns": [],
                    "current_turn": {},
                    "graph_state": {},
                    "events": [],
                    "messages": [],
                    "tool_requests": [],
                    "tool_responses": [],
                    "llm_responses": [],
                    "timings": [],
                    "history": [],
                    "errors": [],
                    "graph_execution_ms": 0,
                }
                st.rerun()

    def login(self):
        st.title("Shopping Assistant")
        col1, col2 = st.columns(2)

        mobile = col1.text_input(
            "Mobile Number",
            placeholder="8828162737"
        )

        otp = col2.text_input(
            "OTP",
            type="password",
            placeholder="Enter OTP"
        )
        customer_controller = CustomerController()
        if st.button("Login"):
            async def _login():
                async with Local_Session() as db:
                    return await customer_controller.customer_login_internal(
                        body=CustomerLoginSchema(
                            mobile=int(mobile),
                            password=otp,
                        ),
                        db=db,
                    )

            login_response = asyncio.run(_login())

            st.session_state.logged_in = True

            st.session_state.customer_id = login_response["customer_id"]
            st.session_state.mobile = login_response["mobile"]
            st.session_state.access_token = login_response["access_token"]
            st.session_state.refresh_token = login_response["refresh_token"]

            # Persistent shopping context. Do not reset product_memory on every turn.
            st.session_state.shopping_state = {
                "customer_id": login_response["customer_id"],
                "mobile": login_response["mobile"],
                "access_token": login_response["access_token"],
                "refresh_token": login_response["refresh_token"],
                "location": "6.9270786%2C79.861243",
                "product_memory": {},
                "search_results": [],
                "search_completed": False,
                "cart": None,
            }

            # Keep the currently persisted state visible in the old State tab/API.
            st.session_state.state = dict(st.session_state.shopping_state)

            st.success("Login Successful")
            st.rerun()

    def debug_panel(self):
        tabs = st.tabs([
            "Current State",
            "All Turns",
            "Messages",
            "Tools",
            "LLM",
            "Events",
            "Timing",
            "History",
        ])

        with tabs[0]:
            st.subheader("Persistent Shopping State")
            st.json(st.session_state.shopping_state)

            st.subheader("Current Graph State")
            st.json(st.session_state.debug.get("graph_state", {}))

        with tabs[1]:
            st.json(st.session_state.debug.get("turns", []))

        with tabs[2]:
            st.json(st.session_state.debug.get("messages", []))

        with tabs[3]:
            st.subheader("Tool Requests")
            st.json(st.session_state.debug.get("tool_requests", []))

            st.subheader("Tool Responses")
            st.json(st.session_state.debug.get("tool_responses", []))

        with tabs[4]:
            st.json(st.session_state.debug.get("llm_responses", []))

        with tabs[5]:
            st.json(st.session_state.debug.get("events", []))

        with tabs[6]:
            st.metric(
                "Last Graph Execution",
                f'{st.session_state.debug.get("graph_execution_ms", 0)} ms',
            )
            st.json(st.session_state.debug.get("timings", []))

        with tabs[7]:
            st.json(st.session_state.debug.get("history", []))

    def chat(self):

        import time

        left, right = st.columns([2, 1])

        # ==========================================================
        # LEFT PANEL - CHAT
        # ==========================================================


        with left:

            st.title("🛒 Shopping Assistant")

            # Previous Chat
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            query = st.chat_input("Ask me anything...")

            if query:

                st.session_state.chat_history.append({
                    "role": "user",
                    "content": query
                })

                with st.chat_message("user"):
                    st.markdown(query)

                ########################################################
                # Build Graph Input State
                #
                # IMPORTANT:
                # Never recreate product_memory/search_results as empty
                # dictionaries on every Streamlit rerun.
                ########################################################

                persistent = st.session_state.shopping_state

                state = {
                    "messages": [HumanMessage(content=query)],
                    "customer_id": persistent["customer_id"],
                    "mobile": persistent["mobile"],
                    "access_token": persistent["access_token"],
                    "refresh_token": persistent["refresh_token"],
                    "location": persistent["location"],
                    "product_memory": dict(persistent.get("product_memory", {})),
                    "search_results": list(persistent.get("search_results", [])),
                    "search_completed": persistent.get("search_completed", False),
                    "cart": persistent.get("cart"),
                }

                # This is the exact state entering THIS graph execution.
                st.session_state.state = dict(state)

                assistant_response = ""

                ########################################################
                # Start a new debug turn, but DO NOT clear previous turns
                ########################################################

                turn_no = len(st.session_state.debug["turns"]) + 1

                turn_debug = {
                    "turn": turn_no,
                    "user_query": query,
                    "input_state": dict(state),
                    "events": [],
                    "messages": [],
                    "tool_requests": [],
                    "tool_responses": [],
                    "llm_responses": [],
                    "timings": [],
                    "errors": [],
                    "output_state": {},
                }

                st.session_state.debug["current_turn"] = turn_debug

                # These are the cumulative views across ALL turns.
                # Do not reset them here.
                graph_start = time.perf_counter()

                ########################################################
                # Execute Graph
                ########################################################

                # for event in graph_builder.stream(
                #         state,
                #         rails=rails,
                #         stream_mode="updates"
                # ):
                #     print("\n" + "=" * 100)
                #     print("RAW EVENT")
                #     print("=" * 100)
                #     pprint(event)

                placeholder = st.empty()
                text = ""

                if "graph_builder" not in st.session_state:
                    st.session_state.graph_builder = GraphOrchestrator.create_graph_builder()

                graph_builder = st.session_state.graph_builder

                print("graph_builder id:", id(st.session_state.graph_builder))

                for mode, data in graph_builder.stream(
                        state,
                        config=config,
                        stream_mode=["messages", "updates"],
                ):

                    ####################################################
                    # Token streaming
                    ####################################################
                    if mode == "messages":
                        chunk, metadata = data

                        if chunk.content:
                            text += chunk.content
                            placeholder.markdown(text)

                    ####################################################
                    # Node updates
                    ####################################################
                    elif mode == "updates":

                        event = data

                        print("\n" + "=" * 80)
                        print("RAW EVENT")
                        print("=" * 80)
                        pprint(event)

                        for node_name, node_output in event.items():

                            node_start = time.perf_counter()

                            print(f"\nNode: {node_name}")
                            print(f"Type: {type(node_output)}")
                            pprint(node_output)

                            ####################################################
                            # Save raw event for THIS turn
                            ####################################################

                            turn_debug["events"].append({
                                "node": node_name,
                                "output": node_output,
                            })

                            ####################################################
                            # Save messages / tool calls / LLM responses
                            ####################################################

                            if node_output and "messages" in node_output:

                                for msg in node_output["messages"]:

                                    message_debug = {
                                        "id": getattr(msg, "id", ""),
                                        "node": node_name,
                                        "type": type(msg).__name__,
                                        "content": getattr(msg, "content", ""),
                                        "tool_calls": getattr(msg, "tool_calls", None),
                                        "usage": getattr(msg, "usage_metadata", None),
                                        "metadata": getattr(msg, "response_metadata", None),
                                    }

                                    turn_debug["messages"].append(message_debug)

                                    if isinstance(msg, AIMessage):

                                        if msg.tool_calls:
                                            turn_debug["tool_requests"].append({
                                                "node": node_name,
                                                "response_id": msg.id,
                                                "tool_calls": msg.tool_calls,
                                                "usage": getattr(
                                                    msg, "usage_metadata", {}
                                                ),
                                                "metadata": getattr(
                                                    msg, "response_metadata", {}
                                                ),
                                            })

                                        else:
                                            if msg.content:
                                                assistant_response = msg.content

                                            turn_debug["llm_responses"].append({
                                                "node": node_name,
                                                "response_id": msg.id,
                                                "content": msg.content,
                                                "usage": getattr(
                                                    msg, "usage_metadata", {}
                                                ),
                                                "metadata": getattr(
                                                    msg, "response_metadata", {}
                                                ),
                                            })

                                    elif isinstance(msg, ToolMessage):

                                        turn_debug["tool_responses"].append({
                                            "node": node_name,
                                            "tool_call_id": msg.tool_call_id,
                                            "tool_name": msg.name,
                                            "response": msg.content,
                                        })

                            ####################################################
                            # Persist graph state updates immediately
                            #
                            # This is the important fix for product_memory.
                            ####################################################

                            if "product_memory" in node_output:
                                st.session_state.shopping_state["product_memory"] = (
                                    node_output["product_memory"]
                                )

                            if "search_results" in node_output:
                                st.session_state.shopping_state["search_results"] = (
                                    node_output["search_results"]
                                )

                            if "search_completed" in node_output:
                                st.session_state.shopping_state["search_completed"] = (
                                    node_output["search_completed"]
                                )

                            if "cart" in node_output:
                                st.session_state.shopping_state["cart"] = (
                                    node_output["cart"]
                                )

                            # Preserve any other top-level state values returned
                            # by the graph, except messages.
                            for key, value in node_output.items():
                                if key in {
                                    "messages",
                                    "product_memory",
                                    "search_results",
                                    "search_completed",
                                    "cart",
                                }:
                                    continue

                                st.session_state.shopping_state[key] = value

                            ####################################################
                            # Capture current graph/checkpoint state
                            ####################################################

                            try:
                                graph_state = graph_builder.get_state(config)

                                current_values = dict(graph_state.values)

                                st.session_state.debug["graph_state"] = {
                                    "values": current_values,
                                    "next": graph_state.next,
                                    "metadata": graph_state.metadata,
                                }

                                turn_debug["state_after_node"] = current_values

                            except Exception as e:
                                error = f"get_state failed: {e}"
                                turn_debug["errors"].append(error)
                                st.session_state.debug["errors"].append(error)

                            ####################################################
                            # Node timing
                            ####################################################

                            elapsed_ms = round(
                                (time.perf_counter() - node_start) * 1000,
                                2,
                            )

                            turn_debug["timings"].append({
                                "node": node_name,
                                "time_ms": elapsed_ms,
                            })

                ########################################################
                # Total Graph Time
                ########################################################

                st.session_state.debug["graph_execution_ms"] = round(
                    (time.perf_counter() - graph_start) * 1000,
                    2,
                )

                ########################################################
                # Final Graph / Checkpoint State
                ########################################################

                try:
                    final_graph_state = graph_builder.get_state(config)

                    final_values = dict(final_graph_state.values)

                    # Persist important cross-turn shopping state.
                    for key in [
                        "customer_id",
                        "mobile",
                        "access_token",
                        "refresh_token",
                        "location",
                        "product_memory",
                        "search_results",
                        "search_completed",
                        "cart",
                    ]:
                        if key in final_values:
                            st.session_state.shopping_state[key] = final_values[key]

                    st.session_state.state = dict(st.session_state.shopping_state)

                    st.session_state.debug["graph_state"] = {
                        "values": final_values,
                        "next": final_graph_state.next,
                        "metadata": final_graph_state.metadata,
                    }

                    turn_debug["output_state"] = dict(st.session_state.shopping_state)

                except Exception as e:
                    error = f"final get_state failed: {e}"
                    turn_debug["errors"].append(error)
                    st.session_state.debug["errors"].append(error)

                    # Still persist the state that was accumulated from updates.
                    st.session_state.state = dict(st.session_state.shopping_state)
                    turn_debug["output_state"] = dict(st.session_state.shopping_state)

                ########################################################
                # Checkpoint History
                ########################################################

                try:
                    turn_debug["history"] = []

                    for checkpoint in graph_builder.get_state_history(config):
                        turn_debug["history"].append({
                            "values": checkpoint.values,
                            "next": checkpoint.next,
                            "metadata": checkpoint.metadata,
                        })

                    st.session_state.debug["history"] = turn_debug["history"]

                except Exception as e:
                    turn_debug["errors"].append(f"history failed: {e}")

                ########################################################
                # Commit THIS turn to cumulative debug history
                ########################################################

                st.session_state.debug["turns"].append(turn_debug)

                # Flatten all debug information across all turns.
                st.session_state.debug["events"] = [
                    event
                    for turn in st.session_state.debug["turns"]
                    for event in turn.get("events", [])
                ]

                st.session_state.debug["messages"] = [
                    message
                    for turn in st.session_state.debug["turns"]
                    for message in turn.get("messages", [])
                ]

                st.session_state.debug["tool_requests"] = [
                    request
                    for turn in st.session_state.debug["turns"]
                    for request in turn.get("tool_requests", [])
                ]

                st.session_state.debug["tool_responses"] = [
                    response
                    for turn in st.session_state.debug["turns"]
                    for response in turn.get("tool_responses", [])
                ]

                st.session_state.debug["llm_responses"] = [
                    response
                    for turn in st.session_state.debug["turns"]
                    for response in turn.get("llm_responses", [])
                ]

                st.session_state.debug["timings"] = [
                    timing
                    for turn in st.session_state.debug["turns"]
                    for timing in turn.get("timings", [])
                ]

                ########################################################
                # Final AI Response
                ########################################################

                ########################################################
                # Final AI Response
                ########################################################

                with st.chat_message("assistant"):
                    st.markdown(assistant_response)

                st.session_state.chat_history.append({

                    "role": "assistant",

                    "content": assistant_response

                })

        # ==========================================================
        # RIGHT PANEL - DEBUG
        # ==========================================================

        with right:

            st.header("🐞 Debug")

            tabs = st.tabs([
                "State",
                "Turns",
                "Messages",
                "Tools",
                "LLM",
                "Events",
                "Timing",
                "History",
            ])

            with tabs[0]:
                st.subheader("Persistent State (next user message)")
                st.json(st.session_state.shopping_state)

                st.subheader("Last Graph State")
                st.json(st.session_state.debug.get("graph_state", {}))

            with tabs[1]:
                st.json(st.session_state.debug.get("turns", []))

            with tabs[2]:
                st.json(st.session_state.debug.get("messages", []))

            with tabs[3]:
                st.subheader("Tool Requests - All Turns")
                st.json(st.session_state.debug.get("tool_requests", []))

                st.subheader("Tool Responses - All Turns")
                st.json(st.session_state.debug.get("tool_responses", []))

            with tabs[4]:
                st.json(st.session_state.debug.get("llm_responses", []))

            with tabs[5]:
                st.json(st.session_state.debug.get("events", []))

            with tabs[6]:
                st.metric(
                    "Last Graph Execution",
                    f'{st.session_state.debug.get("graph_execution_ms", 0)} ms',
                )
                st.json(st.session_state.debug.get("timings", []))

            with tabs[7]:
                st.json(st.session_state.debug.get("history", []))


    def run(self):
        self.sidebar()
        if not st.session_state.logged_in:
            self.login()
        else:
            self.chat()

if __name__=="__main__":
    StreamlitShoppingAssistant().run()