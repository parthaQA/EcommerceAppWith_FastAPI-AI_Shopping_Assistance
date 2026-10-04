import json
from pprint import pformat
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage
from src.ai_manager.agent_config import RunnableConfigBuilder
from src.ai_manager.dtos import ChatRequest, ChatResponse
from src.utils.auth import AuthUser, get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])



def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _build(body: ChatRequest, user: AuthUser):
    config = RunnableConfigBuilder.build_config(
        customer_id=user.customer_id,
        mobile=getattr(user, "mobile", None),
        conversation_id=body.conversation_id,
    )
    state = {"messages": [HumanMessage(content=body.message)]}
    return state, config


# ----------------------------------------------------------------------
# Streaming (Server-Sent Events)
# ----------------------------------------------------------------------
@router.post("")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    graph = request.app.state.graph
    state, config = _build(body, user)

    async def event_stream():
        try:
            async for mode, data in graph.astream(
                state,
                config=config,
                stream_mode=["messages", "updates"],
            ):
                # ---------- Console only: every node's output ----------
                if mode == "updates":
                    for node, update in data.items():
                        print("NODE %-22s -> %s", node, pformat(update, width=120))

                if mode == "messages":
                    chunk, metadata = data
                    if chunk.content and metadata.get("langgraph_node") == "agent":
                        yield _sse("token", {"content": chunk.content})

            yield _sse("done", {})

        except Exception:
            logger.exception("Chat stream failed")
            yield _sse("error", {"message": "Something went wrong. Please try again."})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ----------------------------------------------------------------------
# Non-streaming (returns the final answer only)
# ----------------------------------------------------------------------
@router.post("/sync", response_model=ChatResponse)
async def chat_sync(
    body: ChatRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    graph = request.app.state.graph
    state, config = _build(body, user)

    result = await graph.ainvoke(state, config=config)
    return ChatResponse(reply=result["messages"][-1].content)