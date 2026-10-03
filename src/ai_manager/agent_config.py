# agent/config.py
from uuid import uuid4
from langchain_core.runnables import RunnableConfig
from langchain_core.tracers import LangChainTracer
from src.ai_manager.callbacks import MetricCallBacks
from src.utils.settings import settings


class RunnableConfigBuilder:



    @staticmethod
    def build_config(customer_id: str, mobile: str, conversation_id: str | None = None) -> RunnableConfig:
        thread_id = f"{customer_id}:{conversation_id}" if conversation_id else str(customer_id)
        return {
            "run_id": uuid4(),
            "tags": settings.AGENT_TAGS,
            "recursion_limit": settings.AGENT_RECURSION_LIMIT,
            "callbacks": [
                MetricCallBacks(),
                LangChainTracer(project_name=settings.LANGSMITH_PROJECT),
            ],
            "configurable": {
                "thread_id": thread_id,
                "user": {"customer_id": str(customer_id), "mobile": mobile},
            },
        }

