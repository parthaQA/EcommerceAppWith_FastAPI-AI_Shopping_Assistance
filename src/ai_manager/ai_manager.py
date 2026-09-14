import json
import os
import asyncio
from dotenv import load_dotenv
from langchain_core.tracers import LangChainTracer
from psycopg_pool import ConnectionPool
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.postgres import PostgresSaver
from src.ai_manager.callbacks import MetricCallBacks
from src.ai_manager.tools import Tools
from src.customers.controller import CustomerController
from src.customers.dtos import CustomerLoginSchema
from src.utils.db import Local_Session
from uuid import uuid4
from pathlib import Path
from nemoguardrails import LLMRails, RailsConfig
from langchain_groq import ChatGroq
from langchain_core.rate_limiters import InMemoryRateLimiter


load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")


groq_rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.25,  # 1 token every 4 seconds
    check_every_n_seconds=0.05,
    max_bucket_size=1,
)


guardrail_llm = ChatGroq(
    model="openai/gpt-oss-safeguard-20b",
    api_key=str(groq_api_key),
    temperature=0,
    rate_limiter=groq_rate_limiter
)
GUARDRAILS_DIR = Path(__file__).parent / "rails"

def get_rails_config():
    config = RailsConfig.from_path(str(GUARDRAILS_DIR))

    rails = LLMRails(config=config, llm=guardrail_llm)

    return rails


# -------------------------------------------------------
# Login & Initialization
# -------------------------------------------------------
customer_controller = CustomerController()
db = Local_Session()

login_response = asyncio.run(
    customer_controller.customer_login_internal(
        body=CustomerLoginSchema(
            mobile=8828162737,
            password="asdf#1234"
        ),
        db=db
    )
)

langsmith = LangChainTracer(
    project_name="ecom-Agent_latest_v3",
)

config = {
    "tags": [
        "shopping",
        "search"
        "add to cart"
        "checkout"
        "payment"
        "order tracking"
    ],
    "run_id": uuid4(),
    "callbacks": [ MetricCallBacks(), langsmith],
    "configurable": {
        "thread_id": login_response.get("customer_id"),
        "user": {
            "access_token": login_response.get("access_token"),
            "customer_id": login_response.get("customer_id"),
            "refresh_token": login_response.get("refresh_token"),
            "mobile": login_response.get("mobile"),
        }
    }
}

print("chat config : ", config)



llm_chat = init_chat_model(
    model="llama3.1:8b",
    model_provider="ollama",
    base_url="http://localhost:11434",
    streaming = True,
)


tools = [
    Tools.get_search_product_tool(customer_id=config["configurable"]["user"]["customer_id"], db=db),
    Tools.add_product_to_cart_llm(customer_id=config["configurable"]["user"]["customer_id"], db=db),
    Tools.get_cart_tool(db=db)

]

tools_by_name = {
    tool.name: tool
    for tool in tools
}

llm_with_tools = llm_chat.bind_tools(tools)
