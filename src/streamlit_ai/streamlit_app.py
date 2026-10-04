# streamlit_app.py
import asyncio
import sys
import threading
import time
from pathlib import Path
from pprint import pprint

# Fast_API/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.ai_manager.agent_config import RunnableConfigBuilder
from src.ai_manager.graph_orchestrator import GraphOrchestrator
from src.customers.controller import CustomerController
from src.customers.dtos import CustomerLoginSchema
from src.utils.db import Local_Session

# Name of the graph node that calls the LLM (used to filter token streaming)
LLM_NODE = "agent"
DEFAULT_LOCATION = "6.9270786%2C79.861243"

# State keys persisted across turns for the debug panel
PERSISTED_KEYS = [
    "location",
    "product_memory",
    "search_results",
    "search_completed",
    "cart",
]


# ======================================================================
# Shared event loop
# Streamlit reruns the script on every interaction and is sync, but the
# DB engine, checkpointer pool and async tools must live on ONE loop.
# ======================================================================
@st.cache_resource
def _get_loop() -> asyncio.AbstractEventLoop:
    # 1. Enforce SelectorEventLoopPolicy on Windows before creating the loop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


def run_async(coro):
    """Run a coroutine on the shared loop and block for the result."""
    return asyncio.run_coroutine_threadsafe(coro, _get_loop()).result()


_DONE = object()


def stream_sync(async_gen):
    """Iterate an async generator from sync Streamlit code."""

    async def _next():
        try:
            return await async_gen.__anext__()
        except StopAsyncIteration:
            return _DONE

    while True:
        item = run_async(_next())
        if item is _DONE:
            break
        yield item


async def _collect_history(graph, cfg):
    return [c async for c in graph.aget_state_history(cfg)]


def _empty_debug() -> dict:
    return {
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


def _empty_shopping_state(login_response: dict | None = None) -> dict:
    return {
        "location": DEFAULT_LOCATION,
        "product_memory": {},
        "search_results": [],
        "search_completed": False,
        "cart": None,
    }


class StreamlitShoppingAssistant:
    def __init__(self):
        st.set_page_config(layout="wide", page_title="Shopping Assistant")

        ss = st.session_state
        ss.setdefault("logged_in", False)
        ss.setdefault("chat_history", [])
        ss.setdefault("first_turn", True)
        ss.setdefault("customer_id", None)
        ss.setdefault("mobile", None)
        ss.setdefault("shopping_state", _empty_shopping_state())
        ss.setdefault("debug", _empty_debug())
        ss.setdefault("state", {})

    # ------------------------------------------------------------------
    # Config (built per turn from the logged-in user)
    # ------------------------------------------------------------------
    def _build_config(self):
        return RunnableConfigBuilder.build_config(
            customer_id=st.session_state.customer_id,
            mobile=st.session_state.mobile,
        )

    def _get_graph(self):
        """Create the compiled graph once, on the shared loop."""
        if "graph_builder" not in st.session_state:
            st.session_state.graph_builder = run_async(
                GraphOrchestrator.create_graph_builder()
            )
        return st.session_state.graph_builder

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def sidebar(self):
        with st.sidebar:
            st.header("Configuration")
            st.selectbox("Model", ["llama3.1:8b"])
            st.slider("Temperature", 0.0, 1.0, 0.5)
            st.text_input(
                "Thread Id",
                str(st.session_state.get("customer_id") or ""),
                disabled=True,
            )

            if st.button("Clear Chat"):
                st.session_state.chat_history = []
                st.session_state.first_turn = True
                st.session_state.shopping_state = _empty_shopping_state()
                st.session_state.debug = _empty_debug()
                st.rerun()

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def login(self):
        st.title("Shopping Assistant")
        col1, col2 = st.columns(2)

        mobile = col1.text_input("Mobile Number", placeholder="8828162737")
        otp = col2.text_input("OTP", type="password", placeholder="Enter OTP")

        if st.button("Login"):
            customer_controller = CustomerController()

            async def _login():
                async with Local_Session() as db:
                    return await customer_controller.customer_login_internal(
                        body=CustomerLoginSchema(mobile=int(mobile), password=otp),
                        db=db,
                    )

            login_response = run_async(_login())

            ss = st.session_state
            ss.logged_in = True
            ss.customer_id = str(login_response["customer_id"])
            ss.mobile = login_response["mobile"]
            # Tokens are kept only in the Streamlit session, NOT in graph state
            ss.access_token = login_response["access_token"]
            ss.refresh_token = login_response["refresh_token"]

            ss.shopping_state = _empty_shopping_state()
            ss.state = dict(ss.shopping_state)

            st.success("Login Successful")
            st.rerun()

    # ------------------------------------------------------------------
    # Debug panel (right column)
    # ------------------------------------------------------------------
    def render_debug(self):
        dbg = st.session_state.debug

        st.header("🐞 Debug")
        tabs = st.tabs(
            ["State", "Turns", "Messages", "Tools", "LLM", "Events", "Timing", "History"]
        )

        with tabs[0]:
            st.subheader("Persistent State (next user message)")
            st.json(st.session_state.shopping_state)
            st.subheader("Last Graph State")
            st.json(dbg.get("graph_state", {}), expanded=False)

        with tabs[1]:
            st.json(dbg.get("turns", []), expanded=False)

        with tabs[2]:
            st.json(dbg.get("messages", []), expanded=False)

        with tabs[3]:
            st.subheader("Tool Requests - All Turns")
            st.json(dbg.get("tool_requests", []), expanded=False)
            st.subheader("Tool Responses - All Turns")
            st.json(dbg.get("tool_responses", []), expanded=False)

        with tabs[4]:
            st.json(dbg.get("llm_responses", []), expanded=False)

        with tabs[5]:
            st.json(dbg.get("events", []), expanded=False)

        with tabs[6]:
            st.metric("Last Graph Execution", f'{dbg.get("graph_execution_ms", 0)} ms')
            st.json(dbg.get("timings", []))

        with tabs[7]:
            st.json(dbg.get("history", []), expanded=False)

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
    def chat(self):
        left, right = st.columns([2, 1])

        with left:
            st.title("🛒 Shopping Assistant")

            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

            query = st.chat_input("Ask me anything...")
            if query:
                self._handle_query(query)

        with right:
            self.render_debug()

    def _handle_query(self, query: str):
        ss = st.session_state
        ss.chat_history.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        persistent = ss.shopping_state

        # Graph input: only the new message + location.
        # customer_id / tokens come from config and never enter graph state.
        # product_memory, search_results and cart are restored by the
        # checkpointer for the same thread_id.
        state = {
            "messages": [HumanMessage(content=query)],
            "location": persistent["location"],
        }
        ss.state = dict(state)

        turn_debug = {
            "turn": len(ss.debug["turns"]) + 1,
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
        ss.debug["current_turn"] = turn_debug

        graph = self._get_graph()
        config = self._build_config()  # one config per turn, reused below

        placeholder = st.empty()
        text = ""
        assistant_response = ""
        graph_start = time.perf_counter()

        # ---------------- Execute graph ----------------
        for mode, data in stream_sync(
            graph.astream(
                state,
                config=config,
                stream_mode=["messages", "updates"],
            )
        ):
            # ---- Token streaming (LLM node only) ----
            if mode == "messages":
                chunk, metadata = data
                if chunk.content and metadata.get("langgraph_node") == LLM_NODE:
                    text += chunk.content
                    placeholder.markdown(text)

            # ---- Node updates ----
            elif mode == "updates":
                print("\n" + "=" * 80)
                print("RAW EVENT")
                print("=" * 80)
                pprint(data)

                for node_name, node_output in data.items():
                    node_start = time.perf_counter()
                    node_output = node_output or {}

                    turn_debug["events"].append(
                        {"node": node_name, "output": node_output}
                    )

                    self._record_messages(node_name, node_output, turn_debug)
                    if turn_debug.get("last_final_text"):
                        assistant_response = turn_debug.pop("last_final_text")

                    self._persist_updates(node_output)

                    # Snapshot of checkpoint state after this node
                    try:
                        gs = run_async(graph.aget_state(config))
                        current_values = dict(gs.values)
                        ss.debug["graph_state"] = {
                            "values": current_values,
                            "next": gs.next,
                            "metadata": gs.metadata,
                        }
                        turn_debug["state_after_node"] = current_values
                    except Exception as e:
                        err = f"get_state failed: {e}"
                        turn_debug["errors"].append(err)
                        ss.debug["errors"].append(err)

                    turn_debug["timings"].append(
                        {
                            "node": node_name,
                            "time_ms": round(
                                (time.perf_counter() - node_start) * 1000, 2
                            ),
                        }
                    )

        ss.debug["graph_execution_ms"] = round(
            (time.perf_counter() - graph_start) * 1000, 2
        )

        # ---------------- Final checkpoint state ----------------
        try:
            final_state = run_async(graph.aget_state(config))
            final_values = dict(final_state.values)

            for key in PERSISTED_KEYS:
                if key in final_values:
                    ss.shopping_state[key] = final_values[key]

            ss.state = dict(ss.shopping_state)
            ss.debug["graph_state"] = {
                "values": final_values,
                "next": final_state.next,
                "metadata": final_state.metadata,
            }
        except Exception as e:
            err = f"final get_state failed: {e}"
            turn_debug["errors"].append(err)
            ss.debug["errors"].append(err)
            ss.state = dict(ss.shopping_state)

        turn_debug["output_state"] = dict(ss.shopping_state)

        # ---------------- Checkpoint history ----------------
        try:
            checkpoints = run_async(_collect_history(graph, config))
            turn_debug["history"] = [
                {"values": c.values, "next": c.next, "metadata": c.metadata}
                for c in checkpoints
            ]
            ss.debug["history"] = turn_debug["history"]
        except Exception as e:
            turn_debug["errors"].append(f"history failed: {e}")

        # ---------------- Commit turn + flatten cumulative views ----------------
        ss.debug["turns"].append(turn_debug)
        for key in (
            "events",
            "messages",
            "tool_requests",
            "tool_responses",
            "llm_responses",
            "timings",
        ):
            ss.debug[key] = [
                item for turn in ss.debug["turns"] for item in turn.get(key, [])
            ]

        # ---------------- Final answer ----------------
        final_text = assistant_response or text
        placeholder.empty()
        with st.chat_message("assistant"):
            st.markdown(final_text)
        ss.chat_history.append({"role": "assistant", "content": final_text})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _record_messages(node_name: str, node_output: dict, turn_debug: dict):
        for msg in node_output.get("messages", []) or []:
            turn_debug["messages"].append(
                {
                    "id": getattr(msg, "id", ""),
                    "node": node_name,
                    "type": type(msg).__name__,
                    "content": getattr(msg, "content", ""),
                    "tool_calls": getattr(msg, "tool_calls", None),
                    "usage": getattr(msg, "usage_metadata", None),
                    "metadata": getattr(msg, "response_metadata", None),
                }
            )

            if isinstance(msg, AIMessage):
                entry = {
                    "node": node_name,
                    "response_id": msg.id,
                    "usage": getattr(msg, "usage_metadata", {}),
                    "metadata": getattr(msg, "response_metadata", {}),
                }
                if msg.tool_calls:
                    turn_debug["tool_requests"].append(
                        {**entry, "tool_calls": msg.tool_calls}
                    )
                else:
                    if msg.content:
                        turn_debug["last_final_text"] = msg.content
                    turn_debug["llm_responses"].append(
                        {**entry, "content": msg.content}
                    )

            elif isinstance(msg, ToolMessage):
                turn_debug["tool_responses"].append(
                    {
                        "node": node_name,
                        "tool_call_id": msg.tool_call_id,
                        "tool_name": msg.name,
                        "response": msg.content,
                    }
                )

    @staticmethod
    def _persist_updates(node_output: dict):
        """Copy non-message state updates into the persistent debug state."""
        for key, value in node_output.items():
            if key == "messages":
                continue
            st.session_state.shopping_state[key] = value

    # ------------------------------------------------------------------
    def run(self):
        self.sidebar()
        if not st.session_state.logged_in:
            self.login()
        else:
            self.chat()


if __name__ == "__main__":
    StreamlitShoppingAssistant().run()