


import asyncio
from dotenv import load_dotenv
load_dotenv()

from langchain.chat_models import init_chat_model
from src.ai_manager.tools import Tools
from src.customers.controller import CustomerController
from src.customers.dtos import CustomerLoginSchema
from src.utils.db import Local_Session
from src.ai_manager.settings import settings
from pathlib import Path
from nemoguardrails import LLMRails, RailsConfig
from langchain_groq import ChatGroq
from langchain_core.rate_limiters import InMemoryRateLimiter






# -------------------------------------------------------
# Login & Initialization
# -------------------------------------------------------
customer_controller = CustomerController()


async def _bootstrap_login():
    if settings.AI_LOGIN_MOBILE is None or not settings.AI_LOGIN_PASSWORD:
        raise RuntimeError(
            "Set AI_LOGIN_MOBILE and AI_LOGIN_PASSWORD in .env for AI bootstrap login"
        )

    async with Local_Session() as session:
        return await customer_controller.customer_login_internal(
            body=CustomerLoginSchema(
                mobile=settings.AI_LOGIN_MOBILE,
                password=settings.AI_LOGIN_PASSWORD,
            ),
            db=session,
        )


login_response = asyncio.run(_bootstrap_login())


GUARDRAILS_DIR = Path(__file__).parent / "rails"


def build_guardrail_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.GUARDRAIL_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=settings.GUARDRAIL_TEMPERATURE,
        rate_limiter=InMemoryRateLimiter(
            requests_per_second=settings.GUARDRAIL_REQUESTS_PER_SECOND,
            check_every_n_seconds=settings.GUARDRAIL_CHECK_INTERVAL,
            max_bucket_size=settings.GUARDRAIL_BUCKET_SIZE,
        ),
    )


def get_rails_config() -> LLMRails:
    return LLMRails(
        config=RailsConfig.from_path(str(GUARDRAILS_DIR)),
        llm=build_guardrail_llm(),
    )


def build_chat_model():
    return init_chat_model(
        model=settings.LLM_MODEL,
        model_provider=settings.LLM_PROVIDER,
        base_url=settings.LLM_BASE_URL,
        streaming=settings.LLM_STREAMING,
    )


tools = [
    Tools.search_product
    # Tools.add_product_to_cart_llm(customer_id=config["configurable"]["user"]["customer_id"], db=db),
    # Tools.get_cart_tool(db=db)
    ]
llm_with_tools = build_chat_model().bind_tools(tools)


