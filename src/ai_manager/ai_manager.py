


import asyncio
from functools import lru_cache

from dotenv import load_dotenv
load_dotenv()

from langchain.chat_models import init_chat_model
from src.ai_manager.tools import Tools
from src.ai_manager.settings import ai_settings
from pathlib import Path
from nemoguardrails import LLMRails, RailsConfig
from langchain_groq import ChatGroq
from langchain_core.rate_limiters import InMemoryRateLimiter



GUARDRAILS_DIR = Path(__file__).parent / "rails"


def build_guardrail_llm() -> ChatGroq:
    return ChatGroq(
        model=ai_settings.GUARDRAIL_MODEL,
        api_key=ai_settings.GROQ_API_KEY,
        temperature=ai_settings.GUARDRAIL_TEMPERATURE,
        rate_limiter=InMemoryRateLimiter(
            requests_per_second=ai_settings.GUARDRAIL_REQUESTS_PER_SECOND,
            check_every_n_seconds=ai_settings.GUARDRAIL_CHECK_INTERVAL,
            max_bucket_size=ai_settings.GUARDRAIL_BUCKET_SIZE,
        ),
    )


@lru_cache(maxsize=1)
def get_rails_config() -> LLMRails:
    return LLMRails(
        config=RailsConfig.from_path(str(GUARDRAILS_DIR)),
        llm=build_guardrail_llm(),
    )


def build_chat_model():
    return init_chat_model(
        model=ai_settings.LLM_MODEL,
        model_provider=ai_settings.LLM_PROVIDER,
        base_url=ai_settings.LLM_BASE_URL,
        streaming=ai_settings.LLM_STREAMING,
    )


tools = [
    Tools.search_product
    # Tools.add_product_to_cart_llm(customer_id=config["configurable"]["user"]["customer_id"], db=db),
    # Tools.get_cart_tool(db=db)
    ]
llm_with_tools = build_chat_model().bind_tools(tools)


