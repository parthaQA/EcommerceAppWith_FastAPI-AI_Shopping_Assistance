import json
from pprint import pformat
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.ai_manager.agent_config import RunnableConfigBuilder
from src.ai_manager.dtos import ChatRequest, ChatResponse
from src.ai_manager.utils import Utils
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
    state, config = _build(body, user)         # thread_id + customer_id only

    snapshot = await graph.aget_state(config)

    print("next:", snapshot)

    print("-" * 80)
    pending = Utils.pending_interrupt(snapshot)

    print("pending:", pending)

    print("-" * 80)
    print("body:", pformat(body.resume, width=120))
    # Case 1: user clicked Confirm / Cancel
    if body.resume:
        if not pending:
            raise HTTPException(400, "No pending confirmation for this conversation.")
        graph_input = Command(resume={"approved": body.resume.approved})


    else:
        if not body.message:
            raise HTTPException(400, "message or resume is required.")
        if pending:
            await graph.ainvoke(Command(resume={"approved": False}), config)
        graph_input = state

    # Case 2: normal message (possibly while a confirmation is pending)
        graph_input, _ = _build(body, user)     # state with the new message

    async def event_stream():
        try:
            async for mode, data in graph.astream(
                graph_input,                    # fixed
                config=config,
                stream_mode=["messages", "updates"],
            ):
                print("-" * 80)
                print("mode:", mode, "data:", pformat(data, width=120))
                if mode == "updates":
                    # Paused: send the confirmation payload, then stop reading
                    print("-" * 80)
                    print("updates:", pformat(data, width=120))
                    print("-" * 80)
                    print("data :", pformat(data, width=120))
                    if "__interrupt__" in data:
                        yield _sse("confirm", data["__interrupt__"][0].value)
                        continue

                    for node, update in data.items():
                        print("NODE %-22s -> %s", node, pformat(update, width=120))

                if mode == "messages":
                    chunk, metadata = data
                    node = metadata.get("langgraph_node")
                    if node in ("agent", "rails", "product_not_found") and chunk.content:
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